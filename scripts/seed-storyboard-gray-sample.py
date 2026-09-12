"""Create a disposable, evidence-complete storyboard sample for real LLM gray runs.

The gray validator intentionally refuses shots with no directing evidence.  This
script creates a small, ordinary project with explicit scene/character assets,
locked reference rows and structured action beats so an operator can validate
the complete compiler path without touching production projects.

Usage:
    python scripts/seed-storyboard-gray-sample.py [book_id]

If ``book_id`` is omitted, the next free id above 990000 is selected.  The
script is idempotent for that id and only removes rows belonging to the sample
book before recreating them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from models import (
    Book,
    DecisionPacketRecord,
    DirectorBenchmarkRun,
    DirectorTreatment,
    EpisodeOutline,
    SceneBlocking,
    Script,
    ShotPlan,
    Session,
    StoryboardShot,
    VisualLocation,
    VisualMakeup,
    VisualReferenceAsset,
    init_db,
)


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def choose_book_id(session, requested: int | None) -> int:
    if requested is not None:
        return requested
    used = {int(value) for (value,) in session.query(Book.id).filter(Book.id >= 990000).all()}
    candidate = 990301
    while candidate in used:
        candidate += 1
    return candidate


def clear_sample(session, book_id: int) -> None:
    # Keep this list deliberately scoped to the sample book; no global cleanup.
    for model in (
        VisualReferenceAsset,
        StoryboardShot,
        ShotPlan,
        SceneBlocking,
        DirectorTreatment,
        DirectorBenchmarkRun,
        DecisionPacketRecord,
        Script,
        VisualMakeup,
        VisualLocation,
        EpisodeOutline,
    ):
        session.query(model).filter(model.book_id == book_id).delete()
    session.query(Book).filter(Book.id == book_id).delete()


def main() -> None:
    init_db()
    requested = int(sys.argv[1]) if len(sys.argv) > 1 else None
    with Session() as session:
        book_id = choose_book_id(session, requested)
        clear_sample(session, book_id)
        book = Book(
            id=book_id,
            title="导演运行时灰度样本",
            filename=f"director-runtime-gray-{book_id}.txt",
            chapter_count=1,
            total_words=120,
            status="storyboarded",
        )
        session.add(book)
        session.flush()

        location = VisualLocation(
            book_id=book_id,
            name="雨夜旧公寓门厅",
            category="室内",
            style="写实电影感，狭窄旧公寓门厅",
            description="老旧公寓门厅，深色铁门、潮湿水泥地面、墙面剥落，门外是雨夜街灯。",
            color_palette="冷青灰，少量暖黄门灯",
            lighting_mood="门外冷色雨光从侧后方进入，门厅顶部一盏昏黄灯形成轮廓光",
            core_prompt_zh="保持深色铁门、潮湿地面和冷青灰雨夜色调的空间连续性。",
            negative_prompt="不要木门，不要明亮白天，不要新增人物",
            asset_status="locked",
        )
        session.add(location)
        session.flush()

        character = VisualMakeup(
            book_id=book_id,
            episode=1,
            character_name="林晚",
            stage_name="scene_雨夜旧公寓门厅",
            refined_outfit="深灰色连帽风衣，黑色长裤，湿润布料贴近肩部",
            refined_accessories="旧帆布挎包，银色钥匙串",
            makeup_spec="自然妆，雨水在脸颊留下细小水痕",
            hair_style="黑色齐肩直发，发梢被雨水打湿",
            expression_mood="警觉、压低情绪",
            core_prompt_zh="成年女性林晚，黑色齐肩直发，深灰连帽风衣，识别特征稳定。",
            negative_prompt="不要男性化五官，不要改变发型，不要鲜艳服装",
            asset_status="locked",
            shot_ids=dumps(["1", "2", "3"]),
            meta_info=dumps({"scope": "scene_variant", "fixture": "director-runtime-gray"}),
        )
        session.add(character)
        session.flush()

        # Keep the fixture executable through the formal script workbench too.
        # Earlier versions only created shots/outlines, which made Treatment
        # preview impossible despite the fixture being called evidence-complete.
        scene_name = location.name
        session.add(Script(
            book_id=book_id,
            episode=1,
            status="done",
            content=dumps({
                "scenes": [{
                    "name": scene_name,
                    "time": "深夜",
                    "location": "旧公寓门厅",
                    "characters": [character.character_name],
                    "character_blocking": [{
                        "name": character.character_name,
                        "position": "screen_right",
                        "facing": "screen_left",
                        "anchor": "铁门右侧",
                    }],
                    "beats": [
                        {"id": "B01", "type": "setup", "event": "林晚推开深色铁门进入门厅"},
                        {"id": "B02", "type": "reveal", "event": "林晚回头确认门外无人，再缓慢关门"},
                        {"id": "B03", "type": "decision", "event": "林晚沿墙走到楼梯口并回望铁门"},
                    ],
                }],
            }),
        ))

        session.add_all(
            [
                VisualReferenceAsset(
                    book_id=book_id,
                    episode=1,
                    asset_type="scene",
                    asset_id=str(location.id),
                    asset_name=location.name,
                    image_url="https://example.com/director-gray-scene.png",
                    reference_token="@雨夜旧公寓门厅",
                    status="locked",
                    prompt=location.core_prompt_zh,
                    model="manual-gray-fixture",
                ),
                VisualReferenceAsset(
                    book_id=book_id,
                    episode=1,
                    asset_type="character",
                    asset_id=str(character.id),
                    asset_name=character.character_name,
                    image_url="https://example.com/director-gray-linwan.png",
                    reference_token="@林晚",
                    status="locked",
                    prompt=character.core_prompt_zh,
                    model="manual-gray-fixture",
                ),
            ]
        )

        shot_specs = [
            {
                "shot_id": 1,
                "duration": 6,
                "camera_movement": "slow push-in",
                "purpose": "reveal",
                "start": "深色铁门关闭，林晚站在门外，雨水顺着风衣滴落。",
                "action": "林晚推开深色铁门进入门厅，回头确认门外无人，再缓慢关门。",
                "end": "铁门重新关闭，林晚停在门厅右侧，手仍握着银色钥匙串。",
                "beats": ["林晚推开深色铁门进入门厅", "她回头确认门外无人，再缓慢关门"],
            },
            {
                "shot_id": 2,
                "duration": 5,
                "camera_movement": "static",
                "purpose": "emotion",
                "start": "铁门已经关闭，林晚站在门厅右侧，手握银色钥匙串。",
                "action": "林晚低头拧干风衣袖口的雨水，抬眼看向门缝，保持身体贴近铁门。",
                "end": "她停止拧袖口，目光锁定门缝，银色钥匙串垂在右手边。",
                "beats": ["林晚拧干风衣袖口的雨水", "她抬眼看向门缝并停住"],
            },
            {
                "shot_id": 3,
                "duration": 6,
                "camera_movement": "slow pan-right",
                "purpose": "suspense",
                "start": "林晚仍站在铁门右侧，目光锁定门缝，钥匙串垂在手边。",
                "action": "林晚沿墙向门厅深处迈出两步，镜头缓慢右摇跟随，她在楼梯口停下回望铁门。",
                "end": "林晚停在楼梯口，半侧身回望关闭的深色铁门，门厅保持安静。",
                "beats": ["林晚沿墙向门厅深处迈出两步", "她在楼梯口停下回望铁门"],
            },
        ]
        for spec in shot_specs:
            structured = {
                "scene_asset_id": str(location.id),
                "character_asset_ids": [str(character.id)],
                "prop_asset_ids": [],
                "style_key": "realistic-cinematic",
                "character_blocking": [
                    {
                        "character_id": str(character.id),
                        "visual_alias": "林晚",
                        "screen_position": "画面右侧门厅",
                        "pose": "半侧身，手握银色钥匙串",
                        "emotion": "警觉",
                        "status": "declared",
                    }
                ],
                "action_beats": [
                    {"sequence": index, "description": beat, "emotion": "警觉", "intensity": "medium"}
                    for index, beat in enumerate(spec["beats"], start=1)
                ],
            }
            session.add(StoryboardShot(
                book_id=book_id,
                episode=1,
                scene_name=location.name,
                shot_id=spec["shot_id"],
                dialogue="",
                duration=spec["duration"],
                camera_angle="MS",
                camera_movement=spec["camera_movement"],
                camera_speed="slow",
                shot_purpose=spec["purpose"],
                transition="cut",
                lighting=location.lighting_mood,
                start_state=spec["start"],
                action_process=spec["action"],
                end_state=spec["end"],
                emotion_arc=dumps({"start": "警觉", "end": "压抑", "intensity": "medium"}),
                asset_links=dumps({"references": {"scene": [], "character": []}}),
                meta_info=dumps({"structured_shot": structured}),
                asset_status="asset_ready",
            ))
        session.add(
            EpisodeOutline(
                book_id=book_id,
                episode=1,
                title="雨夜回家",
                core_event="林晚在雨夜回到旧公寓并确认身后无人。",
                characters=dumps(["林晚"]),
                scenes=dumps([location.name]),
            )
        )
        session.commit()
        print(json.dumps({"book_id": book_id, "episode": 1, "shot_ids": [1, 2, 3], "scene_asset_id": str(location.id), "character_asset_id": str(character.id)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
