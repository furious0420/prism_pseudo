"""D2-02 — measure what the demo laptop actually does, and write it up.

    python scripts/bench_llm.py [--repeats N]

Writes backend/logs/day2_benchmark.md. Run it on the ACTUAL presenting laptop.

Why it repeats each prompt: a single pass cannot tell a slow model from a fast
model that hit one stall. Generation speed and everything-else are reported
separately, because they have completely different fixes.
"""
import argparse
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.llm import backend_info, generate_with_stats  # noqa: E402

PROMPTS = [
    ("short", "Q: What is metal fatigue? A:"),
    ("medium",
     "You are an aircraft maintenance diagnostic assistant.\n"
     "Technician query: There is visible pitting on the landing gear strut "
     "near the lower bearing, approximately 2mm deep.\n"
     "Give a diagnosis and an immediate recommended action.\nDiagnosis:"),
    ("long",
     "You are an aircraft maintenance diagnostic assistant. Use ONLY the context below.\n\n"
     "Context:\n"
     + ("Corrosion is the electrochemical deterioration of a metal. In aircraft "
        "structures it commonly appears as pitting, exfoliation or intergranular "
        "attack. Inspection intervals are defined per the applicable maintenance "
        "manual chapter. Removal limits depend on the structural significance of "
        "the member and remaining material thickness. ") * 6
     + "\n\nTechnician query: Pitting corrosion found on a structurally significant "
       "member, depth unknown.\nDiagnosis:"),
]

MAX_TOKENS = 256


def gpu_info() -> tuple[str, float]:
    """Returns (description, fraction_used). fraction is -1 when unknown."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,name",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return "n/a (nvidia-smi returned nothing)", -1.0
        used, total, name = [x.strip() for x in out.stdout.strip().splitlines()[0].split(",")]
        frac = int(used) / int(total)
        return f"{used} MiB / {total} MiB ({name}) — {frac:.0%} used", frac
    except FileNotFoundError:
        return "n/a (no nvidia-smi — CPU-only machine)", -1.0
    except Exception as e:
        return f"n/a ({type(e).__name__})", -1.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=3,
                    help="runs per prompt (default 3; 1 cannot show variance)")
    args = ap.parse_args()

    info = backend_info()
    if not info.get("available"):
        print("No LLM backend available.\n", info.get("reason"))
        return 1

    gpu_desc, gpu_frac = gpu_info()
    print(f"backend : {info['backend']}\nmodel   : {info['model']}\nGPU     : {gpu_desc}\n")

    print("warming up (discarded) ...")
    warm = generate_with_stats(PROMPTS[0][1], max_tokens=64)
    print(f"  cold call: {warm.elapsed_s:.2f}s wall, {warm.overhead_s:.2f}s non-generation\n")

    rows = []
    for size, prompt in PROMPTS:
        for i in range(args.repeats):
            r = generate_with_stats(prompt, max_tokens=MAX_TOKENS)
            gen_s = r.tokens_out / r.tokens_per_sec if r.tokens_per_sec else r.elapsed_s
            rows.append((size, len(prompt), r.tokens_out, r.elapsed_s,
                         gen_s, r.overhead_s, r.tokens_per_sec))
            print(f"[{size:6} {i+1}/{args.repeats}] {r.tokens_out:>3} tok  "
                  f"{r.elapsed_s:>6.2f}s wall = {gen_s:>5.2f}s gen + "
                  f"{r.overhead_s:>5.2f}s other   ({r.tokens_per_sec:.1f} tok/s)", flush=True)

    tps = [r[6] for r in rows]
    walls = [r[3] for r in rows]
    overs = [r[5] for r in rows]
    med_tps, med_wall = statistics.median(tps), statistics.median(walls)
    max_wall, med_over, max_over = max(walls), statistics.median(overs), max(overs)

    out = Path(__file__).resolve().parents[1] / "logs" / "day2_benchmark.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        f.write(f"# Day 2 — LLM performance ({datetime.now():%Y-%m-%d %H:%M})\n\n")
        f.write(f"- Backend: `{info['backend']}`  Model: `{info['model']}`\n")
        f.write(f"- GPU: {gpu_desc}\n")
        f.write(f"- Repeats per prompt: {args.repeats}  Max tokens: {MAX_TOKENS}\n\n")
        f.write("| prompt | chars | tok | wall (s) | generation (s) | other (s) | tok/s |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for size, chars, tok, wall, gen, over, t in rows:
            f.write(f"| {size} | {chars} | {tok} | {wall:.2f} | {gen:.2f} | {over:.2f} | {t:.1f} |\n")
        f.write(f"\n**Median {med_tps:.1f} tok/s. Typical call {med_wall:.2f}s, "
                f"worst {max_wall:.2f}s. Non-generation overhead: median "
                f"{med_over:.2f}s, worst {max_over:.2f}s.**\n\n")

        f.write("## Demo verdict\n\n")
        # Judge the TYPICAL call. One stall does not make a model slow.
        if med_wall <= 10:
            f.write(f"Generation is fine — a typical diagnosis lands in {med_wall:.1f}s.\n")
        elif med_wall <= 18:
            f.write(f"Usable but slow at {med_wall:.1f}s typical. Lower MAX_TOKENS "
                    "(a diagnosis rarely needs 256) and show a spinner in the Day 9 UI.\n")
        else:
            f.write(f"Too slow: {med_wall:.1f}s on a typical call, and that is generation "
                    "itself, not overhead. Confirm the GPU is in use, then try a smaller "
                    "quant.\n")

        if max_over > 5:
            f.write(f"\n**Stall detected.** One or more calls spent {max_over:.1f}s outside "
                    "generation while the model itself ran at full speed. That is the model "
                    "being unloaded or evicted from VRAM and reloaded, not slow inference. "
                    "PRISM now sends `keep_alive` to hold it resident. If stalls persist, "
                    "VRAM pressure is the cause — lower `PRISM_N_CTX` (4096 -> 2048 shrinks "
                    "the KV cache) and close other GPU consumers before demoing.\n")

        if 0 <= gpu_frac:
            if gpu_frac > 0.75:
                f.write(f"\n**VRAM is {gpu_frac:.0%} full with only the LLM loaded.** Day 6 "
                        "adds YOLOv8 and Day 9 runs both in one request. Plan for this now: "
                        "run detection on CPU (fast enough for single images), or unload the "
                        "LLM around detection. Do not discover it on Day 10.\n")
        f.write("\n## Cold start\n\nSend one throwaway prompt during setup so the jury's "
                "first question hits a warm model.\n")

    print(f"\nmedian {med_tps:.1f} tok/s | typical {med_wall:.2f}s | worst {max_wall:.2f}s "
          f"| worst overhead {max_over:.2f}s")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
