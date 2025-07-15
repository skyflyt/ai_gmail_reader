import base64
import os
import re
import logging
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from openai import OpenAI

_LOGGER = logging.getLogger(__name__)

TOKEN_DIR = "/config/.ai_gmail_reader"
TOKEN_PATH = os.path.join(TOKEN_DIR, "token.json")
CREDS_PATH = "/config/gmail/credentials.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def setup_auth() -> str:
    """Run the OAuth flow and store the token file."""
    os.makedirs(TOKEN_DIR, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
    creds = flow.run_local_server(port=0, open_browser=False)
    with open(TOKEN_PATH, "w") as token_file:
        token_file.write(creds.to_json())
    print(f"Token stored to {TOKEN_PATH}")
    return TOKEN_PATH


def check_gmail(
    sender,
    label,
    keyword,
    custom_prompt,
    importance,
    image_required,
    age_limit,
    api_key,
    model,
):
    MAX_RESULTS = 5

    client = OpenAI(api_key=api_key)

    # Setup Gmail API
    _LOGGER.debug("Using token file at %s", TOKEN_PATH)
    creds = Credentials.from_authorized_user_file(TOKEN_PATH)
    service = build("gmail", "v1", credentials=creds)

    # Build search query
    q = f"label:{label} from:{sender} newer_than:{age_limit}"
    if keyword:
        q += f" {keyword}"

    _LOGGER.debug("Gmail query: %s", q)

    try:
        messages = (
            service.users()
            .messages()
            .list(userId="me", q=q, maxResults=MAX_RESULTS)
            .execute()
            .get("messages", [])
        )
    except Exception as err:  # pragma: no cover - runtime protection
        _LOGGER.exception("Failed to fetch messages: %s", err)
        return {"status": "error", "error": str(err)}

    if not messages:
        _LOGGER.debug("No messages found for query")
        return {"status": "no_unread"}

    for msg_meta in messages:
        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_meta["id"], format="full")
                .execute()
            )
        except Exception as err:  # pragma: no cover - runtime protection
            _LOGGER.exception("Failed to fetch message %s: %s", msg_meta.get("id"), err)
            continue

        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        date = parsedate_to_datetime(headers.get("Date", ""))
        subject = headers.get("Subject", "")
        thread_id = msg.get("threadId")

        # Extract HTML body
        parts = msg["payload"].get("parts", [])
        html = ""
        for part in parts:
            if part["mimeType"] == "text/html":
                data = part["body"].get("data")
                if data:
                    html = base64.urlsafe_b64decode(data.encode()).decode()

        # Clean HTML for prompt
        clean_text = re.sub(r"<[^>]+>", "", html)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        # GPT prompt
        full_prompt = f"""
            EMAIL:
            {clean_text}

            INSTRUCTIONS:
            {custom_prompt.strip()}
        """

        try:
            ai_response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an email summarizer for a Gmail inbox.",
                    },
                    {"role": "user", "content": full_prompt.strip()},
                ],
            )
        except Exception as err:  # pragma: no cover - runtime protection
            _LOGGER.exception("OpenAI request failed: %s", err)
            return {"status": "error", "error": str(err)}

        summary = ai_response.choices[0].message.content
        _LOGGER.debug("Summarized email '%s' -> %s", subject, summary)

        # Extract image and link
        link_match = re.search(r"https?://\S+", html)
        image_match = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', html)

        result = {
            "status": "ok",
            "title": subject,
            "message": summary,
            "thread_id": thread_id,
            "link": link_match.group(0) if link_match else "",
            "image": image_match.group(1) if image_match else "",
            "channel": keyword,
            "importance": importance,
            "preorder": "preorder" in clean_text.lower(),
        }

        _LOGGER.debug("Result built: %s", result)

        return result

    _LOGGER.debug("No valid response generated")
    return {"status": "no_valid_response"}
