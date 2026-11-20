"""Authentication, role binding and HOD isolation."""

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import auth, config, data_loader, filters  # noqa: E402

DEMO = {h["Username"]: h["Demo password"] for h in auth.load_demo_account_hints()}


def test_demo_accounts_documented():
    assert set(DEMO) == {"dean_academics", "hod_btech", "hod_mca", "hod_bca", "hod_mba"}


def test_hash_password_is_sha256():
    assert auth.hash_password("abc") == hashlib.sha256(b"abc").hexdigest()


def test_users_store_hashes_only():
    users = auth.load_users(secrets={})  # forces documented fallback
    assert len(users) == 5
    for username, rec in users.items():
        assert len(rec["password_sha256"]) == 64
        assert DEMO[username] not in rec.values()
        assert auth.hash_password(DEMO[username]) == rec["password_sha256"]


def test_no_plaintext_passwords_in_python_sources():
    sources = [p.read_text(encoding="utf-8") for p in (ROOT / "src").glob("*.py")]
    sources += [p.read_text(encoding="utf-8") for p in (ROOT / "pages").glob("*.py")]
    sources.append((ROOT / "app.py").read_text(encoding="utf-8"))
    for pw in DEMO.values():
        assert not any(pw in s for s in sources), f"plain-text password found in Python: {pw}"


def test_secrets_mapping_takes_precedence():
    custom = {"users": {"alt_dean": {"password_sha256": auth.hash_password("x-pass"), "role": "Dean",
                                     "programme_code": "ALL"}}}
    users = auth.load_users(secrets=custom)
    assert list(users) == ["alt_dean"]
    assert auth.authenticate("alt_dean", "x-pass", "Dean of Academics", users=users).ok


def test_dean_login_unlocks_all_four_programmes():
    res = auth.authenticate("dean_academics", DEMO["dean_academics"], "Dean of Academics")
    assert res.ok and res.user.is_dean
    assert res.user.allowed_programme_codes == ("BTECH", "MCA", "BCA", "MBA")
    df = data_loader.load_performance_for_user(res.user)
    assert set(df["programme_code"]) == {"BTECH", "MCA", "BCA", "MBA"}
    assert len(df) == 195
    assert res.user.badge_text == "Role: Dean of Academics | Scope: All 4 Programmes"


def test_hod_mca_locked_strictly_to_mca():
    res = auth.authenticate("hod_mca", DEMO["hod_mca"], "Department HOD", "MCA")
    assert res.ok and res.user.is_hod
    user = res.user
    assert user.allowed_programme_codes == ("MCA",)
    assert user.badge_text == "Role: HOD — MCA | Scope: Restricted to MCA"
    df = data_loader.load_performance_for_user(user)
    assert len(df) > 0
    assert set(df["programme_code"]) == {"MCA"}
    assert (df["programme_code"] != "MCA").sum() == 0
    # Whatever programme is requested through the filter layer, scope stays MCA
    for requested in (None, "All Programmes", "B.Tech", "BCA", "MBA", "ALL", "BTECH"):
        assert filters.resolve_programme_scope(user, requested) == ("MCA",)
    state = {filters.KEY_PROGRAMME: "B.Tech"}
    f = filters.filters_from_state(user, state)
    assert f.programme_codes == ("MCA",)


@pytest.mark.parametrize("username,dept", [("hod_btech", "B.Tech"), ("hod_bca", "BCA"), ("hod_mba", "MBA")])
def test_each_hod_bound_to_own_programme(username, dept):
    res = auth.authenticate(username, DEMO[username], "Department HOD", dept)
    assert res.ok
    df = data_loader.load_performance_for_user(res.user)
    assert set(df["programme_name"]) == {dept}


@pytest.mark.parametrize("dept", ["B.Tech", "BCA", "MBA"])
def test_mismatched_department_rejected(dept):
    res = auth.authenticate("hod_mca", DEMO["hod_mca"], "Department HOD", dept)
    assert not res.ok and res.user is None
    assert "Department mismatch" in res.error


def test_role_mismatch_rejected():
    assert not auth.authenticate("hod_mca", DEMO["hod_mca"], "Dean of Academics").ok
    assert not auth.authenticate("dean_academics", DEMO["dean_academics"], "Department HOD", "MCA").ok


def test_bad_credentials_generic_error():
    for user, pw in (("hod_mca", "wrong"), ("nobody", "whatever")):
        res = auth.authenticate(user, pw, "Department HOD", "MCA")
        assert not res.ok and res.error == auth.GENERIC_LOGIN_ERROR
    assert not auth.authenticate("", "", "Dean of Academics").ok


def test_session_login_logout_and_tamper_guard():
    state = {}
    res = auth.authenticate("hod_bca", DEMO["hod_bca"], "Department HOD", "BCA")
    auth.login(state, res.user)
    state["flt_periods"] = ["2025-26 Sem 1"]
    assert auth.get_current_user(state) == res.user
    auth.logout(state)
    assert state == {}
    assert auth.get_current_user(state) is None
    # A tampered session (HOD claiming ALL) is not accepted
    assert auth.get_current_user({auth.SESSION_USER_KEY: {
        "username": "hod_bca", "role": "HOD", "programme_code": "ALL", "display_name": "x"}}) is None
    assert auth.get_current_user({auth.SESSION_USER_KEY: {
        "username": "x", "role": "Admin", "programme_code": "ALL", "display_name": "x"}}) is None


def test_enforce_scope_blocks_foreign_rows():
    res = auth.authenticate("hod_mca", DEMO["hod_mca"], "Department HOD", "MCA")
    foreign = data_loader.load_performance(["BTECH"])
    with pytest.raises(filters.ScopeViolationError):
        filters.enforce_scope(res.user, foreign)
    assert config.PROGRAMME_CODES == ("BTECH", "MCA", "BCA", "MBA")
