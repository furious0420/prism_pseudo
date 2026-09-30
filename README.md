# PRISM — Proactive Reasoning & Inspection System for Multi-Modal Edge Diagnostics

PRISM is an offline, edge-deployed AI diagnostic assistant for aerospace MRO
(Maintenance, Repair & Overhaul) technicians. A technician describes a symptom,
optionally attaches a photo and live telemetry readings, and PRISM returns a
diagnosis grounded in real FAA maintenance manuals — with the passages it used,
a risk score, and similar past repairs.

**Everything in the diagnosis path runs on the machine.** No cloud calls.

Built for the Tata Technologies InnoVent-27 hackathon (Aerospace track); this
repo is the post-hackathon build-out.

## What actually works today

| Capability | State |
|---|---|
| Grounded diagnosis with citations | **Working.** 5,364 passages from 3 real FAA advisory circulars, retrieved and cited. Declines rather than guessing when the manuals don't cover a query. |
| Local LLM | **Working.** Phi-3 Mini via Ollama, ~17 tok/s on the dev laptop. |
| Risk scoring | **Working.** 0-100 score from telemetry thresholds + any detected defect, with a per-factor breakdown. |
| Case memory | **Working.** 18 authored cases, similarity search, and write-back when you resolve a diagnosis. |
| Defect detection | **Partial.** The pipeline works, but runs *pretrained* YOLOv8n (COCO classes) because no labelled aerospace defect dataset has been sourced yet. Every result is flagged `pretrained: true` so nothing overclaims. See `docs/no_aws_plan.md`. |
| Cloud sync (S3 / Greengrass) | **Not built.** Out of scope for this stage, and never part of the diagnosis path by design. |

## Quick start

Needs [Ollama](https://ollama.com) running with `phi3:mini` pulled, Python
3.10-3.12 and Node 18+.

```bash
# backend
cd backend
python -m venv venv
venv\Scripts\activate          # Windows;  source venv/bin/activate elsewhere
pip install -r ../requirements.txt
python scripts/ingest_corpus.py   # builds the vector index (first run only)
python app.py                     # http://127.0.0.1:5000

# frontend, in a second terminal
cd frontend
npm ci
npm run dev                       # http://localhost:5173
```

Check `GET /health/pipeline` — all four stages should report `available: true`.

## Layout

```
backend/
├── app.py              Flask API
├── models/             llm · retrieval · rag · detect · risk · case_memory · pipeline
├── scripts/            ingest, benchmarks, verification, smoke tests
├── data/
│   ├── corpus_raw/     FAA advisory circulars (committed)
│   └── history_cases.json
└── logs/               generated evidence reports, one per tracker day
frontend/src/           React UI — App.jsx, ErrorBoundary.jsx, index.css
docs/                   no_aws_plan.md, the original demo mockup
sample_images/          a photo for exercising the detection path
infra/                  least-privilege IAM policy, for when AWS is available
```

`FILES.md` explains every file and which tracker day it belongs to.

## API

| Endpoint | Purpose |
|---|---|
| `GET /health`, `/health/llm`, `/health/pipeline` | liveness and per-stage readiness |
| `POST /diagnose` | the full pipeline, one JSON response |
| `POST /diagnose/stream` | same, streamed stage-by-stage (SSE) |
| `GET /corpus/documents`, `/corpus/search` | what's indexed; retrieval without the LLM |
| `GET /memory/cases`, `POST /memory/log-case` | browse case memory; log a resolved case |

## Honest caveats

These are deliberate and documented rather than hidden — a jury is likely to
probe them:

- **The detector doesn't detect defects yet.** It's the pretrained COCO model.
  A photo of real corrosion returns zero detections.
- **Risk thresholds are illustrative**, not certified airworthiness limits.
  Real limits come from the type certificate / CMM for a specific component.
- **SAE J1979 is an automotive OBD-II standard.** Aviation uses ATA chapters
  and MSG-3. The reference needs justifying or swapping in the deck.
- **Retrieved passages show PDF extraction artifacts** (hyphenation, table-of-
  contents dot leaders). That's the raw text the model actually read, shown
  as-is rather than cleaned up for appearances.
