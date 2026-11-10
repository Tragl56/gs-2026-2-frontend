"""Testes da lógica do front (sem subir a interface)."""
import pandas as pd

from features.dashboard import apply_filters, to_frame
from features.manager import cluster_sizes, priority_key
from features.validation import normalize_protocol, validate_report

LONG = "Buraco enorme na rua principal do bairro"


def test_valid_report_has_no_errors():
    assert validate_report(LONG, "01310-100", "perto da escola", True) == []


def test_short_description_and_missing_consent():
    errors = validate_report("buraco", "", "", False)
    assert any("curta" in e for e in errors)
    assert any("caixa" in e for e in errors)


def test_bad_cep():
    assert any("CEP" in e for e in validate_report(LONG, "123", "", True))


def test_protocol_normalization():
    assert normalize_protocol(" zla-20261106-00012 ") == "ZLA-20261106-00012"
    assert normalize_protocol("ZLA-123") is None
    assert normalize_protocol("<script>") is None


def _record(**kw):
    base = {"created_at": "2026-11-09T12:00:00+00:00", "category_label": "Buraco na via",
            "urgency": "alta", "status": "aberto", "neighborhood": "Sé"}
    return {**base, **kw}


def test_to_frame_and_filters():
    df = to_frame([_record(), _record(urgency="baixa"), _record(created_at="2026-01-01T00:00:00+00:00")])
    assert set(df["urgency_label"]) == {"Alta", "Baixa"}
    now = pd.Timestamp("2026-11-10T12:00:00", tz="America/Sao_Paulo")
    view = apply_filters(df, 7, ["alta"], ["Buraco na via"], ["aberto"], now=now)
    assert len(view) == 1


def _report(proto, urgency, cat="buraco_via", hood="Sé", status="aberto", created="2026-11-09T10:00:00+00:00"):
    return {"protocol": proto, "final_urgency": urgency, "final_category": cat, "status": status,
            "location": {"neighborhood": hood}, "created_at": created}


def test_manager_priority_urgency_then_recurrence():
    reports = [
        _report("A", "media", cat="lixo_entulho"),
        _report("B", "alta", cat="iluminacao", hood="Mooca"),
        _report("C", "alta"), _report("D", "alta"),  # 2 buracos na Sé: problema recorrente
        _report("E", "alta", status="resolvido"),
    ]
    clusters = cluster_sizes(reports)
    order = [r["protocol"] for r in sorted(reports[:4], key=lambda r: priority_key(r, clusters))]
    assert order == ["C", "D", "B", "A"]
    assert clusters[("buraco_via", "Sé")] == 2  # o resolvido não conta
