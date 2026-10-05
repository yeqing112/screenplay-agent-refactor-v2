# Canonical Canary Semantic Selection V2

Status: `NO_SEMANTICALLY_USEFUL_CANONICAL_CANARY_TARGET`  
Run: `20261005T091321Z`  
Policy: `canonical_canary_selection_policy_v2`

## 1. Why the previous twelve-way 25-point tie occurred

The V1 extractor counted `prompt_compiler_handoff.asset_identity_bindings.characters` and `props`, while canonical semantic truth lives in `visual_semantic_handoff.subjects`, `visual_semantic_handoff.props`, and its nested `canonical_asset_identity`. V1 also treated missing VIDEO PromptIR as a hard gate and used a smaller score. The twelve 25-point rows were therefore a clone-like empty-scene tie, not evidence of twelve equally strong dialogue canaries.

## 2. Character truth

The V2 extractor reads the canonical `StoryboardShot` projection. Across `20` rows: subject_count=0 for `20`, dialogue_present=false for `20`, and semantically useful rows=`0`. The current canonical source itself contains no subjects or dialogue; this is not an extractor omission. No historical benchmark prompt was used to infer characters.

## 3. Book / project provenance

- `990448`: `UNKNOWN_PROVENANCE`; eligible=`False`; evidence: books row; task_runs row; no explicit production/canary/test provenance marker found.
- `990449`: `UNKNOWN_PROVENANCE`; eligible=`False`; evidence: books row; task_runs row; no explicit production/canary/test provenance marker found.
- `990450`: `CANARY_PROJECT`; eligible=`False`; evidence: books row; task_runs row; GenerationExecutionRecord execution_mode/provider explicitly identifies canary/fake runtime.
- `990451`: `CANARY_PROJECT`; eligible=`False`; evidence: books row; task_runs row; GenerationExecutionRecord execution_mode/provider explicitly identifies canary/fake runtime.
- `990452`: `CANARY_PROJECT`; eligible=`False`; evidence: books row; task_runs row; committed Playwright browser zero-call evidence explicitly names this book.

Book IDs never contribute to quality score; they are used only for evidence grouping and stable output ordering. Unknown, test, migration, and non-official canary projects are not production E2E targets.

## 4. Current production canary conclusion

There is no database row currently suitable for a production canary that tests `人物 + 对白 + IMAGE→VIDEO`. All current rows fail the semantic minimum (`subject_count >= 2 and dialogue_present`, or a one-subject meaningful performance/action fallback). The correct result is `NO_SEMANTICALLY_USEFUL_CANONICAL_CANARY_TARGET`; no winner was manufactured.

VIDEO PromptIR missing is recorded as `MISSING_COMPILE_REQUIRED` in execution readiness and does not remove an otherwise canonical row. No PromptIR compilation was executed.

## Runtime safety

- IMAGE default: `75api-image` / `gpt-image-2-1k`; real IMAGE calls `0`; IMAGE POST `0`.
- VIDEO default: `75api-minimax-h3` / `minimax_h3`; real VIDEO calls `0`; VIDEO POST `0`.
- External LLM `0`; SHAPI `0`; Poyo `0`.
- PromptIR production writes `0`; media writes `0`; OfficialMedia writes `0`.
