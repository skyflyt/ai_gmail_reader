from __future__ import annotations

import logging
from homeassistant.components.sensor import SensorEntity

DOMAIN = "ai_gmail_reader"
_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the Gmail AI response sensor."""
    sensor = GmailAIResponseSensor()
    async_add_entities([sensor])
    hass.data.setdefault(DOMAIN, {})["sensor"] = sensor


class GmailAIResponseSensor(SensorEntity):
    """Sensor that stores the latest AI Gmail response."""

    _attr_name = "Gmail AI Response"
    _attr_icon = "mdi:email"  # Use simple mail icon

    def __init__(self) -> None:
        self._attr_state = None
        self._attr_extra_state_attributes = {}

    async def async_update_from_result(self, result: dict) -> None:
        """Update the sensor from a result dict."""
        self._attr_state = result.get("message")
        self._attr_extra_state_attributes = {
            "title": result.get("title"),
            "message": result.get("message"),
            "image": result.get("image"),
            "link": result.get("link"),
            "channel": result.get("channel"),
            "importance": result.get("importance"),
        }
        _LOGGER.debug("Updated sensor with: %s", result)
        await self.async_update_ha_state()
