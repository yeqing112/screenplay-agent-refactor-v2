import { buildScriptReleaseSummary } from './productWorkspaceScriptRelease'

export interface DashboardSummaryInput {
  contentReady: boolean
  adaptationLocked: boolean
  episodesWithScripts: number
  scriptReleasePendingCount: number
  totalShots: number
  visualCount: number
  qaCount: number
}

export interface DashboardAction {
  title: string
  description: string
  targetSection: 'content' | 'adaptation' | 'scripts' | 'storyboard' | 'assets' | 'qa' | 'delivery'
  priority: 'high' | 'medium' | 'low'
}

export interface EpisodeProgressInput {
  episode: number
  hasLockedAdaptation?: boolean
  hasScript: boolean
  scriptLocked: boolean
  scriptReleased: boolean
  openScriptIssueCount?: number
  shotCount: number
  imageCount: number
  videoCount: number
  qaCount: number
}

export interface EpisodeProgress {
  episode: number
  statusLabel: string
  progressLabel: string
  blockerCount: number
  nextAction: string
}

export interface ScriptWorkbenchChecklist {
  name: string
  status: 'done' | 'pending' | 'blocked'
}

export function buildDashboardActions(input: DashboardSummaryInput): DashboardAction[] {
  if (!input.contentReady) {
    return [
      {
        title: '\u5148\u5b8c\u6210\u5185\u5bb9\u51c6\u5907',
        description: '\u4ece\u957f\u7bc7\u4e0a\u4f20\u6216\u77ed\u7bc7\u5f55\u5165\u5f00\u59cb\uff0c\u5148\u628a\u539f\u59cb\u5185\u5bb9\u5bfc\u5165\u6b63\u5f0f\u94fe\u8def\u3002',
        targetSection: 'content',
        priority: 'high',
      },
    ]
  }

  if (!input.adaptationLocked) {
    return [
      {
        title: '\u9501\u5b9a\u6539\u7f16\u65b9\u5411',
        description: '\u5148\u786e\u8ba4\u9879\u76ee\u7ea7\u4e3b\u65b9\u5411\uff0c\u518d\u63a8\u8fdb\u5267\u672c\u548c\u5206\u955c\uff0c\u907f\u514d\u540e\u7eed\u98ce\u683c\u6f02\u79fb\u3002',
        targetSection: 'adaptation',
        priority: 'high',
      },
    ]
  }

  if (input.episodesWithScripts === 0) {
    return [
      {
        title: '\u8865\u9f50\u5206\u96c6\u5267\u672c',
        description: '\u5f53\u524d\u8fd8\u6ca1\u6709\u6b63\u5f0f\u5267\u672c\u8f93\u51fa\uff0c\u5148\u8fdb\u5165\u5267\u672c\u5de5\u4f5c\u53f0\u786e\u8ba4\u5206\u96c6\u5185\u5bb9\u3002',
        targetSection: 'scripts',
        priority: 'high',
      },
    ]
  }

  if (input.scriptReleasePendingCount > 0) {
    return [
      {
        title: '\u8865\u9f50\u5267\u672c\u9501\u7a3f\u4e0e\u653e\u884c',
        description: `\u5f53\u524d\u4ecd\u6709 ${input.scriptReleasePendingCount} \u96c6\u5267\u672c\u8fd8\u6ca1\u6709\u5b8c\u6210\u9501\u7a3f\u6216\u653e\u884c\uff0c\u5efa\u8bae\u5148\u56de\u5267\u672c\u5de5\u4f5c\u53f0\u8865\u9f50\u4e0a\u6e38\u51b3\u7b56\u3002`,
        targetSection: 'scripts',
        priority: 'high',
      },
    ]
  }

  if (input.totalShots === 0) {
    return [
      {
        title: '\u8fdb\u5165\u955c\u5934\u5de5\u4f5c\u53f0',
        description: '\u5267\u672c\u5df2\u7ecf\u51c6\u5907\u597d\uff0c\u4e0b\u4e00\u6b65\u5e94\u8be5\u751f\u6210\u955c\u5934\u5217\u8868\u5e76\u5f00\u59cb\u5206\u955c\u7f16\u8bd1\u3002',
        targetSection: 'storyboard',
        priority: 'high',
      },
    ]
  }

  if (input.visualCount === 0) {
    return [
      {
        title: '\u8865\u9f50\u89c6\u89c9\u8d44\u4ea7',
        description: '\u5f53\u524d\u5df2\u6709\u5267\u672c\u548c\u5206\u955c\uff0c\u4f46\u8d44\u4ea7\u4e2d\u5fc3\u8fd8\u6ca1\u6709\u8db3\u591f\u7684\u4eba\u7269\u3001\u573a\u666f\u3001\u9053\u5177\u8d44\u4ea7\u3002',
        targetSection: 'assets',
        priority: 'medium',
      },
    ]
  }

  if (input.qaCount > 0) {
    return [
      {
        title: '\u5904\u7406 QA \u963b\u585e',
        description: '\u5df2\u6709\u53ef\u89c1\u95ee\u9898\u79ef\u538b\uff0c\u5efa\u8bae\u5148\u8fdb\u5165 QA \u4fee\u590d\u5de5\u4f5c\u53f0\u5904\u7406\u963b\u585e\u9879\u3002',
        targetSection: 'qa',
        priority: 'medium',
      },
    ]
  }

  return [
    {
      title: '\u51c6\u5907\u5bfc\u51fa\u4ea4\u4ed8',
      description: '\u4e3b\u94fe\u8def\u5df2\u7ecf\u57fa\u672c\u9f50\u5907\uff0c\u53ef\u4ee5\u5f00\u59cb\u505a\u5bfc\u51fa\u524d\u68c0\u67e5\u548c\u4ea4\u4ed8\u5305\u6574\u7406\u3002',
      targetSection: 'delivery',
      priority: 'low',
    },
  ]
}

export function buildEpisodeProgress(items: EpisodeProgressInput[]): EpisodeProgress[] {
  return items
    .map((item) => {
      const release = buildScriptReleaseSummary({
        hasLockedAdaptation: item.hasLockedAdaptation,
        hasScript: item.hasScript,
        scriptLocked: item.scriptLocked,
        scriptReleased: item.scriptReleased,
        openScriptIssueCount: item.openScriptIssueCount,
        shotCount: item.shotCount,
      })

      const blockerCount =
        (item.hasScript ? 0 : 1) +
        (item.scriptLocked ? 0 : 1) +
        (item.scriptReleased ? 0 : 1) +
        (item.shotCount > 0 ? 0 : 1) +
        (item.imageCount > 0 ? 0 : 1) +
        (item.videoCount > 0 ? 0 : 1) +
        (item.qaCount > 0 ? 1 : 0)

      if (release.phase === 'missing_adaptation') {
        return {
          episode: item.episode,
          statusLabel: '\u7f3a\u6539\u7f16\u65b9\u5411',
          progressLabel: '\u9879\u76ee\u4e3b\u65b9\u5411\u8fd8\u6ca1\u6709\u9501\u5b9a\uff0c\u6682\u4e0d\u5e94\u7ee7\u7eed\u4e0b\u6e38\u751f\u4ea7',
          blockerCount,
          nextAction: release.nextAction,
        }
      }

      if (release.phase === 'missing_script') {
        return {
          episode: item.episode,
          statusLabel: '\u5f85\u5267\u672c',
          progressLabel: '\u5c1a\u672a\u8fdb\u5165\u6b63\u5f0f\u5267\u672c\u9636\u6bb5',
          blockerCount,
          nextAction: release.nextAction,
        }
      }

      if (release.phase === 'pending_lock') {
        return {
          episode: item.episode,
          statusLabel: '\u5f85\u9501\u7a3f',
          progressLabel:
            item.shotCount > 0
              ? '\u955c\u5934\u5df2\u5b58\u5728\uff0c\u5efa\u8bae\u56de\u586b\u5267\u672c\u9501\u7a3f\u51b3\u7b56'
              : '\u5267\u672c\u5df2\u751f\u6210\uff0c\u5f85\u786e\u8ba4\u9501\u7a3f',
          blockerCount,
          nextAction: release.nextAction,
        }
      }

      if (release.phase === 'qa_blocked') {
        return {
          episode: item.episode,
          statusLabel: '\u811a\u672c\u5f85\u4fee\u590d',
          progressLabel: release.releaseReason,
          blockerCount,
          nextAction: release.nextAction,
        }
      }

      if (release.phase === 'pending_release') {
        return {
          episode: item.episode,
          statusLabel: '\u5f85\u653e\u884c',
          progressLabel:
            item.shotCount > 0
              ? '\u955c\u5934\u5df2\u5b58\u5728\uff0c\u5efa\u8bae\u8865\u8bb0\u5267\u672c\u653e\u884c\u72b6\u6001'
              : '\u5267\u672c\u5df2\u9501\u7a3f\uff0c\u5f85\u653e\u884c\u5230\u5206\u955c',
          blockerCount,
          nextAction: release.nextAction,
        }
      }

      if (item.shotCount === 0) {
        return {
          episode: item.episode,
          statusLabel: '\u5f85\u5206\u955c',
          progressLabel: '\u5df2\u6709\u5267\u672c\uff0c\u5f85\u751f\u6210\u955c\u5934',
          blockerCount,
          nextAction: '\u751f\u6210\u955c\u5934\u5217\u8868',
        }
      }

      if (item.imageCount === 0) {
        return {
          episode: item.episode,
          statusLabel: '\u5f85\u51fa\u56fe',
          progressLabel: `\u5df2\u6709 ${item.shotCount} \u955c\uff0c\u5f85\u751f\u6210\u5206\u955c\u56fe\u7247`,
          blockerCount,
          nextAction: '\u7f16\u8bd1\u63d0\u793a\u8bcd\u5e76\u51fa\u56fe',
        }
      }

      if (item.videoCount === 0) {
        return {
          episode: item.episode,
          statusLabel: '\u5f85\u89c6\u9891',
          progressLabel: `\u56fe\u7248\u5df2\u6709 ${item.imageCount} \u4e2a\uff0c\u5f85\u751f\u6210\u89c6\u9891`,
          blockerCount,
          nextAction: '\u751f\u6210\u89c6\u9891\u7248\u672c',
        }
      }

      if (item.qaCount > 0) {
        return {
          episode: item.episode,
          statusLabel: '\u5f85\u4fee\u590d',
          progressLabel: `\u5df2\u6709\u89c6\u9891\u4ea7\u51fa\uff0c\u4f46\u4ecd\u6709 ${item.qaCount} \u4e2a QA \u95ee\u9898`,
          blockerCount,
          nextAction: '\u5904\u7406 QA \u95ee\u9898',
        }
      }

      return {
        episode: item.episode,
        statusLabel: '\u53ef\u4ea4\u4ed8',
        progressLabel: '\u5267\u672c\u3001\u5206\u955c\u3001\u56fe\u7248\u3001\u89c6\u9891\u90fd\u5df2\u5177\u5907',
        blockerCount,
        nextAction: '\u8fdb\u5165\u5bfc\u51fa\u4e2d\u5fc3',
      }
    })
    .sort((left, right) => left.episode - right.episode)
}

export function buildScriptWorkbenchChecklist(params: {
  hasLockedAdaptation: boolean
  hasScript: boolean
  qaCount: number
}): ScriptWorkbenchChecklist[] {
  return [
    {
      name: '\u9879\u76ee\u6539\u7f16\u65b9\u5411\u5df2\u9501\u5b9a',
      status: params.hasLockedAdaptation ? 'done' : 'blocked',
    },
    {
      name: '\u5206\u96c6\u5267\u672c\u5df2\u751f\u6210',
      status: params.hasScript ? 'done' : 'pending',
    },
    {
      name: '\u811a\u672c QA \u5df2\u6e05\u7a7a',
      status: params.qaCount > 0 ? 'blocked' : params.hasScript ? 'pending' : 'pending',
    },
    {
      name: '\u5141\u8bb8\u8fdb\u5165\u955c\u5934\u5de5\u4f5c\u53f0',
      status: params.hasLockedAdaptation && params.hasScript && params.qaCount === 0 ? 'done' : 'pending',
    },
  ]
}
