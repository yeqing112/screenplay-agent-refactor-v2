from core.director_skills import apply_skill, list_skills
from core.director_plan import build_director_plan
from core.director_agent_draft import build_agent_draft_preview


def test_builtin_skills_are_declarative_and_constrain_operations():
    skills = {row["id"]: row for row in list_skills()}
    assert {"short_drama_production", "continuity", "tvc", "children_education"} <= set(skills)
    skill, operations = apply_skill("continuity", [{"operation": "continuity_check"}, {"operation": "unknown_shell"}])
    assert skill and skill["version"] == "1.0.0"
    assert operations == [{"operation": "continuity_check"}]


def test_skill_is_frozen_in_plan_and_preview_prompt():
    skill, operations = apply_skill("continuity", [{"operation": "continuity_check"}])
    plan = build_director_plan("检查连续性", {"book_id": 1, "skill": {"id": skill["id"], "version": skill["version"]}}, {}, operations)
    preview = build_agent_draft_preview(objective="检查连续性", plan=plan, profile={"id": "x", "name": "test"})
    assert "连续性监督" in preview["system_prompt"]
    assert preview["evidence"]["scope"]["skill"]["id"] == "continuity"
