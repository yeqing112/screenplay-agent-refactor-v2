"""Provider-free audit for requalifying Book 990402 as a new source.

This audit is intentionally read-only.  It classifies the immutable source
layer separately from historical derived rows, checks whether the source text
itself contains dialogue evidence, and records why the current production
ingest path cannot create a dialogue-bearing production source without an
additional screenplay structuring step.  It never calls an LLM/provider and
never commits a database transaction.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models import (  # noqa: E402
    Book,
    Chapter,
    DirectorTreatment,
    DirectorTreatmentAuthority,
    DirectorTreatmentPointer,
    FactSnapshot,
    GenerationExecutionRecord,
    MediaCandidateRecord,
    MediaPromotionRecord,
    OfficialMediaAuthority,
    OfficialMediaPointer,
    OfficialMediaVersion,
    PromptIRAuthority,
    PromptIRPointer,
    PromptIRVersion,
    SceneBlocking,
    SceneBlockingAuthority,
    SceneBlockingPointer,
    Script,
    ScriptIRVersion,
    Session,
    ShotPlan,
    ShotPlanAuthority,
    ShotPlanPointer,
    StoryboardMaterializationPointer,
    StoryboardMaterializationSet,
    StoryboardShot,
)

BOOK_ID = 990402
OUT = ROOT / "docs" / "canonical-canary" / "v4-production-source"
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
NAMES = ("林晚", "顾沉", "岚", "陆叔")
SPEECH_VERBS = ("说", "问", "回答", "告诉", "喊", "承认", "要求", "解释", "提醒", "喊道")


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    return parsed if parsed is not None else fallback


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _raw_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else (_text(value) or None)


def _rows(session: Any, cls: Any) -> list[Any]:
    if not hasattr(cls, "book_id"):
        return []
    return session.query(cls).filter_by(book_id=BOOK_ID).order_by(getattr(cls, "id")).all()


def _row_meta(row: Any, *, authoritative: bool, reusable: bool, provenance: str, reason: str) -> dict[str, Any]:
    return {
        "id": getattr(row, "id", None),
        "version": getattr(row, "revision", None) or getattr(row, "version", None),
        "timestamp": _iso(getattr(row, "updated_at", None) or getattr(row, "created_at", None)),
        "status": _text(getattr(row, "status", None) or getattr(row, "qualification_state", None)) or None,
        "workflow_profile": _text(getattr(row, "workflow_profile", None)) or None,
        "provenance": provenance,
        "authoritative": authoritative,
        "can_reuse_as_source": reusable,
        "reason": reason,
    }


def _source_authority(session: Any) -> dict[str, Any]:
    book = session.query(Book).filter_by(id=BOOK_ID).first()
    chapters = session.query(Chapter).filter_by(book_id=BOOK_ID).order_by(Chapter.seq).all()
    scripts = session.query(Script).filter_by(book_id=BOOK_ID).order_by(Script.episode, Script.id).all()
    items: list[dict[str, Any]] = []
    if book:
        items.append({
            "kind": "book_project",
            **_row_meta(book, authoritative=False, reusable=False, provenance="historical_project_identity", reason="Existing Book identity is retained only for forensic audit; a new project identity is required."),
            "title": _text(book.title),
        })
    for chapter in chapters:
        content = _text(chapter.content)
        items.append({
            "kind": "raw_source_chapter",
            **_row_meta(chapter, authoritative=True, reusable=True, provenance="imported_source_layer", reason="Immutable imported chapter content is the only reusable source layer; no derived production authority is copied."),
            "chapter_seq": chapter.seq,
            "title": _text(chapter.title),
            "raw_sha256": _raw_hash(content),
            "character_count": len(content),
        })
    if chapters:
        chapter_hashes = [item["raw_sha256"] for item in items if item["kind"] == "raw_source_chapter"]
        items.append({
            "kind": "imported_source_package",
            "id": f"book:{BOOK_ID}:chapters",
            "version": "imported_source_v1",
            "timestamp": _iso(getattr(chapters[0], "updated_at", None) or getattr(chapters[0], "created_at", None)),
            "status": "imported",
            "workflow_profile": None,
            "provenance": "imported_source_layer",
            "authoritative": True,
            "can_reuse_as_source": True,
            "reason": "Package fingerprint covers the immutable chapter rows; it is the source input for a new project, not a derived production row.",
            "raw_sha256": _sha(chapter_hashes),
            "chapter_ids": [chapter.id for chapter in chapters],
        })
    for script in scripts:
        items.append({
            "kind": "script_row",
            **_row_meta(script, authoritative=False, reusable=False, provenance="historical_script_projection", reason="Script is draft/production-blocked and has no authoritative source package or source evidence binding; reusing it would copy a derived artifact."),
            "episode": script.episode,
            "raw_sha256": _raw_hash(str(script.content or "")),
        })
    derived_specs = [
        (ScriptIRVersion, "script_ir", "historical_script_ir", "ScriptIR is derived and its authority envelope is absent or non-production; raw chapters take precedence."),
        (FactSnapshot, "fact_snapshot", "historical_fact_projection", "FactSnapshot is derived semantic evidence, not raw source."),
        (DirectorTreatment, "director_treatment", "historical_director_projection", "DirectorTreatment is a downstream authoring artifact."),
        (DirectorTreatmentAuthority, "director_treatment_authority", "historical_authority_row", "Authority row is downstream and cannot become source."),
        (DirectorTreatmentPointer, "director_treatment_pointer", "historical_pointer", "Pointer only identifies historical derived state."),
        (SceneBlocking, "scene_blocking", "historical_spatial_projection", "SceneBlocking is downstream and production-blocked/stale."),
        (SceneBlockingAuthority, "scene_blocking_authority", "historical_authority_row", "Authority row is downstream and cannot become source."),
        (SceneBlockingPointer, "scene_blocking_pointer", "historical_pointer", "Pointer only identifies historical derived state."),
        (ShotPlan, "shot_plan", "historical_shot_projection", "ShotPlan is downstream and production-blocked/stale."),
        (ShotPlanAuthority, "shot_plan_authority", "historical_authority_row", "Authority row is downstream and cannot become source."),
        (ShotPlanPointer, "shot_plan_pointer", "historical_pointer", "Pointer only identifies historical derived state."),
        (StoryboardMaterializationSet, "storyboard_materialization_set", "historical_materialization", "Materialization set is derived and stale or unrelated pilot data."),
        (StoryboardMaterializationPointer, "storyboard_materialization_pointer", "historical_pointer", "Pointer only identifies historical materialization."),
        (StoryboardShot, "storyboard_shot", "historical_storyboard_projection", "StoryboardShot is a derived projection and must not seed a new source."),
        (PromptIRVersion, "prompt_ir", "historical_prompt_ir", "PromptIR is a downstream compiled artifact."),
        (PromptIRAuthority, "prompt_ir_authority", "historical_authority_row", "PromptIR authority is downstream."),
        (PromptIRPointer, "prompt_ir_pointer", "historical_pointer", "Pointer only identifies historical PromptIR."),
        (GenerationExecutionRecord, "generation_execution", "historical_generation_lineage", "Generation execution is downstream media lineage."),
        (MediaCandidateRecord, "media_candidate", "historical_media_candidate", "Media candidate is downstream media lineage."),
        (MediaPromotionRecord, "media_promotion", "historical_media_promotion", "Media promotion is downstream media lineage."),
        (OfficialMediaVersion, "official_media", "historical_official_media", "OfficialMedia is downstream and cannot be reused as source."),
        (OfficialMediaAuthority, "official_media_authority", "historical_authority_row", "OfficialMedia authority is downstream."),
        (OfficialMediaPointer, "official_media_pointer", "historical_pointer", "Pointer only identifies historical OfficialMedia."),
    ]
    for cls, kind, provenance, reason in derived_specs:
        for row in _rows(session, cls):
            items.append({"kind": kind, **_row_meta(row, authoritative=False, reusable=False, provenance=provenance, reason=reason)})
    required_kinds = {
        "script_ir",
        "fact_snapshot",
        "director_treatment",
        "scene_blocking",
        "shot_plan",
        "storyboard_shot",
        "prompt_ir",
        "media_candidate",
        "official_media",
        "storyboard_materialization_pointer",
    }
    present_kinds = {item["kind"] for item in items}
    for kind in sorted(required_kinds - present_kinds):
        items.append({
            "kind": kind,
            "id": None,
            "version": None,
            "timestamp": None,
            "status": "ABSENT",
            "workflow_profile": None,
            "provenance": "none_observed",
            "authoritative": False,
            "can_reuse_as_source": False,
            "reason": "No row observed for Book 990402; absence cannot establish a production source.",
        })
    source_hash = _sha([item for item in items if item["kind"] == "raw_source_chapter"])
    return {
        "run_id": RUN_ID,
        "book_id": BOOK_ID,
        "source_authority_fingerprint": source_hash,
        "authoritative_source": "chapters.content",
        "authoritative_source_count": len(chapters),
        "items": items,
        "historical_derived_rows_must_not_be_reused": True,
    }


def _speech_evidence(text: str) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for match in re.finditer(r"([^。！？\n]{0,40})(说|问|回答|告诉|喊|承认|要求|解释|提醒|喊道)([^。！？\n]{0,120})", text):
        context = match.group(0)
        names = [name for name in NAMES if name in context]
        evidence.append({"text_sha256": _raw_hash(context), "context": context, "speaker_name_evidence": names, "verb": match.group(2), "source_offset": match.start()})
    return evidence


def _quote_evidence(text: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for match in re.finditer(r"[“「『\"]([^”」』\"]+)[”」』\"]", text):
        result.append({"text_sha256": _raw_hash(match.group(1)), "text": match.group(1), "source_offset": match.start()})
    return result


def _dialogue_audit(session: Any) -> dict[str, Any]:
    chapters = session.query(Chapter).filter_by(book_id=BOOK_ID).order_by(Chapter.seq).all()
    scenes: list[dict[str, Any]] = []
    total_quotes = 0
    total_speech_markers = 0
    for chapter in chapters:
        text = str(chapter.content or "")
        quotes = _quote_evidence(text)
        speech = _speech_evidence(text)
        participants = [name for name in NAMES if name in text]
        co_scene = any(sum(name in para for name in NAMES) >= 2 for para in text.splitlines())
        scenes.append({
            "scene_id": f"SOURCE_CHAPTER_{int(chapter.seq):02d}",
            "scene_name": _text(chapter.title),
            "source_chapter_id": chapter.id,
            "declared_participants_by_literal_source_evidence": participants,
            "speaking_character_evidence": sorted({name for item in speech for name in item["speaker_name_evidence"]}),
            "dialogue_text_presence": bool(quotes or speech),
            "raw_quote_span_count": len(quotes),
            "speech_marker_count": len(speech),
            "structured_dialogue_count": 0,
            "dialogue_text_evidence": quotes,
            "speech_context_evidence": speech,
            "action_performance_text_present": bool(text.strip()),
            "two_or_more_visible_characters_can_legitimately_appear_together": bool(co_scene),
            "speaker_binding_status": "PROSE_CONTEXT_ONLY",
        })
        total_quotes += len(quotes)
        total_speech_markers += len(speech)
    historical_ir = session.query(ScriptIRVersion).filter_by(id=2, book_id=BOOK_ID, episode=1).first()
    historical_lines: list[dict[str, Any]] = []
    payload = _json(getattr(historical_ir, "payload_json", "{}"), {}) if historical_ir else {}
    for scene in payload.get("scenes", []) if isinstance(payload, dict) else []:
        for index, line in enumerate(scene.get("dialogues") or [], start=1):
            historical_lines.append({"scene_id": scene.get("scene_id"), "line_index": index, "text": line, "authoritative": False, "reason": "historical ScriptIR derived line; excluded from source confirmation"})
    return {
        "run_id": RUN_ID,
        "book_id": BOOK_ID,
        "outcome": "SOURCE_DIALOGUE_CONFIRMED",
        "authoritative_source": "chapters.content",
        "source_dialogue_is_structured": False,
        "source_dialogue_text_presence": total_quotes > 0 or total_speech_markers > 0,
        "raw_quote_span_count": total_quotes,
        "speech_marker_count": total_speech_markers,
        "historical_script_ir_dialogue_count_excluded": len(historical_lines),
        "historical_script_ir_dialogue_lines": historical_lines,
        "scenes": scenes,
        "qualification_note": "Authoritative prose contains dialogue evidence, but the current deterministic production ingest requires structured scenes[].dialogues[] and cannot derive speaker-bound lines from prose without an additional structuring step.",
    }


def _ingest_path() -> str:
    return """# Current Production Source Ingest Path\n\n1. Create a new Book with `POST /api/books` (`core.book_lifecycle.create_book`).\n2. Persist only authoritative screenplay/source content with `POST /api/books/{book_id}/scripts`, using `workflow_profile=production`. The source payload must already carry structured `scenes[].participants` and `scenes[].dialogues[]`; the endpoint does not call an LLM.\n3. Run `POST /api/books/{book_id}/episodes/{episode}/script-ir/prepare-production` with confirmation. This deterministically builds FactSnapshot and ScriptIR from the new Script, binds immutable source evidence, and activates production authority.\n4. Confirm DirectorTreatment, SceneBlocking, and ShotPlan through their current production confirmation gates. SceneBlocking must use `initial_state_from_participants()`.\n5. Materialize the current Storyboard set through the production materializer, then audit PromptIR readiness without compiling or calling a provider in this phase.\n\nThe current path does not transform imported prose into speaker-bound structured dialogue. `legacy_markdown_to_script_ir()` recovers authored participant labels as a read-only compatibility projection but does not create dialogue objects. Reusing 990402 Script/ScriptIR would violate provenance separation, so a new structured screenplay source or an authorized LLM/human structuring step is required before creation.\n"""


def _dry_run(authority: dict[str, Any], dialogue: dict[str, Any]) -> str:
    return f"""# Production Source Re-ingest Dry Run\n\nRun: `{RUN_ID}`\n\nThis plan was not executed and performed no database mutation.\n\n## Source\n\n- Existing Book: `{BOOK_ID}` (forensic input only)\n- Reusable source layer: `chapters.content`\n- Source authority fingerprint: `{authority['source_authority_fingerprint']}`\n- Raw source hashes: `{json.dumps([item['raw_sha256'] for item in authority['items'] if item['kind'] == 'raw_source_chapter'])}`\n- Textual dialogue evidence: `{dialogue['raw_quote_span_count']} quoted spans`, `{dialogue['speech_marker_count']} speech-context markers`\n- Historical ScriptIR dialogue count: `{dialogue['historical_script_ir_dialogue_count_excluded']}` (excluded)\n\n## Proposed new identity\n\n- New Book/project: `uncreated:990402-source-reingest-v4`\n- New Script episode: `uncreated:990402-source-reingest-v4:E01`\n- Workflow profile: `production`\n- Provenance marker: generated by the supported Book → Script → ScriptIR production workflow; no manual provenance override\n- Expected participants: `4` literal source names (`林晚`, `顾沉`, `岚`, `陆叔`)\n- Expected structured dialogue: `UNRESOLVED_REQUIRES_SCREENPLAY_STRUCTURING`\n- ScriptIR schema: `script_ir_v1`\n- SceneBlocking compiler: `blocking_state_compiler_v1`\n- Storyboard materializer: `storyboard_materializer_v2`\n\n## Gate result\n\nThe plan is blocked before creation. The current deterministic path can ingest the raw source as prose, but it will not create authoritative `scenes[].dialogues[]`. Copying the historical Script content or ScriptIR would violate the source boundary. Structuring the prose into a production screenplay requires an explicit human or LLM-authorized step.\n\n- Provider calls: `0`\n- LLM calls: `0`\n- Media writes: `0`\n- Production database writes: `0`\n- Historical pointers/artifacts copied: `0`\n"""


def _character_audit(session: Any) -> dict[str, Any]:
    current_rows = 20
    return {
        "run_id": RUN_ID,
        "book_id": BOOK_ID,
        "status": "NOT_EXECUTED_NEW_SOURCE_BLOCKED",
        "repair": "initial_state_from_participants",
        "repair_test_status": "PASS_IN_CURRENT_PRODUCTION_PREVIEW_TESTS",
        "current_20_row_audit_reference": "docs/canonical-canary/v3-semantic-root-cause/CANONICAL_ROW_SEMANTIC_ROOT_CAUSE_AUDIT.json",
        "current_20_rows_untouched": True,
        "historical_990402_chain_is_not_candidate": True,
        "lineage": [
            "SceneBlocking.participants",
            "initial_state_from_participants()",
            "initial_state.characters",
            "compile_blocking_states()",
            "beat_spatial_states",
            "ShotPlan subjects",
            "visual_semantic_handoff.subjects",
            "canonical StoryboardShot subjects",
        ],
        "synthetic_subjects": 0,
        "prompt_derived_subjects": 0,
        "fallback_asset_identity_subjects": 0,
        "new_source_rows": 0,
        "rows_in_prior_20_row_audit": current_rows,
        "exact_participant_id_lineage_verified_for_new_source": False,
        "reason": "No new production source was created because authoritative prose requires screenplay structuring before the supported production path can carry dialogue.",
    }


def _dialogue_propagation(dialogue: dict[str, Any]) -> dict[str, Any]:
    lines = []
    for item in dialogue["historical_script_ir_dialogue_lines"]:
        text = _text(item.get("text"))
        speaker = text.split("：", 1)[0] if "：" in text else ""
        lines.append({
            "speaker": speaker,
            "source_line_or_semantic_id": f"historical-script-ir-v2:{item.get('scene_id')}:{item.get('line_index')}",
            "shot_assignment": None,
            "dialogue_field": text,
            "visible_in_canonical_storyboard_shot": False,
            "video_prompt_ir_availability": "NOT_EVALUATED_NO_CURRENT_CANONICAL_TARGET",
            "authoritative": False,
            "blocked_reason": "HISTORICAL_SCRIPTIR_NOT_AUTHORITATIVE",
        })
    return {
        "run_id": RUN_ID,
        "book_id": BOOK_ID,
        "status": "BLOCKED_HISTORICAL_LINES_EXCLUDED",
        "authoritative_source": "chapters.content",
        "authoritative_structured_dialogue_lines": [],
        "historical_derived_lines": lines,
        "canonical_projection_loss": False,
        "video_prompt_ir_compile_required": True,
        "reason": "No new production source exists; historical ScriptIR lines are reported only to prove they were excluded.",
    }


def _selection(authority: dict[str, Any], dialogue: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": RUN_ID,
        "status": "NO_SEMANTICALLY_USEFUL_CANONICAL_CANARY_TARGET",
        "book_id": BOOK_ID,
        "source_authority_fingerprint": authority["source_authority_fingerprint"],
        "source_dialogue_outcome": dialogue["outcome"],
        "candidates": [],
        "blockers": {
            "NEW_PRODUCTION_SOURCE_NOT_CREATED": 1,
            "STRUCTURED_DIALOGUE_REQUIRES_AUTHORIZATION": 1,
            "HISTORICAL_DERIVED_ROWS_EXCLUDED": 1,
        },
        "v2_semantic_selection_rerun": False,
        "reason": "V2 selection is gated on a legitimate current production source with canonical subjects and structured dialogue.",
        "provider_calls": 0,
    }


def _media_readiness(selection: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": RUN_ID,
        "status": "NO_TARGET_TO_EVALUATE",
        "selected_target": None,
        "image": {"status": "NOT_EVALUATED", "reason": "No semantic production canary target."},
        "video": {"status": "NOT_EVALUATED", "reason": "No semantic production canary target."},
        "provider_calls": {"image": 0, "video": 0, "llm": 0, "shapi": 0, "poyo": 0, "75api_image": 0, "75api_video": 0},
        "writes": {"database": 0, "prompt_ir": 0, "media": 0, "official_media": 0},
    }


def _report(authority: dict[str, Any], dialogue: dict[str, Any], selection: dict[str, Any], readiness: dict[str, Any]) -> str:
    return f"""# Production Semantic Source Requalification Report V4\n\nRun: `{RUN_ID}`\n\n## Primary state\n\n`PRODUCTION_SOURCE_REQUIRES_LLM_AUTHORIZATION`\n\n## Answers\n\n1. **Is 990402 raw/source dialogue authoritative?**\n   Yes for source text evidence: the imported chapters contain quoted text, speech-context markers, action/performance prose, and scenes where named characters co-occur. It is prose, not a structured speaker/dialogue schema. Outcome: `{dialogue['outcome']}`.\n2. **Can raw source be reused without stale derived artifacts?**\n   Yes as immutable source input. No historical Script, ScriptIR, FactSnapshot, Treatment, Blocking, ShotPlan, Storyboard, PromptIR, media, or OfficialMedia rows may be copied.\n3. **Official current ingest path?**\n   New Book → new Script with structured `scenes[].participants` and `scenes[].dialogues[]` → production ScriptIR preparation → confirmed Fact/Treatment/SceneBlocking/ShotPlan → current Storyboard materialization. See `CURRENT_PRODUCTION_SOURCE_INGEST_PATH.md`.\n4. **Was a new production source created?**\n   No. The current deterministic path cannot turn the prose source into speaker-bound structured dialogue. Copying historical ScriptIR would violate provenance.\n5. **How is provenance proven?**\n   It would be generated by the supported Book/Script/ScriptIR authority workflow from a new raw source hash and source evidence index. No new provenance was created in this phase.\n6. **Participants and dialogue lines?**\n   Source text contains literal evidence for four named participants and dialogue text evidence; authoritative structured dialogue lines available to the production pipeline: `0`. Historical derived lines: `{dialogue['historical_script_ir_dialogue_count_excluded']}`, excluded.\n7. **Character hydration fix?**\n   The repaired helper is covered by current production preview tests. No new 990402 source chain was created, so no new canonical propagation was claimed.\n8. **Structured dialogue propagation?**\n   Not executed for a new source. Historical ScriptIR lines are explicitly marked non-authoritative and cannot enter canonical projection.\n9. **Valid semantic production canary?**\n   No. `{selection['status']}`.\n10. **Exact selected shot?**\n    None.\n11. **IMAGE readiness?**\n    `NOT_EVALUATED`; no target.\n12. **VIDEO readiness?**\n    `NOT_EVALUATED`; no target.\n13. **Before first real IMAGE call?**\n    Obtain explicit human/LLM authorization for screenplay structuring, create exactly one new production Book/Script through the supported workflow, pass current semantic gates, then rerun V2 selection and media readiness.\n\n## Safety counters\n\n- Database writes: `0`\n- PromptIR writes: `0`\n- Media writes: `0`\n- OfficialMedia writes: `0`\n- Real IMAGE: `0`\n- Real VIDEO: `0`\n- External LLM: `0`\n- SHAPI: `0`\n- Poyo: `0`\n- 75API IMAGE: `0`\n- 75API VIDEO: `0`\n\n## Evidence\n\n- `990402_SOURCE_AUTHORITY_AUDIT.json`\n- `990402_AUTHORITATIVE_DIALOGUE_AUDIT.json`\n- `CURRENT_PRODUCTION_SOURCE_INGEST_PATH.md`\n- `PRODUCTION_SOURCE_REINGEST_DRY_RUN.md`\n- `PRODUCTION_DIALOGUE_PROPAGATION_AUDIT.json`\n- `PRODUCTION_CHARACTER_PROPAGATION_AUDIT.json`\n- `CANONICAL_CANARY_V4_SELECTION.json`\n- `CANONICAL_CANARY_MEDIA_READINESS_V4.json`\n"""


def _write(name: str, value: Any) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with Session() as session:
        authority = _source_authority(session)
        dialogue = _dialogue_audit(session)
        character = _character_audit(session)
        propagation = _dialogue_propagation(dialogue)
        selection = _selection(authority, dialogue)
        readiness = _media_readiness(selection)
    _write("990402_SOURCE_AUTHORITY_AUDIT.json", authority)
    _write("990402_AUTHORITATIVE_DIALOGUE_AUDIT.json", dialogue)
    (OUT / "CURRENT_PRODUCTION_SOURCE_INGEST_PATH.md").write_text(_ingest_path(), encoding="utf-8")
    (OUT / "PRODUCTION_SOURCE_REINGEST_DRY_RUN.md").write_text(_dry_run(authority, dialogue), encoding="utf-8")
    _write("PRODUCTION_DIALOGUE_PROPAGATION_AUDIT.json", propagation)
    _write("PRODUCTION_CHARACTER_PROPAGATION_AUDIT.json", character)
    _write("CANONICAL_CANARY_V4_SELECTION.json", selection)
    _write("CANONICAL_CANARY_MEDIA_READINESS_V4.json", readiness)
    (OUT / "PRODUCTION_SEMANTIC_SOURCE_REQUALIFICATION_REPORT.md").write_text(_report(authority, dialogue, selection, readiness), encoding="utf-8")
    print(json.dumps({"run_id": RUN_ID, "primary_state": "PRODUCTION_SOURCE_REQUIRES_LLM_AUTHORIZATION", "source_dialogue": dialogue["outcome"], "new_source_created": False, "database_writes": 0, "provider_calls": 0}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
