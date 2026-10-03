# Prompt Production Quality Report V2.1

## Result

`PROMPT_PRODUCTION_READY_FOR_MEDIA_CANARY`

- Blockers: `0`
- Structured JSON in provider prompts: `0`
- Internal token leaks: `0`
- Placeholder leaks: `0`
- Continuity actor contamination: `0`
- Reference lock rate: `100%`
- Pair alignment: `PASS`
- IMAGE score: average `8.74`, lowest `8.6`
- VIDEO score: average `8.64`, lowest `8.5`
- Shot 016: explicit non-generative transition; no fake prompt
- Real provider calls: `0`

## Authority and renderer boundary

CharacterProfile, SceneIdentity, VisualStyleProfile, ShotDirection and PromptIR are bound in each package. Provider payloads contain only natural-language projections plus explicit locked reference metadata. Negative prompts are supplied as supported provider-neutral text; no adapter placeholder is emitted.

## Deep review

### Shot 003
Red umbrella evidence is carried from the shot plan into the image and first-frame video projection; the visible set is 林晚 and 顾沉 only. The owning fix is shot-scoped continuity filtering.

### Shot 005
陆叔 and 林晚 are the only visible subjects; 顾沉 was removed from inherited continuity maps. The handoff remains a two-person power shift with one primary action and one reaction.

### Shot 008
The exit beat keeps 售票员 and 林晚 in the ticket hall. The camera push-in is the single camera motion and the ending state preserves the departure geometry.

### Shot 009
The apartment relationship is established with 林晚 and 陆叔. Scene identity, warm/cool mixed light, and the locked first frame are bound before rendering.

### Shot 012
The hard object on the table is the evidence beat. The prompt names the prop in natural language and does not expose internal event or asset identifiers.

## V1 → V2.1

V1 remains immutable under `docs/prompt-quality/`. V2.1 corrects shot-scoped actor contamination, adds authority completeness, adds independent renderers, adds first-frame and ending-state contracts, and fixes fingerprint freshness with renderer version.

## Cross-layer semantic gate

Shot 008 is resolved from PromptIR + ShotPlan + ShotDirection: visible subjects, action actors, camera target, ending actors and references are 顾沉 + 林晚. The pair comparison passes.

Input continuity contamination is retained as detected/remediated diagnostics; output contamination surviving to the provider is zero.

## Independent fixture

The Book 75 convenience-store and monitoring-room fixture produced six IMAGE prompts and six IMAGE_TO_VIDEO prompts with zero actor, camera, ending-state, reference, pair, JSON, token, or placeholder mismatches.
