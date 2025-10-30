"""Home Assistant integration for reading Gmail with AI."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .const import (
    DOMAIN,
    AUTH_NOTIFICATION_ID,
    AUTH_NOTIFICATION_MESSAGE,
    AUTH_NOTIFICATION_TITLE,
)
from .gmail_reader import check_gmail, setup_auth
from .coordinator import GmailDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class _SafeDict(dict):
    """String format helper that leaves unknown keys untouched."""

    def __missing__(self, key):  # type: ignore[override]
        return "{" + key + "}"


def _format_structure(value: Any, context: Mapping[str, Any]) -> Any:
    """Recursively format strings within a nested structure."""

    if isinstance(value, str):
        return value.format_map(context)
    if isinstance(value, dict):
        return {key: _format_structure(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [_format_structure(item, context) for item in value]
    return value

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
        vol.Optional("model", default="gpt-5-mini"): str,
        vol.Optional("response_variable"): str,
        vol.Optional("notify_service"): str,
        vol.Optional("notify_title"): str,
        vol.Optional("notify_message"): str,
        vol.Optional("notify_data", default=None): dict,
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

            if (
                isinstance(result, dict)
                and result.get("status") == "error"
                and result.get("error") == "auth_failed"
            ):
                await hass.components.persistent_notification.async_create(
                    AUTH_NOTIFICATION_MESSAGE,
                    title=AUTH_NOTIFICATION_TITLE,
                    notification_id=AUTH_NOTIFICATION_ID,
                )
                return

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

            notify_service = data.get("notify_service")
            if notify_service and isinstance(result, list) and result:
                notify_title = data.get("notify_title")
                notify_message = data.get("notify_message")
                notify_data_template = data.get("notify_data") or {}
                sender = data["sender"]
                label = data["label"]

                domain, _, service = notify_service.partition(".")
                if not service:
                    domain, service = "notify", domain

                context_base: dict[str, Any] = {"sender": sender, "label": label}

                for item in result:
                    if not isinstance(item, dict):
                        continue

                    if item.get("status") and item.get("status") != "ok":
                        continue
                    context = _SafeDict({**item, **context_base})

                    if notify_title:
                        title_value = notify_title.format_map(context)
                    else:
                        title_value = item.get("title") or f"New email from {sender}"

                    if notify_message:
                        message_value = notify_message.format_map(context)
                    else:
                        message_value = item.get("message", "")
                        link = item.get("link")
                        if link:
                            message_value = (
                                f"{message_value}\n{link}" if message_value else link
                            )

                    service_data: dict[str, Any] = {"message": message_value}
                    if title_value:
                        service_data["title"] = title_value

                    notify_data: dict[str, Any] = {}
                    if isinstance(notify_data_template, dict):
                        notify_data = _format_structure(notify_data_template, context)
                    else:
                        _LOGGER.debug(
                            "notify_data ignored because it is not a mapping: %s",
                            notify_data_template,
                        )

                    link = item.get("link")
                    if link:
                        notify_data.setdefault("url", link)
                        notify_data.setdefault("clickAction", link)

                    image_url = item.get("image")
                    if image_url:
                        notify_data.setdefault("image", image_url)

                    importance = item.get("importance")
                    if importance:
                        notify_data.setdefault("importance", importance)

                    channel_value = item.get("channel")
                    if channel_value:
                        notify_data.setdefault("channel", channel_value)

                    thread_id = item.get("thread_id")
                    if thread_id:
                        notify_data.setdefault("thread_id", thread_id)

                    preorder = item.get("preorder")
                    if preorder is not None:
                        notify_data.setdefault("preorder", preorder)

                    if notify_data:
                        service_data["data"] = notify_data

                    try:
                        await hass.services.async_call(
                            domain,
                            service,
                            service_data,
                            blocking=False,
                        )
                    except Exception as notify_err:  # pragma: no cover - runtime safety
                        _LOGGER.warning(
                            "Failed to send notification via %s.%s: %s",
                            domain,
                            service,
                            notify_err,
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
        hass,
        sender=sender,
        label=label,
        api_key=api_key,
        model=model,
        keyword=entry.data.get("keyword", ""),
        custom_prompt=entry.data.get("custom_prompt", ""),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # forward to sensor (new plural API)
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # unload the sensor platform
    await hass.config_entries.async_forward_entry_unloads(entry, ["sensor"])
    hass.data[DOMAIN].pop(entry.entry_id)
    return True
