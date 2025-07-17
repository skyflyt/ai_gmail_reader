import base64
import os
import re
import logging

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import openai
import json

_LOGGER = logging.getLogger(__name__)

TOKEN_DIR = "/config/.ai_gmail_reader"
TOKEN_PATH = os.path.join(TOKEN_DIR, "token.json")
CREDS_PATH = "/config/gmail/credentials.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Default context instructions sent to the AI model when building prompts.
DEFAULT_PROMPT_CONTEXT = (
    "Return a JSON object with keys 'summary', 'link' and 'image'. "
    "The summary field must be no longer than 140 characters."
)


def build_prompt(email_text: str, custom_prompt: str) -> str:
    """Return the full prompt for the AI model."""
    preamble = (
        "You are an email summarizer for a Gmail inbox. "
        "The summary field must be no longer than 140 characters."
    )
    return (
        f"{preamble}\n{DEFAULT_PROMPT_CONTEXT}\n{custom_prompt.strip()}\nEMAIL:\n{email_text}"
    )


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
    openai.api_key = api_key

    # Setup Gmail API
    _LOGGER.debug("Using token file at %s", TOKEN_PATH)
    if not os.path.isfile(TOKEN_PATH):
        _LOGGER.error("Gmail token.json not found at %s", TOKEN_PATH)
        return {"status": "error", "error": "no_token"}

    creds = Credentials.from_authorized_user_file(TOKEN_PATH)
    service = build("gmail", "v1", credentials=creds)

    # Build search query using Gmail's "in:" operator
    q = f"in:inbox is:unread from:{sender} newer_than:{age_limit}"
    if keyword:
        q += f" {keyword}"
    _LOGGER.debug("Gmail query: %s", q)

    try:
        response = (
            service.users()
            .messages()
            .list(userId="me", q=q, maxResults=MAX_RESULTS)
            .execute()
        )
        messages = response.get("messages", [])
        _LOGGER.debug("Raw Gmail list response: %s", response)
        _LOGGER.debug("Found %d messages", len(messages))
    except Exception as err:  # pragma: no cover - runtime protection
        _LOGGER.exception("Gmail API list() failed")
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
        full_prompt = build_prompt(clean_text, custom_prompt)

        try:
            ai_response = openai.chat.completions.create(
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

        try:
            ai_json = json.loads(ai_response.choices[0].message.content)
        except json.JSONDecodeError as err:
            _LOGGER.exception("Failed to decode AI response: %s", err)
            continue
        summary = ai_json.get("summary", "")
        if len(summary) > 140:
            summary = summary[:137] + "..."
        _LOGGER.debug("Summarized email '%s' -> %s", subject, summary)

        # mark message as read
        try:
            service.users().messages().modify(
                userId="me",
                id=msg_meta["id"],
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
        except Exception as err:
            _LOGGER.warning("Failed to mark message %s read: %s", msg_meta["id"], err)

        # Extract image and link from HTML (not the cleaned text)
        link_match = re.search(r"https?://\S+", html)
        image_match = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', html)

        result = {
            "status": "ok",
            "title": subject,
            "message": summary,
            "thread_id": thread_id,
            "link": ai_json.get("link") or (link_match.group(0) if link_match else ""),
            "image": ai_json.get("image") or (image_match.group(1) if image_match else ""),
            "channel": keyword,
            "importance": importance,
            "preorder": "preorder" in clean_text.lower(),
        }

        _LOGGER.debug("Result built: %s", result)

        return result

    _LOGGER.debug("No valid response generated")
    return {"status": "no_valid_response"}
