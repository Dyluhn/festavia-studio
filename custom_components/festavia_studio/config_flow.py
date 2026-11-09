"""Home Assistant commissioning, reconfiguration, and device options."""

import copy
import http.client
import probatio as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from .api import commission, has_recovery, private_folder, recover_folder, StudioError
from .backend.lib.errors import AuthenticationError, CertificateError, RecoveryPending
from .backend.lib.net_client import save_credentials
from homeassistant.helpers import issue_registry as ir
import json
import shutil
from .backend.lib.bridge import probe
from .const import DOMAIN


def choices(options):
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[{"value": k, "label": v} for k, v in options.items()],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


PASSWORD = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
)


class FestaviaFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 2

    def __init__(self):
        self.installation = {"schema": 1, "mode": "bridge", "selected": []}
        self.device = None
        self.inventory = []
        self.selection = None
        self.candidate = None
        self.networks = []
        self.saved_entry = None
        self.connection_only = False
        self.hue_entry_id = None
        self.orphans_confirmed = False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return FestaviaOptions()

    async def pending(self):
        if self.saved_entry:
            return await self.hass.async_add_executor_job(
                has_recovery, private_folder(self.hass, self.saved_entry.entry_id)
            )
        return False

    async def run(self, op, data=None):
        if op == "select" and await self.pending():
            raise RecoveryPending("Restore the captured installation before changing fixtures")
        self.installation, result = await self.hass.async_add_executor_job(
            commission, self.installation, self.device, op, data or {}
        )
        return result

    def busy(self):
        return bool(
            self.saved_entry
            and getattr(self.saved_entry, "runtime_data", None)
            and self.saved_entry.runtime_data.playing
        )

    async def async_step_user(self, user_input=None):
        entries = {
            e.entry_id: e
            for e in self.hass.config_entries.async_entries("hue")
            if "api_key" in e.data
        }
        errors = {}
        if user_input is not None:
            if user_input["bridge"] == "manual":
                return await self.async_step_manual()
            entry = entries.get(user_input["bridge"])
            if entry is not None:
                try:
                    summary = await self.run(
                        "bridge",
                        {
                            "host": entry.data["host"],
                            "key": entry.data["api_key"],
                            "bridge_id": entry.unique_id,
                        },
                    )
                    self.hue_entry_id = entry.entry_id
                    self.inventory = summary["lights"]
                    return await self.after_bridge()
                except (OSError, http.client.HTTPException, RuntimeError, ValueError, KeyError):
                    errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("bridge"): choices(
                        {
                            **{k: v.title for k, v in entries.items()},
                            "manual": "Pair another Hue bridge",
                        }
                    )
                }
            ),
        )

    async def async_step_manual(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                self.candidate = await self.hass.async_add_executor_job(probe, user_input["host"])
                if (
                    self.saved_entry
                    and self.connection_only
                    and self.candidate["id"]
                    != self.saved_entry.data["installation"]["bridge"]["id"]
                ):
                    return self.async_abort(reason="unique_id_mismatch")
                return await self.async_step_link()
            except (OSError, http.client.HTTPException, RuntimeError, ValueError, KeyError):
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="manual", errors=errors, data_schema=vol.Schema({vol.Required("host"): str})
        )

    async def async_step_link(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                summary = await self.run("pair", {"bridge": self.candidate})
                self.inventory = summary["lights"]
                self.hue_entry_id = None
                return await self.after_bridge()
            except (OSError, http.client.HTTPException, RuntimeError, ValueError, KeyError):
                errors["base"] = "link_required"
        return self.async_show_form(
            step_id="link",
            errors=errors,
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": self.candidate["name"],
                "bridge_id": self.candidate["id"],
                "fingerprint": self.candidate["pin"],
            },
        )

    async def after_bridge(self):
        if (
            self.saved_entry
            and self.connection_only
            and self.installation["bridge"]["id"]
            != self.saved_entry.data["installation"]["bridge"]["id"]
        ):
            return self.async_abort(reason="unique_id_mismatch")
        if self.connection_only:
            if self.device:
                return await self.async_step_device()
            return await self.finish()
        return await self.async_step_fixtures()

    def conflict(self, ids=None, device=None):
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if self.saved_entry and entry.entry_id == self.saved_entry.entry_id:
                continue
            other = entry.data.get("installation", {})
            if (
                ids
                and other.get("bridge", {}).get("id")
                == self.installation.get("bridge", {}).get("id")
                and set(ids) & set(other.get("selected", []))
            ):
                return True
            if (
                device
                and other.get("mode") == "native"
                and (entry.data.get("device") or {}).get("tls_sha256") == device.get("tls_sha256")
            ):
                return True
        return False

    async def async_step_fixtures(self, user_input=None):
        errors = {}
        if await self.pending():
            return self.async_abort(reason="stop_first")
        if not self.inventory:
            try:
                self.inventory = (await self.run("refresh"))["lights"]
            except (OSError, http.client.HTTPException, RuntimeError, ValueError, KeyError):
                return self.async_abort(reason="cannot_connect")
        if not self.inventory:
            return self.async_abort(reason="no_festavia")
        if user_input is not None:
            self.selection = {"ids": user_input["lights"], "mode": user_input["mode"]}
            if self.conflict(ids=self.selection["ids"]):
                return self.async_abort(reason="already_configured")
            if self.busy():
                errors["base"] = "stop_first"
            elif user_input["mode"] == "native":
                return await self.async_step_device()
            else:
                try:
                    await self.run("select", self.selection)
                    return await self.finish()
                except (OSError, http.client.HTTPException, RuntimeError, ValueError, KeyError):
                    errors["base"] = "invalid_selection"
        return self.async_show_form(
            step_id="fixtures",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "lights", default=self.installation.get("selected", [])
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": l["id"], "label": f"{l['name']} ({l['model']})"}
                                for l in self.inventory
                            ],
                            multiple=True,
                        )
                    ),
                    vol.Required("mode", default=self.installation.get("mode", "bridge")): choices(
                        {
                            "native": "Individual pucks and animation · ESP32-C6",
                            "bridge": "Hue bridge gradient · static colors",
                        }
                    ),
                }
            ),
        )

    async def async_step_device(self, user_input=None):
        errors = {}
        if user_input is not None:
            candidate = {
                "target": "esp32c6",
                "url": user_input["url"].strip().rstrip("/"),
                "token": user_input.get("token") or (self.device or {}).get("token", ""),
                "tls_sha256": user_input.get("tls_sha256")
                or (self.device or {}).get("tls_sha256", ""),
            }
            try:
                if self.conflict(device=candidate):
                    return self.async_abort(reason="already_configured")
                if (
                    self.saved_entry
                    and await self.pending()
                    and candidate["tls_sha256"]
                    != (self.saved_entry.data.get("device") or {}).get("tls_sha256")
                ):
                    return self.async_abort(reason="stop_first")
                result = await self.run("device", {"credentials": candidate, "inspect_only": True})
                self.device = candidate
                if self.connection_only:
                    status = await self.run("esp-status")
                    if status.get("approved_network"):
                        return await self.finish()
                    return await self.async_step_network()
                if result.get("armed"):
                    return await self.async_step_device_recover()
                return await self.async_step_network()
            except (OSError, http.client.HTTPException, RuntimeError, ValueError, KeyError):
                errors["base"] = "device_connection"
        return self.async_show_form(
            step_id="device",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("url", default=(self.device or {}).get("url", "https://")): str,
                    (vol.Optional("token") if self.device else vol.Required("token")): PASSWORD,
                    (
                        vol.Optional("tls_sha256") if self.device else vol.Required("tls_sha256")
                    ): str,
                }
            ),
        )

    async def async_step_device_recover(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                await self.run("recover_device")
                # A previously removed/offline entry may own a bridge journal
                # as well. Recover its original targets before retiring secrets.
                await self.recover_orphans()
                return await self.async_step_network()
            except (
                OSError,
                http.client.HTTPException,
                RuntimeError,
                ValueError,
                KeyError,
                StudioError,
            ):
                errors["base"] = "recovery_failed"
        return self.async_show_form(
            step_id="device_recover", errors=errors, data_schema=vol.Schema({})
        )

    async def orphan_folders(self):
        def find():
            selected = set((self.selection or {}).get("ids", self.installation.get("selected", [])))
            matches = []
            for marker in private_folder(self.hass, "").glob("*/removal-pending.json"):
                old = json.loads((marker.parent / "installation.json").read_text())
                path = marker.parent / "esp/credentials.json"
                same_device = bool(
                    self.device
                    and path.exists()
                    and json.loads(path.read_text()).get("tls_sha256")
                    == self.device.get("tls_sha256")
                )
                same_lights = old.get("bridge", {}).get("id") == self.installation.get(
                    "bridge", {}
                ).get("id") and selected & set(old.get("selected", []))
                if same_lights or same_device:
                    matches.append(marker.parent)
            return matches

        return await self.hass.async_add_executor_job(find)

    async def async_step_orphan_recover(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                await self.recover_orphans()
                self.orphans_confirmed = True
                return await self.finish()
            except (OSError, http.client.HTTPException, RuntimeError, ValueError, KeyError):
                errors["base"] = "recovery_failed"
        return self.async_show_form(
            step_id="orphan_recover", errors=errors, data_schema=vol.Schema({})
        )

    async def recover_orphans(self):
        folders = await self.orphan_folders()

        def restore():
            removed = []
            for folder in folders:
                old = json.loads((folder / "installation.json").read_text())
                if old.get("bridge", {}).get("id") != self.installation.get("bridge", {}).get("id"):
                    raise RecoveryPending(
                        "Complete the repair for the previous bridge before reusing this ESP32"
                    )
                if self.device:
                    path = folder / "esp/credentials.json"
                    if path.exists():
                        if json.loads(path.read_text())["tls_sha256"] != self.device["tls_sha256"]:
                            raise RecoveryPending("Restore the previous ESP32 before replacing it")
                        save_credentials(path, self.device)
                old["bridge"] = self.installation["bridge"]
                save_credentials(folder / "installation.json", old)
                recover_folder(folder)
                shutil.rmtree(folder)
                removed.append(folder.name)
            return removed

        for entry_id in await self.hass.async_add_executor_job(restore):
            ir.async_delete_issue(self.hass, DOMAIN, "recovery_" + entry_id)

    async def async_step_network(self, user_input=None):
        errors = {}
        try:
            status = await self.run("esp-status")
            if status.get("approved_network"):
                if self.connection_only:
                    return await self.finish()
                await self.run("select", self.selection)
                return await self.finish()
            if user_input is not None:
                network = next(n for n in self.networks if n["extpan"] == user_input["network"])
                await self.run("join", {**network, "legacy": user_input["legacy"]})
                return self.async_show_form(step_id="joined", data_schema=vol.Schema({}))
            self.networks = (await self.run("scan"))["networks"]
        except (
            OSError,
            http.client.HTTPException,
            RuntimeError,
            ValueError,
            KeyError,
            StopIteration,
        ):
            errors["base"] = "network_failed"
        return self.async_show_form(
            step_id="network",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("network"): choices(
                        {
                            n[
                                "extpan"
                            ]: f"{n['extpan']} · channel {n['channel']} · joining {'open' if n.get('permit_join') else 'closed'}"
                            for n in self.networks
                        }
                    ),
                    vol.Required("legacy", default=False): bool,
                }
            ),
        )

    async def async_step_joined(self, user_input=None):
        return await self.async_step_network()

    async def finish(self):
        if self.saved_entry and not self.connection_only and await self.pending():
            return self.async_abort(reason="stop_first")
        if not self.saved_entry and not self.orphans_confirmed and await self.orphan_folders():
            return await self.async_step_orphan_recover()
        identifier = (
            f"{self.installation['bridge']['id']}_{'_'.join(sorted(self.installation['selected']))}"
        )
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if self.saved_entry and entry.entry_id == self.saved_entry.entry_id:
                continue
            other = entry.data.get("installation", {})
            same_bridge = other.get("bridge", {}).get("id") == self.installation["bridge"]["id"]
            overlap = set(other.get("selected", [])) & set(self.installation["selected"])
            same_esp = self.device and (entry.data.get("device") or {}).get(
                "url"
            ) == self.device.get("url")
            if (same_bridge and overlap) or (
                same_esp and other.get("mode") == self.installation["mode"] == "native"
            ):
                return self.async_abort(reason="already_configured")
        if self.saved_entry:
            # Keep existing IDs, automations, palettes and scene storage stable.
            current = getattr(self.saved_entry, "runtime_data", None)
            if current and not current.api.closed:
                try:
                    await current.begin_reconfigure(connections_only=self.connection_only)
                except StudioError:
                    return self.async_abort(reason="stop_first")
            return self.async_update_reload_and_abort(
                self.saved_entry,
                data_updates={
                    "installation": self.installation,
                    "device": self.device,
                    "hue_entry_id": self.hue_entry_id,
                },
                reason="reauth_successful" if self.source == "reauth" else "reconfigure_successful",
            )
        await self.async_set_unique_id(identifier)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="Festavia Studio",
            data={
                "installation": self.installation,
                "device": self.device,
                "hue_entry_id": self.hue_entry_id,
            },
            options={"brightness_limit": 100},
        )

    async def async_step_reconfigure(self, user_input=None):
        self.saved_entry = self._get_reconfigure_entry()
        self.installation = copy.deepcopy(self.saved_entry.data["installation"])
        self.device = copy.deepcopy(self.saved_entry.data.get("device"))
        self.hue_entry_id = self.saved_entry.data.get("hue_entry_id")
        return self.async_show_menu(
            step_id="reconfigure", menu_options=["connection", "fixtures", "recover"]
        )

    async def async_step_connection(self, user_input=None):
        self.connection_only = True
        return await self.async_step_user(user_input)

    async def async_step_recover(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                c = getattr(self.saved_entry, "runtime_data", None)
                if c and not c.api.closed:
                    async with c.action_lock:
                        async with c.api.lock:
                            await self.hass.async_add_executor_job(
                                recover_folder, private_folder(self.hass, self.saved_entry.entry_id)
                            )
                            await self.hass.async_add_executor_job(c.api.app.close)
                            c.api.app.studio = None
                    await c.async_request_refresh()
                else:
                    await self.hass.async_add_executor_job(
                        recover_folder, private_folder(self.hass, self.saved_entry.entry_id)
                    )
                return self.async_abort(reason="recovery_successful")
            except (
                OSError,
                http.client.HTTPException,
                RuntimeError,
                ValueError,
                KeyError,
                StudioError,
            ):
                errors["base"] = "recovery_failed"
        return self.async_show_form(step_id="recover", errors=errors, data_schema=vol.Schema({}))

    async def async_step_reauth(self, entry_data):
        self.saved_entry = self._get_reauth_entry()
        self.installation = copy.deepcopy(entry_data["installation"])
        self.device = copy.deepcopy(entry_data.get("device"))
        self.hue_entry_id = entry_data.get("hue_entry_id")
        self.connection_only = True
        await self.async_set_unique_id(self.saved_entry.unique_id)
        self._abort_if_unique_id_mismatch()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                bridge = self.installation["bridge"]
                hue = (
                    self.hass.config_entries.async_get_entry(self.hue_entry_id)
                    if self.hue_entry_id
                    else None
                )
                key = user_input.get("bridge_key") or (
                    hue.data["api_key"] if hue else bridge["key"]
                )
                host = hue.data["host"] if hue else bridge["address"]
                candidate, _ = await self.hass.async_add_executor_job(
                    commission,
                    self.installation,
                    self.device,
                    "bridge",
                    {"host": host, "key": key, "bridge_id": bridge["id"]},
                )
                if candidate["bridge"]["pin"] != bridge["pin"]:
                    raise CertificateError("bridge")
                device = copy.deepcopy(self.device)
                if device:
                    device["token"] = user_input.get("device_token") or device["token"]
                    await self.hass.async_add_executor_job(
                        commission,
                        self.installation,
                        device,
                        "device",
                        {"credentials": device, "inspect_only": True},
                    )
                self.installation["bridge"] = candidate["bridge"]
                if user_input.get("bridge_key"):
                    self.hue_entry_id = None
                self.device = device
                return await self.finish()
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except CertificateError:
                errors["base"] = "certificate_changed"
            except (OSError, http.client.HTTPException, RuntimeError, ValueError, KeyError):
                errors["base"] = "cannot_connect"
        schema = {vol.Optional("bridge_key"): PASSWORD}
        if self.device:
            schema[vol.Optional("device_token")] = PASSWORD
        return self.async_show_form(
            step_id="reauth_confirm", errors=errors, data_schema=vol.Schema(schema)
        )


class FestaviaOptions(OptionsFlow):
    """Installation choices; runtime controls remain entities and actions."""

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(step_id="init", menu_options=["palettes", "network"])

    async def async_step_palettes(self, user_input=None):
        c = self.config_entry.runtime_data
        if user_input is not None:
            async with c.action_lock:
                await c.command("delete", {"name": user_input["preset"]})
                if c.preset == user_input["preset"]:
                    c.preset = "Custom"
                    await c.persist()
            return self.async_create_entry(data=dict(self.config_entry.options))
        return self.async_show_form(
            step_id="palettes",
            data_schema=vol.Schema(
                {vol.Required("preset"): choices({n: n for n in c.data["presets"]})}
            ),
        )

    async def async_step_network(self, user_input=None):
        c = self.config_entry.runtime_data
        if not c.api.app.device_path.exists():
            return self.async_abort(reason="no_esp")
        try:
            status = await c.api.setup("esp-status")
        except StudioError:
            return self.async_abort(reason="cannot_connect")
        if user_input is not None:
            return self.async_create_entry(data=dict(self.config_entry.options))
        return self.async_show_form(
            step_id="network",
            data_schema=vol.Schema({}),
            description_placeholders={
                "state": "Joined and approved"
                if status.get("approved_network")
                else "Not joined. Use Reconfigure to commission this ESP32.",
                "channel": str(status.get("channel", "unknown")),
            },
        )
