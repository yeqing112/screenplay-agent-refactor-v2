"""Guarded runner for the Director Quality V2.1 MiMo benchmark-only Pilot.

The normal command path is preflight-only.  A real run requires all of:

* ``--execute-real``;
* the exact ``--confirmation-token`` value;
* an explicit ``--profile-id`` whose configured model is MiMo.

Even when enabled, this runner only reads the frozen Golden evidence and
writes a benchmark artifact.  It never writes ShotPlan/Storyboard rows,
starts media generation, or touches object storage.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"
GOLDEN_PATH = ARTIFACTS / "director-quality-v2-1-golden-scenes.json"
CONFIRMATION_TOKEN = "CONFIRM_DIRECTOR_V21_REAL_MIMO_PILOT"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取 Golden evidence：{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Golden evidence 必须是 JSON object")
    return value


def validate_real_authorization(
    *,
    execute_real: bool,
    confirmation_token: str,
    profile: dict[str, Any] | None,
) -> dict[str, Any]:
    """Fail closed unless the operator explicitly authorizes a MiMo run."""

    if not execute_real:
        raise PermissionError("真实 Pilot 默认关闭；必须显式提供 --execute-real。")
    if str(confirmation_token or "") != CONFIRMATION_TOKEN:
        raise PermissionError("真实 Pilot confirmation token 不匹配。")
    if not isinstance(profile, dict):
        raise ValueError("必须显式指定已保存的 MiMo LLM profile。")
    if str(profile.get("capability") or "") != "llm":
        raise ValueError("Pilot profile 必须是 LLM 能力。")
    if str(profile.get("provider") or "") != "openai-compatible":
        raise ValueError("真实 MiMo Pilot 需要 openai-compatible provider。")
    if not bool(profile.get("enabled", True)):
        raise ValueError("Pilot profile 已禁用。")
    model_name = str(profile.get("model_name") or "").strip()
    if "mimo" not in model_name.lower():
        raise ValueError("真实 V2.1 Pilot 只允许显式指定 MiMo 模型 profile。")
    if not str(profile.get("api_key") or "").strip():
        raise ValueError("Pilot profile 缺少 API Key。")
    if not str(profile.get("base_url") or "").strip():
        raise ValueError("Pilot profile 缺少 base_url。")
    return {
        "profile_id": str(profile.get("id") or ""),
        "provider": str(profile.get("provider") or ""),
        "model_name": model_name,
    }


def _scene_context(scene: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    evidence = _dict(scene.get("evidence"))
    treatment = _dict(evidence.get("treatment"))
    blocking = _dict(evidence.get("blocking"))
    contract = _dict(evidence.get("contract"))
    strategy = _dict(evidence.get("strategy"))
    if not all((treatment, blocking, contract, strategy)):
        scene_id = str(_dict(scene.get("scene")).get("scene_id") or "<unknown>")
        raise ValueError(f"{scene_id}: frozen evidence is incomplete")
    return treatment, blocking, contract, strategy


def _raw_item(raw: Any, path: str, key: str) -> dict[str, Any] | None:
    """Return the original provider item referenced by a schema diagnostic."""
    match = re.search(rf"{re.escape(key)}\[(\d+)\]", str(path or ""))
    if not match or not isinstance(raw, dict):
        return None
    values = raw.get(key)
    index = int(match.group(1))
    if not isinstance(values, list) or index >= len(values) or not isinstance(values[index], dict):
        return None
    return copy.deepcopy(values[index])


def _repair_prompt(request: dict[str, Any], *, kind: str) -> tuple[str, str]:
    system = (
        "You are a bounded Director Quality local repairer. Return JSON only. "
        "Repair exactly the supplied failed item, preserve its identity and all authoritative facts, "
        "and never return a complete scene or ShotPlan."
    )
    if kind == "patch":
        task = "Return one patch object with plan_shot_id and a non-empty changes object using only creative paths."
    else:
        task = "Return one auxiliary_shot_proposal object. Preserve proposal_id and source_beat_id exactly and use only bound participants."
    user = task + "\nREPAIR_REQUEST\n" + json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return system, user


def run_authorized_pilot(
    *,
    profile: dict[str, Any],
    golden_path: Path = GOLDEN_PATH,
    scene_limit: int = 12,
) -> dict[str, Any]:
    """Run the benchmark-only Pilot against frozen evidence.

    This function is intentionally not called by the default CLI path.  It
    imports the provider-facing client lazily so preflight tests remain
    completely offline.
    """

    # Lazy imports are part of the safety boundary: importing this module or
    # running its default command cannot initialize a provider client.
    from core.director_creative_planner import build_creative_patch_candidate
    from core.director_blind_review import prepare_blind_review
    from core.director_partial_acceptance import apply_partial_acceptance
    from core.director_patch_repair import repair_failed_patch, repair_failed_auxiliary_proposal
    from core.director_prompt import build_director_patch_prompt
    from core.director_quality_metrics import build_director_quality_metrics
    from core.pilot_instrumentation import PilotInvocationRecorder
    from core.llm import call_llm_json

    payload = _load_json(golden_path)
    scenes = payload.get("scenes") if isinstance(payload.get("scenes"), list) else []
    if len(scenes) < scene_limit:
        raise ValueError(f"Frozen Golden scene count {len(scenes)} is below required {scene_limit}")

    recorder = PilotInvocationRecorder()
    results: list[dict[str, Any]] = []
    for scene in scenes[:scene_limit]:
        scene = scene if isinstance(scene, dict) else {}
        metadata = _dict(scene.get("scene"))
        scene_id = str(metadata.get("scene_id") or "<unknown>")
        episode = metadata.get("episode", 1)
        scene_name = str(metadata.get("scene_name") or scene_id)
        baseline = copy.deepcopy(_dict(scene.get("baseline")))
        treatment, blocking, contract, strategy = _scene_context(scene)
        prompt = build_director_patch_prompt(
            contract=contract,
            strategy=strategy,
            structural_shot_plan={
                "scene_name": baseline.get("scene_name"),
                "shots": baseline.get("shots", []),
                "unknowns": baseline.get("unknowns", []),
            },
            model_profile=profile,
            stage="director_quality_v2_1_mimo_pilot",
        )
        start_record = len(recorder.records)
        error = ""
        candidate: dict[str, Any] | None = None
        accepted: dict[str, Any] | None = None
        initial_accepted: dict[str, Any] | None = None
        repair_records: list[dict[str, Any]] = []
        raw: Any = None
        try:
            with recorder.span(
                stage="director_patch_planner",
                episode=episode,
                scene=scene_name,
            ):
                raw = call_llm_json(
                    prompt["user_prompt"],
                    system=prompt["system_prompt"],
                    model_profile=profile,
                    required_keys={"schema_version", "patches", "auxiliary_shot_proposals"},
                    estimated_tokens=5000,
                    audit_extra={
                        "stage": "director_patch_planner",
                        "episode": episode,
                        "scene_name": scene_name,
                        "prompt_prefix_fingerprint": prompt["prompt_prefix_fingerprint"],
                        "prompt_request_fingerprint": prompt["request_fingerprint"],
                    },
                )
            candidate = build_creative_patch_candidate(
                structural_shot_plan=baseline,
                contract=contract,
                strategy=strategy,
                llm_output=raw,
                mode="shadow",
            )
            # ``llm_output`` is injected after the provider call, so mark the
            # provenance explicitly without making the planner call twice.
            candidate.setdefault("model_info", {})["llm_called"] = True
            accepted = apply_partial_acceptance(
                baseline,
                candidate["patch_document"],
                contract,
                treatment=treatment,
                blocking=blocking,
            )
            initial_accepted = copy.deepcopy(accepted)

            # Repair only rejected items.  Each request is bounded to one
            # patch/proposal and never reruns scene planning.
            candidate_doc = copy.deepcopy(candidate["patch_document"])
            patch_items = list(candidate_doc.get("patches") or [])
            aux_items = list(candidate_doc.get("auxiliary_shot_proposals") or [])
            diagnostics = list(_dict(candidate.get("model_info")).get("schema_rejections") or [])
            diagnostics.extend(copy.deepcopy(accepted.get("rejected_patches") or []))
            validation_aux = _dict(_dict(accepted.get("validation")).get("auxiliary"))
            diagnostics.extend(copy.deepcopy(validation_aux.get("rejected") or []))
            seen_repairs: set[tuple[str, str]] = set()
            for issue in diagnostics:
                issue_obj = _dict(issue)
                path = str(issue_obj.get("path") or "")
                kind = "patch" if "patches[" in path or issue_obj.get("plan_shot_id") else ("auxiliary" if "auxiliary" in path or issue_obj.get("proposal_id") else "")
                if not kind:
                    continue
                failed = _raw_item(raw, path, "patches" if kind == "patch" else "auxiliary_shot_proposals")
                if failed is None and kind == "patch":
                    target = str(issue_obj.get("plan_shot_id") or "")
                    failed = next((copy.deepcopy(item) for item in patch_items if str(item.get("plan_shot_id") or "") == target), None)
                if failed is None and kind == "auxiliary":
                    target = str(issue_obj.get("proposal_id") or "")
                    failed = next((copy.deepcopy(item) for item in aux_items if str(item.get("proposal_id") or "") == target), None)
                if not isinstance(failed, dict):
                    continue
                identity = str(failed.get("plan_shot_id") if kind == "patch" else failed.get("proposal_id") or path)
                if (kind, identity) in seen_repairs:
                    continue
                seen_repairs.add((kind, identity))
                request_holder: dict[str, Any] = {}
                repair_call_count = 0

                def repair_call(request: dict[str, Any], *, _kind=kind) -> Any:
                    nonlocal repair_call_count
                    repair_call_count += 1
                    request_holder.clear(); request_holder.update(copy.deepcopy(request))
                    system_prompt, user_prompt = _repair_prompt(request, kind=_kind)
                    with recorder.span(
                        stage="director_patch_repair",
                        episode=episode,
                        scene=scene_name,
                        repair_attempt=repair_call_count,
                        repair_kind=_kind,
                    ):
                        return call_llm_json(
                            user_prompt,
                            system=system_prompt,
                            model_profile=profile,
                            audit_extra={
                                "stage": "director_patch_repair",
                                "episode": episode,
                                "scene_name": scene_name,
                                "repair_kind": _kind,
                            },
                        )

                if kind == "patch":
                    repaired = repair_failed_patch(
                        structural_shot_plan=baseline,
                        failed_patch=failed,
                        issue=issue_obj,
                        contract=contract,
                        strategy=strategy,
                        repair_callable=repair_call,
                        # Preserve the historical V2.1 benchmark wire
                        # semantics.  V2.2+ uses the stricter target-locked
                        # replacement contract and a two-attempt ceiling.
                        max_attempts=1,
                        legacy_path_replacement=True,
                    )
                    repair_records.append({"kind": kind, "identity": identity, **{key: repaired.get(key) for key in ("status", "attempt_count", "attempts", "fallback_to_baseline")}})
                    if repaired.get("status") == "repaired" and isinstance(repaired.get("accepted_patch"), dict):
                        patch_items = [item for item in patch_items if str(item.get("plan_shot_id") or "") != identity]
                        patch_items.append(copy.deepcopy(repaired["accepted_patch"]))
                else:
                    repaired = repair_failed_auxiliary_proposal(
                        structural_shot_plan=baseline,
                        failed_proposal=failed,
                        issue=issue_obj,
                        contract=contract,
                        strategy=strategy,
                        repair_callable=repair_call,
                        max_attempts=1,
                    )
                    repair_records.append({"kind": kind, "identity": identity, **{key: repaired.get(key) for key in ("status", "attempt_count", "attempts", "fallback_to_baseline")}})
                    if repaired.get("status") == "repaired" and isinstance(repaired.get("accepted_proposal"), dict):
                        aux_items = [item for item in aux_items if str(item.get("proposal_id") or "") != identity]
                        aux_items.append(copy.deepcopy(repaired["accepted_proposal"]))
            if repair_records:
                candidate_doc["patches"] = patch_items
                candidate_doc["auxiliary_shot_proposals"] = aux_items
                # The canonical document fingerprint/format metadata belongs
                # to the pre-repair item set; force the schema boundary to
                # recompute both after accepted repairs are merged.
                candidate_doc.pop("patch_fingerprint", None)
                candidate_doc.pop("normalization_metadata", None)
                accepted = apply_partial_acceptance(
                    baseline,
                    candidate_doc,
                    contract,
                    treatment=treatment,
                    blocking=blocking,
                )
                repaired_count = sum(1 for item in repair_records if item.get("status") == "repaired" and item.get("kind") == "patch")
                fallback_count = sum(1 for item in repair_records if item.get("status") == "fallback")
                accepted["partial_acceptance"]["repaired_patch_count"] = repaired_count
                accepted["partial_acceptance"]["fallback_patch_count"] = fallback_count + int(accepted["partial_acceptance"].get("rejected_patch_count") or 0)
        except Exception as exc:  # A scene failure must not abort other scenes.
            error = str(exc)[:500]

        if accepted is None:
            accepted = {
                "candidate": baseline,
                "partial_acceptance": {
                    "accepted_patch_count": 0,
                    "rejected_patch_count": 0,
                    "repaired_patch_count": 0,
                    "fallback_patch_count": 0,
                },
                "rejected_patches": [],
                "validation": {"status": "not_run", "error": error},
            }
        if initial_accepted is None:
            initial_accepted = accepted
        first_candidate = initial_accepted["candidate"]
        final_candidate = accepted["candidate"]
        model_info = _dict(candidate.get("model_info")) if candidate else {}
        scene_records = recorder.records[start_record:]
        scene_telemetry = {
            "stage": "director_patch_planner+repair",
            "calls": len(scene_records),
            "planner_calls": sum(1 for item in scene_records if _dict(item.get("extra")).get("pilot_stage") == "director_patch_planner"),
            "repair_calls": sum(1 for item in scene_records if _dict(item.get("extra")).get("pilot_stage") == "director_patch_repair"),
            "prompt_tokens": sum(int(_dict(item.get("usage")).get("prompt_tokens") or 0) for item in scene_records),
            "cached_tokens": sum(int(_dict(item.get("usage")).get("cached_tokens") or 0) for item in scene_records),
            "completion_tokens": sum(int(_dict(item.get("usage")).get("completion_tokens") or 0) for item in scene_records),
            "total_tokens": sum(int(_dict(item.get("usage")).get("total_tokens") or 0) for item in scene_records),
            "latency_ms": round(sum(float(item.get("latency_ms") or 0) for item in scene_records), 2),
        }
        metrics = build_director_quality_metrics(
            baseline=baseline,
            first_candidate=first_candidate,
            final_candidate=final_candidate,
            treatment=treatment,
            blocking=blocking,
            contract_reliability={
                "schema_pass": model_info.get("schema_pass"),
                "patch_path_pass": not bool(accepted.get("rejected_patches")),
                "fact_override_count": sum(
                    1
                    for item in (model_info.get("schema_rejections") or [])
                    if str(_dict(item).get("code") or _dict(item).get("issue_code") or "") == "DIRECTOR_FACT_OVERRIDE"
                ),
                "fact_override_attempt_count": sum(
                    1
                    for item in (model_info.get("schema_rejections") or [])
                    if str(_dict(item).get("code") or _dict(item).get("issue_code") or "") == "DIRECTOR_FACT_OVERRIDE"
                ),
                "auxiliary_binding_pass": True,
                "parse_success": bool(candidate) and not bool(error) and bool(model_info.get("schema_pass", True)),
                "repair_success": any(item.get("status") == "repaired" for item in repair_records),
                "scene_planner_success": not bool(error),
                "schema_rejections": model_info.get("schema_rejections", []),
                "forbidden_field_attempt": bool(model_info.get("forbidden_field_attempt")),
            },
            partial_acceptance=accepted["partial_acceptance"],
            telemetry=scene_telemetry,
        )
        blind_review_packet = prepare_blind_review(
            {
                "version_a": {
                    "director_quality": metrics["scores"]["baseline"],
                    "shot_count": len(_dict(baseline).get("shots") or []),
                    "shots": baseline.get("shots", []),
                },
                "version_b": {
                    "director_quality": metrics["scores"]["after_repair"],
                    "shot_count": len(_dict(final_candidate).get("shots") or []),
                    "shots": final_candidate.get("shots", []),
                },
            },
            salt=f"director-quality-v2-1:{scene_id}",
        )
        results.append({
            "scene": {key: metadata.get(key) for key in ("book_id", "episode", "scene_name", "scene_id", "scene_type", "source")},
            "prompt": {key: prompt[key] for key in ("protocol_version", "system_prompt_hash", "user_prompt_hash", "prompt_prefix_fingerprint", "request_fingerprint")},
            "candidate": candidate,
            "first_candidate": first_candidate,
            "final_candidate": final_candidate,
            "validation": accepted.get("validation"),
            "partial_acceptance": accepted["partial_acceptance"],
            "rejected_patches": accepted.get("rejected_patches", []),
            "metrics": metrics,
            "blind_review_packet": blind_review_packet,
            "error": error,
            "repair_records": repair_records,
        })

    generated_at = datetime.now(timezone.utc).isoformat()
    aggregate = recorder.summary()
    return {
        "protocol_version": "director-quality-v2-1",
        "pilot_mode": "real_mimo_benchmark_only",
        "generated_at": generated_at,
        "scene_count": len(results),
        "model": {"profile_id": str(profile.get("id") or ""), "provider": str(profile.get("provider") or ""), "model_name": str(profile.get("model_name") or "")},
        "scenes": results,
        "telemetry": aggregate,
        "side_effects": {"production_rows_written": 0, "storyboard_shots_created": 0, "media_calls": 0, "object_storage_calls": 0},
        "blind_judge": {"status": "not_run"},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Guarded Director Quality V2.1 MiMo benchmark-only Pilot")
    parser.add_argument("--execute-real", action="store_true", help="enable the real provider call path")
    parser.add_argument("--confirmation-token", default="", help="exact operator confirmation token")
    parser.add_argument("--profile-id", default="", help="saved MiMo LLM profile id")
    parser.add_argument("--scene-limit", type=int, default=12)
    args = parser.parse_args()

    if not args.execute_real:
        from scripts.run_director_quality_v2_1_mimo_pilot import build_preflight

        print(json.dumps(build_preflight(), ensure_ascii=False, indent=2))
        return

    from api.model_registry import get_profile

    profile = get_profile(args.profile_id)
    safe_model = validate_real_authorization(
        execute_real=args.execute_real,
        confirmation_token=args.confirmation_token,
        profile=profile,
    )
    result = run_authorized_pilot(profile=profile, scene_limit=max(12, int(args.scene_limit)))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ARTIFACTS.mkdir(exist_ok=True)
    path = ARTIFACTS / f"director-quality-v2-1-mimo-pilot-{stamp}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"artifact": str(path), "model": safe_model, "scene_count": result["scene_count"], "telemetry": result["telemetry"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
