"""Minimal deterministic semantic event projection."""
from __future__ import annotations
import hashlib, json, re
from typing import Any

def _d(v): return v if isinstance(v, dict) else {}
def _l(v): return v if isinstance(v, list) else []
def _t(v): return str(v or "").strip()
def _canon(v): return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def fingerprint(v): return hashlib.sha256(_canon(v).encode()).hexdigest()
def _slug(text):
    text = re.sub(r"[^A-Za-z0-9]+", "_", _t(text)).strip("_").upper()
    return text[:48] or "EVENT"

def project_semantic_events(scene: dict[str, Any]) -> dict[str, Any]:
    events = []
    for index, beat in enumerate(_l(scene.get("beats")), 1):
        beat_id = _t(_d(beat).get("beat_id")) or str(index); ref = beat_id if ":" in beat_id else f"beat:{beat_id[1:] if beat_id.upper().startswith('B') else beat_id}"
        actions = _l(beat.get("actions")) if isinstance(beat, dict) else []
        if not actions: actions = [_d(beat).get("action") or _d(beat).get("dialogue_action") or _d(beat).get("summary") or "beat"]
        for action_index, action in enumerate(actions, 1):
            text = _t(action.get("description") if isinstance(action, dict) else action) or "beat"
            events.append({"event_key": f"{_slug(ref.replace(':', '_'))}_{_slug(text)}_{action_index:02d}", "beat_ref": ref, "source": text, "source_type": "BEAT"})
    projection = {"schema_version": "semantic_event_projection_v1", "scene_id": _t(scene.get("scene_id")), "events": events}
    projection["fingerprint"] = fingerprint(projection)
    return projection
