"""D1-02/D5 — upload the shared data to the PRISM S3 bucket.

    python scripts/s3_sync.py --dry-run     # list what WOULD upload, no calls
    python scripts/s3_sync.py               # upload anything missing or changed
    python scripts/s3_sync.py --only weights
    python scripts/s3_sync.py --force       # re-upload even if unchanged

Reads AWS_* and PRISM_S3_BUCKET from backend/.env. Run scripts/s3_check.py
first — this script assumes the bucket exists and the prefixes are created.

WHAT THIS IS FOR, AND WHAT IT IS NOT: S3 here is dev-time storage so a teammate
on another machine gets the same corpus, dataset, cases and trained weights
without re-downloading from Kaggle and faa.gov. NOTHING on the diagnosis path
reads from S3. The offline-first claim depends on that staying true, so do not
import this from models/.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND / ".env")

BUCKET = os.getenv("PRISM_S3_BUCKET")
REGION = os.getenv("AWS_DEFAULT_REGION", "ap-south-1")

OK, BAD, SKIP, WARN = "[ OK ]", "[FAIL]", "[same]", "[WARN]"

# Anything larger than this is refused with an explanation rather than
# silently uploaded. The dataset is 184 MB of images; pushing it by accident
# would be slow and would spend monitored budget for no benefit, since
# fetch_dataset.py re-downloads it credential-free.
MAX_FILE_MB = 50


def _dataset_archive(root: Path) -> Path | None:
    """Zip the validation split into ONE object, built on demand.

    Uploaded as a single archive rather than file by file, deliberately. The
    valid split is 642 images plus 642 labels; as individual objects that is
    1,284 PUTs against a 2,000/month free tier, in one run, for data that
    scripts/fetch_dataset.py re-downloads credential-free. As one zip it is a
    single PUT, and a teammate pulls it in one go.

    Only the validation split, not all 8,582 files: this is the split the
    reported precision/recall/mAP were measured on, so pinning it is what makes
    those numbers reproducible. The train split is re-fetchable and carries no
    such claim.
    """
    src = root / "valid"
    if not src.is_dir():
        return None
    out = BACKEND / "runs" / "valid_split.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        return out
    import zipfile
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(src.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(src))
    return out


def build_plan(only: str | None) -> list[tuple[Path, str]]:
    """[(local_path, s3_key)] — every file this script would upload."""
    plan: list[tuple[Path, str]] = []

    if only in (None, "corpus"):
        for f in sorted((BACKEND / "data" / "corpus_raw").glob("*.pdf")):
            plan.append((f, f"corpus/{f.name}"))

    if only in (None, "cases"):
        f = BACKEND / "data" / "history_cases.json"
        if f.exists():
            plan.append((f, f"cases/{f.name}"))

    if only in (None, "weights"):
        # The whole reason weights/ exists. Named with the metrics in the key
        # so a future upload does not quietly overwrite the model the demo
        # was recorded against.
        f = BACKEND / "runs" / "detect" / "train" / "weights" / "best.pt"
        if f.exists():
            plan.append((f, "weights/yolov8n-aircraft-defect-map50-465.pt"))

    if only in (None, "dataset"):
        z = _dataset_archive(BACKEND / "data" / "vision_dataset")
        if z:
            plan.append((z, "images/labeled/valid_split.zip"))

    return plan


def _etag_matches(s3, key: str, path: Path) -> bool:
    """True when S3 already holds this exact content.

    S3's ETag is the MD5 of the body for a single-part upload, which every
    file here is (all are under the 50 MB cap). Multipart uploads produce a
    "<hash>-<parts>" ETag that is NOT a plain MD5 — those are treated as a
    mismatch rather than guessed at, so the worst case is a needless re-upload.
    """
    try:
        head = s3.head_object(Bucket=BUCKET, Key=key)
    except ClientError:
        return False
    etag = head["ETag"].strip('"')
    if "-" in etag:
        return False
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest() == etag


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan and exit without calling AWS")
    ap.add_argument("--force", action="store_true",
                    help="upload even when S3 already has identical content")
    ap.add_argument("--only", choices=["corpus", "cases", "weights", "dataset"],
                    help="upload just one group")
    args = ap.parse_args()

    if not BUCKET:
        print(f"{BAD} PRISM_S3_BUCKET is not set in backend/.env")
        return 1

    plan = build_plan(args.only)
    if not plan:
        print(f"{WARN} nothing to upload — check the paths in build_plan()")
        return 1

    total_mb = sum(p.stat().st_size for p, _ in plan) / 1e6
    print(f"bucket={BUCKET}  region={REGION}")
    print(f"plan: {len(plan)} file(s), {total_mb:.1f} MB\n")

    if args.dry_run:
        for path, key in plan:
            print(f"  {path.stat().st_size / 1e6:8.2f} MB  ->  s3://{BUCKET}/{key}")
        print("\ndry run — nothing uploaded. Drop --dry-run to do it for real.")
        return 0

    oversized = [(p, k) for p, k in plan if p.stat().st_size > MAX_FILE_MB * 1e6]
    if oversized:
        for p, _ in oversized:
            print(f"{BAD} {p.name} is {p.stat().st_size / 1e6:.0f} MB, over the "
                  f"{MAX_FILE_MB} MB cap")
        print("  Raise MAX_FILE_MB deliberately if this is really intended.")
        return 1

    s3 = boto3.client("s3", region_name=REGION)
    uploaded = skipped = failed = 0
    for path, key in plan:
        try:
            if not args.force and _etag_matches(s3, key, path):
                print(f"{SKIP} {key}")
                skipped += 1
                continue
            s3.upload_file(str(path), BUCKET, key)
            print(f"{OK} {key}  ({path.stat().st_size / 1e6:.2f} MB)")
            uploaded += 1
        except NoCredentialsError:
            print(f"{BAD} no AWS credentials — fill backend/.env "
                  f"(see docs/aws_setup.md)")
            return 1
        except ClientError as e:
            code = e.response["Error"]["Code"]
            print(f"{BAD} {key} — {code}")
            if code in ("AccessDenied", "InvalidAccessKeyId"):
                print("  The policy grants s3:PutObject on this bucket only. If "
                      "the bucket\n  was created with SSE-KMS, uploads ALSO need "
                      "kms:GenerateDataKey,\n  which the policy does not grant — "
                      "see docs/aws_setup.md.")
            failed += 1

    print(f"\nuploaded {uploaded}, unchanged {skipped}, failed {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
