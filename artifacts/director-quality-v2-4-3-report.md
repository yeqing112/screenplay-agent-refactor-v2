# Director Quality V2.4.3 — Targeted Tail Repair Value Re-evaluation

Generated: `2026-09-14T18:35:38.729251+00:00`

## Scope

Frozen 15-scene cohort (5 approved_record + 10 fixture), 27 historical root causes, maximum 54 semantic attempts. No Full24, production shadow, storyboard/media generation, or object-storage side effects.

## Protocol reliability

- Semantic attempts: **28**; HTTP requests: **28**; JSON parser retries: **0**.
- Root-cause acceptance: **27/27 (100.0%)**.
- Creative Value measurement statuses: `ready`.

## Value results

- DQ mean delta: **6.75**; median delta: **6.4**.
- Creative Value mean delta: **11.5802**; median delta: **11.11**.
- Tail reduction (<60): **14.3%**.

## Gate decision

**FAIL** — `NOT_READY_FOR_FULL_24_REEVALUATION`.

The protocol is reliable, but this value experiment does not meet the V2.4.3 uplift thresholds. In particular, DQ mean/median, Creative Value mean, and tail-reduction gates remain below target. This result must not be promoted to Full24 or Production Shadow.

## Cohort separation

Approved-record scenes: **5**; fixture scenes: **10**. Fixture success is not treated as production-value proof.

## Side effects

All production, storyboard, media, object-storage, and production-shadow counters are zero.

## Source artifacts

- `artifacts/director-quality-v2-4-3-provider-free-preflight.json`
- `artifacts/director-quality-v2-4-3-targeted-tail-manifest.json`
- `artifacts/director-quality-v2-4-3-targeted-tail-pilot-real.json`
