"""Config flow for AI Gmail Reader."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    CONF_SENDER,
    CONF_LABEL,
    CONF_API_KEY,
    CONF_MODEL,
    CONF_KEYWORD,
)


DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SENDER): str,
        vol.Required(CONF_LABEL, default="INBOX"): str,
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_MODEL, default="gpt-4o-mini"): str,
        vol.Required(CONF_KEYWORD, default=""): cv.string,
    }
)


class GmailReaderFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AI Gmail Reader."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)

        return self.async_create_entry(title=user_input[CONF_SENDER], data=user_input)
