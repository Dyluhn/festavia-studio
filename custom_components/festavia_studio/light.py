"""The Studio effect behaves like a normal Home Assistant light."""

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from .entity import StudioEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([StudioLight(entry.runtime_data)])


class StudioLight(StudioEntity, LightEntity):
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_supported_features = LightEntityFeature.EFFECT

    def __init__(self, coordinator):
        super().__init__(coordinator, "effect_light", "Effect light", "mdi:string-lights")

    @property
    def is_on(self):
        return self.coordinator.playing

    @property
    def brightness(self):
        return round(self.coordinator.scene.get("brightness", 10) * 255 / 100)

    @property
    def effect(self):
        return self.coordinator.scene.get("effect", "static")

    @property
    def effect_list(self):
        return self.coordinator.data["effects"]

    def _hue_group_has_priority(self):
        watcher = self.coordinator.takeover
        return bool(
            watcher
            and watcher.enabled
            and self._context
            and self._context.id in watcher.hue_contexts
        )

    async def async_turn_on(self, **kwargs):
        if self._hue_group_has_priority():
            return
        changes = {}
        if ATTR_BRIGHTNESS in kwargs:
            value = kwargs[ATTR_BRIGHTNESS]
            if not value:
                await self.async_turn_off()
                return
            changes["brightness"] = max(
                1, min(self.coordinator.data["brightness_limit"], value * 100 / 255)
            )
        if ATTR_EFFECT in kwargs:
            changes["effect"] = kwargs[ATTR_EFFECT]
        await self.coordinator.play(changes=changes)

    async def async_turn_off(self, **kwargs):
        if self._hue_group_has_priority():
            return
        async with self.coordinator.action_lock:
            await self.coordinator.command("off")
