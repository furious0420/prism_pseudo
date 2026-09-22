"""D1-02 — verify (and optionally bootstrap) the PRISM S3 bucket.

    python scripts/s3_check.py              # read/write verification only
    python scripts/s3_check.py --bootstrap  # also create prefixes + apply tags

Reads AWS_* and PRISM_S3_BUCKET from backend/.env.
"""
import argparse
import os
import sys

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv

load_dotenv()

BUCKET = os.getenv("PRISM_S3_BUCKET")
REGION = os.getenv("AWS_DEFAULT_REGION", "ap-south-1")
PREFIXES = ["corpus/", "images/raw/", "images/labeled/", "cases/"]
REQUIRED_TAGS = {"Project Name": "PRISM"}  # "Name" = team leader, set per SOP

OK, BAD, WARN = "[ OK ]", "[FAIL]", "[WARN]"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", action="store_true",
                    help="create the four prefixes and apply project tags")
    args = ap.parse_args()

    if not BUCKET:
        print(f"{BAD} PRISM_S3_BUCKET is not set in backend/.env")
        return 1

    print(f"bucket={BUCKET}  region={REGION}\n")
    s3 = boto3.client("s3", region_name=REGION)
    failures = 0

    # --- bucket reachable, and in the right region -----------------------
    try:
        loc = s3.get_bucket_location(Bucket=BUCKET)["LocationConstraint"] or "us-east-1"
        if loc == REGION:
            print(f"{OK} bucket exists in {loc}")
        else:
            print(f"{BAD} bucket is in {loc}, expected {REGION} (Mumbai)")
            failures += 1
    except NoCredentialsError:
        print(f"{BAD} no AWS credentials found — check backend/.env")
        return 1
    except ClientError as e:
        code = e.response["Error"]["Code"]
        hint = {"404": "bucket does not exist — create it in the console first",
                "403": "credentials lack s3:GetBucketLocation on this bucket"}.get(code, "")
        print(f"{BAD} cannot reach bucket ({code}) {hint}")
        return 1

    # --- read -------------------------------------------------------------
    try:
        resp = s3.list_objects_v2(Bucket=BUCKET, MaxKeys=5)
        print(f"{OK} read  — list_objects_v2 returned {resp.get('KeyCount', 0)} key(s)")
    except ClientError as e:
        print(f"{BAD} read  — {e.response['Error']['Code']} (need s3:ListBucket)")
        failures += 1

    # --- write + delete ---------------------------------------------------
    probe = "cases/.prism_write_probe"
    try:
        s3.put_object(Bucket=BUCKET, Key=probe, Body=b"prism day1 probe")
        print(f"{OK} write — put_object succeeded")
        s3.delete_object(Bucket=BUCKET, Key=probe)
    except ClientError as e:
        print(f"{BAD} write — {e.response['Error']['Code']} (need s3:PutObject)")
        failures += 1

    # --- prefixes ---------------------------------------------------------
    existing = {
        p["Prefix"]
        for p in s3.list_objects_v2(Bucket=BUCKET, Delimiter="/").get("CommonPrefixes", [])
    }
    for pfx in PREFIXES:
        top = pfx.split("/")[0] + "/"
        if top in existing:
            print(f"{OK} prefix {pfx}")
        elif args.bootstrap:
            s3.put_object(Bucket=BUCKET, Key=pfx)
            print(f"{OK} prefix {pfx} (created)")
        else:
            print(f"{WARN} prefix {pfx} missing — rerun with --bootstrap")

    # --- tags -------------------------------------------------------------
    try:
        tags = {t["Key"]: t["Value"]
                for t in s3.get_bucket_tagging(Bucket=BUCKET)["TagSet"]}
    except ClientError:
        tags = {}
    for k, v in REQUIRED_TAGS.items():
        if tags.get(k) == v:
            print(f"{OK} tag {k}={v}")
        else:
            print(f"{WARN} tag {k} missing/wrong (found: {tags.get(k)!r}) — AWS tagging SOP")
    if "Name" not in tags:
        print(f"{WARN} tag 'Name' (team leader) not set — AWS tagging SOP")

    print("\n" + ("PASS — Day 1 S3 access confirmed." if not failures
                  else f"FAIL — {failures} blocking problem(s)."))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
