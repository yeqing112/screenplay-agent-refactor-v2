"""Public asset storage helpers for external generation providers.

External video providers cannot fetch images from a LAN-only workstation. This
module publishes eligible local assets to an object store and returns a URL the
provider can pull. Qiniu is the first supported backend.
"""

from __future__ import annotations

import base64
import hashlib
import mimetypes
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import httpx

import config


@dataclass
class PublicAssetResult:
    ok: bool
    source_url: str
    public_url: str = ""
    storage_provider: str = ""
    object_key: str = ""
    content_type: str = ""
    bytes_count: int = 0
    uploaded: bool = False
    signed: bool = False
    source_accessible: bool | None = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "source_url": self.source_url,
            "public_url": self.public_url,
            "storage_provider": self.storage_provider,
            "object_key": self.object_key,
            "content_type": self.content_type,
            "bytes_count": self.bytes_count,
            "uploaded": self.uploaded,
            "signed": self.signed,
            "source_accessible": self.source_accessible,
            "error": self.error,
        }


def public_asset_storage_enabled() -> bool:
    return config.PUBLIC_ASSET_STORAGE_PROVIDER == "qiniu" and bool(
        config.QINIU_ACCESS_KEY
        and config.QINIU_SECRET_KEY
        and config.QINIU_BUCKET
        and config.QINIU_PUBLIC_BASE_URL
    )


def check_public_url_accessible(url: str, *, timeout_seconds: float = 10.0) -> tuple[bool, str]:
    normalized = str(url or "").strip()
    if not normalized:
        return False, "empty_url"
    if not normalized.startswith(("http://", "https://")):
        return False, "not_http_url"
    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            response = client.get(normalized, headers={"Range": "bytes=0-0"})
        if 200 <= response.status_code < 300:
            return True, ""
        return False, f"http_{response.status_code}"
    except Exception as exc:  # pragma: no cover - network-specific
        return False, str(exc)


def ensure_provider_accessible_url(
    source_url: str,
    *,
    key_hint: str,
    local_base_url: str | None = None,
) -> PublicAssetResult:
    normalized = str(source_url or "").strip()
    if not normalized:
        return PublicAssetResult(ok=False, source_url="", error="empty_source_url")

    if normalized.startswith(("http://", "https://")) and not _is_local_http_url(normalized):
        accessible, error = check_public_url_accessible(normalized)
        if accessible:
            return PublicAssetResult(ok=True, source_url=normalized, public_url=normalized, source_accessible=True)
        if not public_asset_storage_enabled():
            return PublicAssetResult(ok=False, source_url=normalized, source_accessible=False, error=error)

    if not public_asset_storage_enabled():
        return PublicAssetResult(ok=False, source_url=normalized, error="public_asset_storage_not_configured")

    try:
        data, content_type = _load_source_bytes(normalized, local_base_url=local_base_url)
        public_url, object_key, signed = _upload_bytes_to_qiniu(data, content_type=content_type, key_hint=key_hint)
        accessible, error = check_public_url_accessible(public_url)
        return PublicAssetResult(
            ok=accessible,
            source_url=normalized,
            public_url=public_url,
            storage_provider="qiniu",
            object_key=object_key,
            content_type=content_type,
            bytes_count=len(data),
            uploaded=True,
            signed=signed,
            source_accessible=accessible,
            error="" if accessible else error,
        )
    except Exception as exc:
        return PublicAssetResult(
            ok=False,
            source_url=normalized,
            storage_provider="qiniu",
            error=str(exc),
        )


def _is_local_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def _load_source_bytes(source_url: str, *, local_base_url: str | None = None) -> tuple[bytes, str]:
    if source_url.startswith("data:"):
        return _load_data_uri(source_url)
    if source_url.startswith("/"):
        base_url = (local_base_url or config.PUBLIC_ASSET_LOCAL_BASE_URL or "").rstrip("/") + "/"
        return _download_bytes(urljoin(base_url, source_url.lstrip("/")))
    if source_url.startswith(("http://", "https://")):
        return _download_bytes(source_url)
    path = Path(source_url)
    if not path.is_absolute():
        path = config.BASE_DIR / path
    data = path.read_bytes()
    content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return data, content_type


def _load_data_uri(data_uri: str) -> tuple[bytes, str]:
    match = re.match(r"^data:([^;,]+)?(;base64)?,(.*)$", data_uri, flags=re.DOTALL)
    if not match:
        raise RuntimeError("invalid_data_uri")
    content_type = match.group(1) or "application/octet-stream"
    is_base64 = bool(match.group(2))
    payload = match.group(3)
    if is_base64:
        return base64.b64decode(payload), content_type
    from urllib.parse import unquote_to_bytes

    return unquote_to_bytes(payload), content_type


def _download_bytes(url: str) -> tuple[bytes, str]:
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(url)
    response.raise_for_status()
    content_type = str(response.headers.get("content-type") or "").split(";")[0].strip()
    return response.content, content_type or "application/octet-stream"


def _upload_bytes_to_qiniu(data: bytes, *, content_type: str, key_hint: str) -> tuple[str, str, bool]:
    try:
        from qiniu import Auth, put_data
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("qiniu SDK is not installed; run pip install -r requirements.txt") from exc

    digest = hashlib.sha256(data).hexdigest()[:16]
    ext = mimetypes.guess_extension(content_type) or ".bin"
    safe_hint = re.sub(r"[^A-Za-z0-9._/-]+", "-", str(key_hint or "asset")).strip("-/") or "asset"
    date_prefix = datetime.now(UTC).strftime("%Y/%m/%d")
    prefix = config.QINIU_KEY_PREFIX.strip("/")
    object_key = f"{prefix}/{date_prefix}/{safe_hint}-{digest}{ext}" if prefix else f"{date_prefix}/{safe_hint}-{digest}{ext}"

    auth = Auth(config.QINIU_ACCESS_KEY, config.QINIU_SECRET_KEY)
    token = auth.upload_token(config.QINIU_BUCKET, object_key, config.QINIU_UPLOAD_TOKEN_EXPIRES_SECONDS)
    ret, info = put_data(token, object_key, data, mime_type=content_type or "application/octet-stream")
    if getattr(info, "status_code", 0) not in {200, 614}:
        raise RuntimeError(f"qiniu_upload_failed:{getattr(info, 'status_code', '')}:{getattr(info, 'text_body', '')}")
    if not isinstance(ret, dict) or str(ret.get("key") or object_key) != object_key:
        raise RuntimeError("qiniu_upload_returned_unexpected_key")

    unsigned_url = f"{config.QINIU_PUBLIC_BASE_URL}/{quote(object_key)}"
    if config.QINIU_BUCKET_PRIVATE:
        return auth.private_download_url(unsigned_url, expires=config.QINIU_PUBLIC_URL_TTL_SECONDS), object_key, True
    return unsigned_url, object_key, False
