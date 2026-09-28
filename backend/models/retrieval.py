"""D3-01/D4-01 — retrieval over the manual corpus.

    from models.retrieval import search
    hits = search("corrosion on landing gear strut", k=3)

Each hit carries the text plus the document and page it came from, so a
diagnosis can cite its source instead of asserting things unsupported.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional, TypedDict

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

BACKEND = Path(__file__).resolve().parents[1]


def _resolve_under_backend(path_str: str) -> Path:
    """Resolve a configured path the same way no matter where you run from.

    A relative CHROMA_DIR in .env used to resolve against the current working
    directory, so running from backend/ turned "backend/chroma_db" into
    backend/backend/chroma_db and retrieval silently found no index — while
    ingestion had written it somewhere else entirely.
    """
    # Accept Windows-style separators even when parsed on Linux, so one .env
    # works across the team's machines.
    p = Path(path_str.replace("\\", "/"))
    if p.is_absolute():
        return p
    # Strip a leading "backend/" so older .env files keep working.
    parts = p.parts
    if parts and parts[0] == BACKEND.name:
        p = Path(*parts[1:]) if len(parts) > 1 else Path("chroma_db")
    return (BACKEND / p).resolve()


# THE definition of where the index lives. ingest_corpus.py imports this so the
# writer and the reader can never disagree again.
CHROMA_DIR = _resolve_under_backend(os.getenv("CHROMA_DIR", "chroma_db"))
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class Hit(TypedDict):
    text: str
    source: str
    page: int
    score: float


class CorpusMissing(RuntimeError):
    pass


_db: Optional[Chroma] = None
_emb: Optional[HuggingFaceEmbeddings] = None

# Two requests arriving together — e.g. the frontend's /health/pipeline poll
# landing at the same moment as a user action — could both see the singleton
# as None and build it twice. Two Chroma clients opening the same directory
# concurrently fails with "Could not connect to tenant default_tenant", and
# two embedding models would double memory. Seen for real once the UI started
# polling every 12s.
_init_lock = threading.Lock()


def _embeddings() -> HuggingFaceEmbeddings:
    """One shared MiniLM instance. Day 8 embeds cases with the same model, and
    loading it twice would double both memory and startup time."""
    global _emb
    if _emb is not None:
        return _emb
    with _init_lock:
        if _emb is None:
            _emb = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    return _emb


def _get_db() -> Chroma:
    """Open the index once. Loading the embedding model per query would make
    retrieval look far slower than it is in the D11-02 timings."""
    global _db
    if _db is not None:
        return _db
    if not CHROMA_DIR.exists():
        raise CorpusMissing(
            f"No index at {CHROMA_DIR}.\n"
            "  fix -> put the manual PDFs in backend/data/corpus_raw/ and run:\n"
            "         python scripts/ingest_corpus.py"
        )
    # _embeddings() takes the same lock, so resolve it before acquiring
    # (threading.Lock is not reentrant — doing it inside would deadlock).
    emb = _embeddings()
    with _init_lock:
        # Re-check inside the lock: another thread may have built it while we waited.
        if _db is None:
            _db = Chroma(persist_directory=str(CHROMA_DIR), embedding_function=emb)
    return _db


def search(query: str, k: int = 3) -> list[Hit]:
    """Top-k manual passages for a technician query, best first."""
    # similarity_search_with_score returns the raw COSINE DISTANCE because the
    # collection is built with hnsw:space=cosine. For unit-length embeddings
    # that is 1 - cosine_similarity, so similarity = 1 - distance, cleanly in
    # 0-1. We deliberately avoid similarity_search_with_relevance_scores, whose
    # Euclidean-based conversion emits warnings and can return large negatives.
    results = _get_db().similarity_search_with_score(query, k=k)
    return [
        Hit(
            text=doc.page_content,
            source=doc.metadata.get("source", "unknown"),
            page=int(doc.metadata.get("page", 0)),
            score=round(1.0 - float(distance), 4),
        )
        for doc, distance in results
    ]


def format_context(hits: list[Hit]) -> str:
    """Render hits as the Context block D4-01 puts into the prompt."""
    return "\n\n".join(
        f"[{h['source']} p.{h['page']}]\n{h['text']}" for h in hits
    )


def documents() -> list[dict]:
    """Which manuals are actually in the index, and how much of each.

    Backs the frontend's Manuals tab — "is that corpus real?" is a fair
    question to ask of a RAG demo, and this answers it from the index itself
    rather than from a hardcoded list.
    """
    db = _get_db()
    got = db._collection.get(include=["metadatas"])
    counts: dict[str, dict] = {}
    for meta in (got.get("metadatas") or []):
        src = (meta or {}).get("source", "unknown")
        page = (meta or {}).get("page")
        entry = counts.setdefault(src, {"source": src, "chunks": 0, "max_page": 0})
        entry["chunks"] += 1
        if isinstance(page, int) and page > entry["max_page"]:
            entry["max_page"] = page
    return sorted(counts.values(), key=lambda d: d["source"])


def corpus_stats() -> dict:
    try:
        db = _get_db()
    except CorpusMissing as e:
        return {"available": False, "reason": str(e).splitlines()[0]}
    return {"available": True, "chunks": db._collection.count(), "path": str(CHROMA_DIR)}
