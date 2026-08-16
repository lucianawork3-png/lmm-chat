"""
Notion read/write layer for Task Chat.

Three destinations, each a Notion data source with a different schema —
DESTINATIONS below normalizes access to a common add/complete/reschedule/rename API.
"""

from __future__ import annotations

import os

import streamlit as st
from notion_client import Client

DESTINATIONS = {
    "on_demand": {
        "label": "LvR ON DEMAND",
        "icon": "⏯️",
        "data_source_id": "e881e33b-d488-83fd-94e2-873ca72fe93a",
        "title_prop": "Name",
        "status_prop": "Status",
        "status_type": "status",
        "todo_value": "ON Demand",
        "done_value": "Done",
        "date_prop": "Date",
    },
    "gathering": {
        "label": "LvR Mentoring Gathering",
        "icon": "🙂",
        "data_source_id": "abc7ca7f-2a51-41d0-ac62-594cddc98226",
        "title_prop": "Task",
        "status_prop": "Status",
        "status_type": "select",
        "todo_value": "To Do",
        "done_value": "Done",
        "date_prop": "Due Date",
    },
    "personal": {
        "label": "Personal TO DO",
        "icon": "🙅‍♀️",
        "data_source_id": "d5c717a4-1e2b-4326-b70f-74397c0ddc72",
        "title_prop": "Task",
        "status_prop": "Status",
        "status_type": "select",
        "todo_value": "To Do",
        "done_value": "Done",
        "date_prop": "Due Date",
    },
}


def _get_secret(key: str) -> str:
    val = os.environ.get(key, "")
    if val:
        return val
    try:
        return st.secrets.get(key, "")
    except Exception:
        return ""


def _notion_client() -> Client:
    token = _get_secret("NOTION_TOKEN")
    if not token:
        raise RuntimeError("NOTION_TOKEN is not set")
    return Client(auth=token)


def _status_filter_value(dest: dict) -> dict:
    return {dest["status_type"]: {"equals": dest["todo_value"]}}


def _status_property(dest: dict, value: str) -> dict:
    if dest["status_type"] == "status":
        return {"status": {"name": value}}
    return {"select": {"name": value}}


@st.cache_data(ttl=30, show_spinner=False)
def list_open_tasks() -> list[dict]:
    """Open ('to do') tasks across all three destinations, each tagged with its dest key."""
    notion = _notion_client()
    tasks = []
    for dest_key, dest in DESTINATIONS.items():
        # "on_demand" has two distinct to-do-flavored options (ON Demand / Leticia GPT) —
        # treat anything not "Done"/"In progress" as open for matching purposes there.
        if dest_key == "on_demand":
            results = notion.data_sources.query(data_source_id=dest["data_source_id"])["results"]
            results = [r for r in results if _status_name(r, dest) not in ("Done",)]
        else:
            results = notion.data_sources.query(
                data_source_id=dest["data_source_id"],
                filter={"property": dest["status_prop"], **_status_filter_value(dest)},
            )["results"]

        for page in results:
            props = page["properties"]
            title_prop = props[dest["title_prop"]]["title"]
            title = title_prop[0]["plain_text"] if title_prop else "(untitled)"
            date_val = props[dest["date_prop"]]["date"]
            due_date = date_val["start"] if date_val else None
            tasks.append({
                "dest": dest_key,
                "dest_label": f"{dest['icon']} {dest['label']}",
                "page_id": page["id"],
                "title": title,
                "due_date": due_date,
            })

    tasks.sort(key=lambda t: (t["due_date"] is None, t["due_date"] or ""))
    return tasks


def _status_name(page: dict, dest: dict) -> str | None:
    val = page["properties"][dest["status_prop"]].get(dest["status_type"])
    return val["name"] if val else None


def add_task(dest_key: str, title: str, due_date: str | None = None) -> dict:
    dest = DESTINATIONS[dest_key]
    notion = _notion_client()
    properties = {
        dest["title_prop"]: {"title": [{"text": {"content": title}}]},
        dest["status_prop"]: _status_property(dest, dest["todo_value"]),
    }
    if due_date:
        properties[dest["date_prop"]] = {"date": {"start": due_date}}

    page = notion.pages.create(
        parent={"data_source_id": dest["data_source_id"]},
        properties=properties,
    )
    list_open_tasks.clear()
    return {"page_id": page["id"], "url": page.get("url")}


def complete_task(dest_key: str, page_id: str) -> None:
    dest = DESTINATIONS[dest_key]
    notion = _notion_client()
    notion.pages.update(
        page_id=page_id,
        properties={dest["status_prop"]: _status_property(dest, dest["done_value"])},
    )
    list_open_tasks.clear()


def reschedule_task(dest_key: str, page_id: str, new_due_date: str) -> None:
    dest = DESTINATIONS[dest_key]
    notion = _notion_client()
    notion.pages.update(
        page_id=page_id,
        properties={dest["date_prop"]: {"date": {"start": new_due_date}}},
    )
    list_open_tasks.clear()


def rename_task(dest_key: str, page_id: str, new_title: str) -> None:
    dest = DESTINATIONS[dest_key]
    notion = _notion_client()
    notion.pages.update(
        page_id=page_id,
        properties={dest["title_prop"]: {"title": [{"text": {"content": new_title}}]}},
    )
    list_open_tasks.clear()
