"""Tela 'Novo relato': entrada → análise da IA → revisão humana → protocolo."""
from __future__ import annotations

import time

import streamlit as st

from config import DESCRIPTION_MAX, REFERENCE_MAX
from features.validation import validate_report
from providers import api_client as api
from state import session
from ui import components as ui
from ui.theme import URGENCY, URGENCY_ORDER


def _category_picker(cats: dict, default: str, key: str, container=st) -> str:
    options = list(cats)
    return container.selectbox("Tipo de problema", options, index=options.index(default), key=key,
                               format_func=lambda v: f"{cats[v]['icon']} {cats[v]['label']}")


def _urgency_picker(default: str, key: str, container=st) -> str:
    return container.selectbox("Urgência", URGENCY_ORDER, index=URGENCY_ORDER.index(default), key=key,
                               format_func=lambda u: f"{URGENCY[u]['icon']} {URGENCY[u]['label']}")


def _payload(draft: dict) -> dict:
    return {"description": draft["description"], "cep": draft["cep"].strip() or None,
            "reference": draft["reference"].strip() or None}


def _submit(triage: dict | None, final_cat: str, final_urg: str) -> None:
    draft = session.get("draft")
    with st.spinner("Registrando seu relato…"):
        try:
            report = api.confirm(_payload(draft), triage, final_cat, final_urg)
        except api.ApiError as err:
            ui.show_error(err)
            return
    corrected = triage is not None and (final_cat, final_urg) != (triage["category"], triage["urgency"])
    session.save_confirmation(report, corrected=corrected)
    st.rerun()


def _manual_registration() -> None:
    """Plano B: a IA falhou, mas o relato não se perde. O cidadão classifica e envia."""
    try:
        cats = {c["value"]: c for c in api.categories()}
    except api.ApiError:
        return
    with st.container(border=True):
        st.markdown("#### 🙋 Prefere registrar agora, sem o assistente?")
        st.caption("Escolha você mesmo o tipo e a urgência. A equipe da prefeitura confere depois.")
        c1, c2 = st.columns(2)
        cat = _category_picker(cats, "outro", "manual_cat", c1)
        urg = _urgency_picker("media", "manual_urg", c2)
        if st.button("Registrar sem a IA", key="manual_send", width="stretch"):
            _submit(None, cat, urg)


def _step_describe() -> None:
    draft = session.get("draft")
    with st.form("report_form", border=True):
        st.markdown("#### O que está acontecendo?")
        description = st.text_area(
            "Descreva o problema (obrigatório)",
            value=draft["description"], max_chars=DESCRIPTION_MAX, height=150,
            placeholder="Ex.: Tem um buraco grande na Rua das Flores, em frente ao número 120. "
                        "À noite os carros desviam pela contramão.",
            help="Diga o que é, onde fica e há quanto tempo. Não escreva nome, CPF ou telefone.",
        )
        c1, c2 = st.columns([1, 2])
        cep = c1.text_input("CEP (opcional)", value=draft["cep"], max_chars=9, placeholder="01310-100",
                            help="Usamos o CEP para encontrar o bairro e relatos parecidos por perto.")
        reference = c2.text_input("Ponto de referência (opcional)", value=draft["reference"],
                                  max_chars=REFERENCE_MAX, placeholder="Ex.: em frente à padaria, perto da escola")
        consent = st.checkbox("Confirmo que meu relato não traz dados pessoais (nome, CPF, telefone) de outras pessoas.")
        submitted = st.form_submit_button("Analisar meu relato", type="primary", width="stretch")

    if submitted:
        draft = {"description": description, "cep": cep, "reference": reference}
        session.save_ai_failure(draft, None)
        errors = validate_report(description, cep, reference, consent)
        if errors:
            for e in errors:
                st.warning(e, icon="✏️")
            return

        failure = None
        with st.status("Analisando seu relato…", expanded=True) as status:
            st.write("📍 Localizando o endereço pelo CEP…" if cep.strip() else "📝 Lendo seu relato…")
            progress = st.progress(10, text="Preparando")
            try:
                progress.progress(40, text="Nosso assistente está classificando o problema")
                started = time.perf_counter()
                triage = api.analyze(description, cep.strip() or None, reference.strip() or None)
                progress.progress(100, text=f"Pronto em {time.perf_counter() - started:.1f}s")
                status.update(label="Análise concluída", state="complete", expanded=False)
            except api.ApiError as exc:
                status.update(label="Não foi possível analisar agora", state="error", expanded=False)
                failure = exc
        if failure is None:
            session.save_triage(draft, triage)
            st.rerun()
        # O aviso fica fora do st.status para estar sempre visível.
        ui.show_error(failure)
        session.save_ai_failure(draft, failure.kind)

    if session.get("ai_failure") in api.AI_FAILURES:
        _manual_registration()


def _step_review(triage: dict) -> None:
    cats = {c["value"]: c for c in api.categories()}
    st.markdown(f"### {triage['category_icon']} {triage['title']}")
    st.html(ui.urgency_badge(triage["urgency"]))

    if triage.get("safety_alert"):
        st.error(f"**Atenção, risco à segurança:** {triage['safety_alert']}", icon="🚨")

    similar = triage.get("similar_open", 0)
    if similar:
        plural = "relatos parecidos ainda abertos" if similar > 1 else "relato parecido ainda aberto"
        st.info(f"**Já existe{'m' if similar > 1 else ''} {similar} {plural} perto deste local.** "
                "Seu relato soma força a eles e ajuda a prefeitura a priorizar.", icon="👥")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Tipo de problema**")
        st.write(f"{triage['category_icon']} {triage['category_label']}")
        st.markdown("**Quem vai cuidar**")
        st.write(f"🏛️ {triage['department']}")
        st.markdown("**Prazo para primeira resposta**")
        hours = triage["response_deadline_hours"]
        st.write(f"⏱️ até {hours} horas" if hours < 48 else f"⏱️ até {hours // 24} dias")
    with c2:
        st.markdown("**Resumo**")
        st.write(triage["summary"])
        loc = triage.get("location")
        if loc:
            st.markdown("**Local encontrado pelo CEP**")
            st.write(f"📍 {loc['street']}, {loc['neighborhood']} – {loc['city']}/{loc['state']}")

    st.markdown("**O que você pode fazer agora**")
    for tip in triage["citizen_guidance"]:
        st.markdown(f"- {tip}")
    ui.read_aloud_button(f"{triage['title']}. {triage['summary']}. " + ". ".join(triage["citizen_guidance"]))

    conf = float(triage["confidence"])
    st.progress(conf, text=f"Segurança da IA nesta classificação: {conf:.0%}")
    if conf < 0.6:
        st.info("A IA não teve certeza. Confira com atenção e corrija se precisar.", icon="🤔")
    if triage.get("anonymized"):
        st.caption("🔒 Removemos automaticamente dados pessoais (CPF, e-mail ou telefone) antes da análise.")

    st.divider()
    st.markdown("#### A classificação está correta?")
    st.caption("Você tem a palavra final: nada é enviado à prefeitura sem a sua confirmação.")
    choice = st.radio("Sua avaliação", ["Sim, está correta", "Não, quero corrigir"], horizontal=True,
                      label_visibility="collapsed", key="review_choice")
    final_cat, final_urg = triage["category"], triage["urgency"]
    if choice.startswith("Não"):
        c1, c2 = st.columns(2)
        final_cat = _category_picker(cats, triage["category"], "fix_cat", c1)
        final_urg = _urgency_picker(triage["urgency"], "fix_urg", c2)

    b1, b2 = st.columns([2, 1])
    if b1.button("✅ Confirmar e enviar à prefeitura", type="primary", width="stretch"):
        _submit(triage, final_cat, final_urg)
    if b2.button("↩️ Voltar e editar", width="stretch"):
        session.back_to_edit()
        st.rerun()


def _step_done(report: dict) -> None:
    st.success(f"Relato registrado! Seu protocolo é **{report['protocol']}**", icon="🎉")
    st.markdown("Anote o protocolo: com ele você acompanha o andamento na aba **Meus relatos**. "
                "O endereço desta página também guarda seus protocolos: salve-o nos favoritos.")
    ui.report_card(report)

    if not report.get("ai_used", True):
        if st.button("➕ Fazer outro relato"):
            session.new_report()
            st.rerun()
        return

    st.markdown("#### A orientação da Zela foi útil?")
    if report["protocol"] in session.get("feedback_given"):
        st.info("Obrigado pela avaliação! Ela ajuda a melhorar o assistente.", icon="🙏")
    else:
        comment = st.text_input("Comentário (opcional)", max_chars=300, key="fb_comment",
                                placeholder="Ex.: a categoria estava certa, mas o prazo é longo")
        c1, c2, _ = st.columns([1, 1, 2])
        for col, useful, label in ((c1, True, "👍 Foi útil"), (c2, False, "👎 Não ajudou")):
            if col.button(label, width="stretch", key=f"fb_{useful}"):
                try:
                    api.feedback(report["protocol"], useful, comment or None)
                    session.mark_feedback(report["protocol"], useful)
                    st.rerun()
                except api.ApiError as err:
                    ui.show_error(err, retry_hint=False)

    if st.button("➕ Fazer outro relato"):
        session.new_report()
        st.rerun()


def render() -> None:
    step = session.get("step")
    ui.steps(step)
    if step == 1:
        _step_describe()
    elif step == 2 and session.get("triage"):
        _step_review(session.get("triage"))
    elif step == 3 and session.get("last_report"):
        _step_done(session.get("last_report"))
    else:
        session.new_report()
        st.rerun()
