"""Validate reversible storyboard prompt repair on a cloned real-project shot.

This script intentionally writes only to a temporary book id and removes it
after each sample. It clones real storyboard shots, downgrades each clone to a
short prompt with an empty scene_asset_id, then verifies that the normal backend
compile and rollback APIs can repair and fully restore the clone.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.server import (
    _auto_bind_structured_shot_assets,
    _build_prompt_compile_context_v2,
    _build_storyboard_reference_summary,
    _build_storyboard_reference_summary_from_bound_assets,
    _derive_structured_shot_payload,
    _load_asset_links,
    _load_episode_makeup_prompt_stub,
    app,
)
from core.model_adapter import adapt_ir_to_model
from core.prompt_ir import build_shot_ir_from_context
from core.rule_compiler import compile_rules
from models import (
    Book,
    Session,
    StoryboardPromptVersion,
    StoryboardShot,
    VisualLocation,
    VisualMakeup,
    VisualProp,
    VisualReferenceAsset,
    init_db,
)


DEFAULT_SOURCE_SAMPLES = "75:1:1,14:1:1,5:1:1,3:1:1,1:1:1"
TEMP_BOOK_ID = int(os.environ.get("VALIDATE_STORYBOARD_REPAIR_TEMP_BOOK_ID", "999904"))


def log(message: str) -> None:
    print(f"[storyboard-repair-clone] {message}")


def safe_json_loads(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
        return parsed if parsed is not None else fallback
    except Exception:
        return fallback


def clean_prompt_fact(value: Any, max_len: int = 140) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for old, new in {
        "\r": "，",
        "\n": "，",
        "\t": "，",
        "：": "，",
        ":": "，",
        "[": "",
        "]": "",
        "【": "",
        "】": "",
        "（": "",
        "）": "",
        "(": "",
        ")": "",
    }.items():
        text = text.replace(old, new)
    text = "，".join([fragment.strip() for fragment in text.split("，") if fragment.strip()])
    if len(text) > max_len:
        text = text[:max_len].rstrip("，、；; ")
    return text


def asset_part_map(asset: dict[str, Any], field: str) -> dict[str, str]:
    parts = asset.get(field, []) if isinstance(asset.get(field, []), list) else []
    result: dict[str, str] = {}
    for part in parts:
        if not isinstance(part, dict):
            continue
        key = str(part.get("key") or "").strip()
        text = clean_prompt_fact(part.get("text"))
        if key and text and key not in result:
            result[key] = text
    return result


def asset_fact_snippets(asset: dict[str, Any]) -> list[str]:
    """Return compact visual facts that should naturally appear in repaired prompts."""

    asset_type = str(asset.get("asset_type") or "").strip()
    name = clean_prompt_fact(asset.get("asset_name"), max_len=40)
    canonical_profile = asset.get("canonical_prompt_profile", {})
    canonical_profile = canonical_profile if isinstance(canonical_profile, dict) else {}
    authority_parts = asset_part_map(asset, "authority_prompt_parts")
    canonical_parts = asset_part_map(asset, "canonical_prompt_parts")

    if asset_type == "character":
        ordered_keys = [
            "refined_outfit",
            "makeup_spec",
            "hair_style",
            "canonical_outfit",
            "canonical_makeup_expression",
            "canonical_hairstyle",
            "canonical_scene_effects",
            "canonical_appearance",
        ]
        profile_keys = [
            "outfit",
            "makeup_expression",
            "hairstyle",
            "scene_effects",
            "appearance",
            "temperament",
        ]
        max_snippets = 5
    elif asset_type == "scene":
        ordered_keys = [
            "description",
            "style",
            "lighting_mood",
            "color_palette",
            "core_visual",
            "canonical_description",
            "canonical_style",
            "canonical_lighting_mood",
            "canonical_color_palette",
            "canonical_core_visual",
        ]
        profile_keys = ["description", "style", "lighting_mood", "color_palette", "core_visual"]
        max_snippets = 4
    elif asset_type == "prop":
        ordered_keys = [
            "description",
            "core_visual",
            "canonical_description",
            "canonical_core_visual",
            "category",
            "canonical_category",
        ]
        profile_keys = ["description", "core_visual", "category"]
        max_snippets = 3
    else:
        ordered_keys = []
        profile_keys = []
        max_snippets = 2

    snippets: list[str] = []
    if name:
        snippets.append(name)
    for key in ordered_keys:
        for source in (authority_parts, canonical_parts):
            text = source.get(key)
            if text and text not in snippets:
                snippets.append(text)
    for key in profile_keys:
        text = clean_prompt_fact(canonical_profile.get(key))
        if text and text not in snippets:
            snippets.append(text)
    return snippets[:max_snippets]


def build_asset_fact_phrase(bound_assets: list[dict[str, Any]]) -> str:
    phrases: list[str] = []
    for asset in bound_assets:
        snippets = asset_fact_snippets(asset)
        if not snippets:
            continue
        asset_type = str(asset.get("asset_type") or "").strip()
        lead = "人物" if asset_type == "character" else "场景" if asset_type == "scene" else "道具" if asset_type == "prop" else "资产"
        phrases.append(f"{lead}保持{'，'.join(snippets)}")
    return "；".join(phrases)


def parse_source_samples() -> list[tuple[int, int, int]]:
    sample_text = os.environ.get("VALIDATE_STORYBOARD_REPAIR_SAMPLES")
    if not sample_text:
        legacy_book = os.environ.get("VALIDATE_STORYBOARD_REPAIR_SOURCE_BOOK_ID")
        legacy_episode = os.environ.get("VALIDATE_STORYBOARD_REPAIR_SOURCE_EPISODE")
        legacy_shot = os.environ.get("VALIDATE_STORYBOARD_REPAIR_SOURCE_SHOT_ID")
        if legacy_book or legacy_episode or legacy_shot:
            sample_text = f"{legacy_book or '75'}:{legacy_episode or '1'}:{legacy_shot or '1'}"
        else:
            sample_text = DEFAULT_SOURCE_SAMPLES

    samples: list[tuple[int, int, int]] = []
    for token in sample_text.split(","):
        value = token.strip()
        if not value:
            continue
        parts = value.split(":")
        if len(parts) != 3:
            raise RuntimeError(
                "Invalid VALIDATE_STORYBOARD_REPAIR_SAMPLES item "
                f"{value!r}; expected book_id:episode:shot_id."
            )
        try:
            samples.append((int(parts[0]), int(parts[1]), int(parts[2])))
        except ValueError as exc:
            raise RuntimeError(
                "Invalid VALIDATE_STORYBOARD_REPAIR_SAMPLES item "
                f"{value!r}; all fields must be integers."
            ) from exc
    if not samples:
        raise RuntimeError("No source samples configured for clone repair validation.")
    return samples


def cleanup_temp_book() -> None:
    with Session() as session:
        for model in [
            StoryboardPromptVersion,
            StoryboardShot,
            VisualReferenceAsset,
            VisualMakeup,
            VisualLocation,
            VisualProp,
        ]:
            session.query(model).filter(model.book_id == TEMP_BOOK_ID).delete()
        session.query(Book).filter(Book.id == TEMP_BOOK_ID).delete()
        session.commit()


def clone_row(session, row, model, **overrides):
    payload = {}
    for column in model.__table__.columns:
        if column.name == "id":
            continue
        payload[column.name] = getattr(row, column.name)
    payload.update(overrides)
    clone = model(**payload)
    session.add(clone)
    session.flush()
    return clone


def remap_structured_asset_ids(structured: dict[str, Any], location_map: dict[str, str], makeup_map: dict[str, str], prop_map: dict[str, str]) -> dict[str, Any]:
    remapped = dict(structured or {})
    scene_asset_id = str(remapped.get("scene_asset_id") or "").strip()
    remapped["scene_asset_id"] = location_map.get(scene_asset_id, scene_asset_id if scene_asset_id in set(location_map.values()) else "")
    remapped["character_asset_ids"] = remap_structured_id_list(
        remapped.get("character_asset_ids") or [],
        makeup_map,
        preserve_unmapped=True,
    )
    remapped["prop_asset_ids"] = remap_structured_id_list(
        remapped.get("prop_asset_ids") or [],
        prop_map,
        preserve_unmapped=True,
    )
    character_blocking = remapped.get("character_blocking")
    if isinstance(character_blocking, list):
        remapped["character_blocking"] = [
            remap_character_blocking_item(item, makeup_map)
            for item in character_blocking
            if isinstance(item, dict)
        ]
    return remapped


def remap_structured_id_list(values: list[Any], mapping: dict[str, str], *, preserve_unmapped: bool) -> list[str]:
    mapped_values: list[str] = []
    existing_targets = set(mapping.values())
    for value in values:
        source = str(value or "").strip()
        if not source:
            continue
        mapped = mapping.get(source)
        if mapped:
            mapped_values.append(mapped)
        elif source in existing_targets or preserve_unmapped:
            mapped_values.append(source)
    return list(dict.fromkeys(mapped_values))


def remap_character_blocking_item(item: dict[str, Any], makeup_map: dict[str, str]) -> dict[str, Any]:
    remapped = dict(item)
    source = str(remapped.get("character_id") or "").strip()
    if source and source in makeup_map:
        remapped["character_id"] = makeup_map[source]
    return remapped


def clone_source_to_temp(source_book_id: int, source_episode: int, source_shot_id: int, baseline_mode: str = "degraded") -> dict[str, Any]:
    if baseline_mode not in {"degraded", "source"}:
        raise RuntimeError(f"Unsupported clone baseline mode: {baseline_mode}")
    cleanup_temp_book()
    now = datetime.utcnow()

    with Session() as session:
        source_book = session.get(Book, source_book_id)
        source_shot = (
            session.query(StoryboardShot)
            .filter(
                StoryboardShot.book_id == source_book_id,
                StoryboardShot.episode == source_episode,
                StoryboardShot.shot_id == source_shot_id,
            )
            .first()
        )
        if not source_book or not source_shot:
            raise RuntimeError(
                f"Source shot not found: book={source_book_id}, episode={source_episode}, shot={source_shot_id}"
            )

        session.add(
            Book(
                id=TEMP_BOOK_ID,
                title=f"CLONE quality repair #{source_book_id}-{source_episode}-{source_shot_id}",
                filename=f"clone-storyboard-quality-repair-{source_book_id}-{source_episode}-{source_shot_id}.txt",
                chapter_count=source_book.chapter_count or 1,
                total_words=source_book.total_words or 1,
                status="storyboarded",
                created_at=now,
            )
        )

        location_map: dict[str, str] = {}
        makeup_map: dict[str, str] = {}
        prop_map: dict[str, str] = {}

        source_locations = session.query(VisualLocation).filter(VisualLocation.book_id == source_book_id).all()
        for row in source_locations:
            clone = clone_row(session, row, VisualLocation, book_id=TEMP_BOOK_ID, book_title=f"CLONE {source_book_id}")
            location_map[str(row.id)] = str(clone.id)

        # Some older real projects have storyboard rows but no scene asset rows.
        # Add a temp-only repair target so the clone can validate scene auto-binding
        # without changing the original project.
        if not any(row.name == source_shot.scene_name for row in source_locations):
            clone = VisualLocation(
                book_id=TEMP_BOOK_ID,
                book_title=f"CLONE {source_book_id}",
                name=source_shot.scene_name,
                category="cloned-scene",
                description=f"Temporary cloned scene asset for source book {source_book_id}.",
                visual_prompt_zh=f"{source_shot.scene_name}，真实项目克隆验证场景，保持原镜头空间、光线和氛围。",
                lighting_mood=source_shot.lighting or "",
                asset_status="ref_ready",
                created_at=now,
                updated_at=now,
            )
            session.add(clone)
            session.flush()

        for row in session.query(VisualMakeup).filter(VisualMakeup.book_id == source_book_id).all():
            clone = clone_row(
                session,
                row,
                VisualMakeup,
                book_id=TEMP_BOOK_ID,
                book_title=f"CLONE {source_book_id}",
            )
            makeup_map[str(row.id)] = str(clone.id)

        for row in session.query(VisualProp).filter(VisualProp.book_id == source_book_id).all():
            clone = clone_row(session, row, VisualProp, book_id=TEMP_BOOK_ID, book_title=f"CLONE {source_book_id}")
            prop_map[str(row.id)] = str(clone.id)

        for row in session.query(VisualReferenceAsset).filter(VisualReferenceAsset.book_id == source_book_id).all():
            asset_type = str(row.asset_type or "").strip()
            mapped_asset_id = {
                "scene": location_map,
                "character": makeup_map,
                "prop": prop_map,
            }.get(asset_type, {}).get(str(row.asset_id))
            if not mapped_asset_id:
                continue
            clone_row(
                session,
                row,
                VisualReferenceAsset,
                book_id=TEMP_BOOK_ID,
                asset_id=mapped_asset_id,
            )

        source_meta = safe_json_loads(source_shot.meta_info, {})
        source_structured = (
            source_meta.get("structured_shot")
            if isinstance(source_meta.get("structured_shot"), dict)
            else source_meta.get("prompt_compiler", {}).get("structured_shot")
            if isinstance(source_meta.get("prompt_compiler"), dict)
            else {}
        )
        remapped_source_structured = remap_structured_asset_ids(
            source_structured if isinstance(source_structured, dict) else {},
            location_map,
            makeup_map,
            prop_map,
        )
        degraded_structured = {
            "shot_id": str(source_shot.shot_id),
            "scene_name": source_shot.scene_name,
            "duration": source_shot.duration or 3,
            "camera_angle": source_shot.camera_angle or "MS",
            "camera_movement": source_shot.camera_movement or "static",
            "transition": source_shot.transition or "cut",
            "scene_asset_id": "",
            "character_asset_ids": [],
            "prop_asset_ids": [],
            "style_key": "default",
            "character_blocking": [],
            "action_beats": [],
        }
        baseline_structured = degraded_structured if baseline_mode == "degraded" else {
            **degraded_structured,
            **remapped_source_structured,
            "shot_id": str(source_shot.shot_id),
            "scene_name": source_shot.scene_name,
            "duration": source_shot.duration or 3,
            "camera_angle": source_shot.camera_angle or "MS",
            "camera_movement": source_shot.camera_movement or "static",
            "transition": source_shot.transition or "cut",
        }
        if baseline_mode == "degraded":
            baseline_static = str(source_shot.visual_prompt_static or "旧镜头短静态提示词。").strip()[:64] or "旧镜头短静态提示词。"
            baseline_motion = str(source_shot.visual_prompt_motion or "镜头推进。").strip()[:40] or "镜头推进。"
        else:
            baseline_static = str(source_shot.visual_prompt_static or "").strip() or "旧镜头缺少静态提示词。"
            baseline_motion = str(source_shot.visual_prompt_motion or "").strip() or "镜头保持连续推进。"
        degraded_meta = {
            "structured_shot": baseline_structured,
            "prompt_compile_context": {},
            "used_assets": [],
            "reference_images": [],
            "reference_asset_ids": [],
            "compiler_warnings": [
                "cloned real-project shot starts from a degraded short prompt"
                if baseline_mode == "degraded"
                else "cloned real-project shot preserves source prompt text for batch repair validation"
            ],
            "compiler_diagnostics": {
                "status": "warning",
                "checks": [
                    {"key": "static_prompt_quality", "passed": False},
                    {"key": "motion_prompt_quality", "passed": False},
                ],
            },
        }
        cloned_shot = StoryboardShot(
            book_id=TEMP_BOOK_ID,
            episode=source_shot.episode,
            scene_name=source_shot.scene_name,
            shot_id=source_shot.shot_id,
            dialogue=source_shot.dialogue or "",
            duration=source_shot.duration or 3,
            camera_angle=source_shot.camera_angle or "MS",
            camera_movement=source_shot.camera_movement or "static",
            transition=source_shot.transition or "cut",
            lighting=source_shot.lighting or "",
            sound_effects=source_shot.sound_effects or "[]",
            bgm_mood=source_shot.bgm_mood or "",
            start_state=source_shot.start_state or "",
            action_process=source_shot.action_process or "",
            end_state=source_shot.end_state or "",
            visual_prompt_static=baseline_static,
            visual_prompt_motion=baseline_motion,
            visual_prompt_final=source_shot.visual_prompt_final or "",
            asset_links=source_shot.asset_links or "{}",
            asset_status=source_shot.asset_status or "pending",
            meta_info=json.dumps(
                {
                    "structured_shot": baseline_structured,
                    "prompt_compiler": {
                        "latest_version": 1,
                        "compile_reason": f"clone-baseline-{baseline_mode}",
                        "negative_prompt": source_shot.visual_prompt_final or "",
                        **degraded_meta,
                    },
                },
                ensure_ascii=False,
            ),
            notes=f"Temporary clone of book {source_book_id} episode {source_episode} shot {source_shot_id}.",
            created_at=now,
            updated_at=now,
        )
        session.add(cloned_shot)
        session.flush()

        baseline = StoryboardPromptVersion(
            book_id=TEMP_BOOK_ID,
            episode=cloned_shot.episode,
            shot_id=cloned_shot.shot_id,
            version=1,
            compile_reason=f"clone-baseline-{baseline_mode}",
            prompt_static=baseline_static,
            prompt_motion=baseline_motion,
            negative_prompt=cloned_shot.visual_prompt_final or "",
            meta_info=json.dumps(degraded_meta, ensure_ascii=False),
        )
        session.add(baseline)
        session.commit()

        return {
            "source_book_id": source_book_id,
            "temp_book_id": TEMP_BOOK_ID,
            "episode": cloned_shot.episode,
            "shot_id": str(cloned_shot.shot_id),
            "baseline_version_id": baseline.id,
            "baseline_static": baseline_static,
            "baseline_motion": baseline_motion,
            "baseline_structured": baseline_structured,
        }


def build_mock_llm_payload(source_episode: int, source_shot_id: int) -> dict[str, Any]:
    with Session() as session:
        shot = (
            session.query(StoryboardShot)
            .filter(
                StoryboardShot.book_id == TEMP_BOOK_ID,
                StoryboardShot.episode == source_episode,
                StoryboardShot.shot_id == source_shot_id,
            )
            .first()
        )
        if not shot:
            raise RuntimeError("Cloned shot disappeared before compile.")

        meta_info = safe_json_loads(shot.meta_info, {})
        seed = {
            "shot_id": shot.shot_id,
            "scene_name": shot.scene_name,
            "makeup_prompts": _load_episode_makeup_prompt_stub(TEMP_BOOK_ID, shot.episode),
            "action_process": shot.action_process,
            "dialogue": shot.dialogue,
            "start_state": shot.start_state,
            "end_state": shot.end_state,
            "duration": shot.duration,
            "camera_angle": shot.camera_angle,
            "camera_movement": shot.camera_movement,
            "transition": shot.transition,
        }
        structured = _auto_bind_structured_shot_assets(
            TEMP_BOOK_ID,
            shot.episode,
            _derive_structured_shot_payload(meta_info, seed),
            seed,
        )
        asset_link_summary = _build_storyboard_reference_summary(_load_asset_links(shot.asset_links), str(shot.scene_name or "").strip())
        compile_context = _build_prompt_compile_context_v2(TEMP_BOOK_ID, shot, structured, {}, asset_link_summary)
        compile_context["reference_summary"] = _build_storyboard_reference_summary_from_bound_assets(
            compile_context.get("bound_assets", []),
            str(compile_context.get("scene_name") or shot.scene_name or "").strip(),
        )
        bound_assets = [item for item in compile_context.get("bound_assets", []) if isinstance(item, dict)]

    shot_ir = compile_rules(
        build_shot_ir_from_context(compile_context),
        compile_context.get("production_skill", {}),
    )
    adapter_output = adapt_ir_to_model(shot_ir, str(compile_context.get("target_model") or "jimeng"))
    used_assets = [
        {
            "asset_type": item.get("asset_type"),
            "asset_id": item.get("asset_id"),
            "asset_name": item.get("asset_name"),
            "reference_token": item.get("reference_token"),
            "reference_status": item.get("reference_status"),
        }
        for item in bound_assets
    ]
    return {
        "visual_prompt_static": str(adapter_output.get("static_prompt") or "").strip(),
        "visual_prompt_motion": str(adapter_output.get("motion_prompt") or "").strip(),
        "negative_prompt": str(adapter_output.get("negative_prompt") or "").strip(),
        "used_assets": used_assets,
        "warnings": ["deterministic clone repair uses Model Adapter baseline"],
    }


def validate_clone_repair_sample(source_book_id: int, source_episode: int, source_shot_id: int) -> None:
    init_db()
    client = TestClient(app)
    clone = clone_source_to_temp(source_book_id, source_episode, source_shot_id)
    log(
        f"Cloned source book #{clone['source_book_id']} shot {clone['episode']}-{clone['shot_id']} "
        f"to temp book #{clone['temp_book_id']}."
    )

    try:
        mock_payload = build_mock_llm_payload(source_episode, source_shot_id)
        with patch("core.llm.call_llm_json", return_value=mock_payload):
            compile_response = client.post(
                f"/api/books/{TEMP_BOOK_ID}/storyboard/{clone['episode']}/{clone['shot_id']}/compile-prompts",
                json={"compileReason": "clone-quality-repair", "force": True},
            )
        if compile_response.status_code != 200:
            raise RuntimeError(f"Compile failed: {compile_response.status_code} {compile_response.text}")

        compiled = compile_response.json()
        diagnostics_status = str(compiled.get("compiler_diagnostics", {}).get("status") or "")
        if diagnostics_status not in {"pass", "warning"}:
            raise RuntimeError(f"Unexpected compiler diagnostics: {json.dumps(compiled.get('compiler_diagnostics'), ensure_ascii=False)}")
        scene_binding = compiled.get("prompt_compile_context", {}).get("asset_bindings", {}).get("scene", {})
        if not str(scene_binding.get("asset_id") or "").strip():
            raise RuntimeError("Compile did not bind a scene asset on the cloned shot.")
        if len(str(compiled.get("prompt_static") or "")) < 80 or len(str(compiled.get("prompt_motion") or "")) < 50:
            raise RuntimeError("Compile did not repair prompt length enough for the audit baseline.")

        with Session() as session:
            shot = (
                session.query(StoryboardShot)
                .filter(
                    StoryboardShot.book_id == TEMP_BOOK_ID,
                    StoryboardShot.episode == clone["episode"],
                    StoryboardShot.shot_id == int(clone["shot_id"]),
                )
                .first()
            )
            meta = safe_json_loads(shot.meta_info, {})
            repaired_scene_asset_id = str(meta.get("structured_shot", {}).get("scene_asset_id") or "").strip()
            if not repaired_scene_asset_id:
                raise RuntimeError("Persisted structured_shot.scene_asset_id is still empty after compile.")

        rollback_response = client.post(
            f"/api/books/{TEMP_BOOK_ID}/storyboard/{clone['episode']}/{clone['shot_id']}/prompt-versions/{clone['baseline_version_id']}/rollback",
            json={"reason": "clone-quality-repair-rollback"},
        )
        if rollback_response.status_code != 200:
            raise RuntimeError(f"Rollback failed: {rollback_response.status_code} {rollback_response.text}")

        with Session() as session:
            shot = (
                session.query(StoryboardShot)
                .filter(
                    StoryboardShot.book_id == TEMP_BOOK_ID,
                    StoryboardShot.episode == clone["episode"],
                    StoryboardShot.shot_id == int(clone["shot_id"]),
                )
                .first()
            )
            meta = safe_json_loads(shot.meta_info, {})
            if shot.visual_prompt_static != clone["baseline_static"] or shot.visual_prompt_motion != clone["baseline_motion"]:
                raise RuntimeError("Rollback did not restore baseline prompt text.")
            if str(meta.get("structured_shot", {}).get("scene_asset_id") or "").strip():
                raise RuntimeError("Rollback did not restore the empty baseline scene_asset_id.")

        log(
            "Clone repair validation passed: compile repaired prompt/scene binding, "
            "rollback restored baseline prompt and structured_shot."
        )
    finally:
        cleanup_temp_book()
        log(f"Cleaned temp book #{TEMP_BOOK_ID}.")


def validate_clone_repair() -> None:
    samples = parse_source_samples()
    log(f"Configured {len(samples)} source sample(s): {', '.join(f'#{b}:{e}:{s}' for b, e, s in samples)}.")
    for source_book_id, source_episode, source_shot_id in samples:
        validate_clone_repair_sample(source_book_id, source_episode, source_shot_id)
    log(f"All {len(samples)} clone repair sample(s) passed.")


if __name__ == "__main__":
    validate_clone_repair()
