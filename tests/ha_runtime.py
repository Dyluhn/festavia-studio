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
from unittest.mock import patch

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
            "reason": "idle",
            "frames": 0,
            "sent": 0,
            "acked": 0,
            "failures": 0,
        }
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
        if headers.get("Authorization") != "Bearer " + self.token or self.device_auth:
            return 401, {"secret": "must-not-leak"}
        if path == "/api/events?after=0":
            return 200, {"cursor": 0, "events": []}
        if path == "/api/status":
            return 200, {
                "target": "esp32c6",
                "version": "0.3.4",
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
                self.player.update(state="armed", armed=True, playing=False)
                self.snapshot["on"] = True
            elif op == "player_load":
                assert data["transport"] == "palette" and 1 <= len(data["samples"]) <= 64
                assert all(bytes.fromhex(s)[2] <= 38 for s in data["samples"]), (
                    "brightness cap not applied"
                )
                self.player.update(frames=len(data["samples"]), effective_fps=data["fps"])
            elif op == "player_start":
                self.player.update(state="playing", armed=True, playing=True)
            elif op == "player_stop":
                self.player.update(state="restored", armed=False, playing=False)
                self.snapshot = copy.deepcopy(BEFORE)
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
        from custom_components.festavia_studio.repairs import async_create_fix_flow
        from custom_components.festavia_studio.backend.lib.net_client import save_credentials
        from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

        with (
            patch("http.client.HTTPSConnection", HTTPS),
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
            assert len(names) == 14, names
            checks.append("real_commission_and_14_entities")

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
                    {"entity_id": "update.festavia_studio_firmware", "version": "0.3.4"},
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
            repair = await async_create_fix_flow(hass, issue_id, {"entry_id": entry.entry_id})
            repair.hass = hass
            assert (await repair.async_step_init())["step_id"] == "confirm"
            result = await repair.async_step_confirm({})
            assert (
                result["type"] == "create_entry"
                and not offline_folder.exists()
                and not wire.player["armed"]
            ), result
            assert ir.async_get(hass).async_get_issue("festavia_studio", issue_id) is None
            checks.append("offline_remove_retains_recovery_and_native_repair_restores")
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


print(json.dumps(asyncio.run(main())))
