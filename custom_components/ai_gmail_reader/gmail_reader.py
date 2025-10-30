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
        def score_anchor(anchor) -> float:
            href = anchor.get("href", "")
            if not href or href.startswith("mailto:"):
                return -1
            href_lower = href.lower()
            if any(bad in href_lower for bad in ["unsubscribe", "view", "view-in-browser", "preferences", "privacy"]):
                return -1
            if not href_lower.startswith("http"):
                return -1
            if re.search(r"\.(?:jpg|jpeg|png|gif|bmp|svg)(?:[?#]|$)", href_lower):
                return -1

            text = (anchor.get_text(strip=True) or "").lower()
            if any(bad in text for bad in ["unsubscribe", "view in browser", "privacy"]):
                return -1

            score = 0.0
            cls = " ".join(anchor.get("class", [])).lower()
            role = (anchor.get("role") or "").lower()
            data_cta = " ".join([str(v) for k, v in anchor.attrs.items() if "cta" in k.lower()])
            if any(token in cls for token in ["btn", "button", "cta", "primary", "action"]):
                score += 4
            if role == "button":
                score += 3
            if "background" in (anchor.get("style") or "").lower():
                score += 1.5
            if "font-size" in (anchor.get("style") or "").lower():
                score += 0.5
            if data_cta:
                score += 2

            action_words = [
                "shop", "buy", "get", "learn", "book", "explore", "save",
                "start", "join", "order", "register", "claim", "subscribe",
                "upgrade", "download", "watch", "apply"
            ]
            if any(word in text for word in action_words):
                score += 3
            if text.isupper() and len(text) <= 30 and len(text) >= 3:
                score += 1
            if len(text) >= 12:
                score += 0.5

            # If the anchor wraps an image, consider it a CTA but lower priority than text buttons
            if anchor.find("img"):
                score += 1
            return score

        soup = BeautifulSoup(html, "html.parser")
        anchors = soup.find_all("a", href=True)
        best_href, best_score = "", 0
        for anchor in anchors:
            score = score_anchor(anchor)
            if score > best_score:
                best_score = score
                best_href = anchor.get("href", "")

        if best_href:
            return best_href

        for anchor in anchors:
            href = anchor.get("href", "")
            if not href:
                continue
            href_lower = href.lower()
            if not href_lower.startswith("http"):
                continue
            if "unsubscribe" in href_lower:
                continue
            if re.search(r"\.(?:jpg|jpeg|png|gif|bmp|svg)(?:[?#]|$)", href_lower):
                continue
            return href
        return ""

    def extract_hero_image(html: str) -> str:
        def parse_dimension(value) -> int:
            if not value:
                return 0
            if isinstance(value, (int, float)):
                return int(value)
            match = re.search(r"(\d+)(?:\.\d+)?", str(value))
            return int(match.group(1)) if match else 0

        def score_image(img) -> float:
            src = img.get("src", "")
            if not src:
                return -1
            src_lower = src.lower()
            if src_lower.startswith("data:"):
                return -1
            if not src_lower.startswith("http") and "//" not in src_lower:
                return -1
            if any(token in src_lower for token in ["logo", "icon", "spacer", "pixel", "tracking", "badge", "social"]):
                return -1

            alt = (img.get("alt") or "").lower()
            if any(token in alt for token in ["logo", "icon", "twitter", "facebook", "instagram"]):
                return -1

            width = parse_dimension(img.get("width"))
            height = parse_dimension(img.get("height"))
            style = img.get("style") or ""
            style_width = parse_dimension(re.search(r"width\s*:\s*([0-9.]+)", style))
            style_height = parse_dimension(re.search(r"height\s*:\s*([0-9.]+)", style))
            width = max(width, style_width)
            height = max(height, style_height)
            if width == 0 and height == 0:
                width = parse_dimension(img.get("data-width"))
                height = parse_dimension(img.get("data-height"))

            if width and not height:
                height = width
            if height and not width:
                width = height

            area = width * height
            score = float(area)
            if "hero" in alt or "hero" in src_lower or "banner" in alt or "banner" in src_lower:
                score += 500000
            if width >= 300:
                score += 50000
            if img.find_parent("a"):
                score += 1000
            return score

        soup = BeautifulSoup(html, "html.parser")
        imgs = soup.find_all("img", src=True)
        best_img, best_score = None, 0
        for img in imgs:
            score = score_image(img)
            if score > best_score:
                best_img, best_score = img, score

        if best_img:
            return best_img.get("src", "")

        for img in imgs:
            src = img.get("src", "")
            if not src:
                continue
            src_lower = src.lower()
            if any(token in src_lower for token in ["logo", "icon", "spacer", "pixel", "tracking"]):
                continue
            if src_lower.startswith("data:"):
                continue
            if not src_lower.startswith("http") and "//" not in src_lower:
                continue
            return src
        return ""

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
