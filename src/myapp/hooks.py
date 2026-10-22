"""Small cross-platform hook drivers. Full quality gates live in CI."""

import shutil
import subprocess  # nosec B404
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from myapp.checks import RUFF_CONFIG_FILES, check_files, read_index


def run(command: list[str], directory: Path) -> None:
    # All executable names/flags are fixed; filenames are separate argv after --.
    subprocess.run(command, cwd=directory, check=True)  # nosec B603


def pre_commit(names: list[str] | None = None) -> None:
    files = read_index(staged_only=not names, include_ruff_config=True)
    if names:
        files = {
            name: content
            for name, content in files.items()
            if name in names or PurePosixPath(name).name in RUFF_CONFIG_FILES
        }
    check_files(files)
    python_files = [name for name in files if name.endswith(".py")]
    if not python_files:
        return
    ruff = shutil.which("ruff")
    if not ruff:
        raise SystemExit("Ruff executable not found: run uv sync --locked")
    # Check a temporary index snapshot without stashing or rewriting the working tree.
    with TemporaryDirectory(prefix="backend-staged-") as folder:
        root = Path(folder)
        for name, content in files.items():
            path = PurePosixPath(name)
            if not name.endswith(".py") and path.name not in RUFF_CONFIG_FILES:
                continue
            if path.is_absolute() or ".." in path.parts or "\\" in name:
                raise SystemExit("Unsafe staged file path")
            target = root / name
            if not target.resolve().is_relative_to(root):
                raise SystemExit("Unsafe staged file path")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        # Ruff reads only the selected staged Python files; configs retain their relative paths.
        # Independent, read-only commands can safely run together.
        with ThreadPoolExecutor(max_workers=2) as executor:
            for start in range(0, len(python_files), 30):
                batch = python_files[start : start + 30]
                futures = [
                    executor.submit(run, [ruff, *args, "--", *batch], root)
                    for args in (["check"], ["format", "--check"])
                ]
                for future in futures:
                    future.result()


if __name__ == "__main__":
    pre_commit(sys.argv[1:] or None)
