"""D5 — fetch the aircraft surface-defect dataset.

    python scripts/fetch_dataset.py

Downloads and extracts into data/vision_dataset/. No credentials needed —
Kaggle's dataset download endpoint serves this one unauthenticated.

WHY THIS DATASET: it is aircraft-specific. Its classes are crack, dent,
missing-head, paint-off and scratch — real aviation surface-defect
vocabulary, all five now present in models/risk.py's SEVERITY table. An
earlier attempt used a general industrial corrosion set, which was rejected:
the whole claim of this project is aerospace inspection, and a model trained
on bridges and pipes does not support it.

Source : https://www.kaggle.com/datasets/fatimaazfarziya/aircraft-defects
Origin : Roboflow Universe "Innovation Hangar v2"
Licence: CC BY 4.0
"""
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = ("https://www.kaggle.com/api/v1/datasets/download/"
       "fatimaazfarziya/aircraft-defects")
DEST = Path(__file__).resolve().parents[1] / "data" / "vision_dataset"

DATA_YAML = """# Aircraft surface defect detection — Innovation Hangar v2 (CC BY 4.0)
# Absolute path so training works regardless of the working directory.
path: {path}
train: train/images
val: valid/images
test: test/images

nc: 5
names: ['crack', 'dent', 'missing-head', 'paint-off', 'scratch']
"""


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    if (DEST / "train" / "images").is_dir():
        n = len(list((DEST / "train" / "images").glob("*")))
        print(f"already present: {n} training images at {DEST}")
        return 0

    print(f"downloading (~163 MB) from Kaggle ...")
    req = urllib.request.Request(URL, headers={"User-Agent": "PRISM/1.0"})
    with urllib.request.urlopen(req, timeout=600) as r:
        blob = r.read()
    print(f"  {len(blob) / 1024 / 1024:.0f} MB")

    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        z.extractall(DEST)

    # Rewrite data.yaml: the Roboflow export ships relative paths that only
    # resolve from one specific working directory.
    (DEST / "data.yaml").write_text(
        DATA_YAML.format(path=DEST.as_posix()), encoding="utf-8")

    for split in ("train", "valid", "test"):
        imgs = len(list((DEST / split / "images").glob("*")))
        lbls = len(list((DEST / split / "labels").glob("*")))
        print(f"  {split:6} {imgs:5} images  {lbls:5} labels")
    print(f"\nready: {DEST / 'data.yaml'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
