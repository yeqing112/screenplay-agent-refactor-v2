"""Prompt construction and validation for evidence-constrained LLM drafts.

This module intentionally knows nothing about database models or domain writes.  It
turns a frozen DecisionPacket into a bounded request and validates the response so
callers can only persist a reviewable proposal.
"""
from __future__ import annotations

import json
from typing import Any

from core.decision_packet import normalize_decision_packet


DECISION_VALUES = {
    "ready_for_review",
    "needs_information",
    "blocked",
    "no_change_recommended",
}


def build_decision_draft_prompt(packet: dict[str, Any]) -> str:
    """Return a self-contained, JSON-only LLM request for a frozen packet."""
    frozen = normalize_decision_packet(packet)
    payload = json.dumps(frozen, ensure_ascii=False, indent=2, sort_keys=True)
    script_scope_rule = ""
    contract = frozen.get("scope", {}).get("proposal_contract") if isinstance(frozen.get("scope"), dict) else None
    if frozen["domain"] == "script" and isinstance(contract, dict) and contract.get("kind") == "script_qa_single_issue_local_revision_v1":
        if contract.get("target_excerpt_is_precise_span"):
            script_scope_rule = (
                "\n6. 本次只处理 proposal_contract.target_issue_key 指定的一个 QA 问题。"
                "若输出 propose_script_revision，proposed_content 必须是该问题精确片段的完整替换文本，"
                f"不得超过 {int(contract.get('max_replacement_chars') or 0)} 个字符；不得重写整集、不得顺带修复 sibling issues。"
            )
        else:
            script_scope_rule = (
                "\n6. 当前 QA 问题没有精确可替换行区间。可以给出供人工审核的局部修复策略，"
                "但 propose_script_revision.proposed_content 必须为空；不得输出整集或跨场景替换文本。"
            )
    if frozen["domain"] == "script" and isinstance(contract, dict) and contract.get("kind") == "script_qa_target_resolution_v1":
        script_scope_rule = (
            "\n6. 本次只选择一个可供人工确认的修订定位范围，不得输出任何剧本文字。"
            "proposal.operation 必须为 propose_repair_target，target_span 必须完全落在"
            "proposal_contract.candidate_spans 的某一个候选范围内，并原样携带其 source_fingerprint；"
            "不得选择整个候选场景，必须定位到更小的连续剧情节拍。"
        )
    if frozen["domain"] == "script" and isinstance(frozen.get("scope"), dict) and frozen["scope"].get("beat_ids"):
        script_scope_rule += (
            "\n7. 当 allowed_operations 含 propose_edits：输出 edits 数组，每项为 "
            "{\"op\":\"replace|insert_after|delete\", \"beat_id\":\"必须来自 scope.beat_ids\", "
            "\"new_text\":\"replace/insert_after 必填且不得与原文相同\"}。优先用 propose_edits 给出锚定编辑，"
            "不得用整段 propose_script_revision 正文覆盖多个 beat。"
        )
    return f"""你是影视生产系统中的“有限决断”分析器。你只能基于证据包中的事实提出可审核草案，绝不能把草案当成已执行的修改。

强制规则：
1. 证据优先级严格为 locked_fact > approved_fact > source_text > derived_fact > model_observation > unknown。
2. 不得补造人物、场景、道具、动作、镜头时长或资产状态。证据不足或冲突时必须选择 needs_information 或 blocked。
3. allowed_operations 以外的操作不得建议；不得建议直接写入、锁定、验收、生成、发布、删除、迁移或调用外部付费服务。
4. 这是分析草案，不执行任何领域变更；人工审核、编辑和确认始终必需。
5. 仅输出一个合法 JSON object，不要 Markdown 或解释。{script_scope_rule}

请输出此固定结构：
{{
  "decision": "ready_for_review|needs_information|blocked|no_change_recommended",
  "confidence": 0.0,
  "evidence": [{{"id":"证据id", "reason":"如何支持结论"}}],
  "unknowns": ["仍缺失的信息"],
  "conflicts": ["尚未解决的冲突"],
  "proposals": [{{"operation":"必须来自 allowed_operations", "summary":"可供人工审核的建议", "affected_fields":["仅字段名"], "proposed_content":"仅当 operation 为 propose_script_revision 时，可选地给出供人工编辑的完整替换片段；否则为空字符串", "target_span":{{"line_start":0,"line_end":0,"source_fingerprint":""}}, "edits":[{{"op":"replace","beat_id":"","new_text":""}}], "requires_human_review":true}}],
  "human_confirmation_required": true
}}

证据包（不可修改）：
{payload}
"""


def validate_decision_draft(value: Any, packet: dict[str, Any]) -> dict[str, Any]:
    """Normalize a model response and reject proposals outside its authority."""
    if not isinstance(value, dict):
        raise ValueError("LLM decision draft must be a JSON object")
    frozen = normalize_decision_packet(packet)
    decision = str(value.get("decision") or "").strip()
    if decision not in DECISION_VALUES:
        raise ValueError("LLM decision draft has an unsupported decision")
    try:
        confidence = float(value.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise ValueError("LLM decision draft confidence must be a number") from exc
    if not 0 <= confidence <= 1:
        raise ValueError("LLM decision draft confidence must be between 0 and 1")

    allowed = set(frozen["allowed_operations"])
    contract = frozen.get("scope", {}).get("proposal_contract") if isinstance(frozen.get("scope"), dict) else None
    script_local_contract = (
        frozen["domain"] == "script"
        and isinstance(contract, dict)
        and contract.get("kind") == "script_qa_single_issue_local_revision_v1"
    )
    precise_script_span = bool(contract.get("target_excerpt_is_precise_span")) if script_local_contract else False
    max_replacement_chars = int(contract.get("max_replacement_chars") or 0) if script_local_contract else 0
    target_resolution_contract = (
        frozen["domain"] == "script"
        and isinstance(contract, dict)
        and contract.get("kind") == "script_qa_target_resolution_v1"
    )
    scope_conflicts: list[str] = []
    script_revision_seen = False
    proposals = value.get("proposals") if isinstance(value.get("proposals"), list) else []
    normalized_proposals = []
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        operation = str(proposal.get("operation") or "").strip()
        if operation not in allowed:
            raise ValueError("LLM decision draft proposed an operation outside allowed_operations")
        proposed_content = str(proposal.get("proposed_content") or "").strip() if operation == "propose_script_revision" else ""
        target_span: dict[str, Any] = {}
        edits: list[dict[str, Any]] = []
        if operation == "propose_edits":
            allowed_beat_ids = set(frozen["scope"].get("beat_ids") or []) if isinstance(frozen.get("scope"), dict) else set()
            raw_edits = proposal.get("edits") if isinstance(proposal.get("edits"), list) else []
            for item in raw_edits:
                if not isinstance(item, dict):
                    continue
                op = str(item.get("op") or "").strip()
                beat_id = str(item.get("beat_id") or "").strip()
                new_text = str(item.get("new_text") or "")
                if op not in {"replace", "insert_after", "delete"}:
                    scope_conflicts.append(f"edits 含不支持操作 {op}；已忽略。")
                    continue
                if allowed_beat_ids and beat_id not in allowed_beat_ids:
                    scope_conflicts.append(f"edits 引用未授权 beat {beat_id}；已忽略。")
                    continue
                if op in {"replace", "insert_after"} and not new_text.strip():
                    scope_conflicts.append(f"edits {op} 缺 new_text；已忽略。")
                    continue
                edits.append({"op": op, "beat_id": beat_id, "new_text": new_text})
        if script_local_contract and operation == "propose_script_revision":
            if script_revision_seen:
                scope_conflicts.append("候选包含多段脚本替换；已丢弃超出当前单问题范围的内容。")
                proposed_content = ""
            script_revision_seen = True
            if not precise_script_span and proposed_content:
                scope_conflicts.append("当前问题没有精确替换区间；已移除不可安全应用的脚本文本。")
                proposed_content = ""
            elif precise_script_span and max_replacement_chars > 0 and len(proposed_content) > max_replacement_chars:
                scope_conflicts.append("候选替换文本超出当前单问题的长度合同；已移除该文本，等待人工缩小范围。")
                proposed_content = ""
        if target_resolution_contract and operation == "propose_repair_target":
            raw_span = proposal.get("target_span") if isinstance(proposal.get("target_span"), dict) else {}
            try:
                start, end = int(raw_span.get("line_start")), int(raw_span.get("line_end"))
            except (TypeError, ValueError):
                start, end = 0, -1
            fingerprint = str(raw_span.get("source_fingerprint") or "").strip()
            candidates = contract.get("candidate_spans") if isinstance(contract.get("candidate_spans"), list) else []
            valid = next((item for item in candidates if isinstance(item, dict) and start >= int(item.get("line_start") or 0) and end <= int(item.get("line_end") or -1) and fingerprint == str(item.get("source_fingerprint") or "")), None)
            if not valid or start > end or (start == int(valid.get("line_start")) and end == int(valid.get("line_end"))):
                scope_conflicts.append("候选定位越界或覆盖整个候选场景，已移除，等待人工重新选择。")
            else:
                target_span = {"line_start": start, "line_end": end, "source_fingerprint": fingerprint}
        elif target_resolution_contract and operation == "propose_script_revision":
            scope_conflicts.append("定位阶段不得输出剧本文本，已移除。")
            proposed_content = ""
        normalized_proposals.append({
            "operation": operation,
            "summary": str(proposal.get("summary") or "").strip(),
            "affected_fields": [str(item) for item in proposal.get("affected_fields", []) if str(item).strip()],
            "proposed_content": proposed_content,
            "target_span": target_span,
            "edits": edits,
            "requires_human_review": True,
        })

    unknowns = [str(item) for item in value.get("unknowns", []) if str(item).strip()]
    conflicts = [str(item) for item in value.get("conflicts", []) if str(item).strip()]
    conflicts = list(dict.fromkeys([*conflicts, *scope_conflicts]))
    # The model may not erase known blockers merely by claiming confidence.
    if frozen["unknowns"] or frozen["conflicts"]:
        if decision not in {"needs_information", "blocked"}:
            raise ValueError("LLM decision draft must preserve unresolved packet unknowns or conflicts")
        unknowns = list(dict.fromkeys([*frozen["unknowns"], *unknowns]))
        conflicts = list(dict.fromkeys([*frozen["conflicts"], *conflicts]))

    return {
        "decision": decision,
        "confidence": confidence,
        "evidence": [
            {"id": str(item.get("id") or "").strip(), "reason": str(item.get("reason") or "").strip()}
            for item in value.get("evidence", []) if isinstance(item, dict)
        ],
        "unknowns": unknowns,
        "conflicts": conflicts,
        "proposals": normalized_proposals,
        "human_confirmation_required": True,
    }
