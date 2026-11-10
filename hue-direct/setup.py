#!/usr/bin/env python3
"""Guided first installation, wireless continuation, updates and diagnostics."""

import argparse
import ipaddress
import json
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import bootstrap
import commission
import install
import update
from usb_link import Link

net, bridge_lib = commission.net, commission.bridge_lib
RELEASE = Path(__file__).resolve().parent / "release"
GUIDE = Path(__file__).resolve().with_name("GETTING_STARTED.md")


def choose(title, rows, label):
    if not rows:
        raise ValueError("No choices are available")
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


def usb_ports():
    from serial.tools.list_ports import comports

    # This image provisions through UART0. A native ESP USB/JTAG connector can
    # flash successfully but cannot provide that firmware console afterward.
    return sorted(
        [p for p in comports() if p.vid is not None and p.vid != 0x303A],
        key=lambda p: p.device,
    )


def select_port(explicit=None):
    if explicit:
        from serial.tools.list_ports import comports

        if any(p.device == explicit and p.vid == 0x303A for p in comports()):
            raise ValueError("Use the board's USB-to-UART port; this image uses UART0 for setup")
        return explicit
    ports = usb_ports()
    if ports:
        return choose(
            "USB-to-UART connection", ports, lambda p: f"{p.device} - {p.description}"
        ).device
    print("No USB-to-UART port found. Use a data cable and the board's UART connector.")
    print("Check its driver and serial permissions; see the guide's USB troubleshooting.")
    return required("Serial port (or Ctrl+C to stop): ")


def discover_bridges():
    addresses = set()
    lock = threading.Lock()
    try:
        from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf

        def found(zeroconf, service_type, name, state_change):
            if state_change != ServiceStateChange.Added:
                return
            info = zeroconf.get_service_info(service_type, name, timeout=1200)
            if info:
                with lock:
                    addresses.update(
                        a for a in info.parsed_addresses() if ipaddress.ip_address(a).version == 4
                    )

        with Zeroconf() as zeroconf:
            browser = ServiceBrowser(zeroconf, "_hue._tcp.local.", handlers=[found])
            time.sleep(3)
            browser.cancel()
    except (ImportError, OSError):
        pass
    bridges = []
    for address in sorted(addresses):
        try:
            bridges.append(bridge_lib.probe(address))
        except (OSError, ValueError, RuntimeError):
            continue
    if bridges:
        return bridges
    try:
        return bridge_lib.discover()
    except OSError:
        return []


def required(prompt, default=None):
    while True:
        value = input(prompt).strip() or default
        if value:
            return value
        print("Enter a value, or press Ctrl+C to cancel.")


def bridge_config(path):
    value = json.loads(path.read_text())
    value = value.get("data", value)
    value = value.get("bridge", value)
    return {
        "address": value.get("address", value.get("host")),
        "pin": value["pin"],
        "key": value["key"],
    }


def get_bridge(args, state, folder):
    previous = args.existing_bridge or state.get("bridge_file")
    if previous and not args.bridge:
        path = Path(previous).expanduser().resolve()
        return commission.Bridge(bridge_config(path)), path
    if args.bridge:
        selected = bridge_lib.probe(args.bridge)
    else:
        print("Looking for Hue bridges on your local network...")
        bridges = discover_bridges()
        if bridges:
            selected = choose(
                "Hue bridge", bridges, lambda b: f"{b['name']} - {b['address']} ({b['model']})"
            )
        else:
            print("Discovery did not cross your network. Find the bridge IP in Hue or your router.")
            selected = bridge_lib.probe(required("Hue bridge IP address: "))
    bridge = commission.pair(selected["address"])
    path = folder / "bridge.json"
    net.save_credentials(path, {"bridge": bridge.config})
    return bridge, path


def select_fixture(bridge, identifier=None):
    inventory = bridge.inventory()
    if inventory["active_entertainment"]:
        raise RuntimeError("Stop Hue entertainment/Sync, then run setup again")
    supported = [
        row
        for row in inventory["lights"]
        if row["model"] == "LCX030" and row["software"] == "1.163.5"
    ]
    if identifier:
        supported = [row for row in supported if row["id"] == identifier]
    if not supported:
        raise RuntimeError(
            "No matching supported Festavia was found. This candidate requires LCX030 / 1.163.5. "
            "Check the selected bridge and the model/software in Hue."
        )
    selected = choose("Festavia to control", supported, lambda row: row["name"])
    if not selected["reachable"]:
        raise RuntimeError("The selected Festavia is unreachable. Restore its Hue connection first")
    return selected


def sessions(data_dir):
    result = []
    for path in sorted((data_dir / "controllers").glob("*/setup.json")):
        try:
            state = json.loads(path.read_text())
            result.append((path, state))
        except (OSError, ValueError):
            continue
    return result


def get_session(args):
    existing = sessions(args.data_dir)
    if args.device_credentials:
        credentials = args.device_credentials.expanduser().resolve()
        for path, state in existing:
            if Path(state.get("credentials", "")).resolve() == credentials:
                return path, state
        return None, {"credentials": str(credentials), "phase": "wifi_ready"}
    if not existing:
        raise RuntimeError(
            "No saved controller found. Choose New controller, or supply --device-credentials"
        )
    return choose(
        "Saved controller",
        existing,
        lambda item: (
            f"{item[1].get('name', item[0].parent.name)} - {item[1].get('phase', 'incomplete')}"
        ),
    )


def save_state(path, state, phase=None):
    if phase:
        state["phase"] = phase
    net.save_credentials(path, state)


def read_status(credentials):
    api = net.PinnedHTTPS(net.credentials(credentials))
    try:
        identity = api.call("GET", "/api/status")
        state = api.call("POST", "/api/command", obj={"id": 18474, "op": "direct_status"})
        if identity.get("target") != "esp32c6" or not state.get("ok"):
            raise RuntimeError("The selected device is not running Festavia Direct on an ESP32-C6")
        return identity, state
    finally:
        api.close()


def print_status(identity, state):
    print(f"Controller: {identity.get('ieee', 'ESP32-C6')}")
    print(f"Pucks detected: {state['positions']}")
    print(f"Hue connection: {'connected' if state['bridge_connected'] else 'not connected'}")
    print(f"Master: {'on' if state['master'] else 'off'}; program: {state['effect']}")
    print(f"Installation brightness ceiling: {state['installation_cap']}%")
    print(f"Status: {state['state']}; {state['error']}")
    player = state.get("player", {})
    reason = player.get("reason")
    if not player.get("playing") and reason in (
        "target_unresponsive",
        "target_unreachable",
        "delivery_failed",
        "hue_watchdog_expired",
        "network_changed",
        "restore_unconfirmed",
    ):
        print(f"Last playback stopped: {reason}")
        print("Check the light's power and radio range, then the controller's Hue connection.")
        print("Playback stays stopped until you deliberately start it again.")


def verify_ready(credentials):
    deadline = time.monotonic() + 20
    while True:
        try:
            _, state = read_status(credentials)
            if state["bridge_connected"]:
                return
        except OSError:
            pass  # Only repeat read-only diagnostics after a transient disconnect.
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "Hue controls were saved, but the C6's bridge connection is not ready. "
                "Check that its Wi-Fi can reach the bridge over HTTPS, then Continue or Check."
            )
        time.sleep(1)


def wireless_update(args, credentials):
    manifest = json.loads((args.release / "manifest.json").read_text())
    identity, _ = read_status(credentials)
    if identity.get("network", {}).get("elf_sha256") == manifest["elf_sha256"] and not identity[
        "network"
    ].get("pending_verify"):
        print("This controller already has the supplied firmware. No upload is needed.")
        return
    update.main(["--device-credentials", str(credentials), "--release", str(args.release)])


def finish_wifi(args, path, state, *, confirm_ssid=True):
    credentials = Path(state["credentials"])
    if credentials.is_file() and json.loads(credentials.read_text()).get("url"):
        return
    if state["phase"] not in ("flashed", "flash_started", "wifi_ready"):
        raise RuntimeError(
            "First installation has not finished. Choose New controller to review flashing"
        )
    port = select_port(args.port or state.get("port"))
    # An interrupted flash is never automatically repeated. Require the
    # expected application to answer before attempting Wi-Fi-only recovery.
    if state["phase"] == "flash_started":
        link = Link(port)
        try:
            if not link.request("direct_status").get("ok"):
                raise RuntimeError("Festavia firmware did not answer; review USB troubleshooting")
        finally:
            link.close()
    ssid = args.ssid or state.get("ssid")
    if not ssid or (confirm_ssid and not args.ssid):
        ssid = required(f"2.4 GHz Wi-Fi name [{state.get('ssid', '')}]: ", state.get("ssid"))
    install.provision(["--port", port, "--ssid", ssid, "--credentials", str(credentials)])
    state.update(port=port, ssid=ssid)
    save_state(path, state, "wifi_ready")


def run_setup(args):
    if args.mode == "new":
        if args.device_credentials:
            raise ValueError(
                "New setup creates its own credentials. Use Continue for an existing file"
            )
        install.factory_image(args.release)
        folder = args.data_dir / "controllers" / uuid.uuid4().hex[:12]
        folder.mkdir(mode=0o700, parents=True)
        path = folder / "setup.json"
        state = {"phase": "prepared", "credentials": str(folder / "device.json")}
        state["port"] = select_port(args.port)
        state["ssid"] = args.ssid or required("2.4 GHz Wi-Fi network name: ")
    else:
        path, state = get_session(args)
        if path is None:
            folder = args.data_dir / "controllers" / uuid.uuid4().hex[:12]
            folder.mkdir(mode=0o700, parents=True)
            path = folder / "setup.json"
        folder = path.parent
    bridge, bridge_file = get_bridge(args, state, folder)
    state["bridge_file"] = str(bridge_file)
    save_state(path, state)
    fixture = select_fixture(bridge, args.light or state.get("light"))
    state.update(light=fixture["id"], name=fixture["name"])
    save_state(path, state)
    first_flash = args.mode == "new" or state["phase"] == "prepared"
    if first_flash:
        install.factory_image(args.release)
        state["port"] = select_port(args.port or state["port"])
        state["ssid"] = args.ssid or state["ssid"]
        if not 1 <= len(state["ssid"].encode()) <= 32:
            raise ValueError("The Wi-Fi name must contain 1-32 UTF-8 bytes")
        print(f"\nInstall on {state['port']}; Wi-Fi: {state['ssid']}")
        print(f"Hue bridge: {bridge.config['address']}; Festavia: {fixture['name']}")
        print("The puck count is detected automatically. Initial brightness ceiling: 19%.")
        print("This replaces firmware and settings on the selected ESP32-C6.")
        if input("Check the board says ESP32-C6. Type INSTALL to flash: ").strip() != "INSTALL":
            print("Cancelled before flashing. The bridge authorization was saved for the next run.")
            return
        save_state(path, state, "flash_started")
        install.flash_factory(state["port"], args.release)
        save_state(path, state, "flashed")
    finish_wifi(args, path, state, confirm_ssid=not first_flash)
    credentials = Path(state["credentials"])
    _, current = read_status(credentials)
    if current["master"] or current["owns_player"] or current["player"]["armed"]:
        raise RuntimeError(
            "Turn Festavia Master off in Hue and wait for restoration, then Continue"
        )
    # Resume uses the existing ceiling; it must not reset somebody's deliberate
    # installation limit or require editing command-line percentages.
    cap = 19 if first_flash else current["installation_cap"]
    result_file = folder / "hue-setup.json"
    commission.main(
        [
            "--device-credentials",
            str(credentials),
            "--existing-bridge",
            str(bridge_file),
            "--light",
            fixture["id"],
            "--cap",
            str(cap),
            "--output",
            str(result_file),
            *(["--legacy"] if args.legacy else []),
            *(["--extpan", args.extpan] if args.extpan else []),
        ]
    )
    result = json.loads(result_file.read_text())
    state.update(positions=result["positions"], report=str(result_file))
    save_state(path, state, "configured")
    verify_ready(credentials)
    save_state(path, state, "complete")
    print(f"\nReady: {result['positions']} pucks, {len(result['controls'])} Hue controls.")
    print("Open Festavia Direct in Hue. Its preset scene is ready; Master is left OFF.")
    print("Use the guide for color editing and the first 9% preview.")
    print(f"Keep your private setup folder for wireless updates: {folder}")
    print(f"Guide: {GUIDE}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("new", "resume", "update", "status"))
    parser.add_argument("--data-dir", type=Path, default=bootstrap.data_root())
    parser.add_argument("--device-credentials", type=Path)
    bridge = parser.add_mutually_exclusive_group()
    bridge.add_argument("--bridge", help="manual bridge address if discovery cannot cross a VLAN")
    bridge.add_argument("--existing-bridge", type=Path, help="reuse a private bridge enrollment")
    parser.add_argument("--light", help="optional Hue light ID; ordinary setup offers names")
    parser.add_argument("--port", help="optional UART port override")
    parser.add_argument(
        "--ssid", help="optional 2.4 GHz network name; password is prompted privately"
    )
    parser.add_argument(
        "--legacy", action="store_true", help="explicit ZLL joining for an older bridge"
    )
    parser.add_argument(
        "--extpan", help="explicit network selection when several pairing windows are open"
    )
    parser.add_argument("--release", type=Path, default=RELEASE)
    parser.add_argument(
        "--dry-run", action="store_true", help="verify images without USB/network changes"
    )
    args = parser.parse_args(argv)
    args.data_dir = args.data_dir.expanduser().resolve()
    if args.dry_run:
        install.factory_image(args.release)
        update.main(["--device-credentials", "UNUSED", "--release", str(args.release), "--dry-run"])
        print("Guided setup images verified; no device was opened or changed.")
        return
    if args.mode is None:
        args.mode = choose(
            "Festavia Direct setup",
            ["new", "resume", "update", "status"],
            lambda mode: {
                "new": "New controller - first USB installation",
                "resume": "Continue/repair saved setup",
                "update": "Update firmware over Wi-Fi",
                "status": "Check a controller without changing it",
            }[mode],
        )
    if args.mode in ("status", "update"):
        _, state = get_session(args)
        credentials = Path(state["credentials"])
        if args.mode == "status":
            print_status(*read_status(credentials))
        else:
            wireless_update(args, credentials)
        return
    run_setup(args)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled. Saved setup can be continued without an automatic reflash.")
        raise SystemExit(130) from None
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"\nSetup stopped: {exc}", file=sys.stderr)
        print(f"Guide and recovery steps: {GUIDE}", file=sys.stderr)
        raise SystemExit(1) from None
