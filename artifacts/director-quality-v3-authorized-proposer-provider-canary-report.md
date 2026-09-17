# Director Quality V3 — Authorized Proposer Provider Canary

## Baseline Audit

- Scope: only required MissingFactManifest items; maximum 8 candidate anchors per fact.
- Provider role: `PROPOSER`; FactSnapshot / authority / ScriptIR / production writes are forbidden.
- Explicit execution requested: `true`; provider configured: `false`.

## Canary Results

- Required facts: `6`; provider calls: `0` / max `6`.
- Proposals: `0`; exact-evidence pass: `0`; semantic-support pass: `0`.
- Acceptable candidates (dry-run only): `0`.

| Fact | Anchors | Called | Proposed value | Exact evidence | Semantic support | Classification |
|---|---:|---|---|---|---|---|
| `character|宋知夏|visual_identity|global` | 8 | false | — | `PASS` | `—` | `PROVIDER_NOT_CONFIGURED` |
| `character|宋知夏|current_state|global` | 8 | false | — | `PASS` | `—` | `PROVIDER_NOT_CONFIGURED` |
| `character|程雨|visual_identity|global` | 8 | false | — | `PASS` | `—` | `PROVIDER_NOT_CONFIGURED` |
| `character|程雨|current_state|global` | 8 | false | — | `PASS` | `—` | `PROVIDER_NOT_CONFIGURED` |
| `scene|production_scene|geometry|global` | 0 | false | — | `PASS` | `—` | `NO_CANDIDATE_ANCHOR` |
| `prop|production_props|state|global` | 0 | false | — | `PASS` | `—` | `NO_CANDIDATE_ANCHOR` |

## Zero-anchor Retrieval Diagnostics

- `scene|production_scene|geometry|global`: query=`[]`, scene_heading=`True`, environment=`True`, prop_mentions=`True`, hint=`RETRIEVAL_RECALL_GAP`.
- `prop|production_props|state|global`: query=`[]`, scene_heading=`True`, environment=`True`, prop_mentions=`True`, hint=`RETRIEVAL_RECALL_GAP`.

## Audit

- Logical provider calls: `0` audit records; transport/parser retries are configured as `0`.
- Usage (when returned): input `0`, output `0`, cached `0` tokens; cache hit/miss `0/0`.
- Latency samples: `0`; estimated cost is provider-dependent and omitted when unavailable.
- Provider/model: `` / ``.
- Cache, usage and latency fields are retained only in bounded LLM audit records; credentials are never persisted.

## Safety Verification

- `dry_run=true`; `fact_snapshot_writes=0`; `authoritative_record_writes=0`; `production_writes=0`.
- Simulated coverage status: `FACT_COVERAGE_INSUFFICIENT`; formal coverage and ScriptIR status are unchanged.
