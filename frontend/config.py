"""Configuração do front-end, lida de variáveis de ambiente."""
import os

# 127.0.0.1 (e não localhost) evita ~2s de espera por IPv6 no Windows.
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "45"))
DESCRIPTION_MIN, DESCRIPTION_MAX = 20, 1000
REFERENCE_MAX = 150
