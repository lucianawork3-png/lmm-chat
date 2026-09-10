"""
Local-only script (not deployed to Streamlit Cloud): checks upcoming calendar
events for a "reminder_minutes" set via the LMM Calendar widget, and fires a
native macOS notification when that reminder window is reached. Meant to run
periodically via a LaunchAgent — see setup_notify_agent.sh.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env", override=True)

import calendar_google
import calendar_outlook

CACHE_FILE = BASE_DIR / ".notify_cache.json"
LOOKAHEAD = timedelta(hours=3)


def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(json.dumps(cache))


def notify(title: str, subtitle: str) -> None:
    script = (
        f'display notification "{subtitle}" with title "{title}" sound name "Ping"'
    )
    subprocess.run(["osascript", "-e", script], check=False)


def list_calendars() -> list[dict]:
    cals = []
    try:
        cals += calendar_google.list_calendars()
    except Exception:
        pass
    try:
        cals += calendar_outlook.list_calendars()
    except Exception:
        pass
    return cals


def main() -> None:
    now = datetime.now(timezone.utc)
    time_min = now.isoformat().replace("+00:00", "Z")
    time_max = (now + LOOKAHEAD).isoformat().replace("+00:00", "Z")

    fetchers = {"google": calendar_google.list_range, "outlook": calendar_outlook.list_range}
    cache = load_cache()
    fired = 0

    for cal in list_calendars():
        fetch = fetchers.get(cal["provider"])
        if not fetch:
            continue
        try:
            events = fetch(cal["id"], time_min, time_max)
        except Exception:
            continue

        for ev in events:
            minutes = ev.get("reminder_minutes")
            if minutes is None or "T" not in (ev.get("start") or ""):
                continue

            start_dt = datetime.fromisoformat(ev["start"])
            notify_at = start_dt - timedelta(minutes=minutes)
            cache_key = f"{ev['id']}:{ev['start']}"

            if notify_at <= now.astimezone(start_dt.tzinfo) < start_dt and cache_key not in cache:
                when = start_dt.strftime("%H:%M")
                loc = f" at {ev['location']}" if ev.get("location") else ""
                notify(f"In {minutes} min: {ev['title']}", f"{when}{loc}")
                cache[cache_key] = now.isoformat()
                fired += 1

    cutoff = now - timedelta(days=1)
    cache = {
        k: v for k, v in cache.items()
        if datetime.fromisoformat(v.replace("Z", "+00:00")) > cutoff
    }
    save_cache(cache)

    if fired:
        print(f"Fired {fired} notification(s).")


if __name__ == "__main__":
    main()
