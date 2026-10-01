# Sample images for demoing the detection path

Two held-out validation images from the training dataset, committed so the
detection path can be exercised without unpacking the full (gitignored)
dataset.

- **Source:** [Innovation Hangar v2](https://universe.roboflow.com/innovation-hangar/innovation-hangar-v2)
  on Roboflow Universe, the same set the detector was fine-tuned on.
- **Licence:** CC BY 4.0 — redistribution permitted with attribution.
- **Split:** `valid/`, held out from training. The model did not see these
  during the fine-tune, so the detections below are genuine inference, not
  recall of a memorised example.

## `defect_crack_rotor_seating.jpg`

A crack between rotor seating areas. Single clean detection:

```
crack  0.91  pretrained=False
-> governing risk: Critical — crack classified Critical; flagged for human review
```

The simplest end-to-end demo: one real aerospace defect, correctly classed,
escalated to Critical.

## `defect_dent_and_cracks.jpg`

Four detections, and the more interesting of the two:

```
dent   0.98  pretrained=False
crack  0.52  pretrained=False
crack  0.48  pretrained=False
crack  0.40  pretrained=False
-> governing risk: Critical — crack classified Critical; flagged for human review
```

Note what happens here. `dent` is by far the **most confident** detection at
0.98, but the governing risk is **Critical**, driven by a `crack` at half that
confidence. That is `worst_risk()` doing its job: severity governs, not
confidence, because averaging would let three scratches hide a crack. This one
image demonstrates the whole risk-arbitration rule.

## Honest framing for the demo

The detector is demo-grade: precision 0.646, recall 0.472, mAP50 0.465 on the
validation split. Recall near 0.5 means it misses roughly half of what is
present. Present it as something that assists an inspection, never as something
that replaces one. Both images carry `pretrained: false`, so these are the
fine-tuned aircraft classes — if the weights are ever missing, the pipeline
falls back to pretrained COCO and flags `pretrained: true` rather than
pretending.
