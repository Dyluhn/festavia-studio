#!/usr/bin/env python3
"""Enroll one Hue bridge/Festavia once; all everyday settings then live in Hue."""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from hue import Bridge
from transport import module

bridge_lib, net, control = [module(n) for n in ("bridge", "net_client", "control")]
NAMES = {
    11: "Festavia · Master",
    12: "Festavia · Colour",
    13: "Festavia · Position",
    14: "Festavia · Palette",
    15: "Festavia · Motion",
    16: "Festavia · Direction",
    17: "Festavia · Shape",
    18: "Festavia · Preset / Apply",
    19: "Festavia · Apply / Save",
}


def discover(bridge, ieee):
    v1 = bridge.request("GET", "/api/" + bridge.config["key"] + "/lights", authorized=False)
    by_v1 = {row["id_v1"]: row for row in bridge.resources("light") if row.get("id_v1")}
    found = {}
    for identifier, light in v1.items():
        unique = light.get("uniqueid", "")
        if unique.split("-")[0].replace(":", "").lower() != ieee:
            continue
        ep = int(unique.rsplit("-", 1)[-1], 16)
        if ep in NAMES and "/lights/" + identifier in by_v1:
            found[ep] = {"v1": identifier, "v2": by_v1["/lights/" + identifier]["id"]}
    return found


def pair(address):
    probe = bridge_lib.probe(address)
    bridge = Bridge(probe)
    input("Press the Hue bridge link button, then press Enter here: ")
    result = bridge.request(
        "POST", "/api", {"devicetype": "festavia_direct#esp32c6"}, authorized=False
    )
    if not result or "success" not in result[0]:
        raise RuntimeError("Hue link authorization was not granted")
    probe["key"] = result[0]["success"]["username"]
    return Bridge(probe)


def join(device, bridge, extpan=None, legacy=False):
    status = device.call("GET", "/api/status")
    if status.get("approved_network"):
        return
    if not status.get("factory_new"):
        raise RuntimeError("ESP32 already belongs to another network; its pairing was preserved")
    config = bridge.request("GET", "/api/" + bridge.config["key"] + "/config", authorized=False)
    bridge.request("POST", "/api/" + bridge.config["key"] + "/lights", {}, authorized=False)
    result = device.call(
        "POST", "/api/command", obj={"id": 18465, "op": "scan", "channel": config["zigbeechannel"]}
    )
    networks = {
        n["extpan"]: n
        for n in result.get("networks", [])
        if n.get("permit_join") and (not extpan or n["extpan"] == extpan)
    }
    if len(networks) != 1:
        raise RuntimeError(
            "Expected one open network on the bridge channel. Close other pairing windows, or select --extpan from an ESP32 scan; no network was joined"
        )
    network = next(iter(networks.values()))
    result = device.call(
        "POST",
        "/api/command",
        obj={
            "id": 18466,
            "op": "join",
            "extpan": network["extpan"],
            "channel": network["channel"],
            "security": int(legacy),
        },
    )
    if not result.get("ok"):
        raise RuntimeError("ESP32 rejected network selection")
    device.close()
    deadline = time.monotonic() + 75
    while time.monotonic() < deadline:
        time.sleep(2)
        try:
            status = device.call("GET", "/api/status", timeout=5)
        except (OSError, TimeoutError):
            device.close()
            continue
        if status.get("approved_network") and status.get("extpan") == network["extpan"]:
            return
    raise RuntimeError("ESP32 did not join the selected network; no fixture settings were changed")


def create_zone(bridge, controls):
    children = [{"rid": row["v2"], "rtype": "light"} for row in controls.values()]
    members = {r["rid"] for r in children}
    required = {controls[ep]["v2"] for ep in range(11, 19)}
    for zone in bridge.resources("zone"):
        previous = {r["rid"] for r in zone.get("children", [])}
        if previous == members:
            return zone["id"]
        if required <= previous <= members:
            bridge.request("PUT", "/clip/v2/resource/zone/" + zone["id"], {"children": children})
            return zone["id"]
    result = bridge.request(
        "POST",
        "/clip/v2/resource/zone",
        {"metadata": {"name": "Festavia Direct", "archetype": "other"}, "children": children},
    )
    return result["data"][0]["rid"]


def create_scene(bridge, zone, controls, slot=1, identifier=None):
    name = f"Festavia preset {slot}"
    existing = None
    scenes = bridge.resources("scene")
    if identifier:
        existing = next(
            (
                scene
                for scene in scenes
                if scene["id"] == identifier and scene.get("group", {}).get("rid") == zone
            ),
            None,
        )
    for scene in scenes:
        if existing:
            break
        if (
            scene.get("group", {}).get("rid") == zone
            and scene.get("metadata", {}).get("name") == name
        ):
            existing = scene
            break
    # Hue requires every zone member in the scene. Parameter lights only
    # receive ON, so recalling a preset cannot replay stale editor values.
    actions = [
        {
            "target": {"rid": row["v2"], "rtype": "light"},
            "action": {
                "on": {"on": ep != 19},
                **({"dimming": {"brightness": slot}} if ep == 18 else {}),
            },
        }
        for ep, row in controls.items()
    ]
    if existing:
        previous = {a["target"]["rid"]: a for a in existing.get("actions", [])}
        members = {a["target"]["rid"] for a in actions}
        if set(previous) != members:
            actions = [previous.get(a["target"]["rid"], a) for a in actions]
            bridge.request("PUT", "/clip/v2/resource/scene/" + existing["id"], {"actions": actions})
        return existing["id"]
    result = bridge.request(
        "POST",
        "/clip/v2/resource/scene",
        {
            "metadata": {"name": name},
            "group": {"rid": zone, "rtype": "zone"},
            "actions": actions,
            "auto_dynamic": False,
        },
    )
    return result["data"][0]["rid"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-credentials", type=Path, required=True)
    parser.add_argument("--bridge", help="bridge LAN address")
    parser.add_argument(
        "--existing-bridge", type=Path, help="optional private enrolled bridge JSON"
    )
    parser.add_argument("--light", help="Festavia Hue v2 resource ID when more than one is paired")
    parser.add_argument("--cap", type=int, default=19, choices=range(1, 101))
    parser.add_argument(
        "--extpan", help="explicit network selection if several pairing windows are open"
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="use ZLL commissioning for an older bridge if Z3 joining fails",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--status", action="store_true", help="read device diagnostics without changing settings"
    )
    mode.add_argument(
        "--disable",
        action="store_true",
        help="stop/disable standalone mode without erasing presets or pairing",
    )
    parser.add_argument("--output", type=Path, default=Path("festavia-direct-setup.json"))
    args = parser.parse_args(argv)
    device = net.PinnedHTTPS(net.credentials(args.device_credentials))

    def command(op, **values):
        response = device.call("POST", "/api/command", obj={"id": 18471, "op": op, **values})
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "Device command failed"))
        return response

    try:
        if args.status:
            print(json.dumps(command("direct_status"), indent=2))
            return
        if args.disable:
            command("direct_enable", enabled=False)
            deadline = time.monotonic() + 90
            while command("direct_status")["owns_player"]:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "Disabled, but durable recovery still needs attention; inspect direct_status before replacing firmware"
                    )
                time.sleep(1)
            print("Standalone mode disabled; pairing and saved presets retained.")
            return
        if args.existing_bridge:
            config = json.loads(args.existing_bridge.read_text())
            config = config.get("data", config).get("bridge", config.get("data", config))
            bridge = Bridge(
                {
                    "address": config.get("address", config.get("host")),
                    "pin": config["pin"],
                    "key": config["key"],
                }
            )
        elif args.bridge:
            bridge = pair(args.bridge)
        else:
            parser.error("Supply --bridge or --existing-bridge")
        join(device, bridge, args.extpan, args.legacy)
        inventory = bridge.inventory()
        if inventory["active_entertainment"]:
            raise RuntimeError("Stop active Hue entertainment before enrollment")
        fixtures = [
            row
            for row in inventory["lights"]
            if row["model"] == "LCX030"
            and row["software"] == "1.163.5"
            and (not args.light or row["id"] == args.light)
        ]
        if len(fixtures) != 1:
            raise RuntimeError("Select exactly one LCX030 / 1.163.5 Festavia with --light")
        fixture = fixtures[0]
        # The ESP32 intentionally has a small TLS socket pool. Reuse it in
        # sequence rather than keeping an idle enrollment connection open.
        device.close()
        raw = control.Device(args.device_credentials, fixture["ieee"], 11)
        try:
            identity = raw.connect()
            if (
                raw.identity.get("5") != fixture["model"]
                or raw.identity.get("16384") != fixture["software"]
            ):
                raise RuntimeError("Bridge and live fixture identity do not match")
            before = raw.snapshot()
            if not 1 <= before["logical_count"] <= 48:
                raise RuntimeError("Detected logical count must be 1-48")
            if (
                fixture.get("reported_pixels")
                and fixture["reported_pixels"] != before["logical_count"]
            ):
                raise RuntimeError("Hue and direct fixture counts do not agree")
        finally:
            raw.close()
        command(
            "direct_configure",
            ieee=fixture["ieee"],
            positions=before["logical_count"],
            cap=args.cap,
            bridge={
                "host": bridge_lib.local_address(bridge.config["address"]),
                "key": bridge.config["key"],
                "pin": bridge.config["pin"],
                "light": fixture["id"],
            },
        )
        command("direct_enable", enabled=True)
        ieee = identity["esp32"]["ieee"]
        controls = discover(bridge, ieee)
        if len(controls) < 8:
            bridge.request("POST", "/api/" + bridge.config["key"] + "/lights", {}, authorized=False)
            deadline = time.monotonic() + 90
            while len(controls) < 8 and time.monotonic() < deadline:
                time.sleep(3)
                controls = discover(bridge, ieee)
        if not all(ep in controls for ep in range(11, 19)):
            command("direct_enable", enabled=False)
            raise RuntimeError(
                "Bridge did not expose the eight required control lights; standalone mode left disabled"
            )
        for ep, row in controls.items():
            bridge.set_light(row["v2"], {"metadata": {"name": NAMES[ep]}})
            if 12 <= ep <= 18:
                bridge.set_light(row["v2"], {"on": {"on": True}})
        state = command("direct_status")
        if not state["saved_slots"]:
            bridge.set_light(
                controls[18]["v2"], {"dimming": {"brightness": 50}, "dynamics": {"duration": 0}}
            )
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not command("direct_status")["saved_slots"]:
                time.sleep(0.5)
            if not command("direct_status")["saved_slots"]:
                raise RuntimeError("Hue save command was not received; no empty scene was created")
        slot = command("direct_status")["saved_slots"][0]
        # Hue may temporarily program light states while storing a scene.
        # Keep the renderer disabled until that Zigbee traffic has settled.
        command("direct_enable", enabled=False)
        zone = create_zone(bridge, controls)
        previous = json.loads(args.output.read_text()) if args.output.is_file() else {}
        scene = create_scene(bridge, zone, controls, slot, previous.get("scene"))
        started = time.monotonic()
        while True:
            state = command("direct_status")
            age = state.get("last_hue_command_age_ms", 0)
            if time.monotonic() - started >= 5 and (age < 0 or age >= 2000):
                break
            if time.monotonic() - started > 30:
                raise RuntimeError(
                    "Scene programming did not become idle; standalone mode remains disabled. Rerun commissioning when the bridge is idle"
                )
            time.sleep(0.5)
        command("direct_enable", enabled=True)
        bridge.set_light(controls[11]["v2"], {"on": {"on": False}})
        state = command("direct_status")
        if state["master"] or state["owns_player"]:
            command("direct_enable", enabled=False)
            raise RuntimeError(
                "Master did not remain off after commissioning; standalone mode left disabled"
            )
        report = {
            "firmware": identity["esp32"]["version"],
            "positions": before["logical_count"],
            "installation_cap": args.cap,
            "controls": {str(ep): {"name": NAMES[ep], **row} for ep, row in controls.items()},
            "home_assistant_required": False,
            "master_left_off": True,
            "zone": zone,
            "scene": scene,
        }
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(
            f"Enrolled {before['logical_count']} pucks and {len(controls)} Hue controls. Master remains OFF."
        )
        print("Everyday configuration is now through those Hue lights and scenes.")
    finally:
        device.close()


if __name__ == "__main__":
    main()
