# Stage 0 Baseline: Storyboard Production Refactor

## Scope

This baseline maps the current codepath for:

- script -> storyboard
- visual assets -> storyboard context
- storyboard -> generated image/video results
- version adoption -> `book outputs` -> frontend `SceneComposer`

It is meant to anchor the phase roadmap in the pasted brief, with backward compatibility as the main constraint.

## Current Data Model

### `StoryboardShot`

Current storyboard persistence already carries most of the production-facing fields:

- identity: `book_id`, `episode`, `scene_name`, `shot_id`
- shot grammar: `duration`, `camera_angle`, `camera_movement`, `transition`, `lighting`
- narrative timing: `dialogue`, `start_state`, `action_process`, `end_state`
- prompts: `visual_prompt_static`, `visual_prompt_motion`, `visual_prompt_final`
- asset hub: `asset_links`, `asset_status`
- extension bucket: `meta_info`, `notes`

Important constraint:

- `asset_links` is the compatibility center. It already stores generated `images`, `videos`, `audios`, and nested `references`.
- Existing generation and adoption flows mutate only `asset_links` plus `asset_status`.

### Visual asset tables

Existing visual assets are split across:

- `CharacterProfile`: long-lived character portrait/profile data
- `VisualMakeup`: episode-level character appearance refinement
- `VisualLocation`: reusable location descriptions and prompts
- `VisualProp`: reusable prop descriptions and prompts
- `VisualEraSpec`: book-level era/style envelope

What these models already provide:

- prompt text fields for character/location/prop context
- episode usage or shot usage fields such as `episodes` and `shot_ids`
- enough text detail to seed structured asset records later

What they do not yet provide:

- no shared asset status field like `draft` / `ref_ready` / `locked`
- no unified reference-image table
- no explicit stable asset reference handle like `jimeng_ref_name`
- no shot-level structured bindings for scene/character/prop selection

## Current Backend Flow

### 1. Script to storyboard

`/api/pipeline/storyboard` runs `StoryboardAgent`.

Current agent behavior:

- loads script for a book/episode
- splits scenes from script or falls back to `VisualLocation`
- generates shot rows with text prompts
- rewrites all shots for that episode
- backfills `shot_ids` onto `VisualMakeup`, `VisualLocation`, and `VisualProp`

This means the current storyboard is regenerated as a whole and is not yet modeled as a partially locked structured plan.

### 2. Visual assets into storyboard context

Today, asset relationships are mostly indirect:

- `VisualLocation` is matched by `scene_name`
- `VisualMakeup` is matched by `episode + character_name`
- `VisualProp` is matched by prop name and later by `shot_ids`

The system already uses those links for:

- building storyboard context during generation
- backfilling `shot_ids`
- determining which shots receive a reference asset when a reference image is generated

### 3. Generated media persistence

Current generation endpoints:

- `/api/prototyping/generate-image`
- `/api/prototyping/generate-reference-image`
- `/api/prototyping/generate-video`
- `/api/prototyping/adopt-version`

Persistence behavior:

- shot images/videos are appended into `StoryboardShot.asset_links.images` or `.videos`
- reference images are written into `StoryboardShot.asset_links.references`
- adopting a version flips only one item in a group to `adopted=true`
- image generation moves `asset_status` to `asset_ready`
- video generation moves `asset_status` to `done`

Important constraint:

- There is no separate result/version table yet; versions live inside shot JSON.

### 4. Aggregation to frontend

`/api/pipeline/book/{book_id}/outputs` is the main aggregation endpoint.

It returns:

- scripts
- storyboard rows
- visual assets
- QA results
- sanitized `asset_links`

Frontend normalization in `web/src/prototyping/sceneComposerData.ts` already expects:

- `asset_links.images/videos/audios`
- `asset_links.references.scene`
- `asset_links.references.characters`
- `asset_links.references.props`

This means frontend compatibility is already organized around the current `asset_links` schema, not around normalized relational tables.

## Current Frontend Behavior

The current production UI already has important pieces of the roadmap in rough form:

- production overview and gap checking
- shot state tracking
- reference assets as first-class UI nodes
- version adoption
- failure/retry workflow

But the shot model is still mostly prompt-and-version oriented, not structure-first:

- no explicit shot scene binding field beyond `scene_name`
- no explicit selected character asset list
- no explicit selected prop asset list
- no structured blocking/stance/action beat editor

## Reuse vs New Fields

### Fields we should reuse

- `StoryboardShot.scene_name`
- `StoryboardShot.visual_prompt_static`
- `StoryboardShot.visual_prompt_motion`
- `StoryboardShot.visual_prompt_final`
- `StoryboardShot.asset_links`
- `StoryboardShot.asset_status`
- `StoryboardShot.meta_info`
- `VisualMakeup.shot_ids`
- `VisualLocation.shot_ids`
- `VisualProp.shot_ids`

### Fields likely to add first

Prefer additive fields over replacing current ones:

- asset-level:
  - `jimeng_ref_name`
  - `negative_prompt`
  - `asset_status`
- shot-level structured payloads:
  - bound scene asset id
  - bound character asset ids
  - bound prop asset ids
  - character blocking / pose / emotion rows
  - action beat rows

### Best place for first incremental additions

Safest order in this repo:

1. add new nullable columns to `VisualLocation`, `VisualProp`, `VisualMakeup`, and possibly `CharacterProfile`
2. add a dedicated reference asset table
3. store early shot-structure payloads in `StoryboardShot.meta_info` first
4. only introduce dedicated shot-structure tables once the UI and compiler contract stabilizes

Reason:

- `meta_info` and `asset_links` already act as tolerated extension points
- existing outputs, tests, and frontend normalization are resilient to additive JSON
- replacing current shot persistence too early would create avoidable regression risk

## Compatibility Constraints

### Must preserve

- old `book outputs` consumers must still receive legacy storyboard prompt fields
- old shots with empty `asset_links` must still render
- `SceneComposer` must continue to read generated versions from `asset_links`
- generation persistence tests around model registry and creative task persistence must keep passing

### Do not do in phase 1

- do not replace `Book` as the project root
- do not directly wire a new external provider-specific API contract into core persistence
- do not rewrite `SceneComposer` around a brand-new data source
- do not remove prompt fields in favor of only structured shot data

## Actual Current Data Flow

The current end-to-end flow is:

1. `Script` stores episode script text.
2. `StoryboardAgent` generates `StoryboardShot` rows with prompt fields.
3. `StoryboardAgent` backfills `shot_ids` onto visual asset rows.
4. Reference image generation uses visual asset linkage to fan a reference asset out to related shots.
5. Shot image/video generation appends media versions into `StoryboardShot.asset_links`.
6. Adoption flips one version to `adopted=true`.
7. `book outputs` returns storyboard rows plus visual assets plus sanitized asset links.
8. Frontend normalizes that payload into `SceneComposer` view models.

## Smallest Safe Stage 1 Slice

The smallest useful implementation slice for this repo is:

1. Add asset status/reference fields to `VisualLocation`, `VisualProp`, and `VisualMakeup`.
2. Introduce a normalized reference asset table for `character` / `scene` / `prop`.
3. Expose read/write APIs for those asset fields and reference assets.
4. Keep mirroring selected reference assets into `StoryboardShot.asset_links.references` for frontend compatibility.

This gives us:

- persistent, queryable visual assets
- locked/reference-ready semantics
- minimal disruption to current generation/adoption flows
- a base for stage 2 prompt compiler work without breaking existing UI

## Recommendation

Implement stage 1 as a compatibility-first data-layer expansion, not a rewrite:

- relational source of truth for asset metadata and references
- `asset_links.references` retained as the runtime compatibility projection
- structured shot editing postponed until the asset contract is stable
