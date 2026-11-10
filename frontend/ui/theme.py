"""Identidade visual e modos de acessibilidade (alto contraste, texto ampliado)."""
import streamlit as st

# Urgência: cor + ícone + texto (nunca só a cor). Pares texto/fundo com contraste >= 7:1.
URGENCY = {
    "baixa":   {"label": "Baixa",   "icon": "🟢", "fg": "#14532D", "bg": "#DCFCE7", "chart": "#15803D"},
    "media":   {"label": "Média",   "icon": "🟡", "fg": "#713F12", "bg": "#FEF9C3", "chart": "#CA8A04"},
    "alta":    {"label": "Alta",    "icon": "🟠", "fg": "#7C2D12", "bg": "#FFEDD5", "chart": "#EA580C"},
    "critica": {"label": "Crítica", "icon": "🔴", "fg": "#7F1D1D", "bg": "#FEE2E2", "chart": "#B91C1C"},
}
URGENCY_ORDER = ["critica", "alta", "media", "baixa"]

STATUS = {
    "aberto":       {"label": "Recebido",        "icon": "📥"},
    "em_andamento": {"label": "Em andamento",    "icon": "🔧"},
    "resolvido":    {"label": "Resolvido",       "icon": "✅"},
    "rejeitado":    {"label": "Não procede",     "icon": "⛔"},
}

_BASE_CSS = """
<style>
.zela-hero {padding: 1.1rem 1.3rem; border-radius: 14px; background: linear-gradient(120deg,#0F766E,#115E59);
            color: #FFFFFF; margin-bottom: 1rem;}
.zela-hero h1 {color:#FFFFFF; font-size: 1.9rem; margin: 0;}
.zela-hero p {color:#ECFEFF; margin: .3rem 0 0 0; font-size: 1.05rem;}
.zela-badge {display:inline-block; padding: .2rem .65rem; border-radius: 999px; font-weight: 700;
             font-size: .92rem; border: 1px solid currentColor;}
.zela-card {border: 1px solid #CBD5E1; border-radius: 12px; padding: .9rem 1rem; margin-bottom: .6rem;}
.zela-steps {display:flex; gap:.5rem; margin: .3rem 0 1rem 0; flex-wrap: wrap;}
.zela-step {padding:.3rem .8rem; border-radius:999px; background:#E2E8F0; color:#1E293B; font-weight:600;}
.zela-step.active {background:#0F766E; color:#FFFFFF;}
.zela-step.done {background:#CCFBF1; color:#134E4A;}
.zela-empty {text-align:center; padding: 2rem 1rem; color:#334155; border:2px dashed #CBD5E1; border-radius:12px;}
.zela-empty .icon {font-size: 2.4rem;}
:focus-visible {outline: 3px solid #F59E0B !important; outline-offset: 2px;}
</style>
"""

_HIGH_CONTRAST_CSS = """
<style>
.stApp, [data-testid="stSidebar"], [data-testid="stHeader"] {background:#000000 !important; color:#FFFFFF !important;}
.zela-hero {background:#000000 !important; border:2px solid #FFFF00;}
.zela-hero h1, .zela-hero p {color:#FFFF00 !important;}
[data-testid^="stBaseButton"] {background:#FFFF00 !important; color:#000000 !important; border:2px solid #FFFFFF !important;}
[data-testid^="stBaseButton"] p {color:#000000 !important;}
input::placeholder, textarea::placeholder {color:#D4D4D4 !important; opacity:1;}
.stApp p, .stApp label, .stApp span, .stApp li, .stApp h1, .stApp h2, .stApp h3, .stApp div {color:#FFFFFF;}
.zela-card, .zela-empty {border-color:#FFFF00 !important; color:#FFFFFF !important;}
.zela-step {background:#000000 !important; color:#FFFF00 !important; border:2px solid #FFFF00;}
.zela-step.active {background:#FFFF00 !important; color:#000000 !important;}
.zela-badge {background:#000000 !important; color:#FFFF00 !important; border:2px solid #FFFF00 !important;}
input, textarea {background:#000000 !important; color:#FFFFFF !important; border:2px solid #FFFFFF !important;}
</style>
"""

_LARGE_TEXT_CSS = """
<style>
html, .stApp, .stApp p, .stApp label, .stApp li, .stApp input, .stApp textarea {font-size: 1.2rem !important;}
</style>
"""


def apply(high_contrast: bool, large_text: bool) -> None:
    st.html(_BASE_CSS)
    if high_contrast:
        st.html(_HIGH_CONTRAST_CSS)
    if large_text:
        st.html(_LARGE_TEXT_CSS)
