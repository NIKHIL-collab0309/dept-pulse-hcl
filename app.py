"""Department-wise Performance Analysis — Streamlit entry point.

Run:  streamlit run app.py
The login gate runs before st.navigation registers any analytical page.
"""

from __future__ import annotations

import streamlit as st

from src import auth, config, data_loader, filters, ui_components as ui

st.set_page_config(
    page_title=config.APP_TITLE,
    page_icon=":material/school:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Database presence check (never creates the database)
# ---------------------------------------------------------------------------
if not config.DB_PATH.exists():
    st.error(
        f"Database not found at `{config.DB_PATH.relative_to(config.REPO_ROOT)}`. "
        "Run `python src/generate_data.py` from the repository root, then reload.",
        icon=":material/database:",
    )
    st.stop()

user = auth.get_current_user(st.session_state)

# ---------------------------------------------------------------------------
# Unauthenticated: only the login page is registered (pages/ is never exposed)
# ---------------------------------------------------------------------------
PAGE_SPECS = [
    # (script, url_path, title, icon)
    ("pages/01_Overview.py", "overview", "Overview", ":material/dashboard:"),
    ("pages/02_Programme_Comparison.py", "comparison", None, ":material/compare_arrows:"),
    ("pages/03_Attendance_Analysis.py", "attendance", "Attendance Analysis", ":material/event_available:"),
    ("pages/04_Results_Analysis.py", "results", "Results Analysis", ":material/grading:"),
    ("pages/05_Project_Practical_Analysis.py", "project-practical", "Project & Practical Analysis",
     ":material/science:"),
    ("pages/06_Data_Quality.py", "data-quality", "Data Quality", ":material/fact_check:"),
    ("pages/07_Statistics_EDA.py", "statistics-eda", "Statistics & EDA", ":material/query_stats:"),
]

if user is None:
    # Every analytical URL resolves to the sign-in screen while signed out, so a
    # deep link or the rerun after Logout never reaches an analytical script.
    login_pages = [
        st.Page(ui.render_login_page, title="Sign in", icon=":material/login:", url_path=url_path, default=(i == 0))
        for i, (_, url_path, _, _) in enumerate(PAGE_SPECS)
    ]
    st.navigation(login_pages, position="hidden").run()
    st.stop()

# ---------------------------------------------------------------------------
# Authenticated: sidebar identity, logout, global filters, then navigation
# ---------------------------------------------------------------------------
ui.sidebar_identity(user)
if st.sidebar.button("Logout", icon=":material/logout:", width="stretch", key="logout_button",
                     on_click=auth.logout, args=(st.session_state,)):
    # on_click has already run st.session_state.clear() before this script pass
    auth.logout(st.session_state)
    st.rerun()

filters.render_sidebar_filters(user)
st.sidebar.caption(
    f"{config.DATA_VERSION} · {data_loader.table_counts()['performance_fact']} fact rows in database · synthetic"
)

comparison_title = "Programme Comparison" if user.is_dean else "Course & Category Comparison (My Department)"
pages = [
    st.Page(script, title=title or comparison_title, icon=icon, url_path=url_path, default=(i == 0))
    for i, (script, url_path, title, icon) in enumerate(PAGE_SPECS)
]
st.navigation({"Analysis": pages}, position="sidebar").run()
