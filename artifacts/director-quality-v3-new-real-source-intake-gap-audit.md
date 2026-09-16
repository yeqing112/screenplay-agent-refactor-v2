# Director Quality V3 — New Real Source Material Intake Gap Audit

## Baseline Audit

- Starting reference HEAD: `62216b1`; current as-built code is audited without rewriting historical evidence.
- The 73 audited scenes and families `990400/990401/990402` remain legacy/isolated. No old scene, orphaned approval, fixture or generated sample is selected as Fresh input.

## Final As-Built Verification

| Requirement | Evidence |
|---|---|
| Real Source Package V1 | PASS — immutable package schema, provenance and hashes |
| Source versioning | PASS — immutable raw copy, parent/version/hash binding |
| Stable scene source identity | PASS — package + version + ordinal, independent of scene title |
| Duplicate guard | PASS — existing, retired and provider-exposed fingerprints |
| Clean lineage | PASS — explicit Source → FactSnapshot → ScriptIR → Treatment → Blocking edges; skip states rejected |
| Approval evidence | PASS — approval type, reviewer, timestamp and both fingerprints |
| Provider generation = approval | NO — deliberately separate |
| Fresh eligibility clean-lineage check | PASS — `CLEAN_LINEAGE_REQUIRED` hard check |
| Intake CLI | PASS — explicit `--source`/`--manifest`; no workspace scan or bypass flags |
| Dry-run production DB mutation | `0` |
| Provider / LLM / MiMo / HTTP / media / storage / CI calls | `0` |
| Supported source formats | `.txt`, `.md`, `.markdown`, `.docx`, `.pdf`, plain pasted text |
| Preferred format | UTF-8 plain text or Markdown |
| New real source currently present | `NO`; ingestion remains explicit and authorized |
| New book ID allocated | `false` |
| Fresh Pool / Pilot #2 | `BLOCKED` / `NOT READY, NOT AUTHORIZED, NOT FROZEN` |
| Atomic / Production / Human Preference | `HOLD` / `HOLD` / `NOT_RECORDED` |

## Decision

`DIRECTOR_V3_NEW_REAL_SOURCE_MATERIAL_INTAKE_READY`

`WAITING_FOR_REAL_SOURCE_MATERIAL`

The infrastructure is ready. The next run must receive an explicitly identified user-provided real screenplay; no upstream creative stage is started by Intake.
