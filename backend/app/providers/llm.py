"""Acesso ao LLM. Único ponto do sistema que fala com o provedor de IA.

- GeminiProvider: chama o Gemini com saída estruturada (response_schema = LLMTriage).
- FallbackProvider: cadeia de modelos reservas com nova tentativa (picos de demanda do Google).
- MockProvider: heurística por palavras-chave, para testes e demonstração sem chave.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Protocol

from pydantic import ValidationError

from app.config import Settings
from app.schemas.report import CATEGORY_INFO, Category, LLMTriage, Urgency

log = logging.getLogger(__name__)


class LLMError(Exception):
    """O provedor de IA falhou (fora do ar, timeout, cota, chave inválida)."""


class LLMInvalidResponse(Exception):
    """O provedor respondeu, mas fora do formato esperado."""


class LLMProvider(Protocol):
    def triage(self, system_prompt: str, user_prompt: str) -> LLMTriage: ...


class GeminiProvider:
    def __init__(self, client, model: str):
        from google.genai import types  # import tardio: testes não precisam do SDK

        self._types = types
        self._model = model
        self._client = client

    @property
    def name(self) -> str:
        return self._model

    def triage(self, system_prompt: str, user_prompt: str) -> LLMTriage:
        types = self._types
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=LLMTriage,
                    temperature=0.2,
                ),
            )
        except Exception as exc:  # rede, timeout, 4xx/5xx do provedor
            log.warning("Falha no %s: %s", self._model, str(exc)[:200])
            raise LLMError(str(exc)) from exc

        text = response.text or ""
        try:
            return LLMTriage.model_validate_json(text)
        except ValidationError as exc:
            log.warning("Resposta inválida do %s: %s", self._model, text[:300])
            raise LLMInvalidResponse(str(exc)) from exc


class FallbackProvider:
    """Tenta cada modelo em ordem: se um estiver sobrecarregado, lento ou responder fora
    do formato, passa para o próximo. O cidadão só vê erro se todos falharem."""

    def __init__(self, providers: list[LLMProvider], *, retry_rounds: int = 1, retry_wait: float = 2.0,
                 budget_seconds: float = 25.0, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        if not providers:
            raise LLMError("Nenhum modelo configurado")
        self._providers = providers
        self._retry_rounds = retry_rounds
        self._retry_wait = retry_wait
        self._budget = budget_seconds  # nova rodada só se ainda houver tempo (o front espera ~45s)
        self._sleep = sleep
        self._clock = clock
        self.last_used: str | None = None  # qual modelo respondeu (para logs e testes)

    def triage(self, system_prompt: str, user_prompt: str) -> LLMTriage:
        last: Exception | None = None
        self.last_used = None
        started = self._clock()
        for round_ in range(self._retry_rounds + 1):
            if round_:
                if self._clock() - started + self._retry_wait > self._budget:
                    break
                log.info("Todos os modelos falharam; nova rodada em %.0fs", self._retry_wait)
                self._sleep(self._retry_wait)
            for provider in self._providers:
                try:
                    result = provider.triage(system_prompt, user_prompt)
                    self.last_used = getattr(provider, "name", type(provider).__name__)
                    return result
                except (LLMError, LLMInvalidResponse) as exc:
                    last = exc
                    log.info("Modelo %s falhou; tentando o próximo", getattr(provider, "name", provider))
        raise last  # type: ignore[misc]


_KEYWORDS: list[tuple[Category, tuple[str, ...]]] = [
    (Category.alagamento, ("alag", "enchente", "inunda", "água subindo", "bueiro entupido")),
    (Category.arvore, ("árvore", "arvore", "galho", "tronco")),
    (Category.iluminacao, ("poste", "lâmpada", "lampada", "escuro", "iluminação", "iluminacao", "luz apagada")),
    (Category.buraco, ("buraco", "cratera", "asfalto")),
    (Category.lixo, ("lixo", "entulho", "descarte", "sujeira")),
    (Category.calcada, ("calçada", "calcada", "cadeirante", "rampa", "piso tátil")),
    (Category.sinalizacao, ("semáforo", "semaforo", "placa", "faixa de pedestre", "sinal")),
]
_CRITICAL = ("fio", "choque", "desab", "caiu", "caindo", "ferido", "criança", "crianca", "idoso", "carro preso")


class MockProvider:
    """Classificador determinístico usado sem chave de API e nos testes."""

    def triage(self, system_prompt: str, user_prompt: str) -> LLMTriage:
        # Considera só o relato (entre aspas triplas), não a lista de categorias do prompt.
        parts = user_prompt.split('"""')
        text = (parts[1] if len(parts) >= 3 else user_prompt).lower()
        category = next((c for c, words in _KEYWORDS if any(w in text for w in words)), Category.outro)
        critical = any(w in text for w in _CRITICAL)
        urgency = Urgency.critica if critical else (
            Urgency.alta if category in (Category.alagamento, Category.arvore) else Urgency.media
        )
        return LLMTriage(
            category=category,
            urgency=urgency,
            title=f"Relato: {CATEGORY_INFO[category]['label'].lower()}",
            summary="Classificação automática de demonstração (modo sem IA).",
            citizen_guidance=[
                "Guarde o número de protocolo para acompanhar o atendimento.",
                "Se possível, evite a área até o problema ser resolvido.",
            ],
            safety_alert="Mantenha distância e ligue 199 (Defesa Civil) se houver risco imediato." if critical else "",
            confidence=0.55,
        )


def build_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider.lower() == "mock":
        return MockProvider()
    if not settings.gemini_api_key:
        raise LLMError("GEMINI_API_KEY não configurada")
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(timeout=int(settings.llm_timeout_seconds * 1000)),
    )
    models = [m.strip() for m in settings.gemini_model.split(",") if m.strip()]
    return FallbackProvider([GeminiProvider(client, m) for m in models])
