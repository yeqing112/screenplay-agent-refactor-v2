# V7.6.20 Director Semantic V2 Residual Polarity Hardening

`DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT11_AUTHORIZATION_REQUIRED`

## Policy migration

- Old V2 policy fingerprint: `9df29513e7bf0433dae06b148b60e93f9afcb5517fd63d75a8b7b98c3994b501`.
- New V2 policy fingerprint: `cf75e024231e619f83f5b9ee79dc388cd199b25464d8d6f3e69ac6c0ab8cc4b8`.
- Changed: `YES`.
- Physical action scanner: clause-aware, polarity-aware, active positive clauses only, mixed clauses fail closed.
- ShotPlan scanner: shared polarity authority with meta compliance prefixes including `未新增`, `未添加`, `未增加`, `没有新增`, `没有添加`.

## Reassessment

- Attempt-10 historical diagnostic counts: `{'SceneBlocking_leakage': 0, 'ShotPlan_leakage': 1, 'certainty_collapse': 0, 'unsupported_story_action': 1}`.
- Attempt-10 current diagnostic counts: `{'certainty_collapse': 0, 'unsupported_story_action': 0, 'SceneBlocking_leakage': 0, 'ShotPlan_leakage': 0}`; status `PASS`; authority remains `DIAGNOSTIC_ONLY_STRUCTURALLY_INVALID`.
- Attempt-9 current V2 counts: `{'certainty_collapse': 1, 'unsupported_story_action': 1, 'SceneBlocking_leakage': 2, 'ShotPlan_leakage': 0}`; status `BLOCKED`; review fingerprint `1bd69e6ceb8d2b51b098fcabd7f877a636a338759dc5550365e92bef275af198`.
- Attempt-9 true violations remain blocked; historical reviews were not rewritten.

## Dual lineage and structural preservation

- Semantic parent: `attempt-9`.
- Structural failure source: `attempt-10`.
- Structural feedback fingerprint: `4d17ddadda4a473154491359f2dae9a7ae3a190669113fd16a2572cc89a64be4`; constraint count `1`; missing `visual_priority` (`array<string>`).
- Attempt-10 historical provider request fingerprint preserved: `True`.

## Attempt-11 preflight

- Status: `DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT11_AUTHORIZATION_REQUIRED`.
- Expected attempt: `attempt-11`; history `10`.
- Revision parent fingerprint: `72d79ca4fb8c23161274d4c617e2c91bcfecb599701270534762cc010569a15c`.
- System SHA: `6d2c045e97fdc3cfee6797a925010d5e7340fa71d04c41ed3ed59e65ff749baa`.
- User SHA: `752e95af67894f5dcdccdb7d2bd66608882a17f49002d4a0d853a0936ed7dee9`.
- Prompt fingerprint: `050f04dec12f7a41e183e7656d8bbdc7ca9864bc3490e0f25687bc95d9cb861b`.
- Provider request fingerprint: `f6d155ae2dacae455e9d5184cabad08f287cf737df6ff8d1ec2739e436ef1e6f`.
- Prompt differs from V7.6.19: `True`.
- Semantic feedback count: `4`; structural feedback count: `1`.
- Authorization: `REQUIRED_NOT_GRANTED`; Provider calls: `0`.

## Production invariants

- Packet 64 mutation: `0`.
- Ledger: `10 -> 10`.
- Active Stage B: `attempt-9 -> attempt-9`.
- Real LLM / Attempt-11 / Attempt-12 / IMAGE / VIDEO / SHAPI / Poyo / 75API: `0`.
- Approved DirectorTreatment / Authority / Pointer / SceneBlocking / ShotPlan writes: `0`.
- Proposal SHA before/after: `b2dd22fbfa197b06ba61044b44db151686564c419fa030a79201f23e39a598b4 -> b2dd22fbfa197b06ba61044b44db151686564c419fa030a79201f23e39a598b4` (unchanged).
- model_info SHA before/after: `6aff41437818a5aa25e5e19531e0099c087a3a16438f0cb8be09c06f2a3e5eaf -> 6aff41437818a5aa25e5e19531e0099c087a3a16438f0cb8be09c06f2a3e5eaf` (unchanged).

## Verification

- Dedicated V7.6.20 polarity tests: `10 passed`.
- V7.6.19 semantic/structural regression suite: `82 passed`.
- `python -m compileall -q core api scripts`: PASS.
- `git diff --check`: PASS.
- Production row before/after hashes unchanged: `PASS`.
- Working tree before final report-only commit: `CLEAN`.
- Evidence build commit SHA: `f3f0f9d`.
- Evidence build remote HEAD: `f3f0f9d`.
- Final delivery commit and remote HEAD are the final report-only commit shown by the repository branch after push.

All historical evidence remains immutable. The current V2 review is a new provider-free reassessment and is not production authority.
