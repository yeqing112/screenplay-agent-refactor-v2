import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.scene_setup import SceneSetupAgent
from models import CharacterProfile, Session, VisualMakeup


def _load_json_dict(value):
    if not value:
        return {}
    try:
        data = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _load_json_list(value):
    if not value:
        return []
    try:
        data = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _build_result(agent: SceneSetupAgent, row: VisualMakeup, profile, meta_info: dict) -> dict:
    structured = deepcopy(meta_info.get("structured_result", {})) if isinstance(meta_info.get("structured_result"), dict) else {}
    result = {
        "scope": structured.get("scope") or meta_info.get("scope") or "",
        "character_name": row.character_name,
        "episode": row.episode,
        "stage_name": row.stage_name or "",
        "variant_name": structured.get("variant_name") or row.stage_name or f"第{row.episode}集默认造型",
        "shot_ids": structured.get("shot_ids") or _load_json_list(getattr(row, "shot_ids", None)),
        "refined_outfit": row.refined_outfit or "",
        "refined_accessories": row.refined_accessories or "",
        "makeup_spec": row.makeup_spec or "",
        "hair_style": row.hair_style or "",
        "expression_mood": row.expression_mood or "",
        "core_prompt_zh": row.core_prompt_zh or "",
        "outfit_prompt_zh": row.outfit_prompt_zh or "",
        "scene_prompt_zh": row.scene_prompt_zh or "",
        "consistency_notes": row.consistency_notes or "",
        "age": str(structured.get("age") or getattr(profile, "precise_age", "") or ""),
        "region": str(structured.get("region") or "中国"),
        "gender": str(structured.get("gender") or getattr(profile, "gender", "") or ""),
        "identity": str(structured.get("identity") or getattr(profile, "identity", "") or ""),
        "temperament": str(structured.get("temperament") or getattr(profile, "temperament", "") or ""),
    }
    result["scope"] = agent._normalize_makeup_scope(result)
    if not result["variant_name"]:
        if result["scope"] == "episode_default":
            result["variant_name"] = f"第{row.episode}集默认造型"
        elif result["scope"] == "base_identity":
            result["variant_name"] = "基础定妆"
        else:
            result["variant_name"] = row.stage_name or result["scope"]
    result["stage_name"] = agent._default_stage_name(result["scope"], row.episode, result)
    return result


def _should_update(row: VisualMakeup, prompt: str, meta_info: dict, force: bool) -> bool:
    if force:
        return True
    current = str(row.visual_prompt_zh or "")
    if current.startswith("定妆照六宫格布局：纯白背景"):
        return True
    if meta_info.get("scope") == "episode_default" and current.startswith("人物分镜精调定妆设定板"):
        return True
    return not bool(meta_info.get("rendered_from_template"))


def run(book_ids: list[int], force: bool) -> list[dict]:
    results: list[dict] = []
    grouped_agents: dict[int, SceneSetupAgent] = {}
    with Session() as session:
        rows = session.query(VisualMakeup).filter(VisualMakeup.book_id.in_(book_ids)).order_by(
            VisualMakeup.book_id, VisualMakeup.episode, VisualMakeup.id
        ).all()
        for row in rows:
            grouped_agents.setdefault(row.book_id, SceneSetupAgent(row.book_id))
            agent = grouped_agents[row.book_id]
            profile = session.query(CharacterProfile).filter(
                CharacterProfile.book_id == row.book_id,
                CharacterProfile.name == row.character_name,
            ).first()
            meta_info = _load_json_dict(row.meta_info)
            result = _build_result(agent, row, profile, meta_info)
            rendered = agent._render_makeup_prompt_from_result(row.character_name, row.episode, profile or object(), result)
            changed = _should_update(row, rendered, meta_info, force)
            if changed:
                next_meta = deepcopy(meta_info)
                next_meta.update({
                    "scope": result["scope"],
                    "template_version": "makeup_six_grid_v2",
                    "rendered_from_template": True,
                    "prompt_source": next_meta.get("prompt_source") or "migration:legacy-visual-makeup",
                    "structured_result": result,
                    "episode": row.episode,
                    "character_name": row.character_name,
                })
                row.stage_name = result["stage_name"]
                row.visual_prompt_zh = rendered
                row.meta_info = json.dumps(next_meta, ensure_ascii=False)
            results.append({
                "book_id": row.book_id,
                "id": row.id,
                "character_name": row.character_name,
                "scope": result["scope"],
                "stage_name": result["stage_name"],
                "updated": changed,
                "prompt_head": rendered[:80],
            })
        session.commit()
    return results


def main():
    parser = argparse.ArgumentParser(description="Re-render legacy VisualMakeup prompts with fixed six-view templates.")
    parser.add_argument("--book-id", dest="book_ids", action="append", type=int, required=True, help="Book id to migrate. Repeat for multiple books.")
    parser.add_argument("--force", action="store_true", help="Rewrite all matching rows even if they already use the new template.")
    args = parser.parse_args()

    results = run(args.book_ids, args.force)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
