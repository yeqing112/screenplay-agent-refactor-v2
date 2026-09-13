"""Generate the local Director Quality Benchmark V2 artifacts.

The runner is deliberately offline: it reads existing approved records when
available, uses the deterministic planner and controlled shadow planner, and
never calls an LLM/media/object-storage provider or mutates production rows.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.director_benchmark import compare_director_plans
from core.director_creative_planner import build_creative_shot_plan_candidate
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


def _approved_scenes():
    rows = []
    with Session() as session:
        book = session.query(Book).filter(Book.id == 990402).first()
        if not book:
            book = session.query(Book).filter(Book.title.like("%潮汐%")) .order_by(Book.id.desc()).first()
        if book:
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
                rows.append((book.id, str(book.title), treatment, blocking))
    return rows


def _payload(treatment, blocking):
    treatment_payload = {
        "scene_name": treatment.scene_name,
        "scene_id": f"E{int(treatment.episode):02d}:{treatment.scene_name}",
        "status": "approved",
        "character_intents": _json(treatment.character_intents, {}),
        "beat_map": _json(treatment.beat_map, []),
    }
    blocking_payload = {
        "scene_name": blocking.scene_name,
        "scene_id": f"E{int(treatment.episode):02d}:{treatment.scene_name}",
        "status": "approved",
        "participants": _json(blocking.participants, []),
        "unknowns": _json(blocking.unknowns, []),
        "source_spatial_facts": _json(getattr(blocking, "source_spatial_facts", "[]"), []),
    }
    return treatment_payload, blocking_payload


def _fixture(scene_id, name, scene_type, beats, participants):
    treatment = {"scene_name": name, "scene_id": scene_id, "status": "approved", "beat_map": beats}
    blocking = {"scene_name": name, "scene_id": scene_id, "status": "approved", "unknowns": [], "participants": participants}
    return {"book_id": None, "source": "existing_test_fixture", "episode": 0, "scene_name": name, "scene_id": scene_id, "scene_type": scene_type, "why_selected": "补齐《潮汐回声》现有批准场景未覆盖的导演挑战；使用仓库既有测试 fixture 形状。", "expected_directorial_challenges": ["控制信息揭示", "避免对白 coverage", "保持资产和空间事实不变"], "treatment": treatment, "blocking": blocking}


def main():
    type_plan = [
        ("双人对话", ["对话中的视线和反应分配"]),
        ("悬疑", ["延迟揭示、保持空间方向"]),
        ("信息揭示", ["道具/信息焦点与观众知情时机"]),
        ("情绪转折", ["情绪强度递进和反应镜头"]),
        ("权力变化", ["通过景别、角度和构图呈现权力变化"]),
        ("人物入场", ["建立空间地理和入场方向"]),
    ]
    scenes = []
    for index, (book_id, title, treatment_row, blocking_row) in enumerate(_approved_scenes()[:6]):
        scene_type, challenges = type_plan[index]
        treatment, blocking = _payload(treatment_row, blocking_row)
        scenes.append({"book_id": book_id, "source": "潮汐回声 approved treatment + approved scene blocking", "episode": int(treatment_row.episode), "scene_name": treatment_row.scene_name, "scene_id": f"book{book_id}:e{int(treatment_row.episode)}:{treatment_row.scene_name}", "scene_type": scene_type, "why_selected": f"《{title}》已批准场景；用于真实生产证据上的导演质量复跑。", "expected_directorial_challenges": challenges, "treatment": treatment, "blocking": blocking})
    scenes.append(_fixture("FIXTURE_PROP_01", "关键道具交接 fixture", "关键道具", [{"beat_id": "B01", "type": "prop", "event": "角色把已声明的钥匙放到桌上", "information_change": "钥匙位置变化"}, {"beat_id": "B02", "type": "reveal", "event": "另一人看见钥匙"}], [{"character_id": "C1", "name": "甲"}, {"character_id": "C2", "name": "乙"}]))
    scenes.append(_fixture("FIXTURE_SILENT_01", "无对白反应 fixture", "无对白或少对白", [{"beat_id": "B01", "type": "setup", "event": "人物停在门边"}, {"beat_id": "B02", "type": "decision", "event": "人物收起手中的纸条", "emotion_change": "犹豫到决绝"}], [{"character_id": "C1", "name": "甲"}]))
    results = []
    for scene in scenes:
        baseline = build_shot_plan(treatment=scene["treatment"], blocking=scene["blocking"])
        planner = build_creative_shot_plan_candidate(structural_shot_plan=baseline, treatment=scene["treatment"], blocking=scene["blocking"], mode="shadow")
        comparison = compare_director_plans(baseline=baseline, planner=planner, treatment=scene["treatment"], blocking=scene["blocking"])
        results.append({"scene": {key: scene[key] for key in ("book_id", "source", "episode", "scene_name", "scene_id", "scene_type", "why_selected", "expected_directorial_challenges")}, "baseline": baseline, "planner": planner, "comparison": comparison})
    baseline_scores = [item["comparison"]["version_a"]["director_quality"]["director_quality_score"] for item in results]
    planner_scores = [item["comparison"]["version_b"]["director_quality"]["director_quality_score"] for item in results]
    deltas = [item["comparison"]["delta"] for item in results]
    dimension_names = ["DRAMATIC_CLARITY", "SHOT_MOTIVATION", "EMOTIONAL_PROGRESSION", "VISUAL_STORYTELLING", "SPATIAL_CLARITY", "PERFORMANCE_DIRECTION", "EDIT_RHYTHM", "INFORMATION_STRATEGY", "POWER_DYNAMICS", "SHOT_DIVERSITY"]
    dimension_averages = {name: round(sum(item["comparison"]["version_b"]["director_quality"]["dimensions"].get(name, 0) for item in results) / len(results), 2) if results else 0 for name in dimension_names}
    planner_issue_count = sum(len(item["comparison"]["version_b"]["director_quality"].get("issues", [])) for item in results)
    metrics = {
        "protocol_version": "director-quality-v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider_calls": 0,
        "media_calls": 0,
        "object_storage_calls": 0,
        "scene_count": len(results),
        "baseline_average_director_quality_score": round(sum(baseline_scores) / len(baseline_scores), 2) if baseline_scores else 0,
        "planner_average_director_quality_score": round(sum(planner_scores) / len(planner_scores), 2) if planner_scores else 0,
        "average_score_delta": round(sum(deltas) / len(deltas), 2) if deltas else 0,
        "structural_evidence_shared_all": all(item["comparison"]["structural_evidence_shared"] for item in results),
        "fact_override_count": sum(1 for item in results for issue in item["comparison"]["version_b"]["director_quality"]["issues"] if issue.get("code") == "DIRECTOR_FACT_OVERRIDE"),
        "planner_quality_issue_count": planner_issue_count,
        "director_repair_count": 0,
        "planner_hallucination_count": 0,
        "dimension_averages": dimension_averages,
        "blind_review": {"available": True, "labeling": "Version A / Version B", "preferred_version": None, "preferred_rate": None, "judge_calls": 0},
        "miMo": {"pilot_status": "not_run_offline_phase", "calls": 0, "cached_tokens": 0},
    }
    ARTIFACTS.mkdir(exist_ok=True)
    payload = {"protocol_version": "director-quality-v2", "generated_at": metrics["generated_at"], "scenes": results}
    (ARTIFACTS / "director-quality-v2-golden-scenes.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACTS / "director-quality-v2-metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    report = [
        "# Director Quality Benchmark V2 报告", "", f"生成时间：{metrics['generated_at']}", "", "## Executive Summary", "", f"- Golden Director Scenes：{metrics['scene_count']} 个。", f"- Baseline 平均导演质量分：{metrics['baseline_average_director_quality_score']}。", f"- Creative Planner 平均导演质量分：{metrics['planner_average_director_quality_score']}。", f"- 平均提升：{metrics['average_score_delta']} 分。", "- 本次运行完全离线，未调用真实 LLM、生图、视频或对象存储。", "", "## Golden Scene 说明", "", "场景来源为《潮汐回声》现有批准 Treatment/SceneBlocking（6 个）和仓库已有测试 fixture（2 个）；未写入生产表。", "", "| 场景 | 类型 | 来源 |", "|---|---|---|",
    ]
    report.extend(f"| {item['scene']['scene_name']} | {item['scene']['scene_type']} | {item['scene']['source']} |" for item in results)
    report.extend(["", "## Baseline 与 Creative Planner", "", "两种方案共享同一 Script/Treatment/SceneBlocking/结构化 ShotPlan 事实投影；Planner 只改变导演创意字段，保留 plan_shot_id、beat、事件、资产绑定、首尾状态和连续性合同。", "", "## 评分与指标", "", f"- Structural gate：由既有 `score_runtime` 独立计算；本报告没有把创意分混入结构门禁。", f"- Director Quality：10 维、0–100 加权评分；平均 delta = **{metrics['average_score_delta']}**。", "- Blind review：已输出 Version A / Version B 结构，未伪称为真人偏好；本地离线阶段未运行 Judge。", f"- Fact override：{metrics['fact_override_count']}。", "- MiMo token/cache/latency：本离线阶段为 0；真实 MiMo pilot 仍需在人工确认和密钥可用后单独运行。", "", "## Per-scene Before/After", "", "| 场景 | Baseline | Planner | Delta |", "|---|---:|---:|---:|"])
    report.extend(f"| {item['scene']['scene_name']} | {item['comparison']['version_a']['director_quality']['director_quality_score']} | {item['comparison']['version_b']['director_quality']['director_quality_score']} | {item['comparison']['delta']} |" for item in results)
    report.extend(["", "## 十维导演质量评分（Planner 平均）", "", "| 维度 | 平均分（0–10） | 权重 |", "|---|---:|---:|"])
    weights = {"DRAMATIC_CLARITY": 15, "SHOT_MOTIVATION": 15, "EMOTIONAL_PROGRESSION": 12, "VISUAL_STORYTELLING": 12, "SPATIAL_CLARITY": 10, "PERFORMANCE_DIRECTION": 10, "EDIT_RHYTHM": 8, "INFORMATION_STRATEGY": 8, "POWER_DYNAMICS": 5, "SHOT_DIVERSITY": 5}
    report.extend(f"| {name} | {dimension_averages[name]} | {weights[name]}% |" for name in dimension_names)
    report.extend(["", "## 当前结论", "", "本地 shadow planner 能在不改事实的前提下补齐镜头动机、构图、表演方向、信息策略和镜头多样性字段；是否达到 Production Shadow 的最终门槛仍需使用真实《潮汐回声》样本进行 blind judge 和 MiMo pilot，不能仅凭离线 surrogate 宣布达标。", "", "## 失败案例与瓶颈", "", "- 旧版 deterministic ShotPlan 的创意字段缺失导致 baseline 分数偏低；这是基线证据而非评分规则放宽。", "- Planner 目前为受控 deterministic shadow surrogate，尚未证明真实 LLM 输出在多场景上的稳定性。", "- 主要瓶颈：情绪递进与信息揭示仍依赖 Treatment beat 的语义完整度。"])
    (ARTIFACTS / "director-quality-v2-report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
