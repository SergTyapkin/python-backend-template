from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, ValidationError, create_model
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from myapp.api.responses import Schema
from myapp.resources.fields import FieldAccess, ResourceModel

Operation = Literal["create", "patch", "read"]
ACCESS = {
    "create": {FieldAccess.READ_WRITE, FieldAccess.CREATE_ONLY},
    "patch": {FieldAccess.READ_WRITE},
    "read": {FieldAccess.READ_WRITE, FieldAccess.READ_ONLY},
}


@dataclass(frozen=True)
class FieldOverride:
    include: bool | None = None
    required: bool | None = None
    constraints: dict[str, Any] = field(default_factory=dict)


def patch_schema_extra(schema: dict[str, Any]) -> None:
    # Omission is optional, not nullable. None is an internal unvalidated omission default.
    for definition in schema.get("properties", {}).values():
        definition.pop("default", None)


class PatchSchema(Schema):
    model_config = {"json_schema_extra": patch_schema_extra}


def access_of(info: FieldInfo) -> FieldAccess:
    extra = info.json_schema_extra
    value = (
        extra.get("resource_access", "server_only") if isinstance(extra, dict) else "server_only"
    )
    if not isinstance(value, str):
        raise ValueError("Invalid resource field access declaration")
    return FieldAccess(value)


def generate_schema(
    model: type[ResourceModel],
    operation: Operation,
    overrides: dict[str, FieldOverride] | None = None,
    *,
    allow_access_expansion: bool = False,
) -> type[BaseModel]:
    rules = overrides or {}
    unknown = rules.keys() - model.model_fields.keys()
    if unknown:
        raise ValueError(f"Unknown fields in {model.__name__} {operation}: {sorted(unknown)}")
    fields: dict[str, Any] = {}
    for name, source in model.model_fields.items():
        rule = rules.get(name, FieldOverride())
        permitted = access_of(source) in ACCESS[operation]
        include = permitted if rule.include is None else rule.include
        if include and not permitted and not allow_access_expansion:
            raise ValueError(f"Explicit allow_access_expansion required for {operation}.{name}")
        if not include:
            if rule.required is not None or rule.constraints:
                raise ValueError(f"Excluded field {name} cannot have operation rules")
            continue
        allowed_constraints = {"min_length", "max_length", "ge", "gt", "le", "lt", "pattern"}
        if rule.constraints.keys() - allowed_constraints:
            raise ValueError(f"Unsupported constraints for {name}")
        # Public asdict/create_model API; never edit the entity's FieldInfo or model internals.
        definition = source.asdict()
        attributes = definition["attributes"]
        attributes["json_schema_extra"] = None
        metadata = [*definition["metadata"], *Field(**rule.constraints).metadata]
        annotation: Any = (
            Annotated[(definition["annotation"], *metadata)] if metadata else source.annotation
        )
        original = TypeAdapter(source.rebuild_annotation()).json_schema()
        original = next(
            (item for item in original.get("anyOf", [original]) if item.get("type") != "null"),
            original,
        )
        json_names = {
            "min_length": "minLength",
            "max_length": "maxLength",
            "ge": "minimum",
            "gt": "exclusiveMinimum",
            "le": "maximum",
            "lt": "exclusiveMaximum",
        }
        for constraint, value in rule.constraints.items():
            old = original.get(json_names.get(constraint, constraint))
            if old is not None and (
                (constraint in {"min_length", "ge", "gt"} and value < old)
                or (constraint in {"max_length", "le", "lt"} and value > old)
                or (constraint == "pattern" and value != old)
            ):
                raise ValueError(f"Operation constraints cannot weaken declaration for {name}")
        if source.default is not PydanticUndefined and source.default_factory is None:
            try:
                TypeAdapter(annotation).validate_python(source.default)
            except ValidationError as exc:
                raise ValueError(f"Invalid declared default for {name}") from exc
        required = rule.required
        if (operation == "read" and required is not False) or required is True:
            attributes["default"], attributes["default_factory"] = PydanticUndefined, None
        if operation == "patch" and required is not True:
            attributes.update(default=None, default_factory=None, validate_default=False)
        elif required is False and source.is_required():
            raise ValueError(f"{operation}.{name}: optional field needs a declared default")
        fields[name] = (annotation, Field(**attributes))
    generated = create_model(
        f"{model.__name__}{operation.title()}",
        __base__=PatchSchema if operation == "patch" else Schema,
        __module__=model.__module__,
        **fields,
    )
    for name, definition in generated.model_json_schema().get("properties", {}).items():
        for branch in definition.get("anyOf", [definition]):
            if branch.get("minLength", 0) > branch.get("maxLength", float("inf")):
                raise ValueError(f"Contradictory length constraints for {name}")
            lower = max(
                branch.get("minimum", -float("inf")), branch.get("exclusiveMinimum", -float("inf"))
            )
            upper = min(
                branch.get("maximum", float("inf")), branch.get("exclusiveMaximum", float("inf"))
            )
            if lower > upper or (
                lower == upper
                and (
                    branch.get("exclusiveMinimum") == lower
                    or branch.get("exclusiveMaximum") == upper
                )
            ):
                raise ValueError(f"Contradictory numeric constraints for {name}")
    return generated
