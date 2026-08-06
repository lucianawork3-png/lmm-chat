import json
import os
from datetime import date

import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

DESTINATION_BLURBS = """- personal: everyday personal to-dos, errands, admin — the default when nothing else fits
- gathering: tasks related to the LvR Mentoring Gathering (event/community)
- on_demand: tasks related to the ON DEMAND product/course"""

SYSTEM_PROMPT = f"""You are a task management assistant. Parse the user's message into a structured action
against one of three Notion task lists ("destinations"):

{DESTINATION_BLURBS}

Return ONLY a valid JSON object with these keys:
- action: one of "add", "complete", "reschedule", "rename", "clarify"
- destination: "personal" | "gathering" | "on_demand" — required for action="add", inferred from
  the message's subject matter (default to "personal" if nothing else clearly fits). For
  complete/reschedule/rename, this is not needed in your response — you'll return target_page_id instead.
- title: new task title (action="add" only)
- target_page_id: the page_id of the matched existing task, for complete/reschedule/rename — must be
  copied verbatim from the provided task list below, never invented
- matched_task_title: the exact title of the matched task (so a confirmation card can be shown
  without a second lookup)
- due_date: "YYYY-MM-DD" or null — for add (optional) and reschedule (required); resolve relative
  dates ("Friday", "tomorrow") against today's date
- new_title: the new title, for action="rename" only
- note: string or null — flag any assumption you made (e.g. resolved "Friday" to a date, or picked a
  destination that wasn't explicit)
- reply: required when action="clarify" — a short, specific clarifying question

Rules:
- For complete/reschedule/rename, match the referenced task against the provided list (fuzzy/partial/
  case-insensitive is fine). If zero or more than one open task plausibly matches, do NOT guess — set
  action to "clarify" and ask a specific question in reply instead.
- Never fabricate a target_page_id — it must come from the provided list.
- Return raw JSON only, no markdown fences."""


def parse_task_command(user_message: str, open_tasks: list[dict]) -> dict:
    task_list = "\n".join(
        f"- id={t['page_id']} | [{t['dest_label']}] {t['title']} (due: {t['due_date'] or 'none'})"
        for t in open_tasks
    ) or "(no open tasks)"

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Today is {date.today().isoformat()}.\n\n"
                    f"Current open tasks:\n{task_list}\n\nMessage: {user_message}"
                ),
            }
        ],
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)
