from __future__ import annotations

import streamlit as st

import nlp_tasks as nlp
import notion_tasks


def dest_label(key: str) -> str:
    return notion_tasks.DESTINATIONS[key]["label"]


def fmt_date(d: str | None) -> str:
    return d if d else "no due date"


def push_assistant(text: str):
    st.session_state.task_messages.append({"role": "assistant", "content": text})


def run_action(action: dict):
    a = action["action"]
    try:
        if a == "add":
            notion_tasks.add_task(action["destination"], action["title"], action.get("due_date"))
            push_assistant(
                f"Done! Added **{action['title']}** to *{dest_label(action['destination'])}*"
                f" (due: {fmt_date(action.get('due_date'))})."
            )
        elif a == "complete":
            notion_tasks.complete_task(action["dest"], action["target_page_id"])
            push_assistant(f"Done! Marked **{action['matched_task_title']}** as done.")
        elif a == "reschedule":
            notion_tasks.reschedule_task(action["dest"], action["target_page_id"], action["due_date"])
            push_assistant(f"Done! Rescheduled **{action['matched_task_title']}** to {action['due_date']}.")
        elif a == "rename":
            notion_tasks.rename_task(action["dest"], action["target_page_id"], action["new_title"])
            push_assistant(f"Done! Renamed **{action['matched_task_title']}** to **{action['new_title']}**.")
    except Exception as e:
        push_assistant(f"Error: {e}")
    st.session_state.task_pending_action = None
    st.rerun()


def render():
    if "task_messages" not in st.session_state:
        st.session_state.task_messages = []
    if "task_pending_action" not in st.session_state:
        st.session_state.task_pending_action = None

    with st.sidebar:
        st.title("✅ Tasks")
        st.caption("Add or edit tasks across Personal, Mentoring Gathering, and ON DEMAND.")

        try:
            open_tasks = notion_tasks.list_open_tasks()
        except Exception as e:
            open_tasks = []
            st.error(f"Couldn't load tasks: {e}")

        if open_tasks:
            st.markdown("**Open tasks**")
            for t in open_tasks:
                due = f" · {t['due_date']}" if t["due_date"] else ""
                st.caption(f"[{t['dest_label']}] {t['title']}{due}")

        st.divider()
        if st.button("Clear chat", key="task_clear"):
            st.session_state.task_messages = []
            st.session_state.task_pending_action = None
            st.rerun()

    for msg in st.session_state.task_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if st.session_state.task_pending_action:
        action = st.session_state.task_pending_action
        a = action["action"]
        with st.chat_message("assistant"):
            if a == "add":
                st.markdown("**Add this task?**")
                st.markdown(f"**{action['title']}**")
                dest_keys = list(notion_tasks.DESTINATIONS.keys())
                default_index = (
                    dest_keys.index(action["destination"])
                    if action.get("destination") in dest_keys
                    else 0
                )
                chosen_dest = st.radio(
                    "Add to:",
                    dest_keys,
                    index=default_index,
                    format_func=dest_label,
                    key="task_add_destination",
                )
                action["destination"] = chosen_dest
                st.markdown(f"🕐 {fmt_date(action.get('due_date'))}")
                confirm_label = "✅ Add it"
            elif a == "complete":
                st.markdown("**Mark as done?**")
                st.markdown(f"**{action['matched_task_title']}**")
                st.markdown(f"📁 {dest_label(action['dest'])}")
                confirm_label = "✅ Mark done"
            elif a == "reschedule":
                st.markdown("**Reschedule this task?**")
                st.markdown(f"**{action['matched_task_title']}**")
                st.markdown(f"📁 {dest_label(action['dest'])}")
                st.markdown(f"🕐 → {action['due_date']}")
                confirm_label = "✅ Reschedule"
            elif a == "rename":
                st.markdown("**Rename this task?**")
                st.markdown(f"**{action['matched_task_title']}** → **{action['new_title']}**")
                st.markdown(f"📁 {dest_label(action['dest'])}")
                confirm_label = "✅ Rename"
            else:
                confirm_label = "✅ Confirm"

            if action.get("note"):
                st.caption(f"Note: {action['note']}")

            btn_confirm, btn_cancel, _ = st.columns([1, 1, 3])
            if btn_confirm.button(confirm_label, key="task_confirm"):
                run_action(action)
            if btn_cancel.button("✗ Cancel", key="task_cancel"):
                st.session_state.task_pending_action = None
                push_assistant("Cancelled. What else?")
                st.rerun()

    user_input = st.chat_input(
        "e.g. 'add call the accountant' or 'mark call the accountant as done'", key="task_input"
    )

    if user_input:
        st.session_state.task_messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.spinner("Thinking..."):
            try:
                open_tasks = notion_tasks.list_open_tasks()
                parsed = nlp.parse_task_command(user_input, open_tasks)
            except Exception as e:
                push_assistant(f"Sorry, I couldn't parse that: {e}")
                st.rerun()

        if parsed["action"] == "clarify":
            push_assistant(parsed.get("reply") or "Could you clarify which task you mean?")
            st.rerun()

        if parsed["action"] in ("complete", "reschedule", "rename") and parsed.get("target_page_id"):
            matched = next((t for t in open_tasks if t["page_id"] == parsed["target_page_id"]), None)
            parsed["dest"] = matched["dest"] if matched else "personal"

        st.session_state.task_pending_action = parsed
        st.rerun()
