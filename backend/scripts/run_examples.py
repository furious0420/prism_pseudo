"""D4-02 — run the grounded diagnosis loop over varied queries and flag problems.

    python scripts/run_examples.py

Writes logs/day4_examples.md with every query, the context that was retrieved,
the diagnosis produced, and an automatic verdict.

The tracker asks you to "flag any hallucinated or irrelevant answers". Reading
for that by hand does not scale and is easy to fool, so this checks two things
mechanically:

  UNCITED   the answer made claims without citing any manual extract
  FABRICATED the answer cited a document that was never retrieved

The last query is deliberately outside the corpus. A correct system REFUSES it.
If it produces a confident answer instead, that is the single most important
finding of Day 4 and it needs fixing before Day 9 puts it in front of a jury.
"""
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.llm import LLMUnavailable  # noqa: E402
from models.rag import PROMPT_TEMPLATE, diagnose  # noqa: E402
from models.retrieval import CorpusMissing  # noqa: E402

QUERIES = [
    "Pitting corrosion on the landing gear strut, roughly 2mm deep.",
    "Hairline crack found on the wing spar cap during scheduled inspection.",
    "White powdery deposit on an aluminium panel near the wheel well.",
    "Dent in the fuselage skin, about 40mm across and shallow.",
    "Which inspection method finds subsurface cracks in aluminium?",
    "Surface grains lifting and flaking on a 7075-T6 component.",
    # Deliberately out of corpus — the system should decline, not invent.
    "How do I replace the filter in the crew coffee machine?",
]


def main() -> int:
    out = Path(__file__).resolve().parents[1] / "logs" / "day4_examples.md"
    out.parent.mkdir(parents=True, exist_ok=True)

    results, failures = [], []
    for i, q in enumerate(QUERIES, 1):
        print(f"[{i}/{len(QUERIES)}] {q[:62]}...", flush=True)
        try:
            r = diagnose(q)
        except (CorpusMissing, LLMUnavailable) as e:
            print(f"\n{type(e).__name__}: {e}")
            return 1
        results.append(r)

        verdict = "OK"
        if not r.grounded and not r.refused:
            verdict = "ANSWERED WITHOUT CONTEXT"
        elif r.grounded and not r.cited_ok:
            verdict = "UNCITED or FABRICATED CITATION"
        elif r.refused and r.grounded:
            verdict = "REFUSED DESPITE HAVING CONTEXT"
        if verdict != "OK":
            failures.append((q, verdict))
        print(f"      grounded={r.grounded} top={r.top_score:.3f} "
              f"cited={r.citations or 'none'} -> {verdict}")

    last = results[-1]
    with out.open("w", encoding="utf-8") as f:
        f.write(f"# Day 4 — grounded diagnosis examples ({datetime.now():%Y-%m-%d %H:%M})\n\n")
        f.write(f"Backend `{last.backend}` / model `{last.model}`\n\n")

        for r in results:
            f.write(f"## {r.query}\n\n")
            f.write(f"- grounded: **{r.grounded}** (top score {r.top_score:.3f})\n")
            f.write(f"- citations: {', '.join(r.citations) if r.citations else '_none_'}\n")
            f.write(f"- refused: {r.refused}\n")
            f.write(f"- timing: {r.retrieval_ms:.0f} ms retrieval + "
                    f"{r.generation_ms:.0f} ms generation = {r.total_ms:.0f} ms\n\n")
            if r.hits:
                f.write("**Retrieved context**\n\n")
                for h in r.hits:
                    f.write(f"- `{h['source']} p.{h['page']}` ({h['score']:.3f}): "
                            f"{h['text'][:200].replace(chr(10), ' ')}...\n")
                f.write("\n")
            f.write(f"**Diagnosis**\n\n> {r.diagnosis.replace(chr(10), chr(10) + '> ')}\n\n---\n\n")

        n = len(results)
        f.write("## Summary\n\n")
        f.write(f"- Queries: {n}\n")
        f.write(f"- Grounded: {sum(r.grounded for r in results)}/{n}\n")
        f.write(f"- Cited correctly: {sum(r.cited_ok for r in results)}/{n}\n")
        f.write(f"- Refused: {sum(r.refused for r in results)}/{n} "
                f"(expect at least 1 — the coffee machine query)\n")
        avg = sum(r.total_ms for r in results) / n
        f.write(f"- Average end-to-end: **{avg:.0f} ms** (feeds D11-02)\n\n")

        if failures:
            f.write("### Problems found\n\n")
            for q, v in failures:
                f.write(f"- **{v}** — `{q}`\n")
            f.write("\nFixes, in order of likelihood:\n"
                    "1. Tighten the prompt — make the citation rule and the refusal "
                    "sentence more emphatic.\n"
                    "2. Raise `GROUNDING_THRESHOLD` in models/rag.py so weak retrieval "
                    "stops reaching the model at all.\n"
                    "3. Re-chunk the corpus — passages too small to carry context force "
                    "the model to fill gaps from memory.\n")
        else:
            f.write("### Problems found\n\nNone. Every answer was either grounded and "
                    "cited, or correctly declined.\n")

        if not last.refused:
            f.write("\n> **The out-of-corpus query was answered instead of declined.** "
                    "This is the most important thing to fix before Day 9. A confident "
                    "answer to a question the manuals do not cover is exactly what a "
                    "jury will probe.\n")

        f.write("\n## Prompt template (D4-02 step 4)\n\n```\n")
        f.write(PROMPT_TEMPLATE)
        f.write("\n```\n")

    print(f"\n{len(failures)} problem(s) flagged" if failures else "\nno problems flagged")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
