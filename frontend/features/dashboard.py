"""Painel com filtros e gráficos Plotly. Reutilizado pelo cidadão (dados públicos) e pelo gestor."""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
import streamlit as st

from ui import charts
from ui import components as ui
from ui.theme import STATUS, URGENCY, URGENCY_ORDER

TZ = "America/Sao_Paulo"


def to_frame(records: list[dict]) -> pd.DataFrame:
    """Normaliza relatos públicos ou completos para o mesmo formato de tabela."""
    rows = []
    for r in records:
        loc = r.get("location") or {}
        rows.append({
            "created_at": r["created_at"],
            "category_label": r["category_label"],
            "urgency": r.get("urgency") or r.get("final_urgency"),
            "status": r["status"],
            "neighborhood": r.get("neighborhood") or loc.get("neighborhood") or "Não informado",
            "corrected": r.get("corrected_by_citizen", False),
            "ai_used": r.get("ai_used", True),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True, format="ISO8601").dt.tz_convert(TZ)
    df["urgency_label"] = df["urgency"].map(lambda u: URGENCY[u]["label"])
    df["status_label"] = df["status"].map(lambda s: STATUS[s]["label"])
    return df


def apply_filters(df: pd.DataFrame, days: int, urgencies: list[str], categories: list[str],
                  statuses: list[str], now: pd.Timestamp | None = None) -> pd.DataFrame:
    now = now or pd.Timestamp.now(tz=TZ)
    cutoff = now - timedelta(days=days)
    return df[(df["created_at"] >= cutoff) & df["urgency"].isin(urgencies)
              & df["category_label"].isin(categories) & df["status"].isin(statuses)]


def render(records: list[dict], key: str, title: str) -> None:
    df = to_frame(records)
    if df.empty:
        ui.empty_state("📊", "Ainda não há dados para mostrar", "Assim que houver relatos, os gráficos aparecem aqui.")
        return

    st.markdown(f"#### {title}")
    with st.container(border=True):
        st.markdown("**Filtros**")
        c1, c2, c3 = st.columns(3)
        days = c1.select_slider("Período", options=[7, 15, 30, 90], value=30,
                                format_func=lambda d: f"Últimos {d} dias", key=f"{key}_days")
        urgencies = c2.multiselect("Urgência", URGENCY_ORDER, default=URGENCY_ORDER, key=f"{key}_urg",
                                   format_func=lambda u: f"{URGENCY[u]['icon']} {URGENCY[u]['label']}")
        cats = sorted(df["category_label"].unique())
        chosen_cats = c3.multiselect("Tipo de problema", cats, default=cats, key=f"{key}_cat")
        statuses = st.pills("Situação", list(STATUS), default=list(STATUS), selection_mode="multi",
                            format_func=lambda s: f"{STATUS[s]['icon']} {STATUS[s]['label']}", key=f"{key}_st")

    view = apply_filters(df, days, urgencies, chosen_cats, statuses or [])
    if view.empty:
        ui.empty_state("🔍", "Nenhum relato com esses filtros", "Tente ampliar o período ou marcar mais opções.")
        return

    resolved = (view["status"] == "resolvido").mean()
    ui.kpi_row([
        ("Relatos", len(view), None),
        ("Críticos", int((view["urgency"] == "critica").sum()), "Risco imediato à segurança"),
        ("Resolvidos", f"{resolved:.0%}", None),
        ("Corrigidos pelo cidadão", f"{view['corrected'].mean():.0%}",
         "Quanto a classificação da IA foi ajustada por pessoas"),
        ("Sem a IA", int((~view["ai_used"]).sum()), "Registrados manualmente quando o assistente estava fora do ar"),
    ])

    t1, t2, t3 = st.tabs(["Por tipo", "Linha do tempo", "Por bairro"])
    t1.plotly_chart(charts.by_category(view), width="stretch", key=f"{key}_c1")
    t2.plotly_chart(charts.timeline(view), width="stretch", key=f"{key}_c2")
    t3.plotly_chart(charts.by_neighborhood(view), width="stretch", key=f"{key}_c3")
    st.caption("Passe o mouse para ver detalhes, arraste para dar zoom e clique na legenda para esconder séries.")

    st.download_button("⬇️ Baixar dados filtrados (CSV)", key=f"{key}_csv", mime="text/csv",
                       file_name="zela_relatos.csv",
                       data=view[["created_at", "category_label", "urgency_label", "status_label", "neighborhood"]]
                       .to_csv(index=False).encode("utf-8-sig"))
