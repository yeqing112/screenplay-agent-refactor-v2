# Phase J3 legacy provider path retirement

## Current decision

The canonical path is the production authority for new callers. The existing
storyboard frame and video endpoints remain available as a compatibility
surface for old clients that do not yet send `model_profile_id`.

When a profile id is present, those endpoints delegate to canonical preview and
execute. The bridge preserves the existing confirmation shape while the
canonical resolver owns media scope, PromptIR lineage, adapter binding,
credential lifecycle, idempotency and candidate persistence.

When a profile id is absent, the endpoint explicitly marks the response as
`legacy_compatibility_surface`; that branch is not counted as the J3 production
authority and is retained to avoid breaking old clients during migration.

## Retirement conditions

1. The formal workspace sends an explicit profile for every IMAGE and VIDEO
   request.
2. Existing clients have migrated from the no-profile storyboard endpoints.
3. The compatibility branch has zero production traffic for an agreed window.
4. A separate migration change removes the legacy queue path and its tests.

J3 does not claim that these conditions are complete. Real Provider execution
also remains independently authorization-gated and was not exercised here.
