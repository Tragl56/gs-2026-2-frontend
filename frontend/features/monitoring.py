"""Equipe da prefeitura: monitoramento por câmera (vídeo curto ou sequência de fotos) com o módulo de visão."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from providers import api_client as api
from ui import components as ui
from ui import vision as vui

ASSETS = Path(__file__).resolve().parents[1] / "assets"
DEMO_VIDEO = ASSETS / "monitoramento_demo.mp4"


def _video(token: str) -> None:
    src = st.radio("Vídeo", ["Vídeo de demonstração", "Enviar vídeo"], horizontal=True, key="mon_src")
    content, name = None, "video.mp4"
    if src == "Vídeo de demonstração":
        if DEMO_VIDEO.exists():
            content, name = DEMO_VIDEO.read_bytes(), DEMO_VIDEO.name
            st.caption("Câmera percorrendo uma parede com variação de luz e sombra de poste (simulação montada "
                       "com imagens de teste que o modelo nunca viu).")
        else:
            st.info("Vídeo de demonstração não encontrado em frontend/assets/.")
    else:
        up = st.file_uploader("Vídeo curto (MP4, até ~25 s)", type=["mp4", "mov", "avi", "mkv"], key="mon_up")
        if up is not None:
            content, name = up.getvalue(), up.name
    if content is None:
        return
    st.video(content)
    every = st.slider("Analisar 1 a cada N quadros", 1, 10, 1, key="mon_every",
                      help="Pular quadros aumenta o FPS; o último resultado é mantido nos quadros pulados.")
    if st.button("▶️ Processar vídeo", type="primary", key="mon_go"):
        with st.spinner("Processando quadro a quadro no servidor…"):
            try:
                st.session_state.mon_result = api.vision_monitor(token, content, name, every)
            except api.ApiError as err:
                ui.show_error(err, retry_hint=False)
                return
    r = st.session_state.get("mon_result")
    if not r:
        return
    if r.get("video_mp4"):
        st.video(vui.b64_image(r["video_mp4"]))
    ui.kpi_row([
        ("Quadros", r["frames"], f"{r['resolution']} · {r['windows_per_frame']} janelas por quadro"),
        ("FPS (processamento completo)", f"{r['fps_pipeline']:.1f}", "Leitura, modelo, marcação e vídeo de saída"),
        ("Latência média do modelo", f"{r['latency_ms_mean']:.0f} ms", f"p95 {r['latency_ms_p95']:.0f} ms · {r['device']}"),
        ("Quadros em alerta", f"{r['alert_frames']} ({r['alert_frames'] / max(r['frames'], 1):.0%})", None),
    ])
    tl = pd.DataFrame(r["timeline"]).set_index("t")[["confidence", "smoothed"]]
    st.line_chart(tl.rename(columns={"confidence": "confiança no quadro", "smoothed": "média móvel"}),
                  x_label="tempo (s)", y_label="confiança de fissura")
    st.caption(f"Limiar {r['threshold']:.2f}. O alerta liga após 3 quadros seguidos acima do limiar e desliga quando a "
               "média móvel cai abaixo de 0,8 × limiar, para não piscar com um quadro ruim.")
    st.markdown(f"**Trechos para inspeção: {len(r['events'])}**")
    if r["events"]:
        ev = pd.DataFrame(r["events"]).rename(columns={"start_s": "início (s)", "end_s": "fim (s)", "max_confidence": "confiança máx."})
        st.dataframe(ev.style.format({"início (s)": "{:.1f}", "fim (s)": "{:.1f}", "confiança máx.": "{:.0%}"}),
                     hide_index=True, width="stretch")


def _sequence(token: str) -> None:
    files = st.file_uploader("Fotos da vistoria (até 40)", type=["jpg", "jpeg", "png", "webp"],
                             accept_multiple_files=True, key="seq_up")
    if not files:
        return
    if st.button("▶️ Analisar sequência", type="primary", key="seq_go"):
        with st.spinner("Analisando as fotos no servidor…"):
            try:
                st.session_state.seq_result = api.vision_sequence(token, [(f.name, f.getvalue(), f.type or "image/jpeg") for f in files])
            except api.ApiError as err:
                ui.show_error(err, retry_hint=False)
                return
    r = st.session_state.get("seq_result")
    if not r:
        return
    ui.kpi_row([
        ("Fotos", r["images"], None),
        ("Com possível fissura", r["flagged"], f"Limiar de triagem {r['threshold']:.2f}"),
        ("Taxa de processamento", f"{r['images_per_second']:.1f} fotos/s", r["device"]),
        ("Latência média", f"{r['latency_ms_mean']:.0f} ms", None),
    ])
    cols = st.columns(4)
    for i, item in enumerate(r["items"]):
        col = cols[i % 4]
        if item.get("error"):
            col.warning(f"{item['filename']}: {item['error']}")
            continue
        s = item["summary"]
        col.image(vui.b64_image(s["thumbnail_jpeg"]), width="stretch",
                  caption=f"{'🔴 inspecionar' if s['crack_detected'] else '🟢 ok'} · {s['confidence']:.0%} · {item['filename']}")


def render(token: str) -> None:
    st.markdown("#### 🎥 Monitoramento por câmera")
    st.caption("Simula o monitoramento urbano: uma viatura, drone ou fiscal grava a superfície e o sistema aponta os "
               "trechos com possível fissura. " + vui.DISCLAIMER.replace("**", ""))
    mode = st.radio("Entrada", ["Vídeo", "Sequência de fotos"], horizontal=True, key="mon_mode")
    if mode == "Vídeo":
        _video(token)
    else:
        _sequence(token)
