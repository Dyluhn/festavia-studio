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
            "snake_palette": c.snake_palette,
            "palettes": list(c.data["palettes"]),
            "effects": c.data["effects"],
            "positions": c.data["positions"],
            "palette_limit": c.data["palette_limit"],
            "animated_palette_limit": c.data.get("animated_palette_limit", 9),
            "applying": c.data["player"].get("applying", False),
            "brightness_limit": c.data["brightness_limit"],
            "mode": c.data["mode"],
            "playing": c.playing,
            "lights": c.data["lights"],
            "reason": c.data["player"].get("reason"),
            "allow_hue_takeover": c.entry.options.get("allow_hue_takeover", True),
            "hue_events_connected": bool(c.takeover and c.takeover.connected),
            "last_hue_takeover": c.takeover.last_reason if c.takeover else None,
        }
