from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

import notion_tasks


def dest_label(key: str) -> str:
    dest = notion_tasks.DESTINATIONS[key]
    return f"{dest['icon']} {dest['label']}"


def log(text: str):
    st.session_state.task_messages.append(text)


def reset_wizard():
    st.session_state.task_destination = None
    st.session_state.task_action = None
    st.session_state.task_target = None
    st.session_state.task_new_title = None


def reset_action():
    st.session_state.task_action = None
    st.session_state.task_target = None
    st.session_state.task_new_title = None


def finish_add(dest: str, title: str, due_date: str | None):
    notion_tasks.add_task(dest, title, due_date)
    log(
        f"Done! Added **{title}** to *{dest_label(dest)}*"
        + (f" (due: {due_date})." if due_date else " (no deadline).")
    )
    reset_action()
    st.rerun()


def _date_only(due_date: str | None) -> str | None:
    return due_date[:10] if due_date else None


def render_daily_plan():
    st.subheader("📋 Today's Focus")
    today_iso = date.today().isoformat()

    try:
        tasks = notion_tasks.list_open_tasks()
    except Exception as e:
        st.error(f"Couldn't load tasks: {e}")
        return

    if not tasks:
        st.caption("No open tasks. 🎉")
        return

    def section(label: str, group: list[dict]):
        if not group:
            return
        st.markdown(f"**{label}**")
        for t in group:
            key = f"today_pick_{t['page_id']}"
            default_checked = (_date_only(t["due_date"]) or "9999") <= today_iso
            cols = st.columns([0.08, 0.72, 0.2])
            cols[0].checkbox("", value=default_checked, key=key, label_visibility="collapsed")
            due = f" · due {t['due_date']}" if t["due_date"] else ""
            cols[1].markdown(f"{t['dest_label']} — {t['title']}{due}")
            if cols[2].button("✓ Done", key=f"today_done_{t['page_id']}", use_container_width=True):
                notion_tasks.complete_task(t["dest"], t["page_id"])
                st.rerun()

    overdue = [t for t in tasks if (_date_only(t["due_date"]) or today_iso) < today_iso]
    due_today = [t for t in tasks if _date_only(t["due_date"]) == today_iso]
    upcoming = [t for t in tasks if (_date_only(t["due_date"]) or today_iso) > today_iso]
    no_date = [t for t in tasks if not t["due_date"]]

    section("⏰ Overdue", overdue)
    section("📌 Due today", due_today)
    section("🗓️ Upcoming", upcoming)
    section("— No date", no_date)

    st.divider()
    selected = [t for t in tasks if st.session_state.get(f"today_pick_{t['page_id']}")]
    st.caption(f"{len(selected)} task(s) selected for today.")
    if st.button(
        "✅ Set selected as today's focus", key="commit_today_plan",
        type="primary", disabled=not selected,
    ):
        updated = 0
        for t in selected:
            if _date_only(t["due_date"]) != today_iso:
                notion_tasks.reschedule_task(t["dest"], t["page_id"], today_iso)
                updated += 1
        st.success(f"Set {updated} task(s) due today." if updated else "Selection already matches today's due date.")
        st.rerun()


def render():
    if "task_messages" not in st.session_state:
        st.session_state.task_messages = []
    if "task_action" not in st.session_state:
        st.session_state.task_action = None
    if "task_destination" not in st.session_state:
        st.session_state.task_destination = None
    if "task_target" not in st.session_state:
        st.session_state.task_target = None
    if "task_new_title" not in st.session_state:
        st.session_state.task_new_title = None

    with st.sidebar:
        st.title("✅ Tasks")
        st.caption("Add or edit tasks across Personal, Mentoring Gathering, and ON DEMAND.")

        try:
            open_tasks_sidebar = notion_tasks.list_open_tasks()
        except Exception as e:
            open_tasks_sidebar = []
            st.error(f"Couldn't load tasks: {e}")

        if open_tasks_sidebar:
            st.markdown("**Open tasks**")
            for t in open_tasks_sidebar:
                due = f" · {t['due_date']}" if t["due_date"] else ""
                st.caption(f"[{t['dest_label']}] {t['title']}{due}")

        st.divider()
        if st.button("Clear history", key="task_clear"):
            st.session_state.task_messages = []
            reset_wizard()
            st.rerun()

    if "task_view_mode" not in st.session_state:
        st.session_state.task_view_mode = "plan"

    toggle_plan, toggle_manage = st.columns(2)
    if toggle_plan.button(
        "📋 Plan my day", key="task_view_plan_btn", use_container_width=True,
        type="primary" if st.session_state.task_view_mode == "plan" else "secondary",
    ):
        st.session_state.task_view_mode = "plan"
        st.rerun()
    if toggle_manage.button(
        "🛠️ Manage tasks", key="task_view_manage_btn", use_container_width=True,
        type="primary" if st.session_state.task_view_mode == "manage" else "secondary",
    ):
        st.session_state.task_view_mode = "manage"
        st.rerun()

    if st.session_state.task_view_mode == "plan":
        render_daily_plan()
        return

    for msg in st.session_state.task_messages:
        with st.chat_message("assistant"):
            st.markdown(msg)

    destination = st.session_state.task_destination

    if destination is None:
        st.markdown("**Which list?**")
        for key in notion_tasks.DESTINATIONS:
            if st.button(dest_label(key), key=f"pick_dest_{key}", use_container_width=True):
                st.session_state.task_destination = key
                st.rerun()
        return

    action = st.session_state.task_action

    if action is None:
        if st.button("‹ Back", key="task_back_to_destination"):
            reset_wizard()
            st.rerun()
        st.markdown(f"**{dest_label(destination)} — what do you want to do?**")
        c1, c2, c3, c4 = st.columns(4)
        if c1.button("➕ Add", use_container_width=True, key="pick_action_add"):
            st.session_state.task_action = "add"
            st.rerun()
        if c2.button("✅ Complete", use_container_width=True, key="pick_action_complete"):
            st.session_state.task_action = "complete"
            st.rerun()
        if c3.button("📅 Reschedule", use_container_width=True, key="pick_action_reschedule"):
            st.session_state.task_action = "reschedule"
            st.rerun()
        if c4.button("✏️ Rename", use_container_width=True, key="pick_action_rename"):
            st.session_state.task_action = "rename"
            st.rerun()
        return

    if st.button("‹ Back", key="task_back_to_action"):
        reset_action()
        st.rerun()

    if action == "add":
        if st.session_state.task_new_title is None:
            dest = destination
            st.markdown(f"**Adding to _{dest_label(dest)}_ — what's the task?**")
            title = st.text_input("Task", key="add_title_input", placeholder="e.g. Call the accountant")
            if st.button("Next ›", key="add_title_next", disabled=not title.strip()):
                st.session_state.task_new_title = title.strip()
                st.rerun()
        else:
            dest = destination
            title = st.session_state.task_new_title
            st.markdown(f"**What's the deadline for “{title}”?**")
            c1, c2, c3 = st.columns(3)
            if c1.button("No deadline", key="due_none", use_container_width=True):
                finish_add(dest, title, None)
            if c2.button("Today", key="due_today", use_container_width=True):
                finish_add(dest, title, date.today().isoformat())
            if c3.button("Tomorrow", key="due_tomorrow", use_container_width=True):
                finish_add(dest, title, (date.today() + timedelta(days=1)).isoformat())
            st.caption("Or pick a specific date:")
            picked = st.date_input("Date", key="add_due_date_input")
            if st.button("Use this date", key="add_use_date"):
                finish_add(dest, title, picked.isoformat())

    elif action in ("complete", "reschedule", "rename"):
        if st.session_state.task_target is None:
            try:
                open_tasks = [t for t in notion_tasks.list_open_tasks() if t["dest"] == destination]
            except Exception as e:
                open_tasks = []
                st.error(f"Couldn't load tasks: {e}")

            verb = {"complete": "mark done", "reschedule": "reschedule", "rename": "rename"}[action]
            st.markdown(f"**{dest_label(destination)} — which task do you want to {verb}?**")

            if not open_tasks:
                st.info("No open tasks found in this list.")
            for t in open_tasks:
                due = f" · {t['due_date']}" if t["due_date"] else ""
                label = f"{t['title']}{due}"
                if st.button(label, key=f"pick_task_{t['page_id']}", use_container_width=True):
                    st.session_state.task_target = t
                    st.rerun()
        else:
            t = st.session_state.task_target
            if action == "complete":
                st.markdown(f"**Mark “{t['title']}” as done?**")
                if st.button("✅ Confirm", key="complete_confirm"):
                    notion_tasks.complete_task(t["dest"], t["page_id"])
                    log(f"Done! Marked **{t['title']}** as done.")
                    reset_action()
                    st.rerun()
            elif action == "reschedule":
                st.markdown(f"**Reschedule “{t['title']}”**")
                new_date = st.date_input("New due date", key="reschedule_date_input").isoformat()
                if st.button("✅ Confirm", key="reschedule_confirm"):
                    notion_tasks.reschedule_task(t["dest"], t["page_id"], new_date)
                    log(f"Done! Rescheduled **{t['title']}** to {new_date}.")
                    reset_action()
                    st.rerun()
            elif action == "rename":
                st.markdown(f"**Rename “{t['title']}”**")
                new_title = st.text_input("New title", value=t["title"], key="rename_title_input")
                if st.button("✅ Confirm", key="rename_confirm", disabled=not new_title.strip()):
                    notion_tasks.rename_task(t["dest"], t["page_id"], new_title.strip())
                    log(f"Done! Renamed **{t['title']}** to **{new_title.strip()}**.")
                    reset_action()
                    st.rerun()
