from homeassistant.components.switch import SwitchEntity
from .entity import StudioEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Direction(entry.runtime_data)])


class Direction(StudioEntity, SwitchEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator, "reverse", "Reverse direction", "mdi:swap-horizontal")

    @property
    def is_on(self):
        return self.coordinator.scene.get("reverse", False)

    async def async_turn_on(self, **kwargs):
        await self.coordinator.configure({"reverse": True})

    async def async_turn_off(self, **kwargs):
        await self.coordinator.configure({"reverse": False})
