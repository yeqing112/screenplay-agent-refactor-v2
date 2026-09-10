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
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import httpx

import config
from models import get_kv


PUBLIC_ASSET_STORAGE_KV_KEY = "public_asset_storage_config"


def _json_loads_dict(raw: str) -> dict[str, Any]:
    import json

    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class PublicAssetStorageConfig:
    provider: str
    local_base_url: str
    qiniu_access_key: str
    qiniu_secret_key: str
    qiniu_bucket: str
    qiniu_region: str
    qiniu_public_base_url: str
    qiniu_bucket_private: bool
    qiniu_key_prefix: str
    qiniu_upload_token_expires_seconds: int
    qiniu_public_url_ttl_seconds: int

    @property
    def enabled(self) -> bool:
        return self.provider == "qiniu" and bool(
            self.qiniu_access_key
            and self.qiniu_secret_key
            and self.qiniu_bucket
            and self.qiniu_public_base_url
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "enabled": self.enabled,
            "local_base_url": self.local_base_url,
            "qiniu_bucket": self.qiniu_bucket,
            "qiniu_region": self.qiniu_region,
            "qiniu_public_base_url": self.qiniu_public_base_url,
            "qiniu_bucket_private": self.qiniu_bucket_private,
            "qiniu_key_prefix": self.qiniu_key_prefix,
            "qiniu_upload_token_expires_seconds": self.qiniu_upload_token_expires_seconds,
            "qiniu_public_url_ttl_seconds": self.qiniu_public_url_ttl_seconds,
            "qiniu_access_key_configured": bool(self.qiniu_access_key),
            "qiniu_secret_key_configured": bool(self.qiniu_secret_key),
        }


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
    unstable_storage_override: bool = False

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
            "unstable_storage_override": self.unstable_storage_override,
        }


def public_asset_storage_enabled() -> bool:
    return load_public_asset_storage_config().enabled


def public_asset_storage_is_production_safe(
    storage_config: PublicAssetStorageConfig | None = None,
) -> bool:
    """Whether published objects may be used as production provider inputs.

    A configured bucket alone is not sufficient: Qiniu's ``clouddn.com``
    testing domains are temporary and the legacy endpoint may be HTTP.  This
    guard lives in the storage core (rather than only in the UI) so API callers
    cannot publish a reference and then send an unstable URL to a video model.
    """
    resolved = storage_config or load_public_asset_storage_config()
    if not resolved.enabled:
        return False
    try:
        parsed = urlparse(str(resolved.qiniu_public_base_url or "").strip())
    except ValueError:
        return False
    host = str(parsed.hostname or "").strip().lower()
    return bool(
        parsed.scheme == "https"
        and host
        and host != "clouddn.com"
        and not host.endswith(".clouddn.com")
    )


def public_asset_storage_production_requirement(
    storage_config: PublicAssetStorageConfig | None = None,
) -> str:
    """Return a stable, user-safe reason when production publishing is blocked."""
    resolved = storage_config or load_public_asset_storage_config()
    if not resolved.enabled:
        return "public_asset_storage_not_configured"
    try:
        parsed = urlparse(str(resolved.qiniu_public_base_url or "").strip())
    except ValueError:
        return "public_asset_storage_requires_custom_https_domain"
    host = str(parsed.hostname or "").strip().lower()
    if parsed.scheme != "https" or not host or host == "clouddn.com" or host.endswith(".clouddn.com"):
        return "public_asset_storage_requires_custom_https_domain"
    return ""


def load_public_asset_storage_config() -> PublicAssetStorageConfig:
    try:
        saved = _json_loads_dict(get_kv(PUBLIC_ASSET_STORAGE_KV_KEY, "{}"))
    except Exception:
        saved = {}
    return PublicAssetStorageConfig(
        provider=str(saved.get("provider") or config.PUBLIC_ASSET_STORAGE_PROVIDER or "").strip().lower(),
        local_base_url=str(saved.get("local_base_url") or config.PUBLIC_ASSET_LOCAL_BASE_URL or "").strip(),
        qiniu_access_key=str(saved.get("qiniu_access_key") or config.QINIU_ACCESS_KEY or "").strip(),
        qiniu_secret_key=str(saved.get("qiniu_secret_key") or config.QINIU_SECRET_KEY or "").strip(),
        qiniu_bucket=str(saved.get("qiniu_bucket") or config.QINIU_BUCKET or "").strip(),
        qiniu_region=str(saved.get("qiniu_region") or config.QINIU_REGION or "z2").strip(),
        qiniu_public_base_url=str(saved.get("qiniu_public_base_url") or config.QINIU_PUBLIC_BASE_URL or "").strip().rstrip("/"),
        qiniu_bucket_private=_coerce_bool(saved.get("qiniu_bucket_private"), config.QINIU_BUCKET_PRIVATE),
        qiniu_key_prefix=str(saved.get("qiniu_key_prefix") or config.QINIU_KEY_PREFIX or "screenplay-agent").strip().strip("/"),
        qiniu_upload_token_expires_seconds=_coerce_int(
            saved.get("qiniu_upload_token_expires_seconds"),
            config.QINIU_UPLOAD_TOKEN_EXPIRES_SECONDS,
        ),
        qiniu_public_url_ttl_seconds=_coerce_int(
            saved.get("qiniu_public_url_ttl_seconds"),
            config.QINIU_PUBLIC_URL_TTL_SECONDS,
        ),
    )


def check_public_url_accessible(
    url: str,
    *,
    timeout_seconds: float = 10.0,
    attempts: int = 3,
    retry_interval_seconds: float = 1.0,
) -> tuple[bool, str]:
    normalized = str(url or "").strip()
    if not normalized:
        return False, "empty_url"
    if not normalized.startswith(("http://", "https://")):
        return False, "not_http_url"
    normalized_attempts = max(1, int(attempts or 1))
    last_error = ""
    for attempt in range(normalized_attempts):
        try:
            with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
                response = client.get(normalized, headers={"Range": "bytes=0-0"})
            if 200 <= response.status_code < 300:
                return True, ""
            last_error = f"http_{response.status_code}"
        except Exception as exc:  # pragma: no cover - network-specific
            last_error = str(exc)
        if attempt + 1 < normalized_attempts:
            time.sleep(max(0.0, retry_interval_seconds))
    return False, last_error or "public_url_unreachable"


def _is_transient_public_url_check_error(error: str) -> bool:
    normalized = str(error or "").strip().lower()
    return any(
        token in normalized
        for token in (
            "timed out",
            "timeout",
            "readtimeout",
            "connecttimeout",
            "temporarily unavailable",
            "connection reset",
        )
    )


def ensure_provider_accessible_url(
    source_url: str,
    *,
    key_hint: str,
    local_base_url: str | None = None,
    force_storage: bool = False,
    allow_unstable_storage: bool = False,
) -> PublicAssetResult:
    normalized = str(source_url or "").strip()
    if not normalized:
        return PublicAssetResult(ok=False, source_url="", error="empty_source_url")

    if normalized.startswith(("http://", "https://")) and not force_storage and not _is_local_http_url(normalized):
        accessible, error = check_public_url_accessible(normalized)
        if accessible:
            return PublicAssetResult(ok=True, source_url=normalized, public_url=normalized, source_accessible=True)
        if not public_asset_storage_enabled():
            return PublicAssetResult(ok=False, source_url=normalized, source_accessible=False, error=error)

    storage_config = load_public_asset_storage_config()
    if not storage_config.enabled:
        return PublicAssetResult(ok=False, source_url=normalized, error="public_asset_storage_not_configured")
    unstable_storage_override = False
    if force_storage and not public_asset_storage_is_production_safe(storage_config):
        parsed = urlparse(str(storage_config.qiniu_public_base_url or "").strip())
        host = str(parsed.hostname or "").strip().lower()
        # A temporary Qiniu HTTP domain is never accepted by default.  The
        # only escape hatch is an explicit, request-scoped gray-test opt-in;
        # custom domains and other providers remain subject to the normal
        # production-safety check.
        is_temporary_qiniu_http = bool(
            storage_config.provider == "qiniu"
            and parsed.scheme == "http"
            and host.endswith(".clouddn.com")
        )
        if allow_unstable_storage and is_temporary_qiniu_http:
            unstable_storage_override = True
        else:
            requirement = public_asset_storage_production_requirement(storage_config)
            return PublicAssetResult(
                ok=False,
                source_url=normalized,
                storage_provider="qiniu",
                error=requirement,
            )

    try:
        data, content_type = _load_source_bytes(normalized, local_base_url=local_base_url or storage_config.local_base_url)
        data, content_type = _normalize_provider_image_bytes(data, content_type)
        public_url, object_key, signed = _upload_bytes_to_qiniu(
            data,
            content_type=content_type,
            key_hint=key_hint,
            storage_config=storage_config,
        )
        accessible, error = check_public_url_accessible(public_url)
        ok = accessible or _is_transient_public_url_check_error(error)
        return PublicAssetResult(
            ok=ok,
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
            unstable_storage_override=unstable_storage_override,
        )
    except Exception as exc:
        return PublicAssetResult(
            ok=False,
            source_url=normalized,
            storage_provider="qiniu",
            error=str(exc),
            unstable_storage_override=unstable_storage_override,
        )


def _is_local_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def _load_source_bytes(
    source_url: str,
    *,
    local_base_url: str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[bytes, str]:
    if source_url.startswith("data:"):
        return _load_data_uri(source_url)
    manual_media_prefix = "/api/prototyping/manual-media/"
    if source_url.startswith(manual_media_prefix):
        raw_name = source_url.removeprefix(manual_media_prefix).split("?", 1)[0].split("#", 1)[0]
        safe_name = config.sanitize_filename(raw_name.replace("\\", "/").split("/")[-1])
        if not safe_name:
            raise RuntimeError("invalid_manual_media_filename")
        media_dir = (config.UPLOAD_DIR / "manual-media").resolve()
        path = (media_dir / safe_name).resolve()
        try:
            path.relative_to(media_dir)
        except ValueError as exc:
            raise RuntimeError("invalid_manual_media_path") from exc
        if not path.exists() or not path.is_file():
            raise RuntimeError("manual_media_not_found")
        data = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        return data, content_type
    if source_url.startswith("/"):
        base_url = (local_base_url or config.PUBLIC_ASSET_LOCAL_BASE_URL or "").rstrip("/") + "/"
        return _download_bytes(urljoin(base_url, source_url.lstrip("/")), headers=headers)
    if source_url.startswith(("http://", "https://")):
        return _download_bytes(source_url, headers=headers)
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


def _normalize_provider_image_bytes(data: bytes, content_type: str) -> tuple[bytes, str]:
    """Normalize generated placeholder images to formats accepted by video providers.

    MiniMax H3 accepts raster image formats such as PNG/JPEG/WebP, but not SVG.
    The local workbench often uses SVG placeholders for repaired/legacy first
    frames, so the public bridge must rasterize SVG before uploading it.
    """

    normalized_type = str(content_type or "application/octet-stream").split(";")[0].strip().lower()
    if normalized_type != "image/svg+xml":
        return data, content_type or "application/octet-stream"
    try:
        import cairosvg
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("cairosvg is required to publish SVG first frames as PNG for video providers") from exc
    png_bytes = cairosvg.svg2png(bytestring=data)
    if not png_bytes:
        raise RuntimeError("svg_to_png_failed")
    return png_bytes, "image/png"


def _download_bytes(url: str, *, headers: dict[str, str] | None = None) -> tuple[bytes, str]:
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(url, headers=headers or {})
    response.raise_for_status()
    content_type = str(response.headers.get("content-type") or "").split(";")[0].strip()
    return response.content, content_type or "application/octet-stream"


def _upload_bytes_to_qiniu(
    data: bytes,
    *,
    content_type: str,
    key_hint: str,
    storage_config: PublicAssetStorageConfig,
) -> tuple[str, str, bool]:
    try:
        from qiniu import Auth, put_data
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("qiniu SDK is not installed; run pip install -r requirements.txt") from exc

    digest = hashlib.sha256(data).hexdigest()[:16]
    ext = mimetypes.guess_extension(content_type) or ".bin"
    safe_hint = re.sub(r"[^A-Za-z0-9._/-]+", "-", str(key_hint or "asset")).strip("-/") or "asset"
    date_prefix = datetime.now(UTC).strftime("%Y/%m/%d")
    prefix = storage_config.qiniu_key_prefix.strip("/")
    object_key = f"{prefix}/{date_prefix}/{safe_hint}-{digest}{ext}" if prefix else f"{date_prefix}/{safe_hint}-{digest}{ext}"

    auth = Auth(storage_config.qiniu_access_key, storage_config.qiniu_secret_key)
    token = auth.upload_token(storage_config.qiniu_bucket, object_key, storage_config.qiniu_upload_token_expires_seconds)
    ret, info = put_data(token, object_key, data, mime_type=content_type or "application/octet-stream")
    if getattr(info, "status_code", 0) not in {200, 614}:
        raise RuntimeError(f"qiniu_upload_failed:{getattr(info, 'status_code', '')}:{getattr(info, 'text_body', '')}")
    if not isinstance(ret, dict) or str(ret.get("key") or object_key) != object_key:
        raise RuntimeError("qiniu_upload_returned_unexpected_key")

    unsigned_url = f"{storage_config.qiniu_public_base_url}/{quote(object_key)}"
    if storage_config.qiniu_bucket_private:
        return auth.private_download_url(unsigned_url, expires=storage_config.qiniu_public_url_ttl_seconds), object_key, True
    return unsigned_url, object_key, False
