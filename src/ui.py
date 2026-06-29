from __future__ import annotations

import html
from math import ceil
from typing import Iterable

import pandas as pd
import streamlit as st


STATUS_STYLES = {
    "Pendente": ("#7c2d12", "#ffedd5", "#fdba74"),
    "Rascunho": ("#854d0e", "#fef9c3", "#fde047"),
    "Preenchida": ("#166534", "#dcfce7", "#86efac"),
    "Completa": ("#166534", "#dcfce7", "#86efac"),
    "Parcial": ("#1d4ed8", "#dbeafe", "#93c5fd"),
    "Registrada": ("#166534", "#dcfce7", "#86efac"),
    "A seguir": ("#166534", "#dcfce7", "#86efac"),
    "Em andamento": ("#9a3412", "#ffedd5", "#fdba74"),
    "Finalizada": ("#991b1b", "#fee2e2", "#fca5a5"),
}


def apply_app_style() -> None:
    st.markdown(
        """
        <style>
        :root {
            --orion-border: #d8dee8;
            --orion-surface: #ffffff;
            --orion-surface-soft: #fbfcfe;
            --orion-muted: #5f6b7a;
            --orion-text: #17202a;
            --orion-accent: #146c94;
            --orion-accent-2: #2f855a;
        }
        @media (prefers-color-scheme: dark) {
            :root {
                --orion-border: #334155;
                --orion-surface: #111827;
                --orion-surface-soft: #0f172a;
                --orion-muted: #cbd5e1;
                --orion-text: #f8fafc;
                --orion-accent: #38bdf8;
                --orion-accent-2: #4ade80;
            }
        }
        .block-container {
            padding-top: 1.4rem;
            padding-bottom: 3rem;
            max-width: 1280px;
        }
        h1, h2, h3 {
            color: var(--orion-text);
            letter-spacing: 0;
        }
        div[data-testid="stMetric"] {
            background: var(--orion-surface);
            border: 1px solid var(--orion-border);
            border-radius: 8px;
            padding: .85rem 1rem;
        }
        div[data-testid="stMetricLabel"] p {
            color: var(--orion-muted);
            font-size: .82rem;
        }
        .orion-kpis {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: .75rem;
            margin: .75rem 0 1.1rem;
        }
        .orion-kpi {
            border: 1px solid var(--orion-border);
            border-radius: 8px;
            background: var(--orion-surface);
            padding: .9rem 1rem;
        }
        .orion-kpi-label {
            color: var(--orion-muted);
            font-size: .8rem;
            margin-bottom: .35rem;
        }
        .orion-kpi-value {
            color: var(--orion-text);
            font-size: 1.45rem;
            font-weight: 700;
            line-height: 1.15;
        }
        .orion-kpi-note {
            color: var(--orion-muted);
            font-size: .78rem;
            margin-top: .35rem;
        }
        .orion-badge {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            border: 1px solid;
            font-size: .76rem;
            font-weight: 700;
            line-height: 1;
            padding: .28rem .55rem;
            white-space: nowrap;
        }
        .orion-list {
            display: grid;
            gap: .55rem;
            margin: .5rem 0 1rem;
        }
        .orion-row {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            gap: .75rem;
            align-items: center;
            border: 1px solid var(--orion-border);
            border-radius: 8px;
            padding: .75rem .85rem;
            background: var(--orion-surface);
        }
        .orion-row-title {
            font-weight: 700;
            color: var(--orion-text);
            overflow-wrap: anywhere;
        }
        .orion-row-meta {
            color: var(--orion-muted);
            font-size: .84rem;
            margin-top: .2rem;
            overflow-wrap: anywhere;
        }
        .orion-empty {
            border: 1px dashed var(--orion-border);
            border-radius: 8px;
            padding: 1rem;
            color: var(--orion-muted);
            background: var(--orion-surface-soft);
        }
        .stButton > button,
        .stDownloadButton > button,
        button[kind="primary"] {
            border-radius: 8px;
        }
        [data-testid="stDataFrame"] {
            border: 1px solid var(--orion-border);
            border-radius: 8px;
            overflow: hidden;
        }
        @media (max-width: 720px) {
            .orion-row {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_badge(status: object) -> str:
    label = str(status or "-")
    color, background, border = STATUS_STYLES.get(label, ("#374151", "#f3f4f6", "#d1d5db"))
    return (
        f'<span class="orion-badge" style="color:{color};background:{background};'
        f'border-color:{border};">{html.escape(label)}</span>'
    )


def render_kpis(items: Iterable[tuple[str, object, str | None]]) -> None:
    cards = []
    for label, value, note in items:
        note_html = f'<div class="orion-kpi-note">{html.escape(str(note))}</div>' if note else ""
        cards.append(
            '<div class="orion-kpi">'
            f'<div class="orion-kpi-label">{html.escape(str(label))}</div>'
            f'<div class="orion-kpi-value">{html.escape(str(value))}</div>'
            f"{note_html}</div>"
        )
    st.markdown(f'<div class="orion-kpis">{"".join(cards)}</div>', unsafe_allow_html=True)


def render_item_list(rows: Iterable[dict], empty_text: str = "Nada para mostrar.") -> None:
    items = list(rows)
    if not items:
        st.markdown(f'<div class="orion-empty">{html.escape(empty_text)}</div>', unsafe_allow_html=True)
        return

    rendered = []
    for row in items:
        title = html.escape(str(row.get("title", "")))
        meta = html.escape(str(row.get("meta", "")))
        badge = status_badge(row.get("status"))
        rendered.append(
            '<div class="orion-row">'
            f'<div><div class="orion-row-title">{title}</div><div class="orion-row-meta">{meta}</div></div>'
            f"<div>{badge}</div>"
            "</div>"
        )
    st.markdown(f'<div class="orion-list">{"".join(rendered)}</div>', unsafe_allow_html=True)


def paginate_dataframe(df: pd.DataFrame, key: str, page_size: int = 25) -> pd.DataFrame:
    if df.empty or len(df) <= page_size:
        return df
    total_pages = ceil(len(df) / page_size)
    page = st.number_input(
        "Pagina",
        min_value=1,
        max_value=total_pages,
        value=1,
        step=1,
        key=f"{key}_page",
    )
    start = (int(page) - 1) * page_size
    end = start + page_size
    st.caption(f"Mostrando {start + 1}-{min(end, len(df))} de {len(df)} registros.")
    return df.iloc[start:end]
