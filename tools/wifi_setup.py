#!/usr/bin/env python3
"""Provision a C6 over USB once, then save its HTTPS address and certificate pin."""

import argparse
import getpass
import os
import secrets
import sys
import time
from pathlib import Path

from usb_link import Link
from transport import module

PinnedHTTPS = module("net_client").PinnedHTTPS
save_credentials = module("net_client").save_credentials


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", required=True)
    p.add_argument("--ssid", required=True)
    p.add_argument("--password-env", help="read password from this variable instead of prompting")
    p.add_argument(
        "--credentials", type=Path, required=True, help="private local device credentials JSON"
    )
    args = p.parse_args(argv)
    password = (
        os.environ[args.password_env] if args.password_env else getpass.getpass("Wi-Fi password: ")
    )
    if not 1 <= len(args.ssid.encode()) <= 32 or len(password.encode()) > 63:
        raise ValueError("SSID must be 1..32 UTF-8 bytes; password at most 63 bytes")
    link = Link(args.port)
    try:
        info = link.request("net_info")["network"]
        if not info.get("supported"):
            raise RuntimeError(info.get("reason", "network support unavailable; use ESP32-C6"))
        config = {
            "target": "esp32c6",
            "token": secrets.token_hex(32),
            "tls_sha256": info["tls_sha256"],
            "url": None,
        }
        # Save the secret before provisioning so a lost USB response cannot
        # leave a configured device with an unknown token.
        save_credentials(args.credentials, config)
        link.request("net_config", ssid=args.ssid, password=password, token=config["token"])
        password = None
        time.sleep(2)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                info = link.request("net_info", timeout=3)["network"]
                if info.get("url"):
                    config["url"] = info["url"]
                    save_credentials(args.credentials, config)
                    api = PinnedHTTPS(config)
                    try:
                        status = api.call("GET", "/api/status")
                    finally:
                        api.close()
                    if status.get("target") != "esp32c6":
                        raise RuntimeError("unexpected device target")
                    print(f"Wi-Fi and pinned HTTPS verified at {config['url']}")
                    print(f"Private credentials saved to {args.credentials}")
                    return 0
            except (OSError, TimeoutError):
                try:
                    link.reconnect()
                except OSError:
                    pass
            time.sleep(1)
        raise TimeoutError(
            "Wi-Fi/HTTPS not reachable in 60s; credentials are saved for recovery; check SSID, password and LAN access"
        )
    finally:
        link.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, OSError, TimeoutError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
