from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_creds() -> Credentials:
    # Read individual fields to avoid JSON-in-TOML encoding issues
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN", "")
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    if not refresh_token:
        raise RuntimeError("GOOGLE_REFRESH_TOKEN not set")

    token_data = {
        "refresh_token": refresh_token.strip(),
        "client_id": client_id.strip(),
        "client_secret": client_secret.strip(),
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    creds = Credentials.from_authorized_user_info(token_data, SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return creds


def _service():
    return build("calendar", "v3", credentials=_get_creds(), cache_discovery=False)


def list_calendars() -> list[dict]:
    items = _service().calendarList().list().execute().get("items", [])
    return [
        {"id": c["id"], "label": c.get("summary", c["id"]), "provider": "google"}
        for c in items
        if c.get("accessRole") in ("owner", "writer")
    ]


def list_upcoming(calendar_id: str = "primary", max_results: int = 10) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    events = (
        _service()
        .events()
        .list(
            calendarId=calendar_id,
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
        .get("items", [])
    )
    return [
        {
            "title": e.get("summary", "(no title)"),
            "start": e["start"].get("dateTime", e["start"].get("date")),
            "location": e.get("location"),
        }
        for e in events
    ]


def _extract_reminder_minutes(e: dict) -> int | None:
    reminders = e.get("reminders") or {}
    if reminders.get("useDefault"):
        return None
    for o in reminders.get("overrides", []):
        if o.get("method") == "popup":
            return o.get("minutes")
    return None


def list_range(calendar_id: str, time_min: str, time_max: str, max_results: int = 250) -> list[dict]:
    events = (
        _service()
        .events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
        .get("items", [])
    )
    return [
        {
            "id": e["id"],
            "title": e.get("summary", "(no title)"),
            "start": e["start"].get("dateTime", e["start"].get("date")),
            "end": e["end"].get("dateTime", e["end"].get("date")),
            "location": e.get("location"),
            "reminder_minutes": _extract_reminder_minutes(e),
        }
        for e in events
    ]


def update_event(calendar_id: str, event_id: str, updates: dict) -> None:
    body = {}
    if "title" in updates:
        body["summary"] = updates["title"]
    if "start" in updates:
        body["start"] = {"dateTime": updates["start"], "timeZone": "Europe/Lisbon"}
    if "end" in updates:
        body["end"] = {"dateTime": updates["end"], "timeZone": "Europe/Lisbon"}
    if "location" in updates:
        body["location"] = updates["location"]
    if "reminder_minutes" in updates:
        minutes = updates["reminder_minutes"]
        if minutes is None:
            body["reminders"] = {"useDefault": False, "overrides": []}
        else:
            body["reminders"] = {"useDefault": False, "overrides": [{"method": "popup", "minutes": minutes}]}
    _service().events().patch(
        calendarId=calendar_id, eventId=event_id, body=body, sendUpdates="all"
    ).execute()


def delete_event(calendar_id: str, event_id: str) -> None:
    _service().events().delete(
        calendarId=calendar_id, eventId=event_id, sendUpdates="all"
    ).execute()


def create_event(event_dict: dict) -> str:
    calendar_id = event_dict.get("calendar_id", "primary")
    body = {
        "summary": event_dict["title"],
        "start": {"dateTime": event_dict["start"], "timeZone": "Europe/Lisbon"},
        "end": {"dateTime": event_dict["end"], "timeZone": "Europe/Lisbon"},
    }
    if event_dict.get("location"):
        body["location"] = event_dict["location"]
    if event_dict.get("description"):
        body["description"] = event_dict["description"]
    if event_dict.get("_attendee_emails"):
        body["attendees"] = [{"email": e} for e in event_dict["_attendee_emails"]]

    reminder_minutes = event_dict.get("_reminder_minutes", 30)
    body["reminders"] = {
        "useDefault": False,
        "overrides": [
            {"method": "email", "minutes": reminder_minutes},
            {"method": "popup", "minutes": reminder_minutes},
        ],
    }

    result = _service().events().insert(
        calendarId=calendar_id, body=body, sendUpdates="all"
    ).execute()
    return result.get("htmlLink", "")
