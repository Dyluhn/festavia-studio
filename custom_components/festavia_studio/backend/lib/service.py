"""Durable installation settings, guided commissioning and both control paths."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import re
import threading
import time

from .bridge import Bridge, bridge_points, discover, local_address, probe, writable_state
from .control_core import Device
from .hue_mesh import NetworkLink
from .net_client import PinnedHTTPS, credentials, save_credentials
from .player import color, compile_scene
from .studio import Studio
from .festavia import is_festavia
from .errors import RecoveryPending

ROOT = Path(__file__).resolve().parent
RELEASE = ROOT.parent / "release"
CAPABILITIES = json.loads((ROOT / "capabilities.json").read_text())["native_profiles"]
DEFAULT_PALETTES = {
    "Christmas": ["#ff2020", "#00ff00", "#ffdda0"],
    "Candy cane": ["#ff2020", "#fff1d6"],
    "Rainbow": ["#ff0000", "#ff8000", "#ffff00", "#00ff00", "#00ffff", "#0000ff", "#9900ff"],
    "Winter": ["#80dfff", "#e4f4ff", "#4040ff"],
    "Warm whites": ["#ffbb66", "#ffdda0", "#fff1d6", "#ffffff"],
    "Halloween": ["#ff6600", "#9900ff", "#40ff00"],
}


def bounded(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"Value must be between {low} and {high}")
    return value


class Installation:
    def __init__(self, folder, *, brightness_limit=100):
        self.folder = Path(folder).resolve()
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.file = self.folder / "installation.json"
        self.data = (
            json.loads(self.file.read_text())
            if self.file.exists()
            else {"schema": 1, "selected": [], "mode": "bridge"}
        )
        self.limit = bounded(brightness_limit, 1, 100)
        self.lock = threading.RLock()
        self.studio = None
        self.inventory_cache = None
        self.inventory_at = float("-inf")
        self.pending_bridge = None
        self.bridge_journal = self.folder / "bridge-session.json"
        self.bridge_library = self.folder / "bridge-presets.json"
        self.bridge_scene = None
        self.device_path = self.folder / "esp" / "credentials.json"
        self.active_ota = False
        self.palette_library = self.folder / "color-palettes.json"
        # Startup never resumes playback. Firmware owns native recovery. A bridge
        # lease is recovered before any new write, including after a container restart.

    def close(self):
        if self.studio:
            self.studio.close()

    def recovery_pending(self):
        if self.bridge_journal.exists():
            return True
        journal = self.device_path.parent / "player-session.json"
        if journal.exists():
            try:
                return not json.loads(journal.read_text()).get("restored", False)
            except (OSError, ValueError):
                return True
        return False

    def restore(self, *, allow_missing=False):
        if (
            self.data.get("mode") == "native"
            and self.device_path.exists()
            and self.recovery_pending()
        ):
            self.native_studio().call("stop", {})
        self.bridge_restore(allow_missing=allow_missing)

    def save(self):
        save_credentials(self.file, self.data)

    def color_palettes(self):
        """Colors only; legacy scene presets retain all their motion settings."""
        if not self.palette_library.exists():
            return copy.deepcopy(DEFAULT_PALETTES)
        try:
            saved = json.loads(self.palette_library.read_text())
        except (OSError, ValueError):
            return copy.deepcopy(DEFAULT_PALETTES)
        if not isinstance(saved, dict):
            return copy.deepcopy(DEFAULT_PALETTES)
        return {
            name: [c.lower() for c in colors]
            for name, colors in saved.items()
            if isinstance(name, str)
            and 1 <= len(name.strip()) <= 60
            and name.casefold() != "custom"
            and isinstance(colors, list)
            and 1 <= len(colors) <= 27
            and all(isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in colors)
        }

    def bridge(self):
        if not self.data.get("bridge"):
            raise ValueError("Connect your Hue bridge first")
        return Bridge(self.data["bridge"])

    def inventory(self, fresh=False):
        if fresh or self.inventory_cache is None or time.monotonic() - self.inventory_at > 60:
            self.inventory_cache = self.bridge().inventory()
            self.inventory_at = time.monotonic()
        return self.inventory_cache

    def selected(self, fresh=False):
        by_id = {l["id"]: l for l in self.inventory(fresh)["lights"] if is_festavia(l)}
        ids = self.data.get("selected", [])
        if not ids or any(i not in by_id for i in ids):
            raise ValueError("Choose your Festavia lights from the current inventory")
        return [by_id[i] for i in ids]

    def esp_status(self):
        if not self.device_path.exists():
            return None
        client = PinnedHTTPS(credentials(self.device_path))
        try:
            return client.call("GET", "/api/status", timeout=4)
        finally:
            client.close()

    def native_studio(self):
        if self.data.get("mode") != "native" or not self.data.get("native"):
            raise ValueError("Select a verified native fixture first")
        if self.studio is None:
            profile = {
                **self.data["native"],
                "credentials": str(self.device_path),
                "brightness_limit": self.limit,
                "gradient_inventory_provider": lambda: self.inventory(True),
            }
            self.studio = Studio(profile)
        return self.studio

    def summary(self):
        bridge = self.data.get("bridge")
        lights, error = [], None
        if bridge:
            try:
                lights = [
                    {k: v for k, v in light.items() if k != "state"}
                    for light in self.inventory()["lights"]
                    if is_festavia(light)
                ]
            except (OSError, RuntimeError, ValueError, KeyError):
                error = "Bridge unavailable. Check its address and network access, then reconnect if needed."
        eligible = {l["id"] for l in lights}
        saved = self.data.get("selected", [])
        selection_valid = all(identifier in eligible for identifier in saved)
        return {
            "bridge": {k: bridge[k] for k in ("address", "id", "name", "model")}
            if bridge
            else None,
            "lights": lights,
            "inventory_error": error,
            "selected": saved if selection_valid else [],
            "selection_requires_update": bool(saved) and not selection_valid,
            "mode": self.data.get("mode", "bridge"),
            "native": self.data.get("native"),
            "esp_configured": self.device_path.exists(),
            "brightness_limit": self.limit,
            "recovery_pending": self.recovery_pending(),
        }

    def check_scene(self, scene):
        scene = copy.deepcopy(scene)
        bounded(scene.get("brightness", 10), 0, self.limit)
        colors = scene.get("colors", ["#ff2020", "#00ff00", "#9900ff"])
        if not isinstance(colors, list) or not 1 <= len(colors) <= 27:
            raise ValueError("Choose 1–27 colors")
        for item in colors:
            color(item)
        return scene

    def control(self, op, data):
        with self.lock:
            if self.active_ota:
                raise RuntimeError("A firmware update is in progress")
            if op in ("save_palette", "delete_palette"):
                name = data["name"].strip()
                if not 1 <= len(name) <= 60 or name.casefold() == "custom":
                    raise ValueError("Choose a palette name other than Custom")
                palettes = self.color_palettes()
                if op == "save_palette":
                    colors = data["colors"]
                    limit = 9 if self.data.get("mode") == "native" else 27
                    if not isinstance(colors, list) or not 1 <= len(colors) <= limit:
                        raise ValueError("Invalid palette size")
                    for item in colors:
                        if not isinstance(item, str) or not re.fullmatch(r"#[a-fA-F0-9]{6}", item):
                            raise ValueError("Palette colors must be #RRGGBB")
                    if self.data.get("mode") == "native":
                        tones = {max(int(c[i : i + 2], 16) for i in (1, 3, 5)) for c in colors}
                        if len(tones) != 1 or 0 in tones:
                            raise ValueError("Native palette colors share a nonzero tone")
                    palettes[name] = [c.lower() for c in colors]
                else:
                    palettes.pop(name, None)
                save_credentials(self.palette_library, palettes)
                return {"saved" if op == "save_palette" else "deleted": name}
            if op in ("play", "uniform", "save"):
                targets = self.selected(fresh=op in ("play", "uniform"))
                if self.data.get("mode") == "native" and (
                    len(targets) != 1
                    or targets[0].get("ieee") != self.data.get("native", {}).get("ieee")
                ):
                    raise ValueError("Select your Festavia again before native playback")
            if self.data.get("mode") == "native":
                studio = self.native_studio()
                if op in ("play", "save"):
                    scene = self.check_scene(data["scene"])
                    scene["positions"] = self.data["native"]["positions"]
                    # Validate actual encoded peak too, including arbitrary frame banks.
                    from .player import fit_scene

                    scene = fit_scene(scene)
                    samples, _ = compile_scene(scene, list(range(1, len(scene["layout"]) + 1)))
                    import struct

                    peak = (
                        max(bytes.fromhex(s)[2] / 254 * 100 for s in samples)
                        if scene["layout_mode"] == "pucks"
                        else max(
                            (struct.unpack_from("<H", bytes.fromhex(s), p)[0] >> 5) / 2047 * 100
                            for s in samples
                            for p in range(8, len(bytes.fromhex(s)), 7)
                        )
                    )
                    if peak > self.limit + 0.21:
                        raise ValueError("Encoded scene exceeds the configured brightness limit")
                    data = {**data, "scene": scene}
                if op == "uniform":
                    state = dict(data["state"])
                    bounded(
                        state.get("brightness", min(25, round(self.limit * 2.54))),
                        0,
                        math.floor(self.limit * 2.54),
                    )
                    if state.get("on") is True and "brightness" not in state:
                        state["brightness"] = min(25, math.floor(self.limit * 2.54))
                    data = {"state": state}
                result = studio.call(op, data)
                return result
            return self.bridge_control(op, data)

    def bridge_restore(self, *, off=False, allow_missing=False):
        if not self.bridge_journal.exists():
            return {"restored": True}
        journal = json.loads(self.bridge_journal.read_text())
        if journal["bridge_id"] != self.data["bridge"]["id"]:
            raise RuntimeError("Recovery belongs to another bridge; reconnect that bridge first")
        bridge = self.bridge()
        if self.inventory(True)["active_entertainment"]:
            raise RuntimeError("Stop Hue Sync before restoring bridge control")
        now = {l["id"]: l["state"] for l in self.inventory()["lights"]}
        missing = set(journal["before"]) - now.keys()
        if missing and not allow_missing:
            raise RecoveryPending("Captured lights are missing; use Recover removed lights")
        expected_power = {}
        for identifier, state in journal["before"].items():
            if identifier not in now:
                continue
            preserve_off = off or not now[identifier]["on"]["on"]
            expected_power[identifier] = state["on"]["on"] and not preserve_off
            bridge.set_light(identifier, {"on": {"on": False}})
            appearance = {k: v for k, v in state.items() if k != "on"}
            if appearance:
                bridge.set_light(identifier, appearance)
            if state["on"]["on"] and not preserve_off:
                bridge.set_light(identifier, {"on": {"on": True}})
        # Readback power before retiring the durable lease. Hue may gamut-map
        # colors, so exact Zigbee restoration is reserved for the native path.
        actual = {l["id"]: l["state"] for l in self.inventory(True)["lights"]}
        for identifier, expected in expected_power.items():
            if identifier not in actual or actual[identifier]["on"]["on"] != expected:
                raise RuntimeError("Hue did not confirm restored power; recovery remains saved")
        self.bridge_journal.unlink()
        return {"restored": True, "missing_lights_discarded": len(missing)}

    def bridge_control(self, op, data):
        presets = (
            json.loads(self.bridge_library.read_text())
            if self.bridge_library.exists()
            else {
                "Ordered colors": {
                    "layout_mode": "pucks",
                    "effect": "static",
                    "colors": ["#ff2020", "#00ff00", "#9900ff"],
                    "brightness": 10,
                }
            }
        )
        if op == "status":
            pending = self.bridge_journal.exists()
            return {
                "scene": self.bridge_scene,
                "presets": presets,
                "player": {
                    "state": "applied" if pending else "ready",
                    "reason": "bridge_static_scene",
                    "playing": pending,
                    "acked": 0,
                    "failures": 0,
                    "transport": "palette",
                    "frames": 1,
                },
                "limits": {"logical_positions": sum(l["gradient_points"] for l in self.selected())},
            }
        if op in ("save", "delete"):
            name = str(data.get("name", "")).strip()
            if name.casefold() == "custom":
                raise ValueError("Custom is reserved for unsaved colors")
            if not 1 <= len(name) <= 60:
                raise ValueError("Name must be 1–60 characters")
            if op == "save":
                presets[name] = self.check_scene(data["scene"])
            else:
                presets.pop(name, None)
            save_credentials(self.bridge_library, presets)
            return {"saved": name}
        if op == "stop":
            return self.bridge_restore(off=bool(data.get("off")))
        if op == "uniform":
            state = data["state"]
            if set(state) - {"on", "brightness", "mirek", "fade", "effect"}:
                raise ValueError("Unsupported bridge state")
            if "on" in state and type(state["on"]) is not bool:
                raise ValueError("Power must be true or false")
            self.bridge_restore(off=state.get("on") is False)
            level = bounded(
                state.get("brightness", min(25, math.floor(self.limit * 2.54))),
                0,
                math.floor(self.limit * 2.54),
            )
            if "mirek" in state:
                bounded(state["mirek"], 153, 500)
            inventory = self.inventory(True)
            if inventory["active_entertainment"]:
                raise RuntimeError("Stop Hue Sync before changing these lights")
            lights = self.selected()
            if state.get("on", True) and self.limit < 100 and any(not l["dimming"] for l in lights):
                raise ValueError("A selected light cannot dim to the configured brightness limit")
            for light in lights:
                body = {"on": {"on": bool(state.get("on", True))}}
                if body["on"]["on"]:
                    if not light["dimming"] and self.limit < 100:
                        raise ValueError("This light cannot dim to the configured brightness limit")
                    if "effects" in light["state"]:
                        body["effects"] = {"effect": "no_effect"}
                    if light["dimming"]:
                        body["dimming"] = {"brightness": level / 254 * 100}
                    if "mirek" in state and light["white"]:
                        value = int(bounded(state["mirek"], 153, 500))
                        schema = light["state"].get("color_temperature", {}).get("mirek_schema", {})
                        body["color_temperature"] = {
                            "mirek": max(
                                schema.get("mirek_minimum", 153),
                                min(schema.get("mirek_maximum", 500), value),
                            )
                        }
                self.bridge().set_light(light["id"], body)
            self.inventory_at = float("-inf")
            return {"applied": True}
        if op != "play":
            raise ValueError("Unknown action")
        scene = self.check_scene(data["scene"])
        if scene.get("effect", "static") != "static" or data.get("seconds", 0) != 0:
            raise ValueError(
                "Bridge mode supports persistent static scenes. Use verified ESP32 mode for motion and timed playback."
            )
        lights = self.selected(True)
        if self.inventory()["active_entertainment"]:
            raise RuntimeError("Stop Hue Sync before playing a scene")
        if not all(l["reachable"] for l in lights):
            raise RuntimeError("A selected light is unreachable")
        if (
            scene.get("brightness", 10) > 0
            and self.limit < 100
            and any(not l["dimming"] for l in lights)
        ):
            raise ValueError("A selected light cannot dim to the configured brightness limit")
        if any(l["state"].get("dynamics", {}).get("status") not in (None, "none") for l in lights):
            raise RuntimeError("Stop the dynamic Hue scene before capturing a static Studio scene")
        if self.bridge_journal.exists():
            captured = json.loads(self.bridge_journal.read_text())
            if captured.get("bridge_id") != self.data["bridge"]["id"] or set(
                captured["before"]
            ) != {l["id"] for l in lights}:
                raise RecoveryPending("Restore the captured lights before changing the selection")
        if not self.bridge_journal.exists():
            before = {l["id"]: writable_state(l["state"]) for l in lights}
            save_credentials(
                self.bridge_journal, {"bridge_id": self.data["bridge"]["id"], "before": before}
            )
        palettes = bridge_points(lights, scene["colors"], scene.get("reverse", False))
        try:
            for light, palette in zip(lights, palettes):
                body = {"on": {"on": scene.get("brightness", 10) > 0}}
                if "effects" in light["state"]:
                    body["effects"] = {"effect": "no_effect"}
                if light["dimming"]:
                    body["dimming"] = {"brightness": scene.get("brightness", 10)}
                if light["color"]:
                    if light["gradient_points"] > 1:
                        body["gradient"] = {
                            "points": [
                                {"color": {"xy": dict(zip(("x", "y"), color(c)))}} for c in palette
                            ]
                        }
                    else:
                        body["color"] = {"xy": dict(zip(("x", "y"), color(palette[0])))}
                self.bridge().set_light(light["id"], body)
            self.bridge_scene = scene
            self.inventory_at = float("-inf")
            return {"applied": len(lights)}
        except BaseException:
            self.bridge_restore()
            raise

    def setup(self, op, data):
        with self.lock:
            if op == "discover":
                return {"bridges": discover()}
            if op == "probe":
                self.pending_bridge = probe(data["address"])
                return self.pending_bridge
            if op == "pair":
                if not self.pending_bridge or self.pending_bridge["id"] != data.get("id"):
                    raise ValueError("Find and verify the bridge first")
                if self.bridge_journal.exists() or self.data.get("mode") == "native":
                    raise RuntimeError(
                        "Stop and restore playback before replacing bridge authorization"
                    )
                candidate = dict(self.pending_bridge)
                candidate["key"] = Bridge(candidate).pair()
                Bridge(
                    candidate
                ).inventory()  # API v2 required; old round bridges are not supported.
                self.data["bridge"] = candidate
                self.data["selected"] = []
                self.inventory_cache = None
                self.save()
                return {"paired": True}
            if op == "refresh":
                self.inventory(True)
                return self.summary()
            if op == "device":
                config = data["credentials"]
                if set(config) - {"target", "url", "token", "tls_sha256"}:
                    raise ValueError("Unexpected device credential fields")
                from urllib.parse import urlsplit

                parsed = urlsplit(config["url"])
                local_address(parsed.hostname or "")
                if parsed.port not in (None, 443):
                    raise ValueError("ESP32 HTTPS must use port 443")
                if not all(
                    isinstance(config.get(k), str) and re.fullmatch(r"[a-fA-F0-9]{64}", config[k])
                    for k in ("token", "tls_sha256")
                ):
                    raise ValueError("Invalid credential file")
                client = PinnedHTTPS(config)
                try:
                    status = client.call("GET", "/api/status")
                    if status.get("target") != "esp32c6":
                        raise ValueError("This package needs an ESP32-C6")
                    player = client.call("POST", "/api/command", obj={"op": "player_status"})
                    if player.get("armed") and not data.get("inspect_only"):
                        raise RuntimeError("Stop the existing player before importing this ESP32")
                finally:
                    client.close()
                if self.data.get("mode") == "native":
                    raise RuntimeError("Choose bridge mode before replacing an ESP32")
                if not player.get("armed"):
                    save_credentials(self.device_path, config)
                return {"connected": True, "armed": bool(player.get("armed"))}
            if op in ("esp-status", "scan", "join"):
                link = NetworkLink(self.device_path)
                try:
                    if op == "esp-status":
                        return link.request("status")
                    if op == "scan":
                        return link.request("scan")
                    status = link.request("status")
                    if status.get("approved_network"):
                        raise ValueError(
                            "ESP32 is already joined; its existing network was preserved"
                        )
                    extpan = data["extpan"].lower()
                    if not re.fullmatch(r"[a-f0-9]{16}", extpan):
                        raise ValueError("Choose an extended PAN from the scan")
                    channel = int(bounded(data["channel"], 11, 26))
                    return link.request(
                        "join",
                        extpan=extpan,
                        channel=channel,
                        security=int(data.get("legacy", False)),
                    )
                finally:
                    link.close()
            if op == "select":
                if self.recovery_pending():
                    raise RecoveryPending(
                        "Restore the captured installation before changing fixtures"
                    )
                ids = data["ids"]
                if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
                    raise ValueError("Choose distinct lights in playback order")
                known = {l["id"]: l for l in self.inventory(True)["lights"]}
                if any(i not in known for i in ids):
                    raise ValueError("A light is no longer in the bridge inventory")
                if any(not is_festavia(known[i]) for i in ids):
                    raise ValueError("Festavia Studio controls Festavia lights only")
                if self.data.get("mode") == "native":
                    self.native_studio().call("stop", {})
                self.bridge_restore()
                mode = data.get("mode", "bridge")
                if mode not in ("bridge", "native"):
                    raise ValueError("Choose bridge or native mode")
                native = None
                if mode == "native":
                    if len(ids) != 1:
                        raise ValueError(
                            "One native fixture plays per ESP32; bridge scenes can include multiple lights"
                        )
                    light = known[ids[0]]
                    profiles = [p for p in CAPABILITIES if p["model"] == light["model"]]
                    if not profiles or not light["ieee"]:
                        raise ValueError(
                            "Native mapping is currently verified for LCX030. Use bridge mode for this model."
                        )
                    device = Device(str(self.device_path), light["ieee"], profiles[0]["endpoint"])
                    try:
                        identity = device.connect()
                        before = device.snapshot()
                    finally:
                        device.close()
                    accepted = next(
                        (
                            p
                            for p in profiles
                            if p["model"] == identity["identity"].get("5")
                            and p["software"] == identity["identity"].get("16384")
                            and before["logical_count"] in p["logical_counts"]
                        ),
                        None,
                    )
                    if accepted is None:
                        raise ValueError(
                            "This model/firmware/count combination needs calibration; bridge mode remains available"
                        )
                    native = {
                        "ieee": light["ieee"],
                        "endpoint": accepted["endpoint"],
                        "extpan": identity["esp32"]["extpan"],
                        "model": light["model"],
                        "positions": before["logical_count"],
                    }
                self.data.update(selected=ids, mode=mode, native=native)
                self.close()
                self.studio = None
                self.save()
                return self.summary()
            if op == "update":
                if self.data.get("mode") == "native":
                    self.native_studio().call("stop", {})
                from .ota import update

                # Only bundled, checksum-verified images. No arbitrary URL/code upload.
                import hashlib

                manifest = json.loads((RELEASE / "manifest.json").read_text())
                name = manifest["targets"]["esp32c6"]["app"]
                image = RELEASE / name
                if hashlib.sha256(image.read_bytes()).hexdigest() != manifest["sha256"][name]:
                    raise RuntimeError("Bundled firmware checksum failed")
                self.active_ota = True
                try:
                    client = PinnedHTTPS(credentials(self.device_path))
                    try:
                        result = update(client, image.read_bytes())
                    finally:
                        client.close()
                finally:
                    self.active_ota = False
                return {
                    "updated": True,
                    "version": manifest["version"],
                    "confirmed": result["confirmed"],
                }
            raise ValueError("Unknown setup action")
