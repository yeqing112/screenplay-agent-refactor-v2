"""Safe, explicit response contracts for the 75API GPT-image transport."""

from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit


# These paths are deliberately small and explicit.  The first path is the
# shape documented by the 75API Feishu integration guide; the latter two are
# OpenAI-compatible shapes used by the existing adapter contract.
API75_IMAGE_RESPONSE_PATHS = {
    "documented": ("url",),
    "openai_compatible": ("data[].url", "data[].b64_json"),
}

_MEDIA_KEYS = {"url", "b64_json", "base64"}
_SECRET_KEYS = {"api_key", "apikey", "authorization", "token", "access_token", "secret"}
_BASE64_RE = re.compile(r"^[A-Za-z0-9+/\r\n]+={0,2}$")


@dataclass(frozen=True)
class ImageProviderResult:
    preview_url: str = ""
    image_base64: str = ""
    mime_type: str = "image/png"
    provider_request_id: str = ""
    revised_prompt: str = ""
    source_path: str = ""
    result_classification: str = "VALID_IMAGE_RESPONSE"
    provider_response_shape: dict[str, Any] | None = None
    provider_response_fingerprint: str = ""
    provider_http_status: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha(value: Any) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _looks_like_base64(value: str) -> bool:
    compact = "".join(str(value).split())
    if len(compact) < 16 or len(compact) % 4 not in {0, 2, 3} or not _BASE64_RE.fullmatch(compact):
        return False
    try:
        decoded = base64.b64decode(compact + "=" * ((4 - len(compact) % 4) % 4), validate=True)
    except Exception:
        return False
    return len(decoded) >= 8


def _mime_from_bytes(decoded: bytes) -> str:
    if decoded.startswith(b"\x89PNG"):
        return "image/png"
    if decoded.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if decoded.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if decoded.startswith(b"RIFF") and decoded[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _media_descriptor(value: str) -> dict[str, Any]:
    raw = str(value or "")
    if raw.startswith("data:") and ";base64," in raw:
        header, encoded = raw.split(",", 1)
        mime = header[5:].split(";", 1)[0] or "image/png"
        compact = "".join(encoded.split())
        return {"type": "base64", "length": len(compact), "sha256": _sha(compact), "mime_type": mime}
    if _looks_like_base64(raw):
        compact = "".join(raw.split())
        try:
            decoded = base64.b64decode(compact + "=" * ((4 - len(compact) % 4) % 4), validate=True)
            mime = _mime_from_bytes(decoded)
        except Exception:
            mime = "image/png"
        return {"type": "base64", "length": len(compact), "sha256": _sha(compact), "mime_type": mime}
    parts = urlsplit(raw)
    if parts.scheme in {"http", "https"} and parts.netloc:
        safe_path = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        return {"type": f"{parts.scheme}_url", "scheme": parts.scheme, "host": parts.netloc, "path_sha256": _sha(safe_path), "has_query": bool(parts.query)}
    return {"type": "string", "length": len(raw), "sha256": _sha(raw)}


def _shape_value(value: Any, path: str, *, string_meta: dict[str, Any], nested_keys: dict[str, list[str]], list_lengths: dict[str, int]) -> str:
    if isinstance(value, dict):
        nested_keys[path] = sorted(str(key) for key in value.keys() if str(key).lower() not in _SECRET_KEYS)
        return "dict"
    if isinstance(value, list):
        list_lengths[path] = len(value)
        return "list"
    if isinstance(value, str):
        string_meta[path] = _media_descriptor(value) if path.rsplit(".", 1)[-1] in _MEDIA_KEYS or value.startswith(("http://", "https://", "data:")) or _looks_like_base64(value) else {"type": "string", "length": len(value), "sha256": _sha(value)}
        return "string"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


class API75ImageResponseInspector:
    """Produce a safe structural summary without persisting media or secrets."""

    @classmethod
    def inspect(cls, response: Any, *, http_status: int | None = None) -> dict[str, Any]:
        if not isinstance(response, dict):
            return {"response_type": type(response).__name__, "top_level_keys": [], "field_shapes": {}, "nested_keys": {}, "list_lengths": {}, "candidate_media_paths": [], "string_length_metadata": {}, "provider_http_status": http_status}
        field_shapes: dict[str, str] = {}
        nested_keys: dict[str, list[str]] = {}
        list_lengths: dict[str, int] = {}
        string_meta: dict[str, Any] = {}
        for key, value in response.items():
            if str(key).lower() in _SECRET_KEYS:
                continue
            path = str(key)
            field_shapes[path] = _shape_value(value, path, string_meta=string_meta, nested_keys=nested_keys, list_lengths=list_lengths)
            if isinstance(value, list):
                for index, item in enumerate(value[:8]):
                    item_path = f"{path}[{index}]"
                    field_shapes[item_path] = _shape_value(item, item_path, string_meta=string_meta, nested_keys=nested_keys, list_lengths=list_lengths)
                    if isinstance(item, dict):
                        for child_key, child_value in item.items():
                            child_path = f"{item_path}.{child_key}"
                            field_shapes[child_path] = _shape_value(child_value, child_path, string_meta=string_meta, nested_keys=nested_keys, list_lengths=list_lengths)
        candidates: list[str] = []
        if isinstance(response.get("url"), str):
            candidates.append("url")
        if isinstance(response.get("b64_json"), str):
            candidates.append("b64_json")
        data = response.get("data")
        if isinstance(data, list):
            for index, item in enumerate(data[:8]):
                if isinstance(item, dict):
                    if isinstance(item.get("url"), str):
                        candidates.append(f"data[{index}].url")
                    if isinstance(item.get("b64_json"), str):
                        candidates.append(f"data[{index}].b64_json")
        return {"response_type": "dict", "top_level_keys": sorted(str(key) for key in response.keys() if str(key).lower() not in _SECRET_KEYS), "field_shapes": field_shapes, "nested_keys": nested_keys, "list_lengths": list_lengths, "candidate_media_paths": candidates, "string_length_metadata": string_meta, "provider_http_status": http_status}


def _redacted_for_fingerprint(value: Any, path: str = "") -> Any:
    if isinstance(value, dict):
        return {str(key): _redacted_for_fingerprint(child, f"{path}.{key}" if path else str(key)) for key, child in sorted(value.items(), key=lambda item: str(item[0])) if str(key).lower() not in _SECRET_KEYS}
    if isinstance(value, list):
        return [_redacted_for_fingerprint(child, f"{path}[{index}]") for index, child in enumerate(value[:8])]
    if isinstance(value, str):
        if path.rsplit(".", 1)[-1].split("[", 1)[0] in _MEDIA_KEYS or value.startswith(("http://", "https://", "data:")) or _looks_like_base64(value):
            return _media_descriptor(value)
        return value if len(value) <= 500 else {"type": "string", "length": len(value), "sha256": _sha(value)}
    return value


def response_fingerprint(response: Any) -> str:
    canonical = json.dumps(_redacted_for_fingerprint(response), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def safe_provider_response(response: Any, *, http_status: int | None = None) -> dict[str, Any]:
    """Return durable evidence with media and credentials removed."""
    shape = API75ImageResponseInspector.inspect(response, http_status=http_status)
    return {
        "provider_response_shape": shape,
        "provider_response_fingerprint": response_fingerprint(response),
        "provider_http_status": http_status,
        "redacted_response": _redacted_for_fingerprint(response),
    }


def _logical_error(response: Mapping[str, Any]) -> tuple[bool, str]:
    error = response.get("error")
    code = response.get("error_code") or response.get("code")
    status = str(response.get("status") or response.get("state") or "").lower()
    if error or (code is not None and str(code).lower() not in {"0", "200", "success", "ok"}) or status in {"failed", "error"}:
        message = error if isinstance(error, str) else (error.get("message") if isinstance(error, dict) else "")
        return True, str(message or response.get("message") or code or status or "provider logical error")[:500]
    return False, ""


def _decode_media(value: str) -> tuple[str, str, str]:
    raw = str(value or "")
    if raw.startswith("data:") and ";base64," in raw:
        header, encoded = raw.split(",", 1)
        mime = header[5:].split(";", 1)[0] or "image/png"
        return "", "".join(encoded.split()), mime
    if _looks_like_base64(raw):
        compact = "".join(raw.split())
        decoded = base64.b64decode(compact + "=" * ((4 - len(compact) % 4) % 4), validate=True)
        return "", compact, _mime_from_bytes(decoded)
    return raw, "", "image/png"


def extract_75api_image_result(response: Any, *, http_status: int | None = 200) -> ImageProviderResult:
    """Extract only documented/allowlisted media locations."""
    shape = API75ImageResponseInspector.inspect(response, http_status=http_status)
    fingerprint = response_fingerprint(response)
    if not isinstance(response, dict):
        raise ValueError("75API_IMAGE_RESPONSE_SCHEMA_UNKNOWN")
    logical, message = _logical_error(response)
    if logical:
        raise ValueError(f"PROVIDER_LOGICAL_ERROR:{message}")

    candidates: list[tuple[str, Any]] = []
    if isinstance(response.get("url"), str):
        candidates.append(("url", response["url"]))
    if isinstance(response.get("b64_json"), str):
        candidates.append(("b64_json", response["b64_json"]))
    data = response.get("data")
    if isinstance(data, list):
        for index, item in enumerate(data[:8]):
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("url"), str):
                candidates.append((f"data[{index}].url", item["url"]))
            if isinstance(item.get("b64_json"), str):
                candidates.append((f"data[{index}].b64_json", item["b64_json"]))
    for path, value in candidates:
        preview_url, image_base64, mime = _decode_media(value)
        if preview_url or image_base64:
            item = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else response
            request_id = str(response.get("id") or response.get("request_id") or response.get("requestId") or "").strip()
            return ImageProviderResult(preview_url=preview_url, image_base64=image_base64, mime_type=mime, provider_request_id=request_id, revised_prompt=str(item.get("revised_prompt") or item.get("revisedPrompt") or ""), source_path=path, result_classification="VALID_IMAGE_RESPONSE", provider_response_shape=shape, provider_response_fingerprint=fingerprint, provider_http_status=http_status)

    if any(key in response for key in ("data", "status", "state")):
        raise ValueError("75API_IMAGE_RESPONSE_MEDIA_MISSING")
    raise ValueError("75API_IMAGE_RESPONSE_SCHEMA_UNKNOWN")


globals()["75API_IMAGE_RESPONSE_PATHS"] = API75_IMAGE_RESPONSE_PATHS

__all__ = ["API75_IMAGE_RESPONSE_PATHS", "API75ImageResponseInspector", "ImageProviderResult", "extract_75api_image_result", "response_fingerprint", "safe_provider_response"]
