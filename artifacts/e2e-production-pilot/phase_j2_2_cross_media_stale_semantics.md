# Phase J2.2 Cross-Media Stale Semantics

## Core rule

Staleness is evaluated per media scope. A new generation intent in one scope is not evidence that a different scope is tampered or obsolete. Every scope uses its own stored `GenerationPolicy` plus the current shared upstream snapshot.

| Change | IMAGE PromptIR / Official Image | VIDEO PromptIR / Official Video | Historical integrity | Automatic regeneration |
|---|---|---|---|---|
| IMAGE policy revision `IMAGE A → IMAGE A2` | A becomes historical/stale; A2 becomes current after explicit compile/promotion | Unchanged if shared upstream and its reference remain valid | A and existing video remain historically valid | Never |
| VIDEO policy revision `VIDEO B → VIDEO B2` | Unchanged | B becomes historical/stale; B2 becomes current after explicit compile/promotion | IMAGE remains valid | Never |
| New VIDEO generation intent only | Unchanged | Creates/updates VIDEO scope only | IMAGE is not obsolete | Never |
| Shared storyboard, ShotPlan, blocking, or materialization revision | Re-evaluate IMAGE with stored IMAGE policy; stale if deterministic comparison fails | Re-evaluate VIDEO with stored VIDEO policy; stale if comparison fails | Old rows remain valid evidence unless their own envelope is tampered | Never |
| Character, scene, or prop authority revision | Re-evaluate each scope against current H2/H2.2 bindings; affected scopes stale | Same, using its own stored policy and references | Missing/changed current upstream is obsolescence, not historical tamper | Never |
| Official Image I1 → I2 while VIDEO explicitly binds current `SHOT_PRIMARY_IMAGE` | I1 superseded; I2 current | Existing Video remains historically valid but current lineage obsolete because its required current image binding changed | `historical integrity=VALID`, `current_lineage_valid=FALSE` | Never; explicit new VIDEO generation required |
| Official Image I1 → I2 while a future VIDEO contract binds immutable I1 | I1 historical; I2 current | Video may remain current against its immutable I1 binding, subject to policy approval | Both historical chains remain valid | Never |

## Required status distinction

The resolver must distinguish:

```text
historical_integrity_invalid / tampered
historical_integrity_valid + current_lineage_obsolete
current and resolvable
```

Moving an IMAGE pointer to IMAGE A2 or creating a VIDEO pointer must not mutate or mark the other scope's version as tampered. `PromptIRVersion.stale_status` and `PromptIRAuthority.stale_status` describe that version's own lineage; they are not a global per-shot flag.

## Official media and reference behavior

Official Image and Official Video each resolve through their execution target media and matching PromptIR pointer. `media_role` is a product role, not a type parser. A stale Video that depended on current Image I1 may remain available as historical evidence but must not be used as current production truth or silently repaired.

For the selected J2.1 contract, IMAGE_TO_VIDEO binds the current `SHOT_PRIMARY_IMAGE` authority. Therefore promotion of I2 makes a previously bound Video stale in current lineage. The system must wait for an explicit new VIDEO selection/execution; it must not move the Video pointer or regenerate automatically.

## Cross-media audit rule

Compile may inspect another scope for integrity diagnostics, but it must never compare a requested VIDEO policy directly against an IMAGE payload. Each scope is resolved by:

```text
stored scope policy + current shared snapshot + scope-specific references
```
