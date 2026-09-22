"""D3-02 — does retrieval actually return relevant passages?

    python scripts/verify_retrieval.py

Runs realistic technician queries, prints the top hits, and writes
logs/day3_retrieval.md. Judge the output yourself: the score tells you how
confident the index is, not whether the passage answers the question.

If results are poor, re-ingest with different chunking:
    python scripts/ingest_corpus.py --reset --chunk-size 1200 --overlap 200
"""
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.retrieval import CorpusMissing, corpus_stats, search  # noqa: E402

QUERIES = [
    "corrosion on landing gear strut",
    "hairline crack in wing spar",
    "pitting corrosion depth limits",
    "how to inspect for intergranular corrosion",
    "dent in fuselage skin allowable damage",
    "stress corrosion cracking in aluminium alloy",
    "non-destructive inspection methods for cracks",
    "surface corrosion removal procedure",
    "fastener hole elongation repair",
    "exfoliation corrosion treatment",
]

K = 3
LOW_SCORE = 0.25  # cosine similarity; below this the index likely has
                  # nothing on the topic. Calibrate once you see real numbers.


def main() -> int:
    try:
        stats = corpus_stats()
    except Exception as e:
        print("retrieval unavailable:", e)
        return 1
    if not stats.get("available"):
        print(stats.get("reason"))
        return 1

    print(f"index: {stats['chunks']} chunks at {stats['path']}\n")

    out = Path(__file__).resolve().parents[1] / "logs" / "day3_retrieval.md"
    out.parent.mkdir(parents=True, exist_ok=True)

    timings, weak = [], []
    with out.open("w", encoding="utf-8") as f:
        f.write(f"# Day 3 — retrieval spot-check ({datetime.now():%Y-%m-%d %H:%M})\n\n")
        f.write(f"Index: {stats['chunks']} chunks. Top-{K} per query.\n\n")

        for q in QUERIES:
            t0 = time.perf_counter()
            try:
                hits = search(q, k=K)
            except CorpusMissing as e:
                print(e)
                return 1
            dt = time.perf_counter() - t0
            timings.append(dt)

            top = hits[0]["score"] if hits else 0.0
            if top < LOW_SCORE:
                weak.append((q, top))

            flag = "  <-- WEAK" if top < LOW_SCORE else ""
            print(f"{q!r}  ({dt*1000:.0f} ms, top score {top:.3f}){flag}")
            f.write(f"## {q}\n\n_{dt*1000:.0f} ms_\n\n")
            for i, h in enumerate(hits, 1):
                snippet = h["text"].replace("\n", " ")[:300]
                print(f"   {i}. [{h['source']} p.{h['page']}] {h['score']:.3f}  {snippet[:110]}...")
                f.write(f"{i}. **{h['source']} p.{h['page']}** (score {h['score']:.3f})  \n"
                        f"   {snippet}...\n\n")
            print()

        avg_ms = sum(timings) / len(timings) * 1000
        f.write(f"\n## Summary\n\n- Average retrieval latency: **{avg_ms:.0f} ms** "
                f"(feeds the D11-02 metrics)\n")
        if weak:
            f.write(f"- {len(weak)} quer(y/ies) returned nothing confident:\n")
            for q, s in weak:
                f.write(f"  - `{q}` (top score {s:.3f})\n")
            f.write("\n  Either the corpus genuinely lacks that topic — add a manual that "
                    "covers it — or chunks are too small to carry context. Try "
                    "`--chunk-size 1200 --overlap 200` and re-run.\n")
        else:
            f.write("- Every query returned at least one confident hit.\n")
        f.write("\n**Judge these by reading them, not by the scores.** A high score on an "
                "irrelevant passage is exactly the failure mode that produces a confident "
                "wrong diagnosis on Day 4.\n")

    print(f"average retrieval: {avg_ms:.0f} ms")
    if weak:
        print(f"{len(weak)} weak quer(y/ies) — see the report")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
