"""Always check the generator/access rules; use the unit suite for other Python changes."""

import subprocess
import sys
from pathlib import Path


def main() -> None:
    names = sys.argv[1:]
    focused = all(
        name.startswith(
            ("src/myapp/resources/", "src/myapp/modules/tasks/", "tests/unit/test_resources")
        )
        for name in names
    )
    generator_tests = sorted(str(path) for path in Path("tests/unit").glob("test_resources*.py"))
    tests = [*generator_tests, "tests/unit/test_auth.py"] if focused else ["tests/unit"]
    raise SystemExit(
        subprocess.run([sys.executable, "-m", "pytest", *tests, "-q"], check=False).returncode
    )


if __name__ == "__main__":
    main()
