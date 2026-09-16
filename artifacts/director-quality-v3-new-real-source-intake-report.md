# Director Quality V3 — New Real Source Material Intake

## Baseline Audit

- Expected starting HEAD from the execution brief: `62216b1`; current implementation is later than that baseline and was audited without rewriting history.
- Existing 73-scene upstream audit remains legacy; families `990400/990401/990402` are isolated from the next Fresh Pilot.
- No unmarked workspace file was scanned or consumed.

## Final As-Built Verification

- Status: `DIRECTOR_V3_NEW_REAL_SOURCE_MATERIAL_INTAKE_READY`
- Provider / LLM / MiMo / HTTP / image / video / media / external storage calls: `0`
- Source package, versioning, stable scene identity, duplicate guard, clean lineage and approval evidence contracts: `PASS`
- Production DB mutations: `0`; book ID allocated: `false`
- Supported source formats: `.txt`, `.md`, `.markdown`, `.docx`, `.pdf`, plain pasted text (as implemented by the existing attachment parser).
- Intake targeted tests: `32 passed`; full backend regression: `1275 passed`; deterministic Golden: `5/5`.

## Decision

`DIRECTOR_V3_NEW_REAL_SOURCE_MATERIAL_INTAKE_READY`

`WAITING_FOR_REAL_SOURCE_MATERIAL`

The next step requires an explicitly supplied user-provided real screenplay path or manifest. Intake does not automatically run FactSnapshot, ScriptIR, Treatment or Blocking.
