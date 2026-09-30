import { describe, expect, it } from 'vitest'
import { buildStoryboardSurfaceUrl, PRODUCTION_UI_V3_DEFAULT_MAX_SHOTS, readProductionUiV3Flag, resolveStoryboardSurface } from './productionUiV3SurfacePolicy'
import { productionWorkspaceV2Fixture } from '../fixtures/productionWorkspaceV2'

function snapshotWithShots(count: number) {
  const base = structuredClone(productionWorkspaceV2Fixture)
  base.shots = Array.from({ length: count }, (_, index) => ({
    ...base.shots[index % Math.max(1, productionWorkspaceV2Fixture.shots.length)],
    identity: { ...base.shots[index % Math.max(1, productionWorkspaceV2Fixture.shots.length)].identity, shot_id: String(index + 1), storyboard_shot_id: index + 1 },
  }))
  return base
}

const eligible = { v2State: 'ready' as const, snapshot: snapshotWithShots(2) }

describe('resolveStoryboardSurface', () => {
  it('defaults an eligible project to V3', () => expect(resolveStoryboardSurface(eligible)).toMatchObject({ surface: 'v3', reason: 'eligible_default', shotCount: 2 }))
  it.each([
    ['asset blocked', { asset_readiness: { state: 'blocked', current: false, required: {}, missing: ['CHARACTER:x'], stale: [] } }],
    ['model missing', { IMAGE: { ...eligible.snapshot.shots[0].IMAGE, model: { selected_profile_id: null } } }],
    ['review', { IMAGE: { ...eligible.snapshot.shots[0].IMAGE, candidates: { count: 1, latest: null, items: [] } } }],
    ['running', { IMAGE: { ...eligible.snapshot.shots[0].IMAGE, latest_execution: { state: 'RUNNING' } } }],
    ['stale', { asset_readiness: { state: 'stale', current: false, required: {}, missing: [], stale: ['CHARACTER:x'] } }],
  ])('keeps %s in V3', (_label, override) => {
    const snapshot = structuredClone(eligible.snapshot)
    snapshot.shots[0] = { ...snapshot.shots[0], ...override } as typeof snapshot.shots[0]
    expect(resolveStoryboardSurface({ ...eligible, snapshot }).surface).toBe('v3')
  })
  it('honors explicit overrides', () => {
    expect(resolveStoryboardSurface({ ...eligible, search: '?ui_v3=legacy' })).toMatchObject({ surface: 'legacy', reason: 'explicit_legacy', overridden: true })
    expect(resolveStoryboardSurface({ ...eligible, search: '?ui_v3=shot-studio' })).toMatchObject({ surface: 'v3', reason: 'explicit_v3', overridden: true })
  })
  it('hard disables every V3 path', () => {
    expect(resolveStoryboardSurface({ ...eligible, search: '?ui_v3=shot-studio', hardDisabled: true })).toMatchObject({ surface: 'legacy', reason: 'hard_disabled' })
  })
  it('supports the ordinary default rollback switch', () => {
    expect(resolveStoryboardSurface({ ...eligible, defaultEnabled: false })).toMatchObject({ surface: 'legacy', reason: 'default_disabled' })
    expect(resolveStoryboardSurface({ ...eligible, defaultEnabled: false, search: '?ui_v3=shot-studio' }).surface).toBe('v3')
  })
  it('holds a pending surface during V2 loading', () => expect(resolveStoryboardSurface({ ...eligible, v2State: 'loading', snapshot: null })).toMatchObject({ surface: 'pending', reason: 'v2_loading' }))
  it('falls back for unavailable or invalid V2 contracts', () => {
    expect(resolveStoryboardSurface({ ...eligible, v2State: 'unavailable', snapshot: null })).toMatchObject({ surface: 'legacy', reason: 'v2_unavailable' })
    expect(resolveStoryboardSurface({ ...eligible, snapshot: { ...eligible.snapshot, schema_version: 'wrong' } })).toMatchObject({ surface: 'legacy', reason: 'v2_contract_invalid' })
  })
  it('falls back for no shots, active generation, recovery, and legacy steps', () => {
    expect(resolveStoryboardSurface({ ...eligible, snapshot: snapshotWithShots(0) })).toMatchObject({ surface: 'legacy', reason: 'no_canonical_shots' })
    expect(resolveStoryboardSurface({ ...eligible, isGeneratingStoryboard: true })).toMatchObject({ surface: 'legacy', reason: 'storyboard_generation_running' })
    expect(resolveStoryboardSurface({ ...eligible, recoveryTarget: 'storyboard' })).toMatchObject({ surface: 'legacy', reason: 'legacy_recovery_context' })
    expect(resolveStoryboardSurface({ ...eligible, search: '?step=frame' })).toMatchObject({ surface: 'legacy', reason: 'legacy_step_deeplink' })
  })
  it('enforces the 100 shot default ceiling while retaining explicit V3 QA override', () => {
    expect(PRODUCTION_UI_V3_DEFAULT_MAX_SHOTS).toBe(100)
    expect(resolveStoryboardSurface({ ...eligible, snapshot: snapshotWithShots(100) }).surface).toBe('v3')
    expect(resolveStoryboardSurface({ ...eligible, snapshot: snapshotWithShots(101) })).toMatchObject({ surface: 'legacy', reason: 'rollout_shot_limit', shotCount: 101 })
    expect(resolveStoryboardSurface({ ...eligible, snapshot: snapshotWithShots(101), search: '?ui_v3=shot-studio' }).surface).toBe('v3')
  })
})

describe('buildStoryboardSurfaceUrl', () => {
  it('changes only ui_v3 and preserves context and unrelated params', () => {
    const legacy = new URLSearchParams(buildStoryboardSurfaceUrl('?section=storyboard&episode=1&shot=5&foo=bar&ui_v3=shot-studio', 'legacy'))
    expect(legacy.get('section')).toBe('storyboard')
    expect(legacy.get('episode')).toBe('1')
    expect(legacy.get('shot')).toBe('5')
    expect(legacy.get('foo')).toBe('bar')
    expect(legacy.get('ui_v3')).toBe('legacy')
    const v3 = new URLSearchParams(buildStoryboardSurfaceUrl(legacy.toString(), 'v3'))
    expect(v3.get('ui_v3')).toBe('shot-studio')
    expect(v3.get('shot')).toBe('5')
  })
})

describe('readProductionUiV3Flag', () => {
  it('defaults unset values to the requested fallback and parses common false values', () => {
    expect(readProductionUiV3Flag(undefined, true)).toBe(true)
    expect(readProductionUiV3Flag('0', true)).toBe(false)
    expect(readProductionUiV3Flag('false', true)).toBe(false)
    expect(readProductionUiV3Flag('1', false)).toBe(true)
  })
})
