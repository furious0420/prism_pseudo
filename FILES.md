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

## Day 8 — Case memory

| File | Task | What it does |
|---|---|---|
| `backend/models/case_memory.py` | D8-01 | `find_similar_cases(query, k)` over `data/history_cases.json`, embedded with the same MiniLM as Day 3. **Nothing in the tracker creates that file** — returns `[]` with a reason until someone authors ~15–20 cases. |

## Day 9 — Backend and frontend

| File | Task | What it does |
|---|---|---|
| `backend/models/pipeline.py` | D9-01 | `run_diagnosis(image, query)` — detection → diagnosis → risk → case memory, in the tracker's order. **Every stage is failure-isolated**: a dead GPU or a missing case file degrades one section and leaves the rest, so the response is never a 500. |
| `backend/app.py` | D9-01 | `POST /diagnose` (multipart: `image`, `query`), upload size and type validation, JSON errors for every status. |
| `frontend/src/App.jsx` | D9-02 | Upload form; renders risk, diagnosis with citations, the manual passages used, detections, similar cases, and per-stage timings. Shows a live counter while generating, and warns up front when a stage is not ready. |
| `backend/scripts/smoke_diagnose.py` | D9/D10/D11 | Exercises `/diagnose` as the UI does and writes `logs/day9_api.md` — stage readiness, per-request timings, per-stage breakdown and the response contract. `--edge-cases` runs the D10-02 fragility pass and fails if anything returns a 5xx. |

---

## Generated reports (one per day, in `backend/logs/`)

| File | Written by |
|---|---|
| `day2_benchmark.md` | `scripts/bench_llm.py` |
| `day3_retrieval.md` | `scripts/verify_retrieval.py` |
| `day4_examples.md` | `scripts/run_examples.py` |
| `day9_api.md` | `scripts/smoke_diagnose.py` |

These are results, not noise — the timings feed the pitch deck's evidence slide and
the reports let a teammate see the system works without re-running anything. They are
gitignored by default; commit them with `git add -f backend/logs/*.md`.

## Reading order for someone new

`models/llm.py` → `models/retrieval.py` → `models/rag.py` → `models/pipeline.py` → `app.py`.
That follows the data: text in, manual passages retrieved, answer generated, stages combined, HTTP served.

## Not in git, by design

`.env` (holds AWS keys), `venv/`, `node_modules/`, `chroma_db/` (rebuild with `ingest_corpus.py`),
`data/corpus_raw/*.pdf` (FAA manuals — S3 `corpus/` prefix), `*.gguf` and `*.pt` weights.
