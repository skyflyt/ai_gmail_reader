# AI Gmail Reader

This custom integration exposes a service `ai_gmail_reader.check_gmail` which
queries a Gmail account using OpenAI to summarize recent messages.

## Installation

Copy the `custom_components/ai_gmail_reader` folder to your Home Assistant
`custom_components` directory and restart Home Assistant.

Ensure your Gmail API credentials (`token.json` and `credentials.json`) are
available under `/config/gmail/` on your Home Assistant instance.

## Configuration

Add the integration in `configuration.yaml` to load the service:

```yaml
ai_gmail_reader:
```

After reloading, you will be able to call `ai_gmail_reader.check_gmail` from the
Services UI.

## Service Data

Refer to `services.yaml` for all available fields. Example:

```yaml
service: ai_gmail_reader.check_gmail
data:
  sender: spearce@bhwk.com
  label: INBOX
  keyword: pokemon
  custom_prompt: >
    Look for preorder announcements for Pokémon games, cards, or plushies.
    If any preorder links are available, highlight them with summary and image.
  importance: auto
  image_required: "true"
  age_limit: 2d
  api_key: sk-...
  model: gpt-4o-mini
  response_variable: gmail_ai_response
```
