from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from .entity import StudioEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            StudioNumber(
                entry.runtime_data,
                "brightness",
                "Brightness",
                "mdi:brightness-6",
                1,
                entry.runtime_data.data["brightness_limit"],
                1,
                "%",
            ),
            StudioNumber(
                entry.runtime_data, "speed", "Speed", "mdi:speedometer", 0.1, 20, 0.1, None
            ),
            BrightnessLimit(entry.runtime_data),
        ]
    )


class StudioNumber(StudioEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator, key, name, icon, low, high, step, unit):
        super().__init__(coordinator, key, name, icon)
        self.key = key
        self._attr_native_min_value, self._attr_native_max_value = low, high
        self._attr_native_step, self._attr_native_unit_of_measurement = step, unit

    @property
    def native_max_value(self):
        return (
            self.coordinator.data["brightness_limit"]
            if self.key == "brightness"
            else self._attr_native_max_value
        )

    @property
    def native_value(self):
        return self.coordinator.scene.get(self.key, 10 if self.key == "brightness" else 1)

    async def async_set_native_value(self, value):
        await self.coordinator.configure({self.key: value})


class BrightnessLimit(StudioNumber):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator):
        super().__init__(
            coordinator, "brightness_limit", "Brightness limit", "mdi:brightness-7", 1, 100, 1, "%"
        )

    @property
    def native_value(self):
        return self.coordinator.data["brightness_limit"]

    async def async_set_native_value(self, value):
        c = self.coordinator
        async with c.action_lock:
            c.check_ready()
            if c.scene.get("brightness", 10) > value:
                candidate = {**c.scene, "brightness": value}
                if c.playing:
                    await c.command("play", {"scene": candidate, "seconds": 0})
                c.scene = candidate
                await c.persist()
            result = await c.api.set_limit(value)
            c.hass.config_entries.async_update_entry(
                c.entry, options={**c.entry.options, "brightness_limit": value}
            )
            c.async_set_updated_data(result)
