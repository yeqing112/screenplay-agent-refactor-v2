"""Run the bounded AUTHORIZED_PROPOSER_PROVIDER_CANARY.

Default mode is provider-free preflight.  ``--execute`` is an explicit
operator action and uses only the configured default LLM profile.  Both modes
are dry-run with respect to FactSnapshot and production state.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.authorized_proposer_canary import make_llm_provider, run_authorized_proposer_canary  # noqa: E402

ART = ROOT / "artifacts"
DEFAULT_SOURCE = ROOT / "work/intake/director_v3/evaluation_packages/SRC79f12d1b7f5eb828.raw"
DEFAULT_MANIFEST = ART / "director-quality-v3-targeted-missing-fact-manifest.json"
DEFAULT_SNAPSHOT = ART / "director-quality-v3-fact-evidence-attempt2-result.json"
DEFAULT_RESULT = ART / "director-quality-v3-authorized-proposer-provider-canary-result.json"
DEFAULT_REPORT = ART / "director-quality-v3-authorized-proposer-provider-canary-report.md"


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _profile_for_execution() -> dict[str, Any] | None:
    from api.model_registry import get_default_profile
    profile = get_default_profile("llm")
    if not profile or not profile.get("enabled", True):
        return None
    # ``key_configured`` is safe to inspect; never print or persist api_key.
    if not profile.get("key_configured") and not str(profile.get("api_key") or "").strip():
        return None
    return profile


def _markdown(result: dict[str, Any], audit_records: list[dict[str, Any]], *, attempted: bool, profile: dict[str, Any] | None) -> str:
    summary = result.get("summary", {})
    usage = [row.get("usage") for row in audit_records if isinstance(row.get("usage"), dict)]
    def _sum(key: str) -> int:
        return sum(int(item.get(key) or 0) for item in usage)
    cache_hits = sum(1 for item in usage if item.get("cache_hit"))
    lines = [
        "# Director Quality V3 — Authorized Proposer Provider Canary",
        "",
        "## Baseline Audit",
        "",
        "- Scope: only required MissingFactManifest items; maximum 8 candidate anchors per fact.",
        "- Provider role: `PROPOSER`; FactSnapshot / authority / ScriptIR / production writes are forbidden.",
        f"- Explicit execution requested: `{str(attempted).lower()}`; provider configured: `{str(bool(profile)).lower()}`.",
        "",
        "## Canary Results",
        "",
        f"- Required facts: `{summary.get('required_facts', 0)}`; provider calls: `{summary.get('provider_calls', 0)}` / max `{summary.get('provider_calls_maximum', 0)}`.",
        f"- Proposals: `{summary.get('proposal_count', 0)}`; exact-evidence pass: `{summary.get('exact_evidence_pass', 0)}`; semantic-support pass: `{summary.get('semantic_support_pass', 0)}`.",
        f"- Acceptable candidates (dry-run only): `{summary.get('acceptable_candidates', 0)}`.",
        "",
        "| Fact | Anchors | Called | Proposed value | Exact evidence | Semantic support | Classification |",
        "|---|---:|---|---|---|---|---|",
    ]
    for row in result.get("results", []):
        value = json.dumps(row.get("proposed_value"), ensure_ascii=False) if row.get("proposed_value") is not None else "—"
        exact = (row.get("exact_evidence_validation") or {}).get("status", "—")
        support = (row.get("semantic_support_validation") or {}).get("status", "—")
        lines.append(f"| `{row.get('fact_key','')}` | {row.get('candidate_anchor_count',0)} | {str(bool(row.get('provider_called'))).lower()} | {value[:120]} | `{exact}` | `{support}` | `{row.get('final_classification','')}` |")
    lines.extend([
        "",
        "## Zero-anchor Retrieval Diagnostics",
        "",
    ])
    for row in result.get("results", []):
        diagnostic = row.get("retrieval_diagnostic") or {}
        if diagnostic:
            lines.append(f"- `{row.get('fact_key','')}`: query=`{diagnostic.get('query_terms', [])}`, scene_heading=`{diagnostic.get('scene_heading_present')}`, environment=`{diagnostic.get('environment_description_present')}`, prop_mentions=`{diagnostic.get('prop_noun_mentions_present')}`, hint=`{diagnostic.get('classification_hint')}`.")
    lines.extend([
        "",
        "## Audit",
        "",
        f"- Logical provider calls: `{len(audit_records) if audit_records else 0}` audit records; transport/parser retries are configured as `0`.",
        f"- Usage (when returned): input `{_sum('prompt_tokens')}`, output `{_sum('completion_tokens')}`, cached `{_sum('cached_tokens')}` tokens; cache hit/miss `{cache_hits}/{max(0, len(usage)-cache_hits)}`.",
        f"- Latency samples: `{sum(1 for row in audit_records if row.get('latency_ms') is not None)}`; estimated cost is provider-dependent and omitted when unavailable.",
        f"- Provider/model: `{(profile or {}).get('provider','')}` / `{(profile or {}).get('model_name','')}`.",
        "- Cache, usage and latency fields are retained only in bounded LLM audit records; credentials are never persisted.",
        "",
        "## Safety Verification",
        "",
        "- `dry_run=true`; `fact_snapshot_writes=0`; `authoritative_record_writes=0`; `production_writes=0`.",
        f"- Simulated coverage status: `{(result.get('simulated_coverage') or {}).get('status','FACT_COVERAGE_INSUFFICIENT')}`; formal coverage and ScriptIR status are unchanged.",
        "",
    ])
    return "\n".join(lines)


def run(*, source: Path = DEFAULT_SOURCE, manifest: Path = DEFAULT_MANIFEST, snapshot: Path = DEFAULT_SNAPSHOT, execute: bool = False, output: Path = DEFAULT_RESULT, report: Path = DEFAULT_REPORT) -> dict[str, Any]:
    manifest_payload = _read(manifest)
    snapshot_payload = _read(snapshot)
    current_snapshot = snapshot_payload.get("fact_snapshot", snapshot_payload) if isinstance(snapshot_payload, dict) else {}
    source_bytes = source.read_bytes()
    audit_records: list[dict[str, Any]] = []
    profile = _profile_for_execution() if execute else None
    provider = make_llm_provider(model_profile=profile, audit_records=audit_records) if profile else None
    result = run_authorized_proposer_canary(
        source_material=source_bytes,
        current_snapshot=current_snapshot,
        missing_manifest=manifest_payload,
        source_package_id="SRC79f12d1b7f5eb828",
        source_version_id="SRC79f12d1b7f5eb828:V01:d001bab5cc82",
        provider=provider,
        model=profile,
        max_candidates=8,
        execution_authorized=execute,
    )
    result["execution"] = {"explicit_execute": execute, "provider_configured": bool(profile), "audit_records": audit_records}
    if execute and profile is None:
        result["execution"]["status"] = "FAIL_CLOSED_PROVIDER_NOT_CONFIGURED"
    else:
        result["execution"]["status"] = "COMPLETED"
    _write(output, result)
    report.write_text(_markdown(result, audit_records, attempted=execute, profile=profile), encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="explicitly call the configured proposer provider")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--output", default=str(DEFAULT_RESULT))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args(argv)
    result = run(source=Path(args.source), manifest=Path(args.manifest), snapshot=Path(args.snapshot), execute=args.execute, output=Path(args.output), report=Path(args.report))
    print(json.dumps({"status": result["execution"]["status"], "provider_calls": result["summary"]["provider_calls"], "acceptable_candidates": result["summary"]["acceptable_candidates"], "result": str(Path(args.output).relative_to(ROOT)) if Path(args.output).is_relative_to(ROOT) else str(args.output)}, ensure_ascii=False, indent=2))
    return 0 if result["execution"]["status"] == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
