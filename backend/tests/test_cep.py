"""CEP: encontrado, inexistente ou ViaCEP fora do ar, e o aviso que chega ao front."""
import httpx

from app.providers import open_data
from tests.conftest import CEP_FORA_DO_AR

BASE = {"description": "Buraco enorme na avenida, carros desviando pela contramão"}


def test_analyze_reports_found_cep(client):
    body = client.post("/api/v1/reports/analyze", json={**BASE, "cep": "01310-100"}).json()
    assert body["cep_status"] == "found" and body["location"]["neighborhood"] == "Bela Vista"


def test_analyze_reports_unknown_cep(client):
    body = client.post("/api/v1/reports/analyze", json={**BASE, "cep": "09750-780"}).json()
    assert body["cep_status"] == "not_found" and body["location"] is None


def test_analyze_reports_viacep_down(client):
    body = client.post("/api/v1/reports/analyze", json={**BASE, "cep": CEP_FORA_DO_AR}).json()
    assert body["cep_status"] == "unavailable" and body["location"] is None


def test_analyze_without_cep_has_no_status(client):
    assert client.post("/api/v1/reports/analyze", json=BASE).json()["cep_status"] is None


class _Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_lookup_status_found_and_not_found(monkeypatch):
    open_data._fetch.cache_clear()
    found = {"logradouro": "Rua A", "bairro": "Sé", "localidade": "São Paulo", "uf": "SP"}
    monkeypatch.setattr(open_data.httpx, "get", lambda url, **_: _Resp({"erro": "true"} if "00000000" in url else found))
    loc, status = open_data.lookup_cep_status("01001000")
    assert status == "found" and loc.neighborhood == "Sé"
    assert open_data.lookup_cep_status("00000000") == (None, "not_found")


def test_viacep_failure_is_not_cached(monkeypatch):
    """Uma queda passageira do ViaCEP não pode deixar o CEP 'sem endereço' para sempre."""
    open_data._fetch.cache_clear()
    calls = []

    def flaky(url, **_):
        calls.append(url)
        if len(calls) == 1:
            raise httpx.ConnectTimeout("timeout")
        return _Resp({"logradouro": "Rua A", "bairro": "Sé", "localidade": "São Paulo", "uf": "SP"})

    monkeypatch.setattr(open_data.httpx, "get", flaky)
    assert open_data.lookup_cep_status("01001000") == (None, "unavailable")
    assert open_data.lookup_cep_status("01001000")[1] == "found"
    assert len(calls) == 2
