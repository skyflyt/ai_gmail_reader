import base64
import os
import re
import logging

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from openai import OpenAI
import json

_LOGGER = logging.getLogger(__name__)

TOKEN_DIR = "/config/.ai_gmail_reader"
TOKEN_PATH = os.path.join(TOKEN_DIR, "token.json")
OUTPUT_DIR = os.path.join(TOKEN_DIR, "output")
CREDS_PATH = "/config/gmail/credentials.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

BASE_PROMPT = (
    "Pleaser review this email and create a short, informal summary, most relevant link that will lead to more inormation to call to action, and most relevant image from marketing emails. "
    "Return JSON and keep 'summary' <= 140 chars."
)

def build_prompt(email_text: str, custom_prompt: str) -> str:
    return f"{BASE_PROMPT}\n{custom_prompt.strip()}\nEMAIL:\n{email_text}"

def setup_auth() -> str:
    os.makedirs(TOKEN_DIR, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
    creds = flow.run_local_server(port=0, open_browser=False)
    with open(TOKEN_PATH, "w") as token_file:
        token_file.write(creds.to_json())
    print(f"Token stored to {TOKEN_PATH}")
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

    MAX_RESULTS = 5
    client = OpenAI(api_key=api_key)
    profile = keyword.lower().replace(" ", "_") or "default"

    if not os.path.isfile(TOKEN_PATH):
        _LOGGER.error("Gmail token.json not found at %s", TOKEN_PATH)
        return {"status": "error", "error": "no_token"}

    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
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
        try:
            ai_response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an email summarizer. Return only the main call‑to‑action URL "
                            "(the first non‑image hyperlink) and a friendly summary of the email."
                        ),
                    },
                    {"role": "user", "content": full_prompt.strip()},
                ],
            )
        except Exception as err:
            _LOGGER.exception("OpenAI request failed: %s", err)
            results.append({"status": "error", "error": str(err)})
            continue

        raw_response = ai_response.choices[0].message.content.strip()
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

        # Extract the true call-to-action link
        soup = BeautifulSoup(html, "html.parser")
        anchors = [
            a["href"] for a in soup.find_all("a", href=True)
            if not a.find("img")
        ]
        cta_link = ""
        for href in anchors:
            if not re.search(r"\.(?:jpg|jpeg|png|gif|bmp|svg)(?:[?#]|$)", href, re.IGNORECASE):
                cta_link = href
                break
        if not cta_link and anchors:
            cta_link = anchors[0]

        # Image extraction (same as before)
        imgs = re.findall(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', html)
        real_imgs = [u for u in imgs if "s0-d-e1-ft" not in u and "googleusercontent.com/" not in u]
        image = ai_json.get("image") or (real_imgs[0] if real_imgs else "")

        result = {
            "status": "ok",
            "title": subject,
            "message": summary,
            "thread_id": thread_id,
            "link": ai_json.get("link") or cta_link,
            "image": image,
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
