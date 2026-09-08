"""Runtime "Neon" theme toggle shared by both Streamlit apps.

Streamlit has no first-class multi-theme switch, so this is a sidebar radio that
flips a ``st.session_state`` flag plus a one-shot ``st.markdown`` CSS injection
targeting Streamlit's stable ``data-testid`` DOM hooks. Charts are recoloured by
routing every figure dict through :func:`src.theme.apply_theme` (see
``themed_figure``), the same post-processor the FastAPI ``/api/charts`` route uses
for the React app.

Usage (near ``st.set_page_config`` in each app)::

    from src.streamlit_theme import theme_selector, themed_figure
    theme_selector()
    ...
    st.plotly_chart(themed_figure(charts.some_chart(...)), theme=None)
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src.theme import NEON, apply_theme

_STATE_KEY = "citimart_theme"

_NEON_CSS = """
<style>
:root { --neon-bg: #0e1220; --neon-panel: rgba(30,41,74,0.55); --neon-cyan: #22d3ee; --neon-text: #e2e8f0; }
[data-testid="stAppViewContainer"] {
  background-color: var(--neon-bg);
  background-image:
    radial-gradient(ellipse 80% 55% at 12% -5%, rgba(34,211,238,0.16), transparent 60%),
    radial-gradient(ellipse 70% 55% at 88% 10%, rgba(232,121,249,0.14), transparent 55%),
    radial-gradient(ellipse 95% 70% at 50% 108%, rgba(129,140,248,0.14), transparent 62%);
  background-attachment: fixed;
  color: var(--neon-text);
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] {
  background-color: rgba(20,26,45,0.75);
  backdrop-filter: blur(14px) saturate(1.4);
  border-right: 1px solid rgba(148,197,255,0.18);
}
[data-testid="stSidebar"] * , [data-testid="stAppViewContainer"] .stMarkdown, [data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] label, [data-testid="stAppViewContainer"] h1, [data-testid="stAppViewContainer"] h2,
[data-testid="stAppViewContainer"] h3, [data-testid="stAppViewContainer"] h4 { color: var(--neon-text); }
[data-testid="stAppViewContainer"] h1, [data-testid="stAppViewContainer"] h2, [data-testid="stAppViewContainer"] h3 {
  text-shadow: 0 0 18px rgba(34,211,238,0.22);
}
[data-testid="stMetric"] {
  background: var(--neon-panel);
  backdrop-filter: blur(14px) saturate(1.5);
  border: 1px solid rgba(148,197,255,0.18);
  border-radius: 14px;
  padding: 14px 16px;
  box-shadow: 0 8px 30px rgba(4,8,20,0.5), inset 0 1px 0 rgba(255,255,255,0.05);
}
[data-testid="stMetricValue"] { color: var(--neon-cyan); }
.stTabs [data-baseweb="tab-list"] { background: transparent; border-bottom: 1px solid rgba(148,197,255,0.18); }
.stTabs [data-baseweb="tab"] { color: rgba(226,232,240,0.65); }
.stTabs [aria-selected="true"] { color: var(--neon-cyan); }
[data-testid="stDataFrame"], [data-testid="stExpander"] details {
  background: var(--neon-panel);
  border: 1px solid rgba(148,197,255,0.18);
  border-radius: 12px;
}
.stButton > button, .stDownloadButton > button {
  background: rgba(34,211,238,0.12);
  border: 1px solid rgba(34,211,238,0.4);
  color: var(--neon-cyan);
}
.stButton > button:hover, .stDownloadButton > button:hover { background: rgba(34,211,238,0.22); }
</style>
"""


def theme_selector(*, sidebar: bool = True) -> str:
    """Render the Default / Neon picker and return the active theme.

    Persists the choice in ``st.session_state`` and injects the neon CSS on every
    rerun while Neon is active (Streamlit drops injected ``<style>`` between
    reruns, so this must run each pass).
    """
    container = st.sidebar if sidebar else st
    # `key` alone drives persistence across reruns; no `index=`/`value=` so
    # Streamlit doesn't warn about a widget default competing with session state.
    choice = container.radio(
        "Theme",
        options=["Default", "Neon"],
        horizontal=True,
        key=_STATE_KEY,
    )
    if choice == "Neon":
        st.markdown(_NEON_CSS, unsafe_allow_html=True)
        return NEON
    return "default"


def active_theme() -> str:
    return NEON if st.session_state.get(_STATE_KEY) == "Neon" else "default"


def themed_figure(fig_dict: dict) -> go.Figure:
    """``go.Figure`` for ``st.plotly_chart``, recoloured when Neon is active.

    Drop-in replacement for each app's local ``to_figure`` helper.
    """
    return go.Figure(apply_theme(fig_dict, active_theme()))
