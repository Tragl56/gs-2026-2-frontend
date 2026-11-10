"""Zela – ponto de entrada do front-end Streamlit. Só monta o layout e delega às features."""
import streamlit as st

st.set_page_config(page_title="Zela · Sua rua, cuidada junto", page_icon="🏙️", layout="wide")

from features import about, dashboard, manager, my_reports, new_report  # noqa: E402
from providers import api_client as api  # noqa: E402
from state import session  # noqa: E402
from ui import components as ui  # noqa: E402
from ui import theme  # noqa: E402

session.init()

with st.sidebar:
    st.markdown("## 🏙️ Zela")
    profile = st.radio("Quem está usando?", ["cidadao", "gestor"], key="profile",
                       format_func=lambda p: "🙋 Sou cidadão" if p == "cidadao" else "🏛️ Equipe da prefeitura")
    st.divider()
    st.markdown("**Acessibilidade**")
    st.toggle("Alto contraste", key="high_contrast")
    st.toggle("Texto maior", key="large_text")
    st.divider()
    try:
        ok = api.health().get("ai_ready", False)
        st.markdown("🟢 Sistema no ar" if ok else "🟡 Sistema no ar, assistente de IA indisponível")
    except api.ApiError:
        st.markdown("🔴 Sistema fora do ar no momento")
    if session.get("protocols"):
        st.caption(f"Seus protocolos: {', '.join(session.get('protocols'))}")

theme.apply(session.get("high_contrast"), session.get("large_text"))
ui.hero("Zela", "Viu um problema na sua rua? Conte pra gente. A IA organiza e a prefeitura resolve.")

if profile == "gestor":
    manager.render()
else:
    t_new, t_mine, t_city, t_about = st.tabs(["📝 Novo relato", "📋 Meus relatos", "📊 Painel da cidade", "ℹ️ Como funciona"])
    with t_new:
        new_report.render()
    with t_mine:
        my_reports.render()
    with t_city:
        try:
            dashboard.render(api.public_stats(), key="city", title="O que os cidadãos estão relatando")
        except api.ApiError as err:
            ui.show_error(err)
    with t_about:
        about.render()
