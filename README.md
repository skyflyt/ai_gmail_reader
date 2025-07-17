# AI Gmail Reader

This custom integration exposes a service `ai_gmail_reader.check_gmail` which
queries a Gmail account using OpenAI to summarize recent messages. Only unread
messages matching the query are considered.

## Installation

Copy the `custom_components/ai_gmail_reader` folder to your Home Assistant
`custom_components` directory and restart Home Assistant.

The integration relies on the `openai` Python package. Home Assistant will
automatically install the dependency, but you must be running version 1.9.0 or
newer. If your environment uses an older `openai` package you may see import
errors. Updating it to the latest release resolves these issues.

Place your Gmail API `credentials.json` under `/config/gmail/` on your Home
Assistant instance. Run the `ai_gmail_reader.setup_auth` service once to store
`token.json` under `/config/.ai_gmail_reader/`.

## Configuration

After copying the files and restarting Home Assistant, go to **Settings → Integrations** and click **Add Integration**. Choose **AI Gmail Reader** and fill in the form with the sender, label, OpenAI API key and model. A sensor will be created automatically and will poll Gmail every minute.

The latest AI summary is available in `sensor.ai_gmail_reader` and its JSON data is exposed as attributes so it can be used directly in automations and dashboards. You may optionally set a `response_variable` when calling the service to store the raw JSON in an `input_text` helper. The summary field in this JSON never exceeds 140 characters.

If you want a ready-made place to store this JSON output, create an
`input_text` helper in `configuration.yaml`:

```yaml
input_text:
  ai_gmail_result:
    name: AI Gmail Output
    max: 1024
```

Then call the service with `response_variable: ai_gmail_result` to keep the
latest result available for automations.

## Service Data

Refer to `services.yaml` for all available fields. Example:

```yaml
service: ai_gmail_reader.check_gmail
data:
  sender: email@domain.com
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
