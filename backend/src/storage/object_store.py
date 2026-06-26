"""Object storage with tenant-prefixed keys.

All artifacts (uploaded sources now; decks later) live under a tenant prefix so
storage layout mirrors the isolation boundary. The MinIO client is created lazily
so importing this module never requires a reachable storage backend (keeps tests
and the API process light). A Protocol documents the surface used elsewhere.
"""

from __future__ import annotations

import io
from functools import lru_cache
from typing import Protocol

from ..core.config import get_settings
from ..core.logging import get_logger

logger = get_logger("orchestrator.storage")


def tenant_key(*, tenant_id: str, project_id: str, source_id: str, filename: str) -> str:
    """Deterministic tenant-prefixed key: <tenant>/<project>/sources/<source>/<file>."""
    safe = filename.replace("/", "_").strip() or "upload"
    return f"{tenant_id}/{project_id}/sources/{source_id}/{safe}"


class ObjectStore(Protocol):
    def tenant_key(
        self, *, tenant_id: str, project_id: str, source_id: str, filename: str
    ) -> str: ...

    def put_bytes(self, *, key: str, data: bytes, content_type: str) -> None: ...

    def get_bytes(self, *, key: str) -> bytes: ...

    def presigned_get(self, *, key: str) -> str: ...


class MinioObjectStore:
    """MinIO/S3-compatible store. Engine fetches files via short-lived presigned URLs."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = None  # lazily constructed
        self._bucket_ready = False

    def _minio(self):
        if self._client is None:
            from minio import Minio  # lazy import; optional at import time

            endpoint = self._settings.minio_endpoint.replace("http://", "").replace(
                "https://", ""
            )
            self._client = Minio(
                endpoint,
                access_key=self._settings.minio_root_user,
                secret_key=self._settings.minio_root_password,
                secure=self._settings.minio_secure,
            )
        return self._client

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        client = self._minio()
        bucket = self._settings.minio_bucket
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        self._bucket_ready = True

    def tenant_key(
        self, *, tenant_id: str, project_id: str, source_id: str, filename: str
    ) -> str:
        return tenant_key(
            tenant_id=tenant_id,
            project_id=project_id,
            source_id=source_id,
            filename=filename,
        )

    def put_bytes(self, *, key: str, data: bytes, content_type: str) -> None:
        self._ensure_bucket()
        self._minio().put_object(
            self._settings.minio_bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        logger.info("object_stored", extra={"key": key, "bytes": len(data)})

    def get_bytes(self, *, key: str) -> bytes:
        self._ensure_bucket()
        response = self._minio().get_object(self._settings.minio_bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def presigned_get(self, *, key: str) -> str:
        from datetime import timedelta

        self._ensure_bucket()
        return self._minio().presigned_get_object(
            self._settings.minio_bucket,
            key,
            expires=timedelta(seconds=self._settings.ingest_presign_ttl_seconds),
        )


@lru_cache
def get_object_store() -> MinioObjectStore:
    """Process-wide store singleton (the client connects lazily on first use)."""
    return MinioObjectStore()
