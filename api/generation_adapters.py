"""真实生成 provider 适配层。"""

from __future__ import annotations

import base64
import uuid
from asyncio import sleep
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from .model_registry import (
    MINIMAX_H3_75API_PROVIDER,
    MINIMAX_H3_ASYNC_PROVIDER,
    MOCK_PROVIDER,
    OPENAI_COMPATIBLE_PROVIDER,
    POYO_ASYNC_PROVIDER,
    SHAPI_GEMINI_IMAGE_PROVIDER,
    SHAPI_OPENAI_IMAGES_PROVIDER,
    get_default_profile,
    get_profile,
)


class ModelProfileError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        provider_response: dict[str, Any] | None = None,
        provider_request_payload: dict[str, Any] | None = None,
        external_status: str | None = None,
        poll_attempts: int | None = None,
        external_task_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider_response = provider_response
        self.provider_request_payload = provider_request_payload
        self.external_status = external_status
        self.poll_attempts = poll_attempts
        self.external_task_id = external_task_id


def resolve_generation_profile(capability: str, model_profile_id: str | None = None) -> dict[str, Any]:
    profile = get_profile(model_profile_id) if model_profile_id else get_default_profile(capability)
    if not profile:
        raise ModelProfileError(f"{capability} 能力当前没有可用模型配置。")
    if not profile.get("enabled", True):
        raise ModelProfileError(f"模型 {profile.get('name') or profile.get('id') or ''} 当前已被禁用。")
    return profile


def _make_data_uri(image_base64: str, mime_type: str = "image/png") -> str:
    normalized_mime_type = str(mime_type or "image/png").split(";", 1)[0].strip().lower()
    if not normalized_mime_type.startswith("image/"):
        normalized_mime_type = "image/png"
    return f"data:{normalized_mime_type};base64,{image_base64}"


def _map_http_error(
    prefix: str,
    exc: Exception,
    *,
    provider_request_payload: dict[str, Any] | None = None,
) -> ModelProfileError:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        response_text = ""
        response_payload: dict[str, Any] = {}
        try:
            parsed = exc.response.json()
            if isinstance(parsed, dict):
                response_payload = parsed
            else:
                response_payload = {"body": parsed}
        except Exception:
            try:
                response_text = exc.response.text
            except Exception:
                response_text = ""
            if response_text:
                response_payload = {"body": response_text[:2000]}
        message_suffix = ""
        if response_payload:
            detail = (
                response_payload.get("message")
                or response_payload.get("error")
                or response_payload.get("error_msg")
                or response_payload.get("detail")
                or response_payload.get("body")
                or ""
            )
            if detail:
                message_suffix = f"：{str(detail)[:500]}"
        if status in {401, 403}:
            return ModelProfileError(
                f"{prefix}失败：认证未通过，请检查 API Key{message_suffix}。",
                provider_request_payload=provider_request_payload,
                provider_response=response_payload or None,
            )
        if status == 404:
            return ModelProfileError(
                f"{prefix}失败：接口地址不存在，请检查 base_url{message_suffix}。",
                provider_request_payload=provider_request_payload,
                provider_response=response_payload or None,
            )
        if status == 429:
            return ModelProfileError(
                f"{prefix}失败：上游服务暂时限流（HTTP 429），请稍后重试{message_suffix}。",
                provider_request_payload=provider_request_payload,
                provider_response=response_payload or None,
            )
        return ModelProfileError(
            f"{prefix}失败：上游服务返回 HTTP {status}{message_suffix}。",
            provider_request_payload=provider_request_payload,
            provider_response=response_payload or None,
        )
    if isinstance(exc, httpx.ConnectError):
        return ModelProfileError(f"{prefix}失败：无法连接到服务，请检查地址和网络。", provider_request_payload=provider_request_payload)
    if isinstance(exc, httpx.TimeoutException):
        return ModelProfileError(f"{prefix}失败：请求超时。", provider_request_payload=provider_request_payload)
    return ModelProfileError(f"{prefix}失败：{exc}", provider_request_payload=provider_request_payload)


def _read_default_param(profile: dict[str, Any], key: str, fallback: Any = None) -> Any:
    params = profile.get("default_params") or {}
    if isinstance(params, dict) and key in params:
        return params.get(key)
    return fallback


def _coerce_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off", ""}:
        return False
    return False


def _extract_reference_urls(reference_images: list[dict[str, Any]] | None) -> list[str]:
    urls: list[str] = []
    for item in reference_images or []:
        if not isinstance(item, dict):
            continue
        image_url = str(item.get("image_url") or item.get("imageUrl") or item.get("url") or "").strip()
        if image_url:
            urls.append(image_url)
    return urls


def _resolve_video_task_mode(
    profile: dict[str, Any],
    *,
    first_frame_url: str | None,
    reference_images: list[dict[str, Any]] | None,
) -> str | None:
    payload = dict(profile.get("default_params") or {})
    task_modes = payload.get("task_modes")
    if not isinstance(task_modes, list):
        return None

    reference_urls = _extract_reference_urls(reference_images)
    has_first_frame = bool(str(first_frame_url or "").strip())
    has_references = bool(reference_urls)
    if has_references and "reference_to_video" in task_modes:
        return "reference_to_video"
    if has_first_frame and "image_to_video" in task_modes:
        return "image_to_video"
    if "text_to_video" in task_modes:
        return "text_to_video"
    return None


def _extract_poyo_file_url(data: dict[str, Any]) -> str | None:
    candidates: list[Any] = [
        data.get("files"),
        data.get("output", {}).get("files") if isinstance(data.get("output"), dict) else None,
        data.get("data", {}).get("files") if isinstance(data.get("data"), dict) else None,
        data.get("result", {}).get("files") if isinstance(data.get("result"), dict) else None,
        data.get("images"),
        data.get("output", {}).get("images") if isinstance(data.get("output"), dict) else None,
        data.get("data", {}).get("images") if isinstance(data.get("data"), dict) else None,
        data.get("result", {}).get("images") if isinstance(data.get("result"), dict) else None,
        data.get("outputs"),
        data.get("output", {}).get("outputs") if isinstance(data.get("output"), dict) else None,
        data.get("data", {}).get("outputs") if isinstance(data.get("data"), dict) else None,
        data.get("result", {}).get("outputs") if isinstance(data.get("result"), dict) else None,
    ]
    for files in candidates:
        if not isinstance(files, list):
            continue
        for item in files:
            if not isinstance(item, dict):
                continue
            file_url = str(
                item.get("file_url")
                or item.get("url")
                or item.get("fileUrl")
                or item.get("image_url")
                or item.get("imageUrl")
                or item.get("output_url")
                or item.get("outputUrl")
                or ""
            ).strip()
            if file_url:
                return file_url
    for container in (data, data.get("output"), data.get("data"), data.get("result")):
        if not isinstance(container, dict):
            continue
        for key in ("file_url", "url", "preview_url", "previewUrl", "result_url", "resultUrl", "image_url", "imageUrl", "output_url", "outputUrl"):
            value = str(container.get(key) or "").strip()
            if value:
                return value
    return None


def _extract_minimax_h3_file_url(data: dict[str, Any]) -> str | None:
    candidates: list[Any] = [
        data.get("content"),
        data.get("task", {}).get("content") if isinstance(data.get("task"), dict) else None,
        data.get("data", {}).get("content") if isinstance(data.get("data"), dict) else None,
        data.get("result", {}).get("content") if isinstance(data.get("result"), dict) else None,
    ]
    for content in candidates:
        if isinstance(content, dict):
            for key in ("url", "video_url", "videoUrl", "file_url", "fileUrl"):
                value = str(content.get(key) or "").strip()
                if value:
                    return value
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                for key in ("url", "video_url", "videoUrl", "file_url", "fileUrl"):
                    value = str(item.get(key) or "").strip()
                    if value:
                        return value
    for container in (data, data.get("task"), data.get("data"), data.get("result")):
        if not isinstance(container, dict):
            continue
        for key in ("url", "video_url", "videoUrl", "file_url", "fileUrl", "output_url", "outputUrl"):
            value = str(container.get(key) or "").strip()
            if value:
                return value
    return None


def _is_http_status_error(exc: Exception, status_code: int) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == status_code


def _build_poyo_status_rate_limit_error(
    message: str,
    *,
    provider_response: dict[str, Any] | None,
    poll_attempts: int,
    external_task_id: str,
) -> ModelProfileError:
    return ModelProfileError(
        message,
        provider_response=provider_response,
        external_status="rate_limited",
        poll_attempts=poll_attempts,
        external_task_id=external_task_id,
    )


async def submit_poyo_generation(
    profile: dict[str, Any],
    *,
    input_payload: dict[str, Any],
) -> dict[str, Any]:
    api_key = str(profile.get("api_key") or "").strip()
    base_url = str(profile.get("base_url") or "").rstrip("/")
    model_name = str(profile.get("model_name") or "").strip()
    if not api_key:
        raise ModelProfileError("PoYo 模型配置缺少 API Key。")
    if not base_url:
        raise ModelProfileError("PoYo 模型配置缺少 base_url。")
    if not model_name:
        raise ModelProfileError("PoYo 模型配置缺少 model_name。")

    payload = {
        "model": model_name,
        "input": input_payload,
    }

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            response = await client.post(
                f"{base_url}/api/generate/submit",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise _map_http_error("PoYo 提交任务", exc, provider_request_payload=payload) from exc

    nested_data = data.get("data") if isinstance(data.get("data"), dict) else {}
    task = data.get("task") if isinstance(data.get("task"), dict) else {}
    nested_task = nested_data.get("task") if isinstance(nested_data.get("task"), dict) else {}
    external_task_id = str(
        data.get("task_id")
        or data.get("taskId")
        or data.get("id")
        or nested_data.get("task_id")
        or nested_data.get("taskId")
        or nested_data.get("id")
        or task.get("task_id")
        or task.get("taskId")
        or task.get("id")
        or nested_task.get("task_id")
        or nested_task.get("taskId")
        or nested_task.get("id")
        or ""
    ).strip()
    if not external_task_id:
        detail = (
            data.get("message")
            or data.get("error")
            or data.get("error_message")
            or data.get("detail")
            or nested_data.get("message")
            or nested_data.get("error")
            or nested_data.get("error_message")
            or ""
        )
        suffix = f"：{str(detail)[:500]}" if detail else ""
        raise ModelProfileError(
            f"PoYo 提交成功但没有返回 task_id{suffix}",
            provider_response=data,
            provider_request_payload=payload,
            external_status=str(nested_data.get("status") or data.get("status") or "").strip() or None,
        )
    return {
        "externalTaskId": external_task_id,
        "providerResponse": data,
        "providerRequestPayload": payload,
    }


def _coerce_minimax_h3_duration(value: Any) -> int:
    duration = _coerce_int(value, 5)
    return min(max(duration, 4), 15)


def normalize_minimax_h3_duration(value: Any) -> int:
    """Public H3 duration contract for callers that must align prompt and payload."""

    return _coerce_minimax_h3_duration(value)


MINIMAX_H3_SUCCESS_STATUSES = {"succeeded", "success", "finished", "completed", "done"}
MINIMAX_H3_FAILED_STATUSES = {"failed", "fail", "error", "cancelled", "canceled", "expired"}


def _extract_minimax_h3_error_message(data: dict[str, Any], fallback: str) -> str:
    candidates: list[Any] = [
        data.get("error"),
        data.get("message"),
        data.get("detail"),
        data.get("task", {}).get("error") if isinstance(data.get("task"), dict) else None,
        data.get("data", {}).get("error") if isinstance(data.get("data"), dict) else None,
        data.get("result", {}).get("error") if isinstance(data.get("result"), dict) else None,
    ]
    for item in candidates:
        if isinstance(item, dict):
            message = str(item.get("message") or item.get("status_msg") or item.get("detail") or item.get("code") or "").strip()
            if message:
                return message
        else:
            message = str(item or "").strip()
            if message:
                return message
    return fallback


def _build_minimax_h3_video_payload(
    profile: dict[str, Any],
    *,
    prompt: str,
    duration_seconds: int | None,
    aspect_ratio: str | None,
    first_frame_url: str | None,
    reference_images: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_prompt = str(prompt or "").strip()
    if not normalized_prompt:
        raise ModelProfileError("MiniMax H3 视频生成缺少 prompt。")
    if len(normalized_prompt) > 7000:
        raise ModelProfileError("MiniMax H3 prompt 超过 7000 字符限制。")

    params = dict(profile.get("default_params") or {})
    resolution = str(params.get("resolution") or "768P").strip() or "768P"
    if resolution not in {"768P", "2K"}:
        raise ModelProfileError("MiniMax H3 resolution 只能是 768P 或 2K。")

    payload: dict[str, Any] = {
        "model": str(profile.get("model_name") or "MiniMax-H3").strip() or "MiniMax-H3",
        "content": [
            {
                "type": "text",
                "text": normalized_prompt,
            }
        ],
        "resolution": resolution,
        "duration": _coerce_minimax_h3_duration(duration_seconds or params.get("duration") or params.get("duration_seconds")),
    }

    reference_urls = _extract_reference_urls(reference_images)
    configured_max_reference_images = _coerce_int(params.get("max_reference_images"), 9)
    max_reference_images = configured_max_reference_images if configured_max_reference_images > 0 else 9
    normalized_reference_urls = reference_urls[:max_reference_images]
    normalized_first_frame_url = str(first_frame_url or "").strip()
    if normalized_reference_urls and normalized_first_frame_url:
        raise ModelProfileError(
            "MiniMax H3 的多参考图模式与首/尾帧模式互斥；请由连续性策略明确选择一种输入模式。"
        )
    ratio = str(aspect_ratio or params.get("ratio") or "16:9").strip() or "16:9"
    if ratio == "adaptive":
        ratio = "16:9"

    if normalized_reference_urls:
        for reference_url in normalized_reference_urls:
            payload["content"].append({
                "type": "image_url",
                "image_url": {
                    "url": reference_url,
                },
                "role": "reference_image",
            })
        payload["ratio"] = ratio
    elif normalized_first_frame_url:
        payload["content"].append({
            "type": "image_url",
            "image_url": {
                "url": normalized_first_frame_url,
            },
            "role": "first_frame",
        })
    else:
        payload["ratio"] = ratio

    callback_url = str(params.get("callback_url") or params.get("callbackUrl") or "").strip()
    if callback_url:
        payload["callback_url"] = callback_url

    if _coerce_bool(params.get("aigc_watermark", params.get("watermark"))):
        payload["aigc_watermark"] = True

    return payload


async def submit_minimax_h3_generation(
    profile: dict[str, Any],
    *,
    payload: dict[str, Any],
) -> dict[str, Any]:
    api_key = str(profile.get("api_key") or "").strip()
    base_url = str(profile.get("base_url") or "").rstrip("/")
    if not api_key:
        raise ModelProfileError("MiniMax H3 模型配置缺少 API Key。")
    if not base_url:
        raise ModelProfileError("MiniMax H3 模型配置缺少 base_url。")

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            response = await client.post(
                f"{base_url}/v2/video_generation",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise _map_http_error("MiniMax H3 提交任务", exc, provider_request_payload=payload) from exc

    external_task_id = str(
        data.get("task_id")
        or data.get("taskId")
        or data.get("task", {}).get("task_id")
        or data.get("data", {}).get("task_id")
        or ""
    ).strip()
    if not external_task_id:
        raise ModelProfileError("MiniMax H3 提交成功但没有返回 task_id。", provider_request_payload=payload)

    return {
        "externalTaskId": external_task_id,
        "providerResponse": data,
        "providerRequestPayload": payload,
    }


def _normalize_minimax_h3_status(data: dict[str, Any]) -> str:
    return str(
        data.get("status")
        or data.get("task_status")
        or data.get("taskStatus")
        or data.get("task", {}).get("status")
        or data.get("data", {}).get("status")
        or ""
    ).strip().lower()


async def poll_minimax_h3_generation(
    profile: dict[str, Any],
    *,
    external_task_id: str,
) -> dict[str, Any]:
    api_key = str(profile.get("api_key") or "").strip()
    base_url = str(profile.get("base_url") or "").rstrip("/")
    poll_interval = max(_coerce_int(_read_default_param(profile, "poll_interval_seconds", 5), 5), 1)
    poll_timeout = max(_coerce_int(_read_default_param(profile, "poll_timeout_seconds", 900), 900), 10)
    max_attempts = max(1, poll_timeout // poll_interval)

    last_payload: dict[str, Any] = {}
    last_status = "queued"
    async with httpx.AsyncClient(timeout=120) as client:
        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.get(
                    f"{base_url}/v2/query/video_generation/{external_task_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
                data = response.json()
            except Exception as exc:
                if _is_http_status_error(exc, 429):
                    if attempt < max_attempts:
                        await sleep(min(poll_interval * attempt, 8))
                        continue
                raise _map_http_error("MiniMax H3 查询任务状态", exc) from exc

            status = _normalize_minimax_h3_status(data)
            last_payload = data
            last_status = status or last_status

            if status in MINIMAX_H3_SUCCESS_STATUSES:
                file_url = _extract_minimax_h3_file_url(data)
                if not file_url:
                    raise ModelProfileError("MiniMax H3 任务已完成，但结果里缺少可用的视频 URL。", provider_response=data)
                return {
                    "externalStatus": "succeeded",
                    "pollAttempts": attempt,
                    "previewUrl": file_url,
                    "uri": file_url,
                    "providerResponse": data,
                }
            if status in MINIMAX_H3_FAILED_STATUSES:
                message = _extract_minimax_h3_error_message(data, "MiniMax H3 任务失败")
                raise ModelProfileError(
                    message,
                    provider_response=data,
                    external_status=status or "failed",
                    poll_attempts=attempt,
                    external_task_id=external_task_id,
                )
            if attempt < max_attempts:
                await sleep(poll_interval)

    raise ModelProfileError(
        f"MiniMax H3 任务轮询超时，最后状态：{last_status or 'unknown'}",
        provider_response=last_payload or None,
        external_status=last_status or "timeout",
        poll_attempts=max_attempts,
        external_task_id=external_task_id,
    )


async def reconcile_minimax_h3_generation(
    profile: dict[str, Any],
    *,
    external_task_id: str,
) -> dict[str, Any]:
    api_key = str(profile.get("api_key") or "").strip()
    base_url = str(profile.get("base_url") or "").rstrip("/")
    if not api_key:
        raise ModelProfileError("MiniMax H3 configuration is missing an API key.")
    if not base_url:
        raise ModelProfileError("MiniMax H3 configuration is missing a base_url.")

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            response = await client.get(
                f"{base_url}/v2/query/video_generation/{external_task_id}",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise _map_http_error("MiniMax H3 task status check", exc) from exc

    status = _normalize_minimax_h3_status(data)
    if status in MINIMAX_H3_SUCCESS_STATUSES:
        file_url = _extract_minimax_h3_file_url(data)
        if not file_url:
            raise ModelProfileError(
                "MiniMax H3 task completed, but no usable output video URL was returned.",
                provider_response=data,
                external_status=status or "succeeded",
                poll_attempts=1,
                external_task_id=external_task_id,
            )
        return {
            "status": "done",
            "externalStatus": "succeeded",
            "pollAttempts": 1,
            "previewUrl": file_url,
            "uri": file_url,
            "providerResponse": data,
            "externalTaskId": external_task_id,
        }
    if status in MINIMAX_H3_FAILED_STATUSES:
        message = _extract_minimax_h3_error_message(data, "MiniMax H3 task failed")
        raise ModelProfileError(
            message,
            provider_response=data,
            external_status=status or "failed",
            poll_attempts=1,
            external_task_id=external_task_id,
        )
    return {
        "status": "running",
        "externalStatus": status or "queued",
        "pollAttempts": 1,
        "providerResponse": data,
        "externalTaskId": external_task_id,
    }

def _75api_minimax_h3_base_url(profile: dict[str, Any]) -> str:
    """Normalize a 75api profile URL to the host root.

    The UI suggests the host root, but accepting a user-entered ``/v1`` suffix
    avoids producing ``/v1/v1/videos`` in production.
    """

    base_url = str(profile.get("base_url") or "").rstrip("/")
    if base_url.lower().endswith("/v1"):
        base_url = base_url[:-3].rstrip("/")
    return base_url


def _coerce_75api_minimax_h3_seconds(value: Any) -> int:
    seconds = _coerce_int(value, 0)
    if seconds < 5 or seconds > 15:
        raise ModelProfileError("75api MiniMax H3 的 seconds 必须是 5–15 秒；请延长镜头或先拆镜。")
    return seconds


def normalize_75api_minimax_h3_seconds(value: Any) -> int:
    """Validate, rather than silently coerce, the 75api H3 duration contract."""

    return _coerce_75api_minimax_h3_seconds(value)


def _build_75api_minimax_h3_video_payload(
    profile: dict[str, Any],
    *,
    prompt: str,
    duration_seconds: int | None,
    aspect_ratio: str | None,
    first_frame_url: str | None,
    reference_images: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_prompt = str(prompt or "").strip()
    if not normalized_prompt:
        raise ModelProfileError("75api MiniMax H3 视频生成缺少 prompt。")

    params = dict(profile.get("default_params") or {})
    raw_resolution = str(params.get("resolution") or "768p").strip()
    resolution = {"480P": "480p", "768P": "768p", "480p": "480p", "768p": "768p"}.get(raw_resolution)
    if not resolution:
        raise ModelProfileError("75api MiniMax H3 resolution 只能是 480p 或 768p。")

    ratio = str(aspect_ratio or params.get("aspect_ratio") or params.get("ratio") or "16:9").strip() or "16:9"
    if ratio == "adaptive":
        ratio = "16:9"
    if ratio not in {"16:9", "9:16"}:
        raise ModelProfileError("75api MiniMax H3 aspect_ratio 只能是 16:9 或 9:16。")

    reference_urls = _extract_reference_urls(reference_images)
    normalized_first_frame_url = str(first_frame_url or "").strip()
    if reference_urls and normalized_first_frame_url:
        raise ModelProfileError("75api MiniMax H3 的多参考图模式与首帧模式互斥。")
    if not reference_urls and not normalized_first_frame_url:
        raise ModelProfileError("75api MiniMax H3 不支持文生视频，必须提供首帧图或至少一张参考图。")

    configured_limit = _coerce_int(params.get("max_reference_images"), 8)
    if configured_limit <= 0 or configured_limit > 8:
        raise ModelProfileError("75api MiniMax H3 的 max_reference_images 必须在 1–8 之间。")
    image_urls = reference_urls or [normalized_first_frame_url]
    if len(image_urls) > configured_limit:
        raise ModelProfileError(
            f"75api MiniMax H3 最多支持 {configured_limit} 张参考图，当前收到 {len(image_urls)} 张；系统不会静默丢弃参考图。"
        )

    seconds = _coerce_75api_minimax_h3_seconds(
        duration_seconds if duration_seconds is not None else params.get("seconds") or params.get("duration_seconds") or 5
    )
    model_name = str(profile.get("model_name") or "minimax_h3_no_audios").strip() or "minimax_h3_no_audios"
    if model_name != "minimax_h3_no_audios":
        raise ModelProfileError("75api MiniMax H3 provider 只支持模型 minimax_h3_no_audios。")
    return {
        "model": model_name,
        "prompt": normalized_prompt,
        "seconds": str(seconds),
        "aspect_ratio": ratio,
        "resolution": resolution,
        "images": image_urls,
    }


def _extract_75api_minimax_h3_video_url(data: dict[str, Any]) -> str | None:
    candidates: list[Any] = [
        data.get("video_url"),
        data.get("videoUrl"),
        data.get("url"),
        data.get("content"),
        data.get("output"),
        data.get("data", {}).get("video_url") if isinstance(data.get("data"), dict) else None,
        data.get("data", {}).get("videoUrl") if isinstance(data.get("data"), dict) else None,
        data.get("data", {}).get("url") if isinstance(data.get("data"), dict) else None,
        data.get("data", {}).get("output") if isinstance(data.get("data"), dict) else None,
        data.get("result", {}).get("video_url") if isinstance(data.get("result"), dict) else None,
        data.get("result", {}).get("url") if isinstance(data.get("result"), dict) else None,
        data.get("result", {}).get("output") if isinstance(data.get("result"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            for key in ("video_url", "videoUrl", "url", "file_url", "fileUrl"):
                value = str(candidate.get(key) or "").strip()
                if value:
                    return value
        elif isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _normalize_75api_minimax_h3_status(data: dict[str, Any]) -> str:
    nested_data = data.get("data") if isinstance(data.get("data"), dict) else {}
    task = data.get("task") if isinstance(data.get("task"), dict) else {}
    return str(data.get("status") or data.get("task_status") or data.get("taskStatus") or task.get("status") or nested_data.get("status") or "").strip().lower()


def _extract_75api_minimax_h3_task_id(data: dict[str, Any]) -> str:
    nested_data = data.get("data") if isinstance(data.get("data"), dict) else {}
    task = data.get("task") if isinstance(data.get("task"), dict) else {}
    return str(
        data.get("task_id")
        or data.get("taskId")
        or data.get("id")
        or nested_data.get("task_id")
        or nested_data.get("taskId")
        or nested_data.get("id")
        or task.get("task_id")
        or task.get("taskId")
        or task.get("id")
        or ""
    ).strip()


async def submit_75api_minimax_h3_generation(
    profile: dict[str, Any],
    *,
    payload: dict[str, Any],
) -> dict[str, Any]:
    api_key = str(profile.get("api_key") or "").strip()
    base_url = _75api_minimax_h3_base_url(profile)
    if not api_key:
        raise ModelProfileError("75api MiniMax H3 模型配置缺少 API Key。")
    if not base_url:
        raise ModelProfileError("75api MiniMax H3 模型配置缺少 base_url。")

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            response = await client.post(
                f"{base_url}/v1/videos",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise _map_http_error("75api MiniMax H3 提交任务", exc, provider_request_payload=payload) from exc

    external_task_id = _extract_75api_minimax_h3_task_id(data)
    if not external_task_id:
        raise ModelProfileError(
            "75api MiniMax H3 提交成功但没有返回 task_id/id。",
            provider_response=data,
            provider_request_payload=payload,
        )
    return {
        "externalTaskId": external_task_id,
        "providerTaskId": str(data.get("task_id") or data.get("id") or external_task_id),
        "providerResponse": data,
        "providerRequestPayload": payload,
    }


def _75api_minimax_h3_content_url(profile: dict[str, Any], external_task_id: str) -> str:
    return f"{_75api_minimax_h3_base_url(profile)}/v1/videos/{external_task_id}/content"


def _normalize_75api_minimax_h3_video_url(profile: dict[str, Any], url: str) -> str:
    normalized = str(url or "").strip()
    if normalized.startswith("/"):
        return f"{_75api_minimax_h3_base_url(profile)}{normalized}"
    return normalized


async def poll_75api_minimax_h3_generation(
    profile: dict[str, Any],
    *,
    external_task_id: str,
) -> dict[str, Any]:
    api_key = str(profile.get("api_key") or "").strip()
    base_url = _75api_minimax_h3_base_url(profile)
    poll_interval = max(_coerce_int(_read_default_param(profile, "poll_interval_seconds", 5), 5), 1)
    poll_timeout = max(_coerce_int(_read_default_param(profile, "poll_timeout_seconds", 900), 900), 10)
    max_attempts = max(1, poll_timeout // poll_interval)
    last_payload: dict[str, Any] = {}
    last_status = "queued"
    async with httpx.AsyncClient(timeout=120) as client:
        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.get(
                    f"{base_url}/v1/videos/{external_task_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
                data = response.json()
            except Exception as exc:
                if _is_http_status_error(exc, 429) and attempt < max_attempts:
                    await sleep(min(poll_interval * attempt, 8))
                    continue
                raise _map_http_error("75api MiniMax H3 查询任务状态", exc) from exc

            status = _normalize_75api_minimax_h3_status(data)
            last_payload = data
            last_status = status or last_status
            if status in {"completed", "succeeded", "success", "finished", "done"}:
                file_url = _normalize_75api_minimax_h3_video_url(
                    profile,
                    _extract_75api_minimax_h3_video_url(data) or _75api_minimax_h3_content_url(profile, external_task_id),
                )
                return {
                    "externalStatus": "succeeded",
                    "pollAttempts": attempt,
                    "previewUrl": file_url,
                    "uri": file_url,
                    "providerResponse": data,
                    "providerContentRequiresAuth": file_url == _75api_minimax_h3_content_url(profile, external_task_id),
                }
            if status in {"failed", "fail", "error", "cancelled", "canceled", "expired"}:
                message = _extract_minimax_h3_error_message(data, "75api MiniMax H3 任务失败")
                raise ModelProfileError(message, provider_response=data, external_status=status or "failed", poll_attempts=attempt, external_task_id=external_task_id)
            if attempt < max_attempts:
                await sleep(poll_interval)

    raise ModelProfileError(
        f"75api MiniMax H3 任务轮询超时，最后状态：{last_status or 'unknown'}",
        provider_response=last_payload or None,
        external_status=last_status or "timeout",
        poll_attempts=max_attempts,
        external_task_id=external_task_id,
    )


async def reconcile_75api_minimax_h3_generation(
    profile: dict[str, Any],
    *,
    external_task_id: str,
) -> dict[str, Any]:
    api_key = str(profile.get("api_key") or "").strip()
    base_url = _75api_minimax_h3_base_url(profile)
    if not api_key or not base_url:
        raise ModelProfileError("75api MiniMax H3 配置缺少 API Key 或 base_url。")
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            response = await client.get(
                f"{base_url}/v1/videos/{external_task_id}",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise _map_http_error("75api MiniMax H3 查询任务状态", exc) from exc
    status = _normalize_75api_minimax_h3_status(data)
    if status in {"completed", "succeeded", "success", "finished", "done"}:
        file_url = _normalize_75api_minimax_h3_video_url(
            profile,
            _extract_75api_minimax_h3_video_url(data) or _75api_minimax_h3_content_url(profile, external_task_id),
        )
        return {
            "status": "done",
            "externalStatus": "succeeded",
            "pollAttempts": 1,
            "previewUrl": file_url,
            "uri": file_url,
            "providerResponse": data,
            "externalTaskId": external_task_id,
            "providerContentRequiresAuth": file_url == _75api_minimax_h3_content_url(profile, external_task_id),
        }
    if status in {"failed", "fail", "error", "cancelled", "canceled", "expired"}:
        message = _extract_minimax_h3_error_message(data, "75api MiniMax H3 任务失败")
        raise ModelProfileError(message, provider_response=data, external_status=status or "failed", poll_attempts=1, external_task_id=external_task_id)
    return {
        "status": "running",
        "externalStatus": status or "processing",
        "pollAttempts": 1,
        "providerResponse": data,
        "externalTaskId": external_task_id,
    }


async def poll_poyo_generation(
    profile: dict[str, Any],
    *,
    external_task_id: str,
) -> dict[str, Any]:
    api_key = str(profile.get("api_key") or "").strip()
    base_url = str(profile.get("base_url") or "").rstrip("/")
    poll_interval = max(_coerce_int(_read_default_param(profile, "poll_interval_seconds", 3), 3), 1)
    poll_timeout = max(_coerce_int(_read_default_param(profile, "poll_timeout_seconds", 180), 180), 10)
    max_attempts = max(1, poll_timeout // poll_interval)

    last_payload: dict[str, Any] = {}
    last_status = "queued"
    async with httpx.AsyncClient(timeout=120) as client:
        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.get(
                    f"{base_url}/api/generate/status/{external_task_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
                data = response.json()
            except Exception as exc:
                if _is_http_status_error(exc, 429):
                    if attempt < max_attempts:
                        await sleep(min(poll_interval * attempt, 8))
                        continue
                    raise _build_poyo_status_rate_limit_error(
                        "PoYo 查询任务状态时遇到限流（HTTP 429），任务可能仍在 provider 侧继续执行。请稍后重试或继续拉取结果。",
                        provider_response=None,
                        poll_attempts=attempt,
                        external_task_id=external_task_id,
                    ) from exc
                raise _map_http_error("PoYo 查询任务状态", exc) from exc

            status = str(
                data.get("status")
                or data.get("task_status")
                or data.get("taskStatus")
                or data.get("data", {}).get("status")
                or ""
            ).strip().lower()
            last_payload = data
            last_status = status or last_status

            if status in {"finished", "succeeded", "success", "completed", "done"}:
                file_url = _extract_poyo_file_url(data)
                if not file_url:
                    raise ModelProfileError("PoYo 任务已完成，但结果里缺少可用的文件地址。")
                return {
                    "externalStatus": "finished",
                    "pollAttempts": attempt,
                    "previewUrl": file_url,
                    "uri": file_url,
                    "providerResponse": data,
                }
            if status in {"failed", "error", "cancelled", "canceled"}:
                message = str(data.get("error") or data.get("message") or data.get("detail") or "PoYo 任务失败").strip()
                raise ModelProfileError(
                    message,
                    provider_response=data,
                    external_status=status or "failed",
                    poll_attempts=attempt,
                    external_task_id=external_task_id,
                )
            if attempt < max_attempts:
                await sleep(poll_interval)

    raise ModelProfileError(
        f"PoYo 任务轮询超时，最后状态：{last_status or 'unknown'}",
        provider_response=last_payload or None,
        external_status=last_status or "timeout",
        poll_attempts=max_attempts,
        external_task_id=external_task_id,
    )


async def reconcile_poyo_generation(
    profile: dict[str, Any],
    *,
    external_task_id: str,
) -> dict[str, Any]:
    api_key = str(profile.get("api_key") or "").strip()
    base_url = str(profile.get("base_url") or "").rstrip("/")
    if not api_key:
        raise ModelProfileError("PoYo configuration is missing an API key.")
    if not base_url:
        raise ModelProfileError("PoYo configuration is missing a base_url.")

    data: dict[str, Any] | None = None
    async with httpx.AsyncClient(timeout=120) as client:
        for attempt in range(1, 4):
            try:
                response = await client.get(
                    f"{base_url}/api/generate/status/{external_task_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
                data = response.json()
                break
            except Exception as exc:
                if _is_http_status_error(exc, 429):
                    if attempt < 3:
                        await sleep(attempt)
                        continue
                    raise _build_poyo_status_rate_limit_error(
                        "PoYo 查询任务状态时遇到限流（HTTP 429），任务可能仍在 provider 侧继续执行。请稍后重试或继续拉取结果。",
                        provider_response=None,
                        poll_attempts=attempt,
                        external_task_id=external_task_id,
                    ) from exc
                raise _map_http_error("PoYo task status check", exc) from exc

    if not isinstance(data, dict):
        raise _build_poyo_status_rate_limit_error(
            "PoYo 查询任务状态失败，当前还拿不到最终结果。请稍后重试或继续拉取结果。",
            provider_response=None,
            poll_attempts=3,
            external_task_id=external_task_id,
        )

    status = str(
        data.get("status")
        or data.get("task_status")
        or data.get("taskStatus")
        or data.get("data", {}).get("status")
        or ""
    ).strip().lower()

    if status in {"finished", "succeeded", "success", "completed", "done"}:
        file_url = _extract_poyo_file_url(data)
        if not file_url:
            raise ModelProfileError(
                "PoYo task completed, but no usable output file URL was returned.",
                provider_response=data,
                external_status=status or "finished",
                poll_attempts=1,
                external_task_id=external_task_id,
            )
        return {
            "status": "done",
            "externalStatus": "finished",
            "pollAttempts": 1,
            "previewUrl": file_url,
            "uri": file_url,
            "providerResponse": data,
            "externalTaskId": external_task_id,
        }

    if status in {"failed", "error", "cancelled", "canceled"}:
        message = str(data.get("error") or data.get("message") or data.get("detail") or "PoYo task failed").strip()
        raise ModelProfileError(
            message,
            provider_response=data,
            external_status=status or "failed",
            poll_attempts=1,
            external_task_id=external_task_id,
        )

    return {
        "status": "running",
        "externalStatus": status or "queued",
        "pollAttempts": 1,
        "providerResponse": data,
        "externalTaskId": external_task_id,
    }


def _build_poyo_image_input(
    profile: dict[str, Any],
    *,
    prompt: str,
    aspect_ratio: str | None,
    negative_prompt: str | None,
    reference_images: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    payload = dict(profile.get("default_params") or {})
    payload["prompt"] = prompt
    if aspect_ratio:
        normalized_model = str(profile.get("model_name") or "").strip().lower()
        normalized_ratio = str(aspect_ratio or "").strip()
        if normalized_model == "gpt-image-2":
            payload.setdefault("size", normalized_ratio)
            if normalized_ratio and normalized_ratio != "auto":
                payload.setdefault("resolution", "2K")
        else:
            payload.setdefault("aspect_ratio", normalized_ratio)
    if negative_prompt:
        payload.setdefault("negative_prompt", negative_prompt)
    reference_urls = _extract_reference_urls(reference_images)
    if reference_urls:
        if bool(payload.get("supports_reference_images")):
            payload["reference_image_urls"] = reference_urls[: max(_coerce_int(payload.get("max_reference_images"), len(reference_urls)), 1)]
        else:
            payload["image_urls"] = reference_urls
    task_modes = payload.get("task_modes")
    if isinstance(task_modes, list):
        if reference_urls and "image_to_image" in task_modes:
            payload.setdefault("task_mode", "image_to_image")
        elif "text_to_image" in task_modes:
            payload.setdefault("task_mode", "text_to_image")
    return payload


def _build_poyo_video_input(
    profile: dict[str, Any],
    *,
    prompt: str,
    duration_seconds: int | None,
    negative_prompt: str | None,
    aspect_ratio: str | None,
    first_frame_url: str | None,
    reference_images: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    payload = dict(profile.get("default_params") or {})
    payload["prompt"] = prompt
    if duration_seconds:
        payload["duration"] = duration_seconds
    if negative_prompt:
        payload.setdefault("negative_prompt", negative_prompt)
    if aspect_ratio:
        payload.setdefault("aspect_ratio", aspect_ratio)
    normalized_first_frame_url = str(first_frame_url or "").strip()
    if normalized_first_frame_url and bool(payload.get("supports_first_frame")):
        payload.setdefault("first_frame", normalized_first_frame_url)
    reference_urls = _extract_reference_urls(reference_images)
    if reference_urls:
        if bool(payload.get("supports_reference_images")):
            payload["reference_image_urls"] = reference_urls[: max(_coerce_int(payload.get("max_reference_images"), len(reference_urls)), 1)]
        else:
            payload.setdefault("image_urls", reference_urls)
    resolved_task_mode = _resolve_video_task_mode(
        profile,
        first_frame_url=normalized_first_frame_url,
        reference_images=reference_images,
    )
    if resolved_task_mode:
        payload.setdefault("task_mode", resolved_task_mode)
    return payload


def _require_image_provider_config(profile: dict[str, Any], provider_label: str) -> tuple[str, str, str]:
    api_key = str(profile.get("api_key") or "").strip()
    base_url = str(profile.get("base_url") or "").rstrip("/")
    model_name = str(profile.get("model_name") or "").strip()
    if not api_key:
        raise ModelProfileError(f"{provider_label} 图片模型配置缺少 API Key。")
    if not base_url:
        raise ModelProfileError(f"{provider_label} 图片模型配置缺少 base_url。")
    if not model_name:
        raise ModelProfileError(f"{provider_label} 图片模型配置缺少 model_name。")
    return api_key, base_url, model_name


def _append_negative_constraints(prompt: str, negative_prompt: str | None) -> str:
    normalized_prompt = str(prompt or "").strip()
    normalized_negative = str(negative_prompt or "").strip()
    if not normalized_negative:
        return normalized_prompt
    return f"{normalized_prompt}\n\nNegative constraints (must not appear): {normalized_negative}".strip()


def _coerce_positive_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def _build_shapi_openai_images_payload(
    profile: dict[str, Any],
    *,
    prompt: str,
    aspect_ratio: str | None,
    negative_prompt: str | None,
    reference_images: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    reference_urls = _extract_reference_urls(reference_images)
    if reference_urls:
        raise ModelProfileError(
            "SHAPI GPT Image 2 的多参考图编辑接口尚未通过账户级契约验证，已拒绝忽略参考图的请求。"
        )

    params = dict(profile.get("default_params") or {})
    payload: dict[str, Any] = {
        "model": str(profile.get("model_name") or "").strip(),
        "prompt": _append_negative_constraints(prompt, negative_prompt),
        # One image per production task keeps result-to-asset provenance unambiguous.
        "n": 1,
    }
    for key in ("size", "quality", "background", "moderation", "style", "user", "response_format"):
        value = params.get(key)
        if value is not None and value != "":
            payload[key] = value

    normalized_ratio = str(aspect_ratio or "").strip()
    size_by_aspect_ratio = params.get("size_by_aspect_ratio")
    if normalized_ratio and normalized_ratio != "auto" and isinstance(size_by_aspect_ratio, dict):
        mapped_size = size_by_aspect_ratio.get(normalized_ratio)
        if isinstance(mapped_size, str) and mapped_size.strip():
            payload["size"] = mapped_size.strip()
    return payload


def _decode_image_data_uri(value: str, *, max_bytes: int) -> tuple[bytes, str]:
    header, separator, raw_payload = value.partition(",")
    if not separator or not header.lower().startswith("data:image/") or ";base64" not in header.lower():
        raise ModelProfileError("SHAPI Gemini 参考图必须是 HTTPS 图片地址或有效的 base64 图片 data URI。")
    mime_type = header[5:].split(";", 1)[0].strip().lower()
    try:
        data = base64.b64decode(raw_payload, validate=True)
    except Exception as exc:
        raise ModelProfileError("SHAPI Gemini 参考图 data URI 不是有效的 base64 图片。") from exc
    if not data or len(data) > max_bytes:
        raise ModelProfileError(f"SHAPI Gemini 单张参考图必须介于 1 字节与 {max_bytes // (1024 * 1024)}MB 之间。")
    return data, mime_type


async def _load_shapi_gemini_reference_part(
    client: httpx.AsyncClient,
    source_url: str,
    *,
    max_bytes: int,
) -> dict[str, Any]:
    if source_url.startswith("data:"):
        data, mime_type = _decode_image_data_uri(source_url, max_bytes=max_bytes)
        return {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(data).decode("ascii")}}

    parsed = urlparse(source_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ModelProfileError("SHAPI Gemini 仅接受 HTTPS 公网参考图；请先将本地资产回收至对象存储。")

    try:
        async with client.stream("GET", source_url, follow_redirects=False) as response:
            response.raise_for_status()
            mime_type = str(response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
            if not mime_type.startswith("image/"):
                raise ModelProfileError("SHAPI Gemini 参考图地址未返回图片 Content-Type。")
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > max_bytes:
                    raise ModelProfileError(f"SHAPI Gemini 单张参考图不能超过 {max_bytes // (1024 * 1024)}MB。")
    except ModelProfileError:
        raise
    except Exception as exc:
        raise _map_http_error("下载 SHAPI Gemini 参考图", exc) from exc

    if not data:
        raise ModelProfileError("SHAPI Gemini 参考图为空。")
    return {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(bytes(data)).decode("ascii")}}


def _redact_shapi_gemini_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist request intent without storing large source-image bytes in task metadata."""

    redacted = {**payload}
    contents = payload.get("contents")
    if not isinstance(contents, list):
        return redacted
    safe_contents: list[dict[str, Any]] = []
    for content in contents:
        if not isinstance(content, dict):
            continue
        safe_parts: list[dict[str, Any]] = []
        for part in content.get("parts") or []:
            if not isinstance(part, dict):
                continue
            inline_data = part.get("inlineData")
            if isinstance(inline_data, dict):
                raw_data = str(inline_data.get("data") or "")
                safe_parts.append(
                    {
                        "inlineData": {
                            "mimeType": str(inline_data.get("mimeType") or ""),
                            "data": f"<redacted base64: {len(raw_data)} chars>",
                        }
                    }
                )
            else:
                safe_parts.append(dict(part))
        safe_contents.append({**content, "parts": safe_parts})
    redacted["contents"] = safe_contents
    return redacted


def _redact_shapi_gemini_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep response provenance without retaining provider image bytes.

    Gemini returns its generated image in ``inlineData``.  The image itself is
    immediately materialized into ``previewUrl`` and then persisted by the
    creative-task layer; copying the same Base64 into task/asset metadata makes
    every status request unnecessarily huge and duplicates user media.
    """
    def redact(value: Any) -> Any:
        if isinstance(value, list):
            return [redact(item) for item in value]
        if not isinstance(value, dict):
            return value
        safe = {key: redact(item) for key, item in value.items()}
        inline_data = safe.get("inlineData")
        if isinstance(inline_data, dict) and "data" in inline_data:
            raw_data = str(inline_data.get("data") or "")
            safe["inlineData"] = {
                **inline_data,
                "data": f"<redacted base64: {len(raw_data)} chars>",
            }
        inline_data_snake = safe.get("inline_data")
        if isinstance(inline_data_snake, dict) and "data" in inline_data_snake:
            raw_data = str(inline_data_snake.get("data") or "")
            safe["inline_data"] = {
                **inline_data_snake,
                "data": f"<redacted base64: {len(raw_data)} chars>",
            }
        # Gemini may attach a thought signature to an image output part.  It is
        # transport-only state and can be as large as the image itself.
        for key in ("thoughtSignature", "thought_signature"):
            raw_signature = safe.get(key)
            if isinstance(raw_signature, str) and raw_signature:
                safe[key] = f"<redacted thought signature: {len(raw_signature)} chars>"
        return safe

    return redact(payload) if isinstance(payload, dict) else {}


def _build_shapi_gemini_reference_instruction(reference: dict[str, Any], index: int) -> str:
    """Describe a bound reference's contract next to its inline image bytes."""
    def compact(value: Any, fallback: str = "") -> str:
        text = " ".join(str(value or "").split()).strip()
        return (text or fallback)[:160]

    name = compact(
        reference.get("reference_name")
        or reference.get("referenceName")
        or reference.get("asset_name")
        or reference.get("assetName")
        or reference.get("reference_token")
        or reference.get("referenceToken"),
        f"参考资产 {index}",
    )
    role = compact(reference.get("role") or reference.get("reference_role") or reference.get("referenceRole"), "visual")
    purpose = compact(reference.get("reference_purpose") or reference.get("referencePurpose"), "visual consistency")
    return (
        f"参考图 {index}：{name}。角色/用途：{role}，{purpose}。"
        "该图是已确认的视觉事实：必须继承其人物身份、脸型、发型、服装、材质或场景布局；"
        "不得用提示词中的泛化描述覆盖它，也不得新增冲突设定。"
    )


async def _generate_shapi_gemini_image(
    profile: dict[str, Any],
    *,
    prompt: str,
    aspect_ratio: str | None,
    negative_prompt: str | None,
    reference_images: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    api_key, base_url, model_name = _require_image_provider_config(profile, "SHAPI Gemini")
    if base_url.endswith("/v1"):
        base_url = base_url[: -len("/v1")]
    if base_url.endswith("/v1beta"):
        base_url = base_url[: -len("/v1beta")]

    params = dict(profile.get("default_params") or {})
    max_references = _coerce_positive_int(params.get("max_reference_images"), 14, minimum=1, maximum=14)
    max_reference_bytes = _coerce_positive_int(
        params.get("max_reference_image_bytes"), 10 * 1024 * 1024, minimum=1 * 1024 * 1024, maximum=20 * 1024 * 1024
    )
    normalized_references = [
        item for item in (reference_images or [])
        if isinstance(item, dict) and str(item.get("image_url") or item.get("imageUrl") or item.get("url") or "").strip()
    ][:max_references]
    parts: list[dict[str, Any]] = [{"text": _append_negative_constraints(prompt, negative_prompt)}]

    async with httpx.AsyncClient(timeout=120) as client:
        for index, reference in enumerate(normalized_references, start=1):
            reference_url = str(reference.get("image_url") or reference.get("imageUrl") or reference.get("url") or "").strip()
            parts.append({"text": _build_shapi_gemini_reference_instruction(reference, index)})
            parts.append(await _load_shapi_gemini_reference_part(client, reference_url, max_bytes=max_reference_bytes))

        generation_config: dict[str, Any] = {"responseModalities": ["IMAGE"]}
        image_config: dict[str, Any] = {}
        normalized_ratio = str(aspect_ratio or params.get("aspect_ratio") or "").strip()
        if normalized_ratio and normalized_ratio != "auto":
            image_config["aspectRatio"] = normalized_ratio
        image_size = str(params.get("image_size") or "").strip()
        if image_size:
            image_config["imageSize"] = image_size
        if image_config:
            generation_config["imageConfig"] = image_config

        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": generation_config,
        }
        audit_payload = _redact_shapi_gemini_request_payload(payload)
        try:
            response = await client.post(
                f"{base_url}/v1beta/models/{model_name}:generateContent",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # pragma: no cover - covered by public callers/tests
            raise _map_http_error("SHAPI Gemini 图片生成", exc, provider_request_payload=audit_payload) from exc

    for candidate in data.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        for part in content.get("parts") or []:
            if not isinstance(part, dict):
                continue
            inline_data = part.get("inlineData") or part.get("inline_data")
            if not isinstance(inline_data, dict):
                continue
            image_base64 = str(inline_data.get("data") or "").strip()
            if image_base64:
                mime_type = str(inline_data.get("mimeType") or inline_data.get("mime_type") or "image/png")
                preview_url = _make_data_uri(image_base64, mime_type)
                return {
                    "previewUrl": preview_url,
                    "uri": preview_url,
                    "providerResponse": _redact_shapi_gemini_response(data),
                    "providerRequestPayload": audit_payload,
                }
    raise ModelProfileError(
        "SHAPI Gemini 图片模型未返回 inlineData 图片。",
        provider_response=data if isinstance(data, dict) else {},
        provider_request_payload=audit_payload,
    )


async def _generate_shapi_openai_image(
    profile: dict[str, Any],
    *,
    prompt: str,
    aspect_ratio: str | None,
    negative_prompt: str | None,
    reference_images: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    api_key, base_url, _model_name = _require_image_provider_config(profile, "SHAPI OpenAI")
    payload = _build_shapi_openai_images_payload(
        profile,
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        negative_prompt=negative_prompt,
        reference_images=reference_images,
    )
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            response = await client.post(
                f"{base_url}/images/generations",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # pragma: no cover - covered by public callers/tests
            raise _map_http_error("SHAPI OpenAI 图片生成", exc, provider_request_payload=payload) from exc

    items = data.get("data") or []
    if not items or not isinstance(items[0], dict):
        raise ModelProfileError("SHAPI OpenAI 图片模型没有返回可用图片数据。", provider_response=data, provider_request_payload=payload)
    image_item = items[0]
    preview_url = image_item.get("url")
    if not preview_url and image_item.get("b64_json"):
        preview_url = _make_data_uri(str(image_item["b64_json"]), str(image_item.get("mime_type") or "image/png"))
    if not preview_url:
        raise ModelProfileError("SHAPI OpenAI 图片响应缺少 url 或 b64_json。", provider_response=data, provider_request_payload=payload)
    return {
        "previewUrl": preview_url,
        "uri": preview_url,
        "revisedPrompt": image_item.get("revised_prompt"),
        "providerResponse": data,
        "providerRequestPayload": payload,
    }


async def generate_image_asset(
    profile: dict[str, Any],
    *,
    prompt: str,
    aspect_ratio: str | None,
    negative_prompt: str | None = None,
    reference_images: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if profile.get("provider") == MOCK_PROVIDER:
        raise ModelProfileError("Mock provider 应由原型任务适配器处理。")
    if profile.get("provider") == POYO_ASYNC_PROVIDER:
        submitted = await submit_poyo_generation(
            profile,
            input_payload=_build_poyo_image_input(
                profile,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                negative_prompt=negative_prompt,
                reference_images=reference_images,
            ),
        )
        polled = await poll_poyo_generation(profile, external_task_id=submitted["externalTaskId"])
        return {
            **polled,
            "externalTaskId": submitted["externalTaskId"],
            "providerResponse": polled.get("providerResponse") or submitted.get("providerResponse"),
            "providerRequestPayload": submitted.get("providerRequestPayload") or {},
        }
    if profile.get("provider") == SHAPI_GEMINI_IMAGE_PROVIDER:
        return await _generate_shapi_gemini_image(
            profile,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            negative_prompt=negative_prompt,
            reference_images=reference_images,
        )
    if profile.get("provider") == SHAPI_OPENAI_IMAGES_PROVIDER:
        return await _generate_shapi_openai_image(
            profile,
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            negative_prompt=negative_prompt,
            reference_images=reference_images,
        )
    if profile.get("provider") != OPENAI_COMPATIBLE_PROVIDER:
        raise ModelProfileError(f"暂不支持的图片 provider：{profile.get('provider')}")

    api_key = str(profile.get("api_key") or "").strip()
    base_url = str(profile.get("base_url") or "").rstrip("/")
    model_name = str(profile.get("model_name") or "").strip()

    if not api_key:
        raise ModelProfileError("图片模型配置缺少 API Key。")
    if not base_url:
        raise ModelProfileError("图片模型配置缺少 base_url。")
    if not model_name:
        raise ModelProfileError("图片模型配置缺少 model_name。")

    payload: dict[str, Any] = {
        "model": model_name,
        "prompt": prompt,
        "n": 1,
    }
    payload.update(profile.get("default_params") or {})
    payload["model"] = model_name
    payload["prompt"] = prompt
    if aspect_ratio:
        payload.setdefault("aspect_ratio", aspect_ratio)
    if negative_prompt:
        payload.setdefault("negative_prompt", negative_prompt)

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            response = await client.post(
                f"{base_url}/images/generations",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # pragma: no cover - covered by public callers/tests
            raise _map_http_error("图片生成", exc) from exc

    items = data.get("data") or []
    if not items:
        raise ModelProfileError("图片 provider 没有返回可用图片数据。")

    image_item = items[0]
    preview_url = image_item.get("url")
    if not preview_url and image_item.get("b64_json"):
        preview_url = _make_data_uri(image_item["b64_json"])
    if not preview_url:
        raise ModelProfileError("图片 provider 返回结果里缺少 url 或 b64_json。")

    return {
        "previewUrl": preview_url,
        "uri": preview_url,
        "revisedPrompt": image_item.get("revised_prompt"),
        "providerResponse": data,
    }


async def generate_video_asset(
    profile: dict[str, Any],
    *,
    prompt: str,
    duration_seconds: int | None,
    negative_prompt: str | None = None,
    aspect_ratio: str | None = None,
    first_frame_url: str | None = None,
    reference_images: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if profile.get("provider") == MOCK_PROVIDER:
        raise ModelProfileError("Mock provider 应由原型任务适配器处理。")
    if profile.get("provider") == POYO_ASYNC_PROVIDER:
        submitted = await submit_poyo_generation(
            profile,
            input_payload=_build_poyo_video_input(
                profile,
                prompt=prompt,
                duration_seconds=duration_seconds,
                negative_prompt=negative_prompt,
                aspect_ratio=aspect_ratio,
                first_frame_url=first_frame_url,
                reference_images=reference_images,
            ),
        )
        task_mode = _resolve_video_task_mode(
            profile,
            first_frame_url=first_frame_url,
            reference_images=reference_images,
        )
        polled = await poll_poyo_generation(profile, external_task_id=submitted["externalTaskId"])
        return {
            **polled,
            "externalTaskId": submitted["externalTaskId"],
            "providerResponse": polled.get("providerResponse") or submitted.get("providerResponse"),
            "providerRequestPayload": submitted.get("providerRequestPayload") or {},
            "taskMode": task_mode or "",
        }
    if profile.get("provider") == MINIMAX_H3_ASYNC_PROVIDER:
        provider_payload = _build_minimax_h3_video_payload(
            profile,
            prompt=prompt,
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
            first_frame_url=first_frame_url,
            reference_images=reference_images,
        )
        submitted = await submit_minimax_h3_generation(profile, payload=provider_payload)
        polled = await poll_minimax_h3_generation(profile, external_task_id=submitted["externalTaskId"])
        task_mode = "reference_to_video" if _extract_reference_urls(reference_images) else "image_to_video" if str(first_frame_url or "").strip() else "text_to_video"
        return {
            **polled,
            "externalTaskId": submitted["externalTaskId"],
            "providerResponse": polled.get("providerResponse") or submitted.get("providerResponse"),
            "providerRequestPayload": submitted.get("providerRequestPayload") or {},
            "taskMode": task_mode,
        }
    if profile.get("provider") == MINIMAX_H3_75API_PROVIDER:
        provider_payload = _build_75api_minimax_h3_video_payload(
            profile,
            prompt=prompt,
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
            first_frame_url=first_frame_url,
            reference_images=reference_images,
        )
        submitted = await submit_75api_minimax_h3_generation(profile, payload=provider_payload)
        polled = await poll_75api_minimax_h3_generation(profile, external_task_id=submitted["externalTaskId"])
        task_mode = "reference_to_video" if _extract_reference_urls(reference_images) else "image_to_video"
        return {
            **polled,
            "externalTaskId": submitted["externalTaskId"],
            "providerTaskId": submitted.get("providerTaskId") or submitted["externalTaskId"],
            "providerResponse": polled.get("providerResponse") or submitted.get("providerResponse"),
            "providerRequestPayload": submitted.get("providerRequestPayload") or {},
            "taskMode": task_mode,
        }
    if profile.get("provider") != OPENAI_COMPATIBLE_PROVIDER:
        raise ModelProfileError(f"暂不支持的视频 provider：{profile.get('provider')}")

    raise ModelProfileError("真实视频 provider 仍未接入当前工作台，请继续使用 Mock 视频模型。")


def build_task_adapter_asset(
    *,
    kind: str,
    title: str,
    prompt: str,
    model_name: str,
    source_asset_id: str | None,
    asset_scope: str,
    asset_subject: str,
    aspect_ratio: str,
    duration_seconds: int,
    reference_asset_ids: list[str],
    reference_images: list[dict[str, Any]],
    shot_id: str,
    source_node_id: str | None,
    model_profile_id: str | None,
    provider: str,
    source: str,
    preview_url: str,
    first_frame_asset_id: str | None = None,
    first_frame_url: str | None = None,
    provider_task_mode: str | None = None,
) -> dict[str, Any]:
    asset_kind = "image" if kind == "reference-image" else kind
    asset_id = f"{asset_kind}-{uuid.uuid4().hex[:10]}"
    image_role = "reference" if kind == "reference-image" else "storyboard" if asset_kind == "image" else None
    created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return {
        "id": asset_id,
        "kind": asset_kind,
        "title": title,
        "label": "",
        "uri": preview_url,
        "previewUrl": preview_url,
        "prompt": prompt,
        "model": model_name,
        "status": "done",
        "adopted": True,
        "sourceAssetId": source_asset_id,
        "elapsedSeconds": 2,
        "metadata": {
            "source": source,
            "assetScope": asset_scope,
            "assetSubject": asset_subject,
            "aspectRatio": aspect_ratio,
            "durationSeconds": duration_seconds,
            "provider": provider,
            "referenceAssetCount": len(reference_asset_ids),
            "referenceAssetIds": reference_asset_ids,
            "referenceImages": reference_images,
            "shotId": shot_id,
            "sourceNodeId": source_node_id or "",
            "sourceAssetId": source_asset_id or "",
            "firstFrameAssetId": first_frame_asset_id or "",
            "firstFrameUrl": first_frame_url or "",
            "modelProfileId": model_profile_id or "",
            "modelName": model_name,
            "providerTaskMode": provider_task_mode or "",
            "imageRole": image_role,
            "usesMock": provider == "prototype-task-adapter",
            "prompt": prompt,
            "createdAt": created_at,
        },
    }
