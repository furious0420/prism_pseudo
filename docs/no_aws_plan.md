# PRISM — completing Days 5-13 without AWS access

Reference doc, written 2026-09-28. If you're picking up the build and AWS
still isn't available, read this before starting Day 5 — it explains what's
genuinely blocked, what isn't, and the recommended path around it.

## Context

AWS access isn't currently usable: no `aws` CLI installed, and `backend/.env`
has empty `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` (only the region
placeholder is set). This blocks two tracker items that assume AWS:

- **D1-02** (S3 bucket structure) — already explicitly deferred this session.
- **D5-02** (CV dataset readiness) — the tracker's prescribed fallback for
  "no dataset exists" is a SageMaker Ground Truth labeling job, which needs
  AWS (S3 upload, a Ground Truth job, a private Cognito workforce).

Confirmed this is our exact situation: `vision/dataset/images/` and
`vision/dataset/labels/` are empty except `.gitkeep`, and no dataset folder
exists anywhere under `backend/data/` either.

**Why this is safe to work around, not a real blocker:** the original project
brief is explicit that the offline-first PoC must never have a *runtime*
dependency on AWS — S3/Ground Truth are dev-time convenience only (shared
storage, labeling), never part of the demo path. So the AWS gap is a
**data-sourcing problem**, not an architectural one. The code already
anticipates exactly this: `backend/models/detect.py` falls back to pretrained
`yolov8n.pt` with an honest `pretrained: true` flag on every detection when no
fine-tuned weights exist, and `backend/models/risk.py`'s `SEVERITY` dict
carries the comment "Adjust to your actual YOLOv8 class list once Day 6 fixes
the classes" — it was written expecting the class vocabulary to change.

Per your decision: broaden the dataset search to well-established general
metal/industrial surface-defect datasets (not aerospace-exclusive) if nothing
good and aerospace-specific turns up quickly — prioritizing a larger, cleaner,
better-documented dataset over narrative purity, with one honest sentence in
the deck explaining the substitution (the same move the brief's own cited
prior art — aircraft-blade-defect work — makes from general defect-detection
literature).

**Goal:** make real progress through Day 13 with zero AWS dependency, and
explicitly (not silently) defer the genuinely AWS-specific pieces to "once
AWS access resumes."

## Plan

### 1. Source a public defect-detection dataset (D5 substitute, no AWS)

Search Roboflow Universe and Kaggle. Selection order:

1. **Aerospace/aircraft surface-defect dataset** if a good one turns up
   quickly (corrosion/crack/dent on aircraft skin).
2. Otherwise, a well-established **general metal/industrial surface-defect
   dataset** — e.g. NEU-DET-style steel surface defects, Severstal steel
   defect detection, or a Roboflow crack/corrosion/dent detection project.
   Prefer one whose classes overlap `risk.py`'s `SEVERITY` vocabulary
   (`crack`, `corrosion`, `dent`, `scratch`, `pitting`, `exfoliation`,
   `deformation`, `discoloration`) where possible — it won't match
   perfectly, and that's fine (see below).
3. **Format:** prefer already-YOLO-labeled (avoids a conversion step).
   `backend/scripts/dataset_check.py` already classifies YOLO / COCO / VOC —
   if the best dataset isn't YOLO format, write a small one-off conversion
   script rather than passing on an otherwise-good dataset.
4. **Size:** given this machine's constraints (disk fluctuates 5-29GB free
   this session; only ~8GB RAM total, often under 1GB free) target a few
   hundred MB at most — a demo-quality fine-tune needs hundreds to low
   thousands of images, not a production-scale set.
5. **License:** must permit redistribution in this repo (CC BY / CC0 /
   similar) — record it, same as the FAA corpus's public-domain status was
   recorded.
6. **If nothing suitable turns up** after a genuine search effort: don't
   force a bad dataset. Ship the demo honestly on the pretrained YOLOv8n
   fallback (already working, already flagged `pretrained:true` end-to-end
   through the UI) and document the class-vocabulary gap as a deliberate,
   named limitation for the pitch deck's "what's out of scope and why" slide.

### 2. Where the dataset lives

No existing convention to violate — `README.md`'s folder tree
(`vision/dataset/`) doesn't match the actual repo layout (confirmed: no
top-level `nlp/`/`risk/`/`memory/`/`docs/` exist; that logic lives under
`backend/models/`). Propose, consistent with where `corpus_raw/` and
`history_cases.json` already live:

```
backend/data/vision_dataset/
├── images/{train,val}/
├── labels/{train,val}/
├── data.yaml
└── README.md        # source URL, license, class list, download date
```

- **If ≲150-200MB** (same order of magnitude as the 73MB FAA corpus we
  already committed): commit it directly, same precedent.
- **If larger:** keep local-only, gitignore it, and the `README.md` above
  documents exact re-download steps — same pattern already used for `*.pt`
  weights (gitignored, expected to be regenerated locally).

### 3. D6-01 — fine-tune YOLOv8

- Base model `yolov8n.pt` (smallest variant — matches the resource-conscious
  pattern already used for Ollama/phi3:mini on this machine).
- `device=cpu` explicitly (matches `detect.py`'s own `PRISM_YOLO_DEVICE=cpu`
  default and its stated reasoning: the LLM already uses most of the
  4GB VRAM).
- Modest epochs (start ~30-50, adjust live based on actual wall-clock speed
  and memory pressure on this machine — same watch-and-adapt approach used
  during corpus ingestion, which hit a real RAM-pressure failure once).
- Train against `backend/data/vision_dataset/data.yaml`.
- Output lands at `runs/detect/train/weights/best.pt` under `backend/` by
  default — **matches `detect.py`'s existing `PRISM_YOLO_WEIGHTS` default
  exactly, so zero code changes are needed** to wire it in.
- Extend `risk.py`'s `SEVERITY` dict with the dataset's real class names —
  a small, already-anticipated edit (the code comment invites exactly this).

### 4. D6-02 — verify detection

- Run `detect()` against held-out validation images.
- Confirm `pretrained: false` now appears with real defect labels.
- Record observations in `backend/logs/day6_detection.md`, matching the
  style of the existing `day2_benchmark.md`/`day3_retrieval.md`/
  `day4_examples.md`/`day9_api.md` logs.

### 5. D10 — full integration dry run (with a real image this time)

- Re-run the same Playwright browser-driven check already used this
  session, but now upload a real validation image — confirms the full
  detection→risk→diagnosis→case-memory chain with actual detections, not
  just the text-only path already validated.
- Re-try the D10-02 fragility cases (bad image, no visible defect, etc.) —
  `pipeline.py`'s failure isolation already handles these gracefully per
  Day 9's smoke test; just needs re-confirming with real image uploads.

### 6. D11 — reliability + metrics

- Add real YOLO metrics via `model.val(data=...)` (precision/recall/mAP) —
  the one metric category still missing; Days 2-4's LLM/retrieval timing
  numbers already exist.
- 10+ consecutive full-pipeline runs for stability, per the tracker.

### 7. D12/D13 — unchanged from the tracker

Buffer/bug-fix pass, the mandatory demo backup video, feature freeze, and the
handoff summary for the pitch deck — nothing here needs AWS.

### 8. Explicitly deferred to "once AWS access resumes"

- **D1-02:** bootstrap the real S3 bucket + tags via the already-written,
  already-tested `backend/scripts/s3_check.py --bootstrap` — zero new code
  needed, just real credentials + a bucket name.
- **Optional upgrade path:** a real SageMaker Ground Truth labeling pass, if
  the public-dataset fine-tune's accuracy proves insufficient for the demo
  and a properly hand-labeled aerospace-specific set becomes worth the
  investment. Not a blocker — the brief treats S3/Ground Truth as dev-time
  infrastructure, never a runtime dependency.
- Both get written into the tracker's Handoff Notes as a deliberate,
  documented deferral — same treatment D1-02 already got this session, not
  a silent gap.

## Risks / things to flag honestly in the deck

- **Class-vocabulary mismatch:** the sourced dataset's classes likely won't
  match `risk.py`'s `SEVERITY` dict perfectly. Already handled gracefully —
  unmatched classes default to `"Medium"` + `needs_human_review: true`
  rather than being silently treated as safe — but extend `SEVERITY` with
  the real classes once known.
- **License/attribution:** record whatever gets picked, same as the FAA
  corpus precedent.
- **Demo honesty:** if a jury member asks whether this is a "real" model —
  the pretrained-COCO fallback is flagged `pretrained:true` end-to-end
  through the UI; the fine-tuned model's dataset substitution (aerospace vs.
  general industrial) is a one-sentence, documented, defensible decision —
  same posture already taken with `risk.py`'s own SAE-J1979-vs-ATA/MSG-3
  honesty note.
- **Machine constraints:** 8GB RAM (often <1GB free during this session),
  disk fluctuating 5-29GB free, CPU-only training. Keep epochs/dataset size
  modest — this is a demo-quality fine-tune, not a production model, the
  same scoping already applied to Phi-3+Ollama on this machine.

## Verification

- `backend/scripts/dataset_check.py --local backend/data/vision_dataset`
  confirms YOLO-format labels are recognized correctly before training.
- After D6-01: `GET /health/pipeline` should show `detector.pretrained: false`
  once `PRISM_YOLO_WEIGHTS` resolves to the new `best.pt`.
- `model.val(data=...)` output (precision/recall/mAP) captured in
  `backend/logs/day6_detection.md`.
- Full browser click-through (Playwright, same approach as this session)
  with an uploaded validation image, screenshotted, checked for console
  errors — same bar already met for the text-only path.
- `scripts/smoke_diagnose.py --edge-cases --image <path>` re-run to confirm
  no 5xx with real detections flowing through risk scoring and the
  diagnosis prompt.
