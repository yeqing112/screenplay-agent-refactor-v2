# Production Prompt Lineage Canary Report

- Status: `PHASE_PRODUCTION_PROMPT_LINEAGE_CANARY_COMPLETE`
- Approval state: `PRODUCTION_PROMPT_LINEAGE_CANARY_APPROVED`
- Mode: provider-free frozen fixture
- Episode count: `1`; Shot count: `10`
- Prompt count: `12`; Prompt versions: `20`
- Generation intents: `11`; Assets: `13`; Reviews: `13`
- Prompt lineages: `13`; Provider calls: `0`

## Trace

`Shot Requirement → Generation Intent → Prompt Version → Asset Version → Human Review`

- `asset_has_prompt_lineage`: `True`
- `prompt_version_exists`: `True`
- `generation_intent_exists`: `True`
- `review_reproducible`: `True`
- `traceability_result`: `True`

## Fingerprints

- Same prompt / same fingerprint: `True`
- Changed prompt / different fingerprint: `True`

## Prompt change

- Prompt v1: `ppv_5ce6b933579d1ff97fce6569` → rejected review `par_afa33733ba37a2f9258de9df_01`.
- Prompt v2: `ppv_2015f5f9080855d4360740af` → new Asset Version `pav_0a558855a86e57d0cb636ab5` → approved review `par_6993fe54ecfcd097176a28b1_01`.
- Prompt v1 and its review history remain immutable and queryable.

## Boundary and audit

- Prompt history append-only: `True`.
- Source Fact mutations: `0`; ScriptIR mutations: `0`.
- No real Provider was called; fixture provenance is not external Provider output.
- This report closes `PHASE_PRODUCTION_PROMPT_LINEAGE_CANARY`; it does not announce `UI_V2_COMPLETE`.
