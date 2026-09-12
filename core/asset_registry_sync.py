"""Idempotent canonical asset registry sync from a qualified ScriptIR."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from models import VisualLocation, VisualMakeup, VisualProp


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


def sync_assets_from_script_ir(session: Any, script_ir: dict[str, Any], *, book_id: int, episode: int, source_fingerprint: str = "") -> dict[str, Any]:
    """Create/update canonical cards without generating references.

    Existing manually edited values are preserved; only registry provenance
    and missing canonical fields are filled from ScriptIR.
    """
    scenes = script_ir.get("scenes") if isinstance(script_ir.get("scenes"), list) else []
    characters = script_ir.get("characters") if isinstance(script_ir.get("characters"), list) else []
    created = {"scene": 0, "character": 0, "prop": 0}
    updated = {"scene": 0, "character": 0, "prop": 0}
    scene_cards: list[dict[str, Any]] = []
    for scene_index, raw_scene in enumerate(scenes, start=1):
        if not isinstance(raw_scene, dict):
            continue
        name = str(raw_scene.get("location_name") or raw_scene.get("name") or f"未命名场景{scene_index}").strip()
        card = session.query(VisualLocation).filter_by(book_id=book_id, name=name).first()
        if card is None:
            card = VisualLocation(book_id=book_id, name=name, asset_status="draft")
            session.add(card); created["scene"] += 1
        else:
            updated["scene"] += 1
        episodes = _json(card.episodes, [])
        if not isinstance(episodes, list):
            episodes = []
        card.episodes = json.dumps(_append_unique(episodes, int(episode)), ensure_ascii=False)
        canonical = _json(card.canonical_facts, {})
        canonical = canonical if isinstance(canonical, dict) else {}
        canonical.setdefault("scene_id", str(raw_scene.get("scene_id") or ""))
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
            else:
                prop_name = str(mention or "").strip()
            if not prop_name:
                continue
            prop = session.query(VisualProp).filter_by(book_id=book_id, name=prop_name).first()
            if prop is None:
                prop = VisualProp(book_id=book_id, name=prop_name, asset_status="draft")
                session.add(prop); created["prop"] += 1
            else:
                updated["prop"] += 1
            prop_episodes = _json(prop.episodes, [])
            prop.episodes = json.dumps(_append_unique(prop_episodes if isinstance(prop_episodes, list) else [], int(episode)), ensure_ascii=False)
            prop_canonical = _json(prop.canonical_facts, {})
            prop_canonical = prop_canonical if isinstance(prop_canonical, dict) else {}
            prop_canonical.setdefault("name", prop_name); prop_canonical["registry_source"] = "script_ir"; prop_canonical["source_fingerprint"] = str(source_fingerprint or "")
            prop.canonical_facts = json.dumps(prop_canonical, ensure_ascii=False); prop.updated_at = datetime.now()

    character_cards: list[dict[str, Any]] = []
    for raw_character in characters:
        if not isinstance(raw_character, dict):
            continue
        name = str(raw_character.get("name") or raw_character.get("character_name") or "").strip()
        if not name:
            continue
        card = session.query(VisualMakeup).filter_by(book_id=book_id, episode=episode, character_name=name).first()
        if card is None:
            card = VisualMakeup(book_id=book_id, episode=episode, character_name=name, asset_status="draft")
            session.add(card); created["character"] += 1
        else:
            updated["character"] += 1
        meta = _json(card.meta_info, {}); meta = meta if isinstance(meta, dict) else {}
        identity = meta.get("script_ir_identity") if isinstance(meta.get("script_ir_identity"), dict) else {}
        for key in ("character_id", "gender", "age", "role"):
            if raw_character.get(key) not in (None, ""):
                identity.setdefault(key, raw_character[key])
        identity["registry_source"] = "script_ir"; identity["source_fingerprint"] = str(source_fingerprint or "")
        meta["script_ir_identity"] = identity; card.meta_info = json.dumps(meta, ensure_ascii=False); card.updated_at = datetime.now()
        character_cards.append({"id": card.id, "name": name, "episode": episode, "asset_status": card.asset_status})

    return {"created": created, "updated": updated, "scenes": scene_cards, "characters": character_cards, "props_created": created["prop"], "source_fingerprint": str(source_fingerprint or ""), "mutated": any(created.values()) or any(updated.values())}

