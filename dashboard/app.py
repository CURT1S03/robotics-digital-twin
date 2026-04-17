"""Robotics Digital Twin — Streamlit Dashboard.

Multi-page app with:
  • Experiments  — create, list and launch experiments
  • Live Monitor — real-time trajectory and metric view
  • Comparison   — side-by-side algorithm comparison

Run with:
    streamlit run dashboard/app.py
"""

import streamlit as st

st.set_page_config(
    page_title="Robotics Digital Twin",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar navigation ────────────────────────────────────────────────────── #
st.sidebar.title("🤖 Digital Twin")
st.sidebar.caption("Go2 Navigation Validation Platform")
st.sidebar.divider()

page = st.sidebar.radio(
    "Navigate",
    ["Experiments", "Live Monitor", "Comparison"],
    index=0,
)

st.sidebar.divider()
st.sidebar.caption("**Backend:** http://localhost:8000")
st.sidebar.caption("**Docs:** http://localhost:8000/docs")

# ── Route to page ─────────────────────────────────────────────────────────── #
if page == "Experiments":
    from pages.experiments import render
    render()

elif page == "Live Monitor":
    from pages.live_monitor import render
    render()

elif page == "Comparison":
    from pages.comparison import render
    render()
