# V7.6.21 Director CreativeEnrichment Attempt-11 Real Semantic V2 + Structural Revision Canary

DIRECTOR_CREATIVE_ENRICHMENT_ATTEMPT11_VALIDATED
NEXT_STATE=DIRECTOR_TREATMENT_SEMANTIC_REVIEW_REQUIRED
SEMANTIC_REVIEW_V2=BLOCKED

## Transport

- Endpoint: `POST /api/books/990453/episodes/1/director-treatment/creative-enrichment/revision/llm-draft`.
- Authorization: `v7.6.21-attempt11-stage-b-semantic-v2-structural-single-call`; real Provider POST: `1`; automatic retry: `0`.
- Provider profile: `local-llm-2vydoz / mimo-v2.5 / https://api.xiaomimimo.com`.
- HTTP status: `200`; Provider request ID: `None`; finish_reason: `stop`; latency: `89251.69 ms`.
- Tokens: `{'prompt_tokens': 6277, 'cached_tokens': None, 'completion_tokens': 3169, 'total_tokens': 9446, 'cache_hit_rate': None, 'reasoning_tokens': 0, 'completion_tokens_details': {'reasoning_tokens': 0}, 'prompt_tokens_details': {}}`; raw length: `6704`; raw SHA: `383e673412ba6c55e27965a3c1b920044bd0a5172d5d9b8772ad282bbf4cb024`.

## Structural and lineage gates

- Strict parse: `PASS`; duplicate key: `PASS`; schema: `PASS`; top-level keys: `11/11`; missing required fields: `[]`; visual_priority: `yes`.
- Text completeness: `PASS`; runtime validation: `qualified`; beat coverage: `PASS`.
- Stage A binding: `PASS` (`attempt-7`, `b3dbf2624289134c10d19f93c9cbd00614e9caa501dbe40cd002e24e42821086`, `328380be4977fe19f79f574d53facb9df61e229c7098ca28c4919fe25cc5bb01`).
- Semantic parent: `attempt-9`, IR `591bf4ec2f7df8b80a8fdd3a7166c6a76c39a7de0939ba3b1323b6af2320dfaa`, policy `cf75e024231e619f83f5b9ee79dc388cd199b25464d8d6f3e69ac6c0ab8cc4b8`, review `1bd69e6ceb8d2b51b098fcabd7f877a636a338759dc5550365e92bef275af198`, revision parent `72d79ca4fb8c23161274d4c617e2c91bcfecb599701270534762cc010569a15c`.
- Structural source: `attempt-10`, feedback `4d17ddadda4a473154491359f2dae9a7ae3a190669113fd16a2572cc89a64be4`.
- Source fingerprints: `2089dccea46d2392a328335a75266f1c982a66a4d53cda5c502f748fbf95e37f / ea83de61dddd12842ea319e367f284a620bad83ad2c8643b65d331aa003db1c8`.

## Semantic V2

- Attempt-11 IR fingerprint: `78710067de3b0bb119130cd674a61be99f49a54073004ea4b68aadb6e7fa7db8`; semantic review fingerprint: `46ce6eb79c51f6daa3605e383d5ba6e920c5915b88127e8d7e30d5a6d0aa0617`.
- Semantic status: `BLOCKED`; counts certainty `0`, story action `0`, SceneBlocking `0`, ShotPlan `1`.
- Attempt-9 → Attempt-11: `{'certainty_collapse': 1, 'unsupported_story_action': 1, 'SceneBlocking_leakage': 2, 'ShotPlan_leakage': 0} -> {'certainty_collapse': 0, 'unsupported_story_action': 0, 'SceneBlocking_leakage': 0, 'ShotPlan_leakage': 1}`.
- Polarity false-positive count: `1`. The blocking term is the generated note's delegation phrase `交由下游 SceneBlocking 与 ShotPlan 权威处理`; it did not trigger physical action or certainty violations.
- Creative quality audit: 4/4 beats, performance action hits `['停顿', '僵住', '呼吸', '目光', '节奏', '表情', '语气']`, visual priority present and useful; semantic PASS is not treated as creative-quality PASS.

## Persistence and boundaries

- Active Stage B: `attempt-9 -> attempt-11`; stage_b_attempts: `attempt-8, attempt-9, attempt-10, attempt-11`.
- semantic_review_assessments: `0 -> 1`; proposal: `ready_for_review / PROPOSED`; confirm called: `0`; confirm_allowed: `false`; next state: `DIRECTOR_TREATMENT_SEMANTIC_REVIEW_REQUIRED`.
- DirectorTreatment approved writes: `0`; Authority: `0`; Pointer: `0`.
- SceneBlocking / ShotPlan / PromptIR / IMAGE / VIDEO / SHAPI / Poyo / 75API: `0 / 0 / 0 / 0 / 0 / 0 / 0 / 0`.
- Attempt-12: `0`; automatic retry: `0`; Attempt-9 and Attempt-10 archives preserved: `true / true`.
- Attempt-9 raw in prompt: `false`; Attempt-10 raw in prompt: `false`; semantic and structural feedback blocks: `true / true`.

## Verification and delivery

- Provider-free regression after call: run separately; no Provider call is made by tests.
- `python -m compileall -q core api scripts`: run separately.
- `git diff --check`: run separately.
- Working tree at evidence generation: `DIRTY`.
- Evidence commit SHA: `184362b693c3c4cce242e165bdba87c912f39d0b`; remote HEAD: `184362b693c3c4cce242e165bdba87c912f39d0b`.
