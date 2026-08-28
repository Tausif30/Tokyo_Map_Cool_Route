"""
Upload_To_R2.py — pushes outputs/, cleaned_data/, and every *.py pipeline
script up to the hackathon's Cloudflare R2 bucket in one run.

Uses boto3 against R2's S3-compatible endpoint — per the hackathon's own
"サービス公開環境利用マニュアル2026", R2 speaks the S3 API directly, so any
S3 SDK works once pointed at the right endpoint. No wrangler CLI needed.

CREDENTIALS: read from environment variables, never hardcoded. Set these
in your shell (or a .env you keep OUT of git) before running:
    R2_ACCOUNT_ID        - Cloudflare dashboard, R2 Overview page
    R2_ACCESS_KEY_ID      \\_ from R2 > Manage R2 API Tokens > Create API
    R2_SECRET_ACCESS_KEY  /  token (Object Read & Write)
    R2_BUCKET_NAME       - the bucket you made with `wrangler r2 bucket create`

WHAT GETS UPLOADED (paths relative to this script's own folder):
    outputs/**                          -> R2 key "outputs/..."
    cleaned_data/** (incl. charts/ PNGs) -> R2 key "cleaned_data/..."
    *.py in THIS folder only (not subfolders, not this script itself)
                                          -> R2 key "python/..."
Deliberately NOT uploaded: raw csv/, the shapefile category folders
(Water_Canals/, Street_Trees/, etc.), and osm_raw/ (the 460 MB Kanto pbf).
Those are large, re-derivable from Map_Data.py / OSM_Konbini_Offline.py,
and not worth the R2 storage — re-run the pipeline locally instead of
uploading raw sources.

SAFE TO RE-RUN: before uploading, each file's MD5 is compared against the
object already in R2 (via its ETag) and skipped if unchanged, so adding
one new chart and re-running doesn't re-upload everything.

USAGE:
    python Upload_To_R2.py             # actually uploads
    python Upload_To_R2.py --dry-run   # lists what would happen, uploads nothing
"""

import argparse
import hashlib
import mimetypes
import os
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

# (local folder, R2 key prefix) — walked recursively
UPLOAD_TARGETS = [
    (BASE_DIR / "outputs", "outputs"),
    (BASE_DIR / "cleaned_data", "cleaned_data"),
]
PYTHON_FILES_PREFIX = "python"


def get_r2_client():
    account_id = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def local_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def needs_upload(client, bucket, key, local_path):
    """True if the object is missing from R2 or differs from the local file."""
    try:
        head = client.head_object(Bucket=bucket, Key=key)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return True
        raise
    remote_etag = head["ETag"].strip('"')
    # Multipart-uploaded objects get a composite ETag (contains "-") that
    # isn't a plain MD5 - always re-upload rather than guess wrong and
    # silently skip a file that actually changed.
    if "-" in remote_etag:
        return True
    return remote_etag != local_md5(local_path)


def iter_upload_pairs():
    """Yield (local_path, r2_key) for every file this script should push."""
    for local_root, key_prefix in UPLOAD_TARGETS:
        if not local_root.exists():
            print(f"  (skipping {local_root.name}/ - not found next to this script)")
            continue
        for path in sorted(local_root.rglob("*")):
            if path.is_file():
                rel = path.relative_to(local_root)
                yield path, f"{key_prefix}/{rel.as_posix()}"
    # Explicitly catch the massive routing graph from the cache so it maps to outputs/
    cached_graph = BASE_DIR / ".cache" / "cool_route" / "scored_walking.graphml"
    if cached_graph.exists():
        yield cached_graph, "outputs/scored_walking.pkl"
    
    for path in sorted(BASE_DIR.glob("*.py")):
        if path.resolve() == Path(__file__).resolve():
            continue  # don't upload this uploader script to itself
        yield path, f"{PYTHON_FILES_PREFIX}/{path.name}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                         help="Show what would be uploaded without uploading")
    args = parser.parse_args()

    if args.dry_run:
        client, bucket = None, "<dry-run, no bucket needed>"
    else:
        bucket = os.environ["R2_BUCKET_NAME"]
        client = get_r2_client()

    uploaded, skipped, total_bytes = 0, 0, 0
    for local_path, key in iter_upload_pairs():
        size = local_path.stat().st_size
        if args.dry_run:
            print(f"  [dry-run] {key}  ({size / 1024:.1f} KB)")
            continue

        if not needs_upload(client, bucket, key, local_path):
            skipped += 1
            continue

        content_type, _ = mimetypes.guess_type(local_path.name)
        extra_args = {"ContentType": content_type} if content_type else {}
        client.upload_file(str(local_path), bucket, key, ExtraArgs=extra_args)
        uploaded += 1
        total_bytes += size
        print(f"  uploaded {key}  ({size / 1024:.1f} KB)")

    if not args.dry_run:
        print(f"\nDone. {uploaded} uploaded ({total_bytes / 1e6:.1f} MB total), "
              f"{skipped} already up to date in bucket '{bucket}'.")