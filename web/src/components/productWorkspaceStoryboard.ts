import type { StoryboardShotOutput } from '../prototyping/sceneComposerData'
import { buildScriptReleaseSummary } from './productWorkspaceScriptRelease'

export interface ShotReadinessItem {
  label: string
  status: 'ready' | 'missing'
}

export interface ShotReadinessSummary {
  statusLabel: string
  blockerCount: number
  nextAction: string
  items: ShotReadinessItem[]
}

export interface ShotReferenceSummary {
  characterCount: number
  sceneCount: number
  propCount: number
  totalCount: number
}

export interface StoryboardGateSummary {
  status: 'ready' | 'blocked'
  tone: 'ready' | 'blocked'
  message: string
  actionsEnabled: boolean
}

export function hasDegradedPromptVersion(shot: StoryboardShotOutput) {
  return Boolean(shot.prompt_version_audit?.is_degraded_version)
}

function normalizeReferenceScope(scope: string | undefined) {
  const normalized = String(scope || '').trim().toLowerCase()
  if (normalized === 'scene' || normalized === 'location') return 'scene'
  if (normalized === 'character') return 'character'
  if (normalized === 'prop') return 'prop'
  return ''
}

export function summarizeShotReferences(shot: StoryboardShotOutput): ShotReferenceSummary {
  const lockedSummary = shot.locked_reference_summary?.all ?? []
  if (lockedSummary.length > 0) {
    let characterCount = 0
    let sceneCount = 0
    let propCount = 0

    lockedSummary.forEach((item) => {
      const scope = normalizeReferenceScope(item.scope)
      if (scope === 'character') characterCount += 1
      else if (scope === 'scene') sceneCount += 1
      else if (scope === 'prop') propCount += 1
    })

    return {
      characterCount,
      sceneCount,
      propCount,
      totalCount: characterCount + sceneCount + propCount,
    }
  }

  const referenceImages = shot.reference_images ?? []
  if (referenceImages.length > 0) {
    let characterCount = 0
    let sceneCount = 0
    let propCount = 0

    referenceImages.forEach((item) => {
      const scope = normalizeReferenceScope(item.asset_type)
      if (scope === 'character') characterCount += 1
      else if (scope === 'scene') sceneCount += 1
      else if (scope === 'prop') propCount += 1
    })

    return {
      characterCount,
      sceneCount,
      propCount,
      totalCount: characterCount + sceneCount + propCount,
    }
  }

  const characterCount = Object.values(shot.assets?.references?.characters ?? {}).reduce(
    (sum, items) => sum + items.length,
    0,
  )
  const sceneCount = shot.assets?.references?.scene?.length ?? 0
  const propCount = Object.values(shot.assets?.references?.props ?? {}).reduce(
    (sum, items) => sum + items.length,
    0,
  )

  return {
    characterCount,
    sceneCount,
    propCount,
    totalCount: characterCount + sceneCount + propCount,
  }
}

export function buildShotReadiness(shot: StoryboardShotOutput): ShotReadinessSummary {
  const refs = summarizeShotReferences(shot)
  const diagnosticStatus = String(shot.compiler_diagnostics?.status || '').trim().toLowerCase()
  const items: ShotReadinessItem[] = [
    {
      label: '参考资产',
      status: refs.totalCount > 0 ? 'ready' : 'missing',
    },
    {
      label: '静态提示词',
      status: shot.visual_prompt_static?.trim() ? 'ready' : 'missing',
    },
    {
      label: '运动提示词',
      status: shot.visual_prompt_motion?.trim() ? 'ready' : 'missing',
    },
    {
      label: '分镜图版本',
      status: (shot.assets?.images?.length ?? 0) > 0 ? 'ready' : 'missing',
    },
    {
      label: '视频版本',
      status: (shot.assets?.videos?.length ?? 0) > 0 ? 'ready' : 'missing',
    },
  ]

  const blockerCount = items.filter((item) => item.status === 'missing').length

  if (hasDegradedPromptVersion(shot)) {
    const recommendedRestoreVersion = shot.recommended_restore_version?.version
    return {
      statusLabel: '待恢复',
      blockerCount: Math.max(blockerCount, 1),
      nextAction:
        recommendedRestoreVersion !== null && recommendedRestoreVersion !== undefined
          ? `恢复推荐版本 v${String(recommendedRestoreVersion)}`
          : '前往镜头继续修复提示词',
      items,
    }
  }

  if (diagnosticStatus === 'blocked') {
    const firstMissing = items.find((item) => item.status === 'missing')?.label ?? '编译阻塞项'
    return {
      statusLabel: '阻塞',
      blockerCount,
      nextAction: `先处理${firstMissing}`,
      items,
    }
  }

  if (blockerCount === 0) {
    return {
      statusLabel: '可交付',
      blockerCount,
      nextAction: '进入 QA 或导出',
      items,
    }
  }

  const firstMissing = items.find((item) => item.status === 'missing')?.label ?? '待补齐项目'

  return {
    statusLabel: blockerCount >= 3 ? '阻塞' : '待补齐',
    blockerCount,
    nextAction: `先补齐${firstMissing}`,
    items,
  }
}

export function buildStoryboardGateSummary(input: {
  hasLockedAdaptation: boolean
  hasScript: boolean
  scriptLocked: boolean
  scriptReleased: boolean
}): StoryboardGateSummary {
  const release = buildScriptReleaseSummary({
    hasLockedAdaptation: input.hasLockedAdaptation,
    hasScript: input.hasScript,
    scriptLocked: input.scriptLocked,
    scriptReleased: input.scriptReleased,
  })

  if (release.canEnterStoryboard) {
    return {
      status: 'ready',
      tone: 'ready',
      message: '当前集剧本已完成锁稿和放行，可以继续进行提示词编译、出图和出视频。',
      actionsEnabled: true,
    }
  }

  if (release.phase === 'pending_release') {
    return {
      status: 'blocked',
      tone: 'blocked',
      message: '当前集剧本已锁稿，但还没有完成“放行到分镜”，请先回剧本工作台补齐放行决策。',
      actionsEnabled: false,
    }
  }

  if (release.phase === 'missing_adaptation') {
    return {
      status: 'blocked',
      tone: 'blocked',
      message:
        '项目改编方向尚未正式锁定。即使历史上已经生成过镜头或曾放行到下游，当前也只应做只读复核，不应继续新的提示词编译、出图或出视频。',
      actionsEnabled: false,
    }
  }

  if (release.phase === 'pending_lock') {
    return {
      status: 'blocked',
      tone: 'blocked',
      message: '当前集剧本还没有锁稿，镜头工作台先提供只读检查，暂不建议继续编译和出图。',
      actionsEnabled: false,
    }
  }

  if (release.phase === 'missing_script') {
    return {
      status: 'blocked',
      tone: 'blocked',
      message: '当前集还没有正式剧本，镜头工作台暂时只提供只读查看。',
      actionsEnabled: false,
    }
  }

  return {
    status: 'blocked',
    tone: 'blocked',
    message: '当前上游条件未满足，暂不建议继续镜头生产。',
    actionsEnabled: false,
  }
}
