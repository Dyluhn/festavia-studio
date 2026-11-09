from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from .entity import StudioEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    entities = [Direction(entry.runtime_data)]
    if entry.runtime_data.data["mode"] == "native":
        entities.append(AllowHueTakeover(entry.runtime_data))
    async_add_entities(entities)


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


class AllowHueTakeover(StudioEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator):
        super().__init__(coordinator, "allow_hue_takeover", "Allow Hue takeover", "mdi:bridge")

    @property
    def is_on(self):
        return self.coordinator.entry.options.get("allow_hue_takeover", True)

    async def async_turn_on(self, **kwargs):
        await self.coordinator.set_hue_takeover(True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.set_hue_takeover(False)
