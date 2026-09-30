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

# The first five keys are the actual trained YOLOv8 class list (see
# data/vision_dataset/data.yaml); the rest are retained because technicians
# describe defects in free text too, and a typed symptom can name them.
SEVERITY = {
    # --- trained detector classes ---
    "crack": "Critical",
    "dent": "Medium",
    # A missing fastener head is a load-path problem, not cosmetic: the joint
    # it secured is no longer carrying what it was designed to.
    "missing-head": "High",
    # Paint loss is not itself structural, but it removes the coating that
    # prevents corrosion, so it is a precursor rather than a finding.
    "paint-off": "Medium",
    "scratch": "Low",
    # --- additional vocabulary for free-text symptoms ---
    "stress corrosion cracking": "Critical",
    "corrosion": "High",
    "exfoliation": "High",
    "pitting": "High",
    "deformation": "Medium",
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


# ---------------------------------------------------------------------------
# Telemetry scoring (D7-01's original intent)
#
# The 13-day tracker's D7 ended up scoring only defect type + detection
# confidence, which means the risk panel is EMPTY on any text-only diagnosis —
# by far the most common real flow, and the only one possible until a defect
# dataset exists. Scoring telemetry as well decouples risk from detection.
#
# HONESTY NOTE, carried over from the module docstring above: these thresholds
# are ILLUSTRATIVE DEMO VALUES, not certified limits. Real limits come from the
# type certificate / component maintenance manual for a specific aircraft and
# component, and aviation uses ATA chapters + MSG-3, not SAE J1979 (an
# automotive OBD-II standard). Do not present these numbers as airworthiness
# criteria. They are here to demonstrate the scoring mechanism with plausible
# values, and every threshold is a named constant so real ones can be dropped
# in without touching the logic.
# ---------------------------------------------------------------------------

# Band boundaries follow the original 4-person tracker's Phase 2 spec:
# "0-33 Low, 34-66 Medium, 67-100 High".
BAND_LOW_MAX = 33
BAND_MEDIUM_MAX = 66
BAND_CRITICAL_MIN = 85

PARAMETERS = {
    "temperature_c": {
        "label": "Temperature",
        "unit": "°C",
        "nominal_max": 70.0,      # above this: elevated
        "critical_min": 90.0,     # at/above this: critical
        "elevated_points": 25,
        "critical_points": 40,
        "nominal_note": "within normal range",
        "elevated_note": "sustained elevated",
        "critical_note": "exceeds operating limit",
    },
    "pressure_psi": {
        "label": "Pressure",
        "unit": "PSI",
        # Pressure is the one parameter where BOTH directions are bad.
        "band_min": 35.0,
        "band_max": 55.0,
        "critical_low": 25.0,
        "critical_high": 65.0,
        "elevated_points": 20,
        "critical_points": 35,
        "nominal_note": "within normal range",
        "elevated_note": "outside nominal band",
        "critical_note": "far outside nominal band",
    },
    "runtime_hrs": {
        "label": "Runtime",
        "unit": "hrs",
        "nominal_max": 1000.0,
        "critical_min": 1500.0,   # service interval
        "elevated_points": 20,
        "critical_points": 30,
        "nominal_note": "well inside service interval",
        "elevated_note": "approaching service threshold",
        "critical_note": "past service interval",
    },
    "vibration_mm_s": {
        "label": "Vibration",
        "unit": "mm/s",
        "nominal_max": 4.5,
        "critical_min": 7.1,
        "elevated_points": 25,
        "critical_points": 40,
        "nominal_note": "within normal range",
        "elevated_note": "elevated, monitor trend",
        "critical_note": "exceeds vibration limit",
    },
}


class Factor(TypedDict):
    parameter: str
    label: str
    value: float
    unit: str
    band: str          # nominal | elevated | critical
    points: int
    note: str


def band_for_score(score: int) -> str:
    if score <= BAND_LOW_MAX:
        return "Low"
    if score <= BAND_MEDIUM_MAX:
        return "Medium"
    if score < BAND_CRITICAL_MIN:
        return "High"
    return "Critical"


def _score_parameter(key: str, value: float) -> Factor:
    spec = PARAMETERS[key]

    if key == "pressure_psi":
        if value <= spec["critical_low"] or value >= spec["critical_high"]:
            band, points, note = "critical", spec["critical_points"], spec["critical_note"]
        elif value < spec["band_min"] or value > spec["band_max"]:
            band, points, note = "elevated", spec["elevated_points"], spec["elevated_note"]
        else:
            band, points, note = "nominal", 0, spec["nominal_note"]
    else:
        if value >= spec["critical_min"]:
            band, points, note = "critical", spec["critical_points"], spec["critical_note"]
        elif value > spec["nominal_max"]:
            band, points, note = "elevated", spec["elevated_points"], spec["elevated_note"]
        else:
            band, points, note = "nominal", 0, spec["nominal_note"]

    return Factor(
        parameter=key, label=spec["label"], value=float(value), unit=spec["unit"],
        band=band, points=points, note=note,
    )


# What a defect contributes to the 0-100 score, on top of telemetry.
DEFECT_POINTS = {"Low": 5, "Medium": 20, "High": 35, "Critical": 50}


def score_telemetry(telemetry: dict, defect_risk: Risk | None = None) -> dict:
    """Combine telemetry readings (and any detected defect) into a 0-100 score.

    Unknown/blank/non-numeric parameters are skipped rather than guessed at —
    a missing sensor must never silently read as "nominal".
    """
    factors: list[Factor] = []
    for key in PARAMETERS:
        raw = (telemetry or {}).get(key)
        if raw is None or raw == "":
            continue
        try:
            factors.append(_score_parameter(key, float(raw)))
        except (TypeError, ValueError):
            continue    # unparseable reading: skip, don't assume

    score = sum(f["points"] for f in factors)

    defect_factor = None
    if defect_risk:
        pts = DEFECT_POINTS.get(defect_risk["level"], 0)
        score += pts
        defect_factor = {
            "parameter": "defect",
            "label": "Detected defect",
            "value": None,
            "unit": "",
            "band": defect_risk["level"].lower(),
            "points": pts,
            "note": defect_risk["rationale"],
        }
        factors.append(defect_factor)

    score = min(score, 100)
    band = band_for_score(score)

    # Anything above the low band, or any single critical reading, wants eyes on it.
    needs_review = band != "Low" or any(f["band"] == "critical" for f in factors)

    if not factors:
        advisory = "No telemetry supplied and no defect detected — nothing to score."
    elif band == "Critical":
        advisory = "Immediate inspection required before further service."
    elif band == "High":
        advisory = "Inspect before next flight."
    elif band == "Medium":
        advisory = "Approaching service threshold — inspect within 30 days."
    else:
        advisory = "Within normal parameters — monitor at next scheduled check."

    return {
        "score": score,
        "band": band,
        "factors": factors,
        "needs_human_review": needs_review,
        "advisory": advisory,
        "scored_parameters": len([f for f in factors if f["parameter"] != "defect"]),
    }
