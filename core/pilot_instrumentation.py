"""Deterministic instrumentation helpers for the Real Production Pilot.

The pilot must be able to account for every model attempt without changing
the behaviour of existing agents.  ``PilotInvocationRecorder`` is deliberately
an in-process collector: callers may scope an operation with ``span`` and all
LLM audit records emitted by :mod:`core.llm` are captured with the non-secret
stage/episode/scene/shot metadata.  No provider request, prompt, response, or
credential is persisted by this module.
"""

from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Iterator

from core.prompt_cache import summarize_audit_records


class PilotInvocationRecorder:
    """Collect bounded LLM audit records and expose deterministic summaries."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def record(self, record: dict[str, Any]) -> None:
        if isinstance(record, dict):
            # ``core.llm`` already bounds all fields.  Copy the envelope so a
            # later caller mutation cannot alter the pilot trace.
            self.records.append(dict(record))

    @contextmanager
    def span(
        self,
        *,
        stage: str,
        episode: int | str | None = None,
        scene: str | None = None,
        shot: int | str | None = None,
        repair_attempt: int = 0,
        **tags: Any,
    ) -> Iterator[None]:
        """Capture LLM calls made inside one pipeline stage.

        The implementation imports lazily to keep this module usable by
        deterministic tests and to avoid introducing an import cycle during
        application startup.
        """

        from core.llm import llm_audit_context

        metadata: dict[str, Any] = {
            "pilot_stage": str(stage or "").strip(),
            "pilot_episode": episode,
            "pilot_scene": scene,
            "pilot_shot": shot,
            "pilot_repair_attempt": int(repair_attempt or 0),
            **tags,
        }
        # Context metadata is audit-only and must stay scalar.  ``core.llm``
        # applies its own bounded scalar filter before emitting the record.
        with llm_audit_context(sink=self.record, **metadata):
            yield

    def summary(self) -> dict[str, Any]:
        """Return aggregate LLM metrics plus stage-level breakdowns."""

        overall = summarize_audit_records(self.records)
        by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in self.records:
            extra = record.get("extra") if isinstance(record, dict) else None
            stage = str(extra.get("pilot_stage") or "unattributed") if isinstance(extra, dict) else "unattributed"
            by_stage[stage].append(record)
        return {
            "total_calls": len(self.records),
            "total_prompt_tokens": overall.get("prompt_tokens", 0),
            "total_cached_tokens": overall.get("cached_tokens", 0),
            "cache_hit_rate": overall.get("cache_hit_rate"),
            "total_completion_tokens": overall.get("completion_tokens", 0),
            "total_tokens": overall.get("total_tokens", 0),
            "retry_count": max(0, len(self.records) - len({
                str(item.get("request_fingerprint") or "")
                for item in self.records
                if str(item.get("request_fingerprint") or "")
            })),
            "avg_latency_ms": (
                round(sum(float(item.get("latency_ms") or 0) for item in self.records) / len(self.records), 2)
                if self.records else None
            ),
            "stages": {
                stage: {
                    **summarize_audit_records(items),
                    "total_calls": len(items),
                }
                for stage, items in sorted(by_stage.items())
            },
            "records": [dict(item) for item in self.records],
        }

