"""
Pull raw data files from the team's R2 bucket into ./csv/.

Why this exists:
    Raw source files are too large for Git. They live in R2; this
    script is what makes the bucket a shared source of truth instead
    of something only one person can reach.

Setup (each team member, once):
    pip install boto3 python-dotenv
    cp .env.example .env      # then fill in the credentials
    python scripts/fetch_raw.py

NEVER commit .env.

Usage:
    python scripts/fetch_raw.py              # skip files already present
    python scripts/fetch_raw.py --force      # re-download everything
    python scripts/fetch_raw.py --list       # show what's in the bucket
"""

import argparse
import gzip
import os
import shutil
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv

# Anchor to the repo, not the working directory. Drop one .parent if
# this script sits at the repo root rather than in scripts/.
BASE_DIR = Path(__file__).resolve().parent.parent
DEST = BASE_DIR / "csv"

load_dotenv(BASE_DIR / ".env")

ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
ACCESS_KEY = os.getenv("R2_ACCESS_KEY_ID")
SECRET_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
BUCKET = os.getenv("R2_BUCKET", "cool-route-raw")

PREFIX = "raw/"


def client():
    """R2 speaks the S3 API, so boto3 works with a custom endpoint."""
    missing = [
        n
        for n, v in [
            ("R2_ACCOUNT_ID", ACCOUNT_ID),
            ("R2_ACCESS_KEY_ID", ACCESS_KEY),
            ("R2_SECRET_ACCESS_KEY", SECRET_KEY),
        ]
        if not v
    ]
    if missing:
        print(f"Missing env vars: {', '.join(missing)}")
        print("Copy .env.example to .env and fill it in.")
        sys.exit(1)

    return boto3.client(
        "s3",
        endpoint_url=f"https://{ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        region_name="auto",  # R2 ignores region but boto3 wants one
    )


def list_objects(s3) -> list[dict]:
    """Every object under PREFIX. Paginates - buckets can exceed 1000 keys."""
    objects, token = [], None
    while True:
        kwargs = {"Bucket": BUCKET, "Prefix": PREFIX}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        objects.extend(resp.get("Contents", []))
        if not resp.get("IsTruncated"):
            break
        token = resp["NextContinuationToken"]
    return objects


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def download(s3, obj: dict, force: bool) -> str:
    """Returns 'skipped', 'downloaded', or 'failed'."""
    key = obj["Key"]
    name = Path(key).name
    target = DEST / name

    # Gzipped uploads land decompressed, so check for the final name.
    final = DEST / name[:-3] if name.endswith(".gz") else target

    if final.exists() and not force:
        print(f"  skip      {final.name}")
        return "skipped"

    print(f"  download  {name}  ({human(obj['Size'])})")
    try:
        s3.download_file(BUCKET, key, str(target))
    except ClientError as e:
        print(f"  FAILED    {name}: {e}")
        return "failed"

    if name.endswith(".gz"):
        with gzip.open(target, "rb") as fin, open(final, "wb") as fout:
            shutil.copyfileobj(fin, fout)
        target.unlink()
        print(f"            -> {final.name}  ({human(final.stat().st_size)})")

    return "downloaded"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-download existing files")
    ap.add_argument("--list", action="store_true", help="list bucket contents only")
    args = ap.parse_args()

    try:
        s3 = client()
        objects = list_objects(s3)
    except NoCredentialsError:
        print("Credentials rejected. Check .env.")
        return 1
    except ClientError as e:
        print(f"Could not reach the bucket: {e}")
        print(f"Is R2_BUCKET correct? Currently: {BUCKET}")
        return 1

    if not objects:
        print(f"Nothing under '{PREFIX}' in bucket '{BUCKET}'.")
        print("Has anyone uploaded yet? Check the prefix.")
        return 1

    total = sum(o["Size"] for o in objects)
    print(f"{len(objects)} objects, {human(total)} total\n")

    if args.list:
        for o in sorted(objects, key=lambda x: x["Key"]):
            print(f"  {human(o['Size']):>10}  {o['Key']}")
        return 0

    DEST.mkdir(parents=True, exist_ok=True)

    counts = {"downloaded": 0, "skipped": 0, "failed": 0}
    for obj in sorted(objects, key=lambda x: x["Key"]):
        counts[download(s3, obj, args.force)] += 1

    print(
        f"\ndownloaded {counts['downloaded']}  "
        f"skipped {counts['skipped']}  "
        f"failed {counts['failed']}"
    )

    if counts["failed"]:
        print("Some files failed. Re-run to retry just those.")
        return 1

    print(f"\nFiles are in {DEST}/ (gitignored). Raw data is never edited in place -")
    print("scripts read from here and write to cleaned_data/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
