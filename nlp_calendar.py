import json
import os
from datetime import date
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM_PROMPT = """You are a calendar assistant. Parse the user's message into a structured calendar event.

Return ONLY a valid JSON object with these keys:
- title (string, required)
- start (ISO8601 datetime string, required, assume CET/Amsterdam timezone)
- end (ISO8601 datetime string, required — default to 1 hour after start if not specified)
- location (string or null)
- description (string or null)
- calendar_id (string — pick the most appropriate from the list provided)
- attendees (array of strings — first names or emails of people mentioned after "with", empty array if none)
- reminder_minutes (integer — minutes before event to send reminder, default 30, extract from message if mentioned e.g. "remind me 1 hour before" = 60)
- note (string or null — flag any ambiguity or assumption you made)

Always return a calendar event — never reject the message. Use the user's words as the title if nothing else is clear.
Return raw JSON only, no markdown fences."""


def parse_event(user_message: str, calendars: list[dict]) -> dict:
    calendar_list = "\n".join(
        f"- {c['id']}: {c['label']} ({c['provider']})" for c in calendars
    )
    today = date.today().isoformat()

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Today is {today} (Friday). Available calendars:\n{calendar_list}\n\nMessage: {user_message}",
            }
        ],
    )

    text = response.content[0].text.strip()
    # Strip markdown fences if Claude added them despite instructions
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)
