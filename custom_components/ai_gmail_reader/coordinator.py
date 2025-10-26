"""DataUpdateCoordinator for AI Gmail Reader."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    AUTH_NOTIFICATION_ID,
    AUTH_NOTIFICATION_MESSAGE,
    AUTH_NOTIFICATION_TITLE,
)
from .gmail_reader import check_gmail

_LOGGER = logging.getLogger(__name__)


class GmailDataUpdateCoordinator(DataUpdateCoordinator):
    """Poll Gmail/AI periodically and store the latest JSON."""

    def __init__(self, hass, sender, label, api_key, model, keyword="", custom_prompt=""):
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
        self._keyword = keyword
        self._custom_prompt = custom_prompt
        self._auth_failed_notified = False

    async def _async_update_data(self):
        """Fetch data from Gmail + OpenAI in the executor."""
        try:
            results = await self.hass.async_add_executor_job(
                check_gmail,
                self._sender,
                self._label,
                self._keyword,
                self._custom_prompt,
                "auto",
                False,
                "1d",
                self._api_key,
                self._model,
            )
            if isinstance(results, dict) and results.get("status") == "error":
                if results.get("error") == "auth_failed":
                    if not self._auth_failed_notified:
                        self._auth_failed_notified = True
                        self.hass.async_create_task(
                            self.hass.components.persistent_notification.async_create(
                                AUTH_NOTIFICATION_MESSAGE,
                                title=AUTH_NOTIFICATION_TITLE,
                                notification_id=AUTH_NOTIFICATION_ID,
                            )
                        )
                    raise UpdateFailed(
                        "Gmail authentication failed; please run the "
                        "ai_gmail_reader.setup_auth service."
                    )
                raise UpdateFailed(f"Gmail check error: {results.get('error')}")

            if not isinstance(results, list):
                raise UpdateFailed(f"Invalid data from gmail_reader: {results}")

            if self._auth_failed_notified:
                self._auth_failed_notified = False
            return results
        except Exception as err:
            raise UpdateFailed(f"Error fetching Gmail data: {err}")
