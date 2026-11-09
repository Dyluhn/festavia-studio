from homeassistant.components.select import SelectEntity
from .entity import StudioEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            StudioSelect(entry.runtime_data, "effect", "Effect", "mdi:animation"),
            StudioSelect(entry.runtime_data, "preset", "Saved palette", "mdi:palette"),
        ]
    )


class StudioSelect(StudioEntity, SelectEntity):
    def __init__(self, coordinator, key, name, icon):
        super().__init__(coordinator, key, name, icon)
        self.key = key

    @property
    def options(self):
        c = self.coordinator
        return c.data["effects"] if self.key == "effect" else ["Custom", *c.data["presets"]]

    @property
    def current_option(self):
        return (
            self.coordinator.scene.get("effect", "static")
            if self.key == "effect"
            else self.coordinator.preset
        )

    async def async_select_option(self, option):
        if self.key == "effect":
            await self.coordinator.configure({"effect": option})
        else:
            await self.coordinator.choose_preset(option)
