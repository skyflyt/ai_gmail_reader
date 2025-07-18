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

---

## 🚀 Installation

1. Copy the `custom_components/ai_gmail_reader` folder into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Place your Gmail API `credentials.json` in:

    ```
    /config/gmail/credentials.json
    ```

4. Use the built-in service `ai_gmail_reader.setup_auth` once to complete OAuth and generate a `token.json` at:

    ```
    /config/.ai_gmail_reader/token.json
    ```

5. Add the integration from **Settings → Devices & Services → Add Integration** and select **AI Gmail Reader**.

> This integration installs the `openai` Python package automatically. Version 1.9.0+ is required.

---

## ⚙️ Configuration

From the integration UI, you'll be asked to fill in:

- **Sender** (email address)
- **Gmail Label** (e.g., `INBOX` or any custom label)
- **Keyword** (e.g., `preorder`, `pokemon`, etc.)
- **OpenAI API key**
- **Model** (e.g., `gpt-4o`, `gpt-4o-mini`, etc.)
- **Custom prompt** (optional — guides the summary behavior)

A new sensor will be created with attributes reflecting the latest AI-parsed email that matches your query.

---

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
