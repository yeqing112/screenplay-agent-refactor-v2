import type { StoryboardShotOutput } from '../prototyping/sceneComposerData'
import { toDisplayText } from '../prototyping/sceneComposerData'

export type QaLayer = 'script' | 'storyboard' | 'asset' | 'video' | 'general'
export type QaSeverity = 'high' | 'medium' | 'low'
export type QaWorkflowStatus = 'open' | 'in_progress' | 'resolved' | 'wont_fix'
export type QaActionTarget = 'scripts' | 'storyboard' | 'assets'
export type QaWorkbenchFixStatus =
  | 'pending'
  | 'fixed'
  | 'fixing'
  | 'rechecking'
  | 'recheck_passed'
  | 'recheck_failed'
  | 'rolled_back'
export type QaLifecycleFilter = 'all' | QaWorkbenchFixStatus
export type QaIssueSortMode = 'status_priority' | 'updated_desc' | 'severity_desc' | 'episode_asc'

export interface QaRepairAction {
  id: string
  label: string
  target: QaActionTarget
  reason: string
}

export interface WorkspaceQaIssue {
  id: string
  episode: number
  layer: QaLayer
  severity: QaSeverity
  title: string
  detail: string
  shotId: string | null
  promptVersion: number | null
  assetLabel: string | null
  source: 'error' | 'suggestion'
  sourceKind?: 'derived' | 'workbench'
  workflowStatus?: QaWorkflowStatus | null
  rawFixStatus?: QaWorkbenchFixStatus | null
  repairVersion?: string | null
  note?: string | null
  sourceExcerpt?: string | null
  statusReason?: string | null
  ruleFamily?: string | null
  repairGoal?: string | null
  createdAt?: string | null
  updatedAt?: string | null
  recommendedActions: QaRepairAction[]
}

type QaEntry = {
  id?: number
  episode: number
  result: unknown
  error_count?: number
}

export interface QaSummaryStats {
  total: number
  open: number
  inProgress: number
  resolved: number
  wontFix: number
  byLayer: Record<QaLayer, number>
  bySeverity: Record<QaSeverity, number>
}

export function pickQaNavigationIssue(
  issues: WorkspaceQaIssue[],
  statuses: Record<string, QaWorkflowStatus>,
  target: { episode: number | null; shotId: string | null; qaFocus?: 'delivery_recovery' | null },
) {
  const targetEpisode = Number(target.episode ?? 0) || null
  const targetShotId = String(target.shotId ?? '').trim()
  const qaFocus = target.qaFocus ?? null
  const candidates = issues.filter((issue) => {
    if (targetEpisode && issue.episode !== targetEpisode) return false
    if (targetShotId && String(issue.shotId ?? '').trim() !== targetShotId) return false
    return true
  })

  if (candidates.length === 0) return null

  return [...candidates].sort((left, right) => {
    const leftStatus = statuses[left.id] ?? left.workflowStatus ?? 'open'
    const rightStatus = statuses[right.id] ?? right.workflowStatus ?? 'open'
    const leftRawFixStatus = left.rawFixStatus ?? null
    const rightRawFixStatus = right.rawFixStatus ?? null

    const leftActionable = isActionableQaNavigationIssue(leftStatus, leftRawFixStatus)
    const rightActionable = isActionableQaNavigationIssue(rightStatus, rightRawFixStatus)
    if (leftActionable !== rightActionable) return leftActionable ? -1 : 1

    if (qaFocus === 'delivery_recovery') {
      const leftDeliveryRank = deliveryRecoveryNavigationRank(left)
      const rightDeliveryRank = deliveryRecoveryNavigationRank(right)
      if (rightDeliveryRank !== leftDeliveryRank) return rightDeliveryRank - leftDeliveryRank
    }

    const leftWorkbench = left.sourceKind === 'workbench'
    const rightWorkbench = right.sourceKind === 'workbench'
    if (leftWorkbench !== rightWorkbench) return leftWorkbench ? -1 : 1

    const leftShotMatch = targetShotId && String(left.shotId ?? '').trim() === targetShotId
    const rightShotMatch = targetShotId && String(right.shotId ?? '').trim() === targetShotId
    if (leftShotMatch !== rightShotMatch) return leftShotMatch ? -1 : 1

    const severityGap = qaSeverityRank(right.severity) - qaSeverityRank(left.severity)
    if (severityGap !== 0) return severityGap

    const leftUpdated = Date.parse(left.updatedAt ?? left.createdAt ?? '') || 0
    const rightUpdated = Date.parse(right.updatedAt ?? right.createdAt ?? '') || 0
    if (rightUpdated !== leftUpdated) return rightUpdated - leftUpdated

    return left.id.localeCompare(right.id, 'zh-CN')
  })[0] ?? null
}

function deliveryRecoveryNavigationRank(issue: WorkspaceQaIssue) {
  let score = 0

  if (issue.layer === 'video') score += 80
  else if (issue.layer === 'asset') score += 70
  else if (issue.layer === 'storyboard') score += 60
  else if (issue.layer === 'general') score += 20

  if (issue.shotId) score += 25
  if (issue.assetLabel) score += 10
  if (issue.sourceKind === 'derived') score += 5

  return score
}

export function buildQaIssueRecords(
  qaEntries: QaEntry[],
  episodeShots: Record<number, StoryboardShotOutput[]>,
): WorkspaceQaIssue[] {
  return qaEntries.flatMap((entry, entryIndex) => buildIssuesFromEntry(entry, entryIndex, episodeShots))
}

export function buildQaSummaryStats(
  issues: WorkspaceQaIssue[],
  statuses: Record<string, QaWorkflowStatus>,
): QaSummaryStats {
  const byLayer: Record<QaLayer, number> = {
    script: 0,
    storyboard: 0,
    asset: 0,
    video: 0,
    general: 0,
  }
  const bySeverity: Record<QaSeverity, number> = {
    high: 0,
    medium: 0,
    low: 0,
  }

  let open = 0
  let inProgress = 0
  let resolved = 0
  let wontFix = 0

  for (const issue of issues) {
    byLayer[issue.layer] += 1
    bySeverity[issue.severity] += 1
    const workflow = statuses[issue.id] ?? issue.workflowStatus ?? 'open'
    if (workflow === 'open') {
      open += 1
    } else if (workflow === 'in_progress') {
      inProgress += 1
    } else if (workflow === 'resolved') {
      resolved += 1
    } else if (workflow === 'wont_fix') {
      wontFix += 1
    }
  }

  return {
    total: issues.length,
    open,
    inProgress,
    resolved,
    wontFix,
    byLayer,
    bySeverity,
  }
}

function buildIssuesFromEntry(
  entry: QaEntry,
  entryIndex: number,
  episodeShots: Record<number, StoryboardShotOutput[]>,
): WorkspaceQaIssue[] {
  const result = asRecord(entry.result)
  const issueCandidates: WorkspaceQaIssue[] = []
  const highErrors = normalizeIssueList(result.high_errors)
  const mediumErrors = normalizeIssueList(result.medium_errors ?? result.errors ?? result.issues)
  const suggestions = normalizeIssueList(result.suggestions)

  highErrors.forEach((rawIssue, issueIndex) => {
    issueCandidates.push(
      createIssueRecord({
        rawIssue,
        episode: entry.episode,
        severity: 'high',
        source: 'error',
        fallbackId: `qa-${entry.episode}-${entry.id ?? entryIndex}-high-${issueIndex}`,
        episodeShots,
      }),
    )
  })

  mediumErrors.forEach((rawIssue, issueIndex) => {
    issueCandidates.push(
      createIssueRecord({
        rawIssue,
        episode: entry.episode,
        severity: 'medium',
        source: 'error',
        fallbackId: `qa-${entry.episode}-${entry.id ?? entryIndex}-medium-${issueIndex}`,
        episodeShots,
      }),
    )
  })

  suggestions.forEach((rawIssue, issueIndex) => {
    issueCandidates.push(
      createIssueRecord({
        rawIssue,
        episode: entry.episode,
        severity: 'low',
        source: 'suggestion',
        fallbackId: `qa-${entry.episode}-${entry.id ?? entryIndex}-suggestion-${issueIndex}`,
        episodeShots,
      }),
    )
  })

  if (issueCandidates.length === 0 && Number(entry.error_count ?? 0) > 0) {
    issueCandidates.push(
      createIssueRecord({
        rawIssue: `第 ${entry.episode} 集存在 ${entry.error_count} 个待处理问题，但当前未返回结构化明细。`,
        episode: entry.episode,
        severity: 'medium',
        source: 'error',
        fallbackId: `qa-${entry.episode}-${entry.id ?? entryIndex}-summary`,
        episodeShots,
      }),
    )
  }

  return issueCandidates
}

function createIssueRecord({
  rawIssue,
  episode,
  severity,
  source,
  fallbackId,
  episodeShots,
}: {
  rawIssue: unknown
  episode: number
  severity: QaSeverity
  source: 'error' | 'suggestion'
  fallbackId: string
  episodeShots: Record<number, StoryboardShotOutput[]>
}): WorkspaceQaIssue {
  const issue = asRecord(rawIssue)
  const text = pickIssueText(rawIssue, issue)
  const shotId = extractShotId(rawIssue, issue)
  const promptVersion = extractPromptVersion(issue, episodeShots[episode] ?? [], shotId)
  const assetLabel = pickAssetLabel(issue)
  const layer = inferQaLayer(text, issue, shotId)

  return {
    id: String(issue.id ?? fallbackId),
    episode,
    layer,
    severity,
    title: buildIssueTitle(layer, severity, source, shotId, assetLabel),
    detail: text,
    shotId,
    promptVersion,
    assetLabel,
    source,
    sourceKind: 'derived',
    workflowStatus: null,
    rawFixStatus: null,
    repairVersion: '',
    note: '',
    sourceExcerpt: null,
    statusReason: null,
    ruleFamily: null,
    repairGoal: null,
    createdAt: null,
    updatedAt: null,
    recommendedActions: buildRecommendedActions(layer, shotId, source),
  }
}

export function buildQaIssueFromWorkbenchIssue(
  rawIssue: Record<string, unknown>,
  episodeShots: Record<number, StoryboardShotOutput[]>,
): WorkspaceQaIssue {
  const episode = Number(rawIssue.episode ?? 0) || 1
  const description = toDisplayText(firstString(rawIssue.description, rawIssue.suggestion, rawIssue.title), '')
  const metaInfo = asRecord(rawIssue.meta_info)
  const shotId = extractShotId(metaInfo.shot_id ?? metaInfo.shotId ?? rawIssue.location, asRecord(rawIssue.location))
  const assetLabel = pickAssetLabel(metaInfo)
  const layer = inferWorkbenchLayer(
    String(rawIssue.type ?? ''),
    String(rawIssue.title ?? ''),
    description,
    shotId,
  )

  return {
    id: String(rawIssue.issue_id ?? rawIssue.id ?? `workbench-${episode}-${Math.random()}`),
    episode,
    layer,
    severity: normalizeSeverity(String(rawIssue.severity ?? 'medium')),
    title: toDisplayText(firstString(rawIssue.title, rawIssue.type), 'QA 问题'),
    detail: description,
    shotId,
    promptVersion: extractPromptVersion(metaInfo, episodeShots[episode] ?? [], shotId),
    assetLabel,
    source: 'error',
    sourceKind: 'workbench',
    workflowStatus: normalizeWorkflowStatus(firstString(rawIssue.workflow_status)) ?? mapWorkbenchStatus(String(rawIssue.fix_status ?? 'pending')),
    rawFixStatus: normalizeWorkbenchFixStatus(firstString(rawIssue.fix_status)),
    repairVersion: toDisplayText(firstString(rawIssue.repair_version, metaInfo.repair_version), ''),
    note: toDisplayText(firstString(rawIssue.note, metaInfo.note), ''),
    sourceExcerpt: toDisplayText(firstString(rawIssue.source_excerpt), ''),
    statusReason: toDisplayText(firstString(rawIssue.status_reason), ''),
    ruleFamily: toDisplayText(firstString(rawIssue.rule_family, metaInfo.rule_family), ''),
    repairGoal: toDisplayText(firstString(rawIssue.repair_goal, metaInfo.repair_goal), ''),
    createdAt: toDisplayText(firstString(rawIssue.created_at), ''),
    updatedAt: toDisplayText(firstString(rawIssue.updated_at), ''),
    recommendedActions: buildRecommendedActions(layer, shotId, 'error'),
  }
}

export function normalizeWorkbenchFixStatus(value: string | null | undefined): QaWorkbenchFixStatus | null {
  const normalized = String(value ?? '').trim().toLowerCase()
  if (
    normalized === 'pending' ||
    normalized === 'fixed' ||
    normalized === 'fixing' ||
    normalized === 'rechecking' ||
    normalized === 'recheck_passed' ||
    normalized === 'recheck_failed' ||
    normalized === 'rolled_back'
  ) {
    return normalized as QaWorkbenchFixStatus
  }
  return null
}

export function qaLifecycleLabel(value: QaLifecycleFilter) {
  switch (value) {
    case 'pending':
      return '待同步'
    case 'fixed':
      return '已修复待复检'
    case 'fixing':
      return '修复执行中'
    case 'rechecking':
      return '复检中'
    case 'recheck_passed':
      return '复检通过'
    case 'recheck_failed':
      return '复检失败'
    case 'rolled_back':
      return '已回滚'
    default:
      return '全部阶段'
  }
}

export function matchesQaLifecycleFilter(issue: WorkspaceQaIssue, filter: QaLifecycleFilter) {
  if (filter === 'all') return true
  return issue.rawFixStatus === filter
}

function qaSeverityRank(value: QaSeverity) {
  if (value === 'high') return 3
  if (value === 'medium') return 2
  return 1
}

function isActionableQaNavigationIssue(
  workflowStatus: QaWorkflowStatus,
  rawFixStatus: QaWorkbenchFixStatus | null,
) {
  if (rawFixStatus && rawFixStatus !== 'recheck_passed' && rawFixStatus !== 'rolled_back') return true
  return workflowStatus === 'open' || workflowStatus === 'in_progress'
}

function qaWorkflowRank(value: QaWorkflowStatus) {
  if (value === 'open') return 4
  if (value === 'in_progress') return 3
  if (value === 'wont_fix') return 2
  return 1
}

function qaIssueUpdatedAt(issue: WorkspaceQaIssue) {
  return Date.parse(issue.updatedAt || issue.createdAt || '') || 0
}

export function sortQaIssues(
  issues: WorkspaceQaIssue[],
  statuses: Record<string, QaWorkflowStatus>,
  sortMode: QaIssueSortMode,
) {
  return [...issues].sort((left, right) => {
    const leftStatus = statuses[left.id] ?? left.workflowStatus ?? 'open'
    const rightStatus = statuses[right.id] ?? right.workflowStatus ?? 'open'

    if (sortMode === 'updated_desc') {
      return (
        qaIssueUpdatedAt(right) - qaIssueUpdatedAt(left) ||
        qaSeverityRank(right.severity) - qaSeverityRank(left.severity) ||
        left.episode - right.episode
      )
    }

    if (sortMode === 'severity_desc') {
      return (
        qaSeverityRank(right.severity) - qaSeverityRank(left.severity) ||
        qaWorkflowRank(rightStatus) - qaWorkflowRank(leftStatus) ||
        qaIssueUpdatedAt(right) - qaIssueUpdatedAt(left)
      )
    }

    if (sortMode === 'episode_asc') {
      return (
        left.episode - right.episode ||
        String(left.shotId ?? '').localeCompare(String(right.shotId ?? ''), 'zh-Hans-CN') ||
        qaSeverityRank(right.severity) - qaSeverityRank(left.severity)
      )
    }

    return (
      qaWorkflowRank(rightStatus) - qaWorkflowRank(leftStatus) ||
      qaSeverityRank(right.severity) - qaSeverityRank(left.severity) ||
      qaIssueUpdatedAt(right) - qaIssueUpdatedAt(left) ||
      left.episode - right.episode
    )
  })
}

function buildIssueTitle(
  layer: QaLayer,
  severity: QaSeverity,
  source: 'error' | 'suggestion',
  shotId: string | null,
  assetLabel: string | null,
) {
  const base = layer === 'script'
    ? '剧本问题'
    : layer === 'storyboard'
      ? '分镜问题'
      : layer === 'asset'
        ? '资产问题'
        : layer === 'video'
          ? '视频问题'
          : '通用问题'

  const suffix = shotId
    ? ` · 镜头 ${shotId}`
    : assetLabel
      ? ` · ${assetLabel}`
      : ''

  const tone = source === 'suggestion' ? '建议' : severity === 'high' ? '高优先级' : severity === 'medium' ? '处理中' : '优化项'
  return `${base}${suffix} · ${tone}`
}

function buildRecommendedActions(
  layer: QaLayer,
  shotId: string | null,
  source: 'error' | 'suggestion',
): QaRepairAction[] {
  const actions: QaRepairAction[] = []

  if (layer === 'script') {
    actions.push({
      id: 'open-script-workbench',
      label: '进入剧本工作台',
      target: 'scripts',
      reason: '回看该集脚本、场次和台词，再决定是否重写。',
    })
  }

  if (layer === 'storyboard') {
    actions.push({
      id: 'open-storyboard-workbench',
      label: shotId ? `定位镜头 ${shotId}` : '进入镜头工作台',
      target: 'storyboard',
      reason: '检查镜头意图、静态提示词、运动提示词和版本状态。',
    })
  }

  if (layer === 'asset') {
    actions.push({
      id: 'open-assets-center',
      label: '进入资产中心',
      target: 'assets',
      reason: '补参考图、核对定妆/场景/道具资产，确认引用是否正确。',
    })
  }

  if (layer === 'video') {
    actions.push({
      id: 'open-video-repair',
      label: shotId ? `回到镜头 ${shotId}` : '进入镜头工作台',
      target: 'storyboard',
      reason: '检查首帧、运动提示词和视频版本，准备重生或回测。',
    })
    actions.push({
      id: 'check-assets-before-video',
      label: '检查关联资产',
      target: 'assets',
      reason: '确认驱动视频生成的角色、场景和道具参考是否稳定。',
    })
  }

  if (layer === 'general') {
    actions.push({
      id: 'check-script-context',
      label: '检查剧本上下文',
      target: 'scripts',
      reason: '先确认上游脚本与改编方向是否稳定。',
    })
    actions.push({
      id: 'check-storyboard-context',
      label: '检查分镜上下文',
      target: 'storyboard',
      reason: '确认镜头拆解与提示词编译是否吸收了上游变更。',
    })
  }

  if (source === 'suggestion' && !actions.some((item) => item.target === 'scripts')) {
    actions.push({
      id: 'review-copy-or-rhythm',
      label: '回看上游文案',
      target: 'scripts',
      reason: '这是质量建议，优先回看剧本表达和节奏安排。',
    })
  }

  return dedupeActions(actions)
}

function dedupeActions(actions: QaRepairAction[]) {
  const seen = new Set<string>()
  return actions.filter((action) => {
    if (seen.has(action.id)) return false
    seen.add(action.id)
    return true
  })
}

function normalizeSeverity(value: string): QaSeverity {
  const normalized = value.trim().toLowerCase()
  if (normalized === 'high') return 'high'
  if (normalized === 'low') return 'low'
  return 'medium'
}

function mapWorkbenchStatus(value: string): QaWorkflowStatus {
  const normalized = value.trim().toLowerCase()
  if (normalized === 'fixing' || normalized === 'fixed' || normalized === 'rechecking') return 'in_progress'
  if (normalized === 'recheck_passed') return 'resolved'
  if (normalized === 'rolled_back') return 'open'
  if (normalized === 'wont_fix') return 'wont_fix'
  return 'open'
}

function normalizeWorkflowStatus(value: string | null) {
  const normalized = String(value ?? '').trim().toLowerCase()
  if (normalized === 'open' || normalized === 'in_progress' || normalized === 'resolved' || normalized === 'wont_fix') {
    return normalized as QaWorkflowStatus
  }
  return null
}

function inferWorkbenchLayer(type: string, title: string, description: string, shotId: string | null): QaLayer {
  const text = `${type} ${title} ${description}`.toLowerCase()
  if (text.includes('视频') || text.includes('运镜') || text.includes('motion')) return 'video'
  if (shotId || text.includes('分镜') || text.includes('镜头') || text.includes('提示词') || text.includes('画面')) return 'storyboard'
  if (text.includes('资产') || text.includes('定妆') || text.includes('场景资产') || text.includes('道具资产') || text.includes('参考图')) return 'asset'
  if (text.includes('台词') || text.includes('剧本') || text.includes('人物动机') || text.includes('剧情')) return 'script'
  return 'script'
}

function normalizeIssueList(value: unknown) {
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter((item) => item !== null && item !== undefined && String(item).trim() !== '')
}

function pickIssueText(rawIssue: unknown, issue: Record<string, unknown>) {
  if (typeof rawIssue === 'string') {
    return toDisplayText(rawIssue, rawIssue)
  }

  return (
    toDisplayText(firstString(
      issue.description,
      issue.message,
      issue.detail,
      issue.reason,
      issue.summary,
      issue.title,
      issue.name,
    ), '')
    || JSON.stringify(rawIssue)
  )
}

function pickAssetLabel(issue: Record<string, unknown>) {
  const value = firstString(
    issue.asset_name,
    issue.assetName,
    issue.character_name,
    issue.characterName,
    issue.location_name,
    issue.locationName,
    issue.prop_name,
    issue.propName,
  )
  return value ? toDisplayText(value, value) : null
}

function extractShotId(rawIssue: unknown, issue: Record<string, unknown>) {
  const explicit = firstString(
    issue.shot_id,
    issue.shotId,
    issue.storyboard_shot_id,
    issue.storyboardShotId,
  )
  if (explicit) {
    return explicit
  }

  const text = typeof rawIssue === 'string' ? rawIssue : JSON.stringify(rawIssue)
  const matched = text.match(/\b\d{1,3}-\d{1,3}\b/)
  return matched?.[0] ?? null
}

function extractPromptVersion(
  issue: Record<string, unknown>,
  shots: StoryboardShotOutput[],
  shotId: string | null,
) {
  const explicit = firstNumber(issue.prompt_version, issue.promptVersion)
  if (explicit !== null) {
    return explicit
  }

  if (!shotId) {
    return null
  }

  return shots.find((shot) => shot.shot_id === shotId)?.prompt_version ?? null
}

function inferQaLayer(
  text: string,
  issue: Record<string, unknown>,
  shotId: string | null,
): QaLayer {
  const explicitLayer = firstString(issue.layer, issue.kind, issue.category, issue.issue_type, issue.issueType)?.toLowerCase()
  if (explicitLayer?.includes('script') || explicitLayer?.includes('dialogue') || explicitLayer?.includes('story')) return 'script'
  if (explicitLayer?.includes('storyboard') || explicitLayer?.includes('shot') || explicitLayer?.includes('prompt')) return 'storyboard'
  if (explicitLayer?.includes('asset') || explicitLayer?.includes('character') || explicitLayer?.includes('location') || explicitLayer?.includes('prop')) return 'asset'
  if (explicitLayer?.includes('video') || explicitLayer?.includes('motion') || explicitLayer?.includes('frame')) return 'video'

  const haystack = `${text} ${JSON.stringify(issue)}`.toLowerCase()

  if (/(视频|镜头运动|运镜|运动提示词|动态提示词|motion|video|帧间|首帧|sequence)/i.test(haystack)) {
    return 'video'
  }
  if (/(角色|人物|场景|道具|定妆|服装|造型|reference|asset|character|location|prop)/i.test(haystack)) {
    return 'asset'
  }
  if (/(台词|对白|剧本|节奏|剧情|场次|独白|script|dialogue|screenplay|monologue)/i.test(haystack)) {
    return 'script'
  }
  if (shotId || /(分镜|镜头|提示词|构图|prompt|shot|storyboard|镜位)/i.test(haystack)) {
    return 'storyboard'
  }
  return 'general'
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {}
  }
  return value as Record<string, unknown>
}

function firstString(...values: unknown[]) {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value.trim()
    }
  }
  return null
}

function firstNumber(...values: unknown[]) {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value
    }
  }
  return null
}
