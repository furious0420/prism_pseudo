"""D1-03 — does a labeled defect-image dataset already exist, and in what format?

    python scripts/dataset_check.py                  # check S3 only
    python scripts/dataset_check.py --local ./data   # also scan a local folder

Answer this TODAY. If the answer is "no", Day 5 has to run a SageMaker Ground
Truth labeling job with a private workforce, which costs human wall-clock time
that cannot be compressed. Starting it early is the whole point of this check.
"""
import argparse
import json
import os
import re
from collections import Counter
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv

load_dotenv()

IMG = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
# YOLO line: "<class:int> <4 floats in 0..1>"
YOLO_LINE = re.compile(r"^\d+(\s+(0(\.\d+)?|1(\.0+)?)){4}\s*$")


def classify_label_file(name: str, text: str) -> str:
    """Return YOLO / COCO / VOC / UNKNOWN for one label file's contents."""
    ext = Path(name).suffix.lower()
    if ext == ".txt":
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if lines and all(YOLO_LINE.match(ln.strip()) for ln in lines):
            return "YOLO"
        return "UNKNOWN(.txt)"
    if ext == ".json":
        try:
            obj = json.loads(text)
        except Exception:
            return "UNKNOWN(.json)"
        if isinstance(obj, dict) and {"images", "annotations", "categories"} <= obj.keys():
            return "COCO"
        if isinstance(obj, dict) and "source-ref" in obj:
            return "GROUND_TRUTH_MANIFEST"
        return "UNKNOWN(.json)"
    if ext in {".manifest", ".jsonl"}:
        return "GROUND_TRUTH_MANIFEST"
    if ext == ".xml" and "<annotation>" in text:
        return "PASCAL_VOC"
    return "UNKNOWN"


def summarise(images: int, labels: Counter, where: str) -> None:
    print(f"\n--- {where} ---")
    print(f"  images: {images}")
    if not labels:
        print("  labels: NONE FOUND")
        return
    print(f"  labels: {sum(labels.values())}")
    for fmt, n in labels.most_common():
        print(f"    {fmt}: {n}")


def scan_s3() -> tuple[int, Counter]:
    bucket = os.getenv("PRISM_S3_BUCKET")
    region = os.getenv("AWS_DEFAULT_REGION", "ap-south-1")
    if not bucket:
        print("[skip] PRISM_S3_BUCKET not set — S3 scan skipped")
        return 0, Counter()
    s3 = boto3.client("s3", region_name=region)
    images, labels = 0, Counter()
    try:
        pages = s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="images/")
        sampled = 0
        for page in pages:
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                ext = Path(key).suffix.lower()
                if ext in IMG:
                    images += 1
                elif ext in {".txt", ".json", ".xml", ".manifest", ".jsonl"}:
                    # Only fetch a sample — enough to identify the format.
                    if sampled < 8 and obj["Size"] < 2_000_000:
                        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
                        labels[classify_label_file(key, body.decode("utf-8", "ignore"))] += 1
                        sampled += 1
                    else:
                        labels["(not sampled)"] += 1
    except NoCredentialsError:
        print("[skip] no AWS credentials — S3 scan skipped")
    except ClientError as e:
        print(f"[skip] S3 error: {e.response['Error']['Code']}")
    return images, labels


def scan_local(root: Path) -> tuple[int, Counter]:
    images, labels = 0, Counter()
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in IMG:
            images += 1
        elif ext in {".txt", ".json", ".xml", ".manifest", ".jsonl"}:
            try:
                labels[classify_label_file(p.name, p.read_text("utf-8", "ignore")[:200_000])] += 1
            except Exception:
                labels["UNREADABLE"] += 1
    return images, labels


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", type=Path, help="local folder to scan as well")
    args = ap.parse_args()

    s3_img, s3_lbl = scan_s3()
    summarise(s3_img, s3_lbl, f"s3://{os.getenv('PRISM_S3_BUCKET')}/images/")

    loc_img, loc_lbl = 0, Counter()
    if args.local:
        loc_img, loc_lbl = scan_local(args.local)
        summarise(loc_img, loc_lbl, str(args.local.resolve()))

    total_img = s3_img + loc_img
    all_lbl = s3_lbl + loc_lbl
    usable = {k: v for k, v in all_lbl.items() if not k.startswith("UNKNOWN") and k != "(not sampled)"}

    print("\n=== VERDICT (paste into Day 1 Handoff Notes) ===")
    if not total_img:
        print("NO IMAGES FOUND. Day 5 = full Ground Truth job, and you still need raw")
        print("images first. This is the biggest schedule risk in the tracker — raise it now.")
    elif not usable:
        print(f"{total_img} image(s), NO USABLE LABELS.")
        print("=> Day 5 MUST run the SageMaker Ground Truth bounding-box job (D5-02).")
        print("=> Private workforce = your teammates labeling by hand. Start it EARLY.")
    else:
        fmt = max(usable, key=usable.get)
        print(f"{total_img} image(s), {sum(usable.values())} label file(s), format: {fmt}")
        if fmt == "YOLO":
            print("=> Labels are already YOLO format. Day 5 is a no-op; go straight to Day 6 (D5-03).")
        else:
            print(f"=> Labels are {fmt}, NOT YOLO. Day 5 needs a conversion script, not a")
            print("   labeling job. Much cheaper — budget a couple of hours, not days.")


if __name__ == "__main__":
    main()
