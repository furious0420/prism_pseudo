"""D9/D10/D11 — exercise POST /diagnose the way the UI does, and time it.

    python scripts/smoke_diagnose.py                      # text-only
    python scripts/smoke_diagnose.py --image photo.jpg    # image + text
    python scripts/smoke_diagnose.py --edge-cases         # D10-02 fragility pass

Start the backend first:  python app.py
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BASE = "http://127.0.0.1:5000"


def post(query: str, image: Path | None = None) -> tuple[int, dict, float]:
    files = {}
    fh = None
    if image:
        fh = image.open("rb")
        files["image"] = (image.name, fh)
    try:
        t0 = time.perf_counter()
        r = requests.post(f"{BASE}/diagnose", data={"query": query}, files=files, timeout=300)
        ms = (time.perf_counter() - t0) * 1000
        try:
            body = r.json()
        except ValueError:
            body = {"_raw": r.text[:400]}
        return r.status_code, body, ms
    finally:
        if fh:
            fh.close()


def show(label: str, code: int, body: dict, ms: float) -> None:
    print(f"\n--- {label} ---")
    print(f"HTTP {code}  ({ms:.0f} ms)")
    if code != 200:
        print(f"  error : {body.get('error')}\n  detail: {body.get('detail')}")
        return
    print(f"  grounded : {body.get('grounded')}  cited_ok: {body.get('cited_ok')}  "
          f"refused: {body.get('refused')}")
    print(f"  detections: {len(body.get('detections') or [])}  "
          f"similar_cases: {len(body.get('similar_cases') or [])}")
    if body.get("overall_risk"):
        print(f"  risk     : {body['overall_risk']['level']}")
    diag = (body.get("diagnosis") or "")[:160].replace("\n", " ")
    print(f"  diagnosis: {diag}...")
    print("  stages:")
    for s in body.get("stages", []):
        bits = [f"{s['ms']:.0f} ms"]
        if s.get("skipped"): bits.append("skipped")
        if s.get("error"):   bits.append(f"ERROR {s['error']}")
        if s.get("note"):    bits.append(s["note"][:70])
        print(f"    {'ok ' if s['ok'] else 'FAIL'} {s['name']:<12} {' | '.join(bits)}")


def write_report(readiness: dict, rows: list[tuple], bad: list[tuple]) -> Path:
    """logs/day9_api.md — the Day 9 equivalent of the Day 2/3/4 reports."""
    out = Path(__file__).resolve().parents[1] / "logs" / "day9_api.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        f.write(f"# Day 9 — API check ({datetime.now():%Y-%m-%d %H:%M})\n\n")

        f.write("## Stage readiness\n\n")
        for name in ("llm", "corpus", "detector", "case_memory"):
            v = readiness.get(name) or {}
            mark = "ready" if v.get("available") else "NOT READY"
            f.write(f"- **{name}**: {mark}")
            if not v.get("available") and v.get("reason"):
                f.write(f" — {v['reason']}")
            f.write("\n")
        f.write(f"\nPipeline ready: **{readiness.get('ready')}**\n\n")

        f.write("## Requests\n\n")
        f.write("| case | HTTP | ms | grounded | cited | refused | risk | dets | cases |\n")
        f.write("|---|---:|---:|---|---|---|---|---:|---:|\n")
        for label, code, body, ms in rows:
            if code == 200:
                f.write(f"| {label} | {code} | {ms:.0f} | {body.get('grounded')} | "
                        f"{body.get('cited_ok')} | {body.get('refused')} | "
                        f"{body.get('risk_score') or '—'} | "
                        f"{len(body.get('detections') or [])} | "
                        f"{len(body.get('similar_cases') or [])} |\n")
            else:
                f.write(f"| {label} | {code} | {ms:.0f} | — | — | — | — | — | — |\n")

        ok_rows = [r for r in rows if r[1] == 200]
        if ok_rows:
            avg = sum(r[3] for r in ok_rows) / len(ok_rows)
            f.write(f"\nAverage successful request: **{avg:.0f} ms** (feeds D11-02).\n")

        f.write("\n## Per-stage timing, last successful request\n\n")
        last = next((r for r in reversed(rows) if r[1] == 200), None)
        if last:
            f.write("| stage | ok | ms | note |\n|---|---|---:|---|\n")
            for st in last[2].get("stages", []):
                note = st.get("error") or st.get("note") or ("skipped" if st.get("skipped") else "")
                f.write(f"| {st['name']} | {'yes' if st['ok'] else 'NO'} | {st['ms']:.0f} | {note} |\n")

        f.write("\n## Edge cases (D10-02)\n\n")
        if bad:
            f.write("**Failures returning 5xx — fix before the demo (D11-01):**\n\n")
            for label, code in bad:
                f.write(f"- `{label}` returned {code}\n")
        else:
            f.write("No 5xx responses. Every edge case degraded gracefully: each one "
                    "returned a normal response explaining what was missing, or a 4xx "
                    "naming the problem.\n")

        f.write("\n## Response contract (D9-01 step 4)\n\n```\n")
        f.write("detections[]   label, confidence, box, pretrained\n"
                "risks[]        level, severity, confidence, rationale, needs_human_review\n"
                "overall_risk   the governing risk — the WORST, not the average\n"
                "risk_score     convenience alias: overall_risk.level\n"
                "diagnosis      grounded text, citations inline as [document p.N]\n"
                "citations[]    parsed citation labels\n"
                "sources[]      source, page, score for each retrieved passage\n"
                "grounded       retrieval found something above threshold\n"
                "cited_ok       the answer cited a source that was actually retrieved\n"
                "refused        the model declined because the manuals do not cover it\n"
                "needs_input    set when there was nothing to diagnose, and why\n"
                "similar_cases[]  case_id, defect_type, resolution, similarity\n"
                "stages[]       name, ok, ms, skipped, error, note\n"
                "timing_ms      total\n```\n")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", type=Path)
    ap.add_argument("--query", default="Pitting corrosion on the landing gear strut, about 2mm deep.")
    ap.add_argument("--edge-cases", action="store_true", help="D10-02 fragility pass")
    args = ap.parse_args()

    try:
        h = requests.get(f"{BASE}/health", timeout=5)
        h.raise_for_status()
    except Exception as e:
        print(f"Backend not reachable at {BASE} ({type(e).__name__}).\n"
              f"  fix -> in another terminal: python app.py")
        return 1

    readiness = requests.get(f"{BASE}/health/pipeline", timeout=300).json()
    print("pipeline readiness:")
    for name in ("llm", "corpus", "detector", "case_memory"):
        v = readiness.get(name) or {}
        print(f"  {'ready    ' if v.get('available') else 'NOT READY'} {name}"
              f"{'' if v.get('available') else ' — ' + str(v.get('reason'))[:70]}")

    rows: list[tuple] = []
    if not args.edge_cases:
        code, body, ms = post(args.query, args.image)
        show("normal request", code, body, ms)
        rows.append(("normal request", code, body, ms))
        out = write_report(readiness, rows, [])
        print(f"\nwritten: {out}")
        return 0

    # D10-02: deliberately try to break it. None of these may return a 500.
    cases = [
        ("empty query, no image", "", None),
        ("whitespace only", "     ", None),
        ("nonsense query", "asdfkjh qwerty zxcvbn", None),
        ("very long query", "corrosion " * 400, None),
        ("out-of-corpus query", "How do I replace the crew coffee machine filter?", None),
        ("normal query", args.query, None),
    ]
    bad = []
    for label, q, img in cases:
        code, body, ms = post(q, img)
        show(label, code, body, ms)
        rows.append((label, code, body, ms))
        if code >= 500:
            bad.append((label, code))

    print("\n" + ("=" * 60))
    if bad:
        print("5xx found — fix these before the demo (D11-01):")
        for label, code in bad:
            print(f"  {code}  {label}")
    else:
        print("No 5xx. Every edge case degraded gracefully.")
    out = write_report(readiness, rows, bad)
    print(f"written: {out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
