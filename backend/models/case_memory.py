"""D8 — similar past cases.

    from models.case_memory import find_similar_cases
    cases = find_similar_cases("pitting on landing gear strut", k=3)

Reads data/history_cases.json. NOTHING IN THE 13-DAY TRACKER CREATES THAT FILE —
D8-01 describes its structure as though it already exists. Someone has to author
~15-20 cases. Until then this returns an empty list with a reason rather than
failing, so the rest of the pipeline still works.

Uses the same MiniLM model as Day 3 retrieval, so a case and a manual passage
are embedded in the same space and the model is loaded once for both.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, TypedDict

BACKEND = Path(__file__).resolve().parents[1]
CASES_PATH = Path(os.getenv("PRISM_CASES_PATH", str(BACKEND / "data" / "history_cases.json")))

REQUIRED_FIELDS = {"case_id", "defect_type", "symptom_description"}


class SimilarCase(TypedDict):
    case_id: str
    defect_type: str
    symptom_description: str
    diagnosis: str
    resolution: str
    risk_score: str
    similarity: float


_cases: Optional[list[dict]] = None
_vectors = None
_load_error: Optional[str] = None


def _load() -> tuple[list[dict], object]:
    """Load and embed the case file once. Embedding per request would make the
    D11-02 timings meaningless."""
    global _cases, _vectors, _load_error
    if _cases is not None or _load_error is not None:
        return _cases or [], _vectors

    if not CASES_PATH.is_file():
        _load_error = (
            f"No case file at {CASES_PATH}. Nothing in the tracker creates it — "
            "author ~15-20 cases with case_id, defect_type, symptom_description, "
            "diagnosis, resolution, risk_score."
        )
        return [], None

    try:
        raw = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        _load_error = f"{CASES_PATH.name} is not valid JSON: {e}"
        return [], None

    if not isinstance(raw, list):
        _load_error = f"{CASES_PATH.name} must contain a JSON array of case objects."
        return [], None

    good = []
    for i, c in enumerate(raw):
        if not isinstance(c, dict) or not REQUIRED_FIELDS <= c.keys():
            missing = REQUIRED_FIELDS - (c.keys() if isinstance(c, dict) else set())
            _load_error = f"case #{i} is missing required field(s): {sorted(missing)}"
            return [], None
        good.append(c)

    if not good:
        _load_error = f"{CASES_PATH.name} contains no cases."
        return [], None

    import numpy as np
    from models.retrieval import _embeddings  # same MiniLM instance as Day 3

    emb = _embeddings()
    _vectors = np.array([emb.embed_query(c["symptom_description"]) for c in good])
    _cases = good
    return _cases, _vectors


def find_similar_cases(query: str, k: int = 3) -> list[SimilarCase]:
    cases, vectors = _load()
    if not cases:
        return []

    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity

    from models.retrieval import _embeddings

    q = np.array(_embeddings().embed_query(query)).reshape(1, -1)
    sims = cosine_similarity(q, vectors)[0]
    order = sims.argsort()[::-1][:k]

    return [
        SimilarCase(
            case_id=str(cases[i].get("case_id", "")),
            defect_type=cases[i].get("defect_type", ""),
            symptom_description=cases[i].get("symptom_description", ""),
            diagnosis=cases[i].get("diagnosis", ""),
            resolution=cases[i].get("resolution", ""),
            risk_score=cases[i].get("risk_score", ""),
            similarity=round(float(sims[i]), 4),
        )
        for i in order
    ]


def case_memory_info() -> dict:
    cases, _ = _load()
    if not cases:
        return {"available": False, "reason": _load_error}
    return {"available": True, "cases": len(cases), "path": str(CASES_PATH)}
