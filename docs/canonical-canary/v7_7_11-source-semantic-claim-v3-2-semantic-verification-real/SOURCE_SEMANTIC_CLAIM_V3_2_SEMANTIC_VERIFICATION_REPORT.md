# V7.7.11 Source Semantic Claim V3.2 Semantic Verification

- Baseline: `0cd7dc57dbf0a7541c73bd56f2b426c6afce2551`. Claim: `SCC_V7_7_10_0001`; candidate fingerprint `6f5a6a567c83d674f5ecc463ef44bfcc9ecfd0e5798a44a166be929ed5f8717f`; candidate set fingerprint `d896b80a538f515a17a0d82058bbed45d1582675e8a563aabb9929d6f3ac1bfb`; V7.7.10 raw `39c43a5a571f220e15bc88c273f7652fe4679fc52b629886c00713a8e6d21b1a`.
- Verifier input eligibility: `VERIFIER_INPUT_ELIGIBLE`. Transport mapping: `FACT_0001` ↔ `SCC_V7_7_10_0001`; transport IDs are not production Fact IDs.
- Required components: `['SUBJECT', 'PREDICATE', 'OBJECT', 'QUALIFIER:guided_character', 'POLARITY', 'MODALITY']`. Evidence authority `PASS`; typed atomicity `PASS`; support role `ACTION_OCCURRENCE`; anchor surface `NARRATIVE_PROSE`; confirmation ceiling `{'allowed': True, 'ceiling': 'CANDIDATE_WORLD_EVIDENCE', 'reason': 'narrative_prose_still_requires_semantic_entailment'}`.
- Provider: `local-llm-2vydoz / mimo-v2.5`; verifier POSTs `1`; HTTP `400`; finish ``; latency `4727.54 ms`; usage `{'prompt_tokens': None, 'cached_tokens': None, 'completion_tokens': None, 'total_tokens': None, 'cache_hit_rate': None, 'reasoning_tokens': None, 'completion_tokens_details': {}, 'prompt_tokens_details': {}}`.
- Provider transport error: `HTTPStatusError: 400 Bad Request`; the forensic audit records the provider diagnostic `Unsupported model mimo-v2.5`.
- Raw SHA ``; length `0`; parse `BLOCKED`; schema `False`; cardinality `BLOCKED`.
- Verdict `None`; supported `None`; unsupported `None`; component contract `BLOCKED`.
- Disposition `None`; effective authority `None`; effective status `None`; downstream eligible `None`; review required `None`; shadow only `true`; production persisted `false`.
- Program speech companion count `1`; speech verifier posts `0`; proposal and second-order posts `0`; SourceClaim / FactRecord writes `0 / 0`.
- Completeness remains: proposal `NOT_PROVEN`, entity semantic `NOT_PROVEN`, second order `DEFERRED_NOT_PROVEN`, typed director manifest `MISSING`. Ledger `11`; active Stage B `attempt-11`.
- Preflight tests: `203 passed in 1.65s`; compileall `PASS`; git diff check `PASS`.
- Status: `SOURCE_SEMANTIC_CLAIM_V3_SEMANTIC_VERIFICATION_BLOCKED`. Next: `SOURCE_SEMANTIC_CLAIM_V3_SEMANTIC_VERIFICATION_REVIEW_REQUIRED`. No retry, proposal, persistence, Stage A, Attempt-12, Confirm, image, video, PR, or merge was performed.
