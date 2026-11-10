"""Dados abertos: ViaCEP (https://viacep.com.br) para localizar o relato.

Falhas aqui nunca derrubam o fluxo: sem localização, a triagem segue normalmente.
"""
from __future__ import annotations

import logging
from functools import lru_cache

import httpx

from app.config import get_settings
from app.schemas.report import Location

log = logging.getLogger(__name__)


@lru_cache(maxsize=512)
def lookup_cep(cep: str) -> Location | None:
    settings = get_settings()
    try:
        resp = httpx.get(f"{settings.viacep_url}/{cep}/json/", timeout=settings.open_data_timeout_seconds)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.info("ViaCEP indisponível para %s: %s", cep, exc)
        return None
    if data.get("erro"):
        return None
    return Location(
        cep=cep,
        street=data.get("logradouro", ""),
        neighborhood=data.get("bairro", ""),
        city=data.get("localidade", ""),
        state=data.get("uf", ""),
    )
