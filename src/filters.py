"""Global sidebar filters with hard role-scope enforcement.

The programme scope is never taken from a widget for an HOD: it is derived from
the authenticated user's bound programme_code, and every DataFrame leaving this
module is re-checked against that scope.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st

from src import cleaning, config, data_loader

ALL_PROGRAMMES_LABEL = "All Programmes"

KEY_MODE = "flt_dataset_mode"
KEY_PROGRAMME = "flt_programme"
KEY_PERIODS = "flt_periods"
KEY_CATEGORIES = "flt_categories"
KEY_ASSESSMENT = "flt_assessment_types"


class ScopeViolationError(PermissionError):
    """Raised if data outside the user's bound scope ever reaches the UI layer."""


@dataclass(frozen=True)
class FilterState:
    programme_codes: tuple[str, ...]
    period_labels: tuple[str, ...]
    categories: tuple[str, ...]
    assessment_types: tuple[str, ...]
    dataset_mode: str

    @property
    def period_sequences(self) -> tuple[int, ...]:
        return tuple(config.PERIOD_LABELS.index(p) + 1 for p in self.period_labels if p in config.PERIOD_LABELS)

    @property
    def scope_slug(self) -> str:
        return "ALL" if len(self.programme_codes) == len(config.PROGRAMME_CODES) else "-".join(self.programme_codes)


# ---------------------------------------------------------------------------
# Pure scope logic (unit-testable)
# ---------------------------------------------------------------------------
def resolve_programme_scope(user, requested: str | None) -> tuple[str, ...]:
    """HOD: always the bound programme, whatever was requested. Dean: requested programme or all."""
    if user.is_hod:
        return (user.programme_code,)
    if requested in (None, "", ALL_PROGRAMMES_LABEL, config.ALL_SCOPE):
        return config.PROGRAMME_CODES
    code = config.PROGRAMME_CODE_BY_NAME.get(requested) or (requested if requested in config.PROGRAMME_CODES else None)
    return (code,) if code else config.PROGRAMME_CODES


def programme_options(user) -> list[str]:
    if user.is_hod:
        return [config.PROGRAMME_NAMES[user.programme_code]]
    return [ALL_PROGRAMMES_LABEL, *config.PROGRAMME_NAMES.values()]


def filters_from_state(user, state: Mapping[str, Any]) -> FilterState:
    mode = state.get(KEY_MODE, config.MODE_CLEANED)
    if mode not in config.DATASET_MODES:
        mode = config.MODE_CLEANED
    periods = tuple(p for p in state.get(KEY_PERIODS, config.PERIOD_LABELS) if p in config.PERIOD_LABELS)
    cats = tuple(c for c in state.get(KEY_CATEGORIES, config.COURSE_CATEGORIES) if c in config.COURSE_CATEGORIES)
    types = tuple(t for t in state.get(KEY_ASSESSMENT, config.ASSESSMENT_TYPES) if t in config.ASSESSMENT_TYPES)
    return FilterState(
        programme_codes=resolve_programme_scope(user, state.get(KEY_PROGRAMME)),
        period_labels=periods,
        categories=cats,
        assessment_types=types,
        dataset_mode=mode,
    )


def apply_filters(df: pd.DataFrame, f: FilterState, *, apply_periods: bool = True) -> pd.DataFrame:
    """Apply dataset mode, then programme/period/category/assessment filters (pure)."""
    out = cleaning.apply_dataset_mode(df, f.dataset_mode)
    mask = out["programme_code"].isin(f.programme_codes)
    mask &= out["course_category"].isin(f.categories)
    mask &= out["assessment_type"].isin(f.assessment_types)
    if apply_periods:
        mask &= out["period_label"].isin(f.period_labels)
    return out.loc[mask].copy()


def enforce_scope(user, df: pd.DataFrame) -> pd.DataFrame:
    if len(df) and not set(df["programme_code"].unique()) <= set(user.allowed_programme_codes):
        raise ScopeViolationError("Data outside the signed-in user's programme scope was blocked.")
    return df


# ---------------------------------------------------------------------------
# Streamlit wiring
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _cached_performance(programme_codes: tuple[str, ...]) -> pd.DataFrame:
    return data_loader.load_performance(programme_codes)


@st.cache_data(show_spinner=False)
def _cached_quality(programme_codes: tuple[str, ...]) -> pd.DataFrame:
    return data_loader.load_quality_issues(programme_codes)


def scoped_raw_data(user, f: FilterState | None = None) -> pd.DataFrame:
    """Raw view rows for the user's scope (Dean: chosen programme(s); HOD: bound programme only)."""
    codes = f.programme_codes if f is not None else user.allowed_programme_codes
    if user.is_hod:
        codes = (user.programme_code,)  # SQL is executed as WHERE programme_code = ?
    return enforce_scope(user, _cached_performance(tuple(codes)).copy())


def get_filtered_data(user, f: FilterState, *, apply_periods: bool = True) -> pd.DataFrame:
    return enforce_scope(user, apply_filters(scoped_raw_data(user, f), f, apply_periods=apply_periods))


def scoped_quality_issues(user, f: FilterState) -> pd.DataFrame:
    codes = (user.programme_code,) if user.is_hod else f.programme_codes
    dq = _cached_quality(tuple(codes)).copy()
    in_scope = dq["programme_code"].isna() | dq["programme_code"].isin(user.allowed_programme_codes)
    return dq.loc[in_scope].copy()


def render_sidebar_filters(user) -> FilterState:
    """Draw the global filters in the sidebar (called once from app.py)."""
    sb = st.sidebar
    sb.markdown("### Filters")
    sb.radio(
        "Dataset Mode",
        options=list(config.DATASET_MODES),
        key=KEY_MODE,
        help="Cleaned removes 3 duplicate course-period rows (keeps the lowest performance_id). "
             "Raw shows the unfiltered extract so you can see the impact.",
    )
    if user.is_dean:
        sb.selectbox("Programme", programme_options(user), key=KEY_PROGRAMME)
    else:
        # Not a widget the HOD can change: scope is bound at login
        st.session_state.pop(KEY_PROGRAMME, None)
        sb.text_input("Programme (locked to your department)", value=config.PROGRAMME_NAMES[user.programme_code],
                      disabled=True)
    if KEY_PERIODS not in st.session_state:
        st.session_state[KEY_PERIODS] = list(config.PERIOD_LABELS)
    if KEY_CATEGORIES not in st.session_state:
        st.session_state[KEY_CATEGORIES] = list(config.COURSE_CATEGORIES)
    if KEY_ASSESSMENT not in st.session_state:
        st.session_state[KEY_ASSESSMENT] = list(config.ASSESSMENT_TYPES)
    sb.multiselect("Academic periods", list(config.PERIOD_LABELS), key=KEY_PERIODS)
    sb.multiselect("Course categories", list(config.COURSE_CATEGORIES), key=KEY_CATEGORIES)
    sb.multiselect("Assessment types", list(config.ASSESSMENT_TYPES), key=KEY_ASSESSMENT)
    return current_filters(user)


def current_filters(user) -> FilterState:
    return filters_from_state(user, st.session_state)
