"""Validação da entrada do cidadão no front (o back-end valida de novo com Pydantic).

Funções puras, sem Streamlit: testáveis com pytest.
"""
from __future__ import annotations

import re

from config import DESCRIPTION_MAX, DESCRIPTION_MIN, REFERENCE_MAX

_CEP_RE = re.compile(r"^\d{5}-?\d{3}$")
_PROTOCOL_RE = re.compile(r"^ZLA-\d{8}-\d{5}$")


def validate_report(description: str, cep: str, reference: str, consent: bool) -> list[str]:
    errors = []
    text = " ".join(description.split())
    if not text:
        errors.append("Conte o que está acontecendo no campo **Descreva o problema**.")
    elif len(text) < DESCRIPTION_MIN:
        errors.append(f"A descrição está curta: escreva pelo menos {DESCRIPTION_MIN} caracteres "
                      f"(faltam {DESCRIPTION_MIN - len(text)}).")
    elif len(text) > DESCRIPTION_MAX:
        errors.append(f"A descrição passou de {DESCRIPTION_MAX} caracteres.")
    if cep.strip() and not _CEP_RE.match(cep.strip()):
        errors.append("O CEP deve ter 8 números, por exemplo 01310-100.")
    if len(reference) > REFERENCE_MAX:
        errors.append(f"O ponto de referência deve ter até {REFERENCE_MAX} caracteres.")
    if not consent:
        errors.append("Marque a caixa confirmando que o relato não contém dados pessoais de terceiros.")
    return errors


def normalize_protocol(value: str) -> str | None:
    """Devolve o protocolo em maiúsculas se o formato for válido (ZLA-AAAAMMDD-NNNNN)."""
    value = value.strip().upper()
    return value if _PROTOCOL_RE.match(value) else None
