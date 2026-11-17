"""Visão do gestor (prefeitura): fila priorizada e atualização de status."""
from __future__ import annotations

from collections import Counter

import streamlit as st

from features import dashboard
from providers import api_client as api
from state import session
from ui import components as ui
from ui.theme import STATUS, URGENCY, URGENCY_ORDER

OPEN = {"aberto", "em_andamento"}


def _place(r: dict) -> str:
    loc = r.get("location") or {}
    return loc.get("neighborhood") or "Não informado"


def cluster_sizes(reports: list[dict]) -> Counter:
    """Quantos relatos abertos existem por (categoria, bairro): ajuda a achar problemas recorrentes."""
    return Counter((r["final_category"], _place(r)) for r in reports if r["status"] in OPEN)


def priority_key(r: dict, clusters: Counter) -> tuple:
    """Mais urgente primeiro; no empate, problema com mais relatos parecidos; depois o mais antigo."""
    return (URGENCY_ORDER.index(r["final_urgency"]), -clusters[(r["final_category"], _place(r))], r["created_at"])


def login() -> bool:
    if session.get("manager_token"):
        return True
    with st.form("manager_login"):
        st.markdown("#### Acesso da equipe da prefeitura")
        token = st.text_input("Código de acesso", type="password")
        if st.form_submit_button("Entrar", type="primary"):
            try:
                api.manager_reports(token)
            except api.ApiError as err:
                ui.show_error(err, retry_hint=False)
                return False
            session.put("manager_token", token)
            st.rerun()
    return False


def _queue(reports: list[dict], token: str) -> None:
    c1, c2 = st.columns(2)
    urg = c1.multiselect("Urgência", URGENCY_ORDER, default=URGENCY_ORDER, key="q_urg",
                         format_func=lambda u: f"{URGENCY[u]['icon']} {URGENCY[u]['label']}")
    sts = c2.multiselect("Situação", list(STATUS), default=["aberto", "em_andamento"], key="q_st",
                         format_func=lambda s: f"{STATUS[s]['icon']} {STATUS[s]['label']}")
    clusters = cluster_sizes(reports)
    items = sorted((r for r in reports if r["final_urgency"] in urg and r["status"] in sts),
                   key=lambda r: priority_key(r, clusters))
    if not items:
        ui.empty_state("🎉", "Fila vazia", "Nenhum relato com esses filtros.")
        return
    st.caption(f"{len(items)} relato(s): mais urgentes primeiro e, no empate, os que mais se repetem no bairro.")
    for r in items[:50]:
        notes = []
        if r["corrected_by_citizen"] and r.get("ai_category"):
            notes.append(f"IA sugeriu: {r['ai_category']} / {URGENCY[r['ai_urgency']]['label']}")
        same = clusters[(r["final_category"], _place(r))]
        if same > 1:
            notes.append(f"👥 {same} relatos abertos deste tipo em {_place(r)}")
        ui.report_card(r, show_description=True, extra_notes=notes)
        with st.expander(f"Atualizar {r['protocol']}"):
            with st.form(f"st_{r['protocol']}", border=False):
                new = st.selectbox("Nova situação", list(STATUS), index=list(STATUS).index(r["status"]),
                                   format_func=lambda s: f"{STATUS[s]['icon']} {STATUS[s]['label']}")
                msg = st.text_input("Mensagem para o cidadão (opcional)", max_chars=300,
                                    value=r.get("manager_note") or "")
                if st.form_submit_button("Salvar"):
                    try:
                        api.update_status(token, r["protocol"], new, msg or None)
                        st.toast(f"{r['protocol']} atualizado", icon="✅")
                        st.rerun()
                    except api.ApiError as err:
                        ui.show_error(err, retry_hint=False)


def render() -> None:
    if not login():
        return
    token = session.get("manager_token")
    try:
        reports = api.manager_reports(token)
    except api.ApiError as err:
        if err.kind == "unauthorized":
            session.put("manager_token", None)
        ui.show_error(err)
        return

    tab_queue, tab_dash = st.tabs(["🗂️ Fila de atendimento", "📊 Indicadores"])
    with tab_queue:
        _queue(reports, token)
    with tab_dash:
        dashboard.render(reports, key="mgr", title="Indicadores de todos os relatos")
    if st.button("Sair do modo gestor"):
        session.put("manager_token", None)
        st.rerun()
