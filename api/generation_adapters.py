"""真实生成 provider 适配层。"""

from __future__ import annotations

import uuid
from asyncio import sleep
from datetime import UTC, datetime
from typing import Any

import httpx

from .model_registry import (
    MINIMAX_H3_ASYNC_PROVIDER,
    MOCK_PROVIDER,
    OPENAI_COMPATIBLE_PROVIDER,
    POYO_ASYNC_PROVIDER,
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


def _make_data_uri(image_base64: str) -> str:
    return f"data:image/png;base64,{image_base64}"


def _map_http_error(
    prefix: str,
    exc: Exception,
    *,
    provider_request_payload: dict[str, Any] | None = None,
) -> ModelProfileError:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in {401, 403}:
            return ModelProfileError(f"{prefix}失败：认证未通过，请检查 API Key。", provider_request_payload=provider_request_payload)
        if status == 404:
            return ModelProfileError(f"{prefix}失败：接口地址不存在，请检查 base_url。", provider_request_payload=provider_request_payload)
        if status == 429:
            return ModelProfileError(f"{prefix}失败：上游服务暂时限流（HTTP 429），请稍后重试。", provider_request_payload=provider_request_payload)
        return ModelProfileError(f"{prefix}失败：上游服务返回 HTTP {status}。", provider_request_payload=provider_request_payload)
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


def _extract_reference_urls(reference_images: list[dict[str, Any]] | None) -> list[str]:
    urls: list[str] = []
    for item in reference_images or []:
        if not isinstance(item, dict):
            continue
        image_url = str(item.get("image_url") or item.get("imageUrl") or "").strip()
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
    if has_first_frame and "image_to_video" in task_modes:
        return "image_to_video"
    if has_references and "reference_to_video" in task_modes:
        return "reference_to_video"
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

    external_task_id = str(
        data.get("task_id")
        or data.get("taskId")
        or data.get("data", {}).get("task_id")
        or data.get("data", {}).get("taskId")
        or ""
    ).strip()
    if not external_task_id:
        raise ModelProfileError("PoYo 提交成功但没有返回 task_id。")
    return {
        "externalTaskId": external_task_id,
        "providerResponse": data,
        "providerRequestPayload": payload,
    }


def _coerce_minimax_h3_duration(value: Any) -> int:
    duration = _coerce_int(value, 5)
    return min(max(duration, 4), 15)


def _build_minimax_h3_video_payload(
    profile: dict[str, Any],
    *,
    prompt: str,
    duration_seconds: int | None,
    aspect_ratio: str | None,
    first_frame_url: str | None,
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

    normalized_first_frame_url = str(first_frame_url or "").strip()
    if normalized_first_frame_url:
        payload["content"].append({
            "type": "image_url",
            "image_url": {
                "url": normalized_first_frame_url,
            },
            "role": "first_frame",
        })
    else:
        ratio = str(aspect_ratio or params.get("ratio") or "16:9").strip() or "16:9"
        if ratio == "adaptive":
            ratio = "16:9"
        payload["ratio"] = ratio

    callback_url = str(params.get("callback_url") or params.get("callbackUrl") or "").strip()
    if callback_url:
        payload["callback_url"] = callback_url

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

            if status in {"succeeded", "success", "finished", "completed", "done"}:
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
            if status in {"failed", "error", "cancelled", "canceled"}:
                message = str(data.get("error") or data.get("message") or data.get("detail") or "MiniMax H3 任务失败").strip()
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
    if status in {"succeeded", "success", "finished", "completed", "done"}:
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
    if status in {"failed", "error", "cancelled", "canceled"}:
        message = str(data.get("error") or data.get("message") or data.get("detail") or "MiniMax H3 task failed").strip()
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
        )
        submitted = await submit_minimax_h3_generation(profile, payload=provider_payload)
        polled = await poll_minimax_h3_generation(profile, external_task_id=submitted["externalTaskId"])
        task_mode = "image_to_video" if str(first_frame_url or "").strip() else "text_to_video"
        return {
            **polled,
            "externalTaskId": submitted["externalTaskId"],
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
