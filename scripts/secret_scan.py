"""Run a pinned, checksum-verified Gitleaks CLI without a paid GitHub Action."""

import argparse
import hashlib
import io
import platform
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "8.30.1"
CHECKSUMS = {
    "darwin_arm64.tar.gz": "b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5",
    "darwin_x64.tar.gz": "dfe101a4db2255fc85120ac7f3d25e4342c3c20cf749f2c20a18081af1952709",
    "linux_arm64.tar.gz": "e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080",
    "linux_x64.tar.gz": "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb",
    "windows_x64.zip": "d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--history", action="store_true")
    mode.add_argument("--staged", action="store_true")
    args = parser.parse_args()
    system = platform.system().lower()
    architecture = "arm64" if platform.machine().lower() in {"aarch64", "arm64"} else "x64"
    suffix = ".zip" if system == "windows" else ".tar.gz"
    archive = f"{system}_{architecture}{suffix}"
    if archive not in CHECKSUMS:
        raise SystemExit("Unsupported Gitleaks platform; install the CLI manually")
    folder = Path(".local/tools") / f"gitleaks-{VERSION}"
    executable = folder / ("gitleaks.exe" if system == "windows" else "gitleaks")
    if not executable.exists():
        url = f"https://github.com/gitleaks/gitleaks/releases/download/v{VERSION}/gitleaks_{VERSION}_{archive}"
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != CHECKSUMS[archive]:
            raise SystemExit("Gitleaks archive checksum mismatch")
        if suffix == ".zip":
            with zipfile.ZipFile(io.BytesIO(data)) as package:
                binary = package.read(executable.name)
        else:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as package:
                member = package.extractfile(executable.name)
                if member is None:
                    raise SystemExit("Gitleaks binary missing")
                binary = member.read()
        folder.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(binary)
        executable.chmod(0o700)
    command = [str(executable.resolve()), "git", ".", "--redact", "--no-banner"]
    command += ["--log-opts=--all"] if args.history else ["--staged"]
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
