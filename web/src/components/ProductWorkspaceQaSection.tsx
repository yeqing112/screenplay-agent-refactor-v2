import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ScriptOutput, StoryboardShotOutput } from '../domain/bookOutputs'
import {
  buildQaIssueFromWorkbenchIssue,
  buildQaIssueRecords,
  pickQaNavigationIssue,
  buildQaSummaryStats,
  matchesQaLifecycleFilter,
  qaLifecycleLabel,
  sortQaIssues,
  type QaActionTarget,
  type QaIssueSortMode,
  type QaLifecycleFilter,
  type QaLayer,
  type QaWorkflowStatus,
} from './productWorkspaceQa'
import type { CanvasHandoffTarget } from './productWorkspaceSectionContracts'
import type { ScriptDecisionMap } from './productWorkspaceScriptDecisions'
import { buildQaReleaseGateSummary } from './productWorkspaceQaReadiness'
import { ProductWorkspaceQaDecisionPanel } from './ProductWorkspaceQaDecisionPanel'

type WorkspaceSection = 'scripts' | 'storyboard' | 'assets'

type QaEntry = {
  id?: number
  episode: number
  result: unknown
  error_count?: number
}

type QaWorkbenchIssue = {
  issue_id?: string
  episode?: number
  severity?: string
  type?: string
  title?: string
  description?: string
  suggestion?: string
  fix_status?: string
  fix_mode?: string
  workflow_status?: string
  repair_version?: string
  note?: string
  status_reason?: string
  source_excerpt?: string
  location?: Record<string, unknown>
  meta_info?: Record<string, unknown>
}

type QaWorkbenchEpisode = {
  episode?: number
  issues?: QaWorkbenchIssue[]
  versions?: QaWorkbenchScriptVersion[]
}

type QaWorkbenchResponse = {
  episodes?: QaWorkbenchEpisode[]
}

type QaFixOption = {
  id?: string
  title?: string
  summary?: string
  strategy?: string
  patched_text?: string
  risk?: string
}

type QaWorkbenchActionState = {
  mode: 'idle' | 'loading' | 'success' | 'error'
  action: 'generate' | 'preview' | 'apply' | 'autofix' | 'recheck' | 'rollback' | null
  message: string
  options: QaFixOption[]
  diffText: string
}

type QaPreviewPayload = {
  patched_text?: string
  diff_text?: string
}

type QaWorkbenchScriptVersion = {
  id?: number
  version_no?: number
  label?: string
  change_type?: string
  change_reason?: string
  operator_name?: string
  diff_text?: string
  recheck_status?: string
  recheck_summary?: string
  created_at?: string | null
}

type QaPendingRollback = {
  episode: number
  versionId: number
  versionLabel: string
} | null

type QaCanvasPrimaryActionPlan =
  | { action: 'scripts_gate'; label: string; detail: string }
  | { action: 'generate_fix'; label: string; detail: string }
  | { action: 'autofix'; label: string; detail: string }
  | { action: 'recheck'; label: string; detail: string }
  | { action: 'navigate'; label: string; detail: string; target: QaActionTarget }

type QaFollowupPollTarget = {
  issueId: string
  episode: number
  action: 'autofix' | 'recheck'
}

type QaRepairSyncState = {
  mode: 'idle' | 'saving' | 'saved' | 'error'
  message: string
}

type PersistedQaRepairState = Record<
  string,
  {
    status: QaWorkflowStatus
    repairVersion: string
    note: string
  }
>

interface Props {
  bookId: number
  scripts: ScriptOutput[]
  scriptDecisionState: ScriptDecisionMap
  hasExplicitLockedAdaptation: boolean
  qaEntries: QaEntry[]
  shotsByEpisode: Record<number, StoryboardShotOutput[]>
  qaNavigationTarget?: { episode: number | null; shotId: string | null; qaFocus?: 'delivery_recovery' | null } | null
  canvasHandoff?: CanvasHandoffTarget | null
  onNavigate: (section: WorkspaceSection) => void
  onSelectShot: (shotId: string) => void
}

export function buildQaCanvasHandoffSummary(input: {
  handoff?: CanvasHandoffTarget | null
  issue?: {
    title?: string | null
    episode?: number | null
    shotId?: string | null
    assetLabel?: string | null
  } | null
}) {
  const handoff = input.handoff
  if (!handoff) return null

  const issue = input.issue
  const episode = typeof issue?.episode === 'number' && Number.isFinite(issue.episode) ? issue.episode : handoff.episode ?? null
  const shotId = String(issue?.shotId ?? handoff.shotId ?? '').trim() || null
  const assetLabel = String(issue?.assetLabel ?? handoff.assetLabel ?? '').trim() || null

  const contextParts: string[] = []
  if (typeof episode === 'number' && Number.isFinite(episode)) contextParts.push(`第 ${episode} 集`)
  if (shotId) contextParts.push(`镜头 ${shotId}`)
  if (assetLabel) contextParts.push(assetLabel)

  return {
    title: contextParts.length > 0 ? `已从创作画布定位到 ${contextParts.join(' / ')}` : '已从创作画布定位到当前 QA 上下文',
    issueTitle: String(issue?.title ?? '').trim() || null,
    detail:
      handoff.handoffDetail ||
      '当前问题已经根据创作画布上下文自动定位，你可以直接在这里继续确认原因、执行修复动作并回收结果。',
  }
}

export function buildQaCanvasPrimaryActionPlan(input: {
  hasReleaseGateBlock: boolean
  issue: {
    sourceKind?: 'derived' | 'workbench'
    workflowStatus?: QaWorkflowStatus | null
    rawFixStatus?: string | null
    recommendedActions: Array<{ label: string; reason: string; target: QaActionTarget }>
  } | null
  actionState?: {
    action: QaWorkbenchActionState['action']
    options: QaFixOption[]
    diffText: string
  } | null
}) {
  if (!input.issue) return null

  if (input.hasReleaseGateBlock) {
    return {
      action: 'scripts_gate',
      label: '返回剧本工作台补放行',
      detail: '当前 QA 仍被上游剧本放行状态拦住，先补齐锁稿与放行，再继续本条问题的修复闭环。',
    } satisfies QaCanvasPrimaryActionPlan
  }

  const issue = input.issue
  const rawFixStatus = String(issue.rawFixStatus ?? '').trim().toLowerCase()
  const workflowStatus = issue.workflowStatus ?? 'open'
  const actionState = input.actionState

  if (issue.sourceKind === 'workbench') {
    if (rawFixStatus === 'fixed' || rawFixStatus === 'rechecking') {
      return {
        action: 'recheck',
        label: '触发复检',
        detail: '当前工单已经进入待复检阶段，先把 QA 复检跑完，再决定是否继续修或放行。',
      } satisfies QaCanvasPrimaryActionPlan
    }

    if (actionState?.action === 'generate' && (actionState.options.length > 0 || actionState.diffText.trim())) {
      return {
        action: 'autofix',
        label: '自动修复',
        detail: '修复方案已经回流到当前问题，下一步可以直接执行自动修复并等待 QA 复检。',
      } satisfies QaCanvasPrimaryActionPlan
    }

    if (
      workflowStatus === 'open' ||
      workflowStatus === 'in_progress' ||
      rawFixStatus === 'pending' ||
      rawFixStatus === 'recheck_failed' ||
      rawFixStatus === 'rolled_back'
    ) {
      return {
        action: 'generate_fix',
        label: '生成修复方案',
        detail: '先为这条真实 QA 工单生成修复方案，收敛处理方向后再执行自动修复或人工回改。',
      } satisfies QaCanvasPrimaryActionPlan
    }
  }

  const primaryRecommendedAction = issue.recommendedActions[0]
  if (primaryRecommendedAction) {
    return {
      action: 'navigate',
      label: primaryRecommendedAction.label,
      detail: primaryRecommendedAction.reason,
      target: primaryRecommendedAction.target,
    } satisfies QaCanvasPrimaryActionPlan
  }

  return {
    action: 'navigate',
    label: '回剧本工作台复核',
    detail: '当前问题已经没有更具体的自动动作，先回到上游内容与镜头上下文继续确认。',
    target: 'scripts',
  } satisfies QaCanvasPrimaryActionPlan
}

const LAYER_OPTIONS: Array<{ value: 'all' | QaLayer; label: string }> = [
  { value: 'all', label: '全部层级' },
  { value: 'script', label: '剧本 QA' },
  { value: 'storyboard', label: '分镜 QA' },
  { value: 'asset', label: '资产 QA' },
  { value: 'video', label: '视频 QA' },
  { value: 'general', label: '通用 QA' },
]

const STATUS_OPTIONS: Array<{ value: 'all' | QaWorkflowStatus; label: string }> = [
  { value: 'all', label: '全部状态' },
  { value: 'open', label: '待处理' },
  { value: 'in_progress', label: '修复中' },
  { value: 'resolved', label: '已解决' },
  { value: 'wont_fix', label: '不修复' },
]

const LIFECYCLE_OPTIONS: Array<{ value: QaLifecycleFilter; label: string }> = [
  { value: 'all', label: '全部阶段' },
  { value: 'pending', label: '待同步' },
  { value: 'fixed', label: '已修复待复检' },
  { value: 'fixing', label: '修复执行中' },
  { value: 'rechecking', label: '复检中' },
  { value: 'recheck_passed', label: '复检通过' },
  { value: 'recheck_failed', label: '复检失败' },
  { value: 'rolled_back', label: '已回滚' },
]

const SORT_OPTIONS: Array<{ value: QaIssueSortMode; label: string }> = [
  { value: 'status_priority', label: '按待处理优先' },
  { value: 'updated_desc', label: '最近更新' },
  { value: 'severity_desc', label: '严重级优先' },
  { value: 'episode_asc', label: '按集次与镜头' },
]

function qaRepairStorageKey(bookId: number) {
  return `product-workspace:qa-repair:${bookId}`
}

function readQaRepairState(bookId: number): PersistedQaRepairState {
  if (bookId <= 0 || typeof window === 'undefined') {
    return {}
  }

  try {
    const raw = window.localStorage.getItem(qaRepairStorageKey(bookId))
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function persistQaRepairState(bookId: number, state: PersistedQaRepairState) {
  if (bookId <= 0 || typeof window === 'undefined') {
    return
  }
  window.localStorage.setItem(qaRepairStorageKey(bookId), JSON.stringify(state))
}

function severityTone(severity: string) {
  switch (severity) {
    case 'high':
      return 'border-rose-500/30 bg-rose-500/10 text-rose-200'
    case 'medium':
      return 'border-amber-500/30 bg-amber-500/10 text-amber-200'
    default:
      return 'border-sky-500/30 bg-sky-500/10 text-sky-200'
  }
}

function statusTone(status: QaWorkflowStatus) {
  switch (status) {
    case 'resolved':
      return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
    case 'in_progress':
      return 'border-violet-500/30 bg-violet-500/10 text-violet-200'
    case 'wont_fix':
      return 'border-slate-600 bg-slate-800 text-slate-300'
    default:
      return 'border-amber-500/30 bg-amber-500/10 text-amber-200'
  }
}

function layerLabel(layer: QaLayer) {
  switch (layer) {
    case 'script':
      return '剧本'
    case 'storyboard':
      return '分镜'
    case 'asset':
      return '资产'
    case 'video':
      return '视频'
    default:
      return '通用'
  }
}

function statusLabel(status: QaWorkflowStatus) {
  switch (status) {
    case 'in_progress':
      return '修复中'
    case 'resolved':
      return '已解决'
    case 'wont_fix':
      return '不修复'
    default:
      return '待处理'
  }
}

function isHumanReview(issue: { statusReason?: string | null; status_reason?: string; meta_info?: Record<string, unknown> }): boolean {
  const meta = (issue.meta_info || {}) as Record<string, unknown>;
  return meta.routing === 'human' || meta.human_review_required === true || String(issue.statusReason || issue.status_reason || '').includes('人工定稿')
}

function lifecycleTone(rawStatus: QaLifecycleFilter) {
  switch (rawStatus) {
    case 'recheck_passed':
      return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
    case 'recheck_failed':
      return 'border-rose-500/30 bg-rose-500/10 text-rose-200'
    case 'rechecking':
    case 'fixing':
      return 'border-violet-500/30 bg-violet-500/10 text-violet-200'
    case 'fixed':
      return 'border-sky-500/30 bg-sky-500/10 text-sky-200'
    case 'rolled_back':
      return 'border-slate-600 bg-slate-800 text-slate-300'
    case 'pending':
      return 'border-amber-500/30 bg-amber-500/10 text-amber-200'
    default:
      return 'border-slate-700 text-slate-300'
  }
}

function workflowActionLabel(status: QaWorkflowStatus) {
  switch (status) {
    case 'in_progress':
      return '标记修复中'
    case 'resolved':
      return '标记已解决'
    case 'wont_fix':
      return '标记不修复'
    default:
      return '标记待处理'
  }
}

function scriptVersionTone(status: string | undefined) {
  const normalized = String(status ?? '').trim().toLowerCase()
  if (normalized === 'passed' || normalized === 'recheck_passed') {
    return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
  }
  if (normalized === 'failed' || normalized === 'recheck_failed') {
    return 'border-rose-500/30 bg-rose-500/10 text-rose-200'
  }
  if (normalized === 'running' || normalized === 'rechecking') {
    return 'border-violet-500/30 bg-violet-500/10 text-violet-200'
  }
  return 'border-slate-700 text-slate-300'
}

function targetToSection(target: QaActionTarget): WorkspaceSection {
  if (target === 'scripts') return 'scripts'
  if (target === 'assets') return 'assets'
  return 'storyboard'
}

export function findRawWorkbenchIssue(payload: QaWorkbenchResponse | null, issueId: string) {
  for (const episode of payload?.episodes ?? []) {
    for (const issue of episode.issues ?? []) {
      if (String(issue.issue_id ?? '') === issueId) {
        return issue
      }
    }
  }
  return null
}

export function countEpisodePendingIssues(payload: QaWorkbenchResponse | null, episodeNumber: number) {
  const episode = (payload?.episodes ?? []).find((item) => Number(item.episode ?? 0) === episodeNumber)
  if (!episode) {
    return 0
  }
  return (episode.issues ?? []).filter((issue) => String(issue.fix_status ?? '').toLowerCase() !== 'recheck_passed').length
}

export function buildFollowupOutcomeMessage(
  action: 'autofix' | 'recheck',
  issue: QaWorkbenchIssue | null,
  pendingIssueCount: number,
) {
  const normalizedStatus = String(issue?.fix_status ?? '').trim().toLowerCase()
  if (action === 'autofix') {
    if (normalizedStatus === 'recheck_passed') {
      return { mode: 'success' as const, message: '自动修复已完成，QA 复检通过。' }
    }
    if (normalizedStatus === 'recheck_failed') {
      return { mode: 'error' as const, message: '自动修复已完成，但 QA 复检未通过，请继续处理。' }
    }
    if (normalizedStatus) {
      return { mode: 'success' as const, message: `自动修复流程已收敛，当前状态：${normalizedStatus}。` }
    }
    return { mode: 'success' as const, message: '自动修复流程已结束，最新状态已同步。' }
  }

  if (pendingIssueCount <= 0) {
    return { mode: 'success' as const, message: '该集 QA 复检已通过，当前没有待处理问题。' }
  }
  return { mode: 'error' as const, message: `该集 QA 复检已完成，当前仍有 ${pendingIssueCount} 个问题待处理。` }
}

export default function ProductWorkspaceQaSection({
  bookId,
  scripts,
  scriptDecisionState,
  hasExplicitLockedAdaptation,
  qaEntries,
  shotsByEpisode,
  qaNavigationTarget,
  canvasHandoff,
  onNavigate,
  onSelectShot,
}: Props) {
  const [layerFilter, setLayerFilter] = useState<'all' | QaLayer>('all')
  // QA is a work queue first.  Historical resolved records remain available
  // through the status filter, but must not bury the next repair action.
  const [statusFilter, setStatusFilter] = useState<'all' | QaWorkflowStatus>('open')
  const [lifecycleFilter, setLifecycleFilter] = useState<QaLifecycleFilter>('all')
  const [episodeFilter, setEpisodeFilter] = useState<'all' | number>('all')
  const [sortMode, setSortMode] = useState<QaIssueSortMode>('status_priority')
  const [shotFilter, setShotFilter] = useState('')
  const [repairState, setRepairState] = useState<PersistedQaRepairState>({})
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(null)
  const [qaWorkbench, setQaWorkbench] = useState<QaWorkbenchResponse | null>(null)
  const [qaWorkbenchState, setQaWorkbenchState] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle')
  const [actionStateByIssue, setActionStateByIssue] = useState<Record<string, QaWorkbenchActionState>>({})
  const [repairSyncStateByIssue, setRepairSyncStateByIssue] = useState<Record<string, QaRepairSyncState>>({})
  const [qaFollowupPollTarget, setQaFollowupPollTarget] = useState<QaFollowupPollTarget | null>(null)
  const [patchDraftByIssue, setPatchDraftByIssue] = useState<Record<string, string>>({})
  const [selectedOptionByIssue, setSelectedOptionByIssue] = useState<Record<string, string>>({})
  const [previewByIssue, setPreviewByIssue] = useState<Record<string, QaPreviewPayload>>({})
  const [pendingRollback, setPendingRollback] = useState<QaPendingRollback>(null)

  const issues = useMemo(() => {
    const derivedIssues = buildQaIssueRecords(qaEntries, shotsByEpisode)
    const workbenchIssues = (qaWorkbench?.episodes ?? []).flatMap((episode) =>
      (episode.issues ?? []).map((issue) => buildQaIssueFromWorkbenchIssue(issue as Record<string, unknown>, shotsByEpisode)),
    )

    if (workbenchIssues.length === 0) {
      return derivedIssues
    }

    const workbenchDetailSet = new Set(
      workbenchIssues.map((issue) => `${issue.episode}::${issue.detail.trim().toLowerCase()}`),
    )
    const nonDuplicatedDerivedIssues = derivedIssues.filter((issue) => {
      if (issue.layer === 'script') return false
      if (!issue.shotId) return false
      const detailKey = `${issue.episode}::${issue.detail.trim().toLowerCase()}`
      return !workbenchDetailSet.has(detailKey)
    })
    return [...workbenchIssues, ...nonDuplicatedDerivedIssues]
  }, [qaEntries, qaWorkbench, shotsByEpisode])

  const workbenchIssueCount = useMemo(
    () => issues.filter((issue) => issue.sourceKind === 'workbench').length,
    [issues],
  )

  const derivedIssueCount = useMemo(
    () => issues.filter((issue) => issue.sourceKind !== 'workbench').length,
    [issues],
  )
  const stats = useMemo(
    () =>
      buildQaSummaryStats(
        issues,
        Object.fromEntries(
          Object.entries(repairState).map(([issueId, value]) => [issueId, value.status]),
        ),
      ),
    [issues, repairState],
  )
  const releaseGateSummary = useMemo(
    () => buildQaReleaseGateSummary(scripts, scriptDecisionState, hasExplicitLockedAdaptation),
    [hasExplicitLockedAdaptation, scriptDecisionState, scripts],
  )

  const episodeOptions = useMemo(
    () => Array.from(new Set(issues.map((item) => item.episode))).sort((a, b) => a - b),
    [issues],
  )

  const workflowStatuses = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(repairState).map(([issueId, value]) => [issueId, value.status]),
      ),
    [repairState],
  )

  const filteredIssues = useMemo(() => {
    const matched = issues.filter((issue) => {
      const currentStatus = workflowStatuses[issue.id] ?? issue.workflowStatus ?? 'open'
      if (layerFilter !== 'all' && issue.layer !== layerFilter) return false
      if (statusFilter !== 'all' && currentStatus !== statusFilter) return false
      if (!matchesQaLifecycleFilter(issue, lifecycleFilter)) return false
      if (episodeFilter !== 'all' && issue.episode !== episodeFilter) return false
      if (shotFilter.trim() && !String(issue.shotId ?? '').toLowerCase().includes(shotFilter.trim().toLowerCase())) return false
      return true
    })
    return sortQaIssues(matched, workflowStatuses, sortMode)
  }, [episodeFilter, issues, layerFilter, lifecycleFilter, shotFilter, sortMode, statusFilter, workflowStatuses])

  const selectedIssue = useMemo(
    () => filteredIssues.find((item) => item.id === selectedIssueId) ?? filteredIssues[0] ?? null,
    [filteredIssues, selectedIssueId],
  )

  useEffect(() => {
    setRepairState(readQaRepairState(bookId))
  }, [bookId])

  const refreshQaWorkbench = useCallback(async (silent = false) => {
    if (bookId <= 0) {
      setQaWorkbench(null)
      setQaWorkbenchState('idle')
      return null
    }

    if (!silent) {
      setQaWorkbenchState('loading')
    }

    try {
      const response = await fetch(`/api/books/${bookId}/qa/workbench`)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const payload = (await response.json()) as QaWorkbenchResponse
      setQaWorkbench(payload)
      setQaWorkbenchState('loaded')
      return payload
    } catch {
      if (!silent) {
        setQaWorkbench(null)
        setQaWorkbenchState('error')
      }
      return null
    }
  }, [bookId])

  useEffect(() => {
    void refreshQaWorkbench()
  }, [refreshQaWorkbench])

  useEffect(() => {
    persistQaRepairState(bookId, repairState)
  }, [bookId, repairState])

  useEffect(() => {
    const workbenchRepairState = Object.fromEntries(
      issues
        .filter((issue) => issue.sourceKind === 'workbench')
        .map((issue) => [
          issue.id,
          {
            status: issue.workflowStatus ?? 'open',
            repairVersion: issue.repairVersion ?? '',
            note: issue.note ?? '',
          },
        ]),
    )
    if (Object.keys(workbenchRepairState).length === 0) {
      return
    }
    setRepairState((current) => ({
      ...current,
      ...workbenchRepairState,
    }))
  }, [issues])

  useEffect(() => {
    if (!qaFollowupPollTarget) {
      return
    }

    const target = qaFollowupPollTarget
    let cancelled = false

    async function pollUntilSettled() {
      for (let attempt = 0; attempt < 12; attempt += 1) {
        if (attempt > 0) {
          await new Promise((resolve) => window.setTimeout(resolve, 1500))
        }
        if (cancelled) {
          return
        }

        const payload = await refreshQaWorkbench(true)
        if (cancelled || !payload) {
          continue
        }

        const targetIssue = findRawWorkbenchIssue(payload, target.issueId)
        const issueStatus = String(targetIssue?.fix_status ?? '').trim().toLowerCase()
        const pendingIssueCount = countEpisodePendingIssues(payload, target.episode)
        const settled =
          target.action === 'autofix'
            ? issueStatus !== '' && issueStatus !== 'rechecking'
            : pendingIssueCount === 0 || issueStatus === 'recheck_failed' || issueStatus === 'recheck_passed'

        if (!settled) {
          setActionStateByIssue((current) => {
            const previous = current[target.issueId]
            if (!previous) {
              return current
            }
            return {
              ...current,
              [target.issueId]: {
                ...previous,
                mode: 'loading',
                message:
                  target.action === 'autofix'
                    ? '自动修复已提交，正在等待 QA 复检结果回流...'
                    : '该集 QA 复检已启动，正在同步最新结果...',
              },
            }
          })
          continue
        }

        const outcome = buildFollowupOutcomeMessage(target.action, targetIssue, pendingIssueCount)
        setActionStateByIssue((current) => {
          const previous = current[target.issueId]
          if (!previous) {
            return current
          }
          return {
            ...current,
            [target.issueId]: {
              ...previous,
              mode: outcome.mode,
              message: outcome.message,
            },
          }
        })
        setQaFollowupPollTarget(null)
        return
      }

      setActionStateByIssue((current) => {
        const previous = current[target.issueId]
        if (!previous) {
          return current
        }
        return {
          ...current,
          [target.issueId]: {
            ...previous,
            mode: 'error',
            message: '后台复检仍在运行，当前页面已停止自动等待，请稍后手动刷新确认。',
          },
        }
      })
      setQaFollowupPollTarget(null)
    }

    void pollUntilSettled()

    return () => {
      cancelled = true
    }
  }, [qaFollowupPollTarget, refreshQaWorkbench])

  useEffect(() => {
    if (filteredIssues.length === 0) {
      setSelectedIssueId(null)
      return
    }

    setSelectedIssueId((current) => {
      if (current && filteredIssues.some((item) => item.id === current)) {
        return current
      }
      return filteredIssues[0]?.id ?? null
    })
  }, [filteredIssues])

  useEffect(() => {
    if (!qaNavigationTarget) return

    const targetEpisode = Number(qaNavigationTarget.episode ?? 0) || null
    const targetShotId = String(qaNavigationTarget.shotId ?? '').trim()
    const qaFocus = qaNavigationTarget.qaFocus ?? null

    if (targetEpisode) {
      setEpisodeFilter(targetEpisode)
      setLayerFilter('all')
      setStatusFilter('all')
      setLifecycleFilter('all')
      setSortMode('episode_asc')
    }
    setShotFilter(targetShotId)

    if (!targetEpisode && !targetShotId) return

    const matchedIssue = pickQaNavigationIssue(issues, workflowStatuses, {
      episode: targetEpisode,
      shotId: targetShotId || null,
      qaFocus,
    })
    if (matchedIssue) {
      setSelectedIssueId(matchedIssue.id)
    }
  }, [issues, qaNavigationTarget, workflowStatuses])

  const currentRepair = selectedIssue
    ? repairState[selectedIssue.id] ?? {
        status: selectedIssue.workflowStatus ?? 'open',
        repairVersion: selectedIssue.repairVersion ?? '',
        note: selectedIssue.note ?? '',
      }
    : null
  const selectedIssueStatus = currentRepair?.status ?? selectedIssue?.workflowStatus ?? 'open'
  const canvasHandoffSummary = buildQaCanvasHandoffSummary({
    handoff: canvasHandoff,
    issue: selectedIssue
      ? {
          title: selectedIssue.title,
          episode: selectedIssue.episode,
          shotId: selectedIssue.shotId,
          assetLabel: selectedIssue.assetLabel,
        }
      : null,
  })
  const selectedActionState = selectedIssue
    ? actionStateByIssue[selectedIssue.id] ?? { mode: 'idle', action: null, message: '', options: [], diffText: '' }
    : { mode: 'idle', action: null, message: '', options: [], diffText: '' }
  const selectedRepairSyncState = selectedIssue
    ? repairSyncStateByIssue[selectedIssue.id] ?? { mode: 'idle', message: '' }
    : { mode: 'idle', message: '' }
  const selectedRawWorkbenchIssue = selectedIssue ? findRawWorkbenchIssue(qaWorkbench, selectedIssue.id) : null
  const selectedWorkbenchEpisode = useMemo(
    () => (selectedIssue ? (qaWorkbench?.episodes ?? []).find((item) => Number(item.episode ?? 0) === selectedIssue.episode) ?? null : null),
    [qaWorkbench, selectedIssue],
  )
  const selectedPatchDraft = selectedIssue
    ? patchDraftByIssue[selectedIssue.id] ?? selectedActionState.options[0]?.patched_text ?? selectedIssue.sourceExcerpt ?? ''
    : ''
  const selectedPreview = selectedIssue ? previewByIssue[selectedIssue.id] ?? null : null
  const qaCanvasPrimaryAction = buildQaCanvasPrimaryActionPlan({
    hasReleaseGateBlock: releaseGateSummary.isBlocked,
    issue: selectedIssue
      ? {
          sourceKind: selectedIssue.sourceKind,
          workflowStatus: selectedIssueStatus,
          rawFixStatus: selectedIssue.rawFixStatus,
          recommendedActions: selectedIssue.recommendedActions,
        }
      : null,
    actionState: selectedIssue ? selectedActionState : null,
  })

  async function syncWorkbenchRepairRecord(
    issueId: string,
    payload: {
      status?: QaWorkflowStatus
      repairVersion?: string
      note?: string
    },
  ) {
    setRepairSyncStateByIssue((current) => ({
      ...current,
      [issueId]: { mode: 'saving', message: '正在同步真实工单...' },
    }))

    try {
      const response = await fetch(`/api/books/${bookId}/qa/issues/${issueId}/workflow`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workflowStatus: payload.status,
          repairVersion: payload.repairVersion,
          note: payload.note,
        }),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) {
        const message = typeof result?.detail === 'string' ? result.detail : `HTTP ${response.status}`
        throw new Error(message)
      }

      const issuePayload = result?.issue ?? {}
      setRepairState((current) => ({
        ...current,
        [issueId]: {
          status: (issuePayload.workflow_status as QaWorkflowStatus) ?? payload.status ?? current[issueId]?.status ?? 'open',
          repairVersion: typeof issuePayload.repair_version === 'string' ? issuePayload.repair_version : payload.repairVersion ?? current[issueId]?.repairVersion ?? '',
          note: typeof issuePayload.note === 'string' ? issuePayload.note : payload.note ?? current[issueId]?.note ?? '',
        },
      }))
      setRepairSyncStateByIssue((current) => ({
        ...current,
        [issueId]: { mode: 'saved', message: '已同步到真实工单。' },
      }))
      await refreshQaWorkbench(true)
    } catch (error) {
      const message = error instanceof Error ? error.message : '同步失败，请稍后再试。'
      setRepairSyncStateByIssue((current) => ({
        ...current,
        [issueId]: { mode: 'error', message },
      }))
    }
  }

  async function runWorkbenchIssueAction(action: 'generate' | 'autofix' | 'recheck') {
    if (!selectedIssue || selectedIssue.sourceKind !== 'workbench') {
      return
    }

    const issueId = selectedIssue.id
    setActionStateByIssue((current) => ({
      ...current,
      [issueId]: { mode: 'loading', action, message: '', options: [], diffText: '' },
    }))

    try {
      let response: Response
      if (action === 'generate') {
        response = await fetch(`/api/books/${bookId}/qa/issues/${issueId}/generate-fix-options`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode: 'auto', optionCount: 3 }),
        })
      } else if (action === 'autofix') {
        response = await fetch(`/api/books/${bookId}/qa/issues/${issueId}/auto-fix`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mode: 'auto',
            optionCount: 3,
            rerunQa: true,
            operatorName: 'product-workspace',
          }),
        })
      } else {
        response = await fetch(`/api/books/${bookId}/qa/episodes/${selectedIssue.episode}/recheck`, {
          method: 'POST',
        })
      }

      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        const message = typeof payload?.detail === 'string' ? payload.detail : `HTTP ${response.status}`
        throw new Error(message)
      }

      setActionStateByIssue((current) => ({
        ...current,
        [issueId]:
          action === 'generate'
            ? {
                mode: 'success',
                action,
                message: `已生成 ${Array.isArray(payload.options) ? payload.options.length : 0} 个修复方案，请预览 diff 后再应用。`,
                options: Array.isArray(payload.options) ? (payload.options as QaFixOption[]) : [],
                diffText: '',
              }
            : action === 'autofix'
              ? {
                  mode: payload?.recheck?.status === 'running' ? 'loading' : 'success',
                  action,
                  message:
                    payload?.recheck?.status === 'running'
                      ? '自动修复已提交，正在等待 QA 复检结果回流...'
                      : '自动修复已完成，最新状态已同步。',
                  options: [],
                  diffText: typeof payload.diff_text === 'string' ? payload.diff_text : '',
                }
              : {
                  mode: payload?.status === 'running' ? 'loading' : 'success',
                  action,
                  message:
                    payload?.status === 'running'
                      ? '已启动 QA 复检，正在同步最新结果...'
                      : '已完成 QA 复检。',
                  options: [],
                  diffText: '',
                },
      }))
      if (action === 'generate') {
        const options = Array.isArray(payload.options) ? (payload.options as QaFixOption[]) : []
        const firstOption = options[0]
        setSelectedOptionByIssue((current) => ({ ...current, [issueId]: firstOption?.id ?? '' }))
        setPatchDraftByIssue((current) => ({
          ...current,
          [issueId]: current[issueId] ?? firstOption?.patched_text ?? selectedIssue.sourceExcerpt ?? '',
        }))
        setPreviewByIssue((current) => {
          const next = { ...current }
          delete next[issueId]
          return next
        })
      }
      await refreshQaWorkbench(true)
      if (action === 'autofix' && payload?.recheck?.status === 'running') {
        setQaFollowupPollTarget({ issueId, episode: selectedIssue.episode, action: 'autofix' })
      } else if (action === 'recheck' && payload?.status === 'running') {
        setQaFollowupPollTarget({ issueId, episode: selectedIssue.episode, action: 'recheck' })
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : '工单动作执行失败。'
      setActionStateByIssue((current) => ({
        ...current,
        [issueId]: { mode: 'error', action, message, options: [], diffText: '' },
      }))
    }
  }

  async function previewWorkbenchIssueFix() {
    if (!selectedIssue || selectedIssue.sourceKind !== 'workbench') return
    const issueId = selectedIssue.id
    const patchedText = selectedPatchDraft.trim()
    if (!patchedText) {
      setActionStateByIssue((current) => ({
        ...current,
        [issueId]: {
          ...selectedActionState,
          mode: 'error',
          action: 'preview',
          message: '请先生成修复方案，或手动填写修复片段。',
        },
      }))
      return
    }

    setActionStateByIssue((current) => ({
      ...current,
      [issueId]: { ...selectedActionState, mode: 'loading', action: 'preview', message: '正在生成 diff 预览...' },
    }))

    try {
      const response = await fetch(`/api/books/${bookId}/qa/issues/${issueId}/preview-fix`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: selectedRawWorkbenchIssue?.fix_mode || 'manual',
          patchedText,
          optionId: selectedOptionByIssue[issueId] || '',
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        const message = typeof payload?.detail === 'string' ? payload.detail : `HTTP ${response.status}`
        throw new Error(message)
      }
      setPreviewByIssue((current) => ({ ...current, [issueId]: payload as QaPreviewPayload }))
      setActionStateByIssue((current) => ({
        ...current,
        [issueId]: {
          ...selectedActionState,
          mode: 'success',
          action: 'preview',
          message: 'diff 预览已生成，确认无误后可以应用修复。',
          diffText: typeof payload?.diff_text === 'string' ? payload.diff_text : '',
        },
      }))
    } catch (error) {
      const message = error instanceof Error ? error.message : 'diff 预览失败。'
      setActionStateByIssue((current) => ({
        ...current,
        [issueId]: { ...selectedActionState, mode: 'error', action: 'preview', message },
      }))
    }
  }

  async function applyWorkbenchIssueFix() {
    if (!selectedIssue || selectedIssue.sourceKind !== 'workbench') return
    const issueId = selectedIssue.id
    const patchedText = selectedPatchDraft.trim()
    if (!patchedText) {
      setActionStateByIssue((current) => ({
        ...current,
        [issueId]: {
          ...selectedActionState,
          mode: 'error',
          action: 'apply',
          message: '请先生成修复方案，或手动填写修复片段。',
        },
      }))
      return
    }
    if (!selectedPreview || selectedPreview.patched_text !== patchedText) {
      setActionStateByIssue((current) => ({
        ...current,
        [issueId]: {
          ...selectedActionState,
          mode: 'error',
          action: 'apply',
          message: '应用修复前请先预览 diff，并确认预览内容就是当前修复片段。',
        },
      }))
      return
    }

    setActionStateByIssue((current) => ({
      ...current,
      [issueId]: { ...selectedActionState, mode: 'loading', action: 'apply', message: '正在应用修复并触发复检...' },
    }))

    try {
      const response = await fetch(`/api/books/${bookId}/qa/issues/${issueId}/apply-fix`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: selectedRawWorkbenchIssue?.fix_mode || 'manual',
          patchedText,
          changeReason: selectedIssue.title || selectedIssue.detail,
          optionId: selectedOptionByIssue[issueId] || '',
          rerunQa: true,
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        const message = typeof payload?.detail === 'string' ? payload.detail : `HTTP ${response.status}`
        throw new Error(message)
      }

      setPreviewByIssue((current) => {
        const next = { ...current }
        delete next[issueId]
        return next
      })
      setActionStateByIssue((current) => ({
        ...current,
        [issueId]: {
          ...selectedActionState,
          mode: payload?.recheck?.status === 'running' ? 'loading' : 'success',
          action: 'apply',
          message:
            payload?.recheck?.status === 'running'
              ? `修复已保存，第 ${selectedIssue.episode} 集正在后台复检。`
              : '修复已保存，最新状态已同步。',
          diffText: typeof payload?.diff_text === 'string' ? payload.diff_text : selectedActionState.diffText,
        },
      }))
      await refreshQaWorkbench(true)
      if (payload?.recheck?.status === 'running') {
        setQaFollowupPollTarget({ issueId, episode: selectedIssue.episode, action: 'recheck' })
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : '应用修复失败。'
      setActionStateByIssue((current) => ({
        ...current,
        [issueId]: { ...selectedActionState, mode: 'error', action: 'apply', message },
      }))
    }
  }

  async function rollbackQaScriptVersion(target: Exclude<QaPendingRollback, null>) {
    if (!selectedIssue || selectedIssue.sourceKind !== 'workbench') return
    const issueId = selectedIssue.id
    setActionStateByIssue((current) => ({
      ...current,
      [issueId]: { ...selectedActionState, mode: 'loading', action: 'rollback', message: '正在回滚脚本版本并触发复检...' },
    }))
    try {
      const response = await fetch(`/api/books/${bookId}/scripts/${target.episode}/versions/${target.versionId}/rollback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rerunQa: true }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        const message = typeof payload?.detail === 'string' ? payload.detail : `HTTP ${response.status}`
        throw new Error(message)
      }
      setPendingRollback(null)
      setActionStateByIssue((current) => ({
        ...current,
        [issueId]: {
          ...selectedActionState,
          mode: 'loading',
          action: 'rollback',
          message: `已回滚到 ${target.versionLabel} 的修复前状态，正在等待 QA 复检结果回流。`,
        },
      }))
      await refreshQaWorkbench(true)
      setQaFollowupPollTarget({ issueId, episode: target.episode, action: 'recheck' })
    } catch (error) {
      const message = error instanceof Error ? error.message : '脚本版本回滚失败。'
      setActionStateByIssue((current) => ({
        ...current,
        [issueId]: { ...selectedActionState, mode: 'error', action: 'rollback', message },
      }))
    }
  }

  function updateSelectedIssueWorkflow(nextStatus: QaWorkflowStatus) {
    if (!selectedIssue) return
    setRepairState((current) => ({
      ...current,
      [selectedIssue.id]: {
        status: nextStatus,
        repairVersion: current[selectedIssue.id]?.repairVersion ?? '',
        note: current[selectedIssue.id]?.note ?? '',
      },
    }))
    if (selectedIssue.sourceKind === 'workbench') {
      const draft = repairState[selectedIssue.id]
      void syncWorkbenchRepairRecord(selectedIssue.id, {
        status: nextStatus,
        repairVersion: draft?.repairVersion ?? selectedIssue.repairVersion ?? '',
        note: draft?.note ?? selectedIssue.note ?? '',
      })
    }
  }

  function runQaCanvasPrimaryAction() {
    if (!selectedIssue || !qaCanvasPrimaryAction) return

    switch (qaCanvasPrimaryAction.action) {
      case 'scripts_gate':
        onNavigate('scripts')
        return
      case 'generate_fix':
        void runWorkbenchIssueAction('generate')
        return
      case 'autofix':
        void runWorkbenchIssueAction('autofix')
        return
      case 'recheck':
        void runWorkbenchIssueAction('recheck')
        return
      case 'navigate':
        if (selectedIssue.shotId && qaCanvasPrimaryAction.target === 'storyboard') {
          onSelectShot(selectedIssue.shotId)
        }
        onNavigate(targetToSection(qaCanvasPrimaryAction.target))
        return
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[0.95fr,1.2fr,0.95fr]">
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
        <div className="text-sm font-medium text-white">QA 问题列表</div>
        <div className="mt-2 text-xs text-slate-500">
          {qaWorkbenchState === 'loaded'
            ? '已接入真实剧本 QA 工作台，并混合显示分镜/资产派生问题。'
            : qaWorkbenchState === 'loading'
              ? '正在同步真实 QA 工作台...'
              : qaWorkbenchState === 'error'
                ? '真实 QA 工作台读取失败，当前回退为派生问题视图。'
                : '当前显示结构化 QA 问题。'}
        </div>
        <div className="mt-1 text-xs text-slate-500">默认只显示待处理问题；已解决和不修复记录可在“全部状态”中回看。</div>

        {releaseGateSummary.totalScriptEpisodes > 0 ? (
          <div
            className={`mt-4 rounded-xl border p-3 ${
              releaseGateSummary.isBlocked
                ? 'border-amber-500/30 bg-amber-500/10'
                : 'border-emerald-500/30 bg-emerald-500/10'
            }`}
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-white">{releaseGateSummary.summaryLabel}</div>
                <div className="mt-1 text-xs leading-6 text-slate-300">{releaseGateSummary.detail}</div>
              </div>
              <button
                type="button"
                onClick={() => onNavigate('scripts')}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                  releaseGateSummary.isBlocked
                    ? 'border border-amber-400/40 text-amber-100 hover:border-amber-300 hover:text-white'
                    : 'border border-slate-700 text-slate-200 hover:border-sky-500 hover:text-white'
                }`}
              >
                {releaseGateSummary.isBlocked ? '返回剧本工作台补放行' : '回剧本工作台复核'}
              </button>
            </div>
          </div>
        ) : null}

        <details className="mt-4 rounded-lg border border-slate-800 bg-slate-950/30 p-3">
          <summary className="cursor-pointer text-xs font-medium text-slate-300">高级：筛选问题范围、历史与排序</summary>
          <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-1">
          <select
            aria-label="按问题层级筛选"
            value={layerFilter}
            onChange={(event) => setLayerFilter(event.target.value as 'all' | QaLayer)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
          >
            {LAYER_OPTIONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>

          <select
            aria-label="按处理状态筛选"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as 'all' | QaWorkflowStatus)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
          >
            {STATUS_OPTIONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>

          <select
            aria-label="按修复阶段筛选"
            value={lifecycleFilter}
            onChange={(event) => setLifecycleFilter(event.target.value as QaLifecycleFilter)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
          >
            {LIFECYCLE_OPTIONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>

          <select
            aria-label="按集数筛选"
            value={episodeFilter === 'all' ? 'all' : String(episodeFilter)}
            onChange={(event) => setEpisodeFilter(event.target.value === 'all' ? 'all' : Number(event.target.value))}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
          >
            <option value="all">全部集数</option>
            {episodeOptions.map((episode) => (
              <option key={episode} value={episode}>
                第 {episode} 集
              </option>
            ))}
          </select>

          <select
            aria-label="排序方式"
            value={sortMode}
            onChange={(event) => setSortMode(event.target.value as QaIssueSortMode)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
          >
            {SORT_OPTIONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>

          <input
            value={shotFilter}
            onChange={(event) => setShotFilter(event.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-sky-500"
            placeholder="搜索镜头号或问题关键词"
          />
          </div>
        </details>

        <div className="mt-4 space-y-3">
          {filteredIssues.length > 0 ? (
            filteredIssues.map((issue) => {
              const active = selectedIssue?.id === issue.id
              const workflowStatus = repairState[issue.id]?.status ?? issue.workflowStatus ?? 'open'
              return (
                <button
                  key={issue.id}
                  onClick={() => setSelectedIssueId(issue.id)}
                  className={`w-full rounded-xl border p-3 text-left transition ${
                    active
                      ? 'border-sky-500/40 bg-sky-500/10'
                      : 'border-slate-800 bg-slate-950/50 hover:border-slate-700'
                  }`}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded-full border px-2 py-0.5 text-[11px] ${severityTone(issue.severity)}`}>
                      {issue.severity}
                    </span>
                    {isHumanReview(issue) ? (
                      <span className="rounded-full border border-amber-400/50 bg-amber-400/10 px-2 py-0.5 text-[11px] font-medium text-amber-200">
                        人工定稿
                      </span>
                    ) : null}
                    <span className={`rounded-full border px-2 py-0.5 text-[11px] ${statusTone(workflowStatus)}`}>
                      {statusLabel(workflowStatus)}
                    </span>
                    <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">
                      {layerLabel(issue.layer)}
                    </span>
                    <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-400">
                      {issue.sourceKind === 'workbench' ? '真实工单' : '派生问题'}
                    </span>
                    {issue.rawFixStatus ? (
                      <span className={`rounded-full border px-2 py-0.5 text-[11px] ${lifecycleTone(issue.rawFixStatus)}`}>
                        {qaLifecycleLabel(issue.rawFixStatus)}
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-3 text-sm font-medium text-white">{issue.title}</div>
                  <div className="mt-2 line-clamp-3 text-xs leading-5 text-slate-400">{issue.detail}</div>
                  <div className="mt-3 flex items-center justify-between text-[11px] text-slate-500">
                    <span>第 {issue.episode} 集</span>
                    <span>{issue.shotId ? `镜头 ${issue.shotId}` : '未绑定镜头'}</span>
                  </div>
                </button>
              )
            })
          ) : (
            <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
              当前筛选条件下没有 QA 问题。
            </div>
          )}
        </div>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        {selectedIssue ? (
          <>
            {canvasHandoffSummary ? (
              <div className="mb-5 rounded-xl border border-fuchsia-500/30 bg-fuchsia-500/10 p-4">
                <div className="text-xs font-medium tracking-wide text-fuchsia-200">创作画布承接中</div>
                <div className="mt-2 text-sm font-medium text-white">{canvasHandoffSummary.title}</div>
                {canvasHandoffSummary.issueTitle ? (
                  <div className="mt-2 text-sm text-fuchsia-100">{canvasHandoffSummary.issueTitle}</div>
                ) : null}
                <div className="mt-2 text-xs leading-6 text-fuchsia-100/80">{canvasHandoffSummary.detail}</div>
                {qaCanvasPrimaryAction ? (
                  <div className="mt-4 rounded-lg border border-fuchsia-400/20 bg-slate-950/30 p-3">
                    <div className="text-[11px] tracking-wide text-fuchsia-200/90">承接后的首个动作</div>
                    <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium text-white">{qaCanvasPrimaryAction.label}</div>
                        <div className="mt-1 text-xs leading-6 text-fuchsia-100/80">{qaCanvasPrimaryAction.detail}</div>
                      </div>
                      <button
                        type="button"
                        onClick={runQaCanvasPrimaryAction}
                        disabled={selectedActionState.mode === 'loading'}
                        className="rounded-lg border border-fuchsia-400/40 px-3 py-1.5 text-xs font-medium text-fuchsia-100 transition hover:border-fuchsia-300 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        立即继续
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-lg font-semibold text-white">{selectedIssue.title}</div>
                <div className="mt-2 text-sm leading-6 text-slate-400">{selectedIssue.detail}</div>
              </div>
              <div className="flex flex-wrap gap-2">
                <span className={`rounded-full border px-2.5 py-1 text-xs ${severityTone(selectedIssue.severity)}`}>
                  {selectedIssue.severity}
                </span>
                <span className={`rounded-full border px-2.5 py-1 text-xs ${statusTone(selectedIssueStatus)}`}>
                  {statusLabel(selectedIssueStatus)}
                </span>
                <span className="rounded-full border border-slate-700 px-2.5 py-1 text-xs text-slate-300">
                  {selectedIssue.sourceKind === 'workbench' ? '真实工单' : '派生补充'}
                </span>
              </div>
            </div>

            <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <InfoCard title="层级" value={layerLabel(selectedIssue.layer)} detail={selectedIssue.source === 'suggestion' ? '质量建议' : '正式问题'} />
              <InfoCard title="集数" value={`第 ${selectedIssue.episode} 集`} detail={selectedIssue.shotId ? `镜头 ${selectedIssue.shotId}` : '未绑定镜头'} />
              <InfoCard title="提示词版本" value={selectedIssue.promptVersion ? `v${selectedIssue.promptVersion}` : '未记录'} detail="修复后应记录对应版本" />
              <InfoCard title="关联资产" value={selectedIssue.assetLabel ?? '未记录'} detail="角色 / 场景 / 道具引用" />
            </div>

            <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
              <div className="text-sm font-medium text-white">修复动作</div>
              {selectedIssue.statusReason ? (
                <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-xs text-slate-400">
                  当前状态说明：{selectedIssue.statusReason}
                </div>
              ) : null}
              <div className="mt-3 space-y-3">
                {selectedIssue.recommendedActions.map((action) => (
                  <div key={action.id} className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-sm text-white">{action.label}</div>
                      <button
                        type="button"
                        onClick={() => {
                          if (selectedIssue.shotId && action.target === 'storyboard') {
                            onSelectShot(selectedIssue.shotId)
                          }
                          onNavigate(targetToSection(action.target))
                        }}
                        className="rounded-lg border border-sky-500/50 px-3 py-1.5 text-xs font-medium text-sky-200 transition hover:border-sky-400 hover:text-white"
                      >
                        执行入口
                      </button>
                    </div>
                    <div className="mt-2 text-sm leading-6 text-slate-400">{action.reason}</div>
                  </div>
                ))}
              </div>

              {selectedIssue.sourceKind === 'workbench' ? (
                <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/70 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-white">真实 QA 工单动作</div>
                      <div className="mt-1 text-xs text-slate-400">直接生成修复方案、自动修复脚本，并回写最新复检状态。</div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => void runWorkbenchIssueAction('generate')}
                        disabled={selectedActionState.mode === 'loading'}
                        className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        生成修复方案
                      </button>
                      <button
                        type="button"
                        onClick={() => void runWorkbenchIssueAction('autofix')}
                        disabled={selectedActionState.mode === 'loading'}
                        className="rounded-lg border border-emerald-500/50 px-3 py-1.5 text-xs font-medium text-emerald-200 transition hover:border-emerald-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        自动修复
                      </button>
                      <button
                        type="button"
                        onClick={() => void runWorkbenchIssueAction('recheck')}
                        disabled={selectedActionState.mode === 'loading'}
                        className="rounded-lg border border-sky-500/50 px-3 py-1.5 text-xs font-medium text-sky-200 transition hover:border-sky-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        触发复检
                      </button>
                    </div>
                  </div>

                  {selectedActionState.message ? (
                    <div
                      role="status"
                      aria-live="polite"
                      className={`mt-3 rounded-lg border px-3 py-2 text-xs ${
                        selectedActionState.mode === 'error'
                          ? 'border-rose-500/30 bg-rose-500/10 text-rose-200'
                          : selectedActionState.mode === 'loading'
                            ? 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                            : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
                      }`}
                    >
                      {selectedActionState.message}
                    </div>
                  ) : null}

                  {selectedActionState.options.length > 0 ? (
                    <div className="mt-3 space-y-2">
                      {selectedActionState.options.map((option, index) => (
                        <button
                          key={option.id ?? `option-${index}`}
                          type="button"
                          onClick={() => {
                            if (!selectedIssue) return
                            setSelectedOptionByIssue((current) => ({ ...current, [selectedIssue.id]: option.id ?? '' }))
                            setPatchDraftByIssue((current) => ({
                              ...current,
                              [selectedIssue.id]: option.patched_text ?? current[selectedIssue.id] ?? '',
                            }))
                            setPreviewByIssue((current) => {
                              const next = { ...current }
                              delete next[selectedIssue.id]
                              return next
                            })
                          }}
                          className={`w-full rounded-lg border p-3 text-left transition ${
                            selectedIssue && selectedOptionByIssue[selectedIssue.id] === option.id
                              ? 'border-sky-500/40 bg-sky-500/10'
                              : 'border-slate-800 bg-slate-950/80 hover:border-slate-700'
                          }`}
                        >
                          <div className="text-xs font-medium text-white">
                            {option.id ? `方案 ${option.id}` : `方案 ${index + 1}`}
                          </div>
                          <div className="mt-2 text-sm leading-6 text-slate-300">{option.summary ?? option.strategy ?? option.title ?? '暂无摘要'}</div>
                          {option.risk ? <div className="mt-2 text-xs text-amber-300">风险提示：{option.risk}</div> : null}
                        </button>
                      ))}
                    </div>
                  ) : null}

                  <div className="mt-3 grid gap-3 lg:grid-cols-2">
                    <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-3">
                      <div className="text-xs font-medium text-slate-300">修复前片段</div>
                      <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-xs leading-6 text-slate-400">
                        {selectedIssue.sourceExcerpt || '当前问题还没有精确原文定位。'}
                      </pre>
                    </div>
                    <div className="rounded-lg border border-emerald-900/40 bg-emerald-950/10 p-3">
                      <div className="text-xs font-medium text-emerald-200">修复后片段</div>
                      <textarea
                        value={selectedPatchDraft}
                        onChange={(event) => {
                          if (!selectedIssue) return
                          setPatchDraftByIssue((current) => ({ ...current, [selectedIssue.id]: event.target.value }))
                          setPreviewByIssue((current) => {
                            const next = { ...current }
                            delete next[selectedIssue.id]
                            return next
                          })
                        }}
                        className="mt-2 min-h-48 w-full rounded-lg border border-slate-800 bg-slate-950/80 px-3 py-2 text-xs leading-6 text-slate-200 outline-none transition focus:border-emerald-500"
                        placeholder="选择修复方案后会填入这里，也可以直接人工编辑。"
                      />
                    </div>
                  </div>

                  {selectedActionState.diffText ? (
                    <div className="mt-3">
                      <div className="text-xs text-slate-500">修复 Diff</div>
                      <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-950/80 p-3 text-xs leading-6 text-slate-300">
                        {selectedActionState.diffText}
                      </pre>
                    </div>
                  ) : null}

                  <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-violet-900/30 bg-violet-950/10 p-3">
                    <div className="text-xs leading-5 text-violet-100/80">
                      {selectedPreview
                        ? 'diff 已预览；如果继续编辑修复后片段，需要重新预览。'
                        : '应用修复前必须先生成 diff 预览，确认只修改目标片段。'}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => void previewWorkbenchIssueFix()}
                        disabled={selectedActionState.mode === 'loading'}
                        className="rounded-lg border border-violet-500/50 px-3 py-1.5 text-xs font-medium text-violet-200 transition hover:border-violet-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        预览 diff
                      </button>
                      <button
                        type="button"
                        onClick={() => void applyWorkbenchIssueFix()}
                        disabled={selectedActionState.mode === 'loading'}
                        className="rounded-lg border border-emerald-500/50 px-3 py-1.5 text-xs font-medium text-emerald-200 transition hover:border-emerald-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        应用修复并复检
                      </button>
                    </div>
                  </div>
                </div>
              ) : null}
            </div>

            {selectedIssue.sourceExcerpt ? (
              <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                <div className="text-sm font-medium text-white">问题上下文摘录</div>
                <pre className="mt-3 whitespace-pre-wrap rounded-lg bg-slate-950/70 p-3 text-xs leading-6 text-slate-300">
                  {selectedIssue.sourceExcerpt}
                </pre>
              </div>
            ) : null}

            <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
              <div className="text-sm font-medium text-white">生命周期操作</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {(['open', 'in_progress', 'resolved', 'wont_fix'] as QaWorkflowStatus[]).map((status) => {
                  const active = selectedIssueStatus === status
                  return (
                    <button
                      key={status}
                      type="button"
                      onClick={() => updateSelectedIssueWorkflow(status)}
                      className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                        active
                          ? `${statusTone(status)}`
                          : 'border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white'
                      }`}
                    >
                      {workflowActionLabel(status)}
                    </button>
                  )
                })}
              </div>
              {selectedIssue.sourceKind === 'workbench' && selectedRepairSyncState.message ? (
                <div
                  role="status"
                  aria-live="polite"
                  className={`mt-3 rounded-lg border px-3 py-2 text-xs ${
                    selectedRepairSyncState.mode === 'error'
                      ? 'border-rose-500/30 bg-rose-500/10 text-rose-200'
                      : selectedRepairSyncState.mode === 'saving'
                        ? 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                        : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
                  }`}
                >
                  {selectedRepairSyncState.message}
                </div>
              ) : null}
            </div>

              {selectedIssue.sourceKind === 'workbench' ? (
                <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-white">脚本修复版本</div>
                    <div className="mt-1 text-xs text-slate-500">应用修复会生成脚本版本；必要时可从这里回滚并自动复检。</div>
                  </div>
                  <span className="rounded-full border border-slate-700 px-2.5 py-1 text-[11px] text-slate-300">
                    {(selectedWorkbenchEpisode?.versions ?? []).length} 个版本
                  </span>
                </div>

                <details className="mt-4">
                  <summary className="cursor-pointer text-xs font-medium text-sky-300">高级：查看版本、差异与回滚记录</summary>
                  <div className="mt-1 text-xs leading-5 text-slate-500">版本历史只在需要追溯或恢复时展开，不干扰当前问题的修复操作。</div>
                {(selectedWorkbenchEpisode?.versions ?? []).length > 0 ? (
                  <div className="mt-4 space-y-3">
                    {(selectedWorkbenchEpisode?.versions ?? []).slice(0, 6).map((version) => {
                      const versionId = Number(version.id ?? 0)
                      const versionLabel = version.label || `v${version.version_no ?? version.id ?? '?'}`
                      const canRollback = versionId > 0 && String(version.change_type ?? '').toLowerCase() !== 'baseline'
                      return (
                        <div key={version.id ?? `${version.version_no ?? 'v'}-${version.created_at ?? ''}`} className="rounded-lg border border-slate-800 bg-slate-950/80 p-3">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="text-sm font-medium text-white">{versionLabel}</span>
                                <span className={`rounded-full border px-2 py-0.5 text-[11px] ${scriptVersionTone(version.recheck_status)}`}>
                                  {version.recheck_status || 'not_run'}
                                </span>
                              </div>
                              <div className="mt-1 text-xs text-slate-500">
                                {version.change_type || 'manual'} / {version.operator_name || 'system'}
                              </div>
                              {version.change_reason ? <div className="mt-2 text-sm leading-6 text-slate-300">{version.change_reason}</div> : null}
                              {version.recheck_summary ? <div className="mt-2 text-xs leading-5 text-slate-500">{version.recheck_summary}</div> : null}
                            </div>
                            {canRollback ? (
                              <button
                                type="button"
                                onClick={() => setPendingRollback({ episode: selectedIssue.episode, versionId, versionLabel })}
                                disabled={selectedActionState.mode === 'loading'}
                                className="rounded-lg border border-rose-500/40 px-3 py-1.5 text-xs font-medium text-rose-200 transition hover:border-rose-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                回滚到修复前
                              </button>
                            ) : null}
                          </div>
                          {pendingRollback?.versionId === versionId ? (
                            <div className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3">
                              <div className="text-xs leading-5 text-rose-100/90">
                                确认回滚 {pendingRollback.versionLabel}？回滚后会恢复到这次修复前的剧本内容，并触发整集 QA 复检。
                              </div>
                              <div className="mt-3 flex flex-wrap gap-2">
                                <button
                                  type="button"
                                  onClick={() => void rollbackQaScriptVersion(pendingRollback)}
                                  disabled={selectedActionState.mode === 'loading'}
                                  className="rounded-lg border border-rose-400/50 px-3 py-1.5 text-xs font-medium text-rose-100 transition hover:border-rose-300 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  确认回滚并复检
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setPendingRollback(null)}
                                  className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
                                >
                                  取消
                                </button>
                              </div>
                            </div>
                          ) : null}
                          {version.diff_text ? (
                            <details className="mt-3">
                              <summary className="cursor-pointer text-xs text-sky-300">查看版本 diff</summary>
                              <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-950/80 p-3 text-[11px] leading-5 text-slate-300">
                                {version.diff_text}
                              </pre>
                            </details>
                          ) : null}
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <div className="mt-4 rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
                    当前集还没有脚本修复版本。
                  </div>
                )}
                </details>
                </div>
              ) : null}

            {selectedIssue.sourceKind === 'workbench' ? (
              <ProductWorkspaceQaDecisionPanel
                bookId={bookId}
                issueKey={selectedIssue.id}
                onUseProposal={(content) => {
                  setPatchDraftByIssue((current) => ({ ...current, [selectedIssue.id]: content }))
                  setPreviewByIssue((current) => {
                    const next = { ...current }
                    delete next[selectedIssue.id]
                    return next
                  })
                }}
              />
            ) : null}

            <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
              <div className="text-sm font-medium text-white">修复记录</div>
              <div className="mt-4 grid gap-4">
                <select
                  value={currentRepair?.status ?? selectedIssue.workflowStatus ?? 'open'}
                  onChange={(event) => updateSelectedIssueWorkflow(event.target.value as QaWorkflowStatus)}
                  className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
                >
                  {STATUS_OPTIONS.filter((item) => item.value !== 'all').map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>

                <input
                  value={currentRepair?.repairVersion ?? ''}
                  onChange={(event) => {
                    const repairVersion = event.target.value
                    setRepairState((current) => ({
                      ...current,
                      [selectedIssue.id]: {
                        status: current[selectedIssue.id]?.status ?? 'open',
                        repairVersion,
                        note: current[selectedIssue.id]?.note ?? '',
                      },
                    }))
                  }}
                  onBlur={() => {
                    if (selectedIssue.sourceKind === 'workbench') {
                      const draft = repairState[selectedIssue.id]
                      void syncWorkbenchRepairRecord(selectedIssue.id, {
                        status: draft?.status ?? selectedIssue.workflowStatus ?? 'open',
                        repairVersion: draft?.repairVersion ?? '',
                        note: draft?.note ?? '',
                      })
                    }
                  }}
                  className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-sky-500"
                  placeholder="记录修复版本，例如 prompt v4 / asset rev2"
                />

                <textarea
                  rows={4}
                  value={currentRepair?.note ?? ''}
                  onChange={(event) => {
                    const note = event.target.value
                    setRepairState((current) => ({
                      ...current,
                      [selectedIssue.id]: {
                        status: current[selectedIssue.id]?.status ?? 'open',
                        repairVersion: current[selectedIssue.id]?.repairVersion ?? '',
                        note,
                      },
                    }))
                  }}
                  onBlur={() => {
                    if (selectedIssue.sourceKind === 'workbench') {
                      const draft = repairState[selectedIssue.id]
                      void syncWorkbenchRepairRecord(selectedIssue.id, {
                        status: draft?.status ?? selectedIssue.workflowStatus ?? 'open',
                        repairVersion: draft?.repairVersion ?? '',
                        note: draft?.note ?? '',
                      })
                    }
                  }}
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-sky-500"
                  placeholder="记录这次怎么修、修到哪一版、回测结果如何。"
                />
              </div>
            </div>
          </>
        ) : (
          <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
            当前没有可查看的 QA 详情。
          </div>
        )}
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="text-sm font-medium text-white">QA 修复概览</div>

        <div className="mt-4 grid gap-3">
          <InfoCard title="总问题数" value={`${stats.total}`} detail="脚本 / 分镜 / 资产 / 视频统一汇总" />
          <InfoCard title="待处理" value={`${stats.open}`} detail="仍未进入解决态的问题数" />
          <InfoCard title="修复中" value={`${stats.inProgress}`} detail="已进入处理，但还没关闭的问题数" />
          <InfoCard title="已解决" value={`${stats.resolved}`} detail="已经记录解决态的问题数" />
          <InfoCard title="高优先级" value={`${stats.bySeverity.high}`} detail="建议优先处理阻塞生产链路的问题" />
          <InfoCard title="不修复" value={`${stats.wontFix}`} detail="已确认不进入当前修复范围的问题数" />
          <InfoCard
            title="层级分布"
            value={`${stats.byLayer.storyboard + stats.byLayer.asset + stats.byLayer.video}`}
            detail={`剧本 ${stats.byLayer.script} / 分镜 ${stats.byLayer.storyboard} / 资产 ${stats.byLayer.asset} / 视频 ${stats.byLayer.video}`}
          />
          <InfoCard
            title="上游闸门"
            value={
              releaseGateSummary.totalScriptEpisodes > 0
                ? `${releaseGateSummary.blockedEpisodes.length}/${releaseGateSummary.totalScriptEpisodes}`
                : '0/0'
            }
            detail={
              releaseGateSummary.totalScriptEpisodes > 0
                ? releaseGateSummary.isBlocked
                  ? '这些集次还没完成锁稿或放行，QA 通过后也不能直接视为可交付。'
                  : '已有剧本的集次都完成了锁稿和放行。'
                : '当前还没有正式剧本集次。'
            }
          />
          <InfoCard title="真实工单" value={`${workbenchIssueCount}`} detail={`派生补充 ${derivedIssueCount} 条`} />
        </div>

        <div className="mt-5 space-y-3">
          <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
            <div className="text-xs text-slate-500">当前阶段结论</div>
            <div className="mt-2 text-sm leading-6 text-slate-300">
              {stats.total === 0
                ? '当前没有结构化 QA 问题，后续这里会继续承接脚本、分镜、资产和视频的回测闭环。'
                : stats.open === 0 && releaseGateSummary.isBlocked
                  ? '当前 QA 问题已经基本收敛，但上游仍有剧本锁稿 / 放行缺口，所以这一集还不能视为真正验收通过。'
                : stats.open > 0
                  ? '当前 QA 已不再只是报告，所有问题都已经具备修复入口、状态和修复记录位。'
                  : '当前结构化 QA 问题均已进入解决态，可以继续补充回测与导出放行逻辑。'}
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
            <div className="text-xs text-slate-500">验收要点</div>
            <div className="mt-2 text-sm leading-6 text-slate-300">
              这里已经支持分层查看、按集数和镜头筛选、记录修复版本，并从每条问题直接跳去对应工作台。
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function InfoCard({ title, value, detail }: { title: string; value: string; detail: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
      <div className="text-xs text-slate-500">{title}</div>
      <div className="mt-2 text-lg font-semibold text-white">{value}</div>
      <div className="mt-1 text-xs text-slate-400">{detail}</div>
    </div>
  )
}
