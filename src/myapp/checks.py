"""Fast checks against staged bytes, not unstaged working-tree content."""

import argparse
import json
import re
import shutil

# CLI executes only fixed argv lists, never shell code.
import subprocess  # nosec B404
import tomllib
from pathlib import PurePosixPath


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    git = shutil.which("git")
    if not git:
        raise SystemExit("Git executable not found")
    listing = [git, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
    if args.all:
        listing = [git, "ls-files", "-z"]
    # Executable is resolved from PATH, options are fixed, shell is disabled.
    output = subprocess.check_output(listing)  # nosec B603
    names = output.decode().split("\0")
    errors = []
    for name in filter(None, names):
        if PurePosixPath(name).name == ".env":
            errors.append(f"{name}: environment file must not be tracked")
        # Paths originate in Git and are a single revision argument, never shell code.
        content = subprocess.check_output([git, "show", f":{name}"])  # nosec B603
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


if __name__ == "__main__":
    main()
