import json
import sys

import pytest
from openapi_spec_validator import validate

from myapp.cli import export_openapi, init_project


def test_initialization(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APP_ENVIRONMENT", raising=False)
    (tmp_path / ".env.example").write_text("APP_ENVIRONMENT=development\n", encoding="utf-8")
    init_project()
    env = tmp_path / ".env"
    env.write_text("APP_ENVIRONMENT=development\n# preserved\n", encoding="utf-8")
    init_project()
    assert "preserved" in env.read_text(encoding="utf-8")
    assert (tmp_path / ".local/contracts").is_dir()
    monkeypatch.setenv("APP_ENVIRONMENT", "production")
    with pytest.raises(SystemExit):
        init_project()


def test_openapi_export(tmp_path, monkeypatch):
    output = tmp_path / "contract.json"
    monkeypatch.setattr(sys, "argv", ["export-openapi", "--output", str(output)])
    export_openapi()
    validate(json.loads(output.read_text(encoding="utf-8")))
