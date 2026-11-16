"""Dados abertos: ViaCEP (https://viacep.com.br) para localizar o relato.

Falhas aqui nunca derrubam o fluxo: sem localização, a triagem segue normalmente.
O status diz ao cidadão o que aconteceu com o CEP:
- "found": endereço encontrado;
- "not_found": o ViaCEP respondeu que o CEP não existe (provável erro de digitação);
- "unavailable": não foi possível consultar agora (rede ou ViaCEP fora do ar).
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Literal

import httpx

from app.config import get_settings
from app.schemas.report import Location

log = logging.getLogger(__name__)

CepStatus = Literal["found", "not_found", "unavailable"]


class _ViaCepUnavailable(Exception):
    """Falha temporária: não entra no cache, para a próxima consulta tentar de novo."""


@lru_cache(maxsize=512)
def _fetch(cep: str) -> Location | None:
    settings = get_settings()
    try:
        resp = httpx.get(f"{settings.viacep_url}/{cep}/json/", timeout=settings.open_data_timeout_seconds)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.info("ViaCEP indisponível para %s: %s", cep, exc)
        raise _ViaCepUnavailable from exc
    if data.get("erro"):
        return None
    return Location(
        cep=cep,
        street=data.get("logradouro", ""),
        neighborhood=data.get("bairro", ""),
        city=data.get("localidade", ""),
        state=data.get("uf", ""),
    )


def lookup_cep_status(cep: str) -> tuple[Location | None, CepStatus]:
    try:
        location = _fetch(cep)
    except _ViaCepUnavailable:
        return None, "unavailable"
    return location, ("found" if location else "not_found")


def lookup_cep(cep: str) -> Location | None:
    return lookup_cep_status(cep)[0]
