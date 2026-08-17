export type ScriptReleaseUiStatus = 'done' | 'pending' | 'blocked'

export type ScriptReleasePhase =
  | 'missing_adaptation'
  | 'missing_script'
  | 'pending_lock'
  | 'qa_blocked'
  | 'pending_release'
  | 'ready_for_storyboard'
  | 'in_storyboard'

export interface ScriptReleaseSummary {
  phase: ScriptReleasePhase
  uiStatus: ScriptReleaseUiStatus
  releaseLabel: string
  releaseReason: string
  scriptStatusLabel: string
  nextAction: string
  canEnterStoryboard: boolean
  blocksDelivery: boolean
  pendingDecision: boolean
}

interface Params {
  hasLockedAdaptation?: boolean
  hasScript: boolean
  scriptLocked: boolean
  scriptReleased: boolean
  openScriptIssueCount?: number
  shotCount?: number
}

export function buildScriptReleaseSummary(params: Params): ScriptReleaseSummary {
  const hasLockedAdaptation = params.hasLockedAdaptation ?? true
  const openScriptIssueCount = params.openScriptIssueCount ?? 0
  const shotCount = params.shotCount ?? 0

  if (!hasLockedAdaptation) {
    return {
      phase: 'missing_adaptation',
      uiStatus: 'blocked',
      releaseLabel: '缺改编方向',
      releaseReason: '项目主方向还没有锁定，当前不应继续放行剧本。',
      scriptStatusLabel: '缺改编方向',
      nextAction: '先锁定项目改编方向',
      canEnterStoryboard: false,
      blocksDelivery: true,
      pendingDecision: true,
    }
  }

  if (!params.hasScript) {
    return {
      phase: 'missing_script',
      uiStatus: 'blocked',
      releaseLabel: '缺正式剧本',
      releaseReason: '这一集还没有可用的正式剧本内容。',
      scriptStatusLabel: '无剧本',
      nextAction: '先补齐分集剧本',
      canEnterStoryboard: false,
      blocksDelivery: true,
      pendingDecision: true,
    }
  }

  if (!params.scriptLocked) {
    return {
      phase: 'pending_lock',
      uiStatus: 'pending',
      releaseLabel: '待锁稿',
      releaseReason: '剧本已生成，但还没有完成锁稿确认。',
      scriptStatusLabel: '待锁稿',
      nextAction: '回剧本工作台确认锁稿',
      canEnterStoryboard: false,
      blocksDelivery: true,
      pendingDecision: true,
    }
  }

  if (openScriptIssueCount > 0) {
    return {
      phase: 'qa_blocked',
      uiStatus: 'blocked',
      releaseLabel: '脚本 QA 未清',
      releaseReason: `仍有 ${openScriptIssueCount} 条脚本层开放问题，需要先处理再放行。`,
      scriptStatusLabel: '脚本 QA 未清',
      nextAction: '优先处理脚本 QA',
      canEnterStoryboard: false,
      blocksDelivery: true,
      pendingDecision: true,
    }
  }

  if (!params.scriptReleased) {
    return {
      phase: 'pending_release',
      uiStatus: 'pending',
      releaseLabel: '待放行',
      releaseReason: '剧本已锁稿，待放行到分镜。',
      scriptStatusLabel: '待放行',
      nextAction: '回剧本工作台放行到分镜',
      canEnterStoryboard: false,
      blocksDelivery: true,
      pendingDecision: true,
    }
  }

  if (shotCount === 0) {
    return {
      phase: 'ready_for_storyboard',
      uiStatus: 'done',
      releaseLabel: '可进分镜',
      releaseReason: '剧本层检查已满足，下一步可进入镜头工作台生成和编排镜头。',
      scriptStatusLabel: '已锁稿并放行',
      nextAction: '生成镜头列表',
      canEnterStoryboard: true,
      blocksDelivery: false,
      pendingDecision: false,
    }
  }

  return {
    phase: 'in_storyboard',
    uiStatus: 'done',
    releaseLabel: '已进分镜',
    releaseReason: `这一集已经生成 ${shotCount} 个镜头，后续以镜头工作台为主。`,
    scriptStatusLabel: '已锁稿并放行',
    nextAction: '继续推进镜头生产',
    canEnterStoryboard: true,
    blocksDelivery: false,
    pendingDecision: false,
  }
}
