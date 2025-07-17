"""Sensor platform for AI Gmail Reader."""

from __future__ import annotations

from homeassistant.helpers.entity import Entity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the sensor from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GmailSensor(coordinator)], False)


class GmailSensor(Entity):
    """Representation of the AI Gmail Reader as a sensor."""

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self._attr_name = "AI Gmail Reader"
        self._attr_unique_id = f"{coordinator._sender}_gmail_ai"

    @property
    def state(self):
        return self.coordinator.data.get("status")

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data.copy()
        data.pop("status", None)
        return data

    async def async_update(self):
        await self.coordinator.async_request_refresh()
