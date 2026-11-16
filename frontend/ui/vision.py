"""Componentes visuais do módulo de visão (fissuras): resultado da foto e nota nos cartões."""
from __future__ import annotations

import base64

import streamlit as st

DISCLAIMER = ("A análise da foto é uma **triagem**: indica onde vale inspecionar. "
              "Ela não mede a gravidade da fissura nem a segurança da estrutura; isso cabe à vistoria técnica.")


def b64_image(data: str | None) -> bytes | None:
    return base64.b64decode(data) if data else None


def result_panel(result: dict, *, title: str = "📷 Análise automática da foto") -> None:
    """Resultado completo: decisão, confiança, regiões marcadas, Grad-CAM, qualidade da foto e latência."""
    s = result["summary"]
    with st.container(border=True):
        st.markdown(f"#### {title}")
        if s["crack_detected"]:
            st.error(f"**Possível fissura: inspeção recomendada.** Confiança do modelo: **{s['confidence']:.0%}**", icon="🧱")
        else:
            st.success(f"**Sem indício de fissura nesta foto.** Confiança de fissura: {s['confidence']:.0%}", icon="✅")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Confiança (fissura)", f"{s['confidence']:.1%}")
        c2.metric("Área sinalizada", f"{s['area_fraction']:.0%}", help="Fração das partes da foto acima do limiar")
        c3.metric("Regiões", s["regions"])
        c4.metric("Tempo de análise", f"{result['latency_ms']:.0f} ms",
                  help=f"{result['windows']} janela(s) de {result['window_px']} px · {result['device']}")
        g1, g2 = st.columns(2)
        g1.image(b64_image(result["annotated_jpeg"]), width="stretch",
                 caption="Regiões marcadas para inspeção" if result["windows"] > 1 else "Foto enviada")
        if result.get("gradcam_jpeg"):
            g2.image(b64_image(result["gradcam_jpeg"]), width="stretch",
                     caption="Mapa de atenção (Grad-CAM): onde o modelo viu a fissura")
        else:
            g2.caption("O mapa de atenção aparece quando há possível fissura.")
        for alert in s.get("quality_alerts") or []:
            st.warning(alert, icon="📸")
        st.caption(f"Modelo {s['model']} · limiar de triagem {s['threshold']:.2f} · {DISCLAIMER}")
