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
    st.session_state.task_action = None
    st.session_state.task_destination = None
    st.session_state.task_target = None
    st.session_state.task_new_title = None


def finish_add(dest: str, title: str, due_date: str | None):
    notion_tasks.add_task(dest, title, due_date)
    log(
        f"Done! Added **{title}** to *{dest_label(dest)}*"
        + (f" (due: {due_date})." if due_date else " (no deadline).")
    )
    reset_wizard()
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

    for msg in st.session_state.task_messages:
        with st.chat_message("assistant"):
            st.markdown(msg)

    action = st.session_state.task_action

    if action is None:
        st.markdown("**What do you want to do?**")
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

    if st.button("‹ Cancel", key="task_wizard_cancel"):
        reset_wizard()
        st.rerun()

    if action == "add":
        if st.session_state.task_destination is None:
            st.markdown("**Add to which list?**")
            for key in notion_tasks.DESTINATIONS:
                if st.button(dest_label(key), key=f"pick_dest_{key}", use_container_width=True):
                    st.session_state.task_destination = key
                    st.rerun()
        elif st.session_state.task_new_title is None:
            dest = st.session_state.task_destination
            st.markdown(f"**Adding to _{dest_label(dest)}_ — what's the task?**")
            title = st.text_input("Task", key="add_title_input", placeholder="e.g. Call the accountant")
            if st.button("Next ›", key="add_title_next", disabled=not title.strip()):
                st.session_state.task_new_title = title.strip()
                st.rerun()
        else:
            dest = st.session_state.task_destination
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
                open_tasks = notion_tasks.list_open_tasks()
            except Exception as e:
                open_tasks = []
                st.error(f"Couldn't load tasks: {e}")

            verb = {"complete": "mark done", "reschedule": "reschedule", "rename": "rename"}[action]
            st.markdown(f"**Which task do you want to {verb}?**")

            if not open_tasks:
                st.info("No open tasks found.")
            for t in open_tasks:
                due = f" · {t['due_date']}" if t["due_date"] else ""
                label = f"[{t['dest_label']}] {t['title']}{due}"
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
                    reset_wizard()
                    st.rerun()
            elif action == "reschedule":
                st.markdown(f"**Reschedule “{t['title']}”**")
                new_date = st.date_input("New due date", key="reschedule_date_input").isoformat()
                if st.button("✅ Confirm", key="reschedule_confirm"):
                    notion_tasks.reschedule_task(t["dest"], t["page_id"], new_date)
                    log(f"Done! Rescheduled **{t['title']}** to {new_date}.")
                    reset_wizard()
                    st.rerun()
            elif action == "rename":
                st.markdown(f"**Rename “{t['title']}”**")
                new_title = st.text_input("New title", value=t["title"], key="rename_title_input")
                if st.button("✅ Confirm", key="rename_confirm", disabled=not new_title.strip()):
                    notion_tasks.rename_task(t["dest"], t["page_id"], new_title.strip())
                    log(f"Done! Renamed **{t['title']}** to **{new_title.strip()}**.")
                    reset_wizard()
                    st.rerun()
