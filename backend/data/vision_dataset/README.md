# Vision dataset — aircraft surface defects

## Source

- **Dataset:** [`fatimaazfarziya/aircraft-defects`](https://www.kaggle.com/datasets/fatimaazfarziya/aircraft-defects) on Kaggle
- **Origin:** Roboflow Universe — [Innovation Hangar v2](https://universe.roboflow.com/innovation-hangar/innovation-hangar-v2)
- **Licence:** CC BY 4.0
- **Fetched:** 2026-09-30 via `scripts/fetch_dataset.py` (no credentials needed)

## Why this one

It is **aircraft-specific**. An earlier attempt used a general industrial
corrosion/rust dataset and was rejected — correctly. The entire claim of this
project is *aerospace* inspection, and a detector trained on bridges and
pipework does not support it. A judge asking "is this trained on aircraft?"
has to get a yes.

All five classes are real aviation surface-defect categories, and all five are
now in `backend/models/risk.py`'s `SEVERITY` table, so detections map to a
severity with no guesswork:

| Class | Severity | Reasoning |
|---|---|---|
| `crack` | Critical | Structural, propagates under cyclic load |
| `missing-head` | High | A fastener head gone means the joint is no longer carrying its design load |
| `dent` | Medium | Usually within allowable damage limits, but depth-dependent |
| `paint-off` | Medium | Not structural itself, but removes the coating that prevents corrosion — a precursor |
| `scratch` | Low | Cosmetic unless it penetrates primer |

## Contents

| Split | Images | Boxes | Background images |
|---|---:|---:|---:|
| train | 3,217 | 6,642 | 16 |
| valid | 642 | 1,265 | 5 |
| test | 429 | 861 | 3 |

Box counts by class (train / valid / test):

| Class | train | valid | test |
|---|---:|---:|---:|
| crack | 3,202 | 607 | 386 |
| dent | 2,859 | 554 | 413 |
| missing-head | 284 | 54 | 32 |
| paint-off | 237 | 34 | 23 |
| scratch | 60 | 16 | 7 |

**The class imbalance is severe and worth stating honestly:** `crack` and
`dent` together are ~91% of all boxes, while `scratch` has just 60 training
examples. Expect good crack/dent detection and weak scratch detection. Do not
present per-class numbers for the rare classes as if they were reliable — the
`test` split has only 7 scratch boxes, which is far too few to measure
anything.

The `test` split is held back from training entirely and is the honest
evaluation set.

## Not in git

The images and labels are gitignored — 183 MB, and re-fetchable in one
command with no credentials:

```bash
python scripts/fetch_dataset.py
```
