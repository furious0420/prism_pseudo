"""D6 — YOLOv8 defect detection.

    from models.detect import detect, detector_info
    dets = detect("photo.jpg")

Day 6 replaces the weights with a fine-tuned model. Until then this runs
pretrained YOLOv8n, which does NOT know aircraft defect classes — it proves the
pipeline plumbing exactly as D6-01 step 4 describes, and nothing more. The
`pretrained` flag in every result says so, so the UI can label it honestly
rather than presenting COCO classes as defect findings.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, TypedDict

BACKEND = Path(__file__).resolve().parents[1]

# Fine-tuned weights land here after D6-01. Falls back to pretrained yolov8n.
WEIGHTS = os.getenv("PRISM_YOLO_WEIGHTS", "runs/detect/train/weights/best.pt")
FALLBACK_WEIGHTS = "yolov8n.pt"
CONF_THRESHOLD = float(os.getenv("PRISM_YOLO_CONF", "0.25"))

# Day 2 found this machine at 78% VRAM with the LLM alone. Running detection on
# the GPU alongside Phi-3 risks an OOM mid-demo, so default to CPU — single
# images are fast enough on CPU and the contention disappears.
DEVICE = os.getenv("PRISM_YOLO_DEVICE", "cpu")


class Detection(TypedDict):
    label: str
    confidence: float
    box: list[float]      # [x1, y1, x2, y2]
    pretrained: bool      # True = generic COCO model, not a defect detector


class DetectorUnavailable(RuntimeError):
    pass


_model = None
_using_pretrained = True


def _resolve_weights() -> tuple[str, bool]:
    p = Path(WEIGHTS)
    if not p.is_absolute():
        p = BACKEND / p
    if p.is_file():
        return str(p), False
    return FALLBACK_WEIGHTS, True     # ultralytics downloads this on first use


def _get_model():
    global _model, _using_pretrained
    path, pretrained = _resolve_weights()
    if _model is None or (_using_pretrained and not pretrained):
        try:
            from ultralytics import YOLO
        except ImportError as e:
            raise DetectorUnavailable(
                "ultralytics is not installed.  fix -> pip install ultralytics"
            ) from e
        _using_pretrained = pretrained
        _model = YOLO(path)
    return _model


def detect(image_path: str, conf: float = CONF_THRESHOLD) -> list[Detection]:
    """Detected defects in one image, highest confidence first."""
    model = _get_model()
    results = model.predict(image_path, conf=conf, device=DEVICE, verbose=False)
    out: list[Detection] = []
    for r in results:
        names = r.names
        for b in r.boxes:
            label = names[int(b.cls)]
            # If using generic pretrained fallback, suppress non-aviation COCO classes
            # like bus, person, car, etc. that do not belong in aircraft inspection.
            if _using_pretrained and label not in ("crack", "dent", "missing-head", "paint-off", "scratch"):
                continue
            out.append(Detection(
                label=label,
                confidence=round(float(b.conf), 4),
                box=[round(float(v), 1) for v in b.xyxy[0].tolist()],
                pretrained=_using_pretrained,
            ))
    out.sort(key=lambda d: d["confidence"], reverse=True)
    return out


def detector_info() -> dict:
    try:
        _get_model()
    except DetectorUnavailable as e:
        return {"available": False, "reason": str(e)}
    path, pretrained = _resolve_weights()
    return {
        "available": True,
        "weights": path,
        "pretrained": pretrained,
        "device": DEVICE,
        "note": ("Pretrained COCO model — proves plumbing, does NOT detect aircraft "
                 "defects. Fine-tune on Day 6." if pretrained else "Fine-tuned defect model."),
    }
