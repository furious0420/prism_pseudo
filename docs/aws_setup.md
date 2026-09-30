# AWS setup for PRISM

Everything PRISM needs from AWS is **one S3 bucket**. Nothing else — no EC2, no
SageMaker, no Greengrass. This is deliberate: the diagnosis path must run with
no network at all, so AWS is only ever dev-time storage for things the team
shares.

> **Account rules for this hackathon** (usage is monitored, and over-use counts
> against the project):
> - Region must be **Mumbai `ap-south-1`**. The console often defaults elsewhere
>   — change it before creating anything.
> - Every resource needs two tags: `Name` = team leader's name, and
>   `Project Name` = `PRISM`.
> - Never put keys in code. They go in `backend/.env`, which is gitignored.

---

## Step 1 — Create the bucket (console)

1. Sign in, then **switch the region to Asia Pacific (Mumbai) ap-south-1** using
   the selector at the top right. Do this first; a bucket cannot be moved later.
2. **S3 → Create bucket.**
3. **Bucket name** — must be globally unique across all of AWS, lowercase, no
   underscores. Something like `prism-mro-<yourname>` or `prism-mro-innovent27`.
   Write it down; you need it twice more below.
4. Leave **Block all public access ON**. The corpus and case data should not be
   public, and nothing in PRISM reads from a public URL.
5. Leave versioning and encryption at their defaults (SSE-S3 is on by default
   and is fine).
6. **Tags** — add both, exactly:

   | Key | Value |
   |---|---|
   | `Name` | the team leader's name |
   | `Project Name` | `PRISM` |

7. **Create bucket.**

Tags must be set here in the console, not by a script: the IAM policy below
deliberately does not grant `s3:PutBucketTagging`, so nothing running on your
machine can change the billing tags.

## Step 2 — Create the IAM user and its access keys

Use a dedicated user rather than root credentials.

1. **IAM → Users → Create user.** Name it `prism-dev`.
2. Do **not** give it console access — this user is only for the scripts.
3. **Permissions → Attach policies directly → Create policy → JSON tab.**
4. Paste the contents of [`infra/iam-policy-prism-dev.json`](../infra/iam-policy-prism-dev.json)
   as-is. It is already scoped to the real bucket, `prism-mro-innovent27`. The
   two ARNs are both needed and are not a duplicate: one without `/*` is the
   bucket itself (for listing), one with `/*` is the objects inside it. S3
   treats them as separate resources.
5. Name the policy `prism-dev-s3` and create it, then attach it to the user.
6. Open the user → **Security credentials** tab → **Create access key** →
   choose **Application running outside AWS** → Create.
7. Copy both values. **The secret is shown exactly once.** If you lose it,
   delete that key and make a new one — there is no way to retrieve it.

### What that policy allows, and why it's narrow

| Action | On | Why |
|---|---|---|
| `s3:ListBucket` | the bucket | list objects, check prefixes exist |
| `s3:GetBucketLocation` | the bucket | verify it really is in ap-south-1 |
| `s3:GetBucketTagging` | the bucket | verify the SOP tags are present |
| `s3:GetObject` | objects | download corpus / dataset / cases |
| `s3:PutObject` | objects | upload them |
| `s3:DeleteObject` | objects | clean up the write-probe test object |

It cannot touch any other bucket, cannot create or delete buckets, and cannot
change tags. If the key leaks, the blast radius is this one bucket.

## Step 3 — Put the credentials in `backend/.env`

Open `backend/.env` (it already exists) and fill in the four values:

```ini
AWS_ACCESS_KEY_ID=AKIA...................
AWS_SECRET_ACCESS_KEY=........................................
AWS_DEFAULT_REGION=ap-south-1
PRISM_S3_BUCKET=prism-mro-innovent27
```

The region and bucket name are already filled in. Only the two key values are
missing, and they are the two that must never leave your machine.

`backend/.env` is gitignored, so these can never be committed. Do not paste
them into chat, a ticket, or a screenshot.

## Step 4 — Verify

```bash
cd backend
venv\Scripts\activate
python scripts/s3_check.py
```

It checks, in order: the bucket exists and is in `ap-south-1`; `ListBucket`
works; a test object can be written and deleted; the four prefixes exist; and
both tags are present. Exit code 0 means everything blocking passed.

To create the four prefixes if they're missing:

```bash
python scripts/s3_check.py --bootstrap
```

Expected layout once populated:

```
s3://<your-bucket>/
├── corpus/           FAA advisory circular PDFs (the RAG source)
├── images/raw/       unlabelled defect images
├── images/labeled/   the YOLO dataset (images + labels)
└── cases/            history_cases.json
```

## Step 5 — Populate it

Once `s3_check.py` passes, I upload the three data sets the team shares — the
FAA corpus, the aircraft defect dataset, and the case memory — so a teammate on
another machine can pull them instead of re-downloading from Kaggle and faa.gov.

---

## What we are deliberately NOT using

| Service | Why not |
|---|---|
| **SageMaker Ground Truth** | It was only ever the fallback for having no labelled data. We now have a real CC BY 4.0 aircraft defect dataset, so a labelling job would spend monitored budget to produce something we already have. |
| **EC2** | Training runs on the laptop. An instance left running is the easiest way to burn credits by accident. |
| **IoT Greengrass** | Later-phase edge packaging, out of scope for this stage. |
| **Textract** | Would send the manuals to the cloud to extract text, which undercuts the offline-first claim. The local pdfplumber path handles these PDFs. |
| **AWS CLI** | Not needed — `boto3` is already installed and covers every operation above. |

## Cost

Well inside free tier: 5 GB of S3 storage, 20,000 GETs and 2,000 PUTs per month.
PRISM stores roughly 250 MB and touches it rarely. There is no compute running.

## If something fails

| Symptom | Cause |
|---|---|
| `bucket does not exist (404)` | Name typo, or the bucket is in a different account |
| `credentials lack s3:GetBucketLocation (403)` | Policy not attached to the user, or attached to a different user |
| `AccessDenied` on the write probe, though S3 actions look correct | The bucket was created with **SSE-KMS** instead of SSE-S3. Every `PutObject` then also needs `kms:GenerateDataKey` and every `GetObject` needs `kms:Decrypt`, which this policy deliberately does not grant. Recreate the bucket with SSE-S3. |
| `bucket is in us-east-1, expected ap-south-1` | Created before switching region — delete it and recreate |
| `no AWS credentials found` | `.env` values still blank, or the file was not saved |
