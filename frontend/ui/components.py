"""Componentes visuais reutilizáveis (usados em várias telas com parâmetros diferentes)."""
from __future__ import annotations

import html
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

from providers.api_client import ApiError
from ui.theme import STATUS, URGENCY

_TZ = ZoneInfo("America/Sao_Paulo")


def hero(title: str, subtitle: str) -> None:
    st.html(f'<div class="zela-hero" role="banner"><h1>{html.escape(title)}</h1>'
            f'<p>{html.escape(subtitle)}</p></div>')


def urgency_badge(urgency: str, prefix: str = "Urgência") -> str:
    """Selo de urgência: cor + ícone + texto. Retorna HTML para compor outros componentes."""
    u = URGENCY.get(urgency, URGENCY["media"])
    text = f"{prefix} {u['label'].lower()}" if prefix else u["label"]
    return (f'<span class="zela-badge" style="color:{u["fg"]};background:{u["bg"]}" '
            f'aria-label="{html.escape(text)}">{u["icon"]} {html.escape(text)}</span>')


def status_badge(status: str) -> str:
    s = STATUS.get(status, STATUS["aberto"])
    return f'<span class="zela-badge" style="color:#1E293B;background:#F1F5F9">{s["icon"]} {s["label"]}</span>'


def steps(current: int) -> None:
    labels = ["1. Descrever", "2. Revisar", "3. Protocolo"]
    items = []
    for i, label in enumerate(labels, start=1):
        cls = "active" if i == current else ("done" if i < current else "")
        mark = "✓ " if i < current else ""
        aria = ' aria-current="step"' if i == current else ""
        items.append(f'<span class="zela-step {cls}"{aria}>{mark}{label}</span>')
    st.html(f'<nav class="zela-steps" aria-label="Etapas do relato">{"".join(items)}</nav>')


def empty_state(icon: str, title: str, text: str) -> None:
    st.html(f'<div class="zela-empty"><div class="icon" aria-hidden="true">{icon}</div>'
            f'<h3>{html.escape(title)}</h3><p>{html.escape(text)}</p></div>')


def show_error(err: ApiError, retry_hint: bool = True) -> None:
    """Erro amigável: ícone + texto, nunca stack trace."""
    st.error(err.message, icon="⚠️")
    if retry_hint and err.kind in {"offline", "timeout", "llm_unavailable", "server"}:
        st.caption("Se o problema for urgente e houver risco à vida, ligue 199 (Defesa Civil) ou 193 (Bombeiros).")


def format_when(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(_TZ).strftime("%d/%m/%Y %H:%M")


def report_card(report: dict, *, show_description: bool = False, extra_notes: list[str] | None = None) -> None:
    """Cartão de relato, usado em 'Meus relatos' (cidadão), no protocolo e na 'Fila' (gestor)."""
    loc = report.get("location") or {}
    place = ", ".join(p for p in [loc.get("neighborhood"), loc.get("city")] if p) or "Local não informado"
    body = [
        f'<div class="zela-card"><strong>{html.escape(report["title"])}</strong><br>',
        f'{urgency_badge(report["final_urgency"])} {status_badge(report["status"])}<br>',
        f'<small>Protocolo <b>{report["protocol"]}</b> · {format_when(report["created_at"])} · {html.escape(place)}<br>',
        f'Encaminhado para: {html.escape(report["department"])}</small>',
    ]
    if show_description:
        body.append(f'<p style="margin:.5rem 0 0 0">{html.escape(report["description"])}</p>')
    notes = list(extra_notes or [])
    if report.get("corrected_by_citizen"):
        notes.insert(0, "✏️ Classificação corrigida pelo cidadão")
    if report.get("ai_used") is False:
        notes.insert(0, "🙋 Registrado pelo cidadão sem a IA")
    if report.get("manager_note"):
        notes.append(f"💬 Prefeitura: {report['manager_note']}")
    for note in notes:
        body.append(f'<p style="margin:.3rem 0 0 0"><small>{html.escape(note)}</small></p>')
    body.append("</div>")
    st.html("".join(body))


def kpi_row(items: list[tuple[str, str | int, str | None]]) -> None:
    """Linha de indicadores: [(rótulo, valor, ajuda)]."""
    cols = st.columns(len(items))
    for col, (label, value, help_text) in zip(cols, items):
        col.metric(label, value, help=help_text)


def read_aloud_button(text: str) -> None:
    """Leitura em voz alta (Web Speech API do navegador, pt-BR). Nada sai do computador."""
    payload = json.dumps(text)
    components.html(
        f"""
        <button id="b" aria-label="Ouvir orientação em voz alta"
          style="font-size:15px;padding:6px 14px;border-radius:8px;border:1px solid #0F766E;
                 background:#F0FDFA;color:#134E4A;cursor:pointer;font-weight:600">🔊 Ouvir em voz alta</button>
        <script>
          document.getElementById("b").onclick = () => {{
            const u = new SpeechSynthesisUtterance({payload});
            u.lang = "pt-BR"; window.speechSynthesis.cancel(); window.speechSynthesis.speak(u);
          }};
        </script>
        """,
        height=46,
    )
