"""D4-01 — grounded diagnosis: retrieval + generation.

    from models.rag import diagnose
    result = diagnose("pitting on the landing gear strut, about 2mm deep")
    print(result.diagnosis)

The whole point of this file is that the model answers FROM THE MANUALS rather
than from whatever it remembers. Three things enforce that:

  1. The prompt forbids outside knowledge and demands a [source p.N] citation
     on every claim.
  2. If retrieval returns nothing confident, the prompt says so explicitly and
     instructs the model to decline rather than guess.
  3. The result reports whether the answer actually cited a retrieved source,
     so a hallucination is measurable instead of something you have to notice.
"""
from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Running this file directly (python models/rag.py) puts models/ on sys.path
# instead of backend/, so "from models.llm import ..." cannot resolve. Put
# backend/ on the path when there is no package context, so both
# `python models/rag.py` and `python -m models.rag` work.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.llm import LLMUnavailable, generate_with_stats
from models.retrieval import CorpusMissing, Hit, format_context, search

# Below this cosine similarity we treat retrieval as having found nothing
# useful. Calibrate against logs/day3_retrieval.md once you have real numbers.
GROUNDING_THRESHOLD = 0.25

DEFAULT_K = 3
DEFAULT_MAX_TOKENS = 400

# D4-02 step 4 asks for the finalised prompt template to be recorded. It lives
# here, as one constant, so it is never scattered through the codebase.
PROMPT_TEMPLATE = """You are an aircraft maintenance diagnostic assistant.

Answer ONLY from the maintenance manual extracts below. Do not use any outside \
knowledge, even if you are confident it is correct.

Rules:
- Cite the source for every claim, in the form [document p.N], exactly as the \
extract is labelled.
- If the extracts do not cover the query, reply exactly: \
"The provided manual extracts do not cover this." Do not guess.
- Be concise and practical. A technician is reading this at the aircraft.
- State the likely defect, then the recommended immediate action.

Manual extracts:
{context}

Technician query: {query}

Diagnosis:"""

NO_CONTEXT_TEMPLATE = """You are an aircraft maintenance diagnostic assistant.

No relevant maintenance manual extracts were found for the query below.

You MUST reply exactly: "The provided manual extracts do not cover this."
Do not answer from your own knowledge.

Technician query: {query}

Diagnosis:"""

REFUSAL = "The provided manual extracts do not cover this."

# Matches the [document p.12] citation form the prompt asks for.
CITATION_RE = re.compile(r"\[([^\]]+?)\s+p\.(\d+)\]")

# "Likely defect: ..." and "1. do the thing", from the answer format above.
DEFECT_RE = re.compile(r"^\s*likely defect\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
ACTION_RE = re.compile(r"^\s*(\d+)[.)]\s+(.*\S)\s*$", re.MULTILINE)


def _parse_structure(text: str) -> tuple[Optional[str], list[str]]:
    """Opportunistically pull a likely-defect line and numbered actions out of
    the answer, if the model happened to produce them.

    NOT prompt-driven, deliberately. Instructing the model to always emit a
    "Likely defect / numbered actions" format was tried and reverted: asking
    phi3:mini for a citation per action made it mangle the document name
    ("AC_430.13-1B" for "AC_43.13-1B"), which _check_citations correctly reads
    as a fabricated citation, and tightening the format to one citation then
    sent it into a repetition loop that Ollama aborted with a 500. Both are in
    logs/day4_examples.md history. So the prompt is left as verified, and this
    parses structure only when it appears naturally — which it often does.

    Best-effort: anything unparsed comes back empty and the UI falls back to
    the prose. Never raises, never invents.
    """
    m = DEFECT_RE.search(text or "")
    defect = m.group(1).strip() if m else None

    actions: list[str] = []
    seen_numbers: set[int] = set()
    for num, body in ACTION_RE.findall(text or ""):
        n = int(num)
        # Guard against a restarting or duplicated list — take the first
        # occurrence of each number only.
        if n in seen_numbers:
            continue
        seen_numbers.add(n)
        actions.append(body.strip())
    return defect, actions


@dataclass
class DiagnosisResult:
    query: str
    diagnosis: str
    likely_defect: Optional[str] = None
    actions: list[str] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    grounded: bool = True      # retrieval found something above threshold
    cited_ok: bool = True      # the answer cited a source we actually retrieved
    refused: bool = False      # model correctly declined
    top_score: float = 0.0
    retrieval_ms: float = 0.0
    generation_ms: float = 0.0
    backend: str = ""
    model: str = ""

    @property
    def total_ms(self) -> float:
        return self.retrieval_ms + self.generation_ms

    def to_json(self) -> dict:
        """Shape D9-01 returns from POST /diagnose."""
        return {
            "query": self.query,
            "diagnosis": self.diagnosis,
            # Structured form of the same answer, when the model honoured the
            # format. Empty is normal and the UI falls back to the prose.
            "likely_defect": self.likely_defect,
            "actions": self.actions,
            "citations": self.citations,
            "sources": [
                # `text` is the actual retrieved passage. Without it the UI can
                # say WHICH page was cited but not WHAT it said, which is the
                # one thing that proves the answer is grounded rather than
                # recalled — the most probe-worthy claim in the whole demo.
                {"source": h["source"], "page": h["page"], "score": h["score"],
                 "text": h["text"]}
                for h in self.hits
            ],
            "grounded": self.grounded,
            "cited_ok": self.cited_ok,
            "refused": self.refused,
            "timing_ms": {
                "retrieval": round(self.retrieval_ms, 1),
                "generation": round(self.generation_ms, 1),
                "total": round(self.total_ms, 1),
            },
        }


def _is_refusal(text: str) -> bool:
    """Did the model decline?

    A plain substring test is wrong: the grounded prompt CONTAINS the refusal
    sentence as an instruction, and a chatty model that echoes its instructions
    would be misread as declining. The model is told to reply with exactly that
    sentence, so require it to lead the answer.
    """
    normalised = re.sub(r"\s+", " ", text).strip().rstrip(".").lower()
    target = REFUSAL.rstrip(".").lower()
    return normalised.startswith(target)


def _check_citations(text: str, hits: list[Hit]) -> tuple[list[str], bool]:
    """Which sources did the answer cite, and were they really retrieved?

    A citation naming a document that was never retrieved is a fabricated
    citation — worse than no citation at all, because it looks authoritative.
    """
    found = CITATION_RE.findall(text)
    retrieved = {(h["source"], str(h["page"])) for h in hits}
    citations, all_real = [], True
    for doc, page in found:
        label = f"[{doc} p.{page}]"
        citations.append(label)
        if (doc, page) not in retrieved:
            all_real = False
    return citations, (bool(citations) and all_real)


def diagnose(
    query: str,
    k: int = DEFAULT_K,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> DiagnosisResult:
    """Retrieve manual context for a technician query, then generate a grounded
    diagnosis. Raises CorpusMissing or LLMUnavailable with actionable messages."""
    t0 = time.perf_counter()
    hits = search(query, k=k)
    retrieval_ms = (time.perf_counter() - t0) * 1000

    top_score = hits[0]["score"] if hits else 0.0
    grounded = bool(hits) and top_score >= GROUNDING_THRESHOLD

    if grounded:
        prompt = PROMPT_TEMPLATE.format(context=format_context(hits), query=query)
    else:
        # Nothing confident came back. Do not hand the model context it will
        # feel obliged to use — ask it to decline instead.
        prompt = NO_CONTEXT_TEMPLATE.format(query=query)

    t0 = time.perf_counter()
    gen = generate_with_stats(prompt, max_tokens=max_tokens)
    generation_ms = (time.perf_counter() - t0) * 1000

    text = gen.text.strip()
    refused = _is_refusal(text)
    likely_defect, actions = (None, []) if refused else _parse_structure(text)
    citations, cited_ok = _check_citations(text, hits)
    if refused or not grounded:
        # Declining is the correct behaviour with no context; do not mark it
        # as a citation failure.
        cited_ok = True

    return DiagnosisResult(
        query=query,
        diagnosis=text,
        likely_defect=likely_defect,
        actions=actions,
        hits=hits if grounded else [],
        citations=citations,
        grounded=grounded,
        cited_ok=cited_ok,
        refused=refused,
        top_score=top_score,
        retrieval_ms=retrieval_ms,
        generation_ms=generation_ms,
        backend=gen.backend,
        model=gen.model,
    )


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "pitting corrosion on the landing gear strut, about 2mm deep"
    try:
        r = diagnose(q)
    except (CorpusMissing, LLMUnavailable) as e:
        sys.exit(f"{type(e).__name__}: {e}")
    print(f"query    : {r.query}\ngrounded : {r.grounded} (top score {r.top_score:.3f})")
    print(f"cited_ok : {r.cited_ok}  citations: {r.citations or 'none'}")
    print(f"timing   : {r.retrieval_ms:.0f} ms retrieval + {r.generation_ms:.0f} ms generation")
    print(f"\n{r.diagnosis}")
