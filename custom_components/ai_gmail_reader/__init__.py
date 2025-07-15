"""Home Assistant integration for reading Gmail with AI."""

import logging
import json
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .gmail_reader import check_gmail, setup_auth
from .sensor import GmailAIResponseSensor

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ai_gmail_reader"

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
    """Set up the integration and register the Gmail check service."""

    # Ensure domain data storage
    hass.data.setdefault(DOMAIN, {})
    # The sensor entity is set up via the ai_gmail_reader sensor platform.

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
        _LOGGER.warning("ai_gmail_reader args: %s", args)
        try:
            result = await hass.async_add_executor_job(check_gmail, *args)
            _LOGGER.info("Gmail check result: %s", result)

            # Update sensor with latest response if available
            sensor: GmailAIResponseSensor | None = hass.data[DOMAIN].get("sensor")
            if sensor is not None:
                await sensor.async_update_from_result(result)

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
