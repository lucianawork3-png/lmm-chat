from __future__ import annotations

import hmac
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

st.set_page_config(page_title="LMM", page_icon="📅", layout="centered")


# ── Secrets / auth ──────────────────────────────────────────────────────────────

def _get_secret(key: str) -> str:
    val = os.environ.get(key, "")
    if val:
        return val
    try:
        return st.secrets.get(key, "")
    except Exception:
        return ""


def check_password(input_pw: str) -> bool:
    access_pw = _get_secret("APP_PASSWORD")
    if not access_pw:
        return False
    return hmac.compare_digest(input_pw.encode("utf-8"), access_pw.encode("utf-8"))


def show_login():
    st.title("LMM")
    st.caption("Password-protected — add events or tasks by chatting in plain language.")
    pw = st.text_input("Password", type="password", key="login_pw")
    if st.button("Unlock"):
        if check_password(pw):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password.")


if _get_secret("LOCAL_DEV") == "true":
    st.session_state.authenticated = True

if not st.session_state.get("authenticated", False):
    show_login()
    st.stop()


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
