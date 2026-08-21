import type { ScriptOutput } from '../domain/bookOutputs'
import { getScriptDecision, type ScriptDecisionMap } from './productWorkspaceScriptDecisions'
import { buildScriptReleaseSummary } from './productWorkspaceScriptRelease'

export interface QaReleaseGateSummary {
  totalScriptEpisodes: number
  unlockedEpisodes: number[]
  unreleasedEpisodes: number[]
  blockedEpisodes: number[]
  isBlocked: boolean
  summaryLabel: string
  detail: string
}

export function buildQaReleaseGateSummary(
  scripts: ScriptOutput[],
  scriptDecisionState: ScriptDecisionMap,
  hasLockedAdaptation: boolean,
): QaReleaseGateSummary {
  const scriptEpisodes = Array.from(
    new Set(
      scripts
        .filter((item) => item.content.trim())
        .map((item) => Number(item.episode))
        .filter((episode) => Number.isFinite(episode) && episode > 0),
    ),
  ).sort((left, right) => left - right)

  const unlockedEpisodes: number[] = []
  const unreleasedEpisodes: number[] = []

  for (const episode of scriptEpisodes) {
    const decision = getScriptDecision(scriptDecisionState, episode)
    const release = buildScriptReleaseSummary({
      hasLockedAdaptation,
      hasScript: true,
      scriptLocked: Boolean(decision.lockedAt),
      scriptReleased: Boolean(decision.releasedAt),
    })

    if (release.phase === 'pending_lock') {
      unlockedEpisodes.push(episode)
      continue
    }

    if (release.phase === 'pending_release') {
      unreleasedEpisodes.push(episode)
    }
  }

  const blockedEpisodes = [...unlockedEpisodes, ...unreleasedEpisodes]
  const isBlocked = !hasLockedAdaptation || blockedEpisodes.length > 0

  return {
    totalScriptEpisodes: scriptEpisodes.length,
    unlockedEpisodes,
    unreleasedEpisodes,
    blockedEpisodes,
    isBlocked,
    summaryLabel: isBlocked
      ? `上游未放行 ${Math.max(blockedEpisodes.length, hasLockedAdaptation ? 0 : 1)} 集`
      : scriptEpisodes.length > 0
        ? '剧本闸门已通过'
        : '暂无剧本集次',
    detail: isBlocked
      ? buildBlockedDetail(unlockedEpisodes, unreleasedEpisodes, hasLockedAdaptation)
      : scriptEpisodes.length > 0
        ? '当前已有剧本的集次都完成了锁稿和放行，QA 可以继续承担真正的验收闭环。'
        : '当前还没有可检查的正式剧本集次，QA 暂时只作为问题收敛面板。',
  }
}

function buildBlockedDetail(
  unlockedEpisodes: number[],
  unreleasedEpisodes: number[],
  hasLockedAdaptation: boolean,
) {
  const parts: string[] = []

  if (!hasLockedAdaptation) {
    parts.push('项目改编方向尚未正式锁定，当前只应保留历史问题复核，不应作为新的下游验收依据')
  }

  if (unlockedEpisodes.length > 0) {
    parts.push(`待锁稿：第 ${unlockedEpisodes.join('、')} 集`)
  }

  if (unreleasedEpisodes.length > 0) {
    parts.push(`待放行：第 ${unreleasedEpisodes.join('、')} 集`)
  }

  return `即使 QA 问题已修复，这些集次仍不应视为已通过下游验收。${parts.join('；')}。`
}
