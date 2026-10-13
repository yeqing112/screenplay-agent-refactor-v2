# V7.7.8 Source Semantic Claim V3 Foundation

## Contracts and entity authority

- Claim V2 modified: `NO`; frozen versions: `source_semantic_claim_candidate_v2` / `source_semantic_claim_candidate_set_v2`.
- V2 blocker reproducible: `LEGACY_BLOCKED_UNION_TYPE` / `UNION_TYPE_UNSUPPORTED:$.properties.claims.items.properties.qualifiers.additionalProperties.type`.
- `oneOf` patch used: `NO`; V3 uses a scalar-string qualifier wire contract.
- V3 versions: `source_semantic_claim_candidate_v3` / `source_semantic_claim_candidate_set_v3`.
- Provider outputs entity kind: `NO`; program resolves refs through `source_claim_input_entity_registry_v1`.
- Provider outputs `claim_type` / `relation_class`: `NO`; program projects them from relation signatures.
- Claim ID owner: `program after validation`; generated prefix: `SCC_`.
- Verified entity freeze: `88de4d7793043c11897605217c3e6a29847062eb87ac4b7bb20909b147e6b186`; canonical `4`, verified proposals `15`, blocked `0`, promotions `0`.

## Qualifier and relation ontology

- Qualifier wire scalar: `string`; registry: `source_claim_qualifier_registry_v2`.
- V3 qualifier keys/types: `{"destination": "ENTITY_REF", "light_state": "SYMBOLIC_TOKEN", "property_domain": "SYMBOLIC_TOKEN", "speaker_binding": "SYMBOLIC_TOKEN", "state_domain": "SYMBOLIC_TOKEN", "transfer_source": "ENTITY_REF"}`.
- ownership / possession ambiguity: both audited; both excluded from V3 (`V3_SUPPORTED=false`). `ownership` would conflate provenance with an independent ownership fact; `possession` duplicates receipt/possession relation without a unique temporal modifier meaning.
- Boolean decoding: only exact `TRUE` / `FALSE`; current V3 registry has no Boolean qualifier key; isolated decoder fixture tested these tokens.
- Relation signature registry: `source_claim_relation_signature_registry_v2`.
- Proposable predicates `6`: `enter_guided, has_property, left_by, received_by, speech_act, state_value`.
- Excluded legacy structural predicates `2`: `{"scene_existence": "STRUCTURAL_COUNT", "scene_identity_evidence": "STRUCTURAL_EVIDENCE_SET"}`.
- Unresolved relation signatures `2`: `{"knows": "RELATION_SIGNATURE_UNRESOLVED: object domain is not a single registered entity kind.", "uncertainty": "RELATION_SIGNATURE_UNRESOLVED: proposition/value direction has no unique registered entity-kind signature."}`.
- Predicate-name and source-prose inference: `NO`. The unresolved `knows` and `uncertainty` signatures stay outside the provider predicate registry.

## Schema and deterministic projection

- V3 internal / transport schema: `PASS` / `PASS`.
- Transport schema fingerprint: `cbbb2a6a46689af9421ba192fe66f31e3b0d545545fe2f7a479d324a01bcf193`.
- V3 union / oneOf / anyOf / dangling ref counts: `{"anyOf": 0, "dangling_ref": 0, "oneOf": 0, "union_type": 0}`.
- Program-owned semantic projection: `PASS`; typed subject/object, claim type, relation class, qualifiers and `SCC_` IDs are compiled only after candidate validation.
- Fingerprint inputs: typed semantics, sorted evidence/source-unit refs and registry versions; display prose/path/time excluded.

## Provider-free mock results

- Pass: `True`.
- Unknown qualifier: `True`.
- Unregistered ENTITY_REF: `True`.
- Boolean exact decode: `True`.
- Wrong relation signature: `True`.
- Unknown entity ref: `True`.
- Program-owned claim IDs / authority: `True` / `True`; projected claims remain `UNTRUSTED_PROPOSED` and non-canonical.

## Provider and production boundary

- Real Provider calls: `0` (Entity Proposal / Entity Verifier / Claim Proposal / Claim Verifier all `0`).
- V7.5.1 current branch revalidation: `HISTORICAL_REVALIDATION_ONLY`; it is not a V7.7.8 gate or Provider authorization input. Historical V7.5.1 artifacts were not rewritten.
- FactSnapshot / FactRecord / SourceClaim / canonical writes: `0`.
- Production freeze unchanged: `True`.
- FactSnapshot 49 / ScriptIR 52 / Packet 64: unchanged.
- Director ledger: `11 -> 11`; active Stage B: `attempt-11 -> attempt-11`; Stage A / Attempt-12 / Confirm: `0 / 0 / 0`; IMAGE / VIDEO: `0 / 0`.
- Source scope lineage: target Book `990453`; origin Book `990402`, package `book:990402`, chapter `16` seq `3`; raw SHA256 `190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1`; source units `12` / `2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f`.
- Anti-Heuristic review: `PASS`; phrase/scene/attempt/PEC/source literal/local NLP/predicate-name/qualifier-name dependency: `NO`.
- Typed Director Requirement Manifest remains `TYPED_DIRECTOR_REQUIREMENT_MANIFEST_MISSING`; entity completeness remains `NOT_PROVEN`.

## Verification and delivery

- Tests: `72 passed across the V7.7.8 foundation and V7.7.2–V7.7.7 focused regression suites`.
- SceneBlocking historical baseline: `historical broad regression: 227 passed, 3 pre-existing V2 SceneBlocking authority failures (V7.7.0 audit); not rerun or modified`; no SceneBlocking code changed.
- Python compileall: `PASS`; `git diff --check`: `PASS`.
- Branch: `codex/visual-authoring-provider-canary-reconcile`; working tree after evidence publication: `CLEAN`, local HEAD matched remote.
- Implementation commit: `567553e883ad7010c8d10be2f4657a7f37ad7219`; remote HEAD at evidence generation: `567553e883ad7010c8d10be2f4657a7f37ad7219`.
- Evidence publication commit: `70a4a4f681b342dc670a99231e90971e183d19e5`; remote HEAD after evidence publication: `70a4a4f681b342dc670a99231e90971e183d19e5`.
- Overall status: `CLAIM_V3_RELATION_SIGNATURE_BOUNDARY_REQUIRED`.
- Next state: `CLAIM_V3_RELATION_SIGNATURE_BOUNDARY_REQUIRED`.

V3 schema compilation is structurally ready, but the foundation is not marked READY while two mapped relations (`knows`, `uncertainty`) lack a defensible single-kind direction signature. They remain excluded from Provider proposability pending ontology resolution.
