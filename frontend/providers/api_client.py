"""Cliente HTTP da API Zela. O front-end NUNCA fala com o provedor de IA diretamente.

Toda falha vira um ApiError com mensagem pensada para o cidadão (sem detalhes técnicos).
"""
from __future__ import annotations

import logging

import httpx
import streamlit as st

from config import REQUEST_TIMEOUT_SECONDS, api_url

log = logging.getLogger(__name__)

FRIENDLY = {
    "offline": "Não conseguimos falar com o sistema da prefeitura agora. Verifique sua internet e tente de novo em alguns minutos.",
    "timeout": "A análise está demorando mais que o normal. Seu texto continua salvo aqui.",
    "llm_unavailable": "Nosso assistente está fora do ar no momento. Seu texto continua salvo aqui.",
    "invalid_ai_response": "O assistente deu uma resposta que não conseguimos entender. Seu texto continua salvo aqui.",
    "rate_limited": "Você fez muitas análises seguidas. Aguarde um minuto e tente de novo.",
    "invalid_response": "Recebemos uma resposta inesperada do sistema. Tente de novo.",
    "unauthorized": "Código de acesso inválido.",
    "not_found": "Não encontramos esse protocolo.",
    "server": "O sistema encontrou um problema. Tente de novo em alguns minutos.",
}

# Falhas em que a API está no ar, mas a IA não ajudou: o cidadão pode registrar sozinho.
AI_FAILURES = {"timeout", "llm_unavailable", "invalid_ai_response"}


class ApiError(Exception):
    def __init__(self, kind: str, message: str | None = None):
        self.kind = kind
        self.message = message or FRIENDLY.get(kind, FRIENDLY["server"])
        super().__init__(self.message)


@st.cache_resource
def _http() -> httpx.Client:
    """Um único cliente HTTP reaproveitado entre reruns e sessões (pool de conexões)."""
    return httpx.Client(base_url=api_url(), timeout=REQUEST_TIMEOUT_SECONDS)


def _request(method: str, path: str, *, token: str | None = None, **kwargs):
    headers = {"X-Manager-Token": token} if token else None
    try:
        resp = _http().request(method, path, headers=headers, **kwargs)
    except httpx.TimeoutException:
        raise ApiError("timeout")
    except httpx.HTTPError as exc:
        log.warning("API inacessível: %s", exc)
        raise ApiError("offline")

    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", {})
        except ValueError:
            detail = {}
        code = detail.get("code") if isinstance(detail, dict) else None
        if code == "invalid_input":  # mensagens de validação já são amigáveis
            raise ApiError(code, detail.get("message"))
        raise ApiError(code or ("server" if resp.status_code >= 500 else "invalid_response"))
    try:
        return resp.json()
    except ValueError:
        raise ApiError("invalid_response")


def _require_keys(data: dict, keys: set[str]) -> dict:
    if not isinstance(data, dict) or not keys <= data.keys():
        raise ApiError("invalid_response")
    return data


# ---------- Leituras com cache (evitam chamadas repetidas a cada rerun) ----------

@st.cache_data(ttl=10, show_spinner=False)
def health() -> dict:
    return _request("GET", "/health")


@st.cache_data(ttl=600, show_spinner=False)
def categories() -> list[dict]:
    return _request("GET", "/api/v1/categories")


@st.cache_data(ttl=30, show_spinner=False)
def public_stats() -> list[dict]:
    return _request("GET", "/api/v1/stats/public")


@st.cache_data(ttl=30, show_spinner=False)
def my_reports(protocols: tuple[str, ...]) -> list[dict]:
    if not protocols:
        return []
    return _request("GET", "/api/v1/reports", params={"protocols": ",".join(protocols)})


def wake_up(timeout_seconds: float = 90) -> bool:
    """Acorda a API hospedada em plano gratuito (o Render desliga após 15 min sem uso
    e leva ~1 min para voltar). Não usa cache: é chamada só quando o health falha."""
    try:
        resp = httpx.get(f"{api_url()}/health", timeout=timeout_seconds)
        ok = resp.status_code == 200
    except httpx.HTTPError:
        ok = False
    if ok:
        health.clear()
    return ok


def manager_reports(token: str) -> list[dict]:
    return _request("GET", "/api/v1/manager/reports", token=token)


# ---------- Escritas (nunca em cache) ----------

def analyze(description: str, cep: str | None, reference: str | None) -> dict:
    data = _request("POST", "/api/v1/reports/analyze",
                    json={"description": description, "cep": cep or None, "reference": reference or None})
    return _require_keys(data, {"category", "urgency", "title", "department", "citizen_guidance"})


def confirm(report_input: dict, triage: dict | None, final_category: str, final_urgency: str) -> dict:
    """Envia o relato confirmado. `triage=None` = registro manual (IA indisponível)."""
    data = _request("POST", "/api/v1/reports", json={
        "input": report_input, "triage": triage,
        "final_category": final_category, "final_urgency": final_urgency,
    })
    invalidate_reads()
    return _require_keys(data, {"protocol"})


def feedback(protocol: str, useful: bool, comment: str | None) -> dict:
    data = _request("PATCH", f"/api/v1/reports/{protocol}/feedback", json={"useful": useful, "comment": comment})
    my_reports.clear()
    return data


def update_status(token: str, protocol: str, status: str, note: str | None) -> dict:
    data = _request("PATCH", f"/api/v1/manager/reports/{protocol}/status", token=token,
                    json={"status": status, "manager_note": note})
    invalidate_reads()
    return data


def invalidate_reads() -> None:
    my_reports.clear()
    public_stats.clear()
