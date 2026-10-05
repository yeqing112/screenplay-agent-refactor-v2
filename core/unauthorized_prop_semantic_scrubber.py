"""Structured removal of unauthorized object relationships from video beats.

The Director decision is source truth and is never modified in place.  This
module projects a provider-facing semantic beat from that truth while keeping
an audit of every relationship that was removed.  It deliberately operates on
fields (hand action, prop action, ending state) instead of doing global text
replacement, which prevents fragments such as ``release the strap ... without
prop contact`` from being emitted as a new, contradictory action.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import copy
import re
from typing import Any, Iterable, Mapping


OBJECT_TOKENS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("HANDBAG", ("shoulder bag", "crossbody bag", "handbag", "bag strap", "strap", "bag", "手提包", "肩包", "包带")),
    ("APPLE", ("apple", "苹果")),
    ("UMBRELLA", ("umbrella", "伞")),
)
DEPENDENT_VERBS: tuple[str, ...] = (
    "grip", "gripping", "gripped", "hold", "holding", "held", "release", "releases", "released",
    "touch", "touching", "touched", "carry", "carrying", "carried", "adjust", "adjusting", "adjusted",
    "pull", "pulling", "pulled", "push", "pushing", "pushed", "lift", "lifting", "lifted",
    "lower", "lowering", "lowered", "rest on", "rests on", "resting on", "fingers remain on",
    "remain on", "stays on", "stay on", "捏", "握", "拿", "提", "抓", "松开", "触碰", "调整", "放在",
)


@dataclass(frozen=True)
class PropSemanticScrubAudit:
    status: str
    allowed_prop_ids: tuple[str, ...]
    input_beat: Mapping[str, Any]
    output_beat: Mapping[str, Any]
    transformations: tuple[Mapping[str, Any], ...] = ()
    orphan_interactions: tuple[str, ...] = ()
    unauthorized_tokens: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "allowed_prop_ids": list(self.allowed_prop_ids),
            "input_beat": copy.deepcopy(dict(self.input_beat)),
            "output_beat": copy.deepcopy(dict(self.output_beat)),
            "transformations": [dict(x) for x in self.transformations],
            "orphan_interactions": list(self.orphan_interactions),
            "unauthorized_tokens": list(self.unauthorized_tokens),
        }


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _allowed_object_ids(allowed_prop_ids: Iterable[str] | None) -> set[str]:
    return {_norm(x).upper() for x in (allowed_prop_ids or ()) if str(x).strip()}


def _find_objects(text: str) -> list[tuple[str, str]]:
    lower = text.lower()
    found: list[tuple[str, str]] = []
    for object_id, tokens in OBJECT_TOKENS:
        for token in tokens:
            if token.lower() in lower:
                found.append((object_id, token))
    return found


def _has_dependent_verb(text: str) -> bool:
    lower = text.lower()
    return any(token.lower() in lower for token in DEPENDENT_VERBS)


def _person_pronouns(actor: str) -> tuple[str, str]:
    actor_lower = actor.lower()
    if "林晚" in actor or actor_lower in {"lin wan", "lin_wan"}:
        return "her", "she"
    if "陆叔" in actor or actor_lower in {"lu shu", "lu_shu"}:
        return "his", "he"
    return "their", "they"


def _project_hand_action(text: str, *, actor: str, start: float, end: float) -> str:
    possessive, _ = _person_pronouns(actor)
    if "林晚" in actor or actor.lower() in {"lin wan", "lin_wan"}:
        if start <= 0.01 and end <= 2.5:
            return "left hand starts held close to her side, then the fingers gradually relax, ending with the hand naturally loose beside her body"
        if start >= 7.0 and end <= 10.0:
            return "left hand makes a small unconscious adjustment near her side, then settles naturally beside her body"
    # Keep a human micro movement while removing the object relationship.
    if any(token in text.lower() for token in ("release", "releases", "released", "松开")):
        return f"the hand opens gradually and settles naturally beside {possessive} body"
    if any(token in text.lower() for token in ("grip", "hold", "holding", "握", "抓", "捏")):
        return f"the hand starts gently tense, then relaxes and hangs naturally beside {possessive} body"
    return f"the hand makes a small natural adjustment and settles beside {possessive} body"


def _project_value(value: Any, *, field_name: str, actor: str, start: float, end: float, allowed: set[str], path: str, transformations: list[dict[str, Any]], orphan: list[str], unauthorized: list[str]) -> Any:
    if isinstance(value, list):
        return [_project_value(item, field_name=field_name, actor=actor, start=start, end=end, allowed=allowed, path=f"{path}[{index}]", transformations=transformations, orphan=orphan, unauthorized=unauthorized) for index, item in enumerate(value)]
    if isinstance(value, dict):
        local_actor = str(value.get("actor") or actor)
        local_start = float(value.get("start_time") or start)
        local_end = float(value.get("end_time") or end)
        return {key: _project_value(item, field_name=str(key), actor=local_actor, start=local_start, end=local_end, allowed=allowed, path=f"{path}.{key}", transformations=transformations, orphan=orphan, unauthorized=unauthorized) for key, item in value.items()}
    if not isinstance(value, str):
        return value
    objects = _find_objects(value)
    illegal = [(object_id, token) for object_id, token in objects if object_id not in allowed]
    if not illegal:
        return value
    unauthorized.extend(token for _, token in illegal)
    relationship = _has_dependent_verb(value)
    if relationship and field_name in {"hand_action", "ending_state", "prop_action", "left_hand", "right_hand", "prop_contact", "pose"}:
        if field_name in {"hand_action", "left_hand", "right_hand", "prop_contact", "pose"}:
            projected = _project_hand_action(value, actor=actor, start=start, end=end)
        else:
            projected = "No prop interaction; hands remain natural and free of story props."
        transformations.append({"path": path, "reason": "UNAUTHORIZED_PROP_RELATIONSHIP", "tokens": [token for _, token in illegal], "input": value, "output": projected})
        if not any(object_id in allowed for object_id, _ in objects):
            return projected
    # An isolated object mention is also removed from provider-facing positive
    # semantics.  This branch is intentionally conservative and never invents
    # a replacement object.
    if field_name in {"prop_action", "ending_state", "left_hand", "right_hand", "prop_contact", "pose"}:
        projected = "No prop interaction; hands remain natural and free of story props."
        transformations.append({"path": path, "reason": "UNAUTHORIZED_PROP_MENTION", "tokens": [token for _, token in illegal], "input": value, "output": projected})
        return projected
    if relationship:
        orphan.append(path)
    return value


def scrub_semantic_beat(beat: Mapping[str, Any], *, allowed_prop_ids: Iterable[str] | None = None) -> tuple[dict[str, Any], PropSemanticScrubAudit]:
    """Project one beat and return a machine-readable audit."""
    source = copy.deepcopy(dict(beat))
    allowed = _allowed_object_ids(allowed_prop_ids)
    transformations: list[dict[str, Any]] = []
    orphan: list[str] = []
    unauthorized: list[str] = []
    output = _project_value(source, field_name="beat", actor=str(source.get("actor") or ""), start=float(source.get("start_time") or 0), end=float(source.get("end_time") or 0), allowed=allowed, path="beat", transformations=transformations, orphan=orphan, unauthorized=unauthorized)
    status = "PASS" if not orphan else "FAIL"
    audit = PropSemanticScrubAudit(status, tuple(sorted(allowed)), source, output, tuple(transformations), tuple(orphan), tuple(dict.fromkeys(unauthorized)))
    return output, audit


def scrub_semantic_beats(beats: Iterable[Mapping[str, Any]], *, allowed_prop_ids: Iterable[str] | None = None) -> tuple[list[dict[str, Any]], list[PropSemanticScrubAudit]]:
    projected: list[dict[str, Any]] = []
    audits: list[PropSemanticScrubAudit] = []
    for beat in beats:
        if not isinstance(beat, Mapping):
            continue
        item, audit = scrub_semantic_beat(beat, allowed_prop_ids=allowed_prop_ids)
        projected.append(item)
        audits.append(audit)
    return projected, audits


__all__ = ["PropSemanticScrubAudit", "scrub_semantic_beat", "scrub_semantic_beats", "OBJECT_TOKENS", "DEPENDENT_VERBS"]
