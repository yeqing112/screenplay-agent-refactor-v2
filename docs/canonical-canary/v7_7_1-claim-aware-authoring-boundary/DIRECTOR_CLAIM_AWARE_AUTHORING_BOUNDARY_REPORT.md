# Director Claim-aware Authoring Boundary V7.7.1

Status: `SOURCE_CLAIM_MATERIALIZATION_BOUNDARY_REQUIRED`

## Architecture decision

V7.7.0's phrase extractor and special-case grounding remain `LEGACY_SHADOW_DIAGNOSTIC_ONLY`. The future path is `Authoring result -> BeatPlan IR + director_authoring_claim_manifest_v1 -> schema -> Authority Matrix -> typed SourceClaim binding -> semantic gate`. Prose is a human-readable rendering.

## Dependency audit

- V7.7.0 phrase dependence: `YES`.
- V7.7.0 scene dependence: `YES`.
- V7.7.0 special-case grounding dependence: `YES`.
- V7.7.0 baseline scene coupling: `E01_SC001` appeared in the historical extractor; V7.7.1 runtime scene binding removes that dependency from the future path.
- V7.7.1 future typed path phrase/scene/attempt dependence: `NO`.
- Heuristic production dependency: `NO`; production migration remains off.
- Legacy extractor role: historical forensic shadow only.
- Future production extractor role: none; the future production path consumes a co-produced typed manifest.

## Contracts

- Claim Manifest: `director_authoring_claim_manifest_v1` with typed claim fields and optional provenance. `raw_text` and `source_path` are not identity requirements.
- Source Claim materialization: `SOURCE_CLAIM_MATERIALIZATION_BOUNDARY_REQUIRED`. Current SourceAuthoringUnit lacks `actor, action, object, participants, fact_bindings, entity_refs`; text is evidence/provenance only.
- Stage A fields: `beats[].objective` is `DRAMATIC_OBJECTIVE`; canonical intent requires an explicit manifest claim. Information changes require typed source claim IDs.
- Stage B fields: performance and audience fields are creative/non-canonical unless a typed canonical claim explicitly requests source authority.
- Relation registry: `director_claim_relation_registry_v1`.
- Entity binding: runtime canonical refs from declared participants and upstream entity registry; no invented story IDs.
- Completeness: structured semantic slots and covered slots; no lexical blacklist.
- Generic code scan: future typed production path has no forbidden phrase, scene, book or attempt token; legacy extractor/grounding are explicitly excluded and classified as shadow diagnostics.

## Typed mock results

- Stage A BeatPlan + manifest: PASS.
- Unsupported provenance: BLOCKED.
- Certainty over typed uncertainty: BLOCKED.
- Stage B performance option: PASS.
- Canonical intent without SourceClaim: BLOCKED.
- Cross-object property: BLOCKED.
- Environment state mismatch: BLOCKED.
- Possession without matching transfer: BLOCKED.

## Safety and production state

- Provider calls: 0; Stage A revision: 0; Attempt-12: 0; Confirm: 0.
- IMAGE/VIDEO/SHAPI/Poyo/75API: 0.
- Production writes: 0.
- Ledger: 11 -> 11; active Stage B: attempt-11 -> attempt-11.
- Proposal/model_info unchanged; no Authority promotion, SceneBlocking, ShotPlan, IMAGE, VIDEO or PR work.

## Stage A decision

Stage A revision is **not safe**. The typed contract and support path are designed, but SourceClaim materialization must happen first. V7.7.0 historical evidence remains immutable and is not rewritten.

## Known V2 baseline

Three SceneBlocking authority failures remain pre-existing and are recorded in `PRE_EXISTING_SCENEBLOCKING_REGRESSION_BASELINE.json`; V7.7.1 did not modify those paths.

## Delivery verification

- Tests: V7.7.1 + V7.7.0 + targeted V7.2-V7.6 regression **208 passed, 0 failed**; isolated SceneBlocking baseline **12 passed, 3 pre-existing failures**.
- Compileall: PASS.
- Git diff check: PASS.
- Working tree: required clean after push.
- Commit SHA and remote HEAD: recorded after final push and required equal.
