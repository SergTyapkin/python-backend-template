"""Report wall-clock checks and loopback health latency, without speed assertions."""

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

COMMANDS = {
    "ruff": ["-m", "ruff", "check", "."],
    "mypy": ["-m", "mypy"],
    "unit": ["-m", "pytest", "tests/unit", "-q"],
    "integration": ["-m", "pytest", "tests/integration", "-q"],
    "pre-commit": [],
    "pool": ["-m", "pytest", "tests/integration", "-k", "pool_concurrency", "-q"],
}


def measure_health(base_url: str, samples: int) -> dict:
    results = {}
    with httpx.Client(base_url=base_url, timeout=5, trust_env=False) as client:
        for path in ("/health/live", "/health/ready"):
            client.get(path).raise_for_status()  # Warm the connection/pool before timing.
            durations = []
            for _ in range(samples):
                start = time.perf_counter()
                client.get(path).raise_for_status()
                durations.append((time.perf_counter() - start) * 1000)
            ordered = sorted(durations)
            results[path] = {
                "samples": samples,
                "p50_ms": round(statistics.median(ordered), 3),
                "p95_ms": round(ordered[max(0, (95 * samples + 99) // 100 - 1)], 3),
            }
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checks", nargs="+", choices=[*COMMANDS, "health"], default=[*COMMANDS, "health"]
    )
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--base-url", help="Running local API, e.g. http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path(".local/benchmark.json"))
    args = parser.parse_args()
    if args.repeat < 1 or args.samples < 1:
        parser.error("repeat and samples must be positive")
    report: dict[str, Any] = {
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "checks": {},
    }
    failed = False
    for name in args.checks:
        if name in {"integration", "pool"} and not os.environ.get("TEST_DATABASE_URL"):
            report["checks"][name] = {"skipped": "TEST_DATABASE_URL not set"}
            continue
        if name == "health":
            if not args.base_url:
                report["checks"][name] = {"skipped": "--base-url not set"}
                continue
            try:
                report["checks"][name] = measure_health(args.base_url, args.samples)
            except httpx.HTTPError as exc:
                report["checks"][name] = {"error": type(exc).__name__}
                failed = True
            continue
        timings, codes = [], []
        command = [sys.executable, *COMMANDS[name]]
        if name == "pre-commit":
            hook_runner = shutil.which("pre-commit")
            if not hook_runner:
                parser.error("pre-commit not installed: run uv sync --locked")
            command = [hook_runner, "run", "--all-files"]
        for _ in range(args.repeat):
            start = time.perf_counter()
            result = subprocess.run(command, check=False)
            timings.append(round(time.perf_counter() - start, 3))
            codes.append(result.returncode)
        report["checks"][name] = {
            "seconds": timings,
            "median_seconds": statistics.median(timings),
            "exit_codes": codes,
        }
        failed |= any(codes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
