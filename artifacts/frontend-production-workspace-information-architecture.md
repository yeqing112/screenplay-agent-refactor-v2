# Frontend Production Workspace Information Architecture

## Authority-first flow

The formal workspace keeps the existing `ProductWorkspace` shell and routes
all production-facing status through the read-only
`GET /api/books/{book_id}/production-workspace` projection. The projection is
not a second authority store: it resolves only current authority pointers and
returns blockers and navigation targets.

```text
Dashboard
  ├─ Production Spine
  ├─ Current blockers → exact section/episode/shot/asset
  ├─ Next action
  └─ Episode summaries

Content & Script
  └─ human-readable source + ScriptIR confirmation/stale state

Shot Workspace
  ├─ shot list / core action
  ├─ authority-aware blocker panel
  ├─ creative content and continuity
  └─ collapsed production detail (lineage/version)

Asset Center
  ├─ identity and production design
  ├─ current VisualAssetVersion
  ├─ reference candidate/selected/locked/stale
  └─ impacted shots and next action

Task Center
  ├─ Workflow Action (authority blockers)
  └─ Runtime Task (provider polling/recovery)

QA / Canvas / Delivery
  └─ consume projection for navigation; remain owners of their own views
```

## Human-readable state mapping

| Production state | UI label |
| --- | --- |
| `complete` | 已确认 |
| `ready` | 可以继续 |
| `in_progress` | 进行中 |
| `needs_action` | 待处理 |
| `blocked` | 暂不能继续 |
| `stale` | 需要更新 |
| `warning` | 需要注意 |
| `not_started` | 未开始 |

Raw reason codes remain available in advanced detail and audit logs, but are
never the primary user-facing copy.

## Compatibility policy

Creative-draft and legacy aggregate data remain available to existing sections.
They are not promoted to production truth. When a projection is unavailable,
the section may render its compatibility view, but production actions must
remain gated by the authoritative backend route.
