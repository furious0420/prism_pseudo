# Vision dataset — corrosion & crack detection

The D5 substitute. The tracker's own path (SageMaker Ground Truth labelling)
needs AWS access we don't have, so this is a public pre-labelled dataset
instead — see `docs/no_aws_plan.md` for the reasoning.

## Source

- **Dataset:** [`Francesco/corrosion-bi3q3`](https://huggingface.co/datasets/Francesco/corrosion-bi3q3) on Hugging Face
- **Licence:** CC (permits use and redistribution)
- **Origin:** Roboflow Universe, mirrored to HF as an object-detection set
- **Downloaded:** 2026-09-30

## Why this one

Its classes are **`corrosion`** and **`crack`** — both already present in
`backend/models/risk.py`'s `SEVERITY` table (corrosion → High, crack →
Critical), so detections flow into risk scoring with no vocabulary remapping.
That was the main selection criterion; most public defect datasets are steel or
textured-surface sets whose class names mean nothing to this pipeline.

## Contents

| Split | Images | Boxes |
|---|---:|---:|
| train | 840 | 3,112 |
| val | 105 | 422 |

Class indices as they appear in `data.yaml`:

| Index | Name | In `SEVERITY`? | Boxes (train/val) |
|---|---|---|---|
| 0 | `corrosion-0` | no | 0 / 0 — a Roboflow super-class artifact, unused |
| 1 | `Slippage` | no → defaults to Medium + human review | 548 / 0 |
| 2 | `corrosion` | **yes → High** | 1,176 / 164 |
| 3 | `crack` | **yes → Critical** | 1,388 / 258 |

42 images (37 train, 5 val) have empty label files. That is valid YOLO — they
are background images with no annotated defect, and they help suppress false
positives. `scripts/dataset_check.py` reports them as `UNKNOWN(.txt)` because it
classifies by content and an empty file has none; that is a quirk of the checker,
not a problem with the data.

The HF `test` split (304 images) was deliberately **not** converted. It is held
back as a genuinely unseen evaluation set.

## Regenerating

The parquet sources in `_raw/` are gitignored. To rebuild from scratch:

```bash
# re-download the three parquet files into backend/data/vision_dataset/_raw/
python scripts/convert_hf_dataset.py
```

## Caveats to state honestly

- This is **general industrial corrosion/crack imagery, not aircraft-specific**.
  A deliberate call (see `docs/no_aws_plan.md`): a larger, cleaner, properly
  licensed dataset beats a thin aerospace-only one, and the prior art the project
  cites makes the same substitution. Worth one sentence in the deck rather than
  leaving a judge to discover it.
- `Slippage` is not an aviation defect category. It is not in `SEVERITY`, so it
  scores as Medium and is flagged for human review rather than being silently
  treated as safe.
