# Generalized Canary Real Production Persistence V7 Report

Status: `GENERALIZED_CANARY_PRODUCTION_PERSISTED`
Next state: `DIRECTOR_CREATIVE_AUTHORING_AUTHORIZATION_REQUIRED`
Persistence run: `20261006T013634Z-8bf0de6a0e95514a`

## Final report (36 required answers)

1. **Base HEAD:** `50b874f6869cc9e27006c2ce5bdd1ec8a8e576db`; V6.1/V6.2/V6.3 targeted gate passed (`90 passed`).
2. **Origin Book / Chapter:** `990402 / 16`, sequence `3`.
3. **Origin raw SHA:** `190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1` (762 bytes).
4. **Raw LLM response SHA:** `f4204059934cf19eebf4fcb94278756c48eaefce853d947cb5af16db133452ef`.
5. **Original Candidate fingerprint:** `ee66d644cfe91a2f3ad81865247707ac69a6746cfc405d4ddc98af1783456d21`.
6. **Salvaged V2 fingerprint:** `6fad483a2b7f1c73eac42321f13bdae9a41bab4a8b220f72919a6decbb4c7400`.
7. **Reconciliation fingerprint:** `aee7ad3b79f2da379ce42af79082653970a7d5bba6b3382cd507adfcc3f5539c`.
8. **Migrated V3.1 Candidate fingerprint:** `5d24ed442c7df57a845f21a596f54ebcef1a1c5e52770dbf0e3b47e2e08892cb`.
9. **Grounded V3.1 fingerprint:** `14808c1f649d69acefabb4cb810dae5bc70dc2d5fff88209602ac47393f26d32`.
10. **Migration fingerprint:** `4541e40f88dfcdada955f2603c2d8c7d71fe328b8c802b3a0746fec2ec61ed40`.
11. **Frozen manifest fingerprint:** `3b26e37276251d7dc58b03a72ff1993c2d28a4bbfecc0284c4f20e3dd1563833`; status `FROZEN_COMPLETE_SELF_CONSISTENT`.
12. **New Book ID:** `990453`.
13. **New Script ID:** `64`.
14. **FactSnapshot ID:** `49`.
15. **FactRecord count:** `2`.
16. **ScriptIR Version ID:** `52`.
17. **Authority Envelope schema:** `script_ir_authority_envelope_v2`.
18. **Authority profile:** `SOURCE_GROUNDED_V3_1`.
19. **Creative readiness state:** `AUTHORING_REQUIRED`.
20. **Beats count:** `0`.
21. **Transitions count:** `0`.
22. **Target dialogue preserved:** `PASS` — 顾沉 / 也许是你自己.
23. **Speaker/binding preserved:** `PASS` — AUTHORIZED_SEMANTIC_BINDING / COREFERENCE_RESOLUTION; assertion_mode empty.
24. **FactSnapshot source hash:** `190ab63c632ca47ae6c6fa224c1fad9622eca49218ef9f14c3fa18ce98641cb1`.
25. **FactRecord evidence:** `PASS` — all evidence refs are validated Origin anchors (E0001, E0004), authority source_text.
26. **Production resolve:** `PASS`.
27. **Director boundary:** `DIRECTOR_INPUT_READY`; read-only readiness only, no DirectorTreatment created.
28. **External LLM calls:** `0`; LLM POST requests `0`.
29. **IMAGE / VIDEO calls:** `0 / 0`; SHAPI `0`, Poyo `0`, 75API `0`.
30. **Production DB exact delta:** Books `+1`, Scripts `+1`, FactSnapshots `+1`, FactRecords `+2`, ScriptIRVersions `+1`; all downstream tables `+0`.
31. **Partial persistence:** `YES, recovered safely` — Book/Script formal commits completed before an orchestration ORM access error; same run id continued once; no duplicate Book/Script.
32. **production_status:** Script `blocked`; reason `CREATIVE_AUTHORING_REQUIRED`.
33. **Next stage:** enter Director creative authoring only after separate authorization.
34. **Working tree:** clean after final commit.
35. **Commit SHA:** `702c166e642ae2cd08a80905d095f0c80eeb22bc` (production persistence commit; this closure update is evidence-only).
36. **Remote HEAD:** `702c166e642ae2cd08a80905d095f0c80eeb22bc` at the production persistence push; the final evidence-only closure commit is reported in the delivery response.

## Frozen and execution evidence

- Origin refreeze: `PASS`.
- Historical forensic refreeze: `PASS` (persisted_before_parse=true, one transport attempt, retry=false, mimo-v2.5, local-llm-2vydoz).
- V2→V3.1 generalized migration: `PASS`; provider calls `0`.
- Final provider-free preflight: `PASS`.
- Authority envelope: `script_ir_authority_envelope_v2`, `SOURCE_GROUNDED_V3_1`, PRODUCTION_QUALIFIED, FRESH.
- No Director, Treatment, Blocking, ShotPlan, Storyboard, PromptIR, IMAGE, VIDEO, Media or OfficialMedia writes.
- Formal lifecycle used: `core.book_lifecycle.create_book`, `core.book_lifecycle.create_script`, `prepare_script_ir_production(confirmed=true)`.

Evidence directory: `docs/canonical-canary/v7-real-production-persistence/`.

