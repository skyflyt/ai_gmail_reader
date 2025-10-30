# AI Gmail Reader

AI Gmail Reader is a custom Home Assistant integration that connects to your Gmail inbox, filters for unread messages matching specific criteria, and uses OpenAI to extract a short summary, link, and image from each message. This information is exposed as attributes on a sensor, allowing you to trigger notifications or automations based on incoming emails — perfect for preorder alerts, newsletter parsing, or promo detection.

---

## ✅ Features

- Monitors Gmail for new unread messages by sender, label, and keyword
- Uses OpenAI to extract a 140-character summary, a link, and an image from the email body
- Marks messages as read once processed
- Outputs results to a Home Assistant sensor (`sensor.ai_gmail_<channel>`)
- JSON attributes include: `title`, `message`, `link`, `image`, `preorder`, `importance`, `thread_id`, and `channel`
- Built-in service `ai_gmail_reader.check_gmail` for ad-hoc or automation use
- Optional notify helper so a single service call can fetch, summarize, and alert you

---

## 🚀 Installation

1. Copy the `custom_components/ai_gmail_reader` folder into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Create a Gmail API OAuth client and place the downloaded `credentials.json` in:

    ```
    /config/gmail/credentials.json
    ```

4. Use the built-in service `ai_gmail_reader.setup_auth` once to complete OAuth and generate a `token.json` at:

    ```
    /config/.ai_gmail_reader/token.json
    ```

    The authorization flow now explicitly requests offline access, so the resulting token file includes a refresh token for long-lived access without repeating consent.

5. Add the integration from **Settings → Devices & Services → Add Integration** and select **AI Gmail Reader**.

> This integration installs the `openai` Python package automatically. Version 1.9.0+ is required.

### 🔐 How to create `credentials.json`

1. Visit the [Google Cloud Console](https://console.cloud.google.com/) and sign in with the Google account you use for Gmail.
2. Create a new project (or choose an existing one), then open the **APIs & Services → Enabled APIs & services** page and click **Enable APIs and Services**. Search for **Gmail API** and enable it.
3. In **APIs & Services → OAuth consent screen**, choose **External**, provide an app name, user support email, and developer contact email, then save the draft consent screen. You do not need to publish it—test mode is fine for personal use.
4. Go to **APIs & Services → Credentials**, click **Create Credentials → OAuth client ID**, choose **Desktop app**, and give it a recognizable name.
5. Download the client configuration JSON, rename it to `credentials.json` if needed, and copy it to `/config/gmail/credentials.json` on your Home Assistant host (create the `gmail` directory if it does not exist).
6. Restart Home Assistant if the directory or file is new, then run the `ai_gmail_reader.setup_auth` service to finish authorizing the integration.

---

## ⚙️ Configuration

From the integration UI, you'll be asked to fill in:

- **Sender** (email address)
- **Gmail Label** (e.g., `INBOX` or any custom label)
- **Keyword** (e.g., `preorder`, `pokemon`, etc.)
- **OpenAI API key**
- **Model** (e.g., `gpt-5-mini`, `gpt-5`, `gpt-4o`, etc.)
- **Custom prompt** (optional — guides the summary behavior)

A new sensor will be created with attributes reflecting the latest AI-parsed email that matches your query.

---

## 🔔 Built-in notification helper

The `ai_gmail_reader.check_gmail` service can now notify you directly instead of only returning JSON. Provide the `notify_service` field with a Home Assistant notify target (for example `notify.mobile_app_pixel_8`). You can optionally customize the notification content:

- `notify_title` — optional template that uses Python-style `{variable}` placeholders. Available placeholders include everything in the AI result (`title`, `message`, `link`, `image`, `importance`, `channel`, `thread_id`, `preorder`) plus `sender` and `label`.
- `notify_message` — optional message body template using the same placeholders. If omitted, the service sends the AI summary and link.

This allows a single service call to fetch Gmail, summarize the email with AI, and push a notification to any supported device or channel.

## 🔁 Sensor Output Example

```yaml
sensor.ai_gmail_pokemon:
  friendly_name: AI Gmail (pokemon)
  emails:
    - status: ok
      title: "Black Bolt and White Flare Now in Pokémon TCG Live"
      message: "Collect powerful Pokémon ex from Unova! Redeem your booster codes inside."
      thread_id: 1981e4fe4c6f3eba
      link: https://tcg.pokemon.com/en-us/
      image: https://image.email.pokemon.com/lib/…/2019_Gmail_Promo_Logo.png
      channel: pokemon
      importance: auto
      preorder: false
