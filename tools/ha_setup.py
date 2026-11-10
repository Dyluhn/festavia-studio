#!/usr/bin/env python3
"""Guided USB installation and private connection-file export for Home Assistant."""

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import uuid

import bootstrap
from transport import module
from usb_link import Link

ROOT = Path(__file__).resolve().parents[1]
net = module("net_client")
spec = importlib.util.spec_from_file_location("first_install", ROOT / "tools/first-install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def choose(title, rows, label):
    if not rows:
        raise ValueError("No saved controllers. Choose New controller for a first installation.")
    if len(rows) == 1:
        print(f"{title}: {label(rows[0])}")
        return rows[0]
    print(title)
    for number, row in enumerate(rows, 1):
        print(f"  {number}. {label(row)}")
    while True:
        answer = input("Choose a number: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(rows):
            return rows[int(answer) - 1]
        print("Enter one of the numbers above, or press Ctrl+C to cancel.")


def required(prompt, default=None):
    while True:
        value = input(prompt).strip() or default
        if value:
            return value
        print("Enter a value, or press Ctrl+C to cancel.")


def select_port(explicit=None):
    from serial.tools.list_ports import comports

    ports = list(comports())
    if explicit:
        if any(p.device == explicit and p.vid == 0x303A for p in ports):
            raise ValueError("Use the C6's USB-to-UART connector; this image uses UART0")
        return explicit
    usable = sorted(
        [p for p in ports if p.vid is not None and p.vid != 0x303A], key=lambda p: p.device
    )
    if usable:
        return choose(
            "USB-to-UART connection", usable, lambda p: f"{p.device} - {p.description}"
        ).device
    print(
        "No USB-to-UART port found. Check the data cable, UART connector, driver and permissions."
    )
    return required("Serial port (or Ctrl+C to stop): ")


def save(path, state, phase=None):
    if phase:
        state["phase"] = phase
    net.save_credentials(path, state)


def sessions(root):
    result = []
    for path in sorted((root / "controllers").glob("*/setup.json")):
        try:
            result.append((path, json.loads(path.read_text())))
        except (ValueError, OSError):
            continue
    return result


def read_status(credentials):
    config = net.credentials(credentials)
    api = net.PinnedHTTPS(config)
    try:
        status = api.call("GET", "/api/status", timeout=8)
        if status.get("target") != "esp32c6" or status.get("firmware") != "hue-mesh-lab":
            raise ValueError("This connection does not identify supported ESP32-C6 firmware")
        if status.get("network", {}).get("elf_sha256") != expected_elf():
            raise ValueError(
                "This controller does not match the supplied HA firmware. For an older HA controller, update from its Firmware entity first. Hue-only Direct uses its own package."
            )
        return config, status
    finally:
        api.close()


def export_connection(credentials, output):
    if credentials.resolve() == output.expanduser().resolve() or output.name == "setup.json":
        raise ValueError(
            "Choose a separate connection file; do not overwrite credentials or setup progress"
        )
    config, status = read_status(credentials)
    config = {k: config[k] for k in ("target", "url", "token", "tls_sha256")}
    net.save_credentials(
        output,
        {
            "schema": 1,
            "integration": "festavia_studio",
            "edition": "home_assistant",
            "device": config,
        },
    )
    print(f"Connection verified at {config['url']} (firmware {status.get('version', 'unknown')}).")
    print(f"Private connection file: {output}")
    print("In HA: Settings → Devices & services → Add integration → Festavia Studio.")
    print("https://my.home-assistant.io/redirect/config_flow_start/?domain=festavia_studio")
    print("Choose your Hue bridge and Festavia, then upload this file. No keys need copying.")
    print("Pairing, palettes and updates are managed inside HA. Do not share the connection file.")


def expected_elf():
    import hashlib

    manifest = json.loads((ROOT / "firmware-release/manifest.json").read_text())
    name = manifest["targets"]["esp32c6"]["app"]
    data = (ROOT / "firmware-release" / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest["sha256"][name]:
        raise ValueError("App image checksum failed")
    return module("ota").app_info(data)["elf_sha256"]


def probe_interrupted_flash(port):
    link = Link(port)
    try:
        status = link.request("status", timeout=8)
    finally:
        link.close()
    expected = expected_elf()
    if (
        status.get("target") != "esp32c6"
        or status.get("firmware") != "hue-mesh-lab"
        or status.get("network", {}).get("elf_sha256") != expected
    ):
        raise ValueError(
            "The intended HA firmware cannot be verified. See USB recovery in docs/INSTALL.md."
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("new", "resume", "export", "status"))
    parser.add_argument("--data-dir", type=Path, default=bootstrap.data_root())
    parser.add_argument("--port")
    parser.add_argument("--ssid")
    parser.add_argument(
        "--credentials",
        type=Path,
        help="adopt an existing HA device credentials file; never flashes",
    )
    parser.add_argument("--output", type=Path, help="private connection JSON to upload in HA")
    parser.add_argument(
        "--dry-run", action="store_true", help="verify the supplied image; no USB, files or network"
    )
    args = parser.parse_args(argv)
    if args.dry_run:
        installer.factory_image()
        print("HA ESP32-C6 image checksum verified. No USB, network or setup changes.")
        return 0
    if args.mode is None:
        args.mode = choose(
            "Festavia Studio · Home Assistant setup",
            [
                ("new", "New controller · USB installation"),
                ("resume", "Continue an interrupted installation"),
                ("export", "Get the HA connection file again · Wi-Fi"),
                ("status", "Check a controller · Wi-Fi"),
            ],
            lambda row: row[1],
        )[0]
    args.data_dir = args.data_dir.expanduser().resolve()
    if args.mode == "new":
        if args.credentials:
            raise ValueError(
                "Choose Export or Check to use an existing credentials file; do not reinstall it"
            )
        installer.factory_image()
        port = select_port(args.port)
        ssid = args.ssid or required("2.4 GHz Wi-Fi network name: ")
        if not 1 <= len(ssid.encode()) <= 32:
            raise ValueError("Wi-Fi name must contain 1–32 UTF-8 bytes")
        print(f"Install Home Assistant firmware on {port}; Wi-Fi: {ssid}.")
        print(
            "This replaces firmware and settings on that ESP32-C6. Existing HA users update in HA."
        )
        if input("Check the board says ESP32-C6. Type INSTALL to flash: ").strip() != "INSTALL":
            print("Cancelled before writing the board or saving setup.")
            return 0
        folder = args.data_dir / "controllers" / uuid.uuid4().hex[:12]
        args.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        folder.mkdir(mode=0o700, parents=True)
        path = folder / "setup.json"
        state = {
            "phase": "flash_started",
            "port": port,
            "ssid": ssid,
            "credentials": str(folder / "device-credentials.json"),
        }
        save(path, state)
        installer.flash_factory(port)
        save(path, state, "flashed")
    elif args.credentials:
        # Existing owners can export without creating another setup record.
        credentials = args.credentials.expanduser().resolve()
        if args.mode == "status":
            config, status = read_status(credentials)
            print(f"Connected: {config['url']} · firmware {status.get('version', 'unknown')}.")
            return 0
        export_connection(
            credentials, args.output or credentials.with_name("festavia-ha-connection.json")
        )
        return 0
    else:
        path, state = choose(
            "Saved controller",
            sessions(args.data_dir),
            lambda row: f"{row[1].get('ssid', 'Wi-Fi')} · {row[0].parent.name} · {row[1]['phase']}",
        )
        folder = path.parent
    credentials = Path(state["credentials"])
    if args.mode == "status":
        config, status = read_status(credentials)
        print(f"Connected: {config['url']} · firmware {status.get('version', 'unknown')}.")
        return 0
    # Ready credentials always use Wi-Fi, regardless of requested mode. Resume
    # never flashes or resets a configured board, including after unpacking a new ZIP.
    config = json.loads(credentials.read_text()) if credentials.exists() else {}
    if not config.get("url"):
        if args.mode == "export":
            raise ValueError(
                "Wi-Fi setup is unfinished. Choose Continue with the C6 connected by UART."
            )
        port = select_port(args.port or state["port"])
        if state["phase"] == "flash_started":
            print(
                "The previous flash was interrupted. Checking the running image without rewriting it..."
            )
            probe_interrupted_flash(port)
            save(path, state, "flashed")
        ssid = args.ssid or state["ssid"]
        if args.mode != "new":
            ssid = required(f"2.4 GHz Wi-Fi name [{ssid}]: ", ssid)
        state.update(port=port, ssid=ssid)
        save(path, state)
        installer.provision(["--port", port, "--ssid", ssid, "--credentials", str(credentials)])
        save(path, state, "wifi_ready")
    output = (
        args.output.expanduser().resolve() if args.output else ROOT / "festavia-ha-connection.json"
    )
    export_connection(credentials, output)
    save(path, state, "complete")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.CalledProcessError) as exc:
        # Network library exceptions omit response bodies/tokens. Do not dump
        # tracebacks or the private file when a connection cannot be verified.
        print(
            f"Setup could not finish ({type(exc).__name__}). Your saved progress is retained.",
            file=sys.stderr,
        )
        if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError):
            print(str(exc), file=sys.stderr)
        print(
            "See docs/INSTALL.md, then Continue. Check UART/driver permissions for USB failures, or Wi-Fi/HTTPS access for network failures.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    except (KeyboardInterrupt, EOFError):
        print("\nSetup stopped. Choose Continue to resume; it never automatically flashes again.")
        raise SystemExit(130) from None
