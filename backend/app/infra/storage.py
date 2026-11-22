"""Stored files: a folder (the default, in the data folder), Amazon S3 or any S3-compatible store (MinIO, R2, GCS
through its S3 interface), or Google Cloud Storage. Chosen by EVIDENCE_LAB_STORAGE_URL:

  (unset)                     no copies are made (the default)
  /some/folder or file://...  that folder
  s3://bucket/prefix          S3; EVIDENCE_LAB_S3_ENDPOINT_URL names another S3-compatible server (MinIO: http://minio:9000)
  gs://bucket/prefix          Google Cloud Storage, with the host's Google credentials

What the app puts here is a copy: the scanner file of each import and each evidence download. The database stays the
record; a copy that could not be written is logged and changes no answer.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

log = logging.getLogger("evidence_lab.storage")

_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,500}$")


def check_key(key: str) -> str:
    if not _SAFE_KEY.match(key) or ".." in key.split("/") or "//" in key:
        raise ValueError(f"not a safe storage key: {key!r}")
    return key


def safe_name(name: str) -> str:
    """A file name as it may appear in a key: letters, digits, dot, dash and underscore only."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "file"
    return cleaned[:120]


class BlobStore(Protocol):
    kind: str
    location: str

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None: ...
    def get(self, key: str) -> bytes | None: ...
    def exists(self, key: str) -> bool: ...
    def ping(self) -> None: ...


class LocalStore:
    kind = "local"

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.location = str(self.root)

    def _path(self, key: str) -> Path:
        return self.root / check_key(key)

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def get(self, key: str) -> bytes | None:
        path = self._path(key)
        return path.read_bytes() if path.is_file() else None

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def ping(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not os.access(self.root, os.W_OK):
            raise OSError(f"cannot write to {self.root}")


class S3Store:
    kind = "s3"

    def __init__(self, bucket: str, prefix: str, endpoint_url: str | None = None, region: str | None = None) -> None:
        import boto3  # optional package (requirements-infra.in)
        from botocore.config import Config

        self.bucket, self.prefix = bucket, prefix.strip("/")
        self.location = f"s3://{bucket}/{self.prefix}" + (f" at {endpoint_url}" if endpoint_url else "")
        # Path-style addressing works with MinIO and other S3-compatible servers as well as AWS.
        config = Config(
            s3={"addressing_style": "path"} if endpoint_url else {},
            retries={"max_attempts": 3},
            connect_timeout=5,
            read_timeout=30,
        )
        self._s3 = boto3.client("s3", endpoint_url=endpoint_url, region_name=region, config=config)

    def _key(self, key: str) -> str:
        check_key(key)
        return f"{self.prefix}/{key}" if self.prefix else key

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self._s3.put_object(Bucket=self.bucket, Key=self._key(key), Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes | None:
        from botocore.exceptions import ClientError

        try:
            return self._s3.get_object(Bucket=self.bucket, Key=self._key(key))["Body"].read()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._s3.head_object(Bucket=self.bucket, Key=self._key(key))
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound"):
                return False
            raise

    def ping(self) -> None:
        self._s3.head_bucket(Bucket=self.bucket)


class GCSStore:
    kind = "gcs"

    def __init__(self, bucket: str, prefix: str) -> None:
        from google.cloud import storage  # optional package (requirements-infra.in)

        self.prefix = prefix.strip("/")
        self.location = f"gs://{bucket}/{self.prefix}"
        self._bucket = storage.Client().bucket(bucket)

    def _key(self, key: str) -> str:
        check_key(key)
        return f"{self.prefix}/{key}" if self.prefix else key

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self._bucket.blob(self._key(key)).upload_from_string(data, content_type=content_type)

    def get(self, key: str) -> bytes | None:
        blob = self._bucket.blob(self._key(key))
        return blob.download_as_bytes() if blob.exists() else None

    def exists(self, key: str) -> bool:
        return self._bucket.blob(self._key(key)).exists()

    def ping(self) -> None:
        if not self._bucket.exists():
            raise OSError(f"bucket {self._bucket.name} does not exist or cannot be read")


def make_store(url: str | None) -> BlobStore | None:
    """None when no store is named: then the app copies nothing anywhere (the default, as before hosting)."""
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme == "s3":
        if not parsed.netloc:
            raise SystemExit("EVIDENCE_LAB_STORAGE_URL: s3:// needs a bucket, for example s3://evidence-lab/files")
        return S3Store(
            parsed.netloc,
            parsed.path,
            endpoint_url=os.environ.get("EVIDENCE_LAB_S3_ENDPOINT_URL") or None,
            region=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or None,
        )
    if parsed.scheme == "gs":
        if not parsed.netloc:
            raise SystemExit("EVIDENCE_LAB_STORAGE_URL: gs:// needs a bucket, for example gs://evidence-lab/files")
        return GCSStore(parsed.netloc, parsed.path)
    if parsed.scheme == "file":
        return LocalStore(Path(parsed.path))
    if parsed.scheme == "":
        return LocalStore(Path(url))
    raise SystemExit("EVIDENCE_LAB_STORAGE_URL must be a folder, file://, s3:// or gs://")


def put_quietly(store: BlobStore, key: str, data: bytes, content_type: str) -> bool:
    """Write a copy; a failure is logged and reported as False, never raised (the database holds the record)."""
    try:
        store.put(key, data, content_type)
        return True
    except Exception as exc:  # noqa: BLE001 - any storage failure leaves the record in the database as it is
        log.warning("could not store a copy at %s/%s: %s", store.location, key, exc)
        return False
