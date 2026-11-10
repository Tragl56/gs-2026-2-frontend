"""Gráficos Plotly (interativos: hover, zoom, legenda clicável)."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from ui.theme import URGENCY, URGENCY_ORDER

_COLORS = {URGENCY[u]["label"]: URGENCY[u]["chart"] for u in URGENCY}
_ORDER = [URGENCY[u]["label"] for u in URGENCY_ORDER]


def _layout(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(title=title, margin=dict(l=10, r=10, t=50, b=10), legend_title_text="Urgência",
                      font=dict(size=14), hoverlabel=dict(font_size=14))
    return fig


def by_category(df: pd.DataFrame, title: str = "Relatos por tipo de problema") -> go.Figure:
    data = df.groupby(["category_label", "urgency_label"]).size().reset_index(name="relatos")
    fig = px.bar(data, y="category_label", x="relatos", color="urgency_label", orientation="h",
                 color_discrete_map=_COLORS, category_orders={"urgency_label": _ORDER},
                 pattern_shape="urgency_label",  # padrão além da cor (daltonismo)
                 labels={"category_label": "Tipo", "relatos": "Relatos", "urgency_label": "Urgência"})
    fig.update_yaxes(categoryorder="total ascending")
    return _layout(fig, title)


def timeline(df: pd.DataFrame, title: str = "Relatos por dia") -> go.Figure:
    data = (df.assign(dia=df["created_at"].dt.date)
              .groupby(["dia", "urgency_label"]).size().reset_index(name="relatos"))
    fig = px.bar(data, x="dia", y="relatos", color="urgency_label", color_discrete_map=_COLORS,
                 category_orders={"urgency_label": _ORDER},
                 labels={"dia": "Dia", "relatos": "Relatos", "urgency_label": "Urgência"})
    fig.update_xaxes(rangeslider_visible=True)
    return _layout(fig, title)


def by_neighborhood(df: pd.DataFrame, title: str = "Bairros com mais relatos") -> go.Figure:
    data = df.groupby("neighborhood").size().reset_index(name="relatos").sort_values("relatos")
    fig = px.bar(data, y="neighborhood", x="relatos", orientation="h", text="relatos",
                 labels={"neighborhood": "Bairro", "relatos": "Relatos"}, color_discrete_sequence=["#0F766E"])
    return _layout(fig, title)


def session_timeline(history: list[dict]) -> go.Figure:
    df = pd.DataFrame(history)
    fig = px.scatter(df, x="when", y="event", color="event", symbol="event",
                     hover_data=[c for c in ("category", "urgency") if c in df.columns],
                     labels={"when": "Horário", "event": "Ação"})
    fig.update_traces(marker=dict(size=14))
    fig.update_layout(showlegend=False)
    return _layout(fig, "Sua atividade nesta sessão")
