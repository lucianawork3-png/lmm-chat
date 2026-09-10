"""
Menstrual cycle + moon phase awareness for the calendar.

Period start dates live in a Notion database ("Cycle Log") so nothing personal
ends up committed to this public repo. Cycle length is inferred from your
logged history (falling back to a 28-day default until there's enough data),
and the moon phase is computed locally — no external service or API key needed.

This is a rough personal-awareness estimate, not a medical prediction.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta

import streamlit as st
from notion_client import Client

DATA_SOURCE_ID = "42023716-a9cd-40e9-9620-8e370dd00079"  # "Cycle Log" database

DEFAULT_CYCLE_LENGTH = 28
DEFAULT_PERIOD_LENGTH = 5
LUTEAL_LENGTH = 14  # the luteal phase stays ~14 days regardless of total cycle length

SYNODIC_MONTH = 29.530588861
REF_NEW_MOON = datetime(2000, 1, 6, 18, 14)  # a known new moon, UTC

MOON_PHASES = [
    (0.0625, "New Moon", "🌑", "Rest & reset"),
    (0.1875, "Waxing Crescent", "🌒", "Building energy"),
    (0.3125, "First Quarter", "🌓", "Push, take action"),
    (0.4375, "Waxing Gibbous", "🌔", "Building momentum"),
    (0.5625, "Full Moon", "🌕", "Peak energy"),
    (0.6875, "Waning Gibbous", "🌖", "Releasing, sharing"),
    (0.8125, "Last Quarter", "🌗", "Slowing down"),
    (0.9375, "Waning Crescent", "🌘", "Winding down"),
]


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


@st.cache_data(ttl=300, show_spinner=False)
def list_period_starts() -> list[date]:
    notion = _notion_client()
    results = notion.data_sources.query(
        data_source_id=DATA_SOURCE_ID,
        sorts=[{"property": "Start Date", "direction": "ascending"}],
    )["results"]
    starts = []
    for page in results:
        d = page["properties"]["Start Date"]["date"]
        if d and d.get("start"):
            try:
                starts.append(date.fromisoformat(d["start"][:10]))
            except Exception:
                pass
    return starts


def log_period_start(day: date) -> None:
    notion = _notion_client()
    notion.pages.create(
        parent={"data_source_id": DATA_SOURCE_ID},
        properties={
            "Name": {"title": [{"text": {"content": day.strftime("Period start – %d %b %Y")}}]},
            "Start Date": {"date": {"start": day.isoformat()}},
        },
    )
    list_period_starts.clear()


def cycle_stats(starts: list[date]) -> dict:
    """Average cycle length inferred from logged history (falls back to a default)."""
    avg_len = DEFAULT_CYCLE_LENGTH
    if len(starts) >= 2:
        deltas = [(b - a).days for a, b in zip(starts, starts[1:])]
        deltas = [d for d in deltas if 15 <= d <= 45]  # ignore obvious logging mistakes
        if deltas:
            avg_len = round(sum(deltas) / len(deltas))
    return {"avg_length": avg_len, "last_start": starts[-1] if starts else None, "logged_count": len(starts)}


def phase_for_day(day: date, stats: dict) -> dict | None:
    last_start = stats["last_start"]
    if last_start is None:
        return None
    cycle_len = stats["avg_length"]
    cycle_day = ((day - last_start).days % cycle_len) + 1
    ovulation_day = max(cycle_len - LUTEAL_LENGTH, 1)

    if cycle_day <= DEFAULT_PERIOD_LENGTH:
        phase, energy, color = "Menstrual", "Low energy", "#e05a6e"
    elif cycle_day < ovulation_day:
        phase, energy, color = "Follicular", "Rising energy", "#f2a53c"
    elif cycle_day <= ovulation_day + 1:
        phase, energy, color = "Ovulation", "Peak energy", "#3cb887"
    elif cycle_day > cycle_len - 4:
        phase, energy, color = "Late luteal (PMS)", "Low energy", "#8a6fd1"
    else:
        phase, energy, color = "Luteal", "Steady, gradually easing", "#5b8dd6"

    return {"cycle_day": cycle_day, "cycle_length": cycle_len, "phase": phase, "energy": energy, "color": color}


def moon_phase_for_day(day: date) -> dict:
    dt = datetime(day.year, day.month, day.day, 12)  # noon avoids off-by-one at date boundaries
    days_since = (dt - REF_NEW_MOON).total_seconds() / 86400
    frac = (days_since % SYNODIC_MONTH) / SYNODIC_MONTH
    for boundary, name, emoji, energy in MOON_PHASES:
        if frac < boundary:
            return {"name": name, "emoji": emoji, "energy": energy}
    return {"name": "New Moon", "emoji": "🌑", "energy": "Rest & reset"}


def day_badge(day: date, stats: dict) -> dict:
    """Compact info for a single day: moon emoji + cycle color, for badges/headers."""
    moon = moon_phase_for_day(day)
    ph = phase_for_day(day, stats)
    tooltip = f"{moon['emoji']} {moon['name']} — {moon['energy']}"
    if ph:
        tooltip += f" · {ph['phase']} day {ph['cycle_day']}/{ph['cycle_length']} — {ph['energy']}"
    return {"emoji": moon["emoji"], "color": ph["color"] if ph else "#c9c9c9", "tooltip": tooltip}


def day_summary(day: date, stats: dict) -> str:
    """One-line summary for the agenda list."""
    moon = moon_phase_for_day(day)
    parts = [f"{moon['emoji']} {moon['name']} — {moon['energy']}"]
    ph = phase_for_day(day, stats)
    if ph:
        parts.append(f"{ph['phase']} (day {ph['cycle_day']}/{ph['cycle_length']}) — {ph['energy']}")
    return " · ".join(parts)
