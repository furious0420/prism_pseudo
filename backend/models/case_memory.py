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
import re
import tempfile
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


def list_cases() -> list[dict]:
    """All cases, newest (highest case_id) first, for the Case History tab."""
    cases, _ = _load()
    return sorted(cases, key=lambda c: str(c.get("case_id", "")), reverse=True)


_ID_RE = re.compile(r"^HC-(\d+)$")


def _next_case_id(existing: list[dict]) -> str:
    highest = 0
    for c in existing:
        m = _ID_RE.match(str(c.get("case_id", "")))
        if m:
            highest = max(highest, int(m.group(1)))
    return f"HC-{highest + 1:03d}"


def log_case(
    defect_type: str,
    symptom_description: str,
    diagnosis: str,
    resolution: str,
    risk_score: str,
) -> dict:
    """Append a new case, written back by the frontend's "Mark as Resolved"
    flow (D9-era UI addition, not in the 13-day tracker).

    Reads the file fresh from disk — not the module cache — since disk is
    the source of truth for a write. Writes via a temp file + os.replace()
    (atomic on POSIX and Windows) so a crash mid-write can never leave
    history_cases.json truncated or corrupt, which would break case memory
    for every request until someone notices and fixes the file by hand.
    """
    if CASES_PATH.is_file():
        try:
            existing = json.loads(CASES_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"{CASES_PATH.name} is not valid JSON: {e}") from e
        if not isinstance(existing, list):
            raise ValueError(f"{CASES_PATH.name} must contain a JSON array of case objects.")
    else:
        existing = []

    case = {
        "case_id": _next_case_id(existing),
        "defect_type": defect_type or "unspecified",
        "symptom_description": symptom_description,
        "diagnosis": diagnosis,
        "resolution": resolution,
        "risk_score": risk_score or "",
    }
    existing.append(case)

    CASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(CASES_PATH.parent), prefix=".history_cases_", suffix=".json.tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, CASES_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    # Invalidate the module cache so the next find_similar_cases() call
    # re-reads and re-embeds the file, including this new case. Without
    # this, _load()'s "loaded once" guard would keep serving the stale
    # in-memory list for the rest of the process's life.
    global _cases, _vectors, _load_error
    _cases = None
    _vectors = None
    _load_error = None

    return case
