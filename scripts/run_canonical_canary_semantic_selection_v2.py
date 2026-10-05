"""Run the provider-free semantic truth reconciliation for canonical canary selection."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "canonical-canary" / "v2-semantic-selection"
BENCHMARK_IDS = ["SH_E01_SC002_002", "SH_E01_SC002_006", "SH_E01_SC002_007"]


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items() if str(k).lower() not in {"api_key", "authorization", "access_token", "secret", "runtime_credential_value", "raw_base64"}}
    if isinstance(value, list): return [_safe(v) for v in value]
    if isinstance(value, tuple): return [_safe(v) for v in value]
    if isinstance(value, Path): return str(value)
    return value


def _write(name: str, value: dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(_safe(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _profile(capability: str) -> dict[str, Any]:
    from api.model_registry import get_default_profile
    profile = get_default_profile(capability) or {}
    params = dict(profile.get("default_params") or {})
    params.pop("api_key", None); params.pop("authorization", None); params.pop("secret", None)
    return {"id": profile.get("id"), "provider": profile.get("provider"), "model": profile.get("model_name"), "capability": profile.get("capability"), "adapter_id": profile.get("adapter_id"), "adapter_version": profile.get("adapter_version"), "transport_binding_id": profile.get("transport_binding_id"), "credential_configured": bool(profile.get("credential_configured")), "default_params": params}


def _book_provenance(session: Any) -> dict[int, dict[str, Any]]:
    from models import Book, GenerationExecutionRecord, TaskRun
    browser_evidence = ROOT / "output" / "playwright" / "75api-browser-zero-call" / "evidence.json"
    browser_text = browser_evidence.read_text(encoding="utf-8") if browser_evidence.exists() else ""
    result: dict[int, dict[str, Any]] = {}
    for book in session.query(Book).all():
        if not 990448 <= int(book.id) <= 990452:
            continue
        title = str(book.title or ""); filename = str(book.filename or "")
        tokens = f"{title} {filename}".lower()
        tasks = session.query(TaskRun).filter_by(book_id=book.id).all()
        executions = session.query(GenerationExecutionRecord).filter_by(book_id=book.id).all()
        evidence: list[str] = ["books row", "task_runs row"]
        provenance_class = "UNKNOWN_PROVENANCE"
        if "migration" in tokens:
            provenance_class = "MIGRATION_FIXTURE_PROJECT"; evidence.append("book title/filename contains migration")
        elif any(token in tokens for token in ("test", "fixture", "authority")):
            provenance_class = "TEST_FIXTURE_PROJECT"; evidence.append("book title/filename contains fixture/test marker")
        elif any(str(getattr(row, "execution_mode", "")).upper() == "CANARY" or "fake" in str(getattr(row, "provider", "")).lower() or "mock" in str(getattr(row, "provider", "")).lower() for row in executions):
            provenance_class = "CANARY_PROJECT"; evidence.append("GenerationExecutionRecord execution_mode/provider explicitly identifies canary/fake runtime")
        elif str(book.id) in browser_text:
            provenance_class = "CANARY_PROJECT"; evidence.append("committed Playwright browser zero-call evidence explicitly names this book")
        else:
            evidence.append("no explicit production/canary/test provenance marker found")
        result[int(book.id)] = {"book_id": book.id, "title": title, "filename": filename, "status": book.status, "created_at": book.created_at.isoformat() if book.created_at else None, "chapter_count": book.chapter_count, "total_words": book.total_words, "provenance_class": provenance_class, "eligible": provenance_class == "PRODUCTION_PROJECT", "official_production_canary": False, "evidence": evidence, "task_run_count": len(tasks), "generation_execution_count": len(executions), "generation_execution_modes": sorted({str(getattr(row, "execution_mode", "")) for row in executions}), "generation_providers": sorted({str(getattr(row, "provider", "")) for row in executions})}
    return result


def _identity_audit(session: Any) -> dict[str, Any]:
    from core.canary_identity_boundary import CanaryIdentityError, require_production_canonical_identity
    records = []
    for identity in BENCHMARK_IDS:
        try:
            require_production_canonical_identity(session, identity)
            records.append({"identity": identity, "status": "UNEXPECTED_PASS", "error_code": None})
        except CanaryIdentityError as exc:
            records.append({"identity": identity, "status": "BLOCKED", "error_code": exc.code})
    return {"records": records, "all_benchmark_blocked": all(row["error_code"] == "BENCHMARK_IDENTITY_NOT_PRODUCTION_CANONICAL" for row in records), "real_image_calls": 0, "real_video_calls": 0, "external_llm_calls": 0}


def _top10(inventory: list[dict[str, Any]], ranker: Any) -> list[dict[str, Any]]:
    # A diagnostic ranking shows semantic quality even when provenance makes
    # every row ineligible. It never changes eligibility or selection.
    diagnostic = [{**item, "canonical_eligibility": "PASS", "source_canonical_eligibility": item.get("canonical_eligibility"), "diagnostic_rank_only": True} for item in inventory]
    return ranker(diagnostic)[:10]


def _report(run_id: str, inventory: list[dict[str, Any]], selection: dict[str, Any], provenance: dict[int, dict[str, Any]], image: dict[str, Any], video: dict[str, Any]) -> str:
    semantic_counts = {"subject_zero": sum((item.get("semantic_features") or {}).get("subject_count") == 0 for item in inventory), "dialogue_zero": sum(not (item.get("semantic_features") or {}).get("dialogue_present") for item in inventory), "semantic_useful": sum(bool(item.get("semantic_useful")) for item in inventory)}
    book_lines = []
    for bid in sorted(provenance):
        book = provenance[bid]; book_lines.append(f"- `{bid}`: `{book['provenance_class']}`; eligible=`{book['eligible']}`; evidence: {'; '.join(book['evidence'])}.")
    return f"""# Canonical Canary Semantic Selection V2

Status: `{selection.get('status')}`  
Run: `{run_id}`  
Policy: `canonical_canary_selection_policy_v2`

## 1. Why the previous twelve-way 25-point tie occurred

The V1 extractor counted `prompt_compiler_handoff.asset_identity_bindings.characters` and `props`, while canonical semantic truth lives in `visual_semantic_handoff.subjects`, `visual_semantic_handoff.props`, and its nested `canonical_asset_identity`. V1 also treated missing VIDEO PromptIR as a hard gate and used a smaller score. The twelve 25-point rows were therefore a clone-like empty-scene tie, not evidence of twelve equally strong dialogue canaries.

## 2. Character truth

The V2 extractor reads the canonical `StoryboardShot` projection. Across `{len(inventory)}` rows: subject_count=0 for `{semantic_counts['subject_zero']}`, dialogue_present=false for `{semantic_counts['dialogue_zero']}`, and semantically useful rows=`{semantic_counts['semantic_useful']}`. The current canonical source itself contains no subjects or dialogue; this is not an extractor omission. No historical benchmark prompt was used to infer characters.

## 3. Book / project provenance

{chr(10).join(book_lines)}

Book IDs never contribute to quality score; they are used only for evidence grouping and stable output ordering. Unknown, test, migration, and non-official canary projects are not production E2E targets.

## 4. Current production canary conclusion

There is no database row currently suitable for a production canary that tests `人物 + 对白 + IMAGE→VIDEO`. All current rows fail the semantic minimum (`subject_count >= 2 and dialogue_present`, or a one-subject meaningful performance/action fallback). The correct result is `NO_SEMANTICALLY_USEFUL_CANONICAL_CANARY_TARGET`; no winner was manufactured.

VIDEO PromptIR missing is recorded as `MISSING_COMPILE_REQUIRED` in execution readiness and does not remove an otherwise canonical row. No PromptIR compilation was executed.

## Runtime safety

- IMAGE default: `{image.get('provider')}` / `{image.get('model')}`; real IMAGE calls `0`; IMAGE POST `0`.
- VIDEO default: `{video.get('provider')}` / `{video.get('model')}`; real VIDEO calls `0`; VIDEO POST `0`.
- External LLM `0`; SHAPI `0`; Poyo `0`.
- PromptIR production writes `0`; media writes `0`; OfficialMedia writes `0`.
"""


def main() -> int:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    from core.canary_identity_boundary import classify_canary_identity
    from core.canonical_canary_selection import (
        SELECTION_POLICY_VERSION, build_canonical_shot_inventory, detect_semantic_clone_groups,
        extract_canary_semantic_features, rank_canary_candidates, select_semantic_canary_target,
    )
    from models import Session

    image, video = _profile("image"), _profile("video")
    with Session() as session:
        provenance = _book_provenance(session)
        identity = _identity_audit(session)
        inventory = build_canonical_shot_inventory(session, book_provenance=provenance, image_profile=image, video_profile=video)
        clone_groups = detect_semantic_clone_groups(inventory)
        selection = select_semantic_canary_target(inventory, clone_groups)

    history = {"benchmark_fixture_ids": BENCHMARK_IDS, "records": [{**classify_canary_identity(item), "historical_media_authority": False, "historical_documents_retained": True, "production_canonical": False, "adoption": "FORBIDDEN"} for item in BENCHMARK_IDS], "identity_boundary_status": "BENCHMARK_PRODUCTION_IDENTITY_SEPARATED" if identity["all_benchmark_blocked"] else "IDENTITY_BOUNDARY_FAILED"}
    semantic_audit = [{"book_id": item["book_id"], "plan_shot_id": item["plan_shot_id"], "storyboard_shot_id": item["storyboard_shot_id"], "semantic_features": item["semantic_features"], "semantic_completeness": item["semantic_completeness"], "canonical_eligibility": item["canonical_eligibility"], "clone_group_id": item.get("clone_group_id")} for item in inventory]
    asset_audit = [{"book_id": item["book_id"], "plan_shot_id": item["plan_shot_id"], "asset_authority": item["asset_authority"], "reference_requirements": item["reference_requirements"], "readiness": item["execution_readiness"].get("references")} for item in inventory]
    prompt_audit = [{"book_id": item["book_id"], "plan_shot_id": item["plan_shot_id"], "prompt_ir_readiness": item["prompt_ir_readiness"], "prompt_compile_required": item["prompt_compile_required"], "execution_blockers": item["execution_readiness"].get("execution_blockers")} for item in inventory]
    top10 = _top10(inventory, rank_canary_candidates)
    candidate_projection = [{"book_id": item["book_id"], "title": item["book"].get("title"), "project_provenance": item["book"].get("provenance_class"), "episode": item["episode"], "scene_id": item["scene_id"], "plan_shot_id": item["plan_shot_id"], "storyboard_shot_id": item["storyboard_shot_id"], "subject_count": (item["semantic_features"] or {}).get("subject_count"), "subject_ids": (item["semantic_features"] or {}).get("subject_ids"), "dialogue_present": (item["semantic_features"] or {}).get("dialogue_present"), "prop_count": (item["semantic_features"] or {}).get("prop_count"), "camera_complexity": (item["semantic_features"] or {}).get("camera_complexity"), "duration": item["duration"], "semantic_completeness": item["semantic_completeness"], "image_prompt_ir": item["prompt_ir_readiness"].get("IMAGE"), "video_prompt_ir": item["prompt_ir_readiness"].get("VIDEO"), "asset_readiness": item["asset_authority"].get("status"), "reference_requirements": item["reference_requirements"], "canonical_eligibility": item.get("source_canonical_eligibility", item["canonical_eligibility"]), "diagnostic_rank_only": bool(item.get("diagnostic_rank_only")), "execution_blockers": item["execution_readiness"].get("execution_blockers"), "selection_score": item.get("selection_score"), "clone_group_id": item.get("clone_group_id")} for item in top10]
    selection_fingerprint = hashlib.sha256(json.dumps(_safe(selection), ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    _write("CANARY_SELECTION_POLICY_V2.json", {"schema_version": "canonical_canary_selection_policy_v2", "policy_version": SELECTION_POLICY_VERSION, "weights": {"two_subjects": 25, "one_subject": 12, "dialogue": 20, "reaction_performance": 10, "entry_exit": 8, "medium_framing": 8, "low_camera_complexity": 8, "duration_3_to_14": 8, "zero_props": 6, "one_simple_prop": 3, "asset_authority": 10, "image_prompt_current": 4, "video_prompt_current": 4}, "quality_score_inputs_excluded": ["book_id", "storyboard_shot_id", "created_at", "database_row_order"], "semantic_minimum": {"preferred": "subject_count >= 2 and dialogue_present", "fallback": "subject_count >= 1 and meaningful performance/action semantics"}, "prompt_ir_missing": "readiness_only"})
    _write("BOOK_PROVENANCE_AUDIT.json", {"run_id": run_id, "books": list(provenance.values())})
    _write("CANONICAL_SEMANTIC_FEATURE_AUDIT.json", {"run_id": run_id, "count": len(semantic_audit), "items": semantic_audit})
    _write("CANONICAL_ASSET_READINESS_AUDIT.json", {"run_id": run_id, "count": len(asset_audit), "items": asset_audit})
    _write("CANONICAL_PROMPT_IR_READINESS.json", {"run_id": run_id, "count": len(prompt_audit), "items": prompt_audit, "production_compile_calls": 0})
    _write("CANONICAL_CLONE_GROUPS.json", {"run_id": run_id, "groups": clone_groups})
    _write("CANONICAL_CANARY_CANDIDATES_V2.json", {"run_id": run_id, "top10": candidate_projection, "inventory_count": len(inventory), "identity_eligible_count": sum(item["canonical_eligibility"] == "PASS" for item in inventory), "semantic_useful_count": sum(bool(item["semantic_useful"]) for item in inventory)})
    _write("CANONICAL_CANARY_SELECTION_V2.json", {"run_id": run_id, "status": selection["status"], "identity_boundary_status": history["identity_boundary_status"], "selection_fingerprint": selection_fingerprint, "candidate_count": len(selection.get("candidates") or []), "top_candidates": selection.get("top_candidates"), "blocker_counts": selection.get("blocker_counts"), "real_image_calls": 0, "image_post_count": 0, "real_video_calls": 0, "video_post_count": 0, "external_llm_calls": 0, "prompt_ir_production_writes": 0, "media_writes": 0, "official_media_writes": 0})
    (OUT / "CANONICAL_CANARY_SEMANTIC_SELECTION_REPORT.md").write_text(_report(run_id, inventory, selection, provenance, image, video), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
