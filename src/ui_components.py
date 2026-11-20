"""Reusable Streamlit UI pieces.

Decorative HTML (banner, role/scope badge, synthetic-data notice, KPI and
callout cards) is rendered with ``st.iframe`` using the Tailwind CSS CDN plus an
inline CSS fallback, so it still looks right if the CDN is unreachable. Every
dynamic string is passed through ``html.escape``. Interactive widgets, tables,
downloads and charts stay native Streamlit components.
"""

from __future__ import annotations

import html
import math
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd
import streamlit as st

from src import auth, config

TAILWIND_CDN = "https://cdn.tailwindcss.com"

_FALLBACK_CSS = f"""
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{background:transparent;color:{config.THEME['text']};
  font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;font-size:14px;line-height:1.45}}
.dpa-banner{{background:linear-gradient(120deg,#0F172A 0%,#1E293B 60%,#0c4a6e 100%);
  border:1px solid #334155;border-radius:14px;padding:18px 22px}}
.dpa-eyebrow{{color:{config.THEME['primary']};font-size:11px;letter-spacing:.12em;text-transform:uppercase;font-weight:600}}
.dpa-title{{font-size:24px;font-weight:700;color:#F8FAFC;margin-top:4px}}
.dpa-sub{{color:#CBD5E1;margin-top:4px}}
.dpa-row{{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}}
.dpa-chip{{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:4px 12px;font-size:12px;font-weight:600;
  border:1px solid #38BDF8;color:#E0F2FE;background:rgba(56,189,248,.12)}}
.dpa-chip-muted{{border-color:#475569;color:#CBD5E1;background:rgba(148,163,184,.10)}}
.dpa-notice{{margin-top:12px;border-left:3px solid #fab219;background:rgba(250,178,25,.08);color:#FDE68A;
  padding:8px 12px;border-radius:6px;font-size:12.5px}}
.dpa-grid{{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(170px,1fr))}}
.dpa-card{{background:#1E293B;border:1px solid #334155;border-radius:12px;padding:14px 16px}}
.dpa-card-label{{color:#94A3B8;font-size:12px;font-weight:600}}
.dpa-card-id{{color:#64748B;font-size:10.5px;letter-spacing:.06em}}
.dpa-card-value{{color:#F8FAFC;font-size:26px;font-weight:700;margin-top:6px}}
.dpa-card-na{{color:#94A3B8;font-size:16px;font-weight:600;margin-top:12px}}
.dpa-card-sub{{color:#94A3B8;font-size:11.5px;margin-top:4px}}
.dpa-delta{{display:inline-flex;align-items:center;gap:4px;margin-top:8px;font-size:12.5px;font-weight:700;
  border-radius:6px;padding:2px 8px;white-space:nowrap}}
.dpa-up{{color:#4ade80;background:rgba(12,163,12,.14)}}
.dpa-down{{color:#fca5a5;background:rgba(208,59,59,.16)}}
.dpa-flat{{color:#CBD5E1;background:rgba(148,163,184,.14)}}
.dpa-callout-hi{{border-left:4px solid #0ca30c}}
.dpa-callout-lo{{border-left:4px solid #d03b3b}}
"""


def _esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _document(body: str) -> str:
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<script src='{TAILWIND_CDN}'></script>"
        f"<style>{_FALLBACK_CSS}</style></head>"
        f"<body class='bg-transparent text-slate-50 antialiased'>{body}</body></html>"
    )


def render_html(body: str, height: int | str = "content") -> None:
    st.iframe(_document(body), height=height)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------
def is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value)) or value is pd.NA


def fmt_pct(value, digits: int = 1, missing: str = config.NOT_AVAILABLE) -> str:
    return missing if is_missing(value) else f"{float(value):.{digits}f}%"


def fmt_pp(value, digits: int = 1, missing: str = config.NOT_AVAILABLE) -> str:
    if is_missing(value):
        return missing
    v = float(value)
    return f"{v:+.{digits}f} pp"


def fmt_int(value) -> str:
    return config.NOT_AVAILABLE if is_missing(value) else f"{int(value):,}"


# ---------------------------------------------------------------------------
# Session / header
# ---------------------------------------------------------------------------
def require_user() -> auth.UserContext:
    user = auth.get_current_user(st.session_state)
    if user is None:
        st.error("Please sign in to view this page.")
        st.stop()
    return user


def sidebar_identity(user: auth.UserContext) -> None:
    st.sidebar.markdown(f"**{user.display_name}**  \n`{user.username}`")
    st.sidebar.info(user.badge_text, icon=":material/badge:")


def page_header(user: auth.UserContext, title: str, subtitle: str, dataset_mode: str | None = None) -> None:
    chips = [f"<span class='dpa-chip rounded-full'>&#9673; {_esc(user.badge_text)}</span>"]
    if dataset_mode:
        chips.append(f"<span class='dpa-chip dpa-chip-muted rounded-full'>Dataset: {_esc(dataset_mode)}</span>")
    chips.append(f"<span class='dpa-chip dpa-chip-muted rounded-full'>{_esc(config.DATA_VERSION)} · seed {config.DATA_SEED}</span>")
    body = f"""
    <div class='dpa-banner rounded-2xl shadow-lg'>
      <div class='dpa-eyebrow'>{_esc(config.APP_TITLE)} · {_esc(config.COLLEGE_CONTEXT)}</div>
      <div class='dpa-title tracking-tight'>{_esc(title)}</div>
      <div class='dpa-sub'>{_esc(subtitle)}</div>
      <div class='dpa-row'>{''.join(chips)}</div>
      <div class='dpa-notice' role='note'>&#9888; {_esc(config.SYNTHETIC_NOTICE)}</div>
    </div>"""
    render_html(body)
    # Native, screen-reader friendly copy of the scope badge
    st.caption(user.badge_text)


# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------
@dataclass
class KpiCard:
    label: str
    value: str
    kpi_id: str = ""
    sub: str = ""
    delta: float | None = None
    delta_note: str = ""

    @property
    def available(self) -> bool:
        return not self.value.startswith(config.NOT_AVAILABLE)


def _delta_html(delta: float | None, note: str) -> str:
    if delta is None or (isinstance(delta, float) and math.isnan(delta)):
        return f"<div class='dpa-delta dpa-flat'>&#8212; {_esc(note or 'No prior period')}</div>"
    if abs(delta) < 0.05:
        cls, icon = "dpa-flat", "&#9644;"
    elif delta > 0:
        cls, icon = "dpa-up", "&#9650;"
    else:
        cls, icon = "dpa-down", "&#9660;"
    return (f"<div class='dpa-delta {cls}'>{icon}&nbsp;{_esc(fmt_pp(delta))}</div>"
            f"<div class='dpa-card-sub'>{_esc(note)}</div>")


def kpi_cards(cards: Sequence[KpiCard]) -> None:
    items = []
    for c in cards:
        value_html = (
            f"<div class='dpa-card-value'>{_esc(c.value)}</div>" if c.available
            else f"<div class='dpa-card-na'>{_esc(c.value)}</div>"
        )
        delta_html = _delta_html(c.delta, c.delta_note) if (c.delta is not None or c.delta_note) else ""
        items.append(
            "<div class='dpa-card rounded-xl'>"
            f"<div class='dpa-card-id'>{_esc(c.kpi_id)}</div>"
            f"<div class='dpa-card-label'>{_esc(c.label)}</div>{value_html}"
            f"<div class='dpa-card-sub'>{_esc(c.sub)}</div>{delta_html}</div>"
        )
    render_html(f"<div class='dpa-grid'>{''.join(items)}</div>")


def kpi_cards_from_values(kpis: dict, deltas: dict | None = None, keys: Sequence[str] = config.KPI_KEYS,
                          na_text: str = config.NOT_AVAILABLE) -> list[KpiCard]:
    cards = []
    for key in keys:
        d = (deltas or {}).get(key) or {}
        note = ""
        if deltas:
            note = (f"{deltas.get('current_label')} vs {deltas.get('prior_label')}"
                    if deltas.get("prior_label") else "No prior period")
        cards.append(KpiCard(
            label=config.KPI_LABELS[key], kpi_id=config.KPI_IDS[key],
            value=fmt_pct(kpis.get(key), missing=na_text),
            sub="Weighted ratio of sums",
            delta=d.get("pp") if deltas else None, delta_note=note if deltas else "",
        ))
    return cards


def extremes_callouts(kpi_label: str, extremes: dict, group_label: str) -> None:
    if not extremes.get("highest"):
        render_html(f"<div class='dpa-card'><div class='dpa-card-na'>{_esc(kpi_label)}: "
                    f"{_esc(config.NOT_AVAILABLE_IN_DATASET)}</div></div>")
        return
    hi_names = ", ".join(extremes["highest"])
    lo_names = ", ".join(extremes["lowest"])
    tie_hi = " (tie)" if len(extremes["highest"]) > 1 else ""
    tie_lo = " (tie)" if len(extremes["lowest"]) > 1 else ""
    spread = extremes["highest_value"] - extremes["lowest_value"]
    body = f"""
    <div class='dpa-grid'>
      <div class='dpa-card dpa-callout-hi rounded-xl'>
        <div class='dpa-card-id'>KPI-06 · HIGHEST {_esc(group_label.upper())}{_esc(tie_hi.upper())}</div>
        <div class='dpa-card-label'>&#9650; {_esc(kpi_label)}</div>
        <div class='dpa-card-value'>{_esc(hi_names)}</div>
        <div class='dpa-card-sub'>{_esc(fmt_pct(extremes['highest_value']))}</div>
      </div>
      <div class='dpa-card dpa-callout-lo rounded-xl'>
        <div class='dpa-card-id'>KPI-06 · LOWEST {_esc(group_label.upper())}{_esc(tie_lo.upper())}</div>
        <div class='dpa-card-label'>&#9660; {_esc(kpi_label)}</div>
        <div class='dpa-card-value'>{_esc(lo_names)}</div>
        <div class='dpa-card-sub'>{_esc(fmt_pct(extremes['lowest_value']))}</div>
      </div>
      <div class='dpa-card rounded-xl'>
        <div class='dpa-card-id'>SPREAD</div>
        <div class='dpa-card-label'>Highest − lowest</div>
        <div class='dpa-card-value'>{spread:.1f} pp</div>
        <div class='dpa-card-sub'>Percentage points</div>
      </div>
    </div>"""
    render_html(body)


# ---------------------------------------------------------------------------
# Tables & downloads
# ---------------------------------------------------------------------------
def pct_column(label: str, help_text: str | None = None):
    return st.column_config.NumberColumn(label, format="%.1f%%", help=help_text)


def pp_column(label: str, help_text: str | None = None):
    return st.column_config.NumberColumn(label, format="%+.1f pp", help=help_text)


def kpi_table_config(group_cols: dict[str, str]) -> dict:
    cfg = {col: st.column_config.TextColumn(label) for col, label in group_cols.items()}
    cfg.update({
        "records": st.column_config.NumberColumn("Records", format="%d"),
        "course_seat_enrolments": st.column_config.NumberColumn(config.ENROLMENT_LABEL, format="%d",
                                                                help=config.ENROLMENT_CAUTION),
    })
    for key in config.KPI_KEYS:
        cfg[key] = pct_column(config.KPI_LABELS[key], config.KPI_FORMULAS[key])
    return cfg


def show_kpi_table(table: pd.DataFrame, group_cols: dict[str, str], extra: Sequence[str] = ()) -> None:
    """KPI table where unavailable rates read 'Not available' (display only; data stays NULL)."""
    cols = [*group_cols, "records", "course_seat_enrolments", *extra, *config.KPI_KEYS]
    view = table[[c for c in cols if c in table]].copy()
    cfg = kpi_table_config(group_cols)
    for key in config.KPI_KEYS:
        if key in view and view[key].isna().any():
            view[key] = view[key].map(lambda v: fmt_pct(v))
            cfg[key] = st.column_config.TextColumn(config.KPI_LABELS[key], help=config.KPI_FORMULAS[key])
    st.dataframe(view, hide_index=True, width="stretch", column_config=cfg)


def na_text_frame(df: pd.DataFrame, columns: Sequence[str], text: str = config.NOT_AVAILABLE) -> pd.DataFrame:
    """Display copy where missing rates read 'Not available' (display only — data stays NULL)."""
    out = df.copy()
    for c in columns:
        out[c] = out[c].map(lambda v: text if is_missing(v) else round(float(v), 1))
    return out


def csv_download(df: pd.DataFrame, filename: str, label: str = "Download scoped data (CSV)", key: str | None = None) -> None:
    st.download_button(label, data=df.to_csv(index=False).encode("utf-8"), file_name=filename,
                       mime="text/csv", icon=":material/download:", key=key)


def formula_expander(keys: Sequence[str] = config.KPI_KEYS) -> None:
    with st.expander("KPI formulas used on this page"):
        for key in keys:
            st.markdown(f"**{config.KPI_IDS[key]} {config.KPI_LABELS[key]}** — `{config.KPI_FORMULAS[key]}`")
        st.caption("NULL inputs are excluded from that metric's numerator and denominator only; "
                   "they are never treated as 0. Period changes are in percentage points (pp).")


def empty_state(message: str = "No records match the current filters.") -> None:
    st.warning(message + " Adjust the sidebar filters.", icon=":material/filter_alt_off:")


# ---------------------------------------------------------------------------
# Login screen
# ---------------------------------------------------------------------------
def render_login_page() -> None:
    body = f"""
    <div class='dpa-banner rounded-2xl'>
      <div class='dpa-eyebrow'>{_esc(config.COLLEGE_CONTEXT)} · Academic analytics prototype</div>
      <div class='dpa-title'>{_esc(config.APP_TITLE)}</div>
      <div class='dpa-sub'>Sign in with your role. Department HODs see only their own department.</div>
      <div class='dpa-notice' role='note'>&#9888; {_esc(config.SYNTHETIC_NOTICE)}</div>
    </div>"""
    render_html(body)

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader("Sign in")
        role_label = st.radio("Role", list(config.ROLE_LOGIN_LABELS), horizontal=True, key="login_role")
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password")
            department = None
            if config.ROLE_LOGIN_LABELS[role_label] == config.ROLE_HOD:
                department = st.selectbox("Department", list(config.PROGRAMME_NAMES.values()), key="login_department")
            submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
        if submitted:
            result = auth.authenticate(username, password, role_label, department)
            if result.ok and result.user is not None:
                auth.login(st.session_state, result.user)
                st.rerun()
            else:
                st.error(result.error or auth.GENERIC_LOGIN_ERROR, icon=":material/lock:")
    with right:
        st.subheader("Access model")
        st.markdown(
            "- **Dean of Academics** — all 4 programmes, cross-programme comparison.\n"
            "- **Department HOD** — one bound programme only; queries are locked with "
            "`WHERE programme_code = ?` and comparisons run across that department's courses."
        )
        with st.expander("Prototype Demo Accounts"):
            hints = auth.load_demo_account_hints()
            if hints:
                st.dataframe(pd.DataFrame(hints), hide_index=True, width="stretch")
                st.caption("Demo credentials for academic reviewers only (from .streamlit/secrets.toml.example). "
                           "Passwords are verified against SHA-256 hashes; change them before any real deployment.")
            else:
                st.info("Demo account list unavailable.")
