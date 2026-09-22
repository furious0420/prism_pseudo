"""D7 — risk scoring.

    from models.risk import score_risk
    risk = score_risk("corrosion", 0.82)

Pure input -> output, no side effects, so it is trivial to test in isolation
(D7-01 step 4). Severity comes from the defect type; detection confidence can
only moderate it DOWNWARD, never upward — a confident detection of a scratch is
still a scratch, while an uncertain crack still needs a human to look.

NOTE: the tracker cites SAE J1979, which is the OBD-II automotive diagnostics
standard. Aviation maintenance uses ATA chapters and MSG-3. Either justify the
reference or swap it before the jury asks.
"""
from __future__ import annotations

from typing import TypedDict

# Adjust to your actual YOLOv8 class list once Day 6 fixes the classes.
SEVERITY = {
    "crack": "Critical",
    "stress corrosion cracking": "Critical",
    "corrosion": "High",
    "exfoliation": "High",
    "pitting": "High",
    "dent": "Medium",
    "deformation": "Medium",
    "scratch": "Low",
    "discoloration": "Low",
}

LEVELS = ["Low", "Medium", "High", "Critical"]

# Below this we do not trust the class enough to assert its full severity.
LOW_CONFIDENCE = 0.40
UNKNOWN_SEVERITY = "Medium"   # an unrecognised defect is not automatically safe


class Risk(TypedDict):
    level: str
    severity: str
    confidence: float
    rationale: str
    needs_human_review: bool


def score_risk(defect_type: str, confidence: float) -> Risk:
    key = (defect_type or "").strip().lower()
    severity = SEVERITY.get(key, UNKNOWN_SEVERITY)
    known = key in SEVERITY

    level = severity
    notes = []

    if not known:
        notes.append(f"'{defect_type}' is not in the severity table; "
                     f"defaulted to {UNKNOWN_SEVERITY} rather than assuming it is minor")

    if confidence < LOW_CONFIDENCE:
        # Step down one level, but never below Low, and always flag for review.
        idx = max(0, LEVELS.index(severity) - 1)
        level = LEVELS[idx]
        notes.append(f"detection confidence {confidence:.0%} is below "
                     f"{LOW_CONFIDENCE:.0%}, so severity was reduced from {severity}")

    needs_review = (
        level in ("High", "Critical")
        or confidence < LOW_CONFIDENCE
        or not known
    )
    if needs_review and "review" not in " ".join(notes):
        notes.append("flagged for human review")

    rationale = f"{defect_type or 'unknown defect'} classified {severity}"
    if notes:
        rationale += "; " + "; ".join(notes)

    return Risk(
        level=level,
        severity=severity,
        confidence=round(float(confidence), 4),
        rationale=rationale,
        needs_human_review=needs_review,
    )


def worst_risk(risks: list[Risk]) -> Risk | None:
    """The governing risk for an image with several defects: the worst one.
    Averaging would let three scratches hide a crack."""
    if not risks:
        return None
    return max(risks, key=lambda r: LEVELS.index(r["level"]))
