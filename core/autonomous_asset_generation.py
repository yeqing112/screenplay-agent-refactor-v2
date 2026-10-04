"""Provider agnostic autonomous visual asset generation contracts.

The runtime keeps topology and repair state separate from provider media.  A
provider image is an implementation of the geometry contract; it never becomes
the sole source of spatial truth.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
from math import ceil
from typing import Any


class AutonomousAssetState(str, Enum):
    PLANNING = "PLANNING"
    PRIMARY_GENERATING = "PRIMARY_GENERATING"
    PRIMARY_READY = "PRIMARY_READY"
    DERIVING = "DERIVING"
    VALIDATING = "VALIDATING"
    REPAIRING = "REPAIRING"
    READY = "READY"
    FAILED = "FAILED"


@dataclass(frozen=True)
class AssetGenerationBudgetPolicy:
    normal_calls_max: int = 7
    max_attempts_per_view: int = 3
    architecture_threshold: int = 85
    landmarks_threshold: int = 85
    furniture_threshold: int = 80
    lighting_threshold: int = 80


@dataclass(frozen=True)
class SceneGeometryIR:
    scene_id: str
    walls: list[str]
    zones: list[str]
    doors: list[dict[str, Any]]
    windows: list[dict[str, Any]]
    fixed_furniture: list[dict[str, Any]]
    fixed_props: list[dict[str, Any]]
    landmarks: list[str]
    relative_positions: list[dict[str, Any]]
    adjacency: list[dict[str, Any]]
    lighting_sources: list[str]
    lighting_directions: list[str]
    materials: list[str]
    time: str
    weather: str

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SceneDerivedViewPlan:
    view_id: str
    view_type: str
    camera_position: str
    camera_direction: str
    visible_landmarks: list[str]
    occluded_landmarks: list[str]
    required_landmarks: list[str]
    forbidden_changes: list[str]


@dataclass
class AssetRepairContext:
    view_id: str
    previous_prompt: str
    failed_output: dict[str, Any]
    violations: list[str]
    required_corrections: list[str]
    attempt_number: int


@dataclass
class SceneConsistencyAudit:
    view_id: str
    status: str
    same_physical_space: bool
    architecture_score: int
    landmark_score: int
    furniture_score: int
    lighting_score: int
    critical_topology_violations: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    judge_status: str = ""
    attempt_number: int = 1

    @property
    def passes(self) -> bool:
        return (
            self.status == "PASS"
            and self.same_physical_space
            and self.architecture_score >= 85
            and self.landmark_score >= 85
            and self.furniture_score >= 80
            and self.lighting_score >= 80
            and not self.critical_topology_violations
        )


class AutonomousAssetGeneration:
    """State machine shared by CHARACTER, SCENE and PROP asset pipelines."""

    def __init__(self, *, asset_type: str, asset_id: str, budget: AssetGenerationBudgetPolicy | None = None) -> None:
        normalized = str(asset_type or "").upper()
        if normalized not in {"CHARACTER", "SCENE", "PROP"}:
            raise ValueError("asset_type must be CHARACTER, SCENE or PROP")
        self.asset_type = normalized
        self.asset_id = str(asset_id)
        self.budget = budget or AssetGenerationBudgetPolicy()
        self.state = AutonomousAssetState.PLANNING
        self.image_calls = 0
        self.repairs: list[AssetRepairContext] = []
        self.audits: list[SceneConsistencyAudit] = []
        self.geometry: SceneGeometryIR | None = None
        self.derived_plans: list[SceneDerivedViewPlan] = []
        self.media: dict[str, dict[str, Any]] = {}

    def plan_scene(self, geometry: SceneGeometryIR, plans: list[SceneDerivedViewPlan]) -> None:
        if self.asset_type != "SCENE":
            raise RuntimeError("SceneGeometryIR is only valid for SCENE generation")
        if not geometry.scene_id or not plans:
            raise ValueError("scene geometry and derived view plans are required")
        self.geometry = geometry
        self.derived_plans = list(plans)
        self.state = AutonomousAssetState.PRIMARY_GENERATING

    def claim_image_call(self) -> int:
        if self.image_calls >= self.budget.normal_calls_max:
            raise RuntimeError("ASSET_GENERATION_BUDGET_EXCEEDED")
        self.image_calls += 1
        return self.image_calls

    def record_primary(self, media: dict[str, Any]) -> None:
        self.media["MASTER"] = dict(media)
        self.state = AutonomousAssetState.PRIMARY_READY

    def begin_derivation(self) -> None:
        if "MASTER" not in self.media:
            raise RuntimeError("PRIMARY_REFERENCE_REQUIRED")
        self.state = AutonomousAssetState.DERIVING

    def record_derived(self, view_id: str, media: dict[str, Any]) -> None:
        self.media[str(view_id)] = dict(media)

    def record_audit(self, audit: SceneConsistencyAudit) -> None:
        self.audits.append(audit)
        self.state = AutonomousAssetState.VALIDATING

    def prepare_repair(self, context: AssetRepairContext) -> None:
        if context.attempt_number > self.budget.max_attempts_per_view:
            self.state = AutonomousAssetState.FAILED
            raise RuntimeError("ASSET_CONSISTENCY_GENERATION_FAILED")
        self.repairs.append(context)
        self.state = AutonomousAssetState.REPAIRING

    def lock(self) -> dict[str, Any]:
        required = {"MASTER", "REVERSE", "SIDE", "DETAIL"}
        if not required.issubset(self.media):
            self.state = AutonomousAssetState.FAILED
            raise RuntimeError("REQUIRED_SCENE_VIEWS_MISSING")
        latest = {audit.view_id: audit for audit in self.audits}
        if not all(audit.passes for audit in latest.values() if audit.view_id != "MASTER"):
            self.state = AutonomousAssetState.FAILED
            raise RuntimeError("SCENE_CONSISTENCY_GATE_FAILED")
        self.state = AutonomousAssetState.READY
        return {
            "scene_id": self.geometry.scene_id if self.geometry else self.asset_id,
            "geometry_fingerprint": self.geometry.fingerprint if self.geometry else "",
            "views": sorted(required),
            "view_fingerprints": {key: value.get("fingerprint", "") for key, value in self.media.items()},
            "consistency_audit_count": len(self.audits),
            "repair_count": len(self.repairs),
            "image_calls": self.image_calls,
            "status": self.state.value,
        }


def geometry_constrained_prompt(geometry: SceneGeometryIR, plan: SceneDerivedViewPlan, *, repair: AssetRepairContext | None = None) -> str:
    """Render a provider-facing single-view prompt from topology authority."""

    geometry_text = json.dumps(asdict(geometry), ensure_ascii=False, sort_keys=True)
    plan_text = json.dumps(asdict(plan), ensure_ascii=False, sort_keys=True)
    repair_text = ""
    if repair:
        repair_text = (
            "\n这是自动修复，不得重新设计房间。上一版违规如下："
            + "；".join(repair.violations)
            + "。本次必须修正："
            + "；".join(repair.required_corrections)
        )
    return (
        "单张写实电影场景参考图，不要拼图，不要四宫格，不要文字标签，不要人物。"
        "这是与 SceneGeometryIR 完全相同的物理房间，只改变相机位置、相机朝向和自然遮挡；禁止改变墙体、门、窗、"
        "水槽、餐桌、橱柜、固定家具、材质、时间、天气和灯光方向。"
        f"\nSceneGeometryIR：{geometry_text}\nSceneDerivedViewPlan：{plan_text}"
        "\n输出必须是一张完整可读的单视图，所有可见地标按计划保持相对拓扑。"
        + repair_text
    )


__all__ = [
    "AssetGenerationBudgetPolicy",
    "AssetRepairContext",
    "AutonomousAssetGeneration",
    "AutonomousAssetState",
    "SceneConsistencyAudit",
    "SceneDerivedViewPlan",
    "SceneGeometryIR",
    "geometry_constrained_prompt",
]
