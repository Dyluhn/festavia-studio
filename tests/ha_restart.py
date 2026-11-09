"""Real HA restart, offline recovery and legacy reconfiguration regressions."""

import asyncio
import copy
import http.client
import json
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch

from ha_runtime import (
    BEFORE,
    DEVICE_PIN,
    IEEE,
    PAN,
    TOKEN,
    HTTPS,
    ZigbeeDevice,
    bootstrap,
    frame,
    loader,
    wire,
    HomeAssistant,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component


def entry(data, unique="testbridge_fixture"):
    return ConfigEntry(
        version=2,
        minor_version=1,
        domain="festavia_studio",
        title="Festavia Studio",
        data=data,
        options={"brightness_limit": 15},
        source="user",
        unique_id=unique,
        discovery_keys={},
        subentries_data=[],
    )


async def boot(folder):
    hass = HomeAssistant(folder)
    loader.async_setup(hass)
    frame.async_setup(hass)
    assert await bootstrap.async_from_config_dict({"http": {"server_port": 18130}}, hass)
    return hass


async def main():
    from custom_components.festavia_studio import api
    from custom_components.festavia_studio.backend.lib import service, control

    folder = tempfile.mkdtemp(prefix="festavia-ha-restart-")
    hass = None
    checks = []
    with (
        patch("http.client.HTTPSConnection", HTTPS),
        patch.object(service, "Device", ZigbeeDevice),
        patch.object(control, "Device", ZigbeeDevice),
    ):
        try:
            hass = await boot(folder)
            assert await async_setup_component(hass, "festavia_studio", {})
            bridge = await hass.async_add_executor_job(api.probe, "192.168.1.2")
            data = {
                "installation": {
                    "schema": 1,
                    "bridge": {**bridge, "key": wire.key},
                    "mode": "native",
                    "selected": ["fixture"],
                    "native": {
                        "ieee": IEEE,
                        "endpoint": 11,
                        "extpan": PAN,
                        "model": "LCX030",
                        "positions": 27,
                    },
                },
                "device": {
                    "target": "esp32c6",
                    "url": "https://192.168.1.3",
                    "token": TOKEN,
                    "tls_sha256": DEVICE_PIN,
                },
                "hue_entry_id": None,
            }
            e = entry(copy.deepcopy(data))
            await hass.config_entries.async_add(e)
            assert e.state.value == "loaded"
            await e.runtime_data.play(changes={"brightness": 10, "effect": "flow"})
            wire.offline = True
            assert not await hass.config_entries.async_reload(e.entry_id)
            assert e.state.value == "setup_retry", e.state
            notice = ir.async_get(hass).async_get_issue("festavia_studio", "recovery_" + e.entry_id)
            assert notice and notice.is_persistent
            options = await hass.config_entries.options.async_init(e.entry_id)
            assert options["type"] == "abort" and options["reason"] == "not_loaded", options
            wire.offline = False
            assert await hass.config_entries.async_reload(e.entry_id)
            assert (
                e.state.value == "loaded" and not wire.player["armed"] and wire.snapshot == BEFORE
            )
            assert (
                ir.async_get(hass).async_get_issue("festavia_studio", "recovery_" + e.entry_id)
                is None
            )
            checks.append(
                "offline_reload_uses_setup_retry_and_restores_on_reconnect_without_restart"
            )
            await e.runtime_data.play(changes={"brightness": 10, "effect": "flow"})
            # Protocol errors are not OSError, and must still preserve removal recovery.
            wire.protocol_error = http.client.IncompleteRead(b"", 10)
            old_id = e.entry_id
            old_folder = api.private_folder(hass, old_id)
            await hass.config_entries.async_remove(old_id)
            assert (old_folder / "removal-pending.json").exists()
            notice = ir.async_get(hass).async_get_issue("festavia_studio", "recovery_" + old_id)
            assert notice and notice.is_persistent and not notice.is_fixable
            registry = ir.async_get(hass)
            await registry._store.async_save(registry._data_to_save())
            await hass.async_stop(force=True)
            hass = await boot(folder)
            assert "festavia_studio" not in hass.config.top_level_components
            notice = ir.async_get(hass).async_get_issue("festavia_studio", "recovery_" + old_id)
            assert notice and notice.active and notice.is_persistent and not notice.is_fixable
            assert not hass.config_entries.async_entries("festavia_studio")
            # The persisted notice routes to a real HA config flow. It does not
            # offer a generic confirmation that could clear the issue without recovery.
            wire.protocol_error = None
            wire.link = True
            form = await hass.config_entries.flow.async_init(
                "festavia_studio", context={"source": "user"}
            )

            async def advance(value):
                return await hass.config_entries.flow.async_configure(form["flow_id"], value)

            await advance({"bridge": "manual"})
            await advance({"host": "192.168.1.2"})
            await advance({})
            await advance({"lights": ["fixture"], "mode": "native"})
            result = await advance({k: data["device"][k] for k in ("url", "token", "tls_sha256")})
            assert result["step_id"] == "device_recover", result
            result = await advance({})
            assert result["type"] == "create_entry", result
            e = result["result"]
            await hass.async_block_till_done()
            assert (
                e.state.value == "loaded" and wire.snapshot == BEFORE and not wire.player["armed"]
            )
            assert not old_folder.exists()
            assert (
                ir.async_get(hass).async_get_issue("festavia_studio", "recovery_" + old_id) is None
            )
            checks.append(
                "http_protocol_failure_removal_notice_survives_restart_and_native_readd_recovers"
            )
            await hass.config_entries.async_remove(e.entry_id)
            # Legacy IDs stay stable when selections change. New controllers
            # have independent IDs, so the former fixture can be added again.
            legacy_data = copy.deepcopy(data)
            legacy_data["installation"].update(mode="bridge", native=None)
            legacy_data["device"] = None
            legacy = entry(legacy_data)
            await hass.config_entries.async_add(legacy)
            flow = await hass.config_entries.flow.async_init(
                "festavia_studio", context={"source": "reconfigure", "entry_id": legacy.entry_id}
            )
            await hass.config_entries.flow.async_configure(
                flow["flow_id"], {"next_step_id": "fixtures"}
            )
            result = await hass.config_entries.flow.async_configure(
                flow["flow_id"], {"lights": ["second"], "mode": "bridge"}
            )
            assert result["type"] == "abort" and result["reason"] == "reconfigure_successful", (
                result
            )
            await hass.async_block_till_done()
            assert legacy.unique_id == "testbridge_fixture" and legacy.data["installation"][
                "selected"
            ] == ["second"]
            form = await hass.config_entries.flow.async_init(
                "festavia_studio", context={"source": "user"}
            )
            await advance({"bridge": "manual"})
            await advance({"host": "192.168.1.2"})
            await advance({})
            result = await advance({"lights": ["fixture"], "mode": "bridge"})
            assert result["type"] == "create_entry", result
            new = result["result"]
            await hass.async_block_till_done()
            assert (
                new.unique_id != legacy.unique_id
                and new.state.value == legacy.state.value == "loaded"
            )
            checks.append(
                "reconfigure_legacy_controller_then_add_former_fixture_without_identity_collision"
            )
            # Partial filesystem cleanup retains minimal metadata for retry.
            broken = Path(folder) / "partial-cleanup"
            broken.mkdir()
            (broken / "installation.json").write_text(json.dumps(legacy_data["installation"]))

            def partial_remove(path):
                (path / "installation.json").unlink()
                raise OSError("simulated partial cleanup")

            with patch("shutil.rmtree", side_effect=partial_remove):
                try:
                    await hass.async_add_executor_job(api.remove_private_folder, broken)
                except OSError:
                    pass
                else:
                    raise AssertionError("partial cleanup accepted")
            assert (
                json.loads((broken / "installation.json").read_text())
                == legacy_data["installation"]
            )
            shutil.rmtree(broken)
            checks.append("partial_cleanup_restores_metadata_for_retry")
            await hass.config_entries.async_remove(legacy.entry_id)
            await hass.config_entries.async_remove(new.entry_id)
            return {"passed": True, "checks": checks, "actual_ha_restart": True}
        finally:
            wire.offline = False
            wire.protocol_error = None
            if hass:
                await hass.async_stop(force=True)
            shutil.rmtree(folder)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(main())))
