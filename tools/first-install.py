#!/usr/bin/env python3
"""First USB install only. Everyday setup and updates belong to HA."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
from wifi_setup import main as provision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--ssid", required=True)
    parser.add_argument(
        "--credentials", type=Path, default=Path("festavia-device-credentials.json")
    )
    parser.add_argument(
        "--skip-flash", action="store_true", help="provision Wi-Fi on an already flashed board"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="verify factory image only; do not touch USB"
    )
    args = parser.parse_args()
    release = ROOT / "firmware-release"
    manifest = json.loads((release / "manifest.json").read_text())
    target = manifest["targets"]["esp32c6"]
    image = release / target["factory"]
    if hashlib.sha256(image.read_bytes()).hexdigest() != manifest["sha256"][target["factory"]]:
        raise ValueError("Factory image checksum failed")
    if args.dry_run:
        print("ESP32-C6 factory checksum verified; no USB operations performed.")
        return
    if not args.skip_flash:
        print(
            "First installation clears settings and pairing on THIS ESP32. Use HA wireless updates for an existing setup."
        )
        if input("Type ERASE ESP32 to install: ") != "ERASE ESP32":
            raise SystemExit("Cancelled")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "esptool",
                "--chip",
                "esp32c6",
                "--port",
                args.port,
                "--baud",
                "460800",
                "write_flash",
                "--flash_mode",
                target["flash_mode"],
                "--flash_freq",
                target["flash_freq"],
                "--flash_size",
                target["flash_size"],
                "0x0",
                str(image),
            ],
            check=True,
        )
    provision(["--port", args.port, "--ssid", args.ssid, "--credentials", str(args.credentials)])
    print("Continue in HA: Settings → Devices & services → Add integration → Festavia Studio.")


if __name__ == "__main__":
    main()
