"""Deterministic provenance policy for Director proposals and confirmation."""
from __future__ import annotations

from typing import Any

PROPOSAL_ORIGINS = frozenset({"GENERATED_DRAFT", "HUMAN_INPUT", "PROVIDER_PROPOSAL", "IMPORTED_REVIEWED_PROPOSAL"})
CANONICAL_ORIGINS = frozenset({"HUMAN_AUTHORED", "PROVIDER_PROPOSAL_CONFIRMED", "IMPORTED_REVIEWED_CONFIRMED"})


def _text(value: Any) -> str:
    return str(value or "").strip()


def proposal_provenance(origin: str, *, provider: dict[str, Any] | None = None, human_input: bool = False) -> dict[str, Any]:
    origin = _text(origin).upper()
    if origin not in PROPOSAL_ORIGINS:
        raise ValueError("DIRECTOR_PROVENANCE_INVALID: unsupported proposal_origin")
    provider = dict(provider or {})
    called = bool(provider.get("called", False))
    calls = int(provider.get("calls", 0) or 0)
    if called != (calls > 0):
        raise ValueError("DIRECTOR_PROVENANCE_INVALID: provider.called must match provider.calls")
    if origin == "PROVIDER_PROPOSAL" and not called:
        raise ValueError("DIRECTOR_PROVENANCE_INVALID: PROVIDER_PROPOSAL requires a provider call")
    if origin != "PROVIDER_PROPOSAL" and called:
        raise ValueError("DIRECTOR_PROVENANCE_INVALID: non-provider proposal cannot claim provider call")
    return {"proposal_origin": origin, "provider": {"called": called, "calls": calls, "profile_id": provider.get("profile_id"), "model": provider.get("model"), "request_fingerprint": provider.get("request_fingerprint"), "response_fingerprint": provider.get("response_fingerprint")}, "authoring": {"human_input": bool(human_input)}}


def resolve_canonical_origin(provenance: dict[str, Any], confirmation: dict[str, Any]) -> str:
    if not isinstance(provenance, dict) or not isinstance(confirmation, dict) or confirmation.get("confirmed") is not True or _text(confirmation.get("boundary")) != "production_confirm_service":
        raise ValueError("DIRECTOR_PROVENANCE_INVALID: confirmation event is not a production confirmation")
    origin = _text(provenance.get("proposal_origin")).upper()
    if origin in {"GENERATED_DRAFT", "HUMAN_INPUT"}:
        return "HUMAN_AUTHORED"
    if origin == "PROVIDER_PROPOSAL":
        return "PROVIDER_PROPOSAL_CONFIRMED"
    if origin == "IMPORTED_REVIEWED_PROPOSAL":
        return "IMPORTED_REVIEWED_CONFIRMED"
    raise ValueError("DIRECTOR_PROVENANCE_INVALID: no canonical origin transition")


def confirmation_event(provenance: dict[str, Any], *, confirmed_at: str) -> dict[str, Any]:
    canonical = resolve_canonical_origin(provenance, {"confirmed": True, "boundary": "production_confirm_service"})
    return {"confirmed": True, "boundary": "production_confirm_service", "confirmation_type": "HUMAN_CONFIRMATION", "confirmed_at": confirmed_at, "source_proposal_origin": provenance["proposal_origin"], "canonical_origin": canonical, "confirmation_actor": "USER_CONFIRMATION_BOUNDARY"}


def project_legacy_flags(provenance: dict[str, Any]) -> dict[str, Any]:
    provider = provenance.get("provider") if isinstance(provenance.get("provider"), dict) else {}
    called = bool(provider.get("called")) and int(provider.get("calls", 0) or 0) > 0
    return {"llm_called": called, "llm_generated": called and _text(provenance.get("proposal_origin")).upper() == "PROVIDER_PROPOSAL"}


__all__ = ["PROPOSAL_ORIGINS", "CANONICAL_ORIGINS", "proposal_provenance", "resolve_canonical_origin", "confirmation_event", "project_legacy_flags"]
