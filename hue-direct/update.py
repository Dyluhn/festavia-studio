#!/usr/bin/env python3
"""Verified wireless update, preserving Zigbee, Wi-Fi and saved presets."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from transport import module

net, ota = [module(n) for n in ("net_client", "ota")]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--device-credentials", type=Path, required=True)
    p.add_argument("--release", type=Path, default=Path(__file__).resolve().parent / "release")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    manifest = json.loads((args.release / "manifest.json").read_text())
    image = (args.release / manifest["app"]).read_bytes()
    if hashlib.sha256(image).hexdigest() != manifest["sha256"][manifest["app"]]:
        raise ValueError("App image checksum failed")
    ota.app_info(image)
    if args.dry_run:
        print("OTA image identity, chip, slot size and checksum verified; no upload performed.")
        return
    api = net.PinnedHTTPS(net.credentials(args.device_credentials))
    try:
        state = api.call("POST", "/api/command", obj={"id": 18472, "op": "direct_status"})
        legacy = api.call("POST", "/api/command", obj={"id": 18473, "op": "player_status"})
        if (
            legacy.get("armed")
            or state.get("master")
            or state.get("owns_player")
            or state.get("player", {}).get("armed")
        ):
            raise RuntimeError("Turn Festavia Master off and wait for restoration before updating")
        print(json.dumps(ota.update(api, image, wait_seconds=75), indent=2))
    finally:
        api.close()


if __name__ == "__main__":
    main()
