import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.pipelines.triage import TriagePipeline
from app.providers import open_data
from app.providers.llm import LLMError, LLMInvalidResponse, MockProvider
from app.providers.repository import ReportRepository
from app.schemas.report import Location

TOKEN = "token-de-teste"
PAULISTA = Location(cep="01310100", street="Avenida Paulista", neighborhood="Bela Vista", city="São Paulo", state="SP")


def fake_lookup(cep: str):
    return PAULISTA if cep == "01310100" else None


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Os testes nunca acessam a internet: ViaCEP é simulado."""
    monkeypatch.setattr(open_data, "lookup_cep", fake_lookup)
    monkeypatch.setattr("app.pipelines.triage.lookup_cep", fake_lookup)
    monkeypatch.setattr("app.routers.reports.lookup_cep", fake_lookup)
    monkeypatch.setattr("app.routers.deps.get_settings", lambda: Settings(manager_token=TOKEN, _env_file=None))


def make_client(provider=None, rate_limit: int = 100) -> TestClient:
    settings = Settings(llm_provider="mock", manager_token=TOKEN, cors_origins="http://localhost:8501",
                        analyze_rate_limit_per_minute=rate_limit, _env_file=None)
    app = create_app(settings, repo=ReportRepository(":memory:"),
                     pipeline=TriagePipeline(provider or MockProvider()))
    return TestClient(app)


@pytest.fixture
def client():
    with make_client() as c:
        yield c


class FailingProvider:
    def __init__(self, exc):
        self.exc = exc

    def triage(self, *_):
        raise self.exc


@pytest.fixture
def failing_client():
    def make(exc):
        return make_client(FailingProvider(exc))
    return make


__all__ = ["TOKEN", "LLMError", "LLMInvalidResponse", "make_client"]
