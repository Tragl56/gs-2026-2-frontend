"""Dados de DEMONSTRAÇÃO (fictícios) para o painel não abrir vazio.

Ativado com SEED_DEMO_DATA=true e somente quando o banco está vazio.
"""
import random
from datetime import datetime, timedelta, timezone

from app.providers.repository import ReportRepository
from app.schemas.report import CATEGORY_INFO, Category, Location, Status, Urgency

_NEIGHBORHOODS = ["Bela Vista", "Sé", "Pinheiros", "Itaquera", "Capão Redondo", "Santana", "Mooca", "Butantã"]
_SAMPLES = {
    Category.buraco: "Buraco grande na pista, motos desviando",
    Category.iluminacao: "Poste apagado deixa a rua escura à noite",
    Category.lixo: "Entulho descartado na calçada há uma semana",
    Category.alagamento: "Rua alaga toda vez que chove forte",
    Category.arvore: "Galho grande pendurado sobre a calçada",
    Category.calcada: "Calçada quebrada impede passagem de cadeirante",
    Category.sinalizacao: "Semáforo piscando amarelo no cruzamento",
    Category.outro: "Ponto de ônibus sem cobertura",
}
_WEIGHTS = [Urgency.baixa] * 2 + [Urgency.media] * 4 + [Urgency.alta] * 3 + [Urgency.critica]


def seed_if_empty(repo: ReportRepository, n: int = 60) -> None:
    if repo.list():
        return
    rng = random.Random(42)
    now = datetime.now(timezone.utc)
    for _ in range(n):
        cat = rng.choice(list(Category))
        urg = rng.choice(_WEIGHTS)
        corrected = rng.random() < 0.15
        report = repo.add({
            "description": f"[DEMO] {_SAMPLES[cat]}",
            "cep": None,
            "reference": None,
            "location": Location(cep="00000000", neighborhood=rng.choice(_NEIGHBORHOODS), city="São Paulo", state="SP"),
            "ai_category": cat,
            "ai_urgency": rng.choice(_WEIGHTS) if corrected else urg,
            "final_category": cat,
            "final_urgency": urg,
            "corrected_by_citizen": corrected,
            "category_label": CATEGORY_INFO[cat]["label"],
            "department": CATEGORY_INFO[cat]["department"],
            "title": _SAMPLES[cat],
            "summary": _SAMPLES[cat] + ".",
        })
        age = timedelta(days=rng.randint(0, 29), hours=rng.randint(0, 23))
        status = rng.choices(list(Status), weights=[5, 3, 6, 1])[0]
        repo.update(report.model_copy(update={"created_at": now - age, "status": status}))
