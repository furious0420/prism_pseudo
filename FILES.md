# PRISM — what every file is, and which tracker day it belongs to

Run everything from `backend/` with the venv active:

```
cd backend
.\venv\Scripts\Activate.ps1      # Windows
pip install -r ..\requirements.txt
```

---

## Day 1 — Foundations

| File | Task | What it does |
|---|---|---|
| `backend/app.py` | D1-01 | Flask app. `GET /health` since Day 1; `/health/llm`, `/health/pipeline` and `POST /diagnose` added later. |
| `frontend/` | D1-01 | Vite + React. `src/App.jsx` was a health-check page until Day 9 replaced it. |
| `backend/.env.example` | D1-02 | Every config var. Copy to `backend/.env`; never commit the real one. |
| `infra/iam-policy-prism-dev.json` | D1-02 | Least-privilege IAM policy, scoped to the PRISM bucket only. |
| `backend/scripts/s3_check.py` | D1-02 | Verifies region, read, write, the four prefixes and the SOP tags. `--bootstrap` creates the prefixes. Exits non-zero on anything blocking. |
| `backend/scripts/dataset_check.py` | D1-03 | Scans S3 and a local folder for a labeled dataset; identifies YOLO / COCO / Pascal VOC / Ground Truth manifest and prints the Day 5 consequence. |
| `backend/scripts/pdf_probe.py` | D1-04 | Are the manuals real text or scans? A scan makes `pdfplumber` return empty strings and stalls Day 3 silently. |
| `requirements.txt` (root) | D1-04 | Every dependency, mapped to its day, plus the non-pip tools and the install-order trap (CUDA torch first). |

## Day 2 — Local LLM inference

| File | Task | What it does |
|---|---|---|
| `backend/models/llm.py` | D2-01 | **`generate(prompt) -> str`** — the one function the rest of PRISM calls. Backed by Ollama or `llama_cpp`, auto-detected. Both fully offline. |
| `backend/scripts/bench_llm.py` | D2-02 | Tokens/sec, load time, cold start, GPU memory. Repeats each prompt and reports generation time separately from everything else, so a stall is never mistaken for a slow model. Writes `logs/day2_benchmark.md`. |

## Day 3 — Retrieval

| File | Task | What it does |
|---|---|---|
| `backend/scripts/ingest_corpus.py` | D3-01 | PDFs → per-page text → chunks → Chroma. Every chunk keeps its source file and page number so a diagnosis can cite them. `--reset` rebuilds. |
| `backend/models/retrieval.py` | D3-01 | `search(query, k)` and `format_context()`. Owns the single definition of where the index lives, and the shared MiniLM instance Day 8 reuses. |
| `backend/scripts/verify_retrieval.py` | D3-02 | Ten technician queries, top-3 each, flags queries with no confident hit, records average latency. Writes `logs/day3_retrieval.md`. |

## Day 4 — Grounded generation

| File | Task | What it does |
|---|---|---|
| `backend/models/rag.py` | D4-01 | `diagnose(query)` — retrieval + generation. Prompt forbids outside knowledge and demands `[document p.N]` citations. Reports whether the answer cited a source that was *actually retrieved*, so a fabricated citation is caught mechanically. |
| `backend/scripts/run_examples.py` | D4-02 | Seven queries, the last deliberately outside the corpus. Flags UNCITED, FABRICATED and ANSWERED-WITHOUT-CONTEXT. Records the prompt template. Writes `logs/day4_examples.md`. |

## Day 6 — CV detection

| File | Task | What it does |
|---|---|---|
| `backend/models/detect.py` | D6-01 | `detect(image_path)`. Uses fine-tuned weights when present, otherwise pretrained YOLOv8n — which proves the plumbing but does **not** know defect classes. Every result carries a `pretrained` flag so the UI says so honestly. Defaults to **CPU**, because the LLM already uses 78% of this machine's VRAM. |

## Day 7 — Risk scoring

| File | Task | What it does |
|---|---|---|
| `backend/models/risk.py` | D7-01 | `score_risk(defect_type, confidence)`. Pure input → output. Confidence can only lower severity, never raise it. `worst_risk()` governs multi-defect images — averaging would let three scratches hide a crack. **Adjust `SEVERITY` to your real YOLO classes.** |
| `backend/models/risk.py` | D7-01 | `score_telemetry(telemetry, defect_risk)` — the 0-100 score. Scores temperature / pressure / runtime / vibration against `PARAMETERS`, combines with any detected defect, returns score + per-factor breakdown + band + advisory. Bands are 0-33 Low / 34-66 Medium / 67-100 High. **Thresholds are illustrative demo values, not certified limits** — that caveat is surfaced in the UI too. Missing or unparseable readings are skipped, never assumed nominal. Added because risk previously scored only detections, so the risk panel was empty on every text-only diagnosis. |

## Day 8 — Case memory

| File | Task | What it does |
|---|---|---|
| `backend/models/case_memory.py` | D8-01 | `find_similar_cases(query, k)` over `data/history_cases.json`, embedded with the same MiniLM as Day 3. The file now exists (18 hand-authored cases); it degrades to `[]` with a reason if it ever goes missing. |
| `backend/models/case_memory.py` | post-D9 | `log_case(...)` appends a resolved case and `list_cases()` returns them all. The write goes via temp-file + `os.replace()` so a crash cannot truncate the file, and it **resets the module embedding cache** — without that, `_load()`'s load-once guard would serve a stale list for the rest of the process's life and a newly logged case would be invisible to similarity search until restart. |

## Day 9 — Backend and frontend

| File | Task | What it does |
|---|---|---|
| `backend/models/pipeline.py` | D9-01 | `run_diagnosis(image, query)` — detection → diagnosis → risk → case memory, in the tracker's order. **Every stage is failure-isolated**: a dead GPU or a missing case file degrades one section and leaves the rest, so the response is never a 500. |
| `backend/app.py` | D9-01 | `POST /diagnose` (multipart: `image`, `query`, optional telemetry fields), upload size and type validation, JSON errors for every status. |
| `backend/app.py` | post-D9 | `POST /diagnose/stream` — same pipeline over SSE, one event per stage as it completes. The upload is saved *before* the generator starts, because the request context is gone by the time Flask pulls from it. |
| `backend/app.py` | post-D9 | `GET /corpus/documents`, `GET /corpus/search` (retrieval only, no LLM), `GET /memory/cases`, `POST /memory/log-case`. |
| `frontend/src/ErrorBoundary.jsx` | post-D9 | Contains render-time exceptions. Without it any thrown error unmounts the tree to a blank white page — unrecoverable mid-demo without a reload. |
| `frontend/src/App.jsx` | D9-02 | Four tabs (Diagnose / Manuals / Case History / System Status) via local state — no router dependency. Two-column dashboard: input left, results right. Renders the 0-100 risk panel, diagnosis with citations, **the retrieved passage text itself** (expandable — this is what proves grounding), detections, similar cases, per-stage timings, and a "Mark as resolved" write-back. Consumes the SSE stream so stages fill in as they complete, falling back to plain `/diagnose` if streaming fails. Header pill polls `/health/pipeline` every 12s and shows ready / degraded / unreachable. |
| `backend/scripts/smoke_diagnose.py` | D9/D10/D11 | Exercises `/diagnose` as the UI does and writes `logs/day9_api.md` — stage readiness, per-request timings, per-stage breakdown and the response contract. `--edge-cases` runs the D10-02 fragility pass and fails if anything returns a 5xx. |

---

## Generated reports (one per day, in `backend/logs/`)

| File | Written by |
|---|---|
| `day2_benchmark.md` | `scripts/bench_llm.py` |
| `day3_retrieval.md` | `scripts/verify_retrieval.py` |
| `day4_examples.md` | `scripts/run_examples.py` |
| `day9_api.md` | `scripts/smoke_diagnose.py` |
| `day10_integration.md` | hand-written from the Playwright browser pass |
| `day11_metrics.md`, `day11_reliability_raw.json` | reliability pass + consolidated metrics |

These are results, not noise — the timings feed the pitch deck's evidence slide and
the reports let a teammate see the system works without re-running anything. They are
gitignored by default; commit them with `git add -f backend/logs/*.md`.

## Reading order for someone new

`models/llm.py` → `models/retrieval.py` → `models/rag.py` → `models/pipeline.py` → `app.py`.
That follows the data: text in, manual passages retrieved, answer generated, stages combined, HTTP served.

## Not in git, by design

`.env` (holds AWS keys), `venv/`, `node_modules/`, `chroma_db/` (rebuild with `ingest_corpus.py`),
`*.gguf` and `*.pt` weights.

The FAA corpus PDFs (`backend/data/corpus_raw/`) and `backend/logs/*.md` **are**
committed — the corpus is small enough and the logs are evidence, not noise.

## Also in the repo

| Path | What |
|---|---|
| `docs/no_aws_plan.md` | How to finish Days 5-13 without AWS. Read before starting Day 5. |
| `docs/prism_demo_v4.html` | The original hackathon demo mockup — scripted, no backend. Reference for the intended pitch narrative. |
| `sample_images/` | A public-domain aircraft photo for exercising the detection path, with a README explaining why a corrosion photo detects nothing today. |
