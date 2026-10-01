"""D11-02 — capture real metrics on THIS machine and write a results doc.

    python app.py                       # in another terminal
    python scripts/capture_metrics.py

Measures (1) retrieval latency, in-process, and (2) end-to-end POST /diagnose
latency over HTTP, plus how often the answer was grounded / cited / refused.
Writes logs/day11_metrics_<date>.md and a raw JSON beside it.

It does NOT measure detector accuracy. That needs the fine-tuned weights and
the labelled validation set; the doc says so rather than quoting numbers this
run did not produce.
"""
import json
import platform
import statistics
import sys
import time
from datetime import date
from pathlib import Path

import requests

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from models.retrieval import search  # noqa: E402

BASE = "http://127.0.0.1:5000"

# In-scope queries (Day 3 set) + out-of-scope ones, so the refusal rate is
# measured too rather than only the happy path.
IN_SCOPE = [
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
OUT_OF_SCOPE = [
    "how do I fix my coffee machine",
    "what is the torque spec for the Boeing 737-800 CFM56 fan blade retaining bolt",
]


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def main() -> int:
    # 1. retrieval, in-process. First call loads the embedding model, so time
    #    it separately and report warm numbers as the headline.
    t0 = time.perf_counter()
    search(IN_SCOPE[0], k=3)
    cold_ms = (time.perf_counter() - t0) * 1000
    warm = []
    for q in IN_SCOPE:
        t0 = time.perf_counter()
        search(q, k=3)
        warm.append((time.perf_counter() - t0) * 1000)

    # 2. end-to-end over HTTP
    try:
        requests.get(f"{BASE}/health", timeout=5).raise_for_status()
    except requests.RequestException as e:
        sys.exit(f"backend not reachable at {BASE} ({e}).  fix -> python app.py")

    rows = []
    for q in IN_SCOPE + OUT_OF_SCOPE:
        t0 = time.perf_counter()
        try:
            r = requests.post(f"{BASE}/diagnose", data={"query": q}, timeout=300)
            ms = (time.perf_counter() - t0) * 1000
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            rows.append({
                "query": q, "in_scope": q in IN_SCOPE, "status": r.status_code,
                "ms": round(ms), "grounded": body.get("grounded"),
                "cited_ok": body.get("cited_ok"), "refused": body.get("refused"),
                "citations": len(body.get("citations") or []),
            })
        except requests.RequestException as e:
            rows.append({"query": q, "in_scope": q in IN_SCOPE, "status": None,
                         "ms": round((time.perf_counter() - t0) * 1000), "error": str(e)})
        print(f"{rows[-1]['ms']:>7} ms  {rows[-1]['status']}  {q[:60]}", flush=True)

    ok = [r for r in rows if r["status"] == 200]
    times = [r["ms"] / 1000 for r in ok]
    ins = [r for r in rows if r["in_scope"] and r["status"] == 200]
    outs = [r for r in rows if not r["in_scope"] and r["status"] == 200]

    stamp = date.today().isoformat()
    out = BACKEND / "logs" / f"day11_metrics_{stamp}.md"
    L = [
        f"# Day 11 — metrics captured on this machine ({stamp})",
        "",
        f"Machine: {platform.platform()}, Python {platform.python_version()}. "
        "Generation on CPU via Ollama (`phi3:mini`).",
        "Reproduce: `python app.py`, then `python scripts/capture_metrics.py`.",
        "",
        "## Retrieval latency (in-process, 10 queries, k=3)",
        "",
        f"- Cold first call (loads embedding model): {cold_ms:.0f} ms",
        f"- Warm: **avg {statistics.mean(warm):.0f} ms**, median {statistics.median(warm):.0f} ms, "
        f"min {min(warm):.0f} ms, max {max(warm):.0f} ms",
        "",
        f"## End-to-end `POST /diagnose` ({len(rows)} requests, text-only)",
        "",
        f"- Succeeded (HTTP 200): **{len(ok)}/{len(rows)}**; "
        f"non-200 or errors: {len(rows) - len(ok)}",
    ]
    if times:
        L += [f"- Latency: **median {statistics.median(times):.1f} s**, "
              f"mean {statistics.mean(times):.1f} s, p90 {pct(times, 90):.1f} s, "
              f"min {min(times):.1f} s, max {max(times):.1f} s"]
    L += [
        f"- In-scope queries ({len(ins)}): answered {sum(1 for r in ins if not r['refused'])}, "
        f"refused {sum(1 for r in ins if r['refused'])}, "
        f"answered with all citations real {sum(1 for r in ins if not r['refused'] and r['cited_ok'])}, "
        f"answered but uncited/unverified {sum(1 for r in ins if not r['refused'] and not r['cited_ok'])}",
        f"- Out-of-scope queries ({len(outs)}): refused {sum(1 for r in outs if r['refused'])}/{len(outs)}",
        "",
        "| Query | Scope | s | grounded | refused | citations ok |",
        "|---|---|---:|---|---|---|",
    ]
    for r in rows:
        L.append(f"| {r['query'][:62]} | {'in' if r['in_scope'] else 'out'} | {r['ms']/1000:.1f} | "
                 f"{r.get('grounded')} | {r.get('refused')} | {r.get('cited_ok')} |")
    L += [
        "",
        "## Detection metrics (precision / recall / mAP)",
        "",
        "**Not measured in this run.** `model.val()` needs the fine-tuned "
        "`runs/detect/train/weights/best.pt` and the labelled validation split; "
        "neither is present on this machine. The figures in "
        "`day11_metrics.md` (precision 0.646, recall 0.472, mAP50 0.465) were "
        "recorded elsewhere and are **carried over, not reproduced here**.",
        "",
        "## Caveats",
        "",
        "- Text-only requests; image-path latency is not included.",
        f"- {len(rows)} requests is a small sample; a different run will differ, "
        "mostly in generation time.",
        "- `grounded`/`cited_ok` show the answer cited a retrieved page, not that the "
        "claim is supported by it.",
    ]
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    (BACKEND / "logs" / f"day11_metrics_{stamp}_raw.json").write_text(
        json.dumps({"retrieval_warm_ms": warm, "cold_ms": cold_ms, "requests": rows}, indent=1),
        encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
