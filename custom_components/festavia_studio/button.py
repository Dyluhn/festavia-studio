from homeassistant.components.button import ButtonEntity
from .entity import StudioEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            StudioButton(entry.runtime_data, key, name, icon)
            for key, name, icon in [
                ("play", "Play", "mdi:play"),
                ("stop", "Stop and restore", "mdi:stop"),
                ("off", "Lights off", "mdi:lightbulb-off"),
                *(
                    [("release", "Return control to Hue", "mdi:bridge")]
                    if entry.runtime_data.data["mode"] == "native"
                    else []
                ),
            ]
        ]
    )


class StudioButton(StudioEntity, ButtonEntity):
    def __init__(self, coordinator, key, name, icon):
        super().__init__(coordinator, key, name, icon)
        self.key = key

    async def async_press(self):
        if self.key == "play":
            await self.coordinator.play()
        else:
            async with self.coordinator.action_lock:
                await self.coordinator.command(
                    self.key, {"manual": True} if self.key == "release" else None
                )
