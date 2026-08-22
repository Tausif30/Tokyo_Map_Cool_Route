"""
Pull raw data files from the team's R2 bucket into the project, restoring
each file to the same relative path it has locally (csv/..., Water_Canals/...,
osm_raw/..., etc. - see directory-tree.txt) so Map_Data.py's category-folder
scanning and everything else that reads from csv/ just works.

Why this exists:
    Raw source files are too large for Git. They live in R2; this
    script is what makes the bucket a shared source of truth instead
    of something only one person can reach.

Setup (each team member, once):
    pip install boto3 python-dotenv
    cp .env.example .env      # then fill in the credentials
    python fetch_raw.py

NEVER commit .env.

Usage:
    python fetch_raw.py              # skip files already present
    python fetch_raw.py --force      # re-download everything
    python fetch_raw.py --list       # show what's in the bucket
"""

import argparse
import gzip
import os
import shutil
import sys
from pathlib import Path, PurePosixPath

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv

# fetch_raw.py sits at the repo root, next to Map_Data.py / wrangler.py /
# etc. (per directory-tree.txt), not in a scripts/ subfolder - one .parent,
# not two. (With the old two-.parent version, BASE_DIR resolved to the
# folder ABOVE the project, so .env was never found and everything would
# have downloaded into a sibling folder outside the repo entirely.)
BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
ACCESS_KEY = os.getenv("R2_ACCESS_KEY_ID")
SECRET_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
# Renamed from R2_BUCKET to R2_BUCKET_NAME to match wrangler.py's own env
# var. Previously these two scripts read two different variable names, so
# a .env with only one of them set would leave the other script silently
# falling back to its own default bucket instead of erroring - the kind of
# bug that only shows up as "why is fetch_raw pulling from the wrong
# bucket" days later.
BUCKET = os.getenv("R2_BUCKET_NAME", "cool-route-raw")

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
    """Every real object under PREFIX. Paginates - buckets can exceed 1000
    keys. Skips zero-byte 'folder placeholder' objects (key ends in '/')
    that some S3-compatible bucket UIs create when you make a folder -
    those aren't files to download, and downloading one would land at
    BASE_DIR itself rather than inside it."""
    objects, token = [], None
    while True:
        kwargs = {"Bucket": BUCKET, "Prefix": PREFIX}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        objects.extend(o for o in resp.get("Contents", []) if not o["Key"].endswith("/"))
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


def local_target(key: str) -> Path:
    """Maps an R2 key back to where it belongs locally, preserving
    everything under PREFIX as real subfolders. e.g.
      raw/csv/1_1_Land_Area_by_District.csv  -> BASE_DIR/csv/1_1_Land_Area_by_District.csv
      raw/Water_Canals/08_水系/.../河川・運河.shp -> BASE_DIR/Water_Canals/08_水系/.../河川・運河.shp
      raw/osm_raw/kanto-latest.osm.pbf        -> BASE_DIR/osm_raw/kanto-latest.osm.pbf
    The previous version only kept the filename (Path(key).name), which
    silently flattened every shapefile's category folder into one pile -
    Map_Data.py identifies each shapefile's category from its top-level
    folder name (shp_path.relative_to(base_dir).parts[0]), so a flattened
    download would have made every shapefile invisible to it."""
    rel = PurePosixPath(key).relative_to(PREFIX)
    return BASE_DIR / Path(*rel.parts)


def download(s3, obj: dict, force: bool) -> str:
    """Returns 'skipped', 'downloaded', or 'failed'."""
    key = obj["Key"]
    target = local_target(key)

    # Gzipped uploads land decompressed, so check for the final name.
    final = target.with_suffix("") if target.suffix == ".gz" else target
    rel_display = final.relative_to(BASE_DIR)

    if final.exists() and not force:
        print(f"  skip      {rel_display}")
        return "skipped"

    target.parent.mkdir(parents=True, exist_ok=True)

    print(f"  download  {rel_display}  ({human(obj['Size'])})")
    try:
        s3.download_file(BUCKET, key, str(target))
    except ClientError as e:
        print(f"  FAILED    {rel_display}: {e}")
        return "failed"

    if target.suffix == ".gz":
        with gzip.open(target, "rb") as fin, open(final, "wb") as fout:
            shutil.copyfileobj(fin, fout)
        target.unlink()
        print(f"            -> {rel_display}  ({human(final.stat().st_size)})")

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
        print(f"Is R2_BUCKET_NAME correct? Currently: {BUCKET}")
        return 1

    if not objects:
        print(f"Nothing under '{PREFIX}' in bucket '{BUCKET}'.")
        print("Has anyone uploaded yet? Check the prefix.")
        return 1

    total = sum(o["Size"] for o in objects)
    print(f"{len(objects)} objects, {human(total)} total\n")

    if args.list:
        for o in sorted(objects, key=lambda x: x["Key"]):
            print(f"  {human(o['Size']):>10}  {o['Key']}  ->  {local_target(o['Key']).relative_to(BASE_DIR)}")
        return 0

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

    print(f"\nFiles are placed under {BASE_DIR}/, mirroring each key's path under '{PREFIX}'")
    print("(raw/csv/... -> csv/..., raw/Water_Canals/... -> Water_Canals/..., etc).")
    print("Raw data is never edited in place - scripts read from here and write to cleaned_data/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())