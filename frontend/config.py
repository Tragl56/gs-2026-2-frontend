"""Configuração do front-end. A URL da API vem de variável de ambiente ou st.secrets."""
import os

import streamlit as st


def api_url() -> str:
    try:
        url = st.secrets.get("API_URL")  # Streamlit Community Cloud
    except Exception:  # sem secrets.toml
        url = None
    # 127.0.0.1 (e não localhost) evita ~2s de espera por IPv6 no Windows.
    return (url or os.getenv("API_URL", "http://127.0.0.1:8000")).rstrip("/")


REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "40"))
DESCRIPTION_MIN, DESCRIPTION_MAX = 20, 1000
REFERENCE_MAX = 150
