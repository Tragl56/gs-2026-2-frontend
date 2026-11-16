"""Modelos de saída do módulo de visão (fissuras em concreto)."""
from pydantic import BaseModel, Field


class VisionSummary(BaseModel):
    """Resumo que acompanha o relato e aparece na fila da prefeitura."""
    crack_detected: bool = Field(..., description="Confiança acima do limiar de triagem: inspeção recomendada")
    confidence: float = Field(..., ge=0, le=1)
    threshold: float = Field(..., ge=0, le=1)
    area_fraction: float = Field(..., ge=0, le=1, description="Fração das janelas da foto acima do limiar")
    regions: int = Field(..., ge=0)
    model: str = Field(..., max_length=60)
    quality_alerts: list[str] = Field(default_factory=list, max_length=5)
    thumbnail_jpeg: str | None = Field(default=None, max_length=400_000, description="Foto anotada (base64, até 480 px)")


class VisionRegion(BaseModel):
    x: int
    y: int
    w: int
    h: int
    confidence: float


class VisionQuality(BaseModel):
    sharpness: float
    brightness: float
    contrast: float
    alerts: list[str]


class VisionResult(BaseModel):
    summary: VisionSummary
    regions: list[VisionRegion]
    windows: int
    window_px: int
    latency_ms: float
    image_width: int
    image_height: int
    device: str
    quality: VisionQuality
    annotated_jpeg: str
    gradcam_jpeg: str | None = None


class SequenceItem(BaseModel):
    filename: str
    summary: VisionSummary | None = None
    latency_ms: float = 0.0
    error: str | None = None


class SequenceResult(BaseModel):
    items: list[SequenceItem]
    images: int
    flagged: int
    images_per_second: float
    latency_ms_mean: float
    device: str
    threshold: float


class MonitorFrame(BaseModel):
    frame: int
    t: float
    confidence: float
    smoothed: float
    alert: bool


class MonitorEvent(BaseModel):
    start_s: float
    end_s: float
    max_confidence: float


class MonitorResult(BaseModel):
    frames: int
    analyzed_frames: int
    resolution: str
    windows_per_frame: int
    fps_pipeline: float
    latency_ms_mean: float
    latency_ms_p95: float
    alert_frames: int
    threshold: float
    device: str
    model: str
    events: list[MonitorEvent]
    timeline: list[MonitorFrame]
    video_mp4: str | None = None
