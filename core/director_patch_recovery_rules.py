"""Evidence-backed Director patch recovery rule registry.

Rules are data, not scattered resolver branches.  Registration requires a
concrete trace example and positive evidence count; callers must explicitly
apply a named rule after the observability analysis has been reviewed.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from typing import Any, Callable


class RecoveryRuleError(ValueError):
    pass


@dataclass(frozen=True)
class RecoveryRule:
    rule_id: str
    classification: str
    evidence_count: int
    example_raw_path: str
    canonical_output: str
    why_safe: str
    test_case: str
    enabled: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


_RULES: dict[str, RecoveryRule] = {}
_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any] | None]] = {}


def register_recovery_rule(
    rule: RecoveryRule | dict[str, Any],
    *,
    handler: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
) -> RecoveryRule:
    """Register one reviewed rule; ungrounded rules are rejected."""

    if isinstance(rule, dict):
        try:
            rule = RecoveryRule(**rule)
        except TypeError as exc:
            raise RecoveryRuleError(f"invalid recovery rule fields: {exc}") from exc
    if not isinstance(rule, RecoveryRule) or not rule.rule_id.strip():
        raise RecoveryRuleError("rule_id is required")
    if rule.evidence_count <= 0:
        raise RecoveryRuleError("recovery rule requires positive evidence_count")
    required = {
        "classification": rule.classification,
        "example_raw_path": rule.example_raw_path,
        "canonical_output": rule.canonical_output,
        "why_safe": rule.why_safe,
        "test_case": rule.test_case,
    }
    if any(not str(value).strip() for value in required.values()):
        raise RecoveryRuleError(f"recovery rule {rule.rule_id} is missing evidence fields")
    if rule.rule_id in _RULES:
        raise RecoveryRuleError(f"recovery rule already registered: {rule.rule_id}")
    _RULES[rule.rule_id] = copy.deepcopy(rule)
    if handler is not None:
        _HANDLERS[rule.rule_id] = handler
    return copy.deepcopy(rule)


def clear_recovery_rules() -> None:
    """Test helper; production callers should only add reviewed rules."""

    _RULES.clear()
    _HANDLERS.clear()


def list_recovery_rules() -> list[dict[str, Any]]:
    return [copy.deepcopy(_RULES[key].as_dict()) for key in sorted(_RULES)]


def get_recovery_rule(rule_id: str) -> RecoveryRule | None:
    rule = _RULES.get(str(rule_id or ""))
    return copy.deepcopy(rule) if rule else None


def apply_recovery_rule(rule_id: str, trace: dict[str, Any]) -> dict[str, Any] | None:
    """Apply only an enabled, evidence-backed handler to a trace."""

    rule = _RULES.get(str(rule_id or ""))
    if rule is None or not rule.enabled:
        raise RecoveryRuleError(f"recovery rule is not enabled: {rule_id}")
    handler = _HANDLERS.get(rule.rule_id)
    if handler is None:
        raise RecoveryRuleError(f"recovery rule has no handler: {rule.rule_id}")
    result = handler(copy.deepcopy(trace))
    if result is None:
        return None
    if not isinstance(result, dict):
        raise RecoveryRuleError("recovery handler must return an object or None")
    result["recovery_rule_id"] = rule.rule_id
    result["recovery_rule_evidence_count"] = rule.evidence_count
    return result


__all__ = [
    "RecoveryRule",
    "RecoveryRuleError",
    "register_recovery_rule",
    "clear_recovery_rules",
    "list_recovery_rules",
    "get_recovery_rule",
    "apply_recovery_rule",
]
