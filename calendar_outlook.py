import os
import requests
import msal

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPES = ["Calendars.ReadWrite", "offline_access"]


def _get_token() -> str:
    client_id = os.environ["MS_CLIENT_ID"]
    tenant_id = os.environ.get("MS_TENANT_ID", "consumers")
    refresh_token = os.environ.get("MS_REFRESH_TOKEN", "")

    app = msal.PublicClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
    )

    if refresh_token:
        result = app.acquire_token_by_refresh_token(refresh_token, scopes=SCOPES)
    else:
        raise RuntimeError("MS_REFRESH_TOKEN not set — run auth_outlook.py first")

    if "access_token" not in result:
        raise RuntimeError(f"Outlook auth failed: {result.get('error_description')}")

    return result["access_token"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}", "Content-Type": "application/json"}


def list_calendars() -> list[dict]:
    resp = requests.get(f"{GRAPH_BASE}/me/calendars", headers=_headers())
    resp.raise_for_status()
    return [
        {"id": c["id"], "label": c["name"], "provider": "outlook"}
        for c in resp.json().get("value", [])
        if c.get("canEdit")
    ]


def list_upcoming(calendar_id: str = "primary", max_results: int = 10) -> list[dict]:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    url = (
        f"{GRAPH_BASE}/me/calendars/{calendar_id}/events"
        if calendar_id != "primary"
        else f"{GRAPH_BASE}/me/events"
    )
    params = {
        "$top": max_results,
        "$orderby": "start/dateTime",
        "$filter": f"start/dateTime ge '{now}'",
        "$select": "subject,start,end,location",
    }
    resp = requests.get(url, headers=_headers(), params=params)
    resp.raise_for_status()
    return [
        {
            "title": e.get("subject", "(no title)"),
            "start": e["start"]["dateTime"],
            "location": e.get("location", {}).get("displayName"),
        }
        for e in resp.json().get("value", [])
    ]


def list_range(calendar_id: str, time_min: str, time_max: str, max_results: int = 250) -> list[dict]:
    url = (
        f"{GRAPH_BASE}/me/calendars/{calendar_id}/events"
        if calendar_id != "primary"
        else f"{GRAPH_BASE}/me/events"
    )
    params = {
        "$top": max_results,
        "$orderby": "start/dateTime",
        "$filter": f"start/dateTime ge '{time_min}' and start/dateTime le '{time_max}'",
        "$select": "subject,start,end,location",
    }
    resp = requests.get(url, headers=_headers(), params=params)
    resp.raise_for_status()
    return [
        {
            "id": e["id"],
            "title": e.get("subject", "(no title)"),
            "start": e["start"]["dateTime"],
            "end": e["end"]["dateTime"],
            "location": e.get("location", {}).get("displayName"),
        }
        for e in resp.json().get("value", [])
    ]


def update_event(calendar_id: str, event_id: str, updates: dict) -> None:
    body = {}
    if "title" in updates:
        body["subject"] = updates["title"]
    if "start" in updates:
        body["start"] = {"dateTime": updates["start"], "timeZone": "Europe/Lisbon"}
    if "end" in updates:
        body["end"] = {"dateTime": updates["end"], "timeZone": "Europe/Lisbon"}
    if "location" in updates:
        body["location"] = {"displayName": updates["location"]}
    resp = requests.patch(f"{GRAPH_BASE}/me/events/{event_id}", headers=_headers(), json=body)
    resp.raise_for_status()


def delete_event(calendar_id: str, event_id: str) -> None:
    resp = requests.delete(f"{GRAPH_BASE}/me/events/{event_id}", headers=_headers())
    resp.raise_for_status()


def create_event(event_dict: dict) -> str:
    calendar_id = event_dict.get("calendar_id", "primary")
    url = (
        f"{GRAPH_BASE}/me/calendars/{calendar_id}/events"
        if calendar_id != "primary"
        else f"{GRAPH_BASE}/me/events"
    )
    body = {
        "subject": event_dict["title"],
        "start": {"dateTime": event_dict["start"], "timeZone": "Europe/Lisbon"},
        "end": {"dateTime": event_dict["end"], "timeZone": "Europe/Lisbon"},
    }
    if event_dict.get("location"):
        body["location"] = {"displayName": event_dict["location"]}
    if event_dict.get("body"):
        body["body"] = {"contentType": "text", "content": event_dict["description"]}

    resp = requests.post(url, headers=_headers(), json=body)
    resp.raise_for_status()
    return resp.json().get("webLink", "")
