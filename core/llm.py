"""LLM client with rate limiting, retry, and quota tracking."""
import json
import time
import threading
import logging
import httpx

logger = logging.getLogger(__name__)
import config

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


# ── LLM Call ─────────────────────────────────────────────────

def call_llm(prompt, system=None, temperature=None, max_tokens=None,
             retries=3, estimated_tokens=8000, model_profile=None):
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
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system or SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature if temperature is not None else default_params.get("temperature", config.LLM_TEMPERATURE),
        "max_tokens": resolved_max_tokens,
    }

    for attempt in range(retries):
        _limiter.wait_if_needed(estimated_tokens)

        try:
            with httpx.Client(timeout=600) as client:
                resp = client.post(
                    f"{base_url}/chat/completions",
                    headers=headers, json=payload,
                )

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 2 ** (attempt + 2)))
                    logger.warning("[throttle] 429, retry after %ss", retry_after)
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

                return content

        except httpx.HTTPStatusError as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** (attempt + 1))
        except (httpx.ConnectError, httpx.ReadTimeout) as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** (attempt + 1))

    return ""


import re


def call_llm_json(prompt, system=None, model_profile=None, **kwargs):
    """Call LLM and parse JSON response."""
    raw = call_llm(prompt, system=system, model_profile=model_profile, **kwargs)
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            fragment = text[start:end]
            # 尝试修复常见 JSON 问题
            fixed = fragment
            # 1) 修复无引号的 key (JS-like JSON)
            fixed = re.sub(r'(?<=[\{,\[])\s*([a-zA-Z_][a-zA-Z_0-9]*)\s*:', r'"\1":', fixed)
            # 2) 如果末尾有未闭合的字符串（value 被截断），移除最外层的最后一个占位
            # 查找最外层的最后一个 key:value 对，如果 value 引号未闭合则删除
            if fixed.count('"') % 2 != 0:
                # 奇数个引号，尝试闭合
                last_open = fixed.rfind('"')
                # 去掉未闭合的部分
                last_close = fixed[last_open+1:].find('"')
                if last_close == -1:
                    # 没有后续闭合引号，截断
                    fixed = fixed[:last_open] + '"'
            try:
                return json.loads(fixed)
            except json.JSONDecodeError as e:
                # 3) 尝试修复末尾截断 ","... 模式
                if fixed.endswith(',"'):
                    fixed = fixed[:-2] + '}'
                elif fixed.endswith(','):
                    fixed = fixed[:-1] + '}'
                try:
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    raise ValueError(f"Failed to parse LLM JSON response:\n{fragment[:500]}")
        raise ValueError(f"Failed to parse LLM JSON response:\n{text[:500]}")
