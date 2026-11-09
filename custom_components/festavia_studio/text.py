"""Ordered palettes are editable from the native HA device controls."""

import re
from homeassistant.components.text import TextEntity, TextMode
from .entity import StudioEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Palette(entry.runtime_data)])


class Palette(StudioEntity, TextEntity):
    _attr_mode = TextMode.TEXT
    _attr_native_min = 7
    _attr_native_max = 243
    _attr_pattern = r"#[0-9a-fA-F]{6}(?:[ ,]+#[0-9a-fA-F]{6})*"

    def __init__(self, coordinator):
        super().__init__(coordinator, "palette", "Palette", "mdi:palette")

    @property
    def native_value(self):
        return ", ".join(self.coordinator.scene["colors"])

    async def async_set_value(self, value):
        await self.coordinator.configure({"colors": re.split(r"[ ,]+", value.strip())})
