"""End-to-end UI tests with streamlit.testing.v1.AppTest."""

import sys
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import auth, config, filters  # noqa: E402

APP = str(ROOT / "app.py")
PAGES = [
    "pages/01_Overview.py",
    "pages/02_Programme_Comparison.py",
    "pages/03_Attendance_Analysis.py",
    "pages/04_Results_Analysis.py",
    "pages/05_Project_Practical_Analysis.py",
    "pages/06_Data_Quality.py",
    "pages/07_Statistics_EDA.py",
]
DEMO = {h["Username"]: h["Demo password"] for h in auth.load_demo_account_hints()}
DEAN = {"username": "dean_academics", "role": "Dean", "programme_code": "ALL", "display_name": "Dean of Academics"}
HOD_MCA = {"username": "hod_mca", "role": "HOD", "programme_code": "MCA", "display_name": "HOD, MCA"}
MCA_COURSE_PREFIX = "MC-"


def new_app() -> AppTest:
    return AppTest.from_file(APP, default_timeout=90)


def logged_in(user: dict) -> AppTest:
    at = new_app()
    at.session_state[auth.SESSION_USER_KEY] = user
    at.run()
    assert not at.exception
    return at


def all_text(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption] + [s.value for s in at.subheader]
    parts += [i.value for i in at.info] + [e.value for e in at.error]
    return "\n".join(str(p) for p in parts)


def all_frames(at: AppTest) -> list[pd.DataFrame]:
    return [d.value for d in at.dataframe if isinstance(d.value, pd.DataFrame)]


# ---------------------------------------------------------------------------
# Login gate
# ---------------------------------------------------------------------------
def test_login_gate_renders_when_unauthenticated():
    at = new_app()
    at.run()
    assert not at.exception
    assert [r.label for r in at.radio] == ["Role"]
    labels = [t.label for t in at.text_input]
    assert "Username" in labels and "Password" in labels
    # The only table on the login screen is the demo-account helper — no analytical data exposed
    for df in all_frames(at):
        assert not set(df.columns) & set(config.EXPECTED_VIEW_COLUMNS)
        assert "Username" in df.columns
    assert "Overview" not in [s.value for s in at.subheader]
    assert auth.SESSION_USER_KEY not in at.session_state


def _submit(at: AppTest, username: str, password: str, role: str, dept: str | None = None) -> AppTest:
    at.radio(key="login_role").set_value(role).run()
    at.text_input(key="login_username").set_value(username)
    pwd = next(t for t in at.text_input if t.label == "Password")
    pwd.set_value(password)
    if dept:
        at.selectbox(key="login_department").set_value(dept)
    at.button[0].click().run()
    return at


def test_dean_login_via_form():
    at = new_app()
    at.run()
    _submit(at, "dean_academics", DEMO["dean_academics"], "Dean of Academics")
    assert not at.exception
    user = auth.get_current_user(at.session_state)
    assert user is not None and user.is_dean


def test_hod_login_via_form_and_mismatch_rejected():
    at = new_app()
    at.run()
    _submit(at, "hod_mca", DEMO["hod_mca"], "Department HOD", "BCA")
    assert auth.get_current_user(at.session_state) is None
    assert any("Department mismatch" in e.value for e in at.error)

    _submit(at, "hod_mca", DEMO["hod_mca"], "Department HOD", "MCA")
    user = auth.get_current_user(at.session_state)
    assert user is not None and user.programme_code == "MCA"


def test_wrong_password_rejected():
    at = new_app()
    at.run()
    _submit(at, "dean_academics", "not-the-password", "Dean of Academics")
    assert auth.get_current_user(at.session_state) is None
    assert any(auth.GENERIC_LOGIN_ERROR in e.value for e in at.error)


# ---------------------------------------------------------------------------
# Dean session
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("page", PAGES)
def test_dean_loads_every_page(page):
    at = logged_in(DEAN)
    at.switch_page(page).run()
    assert not at.exception, [e.value for e in at.exception]
    assert "Role: Dean of Academics | Scope: All 4 Programmes" in all_text(at)


def test_dean_overview_covers_all_programmes():
    at = logged_in(DEAN)
    frames = all_frames(at)
    summary = next(df for df in frames if "programme_name" in df.columns)
    assert summary["programme_name"].tolist() == ["B.Tech", "MCA", "BCA", "MBA"]


def test_dean_comparison_page_is_cross_programme():
    at = logged_in(DEAN)
    at.switch_page(PAGES[1]).run()
    assert not at.exception
    assert "All KPIs by programme" in [s.value for s in at.subheader]
    names = set()
    for df in all_frames(at):
        if "programme_name" in df.columns:
            names |= set(df["programme_name"])
    assert names == {"B.Tech", "MCA", "BCA", "MBA"}


def test_dean_single_programme_filter():
    at = logged_in(DEAN)
    at.selectbox(key=filters.KEY_PROGRAMME).set_value("BCA").run()
    frames = [df for df in all_frames(at) if "programme_name" in df.columns]
    assert frames and all(set(df["programme_name"]) == {"BCA"} for df in frames)


def test_dataset_mode_toggle_changes_row_counts():
    at = logged_in(DEAN)
    at.switch_page(PAGES[0]).run()
    summary = next(df for df in all_frames(at) if "records" in df.columns)
    cleaned_total = int(summary["records"].sum())
    at.radio(key=filters.KEY_MODE).set_value(config.MODE_RAW).run()
    summary_raw = next(df for df in all_frames(at) if "records" in df.columns)
    assert cleaned_total == 192 and int(summary_raw["records"].sum()) == 195


# ---------------------------------------------------------------------------
# HOD session — strict isolation
# ---------------------------------------------------------------------------
DATASET_LEVEL = "Dataset-level"  # label for DQ-SCHEMA findings that belong to no programme


def _assert_mca_only(at: AppTest):
    for df in all_frames(at):
        if "programme_name" in df.columns:
            vals = set(df["programme_name"].dropna()) - {DATASET_LEVEL}
            assert vals <= {"MCA"}, vals
        if "programme_code" in df.columns:
            assert set(df["programme_code"].dropna()) <= {"MCA"}
        if "course_code" in df.columns:
            codes = df["course_code"].dropna().astype(str)
            codes = codes[codes != DATASET_LEVEL]
            assert codes.str.startswith(MCA_COURSE_PREFIX).all(), set(codes)


@pytest.mark.parametrize("page", PAGES)
def test_hod_pages_restricted_to_bound_department(page):
    at = logged_in(HOD_MCA)
    at.switch_page(page).run()
    assert not at.exception, [e.value for e in at.exception]
    assert "Role: HOD — MCA | Scope: Restricted to MCA" in all_text(at)
    _assert_mca_only(at)


def test_hod_has_no_programme_selector_and_tampering_is_ignored():
    at = logged_in(HOD_MCA)
    assert not any(sb.key == filters.KEY_PROGRAMME for sb in at.selectbox)
    locked = [t for t in at.text_input if t.label.startswith("Programme")]
    assert locked and locked[0].disabled and locked[0].value == "MCA"
    # Attempt to force another programme through session state
    at.session_state[filters.KEY_PROGRAMME] = "B.Tech"
    at.run()
    _assert_mca_only(at)
    at.switch_page(PAGES[1]).run()
    _assert_mca_only(at)


def test_hod_comparison_page_adapts_to_courses_and_categories():
    at = logged_in(HOD_MCA)
    at.switch_page(PAGES[1]).run()
    assert not at.exception
    assert "All KPIs by programme" not in [s.value for s in at.subheader]
    cats = set()
    for df in all_frames(at):
        if "course_category" in df.columns:
            cats |= set(df["course_category"])
    assert cats == {"Core", "Elective", "Practical", "Project"}
    _assert_mca_only(at)


def test_logout_clears_session():
    at = logged_in(HOD_MCA)
    at.button(key="logout_button").click().run()
    assert not at.exception
    assert auth.SESSION_USER_KEY not in at.session_state
    assert filters.KEY_MODE not in at.session_state
    assert [r.label for r in at.radio] == ["Role"]  # back on the login screen
