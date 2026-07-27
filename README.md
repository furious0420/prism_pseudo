# PRISM — Proactive Reasoning & Inspection System for Multi-Modal Edge Diagnostics

PRISM is a fully offline, edge-deployed AI diagnostic assistant for aerospace MRO (Maintenance,
Repair & Overhaul) technicians. It combines computer-vision defect detection, a retrieval-augmented
local LLM for manual-grounded guidance, a rule-based risk scorer, and a self-improving case-memory
store — all designed to run with no dependency on internet connectivity, syncing back to the cloud
opportunistically when a connection is available.

Originally built for the Tata Technologies InnoVent-27 hackathon (Aerospace track); this repo covers
the post-hackathon build-out into a fuller working system.

## Tech stack

- **Vision:** YOLOv8, OpenCV — aerospace defect detection (cracks, corrosion, dents)
- **NLP / RAG:** Phi-3 Mini 3.8B (INT4/GGUF via llama.cpp), LangChain, ChromaDB, MiniLM-L6-v2 —
  grounded Q&A over FAA/EASA MRO manuals
- **Risk scoring:** rule-based scorer against SAE J1979 telemetry thresholds
- **Case memory:** rolling `history_cases.json` store with similarity lookup
- **Frontend:** React
- **Backend:** Flask
- **Offline-first sync:** AWS IoT Greengrass + S3

## Folder structure

```
prism-mro-copilot/
├── nlp/              # Phi-3, RAG, prompts
│   └── corpus/
├── vision/           # YOLOv8, OpenCV
│   └── dataset/
│       ├── images/
│       └── labels/
├── risk/             # rule-based risk scorer
├── memory/           # case memory (history_cases.json)
├── frontend/         # React dashboard
├── backend/          # Flask app + API routes
├── docs/             # architecture.md, sync.md, hil_validation.md
└── README.md
```

## Status

Repo scaffolding only — module build-out follows the phased plan in the project tracker
(Foundations → Core Modules → Case Memory → Sync & Validation → Polish & Demo).
