"""Keep unfinished restoration reachable after an offline entry is removed."""

import shutil
import probatio as vol
from homeassistant.components.repairs import RepairsFlow
from homeassistant.helpers import issue_registry as ir, selector
from .api import private_folder, recover_folder
from .const import DOMAIN


class RestoreRepair(RepairsFlow):
    def __init__(self, issue_id, data):
        self.issue_id, self.data = issue_id, data

    async def async_step_init(self, user_input=None):
        return await self.async_step_confirm(user_input)

    async def async_step_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            folder = private_folder(self.hass, self.data["entry_id"])
            try:
                await self.hass.async_add_executor_job(recover_folder, folder, user_input)
                await self.hass.async_add_executor_job(shutil.rmtree, folder)
            except (OSError, RuntimeError, ValueError, KeyError):
                errors["base"] = "recovery_failed"
            else:
                ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)
                return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional("bridge_host"): str,
                    vol.Optional("device_url"): str,
                    vol.Optional("bridge_key"): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                    vol.Optional("device_token"): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )


async def async_create_fix_flow(hass, issue_id, data):
    return RestoreRepair(issue_id, data)
