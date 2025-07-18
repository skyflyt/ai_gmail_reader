"""Sensor platform for AI Gmail Reader."""

from __future__ import annotations

from homeassistant.helpers.entity import Entity

from .const import DOMAIN, CONF_KEYWORD


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the sensor from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    keyword = entry.data.get(CONF_KEYWORD, "")
    async_add_entities([GmailSensor(coordinator, keyword)], False)


class GmailSensor(Entity):
    """Representation of the AI Gmail Reader as a sensor."""

    def __init__(self, coordinator, keyword: str):
        self.coordinator = coordinator
        self._attr_name = f"AI Gmail ({keyword})"
        self._attr_unique_id = f"ai_gmail_{keyword}"

    @property
    def state(self):
        if self.coordinator.data:
            return len(self.coordinator.data)
        return 0

    @property
    def extra_state_attributes(self):
        if not self.coordinator.data:
            return {}
        return {"emails": self.coordinator.data}

    async def async_update(self):
        await self.coordinator.async_request_refresh()