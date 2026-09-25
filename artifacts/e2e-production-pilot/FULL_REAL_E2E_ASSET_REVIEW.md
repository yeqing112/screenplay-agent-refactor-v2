# FULL_REAL_E2E Asset Review

- Status: `FULL_REAL_E2E_BLOCKED_BY_REAL_VISUAL_ASSET_MEDIA`
- Scope: Episode 01, 15 Production Assets (4 characters, 2 scenes, 9 props)
- Provider / image / video / paid LLM calls: `0 / 0 / 0 / 0`

This review records factual readiness only. No aesthetic or identity-quality score was assigned. No file was bound by filename, approximate name, folder, or visual similarity.

## Asset checklist

| Type | Entity | Current version | Real media | Technical review | Shots |
|---|---|---|---|---|---|
| CHARACTER | `GU_CHEN` | `pav_9e3aecfdf89b5a472fe93f53` | `MISSING` | `NOT_RUN` | 3, 4, 8 |
| CHARACTER | `LIN_WAN` | `pav_6033ae432b0d07a61f4d50e7` | `MISSING` | `NOT_RUN` | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15 |
| CHARACTER | `LU_SHU` | `pav_b8f31e5a2c5bfabcf481be6d` | `MISSING` | `NOT_RUN` | 5, 7, 9, 10, 12, 14, 15 |
| CHARACTER | `TICKET_CLERK` | `pav_0523142173a4d6fec2ee01b3` | `MISSING` | `NOT_RUN` | 1 |
| PROP | `APPLE` | `pav_d7bb5b0fe5d1663d675cd283` | `MISSING` | `NOT_RUN` | 9 |
| PROP | `BROKEN_UMBRELLA_RIB` | `pav_70c4360562349eb0fa4428e4` | `MISSING` | `NOT_RUN` | 3, 6 |
| PROP | `DOOR_LOCK` | `pav_b68555898e9b16a7c3d1ea6d` | `MISSING` | `NOT_RUN` | 9 |
| PROP | `HANDBAG` | `pav_2644388eab9b859fddacc2a1` | `MISSING` | `NOT_RUN` | 5, 11 |
| PROP | `POCKET_HARD_OBJECT` | `pav_52ad9703c71808d0f30da42f` | `MISSING` | `NOT_RUN` | 12 |
| PROP | `RED_FIBER` | `pav_3a08230c1458dedbb0f3d163` | `MISSING` | `NOT_RUN` | 13 |
| PROP | `RED_UMBRELLA` | `pav_a2d118eacdefcee61de9f439` | `MISSING` | `NOT_RUN` | 2, 6 |
| PROP | `TABLE_SCRATCH` | `pav_bec2092927a69686cb114beb` | `MISSING` | `NOT_RUN` | 12 |
| PROP | `TICKET` | `pav_2132524b070f72d5366fdad8` | `MISSING` | `NOT_RUN` | 1 |
| SCENE | `E01_SC001` | `pav_82614896978d97576aadc04f` | `MISSING` | `NOT_RUN` | 1, 2, 3, 4, 5, 6, 7, 8 |
| SCENE | `E01_SC002` | `pav_5dd54748863fe739182193a6` | `MISSING` | `NOT_RUN` | 9, 10, 11, 12, 13, 14, 15 |

## Excluded files

The checkout contains `book-990401` files, but none has an explicit structured mapping to one of the 15 entity IDs. They remain excluded under the no-fuzzy-matching rule; known canary/storyboard outputs are not valid Production Asset references.

## Required human action

Supply one explicit `entity_id → media_identity` mapping and readable media file for each missing entity. The media must be independently byte-checked before any ProductionAssetVersion/Authority/Pointer update.
