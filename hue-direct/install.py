#!/usr/bin/env python3
"""First USB installation of Festavia Direct; later updates work over Wi-Fi."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from wifi_setup import main as provision


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", required=True)
    p.add_argument("--ssid", required=True)
    p.add_argument("--credentials", type=Path, default=Path("festavia-device-credentials.json"))
    p.add_argument("--release", type=Path, default=Path(__file__).resolve().parent / "release")
    p.add_argument("--skip-flash", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    manifest = json.loads((args.release / "manifest.json").read_text())
    image = args.release / manifest["factory"]
    if hashlib.sha256(image.read_bytes()).hexdigest() != manifest["sha256"][image.name]:
        raise ValueError("Factory image checksum failed")
    if args.dry_run:
        print("Factory image checksum verified; no USB operations performed.")
        return
    if not args.skip_flash:
        print(
            "Factory installation replaces firmware and settings on this ESP32. For a paired board use update.py instead."
        )
        if input("Type INSTALL FESTAVIA DIRECT to continue: ") != "INSTALL FESTAVIA DIRECT":
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
                "dio",
                "--flash_freq",
                "80m",
                "--flash_size",
                "4MB",
                "0x0",
                str(image),
            ],
            check=True,
        )
    provision(["--port", args.port, "--ssid", args.ssid, "--credentials", str(args.credentials)])
    print(
        "Next: python hue-direct/commission.py --device-credentials "
        + str(args.credentials)
        + " --bridge BRIDGE_IP"
    )


if __name__ == "__main__":
    main()
