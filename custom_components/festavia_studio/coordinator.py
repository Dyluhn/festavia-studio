"""One shared poll and a persisted, staged scene for all native HA controls."""

import asyncio
import copy
from datetime import timedelta
import logging
import math
import re
from homeassistant.exceptions import ConfigEntryAuthFailed, ServiceValidationError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import StudioError, StudioAuthError, has_recovery, private_folder
from .backend.lib.player import compile_puck_scene
from .const import DOMAIN

DEFAULT_SCENE = {
    "colors": ["#ff382e", "#ff8c30", "#ffce72"],
    "effect": "static",
    "brightness": 10,
    "speed": 1,
    "reverse": False,
    "fps": 10,
    "smoothing": 10240,
    "layout_mode": "pucks",
}


def validate_scene(scene, status):
    """Bound the simple native HA editor before any physical action."""
    scene = copy.deepcopy(scene)
    colors = scene.get("colors")
    if (
        not isinstance(colors, list)
        or not 1 <= len(colors) <= status["palette_limit"]
        or any(not isinstance(c, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in colors)
    ):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="palette_count",
            translation_placeholders={"limit": str(status["palette_limit"])},
        )
    if scene.get("effect") not in status["effects"]:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_effect")
    for key, low, high in (("brightness", 1, status["brightness_limit"]), ("speed", 0.1, 20)):
        value = scene.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="value_range",
                translation_placeholders={"field": key, "low": str(low), "high": str(high)},
            )
    if type(scene.get("reverse")) is not bool:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_scene")
    scene["positions"] = status["positions"]
    scene["colors"] = [c.lower() for c in colors]
    if status.get("mode") == "native":
        values = [max(int(c[i : i + 2], 16) for i in (1, 3, 5)) for c in scene["colors"]]
        if not all(values):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="palette_black")
        if len(set(values)) != 1:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="palette_tone")
        try:
            compile_puck_scene(scene)
        except (ValueError, TypeError, KeyError):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_scene"
            ) from None
    return scene


class StudioCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, api):
        super().__init__(
            hass,
            logging.getLogger(__name__),
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=10),
        )
        self.api = api
        self.entry = entry
        self.scene = copy.deepcopy(DEFAULT_SCENE)
        self.preset = "Custom"
        self.palette = "Custom"
        self.action_lock = asyncio.Lock()
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.scene")
        self._remote_scene = None
        self.reconfiguring = False
        self.acquiring = False
        self.takeover = None

    async def load(self):
        saved = await self.store.async_load()
        if saved:
            self.scene = saved.get("scene", self.scene)
            self.preset = saved.get("preset", "Custom")
            self.palette = saved.get("palette", "Custom")

    @property
    def playing(self):
        return bool(self.data and self.data["player"].get("playing"))

    async def _async_update_data(self):
        try:
            result = await self.api.request()
        except StudioAuthError as exc:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_" + exc.source
            ) from None
        except StudioError as exc:
            raise UpdateFailed(str(exc)) from None
        remote = result.get("scene")
        # Recover an active device scene without replacing idle saved controls.
        if (
            remote
            and remote != self._remote_scene
            and result["player"].get("playing")
            and remote.get("effect") in result["effects"]
            and isinstance(remote.get("colors"), list)
            and all(
                isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in remote["colors"]
            )
        ):
            self.scene = {**copy.deepcopy(DEFAULT_SCENE), **copy.deepcopy(remote)}
            self.preset = "Custom"
            self.palette = "Custom"
        if result["palettes"].get(self.palette) != self.scene.get("colors"):
            self.palette = "Custom"
        self._remote_scene = copy.deepcopy(remote)
        if not result["player"].get("playing"):
            if self.preset not in result["presets"]:
                self.preset = "Custom"
            self.scene["brightness"] = max(
                1, min(result["brightness_limit"], self.scene.get("brightness", 10))
            )
            if self.scene.get("effect") not in result["effects"]:
                self.scene["effect"] = result["effects"][0]
        return result

    def check_ready(self):
        if self.reconfiguring or self.api.closed:
            raise StudioError("unloading")

    async def begin_reconfigure(self, *, connections_only=False):
        async with self.action_lock:
            self.check_ready()
            if not connections_only:
                folder = private_folder(self.hass, self.entry.entry_id)
                if await self.hass.async_add_executor_job(has_recovery, folder):
                    # Retire only firmware-confirmed legacy journals. If a light
                    # was removed, keep protection until explicit recovery.
                    await self.api.request()
                    if await self.hass.async_add_executor_job(has_recovery, folder):
                        raise StudioError("recovery_pending")
            self.reconfiguring = True

    async def set_hue_takeover(self, enabled):
        async with self.action_lock:
            self.check_ready()
            if enabled:
                await self.takeover.ensure_ready(force=True)
            if self.playing and self.data["mode"] == "native":
                await self.api.takeover_keepalive(enabled=enabled)
            self.hass.config_entries.async_update_entry(
                self.entry, options={**self.entry.options, "allow_hue_takeover": enabled}
            )
            self.takeover.new_acquisition()
            self.async_update_listeners()

    async def save_preset(self, name):
        name = name.strip()
        if not 1 <= len(name) <= 60 or name.casefold() == "custom":
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="preset_name")
        async with self.action_lock:
            self.check_ready()
            await self.command("save", {"name": name, "scene": copy.deepcopy(self.scene)})
            self.preset = name
            await self.persist()

    async def persist(self):
        await self.store.async_save(
            {"scene": self.scene, "preset": self.preset, "palette": self.palette}
        )
        self.async_update_listeners()

    async def configure(self, changes, apply=True, preset="Custom", palette=None):
        async with self.action_lock:
            self.check_ready()
            if palette is not None and self.data["palettes"].get(palette) != changes.get("colors"):
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="preset_missing"
                )
            candidate = validate_scene({**self.scene, **changes}, self.data)
            if self.playing and apply:
                await self.command("play", {"scene": candidate, "seconds": 0})
            self.scene, self.preset = candidate, preset
            if palette is not None:
                self.palette = palette
            elif self.data["palettes"].get(self.palette) != candidate["colors"]:
                self.palette = "Custom"
            await self.persist()

    async def save_palette(self, name):
        name = name.strip()
        if not 1 <= len(name) <= 60 or name.casefold() == "custom":
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="preset_name")
        async with self.action_lock:
            self.check_ready()
            scene = validate_scene(self.scene, self.data)
            await self.command("save_palette", {"name": name, "colors": scene["colors"]})
            self.palette = name
            await self.persist()

    async def choose_palette(self, name):
        if name == "Custom":
            async with self.action_lock:
                self.check_ready()
                self.palette = name
                await self.persist()
            return
        if name not in self.data["palettes"]:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="preset_missing"
            )
        await self.configure({"colors": self.data["palettes"][name]}, palette=name)

    async def delete_saved(self, name, *, palette=False):
        async with self.action_lock:
            self.check_ready()
            if name not in self.data["palettes" if palette else "presets"]:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="preset_missing"
                )
            await self.command("delete_palette" if palette else "delete", {"name": name})
            if palette and self.palette == name:
                self.palette = "Custom"
            if not palette and self.preset == name:
                self.preset = "Custom"
            await self.persist()

    async def command(self, operation, data=None):
        self.check_ready()
        try:
            if (
                operation == "release"
                and self.data["mode"] == "native"
                and not self.data["player"].get("hue_takeover_supported")
            ):
                raise StudioError("takeover_update_required")
            if operation == "play" and self.takeover:
                await self.takeover.ensure_ready()
                baseline = (
                    await self.api.hue_control_baseline()
                    if self.data["mode"] == "native" and self.takeover.enabled
                    else {}
                )
                self.takeover.new_acquisition()
                self.takeover.setup_states = baseline
                self.takeover.output_scene = copy.deepcopy((data or {}).get("scene", self.scene))
                self.acquiring = True
            try:
                result = await self.api.request(operation, data)
            finally:
                self.acquiring = False
        except StudioError as exc:
            if isinstance(exc, StudioAuthError):
                self.entry.async_start_reauth(self.hass)
            raise
        self._remote_scene = copy.deepcopy(result.get("scene"))
        self.async_set_updated_data(result)

    async def play(self, preset=None, changes=None):
        async with self.action_lock:
            self.check_ready()
            scene = self.scene
            if preset is not None:
                if preset not in self.data["presets"]:
                    raise ServiceValidationError(
                        translation_domain=DOMAIN, translation_key="preset_missing"
                    )
                scene = {**DEFAULT_SCENE, **self.data["presets"][preset]}
            scene = validate_scene({**scene, **(changes or {})}, self.data)
            await self.command("play", {"scene": scene, "seconds": 0})
            self.scene, self.preset = scene, preset or "Custom"
            if self.data["palettes"].get(self.palette) != scene["colors"]:
                self.palette = "Custom"
            await self.persist()

    async def choose_preset(self, name):
        if name == "Custom":
            async with self.action_lock:
                self.check_ready()
                self.preset = name
                await self.persist()
            return
        if name not in self.data["presets"]:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="preset_missing"
            )
        scene = {**DEFAULT_SCENE, **self.data["presets"][name]}
        await self.configure(scene, preset=name)
