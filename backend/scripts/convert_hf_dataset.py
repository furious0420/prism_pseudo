"""D5 substitute — convert the HF corrosion dataset to YOLO format.

    python scripts/convert_hf_dataset.py

Source: https://huggingface.co/datasets/Francesco/corrosion-bi3q3 (CC licence,
object-detection, Roboflow-derived). Its classes are `corrosion` and `crack`,
which are already in models/risk.py's SEVERITY table.

Reads the parquet splits row-group by row-group rather than loading a split
into memory: this machine has 8GB total and has already failed once on memory
pressure during corpus ingestion, so nothing here holds more than one batch.

Writes the layout ultralytics expects:
    data/vision_dataset/images/{train,val}/*.jpg
    data/vision_dataset/labels/{train,val}/*.txt     class cx cy w h (normalised)
    data/vision_dataset/data.yaml
"""
import io
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1] / "data" / "vision_dataset"
RAW = ROOT / "_raw"
BATCH = 8

# The HF split names map to what ultralytics calls train/val. `test` is held
# back entirely — it is the honest evaluation set, never trained on.
SPLITS = {"train": "train", "validation": "val"}


def main() -> int:
    if not RAW.is_dir():
        print(f"no parquet files at {RAW}")
        return 1

    names = None
    counts = {}

    for src_split, dst_split in SPLITS.items():
        pf = pq.ParquetFile(RAW / f"{src_split}.parquet")

        # Class names live in the parquet schema metadata as a HF feature spec.
        if names is None:
            meta = pf.schema_arrow.metadata or {}
            raw = meta.get(b"huggingface")
            if raw:
                feat = json.loads(raw.decode())["info"]["features"]
                names = feat["objects"]["feature"]["category"]["names"]

        img_dir = ROOT / "images" / dst_split
        lbl_dir = ROOT / "labels" / dst_split
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        n = 0
        for batch in pf.iter_batches(batch_size=BATCH):
            rows = batch.to_pylist()
            for row in rows:
                img = row["image"]
                data = img["bytes"] if isinstance(img, dict) else img
                if not data:
                    continue
                stem = f"{dst_split}_{n:05d}"
                (img_dir / f"{stem}.jpg").write_bytes(data)

                w = float(row.get("width") or 0)
                h = float(row.get("height") or 0)
                lines = []
                for obj in (row.get("objects") or {}).get("bbox", []) if isinstance(row.get("objects"), dict) else []:
                    pass  # handled below
                objs = row.get("objects") or {}
                bboxes = objs.get("bbox") or []
                cats = objs.get("category") or []
                for bbox, cat in zip(bboxes, cats):
                    # HF/COCO gives [x, y, w, h] in absolute pixels; YOLO wants
                    # normalised centre-x, centre-y, w, h.
                    if not w or not h:
                        continue
                    x, y, bw, bh = [float(v) for v in bbox]
                    cx, cy = (x + bw / 2) / w, (y + bh / 2) / h
                    nw, nh = bw / w, bh / h
                    if not (0 <= cx <= 1 and 0 <= cy <= 1 and nw > 0 and nh > 0):
                        continue
                    lines.append(f"{int(cat)} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")
                (lbl_dir / f"{stem}.txt").write_text("\n".join(lines), encoding="utf-8")
                n += 1
        counts[dst_split] = n
        print(f"  {dst_split}: {n} images")

    if not names:
        print("could not read class names from parquet metadata")
        return 1

    yaml = ROOT / "data.yaml"
    yaml.write_text(
        f"path: {ROOT.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n\n"
        f"nc: {len(names)}\n"
        f"names: {json.dumps(names)}\n",
        encoding="utf-8",
    )
    print(f"\nclasses: {names}")
    print(f"wrote {yaml}")
    print(f"totals: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
