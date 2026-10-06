"""Generic, provider free source grounded structuring contract.

V3 is the production path for prose and screenplay source ingestion.  It
keeps source identity and semantic presentation separate and computes all
locators locally.  Reconciliation can only lower authority or restore an
evidence pointer; it never authors story text.
"""
from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from typing import Any, Mapping

from core.source_structuring_v2 import SourceEvidenceError, resolve_exact_source_evidence
from core.source_authority import SourceLineageContext, canonical_json_sha256, reconciliation_fingerprint

SCHEMA_VERSION = "source_grounded_screenplay_structuring_candidate_v3"
GROUNDED_VERSION = "grounded_source_screenplay_structuring_candidate_v3"
PAYLOAD_SCHEMA_VERSION = "source_grounded_script_payload_v3"
SCHEMA_VERSION_V3_1 = "source_grounded_screenplay_structuring_candidate_v3_1"
GROUNDED_VERSION_V3_1 = "grounded_source_screenplay_structuring_candidate_v3_1"
PAYLOAD_SCHEMA_VERSION_V3_1 = "source_grounded_script_payload_v3_1"
SOURCE_FORM_QUOTED_PROSE = "QUOTED_PROSE"
SOURCE_FORM_SPEAKER_LABELED = "SPEAKER_LABELED"
SOURCE_FORM_STRUCTURED_DIALOGUE_BLOCK = "STRUCTURED_DIALOGUE_BLOCK"
SOURCE_FORMS = (SOURCE_FORM_QUOTED_PROSE, SOURCE_FORM_SPEAKER_LABELED, SOURCE_FORM_STRUCTURED_DIALOGUE_BLOCK)
AUTHORITY_LATTICE = ("UNRESOLVED", "UNTRUSTED_MODEL_OUTPUT", "AUTHORIZED_SEMANTIC_LABEL", "SOURCE_FACT")
FORBIDDEN_LLM_FIELDS = {"start", "end", "byte_offset", "byte_start", "byte_end", "char_start", "char_end", "sha256"}
DIRECT_QUOTE_PAIRS = (("“", "”"), ('"', '"'), ("「", "」"), ("『", "』"), ("‘", "’"))


@dataclass(frozen=True)
class SourceStructuringPolicy:
    """Optional caller supplied participant scope.

    ``None`` means names are not allowlisted.  Evidence still has to contain
    the name literally, so an arbitrary model identity cannot enter the
    grounded candidate without source proof.
    """

    allowed_participants: frozenset[str] | None = None
    require_participant_evidence: bool = True
    authorize_semantic_display_label: bool = False


@dataclass(frozen=True)
class SourceIdentityContext:
    episode: int = 1
    scene_namespace: str = "E"

    def scene_id(self, ordinal: int) -> str:
        namespace = str(self.scene_namespace or "E").strip() or "E"
        return f"{namespace}{int(self.episode):02d}_SC{int(ordinal):03d}"


def _sha(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _walk_forbidden(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key) in FORBIDDEN_LLM_FIELDS:
                found.append(f"{path}.{key}")
            found.extend(_walk_forbidden(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_walk_forbidden(child, f"{path}[{index}]"))
    return found


def _occurrences(raw: str, needle: str, start: int = 0, end: int | None = None) -> list[int]:
    limit = len(raw) if end is None else int(end)
    result: list[int] = []
    cursor = max(0, int(start))
    while needle and cursor <= limit:
        found = raw.find(needle, cursor, limit)
        if found < 0:
            break
        result.append(found)
        cursor = found + 1
    return result


def _span(raw: str, start: int, end: int, *, occurrence_count: int = 1) -> dict[str, Any]:
    text = raw[start:end]
    return {
        "text": text,
        "char_start": start,
        "char_end": end,
        "byte_start": len(raw[:start].encode("utf-8")),
        "byte_end": len(raw[:end].encode("utf-8")),
        "sha256": _sha(text),
        "occurrence_count": occurrence_count,
    }


def resolve_exact_evidence_context(raw_source: str, evidence_text: str | Mapping[str, Any]) -> dict[str, Any]:
    """Resolve a unique context span, rejecting repeated context globally."""
    if isinstance(evidence_text, Mapping):
        text = str(evidence_text.get("text") or "")
    else:
        text = str(evidence_text or "")
    if not text:
        raise SourceEvidenceError("SOURCE_EVIDENCE_NOT_FOUND", "evidence context must not be empty")
    return resolve_exact_source_evidence(str(raw_source or ""), text)


def resolve_child_evidence_within_context(raw_source: str, context: str | Mapping[str, Any], child_text: str) -> dict[str, Any]:
    """Resolve one child occurrence using its local context, not global text."""
    raw = str(raw_source or "")
    context_span = resolve_exact_evidence_context(raw, context)
    child = str(child_text or "")
    positions = _occurrences(raw, child, context_span["char_start"], context_span["char_end"])
    if not child or not positions:
        raise SourceEvidenceError("DIALOGUE_NOT_IN_UTTERANCE_CONTEXT", "child evidence was not found in its context", child_text=child)
    if len(positions) != 1:
        raise SourceEvidenceError("DIALOGUE_CONTEXT_OCCURRENCE_AMBIGUOUS", "child text occurs more than once in its context", child_text=child, occurrence_count=len(positions))
    return _span(raw, positions[0], positions[0] + len(child))


def _is_direct_quote_in_context(raw: str, child_span: Mapping[str, Any], context_span: Mapping[str, Any]) -> bool:
    start, end = int(child_span["char_start"]), int(child_span["char_end"])
    context_start, context_end = int(context_span["char_start"]), int(context_span["char_end"])
    for left, right in DIRECT_QUOTE_PAIRS:
        if start - len(left) >= context_start and end + len(right) <= context_end:
            if raw[start - len(left):start] == left and raw[end:end + len(right)] == right:
                return True
    return False


def _speaker_labeled_relation(raw: str, speaker: str, child_span: Mapping[str, Any], context_span: Mapping[str, Any]) -> bool:
    """Validate a structural role separator without a names allowlist."""
    start, end = int(child_span["char_start"]), int(child_span["char_end"])
    context_start, context_end = int(context_span["char_start"]), int(context_span["char_end"])
    prefix = raw[context_start:start]
    if not speaker or not prefix.rstrip().endswith((f"{speaker}:", f"{speaker}：")):
        return False
    return context_start <= start < end <= context_end


def _resolve_source_form(raw: str, dialogue: Mapping[str, Any], child_span: Mapping[str, Any], context_span: Mapping[str, Any]) -> tuple[str | None, str | None]:
    requested = str(dialogue.get("source_form") or "").strip()
    speaker = str(dialogue.get("speaker") or "").strip()
    if requested and requested not in SOURCE_FORMS:
        return None, "SOURCE_FORM_INVALID"
    if requested == SOURCE_FORM_QUOTED_PROSE:
        return (requested, None) if _is_direct_quote_in_context(raw, child_span, context_span) else (None, "DIALOGUE_NOT_DIRECT_QUOTE")
    if requested == SOURCE_FORM_SPEAKER_LABELED:
        return (requested, None) if _speaker_labeled_relation(raw, speaker, child_span, context_span) else (None, "SPEAKER_LABEL_SEPARATOR_NOT_FOUND")
    if requested == SOURCE_FORM_STRUCTURED_DIALOGUE_BLOCK:
        # The caller explicitly identifies the structured source block; no
        # natural-language quotation heuristic is applied.
        return (requested, None)
    if _is_direct_quote_in_context(raw, child_span, context_span):
        return SOURCE_FORM_QUOTED_PROSE, None
    if _speaker_labeled_relation(raw, speaker, child_span, context_span):
        return SOURCE_FORM_SPEAKER_LABELED, None
    return None, "SOURCE_FORM_UNRESOLVED"


def _authority_delta(before: str, after: str) -> str:
    if before == after:
        return "SAME"
    try:
        return "DOWNGRADE" if AUTHORITY_LATTICE.index(after) < AUTHORITY_LATTICE.index(before) else "UPGRADE"
    except ValueError:
        return "DOWNGRADE"


def _resolve_list(raw: str, values: Any, field: str, errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(values, list) or not values:
        errors.append({"code": "SOURCE_EVIDENCE_REQUIRED", "field": field})
        return []
    resolved: list[dict[str, Any]] = []
    for value in values:
        try:
            resolved.append(resolve_exact_evidence_context(raw, value))
        except SourceEvidenceError as exc:
            errors.append({"code": exc.code, "field": field, **exc.details})
    return resolved


def _label(items: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    return [{**item, "evidence_id": f"{prefix}{index:03d}"} for index, item in enumerate(items, 1)]


def ground_candidate_v3(raw_source: str, candidate: Any, *, policy: SourceStructuringPolicy | None = None, expected_source_fingerprint: str | None = None) -> dict[str, Any]:
    """Ground a generic V3 semantic candidate against immutable source text."""
    raw = str(raw_source or "")
    policy = policy or SourceStructuringPolicy()
    errors: list[dict[str, Any]] = []
    if expected_source_fingerprint is not None and _sha(raw) != str(expected_source_fingerprint):
        errors.append({"code": "AUTHORIZED_SOURCE_CHANGED", "expected": str(expected_source_fingerprint), "actual": _sha(raw)})
    if not isinstance(candidate, dict):
        return {"status": "FAIL", "errors": [{"code": "CANDIDATE_NOT_OBJECT"}]}
    if candidate.get("schema_version") not in {SCHEMA_VERSION, SCHEMA_VERSION_V3_1}:
        errors.append({"code": "SCHEMA_VERSION_INVALID"})
    forbidden = _walk_forbidden(candidate)
    if forbidden:
        errors.append({"code": "LLM_MUST_NOT_PROVIDE_LOCAL_OFFSETS_OR_HASHES", "paths": forbidden})
    scenes = candidate.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        errors.append({"code": "SCENES_REQUIRED"})
        return {"status": "FAIL", "errors": errors}
    grounded_scenes: list[dict[str, Any]] = []
    consumed_dialogue_spans: set[tuple[int, int]] = set()
    for scene_index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            errors.append({"code": "SCENE_INVALID", "scene_index": scene_index})
            continue
        scene_errors_start = len(errors)
        scene_evidence = _resolve_list(raw, scene.get("scene_evidence"), f"scenes[{scene_index}].scene_evidence", errors)
        requested_display_label = str(scene.get("display_label") or "").strip()
        requested_display_authority = str(scene.get("display_label_authority") or "UNTRUSTED_MODEL_OUTPUT")
        if requested_display_label and policy.authorize_semantic_display_label and requested_display_authority == "AUTHORIZED_SEMANTIC_LABEL":
            display_label = requested_display_label
            display_authority = "AUTHORIZED_SEMANTIC_LABEL"
            untrusted_display_label = ""
        elif requested_display_label:
            display_label = ""
            display_authority = "UNRESOLVED"
            untrusted_display_label = requested_display_label
        else:
            display_label = ""
            display_authority = "UNRESOLVED"
            untrusted_display_label = ""
        grounded_participants: list[dict[str, Any]] = []
        for participant_index, participant in enumerate(scene.get("participants") if isinstance(scene.get("participants"), list) else [], 1):
            if not isinstance(participant, dict):
                errors.append({"code": "PARTICIPANT_INVALID", "scene_index": scene_index})
                continue
            name = str(participant.get("name") or "").strip()
            if not name:
                errors.append({"code": "PARTICIPANT_NAME_REQUIRED", "scene_index": scene_index})
            if policy.allowed_participants is not None and name not in policy.allowed_participants:
                errors.append({"code": "PARTICIPANT_NOT_ALLOWED", "name": name})
            evidence = _resolve_list(raw, participant.get("evidence"), f"participant:{name}", errors)
            if policy.require_participant_evidence and not any(name and name in item["text"] for item in evidence):
                errors.append({"code": "PARTICIPANT_EVIDENCE_IDENTITY_MISSING", "name": name})
            grounded_participants.append({"name": name, "evidence": _label(evidence, f"S{scene_index}P{participant_index}E")})
        grounded_actions: list[dict[str, Any]] = []
        for action_index, action in enumerate(scene.get("actions") if isinstance(scene.get("actions"), list) else [], 1):
            source_text = str(action.get("text") or action.get("source_text") or "") if isinstance(action, dict) else ""
            if not source_text:
                errors.append({"code": "ACTION_SOURCE_TEXT_REQUIRED", "scene_index": scene_index})
                continue
            try:
                context_value = action.get("source_evidence") or action.get("context_evidence")
                if context_value:
                    context_span = resolve_exact_evidence_context(raw, context_value)
                    evidence = resolve_child_evidence_within_context(raw, context_span, source_text)
                    grounded_actions.append({"text": source_text, "source_evidence": {**evidence, "evidence_id": f"S{scene_index}A{action_index:03d}"}, "context_evidence": context_span})
                else:
                    evidence = resolve_exact_source_evidence(raw, source_text)
                    grounded_actions.append({"text": source_text, "source_evidence": {**evidence, "evidence_id": f"S{scene_index}A{action_index:03d}"}, "context_evidence": evidence})
            except SourceEvidenceError as exc:
                code = "ACTION_CONTEXT_REQUIRED" if exc.code == "SOURCE_EVIDENCE_AMBIGUOUS" else exc.code
                errors.append({"code": code, "field": f"action:{action_index}", **exc.details})
        grounded_dialogues: list[dict[str, Any]] = []
        for dialogue_index, dialogue in enumerate(scene.get("dialogues") if isinstance(scene.get("dialogues"), list) else [], 1):
            if not isinstance(dialogue, dict):
                errors.append({"code": "DIALOGUE_INVALID", "scene_index": scene_index})
                continue
            speaker = str(dialogue.get("speaker") or "").strip()
            text = str(dialogue.get("text") or "")
            if not speaker or not text:
                errors.append({"code": "DIALOGUE_FIELDS_REQUIRED", "scene_index": scene_index, "dialogue_index": dialogue_index})
                continue
            context_values = dialogue.get("utterance_evidence")
            context_spans = _resolve_list(raw, context_values, f"dialogue:{dialogue_index}.utterance_evidence", errors)
            if not context_spans:
                continue
            if len(context_spans) != 1:
                errors.append({"code": "UTTERANCE_CONTEXT_MUST_BE_UNIQUE", "dialogue_index": dialogue_index})
                continue
            context_span = context_spans[0]
            try:
                utterance = resolve_child_evidence_within_context(raw, context_span, text)
            except SourceEvidenceError as exc:
                errors.append({"code": exc.code, "dialogue_index": dialogue_index, **exc.details})
                continue
            source_form, source_form_error = _resolve_source_form(raw, dialogue, utterance, context_span)
            if source_form_error:
                errors.append({"code": source_form_error, "text": text})
            span_key = (int(utterance["char_start"]), int(utterance["char_end"]))
            if span_key in consumed_dialogue_spans:
                errors.append({"code": "DIALOGUE_SOURCE_SPAN_DUPLICATED", "text": text, "char_start": span_key[0]})
            consumed_dialogue_spans.add(span_key)
            identity = _resolve_list(raw, dialogue.get("speaker_identity_evidence"), f"dialogue:{dialogue_index}.speaker_identity_evidence", errors)
            binding_type = str(dialogue.get("binding_type") or "").strip()
            if not binding_type:
                errors.append({"code": "BINDING_TYPE_REQUIRED", "speaker": speaker})
            if binding_type not in {"SOURCE_LITERAL", "COREFERENCE_RESOLUTION"}:
                errors.append({"code": "BINDING_TYPE_INVALID", "speaker": speaker})
            if binding_type == "SOURCE_LITERAL" and source_form is None:
                errors.append({"code": "SOURCE_LITERAL_RELATION_REQUIRED", "speaker": speaker})
            if binding_type == "COREFERENCE_RESOLUTION" and not dialogue.get("speaker_identity_evidence"):
                errors.append({"code": "COREFERENCE_IDENTITY_EVIDENCE_REQUIRED", "speaker": speaker})
            if not source_form:
                continue
            if binding_type == "SOURCE_LITERAL" and not any(speaker in item["text"] for item in identity):
                errors.append({"code": "SPEAKER_IDENTITY_EVIDENCE_MISSING", "speaker": speaker})
            if binding_type == "COREFERENCE_RESOLUTION" and not dialogue.get("speaker_identity_evidence"):
                errors.append({"code": "SEMANTIC_BINDING_TYPE_REQUIRED", "speaker": speaker})
            grounded_dialogues.append({"speaker": speaker, "text": text, "source_form": source_form, "utterance": {**utterance, "evidence_id": f"S{scene_index}D{dialogue_index:03d}"}, "utterance_evidence": _label(context_spans, f"S{scene_index}D{dialogue_index}U"), "speaker_identity_evidence": _label(identity, f"S{scene_index}D{dialogue_index}I"), "binding_type": binding_type, "binding_classification": "SOURCE_LITERAL_BINDING" if binding_type == "SOURCE_LITERAL" else "AUTHORIZED_SEMANTIC_BINDING", "direct_quote": source_form == SOURCE_FORM_QUOTED_PROSE})
        grounded_scenes.append({"scene_id": str(scene.get("scene_id") or "").strip(), "source_identity_evidence": _label(scene_evidence, f"S{scene_index}I"), "display_label": display_label, "display_label_authority": display_authority, "untrusted_display_label": untrusted_display_label, "participants": grounded_participants, "actions": grounded_actions, "dialogues": grounded_dialogues})
    grounded = {"schema_version": GROUNDED_VERSION, "source_fingerprint": _sha(raw), "source_length": len(raw.encode("utf-8")), "scenes": grounded_scenes, "unknowns": candidate.get("unknowns") if isinstance(candidate.get("unknowns"), list) else [], "validation_status": "PASS" if not errors else "FAIL", "errors": errors}
    return {"status": grounded["validation_status"], "errors": errors, "grounded_candidate": grounded}


def _distance(a: Mapping[str, Any], b: Mapping[str, Any]) -> int:
    a_start, a_end = int(a["char_start"]), int(a["char_end"])
    b_start, b_end = int(b["char_start"]), int(b["char_end"])
    if a_end < b_start:
        return b_start - a_end
    if b_end < a_start:
        return a_start - b_end
    return 0


def reconcile_candidate_v3(raw_source: str, candidate: Any) -> dict[str, Any]:
    """Apply only evidence-preserving, fail-closed transformations."""
    raw = str(raw_source or "")
    if not isinstance(candidate, dict):
        return {"status": "SOURCE_STRUCTURING_RECONCILIATION_FAILED", "errors": [{"code": "CANDIDATE_NOT_OBJECT"},], "transformation_journal": []}
    result = copy.deepcopy(candidate)
    input_candidate_fingerprint = canonical_json_sha256(candidate)
    journal: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for scene_index, scene in enumerate(result.get("scenes") or [], 1):
        if not isinstance(scene, dict):
            continue
        # Labels are never source identity.  Keep an explicit semantic label
        # only as presentation metadata.
        if scene.get("display_label") and scene.get("display_label_authority") != "AUTHORIZED_SEMANTIC_LABEL":
            before = str(scene.get("display_label_authority") or "UNTRUSTED_MODEL_OUTPUT")
            scene["untrusted_display_label"] = scene.get("display_label")
            scene["display_label"] = ""
            scene["display_label_authority"] = "UNRESOLVED"
            journal.append({"transformation": "SCENE_LABEL_DEAUTHORIZED", "scene_index": scene_index, "authority_before": before, "authority_after": "UNRESOLVED", "authority_delta": _authority_delta(before, "UNRESOLVED"), "semantic_change": False})
        participant_evidence: dict[str, list[dict[str, Any]]] = {}
        for participant in scene.get("participants") or []:
            if not isinstance(participant, dict):
                continue
            name = str(participant.get("name") or "")
            participant_evidence[name] = []
            for value in participant.get("evidence") or []:
                try:
                    span = resolve_exact_evidence_context(raw, value)
                except SourceEvidenceError:
                    continue
                if name and name in span["text"]:
                    participant_evidence[name].append(span)
        retained: list[dict[str, Any]] = []
        actions = scene.setdefault("actions", [])
        action_texts = {str(item.get("text") or item.get("source_text") or "") for item in actions if isinstance(item, dict)}
        for dialogue_index, dialogue in enumerate(scene.get("dialogues") or [], 1):
            if not isinstance(dialogue, dict):
                continue
            text = str(dialogue.get("text") or "")
            contexts: list[dict[str, Any]] = []
            for value in dialogue.get("utterance_evidence") or []:
                try:
                    contexts.append(resolve_exact_evidence_context(raw, value))
                except SourceEvidenceError as exc:
                    errors.append({"code": exc.code, "scene_index": scene_index, "dialogue_index": dialogue_index})
            if len(contexts) != 1:
                retained.append(dialogue)
                continue
            context = contexts[0]
            try:
                child = resolve_child_evidence_within_context(raw, context, text)
            except SourceEvidenceError:
                retained.append(dialogue)
                continue
            source_form, _ = _resolve_source_form(raw, dialogue, child, context)
            if source_form is None:
                source_text = context["text"]
                duplicate = source_text in action_texts
                if not duplicate:
                    actions.append({"text": source_text, "source_evidence": source_text, "context_evidence": source_text})
                    action_texts.add(source_text)
                journal.append({"transformation": "EVIDENCE_PRESERVING_DIALOGUE_DEMOTION", "scene_index": scene_index, "dialogue_index": dialogue_index, "source_evidence_ref": context, "authority_before": "SOURCE_FACT", "authority_after": "SOURCE_FACT", "authority_delta": "SAME", "semantic_change": False, "duplicate_action_prevented": duplicate})
                continue
            updated = copy.deepcopy(dialogue)
            updated["source_form"] = source_form
            identity_valid = any(str(dialogue.get("speaker") or "") in str(value) for value in dialogue.get("speaker_identity_evidence") or [])
            if not identity_valid:
                candidates = participant_evidence.get(str(dialogue.get("speaker") or ""), [])
                if not candidates:
                    errors.append({"code": "SPEAKER_IDENTITY_RECOVERY_NOT_PROVABLE", "scene_index": scene_index, "dialogue_index": dialogue_index})
                else:
                    ranked = sorted(candidates, key=lambda value: (_distance(value, context), int(value["char_start"]), int(value["char_end"])))
                    best_distance = _distance(ranked[0], context)
                    tied = [value for value in ranked if _distance(value, context) == best_distance]
                    if len(tied) != 1:
                        errors.append({"code": "SPEAKER_IDENTITY_RECOVERY_AMBIGUOUS", "scene_index": scene_index, "dialogue_index": dialogue_index})
                    else:
                        updated["speaker_identity_evidence"] = [tied[0]["text"]]
                        journal.append({"transformation": "SPEAKER_IDENTITY_EVIDENCE_RECOVERY", "scene_index": scene_index, "dialogue_index": dialogue_index, "source_evidence_ref": tied[0], "authority_before": "SOURCE_FACT", "authority_after": "SOURCE_FACT", "authority_delta": "SAME", "semantic_change": False, "distance": best_distance})
            retained.append(updated)
        scene["dialogues"] = retained
    if errors:
        return {"status": "SOURCE_STRUCTURING_RECONCILIATION_FAILED", "errors": errors, "candidate": result, "transformation_journal": journal, "reconciliation_status": "FAILED"}
    output_candidate_fingerprint = canonical_json_sha256(result)
    evidence = {"policy_version": "source_structuring_reconciliation_v3", "transformations": journal, "input_candidate_fingerprint": input_candidate_fingerprint, "output_candidate_fingerprint": output_candidate_fingerprint}
    return {"status": "SOURCE_STRUCTURING_RECONCILIATION_PASS", "errors": [], "candidate": result, "transformation_journal": journal, "reconciliation_status": "PASS", "reconciliation_fingerprint": reconciliation_fingerprint(policy_version=evidence["policy_version"], transformations=journal, input_candidate_fingerprint=input_candidate_fingerprint, output_candidate_fingerprint=output_candidate_fingerprint), "reconciliation_evidence": evidence, "provider_calls": 0, "production_writes": 0}


def migrate_candidate_v2_to_v3(raw_source: str, candidate_v2: Any) -> dict[str, Any]:
    """Provider-free migration; semantic fields are copied, labels are cleared."""
    if not isinstance(candidate_v2, dict):
        return {"status": "CANARY_V2_TO_V3_MIGRATION_NOT_PROVEN", "errors": [{"code": "CANDIDATE_NOT_OBJECT"}]}
    scenes: list[dict[str, Any]] = []
    for scene in candidate_v2.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        scenes.append({
            "scene_evidence": list(scene.get("scene_evidence") or []),
            "display_label": "",
            "display_label_authority": "UNRESOLVED",
            "participants": [{"name": str(item.get("name") or ""), "evidence": list(item.get("evidence") or [])} for item in scene.get("participants") or [] if isinstance(item, dict)],
            "actions": [{"text": str(item.get("text") or item.get("source_text") or ""), "source_evidence": item.get("source_evidence") or item.get("source_text"), "context_evidence": item.get("context_evidence") or item.get("source_evidence") or item.get("source_text")} for item in scene.get("actions") or [] if isinstance(item, dict) and (item.get("source_text") or item.get("text"))],
            "dialogues": [copy.deepcopy(item) for item in scene.get("dialogues") or [] if isinstance(item, dict)],
        })
    candidate = {"schema_version": SCHEMA_VERSION_V3_1, "scenes": scenes, "unknowns": list(candidate_v2.get("unknowns") or [])}
    reconciliation = reconcile_candidate_v3(raw_source, candidate)
    if reconciliation.get("status") != "SOURCE_STRUCTURING_RECONCILIATION_PASS":
        return {"status": "CANARY_V2_TO_V3_MIGRATION_NOT_PROVEN", "errors": reconciliation.get("errors", []), "candidate": reconciliation.get("candidate"), "transformation_journal": reconciliation.get("transformation_journal", []), "reconciliation_fingerprint": reconciliation.get("reconciliation_fingerprint", "")}
    grounded = ground_candidate_v3(raw_source, reconciliation["candidate"])
    return {"status": "PASS" if grounded.get("status") == "PASS" else "CANARY_V2_TO_V3_MIGRATION_NOT_PROVEN", "candidate": reconciliation["candidate"], "grounded_candidate": grounded.get("grounded_candidate"), "grounding": grounded, "transformation_journal": reconciliation.get("transformation_journal", []), "reconciliation_fingerprint": reconciliation.get("reconciliation_fingerprint", ""), "provider_calls": 0, "production_writes": 0}


def canonical_script_payload_v3(grounded: Any, *, identity_context: SourceIdentityContext | None = None, source_lineage: SourceLineageContext | None = None) -> dict[str, Any]:
    if not isinstance(grounded, dict) or grounded.get("schema_version") not in {GROUNDED_VERSION, GROUNDED_VERSION_V3_1} or grounded.get("validation_status") != "PASS":
        raise ValueError("GROUNDED_CANDIDATE_V3_REQUIRED")
    context = identity_context or SourceIdentityContext()
    scenes: list[dict[str, Any]] = []
    for index, scene in enumerate(grounded.get("scenes") or [], 1):
        scene_id = str(scene.get("scene_id") or "").strip() or context.scene_id(index)
        participants = [{"id": p["name"], "character_id": p["name"], "name": p["name"], "evidence": p.get("evidence", [])} for p in scene.get("participants") or []]
        actions = [{"action_id": f"{scene_id}_A{n:03d}", "text": item.get("text") or item["source_evidence"]["text"], "source_evidence": item["source_evidence"], "context_evidence": item.get("context_evidence") or item["source_evidence"]} for n, item in enumerate(scene.get("actions") or [], 1)]
        dialogues = [{"dialogue_id": f"{scene_id}_D{n:03d}", "speaker": item["speaker"], "text": item["text"], "assertion_mode": "", "source_form": item.get("source_form"), "source_evidence": item["utterance"], "speaker_binding": {"classification": item["binding_classification"], "binding_type": item["binding_type"], "identity_evidence": item["speaker_identity_evidence"], "utterance_evidence": item["utterance_evidence"]}} for n, item in enumerate(scene.get("dialogues") or [], 1)]
        timeline_items = [(a["source_evidence"]["char_start"], "ACTION", a["action_id"]) for a in actions] + [(d["source_evidence"]["char_start"], "DIALOGUE", d["dialogue_id"]) for d in dialogues]
        if len({position for position, _, _ in timeline_items}) != len(timeline_items):
            raise ValueError("SOURCE_TIMELINE_ORDER_UNRESOLVED")
        timeline_items.sort(key=lambda item: int(item[0]))
        blocks = [{"order": (n + 1) * 10, "type": kind, "ref": ref} for n, (_, kind, ref) in enumerate(timeline_items)]
        scenes.append({"scene_id": scene_id, "name": "", "display_name": scene.get("display_label", ""), "display_name_authority": scene.get("display_label_authority", "UNRESOLVED"), "untrusted_display_label": scene.get("untrusted_display_label", ""), "source_identity_evidence": scene.get("source_identity_evidence", []), "location_name": "", "location_authority": "UNRESOLVED", "location_evidence": None, "participants": participants, "actions": actions, "dialogues": dialogues, "scene_evidence": scene.get("source_identity_evidence", []), "script_blocks": blocks, "timeline_origin": "SOURCE_GROUNDED", "timeline_authority": "SOURCE_EVIDENCE_ORDER", "production_eligible": True})
    body = {"schema_version": PAYLOAD_SCHEMA_VERSION_V3_1, "source_grounded_schema_version": PAYLOAD_SCHEMA_VERSION_V3_1, "origin_source_raw_hash": grounded["source_fingerprint"], "scenes": scenes, "scene_transitions": []}
    canonical_fingerprint = canonical_json_sha256(body)
    body["canonical_script_payload_fingerprint"] = canonical_fingerprint
    if source_lineage is not None:
        lineage = source_lineage.to_dict()
        lineage["canonical_script_payload_fingerprint"] = canonical_fingerprint
        body["source_lineage"] = lineage
    return body


__all__ = ["SCHEMA_VERSION", "GROUNDED_VERSION", "PAYLOAD_SCHEMA_VERSION", "SCHEMA_VERSION_V3_1", "GROUNDED_VERSION_V3_1", "PAYLOAD_SCHEMA_VERSION_V3_1", "SOURCE_FORM_QUOTED_PROSE", "SOURCE_FORM_SPEAKER_LABELED", "SOURCE_FORM_STRUCTURED_DIALOGUE_BLOCK", "SOURCE_FORMS", "AUTHORITY_LATTICE", "SourceStructuringPolicy", "SourceIdentityContext", "resolve_exact_evidence_context", "resolve_child_evidence_within_context", "ground_candidate_v3", "reconcile_candidate_v3", "migrate_candidate_v2_to_v3", "canonical_script_payload_v3"]
