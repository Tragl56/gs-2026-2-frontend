"""Detector de fissuras: janelas deslizantes + CNN + Grad-CAM + checagem de qualidade da foto.

Importa torch/torchvision/cv2: só é carregado quando a visão está disponível (ver service.py).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import torchvision.models as tvm

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def build_model(arch: str) -> nn.Module:
    ctor = {"resnet18": tvm.resnet18, "resnet50": tvm.resnet50, "mobilenet_v3_large": tvm.mobilenet_v3_large}[arch]
    m = ctor(weights=None)
    if arch.startswith("resnet"):
        m.fc = nn.Linear(m.fc.in_features, 2)
    else:
        m.classifier[3] = nn.Linear(m.classifier[3].in_features, 2)
    return m


def _cam_layer(model: nn.Module, arch: str) -> nn.Module:
    return model.layer4 if arch.startswith("resnet") else model.features[-1]


@dataclass
class Tile:
    x: int
    y: int
    w: int
    h: int
    prob: float


@dataclass
class Analysis:
    prob_max: float
    frac_tiles: float
    n_tiles: int
    tile_size: int
    latency_ms: float
    tiles: list[Tile] = field(default_factory=list)


class CrackDetector:
    """Carrega `<models_dir>/<name>.pt` + `<name>.json` (exportados pelo notebook)."""

    def __init__(self, models_dir: str | Path, name: str | None = None, device: str | None = None):
        models_dir = Path(models_dir)
        if name is None:
            name = json.loads((models_dir / "selected.json").read_text(encoding="utf-8"))["arch"]
        self.cfg = json.loads((models_dir / f"{name}.json").read_text(encoding="utf-8"))
        self.name = name
        self.arch = self.cfg.get("arch", name)
        self.size = int(self.cfg.get("img_size", 224))
        self.temperature = float(self.cfg.get("temperature", 1.0))
        self.threshold = float(self.cfg.get("thresholds", {}).get("triagem", 0.5))
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        m = build_model(self.arch)
        m.load_state_dict(torch.load(models_dir / f"{name}.pt", map_location="cpu", weights_only=True))
        self.model = m.to(self.device).eval()  # fp32: nas GTX 16xx o fp16 é mais lento e gera NaN
        self.device_name = torch.cuda.get_device_name(0) if self.device == "cuda" else "CPU"
        self.predict([np.zeros((self.size, self.size, 3), np.uint8)] * 4)  # aquecimento do cuDNN

    def _tensor(self, crops: list[np.ndarray]) -> torch.Tensor:
        arr = np.stack([cv2.resize(c, (self.size, self.size), interpolation=cv2.INTER_AREA) for c in crops])
        # .contiguous(): sem isso o layout fica channels-last e o cuDNN fica ~12x mais lento na GTX 1650
        t = torch.as_tensor(arr).to(self.device).permute(0, 3, 1, 2).contiguous().float().div_(255.0)
        mean = torch.tensor(IMAGENET_MEAN, device=self.device).view(1, 3, 1, 1)
        std = torch.tensor(IMAGENET_STD, device=self.device).view(1, 3, 1, 1)
        return (t - mean) / std

    @torch.no_grad()
    def predict(self, crops: list[np.ndarray], batch: int = 64) -> np.ndarray:
        out = []
        for i in range(0, len(crops), batch):
            logits = self.model(self._tensor(crops[i : i + batch]))
            out.append(torch.softmax(logits / self.temperature, 1)[:, 1].cpu().numpy())
        return np.concatenate(out) if out else np.zeros(0)

    @staticmethod
    def auto_tile(h: int, w: int) -> int:
        """Os recortes de treino cobrem uma pequena parte da superfície: fotos grandes viram janelas."""
        if min(h, w) <= 320:
            return min(h, w)
        return int(np.clip(min(h, w) / 6, 160, 480))

    def analyze(self, img: np.ndarray, tile: int | None = None, overlap: float = 0.25) -> Analysis:
        t0 = time.perf_counter()
        h, w = img.shape[:2]
        tile = min(tile or self.auto_tile(h, w), h, w)
        stride = max(1, int(tile * (1 - overlap)))
        ys = list(range(0, max(h - tile, 0) + 1, stride))
        xs = list(range(0, max(w - tile, 0) + 1, stride))
        if ys[-1] + tile < h:
            ys.append(h - tile)
        if xs[-1] + tile < w:
            xs.append(w - tile)
        coords = [(x, y) for y in ys for x in xs]
        probs = self.predict([img[y : y + tile, x : x + tile] for x, y in coords])
        if self.device == "cuda":
            torch.cuda.synchronize()
        return Analysis(
            prob_max=float(probs.max()),
            frac_tiles=float((probs >= self.threshold).mean()),
            n_tiles=len(coords),
            tile_size=tile,
            latency_ms=(time.perf_counter() - t0) * 1000,
            tiles=[Tile(x, y, tile, tile, float(p)) for (x, y), p in zip(coords, probs)],
        )

    def gradcam(self, crop: np.ndarray) -> np.ndarray:
        layer = _cam_layer(self.model, self.arch)
        store = {}
        hook = layer.register_forward_hook(lambda m, i, o: store.__setitem__("act", o))
        try:
            with torch.enable_grad():
                logits = self.model(self._tensor([crop]))
                grad = torch.autograd.grad(logits[0, 1], store["act"])[0]
            act = store["act"]
            cam = torch.relu((grad.mean(dim=(2, 3), keepdim=True) * act).sum(1))[0].detach().cpu().numpy()
        finally:
            hook.remove()
        cam = cv2.resize(cam, (crop.shape[1], crop.shape[0]))
        return cam / (cam.max() + 1e-8)


# ------------------------------------------------------------------ utilidades
def image_quality(img: np.ndarray) -> dict:
    """Nitidez relativa (Laplaciano da foto / Laplaciano dela levemente borrada), brilho e contraste.

    Calibrado em 400 recortes de teste: fotos nítidas p5 = 4,9; desfocadas p95 = 1,9.
    """
    g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    s = 1024 / max(g.shape)
    if s < 1:
        g = cv2.resize(g, (int(g.shape[1] * s), int(g.shape[0] * s)), interpolation=cv2.INTER_AREA)
    sharp = float(cv2.Laplacian(g, cv2.CV_64F).var() / (cv2.Laplacian(cv2.GaussianBlur(g, (0, 0), 1.5), cv2.CV_64F).var() + 1e-6))
    bright, contrast = float(g.mean()), float(g.std())
    alerts = []
    if sharp < 3.0:
        alerts.append("A foto parece borrada. Se puder, tire outra mais de perto e com a câmera parada.")
    if bright < 50:
        alerts.append("A foto está escura. Fissuras finas podem não aparecer.")
    if bright > 215:
        alerts.append("A foto está muito clara (superexposta).")
    if contrast < 15:
        alerts.append("A foto tem pouco contraste.")
    return {"sharpness": sharp, "brightness": bright, "contrast": contrast, "alerts": alerts}


def heatmap(res: Analysis, shape) -> np.ndarray:
    h, w = shape[:2]
    heat = np.zeros((h, w), np.float32)
    cnt = np.zeros((h, w), np.float32)
    for t in res.tiles:
        heat[t.y : t.y + t.h, t.x : t.x + t.w] += t.prob
        cnt[t.y : t.y + t.h, t.x : t.x + t.w] += 1
    return heat / np.maximum(cnt, 1)


def regions(heat: np.ndarray, threshold: float) -> list[tuple[tuple[int, int, int, int], float]]:
    n, lab, stats, _ = cv2.connectedComponentsWithStats((heat >= threshold).astype(np.uint8), connectivity=8)
    out = [((int(stats[i, 0]), int(stats[i, 1]), int(stats[i, 2]), int(stats[i, 3])), float(heat[lab == i].max()))
           for i in range(1, n)]
    return sorted(out, key=lambda r: -r[1])


def draw(img: np.ndarray, res: Analysis, threshold: float, alpha: float = 0.35) -> np.ndarray:
    h, w = img.shape[:2]
    heat = heatmap(res, img.shape)
    color = cv2.applyColorMap((heat * 255).astype(np.uint8), cv2.COLORMAP_JET)[..., ::-1]
    out = np.where((heat >= threshold)[..., None], (img * (1 - alpha) + color * alpha).astype(np.uint8), img)
    lw = max(2, int(min(h, w) / 300))
    for (x, y, bw, bh), p in regions(heat, threshold):
        cv2.rectangle(out, (x, y), (x + bw - 1, y + bh - 1), (255, 40, 40), lw)
        label = f"fissura {p:.0%}"
        fs = 0.45 * lw / 2 + 0.2
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, fs, max(1, lw // 2))
        cv2.rectangle(out, (x, y), (x + tw + 6, y + th + 8), (255, 40, 40), -1)
        cv2.putText(out, label, (x + 3, y + th + 4), cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), max(1, lw // 2), cv2.LINE_AA)
    return out


def overlay_cam(img: np.ndarray, cam: np.ndarray, alpha: float = 0.45) -> np.ndarray:
    color = cv2.applyColorMap((cam * 255).astype(np.uint8), cv2.COLORMAP_JET)[..., ::-1]
    return (img * (1 - alpha) + color * alpha).astype(np.uint8)
