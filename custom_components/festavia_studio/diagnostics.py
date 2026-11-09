"""Diagnostics intentionally omit tokens, URLs, fixture names and palettes."""


async def async_get_config_entry_diagnostics(hass, entry):
    c = entry.runtime_data
    return {
        key: c.data.get(key)
        for key in (
            "api",
            "version",
            "mode",
            "positions",
            "palette_limit",
            "brightness_limit",
            "effects",
            "player",
            "firmware",
            "last_error",
        )
    }
