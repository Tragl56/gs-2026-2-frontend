"""Estado centralizado da sessão. Toda leitura/escrita de st.session_state passa por aqui."""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from features.validation import normalize_protocol

DEFAULTS = {
    "step": 1,                 # 1 = descrever, 2 = revisar IA, 3 = protocolo gerado
    "draft": {"description": "", "cep": "", "reference": ""},
    "triage": None,            # resultado da IA (evita nova chamada a cada rerun)
    "ai_failure": None,        # tipo de falha da IA na última análise (habilita registro manual)
    "last_report": None,       # último relato confirmado
    "protocols": [],           # protocolos do cidadão (espelhados na URL)
    "history": [],             # linha do tempo das interações (alimenta gráfico)
    "feedback_given": set(),
    "profile": "cidadao",
    "manager_token": None,
    "high_contrast": False,
    "large_text": False,
}


def init() -> None:
    first_run = "step" not in st.session_state
    for key, value in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value.copy() if hasattr(value, "copy") else value
    if first_run:
        _load_protocols_from_url()


# ---------- Protocolos na URL: sobrevivem a recarregar a página e podem virar favorito ----------

def _load_protocols_from_url() -> None:
    raw = st.query_params.get("p", "")
    for item in raw.split(","):
        proto = normalize_protocol(item)
        if proto and proto not in st.session_state.protocols:
            st.session_state.protocols.append(proto)


def _sync_url() -> None:
    if st.session_state.protocols:
        st.query_params["p"] = ",".join(st.session_state.protocols[-20:])
    elif "p" in st.query_params:
        del st.query_params["p"]


def get(key: str):
    return st.session_state[key]


def put(key: str, value) -> None:
    st.session_state[key] = value


def log_event(kind: str, **data) -> None:
    st.session_state.history.append({"when": datetime.now(), "event": kind, **data})


def save_triage(draft: dict, triage: dict) -> None:
    st.session_state.draft = draft
    st.session_state.triage = triage
    st.session_state.ai_failure = None
    st.session_state.step = 2
    log_event("analisado", category=triage["category_label"], urgency=triage["urgency"])


def save_ai_failure(draft: dict, kind: str | None) -> None:
    st.session_state.draft = draft
    st.session_state.ai_failure = kind


def save_confirmation(report: dict, corrected: bool) -> None:
    st.session_state.last_report = report
    st.session_state.ai_failure = None
    if report["protocol"] not in st.session_state.protocols:
        st.session_state.protocols.append(report["protocol"])
    _sync_url()
    st.session_state.step = 3
    log_event("confirmado", category=report["category_label"], urgency=report["final_urgency"], corrected=corrected)


def add_protocol(protocol: str) -> bool:
    proto = normalize_protocol(protocol)
    if not proto:
        return False
    if proto not in st.session_state.protocols:
        st.session_state.protocols.append(proto)
        _sync_url()
    return True


def mark_feedback(protocol: str, useful: bool) -> None:
    st.session_state.feedback_given.add(protocol)
    log_event("avaliado", useful=useful)


def back_to_edit() -> None:
    st.session_state.step = 1
    st.session_state.triage = None


def new_report() -> None:
    st.session_state.step = 1
    st.session_state.triage = None
    st.session_state.ai_failure = None
    st.session_state.last_report = None
    st.session_state.draft = {"description": "", "cep": "", "reference": ""}
