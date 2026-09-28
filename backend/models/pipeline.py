"""D9-01 — the full diagnostic pipeline, in the order the tracker specifies:

    detection (D6) -> retrieval + diagnosis (D4) -> risk (D7) -> case memory (D8)

    from models.pipeline import run_diagnosis
    result = run_diagnosis(image_path="strut.jpg", query="pitting near bearing")

Every stage is independent and failure-isolated. A missing YOLO model, an empty
case file or a cold LLM degrades that ONE section of the response and leaves the
rest intact. That matters for the demo: D10-02 asks what happens with no image,
an empty query or a nonsense query, and the answer should be a partial result
with an explanation, never a 500.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Stage:
    """One pipeline step's outcome, so the UI can show what ran and what didn't."""
    name: str
    ok: bool
    ms: float = 0.0
    skipped: bool = False
    error: Optional[str] = None
    note: Optional[str] = None

    def to_json(self) -> dict:
        d: dict[str, Any] = {"name": self.name, "ok": self.ok, "ms": round(self.ms, 1)}
        if self.skipped:
            d["skipped"] = True
        if self.error:
            d["error"] = self.error
        if self.note:
            d["note"] = self.note
        return d


def _timed(fn, *a, **kw):
    t0 = time.perf_counter()
    try:
        return fn(*a, **kw), (time.perf_counter() - t0) * 1000, None
    except Exception as e:                      # noqa: BLE001 - deliberate
        return None, (time.perf_counter() - t0) * 1000, f"{type(e).__name__}: {e}"


def _run(
    image_path: Optional[str] = None,
    query: str = "",
    k: int = 3,
    telemetry: Optional[dict] = None,
):
    """The pipeline, as a generator of events.

    Yields ("stage", stage_json) as each stage finishes, then one final
    ("result", payload). run_diagnosis() drains this and returns the payload;
    run_diagnosis_stream() forwards the events. One code path serves both, so
    the streaming endpoint cannot drift from the verified behaviour of the
    plain one.
    """
    started = time.perf_counter()
    stages: list[Stage] = []
    query = (query or "").strip()
    no_input_reason: Optional[str] = None

    # ---------------- D6: detection ----------------
    detections: list[dict] = []
    if image_path:
        from models.detect import detect
        dets, ms, err = _timed(detect, image_path)
        if err:
            stages.append(Stage("detection", ok=False, ms=ms, error=err))
        else:
            detections = list(dets or [])
            note = None
            if detections and detections[0].get("pretrained"):
                note = ("Pretrained COCO model — these are generic object classes, "
                        "not aircraft defects. Fine-tune on Day 6.")
            stages.append(Stage("detection", ok=True, ms=ms, note=note))
    else:
        stages.append(Stage("detection", ok=True, skipped=True,
                            note="no image supplied — text-only diagnosis"))
    yield ("stage", stages[-1].to_json())

    # ---------------- D7: risk ----------------
    # Before generation, so a detected defect can be named in the query below.
    from models.risk import score_risk, score_telemetry, worst_risk
    risks = [score_risk(d["label"], d["confidence"]) for d in detections]
    overall = worst_risk(risks)

    # Telemetry scoring runs even with zero detections — otherwise the risk
    # panel is empty on every text-only diagnosis, which is the common case.
    telemetry = telemetry or {}
    scored = score_telemetry(telemetry, overall)
    has_risk_input = bool(risks) or scored["scored_parameters"] > 0
    stages.append(Stage(
        "risk", ok=True, skipped=not has_risk_input,
        note=None if has_risk_input else "no detections and no telemetry to score",
    ))
    yield ("stage", stages[-1].to_json())

    # ---------------- D4: retrieval + grounded diagnosis ----------------
    diagnosis: dict = {}
    if query or detections:
        # A detected defect sharpens retrieval even when the technician typed little.
        effective = query
        if detections:
            labels = ", ".join(sorted({d["label"] for d in detections[:3]}))
            effective = f"{query}\n\nDetected in image: {labels}".strip()

        from models.rag import diagnose
        res, ms, err = _timed(diagnose, effective, k)
        if err:
            stages.append(Stage("diagnosis", ok=False, ms=ms, error=err))
        else:
            diagnosis = res.to_json()
            stages.append(Stage("diagnosis", ok=True, ms=ms))
    else:
        stages.append(Stage("diagnosis", ok=True, skipped=True,
                            note="no query and no detections — nothing to diagnose"))
        no_input_reason = (
            "No defects were detected in the image and no symptom description was "
            "given, so there was nothing to diagnose. Add a description of what you "
            "are seeing."
            if image_path else
            "No symptom description was given."
        )
    yield ("stage", stages[-1].to_json())

    # ---------------- D8: case memory ----------------
    similar: list[dict] = []
    if query:
        from models.case_memory import case_memory_info, find_similar_cases
        cases, ms, err = _timed(find_similar_cases, query, k)
        if err:
            stages.append(Stage("case_memory", ok=False, ms=ms, error=err))
        else:
            similar = list(cases or [])
            info = case_memory_info()
            stages.append(Stage(
                "case_memory", ok=True, ms=ms,
                note=None if info.get("available") else info.get("reason"),
            ))
    else:
        stages.append(Stage("case_memory", ok=True, skipped=True, note="no query text"))
    yield ("stage", stages[-1].to_json())

    total_ms = (time.perf_counter() - started) * 1000

    yield ("result", {
        "needs_input": no_input_reason,
        "query": query,
        "detections": detections,
        "risks": risks,
        "overall_risk": overall,
        # 0-100 score + per-parameter breakdown (telemetry + any defect).
        "risk_assessment": scored if has_risk_input else None,
        "telemetry": {k: v for k, v in telemetry.items() if v not in (None, "")},
        # D9-01 step 4 names a single `risk_score` field. `overall_risk` carries
        # the full object because one string cannot express "three scratches and
        # one crack" — averaging would let the crack hide. This alias keeps the
        # response matching the tracker as written. It now prefers the combined
        # telemetry+defect band, falling back to the defect-only level, so a
        # text-only diagnosis with telemetry still reports a risk.
        "risk_score": (scored["band"] if has_risk_input
                       else (overall["level"] if overall else None)),
        "diagnosis": diagnosis.get("diagnosis", ""),
        "likely_defect": diagnosis.get("likely_defect"),
        "actions": diagnosis.get("actions", []),
        "citations": diagnosis.get("citations", []),
        "sources": diagnosis.get("sources", []),
        "grounded": diagnosis.get("grounded"),
        "cited_ok": diagnosis.get("cited_ok"),
        "refused": diagnosis.get("refused"),
        "similar_cases": similar,
        "stages": [s.to_json() for s in stages],
        "timing_ms": {"total": round(total_ms, 1)},
    })


def run_diagnosis(
    image_path: Optional[str] = None,
    query: str = "",
    k: int = 3,
    telemetry: Optional[dict] = None,
) -> dict:
    """Run every stage and return one combined response (POST /diagnose)."""
    payload: dict = {}
    for kind, data in _run(image_path, query, k, telemetry):
        if kind == "result":
            payload = data
    return payload


def run_diagnosis_stream(
    image_path: Optional[str] = None,
    query: str = "",
    k: int = 3,
    telemetry: Optional[dict] = None,
):
    """Same pipeline, emitting each stage as it completes (POST /diagnose/stream).

    The point is pacing: generation dominates the wall clock (often 15-25s on
    the demo machine), so without this the UI shows nothing at all for the
    whole run and then everything at once. The timings reported are the real
    measured ones — nothing here fakes progress.
    """
    yield from _run(image_path, query, k, telemetry)


def pipeline_info() -> dict:
    """Which stages are ready right now. Backs GET /health/pipeline."""
    out = {}
    from models.llm import backend_info
    out["llm"] = backend_info()
    try:
        from models.retrieval import corpus_stats
        out["corpus"] = corpus_stats()
    except Exception as e:                      # noqa: BLE001
        out["corpus"] = {"available": False, "reason": f"{type(e).__name__}: {e}"}
    try:
        from models.detect import detector_info
        out["detector"] = detector_info()
    except Exception as e:                      # noqa: BLE001
        out["detector"] = {"available": False, "reason": f"{type(e).__name__}: {e}"}
    try:
        from models.case_memory import case_memory_info
        out["case_memory"] = case_memory_info()
    except Exception as e:                      # noqa: BLE001
        out["case_memory"] = {"available": False, "reason": f"{type(e).__name__}: {e}"}
    out["ready"] = bool(out["llm"].get("available") and out["corpus"].get("available"))
    return out
