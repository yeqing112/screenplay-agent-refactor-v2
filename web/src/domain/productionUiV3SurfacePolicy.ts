import type { ProductionWorkspaceLoadState, ProductionWorkspaceV2Snapshot } from './productionWorkspace'

export const PRODUCTION_UI_V3_DEFAULT_MAX_SHOTS = 100

export type StoryboardSurface = 'v3' | 'legacy' | 'pending'

export type StoryboardSurfaceReason =
  | 'hard_disabled'
  | 'explicit_v3'
  | 'explicit_legacy'
  | 'default_disabled'
  | 'v2_loading'
  | 'v2_unavailable'
  | 'v2_contract_invalid'
  | 'legacy_recovery_context'
  | 'legacy_step_deeplink'
  | 'storyboard_generation_running'
  | 'no_canonical_shots'
  | 'rollout_shot_limit'
  | 'eligible_default'

export interface StoryboardSurfaceDecision {
  surface: StoryboardSurface
  reason: StoryboardSurfaceReason
  overridden: boolean
  shotCount: number
  maxShots: number
}

export interface StoryboardSurfaceInputs {
  search?: string
  v2State: ProductionWorkspaceLoadState
  snapshot: ProductionWorkspaceV2Snapshot | null
  recoveryTarget?: string | null
  isGeneratingStoryboard?: boolean
  defaultEnabled?: boolean
  hardDisabled?: boolean
  maxShots?: number
}

export type LegacyStoryboardMode = 'advanced_compatibility' | 'creation' | 'recovery' | 'full_fallback'

export interface LegacyStoryboardModeDecision {
  mode: LegacyStoryboardMode
  reason: StoryboardSurfaceReason | 'recovery_focus' | 'recovery_deeplink'
  canonicalGenerationVisible: boolean
  canonicalStatusVisible: boolean
  creationVisible: boolean
  recoveryVisible: boolean
  advancedToolsVisible: boolean
  v3ReturnVisible: boolean
}

export interface LegacyStoryboardModeInputs {
  /** The already resolved surface decision. Supplying it keeps this policy pure and deterministic. */
  surfaceDecision?: StoryboardSurfaceDecision | null
  /** Alias accepted for callers that use the shorter decision name. */
  decision?: StoryboardSurfaceDecision | null
  search?: string
  recoveryTarget?: string | null
  recoveryFocus?: { target?: string | null } | null
  snapshot?: ProductionWorkspaceV2Snapshot | null
}

function hasQuery(search: string, key: string, value: string) {
  return new URLSearchParams(search || '').get(key) === value
}

function hasStepDeepLink(search: string) {
  return new URLSearchParams(search || '').has('step')
}

export function isProductionWorkspaceV2ContractValid(snapshot: ProductionWorkspaceV2Snapshot | null): snapshot is ProductionWorkspaceV2Snapshot {
  return Boolean(
    snapshot &&
      snapshot.schema_version === 'production_workspace_projection_v2' &&
      snapshot.read_only === true &&
      snapshot.authority_source === 'current_authority_pointers_only',
  )
}

export function resolveStoryboardSurface({
  search = '',
  v2State,
  snapshot,
  recoveryTarget = null,
  isGeneratingStoryboard = false,
  defaultEnabled = true,
  hardDisabled = false,
  maxShots = PRODUCTION_UI_V3_DEFAULT_MAX_SHOTS,
}: StoryboardSurfaceInputs): StoryboardSurfaceDecision {
  const explicitV3 = hasQuery(search, 'ui_v3', 'shot-studio')
  const explicitLegacy = hasQuery(search, 'ui_v3', 'legacy')
  const safeMaxShots = Number.isFinite(maxShots) && maxShots > 0 ? Math.floor(maxShots) : PRODUCTION_UI_V3_DEFAULT_MAX_SHOTS
  const shotCount = Array.isArray(snapshot?.shots) ? snapshot.shots.length : 0
  const overridden = explicitV3 || explicitLegacy

  if (hardDisabled) return { surface: 'legacy', reason: 'hard_disabled', overridden: false, shotCount, maxShots: safeMaxShots }
  if (explicitLegacy) return { surface: 'legacy', reason: 'explicit_legacy', overridden: true, shotCount, maxShots: safeMaxShots }
  if (explicitV3) {
    if (v2State === 'loading') return { surface: 'pending', reason: 'v2_loading', overridden: true, shotCount, maxShots: safeMaxShots }
    return { surface: 'v3', reason: 'explicit_v3', overridden: true, shotCount, maxShots: safeMaxShots }
  }
  if (!defaultEnabled) return { surface: 'legacy', reason: 'default_disabled', overridden: false, shotCount, maxShots: safeMaxShots }
  if (isGeneratingStoryboard) return { surface: 'legacy', reason: 'storyboard_generation_running', overridden: false, shotCount, maxShots: safeMaxShots }
  if (recoveryTarget === 'storyboard') return { surface: 'legacy', reason: 'legacy_recovery_context', overridden: false, shotCount, maxShots: safeMaxShots }
  if (hasStepDeepLink(search)) return { surface: 'legacy', reason: 'legacy_step_deeplink', overridden: false, shotCount, maxShots: safeMaxShots }
  if (v2State === 'loading') return { surface: 'pending', reason: 'v2_loading', overridden: false, shotCount, maxShots: safeMaxShots }
  if (v2State === 'unavailable' || snapshot === null) return { surface: 'legacy', reason: 'v2_unavailable', overridden: false, shotCount, maxShots: safeMaxShots }
  if (!isProductionWorkspaceV2ContractValid(snapshot)) return { surface: 'legacy', reason: 'v2_contract_invalid', overridden: false, shotCount, maxShots: safeMaxShots }
  if (snapshot.shots.length === 0) return { surface: 'legacy', reason: 'no_canonical_shots', overridden: false, shotCount, maxShots: safeMaxShots }
  if (snapshot.shots.length > safeMaxShots) return { surface: 'legacy', reason: 'rollout_shot_limit', overridden: false, shotCount, maxShots: safeMaxShots }
  return { surface: 'v3', reason: 'eligible_default', overridden, shotCount, maxShots: safeMaxShots }
}

export function buildStoryboardSurfaceUrl(search: string, surface: 'v3' | 'legacy') {
  const params = new URLSearchParams(search || '')
  params.set('ui_v3', surface === 'v3' ? 'shot-studio' : 'legacy')
  const serialized = params.toString()
  return serialized ? `?${serialized}` : '?ui_v3=shot-studio'
}

/**
 * Build the explicit return link from a Legacy recovery/compatibility surface.
 * Legacy-only step state must not leak into the Shot Studio deep link, while
 * episode/shot and unrelated query context remain intact.
 */
export function buildStoryboardReturnToV3Url(search: string) {
  const params = new URLSearchParams(search || '')
  params.delete('step')
  params.set('ui_v3', 'shot-studio')
  const serialized = params.toString()
  return serialized ? `?${serialized}` : '?ui_v3=shot-studio'
}

function hasRecoveryDeepLink(search: string) {
  const params = new URLSearchParams(search || '')
  const step = params.get('step')
  if (step === 'frame' || step === 'video' || step === 'review') return true
  return ['recovery', 'recovery_task', 'recovery_task_id', 'task_id', 'focus'].some((key) => {
    const value = params.get(key)
    return Boolean(value && value !== 'false' && value !== '0')
  })
}

function legacyModeDecision(mode: LegacyStoryboardMode, reason: LegacyStoryboardModeDecision['reason']): LegacyStoryboardModeDecision {
  return {
    mode,
    reason,
    canonicalGenerationVisible: mode === 'full_fallback',
    canonicalStatusVisible: mode === 'full_fallback',
    creationVisible: mode === 'creation',
    recoveryVisible: mode === 'recovery' || mode === 'full_fallback',
    advancedToolsVisible: mode !== 'creation',
    v3ReturnVisible: mode === 'advanced_compatibility' || mode === 'recovery',
  }
}

/**
 * Decide how much of the Legacy storyboard surface should be exposed.
 * This is presentation policy only: it never changes generation capability,
 * source facts, recovery state, or the canonical production contract.
 */
export function resolveLegacyStoryboardMode({
  surfaceDecision: suppliedDecision,
  decision,
  search = '',
  recoveryTarget = null,
  recoveryFocus = null,
  snapshot = null,
}: LegacyStoryboardModeInputs): LegacyStoryboardModeDecision {
  const resolved = suppliedDecision ?? decision ?? null
  const shotCount = resolved?.shotCount ?? (snapshot ? (Array.isArray(snapshot.shots) ? snapshot.shots.length : 0) : null)
  const reason = resolved?.reason
  const hasRecoveryFocus = recoveryTarget === 'storyboard' || recoveryFocus?.target === 'storyboard'
  if (hasRecoveryFocus) return legacyModeDecision('recovery', 'recovery_focus')
  if (hasRecoveryDeepLink(search)) {
    const step = new URLSearchParams(search || '').get('step')
    return legacyModeDecision('recovery', step ? 'recovery_deeplink' : 'recovery_deeplink')
  }
  if (
    reason === 'hard_disabled' ||
    reason === 'default_disabled' ||
    reason === 'v2_unavailable' ||
    reason === 'v2_contract_invalid' ||
    reason === 'rollout_shot_limit' ||
    reason === 'storyboard_generation_running'
  ) {
    return legacyModeDecision('full_fallback', reason)
  }
  if (reason === 'no_canonical_shots' || shotCount === 0) return legacyModeDecision('creation', 'no_canonical_shots')
  if (reason === 'explicit_legacy' && resolved?.surface === 'legacy') {
    return legacyModeDecision('advanced_compatibility', reason)
  }
  // A standalone Legacy section or an unknown future reason should remain
  // operationally safe and expose the complete fallback surface.
  return legacyModeDecision('full_fallback', reason || 'v2_unavailable')
}

export function readProductionUiV3Flag(value: unknown, fallback: boolean) {
  if (value === undefined || value === null || value === '') return fallback
  return !['0', 'false', 'off', 'no'].includes(String(value).trim().toLowerCase())
}
