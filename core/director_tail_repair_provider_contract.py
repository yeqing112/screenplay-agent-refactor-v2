"""Single source of truth for the provider-facing Director Tail Repair contract.

The model-facing contract is intentionally the semantic Repair IR.  Canonical
``director_creative_patch_v1`` is produced only after validation by the
deterministic compiler and is never requested from a provider.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from core.director_tail_repair_ir import (
    ALLOWED_FIELDS,
    DIRECTOR_TARGET_DIMENSIONS,
    REPAIR_IR_SCHEMA_VERSION,
    REPAIR_TYPES,
    ROOT_CAUSE_TYPES,
)


REPAIR_IR_REQUIRED_KEYS = frozenset(
    {"schema_version", "repair_type", "root_cause", "target_dimensions", "shot_decisions"}
)


def build_provider_output_contract() -> dict[str, Any]:
    """Build the provider-facing output description from IR constants."""

    semantic_fields = {
        repair_type: {
            group: sorted(fields)
            for group, fields in sorted(groups.items())
        }
        for repair_type, groups in sorted(ALLOWED_FIELDS.items())
    }
    return {
        "schema_version": REPAIR_IR_SCHEMA_VERSION,
        "required_keys": sorted(REPAIR_IR_REQUIRED_KEYS),
        "repair_types": sorted(REPAIR_TYPES),
        "root_cause_types": {
            key: sorted(values) for key, values in sorted(ROOT_CAUSE_TYPES.items())
        },
        "target_dimensions": sorted(DIRECTOR_TARGET_DIMENSIONS),
        "semantic_fields": semantic_fields,
        "no_canonical_paths": True,
        "ir_fingerprint": "system-computed; do not provide",
    }


def provider_contract_fingerprint() -> str:
    payload = json.dumps(
        build_provider_output_contract(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_provider_system_prompt() -> str:
    """Return the provider system instruction for semantic Repair IR only."""

    contract = build_provider_output_contract()
    fields = json.dumps(contract["semantic_fields"], ensure_ascii=False, sort_keys=True)
    return (
        "你是 Director Tail Repair Planner。\n"
        "你的任务是只输出一个合法 JSON object，协议为 "
        f"{REPAIR_IR_SCHEMA_VERSION}。\n"
        "你负责导演语义决策，不负责 JSON Patch、canonical path、生产写入、"
        "FactSnapshot、ScriptIR、ShotPlan 身份或不可变事实修改。\n"
        "必须包含字段：schema_version、repair_type、root_cause、"
        "target_dimensions、shot_decisions；repair_type 只能是 "
        "edit、emotion、information、performance、camera。\n"
        "shot_decisions 只能引用输入中提供的 plan_shot_id，并使用对应 repair_type "
        "允许的语义字段；当 allowed_plan_shot_ids 非空时，shot_decisions 必须至少包含一项，"
        "且每项 plan_shot_id 必须属于该集合。不要输出 patches、auxiliary_shot_proposals、path、"
        "changes 或任何 canonical patch 字段。不要输出 Markdown、解释文字或代码块。\n"
        f"允许的语义字段映射：{fields}\n"
        "ir_fingerprint 由系统计算，不要提供。"
    )


__all__ = [
    "REPAIR_IR_REQUIRED_KEYS",
    "build_provider_output_contract",
    "provider_contract_fingerprint",
    "build_provider_system_prompt",
]
