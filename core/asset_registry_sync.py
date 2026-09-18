"""Idempotent canonical asset registry sync from a qualified ScriptIR."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from models import VisualLocation, VisualMakeup, VisualProp
from core.visual_asset_authority import build_asset_key


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if parsed is not None else fallback
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _append_unique(values: list[Any], value: Any) -> list[Any]:
    if value not in values:
        values.append(value)
    return values


def sync_assets_from_script_ir(session: Any, script_ir: dict[str, Any], *, book_id: int, episode: int, source_fingerprint: str = "", workflow_profile: str = "creative_draft") -> dict[str, Any]:
    """Create/update canonical cards without generating references.

    Existing manually edited values are preserved; only registry provenance
    and missing canonical fields are filled from ScriptIR.
    """
    production = str(workflow_profile or "creative_draft").strip().lower() == "production"
    scenes = script_ir.get("scenes") if isinstance(script_ir.get("scenes"), list) else []
    characters = script_ir.get("characters") if isinstance(script_ir.get("characters"), list) else []
    created = {"scene": 0, "character": 0, "prop": 0}
    updated = {"scene": 0, "character": 0, "prop": 0}
    scene_cards: list[dict[str, Any]] = []
    for scene_index, raw_scene in enumerate(scenes, start=1):
        if not isinstance(raw_scene, dict):
            continue
        name = str(raw_scene.get("location_name") or raw_scene.get("name") or "").strip()
        scene_id = str(raw_scene.get("scene_id") or raw_scene.get("location_id") or "").strip()
        if production and not scene_id:
            raise ValueError("PRODUCTION_SCENE_ID_REQUIRED")
        if not name and production:
            raise ValueError("PRODUCTION_SCENE_NAME_REQUIRED")
        name = name or f"未命名场景{scene_index}"
        asset_key = build_asset_key(book_id=book_id, asset_type="scene", canonical_id=scene_id) if scene_id else ""
        card = session.query(VisualLocation).filter_by(book_id=book_id, asset_key=asset_key).first() if asset_key else session.query(VisualLocation).filter_by(book_id=book_id, name=name).first()
        if card is None:
            card = VisualLocation(book_id=book_id, asset_key=asset_key, scene_id=scene_id, name=name, asset_status="IDENTITY_REGISTERED" if production else "draft")
            session.add(card); created["scene"] += 1
        else:
            updated["scene"] += 1
        if asset_key:
            card.asset_key = asset_key
            card.scene_id = scene_id
        episodes = _json(card.episodes, [])
        if not isinstance(episodes, list):
            episodes = []
        card.episodes = json.dumps(_append_unique(episodes, int(episode)), ensure_ascii=False)
        canonical = _json(card.canonical_facts, {})
        canonical = canonical if isinstance(canonical, dict) else {}
        canonical.setdefault("scene_id", scene_id)
        canonical.setdefault("asset_key", asset_key)
        canonical.setdefault("location_name", name)
        if str(raw_scene.get("time_of_day") or "").strip():
            canonical.setdefault("time_of_day", str(raw_scene["time_of_day"]).strip())
        if str(raw_scene.get("weather") or "").strip():
            canonical.setdefault("weather", str(raw_scene["weather"]).strip())
        canonical["registry_source"] = "script_ir"
        canonical["source_fingerprint"] = str(source_fingerprint or "")
        card.canonical_facts = json.dumps(canonical, ensure_ascii=False)
        card.updated_at = datetime.now()
        scene_cards.append({"id": card.id, "name": name, "asset_status": card.asset_status})

        mentions = raw_scene.get("asset_mentions") if isinstance(raw_scene.get("asset_mentions"), list) else []
        for mention in mentions:
            if isinstance(mention, dict):
                prop_name = str(mention.get("name") or mention.get("prop_name") or "").strip()
                prop_id = str(mention.get("prop_id") or mention.get("id") or "").strip()
            else:
                prop_name = str(mention or "").strip()
                prop_id = ""
            if not prop_name:
                continue
            if production and not prop_id:
                raise ValueError("PRODUCTION_PROP_ID_REQUIRED")
            prop_key = build_asset_key(book_id=book_id, asset_type="prop", canonical_id=prop_id) if prop_id else ""
            prop = session.query(VisualProp).filter_by(book_id=book_id, asset_key=prop_key).first() if prop_key else session.query(VisualProp).filter_by(book_id=book_id, name=prop_name).first()
            if prop is None:
                prop = VisualProp(book_id=book_id, asset_key=prop_key, name=prop_name, asset_status="IDENTITY_REGISTERED" if production else "draft")
                session.add(prop); created["prop"] += 1
            else:
                updated["prop"] += 1
            if prop_key:
                prop.asset_key = prop_key
            prop_episodes = _json(prop.episodes, [])
            prop.episodes = json.dumps(_append_unique(prop_episodes if isinstance(prop_episodes, list) else [], int(episode)), ensure_ascii=False)
            prop_canonical = _json(prop.canonical_facts, {})
            prop_canonical = prop_canonical if isinstance(prop_canonical, dict) else {}
            prop_canonical.setdefault("name", prop_name); prop_canonical.setdefault("prop_id", prop_id); prop_canonical.setdefault("asset_key", prop_key); prop_canonical["registry_source"] = "script_ir"; prop_canonical["source_fingerprint"] = str(source_fingerprint or "")
            prop.canonical_facts = json.dumps(prop_canonical, ensure_ascii=False); prop.updated_at = datetime.now()

    character_cards: list[dict[str, Any]] = []
    for raw_character in characters:
        if not isinstance(raw_character, dict):
            continue
        name = str(raw_character.get("name") or raw_character.get("character_name") or "").strip()
        character_id = str(raw_character.get("character_id") or raw_character.get("id") or "").strip()
        if production and not character_id:
            raise ValueError("PRODUCTION_CHARACTER_ID_REQUIRED")
        if not name:
            continue
        character_key = build_asset_key(book_id=book_id, asset_type="character", canonical_id=character_id) if character_id else ""
        card = session.query(VisualMakeup).filter_by(book_id=book_id, episode=episode, asset_key=character_key).first() if character_key else session.query(VisualMakeup).filter_by(book_id=book_id, episode=episode, character_name=name).first()
        if card is None:
            card = VisualMakeup(book_id=book_id, episode=episode, asset_key=character_key, character_name=name, asset_status="IDENTITY_REGISTERED" if production else "draft")
            session.add(card); created["character"] += 1
        else:
            updated["character"] += 1
        meta = _json(card.meta_info, {}); meta = meta if isinstance(meta, dict) else {}
        identity = meta.get("script_ir_identity") if isinstance(meta.get("script_ir_identity"), dict) else {}
        identity.setdefault("character_id", character_id); identity.setdefault("asset_key", character_key)
        for key in ("character_id", "gender", "age", "role"):
            if raw_character.get(key) not in (None, ""):
                identity.setdefault(key, raw_character[key])
        identity["registry_source"] = "script_ir"; identity["source_fingerprint"] = str(source_fingerprint or "")
        meta["script_ir_identity"] = identity; card.meta_info = json.dumps(meta, ensure_ascii=False); card.updated_at = datetime.now()
        character_cards.append({"id": card.id, "name": name, "episode": episode, "asset_status": card.asset_status})

    return {"created": created, "updated": updated, "scenes": scene_cards, "characters": character_cards, "props_created": created["prop"], "source_fingerprint": str(source_fingerprint or ""), "mutated": any(created.values()) or any(updated.values())}

