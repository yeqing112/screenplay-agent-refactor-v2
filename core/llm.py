"""LLM client with rate limiting, retry, and quota tracking."""
import json
import hashlib
import time
import threading
import logging
import httpx
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import urlparse

logger = logging.getLogger(__name__)
import config
from core.prompt_cache import cache_metrics, prompt_fingerprint

SYSTEM_PROMPT = '你是一个专业的编剧助手。请严格按照要求的JSON格式输出，不要添加额外解释。\n\n输出格式要求：\n```json\n{\n  "summary": "章节摘要",\n  "characters": [{"name": "姓名", "aliases": ["别名"], "personality": "性格特征", "relationships": {"与其他人物关系": "描述"}}],\n  "events": [{"seq": 1, "description": "事件描述", "importance": "high/medium/low", "characters_involved": ["涉及人物"]}],\n  "scenes": [{"location": "地点", "time": "时间", "mood": "氛围", "description": "场景描述"}],\n  "foreshadowing": ["伏笔1", "伏笔2"]\n}\n```'


# ── Rate Limiter ──────────────────────────────────────────────

class RateLimiter:
    """Token-bucket + daily quota rate limiter. Thread-safe."""

    def __init__(self, rpm=10, tpm=200_000, daily_limit=0, min_interval=1.0):
        self.rpm = rpm
        self.tpm = tpm
        self.daily_limit = daily_limit
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._request_times = []
        self._token_buffer = []
        self._daily_tokens = 0
        self._daily_date = ""
        self._last_call = 0.0

    def _clean_window(self):
        now = time.time()
        cutoff = now - 60
        self._request_times = [t for t in self._request_times if t > cutoff]
        self._token_buffer = [(t, tok) for t, tok in self._token_buffer if t > cutoff]

    def _check_daily(self):
        today = time.strftime("%Y-%m-%d")
        if today != self._daily_date:
            self._daily_date = today
            self._daily_tokens = 0

    def wait_if_needed(self, estimated_tokens=2000):
        """Block until a request slot is available."""
        with self._lock:
            self._clean_window()
            self._check_daily()

            if self.daily_limit > 0 and self._daily_tokens + estimated_tokens > self.daily_limit:
                raise QuotaExceeded(
                    f"Daily quota exhausted: {self._daily_tokens}/{self.daily_limit}"
                )

            while len(self._request_times) >= self.rpm:
                elapsed = time.time() - self._request_times[0]
                if elapsed < 60:
                    time.sleep(60 - elapsed + 0.1)
                self._clean_window()

            current_tpm = sum(tok for _, tok in self._token_buffer)
            while current_tpm + estimated_tokens > self.tpm:
                time.sleep(1)
                self._clean_window()
                current_tpm = sum(tok for _, tok in self._token_buffer)

            elapsed = time.time() - self._last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)

    def record(self, tokens_used):
        with self._lock:
            now = time.time()
            self._request_times.append(now)
            self._token_buffer.append((now, tokens_used))
            self._daily_tokens += tokens_used
            self._last_call = now

    def stats(self):
        with self._lock:
            self._clean_window()
            self._check_daily()
            return {
                "rpm_used": len(self._request_times),
                "rpm_limit": self.rpm,
                "tpm_used": sum(tok for _, tok in self._token_buffer),
                "tpm_limit": self.tpm,
                "daily_tokens": self._daily_tokens,
                "daily_limit": self.daily_limit or "unlimited",
            }


class QuotaExceeded(Exception):
    pass


# ── Global Rate Limiter ──────────────────────────────────────

_limiter = RateLimiter(
    rpm=int(__import__("os").getenv("LLM_RPM", "10")),
    tpm=int(__import__("os").getenv("LLM_TPM", "200000")),
    daily_limit=int(__import__("os").getenv("LLM_DAILY_LIMIT", "0")),
    min_interval=float(__import__("os").getenv("LLM_MIN_INTERVAL", "1.0")),
)


# Optional per-request audit context.  Existing callers do not need to pass a
# callback; pilot/integration code can scope a call and receive the same safe
# audit envelope without changing provider-facing payloads.
_llm_audit_context: ContextVar[dict] = ContextVar("llm_audit_context", default={})


@contextmanager
def llm_audit_context(**metadata):
    """Attach bounded, non-secret metadata to LLM audit records."""

    token = _llm_audit_context.set(dict(metadata))
    try:
        yield
    finally:
        _llm_audit_context.reset(token)


def _dispatch_audit_record(record: dict, explicit_callback=None) -> None:
    """Send one record to both the legacy callback and scoped pilot sink."""

    context = _llm_audit_context.get() or {}
    sink = context.get("sink") if callable(context.get("sink")) else None
    if context:
        safe_context = {
            key: value for key, value in context.items()
            if key != "sink" and isinstance(key, str) and key
            and (isinstance(value, (str, int, float, bool)) or value is None)
        }
        if safe_context:
            merged = dict(record)
            existing = merged.get("extra") if isinstance(merged.get("extra"), dict) else {}
            merged["extra"] = {**existing, **safe_context}
            record = merged
    for callback in (explicit_callback, sink):
        if not callable(callback):
            continue
        try:
            callback(record)
        except Exception:  # pragma: no cover - audit must never break a call
            logger.warning("LLM audit callback raised; suppressed")


def get_limiter():
    return _limiter


def _resolve_llm_profile(model_profile=None):
    if model_profile:
        return dict(model_profile)

    try:
        from api.model_registry import get_default_profile

        profile = get_default_profile("llm")
        if profile:
            return dict(profile)
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Resolve default llm profile failed, fallback to env: %s", exc)

    return {}


def _normalize_max_tokens(value):
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return config.LLM_MAX_TOKENS
    if resolved <= 0:
        return config.LLM_MAX_TOKENS
    safe_upper_bound = 393216
    if resolved > safe_upper_bound:
        logger.warning("Configured max_tokens=%s exceeds safe upper bound %s, clamping request.", resolved, safe_upper_bound)
        return safe_upper_bound
    return resolved


def _normalize_thinking_param(value):
    if isinstance(value, dict):
        thinking_type = value.get("type")
        if thinking_type in {"enabled", "disabled"}:
            return {"type": thinking_type}
        return value if value else None
    if value in {"enabled", "disabled"}:
        return {"type": value}
    if isinstance(value, bool):
        return {"type": "enabled" if value else "disabled"}
    return None


# ── LLM Call ─────────────────────────────────────────────────

def _audit_safe_hash(value: str) -> str:
    """Stable, non-secret fingerprint for an arbitrary string payload.

    Callers must never feed API keys, bearer tokens, or other credentials
    into this helper.  The output is the first 32 hex characters of SHA-256.
    """
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()[:32]


def _audit_vendor_host(value: str) -> str:
    """Return only the hostname portion of a provider URL for audit logs."""
    parsed = urlparse(str(value or ""))
    # ``netloc`` may contain user-info; use ``hostname`` so an accidentally
    # embedded credential can never enter an audit row.
    return str(parsed.hostname or parsed.path or "")[:200]


def _build_audit_record(
    *,
    system,
    user,
    vendor_model,
    vendor_host,
    profile_id,
    status,
    response_text,
    parse_ok,
    repair_request=None,
    extra=None,
    usage=None,
    latency_ms=None,
) -> dict:
    system_str = system or ""
    user_str = user or ""
    response_str = response_text or ""
    repair_dict = repair_request if isinstance(repair_request, dict) else {}
    has_repair = bool(repair_dict)
    record = {
        "vendor_model": str(vendor_model or "")[:120],
        "vendor_host": _audit_vendor_host(vendor_host),
        "profile_id": str(profile_id or "")[:120],
        "system_prompt_sha256": _audit_safe_hash(system_str),
        "system_prompt_length": len(system_str),
        "user_prompt_sha256": _audit_safe_hash(user_str),
        "user_prompt_length": len(user_str),
        "request_messages_sha256": _audit_safe_hash(system_str + "\n--boundary--\n" + user_str),
        "request_fingerprint": prompt_fingerprint(system_str, user_str),
        "has_repair_request": has_repair,
        "repair_request_sha256": _audit_safe_hash(json.dumps(repair_dict, ensure_ascii=False, sort_keys=True, default=str)) if has_repair else "",
        "repair_request_length": len(json.dumps(repair_dict, ensure_ascii=False, default=str)) if has_repair else 0,
        "response_sha256": _audit_safe_hash(response_str),
        "response_length": len(response_str),
        "http_status": int(status or 0),
        "parse_ok": bool(parse_ok),
    }
    metrics = cache_metrics(usage)
    record["usage"] = metrics
    if latency_ms is not None:
        try:
            record["latency_ms"] = round(float(latency_ms), 2)
        except (TypeError, ValueError):
            pass
    if isinstance(extra, dict) and extra:
        safe_extra = {}
        for key, value in extra.items():
            if not isinstance(key, str) or not key:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe_extra[key[:64]] = value if not isinstance(value, str) else value[:200]
        if safe_extra:
            record["extra"] = safe_extra
    return record


def call_llm(prompt, system=None, temperature=None, max_tokens=None,
             retries=3, estimated_tokens=8000, model_profile=None,
             response_format=None, audit_callback=None, audit_extra=None,
             audit_repair_request=None, image_data_urls=None):
    """Call LLM with rate limiting and retry. Returns raw response text.

    For reasoning models (like mimo-v2.5), completion_tokens include
    reasoning_tokens. We set max_tokens high enough and use actual usage
    for rate tracking.
    """
    profile = _resolve_llm_profile(model_profile)
    api_key = profile.get("api_key") or config.OPENAI_API_KEY
    base_url = str(profile.get("base_url") or config.OPENAI_BASE_URL).rstrip("/")
    model_name = profile.get("model_name") or config.LLM_MODEL
    default_params = profile.get("default_params") if isinstance(profile.get("default_params"), dict) else {}
    headers = {"Authorization": f"Bearer {api_key}"}
    resolved_max_tokens = _normalize_max_tokens(
        max_tokens if max_tokens is not None else default_params.get("max_tokens", config.LLM_MAX_TOKENS)
    )
    user_content = prompt
    if image_data_urls:
        user_content = [{"type": "text", "text": str(prompt)}]
        for image_url in image_data_urls:
            if isinstance(image_url, str) and image_url.startswith("data:image/"):
                user_content.append({"type": "image_url", "image_url": {"url": image_url}})
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system or SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature if temperature is not None else default_params.get("temperature", config.LLM_TEMPERATURE),
        "max_tokens": resolved_max_tokens,
    }
    resolved_response_format = response_format or default_params.get("response_format")
    if isinstance(resolved_response_format, dict) and resolved_response_format:
        payload["response_format"] = resolved_response_format
    resolved_thinking = _normalize_thinking_param(default_params.get("thinking"))
    if resolved_thinking:
        payload["thinking"] = resolved_thinking

    # Historical callers pass ``retries`` as the total-attempt budget.  Guard
    # the boundary so ``0`` means one non-retrying call rather than silently
    # returning an empty string without contacting the configured provider.
    # That distinction is essential for auditable, explicitly confirmed LLM
    # operations: an empty response must mean a real provider response, not a
    # control-flow omission.
    attempt_budget = max(1, int(retries or 0))
    for attempt in range(attempt_budget):
        _limiter.wait_if_needed(estimated_tokens)
        audit_http_status = 0
        audit_response_text = ""
        audit_parse_ok = False
        request_started = time.monotonic()

        try:
            with httpx.Client(timeout=600) as client:
                resp = client.post(
                    f"{base_url}/chat/completions",
                    headers=headers, json=payload,
                )
                audit_http_status = int(getattr(resp, "status_code", 0) or 0)
                # Keep audit payloads bounded even for provider-side HTML/error
                # pages.  The actual response is never persisted, only its hash
                # and length are recorded by the callback.
                audit_response_text = str(getattr(resp, "text", "") or "")[:2000]

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 2 ** (attempt + 2)))
                    logger.warning("[throttle] 429, retry after %ss", retry_after)
                    _dispatch_audit_record(_build_audit_record(
                        system=system, user=prompt,
                        vendor_model=model_name, vendor_host=base_url,
                        profile_id=str(profile.get("id") or ""),
                        status=audit_http_status, response_text=audit_response_text,
                        parse_ok=False, repair_request=audit_repair_request,
                        extra=audit_extra,
                        latency_ms=(time.monotonic() - request_started) * 1000,
                    ), audit_callback)
                    time.sleep(retry_after)
                    continue

                resp.raise_for_status()
                data = resp.json()
                usage = data.get("usage", {})
                total_tokens = usage.get("total_tokens", estimated_tokens)
                _limiter.record(total_tokens)

                msg = data["choices"][0]["message"]
                content = msg.get("content", "")

                # Reasoning models may put answer in content after reasoning
                # If content is empty but reasoning_content exists, use reasoning
                if not content and msg.get("reasoning_content"):
                    content = msg["reasoning_content"]

                audit_parse_ok = bool(content)
                audit_response_text = str(content or "")
                _dispatch_audit_record(_build_audit_record(
                    system=system, user=prompt,
                    vendor_model=model_name, vendor_host=base_url,
                    profile_id=str(profile.get("id") or ""),
                    status=audit_http_status, response_text=audit_response_text,
                    parse_ok=audit_parse_ok,
                    repair_request=audit_repair_request, extra=audit_extra,
                    usage=usage,
                    latency_ms=(time.monotonic() - request_started) * 1000,
                ), audit_callback)
                return content

        except httpx.HTTPStatusError as e:
            if attempt == attempt_budget - 1:
                err_resp = getattr(e, "response", None)
                err_status = int(getattr(err_resp, "status_code", 0) or 0)
                err_text = str(getattr(err_resp, "text", "") or "")[:2000]
                _dispatch_audit_record(_build_audit_record(
                    system=system, user=prompt,
                    vendor_model=model_name, vendor_host=base_url,
                    profile_id=str(profile.get("id") or ""),
                    status=err_status, response_text=err_text,
                    parse_ok=False, repair_request=audit_repair_request,
                    extra=audit_extra,
                    latency_ms=(time.monotonic() - request_started) * 1000,
                ), audit_callback)
            if attempt == attempt_budget - 1:
                raise
            time.sleep(2 ** (attempt + 1))
        except (httpx.ConnectError, httpx.ReadTimeout) as e:
            if attempt == attempt_budget - 1:
                _dispatch_audit_record(_build_audit_record(
                    system=system, user=prompt,
                    vendor_model=model_name, vendor_host=base_url,
                    profile_id=str(profile.get("id") or ""),
                    status=0, response_text=str(e)[:400],
                    parse_ok=False, repair_request=audit_repair_request,
                    extra=audit_extra,
                    latency_ms=(time.monotonic() - request_started) * 1000,
                ), audit_callback)
            if attempt == attempt_budget - 1:
                raise
            time.sleep(2 ** (attempt + 1))

    return ""


import os
import re

from core.structured_output import parse_json_object


def _repair_common_json_text(text: str) -> str:
    fixed = str(text or "")
    fixed = re.sub(r'(?<=[\{,\[])\s*([a-zA-Z_][a-zA-Z_0-9]*)\s*:', r'"\1":', fixed)
    fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
    return fixed


def _json_retry_prompt(prompt: str, error: Exception) -> str:
    return (
        f"{prompt}\n\n"
        "上一轮输出无法被系统解析为 JSON。请重新输出一个完整、合法、可直接 json.loads 的 JSON object。"
        "不要使用 Markdown 代码块，不要解释，不要省略字段，不要在 JSON 前后添加任何文本。"
        f"解析错误摘要：{str(error)[:240]}"
    )


def call_llm_json(
    prompt,
    system=None,
    model_profile=None,
    required_keys: set[str] | None = None,
    json_parse_retries: int = 1,
    audit_callback=None,
    audit_extra=None,
    audit_repair_request=None,
    **kwargs,
):
    """Call LLM and parse a JSON object response with parser-level retries."""

    parse_attempts = max(1, int(json_parse_retries or 0) + 1)
    active_prompt = prompt
    last_error: Exception | None = None
    for attempt in range(parse_attempts):
        call_kwargs = dict(kwargs)
        if os.environ.get("LLM_JSON_RESPONSE_FORMAT") == "1" and "response_format" not in call_kwargs:
            call_kwargs["response_format"] = {"type": "json_object"}
        raw = call_llm(active_prompt, system=system, model_profile=model_profile,
                       audit_callback=audit_callback, audit_extra=audit_extra,
                       audit_repair_request=audit_repair_request, **call_kwargs)
        text = _repair_common_json_text(str(raw or "").strip())
        try:
            return parse_json_object(
                text,
                label="LLM JSON response",
                required_keys=required_keys,
            )
        except ValueError as exc:
            last_error = exc
            if attempt >= parse_attempts - 1:
                break
            active_prompt = _json_retry_prompt(str(prompt), exc)
            logger.warning("LLM JSON parse failed, retrying parse-call once: %s", exc)
    raise ValueError(f"Failed to parse LLM JSON response:\n{str(last_error)[:500]}")
