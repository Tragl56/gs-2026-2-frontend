from app.pipelines.triage import TriagePipeline, anonymize, apply_rules, build_user_prompt, manual_title
from app.providers.llm import MockProvider
from app.providers.rate_limit import RateLimiter
from app.schemas.report import Category, LLMTriage, ReportInput, Urgency


def test_anonymize_removes_cpf_email_and_phone():
    text, changed = anonymize("Sou Ana, CPF 123.456.789-00, email ana@mail.com, tel (11) 98765-4321")
    assert changed
    assert "123.456.789-00" not in text and "ana@mail.com" not in text and "98765-4321" not in text
    assert "[CPF]" in text and "[EMAIL]" in text and "[TELEFONE]" in text


def test_anonymize_keeps_clean_text():
    text, changed = anonymize("Poste apagado na rua das Flores há uma semana")
    assert not changed
    assert text == "Poste apagado na rua das Flores há uma semana"


def test_safety_alert_raises_low_urgency():
    triage = LLMTriage(category=Category.arvore, urgency=Urgency.baixa, title="t", summary="s",
                       citizen_guidance=["a"], safety_alert="Risco de queda", confidence=0.9)
    assert apply_rules(triage).urgency == Urgency.alta


def test_empty_guidance_gets_default():
    triage = LLMTriage(category=Category.outro, urgency=Urgency.baixa, title="t", summary="s",
                       citizen_guidance=["  "], safety_alert="", confidence=0.5)
    assert len(apply_rules(triage).citizen_guidance) == 1


def test_prompt_lists_allowed_categories():
    prompt = build_user_prompt("Buraco enorme na avenida principal", "perto da escola", None)
    assert "buraco_via" in prompt and "perto da escola" in prompt


def test_pipeline_end_to_end_with_mock():
    result = TriagePipeline(MockProvider()).run(
        ReportInput(description="Fio de poste caiu na calçada e está soltando faísca")
    )
    assert result.urgency == Urgency.critica
    assert result.department
    assert result.response_deadline_hours == 4
    assert result.safety_alert


def test_pipeline_caches_identical_requests():
    calls = []

    class Counting(MockProvider):
        def triage(self, s, u):
            calls.append(u)
            return super().triage(s, u)

    pipeline = TriagePipeline(Counting())
    data = ReportInput(description="Lixo acumulado na esquina há dias, com mau cheiro")
    pipeline.run(data)
    pipeline.run(data)
    assert len(calls) == 1


def test_manual_title_truncates_long_text():
    title = manual_title("palavra " * 30)
    assert len(title) <= 60 and title.endswith("…")


def test_rate_limiter_blocks_then_releases():
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    assert limiter.allow("ip", now=0) and limiter.allow("ip", now=1)
    assert not limiter.allow("ip", now=2)
    assert limiter.allow("outro-ip", now=2)
    assert limiter.allow("ip", now=61)
