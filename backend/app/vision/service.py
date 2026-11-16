"""Serviço de visão usado pelos endpoints: carrega o modelo uma vez e devolve resultados prontos para o front.

Sem PyTorch/OpenCV instalados (ex.: deploy serverless na Vercel), `build_vision` devolve None e a API
segue funcionando; os endpoints de visão respondem 503 `vision_unavailable`.
"""
from __future__ import annotations

import base64
import logging
import tempfile
import threading
import time
from pathlib import Path

from app.schemas.vision import (
    MonitorEvent,
    MonitorFrame,
    MonitorResult,
    SequenceItem,
    SequenceResult,
    VisionQuality,
    VisionRegion,
    VisionResult,
    VisionSummary,
)

log = logging.getLogger("zela.vision")


class VisionInputError(ValueError):
    """Arquivo enviado não é uma imagem/vídeo legível."""


class VisionService:
    def __init__(self, models_dir: str | Path, max_frames: int = 600):
        import cv2  # noqa: F401  (falha cedo se a dependência não existir)

        from app.vision.detector import CrackDetector

        self.det = CrackDetector(models_dir)
        self.max_frames = max_frames
        # Uma GPU, um modelo: requisições simultâneas são serializadas (o Grad-CAM usa hooks no modelo).
        self._lock = threading.RLock()
        log.info("Visão pronta: %s em %s (limiar %.2f)", self.det.name, self.det.device_name, self.det.threshold)

    # ------------------------------------------------------------ info
    def info(self) -> dict:
        c = self.det.cfg
        return {"model": self.det.name, "arch": self.det.arch, "device": self.det.device_name,
                "input_px": self.det.size, "threshold": self.det.threshold, "temperature": self.det.temperature,
                "field_augmentation": bool(c.get("field_aug", False))}

    # --------------------------------------------------------- imagens
    @staticmethod
    def _decode(data: bytes):
        import cv2
        import numpy as np

        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise VisionInputError("Não conseguimos ler a imagem. Envie um arquivo JPG ou PNG.")
        h, w = img.shape[:2]
        s = 2048 / max(h, w)  # limita o custo em fotos de celular muito grandes
        if s < 1:
            img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    @staticmethod
    def _jpeg(img, max_side: int | None = None, quality: int = 85) -> str:
        import cv2

        if max_side and max(img.shape[:2]) > max_side:
            s = max_side / max(img.shape[:2])
            img = cv2.resize(img, (int(img.shape[1] * s), int(img.shape[0] * s)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", img[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, quality])
        return base64.b64encode(buf.tobytes()).decode()

    def inspect(self, data: bytes) -> VisionResult:
        with self._lock:
            return self._inspect(data)

    def _inspect(self, data: bytes) -> VisionResult:
        from app.vision.detector import draw, heatmap, image_quality, overlay_cam, regions

        img = self._decode(data)
        res = self.det.analyze(img)
        thr = self.det.threshold
        regs = regions(heatmap(res, img.shape), thr)
        q = image_quality(img)
        annotated = draw(img, res, thr) if res.n_tiles > 1 else img
        cam = None
        if res.prob_max >= thr:  # explica a decisão: na foto inteira (1 janela) ou na região mais provável
            (x, y, w, h), _ = regs[0] if (regs and res.n_tiles > 1) else ((0, 0, img.shape[1], img.shape[0]), 0)
            crop = img[y : y + h, x : x + w]
            if min(crop.shape[:2]) >= 32:
                cam = self._jpeg(overlay_cam(crop, self.det.gradcam(crop)), max_side=640)
        detected = res.prob_max >= thr
        summary = VisionSummary(
            crack_detected=detected, confidence=round(res.prob_max, 4), threshold=round(thr, 4),
            area_fraction=round(res.frac_tiles, 4), regions=len(regs), model=self.det.name,
            quality_alerts=q["alerts"], thumbnail_jpeg=self._jpeg(annotated, max_side=480, quality=75),
        )
        return VisionResult(
            summary=summary,
            regions=[VisionRegion(x=x, y=y, w=w, h=h, confidence=round(p, 4)) for (x, y, w, h), p in regs],
            windows=res.n_tiles, window_px=res.tile_size, latency_ms=round(res.latency_ms, 1),
            image_width=img.shape[1], image_height=img.shape[0], device=self.det.device_name,
            quality=VisionQuality(**q), annotated_jpeg=self._jpeg(annotated, max_side=1280), gradcam_jpeg=cam,
        )

    def sequence(self, files: list[tuple[str, bytes]]) -> SequenceResult:
        t0 = time.perf_counter()
        items = []
        for name, data in files:
            try:
                r = self.inspect(data)
                items.append(SequenceItem(filename=name, summary=r.summary, latency_ms=r.latency_ms))
            except VisionInputError as exc:
                items.append(SequenceItem(filename=name, error=str(exc)))
        wall = time.perf_counter() - t0
        ok = [i for i in items if i.summary]
        return SequenceResult(
            items=items, images=len(items), flagged=sum(i.summary.crack_detected for i in ok),
            images_per_second=round(len(items) / wall, 2) if wall else 0.0,
            latency_ms_mean=round(sum(i.latency_ms for i in ok) / len(ok), 1) if ok else 0.0,
            device=self.det.device_name, threshold=self.det.threshold,
        )

    # ------------------------------------------------------------ vídeo
    def monitor(self, data: bytes, every: int = 1, ema_alpha: float = 0.4, on_frames: int = 3) -> MonitorResult:
        with self._lock:
            return self._monitor(data, every, ema_alpha, on_frames)

    def _monitor(self, data: bytes, every: int, ema_alpha: float, on_frames: int) -> MonitorResult:
        """Processa um vídeo curto quadro a quadro.

        Alerta com histerese: liga após `on_frames` quadros seguidos acima do limiar e desliga quando a
        média móvel cai abaixo de 0,8 x limiar (não pisca por causa de um quadro ruim).
        """
        import cv2
        import numpy as np

        from app.vision.detector import draw

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "entrada.mp4"
            src.write_bytes(data)
            cap = cv2.VideoCapture(str(src))
            fps_video = cap.get(cv2.CAP_PROP_FPS) or 24.0
            frames = []
            while len(frames) < self.max_frames:
                ok, f = cap.read()
                if not ok:
                    break
                h, w = f.shape[:2]
                s = min(1.0, 1024 / max(h, w))
                if s < 1:
                    f = cv2.resize(f, (int(w * s) // 2 * 2, int(h * s) // 2 * 2), interpolation=cv2.INTER_AREA)
                frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
            cap.release()
            if not frames:
                raise VisionInputError("Não conseguimos ler o vídeo. Envie um MP4 curto.")

            thr = self.det.threshold
            # vídeo de câmera percorrendo a superfície: janelas do tamanho dos recortes de treino
            tile = 227 if min(frames[0].shape[:2]) >= 454 else None
            ema, streak, alert, last = 0.0, 0, False, None
            timeline, lat, out = [], [], []
            t0 = time.perf_counter()
            for i, frame in enumerate(frames):
                if i % every == 0 or last is None:
                    last = self.det.analyze(frame, tile=tile)
                    lat.append(last.latency_ms)
                    ema = ema_alpha * last.prob_max + (1 - ema_alpha) * ema
                    streak = streak + 1 if last.prob_max >= thr else 0
                    if not alert and streak >= on_frames:
                        alert = True
                    elif alert and ema < 0.8 * thr:
                        alert = False
                out.append(self._hud(draw(frame, last, thr), i, last, alert, thr))
                timeline.append(MonitorFrame(frame=i, t=round(i / fps_video, 2), confidence=round(last.prob_max, 4),
                                             smoothed=round(ema, 4), alert=alert))
            wall = time.perf_counter() - t0

            events, start = [], None
            for fr in timeline:
                if fr.alert and start is None:
                    start = fr
                if not fr.alert and start is not None:
                    seg = [x.confidence for x in timeline if start.frame <= x.frame < fr.frame]
                    events.append(MonitorEvent(start_s=start.t, end_s=fr.t, max_confidence=max(seg)))
                    start = None
            if start is not None:
                seg = [x.confidence for x in timeline if x.frame >= start.frame]
                events.append(MonitorEvent(start_s=start.t, end_s=timeline[-1].t, max_confidence=max(seg)))

            video_b64 = None
            try:
                import imageio.v2 as imageio

                dst = Path(tmp) / "saida.mp4"
                with imageio.get_writer(dst, fps=fps_video, codec="libx264", quality=6, macro_block_size=8,
                                        pixelformat="yuv420p") as wr:
                    for f in out:
                        wr.append_data(f)
                video_b64 = base64.b64encode(dst.read_bytes()).decode()
            except Exception as exc:  # sem ffmpeg: devolve só as métricas
                log.warning("Não foi possível gerar o vídeo anotado: %s", exc)

        return MonitorResult(
            frames=len(frames), analyzed_frames=len(lat), resolution=f"{frames[0].shape[1]}x{frames[0].shape[0]}",
            windows_per_frame=last.n_tiles, fps_pipeline=round(len(frames) / wall, 2),
            latency_ms_mean=round(float(np.mean(lat)), 1), latency_ms_p95=round(float(np.percentile(lat, 95)), 1),
            alert_frames=sum(f.alert for f in timeline), threshold=thr, device=self.det.device_name,
            model=self.det.name, events=events, timeline=timeline, video_mp4=video_b64,
        )

    def _hud(self, frame, i: int, res, alert: bool, thr: float):
        import cv2

        h, w = frame.shape[:2]
        cv2.rectangle(frame, (0, 0), (w, 30), (20, 24, 32), -1)
        cv2.putText(frame, "Zela | monitoramento de fissuras", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240, 240, 240), 1, cv2.LINE_AA)
        cv2.putText(frame, "ALERTA: INSPECIONAR" if alert else "monitorando", (w - 230, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (255, 70, 70) if alert else (120, 220, 140), 2, cv2.LINE_AA)
        cv2.rectangle(frame, (0, h - 24), (w, h), (20, 24, 32), -1)
        cv2.putText(frame, f"quadro {i}  conf. {res.prob_max:.2f}  latencia {res.latency_ms:.0f} ms  limiar {thr:.2f}  [{self.det.device_name}]",
                    (10, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (230, 230, 230), 1, cv2.LINE_AA)
        return frame


def build_vision(enabled: bool, models_dir: str, max_frames: int) -> VisionService | None:
    if not enabled:
        return None
    try:
        return VisionService(models_dir, max_frames=max_frames)
    except ImportError as exc:
        log.warning("Visão desativada: dependências ausentes (%s). Instale requirements-vision.txt.", exc)
    except FileNotFoundError as exc:
        log.warning("Visão desativada: modelo não encontrado (%s).", exc)
    except Exception as exc:  # noqa: BLE001 - a API não pode cair por causa do módulo de visão
        log.error("Visão desativada: %s", exc)
    return None
