from collections import Counter
import importlib.util
from pathlib import Path


_SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "audit-shot-executability-replay.py"
_SPEC = importlib.util.spec_from_file_location("shot_executability_replay", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
_missing_required_statuses = _MODULE._missing_required_statuses
_build_gate_actions = _MODULE._build_gate_actions


def test_missing_required_statuses_reports_only_absent_states():
    counts = Counter({"ready": 2, "conflict": 1})
    assert _missing_required_statuses(counts, ["ready", "needs_information", "conflict"]) == [
        "needs_information"
    ]


def test_missing_required_statuses_accepts_all_required_states():
    counts = Counter({"ready": 2, "needs_information": 1, "conflict": 1})
    assert _missing_required_statuses(counts, ["ready", "needs_information", "conflict"]) == []


def test_gate_actions_explain_count_and_state_blockers_without_project_specific_rules():
    blockers, actions = _build_gate_actions(
        sampled_shots=3,
        required_minimum=30,
        missing_intent=["needs_information"],
        missing_timing=["conflict"],
    )
    assert blockers == [
        "真实 active 镜头不足（3/30）",
        "缺少意图状态：needs_information",
        "缺少节拍状态：conflict",
    ]
    assert actions == [
        "补充真实 active 镜头，直到达到至少 30 个",
        "在正式镜头工作台补齐意图证据：needs_information",
        "在正式镜头工作台补齐节拍证据：conflict",
    ]


def test_gate_actions_offer_next_stage_when_all_contracts_are_met():
    blockers, actions = _build_gate_actions(
        sampled_shots=30,
        required_minimum=30,
        missing_intent=[],
        missing_timing=[],
    )
    assert blockers == []
    assert actions == ["继续执行真实浏览器回归和受控媒体灰度"]
