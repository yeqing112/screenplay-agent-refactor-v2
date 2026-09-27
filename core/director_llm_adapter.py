"""Provider-neutral Director LLM adapter runtime.

Adapters return untrusted JSON only.  They never receive a SQLAlchemy session
and never write production objects.  The API layer validates the result,
adds lineage, and persists a review-required DirectorReasoning draft.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
import hashlib
import json
from typing import Any, Callable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from core.director_reasoning import (
    DirectorReasoningCompileError,
    DirectorReasoningPayload,
    director_reason,
    validate_reasoning_for_compile,
)


DIRECTOR_CONTEXT_SCHEMA_VERSION = "director_context_v1"
DIRECTOR_LLM_ADAPTER_SCHEMA_VERSION = "director_llm_adapter_runtime_v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def content_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return deepcopy(dict(value))
    if hasattr(value, "__dict__"):
        return {key: deepcopy(item) for key, item in vars(value).items() if not key.startswith("_")}
    return {}


def _records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    return [payload for item in value if (payload := _mapping(item))]


class DirectorContext(BaseModel):
    """Immutable-by-convention, provider-safe production context snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = DIRECTOR_CONTEXT_SCHEMA_VERSION
    episode: dict[str, Any] = Field(default_factory=dict)
    script_ir: dict[str, Any] = Field(default_factory=dict)
    characters: list[dict[str, Any]] = Field(default_factory=list)
    scenes: list[dict[str, Any]] = Field(default_factory=list)
    visual_styles: list[dict[str, Any]] = Field(default_factory=list)
    existing_shots: list[dict[str, Any]] = Field(default_factory=list)
    source_hashes: dict[str, str] = Field(default_factory=dict)
    constraints: dict[str, Any] = Field(default_factory=lambda: {
        "source_fact_mutated": False,
        "script_ir_mutated": False,
        "human_review_required": True,
        "direct_database_write": False,
        "media_generation_allowed": False,
    })

    @property
    def context_hash(self) -> str:
        return content_hash(self.model_dump())

    def to_payload(self) -> dict[str, Any]:
        """Return a deep copy so a custom adapter cannot mutate this snapshot."""
        return deepcopy(self.model_dump())


class DirectorContextBuilder:
    """Build a minimal, hashed context snapshot for an adapter invocation."""

    def build(
        self,
        *,
        episode: Mapping[str, Any] | Any | None = None,
        script_ir: Mapping[str, Any] | Any | None = None,
        characters: list[Mapping[str, Any]] | None = None,
        scenes: list[Mapping[str, Any]] | None = None,
        visual_styles: list[Mapping[str, Any]] | None = None,
        existing_shots: list[Mapping[str, Any]] | None = None,
    ) -> DirectorContext:
        episode_payload = _mapping(episode)
        script_payload = _mapping(script_ir)
        scene_items = _records(scenes if scenes is not None else script_payload.get("scenes") or episode_payload.get("scenes"))
        character_items = _records(characters if characters is not None else (
            episode_payload.get("character_profiles") or episode_payload.get("characters") or script_payload.get("characters")
        ))
        style_items = _records(visual_styles if visual_styles is not None else (
            episode_payload.get("visual_style_profiles") or episode_payload.get("visual_styles") or script_payload.get("visual_styles")
        ))

        if existing_shots is None:
            shot_items: list[dict[str, Any]] = []
            for scene in scene_items:
                scene_id = str(scene.get("scene_id") or scene.get("id") or "")
                for key in ("shots", "shot_plans", "coverage"):
                    values = scene.get(key)
                    if isinstance(values, list):
                        for shot in values:
                            shot_payload = _mapping(shot)
                            if shot_payload:
                                shot_payload.setdefault("scene_id", scene_id)
                                shot_items.append(shot_payload)
                        break
        else:
            shot_items = _records(existing_shots)

        source_hashes = {
            "script_ir": str(script_payload.get("source_script_ir_hash") or content_hash(script_payload)),
            "source_fact": str(
                episode_payload.get("source_fact_snapshot_hash")
                or episode_payload.get("source_fact_hash")
                or ""
            ),
        }
        return DirectorContext(
            episode=episode_payload,
            script_ir=script_payload,
            characters=character_items,
            scenes=scene_items,
            visual_styles=style_items,
            existing_shots=shot_items,
            source_hashes=source_hashes,
        )


class DirectorLLMAdapterError(RuntimeError):
    def __init__(self, message: str, *, code: str = "DIRECTOR_LLM_ADAPTER_ERROR", provider_calls: int = 0):
        super().__init__(message)
        self.code = code
        self.provider_calls = provider_calls

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "provider_calls": self.provider_calls}


class DirectorLLMAdapter(ABC):
    """Contract implemented by OpenAI-compatible, Anthropic-compatible, or custom adapters."""

    provider = "custom"
    adapter_name = "director-llm-adapter"
    is_real_provider = False

    @property
    def provider_calls(self) -> int:
        return 0

    @abstractmethod
    def generate_reasoning(self, context: DirectorContext) -> Any:
        """Return an untrusted JSON object/string containing DirectorReasoningIR."""


class MockDirectorLLMAdapter(DirectorLLMAdapter):
    provider = "mock"
    adapter_name = "mock-director-llm"

    def __init__(self, response: Any | None = None):
        self.response = deepcopy(response)
        self._calls = 0

    @property
    def provider_calls(self) -> int:
        return self._calls

    def generate_reasoning(self, context: DirectorContext) -> Any:
        self._calls += 1
        if self.response is not None:
            return deepcopy(self.response)
        return director_reason(
            context.episode,
            context.script_ir,
            {"scenes": context.scenes, "visual_styles": context.visual_styles},
        )


class _TransportDirectorLLMAdapter(DirectorLLMAdapter):
    is_real_provider = True

    def __init__(self, transport: Callable[[dict[str, Any]], Any] | None = None, *, model: str = ""):
        self.transport = transport
        self.model = model
        self._calls = 0

    @property
    def provider_calls(self) -> int:
        return self._calls

    def generate_reasoning(self, context: DirectorContext) -> Any:
        if self.transport is None:
            raise DirectorLLMAdapterError(
                "real provider transport is disabled; inject a mock transport for tests",
                code="DIRECTOR_LLM_PROVIDER_CALL_DISABLED",
            )
        self._calls += 1
        try:
            return self.transport(context.to_payload())
        except DirectorLLMAdapterError:
            raise
        except Exception as exc:
            raise DirectorLLMAdapterError(str(exc), code="DIRECTOR_LLM_PROVIDER_TRANSPORT_FAILED", provider_calls=self._calls) from exc


class OpenAICompatibleDirectorAdapter(_TransportDirectorLLMAdapter):
    provider = "openai-compatible"
    adapter_name = "openai-compatible-director-llm"


class AnthropicCompatibleDirectorAdapter(_TransportDirectorLLMAdapter):
    provider = "anthropic-compatible"
    adapter_name = "anthropic-compatible-director-llm"


class CustomDirectorLLMAdapter(DirectorLLMAdapter):
    provider = "custom"
    adapter_name = "custom-director-llm"

    def __init__(self, generator: Callable[[DirectorContext], Any]):
        if not callable(generator):
            raise TypeError("custom director adapter requires a callable generator")
        self.generator = generator
        self._calls = 0

    @property
    def provider_calls(self) -> int:
        return self._calls

    def generate_reasoning(self, context: DirectorContext) -> Any:
        self._calls += 1
        try:
            return self.generator(context)
        except Exception as exc:
            raise DirectorLLMAdapterError(str(exc), code="DIRECTOR_LLM_CUSTOM_ADAPTER_FAILED", provider_calls=self._calls) from exc


class DirectorLLMAdapterRegistry:
    def __init__(self, adapters: Mapping[str, DirectorLLMAdapter] | None = None):
        self._adapters = dict(adapters or {})

    def register(self, provider: str, adapter: DirectorLLMAdapter) -> None:
        if not isinstance(adapter, DirectorLLMAdapter):
            raise TypeError("adapter must implement DirectorLLMAdapter")
        self._adapters[str(provider).strip().lower()] = adapter

    def resolve(self, provider: str) -> DirectorLLMAdapter:
        key = str(provider or "mock").strip().lower()
        adapter = self._adapters.get(key)
        if adapter is None:
            raise DirectorLLMAdapterError(f"unsupported director LLM provider: {key}", code="DIRECTOR_LLM_PROVIDER_UNSUPPORTED")
        return adapter


def build_default_director_llm_registry() -> DirectorLLMAdapterRegistry:
    return DirectorLLMAdapterRegistry({
        "mock": MockDirectorLLMAdapter(),
        "openai-compatible": OpenAICompatibleDirectorAdapter(),
        "anthropic-compatible": AnthropicCompatibleDirectorAdapter(),
    })


DEFAULT_DIRECTOR_LLM_ADAPTERS = build_default_director_llm_registry()


def _extract_provider_payload(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DirectorLLMAdapterError("provider output is not valid JSON", code="DIRECTOR_LLM_OUTPUT_NOT_JSON") from exc
    if not isinstance(raw, Mapping):
        raise DirectorLLMAdapterError("provider output must be a JSON object", code="DIRECTOR_LLM_OUTPUT_NOT_OBJECT")
    candidate = dict(raw)
    # Accept common compatible-provider envelopes, but validate the final
    # object strictly as DirectorReasoningIR.
    choices = candidate.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0] if isinstance(choices[0], Mapping) else {}
        message = choice.get("message") if isinstance(choice, Mapping) else None
        candidate = message.get("content") if isinstance(message, Mapping) else choice.get("text", choice)
    elif isinstance(candidate.get("content"), list):
        blocks = candidate["content"]
        text = next((block.get("text") for block in blocks if isinstance(block, Mapping) and isinstance(block.get("text"), str)), None)
        candidate = text if text is not None else candidate
    elif isinstance(candidate.get("output"), (Mapping, str)):
        candidate = candidate["output"]
    elif isinstance(candidate.get("reasoning"), (Mapping, str)):
        candidate = candidate["reasoning"]
    if isinstance(candidate, str):
        try:
            candidate = json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise DirectorLLMAdapterError("provider envelope content is not valid JSON", code="DIRECTOR_LLM_OUTPUT_NOT_JSON") from exc
    if not isinstance(candidate, Mapping):
        raise DirectorLLMAdapterError("provider output envelope did not contain an object", code="DIRECTOR_LLM_OUTPUT_NOT_OBJECT")
    return dict(candidate)


def director_reasoning_json_schema() -> dict[str, Any]:
    return DirectorReasoningPayload.model_json_schema()


def validate_llm_reasoning_output(raw: Any, context: DirectorContext) -> dict[str, Any]:
    """Validate provider JSON and cross-reference it against the context."""
    candidate = _extract_provider_payload(raw)
    try:
        validated = DirectorReasoningPayload.model_validate(candidate)
    except Exception as exc:
        raise DirectorLLMAdapterError("provider output failed DirectorReasoningIR schema validation", code="DIRECTOR_LLM_OUTPUT_SCHEMA_INVALID") from exc
    expected_episode_id = str(context.episode.get("episode_id") or context.episode.get("id") or context.script_ir.get("episode_id") or "")
    if expected_episode_id and str(validated.episode_id) != expected_episode_id:
        raise DirectorLLMAdapterError("provider output episode_id does not match context", code="DIRECTOR_LLM_OUTPUT_EPISODE_MISMATCH")
    try:
        validate_reasoning_for_compile(
            validated.model_dump(),
            episode_context={**context.episode, "character_profiles": context.characters, "visual_style_profiles": context.visual_styles},
            script_ir={**context.script_ir, "scenes": context.scenes},
            scene_context={"scenes": context.scenes, "visual_styles": context.visual_styles},
        )
    except DirectorReasoningCompileError as exc:
        raise DirectorLLMAdapterError("provider output failed DirectorReasoningIR reference validation", code="DIRECTOR_LLM_OUTPUT_IR_INVALID") from exc
    return validated.model_dump()


def add_adapter_lineage(payload: Mapping[str, Any], *, context: DirectorContext, adapter: DirectorLLMAdapter) -> dict[str, Any]:
    data = deepcopy(dict(payload))
    data["status"] = "REVIEW_REQUIRED"
    data["reasoning_trace"] = {
        **(data.get("reasoning_trace") if isinstance(data.get("reasoning_trace"), Mapping) else {}),
        "mode": "llm_adapter",
        "provider": adapter.provider,
        "adapter_name": adapter.adapter_name,
        "llm_called": True,
        "provider_calls": adapter.provider_calls,
        "human_review_required": True,
        "source_fact_mutated": False,
        "script_ir_mutated": False,
        "direct_database_write": False,
    }
    data["lineage"] = {
        **(data.get("lineage") if isinstance(data.get("lineage"), Mapping) else {}),
        "schema_version": DIRECTOR_LLM_ADAPTER_SCHEMA_VERSION,
        "adapter_provider": adapter.provider,
        "adapter_name": adapter.adapter_name,
        "context_hash": context.context_hash,
        "source_script_ir_hash": context.source_hashes.get("script_ir", ""),
        "source_fact_snapshot_hash": context.source_hashes.get("source_fact", ""),
        "source_fact_mutated": False,
        "script_ir_mutated": False,
        "human_review_required": True,
        "direct_database_write": False,
    }
    data.pop("payload_hash", None)
    return data


__all__ = [
    "DIRECTOR_CONTEXT_SCHEMA_VERSION",
    "DIRECTOR_LLM_ADAPTER_SCHEMA_VERSION",
    "DirectorContext",
    "DirectorContextBuilder",
    "DirectorLLMAdapter",
    "DirectorLLMAdapterError",
    "MockDirectorLLMAdapter",
    "OpenAICompatibleDirectorAdapter",
    "AnthropicCompatibleDirectorAdapter",
    "CustomDirectorLLMAdapter",
    "DirectorLLMAdapterRegistry",
    "DEFAULT_DIRECTOR_LLM_ADAPTERS",
    "build_default_director_llm_registry",
    "director_reasoning_json_schema",
    "validate_llm_reasoning_output",
    "add_adapter_lineage",
    "content_hash",
]
