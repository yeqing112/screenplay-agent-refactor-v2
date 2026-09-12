"""Validation and fingerprinting for evidence-constrained LLM decision packets."""
from __future__ import annotations
import hashlib
import json
from typing import Any

EVIDENCE_TIERS = {"locked_fact", "approved_fact", "source_text", "derived_fact", "model_observation", "unknown"}
DOMAINS = {"script", "storyboard", "asset", "prompt", "continuity", "director_treatment"}

def normalize_decision_packet(packet: dict[str, Any]) -> dict[str, Any]:
    domain = str(packet.get("domain") or "").strip().lower()
    if domain not in DOMAINS: raise ValueError("unsupported decision packet domain")
    evidence = packet.get("evidence") if isinstance(packet.get("evidence"), list) else []
    normalized = []
    for item in evidence:
        if not isinstance(item, dict): continue
        tier = str(item.get("tier") or "unknown").strip()
        if tier not in EVIDENCE_TIERS: raise ValueError("unsupported evidence tier")
        normalized.append({"id": str(item.get("id") or "").strip(), "tier": tier, "summary": str(item.get("summary") or "").strip(), "version": str(item.get("version") or "").strip()})
    return {"domain": domain, "scope": packet.get("scope") if isinstance(packet.get("scope"), dict) else {}, "evidence": normalized, "unknowns": [str(x) for x in packet.get("unknowns", []) if str(x).strip()], "conflicts": [str(x) for x in packet.get("conflicts", []) if str(x).strip()], "allowed_operations": [str(x) for x in packet.get("allowed_operations", []) if str(x).strip()]}

def decision_packet_fingerprint(packet: dict[str, Any]) -> str:
    normalized = normalize_decision_packet(packet)
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
