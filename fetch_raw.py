"""
Pull raw data files from the team's R2 bucket into the project, restoring
each file to the same relative path it has locally (csv/..., Water_Canals/...,
osm_raw/..., etc. - see directory-tree.txt) so Map_Data.py's category-folder
scanning and everything else that reads from csv/ just works.

Why this exists:
    Raw source files are too large for Git. They live in R2; this
    script is what makes the bucket a shared source of truth instead
    of something only one person can reach.

Some objects are very large (kanto-latest.osm.pbf, the multi-GB greenery
GeoJSON). Those are skipped by default so a fresh clone doesn't pull
gigabytes nobody on that part of the pipeline needs. Fetch them
deliberately with --big or --only.

Setup (each team member, once):
    pip install boto3 python-dotenv
    cp .env.example .env      # then fill in the credentials
    python fetch_raw.py

NEVER commit .env.

Usage:
    python fetch_raw.py                    # everything under the size cap
    python fetch_raw.py --list             # show what's in the bucket
    python fetch_raw.py --big              # include oversized objects
    python fetch_raw.py --only Water_Canals
    python fetch_raw.py --prefix outputs/  # a different bucket prefix
    python fetch_raw.py --force            # re-download existing files
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
BUCKET = os.getenv("R2_BUCKET_NAME", "tokyo-heat-map")

DEFAULT_PREFIX = "cleaned_data/"

# Anything larger is skipped unless --big or --only names it. Nothing this
# size belongs in the frontend, and only whoever is working on that
# specific dataset needs it locally.
SIZE_CAP_MB = 50


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


def list_objects(s3, prefix: str) -> list[dict]:
    """Every real object under the prefix. Paginates - buckets can exceed
    1000 keys. Skips zero-byte 'folder placeholder' objects (key ends in
    '/') that some S3-compatible bucket UIs create when you make a folder -
    those aren't files to download, and downloading one would land at
    BASE_DIR itself rather than inside it."""
    objects, token = [], None
    while True:
        kwargs = {"Bucket": BUCKET, "Prefix": prefix}
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


def local_target(key: str, prefix: str) -> Path:
    """Maps an R2 key back to where it belongs locally, preserving
    everything under the prefix as real subfolders. e.g.
      raw/csv/1_1_Land_Area_by_District.csv  -> BASE_DIR/csv/1_1_Land_Area_by_District.csv
      raw/Water_Canals/08_水系/.../河川・運河.shp -> BASE_DIR/Water_Canals/08_水系/.../河川・運河.shp
      raw/osm_raw/kanto-latest.osm.pbf        -> BASE_DIR/osm_raw/kanto-latest.osm.pbf
    Keeping only the filename (Path(key).name) would silently flatten every
    shapefile's category folder into one pile - Map_Data.py identifies each
    shapefile's category from its top-level folder name
    (shp_path.relative_to(base_dir).parts[0]), so a flattened download makes
    every shapefile invisible to it."""
    rel = PurePosixPath(key).relative_to(prefix)
    return BASE_DIR / Path(*rel.parts)


def download(s3, obj: dict, prefix: str, force: bool) -> str:
    """Returns 'skipped', 'downloaded', or 'failed'."""
    key = obj["Key"]
    target = local_target(key, prefix)

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
    ap.add_argument(
        "--big",
        action="store_true",
        help=f"include objects larger than {SIZE_CAP_MB} MB",
    )
    ap.add_argument(
        "--only",
        metavar="SUBSTR",
        help="only keys containing this substring (implies --big for those)",
    )
    ap.add_argument(
        "--prefix",
        default=DEFAULT_PREFIX,
        help=f"bucket prefix to mirror (default: {DEFAULT_PREFIX})",
    )
    args = ap.parse_args()

    prefix = args.prefix if args.prefix.endswith("/") else args.prefix + "/"

    try:
        s3 = client()
        objects = list_objects(s3, prefix)
    except NoCredentialsError:
        print("Credentials rejected. Check .env.")
        return 1
    except ClientError as e:
        print(f"Could not reach the bucket: {e}")
        print(f"Is R2_BUCKET_NAME correct? Currently: {BUCKET}")
        return 1

    if not objects:
        print(f"Nothing under '{prefix}' in bucket '{BUCKET}'.")
        print("Has anyone uploaded yet? Check the prefix.")
        return 1

    # --only is an explicit request, so it overrides the size cap for the
    # files it matches. Asking for a file by name and being told it's too
    # big would just be annoying.
    if args.only:
        objects = [o for o in objects if args.only.lower() in o["Key"].lower()]
        if not objects:
            print(f"No keys under '{prefix}' contain '{args.only}'.")
            return 1

    cap = SIZE_CAP_MB * 1024 * 1024
    allow_big = args.big or bool(args.only)

    total = sum(o["Size"] for o in objects)
    print(f"{len(objects)} objects, {human(total)} total\n")

    if args.list:
        for o in sorted(objects, key=lambda x: x["Key"]):
            flag = "  [OVER CAP]" if o["Size"] > cap and not allow_big else ""
            dest = local_target(o["Key"], prefix).relative_to(BASE_DIR)
            print(f"  {human(o['Size']):>10}  {o['Key']}  ->  {dest}{flag}")
        return 0

    counts = {"downloaded": 0, "skipped": 0, "too_big": 0, "failed": 0}
    skipped_bytes = 0

    for obj in sorted(objects, key=lambda x: x["Key"]):
        if obj["Size"] > cap and not allow_big:
            dest = local_target(obj["Key"], prefix).relative_to(BASE_DIR)
            print(f"  too big   {dest}  ({human(obj['Size'])})  — use --big or --only")
            counts["too_big"] += 1
            skipped_bytes += obj["Size"]
            continue
        counts[download(s3, obj, prefix, args.force)] += 1

    print(
        f"\ndownloaded {counts['downloaded']}  "
        f"skipped {counts['skipped']}  "
        f"too_big {counts['too_big']}  "
        f"failed {counts['failed']}"
    )

    if counts["too_big"]:
        print(f"Skipped {human(skipped_bytes)} of oversized objects (--big to include).")

    if counts["failed"]:
        print("Some files failed. Re-run to retry just those.")
        return 1

    print(f"\nFiles are placed under {BASE_DIR}/, mirroring each key's path under '{prefix}'")
    print("(raw/csv/... -> csv/..., raw/Water_Canals/... -> Water_Canals/..., etc).")
    print("Raw data is never edited in place - scripts read from here and write to cleaned_data/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
