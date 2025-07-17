"""Home Assistant integration for reading Gmail with AI."""

from __future__ import annotations

import json
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .const import DOMAIN
from .gmail_reader import check_gmail, setup_auth
from .coordinator import GmailDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_CHECK_GMAIL = "check_gmail"
SERVICE_SETUP_AUTH = "setup_auth"

SERVICE_CHECK_GMAIL_SCHEMA = vol.Schema(
    {
        vol.Required("sender"): str,
        vol.Optional("label", default="INBOX"): str,
        vol.Optional("keyword", default=""): str,
        vol.Optional("custom_prompt", default=""): str,
        vol.Optional("importance", default="auto"): vol.In(["auto", "high", "low"]),
        vol.Optional("image_required", default="false"): vol.In(["true", "false"]),
        vol.Optional("age_limit", default="1d"): str,
        vol.Required("api_key"): str,
        vol.Optional("model", default="gpt-4o-mini"): str,
        vol.Optional("response_variable"): str,
    }
)

SERVICE_SETUP_AUTH_SCHEMA = vol.Schema({})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration and register services."""
    hass.data.setdefault(DOMAIN, {})

    async def handle_check_gmail(call: ServiceCall) -> None:
        data = call.data
        args = [
            data["sender"],
            data["label"],
            data["keyword"],
            data["custom_prompt"],
            data["importance"],
            data["image_required"],
            data["age_limit"],
            data["api_key"],
            data["model"],
        ]
        try:
            result = await hass.async_add_executor_job(check_gmail, *args)
            _LOGGER.info("Gmail check result: %s", result)

            if resp_var := data.get("response_variable"):
                await hass.services.async_call(
                    "input_text",
                    "set_value",
                    {
                        "entity_id": f"input_text.{resp_var}",
                        "value": json.dumps(result),
                    },
                    blocking=False,
                )
        except Exception as err:  # pragma: no cover - runtime protection
            _LOGGER.exception("Unexpected error in Gmail reader: %s", err)

    hass.services.async_register(
        DOMAIN,
        SERVICE_CHECK_GMAIL,
        handle_check_gmail,
        schema=SERVICE_CHECK_GMAIL_SCHEMA,
    )

    async def handle_setup_auth(call: ServiceCall) -> None:
        try:
            await hass.async_add_executor_job(setup_auth)
            _LOGGER.info("Gmail OAuth setup completed")
        except Exception as err:  # pragma: no cover - runtime protection
            _LOGGER.exception("OAuth setup failed: %s", err)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SETUP_AUTH,
        handle_setup_auth,
        schema=SERVICE_SETUP_AUTH_SCHEMA,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AI Gmail Reader from a config entry."""
    sender = entry.data["sender"]
    label = entry.data["label"]
    api_key = entry.data["api_key"]
    model = entry.data["model"]

    coordinator = GmailDataUpdateCoordinator(
        hass, sender=sender, label=label, api_key=api_key, model=model
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setup(entry, "sensor")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    hass.data[DOMAIN].pop(entry.entry_id)
    return True
