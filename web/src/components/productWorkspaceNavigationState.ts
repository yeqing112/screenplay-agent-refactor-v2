import type { CanvasNavigationTarget } from './productWorkspaceSectionContracts'
import type { WorkspaceSection } from './productWorkspaceAssetViewController'

type PersistedWorkspaceSection = WorkspaceSection

interface PersistedProductWorkspaceNavigationState {
  section: PersistedWorkspaceSection
  canvasNavigationTarget: CanvasNavigationTarget | null
}

export function getProductWorkspaceNavigationStateStorageKey(bookId: number) {
  return `product-workspace.navigation-state.${bookId}`
}

function normalizeText(value: unknown) {
  const normalized = String(value ?? '').trim()
  return normalized || null
}

function normalizeEpisode(value: unknown) {
  const numeric = Number(value ?? 0)
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null
}

export function sanitizeCanvasNavigationTarget(value: unknown): CanvasNavigationTarget | null {
  if (!value || typeof value !== 'object') return null
  const target = value as Record<string, unknown>
  const recoveryKind = target.recoveryKind
  const recoveryIntent = target.recoveryIntent

  return {
    episode: normalizeEpisode(target.episode),
    shotId: normalizeText(target.shotId),
    assetId: normalizeText(target.assetId),
    assetLabel: normalizeText(target.assetLabel),
    taskId: normalizeText(target.taskId),
    recoveryKind:
      recoveryKind === 'frame' || recoveryKind === 'video' || recoveryKind === 'reference' || recoveryKind === 'prompt'
        ? recoveryKind
        : null,
    recoveryIntent:
      recoveryIntent === 'reference' || recoveryIntent === 'shot_variant_refinement' ? recoveryIntent : null,
  }
}

export function readProductWorkspaceNavigationState(bookId: number): PersistedProductWorkspaceNavigationState | null {
  if (typeof window === 'undefined' || !window.localStorage) return null
  try {
    const raw = window.localStorage.getItem(getProductWorkspaceNavigationStateStorageKey(bookId))
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<PersistedProductWorkspaceNavigationState> | null
    if (!parsed || parsed.section !== 'canvas') return null
    return {
      section: 'canvas',
      canvasNavigationTarget: sanitizeCanvasNavigationTarget(parsed.canvasNavigationTarget),
    }
  } catch {
    return null
  }
}

export function writeProductWorkspaceNavigationState(
  bookId: number,
  state: PersistedProductWorkspaceNavigationState | null,
) {
  if (typeof window === 'undefined' || !window.localStorage) return
  const key = getProductWorkspaceNavigationStateStorageKey(bookId)
  if (!state || state.section !== 'canvas' || !state.canvasNavigationTarget) {
    window.localStorage.removeItem(key)
    return
  }
  window.localStorage.setItem(
    key,
    JSON.stringify({
      section: 'canvas',
      canvasNavigationTarget: sanitizeCanvasNavigationTarget(state.canvasNavigationTarget),
    }),
  )
}
