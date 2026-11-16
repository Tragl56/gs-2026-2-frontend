"""Endpoints de visão com um serviço falso (os testes não carregam PyTorch nem o modelo)."""
from app.schemas.vision import (
    MonitorResult,
    SequenceItem,
    SequenceResult,
    VisionQuality,
    VisionResult,
    VisionSummary,
)
from app.vision.service import VisionInputError
from tests.conftest import TOKEN, make_client

JPEG = b"\xff\xd8\xff\xe0fake-jpeg"
SUMMARY = VisionSummary(crack_detected=True, confidence=0.97, threshold=0.94, area_fraction=0.3, regions=2,
                        model="resnet18_campo", quality_alerts=[], thumbnail_jpeg="aGVsbG8=")


class FakeVision:
    def info(self):
        return {"model": "resnet18_campo", "threshold": 0.94}

    def inspect(self, data: bytes) -> VisionResult:
        if data == b"corrompido":
            raise VisionInputError("Não conseguimos ler a imagem.")
        return VisionResult(summary=SUMMARY, regions=[], windows=4, window_px=227, latency_ms=12.0, image_width=454,
                            image_height=454, device="CPU", annotated_jpeg="aGVsbG8=",
                            quality=VisionQuality(sharpness=10, brightness=150, contrast=30, alerts=[]))

    def sequence(self, files):
        return SequenceResult(items=[SequenceItem(filename=n, summary=SUMMARY, latency_ms=10) for n, _ in files],
                              images=len(files), flagged=len(files), images_per_second=50, latency_ms_mean=10,
                              device="CPU", threshold=0.94)

    def monitor(self, data, every=1):
        return MonitorResult(frames=10, analyzed_frames=10, resolution="1024x576", windows_per_frame=18, fps_pipeline=8,
                             latency_ms_mean=60, latency_ms_p95=80, alert_frames=4, threshold=0.94, device="CPU",
                             model="resnet18_campo", events=[], timeline=[])


def _client():
    return make_client(vision=FakeVision())


def test_health_reports_vision_ready():
    with _client() as c:
        assert c.get("/health").json()["vision_ready"] is True


def test_vision_unavailable_returns_503(client):
    resp = client.post("/api/v1/vision/inspect", files={"file": ("a.jpg", JPEG, "image/jpeg")})
    assert resp.status_code == 503 and resp.json()["detail"]["code"] == "vision_unavailable"


def test_inspect_photo():
    with _client() as c:
        resp = c.post("/api/v1/vision/inspect", files={"file": ("a.jpg", JPEG, "image/jpeg")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["crack_detected"] is True and body["summary"]["confidence"] == 0.97


def test_inspect_rejects_non_image_and_unreadable():
    with _client() as c:
        assert c.post("/api/v1/vision/inspect", files={"file": ("a.txt", b"oi", "text/plain")}).status_code == 415
        bad = c.post("/api/v1/vision/inspect", files={"file": ("a.jpg", b"corrompido", "image/jpeg")})
        assert bad.status_code == 422 and bad.json()["detail"]["code"] == "invalid_input"


def test_monitor_and_sequence_are_manager_only():
    with _client() as c:
        video = {"file": ("v.mp4", b"video", "video/mp4")}
        assert c.post("/api/v1/vision/monitor", files=video).status_code == 401
        ok = c.post("/api/v1/vision/monitor", files=video, headers={"X-Manager-Token": TOKEN})
        assert ok.status_code == 200 and ok.json()["fps_pipeline"] == 8
        files = [("files", ("1.jpg", JPEG, "image/jpeg")), ("files", ("2.jpg", JPEG, "image/jpeg"))]
        assert c.post("/api/v1/vision/sequence", files=files).status_code == 401
        seq = c.post("/api/v1/vision/sequence", files=files, headers={"X-Manager-Token": TOKEN})
        assert seq.status_code == 200 and seq.json()["flagged"] == 2


def test_report_keeps_vision_summary_for_the_manager():
    with _client() as c:
        report_in = {"description": "Rachadura grande no muro da escola, aumentou depois da chuva"}
        triage = c.post("/api/v1/reports/analyze", json=report_in).json()
        assert triage["category"] == "fissura_estrutura"
        body = {"input": report_in, "triage": triage, "final_category": triage["category"],
                "final_urgency": triage["urgency"], "vision": SUMMARY.model_dump()}
        created = c.post("/api/v1/reports", json=body).json()
        assert created["vision"]["confidence"] == 0.97
        queue = c.get("/api/v1/manager/reports", headers={"X-Manager-Token": TOKEN}).json()
        assert queue[0]["vision"]["crack_detected"] is True
        public = c.get("/api/v1/stats/public").json()
        assert "vision" not in public[0]  # foto não vai para o painel público


def test_demo_seed_covers_every_category():
    from app.providers.repository import SQLiteReportRepository
    from app.providers.seed import seed_if_empty

    seed_if_empty(SQLiteReportRepository(":memory:"))  # quebrava ao criar uma categoria sem exemplo
