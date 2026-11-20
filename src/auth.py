"""Role-based authentication and scope binding.

Passwords are never stored in Python source. User records (SHA-256 hashes,
role and bound programme) are read from ``st.secrets["users"]``; when no
``.streamlit/secrets.toml`` exists (tests, fresh clones) the documented
``.streamlit/secrets.toml.example`` file is used as a read-only fallback.
"""

from __future__ import annotations

import hashlib
import hmac
import tomllib
from collections.abc import Mapping, MutableMapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src import config

SESSION_USER_KEY = "auth_user"


@dataclass(frozen=True)
class UserContext:
    """The authenticated user and the data scope they are bound to."""

    username: str
    role: str  # "Dean" | "HOD"
    programme_code: str  # "ALL" for Dean, otherwise one of PROGRAMME_CODES
    display_name: str

    @property
    def is_dean(self) -> bool:
        return self.role == config.ROLE_DEAN

    @property
    def is_hod(self) -> bool:
        return self.role == config.ROLE_HOD

    @property
    def allowed_programme_codes(self) -> tuple[str, ...]:
        if self.is_dean:
            return config.PROGRAMME_CODES
        return (self.programme_code,)

    @property
    def programme_name(self) -> str:
        return "All Programmes" if self.is_dean else config.PROGRAMME_NAMES[self.programme_code]

    @property
    def role_label(self) -> str:
        if self.is_dean:
            return "Dean of Academics"
        return f"HOD — {self.programme_name}"

    @property
    def scope_label(self) -> str:
        if self.is_dean:
            return f"All {len(config.PROGRAMME_CODES)} Programmes"
        return f"Restricted to {self.programme_name}"

    @property
    def badge_text(self) -> str:
        return f"Role: {self.role_label} | Scope: {self.scope_label}"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "UserContext":
        return cls(
            username=str(data["username"]),
            role=str(data["role"]),
            programme_code=str(data["programme_code"]),
            display_name=str(data.get("display_name", data["username"])),
        )


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    user: UserContext | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Credential storage
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Return the lowercase hex SHA-256 digest of ``password`` (UTF-8)."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _load_example_file(path: Path = config.SECRETS_EXAMPLE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _normalise_users(raw: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    users: dict[str, dict[str, str]] = {}
    for username, rec in raw.items():
        rec = dict(rec)
        role = str(rec.get("role", ""))
        code = str(rec.get("programme_code", "")).upper()
        digest = str(rec.get("password_sha256", "")).lower()
        if role not in (config.ROLE_DEAN, config.ROLE_HOD) or len(digest) != 64:
            continue
        if role == config.ROLE_DEAN and code != config.ALL_SCOPE:
            continue
        if role == config.ROLE_HOD and code not in config.PROGRAMME_CODES:
            continue
        users[str(username)] = {
            "password_sha256": digest,
            "role": role,
            "programme_code": code,
            "display_name": str(rec.get("display_name", username)),
        }
    return users


def load_users(secrets: Mapping[str, Any] | None = None) -> dict[str, dict[str, str]]:
    """Load user records from Streamlit secrets, falling back to the documented example file."""
    if secrets is None:
        try:
            import streamlit as st

            secrets = st.secrets
            raw = secrets["users"] if "users" in secrets else None
        except Exception:  # no secrets.toml present, or outside a Streamlit runtime
            raw = None
    else:
        raw = secrets.get("users")
    if not raw:
        raw = _load_example_file().get("users", {})
    return _normalise_users(raw)


def load_demo_account_hints() -> list[dict[str, str]]:
    """Demo usernames/passwords for reviewers, read from the TOML example (never from Python)."""
    data = _load_example_file()
    hints = data.get("demo_accounts", {})
    users = _normalise_users(data.get("users", {}))
    rows = []
    for username, password in hints.items():
        rec = users.get(username)
        if rec is None:
            continue
        rows.append({
            "Username": username,
            "Demo password": str(password),
            "Login as": "Dean of Academics" if rec["role"] == config.ROLE_DEAN else "Department HOD",
            "Department": "All" if rec["programme_code"] == config.ALL_SCOPE
            else config.PROGRAMME_NAMES[rec["programme_code"]],
        })
    return rows


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
GENERIC_LOGIN_ERROR = "Invalid username or password."


def authenticate(
    username: str,
    password: str,
    role_label: str,
    department_name: str | None = None,
    users: Mapping[str, Mapping[str, str]] | None = None,
) -> AuthResult:
    """Verify credentials, selected role and (for HODs) the selected department binding."""
    users = load_users() if users is None else users
    username = (username or "").strip()
    if not username or not password:
        return AuthResult(False, error="Enter both username and password.")

    rec = users.get(username)
    # Always compute a digest so timing does not reveal whether the username exists
    supplied = hash_password(password)
    expected = rec["password_sha256"] if rec else "0" * 64
    if rec is None or not hmac.compare_digest(supplied, expected):
        return AuthResult(False, error=GENERIC_LOGIN_ERROR)

    selected_role = config.ROLE_LOGIN_LABELS.get(role_label)
    if selected_role is None:
        return AuthResult(False, error="Select a valid role.")
    if selected_role != rec["role"]:
        return AuthResult(
            False,
            error=f"Role mismatch: '{username}' is not registered as {role_label}.",
        )

    if selected_role == config.ROLE_HOD:
        selected_code = config.PROGRAMME_CODE_BY_NAME.get(department_name or "")
        if selected_code is None:
            return AuthResult(False, error="Select your department.")
        if selected_code != rec["programme_code"]:
            return AuthResult(
                False,
                error=(
                    f"Department mismatch: '{username}' is not the HOD account for {department_name}. "
                    "HOD accounts can only sign in to their bound department."
                ),
            )

    user = UserContext(
        username=username,
        role=rec["role"],
        programme_code=rec["programme_code"],
        display_name=rec["display_name"],
    )
    return AuthResult(True, user=user)


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------
def login(session_state: MutableMapping[str, Any], user: UserContext) -> None:
    session_state[SESSION_USER_KEY] = user.to_dict()


def logout(session_state: MutableMapping[str, Any]) -> None:
    """Remove every key from session state (credentials, filters, cached choices)."""
    session_state.clear()


def get_current_user(session_state: Mapping[str, Any]) -> UserContext | None:
    data = session_state.get(SESSION_USER_KEY)
    if not data:
        return None
    try:
        user = UserContext.from_dict(data)
    except (KeyError, TypeError):
        return None
    # Defensive re-validation of the scope binding stored in session
    if user.is_dean and user.programme_code != config.ALL_SCOPE:
        return None
    if user.is_hod and user.programme_code not in config.PROGRAMME_CODES:
        return None
    if user.role not in (config.ROLE_DEAN, config.ROLE_HOD):
        return None
    return user
