# Day 11 — reliability pass + consolidated metrics (2026-09-28)

## Reliability: 10 consecutive `/diagnose` requests

Real HTTP requests against the live backend, varied corrosion/crack/dent
queries (text-only — see `docs/no_aws_plan.md` for why no image dataset is
in this pass yet). Raw per-request data in `day11_reliability_raw.json`.

- **10/10 succeeded, HTTP 200, zero failures, zero 5xx.**
- All 10 were `grounded: true` and cited a real manual source.
- Timing: **median 17.4s, min 5.8s, max 36.5s, avg 19.4s.**

The spread (5.8s-36.5s) is wider than the Day 2 benchmark's own range
(11.4s typical, 18.4s worst) because these are full end-to-end
`/diagnose` calls (retrieval + generation + risk + case memory), not
isolated `generate()` calls, and this 8GB-RAM machine has variable memory
pressure across a session (see the ingestion RAM-pressure incident in
`day3_retrieval.md`'s handoff notes). No request came close to timing out
or erroring — the spread is a demo-pacing consideration (worth a spinner
that can't look "stuck" up to ~40s), not a reliability concern.

## Consolidated metrics across all days

| Day | Metric | Result | Source |
|---|---|---:|---|
| 2 | LLM generation | median 16.8 tok/s, typical call 11.4s, cold start 51.3s | `day2_benchmark.md` |
| 3 | Retrieval latency | avg 27 ms across 10 queries, all confident (>0.47) | `day3_retrieval.md` |
| 4 | Grounded diagnosis | 6/7 clean, 1 correct refusal (coffee-machine query) | `day4_examples.md` |
| 9 | Full `/diagnose`, incl. edge cases | 6/6 edge cases handled, zero 5xx | `day9_api.md` |
| 10 | Full browser UI, 4 image/query combos | 4/4 stitched correctly, zero console/page errors | `day10_integration.md` |
| 11 | Reliability, 10x `/diagnose` | 10/10 succeeded, median 17.4s | this file |

## Deliberately NOT in this pass: YOLO detection metrics

`model.val()` precision/recall/mAP requires a labeled validation set, and
none exists yet (`vision/dataset/` is empty — confirmed via
`scripts/dataset_check.py`). This is the AWS-blocked D5 gap, tracked in
`docs/no_aws_plan.md`. The detector itself is verified *working* (Day 9/10
show `detector.available: true`, pretrained YOLOv8n runs and returns
`pretrained: true` results) — what's missing is an accuracy number against
real aircraft-defect images, not plumbing.

## What this means for the demo

Every number above measures the parts of PRISM that are demo-ready today:
local LLM speed, retrieval quality, grounded-vs-refused correctness, and
full-stack reliability under repeated real use. The one number still
missing (detection accuracy) is explicitly scoped and documented, not
silently absent.
