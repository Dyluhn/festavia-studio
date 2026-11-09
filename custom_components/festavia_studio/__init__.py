"""Native HA entities and actions for the Festavia Studio lighting engine."""

from pathlib import Path
import probatio as vol
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.storage import Store
import logging
import http.client
import json
from .api import NativeClient, StudioError, private_folder, recover_folder, remove_private_folder
from .const import DOMAIN, PLATFORMS, VERSION
from .coordinator import StudioCoordinator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
LOGGER = logging.getLogger(__name__)

FIELDS = {
    vol.Optional("colors"): [str],
    vol.Optional("snake_colors"): [str],
    vol.Optional("effect"): str,
    vol.Optional("brightness"): vol.Coerce(float),
    vol.Optional("speed"): vol.Coerce(float),
    vol.Optional("reverse"): bool,
}


async def async_setup(hass, config):
    hass.data.setdefault(DOMAIN, {})
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                "/festavia_studio/festavia-studio-card.js",
                str(Path(__file__).parent / "frontend" / "festavia-studio-card.js"),
                False,
            )
        ]
    )
    # Lovelace waits for registered resources before constructing custom cards.
    # Do not import this card globally before HA initializes its element registry.
    await async_register_resource(hass)

    async def handle(call):
        entries = {
            e.entry_id: e.runtime_data
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.state.value == "loaded" and getattr(e, "runtime_data", None)
        }
        entry_id = call.data.get("entry_id")
        if entry_id:
            coordinator = entries.get(entry_id)
        else:
            coordinator = next(iter(entries.values())) if len(entries) == 1 else None
        if coordinator is None:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="entry_missing")
        changes = {
            key: value
            for key, value in call.data.items()
            if key in ("colors", "snake_colors", "effect", "brightness", "speed", "reverse")
        }
        if call.service == "play":
            await coordinator.play(call.data.get("preset"), changes)
        elif call.service in ("configure", "set_palette"):
            await coordinator.configure(changes, apply=call.data.get("apply", True))
        elif call.service in ("load_preset", "load_scene"):
            await coordinator.choose_preset(call.data["preset"])
        elif call.service in ("save_preset", "save_scene"):
            await coordinator.save_preset(call.data["name"])
        elif call.service == "load_palette":
            await coordinator.choose_palette(
                call.data["palette"], call.data.get("layer", "background")
            )
        elif call.service == "save_palette":
            await coordinator.save_palette(call.data["name"], call.data.get("layer", "background"))
        elif call.service in ("delete_palette", "delete_scene"):
            await coordinator.delete_saved(
                call.data["name"], palette=call.service == "delete_palette"
            )
        else:
            async with coordinator.action_lock:
                await coordinator.command(
                    call.service,
                    {"off": call.data.get("off", False), "manual": call.service == "release"},
                )

    base = {vol.Optional("entry_id"): str}
    for name in (
        "play",
        "configure",
        "set_palette",
        "stop",
        "off",
        "release",
        "save_preset",
        "load_preset",
        "save_scene",
        "load_scene",
        "save_palette",
        "load_palette",
        "delete_palette",
        "delete_scene",
    ):
        fields = dict(base)
        if name in ("play", "configure", "set_palette"):
            fields.update(FIELDS)
        if name == "set_palette":
            fields.pop(vol.Optional("colors"), None)
            fields[vol.Required("colors")] = [str]
        if name == "play":
            fields[vol.Optional("preset")] = str
        if name in ("configure", "set_palette"):
            fields[vol.Optional("apply", default=True)] = bool
        if name == "stop":
            fields[vol.Optional("off", default=False)] = bool
        if name in ("load_preset", "load_scene"):
            fields[vol.Required("preset")] = str
        if name == "load_palette":
            fields[vol.Required("palette")] = str
        if name in ("load_palette", "save_palette"):
            fields[vol.Optional("layer", default="background")] = vol.In(("background", "snake"))
        if name in ("save_preset", "save_scene", "save_palette", "delete_palette", "delete_scene"):
            fields[vol.Required("name")] = str
        hass.services.async_register(DOMAIN, name, handle, schema=vol.Schema(fields))
    return True


async def async_setup_entry(hass, entry):
    await async_register_resource(hass)
    api = NativeClient(hass, entry)
    try:
        await api.initialize()
        coordinator = StudioCoordinator(hass, entry, api)
        await coordinator.load()
        await coordinator.async_config_entry_first_refresh()
    except Exception as exc:
        if api.app:
            await api.close(restore=False)
        from .api import StudioAuthError
        from homeassistant.exceptions import ConfigEntryAuthFailed

        if isinstance(exc, StudioAuthError):
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_" + exc.source
            ) from None
        if isinstance(exc, StudioError):
            from homeassistant.exceptions import ConfigEntryNotReady

            raise ConfigEntryNotReady(translation_domain=DOMAIN, translation_key=exc.key) from None
        raise
    ir.async_delete_issue(hass, DOMAIN, "recovery_" + entry.entry_id)
    entry.runtime_data = coordinator
    from .takeover import HueTakeover

    coordinator.takeover = HueTakeover(coordinator)
    coordinator.takeover.start()

    async def stop_takeover(event):
        await coordinator.takeover.close()

    entry.async_on_unload(hass.bus.async_listen_once("homeassistant_stop", stop_takeover))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_migrate_entry(hass, entry):
    """Import the private installation once, retaining registry and scene IDs."""
    if entry.version > 2:
        return False
    if entry.version == 1:

        def read():
            folder = private_folder(hass, entry.entry_id)
            installation = json.loads((folder / "installation.json").read_text())
            device = folder / "esp" / "credentials.json"
            options_file = folder / "migration-options.json"
            options = (
                json.loads(options_file.read_text())
                if options_file.exists()
                else dict(entry.options)
            )
            return {
                "installation": installation,
                "device": json.loads(device.read_text()) if device.exists() else None,
            }, options

        try:
            data, options = await hass.async_add_executor_job(read)
        except (OSError, ValueError):
            return False
        hass.config_entries.async_update_entry(entry, data=data, options=options, version=2)
    return True


async def async_register_resource(hass):
    url = f"/festavia_studio/festavia-studio-card.js?v={VERSION}"
    resources = hass.data["lovelace"].resources
    if isinstance(resources, ResourceStorageCollection):
        await resources.async_get_info()
        existing = next(
            (
                item
                for item in resources.async_items()
                if item["url"].split("?")[0] == url.split("?")[0]
            ),
            None,
        )
        if existing:
            if existing["url"] != url:
                await resources.async_update_item(
                    existing["id"], {"url": url, "res_type": "module"}
                )
        else:
            await resources.async_create_item({"url": url, "res_type": "module"})


async def async_remove_resource(hass):
    resources = hass.data["lovelace"].resources
    if isinstance(resources, ResourceStorageCollection):
        await resources.async_get_info()
        for item in list(resources.async_items()):
            if item["url"].split("?")[0] == "/festavia_studio/festavia-studio-card.js":
                await resources.async_delete_item(item["id"])


async def async_unload_entry(hass, entry):
    c = entry.runtime_data
    if c.takeover:
        await c.takeover.close()
    # Drain actions before closing; a replacement coordinator cannot acquire the
    # same fixture while an executor operation from this one is still running.
    async with c.action_lock:
        c.reconfiguring = True
        try:
            await c.api.close()
        except StudioError:
            # A network outage must not strand HA in FAILED_UNLOAD. The durable
            # lease remains and the next setup retries restoration first.
            from .backend.lib.net_client import save_credentials

            if await hass.async_add_executor_job(c.api.app.recovery_pending):
                await hass.async_add_executor_job(
                    save_credentials,
                    private_folder(hass, entry.entry_id) / "unload-pending.json",
                    {"restore": True},
                )
                recovery_notice(hass, entry.entry_id)
            await c.api.close(restore=False)
        return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass, entry):
    folder = private_folder(hass, entry.entry_id)
    current = getattr(entry, "runtime_data", None)
    if current:
        async with current.action_lock:
            current.reconfiguring = True
            await current.api.close(restore=False)
        await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    try:
        # HA calls removal even when unload failed, and deletes the entry before
        # this callback. Preserve the recovery material if contact is lost.
        if folder.exists():
            await hass.async_add_executor_job(recover_folder, folder)
            await hass.async_add_executor_job(remove_private_folder, folder)
        ir.async_delete_issue(hass, DOMAIN, "recovery_" + entry.entry_id)
    except (OSError, http.client.HTTPException, RuntimeError, ValueError, KeyError):
        marker = folder / "removal-pending.json"
        from .backend.lib.net_client import save_credentials

        await hass.async_add_executor_job(save_credentials, marker, {"entry_id": entry.entry_id})
        recovery_notice(hass, entry.entry_id)
    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.scene").async_remove()
    if not hass.config_entries.async_entries(DOMAIN):
        await async_remove_resource(hass)


def recovery_notice(hass, entry_id):
    ir.async_create_issue(
        hass,
        DOMAIN,
        "recovery_" + entry_id,
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.ERROR,
        translation_key="recovery_pending",
        data={"entry_id": entry_id},
    )
