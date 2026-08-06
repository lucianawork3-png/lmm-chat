from __future__ import annotations

from datetime import datetime

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
