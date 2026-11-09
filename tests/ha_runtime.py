"""Actual HA lifecycle + production backend; fake only HTTPS/Zigbee hardware.

Run in the pinned HA container. No live bridge/device is contacted. Installation,
commission, Player, encoders, stores, entity services and flows are production.
"""

import asyncio
import copy
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from unittest.mock import patch
from types import SimpleNamespace

logging.basicConfig(level=logging.ERROR)
os.environ.pop("SUPERVISOR_TOKEN", None)
os.environ.pop("HASSIO", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeassistant import bootstrap, loader
from homeassistant.core import HomeAssistant
from homeassistant.helpers import frame, issue_registry as ir

BRIDGE_CERT = b"isolated bridge certificate"
DEVICE_CERT = b"isolated esp certificate"
BRIDGE_PIN = hashlib.sha256(BRIDGE_CERT).hexdigest()
DEVICE_PIN = hashlib.sha256(DEVICE_CERT).hexdigest()
TOKEN = "a" * 64
IEEE = "0017880102030405"
PAN = "0102030405060708"
BEFORE = {
    "on": False,
    "level": 115,
    "color": {"3": 30121, "4": 26905, "7": 370, "8": 2},
    "fc03": "07020073720100",
    "logical_count": 27,
    "segments": [[0, 3], [3, 3], [6, 5], [11, 5], [16, 5], [21, 3], [24, 3]],
    "aliases": list(range(100, 107)),
}


class Wire:
    """Small firmware/Hue simulator at the requests and physical-ZCL boundary."""

    def __init__(self):
        self.key = "test-private"
        self.token = TOKEN
        self.link = False
        self.offline = False
        self.protocol_error = None
        self.device_auth = False
        self.ota_error = False
        self.calls = []
        self.connections = 0
        self.snapshot = copy.deepcopy(BEFORE)
        self.player = {
            "ok": True,
            "state": "idle",
            "armed": False,
            "playing": False,
            "native_palette_supported": True,
            "hue_takeover_supported": True,
            "reason": "idle",
            "frames": 0,
            "sent": 0,
            "acked": 0,
            "failures": 0,
        }
        self.hue_queues = {}
        self.hue_deadline = 0
        self.lights = {
            identifier: {
                "id": identifier,
                "owner": {"rid": "dev-" + identifier},
                "metadata": {"name": "Test Festavia " + identifier},
                "on": {"on": False},
                "dimming": {"brightness": 45},
                "color": {"xy": {"x": 0.3, "y": 0.3}},
                "gradient": {
                    "points_capable": 5,
                    "points": [{"color": {"xy": {"x": 0.3, "y": 0.3}}}] * 5,
                },
            }
            for identifier in ("fixture", "second")
        }

    def request(self, host, method, path, data, headers):
        self.calls.append((host, method, path, copy.deepcopy(data)))
        if self.offline:
            raise OSError("private-wire-detail")
        if self.protocol_error is not None:
            raise self.protocol_error
        device = host == "192.168.1.3"
        if not device:
            if path == "/api/config":
                return 200, {"bridgeid": "testbridge", "name": "Test bridge", "modelid": "BSB003"}
            if path == "/api":
                return 200, [{"success": {"username": self.key}}] if self.link else [
                    {"error": {"type": 101}}
                ]
            if headers.get("hue-application-key") != self.key:
                return 403, {"secret": "must-not-leak"}
            kind = path.rsplit("/", 1)[-1]
            if method == "PUT":
                self.lights[kind].update(data)
                return 200, {"errors": [], "data": [{"rid": kind}]}
            resources = {
                "device": [
                    {
                        "id": "dev-" + i,
                        "product_data": {
                            "model_id": "LCX030",
                            "product_name": "Festavia permanent",
                            "software_version": "1.163.5",
                        },
                    }
                    for i in self.lights
                ],
                "zigbee_connectivity": [
                    {
                        "owner": {"rid": "dev-" + i},
                        "status": "connected",
                        "mac_address": IEEE if i == "fixture" else "0017880102030406",
                    }
                    for i in self.lights
                ],
                "light": list(self.lights.values()),
                "entertainment_configuration": [],
            }
            return 200, {"errors": [], "data": resources[kind]}
        if (
            self.player.get("playing")
            and self.player.get("hue_takeover")
            and self.hue_deadline
            and time.monotonic() >= self.hue_deadline
        ):
            self.player.update(
                state="released", armed=False, playing=False, reason="hue_watchdog_expired"
            )
        if headers.get("Authorization") != "Bearer " + self.token or self.device_auth:
            return 401, {"secret": "must-not-leak"}
        if path == "/api/events?after=0":
            return 200, {"cursor": 0, "events": []}
        if path == "/api/status":
            return 200, {
                "target": "esp32c6",
                "version": "0.3.8",
                "approved_network": True,
                "channel": 20,
                "extpan": PAN,
            }
        if path == "/api/ota":
            return 500, {"secret": "must-not-leak"}
        if path == "/api/command":
            op = data["op"]
            if op == "player_prepare":
                assert data["restore"] and data["verify"] and data["setup"]
                self.captured = copy.deepcopy(self.snapshot)
                self.player.update(
                    state="armed",
                    armed=True,
                    playing=False,
                    hue_takeover=data.get("hue_takeover", False),
                )
                self.snapshot["on"] = True
            elif op == "player_load":
                assert data["transport"] == "palette" and 1 <= len(data["samples"]) <= 64
                assert all(bytes.fromhex(s)[2] <= 38 for s in data["samples"]), (
                    "brightness cap not applied"
                )
                self.player.update(frames=len(data["samples"]), effective_fps=data["fps"])
            elif op == "player_start":
                self.player.update(state="playing", armed=True, playing=True)
                self.hue_deadline = time.monotonic() + 15
            elif op == "player_release":
                self.player.update(
                    state="released", armed=False, playing=False, reason="hue_takeover"
                )
            elif op == "player_takeover":
                self.player["hue_takeover"] = data["enabled"]
                self.hue_deadline = time.monotonic() + 15
            elif op == "player_keepalive":
                self.hue_deadline = time.monotonic() + 10
            elif op == "player_stop":
                self.player.update(state="restored", armed=False, playing=False)
                self.snapshot = copy.deepcopy(getattr(self, "captured", BEFORE))
            elif op not in ("status", "player_status"):
                raise AssertionError(op)
            return 200, {
                **self.player,
                "id": data.get("id"),
                "approved_network": True,
                "channel": 20,
            }
        raise AssertionError((method, path))


wire = Wire()


async def fake_hue_events(self):
    self.connected = True
    self.ready.set()
    queue = wire.hue_queues.setdefault(self.coordinator.entry.entry_id, asyncio.Queue())
    while True:
        message = await queue.get()
        if message == "disconnect":
            raise OSError("simulated stream loss")
        yield message


class Socket:
    def __init__(self, cert):
        self.cert = cert

    def getpeercert(self, binary_form):
        return self.cert

    def settimeout(self, value):
        pass


class HTTPS:
    def __init__(self, host, port=None, **kwargs):
        assert host in ("192.168.1.2", "192.168.1.3", "192.168.1.4"), host
        self.host = host
        self.timeout = kwargs.get("timeout")
        self.sock = None
        wire.connections += 1

    def connect(self):
        self.sock = Socket(DEVICE_CERT if self.host == "192.168.1.3" else BRIDGE_CERT)

    def close(self):
        self.sock = None

    def request(self, method, path, body=None, headers=None):
        obj = (
            json.loads(body)
            if body and (headers or {}).get("Content-Type") != "application/octet-stream"
            else body
        )
        self.result = wire.request(self.host, method, path, obj, headers or {})

    def getresponse(self):
        status, obj = self.result

        class Response:
            will_close = False

            def read(self, size):
                return json.dumps(obj).encode()[:size]

        response = Response()
        response.status = status
        return response


class ZigbeeDevice:
    """Physical fixture adapter; production ownership/encoders remain active."""

    def __init__(self, credentials, ieee, endpoint, **kwargs):
        self.ieee, self.endpoint, self.address = ieee, endpoint, 123
        self.identity = {"5": "LCX030", "16384": "1.163.5"}

    def connect(self):
        return {"identity": self.identity, "esp32": {"extpan": PAN, "address": 200}}

    def snapshot(self):
        return copy.deepcopy(wire.snapshot)

    def verify_baseline(self, before):
        return wire.snapshot == before

    def combined(self, **fields):
        for a, b in (("on", "on"), ("brightness", "level")):
            if a in fields:
                wire.snapshot[b] = fields[a]
        return {"ok": True}

    def close(self):
        pass


async def main():
    folder = tempfile.mkdtemp(prefix="festavia-ha-isolated-")
    hass = HomeAssistant(folder)
    loader.async_setup(hass)
    frame.async_setup(hass)
    checks = []
    try:
        assert await bootstrap.async_from_config_dict({"http": {"server_port": 18129}}, hass)
        from homeassistant.setup import async_setup_component

        assert await async_setup_component(hass, "festavia_studio", {})
        from custom_components.festavia_studio import api, async_migrate_entry
        from custom_components.festavia_studio.backend.lib import service as backend, control
        from custom_components.festavia_studio.diagnostics import async_get_config_entry_diagnostics
        from custom_components.festavia_studio.api import private_folder, has_recovery
        from custom_components.festavia_studio.backend.lib.net_client import save_credentials
        from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

        from custom_components.festavia_studio.takeover import HueTakeover

        with (
            patch.object(HueTakeover, "_events", fake_hue_events),
            patch("http.client.HTTPSConnection", HTTPS),
            # A just-booted CI/HA host may have uptime below the cache TTL.
            patch.object(api, "time", SimpleNamespace(monotonic=lambda: 30.0)),
            patch.object(backend, "Device", ZigbeeDevice),
            patch.object(control, "Device", ZigbeeDevice),
        ):
            # Real commission, pair, Hue resource parsing, capability inspection.
            form = await hass.config_entries.flow.async_init(
                "festavia_studio", context={"source": "user"}
            )

            async def advance(data):
                return await hass.config_entries.flow.async_configure(form["flow_id"], data)

            assert (await advance({"bridge": "manual"}))["step_id"] == "manual"
            assert (await advance({"host": "8.8.8.8"}))["errors"]["base"] == "cannot_connect"
            assert (await advance({"host": "192.168.1.2"}))["step_id"] == "link"
            assert (await advance({}))["errors"]["base"] == "link_required"
            wire.link = True
            assert (await advance({}))["step_id"] == "fixtures"
            assert (await advance({"lights": ["fixture"], "mode": "native"}))["step_id"] == "device"
            device = {"url": "https://192.168.1.3", "token": TOKEN, "tls_sha256": DEVICE_PIN}
            assert (await advance({**device, "token": "bad"}))["errors"][
                "base"
            ] == "device_connection"
            result = await advance(device)
            assert result["type"] == "create_entry", result
            entry = result["result"]
            await hass.async_block_till_done()
            assert entry.state.value == "loaded", entry.state
            assert "url" not in entry.data and "token" not in entry.data
            names = [s.entity_id for s in hass.states.async_all() if "_studio_" in s.entity_id]
            assert len(names) == 17, names
            checks.append("real_commission_and_17_entities")

            async def service(domain, name, data):
                await hass.services.async_call(domain, name, data, blocking=True)
                await hass.async_block_till_done()

            async def action(name, data=None):
                await service("festavia_studio", name, {"entry_id": entry.entry_id, **(data or {})})

            await service(
                "number",
                "set_value",
                {"entity_id": "number.festavia_studio_brightness_limit", "value": 15},
            )
            await service(
                "text",
                "set_value",
                {
                    "entity_id": "text.festavia_studio_palette",
                    "value": "#ff0000, #00ff00, #9900ff, #ffff00",
                },
            )
            count = len([c for c in wire.calls if c[1] in ("PUT", "POST") and c[2] != "/api"])
            for bad in (
                {"brightness": 20},
                {"colors": ["#ff0000"] * 10},
                {"speed": float("nan")},
                {"effect": "bad"},
                {"colors": ["#ff0000", "#001000"]},
                {"colors": ["#000000"]},
            ):
                try:
                    await action("configure", bad)
                except ServiceValidationError:
                    pass
                else:
                    raise AssertionError(("invalid scene accepted", bad))
            assert count == len(
                [c for c in wire.calls if c[1] in ("PUT", "POST") and c[2] != "/api"]
            )
            for name in ("Custom", " custom ", ""):
                try:
                    await action("save_preset", {"name": name})
                except ServiceValidationError:
                    pass
                else:
                    raise AssertionError("reserved palette name accepted")
            checks.append("invalid_palette_and_cap_rejected_before_write")
            # A normal Hue light may already be brighter than Studio's effect
            # limit. Starting must capture it and lower it while OFF, rather
            # than rejecting every Play/Power button before prepare.
            wire.snapshot.update(on=True, level=115)
            original_on = copy.deepcopy(wire.snapshot)
            await service(
                "light",
                "turn_on",
                {"entity_id": "light.festavia_studio_effect_light", "brightness": 26},
            )
            assert wire.player["playing"]
            prepare = next(
                call[3]
                for call in reversed(wire.calls)
                if call[2] == "/api/command" and call[3].get("op") == "player_prepare"
            )
            assert prepare["setup"][0]["cluster"] == 6 and prepare["setup"][0]["command"] == 0
            await action("stop")
            assert wire.snapshot == original_on
            checks.append("start_from_existing_hue_brightness_above_effect_limit_and_restore")
            wire.snapshot = copy.deepcopy(BEFORE)
            wire.snapshot["fc03"] = "0001"
            try:
                await action("play")
            except api.StudioError as exc:
                assert exc.key == "hue_effect_active"
            else:
                raise AssertionError("Unsupported Hue effect was silently overwritten")
            await entry.runtime_data.async_refresh()
            diagnostics = await async_get_config_entry_diagnostics(hass, entry)
            assert diagnostics["last_error"] == {
                "reason": "hue_effect_active",
                "exception": "PlaybackBlocked",
            }
            checks.append("unsupported_hue_state_has_actionable_error_and_safe_diagnostics")
            wire.snapshot = copy.deepcopy(BEFORE)
            await service(
                "light",
                "turn_on",
                {
                    "entity_id": "light.festavia_studio_effect_light",
                    "brightness": 26,
                    "effect": "flow",
                },
            )
            assert wire.player["playing"]
            journal = private_folder(hass, entry.entry_id) / "esp/player-session.json"
            assert len(json.loads(journal.read_text())["scene"]["colors"]) == 4
            # Concurrent standard entity edits retain both changes through action_lock.
            await asyncio.gather(
                service(
                    "number", "set_value", {"entity_id": "number.festavia_studio_speed", "value": 2}
                ),
                service(
                    "switch", "turn_on", {"entity_id": "switch.festavia_studio_reverse_direction"}
                ),
            )
            scene = json.loads(journal.read_text())["scene"]
            assert scene["speed"] == 2 and scene["reverse"] is True
            await action("save_preset", {"name": "Saved test"})
            assert "Saved test" in entry.runtime_data.data["presets"]
            checks.append("real_player_prepare_load_start_live_edits_and_concurrency")
            # Color palettes preserve motion; complete scenes restore it.
            motion = {
                k: entry.runtime_data.scene[k] for k in ("effect", "speed", "reverse", "brightness")
            }
            await action("save_palette", {"name": "Colors only"})
            assert isinstance(entry.runtime_data.data["palettes"]["Colors only"], list)
            await service(
                "select",
                "select_option",
                {"entity_id": "select.festavia_studio_color_palette", "option": "Winter"},
            )
            assert {k: entry.runtime_data.scene[k] for k in motion} == motion
            assert entry.runtime_data.scene["colors"] == ["#80dfff", "#e4f4ff", "#4040ff"]
            assert entry.runtime_data.palette == "Winter"
            app = entry.runtime_data.api.app
            libraries = app.color_palettes()
            libraries.update(
                {"Bridge only count": ["#ff0000"] * 10, "Bridge only tones": ["#ff0000", "#001000"]}
            )
            save_credentials(app.palette_library, libraries)
            await entry.runtime_data.async_refresh()
            assert "Bridge only count" not in entry.runtime_data.data["palettes"]
            assert "Bridge only tones" not in entry.runtime_data.data["palettes"]
            entry.runtime_data.palette = "Removed elsewhere"
            await entry.runtime_data.async_refresh()
            assert entry.runtime_data.palette == "Custom"
            checks.append("native_palettes_filtered_and_stale_selection_reconciled")
            await action("load_palette", {"palette": "Colors only"})
            assert {k: entry.runtime_data.scene[k] for k in motion} == motion
            from custom_components.festavia_studio.backend.lib.player import PUCK_EFFECTS

            for effect in PUCK_EFFECTS:
                await service(
                    "select",
                    "select_option",
                    {"entity_id": "select.festavia_studio_effect", "option": effect},
                )
                assert wire.player["playing"] and entry.runtime_data.scene["effect"] == effect
            await action("save_scene", {"name": "Complete scene"})
            full_scene = copy.deepcopy(entry.runtime_data.scene)
            await action("configure", {"effect": "static", "speed": 3})
            await action("load_scene", {"preset": "Complete scene"})
            assert all(
                entry.runtime_data.scene[k] == full_scene[k]
                for k in ("colors", "effect", "speed", "brightness", "reverse")
            )
            await action("delete_palette", {"name": "Colors only"})
            assert (
                "Colors only" not in entry.runtime_data.data["palettes"] and wire.player["playing"]
            )
            await action("delete_scene", {"name": "Complete scene"})
            assert (
                "Complete scene" not in entry.runtime_data.data["presets"]
                and wire.player["playing"]
            )
            checks.append("color_palettes_preserve_motion_and_full_scenes_restore_it")
            checks.append("all_eight_native_animations_load_through_real_entities")
            # Real coordinator/transport release must not restore old lamp state.
            c = entry.runtime_data
            queue = wire.hue_queues[entry.entry_id]
            desired = {"color": {"xy": {"x": 0.17, "y": 0.08}}, "dimming": {"brightness": 8}}

            async def emit(identifier, patch):
                await queue.put(
                    [{"type": "update", "data": [{"type": "light", "id": identifier, **patch}]}]
                )
                for _ in range(100):
                    await asyncio.sleep(0.02)
                    if c.takeover.worker and c.takeover.worker.done():
                        break

            before_handoff = len(wire.calls)
            wire.lights["fixture"].update(copy.deepcopy(desired))
            await emit("fixture", desired)
            assert not c.playing and wire.player["state"] == "released"
            commands = [
                call[3].get("op")
                for call in wire.calls[before_handoff:]
                if call[2] == "/api/command"
            ]
            assert "player_release" in commands and "player_stop" not in commands
            assert wire.lights["fixture"]["color"] == desired["color"]
            assert wire.lights["fixture"]["dimming"] == desired["dimming"]
            assert json.loads(journal.read_text())["released"]
            await action("play", {"brightness": 10})
            before_handoff = len(wire.calls)
            wire.lights["fixture"].update(copy.deepcopy(desired))
            wire.lights["fixture"]["dimming"]["min_dim_level"] = 0.02
            await emit("fixture", {"color": desired["color"]})
            patches = [
                call[3]
                for call in wire.calls[before_handoff:]
                if call[1] == "PUT" and call[2].endswith("/light/fixture")
            ]
            assert patches[-1]["color"] == desired["color"]
            assert patches[-1]["dimming"] == desired["dimming"]
            checks.append("Hue_color_handoff_preserves_brightness_omitted_from_SSE")
            await service(
                "switch", "turn_off", {"entity_id": "switch.festavia_studio_allow_hue_takeover"}
            )
            await action("play", {"brightness": 10})
            await emit("fixture", desired)
            assert c.playing and not c.takeover.enabled
            await service(
                "switch", "turn_on", {"entity_id": "switch.festavia_studio_allow_hue_takeover"}
            )
            # A different light and metadata-only reports do not steal ownership.
            c.takeover.worker = None
            await emit("second", desired)
            await emit("fixture", {"metadata": {"name": "Renamed"}})
            assert c.playing
            checks.append(
                "Hue_takeover_releases_without_restore_replays_new_intent_and_respects_option_and_target"
            )
            await queue.put("disconnect")
            for _ in range(100):
                await asyncio.sleep(0.02)
                if not c.playing:
                    break
            assert not c.playing and c.takeover.last_reason == "connection_lost"
            checks.append("Hue_stream_disconnect_yields_without_replaying_old_state")
            await c.takeover.ensure_ready()
            await action("play", {"brightness": 10})
            await service(
                "button", "press", {"entity_id": "button.festavia_studio_return_control_to_hue"}
            )
            assert not c.playing and wire.player["state"] == "released"
            checks.append("native_manual_return_to_Hue_button_releases_without_restore")
            # Recorded delayed native-output reports must not steal ownership.
            from custom_components.festavia_studio.takeover import hue_patch

            output = c.takeover.output_scene
            c.takeover.output_scene = {
                **c.scene,
                "colors": [
                    "#fb5d54",
                    "#fb4d00",
                    "#fb8f00",
                    "#fbbb67",
                    "#fb5d54",
                    "#fb4d00",
                    "#fb8f00",
                    "#fb0000",
                    "#fbb2b2",
                ],
                "brightness": 10,
                "effect": "flow",
            }
            for echo in (
                {"on": {"on": True}},
                {"dimming": {"brightness": 9.49}},
                {
                    "color": {"xy": {"x": 0.551, "y": 0.4052}},
                    "color_temperature": {"mirek": None, "mirek_valid": False},
                    "gradient": {"points": [], "points_capable": 5},
                },
            ):
                assert c.takeover.is_output_echo(echo), echo
            assert not c.takeover.is_output_echo({"color": {"xy": {"x": 0.17, "y": 0.08}}})
            c.takeover.output_scene = output
            assert hue_patch(
                {
                    "color": {"xy": {"x": 0.17, "y": 0.08}},
                    "gradient": {"points": []},
                    "color_temperature": {"mirek": None},
                }
            ) == {"color": {"xy": {"x": 0.17, "y": 0.08}}}
            checks.append(
                "recorded_native_output_echoes_are_ignored_and_empty_gradients_not_replayed"
            )
            c.acquiring = True
            c.takeover.setup_states = {
                "fixture": {
                    "on": {"on": True},
                    "dimming": {"brightness": 7.91},
                    "color": {"xy": {"x": 0.4475, "y": 0.4076}},
                    "color_temperature": {"mirek": 350, "mirek_valid": True},
                }
            }
            for echo in (
                {"on": {"on": False}},
                {"dimming": {"brightness": 7.91}},
                {
                    "color": {"xy": {"x": 0.4475, "y": 0.4076}},
                    "color_temperature": {"mirek": 350, "mirek_valid": True},
                },
            ):
                assert c.takeover.is_output_echo({"id": "fixture", **echo})
            assert not c.takeover.is_output_echo(
                {"id": "fixture", "color": {"xy": {"x": 0.17, "y": 0.08}}}
            )
            c.acquiring = False
            assert not c.takeover.is_output_echo({"id": "fixture", "on": {"on": False}})
            assert not c.takeover.is_output_echo(
                {"id": "fixture", "color_temperature": {"mirek": 350, "mirek_valid": True}}
            )
            checks.append("native_acquisition_power_and_baseline_echoes_do_not_abort_Play")
            # Relative commands are resolved once at the original service event.
            from homeassistant.core import Context, Event
            from homeassistant.helpers import entity_registry as er

            registry = er.async_get(hass)
            peer = registry.async_get_or_create(
                "light", "hue", "fixture", suggested_object_id="test_hue_fixture"
            )
            hass.states.async_set(peer.entity_id, "on", {"brightness": 26})
            await action("play", {"brightness": 10})
            ordered = []

            async def peer_call(_registry, domain, action, data, **kwargs):
                ordered.append((domain, action, copy.deepcopy(data)))

            c.takeover.schedule({"fixture": desired}, "hue_command")
            c.takeover.ha_command(
                Event(
                    "call_service",
                    data={
                        "domain": "light",
                        "service": "turn_on",
                        "service_data": {"entity_id": peer.entity_id, "brightness_step_pct": 2},
                    },
                    context=Context(),
                )
            )
            with patch.object(type(hass.services), "async_call", peer_call):
                await c.takeover.worker
            assert not c.playing and ordered[-1][2]["brightness"] == 31
            assert "brightness_step_pct" not in ordered[-1][2]
            checks.append("HA_relative_brightness_is_replayed_as_one_absolute_change")

            # A later HA command can arrive after firmware release while an
            # earlier replay is awaiting its network response. It must win.
            await action("play", {"brightness": 10})
            ordered.clear()

            async def interleaved_call(_registry, domain, action, data, **kwargs):
                ordered.append(copy.deepcopy(data))
                if len(ordered) == 1:
                    assert not c.playing and c.takeover.replaying
                    c.takeover.ha_command(
                        Event(
                            "call_service",
                            data={
                                "domain": "light",
                                "service": "turn_on",
                                "service_data": {"entity_id": peer.entity_id, "brightness": 17},
                            },
                            context=Context(),
                        )
                    )
                await asyncio.sleep(0)

            c.takeover.ha_command(
                Event(
                    "call_service",
                    data={
                        "domain": "light",
                        "service": "turn_on",
                        "service_data": {"entity_id": peer.entity_id, "brightness": 26},
                    },
                    context=Context(),
                )
            )
            with patch.object(type(hass.services), "async_call", interleaved_call):
                await c.takeover.worker
            assert [item["brightness"] for item in ordered] == [26, 17]
            assert not c.takeover.actions
            checks.append("HA_command_during_replay_wins_and_does_not_get_stranded")

            wire.snapshot = copy.deepcopy(BEFORE)
            await action("play", {"brightness": 10})

            reconfig = await hass.config_entries.flow.async_init(
                "festavia_studio", context={"source": "reconfigure", "entry_id": entry.entry_id}
            )
            reconfig = await hass.config_entries.flow.async_configure(
                reconfig["flow_id"], {"next_step_id": "fixtures"}
            )
            assert reconfig["type"] == "abort" and reconfig["reason"] == "stop_first", reconfig
            # Repeated polls do not open Hue inventory TLS sessions.
            old = len([c for c in wire.calls if c[0] == "192.168.1.2"])
            for _ in range(3):
                entry.runtime_data.api.app.studio.status_at = 0
                await entry.runtime_data.async_refresh()
            assert len([c for c in wire.calls if c[0] == "192.168.1.2"]) == old
            checks.append("polls_no_hue_inventory_and_no_reconfigure_active_lease")
            # Unload/reload restores the captured original and never resumes.
            await action("configure", {"speed": 3, "brightness": 7, "apply": False})
            assert await hass.config_entries.async_reload(entry.entry_id)
            await hass.async_block_till_done()
            assert wire.snapshot == BEFORE and not wire.player["playing"]
            assert (
                entry.runtime_data.scene["speed"] == 3
                and entry.runtime_data.scene["brightness"] == 7
            )
            assert entry.runtime_data.data["brightness_limit"] == 15
            checks.append("reload_drains_restores_and_retains_staged_controls")
            # Real OTA backend error must emerge as a HomeAssistantError, redacted.
            try:
                await service(
                    "update",
                    "install",
                    {
                        "entity_id": "update.festavia_studio_firmware",
                        "version": entry.runtime_data.api.latest_version,
                    },
                )
            except HomeAssistantError as exc:
                assert "private-wire" not in str(exc) and "must-not-leak" not in str(exc)
            else:
                raise AssertionError("OTA failure accepted")
            assert (
                hass.states.get("update.festavia_studio_firmware").attributes["in_progress"]
                is False
            )
            checks.append("ota_failure_is_actionable_and_resets_progress")
            # Firmware auth denial propagates through the real pinned HTTPS client.
            wire.device_auth = True
            entry.runtime_data.api.app.studio.status_at = 0
            await entry.runtime_data.async_refresh()
            await hass.async_block_till_done()
            assert not entry.runtime_data.last_update_success
            flows = hass.config_entries.flow.async_progress_by_handler("festavia_studio")
            assert any(f["context"]["source"] == "reauth" for f in flows), flows
            wire.device_auth = False
            wire.token = "c" * 64
            reauth = next(f for f in flows if f["context"]["source"] == "reauth")
            result = await hass.config_entries.flow.async_configure(
                reauth["flow_id"], {"device_token": wire.token}
            )
            assert result["type"] == "abort" and result["reason"] == "reauth_successful", result
            await hass.async_block_till_done()
            assert entry.state.value == "loaded" and entry.data["device"]["token"] == wire.token
            checks.append("real_transport_auth_denial_and_successful_reauth")
            diagnostics = await async_get_config_entry_diagnostics(hass, entry)
            for secret in (wire.key, TOKEN, wire.token, DEVICE_PIN, "192.168.1.3"):
                assert secret not in json.dumps(diagnostics)
            checks.append("diagnostics_redacted")
            # An unloaded entry's actual bridge lease blocks temporary commissioning.
            await hass.config_entries.async_unload(entry.entry_id)
            folder_path = private_folder(hass, entry.entry_id)
            bridge_journal = folder_path / "bridge-session.json"
            save_credentials(
                bridge_journal,
                {"bridge_id": "testbridge", "before": {"fixture": {"on": {"on": False}}}},
            )
            flow = await hass.config_entries.flow.async_init(
                "festavia_studio", context={"source": "reconfigure", "entry_id": entry.entry_id}
            )
            result = await hass.config_entries.flow.async_configure(
                flow["flow_id"], {"next_step_id": "fixtures"}
            )
            assert result["type"] == "abort" and result["reason"] == "stop_first", result
            assert bridge_journal.exists()
            await hass.async_add_executor_job(api.recover_folder, folder_path)
            assert not has_recovery(folder_path)
            assert await hass.config_entries.async_setup(entry.entry_id)
            checks.append("unloaded_reconfigure_preserves_real_journal")
            # Version1 migration retains all registry IDs and removes obsolete app auth.
            unique_id = entry.unique_id
            original_data = copy.deepcopy(dict(entry.data))
            await hass.config_entries.async_unload(entry.entry_id)
            hass.config_entries.async_update_entry(
                entry, version=1, data={"url": "http://retired", "token": "retired"}
            )
            assert await async_migrate_entry(hass, entry)
            assert entry.version == 2 and entry.unique_id == unique_id and "url" not in entry.data
            assert await hass.config_entries.async_setup(entry.entry_id)
            checks.append("legacy_private_folder_migration_preserves_ids")
            # Online removal must stop playback and delete private records/resources.
            await action("play", {"brightness": 10})
            await hass.config_entries.async_remove(entry.entry_id)
            assert not wire.player["armed"] and not folder_path.exists()
            assert not any(
                "/festavia_studio/" in r["url"]
                for r in hass.data["lovelace"].resources.async_items()
            )
            checks.append("online_remove_restores_and_cleans_resources_and_secrets")
            # Re-add uses real backend setup; failed removal retains a native repair.
            from homeassistant.config_entries import ConfigEntry

            second = ConfigEntry(
                version=2,
                minor_version=1,
                domain="festavia_studio",
                title="Festavia Studio",
                data=original_data,
                options={"brightness_limit": 15},
                source="user",
                unique_id=unique_id,
                discovery_keys={},
                subentries_data=[],
            )
            await hass.config_entries.async_add(second)
            assert second.state.value == "loaded"
            entry = second
            assert any(
                "/festavia_studio/" in r["url"]
                for r in hass.data["lovelace"].resources.async_items()
            )
            await action("play", {"brightness": 10})
            offline_folder = private_folder(hass, entry.entry_id)
            wire.offline = True
            await hass.config_entries.async_remove(entry.entry_id)
            issue_id = "recovery_" + entry.entry_id
            issue = ir.async_get(hass).async_get_issue("festavia_studio", issue_id)
            assert (
                issue
                and offline_folder.exists()
                and (offline_folder / "removal-pending.json").exists()
            )
            wire.offline = False
            from custom_components.festavia_studio.config_flow import FestaviaFlow

            reconnect = FestaviaFlow()
            reconnect.hass = hass
            reconnect.installation = copy.deepcopy(original_data["installation"])
            reconnect.selection = {"ids": ["second"], "mode": "native"}
            reconnect.device = copy.deepcopy(original_data["device"])
            assert offline_folder in await reconnect.orphan_folders(), (
                "same ESP lease lost when new fixture differs"
            )
            assert issue.is_persistent and not issue.is_fixable
            await reconnect.recover_orphans()
            assert not offline_folder.exists() and not wire.player["armed"]
            assert ir.async_get(hass).async_get_issue("festavia_studio", issue_id) is None
            checks.append("offline_remove_retains_recovery_and_native_readd_restores")
            # Reuse an existing HA Hue entry; a disabled Hue entry avoids opening
            # a second real Hue connection in this isolated runtime.
            from homeassistant.config_entries import ConfigEntryDisabler

            hue = ConfigEntry(
                version=1,
                minor_version=1,
                domain="hue",
                title="Existing Hue",
                data={"host": "192.168.1.2", "api_key": wire.key},
                options={},
                source="user",
                unique_id="testbridge",
                discovery_keys={},
                subentries_data=[],
                disabled_by=ConfigEntryDisabler.USER,
            )
            await hass.config_entries.async_add(hue)
            wire.player.update(state="playing", armed=True, playing=True)
            form = await hass.config_entries.flow.async_init(
                "festavia_studio", context={"source": "user"}
            )
            before_pair = sum(c[2] == "/api" for c in wire.calls)
            assert (await advance({"bridge": hue.entry_id}))["step_id"] == "fixtures"
            assert (await advance({"lights": ["fixture"], "mode": "native"}))["step_id"] == "device"
            result = await advance({**device, "token": wire.token})
            assert result["step_id"] == "device_recover", result
            assert wire.player["armed"], "setup stopped an armed player before confirmation"
            result = await advance({})
            assert result["type"] == "create_entry", result
            entry = result["result"]
            await hass.async_block_till_done()
            assert entry.state.value == "loaded" and entry.data["hue_entry_id"] == hue.entry_id
            assert before_pair == sum(c[2] == "/api" for c in wire.calls), (
                "reused Hue key was paired again"
            )
            assert not wire.player["armed"]
            checks.append("existing_hue_reuse_and_confirmed_armed_device_recommission")
            # Early duplicate detection must happen before device takeover.
            duplicate = await hass.config_entries.flow.async_init(
                "festavia_studio", context={"source": "user"}
            )
            await hass.config_entries.flow.async_configure(
                duplicate["flow_id"], {"bridge": hue.entry_id}
            )
            result = await hass.config_entries.flow.async_configure(
                duplicate["flow_id"], {"lights": ["fixture"], "mode": "native"}
            )
            assert result["type"] == "abort" and result["reason"] == "already_configured", result
            checks.append("duplicate_selection_rejected_before_device_takeover")
            wire.key = "renewed-hue-private-key"
            hass.config_entries.async_update_entry(
                hue, data={"host": "192.168.1.4", "api_key": wire.key}
            )
            await entry.runtime_data.async_refresh()
            assert entry.data["installation"]["bridge"]["address"] == "192.168.1.4"
            assert entry.data["installation"]["bridge"]["key"] == wire.key
            await service(
                "number",
                "set_value",
                {"entity_id": "number.festavia_studio_brightness_limit", "value": 15},
            )
            await action("play", {"brightness": 10})
            await action("stop")
            checks.append("linked_hue_address_and_key_follow_without_reload")
            # Explicit manual reauthorization must not be reverted by the stale
            # key in another integration.
            wire.key = "manual-renewed-private-key"
            form = await hass.config_entries.flow.async_init(
                "festavia_studio",
                context={"source": "reauth", "entry_id": entry.entry_id},
                data=dict(entry.data),
            )
            result = await advance({"bridge_key": wire.key})
            assert result["type"] == "abort" and result["reason"] == "reauth_successful", result
            await hass.async_block_till_done()
            assert entry.state.value == "loaded" and entry.data["hue_entry_id"] is None
            await entry.runtime_data.async_refresh()
            assert entry.data["installation"]["bridge"]["key"] == wire.key
            await hass.config_entries.async_remove(entry.entry_id)
            checks.append("manual_reauth_does_not_restore_stale_imported_key")
            # Bridge recovery on credential renewal uses the just-validated new
            # key while the old runtime is unloading, rather than deadlocking it.
            bridge_data = copy.deepcopy(original_data)
            bridge_data["installation"].update(mode="bridge", native=None)
            bridge_data["installation"]["bridge"].update(address="192.168.1.4", key=wire.key)
            bridge_data.update(device=None, hue_entry_id=None)
            entry = ConfigEntry(
                version=2,
                minor_version=1,
                domain="festavia_studio",
                title="Festavia Studio",
                data=bridge_data,
                options={"brightness_limit": 15},
                source="user",
                unique_id=unique_id,
                discovery_keys={},
                subentries_data=[],
            )
            await hass.config_entries.async_add(entry)
            assert entry.state.value == "loaded"
            await action("play", {"brightness": 10, "effect": "static"})
            assert wire.lights["fixture"]["on"]["on"]
            wire.key = "bridge-lease-renewed-key"
            form = await hass.config_entries.flow.async_init(
                "festavia_studio",
                context={"source": "reauth", "entry_id": entry.entry_id},
                data=dict(entry.data),
            )
            result = await advance({"bridge_key": wire.key})
            assert result["type"] == "abort" and result["reason"] == "reauth_successful", result
            await hass.async_block_till_done()
            assert entry.state.value == "loaded"
            assert not wire.lights["fixture"]["on"]["on"] and not has_recovery(
                private_folder(hass, entry.entry_id)
            )
            await hass.config_entries.async_remove(entry.entry_id)
            checks.append("bridge_lease_reauth_restores_with_new_key_during_unload")
            return {
                "passed": True,
                "checks": checks,
                "production_backend": True,
                "transport_only_simulation": True,
                "https_requests": len(wire.calls),
                "https_connections": wire.connections,
            }
    finally:
        await hass.async_stop(force=True)
        shutil.rmtree(folder)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(main())))
