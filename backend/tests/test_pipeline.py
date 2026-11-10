from app.pipelines.triage import TriagePipeline, anonymize, apply_rules, build_user_prompt, manual_title
from app.providers.llm import FallbackProvider, LLMError, LLMInvalidResponse, MockProvider
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


class _Broken:
    name = "quebrado"

    def __init__(self, exc):
        self.exc = exc

    def triage(self, *_):
        raise self.exc


def test_fallback_uses_next_model_when_first_is_overloaded():
    mock = MockProvider()
    mock.name = "reserva"
    chain = FallbackProvider([_Broken(LLMError("503 alta demanda")), _Broken(LLMInvalidResponse("json")), mock])
    result = chain.triage("s", '"""Buraco enorme na avenida"""')
    assert result.category == Category.buraco
    assert chain.last_used == "reserva"


def test_fallback_retries_after_a_short_wait():
    calls, waits = [], []

    class FlakyOnce:
        name = "instavel"

        def triage(self, s, u):
            calls.append(1)
            if len(calls) == 1:
                raise LLMError("503 alta demanda")
            return MockProvider().triage(s, u)

    chain = FallbackProvider([FlakyOnce()], retry_rounds=1, retry_wait=2, sleep=waits.append)
    assert chain.triage("s", '"""Poste apagado na rua"""').category == Category.iluminacao
    assert waits == [2] and len(calls) == 2


def test_fallback_skips_retry_when_out_of_time():
    ticks = iter([0, 30])  # início, depois de a 1ª rodada já ter gasto 30s
    waits = []
    chain = FallbackProvider([_Broken(LLMError("504"))], retry_rounds=1, retry_wait=2, budget_seconds=25,
                             sleep=waits.append, clock=lambda: next(ticks))
    try:
        chain.triage("s", "u")
    except LLMError:
        pass
    assert waits == []


def test_fallback_raises_last_error_when_all_fail():
    chain = FallbackProvider([_Broken(LLMError("504")), _Broken(LLMError("503"))], retry_rounds=0)
    try:
        chain.triage("s", "u")
    except LLMError as exc:
        assert "503" in str(exc)
    else:
        raise AssertionError("deveria falhar")


def test_manual_title_truncates_long_text():
    title = manual_title("palavra " * 30)
    assert len(title) <= 60 and title.endswith("…")


def test_rate_limiter_blocks_then_releases():
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    assert limiter.allow("ip", now=0) and limiter.allow("ip", now=1)
    assert not limiter.allow("ip", now=2)
    assert limiter.allow("outro-ip", now=2)
    assert limiter.allow("ip", now=61)


def test_build_repository_picks_backend(monkeypatch):
    from app.providers import repository as repo_mod

    assert isinstance(repo_mod.build_repository("", ":memory:"), repo_mod.SQLiteReportRepository)

    monkeypatch.setattr(repo_mod.PostgresReportRepository, "__init__", lambda self, url: setattr(self, "url", url))
    pg = repo_mod.build_repository("postgresql://u:p@host/db", ":memory:")
    assert isinstance(pg, repo_mod.PostgresReportRepository) and pg.url.startswith("postgresql://")
