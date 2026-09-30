# PRISM — build handoff for the pitch deck

One page for whoever builds the deck. Written 2026-09-30, against commit `8fb65ab`.
Everything below is measured on the actual dev/demo laptop, not estimated.

---

## What PRISM is

A technician describes a symptom — optionally with a photo and live telemetry —
and PRISM returns a diagnosis **grounded in real FAA maintenance manuals**, with
the passages it used, a risk score, and similar past repairs.

Every part of the diagnosis path runs on the machine. No cloud calls, no API keys,
no network dependency at inference time.

## Architecture (one line per stage)

```
photo ─→ YOLOv8 detection ─┐
                            ├─→ risk scoring (0-100)
telemetry ─────────────────┘
                                                    ┌─→ diagnosis + citations
symptom text ─→ MiniLM embed ─→ ChromaDB retrieval ─┤
                                                    └─→ Phi-3 Mini (local, Ollama)
symptom text ─→ case memory (MiniLM similarity) ───→ similar past repairs
```

Orchestrated by `backend/models/pipeline.py`. **Every stage is failure-isolated** —
a dead model or a missing file degrades one section and leaves the rest, so the
response is never a 500. That was tested deliberately, not assumed.

## Evidence-based results

| Metric | Result | Source |
|---|---|---|
| Local LLM generation | median **16.8 tok/s**, typical call 11.4s, cold start 51s | `logs/day2_benchmark.md` |
| Retrieval latency | **20 ms** average across 10 queries | `logs/day3_retrieval.md` |
| Corpus indexed | **4,769 passages** from 3 FAA advisory circulars (1,350 pages), column-aware and stripped of running headers, contents lines and captions | `logs/day3_extraction_fix.md` |
| Grounding | **6/7** queries grounded + correctly cited; 7th correctly **refused**. The 1 flag is a reproducible phi3:mini filename slip the citation checker catches and the UI warns on | `logs/day4_examples.md` |
| Full request reliability | **10/10** succeeded, zero failures, median 17.4s | `logs/day11_metrics.md` |
| Detection (fine-tuned YOLOv8n) | precision **0.646**, recall **0.472**, mAP50 **0.465** — demo grade; misses roughly half of what is present | `logs/day11_metrics.md` |
| Edge-case robustness | **6/6** handled, **zero 5xx** (empty, whitespace, nonsense, 400-word, out-of-corpus) | `logs/day9_api.md` |
| Browser integration | **4/4** image+query combinations stitched correctly, zero console errors | `logs/day10_integration.md` |
| Time to first visible stage | **~0.9s** (streamed), vs 15-25s blank before | verified in-browser |

## The three claims worth leading with

1. **It refuses rather than guesses.** Asked something the manuals don't cover, it
   replies "The provided manual extracts do not cover this." Verified against a
   deliberate out-of-corpus query — and it still refused even when retrieval
   returned a *moderately* confident but irrelevant passage.
2. **Every claim is traceable.** The UI shows the actual retrieved passage text,
   not just a page number. A citation naming a document that was never retrieved
   is detected mechanically (`cited_ok`), so fabrication is measurable rather than
   something a reader has to spot.
3. **It genuinely runs offline.** Phi-3 Mini via Ollama, ChromaDB on disk, YOLOv8
   local. Nothing in the diagnosis path reaches the network.

## Deliberately out of scope — and why

State these plainly if asked; each is a decision, not an oversight.

| Not built | Why |
|---|---|
| **Production-accuracy vision model** | Closed as a gap, but only to demo grade. YOLOv8n is now fine-tuned on an aircraft surface-defect set (CC BY 4.0, 5 classes) — precision 0.646, recall 0.472, mAP50 0.465. Recall near 0.5 means it misses roughly half of what is present. It assists an inspection; it does not replace one. SageMaker Ground Truth was dropped deliberately: a labelling job would spend monitored budget producing data we already have. |
| **IoT Greengrass cloud sync** | Explicitly a later-phase item. The offline-first claim would be *weakened*, not helped, by a runtime cloud dependency. An S3 bucket exists for dev-time data sharing only (`docs/aws_setup.md`); nothing on the diagnosis path touches it. |
| **VLM (LLaVA / Phi-3-Vision)** | De-risked out of this stage — memory pressure on a 4GB GPU plus fine-tuning risk. |
| **HIL testbench validation** | Later phase. |

## Caveats a technical judge may probe

- **Risk thresholds are illustrative demo values**, not certified airworthiness
  limits. Real limits come from the type certificate / CMM for a specific
  component. This is stated in the code and shown in the UI.
- **"SAE J1979" is an automotive OBD-II standard.** Aviation uses ATA chapters and
  MSG-3. Either justify the reference in one line or swap it in the deck — this is
  the single most likely question from anyone with an aviation background.
- **Retrieved passages show PDF extraction artifacts** (hyphenation, table-of-
  contents dot leaders). That is the raw text the model actually read, shown as-is
  rather than cleaned up for appearances.

## Run a warm-up query before the demo starts

Not optional. The first diagnosis after starting the backend takes **~52s**
because the model loads on demand; every subsequent one takes **~14s**. This was
measured twice in a row during final verification — 52.4s then 14.1s, same query.
Send one throwaway query while setting up so the jury's first question hits a warm
model.

## Demo assets

- Live app: `backend/` then `frontend/` (see README) — http://localhost:5173
- Sample images for the detection path: `sample_images/` — two held-out
  validation images (CC BY 4.0) the fine-tuned detector fires on, with the
  detections and risk arbitration written up in its README
- Evidence logs: `backend/logs/*.md` — every number in the table above
- Original pitch mockup: `docs/prism_demo_v4.html`

## Still to do before freeze

### Mandatory

| Item | Why it cannot slip |
|---|---|
| **Record the backup demo video (D12-02)** | The fallback if anything fails live. A 3.9 GB model, a 50 MB index and a CPU detector are three things that can misbehave on someone else's laptop. |

### Frontend — features and design

The UI works and covers all four tabs, but several things the pipeline already
computes are never shown. These are ordered by demo impact per hour of work.

| # | Item | Notes |
|---|---|---|
| 1 | **Bounding-box overlay on the uploaded image** | **Highest value in the list.** `detect()` already returns `box: [x1, y1, x2, y2]` for every detection and the API already sends it — `App.jsx` renders a plain `<img>` and throws the coordinates away. Draw them on a canvas or as absolutely-positioned divs, labelled with class + confidence, coloured by severity. Nothing new is needed server-side. The original mockup had an `overlay` element for exactly this. |
| 2 | **Severity colour on each box and detection row** | Reuse the existing `.risk-*` tokens so a Critical crack reads red and a Low scratch reads grey. Makes `worst_risk()` legible at a glance instead of only in the Risk panel. |
| 3 | **Export a diagnosis as a report** | Print stylesheet or PDF. An MRO finding that cannot leave the screen is not a paper trail, and it is the question an aerospace judge is most likely to ask. |
| 4 | **Tablet layout pass** | The two-column dashboard assumes a laptop. A technician at an airframe is holding a tablet. Worth one responsive breakpoint. |
| 5 | **Per-detection crop thumbnails** | Crop each box from the upload and show it beside the row, so a 0.52 crack can be eyeballed rather than trusted. |
| 6 | **Confidence-threshold slider** | Let the user raise the bar past 0.5 and watch marginal detections drop out. Honest about a recall-0.472 model, and demonstrates the trade-off rather than hiding it. |
| 7 | **Accessibility and keyboard pass** | Focus order, labels on the telemetry inputs, contrast check on the navy/teal theme. |

### Backend and evidence

| Item | Notes |
|---|---|
| **D6-02 — detection verification log** | Every other tracker day has a `logs/dayN_*.md`; Day 6 does not. Run `model.val()` formally and write `logs/day6_detection.md` with per-class precision/recall, not just the aggregate. |
| **Fix the leading raw-text fragment** | A diagnosis occasionally opens with a stray fragment. Cosmetic, but it is the first thing a viewer reads. |
| **The phi3 citation slip** | Query 1 reproducibly mangles `AC_43.13-1B` into `AC_430.13-1B`. The checker catches it and the UI warns, so this is presentation, not correctness. Options: try a shorter source label, or leave it and let the guard-rail be the story. Do NOT loosen `_check_citations` to make the number read 7/7. |
| **D13 — feature freeze** | Then handoff notes and the pitch-deck summary. |

### AWS — blocked, not forgotten

| Item | State |
|---|---|
| Bucket + data | **Done, by console upload.** See `docs/aws_setup.md`. |
| `s3_check.py` / `s3_sync.py` verification | **Blocked.** This account issues no programmatic credentials — every relevant `iam:*` action is denied. Both scripts are written, reviewed and correct; they run the moment an admin grants a key. |
| `images/raw/` | Left empty deliberately — nothing unlabelled to put there yet. |

Known cosmetic issues, neither affecting correctness, are documented in
`logs/day10_integration.md`. The table-of-contents dot-leader chunks noted
there are now largely gone: the corpus rework dropped 34 contents pages and
595 furniture chunks, leaving dot-leaders in 0.6% of the index.
