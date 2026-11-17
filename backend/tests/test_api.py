from tests.conftest import TOKEN, LLMError, LLMInvalidResponse, make_client

VALID = {"description": "Buraco enorme na avenida, carros desviando pela contramão", "cep": "01310-100"}


def analyze_and_confirm(client, **overrides):
    triage = client.post("/api/v1/reports/analyze", json=VALID).json()
    body = {"input": VALID, "triage": triage,
            "final_category": overrides.get("category", triage["category"]),
            "final_urgency": overrides.get("urgency", triage["urgency"])}
    return client.post("/api/v1/reports", json=body)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "ai_ready": True}


def test_categories(client):
    data = client.get("/api/v1/categories").json()
    assert any(c["value"] == "buraco_via" for c in data)


def test_analyze_returns_structured_triage(client):
    resp = client.post("/api/v1/reports/analyze", json=VALID)
    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] == "buraco_via"
    assert body["location"]["neighborhood"] == "Bela Vista"
    assert {"urgency", "department", "citizen_guidance", "response_deadline_hours", "similar_open"} <= body.keys()


def test_analyze_rejects_short_text(client):
    resp = client.post("/api/v1/reports/analyze", json={"description": "buraco"})
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "invalid_input"


def test_analyze_rejects_bad_cep(client):
    resp = client.post("/api/v1/reports/analyze", json={**VALID, "cep": "123"})
    assert resp.status_code == 422
    assert "CEP" in resp.json()["detail"]["message"]


def test_confirm_creates_protocol_and_tracks_correction(client):
    resp = analyze_and_confirm(client, urgency="critica")
    assert resp.status_code == 201
    report = resp.json()
    assert report["protocol"].startswith("ZLA-")
    assert report["corrected_by_citizen"] is True
    assert report["ai_used"] is True
    assert report["cep"] == "01310100"


def test_similar_reports_are_counted(client):
    assert client.post("/api/v1/reports/analyze", json=VALID).json()["similar_open"] == 0
    analyze_and_confirm(client)
    analyze_and_confirm(client)
    assert client.post("/api/v1/reports/analyze", json=VALID).json()["similar_open"] == 2


def test_resolved_reports_do_not_count_as_similar(client):
    p = analyze_and_confirm(client).json()["protocol"]
    client.patch(f"/api/v1/manager/reports/{p}/status", headers={"X-Manager-Token": TOKEN},
                 json={"status": "resolvido"})
    assert client.post("/api/v1/reports/analyze", json=VALID).json()["similar_open"] == 0


def test_manual_report_without_ai(client):
    resp = client.post("/api/v1/reports", json={"input": VALID, "triage": None,
                                                "final_category": "buraco_via", "final_urgency": "alta"})
    assert resp.status_code == 201
    report = resp.json()
    assert report["ai_used"] is False and report["ai_category"] is None
    assert report["location"]["neighborhood"] == "Bela Vista"
    assert report["title"].startswith("Buraco enorme")


def test_citizen_sees_only_own_reports(client):
    p1 = analyze_and_confirm(client).json()["protocol"]
    analyze_and_confirm(client)
    mine = client.get("/api/v1/reports", params={"protocols": p1}).json()
    assert [r["protocol"] for r in mine] == [p1]


def test_public_stats_hide_personal_text(client):
    analyze_and_confirm(client)
    records = client.get("/api/v1/stats/public").json()
    assert len(records) == 1
    assert "description" not in records[0] and "cep" not in records[0]


def test_feedback(client):
    p = analyze_and_confirm(client).json()["protocol"]
    resp = client.patch(f"/api/v1/reports/{p}/feedback", json={"useful": False, "comment": "Categoria errada"})
    assert resp.json()["feedback_useful"] is False


def test_feedback_unknown_protocol(client):
    resp = client.patch("/api/v1/reports/ZLA-0-0/feedback", json={"useful": True})
    assert resp.status_code == 404


def test_manager_requires_token(client):
    assert client.get("/api/v1/manager/reports").status_code == 401
    assert client.get("/api/v1/manager/reports", headers={"X-Manager-Token": "errado"}).status_code == 401


def test_manager_updates_status(client):
    p = analyze_and_confirm(client).json()["protocol"]
    resp = client.patch(f"/api/v1/manager/reports/{p}/status", headers={"X-Manager-Token": TOKEN},
                        json={"status": "em_andamento", "manager_note": "Equipe a caminho"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "em_andamento"


def test_llm_down_returns_friendly_503(failing_client):
    with failing_client(LLMError("timeout")) as c:
        resp = c.post("/api/v1/reports/analyze", json=VALID)
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "llm_unavailable"
    assert "timeout" not in resp.text  # não vaza detalhe técnico


def test_llm_invalid_output_returns_502(failing_client):
    with failing_client(LLMInvalidResponse("json quebrado")) as c:
        resp = c.post("/api/v1/reports/analyze", json=VALID)
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "invalid_ai_response"


def test_rate_limit_on_analyze():
    with make_client(rate_limit=2) as c:
        codes = [c.post("/api/v1/reports/analyze", json=VALID).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_cors_is_restrictive(client):
    resp = client.options("/api/v1/categories", headers={"Origin": "https://site-malicioso.com",
                                                           "Access-Control-Request-Method": "GET"})
    assert resp.headers.get("access-control-allow-origin") != "*"
    assert "site-malicioso" not in resp.headers.get("access-control-allow-origin", "")
