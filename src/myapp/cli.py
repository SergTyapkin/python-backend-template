import argparse
import json
import os
import shutil

# Development-only hook installer; no shell execution.
import subprocess  # nosec B404
from pathlib import Path

from myapp.core.config import Settings


def init_project() -> None:
    # Both deployment environment and an existing .env are checked before writing anything.
    if os.environ.get("APP_ENVIRONMENT", "").lower() == "production":
        raise SystemExit("project-init is development-only")
    settings = Settings()
    if settings.environment == "production":
        raise SystemExit("project-init is development-only")
    env = Path(".env")
    if not env.exists():
        with env.open("x", encoding="utf-8") as target:
            target.write(Path(".env.example").read_text(encoding="utf-8"))
        env.chmod(0o600)
    for name in (".local", ".local/contracts", ".local/tmp"):
        Path(name).mkdir(parents=True, exist_ok=True)
    Settings()  # Validate the resulting env, never print its values.
    if Path(".git").exists():
        executable = shutil.which("lefthook")
        if not executable:
            raise SystemExit("Lefthook missing: run uv sync")
        subprocess.run([executable, "install"], check=True)  # nosec B603
    print("Development environment initialized; existing .env preserved.")


def export_openapi() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=".local/contracts/openapi.json")
    args = parser.parse_args()
    from myapp.main import create_app

    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = create_app().openapi()
    path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"OpenAPI exported to {path}")


def make_migration() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("message")
    args = parser.parse_args()
    from alembic import command
    from alembic.config import Config

    command.revision(Config("alembic.ini"), message=args.message, autogenerate=True)
