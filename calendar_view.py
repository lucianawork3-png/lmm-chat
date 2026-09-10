from __future__ import annotations

import calendar as calendar_module
from datetime import datetime, timedelta, timezone

import streamlit as st

import nlp_calendar as nlp
import calendar_google
import calendar_outlook
import contacts


def fmt_dt(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%a %d %b, %H:%M")
    except Exception:
        return iso


def push_assistant(text: str):
    st.session_state.cal_messages.append({"role": "assistant", "content": text})


def add_event_to_calendar(ev: dict):
    provider = ev.get("_provider", "google")
    try:
        if provider == "google":
            link = calendar_google.create_event(ev)
        else:
            link = calendar_outlook.create_event(ev)
        st.session_state.cal_pending_event = None
        push_assistant(
            f"Done! **{ev['title']}** added to {ev['_calendar_label']}."
            + (f" [Open event]({link})" if link else "")
        )
        load_upcoming_events.clear()
        load_month_events.clear()
    except Exception as e:
        push_assistant(f"Error adding event: {e}")
    st.rerun()


@st.cache_data(ttl=300)
def load_all_calendars():
    cals = []
    errors = []
    try:
        cals += calendar_google.list_calendars()
    except Exception as e:
        errors.append(f"Google: {e}")
    try:
        cals += calendar_outlook.list_calendars()
    except Exception as e:
        errors.append(f"Outlook: {e}")
    return cals, errors


@st.cache_data(ttl=60)
def load_upcoming_events(calendars: list[dict], max_per_calendar: int = 15) -> list[dict]:
    fetchers = {"google": calendar_google.list_upcoming, "outlook": calendar_outlook.list_upcoming}
    events = []
    for cal in calendars:
        fetch = fetchers.get(cal["provider"])
        if not fetch:
            continue
        try:
            for ev in fetch(cal["id"], max_results=max_per_calendar):
                ev["_calendar_label"] = cal["label"]
                events.append(ev)
        except Exception:
            pass
    events.sort(key=lambda e: e["start"])
    return events


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    start = datetime(year, month, 1, tzinfo=timezone.utc) - timedelta(days=1)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) + timedelta(days=1)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc) + timedelta(days=1)
    return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")


@st.cache_data(ttl=60)
def load_month_events(calendars: list[dict], year: int, month: int) -> list[dict]:
    time_min, time_max = _month_bounds(year, month)
    fetchers = {"google": calendar_google.list_range, "outlook": calendar_outlook.list_range}
    events = []
    for cal in calendars:
        fetch = fetchers.get(cal["provider"])
        if not fetch:
            continue
        try:
            for ev in fetch(cal["id"], time_min, time_max):
                ev["_calendar_label"] = cal["label"]
                events.append(ev)
        except Exception:
            pass
    events.sort(key=lambda e: e["start"])
    return events


def render_agenda(events: list[dict]):
    st.subheader("📅 Upcoming")
    if not events:
        st.caption("Nothing on the calendar.")
        return

    today = datetime.now().date()
    grouped: dict = {}
    for ev in events:
        try:
            dt = datetime.fromisoformat(ev["start"])
        except Exception:
            continue
        grouped.setdefault(dt.date(), []).append((dt, ev))

    for day in sorted(grouped):
        if day == today:
            label = "Today"
        elif day == today + timedelta(days=1):
            label = "Tomorrow"
        else:
            label = day.strftime("%a %d %b")
        st.markdown(f"**{label}**")
        for dt, ev in sorted(grouped[day], key=lambda x: x[0]):
            time_str = dt.strftime("%H:%M") if "T" in ev["start"] else "All day"
            loc = f" — {ev['location']}" if ev.get("location") else ""
            st.markdown(f"- {time_str} · {ev['title']}{loc}")
    st.divider()


def render_month_grid(calendars: list[dict]):
    st.subheader("📅 Month")

    today = datetime.now().date()
    if "cal_month_cursor" not in st.session_state:
        st.session_state.cal_month_cursor = today.replace(day=1)
    if "cal_selected_day" not in st.session_state:
        st.session_state.cal_selected_day = today

    cursor = st.session_state.cal_month_cursor

    nav_prev, nav_label, nav_next = st.columns([1, 3, 1])
    if nav_prev.button("◀", key="cal_month_prev", use_container_width=True):
        prev_month = 12 if cursor.month == 1 else cursor.month - 1
        prev_year = cursor.year - 1 if cursor.month == 1 else cursor.year
        st.session_state.cal_month_cursor = cursor.replace(year=prev_year, month=prev_month, day=1)
        st.rerun()
    nav_label.markdown(f"<div style='text-align:center;font-weight:600'>{cursor.strftime('%B %Y')}</div>", unsafe_allow_html=True)
    if nav_next.button("▶", key="cal_month_next", use_container_width=True):
        next_month = 1 if cursor.month == 12 else cursor.month + 1
        next_year = cursor.year + 1 if cursor.month == 12 else cursor.year
        st.session_state.cal_month_cursor = cursor.replace(year=next_year, month=next_month, day=1)
        st.rerun()

    events = load_month_events(calendars, cursor.year, cursor.month)
    events_by_day: dict = {}
    for ev in events:
        try:
            dt = datetime.fromisoformat(ev["start"])
        except Exception:
            continue
        events_by_day.setdefault(dt.date(), []).append(ev)

    header_cols = st.columns(7)
    for col, name in zip(header_cols, ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]):
        col.markdown(f"<div style='text-align:center;color:#888;font-size:0.75em'>{name}</div>", unsafe_allow_html=True)

    for week in calendar_module.Calendar(firstweekday=0).monthdatescalendar(cursor.year, cursor.month):
        cols = st.columns(7)
        for col, day in zip(cols, week):
            if day.month != cursor.month:
                col.markdown("&nbsp;", unsafe_allow_html=True)
                continue
            count = len(events_by_day.get(day, []))
            label = f"{day.day} •" if count else str(day.day)
            btn_type = "primary" if day == st.session_state.cal_selected_day else "secondary"
            if col.button(label, key=f"cal_day_{day.isoformat()}", type=btn_type, use_container_width=True):
                st.session_state.cal_selected_day = day
                st.rerun()

    st.divider()
    selected = st.session_state.cal_selected_day
    selected_label = "Today" if selected == today else selected.strftime("%a %d %b")
    st.markdown(f"**{selected_label}**")
    day_events = sorted(events_by_day.get(selected, []), key=lambda e: e["start"])
    if not day_events:
        st.caption("No events.")
    for ev in day_events:
        try:
            dt = datetime.fromisoformat(ev["start"])
            time_str = dt.strftime("%H:%M") if "T" in ev["start"] else "All day"
        except Exception:
            time_str = ""
        loc = f" — {ev['location']}" if ev.get("location") else ""
        st.markdown(f"- {time_str} · {ev['title']}{loc}")
    st.divider()


def render():
    if "cal_messages" not in st.session_state:
        st.session_state.cal_messages = []
    if "cal_pending_event" not in st.session_state:
        st.session_state.cal_pending_event = None

    with st.sidebar:
        st.title("📅 Calendar")
        st.caption("Type a meeting in plain language — I'll add it to your calendar.")

        calendars, cal_errors = load_all_calendars()
        for err in cal_errors:
            st.warning(err)

        default_cal = {"id": "primary", "label": "Primary", "provider": "google"}
        if calendars:
            cal_options = {f"{c['label']} ({c['provider']})": c for c in calendars}
            chosen_label = st.selectbox("Default calendar", list(cal_options.keys()))
            default_cal = cal_options[chosen_label]
        else:
            st.error("No calendars loaded. Check credentials in .env")

        st.divider()
        if st.button("Clear chat", key="cal_clear"):
            st.session_state.cal_messages = []
            st.session_state.cal_pending_event = None
            st.rerun()

    if calendars:
        view_mode = st.radio(
            "View", ["List", "Month"], horizontal=True, key="cal_view_mode", label_visibility="collapsed"
        )
        if view_mode == "List":
            render_agenda(load_upcoming_events(calendars))
        else:
            render_month_grid(calendars)

    for msg in st.session_state.cal_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if st.session_state.cal_pending_event:
        ev = st.session_state.cal_pending_event
        with st.chat_message("assistant"):
            st.markdown("**Confirm this event?**")
            col_left, col_right = st.columns(2)
            with col_left:
                st.markdown(f"**{ev['title']}**")
                st.markdown(f"🕐 {fmt_dt(ev['start'])} → {fmt_dt(ev['end'])}")
                if ev.get("location"):
                    st.markdown(f"📍 {ev['location']}")
            with col_right:
                st.markdown(f"📁 {ev.get('_calendar_label', 'Calendar')} ({ev.get('_provider', 'google')})")
                if ev.get("_attendee_emails"):
                    st.markdown("👥 " + ", ".join(ev["_attendee_emails"]))
                if ev.get("note"):
                    st.caption(f"Note: {ev['note']}")

            btn_add, btn_cancel, _ = st.columns([1, 1, 3])
            if btn_add.button("✅ Add it", key="cal_confirm"):
                add_event_to_calendar(ev)
            if btn_cancel.button("✗ Cancel", key="cal_cancel"):
                st.session_state.cal_pending_event = None
                push_assistant("Cancelled. What else?")
                st.rerun()

    user_input = st.chat_input(
        "e.g. 'Coffee with Sara next Tuesday 10am at Lot Sixty One'", key="cal_input"
    )

    if user_input:
        st.session_state.cal_messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.spinner("Thinking..."):
            try:
                parsed = nlp.parse_event(user_input, calendars or [default_cal])
            except Exception as e:
                push_assistant(f"Sorry, I couldn't parse that: {e}")
                st.rerun()

        cal_id = parsed.get("calendar_id", default_cal["id"])
        matched_cal = next((c for c in calendars if c["id"] == cal_id), default_cal)
        parsed["calendar_id"] = matched_cal["id"]
        parsed["_provider"] = matched_cal["provider"]
        parsed["_calendar_label"] = matched_cal["label"]
        parsed["_attendee_emails"] = contacts.resolve_attendees(parsed.get("attendees") or [])
        parsed["_reminder_minutes"] = parsed.get("reminder_minutes", 30)

        st.session_state.cal_pending_event = parsed
        st.rerun()
