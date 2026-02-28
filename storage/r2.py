"""
Cloudflare R2 storage — upload final videos and return public URLs.

Free tier: 10 GB storage, 1M writes/month, 10M reads/month, zero egress fees.

Setup:
  1. Create a Cloudflare account → R2 → New bucket
  2. Bucket settings → Enable "Public Access" (gives you a *.r2.dev URL)
  3. R2 → Manage R2 API Tokens → Create token (Object Read & Write)
  4. Set env vars: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
                   R2_BUCKET_NAME, R2_PUBLIC_URL
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

_client = None  # lazy boto3 S3 client


def _get_client(account_id: str, access_key: str, secret_key: str):
    global _client
    if _client is None:
        import boto3

        _client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
        )
    return _client


def upload_video(
    file_path: Path,
    bucket: str,
    account_id: str,
    access_key: str,
    secret_key: str,
    public_url: str,
    key: str | None = None,
) -> str:
    """
    Upload a video file to R2 and return its public URL.

    Args:
        file_path:  Local path to the .mp4 file.
        bucket:     R2 bucket name.
        account_id: Cloudflare account ID.
        access_key: R2 API token access key ID.
        secret_key: R2 API token secret access key.
        public_url: Public base URL for the bucket (e.g. https://pub-xxx.r2.dev
                    or your custom domain). No trailing slash.
        key:        Object key in the bucket. Defaults to the filename.

    Returns:
        Public URL of the uploaded video.
    """
    if key is None:
        key = f"videos/{file_path.name}"

    client = _get_client(account_id, access_key, secret_key)

    log.info("Uploading %s → r2://%s/%s", file_path.name, bucket, key)
    with open(file_path, "rb") as f:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=f,
            ContentType="video/mp4",
        )

    url = f"{public_url.rstrip('/')}/{key}"
    log.info("Uploaded → %s", url)
    return url


def upload_json(
    data: dict,
    bucket: str,
    account_id: str,
    access_key: str,
    secret_key: str,
    key: str,
) -> None:
    """
    Upload a dict as a JSON file to R2. Used for persisting LLM plan output.

    Args:
        data:       Dict to serialise and upload.
        bucket:     R2 bucket name.
        account_id: Cloudflare account ID.
        access_key: R2 API token access key ID.
        secret_key: R2 API token secret access key.
        key:        Object key in the bucket (e.g. "plans/abc123.json").
    """
    import json

    client = _get_client(account_id, access_key, secret_key)
    body = json.dumps(data, indent=2, ensure_ascii=False).encode()

    log.info("Uploading JSON → r2://%s/%s (%d bytes)", bucket, key, len(body))
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
    )
