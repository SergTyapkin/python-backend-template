"""Fast checks against staged bytes, not unstaged working-tree content."""

import argparse
import io
import json
import os
import re
import shutil

# CLI executes only fixed argv lists, never shell code.
import subprocess  # nosec B404
import tomllib
from collections.abc import Mapping
from pathlib import PurePosixPath

RUFF_CONFIG_FILES = {"pyproject.toml", "ruff.toml", ".ruff.toml"}


def git_output(*arguments: str, data: bytes | None = None) -> bytes:
    git = shutil.which("git")
    if not git:
        raise SystemExit("Git executable not found")
    # Fixed executable, separate argv, no shell; object IDs are supplied through stdin.
    return subprocess.check_output([git, *arguments], input=data)  # nosec B603


def read_index(*, staged_only: bool, include_ruff_config: bool = False) -> dict[str, bytes]:
    """Read one consistent index listing and fetch blobs in a single Git process."""
    changed = None
    if staged_only:
        changed = set(
            git_output("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split(b"\0")
        )
    entries: list[tuple[str, bytes]] = []
    for entry in git_output("ls-files", "--stage", "-z").split(b"\0"):
        if not entry:
            continue
        metadata, raw_name = entry.split(b"\t", 1)
        mode, oid, stage = metadata.split()
        name = os.fsdecode(raw_name)
        config = PurePosixPath(name).name in RUFF_CONFIG_FILES
        if changed is not None and raw_name not in changed and not (include_ruff_config and config):
            continue
        if stage != b"0":
            raise SystemExit("Resolve index conflicts before running checks")
        if mode == b"160000":  # Submodules are commits, not blobs.
            continue
        entries.append((name, oid))
    if not entries:
        return {}
    output = io.BytesIO(
        git_output("cat-file", "--batch", data=b"".join(oid + b"\n" for _, oid in entries))
    )
    files = {}
    for name, _ in entries:
        _, kind, size = output.readline().split()
        if kind != b"blob":
            raise SystemExit("Expected a staged file blob")
        files[name] = output.read(int(size))
        if output.read(1) != b"\n":
            raise SystemExit("Invalid git cat-file response")
    return files


def check_files(files: Mapping[str, bytes]) -> None:
    errors = []
    for name, content in files.items():
        if PurePosixPath(name).name == ".env":
            errors.append(f"{name}: environment file must not be tracked")
        try:
            source = content.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", source):
            errors.append(f"{name}: private key detected")
        if re.search(
            r"(?:gh[pousr]_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16}|sk-proj-[A-Za-z0-9_-]{24,})", source
        ):
            errors.append(f"{name}: credential pattern detected")
        try:
            if name.endswith(".toml"):
                tomllib.loads(source)
            if name.endswith(".json"):
                json.loads(source)
            if name.endswith((".yml", ".yaml")):
                import yaml

                yaml.safe_load(source)
            if name.endswith((".toml", ".json", ".yml", ".yaml")):
                if not source.endswith("\n") or any(
                    line.rstrip() != line for line in source.splitlines()
                ):
                    errors.append(f"{name}: trailing whitespace or missing final newline")
        except Exception as exc:
            errors.append(f"{name}: invalid configuration ({type(exc).__name__})")
    if errors:
        raise SystemExit("\n".join(errors))


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--staged", action="store_true")
    mode.add_argument("--all", action="store_true")
    args = parser.parse_args()
    check_files(read_index(staged_only=not args.all))


if __name__ == "__main__":
    main()
