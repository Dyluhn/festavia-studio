from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from .entity import StudioEntity
from homeassistant.const import EntityCategory

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Connection(entry.runtime_data)])


class Connection(StudioEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator):
        super().__init__(coordinator, "connection", "Connection", "mdi:lan-connect")

    @property
    def available(self):
        return True

    @property
    def is_on(self):
        return self.coordinator.last_update_success
