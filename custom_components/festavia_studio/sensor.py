from homeassistant.components.sensor import SensorEntity
from .entity import StudioEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Playback(entry.runtime_data)])


class Playback(StudioEntity, SensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator, "playback", "Playback", "mdi:animation-play")

    @property
    def native_value(self):
        return self.coordinator.data["player"].get("state", "unknown")

    @property
    def extra_state_attributes(self):
        c = self.coordinator
        return {
            "entry_id": c.entry.entry_id,
            "scene": c.scene,
            "preset": c.preset,
            "presets": list(c.data["presets"]),
            "palette": c.palette,
            "palettes": list(c.data["palettes"]),
            "effects": c.data["effects"],
            "positions": c.data["positions"],
            "palette_limit": c.data["palette_limit"],
            "brightness_limit": c.data["brightness_limit"],
            "mode": c.data["mode"],
            "playing": c.playing,
            "lights": c.data["lights"],
            "reason": c.data["player"].get("reason"),
        }
