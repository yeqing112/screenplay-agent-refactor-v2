import type { ScriptOutput, StoryboardShotOutput } from '../domain/bookOutputs'
import { buildQaIssueFromWorkbenchIssue, type QaLayer } from './productWorkspaceQa'
import type { EpisodeProgress } from './productWorkspaceProgress'
import { getScriptDecision, type ScriptDecisionMap } from './productWorkspaceScriptDecisions'
import { buildScriptReleaseSummary } from './productWorkspaceScriptRelease'

export type ScriptReleaseStatus = 'done' | 'pending' | 'blocked'

export interface ScriptWorkbenchIssue {
  issue_id?: string
  episode?: number
  severity?: string
  type?: string
  title?: string
  description?: string
  suggestion?: string
  fix_status?: string
  status_reason?: string
  source_excerpt?: string
  location?: Record<string, unknown>
  meta_info?: Record<string, unknown>
}

export interface ScriptWorkbenchVersion {
  id?: number
  episode?: number
  version_no?: number
  label?: string
  change_type?: string
  change_reason?: string
  qa_issue_id?: string
  operator_name?: string
  diff_text?: string
  recheck_status?: string
  recheck_summary?: string
  created_at?: string | null
  updated_at?: string | null
}

export interface ScriptWorkbenchEpisode {
  episode?: number
  script_id?: number
  script_status?: string
  qa_summary?: {
    qa_result_id?: number | null
    overall_score?: number | null
    error_count?: number
    open_issue_count?: number
    suggestions?: unknown[]
  }
  issues?: ScriptWorkbenchIssue[]
  versions?: ScriptWorkbenchVersion[]
}

export interface ScriptWorkbenchResponse {
  episodes?: ScriptWorkbenchEpisode[]
}

export interface ScriptEpisodeSummary {
  episode: number
  scriptStatus: string
  progressLabel: string
  nextAction: string
  releaseStatus: ScriptReleaseStatus
  releaseLabel: string
  releaseReason: string
  versionCount: number
  totalIssueCount: number
  openIssueCount: number
  openScriptIssueCount: number
  openNonScriptIssueCount: number
  shotCount: number
  sceneCount: number
  overallScore: number | null
  scriptLength: number
}

export interface ScriptSceneSummary {
  index: number
  heading: string
  title: string
  timeLabel: string
  locationLabel: string
  characterLabel: string
  beatPreview: string
}

function isIssueOpen(status?: string) {
  const normalized = String(status ?? '').trim().toLowerCase()
  return normalized !== 'recheck_passed' && normalized !== 'resolved'
}

function toSingleLine(value: string) {
  return value.replace(/\s+/g, ' ').trim()
}

function extractField(block: string, label: string) {
  const pattern = new RegExp(`[-*]\\s*${label}[：:]\\s*(.+)`)
  const matched = block.match(pattern)
  return matched?.[1]?.trim() ?? ''
}

export function parseScriptScenes(content: string): ScriptSceneSummary[] {
  const normalized = String(content || '').replace(/\r\n/g, '\n')
  const headingRegex = /\*\*场景([一二三四五六七八九十百千万零\d]+)[：:]\s*\[([^\]]+)\]\*\*/g
  const matches = Array.from(normalized.matchAll(headingRegex))

  if (matches.length === 0) {
    return []
  }

  return matches.map((match, index) => {
    const start = match.index ?? 0
    const end = index + 1 < matches.length ? (matches[index + 1].index ?? normalized.length) : normalized.length
    const block = normalized.slice(start, end)
    const lines = block
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)

    const nonMetaLine =
      lines.find(
        (line) =>
          !line.startsWith('**场景') &&
          !/^[-*]\s*(时间|地点|人物)[：:]/.test(line) &&
          !/^---+$/.test(line),
      ) ?? ''

    return {
      index: index + 1,
      heading: match[0].replace(/\*\*/g, '').trim(),
      title: match[2]?.trim() ?? `场景 ${index + 1}`,
      timeLabel: extractField(block, '时间'),
      locationLabel: extractField(block, '地点'),
      characterLabel: extractField(block, '人物'),
      beatPreview: toSingleLine(nonMetaLine.replace(/^\*\*|\*\*$/g, '')),
    }
  })
}

function countIssuesByLayer(
  issues: ScriptWorkbenchIssue[],
  episode: number,
  shotsByEpisode: Record<number, StoryboardShotOutput[]>,
  layer: QaLayer,
) {
  return issues.filter((issue) => {
    const mapped = buildQaIssueFromWorkbenchIssue(
      {
        location: {},
        meta_info: {},
        ...issue,
      } as Record<string, unknown>,
      shotsByEpisode,
    )
    return mapped.episode === episode && mapped.layer === layer && isIssueOpen(issue.fix_status)
  }).length
}

export function buildScriptEpisodeSummaries(params: {
  scripts: ScriptOutput[]
  episodeProgress: EpisodeProgress[]
  qaWorkbench: ScriptWorkbenchResponse | null
  shotsByEpisode: Record<number, StoryboardShotOutput[]>
  scriptDecisionState: ScriptDecisionMap
  hasLockedAdaptation: boolean
}): ScriptEpisodeSummary[] {
  const workbenchByEpisode = new Map<number, ScriptWorkbenchEpisode>()
  for (const item of params.qaWorkbench?.episodes ?? []) {
    const episode = Number(item.episode ?? 0)
    if (episode > 0) {
      workbenchByEpisode.set(episode, item)
    }
  }

  const progressByEpisode = new Map(params.episodeProgress.map((item) => [item.episode, item]))
  const scriptByEpisode = new Map(params.scripts.map((item) => [item.episode, item]))
  const allEpisodes = Array.from(
    new Set([
      ...params.scripts.map((item) => item.episode),
      ...params.episodeProgress.map((item) => item.episode),
      ...Array.from(workbenchByEpisode.keys()),
    ]),
  ).sort((left, right) => left - right)

  return allEpisodes.map((episode) => {
    const script = scriptByEpisode.get(episode)
    const progress = progressByEpisode.get(episode)
    const workbench = workbenchByEpisode.get(episode)
    const issues = workbench?.issues ?? []
    const totalIssueCount = issues.length
    const openIssueCount = issues.filter((issue) => isIssueOpen(issue.fix_status)).length
    const openScriptIssueCount = countIssuesByLayer(issues, episode, params.shotsByEpisode, 'script')
    const openNonScriptIssueCount = Math.max(0, openIssueCount - openScriptIssueCount)
    const shotCount = params.shotsByEpisode[episode]?.length ?? 0
    const scriptContent = (script?.content ?? '').trim()
    const scriptLength = scriptContent.length
    const sceneCount = parseScriptScenes(scriptContent).length
    const scriptDecision = getScriptDecision(params.scriptDecisionState, episode)
    const release = buildScriptReleaseSummary({
      hasLockedAdaptation: params.hasLockedAdaptation,
      hasScript: scriptLength > 0,
      scriptLocked: Boolean(scriptDecision.lockedAt),
      scriptReleased: Boolean(scriptDecision.releasedAt),
      openScriptIssueCount,
      shotCount,
    })

    return {
      episode,
      scriptStatus: script?.status || workbench?.script_status || 'unknown',
      progressLabel: progress?.progressLabel ?? (scriptLength > 0 ? '已有正式剧本内容' : '尚未进入正式剧本阶段'),
      nextAction: release.phase === 'qa_blocked' ? release.nextAction : progress?.nextAction ?? release.nextAction,
      releaseStatus: release.uiStatus,
      releaseLabel: release.releaseLabel,
      releaseReason: release.releaseReason,
      versionCount: workbench?.versions?.length ?? 0,
      totalIssueCount,
      openIssueCount,
      openScriptIssueCount,
      openNonScriptIssueCount,
      shotCount,
      sceneCount,
      overallScore:
        typeof workbench?.qa_summary?.overall_score === 'number' ? workbench.qa_summary.overall_score : null,
      scriptLength,
    }
  })
}
