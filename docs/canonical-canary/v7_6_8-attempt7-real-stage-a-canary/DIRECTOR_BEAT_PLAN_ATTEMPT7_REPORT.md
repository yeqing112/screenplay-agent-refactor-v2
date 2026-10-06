DIRECTOR_BEAT_PLAN_ATTEMPT7_VALIDATED
NEXT_STATE=DIRECTOR_CREATIVE_ENRICHMENT_AUTHORIZATION_REQUIRED

## Provider

- HTTP POST count: `1`
- HTTP status: `200`
- provider request ID: `` (empty as returned)
- finish_reason: `stop`
- choice index: `0`
- token usage: prompt `2460`, completion `735`, reasoning `0`, total `3195`
- latency: `24243.7 ms`
- raw length: `1326`
- raw SHA: `83b935f4062a3f9be1009fb91ce0d9e7c548020275ac478d4dbd05eaba7a38c7`
- transport attempts: `1`; retry: `0`

## Gates

- strict parse: `PASS`
- duplicate-key gate: `PASS` (`0` duplicates)
- schema: `PASS`; schema errors: `0`
- canonical top-level keys: `['version', 'scene_label', 'scene_objective', 'dramatic_question', 'beats', 'passthrough_refs', 'unknowns', 'confidence', 'note']`
- canonical beat keys: `['refs', 'purpose', 'objective', 'information_change', 'hook']`
- noncanonical key count: `0`
- hook type: `PASS`; distribution: `true=4, false=0`
- beat count: `4`
- text completeness: `PASS`
- source units: `12`; covered: `12`; missing: `0`; duplicate refs: `0`; invalid refs: `0`
- local creative completion: `0`
- materialized beat IDs: `['DBP_E01_SC001_001', 'DBP_E01_SC001_002', 'DBP_E01_SC001_003', 'DBP_E01_SC001_004']`
- raw IR fingerprint: `b3dbf2624289134c10d19f93c9cbd00614e9caa501dbe40cd002e24e42821086`
- materialized fingerprint: `328380be4977fe19f79f574d53facb9df61e229c7098ca28c4919fe25cc5bb01`

## Attempt-6 → Attempt-7

- hook problem: `resolved`
- canonical key drift: `resolved`
- new schema failure: `no`
- additional property violations: `0`
- required field omissions: `0`
- duplicate JSON keys: `0`

## Lineage and boundary

- ledger: `6 → 7`
- latest attempt: `attempt-7`
- latest status: `DIRECTOR_BEAT_PLAN_ATTEMPT7_VALIDATED`
- Stage A persisted attempt_id: `attempt-7`
- lineage parity: `PASS`
- Packet proposal before/after: `{"decision":"awaiting_llm"}` → `{"decision": "awaiting_llm"}`
- DirectorTreatment rows: `0`
- Authority rows: `0`
- Pointer rows: `0`
- Stage B calls: `0`
- IMAGE calls: `0`
- VIDEO calls: `0`
- Attempt-8: `0`

## Quality audit

Read-only content quality audit is stored separately and did not modify or gate the validated Provider output.

## Verification

- tests: `123 passed` before the single Provider call
- compileall: `PASS`
- git diff --check: `PASS`
- working tree: verified after evidence commit
- Commit SHA (implementation and evidence): `387ce66` (`387ce660fa2c92c9960b8be8f78567ca45db89bd`)
- Remote HEAD at implementation/evidence push: `387ce660fa2c92c9960b8be8f78567ca45db89bd`

## Identity

- system SHA256: `0d33e6805d856ec167ba6c6c9327f2942c6db159fd5edbacb3df0c16c25d12a7`
- user SHA256: `08d8372d31f939f1629a0ed8c094be3a8c56a611570216fa599c367aa0f4f9f4`
- prompt fingerprint: `2d6e0d66005d26edbed961ad45af4697f0954eefce99afaea0231c01b16c4c91`
- Provider Request Fingerprint V2: `eb7a104853cad07ba56da007270da4a352449c7ff0f61ecbac9f4e2f7902bab2`
