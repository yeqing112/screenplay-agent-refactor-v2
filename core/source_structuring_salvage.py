"""Provider-free salvage for a failed source structuring candidate.

The salvage boundary is intentionally narrow.  It can demote a candidate's
own reported-speech evidence to source-grounded actions, recover a speaker
identity pointer from the same participant's earlier evidence, and replace a
non-literal scene label with the earliest exact scene evidence.  It cannot
author new story text or change an LLM semantic decision.
"""
from __future__ import annotations

import copy
from typing import Any

from core.source_structuring_v2 import resolve_exact_source_evidence


DIRECT_QUOTE_PAIRS = (("“", "”"), ('"', '"'), ("「", "」"), ("『", "』"), ("‘", "’"))


def is_direct_quote(raw: str, text: str) -> bool:
    return any(f"{left}{text}{right}" in str(raw or "") for left, right in DIRECT_QUOTE_PAIRS)


def _resolve_all(raw: str, values: Any) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for value in values if isinstance(values, list) else []:
        resolved.append(resolve_exact_source_evidence(raw, str(value)))
    return resolved


def _recover_speaker_identity(*, raw: str, scene: dict[str, Any], speaker: str, utterance_start: int) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for participant in scene.get("participants") or []:
        if not isinstance(participant, dict) or str(participant.get("name") or "") != str(speaker or ""):
            continue
        for evidence in _resolve_all(raw, participant.get("evidence")):
            if speaker in evidence["text"]:
                candidates.append(evidence)
    if not candidates:
        raise ValueError("SPEAKER_IDENTITY_RECOVERY_NOT_PROVABLE")
    def distance(item: dict[str, Any]) -> int:
        start, end = int(item["char_start"]), int(item["char_end"])
        if end < utterance_start:
            return utterance_start - end
        if start > utterance_start:
            return start - utterance_start
        return 0
    best_distance = min(distance(item) for item in candidates)
    best = [item for item in candidates if distance(item) == best_distance]
    if len(best) != 1:
        raise ValueError("SPEAKER_IDENTITY_RECOVERY_AMBIGUOUS")
    return best[0]


def salvage_candidate_v2(raw: str, candidate: Any) -> dict[str, Any]:
    """Return a deterministic candidate salvage or a fail-closed result."""
    if not isinstance(candidate, dict):
        return {"status": "DETERMINISTIC_SALVAGE_NOT_PROVABLE", "errors": [{"code": "CANDIDATE_NOT_OBJECT"}]}
    salvaged = copy.deepcopy(candidate)
    errors: list[dict[str, Any]] = []
    demotions: list[dict[str, Any]] = []
    recoveries: list[dict[str, Any]] = []
    scene_audits: list[dict[str, Any]] = []

    for scene_index, scene in enumerate(salvaged.get("scenes") or [], start=1):
        if not isinstance(scene, dict):
            errors.append({"code": "SCENE_INVALID", "scene_index": scene_index})
            continue
        original_label = str(scene.get("scene_label") or "")
        try:
            literal_label = resolve_exact_source_evidence(raw, original_label)
            scene_audits.append({"scene_index": scene_index, "original_scene_label": original_label, "status": "SOURCE_LITERAL", "selected_scene_identity": literal_label})
        except Exception:
            try:
                evidence = sorted(_resolve_all(raw, scene.get("scene_evidence")), key=lambda item: (int(item["char_start"]), int(item["char_end"])))
            except Exception as exc:
                errors.append({"code": "SCENE_LABEL_NOT_SOURCE_LITERAL", "scene_index": scene_index, "reason": str(exc)})
                continue
            if not evidence:
                errors.append({"code": "SCENE_IDENTITY_RECOVERY_NOT_PROVABLE", "scene_index": scene_index})
                continue
            literal_label = evidence[0]
            scene["scene_label"] = literal_label["text"]
            scene_audits.append({"scene_index": scene_index, "original_scene_label": original_label, "status": "SCENE_LABEL_NOT_SOURCE_LITERAL", "selected_scene_identity": literal_label, "display_label": original_label, "display_label_authority": "AUTHORIZED_SEMANTIC_LABEL"})

        original_dialogues = list(scene.get("dialogues") or [])
        retained_dialogues: list[dict[str, Any]] = []
        action_texts = {str(item.get("source_text") or "") for item in scene.get("actions") or [] if isinstance(item, dict)}
        for dialogue_index, dialogue in enumerate(original_dialogues, start=1):
            if not isinstance(dialogue, dict):
                errors.append({"code": "DIALOGUE_INVALID", "scene_index": scene_index, "dialogue_index": dialogue_index})
                continue
            text = str(dialogue.get("text") or "")
            try:
                utterance_evidence = _resolve_all(raw, dialogue.get("utterance_evidence"))
            except Exception as exc:
                errors.append({"code": "DIALOGUE_EVIDENCE_UNRESOLVED", "scene_index": scene_index, "dialogue_index": dialogue_index, "reason": str(exc)})
                continue
            reported = [item for item in utterance_evidence if text and text in item["text"] and not is_direct_quote(item["text"], text)]
            if reported:
                for evidence in reported:
                    action_text = evidence["text"]
                    duplicate = action_text in action_texts
                    if not duplicate:
                        scene.setdefault("actions", []).append({"source_text": action_text})
                        action_texts.add(action_text)
                    demotions.append({"scene_index": scene_index, "dialogue_index": dialogue_index, "original_dialogue": copy.deepcopy(dialogue), "source_evidence": evidence, "demoted_action": {"source_text": action_text}, "duplicate_action_prevented": duplicate, "reason": "non_direct_quote_in_unique_utterance_context", "classification": "DETERMINISTIC_REPORTED_SPEECH_DEMOTION", "no_semantic_rewrite": True})
                continue

            if is_direct_quote(raw, text):
                updated = copy.deepcopy(dialogue)
                try:
                    utterance_start = resolve_exact_source_evidence(raw, text)["char_start"]
                    recovered = _recover_speaker_identity(raw=raw, scene=scene, speaker=str(dialogue.get("speaker") or ""), utterance_start=utterance_start)
                except Exception as exc:
                    errors.append({"code": str(exc), "scene_index": scene_index, "dialogue_index": dialogue_index})
                    retained_dialogues.append(updated)
                    continue
                updated["speaker_identity_evidence"] = [recovered["text"]]
                recoveries.append({"scene_index": scene_index, "dialogue_index": dialogue_index, "speaker": dialogue.get("speaker"), "original_evidence": dialogue.get("speaker_identity_evidence"), "recovered_evidence": recovered, "rule": "same_scene_same_participant_exact_evidence_contains_speaker_choose_nearest_textual_distance_before_or_after", "classification": "DETERMINISTIC_SPEAKER_IDENTITY_EVIDENCE_RECOVERY"})
                retained_dialogues.append(updated)
                continue

            errors.append({"code": "NON_DIRECT_DIALOGUE_DEMOTION_NOT_PROVABLE", "scene_index": scene_index, "dialogue_index": dialogue_index, "text": text})
            retained_dialogues.append(copy.deepcopy(dialogue))
        scene["dialogues"] = retained_dialogues

    if errors:
        return {"status": "DETERMINISTIC_SALVAGE_NOT_PROVABLE", "errors": errors, "demotions": demotions, "recoveries": recoveries, "scene_audits": scene_audits}
    return {"status": "PASS", "candidate": salvaged, "demotions": demotions, "recoveries": recoveries, "scene_audits": scene_audits, "errors": []}


__all__ = ["DIRECT_QUOTE_PAIRS", "is_direct_quote", "salvage_candidate_v2"]
