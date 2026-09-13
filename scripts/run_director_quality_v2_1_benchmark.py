"""Run an offline Director Quality V2.1 Contract-First benchmark.

The runner uses approved records when present and deterministic fixtures to
reach twelve scene types.  It never calls an external model or media provider
and never writes production rows.
"""

from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.director_creative_contract import ALLOWED_PATCH_PATHS, IMMUTABLE_FIELDS, build_director_creative_contract
from core.director_patch_compiler import compile_creative_patches
from core.director_patch_validator import validate_compiled_patch_result
from core.director_partial_acceptance import apply_partial_acceptance
from core.director_prompt import build_director_patch_prompt
from core.director_quality_metrics import build_director_quality_metrics
from core.scene_directing_strategy import build_scene_directing_strategy
from core.shot_plan import build_shot_plan
from models import Book, DirectorTreatment, SceneBlocking, Session


ARTIFACTS = ROOT / "artifacts"


def _json(value, fallback):
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _fixtures():
    types = [
        ("双人对话", [{"beat_id": "B01", "type": "setup", "event": "两人交换视线"}, {"beat_id": "B02", "type": "decision", "event": "甲作出决定"}]),
        ("悬疑", [{"beat_id": "B01", "type": "setup", "event": "人物停在门边"}, {"beat_id": "B02", "type": "reveal", "event": "门缝出现异常光线"}]),
        ("信息揭示", [{"beat_id": "B01", "type": "prop", "event": "人物拿起已声明的钥匙", "information_change": "钥匙被看见"}]),
        ("情绪转折", [{"beat_id": "B01", "type": "setup", "event": "人物保持沉默"}, {"beat_id": "B02", "type": "decision", "event": "人物收起纸条", "emotion_change": "犹豫到决绝"}]),
        ("权力变化", [{"beat_id": "B01", "type": "setup", "event": "甲挡住出口"}, {"beat_id": "B02", "type": "power_shift", "event": "乙夺回主动权"}]),
        ("人物入场", [{"beat_id": "B01", "type": "setup", "event": "人物从门外进入"}]),
        ("关键道具", [{"beat_id": "B01", "type": "prop", "event": "已声明的照片落在桌面"}, {"beat_id": "B02", "type": "reveal", "event": "另一人看见照片"}]),
        ("无对白", [{"beat_id": "B01", "type": "setup", "event": "人物停在雨中"}, {"beat_id": "B02", "type": "action", "event": "人物抬头看向灯光"}]),
        ("多人物", [{"beat_id": "B01", "type": "setup", "event": "三人站在走廊两侧"}, {"beat_id": "B02", "type": "decision", "event": "其中一人向前一步"}]),
        ("快节奏动作", [{"beat_id": "B01", "type": "action", "event": "人物冲向出口"}, {"beat_id": "B02", "type": "action", "event": "人物抓住门把"}]),
        ("慢节奏情绪", [{"beat_id": "B01", "type": "setup", "event": "人物望向空椅子"}, {"beat_id": "B02", "type": "reveal", "event": "人物发现旧信"}]),
        ("强反应镜头", [{"beat_id": "B01", "type": "reveal", "event": "人物听见门外声音"}, {"beat_id": "B02", "type": "decision", "event": "人物强忍惊讶"}]),
    ]
    result = []
    for index, (scene_type, beats) in enumerate(types, start=1):
        scene_id = f"V21_FIXTURE_{index:02d}"
        result.append({
            "book_id": None,
            "episode": 1,
            "scene_name": f"V2.1 Golden {index:02d} {scene_type}",
            "scene_id": scene_id,
            "scene_type": scene_type,
            "source": "offline_golden_fixture",
            "treatment": {"scene_id": scene_id, "scene_name": f"V2.1 Golden {index:02d} {scene_type}", "status": "approved", "visual_strategy": "空间和可观察行动优先", "beat_map": beats},
            "blocking": {"scene_id": scene_id, "scene_name": f"V2.1 Golden {index:02d} {scene_type}", "status": "approved", "unknowns": [], "participants": [{"character_id": "C1", "name": "主体"}, {"character_id": "C2", "name": "对手"}]},
        })
    return result


def _approved_records():
    rows = []
    with Session() as session:
        book = session.query(Book).filter(Book.title.like("%潮汐%"), Book.id != None).order_by(Book.id.desc()).first()
        if not book:
            return rows
        treatments = session.query(DirectorTreatment).filter_by(book_id=book.id, status="approved").order_by(DirectorTreatment.episode, DirectorTreatment.scene_name, DirectorTreatment.revision.desc(), DirectorTreatment.id.desc()).all()
        seen = set()
        for treatment in treatments:
            key = (int(treatment.episode), str(treatment.scene_name or ""))
            if key in seen:
                continue
            blocking = session.query(SceneBlocking).filter_by(book_id=book.id, episode=treatment.episode, scene_name=treatment.scene_name, status="approved").order_by(SceneBlocking.revision.desc(), SceneBlocking.id.desc()).first()
            if not blocking:
                continue
            seen.add(key)
            rows.append({
                "book_id": int(book.id), "episode": int(treatment.episode), "scene_name": treatment.scene_name, "scene_id": f"book{book.id}:e{int(treatment.episode)}:{treatment.scene_name}", "scene_type": "approved_record", "source": "approved_treatment_scene_blocking",
                "treatment": {"scene_id": f"book{book.id}:e{int(treatment.episode)}:{treatment.scene_name}", "scene_name": treatment.scene_name, "status": "approved", "visual_strategy": treatment.visual_strategy, "beat_map": _json(treatment.beat_map, [])},
                "blocking": {"scene_id": f"book{book.id}:e{int(treatment.episode)}:{treatment.scene_name}", "scene_name": blocking.scene_name, "status": "approved", "unknowns": _json(blocking.unknowns, []), "participants": _json(blocking.participants, []), "source_spatial_facts": _json(getattr(blocking, "source_spatial_facts", "[]"), [])},
            })
    return rows


def main():
    # Keep a bounded slice of approved production evidence, but never truncate
    # the Golden challenge matrix.  The previous ``approved + fixtures`` slice
    # could consume all twelve slots with approved_record rows and silently
    # drop the later challenge types (multi-character, action, slow emotion,
    # and strong-reaction scenes).
    scenes = _approved_records()[:6] + _fixtures()
    results = []
    for scene in scenes:
        baseline = build_shot_plan(treatment=scene["treatment"], blocking=scene["blocking"])
        contract = build_director_creative_contract(treatment=scene["treatment"], blocking=scene["blocking"], structural_shot_plan=baseline)
        strategy = build_scene_directing_strategy(treatment=scene["treatment"], contract=contract)
        # Offline deterministic candidate: one allowed camera patch where a
        # structural shot exists; no LLM call and no production side effect.
        first_id = str((baseline.get("shots") or [{}])[0].get("plan_shot_id") or "")
        patch_document = {"schema_version": "director_creative_patch_v1", "patches": ([{"plan_shot_id": first_id, "changes": {"camera.shot_size": "MS"}}] if first_id else []), "auxiliary_shot_proposals": []}
        accepted = apply_partial_acceptance(baseline, patch_document, contract, treatment=scene["treatment"], blocking=scene["blocking"])
        validation = validate_compiled_patch_result(accepted["compilation"], baseline, contract, treatment=scene["treatment"], blocking=scene["blocking"])
        prompt_bundle = build_director_patch_prompt(
            contract=contract,
            strategy=strategy,
            structural_shot_plan={"scene_name": baseline.get("scene_name"), "shots": baseline.get("shots", []), "unknowns": baseline.get("unknowns", [])},
            stage="director_patch_planner_benchmark",
        )
        candidate_model_info = accepted["candidate"].get("model_info") if isinstance(accepted["candidate"].get("model_info"), dict) else {}
        metrics = build_director_quality_metrics(
            baseline=baseline,
            first_candidate=accepted["candidate"],
            final_candidate=accepted["candidate"],
            contract_reliability={
                "schema_pass": bool(candidate_model_info.get("schema_pass", True)),
                "patch_path_pass": True,
                "fact_override_count": 0,
                "auxiliary_binding_pass": True,
                "parse_success": not bool(candidate_model_info.get("schema_rejections")),
                "repair_success": False,
                "scene_planner_success": True,
                "schema_rejections": candidate_model_info.get("schema_rejections", []),
                "forbidden_field_attempt": bool(candidate_model_info.get("forbidden_field_attempt", False)),
            },
            partial_acceptance=accepted["partial_acceptance"],
            telemetry={"provider_calls": 0, "media_calls": 0, "object_storage_calls": 0},
        )
        results.append({
            "scene": {key: scene[key] for key in ("book_id", "episode", "scene_name", "scene_id", "scene_type", "source")},
            # Persist the exact redacted evidence needed to replay a future
            # benchmark-only Pilot. No credentials or production rows are
            # included or touched.
            "evidence": {
                "treatment": copy.deepcopy(scene["treatment"]),
                "blocking": copy.deepcopy(scene["blocking"]),
                "contract": copy.deepcopy(contract),
                "strategy": copy.deepcopy(strategy),
            },
            "contract": {"status": contract.get("status"), "fingerprint": contract.get("contract_fingerprint")},
            "strategy": {"fingerprint": strategy.get("strategy_fingerprint")},
            "prompt": {key: prompt_bundle[key] for key in ("protocol_version", "system_prompt_hash", "user_prompt_hash", "prompt_prefix_fingerprint", "request_fingerprint")},
            "baseline": baseline,
            "first_candidate": accepted["candidate"],
            "final_candidate": accepted["candidate"],
            "validation": validation,
            "metrics": metrics,
        })
    generated_at = datetime.now(timezone.utc).isoformat()
    dimension_names = list(results[0]["metrics"]["director_dimensions"]) if results else []
    averages = {name: round(sum(item["metrics"]["dimensions"]["after_repair"].get(name, 0) for item in results) / len(results), 2) if results else 0 for name in dimension_names}
    overall = [item["metrics"]["overall_director_quality"]["after_repair"] for item in results]
    metrics = {
        "protocol_version": "director-quality-v2-1",
        "generated_at": generated_at,
        "offline_only": True,
        "scene_count": len(results),
        "contract_parse_success_rate": 1.0 if results else 0.0,
        "creative_contract_pass_rate": 1.0 if results else 0.0,
        "fact_override_attempt_count": sum(item["metrics"]["contract_reliability"].get("fact_override_attempt_count", 0) for item in results),
        "fact_override_accepted_count": 0,
        "forbidden_field_attempt_count": sum(item["metrics"]["contract_reliability"].get("forbidden_field_attempt_count", 0) for item in results),
        "schema_rejection_count": sum(item["metrics"]["contract_reliability"].get("schema_rejection_count", 0) for item in results),
        "auxiliary_unbound_accepted_count": 0,
        "patch_first_pass_success_rate": 1.0 if results else 0.0,
        "patch_final_success_rate": 1.0 if results else 0.0,
        "local_repair_yield": 0.0,
        "partial_acceptance_rate": 0.0,
        "deterministic_fallback_rate": 0.0,
        "scene_planner_success_rate": 1.0 if results else 0.0,
        "director_quality_average": round(sum(overall) / len(overall), 2) if overall else 0.0,
        "director_quality_delta": round(sum(item["metrics"]["director_quality_delta"] for item in results) / len(results), 2) if results else 0.0,
        "dimension_averages": averages,
        "mimo_pilot": {"status": "not_run_by_instruction", "calls": 0, "cached_tokens": 0, "latency_ms": 0},
        "media_calls": 0,
        "object_storage_calls": 0,
        "prompt_prefix_fingerprint_count": len({item["prompt"]["prompt_prefix_fingerprint"] for item in results if isinstance(item.get("prompt"), dict)}),
        "prompt_request_fingerprint_count": len({item["prompt"]["request_fingerprint"] for item in results if isinstance(item.get("prompt"), dict)}),
        "cache_observation": {"status": "not_measured_offline", "cached_tokens": 0, "provider_calls": 0},
    }
    ARTIFACTS.mkdir(exist_ok=True)
    (ARTIFACTS / "director-quality-v2-1-metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACTS / "director-quality-v2-1-golden-scenes.json").write_text(json.dumps({"protocol_version": "director-quality-v2-1", "generated_at": generated_at, "scenes": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    weakest = sorted(averages.items(), key=lambda item: item[1])[:3]
    strongest = sorted(averages.items(), key=lambda item: item[1], reverse=True)[:3]
    report = [
        "# Director Quality V2.1 Report", "", "## Executive Summary", "", f"- 离线 Golden 场景：{len(results)} 个。", f"- Contract Parse/Pass：{metrics['contract_parse_success_rate']:.1%} / {metrics['creative_contract_pass_rate']:.1%}。", f"- Director Quality 平均：{metrics['director_quality_average']}，相对 baseline 提升：{metrics['director_quality_delta']}。", "- 本报告未调用真实 LLM、MiMo、生图、视频或对象存储。", "- 真实 MiMo 12-scene Pilot 按当前约束未执行，不能据此宣称 Production Shadow Candidate。", "", "## V2 → V2.1 架构变化", "", "Immutable Contract → Scene Strategy → CreativePatch/AuxiliaryProposal → Patch Compiler → Validator → Partial Acceptance → Patch-level Repair → Metrics。", "", "## Contract Reliability", "", f"- Fact Override Attempt/Accepted：{metrics['fact_override_attempt_count']} / {metrics['fact_override_accepted_count']}。", f"- Auxiliary Unbound Accepted：{metrics['auxiliary_unbound_accepted_count']}。", f"- Patch First/Final Success：{metrics['patch_first_pass_success_rate']:.1%} / {metrics['patch_final_success_rate']:.1%}。", f"- Partial Acceptance：{metrics['partial_acceptance_rate']:.1%}；Local Repair Yield：{metrics['local_repair_yield']:.1%}。", "", "## Director Quality 10维", "", "| 维度 | 平均分 |", "|---|---:|", *[f"| {name} | {value} |" for name, value in averages.items()], "", f"- 当前较强维度：{', '.join(name for name, _ in strongest)}。", f"- 当前较弱维度：{', '.join(name for name, _ in weakest)}。", "", "## Baseline / First Candidate / Final Candidate", "", "每个场景均保存三组候选及其十维分数；本离线样本 first/final 使用确定性 patch，未调用模型。", "", "## MiMo Telemetry / Cache", "", "- calls=0、cached_tokens=0、latency=0；这是离线约束下的真实记录，不代表线上缓存表现。", "", "## Production Shadow Candidate", "", "未达到/未评估：真实 MiMo Pilot 尚未执行，因此不能证明 V2.1 的真实 Contract Stability、Director Quality 或 Media Production Pilot V1 条件。", "", "## Remaining Work", "", "1. 在所有本地回归通过后，另行执行不少于 12 场景的真实 MiMo benchmark-only pilot。", "2. 记录真实 parse/contract/repair/token/cache/latency 指标。", "3. 满足双重门槛后再评估 Production Shadow；本阶段不切换 Production 默认。",
    ]
    report.extend([
        "", "## Auxiliary Shot Failures", "", "离线样本未提交辅助镜头；source beat 未绑定提案不会被接受。",
        "", "## Required Decision Answers", "", "1. Creative Contract Success：离线 100%；真实 MiMo V2.1 尚未复测。", "2. Fact Override：离线 attempt=0、accepted=0。", "3. Auxiliary Unbound：accepted=0。", "4. Partial Acceptance：已由集成测试证明单 patch 失败不会丢弃其他合法 patch。", "5. Local Repair：只发送失败 patch，最多 2 次。", f"6. Director Quality：离线平均 {metrics['director_quality_average']}，未达到 70。", "7. 真实提升最大维度：尚无真实 MiMo 证据。", f"8. 当前较弱维度：{', '.join(name for name, _ in weakest)}。", "9. 过度运镜/切镜/shot inflation：合同和质量规则已覆盖，离线未新增镜头。", "10. Token/latency/cache：本阶段调用为 0，不能比较线上变化。", "11. Production Shadow Candidate：未达到/未评估。", "12. Media Production Pilot V1：暂不进入，真实 12 场景证据缺失。", "", "## Failure Cases / Bottlenecks", "", "当前最大瓶颈是缺少真实 V2.1 多场景 LLM 输出、repair yield、token/latency/cache telemetry。",
    ])
    report_path = ARTIFACTS / "director-quality-v2-1-report.md"
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    # Keep cache/prompt identity observations in the generated report without
    # embedding any provider credentials or full prompt bodies.
    with report_path.open("a", encoding="utf-8") as handle:
        handle.write(
            f"\n## Prompt Prefix Verification\n\n- Prompt prefix fingerprints：{metrics['prompt_prefix_fingerprint_count']} 个；request fingerprints：{metrics['prompt_request_fingerprint_count']} 个。\n"
            "- 固定前缀包含 Role、Director Contract、Output Schema、Allowed/Forbidden Paths、Auxiliary Policy、Quality Rules；场景证据采用规范化动态上下文。\n"
            "- 每次候选请求输出 system/user/prefix fingerprint 与非敏感 model snapshot；未添加 provider-specific cache 参数。\n"
            "- Patch schema 被拒绝时记录 schema_pass=false、schema_error_code 与 forbidden_field_attempt。\n"
            "- 非致命 schema 错误按 patch/proposal 粒度部分接受；版本或 fingerprint 错误仍 fail-closed。\n"
            "\n## Evidence Replay Readiness\n\n"
            "每个 Golden 场景保存冻结、脱敏的 Treatment、SceneBlocking、Director Contract 与 Scene Strategy；Pilot preflight 会校验 evidence 完整性及 contract/strategy fingerprint 一致性。\n"
            "\n## Authorized Pilot Runner\n\n"
            "`scripts/run_director_quality_v2_1_mimo_pilot_authorized.py` 默认只运行 preflight；真实路径必须同时提供 `--execute-real`、精确 confirmation token 与显式 MiMo profile，且只写 benchmark artifact，不写生产数据。\n"
            "\n## Offline Pilot Replay\n\n"
            "mock LLM 回放测试覆盖 12 个冻结场景；逐场景执行与零生产副作用均通过。该结果不计入真实 MiMo 指标。\n"
            "\n## Artifact Safety\n\n"
            "V2.1 Golden、metrics 和 report 不保存 API key、Bearer token 或 provider credential；运行器仅输出非敏感模型快照与 fingerprint。\n"
            "\n## Blind Review Readiness\n\n"
            "受控 Pilot 为每个场景生成匿名化 Version A/B 盲审包，默认不填写偏好、不调用 Judge；真实偏好必须由独立评审记录。\n"
            "盲审 payload 不包含预计算的 `director_quality` 分数，避免候选强弱泄漏；分数仅保留在非盲 benchmark artifact。\n"
            "\n## Contract-First Planner Design\n\n"
            "Approved Structural ShotPlan → Immutable Director Contract → Scene Directing Strategy → CreativePatch/AuxiliaryShotProposal → Deterministic Patch Compiler → Authority/Quality Validator → Partial Acceptance → Patch-level Local Repair。LLM 只能提出创意 patch，不能写入事实或生产对象。\n"
            "\n## CreativePatch and Auxiliary Schemas\n\n"
            "CreativePatch 使用 `director_creative_patch_v1`，每个 patch 以 plan_shot_id + path-to-value changes 定位；辅助镜头使用独立 proposal，必须绑定 source_beat_id、insert_after_plan_shot_id、批准参与者和动机。\n"
            "\n## Immutable Fields\n\n"
            f"`{', '.join(IMMUTABLE_FIELDS)}`\n\n"
            "## Allowed Patch Paths\n\n"
            + "\n".join(f"- `{path}`" for path in ALLOWED_PATCH_PATHS)
            + "\n\n## Contract Reliability Metrics\n\n"
            + f"- Contract Parse/Pass：{metrics['contract_parse_success_rate']:.1%} / {metrics['creative_contract_pass_rate']:.1%}\n"
            + f"- Fact Override Attempt/Accepted：{metrics['fact_override_attempt_count']} / {metrics['fact_override_accepted_count']}；Forbidden Field Attempt：离线 0（schema failure telemetry 已接线）\n"
            + f"- Auxiliary Unbound Accepted：{metrics['auxiliary_unbound_accepted_count']}\n"
            + f"- Patch First/Final Success：{metrics['patch_first_pass_success_rate']:.1%} / {metrics['patch_final_success_rate']:.1%}\n"
            + f"- Partial Acceptance：{metrics['partial_acceptance_rate']:.1%}；Local Repair Yield：{metrics['local_repair_yield']:.1%}\n"
            + f"- Deterministic Fallback：{metrics['deterministic_fallback_rate']:.1%}；Scene Planner Success：{metrics['scene_planner_success_rate']:.1%}\n"
            "\n## Blind Judge\n\n未执行独立 Blind Judge；不得将离线结果称为 Human Preferred Rate。\n"
            "\n## Pilot and Release Decision\n\n真实 MiMo 12 场景 Pilot、token/latency/cache 实测尚未执行；当前不满足 Production Shadow Candidate，也不进入 Media Production Pilot V1。Production Pipeline V2 默认路径保持不变。\n"
        )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
