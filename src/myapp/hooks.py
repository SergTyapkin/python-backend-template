"""Small cross-platform hook drivers. Full quality gates live in CI."""

import shutil
import subprocess  # nosec B404
import sys


def run(command: list[str]) -> None:
    # All executable names/flags are fixed; filenames are separate argv after --.
    subprocess.run(command, check=True)  # nosec B603


def pre_commit() -> None:
    git = shutil.which("git")
    if not git:
        raise SystemExit("Git executable not found")
    # The Git executable is resolved and flags are fixed, with shell disabled.
    output = subprocess.check_output(  # nosec B603
        [git, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
    )
    names = output.decode().split("\0")
    python_files = [name for name in names if name.endswith(".py")]
    # Chunk argv to avoid Windows command-line limits in larger projects.
    for start in range(0, len(python_files), 30):
        files = python_files[start : start + 30]
        run([sys.executable, "-m", "ruff", "check", "--", *files])
        run([sys.executable, "-m", "ruff", "format", "--check", "--", *files])
    run([sys.executable, "-m", "myapp.checks", "--staged"])
    if any(name.startswith(("src/myapp/api/", "src/myapp/core/")) for name in python_files):
        run([sys.executable, "-m", "pytest", "tests/unit/test_schemas.py", "-q"])


def pre_push() -> None:
    run([sys.executable, "-m", "myapp.checks", "--all"])
