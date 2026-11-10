"""A controller device, separate from the existing Hue lamp entity."""

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN


class StudioEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, name, icon):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.unique_id)},
            name="Festavia Studio",
            manufacturer="Festavia Studio community project",
            model="Festavia effect controller",
            sw_version=coordinator.data.get("firmware", {}).get("version"),
        )
        hue_id = coordinator.entry.data.get("hue_entry_id")
        if hue_id:
            registry = dr.async_get(coordinator.hass)
            bridge = next(
                (
                    d
                    for d in dr.async_entries_for_config_entry(registry, hue_id)
                    if any(domain == "hue" for domain, _ in d.identifiers)
                ),
                None,
            )
            if bridge:
                self._attr_device_info["via_device"] = next(
                    i for i in bridge.identifiers if i[0] == "hue"
                )
