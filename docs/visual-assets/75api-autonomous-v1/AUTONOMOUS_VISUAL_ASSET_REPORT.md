# 75API Autonomous Character / Prop Real Canary

## Status

`AUTONOMOUS_VISUAL_ASSET_PIPELINE_PARTIAL`

## Production Provider Policy

- IMAGE: `75api-image / gpt-image-2-1k`
- VIDEO: `75api-minimax-h3 / minimax_h3_no_audios`
- Strict provider: `true`
- SHAPI/Poyo fallback: disabled

## 75API image preflight

- text_to_image: PASS
- image_to_image: PASS
- multi-reference: declared PASS; no derived call reached
- HTTPS reference: PASS
- data URI reference: PASS by contract; no derived call reached
- credential ready: PASS
- transport registered: PASS

## Lin Wan

- MASTER: 1 real 75API POST attempted
- Result: `SUBMISSION_AMBIGUOUS` after POST timeout
- Retry: blocked
- Derived views: not run
- Authority: not created

## Lu Shu / HANDBAG

Stopped by progressive canary after Lin Wan Stage A failed. No calls made.

## Scene E01_SC002

Existing `READY` SceneAuthority was preserved and not regenerated.

## Safety

- Real IMAGE calls: 1
- 75api IMAGE: 1
- SHAPI IMAGE: 0
- Poyo IMAGE: 0
- Real VIDEO calls: 0
- Production writes: 0
- Book 990400 writes: 0
- Browser direct Provider calls: 0
- Secret leaks: 0
- Orphans: 0
- Keyframes: 0

The timeout occurred after the 75API POST was sent, so the run was deliberately not retried and no alternate provider was used.

## Board hygiene

- Existing de83476 boards: `STALE_NON_AUTHORITATIVE_ARTIFACT`, moved to `historical-invalid-artifacts/de83476/`.
- Partial run publication: `NOT_PUBLISHED`.
- New run media: staged under `work/<run_id>/publish-staging/`; publication requires READY Authority and provenance.
- Character FACE framing: requested `1:1`.
- Character FULL framing: requested `2:3`, projected to provider `9:16` with recorded reason.
- Prop framing: `1:1`. Scene framing remains `16:9`.
