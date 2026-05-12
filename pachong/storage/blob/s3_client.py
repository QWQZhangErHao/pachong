"""aioboto3 async S3 client with automatic Brotli compression.

All raw HTML and screenshots flow through this module.
Data is always compressed before upload and decompressed on download.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import aioboto3

from pachong.core.compression import compress, decompress, decompress_html

if TYPE_CHECKING:
    from types_aiobotocore_s3 import S3Client

    from pachong.core.settings import S3Settings


_session: aioboto3.Session | None = None
_client: "S3Client | None" = None
_settings: "S3Settings | None" = None


def init_s3(settings: "S3Settings") -> "S3Client":
    """Initialize aioboto3 session. Returns the client."""
    global _session, _client, _settings
    _settings = settings

    _session = aioboto3.Session(
        aws_access_key_id=settings.access_key,
        aws_secret_access_key=settings.secret_key,
        region_name=settings.region,
    )
    _client = _session.create_client(
        "s3",
        endpoint_url=settings.endpoint,
        use_ssl=settings.use_ssl,
    )
    return _client


def get_s3() -> "S3Client":
    """Get the S3 client handle."""
    if _client is None:
        raise RuntimeError("S3 not initialized. Call init_s3() first.")
    return _client


async def ensure_bucket() -> None:
    """Create the bucket if it doesn't exist."""
    s3 = get_s3()
    try:
        await s3.head_bucket(Bucket=_settings.bucket)
    except Exception:
        await s3.create_bucket(Bucket=_settings.bucket)


async def upload_raw_html(html: str, key: str, content_type: str = "text/html") -> str:
    """Compress and upload raw HTML to S3. Returns the S3 key."""
    s3 = get_s3()
    compressed = compress(html.encode("utf-8"), algo=_settings.compression, level=_settings.compression_level)

    await s3.put_object(
        Bucket=_settings.bucket,
        Key=key,
        Body=compressed,
        ContentType=content_type,
        ContentEncoding=_settings.compression,
        Metadata={"original-size": str(len(html.encode("utf-8"))), "compressed-size": str(len(compressed))},
    )
    return key


async def upload_screenshot(image_bytes: bytes, key: str, content_type: str = "image/png") -> str:
    """Upload screenshot bytes to S3. Screenshots are already compressed (PNG) so no double compression."""
    s3 = get_s3()
    await s3.put_object(
        Bucket=_settings.bucket,
        Key=key,
        Body=image_bytes,
        ContentType=content_type,
    )
    return key


async def download_raw_html(key: str) -> str:
    """Download and decompress raw HTML from S3."""
    s3 = get_s3()
    response = await s3.get_object(Bucket=_settings.bucket, Key=key)
    data = await response["Body"].read()

    content_encoding = response.get("ContentEncoding", "")
    if content_encoding in ("brotli", "gzip"):
        return decompress_html(data, algo=content_encoding)
    return data.decode("utf-8")


async def download_bytes(key: str) -> bytes:
    """Download raw bytes from S3."""
    s3 = get_s3()
    response = await s3.get_object(Bucket=_settings.bucket, Key=key)
    data = await response["Body"].read()

    content_encoding = response.get("ContentEncoding", "")
    if content_encoding in ("brotli", "gzip"):
        return decompress(data, algo=content_encoding)
    return data


async def delete_object(key: str) -> None:
    """Delete an object from S3."""
    s3 = get_s3()
    await s3.delete_object(Bucket=_settings.bucket, Key=key)


async def object_exists(key: str) -> bool:
    """Check if an object exists in S3."""
    s3 = get_s3()
    try:
        await s3.head_object(Bucket=_settings.bucket, Key=key)
        return True
    except Exception:
        return False


async def generate_presigned_url(key: str, expires_in: int = 3600) -> str:
    """Generate a presigned URL for temporary access (useful for serverless handoff)."""
    s3 = get_s3()
    url = await s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": _settings.bucket, "Key": key},
        ExpiresIn=expires_in,
    )
    return url


async def close_s3() -> None:
    """Close S3 client connections."""
    if _client:
        await _client.close()
