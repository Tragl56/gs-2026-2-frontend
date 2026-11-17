"""Tela 'Meus relatos': histórico do cidadão (vindo do estado da sessão)."""
import streamlit as st

from providers import api_client as api
from state import session
from ui import charts
from ui import components as ui


def render() -> None:
    protocols = tuple(session.get("protocols"))
    lookup = st.expander("🔎 Acompanhar um protocolo pelo número", expanded=not protocols)
    with lookup, st.form("add_protocol", border=False):
        proto = st.text_input("Número do protocolo", placeholder="ZLA-20261106-00012", max_chars=30)
        if st.form_submit_button("Acompanhar"):
            if session.add_protocol(proto):
                st.rerun()
            else:
                st.warning("O protocolo tem o formato ZLA-AAAAMMDD-NNNNN, por exemplo ZLA-20261106-00012.",
                           icon="✏️")

    if not protocols:
        ui.empty_state("📭", "Você ainda não fez nenhum relato",
                       "Use a aba Avisar um problema para contar o que viu na sua rua. Seus relatos aparecem aqui, "
                       "mesmo se você fechar a página. Já tem um protocolo? Digite o número acima.")
        return

    try:
        reports = api.my_reports(protocols)
    except api.ApiError as err:
        ui.show_error(err)
        return

    missing = set(protocols) - {r["protocol"] for r in reports}
    if missing:
        st.warning(f"Não encontramos: {', '.join(sorted(missing))}", icon="🔍")

    resolved = sum(r["status"] == "resolvido" for r in reports)
    ui.kpi_row([
        ("Seus relatos", len(reports), None),
        ("Resolvidos", resolved, None),
        ("Em aberto", len(reports) - resolved, "Recebidos ou em andamento"),
    ])
    for r in reports:
        ui.report_card(r, show_description=True)

    history = session.get("history")
    if history:
        st.plotly_chart(charts.session_timeline(history), width="stretch")
