#!/usr/bin/env python3
"""Prepare private setup tools, then run the Festavia Direct wizard."""

import argparse
import hashlib
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def data_root():
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return base / "FestaviaDirect"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/FestaviaDirect"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "festavia-direct"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if sys.version_info < (3, 10):
        raise RuntimeError("Install Python 3.10 or newer from https://www.python.org/downloads/")
    wizard = ROOT / "hue-direct/setup.py"
    if "--help" in argv or "-h" in argv:
        return subprocess.run([sys.executable, str(wizard), *argv], check=False).returncode
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--data-dir", type=Path, default=data_root())
    args, _ = parser.parse_known_args(argv)
    args.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    tools = args.data_dir / f"tools-py{sys.version_info.major}.{sys.version_info.minor}"
    python = tools / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        print("Preparing Festavia setup tools (first run needs Internet access)...", flush=True)
        venv.EnvBuilder(with_pip=True).create(tools)
    requirements = ROOT / "requirements.txt"
    if not requirements.is_file():
        requirements = ROOT / "hue-direct/requirements.txt"
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = tools / "requirements.sha256"
    if not marker.is_file() or marker.read_text().strip() != digest:
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-r",
                str(requirements),
            ],
            check=True,
        )
        marker.write_text(digest + "\n")
    return subprocess.run([str(python), str(wizard), *argv], check=False).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Setup tools could not start: {exc}", file=sys.stderr)
        print("See hue-direct/GETTING_STARTED.md for Python/venv troubleshooting.", file=sys.stderr)
        raise SystemExit(1) from None
