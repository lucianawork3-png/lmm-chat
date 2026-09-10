from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import streamlit as st

import nlp_calendar as nlp
import calendar_google
import calendar_outlook
import contacts

LISBON_TZ = ZoneInfo("Europe/Lisbon")


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
        load_range_events.clear()
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


@st.cache_data(ttl=60)
def load_range_events(calendars: list[dict], time_min: str, time_max: str) -> list[dict]:
    fetchers = {"google": calendar_google.list_range, "outlook": calendar_outlook.list_range}
    events = []
    for cal in calendars:
        fetch = fetchers.get(cal["provider"])
        if not fetch:
            continue
        try:
            for ev in fetch(cal["id"], time_min, time_max):
                ev["_calendar_label"] = cal["label"]
                ev["_provider"] = cal["provider"]
                ev["_calendar_id"] = cal["id"]
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

    today = datetime.now(LISBON_TZ).date()
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


WEEK_START_HOUR = 7
WEEK_END_HOUR = 20
HOUR_PX = 38


def _parse_dt(iso: str):
    try:
        return datetime.fromisoformat(iso)
    except Exception:
        return None


def _layout_day_columns(day_events: list[dict]):
    """Assign each timed event a column so overlapping events sit side-by-side."""
    dated = []
    for ev in day_events:
        start = _parse_dt(ev["start"])
        end = _parse_dt(ev.get("end") or ev["start"])
        if start is None:
            continue
        dated.append((ev, start, end or start))
    dated.sort(key=lambda x: x[1])

    col_end_times: list[datetime] = []
    placements = []
    for ev, start, end in dated:
        placed = False
        for i, col_end in enumerate(col_end_times):
            if start >= col_end:
                col_end_times[i] = end
                placements.append((ev, start, end, i))
                placed = True
                break
        if not placed:
            col_end_times.append(end)
            placements.append((ev, start, end, len(col_end_times) - 1))
    total_cols = max(len(col_end_times), 1)
    return placements, total_cols


def _build_week_html(days: list, timed_by_day: dict, allday_by_day: dict, today) -> str:
    grid_height = (WEEK_END_HOUR - WEEK_START_HOUR) * HOUR_PX

    def time_to_top(dt: datetime) -> float:
        minutes = (dt.hour - WEEK_START_HOUR) * 60 + dt.minute
        return max(0.0, minutes) / 60 * HOUR_PX

    day_cols_html = []
    for d in days:
        placements, total_cols = _layout_day_columns(timed_by_day[d])
        blocks = []
        for ev, start, end, col in placements:
            top = time_to_top(start)
            bottom = time_to_top(end) if end > start else top + HOUR_PX / 2
            height = max(bottom - top, 20)
            width_pct = 100 / total_cols
            left_pct = col * width_pct
            title = (ev.get("title") or "").replace("<", "&lt;")

            # Only include lines that actually fit the block's height, so text never gets
            # clipped mid-word — drop location first, then the time label, for short events.
            time_html = f"<div class='ev-time'>{start.strftime('%H:%M')}</div>" if height >= 26 else ""
            loc_html = (
                f"<div class='ev-loc'>{ev['location']}</div>"
                if height >= 46 and ev.get("location")
                else ""
            )
            blocks.append(
                f"<div class='event' style='top:{top}px;height:{height}px;left:{left_pct}%;width:{width_pct}%;'>"
                f"{time_html}<div class='ev-title'>{title}</div>{loc_html}</div>"
            )
        day_cols_html.append(f"<div class='day-col'>{''.join(blocks)}</div>")

    hour_labels_html = "".join(
        f"<div class='hour-row' style='top:{(h - WEEK_START_HOUR) * HOUR_PX}px'>{h:02d}:00</div>"
        for h in range(WEEK_START_HOUR, WEEK_END_HOUR + 1)
    )
    gridlines_html = "".join(
        f"<div class='gridline' style='top:{(h - WEEK_START_HOUR) * HOUR_PX}px'></div>"
        for h in range(WEEK_START_HOUR, WEEK_END_HOUR + 1)
    )
    header_cells = "".join(
        f"<div class='day-header{' today' if d == today else ''}'>"
        f"<div class='dn'>{d.strftime('%a')}</div><div class='dd'>{d.strftime('%d')}</div></div>"
        for d in days
    )
    allday_cells = "".join(
        "<div class='allday-col'>"
        + "".join(f"<div class='allday-ev'>{e['title']}</div>" for e in allday_by_day[d])
        + "</div>"
        for d in days
    )

    return f"""
    <style>
      * {{ box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }}
      body {{ margin: 0; }}
      .cal {{ display: flex; flex-direction: column; }}
      .header-row {{ display: flex; border-bottom: 1px solid #e0e0e0; }}
      .time-gutter {{ width: 52px; flex-shrink: 0; }}
      .day-header {{ flex: 1; text-align: center; padding: 6px 2px; font-size: 13px; color: #333; border-left: 1px solid #eee; }}
      .day-header.today .dd {{ background: #1a73e8; color: white; border-radius: 50%; display: inline-block; width: 22px; height: 22px; line-height: 22px; }}
      .dn {{ color: #888; font-size: 11px; text-transform: uppercase; }}
      .dd {{ font-size: 15px; font-weight: 600; }}
      .allday-row {{ display: flex; border-bottom: 1px solid #eee; min-height: 22px; }}
      .allday-col {{ flex: 1; border-left: 1px solid #f0f0f0; padding: 2px; }}
      .allday-ev {{ background: #e4f6ea; border: 1px solid #34a853; border-radius: 4px; font-size: 11px; padding: 1px 4px; margin-bottom: 2px; }}
      .body-row {{ display: flex; }}
      .hours-col {{ width: 52px; flex-shrink: 0; position: relative; height: {grid_height}px; }}
      .hour-row {{ position: absolute; right: 6px; transform: translateY(-6px); font-size: 10px; color: #999; }}
      .days-grid {{ flex: 1; display: flex; position: relative; height: {grid_height}px; }}
      .gridlines-overlay {{ position: absolute; inset: 0; pointer-events: none; z-index: 0; }}
      .gridline {{ position: absolute; left: 0; right: 0; border-top: 1px solid #f2f2f2; }}
      .day-col {{ flex: 1; position: relative; border-left: 1px solid #f0f0f0; z-index: 1; }}
      .event {{ position: absolute; background: #e4f6ea; border-left: 3px solid #34a853; border-radius: 4px; padding: 1px 4px; overflow: hidden; font-size: 11px; line-height: 1.15; z-index: 2; }}
      .ev-time {{ color: #1e7e3c; font-size: 10px; line-height: 1.15; }}
      .ev-title {{ font-weight: 600; color: #1a3d1f; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.15; }}
      .ev-loc {{ font-size: 10px; color: #4d7a58; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.15; }}
    </style>
    <div class="cal">
      <div class="header-row"><div class="time-gutter"></div>{header_cells}</div>
      <div class="allday-row"><div class="time-gutter"></div>{allday_cells}</div>
      <div class="body-row">
        <div class="hours-col">{hour_labels_html}</div>
        <div class="days-grid">
          <div class="gridlines-overlay">{gridlines_html}</div>
          {''.join(day_cols_html)}
        </div>
      </div>
    </div>
    """


def render_week_grid(calendars: list[dict]):
    st.subheader("🗓️ Week")

    today = datetime.now(LISBON_TZ).date()
    if "cal_week_cursor" not in st.session_state:
        diff = (today.weekday() + 1) % 7  # days since last Sunday
        st.session_state.cal_week_cursor = today - timedelta(days=diff)

    week_start = st.session_state.cal_week_cursor
    week_end = week_start + timedelta(days=6)

    nav_prev, nav_label, nav_next = st.columns([1, 4, 1])
    if nav_prev.button("◀", key="cal_week_prev", use_container_width=True):
        st.session_state.cal_week_cursor = week_start - timedelta(days=7)
        st.rerun()
    nav_label.markdown(
        f"<div style='text-align:center;font-weight:600'>{week_start.strftime('%d %b')} – {week_end.strftime('%d %b %Y')}</div>",
        unsafe_allow_html=True,
    )
    if nav_next.button("▶", key="cal_week_next", use_container_width=True):
        st.session_state.cal_week_cursor = week_start + timedelta(days=7)
        st.rerun()

    time_min = datetime.combine(week_start, datetime.min.time(), tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    time_max = (
        datetime.combine(week_end, datetime.min.time(), tzinfo=timezone.utc) + timedelta(days=1)
    ).isoformat().replace("+00:00", "Z")
    events = load_range_events(calendars, time_min, time_max)

    days = [week_start + timedelta(days=i) for i in range(7)]
    timed_by_day: dict = {d: [] for d in days}
    allday_by_day: dict = {d: [] for d in days}
    for ev in events:
        start = _parse_dt(ev["start"])
        if start is None or start.date() not in timed_by_day:
            continue
        if "T" in ev["start"]:
            timed_by_day[start.date()].append(ev)
        else:
            allday_by_day[start.date()].append(ev)

    html = _build_week_html(days, timed_by_day, allday_by_day, today)
    st.components.v1.html(html, height=(WEEK_END_HOUR - WEEK_START_HOUR) * HOUR_PX + 70, scrolling=True)

    st.divider()
    st.markdown("**This week's events**")
    week_events = sorted(events, key=lambda e: e["start"])
    if not week_events:
        st.caption("No events this week.")
    for ev in week_events:
        dt = _parse_dt(ev["start"])
        if dt is None:
            continue
        when = dt.strftime("%a %H:%M") if "T" in ev["start"] else f"{dt.strftime('%a')} (all day)"
        label = f"{when} · {ev['title']}"
        if st.button(label, key=f"cal_event_btn_{ev['id']}", use_container_width=True):
            st.session_state.cal_editing_event = ev
            st.rerun()

    if st.session_state.get("cal_editing_event"):
        render_event_editor(st.session_state.cal_editing_event)


def render_event_editor(ev: dict):
    st.divider()
    st.markdown(f"**Edit event**")

    start_dt = _parse_dt(ev["start"])
    end_dt = _parse_dt(ev.get("end") or ev["start"]) or start_dt
    is_all_day = "T" not in ev["start"]

    new_title = st.text_input("Title", value=ev.get("title", ""), key="edit_ev_title")

    new_start_dt, new_end_dt = start_dt, end_dt
    if is_all_day:
        st.caption("All-day event — editing its time isn't supported here yet, but you can still edit the title/location or delete it.")
    else:
        c1, c2 = st.columns(2)
        new_start_date = c1.date_input("Start date", value=start_dt.date(), key="edit_ev_start_date")
        new_start_time = c2.time_input("Start time", value=start_dt.time(), key="edit_ev_start_time")
        c3, c4 = st.columns(2)
        new_end_date = c3.date_input("End date", value=end_dt.date(), key="edit_ev_end_date")
        new_end_time = c4.time_input("End time", value=end_dt.time(), key="edit_ev_end_time")
        new_start_dt = datetime.combine(new_start_date, new_start_time)
        new_end_dt = datetime.combine(new_end_date, new_end_time)

    new_location = st.text_input("Location", value=ev.get("location") or "", key="edit_ev_location")

    fetchers = {"google": (calendar_google.update_event, calendar_google.delete_event),
                "outlook": (calendar_outlook.update_event, calendar_outlook.delete_event)}
    update_fn, delete_fn = fetchers[ev["_provider"]]

    col_save, col_delete, col_cancel = st.columns(3)
    if col_save.button("💾 Save", key="edit_ev_save", type="primary"):
        updates = {"title": new_title, "location": new_location}
        if not is_all_day:
            updates["start"] = new_start_dt.isoformat()
            updates["end"] = new_end_dt.isoformat()
        try:
            update_fn(ev["_calendar_id"], ev["id"], updates)
            load_range_events.clear()
            st.session_state.cal_editing_event = None
            st.success("Saved.")
            st.rerun()
        except Exception as e:
            st.error(f"Couldn't save: {e}")

    if col_delete.button("🗑️ Delete", key="edit_ev_delete"):
        try:
            delete_fn(ev["_calendar_id"], ev["id"])
            load_range_events.clear()
            st.session_state.cal_editing_event = None
            st.success("Deleted.")
            st.rerun()
        except Exception as e:
            st.error(f"Couldn't delete: {e}")

    if col_cancel.button("✗ Cancel", key="edit_ev_cancel"):
        st.session_state.cal_editing_event = None
        st.rerun()


def render():
    st.markdown("<style>section.stMain{overflow-anchor: none;}</style>", unsafe_allow_html=True)

    if "cal_messages" not in st.session_state:
        st.session_state.cal_messages = []
    if "cal_pending_event" not in st.session_state:
        st.session_state.cal_pending_event = None
    if "cal_editing_event" not in st.session_state:
        st.session_state.cal_editing_event = None

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
        if st.session_state.get("cal_view_mode") not in ("List", "Week"):
            st.session_state.cal_view_mode = "List"
        toggle_list, toggle_week = st.columns(2)
        if toggle_list.button(
            "List", key="cal_view_list_btn", use_container_width=True,
            type="primary" if st.session_state.cal_view_mode == "List" else "secondary",
        ):
            st.session_state.cal_view_mode = "List"
            st.rerun()
        if toggle_week.button(
            "Week", key="cal_view_week_btn", use_container_width=True,
            type="primary" if st.session_state.cal_view_mode == "Week" else "secondary",
        ):
            st.session_state.cal_view_mode = "Week"
            st.rerun()

        if st.session_state.cal_view_mode == "List":
            render_agenda(load_upcoming_events(calendars))
        else:
            render_week_grid(calendars)

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
