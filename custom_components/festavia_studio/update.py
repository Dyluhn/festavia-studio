"""Wireless ESP32 updates through Home Assistant's standard update entity."""

from homeassistant.components.update import UpdateDeviceClass, UpdateEntity, UpdateEntityFeature
from homeassistant.const import EntityCategory
from .entity import StudioEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.data.get("device"):
        async_add_entities([Firmware(entry.runtime_data)])


class Firmware(StudioEntity, UpdateEntity):
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_entity_category = EntityCategory.CONFIG
    _attr_supported_features = UpdateEntityFeature.INSTALL | UpdateEntityFeature.SPECIFIC_VERSION
    _attr_title = "Festavia ESP32-C6"
    _attr_in_progress = False

    def __init__(self, coordinator):
        super().__init__(coordinator, "firmware", "Firmware", "mdi:chip")

    @property
    def available(self):
        return super().available and self.coordinator.data.get("firmware", {}).get(
            "connected", False
        )

    @property
    def installed_version(self):
        return self.coordinator.data.get("firmware", {}).get("version")

    @property
    def latest_version(self):
        return self.coordinator.api.latest_version

    async def async_install(self, version, backup, **kwargs):
        if version not in (None, self.latest_version):
            from homeassistant.exceptions import HomeAssistantError

            raise HomeAssistantError(
                translation_domain="festavia_studio", translation_key="firmware_version"
            )
        self._attr_in_progress = True
        self.async_write_ha_state()
        try:
            async with self.coordinator.action_lock:
                self.coordinator.check_ready()
                try:
                    await self.coordinator.api.update_firmware()
                except Exception as exc:
                    from .api import StudioAuthError

                    if isinstance(exc, StudioAuthError):
                        self.coordinator.entry.async_start_reauth(self.hass)
                    raise
                await self.coordinator.async_request_refresh()
        finally:
            self._attr_in_progress = False
            self.async_write_ha_state()
