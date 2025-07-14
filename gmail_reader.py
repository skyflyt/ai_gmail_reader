import base64
import os
import re
import requests
import json
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from openai import OpenAI

def check_gmail(sender, label, keyword, custom_prompt, importance,
                image_required, age_limit, api_key, model):

    GMAIL_TOKEN_PATH = "/config/gmail/token.json"
    GMAIL_CREDS_PATH = "/config/gmail/credentials.json"
    MAX_RESULTS = 5

    client = OpenAI(api_key=api_key)

    # Setup Gmail API
    creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_PATH)
    service = build('gmail', 'v1', credentials=creds)

    # Build search query
    q = f"label:{label} from:{sender} newer_than:{age_limit}"
    if keyword:
        q += f" {keyword}"

    messages = service.users().messages().list(userId='me', q=q, maxResults=MAX_RESULTS).execute().get('messages', [])

    if not messages:
        return {"status": "no_unread"}

    for msg_meta in messages:
        msg = service.users().messages().get(userId='me', id=msg_meta['id'], format='full').execute()

        headers = {h['name']: h['value'] for h in msg['payload']['headers']}
        date = parsedate_to_datetime(headers.get('Date', ''))
        subject = headers.get('Subject', '')
        thread_id = msg.get('threadId')

        # Extract HTML body
        parts = msg['payload'].get('parts', [])
        html = ""
        for part in parts:
            if part['mimeType'] == 'text/html':
                data = part['body'].get('data')
                if data:
                    html = base64.urlsafe_b64decode(data.encode()).decode()

        # Clean HTML for prompt
        clean_text = re.sub(r'<[^>]+>', '', html)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        # GPT prompt
        full_prompt = f"""
            EMAIL:
            {clean_text}

            INSTRUCTIONS:
            {custom_prompt.strip()}
        """

        ai_response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an email summarizer for a Gmail inbox."},
                {"role": "user", "content": full_prompt.strip()}
            ]
        )

        summary = ai_response.choices[0].message.content

        # Extract image and link
        link_match = re.search(r'https?://\S+', html)
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
            "preorder": "preorder" in clean_text.lower()
        }

        return result

    return {"status": "no_valid_response"}
