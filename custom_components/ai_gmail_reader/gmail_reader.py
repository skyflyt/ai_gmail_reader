import base64
import os
import re
import logging

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from openai import OpenAI
import json
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError

_LOGGER = logging.getLogger(__name__)

TOKEN_DIR = "/config/.ai_gmail_reader"
TOKEN_PATH = os.path.join(TOKEN_DIR, "token.json")
OUTPUT_DIR = os.path.join(TOKEN_DIR, "output")
CREDS_PATH = "/config/gmail/credentials.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

BASE_PROMPT = (
    "You are an AI summarizer for promotional emails. Always reply using a JSON object "
    "with exactly three keys: \"summary\", \"link\", and \"image\". "
    "\"summary\" is an informal, friendly synopsis of the offer (<= 140 characters). "
    "\"link\" is the primary call-to-action URL in the email body (ignore image URLs, tracking pixels, unsubscribe, and 'view in browser' links). "
    "\"image\" is the main hero image URL — the largest or most prominent marketing image (not logos, icons, social buttons, or tracking pixels). "
    "Return only the JSON object, no code fences or extra text."
)

def build_prompt(email_text: str, custom_prompt: str) -> str:
    return f"{BASE_PROMPT}\n{custom_prompt.strip()}\nEMAIL:\n{email_text}"

def setup_auth() -> str:
    os.makedirs(TOKEN_DIR, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
    creds = flow.run_local_server(
        port=0,
        open_browser=False,
        access_type="offline",
        prompt="consent",
        include_granted_scopes=True,
    )
    with open(TOKEN_PATH, "w") as token_file:
        token_file.write(creds.to_json())
    _LOGGER.info("Token stored to %s", TOKEN_PATH)
    return TOKEN_PATH

def find_html_part(payload):
    if payload.get("mimeType") == "text/html":
        return payload.get("body", {}).get("data")
    for part in payload.get("parts", []):
        result = find_html_part(part)
        if result:
            return result
    return None

def check_gmail(sender, label, keyword, custom_prompt, importance, image_required, age_limit, api_key, model):
    import os
    import re
    import base64
    import json
    from bs4 import BeautifulSoup
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    def extract_cta_link(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        anchors = soup.find_all("a", href=True)
        for a in anchors:
            href = a["href"]
            text = (a.get_text() or "").lower()
            # Skip unsubscribe/view-in-browser/mailto and image links
            if any(k in href.lower() for k in ["unsubscribe", "view", "view-in-browser", "mailto:"]):
                continue
            if re.search(r"\.(?:jpg|jpeg|png|gif|bmp|svg)(?:[?#]|$)", href, re.IGNORECASE):
                continue
            if any(k in text for k in ["unsubscribe", "view in browser"]):
                continue
            cls = " ".join(a.get("class", [])).lower()
            role = (a.get("role") or "").lower()
            if "btn" in cls or "button" in cls or role == "button":
                return href
        for a in anchors:
            href = a["href"]
            if not re.search(r"\.(?:jpg|jpeg|png|gif|bmp|svg)(?:[?#]|$)", href, re.IGNORECASE) \
               and "unsubscribe" not in href.lower():
                return href
        return ""

    def extract_hero_image(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        imgs = soup.find_all("img", src=True)
        cleaned = []
        for img in imgs:
            src = img["src"]
            al = (img.get("alt") or "").lower()
            if any(k in src.lower() for k in ["logo", "icon", "spacer", "pixel", "tracking", "googleusercontent.com/"]):
                continue
            if any(k in al for k in ["logo", "icon"]):
                continue
            cleaned.append(img)
        for img in cleaned:
            al = (img.get("alt") or "").lower()
            if "hero" in al or "hero" in img["src"].lower():
                return img["src"]
        max_area, best = 0, ""
        for img in cleaned:
            try:
                w = int(img.get("width", 0))
                h = int(img.get("height", 0))
                area = w * h
                if area > max_area:
                    max_area, best = area, img["src"]
            except Exception:
                pass
        if best:
            return best
        return cleaned[0]["src"] if cleaned else ""

    MAX_RESULTS = 5
    client = OpenAI(api_key=api_key)
    profile = keyword.lower().replace(" ", "_") or "default"

    if not os.path.isfile(TOKEN_PATH):
        _LOGGER.error("Gmail token.json not found at %s", TOKEN_PATH)
        return {"status": "error", "error": "no_token"}

    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds and creds.expired:
        if creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as err:
                _LOGGER.error("Failed to refresh Gmail token: %s", err)
                return {"status": "error", "error": "auth_failed"}
            with open(TOKEN_PATH, "w") as token_file:
                token_file.write(creds.to_json())
        else:
            _LOGGER.error("Gmail token expired and no refresh token available")
            return {"status": "error", "error": "auth_failed"}
    service = build("gmail", "v1", credentials=creds)

    label_term = "in:inbox" if label.lower() == "inbox" else f'label:"{label}"' if " " in label else f"label:{label}"
    q = f"{label_term} is:unread from:{sender} newer_than:{age_limit}"
    if keyword:
        q += f" {keyword}"

    try:
        response = service.users().messages().list(userId="me", q=q, maxResults=MAX_RESULTS).execute()
        messages = response.get("messages", [])
    except Exception as err:
        _LOGGER.exception("Gmail API list() failed")
        return {"status": "error", "error": str(err)}

    if not messages:
        return []

    results = []
    for msg_meta in messages:
        try:
            msg = service.users().messages().get(userId="me", id=msg_meta["id"], format="full").execute()
        except Exception as err:
            _LOGGER.exception("Failed to fetch message %s: %s", msg_meta.get("id"), err)
            continue

        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        subject = headers.get("Subject", "")
        thread_id = msg.get("threadId")

        html_encoded = find_html_part(msg["payload"])
        html = base64.urlsafe_b64decode(html_encoded.encode()).decode() if html_encoded else ""
        _LOGGER.debug("Decoded HTML (preview): %s", html[:200])

        clean_text = re.sub(r"<[^>]+>", "", html)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        full_prompt = build_prompt(clean_text, custom_prompt)
        tools = [{
            "type": "function",
            "function": {
                "name": "extract_email_details",
                "description": "Extract summary, CTA link, and hero image from a promotional email.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string", "description": "<=140 character friendly synopsis"},
                        "link": {"type": "string", "description": "primary CTA URL (non-image, not unsubscribe/view in browser)"},
                        "image": {"type": "string", "description": "hero image URL (largest/prominent, not logo/icon/pixel)"},
                    },
                    "required": ["summary", "link", "image"],
                },
            },
        }]
        tool_choice = {"type": "function", "function": {"name": "extract_email_details"}}
        try:
            ai_response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an email summarizer. Follow the schema strictly and reply with only a JSON object containing summary, link, image."
                        ),
                    },
                    {"role": "user", "content": full_prompt.strip()},
                ],
                tools=tools,
                tool_choice=tool_choice,
            )
        except Exception as err:
            _LOGGER.exception("OpenAI request failed: %s", err)
            results.append({"status": "error", "error": str(err)})
            continue

        ai_message = ai_response.choices[0].message
        if getattr(ai_message, "tool_calls", None):
            try:
                tool_args = ai_message.tool_calls[0].function.arguments
                ai_json = json.loads(tool_args)
            except Exception:
                _LOGGER.warning("Failed to parse tool call JSON: %s", ai_message.tool_calls[0].function.arguments)
                ai_json = {}
        else:
            raw_response = (ai_message.content or "").strip()
            if raw_response.startswith("```json"):
                raw_response = raw_response[7:]
            if raw_response.endswith("```"):
                raw_response = raw_response[:-3]
            try:
                ai_json = json.loads(raw_response)
            except json.JSONDecodeError:
                _LOGGER.warning("Failed to parse AI JSON: %s", raw_response)
                ai_json = {"summary": raw_response}

        summary = ai_json.get("summary", "").strip()
        if len(summary) > 140:
            summary = summary[:137].rstrip() + "…"

        try:
            service.users().messages().modify(
                userId="me",
                id=msg_meta["id"],
                body={"removeLabelIds": ["UNREAD"]}
            ).execute()
        except Exception as err:
            _LOGGER.warning("Failed to mark message %s read: %s", msg_meta["id"], err)

        # Extract link and image, applying fallbacks if necessary
        cta_link = ai_json.get("link", "").strip()
        if not cta_link or re.search(r"\.(?:jpg|jpeg|png|gif|bmp|svg)(?:[?#]|$)", cta_link, re.IGNORECASE):
            new_link = extract_cta_link(html)
            if new_link and new_link != cta_link:
                _LOGGER.debug("Overrode CTA link with fallback")
            cta_link = new_link or ""

        image_url = ai_json.get("image", "").strip()
        if not image_url or not re.search(r"\.(?:jpg|jpeg|png|gif|bmp|svg)(?:[?#]|$)", image_url, re.IGNORECASE):
            new_image = extract_hero_image(html)
            if new_image and new_image != image_url:
                _LOGGER.debug("Overrode hero image with fallback")
            image_url = new_image or ""

        result = {
            "status": "ok",
            "title": subject,
            "message": summary,
            "thread_id": thread_id,
            "link": cta_link,
            "image": image_url,
            "channel": profile,
            "importance": importance,
            "preorder": "preorder" in clean_text.lower(),
        }

        # cache to disk
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            sender_id = re.sub(r"[^A-Za-z0-9]+", "_", sender)
            out_path = os.path.join(OUTPUT_DIR, f"last_{sender_id}_output.json")
            with open(out_path, "w") as out_file:
                json.dump(result, out_file)
        except Exception as err:
            _LOGGER.warning("Failed to cache output: %s", err)

        results.append(result)

    return results


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="AI Gmail Reader utility")
    parser.add_argument("--auth", action="store_true", help="Run OAuth setup")
    args = parser.parse_args()
    if args.auth:
        setup_auth()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
