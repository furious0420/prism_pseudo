# Sample images for demoing the detection path

## `aircraft_nasa_sca.jpg`

- **Source:** Wikimedia Commons — "NASA's Shuttle Carrier Aircraft 905 (front) and 911 (rear)"
- **License:** Public domain (NASA work), no attribution required
- **Downloaded:** 2026-09-28

**Why this image:** the detector currently runs **pretrained YOLOv8n (COCO
classes)**, not a defect-trained model — see `docs/no_aws_plan.md` for why
(the Day 5/6 dataset gap). COCO has no `corrosion`/`crack`/`dent` classes, so
a photo of real aircraft corrosion detects **nothing**.

COCO *does* have an `airplane` class, so this image makes the detection path
visibly fire. Verified output:

```
airplane  0.866  pretrained=True
airplane  0.827  pretrained=True
overall risk: Medium
rationale: airplane classified Medium; 'airplane' is not in the severity
table; defaulted to Medium rather than assuming it is minor; flagged for
human review
```

That is the intended honest behaviour, and it exercises three things nothing
else in the demo does:

1. The **Detected in image** card populating, with its `pretrained` warning.
2. The **Risk** card populating at all — every text-only run skips risk
   because there are no detections to score.
3. `risk.py`'s unknown-class path: an unrecognised label defaults to
   `Medium` + `needs_human_review`, never silently "safe".

**Do not present this as defect detection.** It detects aircraft, not faults.
Once a real defect dataset is sourced and YOLOv8 is fine-tuned (D5/D6), swap
in genuine defect photos and this file stops being needed.
