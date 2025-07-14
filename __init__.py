import logging
from homeassistant.core import HomeAssistant, ServiceCall
import subprocess
import json

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ai_gmail_reader"

async def async_setup(hass: HomeAssistant, config: dict):
    async def handle_check_gmail(call: ServiceCall):
        args = [
            "python3",
            "/config/gmail/ai_gmail_reader.py",
            call.data.get("sender", ""),
            call.data.get("label", "INBOX"),
            call.data.get("keyword", ""),
            call.data.get("custom_prompt", ""),
            call.data.get("importance", "auto"),
            call.data.get("image_required", "false"),
            call.data.get("age_limit", "1d"),
            call.data.get("api_key", ""),
            call.data.get("model", "gpt-4o-mini")
        ]

        try:
            output = subprocess.check_output(args, stderr=subprocess.STDOUT)
            parsed = json.loads(output.decode())
            _LOGGER.info(f"Gmail check result: {parsed}")
        except subprocess.CalledProcessError as e:
            _LOGGER.error(f"Gmail script failed: {e.output.decode()}")
        except Exception as e:
            _LOGGER.error(f"Unexpected error in Gmail reader: {str(e)}")

    hass.services.async_register(DOMAIN, "check_gmail", handle_check_gmail)
    return True
