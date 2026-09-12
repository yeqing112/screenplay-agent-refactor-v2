"""Seed/clean a disposable fixture for the machine-prompt export browser flow.

This fixture is deliberately independent from any user project.  It provides
the minimum upstream approvals (locked adaptation + released script), one
structured shot, locked scene/character references, and a baseline prompt
version so the browser test follows the same gates as a real project.

Usage:
    python scripts/seed-machine-prompt-export-fixture.py seed <book_id>
    python scripts/seed-machine-prompt-export-fixture.py cleanup <book_id>
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from models import (  # noqa: E402
    Book,
    EpisodeOutline,
    ProductionExportRecord,
    Script,
    Session,
    StoryboardPromptVersion,
    StoryboardShot,
    TaskRun,
    VisualLocation,
    VisualMakeup,
    VisualReferenceAsset,
    get_kv,
    init_db,
    set_kv,
)


def dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def decision_path(book_id: int) -> Path:
    path = ROOT_DIR / "script_decisions" / f"book_{book_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def cleanup(book_id: int) -> None:
    """Remove only rows/state owned by this reserved fixture book."""
    init_db()
    with Session() as session:
        for model in (
            ProductionExportRecord,
            TaskRun,
            StoryboardPromptVersion,
            StoryboardShot,
            VisualReferenceAsset,
            VisualMakeup,
            VisualLocation,
            EpisodeOutline,
            Script,
        ):
            session.query(model).filter(model.book_id == book_id).delete()
        session.query(Book).filter(Book.id == book_id).delete()
        session.commit()
    for key in (
        f"product_workspace:adaptation:{book_id}",
        f"product_workspace:production_skill:{book_id}",
        f"production_skill_state:{book_id}",
    ):
        # set_kv is the project KV abstraction; delete through the model so
        # cleanup remains idempotent even when a key was never created.
        from models import KV

        with Session() as session:
            session.query(KV).filter(KV.key == key).delete(synchronize_session=False)
            session.commit()
    path = decision_path(book_id)
    if path.exists():
        path.unlink()


def seed(book_id: int) -> dict[str, object]:
    cleanup(book_id)
    now = datetime.now(timezone.utc).isoformat()
    image_url = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='320' height='180'%3E%3Crect width='320' height='180' fill='%230f172a'/%3E%3Ctext x='30' y='100' fill='%23bae6fd' font-size='20'%3EE2E Export%3C/text%3E%3C/svg%3E"
    init_db()
    with Session() as session:
        session.add(Book(
            id=book_id,
            title="机器提示词导出回归样本",
            filename=f"machine-prompt-export-{book_id}.txt",
            chapter_count=1,
            total_words=180,
            status="storyboarded",
        ))
        session.add(EpisodeOutline(
            book_id=book_id,
            episode=1,
            title="夜班收银台",
            core_event="林小夏在深夜便利店发现异常来客。",
            characters=dumps(["林小夏"]),
            scenes=dumps(["深夜便利店收银台"]),
        ))
        session.add(Script(
            book_id=book_id,
            episode=1,
            status="done",
            content="深夜便利店收银台。林小夏听到门铃后停顿，随后把视线投向门口。",
        ))
        location = VisualLocation(
            book_id=book_id,
            name="深夜便利店收银台",
            category="interior",
            style="写实电影感",
            description="狭窄收银台、扫码器、烟架与冷白荧光灯，门外是深夜街道。",
            visual_prompt_zh="深夜便利店收银台，冷白荧光灯，狭窄空间，写实电影感",
            asset_status="locked",
        )
        character = VisualMakeup(
            book_id=book_id,
            episode=1,
            character_name="林小夏",
            stage_name="便利店夜班",
            refined_outfit="深色便利店员工外套",
            hair_style="黑色短发",
            makeup_spec="自然妆",
            visual_prompt_zh="成年女性林小夏，黑色短发，深色便利店员工外套",
            asset_status="locked",
        )
        session.add_all([location, character])
        session.flush()
        session.add_all([
            VisualReferenceAsset(
                book_id=book_id, episode=1, asset_type="scene", asset_id=str(location.id),
                asset_name=location.name, image_url=image_url,
                reference_token="@深夜便利店收银台", status="locked",
                prompt=location.visual_prompt_zh, model="e2e-fixture",
            ),
            VisualReferenceAsset(
                book_id=book_id, episode=1, asset_type="character", asset_id=str(character.id),
                asset_name=character.character_name, image_url=image_url,
                reference_token="@林小夏", status="locked",
                prompt=character.visual_prompt_zh, model="e2e-fixture",
            ),
        ])
        structured = {
            "scene_asset_id": str(location.id),
            "character_asset_ids": [str(character.id)],
            "prop_asset_ids": [],
            "style_key": "cinematic-default",
            "character_blocking": [{
                "character_id": str(character.id), "visual_alias": "林小夏",
                "screen_position": "收银台内侧", "pose": "站立，视线投向门口",
                "emotion": "警觉", "status": "declared",
            }],
            "action_beats": [{
                "sequence": 1, "description": "林小夏听到门铃后停顿，再把视线投向门口。",
                "emotion": "警觉", "intensity": "medium",
            }],
        }
        prompt_context = {
            "asset_bindings": {
                "scene": {"asset_id": str(location.id), "asset_name": location.name, "reference_status": "locked"},
                "characters": [{"asset_id": str(character.id), "asset_name": character.character_name, "reference_status": "locked"}],
                "props": [],
            },
            "acceptance_feedback": {},
        }
        shot = StoryboardShot(
            book_id=book_id, episode=1, scene_name=location.name, shot_id=1,
            dialogue="", duration=4, camera_angle="MS", camera_movement="slow push-in",
            transition="cut", lighting="冷白荧光灯，门外深夜冷色光",
            start_state="收银台安静，林小夏正在整理台面。",
            action_process="门铃响起；林小夏停顿，把视线投向门口。",
            end_state="她保持警觉，视线停在门口。",
            visual_prompt_static="深夜便利店收银台，林小夏站在台内，冷白荧光灯，电影感中景。",
            visual_prompt_motion="门铃响起，林小夏先停顿，再缓慢把视线投向门口，镜头轻微推进。",
            visual_prompt_final="字幕, 水印, 变形手指",
            asset_links=dumps({"references": {"scene": [], "character": []}}),
            asset_status="asset_ready",
            meta_info=dumps({"structured_shot": structured}),
        )
        session.add(shot)
        session.add(StoryboardPromptVersion(
            book_id=book_id, episode=1, shot_id=1, version=1,
            compile_reason="fixture-baseline",
            prompt_static=shot.visual_prompt_static,
            prompt_motion=shot.visual_prompt_motion,
            negative_prompt=shot.visual_prompt_final,
            meta_info=dumps({"prompt_compile_context": prompt_context, "compiler_diagnostics": {"score": 90}}),
        ))
        session.commit()

    set_kv(f"product_workspace:adaptation:{book_id}", dumps({
        "book_id": book_id, "selected_id": "emotion-suspense",
        "selected_name": "竖屏情绪悬疑短剧", "locked_at": now,
        "created_at": now, "updated_at": now,
    }))
    set_kv(f"product_workspace:production_skill:{book_id}", dumps({
        "skill_id": "rebirth_suspense", "platform": "douyin",
        "track": "悬疑", "emotion_goal": "高压悬念", "locked_at": now,
    }))
    decision_path(book_id).write_text(json.dumps({
        "book_id": book_id,
        "episodes": {"1": {"locked_at": now, "released_at": now, "note": "E2E fixture"}},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"book_id": book_id, "episode": 1, "shot_id": 1}


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in {"seed", "cleanup"}:
        raise SystemExit("usage: seed-machine-prompt-export-fixture.py seed|cleanup <book_id>")
    target = int(sys.argv[2])
    result = seed(target) if sys.argv[1] == "seed" else (cleanup(target) or {"book_id": target, "cleaned": True})
    print(json.dumps(result or {}, ensure_ascii=False))
