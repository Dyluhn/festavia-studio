"""Ordered palettes are editable from the native HA device controls."""

import re
from homeassistant.components.text import TextEntity, TextMode
from homeassistant.exceptions import ServiceValidationError
from .entity import StudioEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Palette(entry.runtime_data)])


class Palette(StudioEntity, TextEntity):
    _attr_mode = TextMode.TEXT
    _attr_native_min = 7
    _attr_native_max = 255
    _attr_pattern = r"(?:#[0-9a-fA-F]{6}(?:[ ,]+#[0-9a-fA-F]{6})*|[1-9][0-9]* colors; edit in Festavia Studio card)"

    def __init__(self, coordinator):
        super().__init__(coordinator, "palette", "Palette", "mdi:palette")

    @property
    def native_value(self):
        colors = self.coordinator.scene["colors"]
        value = ", ".join(colors)
        # HA states cannot exceed 255 characters; the card edits the complete
        # palette from coordinator attributes regardless of its size.
        return value if len(value) <= 255 else f"{len(colors)} colors; edit in Festavia Studio card"

    async def async_set_value(self, value):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}(?:[ ,]+#[0-9a-fA-F]{6})*", value.strip()):
            raise ServiceValidationError(
                translation_domain="festavia_studio", translation_key="invalid_scene"
            )
        await self.coordinator.configure({"colors": re.split(r"[ ,]+", value.strip())})
