"""DataUpdateCoordinator for AI Gmail Reader."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .gmail_reader import check_gmail

_LOGGER = logging.getLogger(__name__)


class GmailDataUpdateCoordinator(DataUpdateCoordinator):
    """Poll Gmail/AI periodically and store the latest JSON."""

    def __init__(self, hass, sender, label, api_key, model):
        super().__init__(
            hass,
            _LOGGER,
            name="AI Gmail Reader",
            update_interval=timedelta(seconds=60),
        )
        self._sender = sender
        self._label = label
        self._api_key = api_key
        self._model = model

    async def _async_update_data(self):
        """Fetch data from Gmail + OpenAI in the executor."""
        try:
            result = await self.hass.async_add_executor_job(
                check_gmail,
                self._sender,
                self._label,
                "",
                "",
                "auto",
                False,
                "1d",
                self._api_key,
                self._model,
            )
            return result
        except Exception as err:
            raise UpdateFailed(f"Error fetching Gmail data: {err}")
