# Day 10 — full integration dry run (2026-09-28)

Driven through the real browser UI (Playwright, headless Chromium) against
the live Flask + Vite dev servers — not just the API, the actual rendered
page a user would click through. 4 different image/query combinations, per
D10-01. Test image: a stock Windows wallpaper photo (no aircraft defects in
it, used only to exercise the real detection code path — the pretrained
YOLOv8n fallback is expected to find nothing recognizable in it, and that is
exactly what happened; a real defect dataset is still pending, see
`docs/no_aws_plan.md`).

## Scenarios run

| # | query | image | result | total ms |
|---|---|---|---|---:|
| 1 | "Pitting corrosion on the landing gear strut, roughly 2mm deep." | yes | grounded, cited AC_43.13-1B p.428, similar case HC-001 (87%) | 23390 |
| 2 | *(empty)* | yes | 0 detections in image + no query -> correctly declined with "nothing to diagnose", no error | 110 |
| 3 | "Hairline crack found on the wing spar cap during scheduled inspection." | no | grounded, cited AC_43.13-1B p.46, similar case HC-002 (97%) | 8238 |
| 4 | "Dent in the fuselage skin, about 40mm across and shallow." | yes | grounded, cited 2 sources, similar cases HC-003 (82%)/HC-016 (63%) | 11542 |

**All 4 stitched correctly end-to-end** (detection -> risk -> diagnosis ->
case memory, in the tracker's order). Zero error banners, zero browser
console errors, zero page exceptions across all 4 runs. Scenario 2 is the
interesting one: an image with no recognizable COCO objects and no query text
degrades to an honest "No defects were detected in the image and no symptom
description was given... Add a description of what you are seeing" instead
of a blank result or a crash — this is `pipeline.py`'s `no_input_reason`
logic working exactly as designed, discovered here for real rather than only
in the Day 9 smoke test's synthetic edge cases.

## Two minor content-quality artifacts found (not blocking, note for D12)

1. **Scenario 1's diagnosis opens with a stray fragment**: "PROBLEMS. During
   inspection and before date." before the actual likely-defect/action text.
   This is the LLM echoing a rough edge of the retrieved chunk rather than a
   clean summary — the citation and the actual recommendation are still
   correct, just a bit untidy for a live demo. Worth a prompt tweak later
   (e.g. explicitly instruct "do not quote raw manual headers/fragments
   verbatim before your own sentence").
2. **Scenario 4 retrieved a chunk that's mostly a broken table-of-contents
   line**: "dures ------------------------.------------------ 83" — an
   artifact of `pdfplumber` extracting a ToC dot-leader line as if it were
   body text during Day 3 ingestion. The diagnosis still reads fine around
   it, but a re-ingest with a filter for low-information/dot-leader lines
   (e.g. skip chunks that are mostly `-`/`.` characters) would clean this up.

Neither affects correctness (citations stay accurate, refusal/grounding
logic is unaffected) — both are demo-polish items, not bugs.

## Screenshots

`d10_scenario{1..4}_*.png` in the session scratchpad, full-page captures of
each result.
