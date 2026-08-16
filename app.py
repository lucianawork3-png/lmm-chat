from __future__ import annotations

from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

st.set_page_config(page_title="LMM", page_icon="📅", layout="centered")


# ── Mode picker ──────────────────────────────────────────────────────────────

if "mode" not in st.session_state:
    st.session_state.mode = None


def show_picker():
    st.title("LMM")
    st.caption("What do you want to do?")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📅  Calendar", use_container_width=True):
            st.session_state.mode = "calendar"
            st.rerun()
        st.caption("Add events by chatting")
    with col2:
        if st.button("✅  Tasks", use_container_width=True):
            st.session_state.mode = "tasks"
            st.rerun()
        st.caption("Add or edit tasks in Notion")


if st.session_state.mode is None:
    show_picker()
    st.stop()

if st.button("‹ Back"):
    st.session_state.mode = None
    st.rerun()

if st.session_state.mode == "calendar":
    import calendar_view
    calendar_view.render()
else:
    import tasks_view
    tasks_view.render()
