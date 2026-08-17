export interface ScriptDecisionState {
  lockedAt: string | null
  releasedAt: string | null
  note: string
}

export type ScriptDecisionMap = Record<string, ScriptDecisionState>

export function createEmptyScriptDecision(): ScriptDecisionState {
  return {
    lockedAt: null,
    releasedAt: null,
    note: '',
  }
}

export function normalizeScriptDecisionState(payload: unknown): ScriptDecisionMap {
  if (!payload || typeof payload !== 'object') return {}

  const episodes = (payload as {
    episodes?: Record<string, { locked_at?: string | null; released_at?: string | null; note?: string }>
  }).episodes

  if (!episodes || typeof episodes !== 'object') return {}

  return Object.fromEntries(
    Object.entries(episodes).map(([episode, value]) => [
      episode,
      {
        lockedAt: typeof value?.locked_at === 'string' ? value.locked_at : null,
        releasedAt: typeof value?.released_at === 'string' ? value.released_at : null,
        note: typeof value?.note === 'string' ? value.note : '',
      },
    ]),
  )
}

export function getScriptDecision(
  decisionState: ScriptDecisionMap,
  episode: number | null | undefined,
): ScriptDecisionState {
  if (!episode) {
    return createEmptyScriptDecision()
  }
  return decisionState[String(episode)] ?? createEmptyScriptDecision()
}

export function isScriptDecisionLocked(decision: ScriptDecisionState | null | undefined) {
  return Boolean(decision?.lockedAt)
}

export function isScriptDecisionReleased(decision: ScriptDecisionState | null | undefined) {
  return Boolean(decision?.releasedAt)
}
