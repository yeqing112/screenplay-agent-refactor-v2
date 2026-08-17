/** ProductionMode — 生产模式界面组件，用于展示和编辑剧本成品。 */
import { useEffect, useState, useCallback, useMemo, useRef, type ReactNode } from 'react'
import ModelRegistryModal from './ModelRegistryModal'
import {
  fetchModelRegistry,
  fetchModelRegistryDefaults,
  type ModelRegistryPayload,
} from '../prototyping/sceneComposerModelRegistry'
import { buildExportReadiness, buildReferencedVisualAssetSummary, buildShotChecklist, buildStoryboardReadiness, buildVisualAssetSummary } from './productionReadiness'
import {
  isLikelyCorruptedDeliveryText,
  normalizeDeliveryRecordFormatLabel,
  summarizeDeliveryRecordHistory,
} from './productWorkspaceDelivery'

interface Props {
  book: { id: number; title: string }
  bookData: any
  onRefresh: () => void
  onBookChange?: (bookId: number) => void
  onSwitchToDev: () => void
  onOpenPrototype?: () => void
}

type ActiveModule = 'script' | 'storyboard' | 'visual' | 'export'
type OutputTab = 'bible' | 'portrait' | 'visual' | 'outline' | 'script' | 'storyboard' | 'qa' | 'export'
type RunState = 'idle' | 'running' | 'done' | 'error' | 'partial'
type VisualAssetType = 'scene' | 'prop' | 'character'
type VisualReferenceCreatePayload = {
  imageUrl: string
  referenceToken: string
  status: string
  notes: string
  prompt?: string
  model?: string
  metaInfo?: Record<string, unknown>
}
type VisualReferenceCreateResult = {
  id?: number
  sync_warning?: string
  taskId?: string
  stillRunning?: boolean
}
type VisualReferenceUpdatePayload = {
  status?: string
  notes?: string
  referenceToken?: string
}
type VisualAssetPatchPayload = {
  jimengRefName?: string
  negativePrompt?: string
  assetStatus?: string
  shotIds?: string[]
}
type VisualReferenceDeleteResult = {
  deleted: boolean
  removed_storyboard_references?: number
  sync_warning?: string
}
type CreativeTaskWaitOptions = {
  softTimeoutMs?: number
  softTimeoutMessage?: string
}
type PendingVisualReferenceTask = {
  taskId: string
  assetType: VisualAssetType
  assetId: string
  assetName: string
  updatedAt: string
}
type VisualReferenceRecoveryMeta = {
  status: 'auto-recovering' | 'waiting-provider' | 'recovered' | 'failed'
  updatedAt: string
  message: string
}
type VisualBatchEntryStatus = 'waiting' | 'running' | 'done' | 'error' | 'skipped' | 'recovering'
type VisualBatchEntry = {
  key: string
  name: string
  status: VisualBatchEntryStatus
  message: string
  taskId?: string
}
type StoryboardTaskKind = 'frame' | 'video'
type PendingStoryboardTask = {
  taskId: string
  episode: number
  shotId: string
  kind: StoryboardTaskKind
  updatedAt: string
}
type WorkflowFeedbackStatus = 'idle' | 'loading' | 'running' | 'info' | 'success' | 'done' | 'warning' | 'partial' | 'error'

// --- Helpers ---
const GENRE_OPTIONS = [
  { value: 'short_drama', label: '短剧爽文' },
  { value: 'ancient_sweet', label: '古装甜宠' },
  { value: 'modern_ceo', label: '现代霸总' },
  { value: 'xianxia', label: '玄幻仙侠' },
  { value: 'suspense', label: '悬疑' },
]

const PIPELINE_STEPS = [
  { key: 'ingest', label: '小说解析' },
  { key: 'read', label: '逐章分析' },
  { key: 'bible', label: '世界观 Bible' },
  { key: 'portrait', label: '人物画像' },
  { key: 'adapt', label: '改编方案' },
  { key: 'outline', label: '分集大纲' },
  { key: 'script', label: '剧本写作' },
  { key: 'check', label: '质检' },
  { key: 'storyboard', label: '分镜生成' },
]

const QA_FIX_STATUS_META: Record<string, { label: string; tone: string }> = {
  pending: { label: '待处理', tone: 'bg-slate-800 text-slate-300' },
  fixing: { label: '修复中', tone: 'bg-violet-900/40 text-violet-300' },
  rechecking: { label: '复检中', tone: 'bg-indigo-900/40 text-indigo-300' },
  fixed: { label: '已修复', tone: 'bg-sky-900/40 text-sky-300' },
  recheck_passed: { label: '复检通过', tone: 'bg-emerald-900/40 text-emerald-300' },
  recheck_failed: { label: '复检仍失败', tone: 'bg-rose-900/40 text-rose-300' },
  rolled_back: { label: '已回滚', tone: 'bg-amber-900/40 text-amber-300' },
}

const QA_RECHECK_STATUS_META: Record<string, { label: string; tone: string }> = {
  not_run: { label: '未复检', tone: 'text-slate-500' },
  running: { label: '后台复检中', tone: 'text-indigo-300' },
  passed: { label: '复检通过', tone: 'text-emerald-300' },
  failed: { label: '复检失败', tone: 'text-rose-300' },
  error: { label: '复检异常', tone: 'text-amber-300' },
}

function getQaAutoFixFailureMeta(kind: string | undefined) {
  switch (String(kind || '').trim()) {
    case 'safety_guard_blocked':
      return { label: '安全护栏拦截', tone: 'border-amber-700/60 bg-amber-950/30 text-amber-200' }
    case 'stopped_after_failed_rechecks':
      return { label: '连续失败已停手', tone: 'border-rose-700/60 bg-rose-950/30 text-rose-200' }
    case 'no_usable_option':
      return { label: '无可用方案', tone: 'border-slate-700 bg-slate-950/40 text-slate-300' }
    default:
      return { label: '自动修复失败', tone: 'border-rose-700/60 bg-rose-950/30 text-rose-200' }
  }
}

function getQaAutoFixFailureActionLabel(kind: string | undefined) {
  switch (String(kind || '').trim()) {
    case 'safety_guard_blocked':
      return '转人工预览'
    case 'stopped_after_failed_rechecks':
      return '转人工改写'
    case 'no_usable_option':
      return '尝试人工起草'
    default:
      return '查看并处理'
  }
}

const STEP_ORDER = PIPELINE_STEPS.map(s => s.key)

function statusFromBook(bs: string): number {
  const map: Record<string, number> = {
    imported: 0, ingested: 1, read: 1, bibeled: 2, portraited: 3,
    adapted: 4, outlined: 5, scripted: 6, checked: 7, storyboarded: 8,
  }
  return map[bs] ?? 0
}

type Step = 'script' | 'storyboard' | 'visual' | 'export'
const STEPS: { key: Step; label: string; icon: string }[] = [
  { key: 'script', label: '内容准备', icon: '📝' },
  { key: 'storyboard', label: '分镜生产', icon: '🎬' },
  { key: 'visual', label: '视觉资产', icon: '🎨' },
  { key: 'export', label: '导出', icon: '📥' },
]
const PENDING_VISUAL_REFERENCE_TASKS_KEY_PREFIX = 'production-mode.pending-visual-reference-tasks'
const PENDING_STORYBOARD_TASKS_KEY_PREFIX = 'production-mode.pending-storyboard-tasks'

function getPendingVisualReferenceTasksStorageKey(bookId: number) {
  return `${PENDING_VISUAL_REFERENCE_TASKS_KEY_PREFIX}.${bookId}`
}

function getVisualAssetPendingTaskKey(assetType: VisualAssetType, assetId: string | number) {
  return `${assetType}:${String(assetId)}`
}

function readPendingVisualReferenceTasks(bookId: number): PendingVisualReferenceTask[] {
  if (typeof window === 'undefined' || !window.localStorage) return []
  try {
    const raw = window.localStorage.getItem(getPendingVisualReferenceTasksStorageKey(bookId))
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item): item is PendingVisualReferenceTask => (
      item
      && typeof item === 'object'
      && typeof item.taskId === 'string'
      && typeof item.assetType === 'string'
      && typeof item.assetId === 'string'
    ))
  } catch {
    return []
  }
}

function writePendingVisualReferenceTasks(bookId: number, tasks: PendingVisualReferenceTask[]) {
  if (typeof window === 'undefined' || !window.localStorage) return
  if (tasks.length === 0) {
    window.localStorage.removeItem(getPendingVisualReferenceTasksStorageKey(bookId))
    return
  }
  window.localStorage.setItem(getPendingVisualReferenceTasksStorageKey(bookId), JSON.stringify(tasks))
}

function upsertPendingVisualReferenceTask(bookId: number, task: PendingVisualReferenceTask) {
  const current = readPendingVisualReferenceTasks(bookId)
  const next = [
    task,
    ...current.filter((item) => item.taskId !== task.taskId && getVisualAssetPendingTaskKey(item.assetType, item.assetId) !== getVisualAssetPendingTaskKey(task.assetType, task.assetId)),
  ]
  writePendingVisualReferenceTasks(bookId, next)
  return next
}

function removePendingVisualReferenceTask(bookId: number, taskId: string) {
  const current = readPendingVisualReferenceTasks(bookId)
  const next = current.filter((item) => item.taskId !== taskId)
  writePendingVisualReferenceTasks(bookId, next)
  return next
}

function buildPendingVisualReferenceTaskMap(tasks: PendingVisualReferenceTask[]) {
  const entries = [...tasks].sort((left, right) => String(right.updatedAt || '').localeCompare(String(left.updatedAt || '')))
  const result: Record<string, string> = {}
  for (const item of entries) {
    const key = getVisualAssetPendingTaskKey(item.assetType, item.assetId)
    if (!result[key]) {
      result[key] = item.taskId
    }
  }
  return result
}

function getPendingStoryboardTasksStorageKey(bookId: number) {
  return `${PENDING_STORYBOARD_TASKS_KEY_PREFIX}.${bookId}`
}

function getStoryboardPendingTaskKey(episode: number, shotId: string | number, kind: StoryboardTaskKind) {
  return `${episode}:${String(shotId)}:${kind}`
}

function readPendingStoryboardTasks(bookId: number): PendingStoryboardTask[] {
  if (typeof window === 'undefined' || !window.localStorage) return []
  try {
    const raw = window.localStorage.getItem(getPendingStoryboardTasksStorageKey(bookId))
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item): item is PendingStoryboardTask => (
      item
      && typeof item === 'object'
      && typeof item.taskId === 'string'
      && typeof item.episode === 'number'
      && typeof item.shotId === 'string'
      && (item.kind === 'frame' || item.kind === 'video')
    ))
  } catch {
    return []
  }
}

function writePendingStoryboardTasks(bookId: number, tasks: PendingStoryboardTask[]) {
  if (typeof window === 'undefined' || !window.localStorage) return
  if (tasks.length === 0) {
    window.localStorage.removeItem(getPendingStoryboardTasksStorageKey(bookId))
    return
  }
  window.localStorage.setItem(getPendingStoryboardTasksStorageKey(bookId), JSON.stringify(tasks))
}

function upsertPendingStoryboardTask(bookId: number, task: PendingStoryboardTask) {
  const current = readPendingStoryboardTasks(bookId)
  const next = [
    task,
    ...current.filter((item) => item.taskId !== task.taskId && getStoryboardPendingTaskKey(item.episode, item.shotId, item.kind) !== getStoryboardPendingTaskKey(task.episode, task.shotId, task.kind)),
  ]
  writePendingStoryboardTasks(bookId, next)
  return next
}

function removePendingStoryboardTask(bookId: number, taskId: string) {
  const current = readPendingStoryboardTasks(bookId)
  const next = current.filter((item) => item.taskId !== taskId)
  writePendingStoryboardTasks(bookId, next)
  return next
}

function buildPendingStoryboardTaskMap(tasks: PendingStoryboardTask[]) {
  const entries = [...tasks].sort((left, right) => String(right.updatedAt || '').localeCompare(String(left.updatedAt || '')))
  const result: Record<string, string> = {}
  for (const item of entries) {
    const key = getStoryboardPendingTaskKey(item.episode, item.shotId, item.kind)
    if (!result[key]) {
      result[key] = item.taskId
    }
  }
  return result
}

function getMakeupScopeTone(scope: string | undefined) {
  switch (scope) {
    case 'base_identity':
      return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
    case 'episode_default':
      return 'border-sky-500/40 bg-sky-500/10 text-sky-200'
    case 'scene_variant':
      return 'border-fuchsia-500/40 bg-fuchsia-500/10 text-fuchsia-200'
    case 'shot_variant':
      return 'border-amber-500/40 bg-amber-500/10 text-amber-200'
    default:
      return 'border-slate-600/60 bg-slate-800/60 text-slate-200'
  }
}

export function formatProductionMakeupScopeLabel(scopeLabel: string | undefined, makeupScope?: string) {
  const explicit = String(scopeLabel || '').trim()
  const normalizedScope = String(makeupScope || '').trim().toLowerCase()

  if (normalizedScope === 'base_identity') return '基础定妆'
  if (normalizedScope === 'episode_default') return '分集默认'
  if (normalizedScope === 'scene_variant') return '场景变体'
  if (normalizedScope === 'shot_variant') return '分镜精调'

  if (explicit.includes('基础定妆')) return '基础定妆'
  if (explicit.includes('分集默认')) return '分集默认'
  if (explicit.includes('场景变体')) return '场景变体'
  if (explicit.includes('分镜精调')) return '分镜精调'

  return explicit || '定妆'
}

export function formatProductionMakeupStageLabel(stageName: string | undefined, makeupScope?: string) {
  const text = String(stageName || '').trim()
  const lowered = text.toLowerCase()
  const normalizedScope = String(makeupScope || '').trim().toLowerCase()

  if (!text) {
    if (normalizedScope === 'base_identity') return '基础身份阶段'
    return ''
  }

  if (lowered === 'base_identity' || normalizedScope === 'base_identity') return '基础身份阶段'

  const episodeMatch = lowered.match(/^episode_(\d+)_default$/)
  if (episodeMatch) return `第${episodeMatch[1]}集默认造型`

  const shotMatch = text.match(/^shot_(\d+)_(.+)$/i)
  if (shotMatch) return `镜头 ${shotMatch[1]} · ${shotMatch[2].replace(/_/g, ' ')}`

  return text
}

export function formatProductionMakeupVersionLabel(scopeLabel: string | undefined, stageName: string | undefined, makeupScope?: string) {
  const normalizedScopeLabel = formatProductionMakeupScopeLabel(scopeLabel, makeupScope)
  const normalizedStageLabel = formatProductionMakeupStageLabel(stageName, makeupScope)
  return normalizedStageLabel ? `${normalizedScopeLabel} / ${normalizedStageLabel}` : normalizedScopeLabel
}

function groupMakeupsByEpisodeAndCharacter(makeups: any[]) {
  const episodeGroups: Record<number, Record<string, any[]>> = {}
  for (const makeup of makeups || []) {
    const episode = Number(makeup?.episode ?? 0) || 0
    const characterName = String(makeup?.character_name ?? '未命名角色').trim() || '未命名角色'
    if (!episodeGroups[episode]) episodeGroups[episode] = {}
    if (!episodeGroups[episode][characterName]) episodeGroups[episode][characterName] = []
    episodeGroups[episode][characterName].push(makeup)
  }

  for (const characterGroups of Object.values(episodeGroups)) {
    for (const items of Object.values(characterGroups)) {
      items.sort((left: any, right: any) => {
        const scopeOrder: Record<string, number> = {
          base_identity: 0,
          episode_default: 1,
          scene_variant: 2,
          shot_variant: 3,
          custom_variant: 4,
        }
        const leftScope = scopeOrder[String(left?.makeup_scope ?? '')] ?? 9
        const rightScope = scopeOrder[String(right?.makeup_scope ?? '')] ?? 9
        if (leftScope !== rightScope) return leftScope - rightScope
        return String(left?.stage_name ?? '').localeCompare(String(right?.stage_name ?? ''))
      })
    }
  }

  return episodeGroups
}

export function getActiveMakeupReferenceSourceLabel(referenceSource: string | undefined, makeupScope?: string) {
  if (referenceSource === 'base_identity') return '基础定妆回退'
  if (referenceSource === 'missing') return '未绑定参考图'

  const normalizedScope = String(makeupScope || '').trim()
  if (referenceSource === 'active_variant' || referenceSource === 'resolved_makeup') {
    if (normalizedScope === 'episode_default') return '当前分集默认定妆'
    if (normalizedScope === 'base_identity') return '基础定妆'
    return '当前精调定妆'
  }

  return '未绑定参考图'
}

function getStoryboardFailureMeta(failureKind: string | undefined) {
  switch (String(failureKind || '').trim()) {
    case 'llm_truncated':
      return {
        label: 'LLM 截断',
        tone: 'border-amber-700/70 bg-amber-950/20 text-amber-200',
      }
    case 'structure_invalid':
      return {
        label: '结构化失败',
        tone: 'border-fuchsia-700/70 bg-fuchsia-950/20 text-fuchsia-200',
      }
    case 'missing_script':
      return {
        label: '缺少剧本',
        tone: 'border-sky-700/70 bg-sky-950/20 text-sky-200',
      }
    default:
      return {
        label: '普通异常',
        tone: 'border-rose-700/70 bg-rose-950/20 text-rose-200',
      }
  }
}

function getStoryboardEpisodeNextStep(item: any) {
  const failureKind = String(item?.failure_kind || '').trim()
  const hasResumeAnchor = Boolean(String(item?.last_completed_scene_name || '').trim())
  const fallbackCount = Number(item?.fallback_scene_count ?? 0)

  if (item?.status === 'done' && fallbackCount > 0) {
    return '建议优先复核已降级为保底分镜的场景。'
  }
  if (item?.status !== 'error') {
    return ''
  }
  if (failureKind === 'llm_truncated' && hasResumeAnchor) {
    return '推荐从最近完成场景之后继续，避免重复生成前面已成功的部分。'
  }
  if (failureKind === 'llm_truncated') {
    return '推荐先只重试这一集；若连续失败，再缩小范围检查该集剧本。'
  }
  if (failureKind === 'structure_invalid') {
    return '建议先检查该集剧本分段和场景结构，再重试。'
  }
  if (failureKind === 'missing_script') {
    return '需要先回到内容准备补齐这一集剧本。'
  }
  return '建议先只重试这一集；如果仍失败，再检查该集剧本和提示词上下文。'
}

function getWorkflowFeedbackMeta(status: WorkflowFeedbackStatus) {
  switch (status) {
    case 'success':
    case 'done':
      return {
        tone: 'border-emerald-800 bg-emerald-950/40 text-emerald-200',
        labelTone: 'text-emerald-300',
      }
    case 'error':
      return {
        tone: 'border-rose-800 bg-rose-950/40 text-rose-200',
        labelTone: 'text-rose-300',
      }
    case 'warning':
    case 'partial':
      return {
        tone: 'border-amber-800 bg-amber-950/40 text-amber-100',
        labelTone: 'text-amber-300',
      }
    case 'loading':
    case 'running':
      return {
        tone: 'border-sky-800 bg-sky-950/40 text-sky-100',
        labelTone: 'text-sky-300',
      }
    case 'info':
      return {
        tone: 'border-indigo-800 bg-indigo-950/40 text-indigo-100',
        labelTone: 'text-indigo-300',
      }
    default:
      return {
        tone: 'border-slate-800 bg-slate-950/60 text-slate-200',
        labelTone: 'text-slate-400',
      }
  }
}

function getStoryboardBatchModeLabel(mode: string) {
  switch (mode) {
    case 'compile':
      return '批量编译反馈'
    case 'frame':
      return '批量首帧反馈'
    case 'video':
      return '批量视频反馈'
    default:
      return '分镜批处理反馈'
  }
}

function getVisualBatchScopeLabel(scope: string) {
  switch (scope) {
    case 'scene':
      return '场景批量参考图'
    case 'prop':
      return '道具批量参考图'
    case 'character':
      return '角色批量参考图'
    default:
      return '视觉资产批处理'
  }
}

function WorkflowFeedbackBanner({
  status,
  title,
  message,
  hint,
  className = '',
}: {
  status: WorkflowFeedbackStatus
  title: string
  message?: string
  hint?: string
  className?: string
}) {
  if (!message && !hint) return null
  const meta = getWorkflowFeedbackMeta(status)
  return (
    <div className={`rounded-lg border px-3 py-2 text-xs ${meta.tone} ${className}`.trim()}>
      <div className={`font-semibold ${meta.labelTone}`}>{title}</div>
      {message ? <div className="mt-1 leading-5">{message}</div> : null}
      {hint ? <div className="mt-1 text-[11px] text-slate-400">{hint}</div> : null}
    </div>
  )
}

function InlineConfirmBar({
  title,
  message,
  confirmLabel,
  cancelLabel = '取消',
  busy = false,
  onConfirm,
  onCancel,
  className = '',
}: {
  title: string
  message: string
  confirmLabel: string
  cancelLabel?: string
  busy?: boolean
  onConfirm: () => void | Promise<void>
  onCancel: () => void
  className?: string
}) {
  return (
    <div className={`rounded-lg border border-rose-800/70 bg-rose-950/30 px-3 py-3 text-xs text-rose-100 ${className}`.trim()}>
      <div className="font-semibold text-rose-200">{title}</div>
      <div className="mt-1 leading-5 text-rose-100/90">{message}</div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => { void onConfirm() }}
          disabled={busy}
          className="rounded-lg border border-rose-600 bg-rose-900/50 px-3 py-1.5 text-xs font-semibold text-rose-100 transition hover:border-rose-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy ? '处理中...' : confirmLabel}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
        >
          {cancelLabel}
        </button>
      </div>
    </div>
  )
}

export function buildActiveMakeupVariants(shot: any) {
  const compiledCharacterVariants = Array.isArray(shot?.prompt_compile_context?.character_variants)
    ? shot.prompt_compile_context.character_variants
    : []

  if (compiledCharacterVariants.length > 0) {
    return compiledCharacterVariants
  }

  if (!Array.isArray(shot?.makeup_prompts)) {
    return []
  }

  return shot.makeup_prompts.map((makeup: any) => {
    const makeupScope = String(makeup?.makeup_scope || '').trim()
    const hasReference = Array.isArray(makeup?.reference_images) && makeup.reference_images.length > 0
    const referenceSource = hasReference
      ? (makeupScope === 'base_identity' ? 'base_identity' : 'resolved_makeup')
      : 'missing'

    return {
      asset_id: makeup?.id,
      asset_name: makeup?.character_name,
      character_name: makeup?.character_name,
      scope_label: formatProductionMakeupScopeLabel(makeup?.scope_label, makeupScope),
      stage_name: formatProductionMakeupStageLabel(makeup?.stage_name, makeupScope),
      makeup_scope: makeupScope,
      reference_source: referenceSource,
    }
  })
}

// --- Component ---
export default function ProductionMode({ book, bookData, onRefresh, onBookChange, onSwitchToDev, onOpenPrototype }: Props) {
  const [activeModule, setActiveModule] = useState<ActiveModule>('script')
  const [outputTab, setOutputTab] = useState<OutputTab>('bible')
  const [portrait, setPortrait] = useState('')
  const [visualData, setVisualData] = useState<any>(null)
  const [scriptEpisode, setScriptEpisode] = useState(1)
  const [runState, setRunState] = useState<RunState>('idle')
  const [qaData, setQaData] = useState<any[]>([])
  const [qaWorkbench, setQaWorkbench] = useState<any[]>([])
  const [qaWorkbenchState, setQaWorkbenchState] = useState<{ status: 'idle' | 'loading' | 'info' | 'success' | 'error'; message: string }>({
    status: 'idle',
    message: '',
  })
  const [qaFixOptionsByIssue, setQaFixOptionsByIssue] = useState<Record<string, any[]>>({})
  const [qaPatchDrafts, setQaPatchDrafts] = useState<Record<string, string>>({})
  const [qaPreviewByIssue, setQaPreviewByIssue] = useState<Record<string, { diff_text: string; patched_text: string; option_id?: string }>>({})
  const [qaSelectedOptionByIssue, setQaSelectedOptionByIssue] = useState<Record<string, string>>({})
  const [qaOpenLocations, setQaOpenLocations] = useState<Record<string, boolean>>({})
  const [qaBusyMap, setQaBusyMap] = useState<Record<string, boolean>>({})
  const [qaAutoFixReportsByEpisode, setQaAutoFixReportsByEpisode] = useState<Record<number, any>>({})
  const [qaFocusedIssueId, setQaFocusedIssueId] = useState<string | null>(null)
  const [qaPendingRollback, setQaPendingRollback] = useState<{ episode: number; versionId: number; versionLabel: string } | null>(null)
  const [storyboardData, setStoryboardData] = useState<any[]>([])
  const [selectedSBEps, setSelectedSBEps] = useState<Set<number>>(new Set())
  const [progress, setProgress] = useState(0)
  const [currentStep, setCurrentStep] = useState('')
  const [sbRunState, setSbRunState] = useState<RunState>('idle')
  const [sbProgress, setSbProgress] = useState(0)
  const [sbStep, setSbStep] = useState('')
  const [sbTaskDetail, setSbTaskDetail] = useState<any | null>(null)
  const sbPollRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const qaIssueCardRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const [vsRunState, setVsRunState] = useState<RunState>('idle')
  const [vsProgress, setVsProgress] = useState(0)
  const [vsStep, setVsStep] = useState('')
  const [taskId, setTaskId] = useState<string | null>(null)
  const [modelDefaults, setModelDefaults] = useState<ModelRegistryPayload['default_profiles']>({})
  const [modelDefaultsState, setModelDefaultsState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [modelRegistryOpen, setModelRegistryOpen] = useState(false)
  const [modelRegistryData, setModelRegistryData] = useState<ModelRegistryPayload | null>(null)
  const [modelRegistryError, setModelRegistryError] = useState<string | null>(null)
  const [pendingVisualReferenceTasks, setPendingVisualReferenceTasks] = useState<PendingVisualReferenceTask[]>([])
  const [pendingStoryboardTasks, setPendingStoryboardTasks] = useState<PendingStoryboardTask[]>([])
  const [autoRecoveringVisualReferenceTaskIds, setAutoRecoveringVisualReferenceTaskIds] = useState<string[]>([])
  const [autoRecoveringStoryboardTaskIds, setAutoRecoveringStoryboardTaskIds] = useState<string[]>([])
  const [visualReferenceRecoveryMeta, setVisualReferenceRecoveryMeta] = useState<Record<string, VisualReferenceRecoveryMeta>>({})
  const [storyboardRecoveryMeta, setStoryboardRecoveryMeta] = useState<Record<string, VisualReferenceRecoveryMeta>>({})
  const autoRecoveringTaskIdsRef = useRef<Set<string>>(new Set())
  const attemptedAutoRecoverTaskIdsRef = useRef<Set<string>>(new Set())
  const autoRecoveringStoryboardTaskIdsRef = useRef<Set<string>>(new Set())
  const attemptedAutoRecoverStoryboardTaskIdsRef = useRef<Set<string>>(new Set())

  // Config
  // Input source
  const [inputMode, setInputMode] = useState<'book' | 'upload' | 'text'>('book')
  const [textInput, setTextInput] = useState('')

  const [genre, setGenre] = useState('short_drama')
  const [availableGenres, setAvailableGenres] = useState<string[]>([])
  const [episodeCount, setEpisodeCount] = useState(1)
  const [episodeDuration, setEpisodeDuration] = useState(3)
  const [scope, setScope] = useState<'auto' | 'first_n' | 'all'>('auto')
  const [scopeChapters, setScopeChapters] = useState(30)
  const [showAdvanced, setShowAdvanced] = useState(false)

  // 改编方向
  const [genreSubtype, setGenreSubtype] = useState('')
  const [toneTags, setToneTags] = useState<string[]>([])
  const [adaptDirection, setAdaptDirection] = useState('')

  const TONE_PRESETS = [
    { group: '剧情基调', items: ['高甜', '虐心', '爽文', '搞笑', '暗黑', '治愈', '热血'] },
    { group: '风格偏好', items: ['节奏紧凑', '细节丰富', '剧情反转多', '台词精炼', '情感细腻'] },
    { group: '角色偏好', items: ['大女主', '群像戏', '恋爱线为主', '事业线为主', '反派智商在线'] },
  ]

  const DURATION_OPTIONS = [
    { value: 1, label: '约 1 分钟 / 集（小程序短剧）' },
    { value: 3, label: '约 3 分钟 / 集（标准竖屏短剧）' },
    { value: 5, label: '约 5 分钟 / 集（精品短剧）' },
    { value: 10, label: '约 10 分钟 / 集（网剧规格）' },
  ]

  const toggleTone = (tag: string) => {
    setToneTags(prev =>
      prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]
    )
  }

  // Outputs from DB
  const [bible, setBible] = useState('')
  const [outlines, setOutlines] = useState<any[]>([])
  const [scripts, setScripts] = useState<any[]>([])
  const [maxScriptEp, setMaxScriptEp] = useState(0)
  const [currentScript, setCurrentScript] = useState('')

  // Edit states
  const [editingBible, setEditingBible] = useState(false)
  const [bibleDraft, setBibleDraft] = useState('')
  const [editingOutline, setEditingOutline] = useState<number | null>(null)
  const [outlineDrafts, setOutlineDrafts] = useState<Record<number, any>>({})
  const [editingScript, setEditingScript] = useState(false)
  const [scriptDraft, setScriptDraft] = useState('')
  const [savingMap, setSavingMap] = useState<Record<string, boolean>>({})
  const [storyboardBatchState, setStoryboardBatchState] = useState<{ mode: string; status: 'idle' | 'running' | 'done' | 'error'; message: string }>({
    mode: '',
    status: 'idle',
    message: '',
  })
  const [activeShotKey, setActiveShotKey] = useState<string | null>(null)
  const [exportRecords, setExportRecords] = useState<any[]>([])
  const [exportActionState, setExportActionState] = useState<{ status: 'idle' | 'running' | 'done' | 'error'; message: string }>({
    status: 'idle',
    message: '',
  })
  const [visualBatchState, setVisualBatchState] = useState<{
    scope: string
    status: 'idle' | 'running' | 'done' | 'error'
    message: string
    entries: VisualBatchEntry[]
  }>({
    scope: '',
    status: 'idle',
    message: '',
    entries: [],
  })

  const fetchOutputs = useCallback(async () => {
    try {
      const res = await fetch(`/api/pipeline/book/${book.id}/outputs?genre=${encodeURIComponent(genre)}`)
      const data = await res.json()
      if (data.genres) { setAvailableGenres(data.genres) }
      if (data.bible) { setBible(data.bible); setBibleDraft(data.bible); setEditingBible(false) }
      if (data.portrait) { setPortrait(data.portrait) }
      if (data.visual) { setVisualData(data.visual) }
      if (data.outlines) { setOutlines(data.outlines) }
      if (data.qa) { setQaData(data.qa) }
      if (data.storyboard) { setStoryboardData(data.storyboard) }
      // Init storyboard episode selection
      if (data.scripts && data.scripts.length > 0) {
        const allEps: Set<number> = new Set(data.scripts.map((s: any) => s.episode))
        setSelectedSBEps((prev: Set<number>): Set<number> => {
          if (prev.size === 0) return allEps
          for (const ep of prev) { if (!allEps.has(ep)) return allEps }
          return prev
        })
      }
      if (data.scripts) {
        setScripts(data.scripts)
        const maxEp = Math.max(...data.scripts.map((s: any) => s.episode), 0)
        setMaxScriptEp(maxEp)
        const cur = data.scripts.find((s: any) => s.episode === scriptEpisode)
        if (cur) { setCurrentScript(cur.content); setScriptDraft(cur.content) }
      }
      return data
    } catch (e) {
      console.warn('fetchOutputs failed:', e)
      return null
    }
  }, [book.id, scriptEpisode, genre])

  const fetchExportRecords = useCallback(async () => {
    try {
      const response = await fetch(`/api/books/${book.id}/export-records`)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const payload = await response.json()
      setExportRecords(Array.isArray(payload.records) ? payload.records : [])
    } catch (error) {
      console.warn('fetchExportRecords failed:', error)
      setExportRecords([])
    }
  }, [book.id])

  const getLegacyRecordSummary = useCallback((record: any) => {
    const summarySource = String(record?.summary || '').trim()
    const hasBrokenSeparator = /\s[路璺]\s/.test(summarySource)
    if (summarySource && !isLikelyCorruptedDeliveryText(summarySource) && !hasBrokenSeparator) {
      return summarySource
    }

    const metaInfo = record?.meta_info && typeof record.meta_info === 'object' ? record.meta_info : {}
    const blockedShotIds = Array.isArray(metaInfo.blockedShotIds)
      ? metaInfo.blockedShotIds.map((item: unknown) => String(item))
      : []
    const blockedReasons = Array.isArray(metaInfo.blocked_reasons)
      ? metaInfo.blocked_reasons.map((item: unknown) => String(item))
      : Array.isArray(metaInfo.issues)
        ? metaInfo.issues.map((item: unknown) => String(item))
        : []

    const episodeFromMeta = Number(metaInfo.episode ?? 0)
    const episodeFromShotId = blockedShotIds
      .map((item: string) => {
        const match = item.match(/^(\d+)-/)
        return match ? Number(match[1]) : 0
      })
      .find((episode: number) => episode > 0)

    return summarizeDeliveryRecordHistory({
      episode: episodeFromMeta || episodeFromShotId || 0,
      scriptStatusLabel:
        typeof metaInfo.script_status === 'string' && metaInfo.script_status.trim()
          ? metaInfo.script_status.trim()
          : null,
      deliverableShots: Number(record?.deliverable_shots ?? 0),
      totalShots: Number(record?.total_shots ?? 0),
      pendingReviewShots: Number(record?.pending_review_shots ?? 0),
      blockedReasons: blockedReasons.filter((item: string) => !isLikelyCorruptedDeliveryText(item)),
      exportFormat: String(record?.export_format || '').trim() || normalizeDeliveryRecordFormatLabel('json'),
      status: record?.status === 'completed' ? 'completed' : 'blocked',
    })
  }, [])

  const fetchQaWorkbench = useCallback(async () => {
    try {
      setQaWorkbenchState({ status: 'loading', message: '' })
      const response = await fetch(`/api/books/${book.id}/qa/workbench`)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const payload = await response.json()
      setQaWorkbench(Array.isArray(payload.episodes) ? payload.episodes : [])
      setQaWorkbenchState({ status: 'idle', message: '' })
    } catch (error: any) {
      console.warn('fetchQaWorkbench failed:', error)
      setQaWorkbench([])
      setQaWorkbenchState({ status: 'error', message: error?.message || '加载质检修复工作台失败' })
    }
  }, [book.id])

  const pollQaWorkbenchUntilStable = useCallback(async (episode: number, timeoutMs = 90000) => {
    const startedAt = Date.now()
    while (Date.now() - startedAt < timeoutMs) {
      const response = await fetch(`/api/books/${book.id}/qa/workbench`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const payload = await response.json()
      const episodes = Array.isArray(payload.episodes) ? payload.episodes : []
      setQaWorkbench(episodes)
      setQaWorkbenchState({ status: 'idle', message: '' })
      const current = episodes.find((item: any) => item.episode === episode)
      const hasRunningIssue = Array.isArray(current?.issues) && current.issues.some((item: any) => item.fix_status === 'rechecking')
      const hasRunningVersion = Array.isArray(current?.versions) && current.versions.some((item: any) => item.recheck_status === 'running')
      if (!hasRunningIssue && !hasRunningVersion) return
      await new Promise((resolve) => window.setTimeout(resolve, 2500))
    }
    throw new Error('QA 复检超时，请稍后手动刷新查看结果。')
  }, [book.id])

  const syncQaEpisode = useCallback(async (episode: number) => {
    setQaBusyMap((prev) => ({ ...prev, [`sync-${episode}`]: true }))
    try {
      const response = await fetch(`/api/books/${book.id}/qa/episodes/${episode}/sync`, { method: 'POST' })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      await fetchQaWorkbench()
    } finally {
      setQaBusyMap((prev) => ({ ...prev, [`sync-${episode}`]: false }))
    }
  }, [book.id, fetchQaWorkbench])

  const recheckQaEpisode = useCallback(async (episode: number) => {
    setQaBusyMap((prev) => ({ ...prev, [`recheck-${episode}`]: true }))
    try {
      const response = await fetch(`/api/books/${book.id}/qa/episodes/${episode}/recheck`, { method: 'POST' })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      await fetchOutputs()
      setQaWorkbenchState({ status: 'info', message: `第 ${episode} 集已开始后台复检，结果会自动刷新。` })
      await pollQaWorkbenchUntilStable(episode)
    } finally {
      setQaBusyMap((prev) => ({ ...prev, [`recheck-${episode}`]: false }))
    }
  }, [book.id, fetchOutputs, pollQaWorkbenchUntilStable])

  const generateQaFixOptions = useCallback(async (issue: any) => {
    setQaBusyMap((prev) => ({ ...prev, [`options-${issue.issue_id}`]: true }))
    try {
      const response = await fetch(`/api/books/${book.id}/qa/issues/${issue.issue_id}/generate-fix-options`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: issue.fix_mode || 'semi_auto' }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const payload = await response.json()
      const options = Array.isArray(payload.options) ? payload.options : []
      setQaFixOptionsByIssue((prev) => ({ ...prev, [issue.issue_id]: options }))
      setQaSelectedOptionByIssue((prev) => ({ ...prev, [issue.issue_id]: options[0]?.id || '' }))
      setQaPatchDrafts((prev) => ({
        ...prev,
        [issue.issue_id]: prev[issue.issue_id] || options[0]?.patched_text || issue.source_excerpt || '',
      }))
      setQaPreviewByIssue((prev) => {
        const next = { ...prev }
        delete next[issue.issue_id]
        return next
      })
      await fetchQaWorkbench()
    } finally {
      setQaBusyMap((prev) => ({ ...prev, [`options-${issue.issue_id}`]: false }))
    }
  }, [book.id, fetchQaWorkbench])

  const previewQaFix = useCallback(async (issue: any) => {
    const patchedText = (qaPatchDrafts[issue.issue_id] || '').trim()
    if (!patchedText) {
      setQaFocusedIssueId(issue.issue_id)
      setQaWorkbenchState({ status: 'error', message: '请先生成修复方案，或手动填写修复片段。' })
      return
    }
    setQaBusyMap((prev) => ({ ...prev, [`preview-${issue.issue_id}`]: true }))
    try {
      const response = await fetch(`/api/books/${book.id}/qa/issues/${issue.issue_id}/preview-fix`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: issue.fix_mode || 'manual',
          patchedText,
          optionId: qaSelectedOptionByIssue[issue.issue_id] || '',
        }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const payload = await response.json()
      setQaPreviewByIssue((prev) => ({ ...prev, [issue.issue_id]: payload }))
    } finally {
      setQaBusyMap((prev) => ({ ...prev, [`preview-${issue.issue_id}`]: false }))
    }
  }, [book.id, qaPatchDrafts, qaSelectedOptionByIssue])

  const applyQaFix = useCallback(async (issue: any) => {
    const patchedText = (qaPatchDrafts[issue.issue_id] || '').trim()
    if (!patchedText) {
      setQaFocusedIssueId(issue.issue_id)
      setQaWorkbenchState({ status: 'error', message: '请先生成修复方案，或手动填写修复片段。' })
      return
    }
    const preview = qaPreviewByIssue[issue.issue_id]
    if (!preview || preview.patched_text !== patchedText) {
      setQaFocusedIssueId(issue.issue_id)
      setQaWorkbenchState({ status: 'error', message: '应用修复前请先预览 diff，确认本次改动。' })
      return
    }
    setQaBusyMap((prev) => ({ ...prev, [`apply-${issue.issue_id}`]: true }))
    try {
      const response = await fetch(`/api/books/${book.id}/qa/issues/${issue.issue_id}/apply-fix`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: issue.fix_mode || 'manual',
          patchedText,
          changeReason: issue.title || issue.description,
          optionId: qaSelectedOptionByIssue[issue.issue_id] || '',
          rerunQa: true,
        }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      await fetchOutputs()
      setQaWorkbenchState({ status: 'success', message: `修复已保存，第 ${issue.episode} 集正在后台复检。` })
      await pollQaWorkbenchUntilStable(issue.episode)
      setQaPreviewByIssue((prev) => {
        const next = { ...prev }
        delete next[issue.issue_id]
        return next
      })
    } finally {
      setQaBusyMap((prev) => ({ ...prev, [`apply-${issue.issue_id}`]: false }))
    }
  }, [book.id, qaPatchDrafts, qaPreviewByIssue, qaSelectedOptionByIssue, fetchOutputs, pollQaWorkbenchUntilStable])

  const autoFixQaIssue = useCallback(async (issue: any) => {
    setQaBusyMap((prev) => ({ ...prev, [`autofix-${issue.issue_id}`]: true }))
    try {
      const response = await fetch(`/api/books/${book.id}/qa/issues/${issue.issue_id}/auto-fix`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: issue.fix_mode || 'auto',
          rerunQa: true,
          operatorName: 'auto-fixer',
        }),
      })
      if (!response.ok) {
        let detail = `HTTP ${response.status}`
        try {
          const payload = await response.json()
          detail = payload?.detail || detail
        } catch {}
        throw new Error(detail)
      }
      const payload = await response.json()
      if (payload?.selected_option?.patched_text) {
        setQaPatchDrafts((prev) => ({ ...prev, [issue.issue_id]: payload.selected_option.patched_text }))
      }
      await fetchOutputs()
      setQaWorkbenchState({ status: 'success', message: `已自动修复“${issue.title || issue.description}”，正在后台复检。` })
      await pollQaWorkbenchUntilStable(issue.episode)
    } catch (error: any) {
      setQaWorkbenchState({ status: 'error', message: error?.message || '自动修复失败' })
    } finally {
      setQaBusyMap((prev) => ({ ...prev, [`autofix-${issue.issue_id}`]: false }))
    }
  }, [book.id, fetchOutputs, pollQaWorkbenchUntilStable])

  const autoFixQaEpisode = useCallback(async (episode: number) => {
    setQaBusyMap((prev) => ({ ...prev, [`autofix-episode-${episode}`]: true }))
    try {
      const response = await fetch(`/api/books/${book.id}/qa/episodes/${episode}/auto-fix`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: 'auto',
          rerunQa: true,
          operatorName: 'auto-fixer',
          maxIssues: 10,
        }),
      })
      if (!response.ok) {
        let detail = `HTTP ${response.status}`
        try {
          const payload = await response.json()
          detail = payload?.detail || detail
        } catch {}
        throw new Error(detail)
      }
      const payload = await response.json()
      setQaWorkbenchState({
        status: 'success',
        message: `第 ${episode} 集已自动修复 ${payload.applied_count || 0} 个问题${payload.failed_count ? `，另有 ${payload.failed_count} 个未修复` : ''}，正在后台复检。`,
      })
      setQaAutoFixReportsByEpisode((prev) => ({ ...prev, [episode]: payload.report || null }))
      await fetchOutputs()
      await pollQaWorkbenchUntilStable(episode)
    } catch (error: any) {
      setQaWorkbenchState({ status: 'error', message: error?.message || '自动修复本集失败' })
    } finally {
      setQaBusyMap((prev) => ({ ...prev, [`autofix-episode-${episode}`]: false }))
    }
  }, [book.id, fetchOutputs, pollQaWorkbenchUntilStable])

  const routeQaAutoFixFailureToManual = useCallback(async (issue: any, failureKind?: string) => {
    setQaFocusedIssueId(issue.issue_id)
    setQaOpenLocations((prev) => ({ ...prev, [issue.issue_id]: true }))
    if (failureKind !== 'stopped_after_failed_rechecks') {
      try {
        await generateQaFixOptions(issue)
      } catch {}
    }
    const message =
      failureKind === 'safety_guard_blocked'
        ? '这条问题被安全护栏拦下了，已为你打开原文定位，并尝试生成人工可选修复方案。'
        : failureKind === 'stopped_after_failed_rechecks'
          ? '这条问题已经连续复检失败，系统已停手。建议你直接基于原文做人工改写。'
          : failureKind === 'no_usable_option'
            ? '系统没有生成出可靠方案，已为你打开原文定位，方便人工起草。'
            : '已为你打开原文定位，建议继续人工处理。'
    setQaWorkbenchState({ status: 'info', message })
  }, [generateQaFixOptions])

  useEffect(() => {
    if (!qaFocusedIssueId) return
    const target = qaIssueCardRefs.current[qaFocusedIssueId]
    if (!target) return
    target.scrollIntoView({ behavior: 'smooth', block: 'center' })
    const timer = window.setTimeout(() => setQaFocusedIssueId((current) => current === qaFocusedIssueId ? null : current), 2200)
    return () => window.clearTimeout(timer)
  }, [qaFocusedIssueId, qaWorkbench])

  const rollbackQaVersion = useCallback(async (episode: number, versionId: number) => {
    setQaBusyMap((prev) => ({ ...prev, [`rollback-${versionId}`]: true }))
    try {
      const response = await fetch(`/api/books/${book.id}/scripts/${episode}/versions/${versionId}/rollback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rerunQa: true }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      await fetchOutputs()
      setQaPendingRollback(null)
      setQaWorkbenchState({ status: 'success', message: `已提交回滚，第 ${episode} 集正在后台复检。` })
      await pollQaWorkbenchUntilStable(episode)
    } finally {
      setQaBusyMap((prev) => ({ ...prev, [`rollback-${versionId}`]: false }))
    }
  }, [book.id, fetchOutputs, pollQaWorkbenchUntilStable])

  useEffect(() => { fetchOutputs() }, [fetchOutputs])
  useEffect(() => { fetchExportRecords() }, [fetchExportRecords])
  useEffect(() => { fetchQaWorkbench() }, [fetchQaWorkbench])
  useEffect(() => { onRefresh() }, [])
  useEffect(() => {
    setPendingVisualReferenceTasks(readPendingVisualReferenceTasks(book.id))
    setPendingStoryboardTasks(readPendingStoryboardTasks(book.id))
    setAutoRecoveringVisualReferenceTaskIds([])
    setAutoRecoveringStoryboardTaskIds([])
    setVisualReferenceRecoveryMeta({})
    setStoryboardRecoveryMeta({})
    autoRecoveringTaskIdsRef.current.clear()
    attemptedAutoRecoverTaskIdsRef.current.clear()
    autoRecoveringStoryboardTaskIdsRef.current.clear()
    attemptedAutoRecoverStoryboardTaskIdsRef.current.clear()
  }, [book.id])
  useEffect(() => {
    if (storyboardData.length === 0) {
      setActiveShotKey(null)
      return
    }
    const availableKeys = new Set(storyboardData.map((shot: any) => `${shot.episode}-${shot.shot_id}`))
    setActiveShotKey((current) => {
      if (current && availableKeys.has(current)) {
        return current
      }
      const firstShot = storyboardData[0]
      return firstShot ? `${firstShot.episode}-${firstShot.shot_id}` : null
    })
  }, [storyboardData])
  // Visual data refresh helper
  const refreshVisualData = useCallback(async () => {
    try {
      const r = await fetch(`/api/pipeline/book/${book.id}/outputs?genre=${encodeURIComponent(genre)}`)
      const d = await r.json()
      setVisualData(d.visual || null)
    } catch { setVisualData(null) }
  }, [book.id, genre])

  const registerPendingVisualReferenceTask = useCallback((
    assetType: VisualAssetType,
    assetId: string | number,
    assetName: string,
    taskId: string,
  ) => {
    const next = upsertPendingVisualReferenceTask(book.id, {
      taskId,
      assetType,
      assetId: String(assetId),
      assetName,
      updatedAt: new Date().toISOString(),
    })
    setPendingVisualReferenceTasks(next)
  }, [book.id])

  const clearPendingVisualReferenceTask = useCallback((taskId: string) => {
    const next = removePendingVisualReferenceTask(book.id, taskId)
    setPendingVisualReferenceTasks(next)
  }, [book.id])

  const setVisualReferenceRecoveryState = useCallback((taskId: string, meta: VisualReferenceRecoveryMeta) => {
    setVisualReferenceRecoveryMeta((current) => ({
      ...current,
      [taskId]: meta,
    }))
  }, [])

  const registerPendingStoryboardTask = useCallback((
    episode: number,
    shotId: string | number,
    kind: StoryboardTaskKind,
    taskId: string,
  ) => {
    const next = upsertPendingStoryboardTask(book.id, {
      taskId,
      episode,
      shotId: String(shotId),
      kind,
      updatedAt: new Date().toISOString(),
    })
    setPendingStoryboardTasks(next)
  }, [book.id])

  const clearPendingStoryboardTask = useCallback((taskId: string) => {
    const next = removePendingStoryboardTask(book.id, taskId)
    setPendingStoryboardTasks(next)
  }, [book.id])

  const setStoryboardGenerationRecoveryState = useCallback((taskId: string, meta: VisualReferenceRecoveryMeta) => {
    setStoryboardRecoveryMeta((current) => ({
      ...current,
      [taskId]: meta,
    }))
  }, [])

  const patchVisualAsset = useCallback(async (
    assetType: VisualAssetType,
    assetId: number,
    payload: VisualAssetPatchPayload,
  ) => {
    const response = await fetch(`/api/books/${book.id}/visual-assets/${assetType}/${assetId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const updated = await response.json()
    await refreshVisualData()
    await fetchOutputs()
    return updated
  }, [book.id, refreshVisualData, fetchOutputs])

  const createVisualReferenceAsset = useCallback(async (
    assetType: VisualAssetType,
    assetId: number,
    assetName: string,
    episode: number | null,
    payload: VisualReferenceCreatePayload,
  ) => {
    const response = await fetch(`/api/books/${book.id}/visual-reference-assets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        assetType,
        assetId: String(assetId),
        assetName,
        episode,
        imageUrl: payload.imageUrl,
        referenceToken: payload.referenceToken,
        status: payload.status,
        prompt: payload.prompt,
        model: payload.model,
        notes: payload.notes,
        metaInfo: payload.metaInfo,
      }),
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const created = await response.json() as VisualReferenceCreateResult
    await refreshVisualData()
    await fetchOutputs()
    return created
  }, [book.id, refreshVisualData, fetchOutputs])

  const patchVisualReferenceAsset = useCallback(async (
    referenceId: number,
    payload: VisualReferenceUpdatePayload,
  ) => {
    const response = await fetch(`/api/books/${book.id}/visual-reference-assets/${referenceId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const updated = await response.json() as VisualReferenceCreateResult
    await refreshVisualData()
    await fetchOutputs()
    return updated
  }, [book.id, refreshVisualData, fetchOutputs])

  const deleteVisualReferenceAsset = useCallback(async (referenceId: number) => {
    const response = await fetch(`/api/books/${book.id}/visual-reference-assets/${referenceId}`, {
      method: 'DELETE',
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const deleted = await response.json() as VisualReferenceDeleteResult
    await refreshVisualData()
    await fetchOutputs()
    return deleted
  }, [book.id, refreshVisualData, fetchOutputs])

  const getReferenceTokenFallback = useCallback((asset: any, assetName: string) => {
    const existing = String(asset?.jimeng_ref_name ?? '').trim()
    if (existing) return existing
    const slug = String(assetName ?? '')
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '-')
      .replace(/^-+|-+$/g, '')
    return slug ? `@${slug}` : `@asset-${asset?.id ?? 'ref'}`
  }, [])

  const getVisualAssetPrompt = useCallback((asset: any, assetName: string) => {
    const segments = [
      asset?.visual_prompt_zh,
      asset?.core_prompt_zh,
      asset?.scene_prompt_zh,
      asset?.outfit_prompt_zh,
      asset?.description,
      asset?.refined_outfit,
      asset?.refined_accessories,
      asset?.makeup_spec,
      asset?.hair_style,
      asset?.expression_mood,
      assetName,
    ]
      .map((item) => (typeof item === 'string' ? item.trim() : ''))
      .filter(Boolean)
    return Array.from(new Set(segments)).join('\n')
  }, [])

  const resolveRelatedShotsForAsset = useCallback((assetType: VisualAssetType, asset: any, assetName: string) => {
    const shotTokens = new Set(
      (Array.isArray(asset?.shot_ids) ? asset.shot_ids : [])
        .map((item: unknown) => String(item ?? '').trim())
        .filter(Boolean),
    )
    const matches = storyboardData.filter((shot: any) => {
      const shotId = String(shot?.shot_id ?? '').trim()
      const episode = Number(shot?.episode ?? 0)
      if (shotTokens.size > 0) {
        return (
          shotTokens.has(shotId)
          || shotTokens.has(`${episode}-${shotId}`)
          || shotTokens.has(`shot-${shotId}`)
        )
      }
      if (assetType === 'scene') {
        return String(shot?.scene_name ?? '').trim() === assetName
      }
      return false
    })

    if (matches.length > 0) {
      return matches.sort((a: any, b: any) => {
        const episodeDelta = Number(a?.episode ?? 0) - Number(b?.episode ?? 0)
        if (episodeDelta !== 0) return episodeDelta
        return Number(a?.shot_id ?? 0) - Number(b?.shot_id ?? 0)
      })
    }

    return storyboardData.length > 0 ? [storyboardData[0]] : []
  }, [storyboardData])

  const generateVisualReferenceAsset = useCallback(async (
    assetType: VisualAssetType,
    asset: any,
    assetName: string,
  ) => {
    const prompt = getVisualAssetPrompt(asset, assetName)
    if (!prompt) {
      throw new Error('当前资产还没有可用的提示词或描述')
    }

    const relatedShots = resolveRelatedShotsForAsset(assetType, asset, assetName)
    const seedShot = relatedShots[0]
    const episode = Number(asset?.episode ?? seedShot?.episode ?? 1)
    const shotId = String(seedShot?.shot_id ?? asset?.shot_ids?.[0] ?? '1')
    const assetScope = assetType === 'scene' ? 'location' : assetType
    const assetSubject = String(
      assetType === 'character'
        ? asset?.character_name ?? assetName
        : asset?.name ?? assetName,
    ).trim()

    const response = await fetch('/api/prototyping/generate-reference-image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bookId: book.id,
        episode,
        shotId,
        sourceNodeId: `visual-${assetType}-${asset.id}`,
        sourceAssetId: String(asset.id),
        assetScope,
        assetSubject,
        targetKind: 'image',
        prompt,
        negativePrompt: String(asset?.negative_prompt ?? '').trim(),
        aspectRatio: '1:1',
      }),
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      throw new Error(payload.detail || `HTTP ${response.status}`)
    }

    const task = await response.json()
    registerPendingVisualReferenceTask(assetType, asset.id, assetName, task.task_id)
    let completedTask: any
    try {
      completedTask = await waitForCreativeTask(task.task_id, {
        softTimeoutMs: 45000,
        softTimeoutMessage: '真实生成任务仍在 provider side 执行，已经超过当前等待窗口。请稍后点击“继续拉取结果”，不要重复新建任务。',
      })
    } catch (error) {
      if (error instanceof Error) {
        ;(error as Error & { taskId?: string }).taskId = task.task_id
      }
      throw error
    }
    const persistedReference = completedTask?.reference_asset
    if (persistedReference) {
      clearPendingVisualReferenceTask(task.task_id)
      await refreshVisualData()
      await fetchOutputs()
      return { ...persistedReference, taskId: task.task_id } as VisualReferenceCreateResult
    }
    const generatedAsset = completedTask?.asset
    const imageUrl = String(generatedAsset?.uri || generatedAsset?.previewUrl || '').trim()
    if (!imageUrl) {
      throw new Error('参考图任务已完成，但未返回图片地址')
    }

    const generatedAt = new Date().toISOString()
    const created = await createVisualReferenceAsset(assetType, asset.id, assetName, episode, {
      imageUrl,
      referenceToken: getReferenceTokenFallback(asset, assetName),
      status: 'selected',
      prompt: String(generatedAsset?.prompt || prompt),
      model: String(generatedAsset?.model || generatedAsset?.metadata?.modelName || ''),
      notes: `视觉资产库生成 · ${generatedAt.slice(0, 16).replace('T', ' ')}`,
      metaInfo: {
        source: 'visual-asset-library-generate',
        taskId: task.task_id,
        version: generatedAsset?.label || '',
        generatedAt,
        assetScope,
        assetSubject,
        usesMock: Boolean(completedTask?.uses_mock),
      },
    })
    clearPendingVisualReferenceTask(task.task_id)
    return { ...created, taskId: task.task_id }
  }, [
    book.id,
    clearPendingVisualReferenceTask,
    createVisualReferenceAsset,
    fetchOutputs,
    getReferenceTokenFallback,
    getVisualAssetPrompt,
    registerPendingVisualReferenceTask,
    refreshVisualData,
    resolveRelatedShotsForAsset,
    waitForCreativeTask,
  ])

  const recoverVisualReferenceGeneration = useCallback(async (taskId: string) => {
    const response = await fetch(`/api/prototyping/tasks/${taskId}/reconcile`, {
      method: 'POST',
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const payload = await response.json()
    if (payload.status === 'done') {
      clearPendingVisualReferenceTask(taskId)
      setVisualReferenceRecoveryState(taskId, {
        status: 'recovered',
        updatedAt: new Date().toISOString(),
        message: '已成功回收 provider 侧结果，并自动写入视觉资产库。',
      })
      await refreshVisualData()
      await fetchOutputs()
      return {
        ...(payload.reference_asset || {}),
        taskId,
        sync_warning: payload.reference_asset?.sync_warning || payload.asset?.metadata?.referenceSyncWarning,
      } as VisualReferenceCreateResult
    }
    if (payload.status === 'running') {
      setVisualReferenceRecoveryState(taskId, {
        status: 'waiting-provider',
        updatedAt: new Date().toISOString(),
        message: '任务还在 provider 侧执行，系统会继续等待，也可以稍后手动继续拉取结果。',
      })
      return {
        taskId,
        stillRunning: true,
      } satisfies VisualReferenceCreateResult
    }
    if (!isCreativeTaskRecoveryMessage(payload.error)) {
      clearPendingVisualReferenceTask(taskId)
    }
    setVisualReferenceRecoveryState(taskId, {
      status: isCreativeTaskRecoveryMessage(payload.error) ? 'waiting-provider' : 'failed',
      updatedAt: new Date().toISOString(),
      message: formatCreativeTaskMessage(payload.error, '结果回收失败'),
    })
    throw new Error(formatCreativeTaskMessage(payload.error, '结果回收失败'))
  }, [clearPendingVisualReferenceTask, fetchOutputs, refreshVisualData, setVisualReferenceRecoveryState])

  const pendingVisualReferenceTaskMap = useMemo(
    () => buildPendingVisualReferenceTaskMap(pendingVisualReferenceTasks),
    [pendingVisualReferenceTasks],
  )
  const pendingStoryboardTaskMap = useMemo(
    () => buildPendingStoryboardTaskMap(pendingStoryboardTasks),
    [pendingStoryboardTasks],
  )

  useEffect(() => {
    if (activeModule !== 'visual' || !visualData || pendingVisualReferenceTasks.length === 0) {
      return
    }

    const queued = pendingVisualReferenceTasks.filter((item) => !attemptedAutoRecoverTaskIdsRef.current.has(item.taskId))
    if (queued.length === 0) return

    queued.forEach((item) => {
      attemptedAutoRecoverTaskIdsRef.current.add(item.taskId)
      if (autoRecoveringTaskIdsRef.current.has(item.taskId)) return
      autoRecoveringTaskIdsRef.current.add(item.taskId)
      setAutoRecoveringVisualReferenceTaskIds((current) => current.includes(item.taskId) ? current : [...current, item.taskId])
      setVisualReferenceRecoveryState(item.taskId, {
        status: 'auto-recovering',
        updatedAt: new Date().toISOString(),
        message: '页面已自动发起一次结果回收，正在检查 provider 侧是否已经完成。',
      })
      recoverVisualReferenceGeneration(item.taskId)
        .catch((error) => {
          const message = error instanceof Error ? error.message : '自动回收失败'
          setVisualReferenceRecoveryState(item.taskId, {
            status: isCreativeTaskRecoveryMessage(message) ? 'waiting-provider' : 'failed',
            updatedAt: new Date().toISOString(),
            message: formatCreativeTaskMessage(message, '自动回收失败'),
          })
          // Keep recoverable tasks in local state so the user can continue manually.
        })
        .finally(() => {
          autoRecoveringTaskIdsRef.current.delete(item.taskId)
          setAutoRecoveringVisualReferenceTaskIds((current) => current.filter((value) => value !== item.taskId))
      })
    })
  }, [activeModule, pendingVisualReferenceTasks, recoverVisualReferenceGeneration, setVisualReferenceRecoveryState, visualData])

  useEffect(() => {
    if (activeModule !== 'storyboard' || storyboardData.length === 0 || pendingStoryboardTasks.length === 0) {
      return
    }

    const queued = pendingStoryboardTasks.filter((item) => !attemptedAutoRecoverStoryboardTaskIdsRef.current.has(item.taskId))
    if (queued.length === 0) return

    queued.forEach((item) => {
      attemptedAutoRecoverStoryboardTaskIdsRef.current.add(item.taskId)
      if (autoRecoveringStoryboardTaskIdsRef.current.has(item.taskId)) return
      autoRecoveringStoryboardTaskIdsRef.current.add(item.taskId)
      setAutoRecoveringStoryboardTaskIds((current) => current.includes(item.taskId) ? current : [...current, item.taskId])
      setStoryboardGenerationRecoveryState(item.taskId, {
        status: 'auto-recovering',
        updatedAt: new Date().toISOString(),
        message: '页面已自动发起一次结果回收，正在检查 provider 侧是否已经完成。',
      })
      fetch(`/api/prototyping/tasks/${item.taskId}/reconcile`, { method: 'POST' })
        .then(async (response) => {
          if (!response.ok) throw new Error(`HTTP ${response.status}`)
          const payload = await response.json()
          if (payload.status === 'done') {
            clearPendingStoryboardTask(item.taskId)
            setStoryboardGenerationRecoveryState(item.taskId, {
              status: 'recovered',
              updatedAt: new Date().toISOString(),
              message: `${item.kind === 'frame' ? '首帧' : '视频'}结果已自动回收并写回镜头。`,
            })
            await fetchOutputs()
            return
          }
          if (payload.status === 'running') {
            setStoryboardGenerationRecoveryState(item.taskId, {
              status: 'waiting-provider',
              updatedAt: new Date().toISOString(),
              message: `${item.kind === 'frame' ? '首帧' : '视频'}任务还在 provider 侧执行，可以稍后继续拉取结果。`,
            })
            return
          }
          throw new Error(payload.error || '结果回收失败')
        })
        .catch((error) => {
          const message = error instanceof Error ? error.message : '自动回收失败'
          setStoryboardGenerationRecoveryState(item.taskId, {
            status: isCreativeTaskRecoveryMessage(message) ? 'waiting-provider' : 'failed',
            updatedAt: new Date().toISOString(),
            message: formatCreativeTaskMessage(message, '自动回收失败'),
          })
        })
        .finally(() => {
          autoRecoveringStoryboardTaskIdsRef.current.delete(item.taskId)
          setAutoRecoveringStoryboardTaskIds((current) => current.filter((value) => value !== item.taskId))
        })
    })
  }, [activeModule, clearPendingStoryboardTask, fetchOutputs, pendingStoryboardTasks, setStoryboardGenerationRecoveryState, storyboardData.length])

  useEffect(() => {
    if (visualBatchState.entries.length === 0) return
    const recoveryByTaskId = visualReferenceRecoveryMeta
    setVisualBatchState((current) => {
      let changed = false
      const nextEntries: VisualBatchEntry[] = current.entries.map((entry) => {
        if (!entry.taskId) return entry
        const meta = recoveryByTaskId[entry.taskId]
        if (!meta) return entry
        if (meta.status === 'recovered' && (entry.status !== 'done' || entry.message !== meta.message)) {
          changed = true
          return { ...entry, status: 'done' as const, message: meta.message }
        }
        if ((meta.status === 'auto-recovering' || meta.status === 'waiting-provider') && (entry.status !== 'recovering' || entry.message !== meta.message)) {
          changed = true
          return { ...entry, status: 'recovering' as const, message: meta.message }
        }
        if (meta.status === 'failed' && (entry.status !== 'error' || entry.message !== meta.message)) {
          changed = true
          return { ...entry, status: 'error' as const, message: meta.message }
        }
        return entry
      })
      if (!changed) return current
      return { ...current, entries: nextEntries }
    })
  }, [visualBatchState.entries.length, visualReferenceRecoveryMeta])

  const patchStoryboardStructure = useCallback(async (
    episode: number,
    shotId: string | number,
    payload: {
      duration: number
      cameraAngle: string
      cameraMovement: string
      transition: string
      sceneAssetId: string
      characterAssetIds: string[]
      propAssetIds: string[]
      styleKey: string
      characterBlocking: Array<Record<string, string>>
      actionBeats: Array<Record<string, string | number>>
    },
  ) => {
    const response = await fetch(`/api/books/${book.id}/storyboard/${episode}/${shotId}/structure`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    await fetchOutputs()
  }, [book.id, fetchOutputs])

  const autoBindStoryboardVisualAssets = useCallback(async (episodes: number[]) => {
    const response = await fetch(`/api/books/${book.id}/storyboard/auto-bind-visual-assets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ episodes }),
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const payload = await response.json()
    await fetchOutputs()
    return payload
  }, [book.id, fetchOutputs])

  const compileStoryboardPrompts = useCallback(async (
    episode: number,
    shotId: string | number,
    compileReason = 'manual',
    force = false,
  ) => {
    const response = await fetch(`/api/books/${book.id}/storyboard/${episode}/${shotId}/compile-prompts/async`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ compileReason, force }),
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      throw new Error(payload.detail || `HTTP ${response.status}`)
    }

    const payload = await response.json().catch(() => ({}))
    const taskId = String(payload?.task_id || '').trim()
    if (!taskId) {
      throw new Error('Failed to get storyboard prompt compile task id')
    }

    let settled: any = null
    const startedAt = Date.now()
    while (Date.now() - startedAt < 45000) {
      const taskResponse = await fetch(`/api/storyboard-prompt-compile-tasks/${taskId}`)
      if (!taskResponse.ok) {
        throw new Error(`HTTP ${taskResponse.status}`)
      }
      settled = await taskResponse.json()
      if (settled?.status === 'done' || settled?.status === 'error') {
        break
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1000))
    }

    if (!settled || (settled.status !== 'done' && settled.status !== 'error')) {
      await fetchOutputs()
      return { status: 'soft_timeout', task_id: taskId }
    }

    if (settled.status === 'done' || settled.status === 'soft_timeout') {
      await fetchOutputs()
      return settled
    }

    throw new Error('error' in settled ? String(settled.error || '') : 'Storyboard prompt compile failed')
  }, [book.id, fetchOutputs])

  const setPromptLock = useCallback(async (episode: number, shotId: string | number, locked: boolean) => {
    const response = await fetch(`/api/books/${book.id}/storyboard/${episode}/${shotId}/prompt-lock`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ locked }),
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    await fetchOutputs()
    return response.json()
  }, [book.id, fetchOutputs])

  const loadPromptVersions = useCallback(async (episode: number, shotId: string | number) => {
    const response = await fetch(`/api/books/${book.id}/storyboard/${episode}/${shotId}/prompt-versions`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    return response.json()
  }, [book.id])

  const saveAcceptanceRecord = useCallback(async (
    episode: number,
    shotId: string | number,
    payload: {
      assetKind: string
      assetId: string
      status: string
      failureTags: string[]
      notes: string
    },
  ) => {
    const response = await fetch(`/api/books/${book.id}/storyboard/${episode}/${shotId}/acceptance-records`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    await fetchOutputs()
    return response.json()
  }, [book.id, fetchOutputs])

  async function waitForCreativeTask(taskId: string, options?: CreativeTaskWaitOptions) {
    const softTimeoutMs = typeof options?.softTimeoutMs === 'number' ? options.softTimeoutMs : 0
    const softTimeoutMessage = options?.softTimeoutMessage || 'Generation is still running on the provider side. Please refresh shortly to recover the finished result.'
    const startedAt = Date.now()

    async function fetchTask() {
      const response = await fetch(`/api/prototyping/tasks/${taskId}`)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      return response.json()
    }

    async function reconcileTask() {
      const response = await fetch(`/api/prototyping/tasks/${taskId}/reconcile`, { method: 'POST' })
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      return response.json()
    }

    async function waitLoop(maxAttempts: number, delayMs: number) {
      for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
        const payload = await fetchTask()
        if (payload.status === 'done') {
          return payload
        }
        if (payload.status === 'error') {
          return payload
        }
        if (softTimeoutMs > 0 && Date.now() - startedAt >= softTimeoutMs) {
          return { status: 'soft_timeout' }
        }
        await new Promise((resolve) => window.setTimeout(resolve, delayMs))
      }
      if (softTimeoutMs > 0 && Date.now() - startedAt >= softTimeoutMs) {
        return { status: 'soft_timeout' }
      }
      return null
    }

    const initial = await waitLoop(180, 1000)
    if (initial?.status === 'done') {
      return initial
    }
    if (initial?.status === 'soft_timeout') {
      const reconciled = await reconcileTask()
      if (reconciled.status === 'done') {
        return reconciled
      }
      if (reconciled.status === 'error') {
        throw new Error(formatCreativeTaskMessage(reconciled.error, '生成失败'))
      }
      throw new Error(softTimeoutMessage)
    }

    if (initial?.status === 'error') {
      const reconciled = await reconcileTask()
      if (reconciled.status === 'done') {
        return reconciled
      }
      if (reconciled.status === 'error') {
        throw new Error(formatCreativeTaskMessage(reconciled.error, '生成失败'))
      }
      const resumed = await waitLoop(45, 2000)
      if (resumed?.status === 'done') {
        return resumed
      }
      if (resumed?.status === 'error') {
        throw new Error(formatCreativeTaskMessage(resumed.error, '生成失败'))
      }
      throw new Error('Generation is still running on the provider side. Please refresh shortly to recover the finished result.')
    }

    const reconciled = await reconcileTask()
    if (reconciled.status === 'done') {
      return reconciled
    }
    if (reconciled.status === 'error') {
      throw new Error(formatCreativeTaskMessage(reconciled.error, '生成失败'))
    }

    const resumed = await waitLoop(45, 2000)
    if (resumed?.status === 'done') {
      return resumed
    }
    if (resumed?.status === 'error') {
      throw new Error(formatCreativeTaskMessage(resumed.error, '生成失败'))
    }
    throw new Error('Generation timed out. The task may still be running on the provider side. If the provider finishes later, refresh and the result should be recovered automatically.')
  }

  const generateStoryboardFrame = useCallback(async (episode: number, shotId: string | number) => {
    const response = await fetch(`/api/books/${book.id}/storyboard/${episode}/${shotId}/generate-frame`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const payload = await response.json()
    registerPendingStoryboardTask(episode, shotId, 'frame', payload.task_id)
    try {
      await waitForCreativeTask(payload.task_id, {
        softTimeoutMs: 45000,
        softTimeoutMessage: '首帧任务仍在 provider side 执行，已经超过当前等待窗口。请稍后继续拉取结果，不要重复新建任务。',
      })
    } catch (error) {
      if (error instanceof Error) {
        ;(error as Error & { taskId?: string }).taskId = payload.task_id
      }
      throw error
    }
    clearPendingStoryboardTask(payload.task_id)
    setStoryboardGenerationRecoveryState(payload.task_id, {
      status: 'recovered',
      updatedAt: new Date().toISOString(),
      message: '首帧已生成并写回镜头。',
    })
    await fetchOutputs()
    return payload
  }, [book.id, clearPendingStoryboardTask, fetchOutputs, registerPendingStoryboardTask, setStoryboardGenerationRecoveryState, waitForCreativeTask])

  const generateStoryboardVideo = useCallback(async (episode: number, shotId: string | number) => {
    const response = await fetch(`/api/books/${book.id}/storyboard/${episode}/${shotId}/generate-video`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const payload = await response.json()
    registerPendingStoryboardTask(episode, shotId, 'video', payload.task_id)
    try {
      await waitForCreativeTask(payload.task_id, {
        softTimeoutMs: 45000,
        softTimeoutMessage: '视频任务仍在 provider side 执行，已经超过当前等待窗口。请稍后继续拉取结果，不要重复新建任务。',
      })
    } catch (error) {
      if (error instanceof Error) {
        ;(error as Error & { taskId?: string }).taskId = payload.task_id
      }
      throw error
    }
    clearPendingStoryboardTask(payload.task_id)
    setStoryboardGenerationRecoveryState(payload.task_id, {
      status: 'recovered',
      updatedAt: new Date().toISOString(),
      message: '视频已生成并写回镜头。',
    })
    await fetchOutputs()
    return payload
  }, [book.id, clearPendingStoryboardTask, fetchOutputs, registerPendingStoryboardTask, setStoryboardGenerationRecoveryState, waitForCreativeTask])

  const recoverStoryboardGeneration = useCallback(async (taskId: string, kind: StoryboardTaskKind) => {
    const response = await fetch(`/api/prototyping/tasks/${taskId}/reconcile`, { method: 'POST' })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const payload = await response.json()
    if (payload.status === 'done') {
      clearPendingStoryboardTask(taskId)
      setStoryboardGenerationRecoveryState(taskId, {
        status: 'recovered',
        updatedAt: new Date().toISOString(),
        message: `${kind === 'frame' ? '首帧' : '视频'}结果已回收并写回镜头。`,
      })
      await fetchOutputs()
      return { taskId, stillRunning: false as const }
    }
    if (payload.status === 'running') {
      setStoryboardGenerationRecoveryState(taskId, {
        status: 'waiting-provider',
        updatedAt: new Date().toISOString(),
        message: `${kind === 'frame' ? '首帧' : '视频'}任务还在 provider 侧执行，请稍后再次拉取结果。`,
      })
      return { taskId, stillRunning: true as const }
    }
    const message = formatCreativeTaskMessage(payload.error, '结果回收失败')
    setStoryboardGenerationRecoveryState(taskId, {
      status: isCreativeTaskRecoveryMessage(message) ? 'waiting-provider' : 'failed',
      updatedAt: new Date().toISOString(),
      message,
    })
    if (!isCreativeTaskRecoveryMessage(message)) {
      clearPendingStoryboardTask(taskId)
    }
    throw new Error(message)
  }, [clearPendingStoryboardTask, fetchOutputs, setStoryboardGenerationRecoveryState])

  const hasSelectedReferenceAsset = useCallback((assetType: 'scene' | 'prop' | 'character', assetId: string) => {
    if (!assetId) return false
    const collections =
      assetType === 'scene'
        ? visualData?.locations
        : assetType === 'prop'
          ? visualData?.props
          : visualData?.makeups
    const asset = Array.isArray(collections) ? collections.find((item: any) => String(item.id) === String(assetId)) : null
    const references = Array.isArray(asset?.reference_assets) ? asset.reference_assets : []
    return references.some((item: any) => ['selected', 'locked'].includes(String(item?.status || '')))
  }, [visualData])

  const hasLockedReferenceAsset = useCallback((assetType: 'scene' | 'prop' | 'character', assetId: string) => {
    if (!assetId) return false
    const collections =
      assetType === 'scene'
        ? visualData?.locations
        : assetType === 'prop'
          ? visualData?.props
          : visualData?.makeups
    const asset = Array.isArray(collections) ? collections.find((item: any) => String(item.id) === String(assetId)) : null
    const references = Array.isArray(asset?.reference_assets) ? asset.reference_assets : []
    return references.some((item: any) => String(item?.status || '') === 'locked')
  }, [visualData])

  const getShotChecklist = useCallback((shot: any) => {
    return buildShotChecklist(shot, hasSelectedReferenceAsset, hasLockedReferenceAsset)
  }, [hasLockedReferenceAsset, hasSelectedReferenceAsset])

  const getLockedReferenceMissing = useCallback((checklist: { missing: string[] }) => {
    return checklist.missing.filter((item) => item.includes('参考图未锁定'))
  }, [])

  const shotHasVisualBindings = useCallback((shot: any) => {
    const structured = shot?.structured_shot ?? {}
    return Boolean(String(structured?.scene_asset_id ?? '').trim())
      || (Array.isArray(structured?.character_asset_ids) && structured.character_asset_ids.some((item: unknown) => String(item ?? '').trim()))
      || (Array.isArray(structured?.prop_asset_ids) && structured.prop_asset_ids.some((item: unknown) => String(item ?? '').trim()))
  }, [])

  const buildBatchShotPlan = useCallback((
    shots: any[],
    mode: 'compile' | 'frame' | 'video',
  ) => {
    const executable: any[] = []
    const blocked: Array<{ shot: any; reasons: string[] }> = []
    const skippedLockedPrompt: any[] = []

    for (const shot of shots) {
      const checklist = getShotChecklist(shot)
      const lockedReferenceReasons = getLockedReferenceMissing(checklist)

      if (mode === 'compile') {
        if (shot.prompt_locked) {
          skippedLockedPrompt.push(shot)
          continue
        }
        if (lockedReferenceReasons.length > 0) {
          blocked.push({ shot, reasons: lockedReferenceReasons })
          continue
        }
        executable.push(shot)
        continue
      }

      if (mode === 'frame') {
        if (!checklist.promptReady || checklist.frameReady) continue
        if (checklist.diagnosticBlocked) {
          blocked.push({ shot, reasons: ['提示词诊断阻塞'] })
          continue
        }
        if (lockedReferenceReasons.length > 0) {
          blocked.push({ shot, reasons: lockedReferenceReasons })
          continue
        }
        executable.push(shot)
        continue
      }

      if (!checklist.promptReady || !checklist.frameReady || checklist.videoReady) continue
      if (checklist.diagnosticBlocked) {
        blocked.push({ shot, reasons: ['提示词诊断阻塞'] })
        continue
      }
      if (lockedReferenceReasons.length > 0) {
        blocked.push({ shot, reasons: lockedReferenceReasons })
        continue
      }
      executable.push(shot)
    }

    return {
      executable,
      blocked,
      skippedLockedPrompt,
      boundVisualShots: shots.filter((shot) => shotHasVisualBindings(shot)).length,
    }
  }, [getLockedReferenceMissing, getShotChecklist, shotHasVisualBindings])

  const formatBlockedShotPreview = useCallback((blocked: Array<{ shot: any; reasons: string[] }>, limit = 5) => {
    return blocked
      .slice(0, limit)
      .map(({ shot, reasons }) => `第 ${shot.episode} 集 / 镜头 ${shot.shot_id}: ${reasons.join('、')}`)
      .join('；')
  }, [])

  const exportSummaryText = () => ([
    `导出状态：${exportReadiness.canExport ? '可导出' : '未完成'}`,
    `总镜头：${exportReadiness.totalShots}`,
    `可交付镜头：${exportReadiness.deliverableShots}`,
    `待验收镜头：${exportReadiness.pendingReviewShots}`,
    `阻塞镜头：${exportReadiness.blockedShots.length}`,
    ...exportReadiness.issues.map((item) => `- ${item}`),
  ].join('\n'))

  const getSafeExportTitle = () => book.title.replace(/[^\w\u4e00-\u9fa5-]+/g, '_') || 'project'

  const downloadTextFile = (content: string, mimeType: string, extension: string) => {
    const blob = new Blob([content], { type: `${mimeType};charset=utf-8` })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${getSafeExportTitle()}-production-export.${extension}`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  }

  const escapeHtml = (value: unknown) => String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')

  const escapeXml = (value: unknown) => String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')

  const buildWordExportDocument = () => {
    const scriptSections = scripts.map((script: any) => `
      <section>
        <h2>第 ${script.episode} 集</h2>
        <pre>${escapeHtml(script.content || '')}</pre>
      </section>
    `).join('')

    const storyboardRows = storyboardData.map((shot: any) => `
      <tr>
        <td>${escapeHtml(shot.episode)}</td>
        <td>${escapeHtml(shot.shot_id)}</td>
        <td>${escapeHtml(shot.scene_name || '')}</td>
        <td>${escapeHtml(shot.camera_angle || '')}</td>
        <td>${escapeHtml(shot.camera_movement || '')}</td>
        <td>${escapeHtml(shot.duration || '')}</td>
        <td>${escapeHtml(shot.dialogue || '')}</td>
        <td>${escapeHtml(shot.action_process || '')}</td>
      </tr>
    `).join('')

    return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>${escapeHtml(book.title)} 生产交付</title>
  <style>
    body { font-family: "Microsoft YaHei", sans-serif; padding: 32px; color: #111827; }
    h1, h2 { margin-bottom: 12px; }
    .meta { margin-bottom: 24px; color: #4b5563; white-space: pre-wrap; }
    table { width: 100%; border-collapse: collapse; margin-top: 16px; }
    th, td { border: 1px solid #cbd5e1; padding: 8px; font-size: 12px; vertical-align: top; }
    th { background: #e2e8f0; }
    pre { white-space: pre-wrap; background: #f8fafc; border: 1px solid #e2e8f0; padding: 16px; }
  </style>
</head>
<body>
  <h1>${escapeHtml(book.title)} 生产交付文档</h1>
  <div class="meta">${escapeHtml(exportSummaryText())}</div>
  <h2>剧本</h2>
  ${scriptSections || '<p>暂无剧本内容</p>'}
  <h2>分镜总表</h2>
  <table>
    <thead>
      <tr><th>集</th><th>镜号</th><th>场景</th><th>景别</th><th>运镜</th><th>时长</th><th>对白</th><th>动作</th></tr>
    </thead>
    <tbody>
      ${storyboardRows || '<tr><td colspan="8">暂无分镜数据</td></tr>'}
    </tbody>
  </table>
</body>
</html>`
  }

  const buildFinalDraftExportDocument = () => {
    const paragraphs = scripts.flatMap((script: any) => {
      const lines = String(script.content || '').split(/\r?\n/)
      return [
        `<Paragraph Type="Scene Heading"><Text>第 ${escapeXml(script.episode)} 集</Text></Paragraph>`,
        ...lines
          .filter((line: string) => line.trim())
          .map((line: string) => `<Paragraph Type="Action"><Text>${escapeXml(line)}</Text></Paragraph>`),
      ]
    }).join('')

    return `<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<FinalDraft DocumentType="Script" Template="No" Version="1">
  <Content>
    <Paragraph Type="Title"><Text>${escapeXml(book.title)} 生产导出</Text></Paragraph>
    <Paragraph Type="Action"><Text>${escapeXml(exportSummaryText())}</Text></Paragraph>
    ${paragraphs || '<Paragraph Type="Action"><Text>暂无剧本内容</Text></Paragraph>'}
  </Content>
</FinalDraft>`
  }

  const createExportRecord = async (format: string) => {
    const blockedShotIds = exportReadiness.blockedShots.map((item) => `${item.episode}-${item.shotId}`)
    const response = await fetch(`/api/books/${book.id}/export-records`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        exportFormat: format,
        status: exportReadiness.canExport ? 'completed' : 'blocked',
        totalShots: exportReadiness.totalShots,
        deliverableShots: exportReadiness.deliverableShots,
        pendingReviewShots: exportReadiness.pendingReviewShots,
        blockedShots: exportReadiness.blockedShots.length,
        summary: `${book.title} ${format.toUpperCase()} 交付记录`,
        metaInfo: {
          canExport: exportReadiness.canExport,
          visualReady,
          issues: exportReadiness.issues,
          blockedShotIds,
        },
      }),
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    await fetchExportRecords()
    return response.json()
  }

  const handleRegisterDelivery = async () => {
    setExportActionState({ status: 'running', message: '正在登记本次交付记录...' })
    try {
      await createExportRecord('delivery')
      setExportActionState({ status: 'done', message: '本次交付记录已保存到历史。' })
    } catch (error) {
      setExportActionState({ status: 'error', message: error instanceof Error ? error.message : '登记交付记录失败' })
    }
  }

  const handleExportJson = async () => {
    setExportActionState({ status: 'running', message: '正在导出 JSON 并登记交付历史...' })
    try {
      const record = await createExportRecord('json')
      const payload = {
        book: {
          id: book.id,
          title: book.title,
        },
        exportedAt: new Date().toISOString(),
        readiness: exportReadiness,
        scripts,
        storyboard: storyboardData,
        visual: visualData,
        exportRecord: record,
      }
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${getSafeExportTitle()}-production-export.json`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      setExportActionState({ status: 'done', message: 'JSON 已导出，交付历史已记录。' })
    } catch (error) {
      setExportActionState({ status: 'error', message: error instanceof Error ? error.message : '导出 JSON 失败' })
    }
  }

  const handleExportWord = async () => {
    setExportActionState({ status: 'running', message: '正在导出 Word 并登记交付历史...' })
    try {
      await createExportRecord('word')
      downloadTextFile(buildWordExportDocument(), 'application/msword', 'doc')
      setExportActionState({ status: 'done', message: 'Word 已导出，交付历史已记录。' })
    } catch (error) {
      setExportActionState({ status: 'error', message: error instanceof Error ? error.message : '导出 Word 失败' })
    }
  }

  const handleExportFinalDraft = async () => {
    setExportActionState({ status: 'running', message: '正在导出 Final Draft 并登记交付历史...' })
    try {
      await createExportRecord('fdx')
      downloadTextFile(buildFinalDraftExportDocument(), 'application/vnd.finaldraft', 'fdx')
      setExportActionState({ status: 'done', message: 'Final Draft 已导出，交付历史已记录。' })
    } catch (error) {
      setExportActionState({ status: 'error', message: error instanceof Error ? error.message : '导出 Final Draft 失败' })
    }
  }

  const handleExportPdf = async () => {
    setExportActionState({ status: 'running', message: '正在导出 PDF 并登记交付历史...' })
    try {
      await createExportRecord('pdf')
      const response = await fetch(`/api/books/${book.id}/export-pdf`)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${getSafeExportTitle()}-production-export.pdf`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      setExportActionState({ status: 'done', message: 'PDF 已导出，交付历史已记录。' })
    } catch (error) {
      setExportActionState({ status: 'error', message: error instanceof Error ? error.message : '导出 PDF 失败' })
    }
  }

  const batchCompileShots = useCallback(async (shots: any[], compileReason: string) => {
    const { executable, blocked, skippedLockedPrompt, boundVisualShots } = buildBatchShotPlan(shots, 'compile')
    const noVisualBindingHint = boundVisualShots === 0 ? '当前镜头尚未绑定结构化视觉资产，所以锁定参考图拦截暂未生效。' : ''
    if (executable.length === 0) {
      const blockedSummary = blocked.length > 0 ? `；${formatBlockedShotPreview(blocked)}` : ''
      const lockedSummary = skippedLockedPrompt.length > 0 ? `；另有 ${skippedLockedPrompt.length} 个镜头已锁定提示词` : ''
      setStoryboardBatchState({ mode: 'compile', status: 'error', message: `没有可批量编译的镜头。${blocked.length > 0 ? `请先锁定参考图：${blocked.length} 个镜头被拦截` : '当前镜头都已锁定或已处理'}${blockedSummary}${lockedSummary}${noVisualBindingHint ? `；${noVisualBindingHint}` : ''}` })
      return
    }
    setStoryboardBatchState({ mode: 'compile', status: 'running', message: `正在编译 ${executable.length} 个镜头${skippedLockedPrompt.length > 0 ? `，跳过 ${skippedLockedPrompt.length} 个已锁定提示词镜头` : ''}${blocked.length > 0 ? `，拦截 ${blocked.length} 个缺锁定参考图镜头` : ''}...` })
    try {
      for (const shot of executable) {
        await compileStoryboardPrompts(shot.episode, shot.shot_id, compileReason)
      }
      await fetchOutputs()
      setStoryboardBatchState({
        mode: 'compile',
        status: 'done',
        message: `已完成 ${executable.length} 个镜头的提示词编译${skippedLockedPrompt.length > 0 ? `，跳过 ${skippedLockedPrompt.length} 个已锁定提示词镜头` : ''}${blocked.length > 0 ? `；仍有 ${blocked.length} 个镜头因缺少锁定参考图未执行${formatBlockedShotPreview(blocked) ? `：${formatBlockedShotPreview(blocked)}` : ''}` : ''}${noVisualBindingHint ? `；${noVisualBindingHint}` : ''}`,
      })
    } catch (error) {
      setStoryboardBatchState({ mode: 'compile', status: 'error', message: error instanceof Error ? error.message : '批量编译失败' })
    }
  }, [buildBatchShotPlan, compileStoryboardPrompts, fetchOutputs, formatBlockedShotPreview])

  const batchGenerateFrames = useCallback(async (shots: any[]) => {
    const { executable, blocked, boundVisualShots } = buildBatchShotPlan(shots, 'frame')
    const noVisualBindingHint = boundVisualShots === 0 ? '当前镜头尚未绑定结构化视觉资产，所以锁定参考图拦截暂未生效。' : ''
    if (executable.length === 0) {
      setStoryboardBatchState({
        mode: 'frame',
        status: 'error',
        message: blocked.length > 0
          ? `没有可补首帧的镜头。请先锁定参考图：${blocked.length} 个镜头被拦截${formatBlockedShotPreview(blocked) ? `；${formatBlockedShotPreview(blocked)}` : ''}${noVisualBindingHint ? `；${noVisualBindingHint}` : ''}`
          : `没有符合条件的镜头可补首帧。需要先完成提示词编译，且当前镜头尚未已有首帧。${noVisualBindingHint ? ` ${noVisualBindingHint}` : ''}`,
      })
      return
    }
    setStoryboardBatchState({ mode: 'frame', status: 'running', message: `正在串行生成 ${executable.length} 个镜头的首帧${blocked.length > 0 ? `，拦截 ${blocked.length} 个缺锁定参考图镜头` : ''}...` })
    let recovering = 0
    let failed = 0
    try {
      for (const shot of executable) {
        try {
          await generateStoryboardFrame(shot.episode, shot.shot_id)
        } catch (error) {
          if (deriveRecoverTaskIdFromError(error)) {
            recovering += 1
            continue
          }
          failed += 1
          throw error
        }
      }
      await fetchOutputs()
      setStoryboardBatchState({
        mode: 'frame',
        status: failed > 0 ? 'error' : 'done',
        message: `批量首帧生成已完成，共执行 ${executable.length} 个镜头，待回收 ${recovering} 个${blocked.length > 0 ? `；${blocked.length} 个镜头仍缺锁定参考图` : ''}${blocked.length > 0 && formatBlockedShotPreview(blocked) ? `：${formatBlockedShotPreview(blocked)}` : ''}${noVisualBindingHint ? `；${noVisualBindingHint}` : ''}`,
      })
    } catch (error) {
      setStoryboardBatchState({ mode: 'frame', status: 'error', message: error instanceof Error ? error.message : '批量首帧生成失败' })
    }
  }, [buildBatchShotPlan, fetchOutputs, formatBlockedShotPreview, generateStoryboardFrame])

  const batchGenerateVideos = useCallback(async (shots: any[]) => {
    const { executable, blocked, boundVisualShots } = buildBatchShotPlan(shots, 'video')
    const noVisualBindingHint = boundVisualShots === 0 ? '当前镜头尚未绑定结构化视觉资产，所以锁定参考图拦截暂未生效。' : ''
    if (executable.length === 0) {
      setStoryboardBatchState({
        mode: 'video',
        status: 'error',
        message: blocked.length > 0
          ? `没有可补视频的镜头。请先锁定参考图：${blocked.length} 个镜头被拦截${formatBlockedShotPreview(blocked) ? `；${formatBlockedShotPreview(blocked)}` : ''}${noVisualBindingHint ? `；${noVisualBindingHint}` : ''}`
          : `没有符合条件的镜头可补视频。需要先有已编译提示词和已采用首帧。${noVisualBindingHint ? ` ${noVisualBindingHint}` : ''}`,
      })
      return
    }
    setStoryboardBatchState({ mode: 'video', status: 'running', message: `正在串行生成 ${executable.length} 个镜头的视频${blocked.length > 0 ? `，拦截 ${blocked.length} 个缺锁定参考图镜头` : ''}...` })
    let recovering = 0
    let failed = 0
    try {
      for (const shot of executable) {
        try {
          await generateStoryboardVideo(shot.episode, shot.shot_id)
        } catch (error) {
          if (deriveRecoverTaskIdFromError(error)) {
            recovering += 1
            continue
          }
          failed += 1
          throw error
        }
      }
      await fetchOutputs()
      setStoryboardBatchState({
        mode: 'video',
        status: failed > 0 ? 'error' : 'done',
        message: `批量视频生成已完成，共执行 ${executable.length} 个镜头，待回收 ${recovering} 个${blocked.length > 0 ? `；${blocked.length} 个镜头仍缺锁定参考图` : ''}${blocked.length > 0 && formatBlockedShotPreview(blocked) ? `：${formatBlockedShotPreview(blocked)}` : ''}${noVisualBindingHint ? `；${noVisualBindingHint}` : ''}`,
      })
    } catch (error) {
      setStoryboardBatchState({ mode: 'video', status: 'error', message: error instanceof Error ? error.message : '批量视频生成失败' })
    }
  }, [buildBatchShotPlan, fetchOutputs, formatBlockedShotPreview, generateStoryboardVideo])

  const ensureSelectedEpisodesAutoBound = useCallback(async (): Promise<{ episodes: number[]; shots: any[] }> => {
    const selectedEpisodes = Array.from(selectedSBEps).sort((a, b) => a - b)
    if (selectedEpisodes.length === 0) {
      return { episodes: [], shots: [] }
    }
    await autoBindStoryboardVisualAssets(selectedEpisodes)
    const refreshed = await fetchOutputs()
    return {
      episodes: selectedEpisodes,
      shots: Array.isArray(refreshed?.storyboard) ? refreshed.storyboard : storyboardData,
    }
  }, [autoBindStoryboardVisualAssets, fetchOutputs, selectedSBEps, storyboardData])

  const batchCompileSelectedEpisodes = useCallback(async () => {
    const { episodes, shots } = await ensureSelectedEpisodesAutoBound()
    const selectedEpisodes = new Set(episodes)
    const selectedShots = shots.filter((shot: any) => selectedEpisodes.has(shot.episode))
    await batchCompileShots(selectedShots, 'batch-selected-episodes')
  }, [batchCompileShots, ensureSelectedEpisodesAutoBound])

  const batchGenerateFramesSelectedEpisodes = useCallback(async () => {
    const { episodes, shots } = await ensureSelectedEpisodesAutoBound()
    const selectedEpisodes = new Set(episodes)
    const selectedShots = shots.filter((shot: any) => selectedEpisodes.has(shot.episode))
    await batchGenerateFrames(selectedShots)
  }, [batchGenerateFrames, ensureSelectedEpisodesAutoBound])

  const batchGenerateVideosSelectedEpisodes = useCallback(async () => {
    const { episodes, shots } = await ensureSelectedEpisodesAutoBound()
    const selectedEpisodes = new Set(episodes)
    const selectedShots = shots.filter((shot: any) => selectedEpisodes.has(shot.episode))
    await batchGenerateVideos(selectedShots)
  }, [batchGenerateVideos, ensureSelectedEpisodesAutoBound])

  const autoBindSelectedEpisodes = useCallback(async () => {
    const selectedEpisodes = Array.from(selectedSBEps).sort((a, b) => a - b)
    if (selectedEpisodes.length === 0) {
      setStoryboardBatchState({ mode: 'compile', status: 'error', message: '请先选择至少一集，再同步视觉绑定。' })
      return
    }
    setStoryboardBatchState({ mode: 'compile', status: 'running', message: `正在同步第 ${selectedEpisodes.join('、')} 集的视觉绑定...` })
    try {
      const payload = await autoBindStoryboardVisualAssets(selectedEpisodes)
      setStoryboardBatchState({
        mode: 'compile',
        status: 'done',
        message: `视觉绑定同步完成：检查了 ${payload.inspected_shots ?? 0} 个镜头，写回 ${payload.changed_shots ?? 0} 个镜头。`,
      })
    } catch (error) {
      setStoryboardBatchState({ mode: 'compile', status: 'error', message: error instanceof Error ? error.message : '同步视觉绑定失败' })
    }
  }, [autoBindStoryboardVisualAssets, selectedSBEps])

  const refreshModelDefaults = useCallback(async () => {
    setModelDefaultsState('loading')
    try {
      const payload = await fetchModelRegistryDefaults()
      setModelDefaults(payload.default_profiles ?? {})
      setModelDefaultsState('idle')
    } catch {
      setModelDefaultsState('error')
    }
  }, [])

  const openModelRegistry = useCallback(() => {
    setModelRegistryOpen(true)
    setModelRegistryError(null)
    fetchModelRegistry()
      .then((payload) => setModelRegistryData(payload))
      .catch((error) => setModelRegistryError(error instanceof Error ? error.message : '加载模型配置失败'))
  }, [])

  const handleModelRegistrySaved = useCallback((payload: ModelRegistryPayload) => {
    setModelRegistryData(payload)
    setModelDefaults(payload.default_profiles ?? {})
    setModelDefaultsState('idle')
  }, [])

  // Refresh visual data when switching to visual module, or when non-null
  useEffect(() => {
    if (activeModule === 'visual' || visualData) {
      refreshVisualData()
    }
  }, [activeModule])

  useEffect(() => {
    void refreshModelDefaults()
  }, [refreshModelDefaults])

  // Start pipeline
  const startPipeline = async () => {
    setRunState('running')
    setProgress(0)
    setCurrentStep('starting')
    setTaskId(null)
    try {
      let pipelineBody: any = {
        book_id: book.id,
        genre,
        episode_count: episodeCount,
        episode_duration: episodeDuration,
        scope,
        scope_chapters: scopeChapters,
        genre_subtype: genreSubtype,
        tone_tags: toneTags,
        adapt_direction: adaptDirection,
      }

      // For text/upload mode, ingest the content first
      if (inputMode === 'text' && textInput.trim()) {
        const blob = new Blob([textInput], { type: 'text/plain' })
        const formData = new FormData()
        formData.append('file', blob, 'text_input.txt')
        const uploadRes = await fetch('/api/upload', { method: 'POST', body: formData })
        const uploadData = await uploadRes.json()
        pipelineBody = { ...pipelineBody, book_id: 0, filepath: uploadData.filepath }
      } else if (inputMode === 'upload') {
        // User needs to have uploaded via the file input
        // For now fall back to existing book
        pipelineBody.from_step = statusFromBook(bookData?.status || 'imported') >= 2 ? 'outline' : undefined
      } else {
        pipelineBody.from_step = statusFromBook(bookData?.status || 'imported') >= 2 ? 'outline' : undefined
      }

      const res = await fetch('/api/pipeline/script', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(pipelineBody),
      })
      const data = await res.json()
      setTaskId(data.task_id)

      // Poll progress
      const poll = async () => {
        const pr = await fetch(`/api/pipeline/task/${data.task_id}`)
        const pd = await pr.json()
        setProgress(pd.progress || 0)
        setCurrentStep(pd.current_step || '')
        if (pd.status === 'running' || pd.status === 'queued') {
          setTimeout(poll, 2000)
        } else if (pd.status === 'done') {
          setRunState('done')
          setProgress(100)
          setCurrentStep('complete')
          // If pipeline created a new book, tell parent to switch to it
          if (pd.new_book_id && onBookChange) {
            onBookChange(pd.new_book_id)
          } else {
            onRefresh()
            fetchOutputs()
          }
        } else {
          setRunState('error')
          setCurrentStep(pd.error || pd.current_step || 'error')
        }
      }
      setTimeout(poll, 2000)
    } catch (e: any) {
      setRunState('error')
      setCurrentStep(e.message)
    }
  }

  // Start storyboard (independent from pipeline)
  const startStoryboard = async (overrideEpisodes?: number[], options?: { resumeFromScene?: Record<string, string> }) => {
    const selected = (overrideEpisodes && overrideEpisodes.length > 0
      ? [...overrideEpisodes]
      : Array.from(selectedSBEps)).sort((a, b) => a - b)
    if (selected.length === 0) return
    // Clear any previous poll
    if (sbPollRef.current) clearTimeout(sbPollRef.current)
    setSbRunState('running')
    setSbProgress(0)
    setSbStep('starting')
    setSbTaskDetail({
      status: 'running',
      progress: 0,
      current_step: 'starting',
      episodes: selected.map((episode, index) => ({
        episode,
        status: index === 0 ? 'running' : 'queued',
        progress: index === 0 ? 5 : 0,
        current_step: index === 0 ? 'preparing' : 'queued',
        error: '',
      })),
    })
    let maxRetries = 0
    try {
      const res = await fetch('/api/pipeline/storyboard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ book_id: book.id, genre, episodes: selected, resumeFromScene: options?.resumeFromScene || {} }),
      })
      const { task_id } = await res.json()
      const poll = async () => {
        try {
          const pr = await fetch(`/api/pipeline/storyboard/task/${task_id}`)
          const pd = await pr.json()
          setSbTaskDetail(pd)
          setSbProgress(pd.progress || 0)
          setSbStep(pd.current_step || '')
          if (pd.status === 'running') {
            maxRetries++
            // Safety: if progress is 100 but still 'running' after 15+ polls (30s), force reload
            if (pd.progress >= 100 && maxRetries > 15) {
              onRefresh()
              fetchOutputs()
              setSbRunState('done')
              setSbStep('分镜生成完成（延迟确认）')
              return
            }
            sbPollRef.current = setTimeout(poll, 2000)
          } else if (pd.status === 'done' || pd.status === 'partial') {
            setSbRunState(pd.status === 'partial' ? 'partial' : 'done')
            setSbProgress(100)
            setSbStep(pd.current_step || (pd.status === 'partial' ? '分镜部分完成' : '分镜生成完成'))
            onRefresh()
            fetchOutputs()
          } else {
            setSbRunState('error')
            setSbStep(pd.error || pd.current_step || 'error')
          }
        } catch (e) {
          // On fetch error, try one last check
          try {
            const pr2 = await fetch(`/api/pipeline/storyboard/task/${task_id}`)
            const pd2 = await pr2.json()
            setSbTaskDetail(pd2)
            if (pd2.status === 'done' || pd2.status === 'partial' || pd2.status === 'error') {
              setSbRunState(pd2.status === 'done' ? 'done' : pd2.status === 'partial' ? 'partial' : 'error')
              setSbProgress(pd2.progress || 0)
              setSbStep(pd2.current_step || pd2.error || '')
              if (pd2.status === 'done' || pd2.status === 'partial') { onRefresh(); fetchOutputs() }
              return
            }
          } catch {}
          maxRetries++
          if (maxRetries > 5) {
            setSbRunState('error')
            setSbStep('Poll failed after retries: ' + String(e))
          } else {
            sbPollRef.current = setTimeout(poll, 2000)
          }
        }
      }
      sbPollRef.current = setTimeout(poll, 500)
    } catch (e: any) {
      setSbRunState('error')
      setSbStep(e.message)
    }
  }

  // Cleanup storyboard poll on unmount
  useEffect(() => {
    return () => {
      if (sbPollRef.current) clearTimeout(sbPollRef.current)
    }
  }, [])

  // Start visual setup
  const startVisualSetup = async () => {
    setVsRunState('running')
    setVsProgress(0)
    setVsStep('starting')
    let maxRetries = 0
    try {
      const res = await fetch('/api/pipeline/visual-setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ book_id: book.id, genre, episode_count: episodeCount }),
      })
      const { task_id } = await res.json()
      const poll = async () => {
        try {
          const pr = await fetch(`/api/pipeline/visual-setup/task/${task_id}`)
          const pd = await pr.json()
          setVsProgress(pd.progress || 0)
          setVsStep(pd.current_step || '')
          if (pd.status === 'running') {
            maxRetries++
            if (pd.progress >= 100 && maxRetries > 15) {
              onRefresh()
              fetchOutputs()
              setVsRunState('done')
              return
            }
            setTimeout(poll, 2000)
          } else if (pd.status === 'done') {
            setVsRunState('done')
            setVsProgress(100)
            setVsStep('视觉设定完成')
            onRefresh()
            refreshVisualData()
          } else {
            setVsRunState('error')
            setVsStep(pd.error || pd.current_step || 'error')
          }
        } catch (e) {
          // On fetch error, try one last check at current url
          try {
            const pr2 = await fetch(`/api/pipeline/visual-setup/task/${task_id}`)
            const pd2 = await pr2.json()
            if (pd2.status === 'done' || pd2.status === 'error') {
              setVsRunState(pd2.status === 'done' ? 'done' : 'error')
              setVsProgress(pd2.progress || 0)
              setVsStep(pd2.current_step || pd2.error || '')
              if (pd2.status === 'done') { onRefresh(); fetchOutputs() }
              return
            }
          } catch {}
          maxRetries++
          if (maxRetries > 5) {
            setVsRunState('error')
            setVsStep('Poll failed: ' + String(e))
          } else {
            setTimeout(poll, 2000)
          }
        }
      }
      setTimeout(poll, 2000)
    } catch (e: any) {
      setVsRunState('error')
      setVsStep(e.message)
    }
  }

  // Save bible
  const saveBible = async () => {
    setSavingMap(m => ({ ...m, bible: true }))
    try {
      await fetch(`/api/bibles/${book.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: bibleDraft }),
      })
      setBible(bibleDraft)
      setEditingBible(false)
    } catch {}
    setSavingMap(m => ({ ...m, bible: false }))
  }

  // Save outline
  const saveOutline = async (ep: number) => {
    setSavingMap(m => ({ ...m, [`outline_${ep}`]: true }))
    const draft = outlineDrafts[ep]
    if (!draft) return
    try {
      const outline = outlines.find(o => o.episode === ep)
      if (outline?.id) {
        await fetch(`/api/outlines/${outline.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(draft),
        })
      }
      setEditingOutline(null)
    } catch {}
    setSavingMap(m => ({ ...m, [`outline_${ep}`]: false }))
  }

  // Save script
  const saveScript = async () => {
    setSavingMap(m => ({ ...m, script: true }))
    try {
      const script = scripts.find(s => s.episode === scriptEpisode)
      if (script?.id) {
        await fetch(`/api/scripts/${script.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: scriptDraft }),
        })
      }
      setCurrentScript(scriptDraft)
      setEditingScript(false)
    } catch {}
    setSavingMap(m => ({ ...m, script: false }))
  }

  // Episode count based on book status
  const pipelineDone = statusFromBook(bookData?.status || 'imported')
  const epCount = outlines.length || episodeCount
  const outlineReady = outlines.length > 0
  const scriptReady = scripts.length > 0
  const scriptStageReady = !!bible || outlineReady || scriptReady
  const storyboardReady = storyboardData.length > 0
  const visualAssetData = visualData ?? bookData?.visual ?? null
  const visualAssetSummary = useMemo(() => buildVisualAssetSummary(visualAssetData), [visualAssetData])
  const visualReady = visualAssetSummary.ready
  const hasAnyReferenceImages = useCallback((asset: any) => {
    const references = Array.isArray(asset?.reference_assets) ? asset.reference_assets : []
    return references.some((reference: any) => Boolean(reference?.image_url || reference?.local_path))
  }, [])
  const hasLockedReferenceImage = useCallback((asset: any) => {
    const references = Array.isArray(asset?.reference_assets) ? asset.reference_assets : []
    return references.some((reference: any) => String(reference?.status || '') === 'locked')
  }, [])
  const runVisualAssetBatch = useCallback(async (
    scope: 'scene' | 'prop' | 'character' | 'missing',
  ) => {
    const assetGroups: Array<{ assetType: VisualAssetType; asset: any; assetName: string }> = []
    if (scope === 'scene' || scope === 'missing') {
      for (const asset of visualAssetData?.locations || []) {
        assetGroups.push({ assetType: 'scene', asset, assetName: asset.name })
      }
    }
    if (scope === 'prop' || scope === 'missing') {
      for (const asset of visualAssetData?.props || []) {
        assetGroups.push({ assetType: 'prop', asset, assetName: asset.name })
      }
    }
    if (scope === 'character' || scope === 'missing') {
      for (const asset of visualAssetData?.makeups || []) {
        assetGroups.push({ assetType: 'character', asset, assetName: asset.character_name })
      }
    }

    const initialEntries = assetGroups.map(({ assetType, asset, assetName }) => ({
      key: `${assetType}-${asset.id}`,
      name: assetName,
      status: 'waiting' as const,
      message: '',
    }))
    setVisualBatchState({
      scope,
      status: 'running',
      message: `准备处理 ${initialEntries.length} 个资产...`,
      entries: initialEntries,
    })

    let completed = 0
    let skipped = 0
    let failed = 0
    let recovering = 0
    for (const item of assetGroups) {
      const key = `${item.assetType}-${item.asset.id}`
      const skipForLocked = hasLockedReferenceImage(item.asset)
      const skipForExisting = scope === 'missing' && hasAnyReferenceImages(item.asset)
      if (skipForLocked || skipForExisting) {
        skipped += 1
        setVisualBatchState((current) => ({
          ...current,
          message: `已处理 ${completed + skipped + failed}/${assetGroups.length}，跳过 ${skipped} 个`,
          entries: current.entries.map((entry) => (
            entry.key === key
              ? {
                  ...entry,
                  status: 'skipped',
                  message: skipForLocked ? '跳过 locked 资产' : '已有参考图，跳过',
                }
              : entry
          )),
        }))
        continue
      }

      setVisualBatchState((current) => ({
        ...current,
        message: `正在处理 ${item.assetName} (${completed + skipped + failed + 1}/${assetGroups.length})`,
        entries: current.entries.map((entry) => (
          entry.key === key ? { ...entry, status: 'running', message: '生成中...' } : entry
        )),
      }))
      try {
        const result = await generateVisualReferenceAsset(item.assetType, item.asset, item.assetName)
        completed += 1
        setVisualBatchState((current) => ({
          ...current,
          message: `已完成 ${completed}/${assetGroups.length}，跳过 ${skipped} 个，待回收 ${recovering} 个，失败 ${failed} 个`,
          entries: current.entries.map((entry) => (
            entry.key === key
              ? { ...entry, status: 'done', message: formatReferenceSyncMessage(result.sync_warning, '生成并入库成功') }
              : entry
          )),
        }))
      } catch (error) {
        const recoverTaskId = deriveRecoverTaskIdFromError(error)
        if (recoverTaskId) {
          recovering += 1
          setVisualBatchState((current) => ({
            ...current,
            message: `已完成 ${completed}/${assetGroups.length}，跳过 ${skipped} 个，待回收 ${recovering} 个，失败 ${failed} 个`,
            entries: current.entries.map((entry) => (
              entry.key === key
                ? {
                    ...entry,
                    status: 'recovering',
                    taskId: recoverTaskId,
                    message: formatCreativeTaskMessage(error instanceof Error ? error.message : '', '任务已提交，等待后续回收'),
                  }
                : entry
            )),
          }))
          continue
        }
        failed += 1
        setVisualBatchState((current) => ({
          ...current,
          message: `已完成 ${completed}/${assetGroups.length}，跳过 ${skipped} 个，待回收 ${recovering} 个，失败 ${failed} 个`,
          entries: current.entries.map((entry) => (
            entry.key === key
              ? {
                  ...entry,
                  status: 'error',
                  message: error instanceof Error ? error.message : '生成失败',
                }
              : entry
          )),
        }))
      }
    }

    setVisualBatchState((current) => ({
      ...current,
      status: failed > 0 ? 'error' : 'done',
      message: `批量任务完成：成功 ${completed}，跳过 ${skipped}，待回收 ${recovering}，失败 ${failed}`,
    }))
  }, [generateVisualReferenceAsset, hasAnyReferenceImages, hasLockedReferenceImage, visualAssetData])

  const storyboardReadiness = useMemo(() => {
    return buildStoryboardReadiness(storyboardData, new Set(Array.from(selectedSBEps)), getShotChecklist)
  }, [getShotChecklist, selectedSBEps, storyboardData])

  const storyboardEpisodeTaskRows = useMemo(() => (
    Array.isArray(sbTaskDetail?.episodes) ? sbTaskDetail.episodes : []
  ), [sbTaskDetail])

  const failedStoryboardEpisodes = useMemo(() => (
    storyboardEpisodeTaskRows
      .filter((item: any) => item?.status === 'error' && Number(item?.episode ?? 0) > 0)
      .map((item: any) => Number(item.episode))
  ), [storyboardEpisodeTaskRows])

  const completedStoryboardEpisodes = useMemo(() => (
    storyboardEpisodeTaskRows
      .filter((item: any) => item?.status === 'done' && Number(item?.episode ?? 0) > 0)
      .map((item: any) => Number(item.episode))
  ), [storyboardEpisodeTaskRows])

  const storyboardResumeSceneMap = useMemo(() => {
    const result: Record<string, string> = {}
    for (const item of storyboardEpisodeTaskRows) {
      const episode = Number(item?.episode ?? 0)
      const anchor = String(item?.last_completed_scene_name ?? '').trim()
      if (episode > 0 && anchor) {
        result[String(episode)] = anchor
      }
    }
    return result
  }, [storyboardEpisodeTaskRows])

  const resumeableFailedStoryboardEpisodes = useMemo(() => (
    failedStoryboardEpisodes.filter((episode: number) => Boolean(storyboardResumeSceneMap[String(episode)]))
  ), [failedStoryboardEpisodes, storyboardResumeSceneMap])

  const retryOnlyFailedStoryboardEpisodes = useMemo(() => (
    failedStoryboardEpisodes.filter((episode: number) => !storyboardResumeSceneMap[String(episode)])
  ), [failedStoryboardEpisodes, storyboardResumeSceneMap])

  const fallbackStoryboardEpisodes = useMemo(() => (
    storyboardEpisodeTaskRows
      .filter((item: any) => item?.status === 'done' && Number(item?.fallback_scene_count ?? 0) > 0)
      .map((item: any) => Number(item.episode))
  ), [storyboardEpisodeTaskRows])

  const referencedVisualAssetSummary = useMemo(() => {
    return buildReferencedVisualAssetSummary(storyboardData, visualAssetData)
  }, [storyboardData, visualAssetData])

  const exportReadiness = useMemo(() => {
    return buildExportReadiness(
      storyboardData,
      scripts.length,
      visualReady,
      storyboardReadiness,
      getShotChecklist,
      referencedVisualAssetSummary,
    )
  }, [
    getShotChecklist,
    referencedVisualAssetSummary,
    scripts.length,
    storyboardData,
    storyboardReadiness,
    visualReady,
  ])

  // stepDone for StepBar
  const stepDone: Record<string, boolean> = {
    script: scriptStageReady,
    storyboard: storyboardReady,
    visual: visualReady,
    export: exportReadiness.canExport,
  }

  const productionOverview = useMemo(() => {
    const stats = [
      { label: '剧本', value: scriptReady ? `${scripts.length} 集` : outlineReady ? `${outlines.length} 集大纲` : bible ? '已有基础内容' : '未开始', ready: scriptStageReady },
      { label: '分镜', value: storyboardReady ? `${storyboardData.length} 个镜头` : '待生成', ready: storyboardReady },
      { label: '视觉设定', value: visualReady ? '已生成' : '待生成', ready: visualReady },
      { label: '下一站', value: visualReady && storyboardReady ? '可进入分镜生产' : storyboardReady ? '补齐视觉设定' : scriptStageReady ? '生成分镜' : '先完成内容准备', ready: visualReady && storyboardReady },
    ]

    if (runState === 'running') {
      return {
        tone: 'running' as const,
        title: '正在生产剧本内容',
        detail: '当前正在执行文本解析、改编和剧本生产，完成后会自动刷新本页内容。',
        primaryLabel: '查看当前进度',
        primaryAction: () => window.scrollTo({ top: 0, behavior: 'smooth' }),
        secondaryLabel: undefined,
        secondaryAction: undefined,
        stats,
      }
    }

    if (runState === 'error') {
      return {
        tone: 'error' as const,
        title: '剧本生产遇到错误',
        detail: '先检查报错信息与输入内容，再重新发起剧本生产，避免后续分镜和视觉设定建立在缺失数据上。',
        primaryLabel: '重新生成剧本',
        primaryAction: startPipeline,
        secondaryLabel: '去高级编排查看',
        secondaryAction: onSwitchToDev,
        stats,
      }
    }

    if (!scriptStageReady) {
      return {
        tone: 'info' as const,
        title: '先把文本变成可用剧本',
        detail: book.id <= 0
          ? '当前是空项目。建议先上传文件或粘贴小说内容，再一键生成完整剧本。'
          : '先确认输入来源、集数和时长，再一键生成完整剧本，为后续分镜与视觉资产打底。',
        primaryLabel: '生成剧本',
        primaryAction: startPipeline,
        secondaryLabel: '去高级编排手动处理',
        secondaryAction: onSwitchToDev,
        stats,
      }
    }

    if (!storyboardReady) {
      return {
        tone: 'warn' as const,
        title: '剧本已就绪，下一步生成分镜',
        detail: '先把已有剧本转换成分镜表，后续参考图、分镜图和视频都会依赖这些镜头数据。',
        primaryLabel: '去分镜生产',
        primaryAction: () => setActiveModule('storyboard'),
        secondaryLabel: '查看当前剧本',
        secondaryAction: () => setActiveModule('script'),
        stats,
      }
    }

    if (!visualReady) {
      return {
        tone: 'warn' as const,
        title: '分镜已就绪，下一步补齐视觉设定',
        detail: '建议现在生成时代、场景、道具和定妆设定，避免进入分镜生产后缺少统一视觉参考。',
        primaryLabel: '去视觉设定',
        primaryAction: () => setActiveModule('visual'),
        secondaryLabel: '回看分镜表',
        secondaryAction: () => setActiveModule('storyboard'),
        stats,
      }
    }

    return {
      tone: 'success' as const,
      title: '内容准备已齐备',
      detail: '剧本、分镜和视觉设定都已具备，可以进入分镜生产继续做参考图、分镜图、视频和成片交付。',
      primaryLabel: '打开分镜模块',
      primaryAction: () => setActiveModule('storyboard'),
      secondaryLabel: onOpenPrototype ? '打开创作沙盘' : '去高级编排',
      secondaryAction: onOpenPrototype ?? onSwitchToDev,
      stats,
    }
  }, [
    bible,
    book.id,
    onOpenPrototype,
    onSwitchToDev,
    outlineReady,
    outlines.length,
    runState,
    scriptReady,
    scriptStageReady,
    scripts.length,
    storyboardData.length,
    storyboardReady,
    visualReady,
  ])

  const llmModelSummary = modelDefaultsState === 'loading'
    ? '正在加载'
    : modelDefaultsState === 'error'
      ? '加载失败'
      : modelDefaults.llm?.name ?? '未设置'

  const embeddingModelSummary = modelDefaultsState === 'loading'
    ? '正在加载'
    : modelDefaultsState === 'error'
      ? '加载失败'
      : modelDefaults.embedding?.name ?? '未设置'

  const stageGuide = useMemo(() => {
    const stats = [
      { label: '剧本', value: scriptReady ? `${scripts.length} 集` : outlineReady ? `${outlines.length} 集大纲` : bible ? '已有基础内容' : '未开始', ready: scriptStageReady },
      { label: '分镜', value: storyboardReady ? `${storyboardData.length} 个镜头` : '待生成', ready: storyboardReady },
      { label: '视觉设定', value: visualReady ? '已生成' : '待生成', ready: visualReady },
      { label: '下一步', value: visualReady && storyboardReady ? '可进入分镜生产' : storyboardReady ? '补齐视觉设定' : scriptStageReady ? '生成分镜' : '先完成内容准备', ready: visualReady && storyboardReady },
    ]

    if (runState === 'running') {
      return {
        tone: 'running' as const,
        title: '正在生产剧本内容',
        detail: '当前正在执行文本解析、改编和剧本生产，完成后会自动刷新本页内容。',
        primaryLabel: '查看当前进度',
        primaryAction: () => window.scrollTo({ top: 0, behavior: 'smooth' }),
        secondaryLabel: undefined,
        secondaryAction: undefined,
        stats,
      }
    }

    if (runState === 'error') {
      return {
        tone: 'error' as const,
        title: '剧本生产遇到错误',
        detail: '先检查报错信息与输入内容，再重新发起剧本生产，避免后续分镜和视觉设定建立在缺失数据上。',
        primaryLabel: '重新生成剧本',
        primaryAction: startPipeline,
        secondaryLabel: '去高级编排查看',
        secondaryAction: onSwitchToDev,
        stats,
      }
    }

    if (!scriptStageReady) {
      return {
        tone: 'info' as const,
        title: '先把文本变成可用剧本',
        detail: book.id <= 0
          ? '当前是空项目。建议先上传文件或粘贴小说内容，再一键生成完整剧本。'
          : '先确认输入来源、集数和时长，再一键生成完整剧本，为后续分镜与视觉资产打底。',
        primaryLabel: '生成剧本',
        primaryAction: startPipeline,
        secondaryLabel: '去高级编排手动处理',
        secondaryAction: onSwitchToDev,
        stats,
      }
    }

    if (!storyboardReady) {
      return {
        tone: 'warn' as const,
        title: '剧本已就绪，下一步生成分镜',
        detail: '先把已有剧本转换成分镜表，后续参考图、分镜图和视频都会依赖这些镜头数据。',
        primaryLabel: '去分镜生产',
        primaryAction: () => setActiveModule('storyboard'),
        secondaryLabel: '查看当前剧本',
        secondaryAction: () => setActiveModule('script'),
        stats,
      }
    }

    if (!visualReady) {
      return {
        tone: 'warn' as const,
        title: '分镜已就绪，下一步补齐视觉设定',
        detail: '建议现在生成时代、场景、道具和定妆设定，避免进入分镜生产后缺少统一视觉参考。',
        primaryLabel: '去视觉设定',
        primaryAction: () => setActiveModule('visual'),
        secondaryLabel: '回看分镜表',
        secondaryAction: () => setActiveModule('storyboard'),
        stats,
      }
    }

    return {
      tone: 'success' as const,
      title: '内容准备已齐备',
      detail: '剧本、分镜和视觉设定都已具备，可以进入分镜生产继续做参考图、分镜图、视频和成片交付。',
      primaryLabel: '打开分镜模块',
      primaryAction: () => setActiveModule('storyboard'),
      secondaryLabel: onOpenPrototype ? '打开创作沙盘' : '去高级编排',
      secondaryAction: onOpenPrototype ?? onSwitchToDev,
      stats,
    }
  }, [
    bible,
    book.id,
    onOpenPrototype,
    onSwitchToDev,
    outlineReady,
    outlines.length,
    runState,
    scriptReady,
    scriptStageReady,
    scripts.length,
    storyboardData.length,
    storyboardReady,
    visualReady,
  ])

  // --- Render ---
  return (
    <div className="flex flex-1 overflow-hidden">
      <StepBar
        activeStep={activeModule}
        steps={STEPS}
        stepDone={stepDone}
        onStepClick={(k) => setActiveModule(k)}
        onOpenComposer={null}
      />

      <div className="flex-1 overflow-y-auto">
        <ProductionJourneyPanel
          title={stageGuide.title}
          detail={stageGuide.detail}
          tone={stageGuide.tone}
          stats={stageGuide.stats}
          primaryLabel={stageGuide.primaryLabel}
          primaryAction={stageGuide.primaryAction}
          secondaryLabel={stageGuide.secondaryLabel}
          secondaryAction={stageGuide.secondaryAction}
        />

        {activeModule === 'script' && (
          <div className="p-6">
            <div className="mb-4 flex flex-wrap gap-2">
              <button
                onClick={startPipeline}
                disabled={runState === 'running'}
                className={`text-xs px-4 py-2 rounded-lg transition-colors ${
                  runState === 'running'
                    ? 'bg-slate-800 text-slate-500 border border-slate-700 cursor-not-allowed'
                    : 'bg-blue-600 text-white hover:bg-blue-500'
                }`}
              >
                {runState === 'running' ? '剧本生成中...' : '一键生成完整剧本'}
              </button>
              <button
                onClick={() => setShowAdvanced((value) => !value)}
                className="text-xs px-4 py-2 rounded-lg border border-slate-700 text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
              >
                {showAdvanced ? '收起高级选项' : '展开高级选项'}
              </button>
            </div>
            {/* Header */}
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-lg font-bold text-[#f1f5f9]">📝 剧本生产</h1>
              <span className={`text-[15px] px-2 py-0.5 rounded-full ${
                runState === 'running' ? 'bg-yellow-900/40 text-yellow-400' :
                runState === 'done' ? 'bg-green-900/40 text-green-400' :
                'bg-slate-800 text-slate-500'
              }`}>
                {runState === 'idle' && !scriptReady ? '未开始' :
                 runState === 'running' ? '生成中' :
                 runState === 'done' ? '已完成' :
                 runState === 'error' ? '出错' :
                 scriptReady ? '有产出' : '未开始'}
              </span>
            </div>

            <div className="mb-4 rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3 text-sm text-slate-300">
              <div className="font-medium text-slate-100">剧本生产</div>
              <div className="mt-1 text-slate-400">先准备文本来源，再生成世界观、分集大纲、剧本和质检结果。</div>
            </div>

            {/* Editable Book Title */}
            <div className="mb-4">
              <BookTitleInput bookId={book.id} initialTitle={book.title} />
            </div>

            <div className="mb-4 rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-4 text-sm text-slate-300">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="font-medium text-slate-100">当前模型上下文</div>
                  <div className="mt-1 text-slate-400">
                    内容准备会优先使用默认 LLM 和默认向量模型来完成剧本、分镜表与检索链路。
                  </div>
                </div>
                <button
                  onClick={openModelRegistry}
                  className="rounded-full border border-violet-600/60 px-3 py-1.5 text-xs text-violet-200 transition hover:border-violet-400 hover:text-white"
                >
                  模型设置
                </button>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <div className="rounded-2xl border border-slate-800 bg-slate-950/60 px-3 py-3">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">LLM</div>
                  <div className="mt-1 text-sm text-slate-100">{llmModelSummary}</div>
                  <div className="mt-1 text-xs text-slate-500">{modelDefaults.llm?.provider ?? '默认文本生成配置'}</div>
                </div>
                <div className="rounded-2xl border border-slate-800 bg-slate-950/60 px-3 py-3">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">向量模型</div>
                  <div className="mt-1 text-sm text-slate-100">{embeddingModelSummary}</div>
                  <div className="mt-1 text-xs text-slate-500">{modelDefaults.embedding?.provider ?? '默认检索配置'}</div>
                </div>
              </div>
            </div>

            {/* Config */}
            <div className="bg-[#111827] border border-[#1e293b] rounded-xl p-5 mb-5">
              <div className="flex items-center gap-2 text-xs text-[#94a3b8] mb-4">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
                配置
              </div>
              <div className="grid grid-cols-5 gap-4 mb-4">
                {/* LEFT: Input + 格式 — col-span-3 */}
                <div className="col-span-3">
                  <label className="text-[15px] text-[#64748b] block mb-1.5"></label>
                  <div className="mb-2 flex flex-wrap gap-2">
                    <button onClick={() => setInputMode('upload')} className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${inputMode === 'upload' ? 'bg-blue-900/30 border-blue-600 text-blue-300' : 'bg-slate-900 border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white'}`}>上传文件</button>
                    <button onClick={() => setInputMode('text')} className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${inputMode === 'text' ? 'bg-blue-900/30 border-blue-600 text-blue-300' : 'bg-slate-900 border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white'}`}>粘贴文本</button>
                    {bookData ? (
                      <button onClick={() => setInputMode('book')} className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${inputMode === 'book' ? 'bg-blue-900/30 border-blue-600 text-blue-300' : 'bg-slate-900 border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white'}`}>使用当前项目文本</button>
                    ) : null}
                  </div>
                  <div className="flex gap-1 mb-2 flex-wrap">
                    <button onClick={() => setInputMode('upload')} className={`text-[15px] px-2.5 py-1.5 rounded-lg border transition-colors ${inputMode === 'upload' ? 'bg-blue-900/30 border-blue-600 text-blue-400' : 'bg-[#1e293b] border-[#334155] text-[#64748b] hover:text-[#94a3b8]'}`}>📁 上传文件</button>
                    <button onClick={() => setInputMode('text')} className={`text-[15px] px-2.5 py-1.5 rounded-lg border transition-colors ${inputMode === 'text' ? 'bg-blue-900/30 border-blue-600 text-blue-400' : 'bg-[#1e293b] border-[#334155] text-[#64748b] hover:text-[#94a3b8]'}`}>✏️ 粘贴文本</button>
                    {bookData && <button onClick={() => setInputMode('book')} className={`text-[15px] px-2.5 py-1.5 rounded-lg border transition-colors ${inputMode === 'book' ? 'bg-blue-900/30 border-blue-600 text-blue-400' : 'bg-[#1e293b] border-[#334155] text-[#64748b] hover:text-[#94a3b8]'}`}>📖 {bookData.title}</button>}
                  </div>
                  {inputMode === 'upload' && (
                    <label className="flex items-center justify-center gap-2 w-full rounded-lg bg-[#1e293b] border border-[#334155] border-dashed px-3 py-3 text-[15px] text-[#64748b] hover:border-blue-500 hover:text-blue-400 cursor-pointer transition-colors">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
                      点击上传 TXT / MD 文件
                      <input type="file" accept=".txt,.md" className="hidden" />
                    </label>
                  )}
                  {inputMode === 'text' && (
                    <textarea value={textInput} onChange={e => setTextInput(e.target.value)} placeholder="可直接粘贴小说文本，限 5000 字以内..." maxLength={5000} className="w-full h-16 text-[15px] bg-[#0f172a] border border-[#334155] rounded-lg px-2.5 py-2 text-[#cbd5e1] outline-none focus:border-blue-500 resize-none placeholder:text-[#475569]" />
                  )}
                  {inputMode === 'book' && bookData && <div className="text-xs text-[#e2e8f0] bg-[#1e293b] rounded-lg px-3 py-2 border border-[#334155]">{bookData.title}（{bookData.chapters}章，{((bookData.words || 0)/10000).toFixed(1)}万字）</div>}

                  <div className="mt-2 grid grid-cols-2 gap-3 text-[11px] text-slate-400">
                    <div>左侧输入区：选择文本来源。</div>
                    <div>右侧参数区：设置集数、时长和改编方向。</div>
                  </div>

                  {/* Output format row */}
                  <div className="grid grid-cols-2 gap-3 mt-3">
                    <div>
                      <label className="text-[15px] text-[#64748b] block mb-1">集数</label>
                      <div className="flex items-center gap-1">
                        <button onClick={() => setEpisodeCount(Math.max(1, episodeCount - 1))} className="w-8 h-8 rounded bg-[#1e293b] border border-[#334155] flex items-center justify-center text-[#64748b] hover:text-[#e2e8f0] text-xs">−</button>
                        <input type="number" value={episodeCount} onChange={e => setEpisodeCount(Math.max(1, Number(e.target.value)))} min={1} className="w-16 text-center text-[15px] bg-[#1e293b] border border-[#334155] rounded px-1.5 py-1 text-[#e2e8f0] outline-none focus:border-blue-500" />
                        <button onClick={() => setEpisodeCount(episodeCount + 1)} className="w-8 h-8 rounded bg-[#1e293b] border border-[#334155] flex items-center justify-center text-[#64748b] hover:text-[#e2e8f0] text-xs">+</button>
                      </div>
                    </div>
                    <div>
                      <label className="text-[15px] text-[#64748b] block mb-1">每集时长</label>
                      <select value={episodeDuration} onChange={e => setEpisodeDuration(Number(e.target.value))} className="w-full text-[15px] bg-[#1e293b] border border-[#334155] rounded px-2 py-1.5 text-[#e2e8f0] outline-none focus:border-blue-500">
                        {DURATION_OPTIONS.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
                      </select>
                    </div>
                  </div>
                </div>

                {/* RIGHT: 改编方向 — col-span-2 */}
                <div className="col-span-2">
                  <label className="text-[15px] text-[#64748b] block mb-1.5">🎯 改编方向</label>
                  <div className="bg-[#0f172a] border border-[#334155] rounded-lg p-3">
                    {/* 细分类型标签 */}
                    <div className="mb-2.5">
                      <label className="text-[15px] text-[#475569] block mb-1">细分类型</label>
                      <div className="flex gap-1 flex-wrap">
                        {['重生宅斗','穿越种田','霸总甜宠','先婚后爱','金手指爽文','系统流','宫斗权谋','神医弃妃'].map(t => (
                          <button key={t} onClick={() => setGenreSubtype(genreSubtype === t ? '' : t)} className={`text-[14px] px-2 py-0.5 rounded-full border transition-colors ${genreSubtype === t ? 'bg-blue-900/40 border-blue-600 text-blue-400' : 'bg-transparent border-[#334155] text-[#475569] hover:border-[#475569] hover:text-[#64748b]'}`}>{t}</button>
                        ))}
                      </div>
                    </div>

                    {/* 风格标签 */}
                    <div className="mb-2.5">
                      <label className="text-[15px] text-[#475569] block mb-1">基调 / 风格</label>
                      {TONE_PRESETS.map(group => (
                        <div key={group.group} className="mb-1.5 last:mb-0">
                          <span className="text-[12px] text-[#334155]">{group.group}</span>
                          <div className="flex gap-1 flex-wrap mt-0.5">
                            {group.items.map(tag => (
                              <button key={tag} onClick={() => toggleTone(tag)} className={`text-[14px] px-2 py-0.5 rounded-full border transition-colors ${toneTags.includes(tag) ? 'bg-purple-900/40 border-purple-600 text-purple-400' : 'bg-transparent border-[#334155] text-[#475569] hover:border-[#475569] hover:text-[#64748b]'}`}>{tag}</button>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* 自定义说明 */}
                    <div>
                      <label className="text-[15px] text-[#475569] block mb-1">自定义改编说明（选填）</label>
                      <textarea value={adaptDirection} onChange={e => setAdaptDirection(e.target.value)} placeholder="例如：参考《知否》风格，保留暖调田园气息，核心冲突提前到前2集..." className="w-full h-14 text-[15px] bg-[#0f172a] border border-[#334155] rounded px-2 py-1.5 text-[#cbd5e1] outline-none focus:border-blue-500 resize-none placeholder:text-[#334155]" />
                    </div>
                  </div>
                </div>
              </div>

              {/* Action row: button + advanced inline */}
              <div className="flex items-center gap-3 mt-1">
                <button onClick={startPipeline} disabled={runState === 'running'} className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white text-xs font-semibold rounded-lg hover:bg-blue-500 disabled:bg-blue-900/50 disabled:text-slate-500 transition-colors">
                  {runState === 'running' ? '⏳ 生成中...' : '▶ 一键生产完整剧本'}
                </button>
                <button onClick={() => setShowAdvanced(!showAdvanced)} className="text-[15px] text-[#475569] hover:text-[#64748b] flex items-center gap-1 transition-colors">
                  <svg className={`w-3 h-3 transition-transform ${showAdvanced ? 'rotate-90' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
                  高级选项
                </button>
              </div>

              {/* Advanced options panel */}
              {showAdvanced && (
                <div className="mt-3 flex items-center gap-4 pt-3 border-t border-[#1e293b]">
                  <div className="flex items-center gap-2">
                    <label className="text-[15px] text-[#64748b]">处理范围：</label>
                    <select value={scope} onChange={e => setScope(e.target.value as any)} className="text-[15px] bg-[#1e293b] border border-[#334155] rounded-lg px-2 py-1 text-[#e2e8f0] outline-none">
                      <option value="auto">自动分析</option>
                      <option value="first_n">仅前 N 章</option>
                      <option value="all">全部章节</option>
                    </select>
                  </div>
                  {scope === 'first_n' && <input type="number" value={scopeChapters} onChange={e => setScopeChapters(Math.max(5, Number(e.target.value)))} min={5} className="w-20 text-[15px] bg-[#1e293b] border border-[#334155] rounded-lg px-2 py-1 text-[#e2e8f0] outline-none" placeholder="章数" />}
                </div>
              )}
            </div>

            {/* Pipeline steps — clickable to show output */}
            <div className="flex items-center gap-0 mb-5 overflow-x-auto pb-1 scrollbar-none">
              {PIPELINE_STEPS.map((step, i) => {
                const idx = STEP_ORDER.indexOf(step.key)
                const done = pipelineDone > idx
                const active = pipelineDone === idx && runState === 'running'
                const tabMap: Record<string, OutputTab> = {
                  read: 'bible',
                  bible: 'bible',
                  portrait: 'portrait',
                  adapt: 'outline',
                  outline: 'outline',
                  script: 'script',
                  check: 'qa',
                  storyboard: 'storyboard',
                }
                return (
                  <div key={step.key} className="flex items-center shrink-0">
                    <button
                      onClick={() => { const t = tabMap[step.key]; if (t) setOutputTab(t) }}
                      className={`text-[15px] px-3 py-1.5 rounded-md whitespace-nowrap border transition-colors cursor-pointer ${
                        done ? 'bg-green-900/30 text-green-400 border-green-800/40 hover:bg-green-900/50' :
                        active ? 'bg-blue-900/40 text-blue-400 border-blue-700/40 animate-pulse' :
                        'bg-[#1e293b] text-[#475569] border-[#1e293b]'
                      }`}
                    >
                      {done ? '✓ ' : active ? '● ' : ''}{step.label}
                    </button>
                    {i < PIPELINE_STEPS.length - 1 && <span className="text-[#334155] mx-1.5 text-xs">→</span>}
                  </div>
                )
              })}
            </div>

            {/* Progress */}
            {(runState === 'running' || runState === 'error') && (
              <div className="mb-5">
                <div className="h-1.5 bg-[#1e293b] rounded-full overflow-hidden mb-2">
                  <div className="h-full bg-gradient-to-r from-blue-500 to-purple-500 rounded-full transition-all duration-500" style={{ width: `${Math.max(5, progress)}%` }} />
                </div>
                <div className="flex justify-between text-[15px] text-[#64748b]">
                  <span>{currentStep}</span>
                  <span>{Math.round(progress)}%</span>
                </div>
                {runState === 'error' && (
                  <div className="mt-3 p-3 rounded-lg bg-red-900/20 border border-red-800/50 text-[14px] text-red-400 font-mono whitespace-pre-wrap">
                    {currentStep}
                  </div>
                )}
              </div>
            )}

            {/* ─── 两列：Bible + Scripts ─── */}
            {(bible || scripts.length > 0) && (
              <div className="grid grid-cols-2 gap-5">
                <div className="bg-[#111827] border border-[#1e293b] rounded-xl p-5">
                  <div className="flex items-center justify-between mb-3">
                    <div className="text-[14px] font-semibold text-[#e2e8f0]">🌍 世界观圣经</div>
                    <div className="flex gap-2">
                      {editingBible ? (
                        <>
                          <button onClick={saveBible} disabled={savingMap['bible']} className="text-xs px-3 py-1 rounded bg-green-600 text-white hover:bg-green-500 disabled:opacity-50">
                            {savingMap['bible'] ? '保存中...' : '💾 保存'}
                          </button>
                          <button onClick={() => { setBibleDraft(bible); setEditingBible(false) }} className="text-xs px-3 py-1 rounded bg-[#1e293b] text-[#64748b] hover:text-[#94a3b8]">
                            取消
                          </button>
                        </>
                      ) : (
                        <button onClick={() => setEditingBible(true)} className="text-xs px-3 py-1 rounded bg-[#1e293b] text-[#64748b] hover:text-[#94a3b8]">
                          ✏️ 编辑
                        </button>
                      )}
                    </div>
                  </div>
                  {editingBible ? (
                    <textarea value={bibleDraft} onChange={e => setBibleDraft(e.target.value)} className="w-full h-[300px] bg-[#0f172a] border border-[#334155] rounded-lg p-3 text-xs text-[#cbd5e1] font-mono leading-relaxed outline-none focus:border-blue-500 resize-none" />
                  ) : (
                    <div className="text-xs text-[#94a3b8] leading-relaxed whitespace-pre-wrap max-h-[300px] overflow-y-auto">
                      {bible || '暂无圣经内容，请先运行管线'}
                    </div>
                  )}
                </div>
                <div className="bg-[#111827] border border-[#1e293b] rounded-xl p-5">
                  <div className="flex items-center justify-between mb-3">
                    <div className="text-[14px] font-semibold text-[#e2e8f0]">🎭 剧本</div>
                    <div className="flex items-center gap-2 flex-wrap">
                      {scripts.length === 0 && <span className="text-xs text-[#475569]">暂无集数</span>}
                      {Array.from({ length: Math.max(outlines.length, maxScriptEp) }, (_, i) => i + 1).map(ep => (
                        <button
                          key={ep}
                          onClick={() => {
                            setScriptEpisode(ep)
                            const found = scripts.find(s => s.episode === ep)
                            if (found) { setCurrentScript(found.content); setScriptDraft(found.content) }
                          }}
                          className={`text-xs px-2 py-1 rounded transition-colors ${
                            scriptEpisode === ep
                              ? 'bg-blue-600 text-white'
                              : ep <= maxScriptEp
                              ? 'bg-green-900/30 text-green-400'
                              : 'bg-[#1e293b] text-[#475569]'
                          }`}
                        >
                          {ep <= maxScriptEp ? '✓ ' : ''}第{ep}集
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="text-xs text-[#cbd5e1] whitespace-pre-wrap leading-relaxed max-h-[400px] overflow-y-auto font-mono">
                    {currentScript || '暂无剧本内容，请先运行管线'}
                  </div>
                </div>
              </div>
            )}

            {/* ─── Portrait display ─── */}
            {portrait && (
              <div className="bg-[#111827] border border-[#1e293b] rounded-xl p-5">
                <div className="flex items-center gap-2 mb-3">
                  <div className="text-xs font-semibold text-[#94a3b8]">👤 人物画像</div>
                </div>
                <div className="text-xs text-[#cbd5e1] whitespace-pre-wrap leading-relaxed max-h-[400px] overflow-y-auto font-mono">
                  {portrait}
                </div>
              </div>
            )}

            {/* ─── Outlines display ─── */}
            {outlines.length > 0 && (
              <div className="bg-[#111827] border border-[#1e293b] rounded-xl p-5">
                <div className="text-xs font-semibold text-[#94a3b8] mb-3">📋 分集大纲（共{outlines.length}集）</div>
                <div className="space-y-1 max-h-[400px] overflow-y-auto">
                  {outlines.map((o, i) => {
                    const editing = editingOutline === o.episode
                    const draft = outlineDrafts[o.episode]
                    const title = draft?.title ?? o.title
                    const summary = draft?.core_event ?? o.core_event ?? o.summary
                    return (
                      <div key={o.id || i} className="flex gap-2 items-start py-2 px-3 rounded-lg hover:bg-[#1e293b] group">
                        <span className="text-xs w-8 h-8 rounded bg-[#1e293b] flex items-center justify-center text-[#94a3b8] font-semibold shrink-0">
                          {o.episode}
                        </span>
                        <div className="flex-1 min-w-0">
                          {editing ? (
                            <div className="space-y-2">
                              <input value={draft?.title ?? o.title} onChange={e => setOutlineDrafts(m => ({ ...m, [o.episode]: { ...m[o.episode], title: e.target.value, core_event: m[o.episode]?.core_event ?? o.core_event } }))} className="w-full text-xs bg-[#0f172a] border border-[#334155] rounded px-2 py-1 text-[#e2e8f0] outline-none" placeholder="标题" />
                              <textarea value={draft?.core_event ?? o.core_event ?? ''} onChange={e => setOutlineDrafts(m => ({ ...m, [o.episode]: { core_event: e.target.value } }))} className="w-full h-16 text-xs bg-[#0f172a] border border-[#334155] rounded px-2 py-1 text-[#94a3b8] outline-none resize-none" placeholder="核心事件" />
                              <div className="flex gap-2">
                                <button onClick={() => saveOutline(o.episode)} disabled={savingMap[`outline_${o.episode}`]} className="text-xs px-2 py-1 rounded bg-green-600 text-white hover:bg-green-500">💾 保存</button>
                                <button onClick={() => { setEditingOutline(null); setOutlineDrafts(m => { const n = {...m}; delete n[o.episode]; return n }) }} className="text-xs px-2 py-1 rounded bg-[#1e293b] text-[#64748b]">取消</button>
                              </div>
                            </div>
                          ) : (
                            <>
                              <div className="text-xs font-medium text-[#e2e8f0]">{title}</div>
                              <div className="text-xs text-[#64748b] mt-0.5 truncate">{typeof summary === 'string' ? summary : JSON.stringify(summary)?.slice(0, 80)}</div>
                            </>
                          )}
                        </div>
                        {!editing && (
                          <button onClick={() => { setEditingOutline(o.episode); setOutlineDrafts(m => ({ ...m, [o.episode]: { title: o.title, core_event: o.core_event ?? o.summary } })) }} className="text-xs text-[#475569] hover:text-[#94a3b8] opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                            ✏️
                          </button>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* ─── QA workbench ─── */}
            {(qaData.length > 0 || qaWorkbench.length > 0) && (
              <div className="bg-[#111827] border border-[#1e293b] rounded-xl p-5">
                <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                  <div>
                    <div className="text-xs font-semibold text-[#94a3b8]">质检修复工作台</div>
                    <div className="text-xs text-[#64748b] mt-1">问题列表 {'->'} 定位原文 {'->'} 生成修复方案 {'->'} 应用修复 {'->'} 自动复检 {'->'} 版本回滚</div>
                  </div>
                </div>
                <WorkflowFeedbackBanner
                  status={qaWorkbenchState.status}
                  title={qaWorkbenchState.status === 'error'
                    ? '质检操作失败'
                    : qaWorkbenchState.status === 'loading'
                      ? '正在加载质检工作台'
                      : '质检工作台反馈'}
                  message={qaWorkbenchState.message}
                  hint="自动修复、人工修复、回滚后的复检结果都会在这里持续反馈，不再使用浏览器弹窗。"
                  className="mb-4"
                />

                <div className="space-y-4">
                  {qaWorkbench.map((episodeEntry: any, index: number) => {
                    const episodeIssues = Array.isArray(episodeEntry.issues) ? episodeEntry.issues : []
                    const episodeVersions = Array.isArray(episodeEntry.versions) ? episodeEntry.versions : []
                    const qaSummary = episodeEntry.qa_summary || {}
                    const autoFixReport = qaAutoFixReportsByEpisode[episodeEntry.episode]
                    return (
                      <details key={episodeEntry.episode || index} open={index === 0} className="rounded-xl border border-[#1e293b] bg-[#0f172a]">
                        <summary className="cursor-pointer list-none px-4 py-3">
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-sm font-semibold text-[#e2e8f0]">第 {episodeEntry.episode} 集</span>
                              <span className={`rounded-full px-2 py-1 text-[11px] ${
                                (qaSummary.open_issue_count || 0) === 0 ? 'bg-emerald-900/40 text-emerald-300' : 'bg-rose-900/40 text-rose-300'
                              }`}>
                                {(qaSummary.open_issue_count || 0) === 0 ? '复检通过' : `待处理 ${qaSummary.open_issue_count || 0}`}
                              </span>
                              {typeof qaSummary.overall_score !== 'undefined' && qaSummary.overall_score !== null && (
                                <span className="rounded-full bg-slate-800 px-2 py-1 text-[11px] text-slate-300">评分 {qaSummary.overall_score}</span>
                              )}
                            </div>
                            <div className="flex flex-wrap items-center gap-2">
                              <button
                                onClick={(event) => { event.preventDefault(); syncQaEpisode(episodeEntry.episode) }}
                                className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:border-slate-500"
                              >
                                {qaBusyMap[`sync-${episodeEntry.episode}`] ? '同步中...' : '同步问题'}
                              </button>
                              <button
                                onClick={(event) => { event.preventDefault(); recheckQaEpisode(episodeEntry.episode) }}
                                className="rounded-full border border-emerald-700 px-3 py-1 text-xs text-emerald-300 hover:border-emerald-500"
                              >
                                {qaBusyMap[`recheck-${episodeEntry.episode}`] ? '复检中...' : '整集复检'}
                              </button>
                              <button
                                onClick={(event) => { event.preventDefault(); autoFixQaEpisode(episodeEntry.episode) }}
                                className="rounded-full border border-lime-700 px-3 py-1 text-xs text-lime-300 hover:border-lime-500"
                              >
                                {qaBusyMap[`autofix-episode-${episodeEntry.episode}`] ? '自动修复中...' : '自动修复本集'}
                              </button>
                            </div>
                          </div>
                        </summary>

                        <div className="px-4 pb-4 space-y-4">
                          {autoFixReport && (
                            <div className="rounded-xl border border-lime-900/40 bg-lime-950/10 p-4">
                              <div className="flex flex-wrap items-center gap-2">
                                <div className="text-sm font-semibold text-lime-200">自动修复报告</div>
                                <span className="rounded-full bg-lime-900/30 px-2 py-0.5 text-[11px] text-lime-200">已修复 {autoFixReport.applied_count || 0}</span>
                                <span className="rounded-full bg-rose-900/30 px-2 py-0.5 text-[11px] text-rose-200">未修复 {autoFixReport.failed_count || 0}</span>
                                {autoFixReport.failed_summary?.safety_guard_blocked ? (
                                  <span className="rounded-full bg-amber-900/30 px-2 py-0.5 text-[11px] text-amber-200">护栏拦截 {autoFixReport.failed_summary.safety_guard_blocked}</span>
                                ) : null}
                                {autoFixReport.failed_summary?.stopped_after_failed_rechecks ? (
                                  <span className="rounded-full bg-rose-900/30 px-2 py-0.5 text-[11px] text-rose-200">停手 {autoFixReport.failed_summary.stopped_after_failed_rechecks}</span>
                                ) : null}
                              </div>
                              {Array.isArray(autoFixReport.applied) && autoFixReport.applied.length > 0 && (
                                <div className="mt-3 space-y-2">
                                  {autoFixReport.applied.map((item: any) => (
                                    <div key={`autofix-applied-${item.issue_id}`} className="rounded-lg border border-lime-900/30 bg-slate-950/40 px-3 py-2 text-xs text-slate-300">
                                      <div className="font-medium text-lime-200">{item.title || item.issue_id}</div>
                                      <div className="mt-1 text-slate-400">已采用方案 {item.option_id || 'A'}{item.strategy ? ` · ${item.strategy}` : ''}</div>
                                      {item.guard ? (
                                        <div className="mt-1 text-slate-500">护栏评估：变更行数 {item.guard.changed_line_count} · 长度偏移 {Math.round((Number(item.guard.length_delta_ratio || 0)) * 100)}%</div>
                                      ) : null}
                                    </div>
                                  ))}
                                </div>
                              )}
                              {Array.isArray(autoFixReport.failed) && autoFixReport.failed.length > 0 && (
                                <div className="mt-3 space-y-2">
                                  {autoFixReport.failed.map((item: any) => {
                                    const failureMeta = getQaAutoFixFailureMeta(item.failure_kind)
                                    const relatedIssue = episodeIssues.find((issue: any) => issue.issue_id === item.issue_id)
                                    return (
                                    <div key={`autofix-failed-${item.issue_id}`} className="rounded-lg border border-rose-900/30 bg-slate-950/40 px-3 py-2 text-xs text-rose-200">
                                      <div className="flex flex-wrap items-center gap-2">
                                        <div className="font-medium">{item.title || item.issue_id}</div>
                                        <span className={`rounded-full border px-2 py-0.5 text-[11px] ${failureMeta.tone}`}>{failureMeta.label}</span>
                                      </div>
                                      <div className="mt-1 text-rose-300">{item.reason || '自动修复失败'}</div>
                                      {relatedIssue ? (
                                        <div className="mt-2 flex flex-wrap gap-2">
                                          <button
                                            onClick={() => { void routeQaAutoFixFailureToManual(relatedIssue, item.failure_kind) }}
                                            className="rounded-lg border border-slate-700 px-3 py-1 text-[11px] text-slate-200 transition-colors hover:border-slate-500"
                                          >
                                            {getQaAutoFixFailureActionLabel(item.failure_kind)}
                                          </button>
                                          <button
                                            onClick={() => setQaOpenLocations((prev) => ({ ...prev, [relatedIssue.issue_id]: true }))}
                                            className="rounded-lg border border-slate-800 px-3 py-1 text-[11px] text-slate-400 transition-colors hover:border-slate-600 hover:text-slate-200"
                                          >
                                            打开原文定位
                                          </button>
                                        </div>
                                      ) : null}
                                    </div>
                                  )})}
                                </div>
                              )}
                            </div>
                          )}
                          {episodeIssues.length === 0 ? (
                            <div className="rounded-xl border border-dashed border-slate-800 px-4 py-4 text-sm text-slate-400">
                              当前还没有结构化问题条目。如果这一集已有 QA 结果，页面会自动同步；也可以手动点击“同步问题”重新整理。
                            </div>
                          ) : (
                            <div className="space-y-3">
                              {episodeIssues.map((issue: any) => {
                                const options = qaFixOptionsByIssue[issue.issue_id] || []
                                const draftText = qaPatchDrafts[issue.issue_id] ?? ''
                                const preview = qaPreviewByIssue[issue.issue_id]
                                const fixStatusMeta = QA_FIX_STATUS_META[issue.fix_status || 'pending'] || QA_FIX_STATUS_META.pending
                                const isFocusedIssue = qaFocusedIssueId === issue.issue_id
                                return (
                                  <div
                                    key={issue.issue_id}
                                    ref={(node) => { qaIssueCardRefs.current[issue.issue_id] = node }}
                                    className={`rounded-xl border bg-[#111827] p-4 space-y-3 transition-all duration-500 ${
                                      isFocusedIssue
                                        ? 'border-sky-500 shadow-[0_0_0_1px_rgba(56,189,248,0.45),0_0_32px_rgba(14,165,233,0.18)]'
                                        : 'border-[#1e293b]'
                                    }`}
                                  >
                                    <div className="flex flex-wrap items-start justify-between gap-3">
                                      <div>
                                        <div className="flex flex-wrap items-center gap-2">
                                          <span className="text-sm font-semibold text-slate-100">{issue.title || issue.description}</span>
                                          <span className={`rounded-full px-2 py-0.5 text-[11px] ${
                                            issue.severity === 'high' ? 'bg-rose-900/40 text-rose-300' :
                                            issue.severity === 'medium' ? 'bg-amber-900/40 text-amber-300' :
                                            'bg-slate-800 text-slate-300'
                                          }`}>{issue.severity || 'medium'}</span>
                                          <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[11px] text-slate-300">{issue.type || 'unknown'}</span>
                                          <span className={`rounded-full px-2 py-0.5 text-[11px] ${fixStatusMeta.tone}`}>{fixStatusMeta.label}</span>
                                        </div>
                                        <div className="mt-2 text-sm text-slate-300">{issue.description}</div>
                                        {issue.status_reason && (
                                          <div className="mt-1 text-xs text-slate-400">{issue.status_reason}</div>
                                        )}
                                        {(issue.location?.script_section || issue.location?.line_range?.length > 0) && (
                                          <div className="mt-2 text-xs text-slate-500">
                                            {issue.location?.script_section || '未标记场次'}
                                            {issue.location?.line_range?.length > 0 ? ` · 行 ${issue.location.line_range[0]}-${issue.location.line_range[1]}` : ''}
                                          </div>
                                        )}
                                      </div>
                                      <div className="flex flex-wrap gap-2">
                                        <button
                                          onClick={() => setQaOpenLocations((prev) => ({ ...prev, [issue.issue_id]: !prev[issue.issue_id] }))}
                                          className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:border-slate-500"
                                        >
                                          查看定位
                                        </button>
                                        <button
                                          onClick={() => generateQaFixOptions(issue)}
                                          className="rounded-full border border-sky-700 px-3 py-1 text-xs text-sky-300 hover:border-sky-500"
                                        >
                                          {qaBusyMap[`options-${issue.issue_id}`] ? '生成中...' : '生成修复方案'}
                                        </button>
                                        <button
                                          onClick={() => previewQaFix(issue)}
                                          className="rounded-full border border-violet-700 px-3 py-1 text-xs text-violet-300 hover:border-violet-500"
                                        >
                                          {qaBusyMap[`preview-${issue.issue_id}`] ? '预览中...' : '预览 diff'}
                                        </button>
                                        <button
                                          onClick={() => applyQaFix(issue)}
                                          className="rounded-full border border-emerald-700 px-3 py-1 text-xs text-emerald-300 hover:border-emerald-500"
                                        >
                                          {qaBusyMap[`apply-${issue.issue_id}`] ? '应用中...' : '应用修复'}
                                        </button>
                                        <button
                                          onClick={() => autoFixQaIssue(issue)}
                                          className="rounded-full border border-lime-700 px-3 py-1 text-xs text-lime-300 hover:border-lime-500"
                                        >
                                          {qaBusyMap[`autofix-${issue.issue_id}`] ? '自动修复中...' : '一键自动修复'}
                                        </button>
                                      </div>
                                    </div>

                                    {qaOpenLocations[issue.issue_id] && (
                                      <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                                        <div className="text-xs font-semibold text-slate-300 mb-2">原文定位</div>
                                        <pre className="whitespace-pre-wrap text-xs leading-6 text-slate-300">{issue.source_excerpt || '当前问题还没有精确原文定位。'}</pre>
                                      </div>
                                    )}

                                    {issue.suggestion && (
                                      <div className="rounded-xl border border-amber-900/30 bg-amber-950/20 p-3 text-xs text-amber-100">
                                        修复建议：{issue.suggestion}
                                      </div>
                                    )}

                                    {options.length > 0 && (
                                      <div className="space-y-2">
                                        <div className="text-xs font-semibold text-slate-300">修复方案</div>
                                        <div className="space-y-2">
                                          {options.map((option: any) => (
                                            <button
                                              key={option.id}
                                              onClick={() => {
                                                setQaSelectedOptionByIssue((prev) => ({ ...prev, [issue.issue_id]: option.id || '' }))
                                                setQaPatchDrafts((prev) => ({ ...prev, [issue.issue_id]: option.patched_text || '' }))
                                                setQaPreviewByIssue((prev) => {
                                                  const next = { ...prev }
                                                  delete next[issue.issue_id]
                                                  return next
                                                })
                                              }}
                                              className="w-full rounded-xl border border-slate-800 bg-slate-950/50 px-3 py-2 text-left hover:border-slate-600"
                                            >
                                              <div className="text-xs font-semibold text-slate-200">{option.id}. {option.title || '未命名方案'}</div>
                                              <div className="mt-1 text-xs text-slate-400">{option.strategy || '未提供修复思路'}</div>
                                            </button>
                                          ))}
                                        </div>
                                      </div>
                                    )}

                                    <div className="grid gap-3 lg:grid-cols-2">
                                      <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
                                        <div className="text-xs font-semibold text-slate-300 mb-2">修复前</div>
                                        <pre className="whitespace-pre-wrap text-xs leading-6 text-slate-400">{issue.source_excerpt || '暂无原文片段'}</pre>
                                      </div>
                                      <div className="rounded-xl border border-emerald-900/30 bg-emerald-950/10 p-3">
                                        <div className="text-xs font-semibold text-emerald-200 mb-2">修复后预览</div>
                                        <textarea
                                          value={draftText}
                                          onChange={(event) => {
                                            setQaPatchDrafts((prev) => ({ ...prev, [issue.issue_id]: event.target.value }))
                                            setQaPreviewByIssue((prev) => {
                                              const next = { ...prev }
                                              delete next[issue.issue_id]
                                              return next
                                            })
                                          }}
                                          className="min-h-[180px] w-full rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs leading-6 text-slate-200 outline-none"
                                          placeholder="这里会显示自动生成的修复片段，也可以手动编辑。"
                                        />
                                      </div>
                                    </div>

                                    <div className="rounded-xl border border-violet-900/30 bg-violet-950/10 p-3">
                                      <div className="flex flex-wrap items-center justify-between gap-2">
                                        <div className="text-xs font-semibold text-violet-200">diff 预览</div>
                                        <div className="text-[11px] text-violet-300">
                                          {preview ? '已预览，可安全应用修复' : '应用修复前必须先预览 diff'}
                                        </div>
                                      </div>
                                      {preview?.diff_text ? (
                                        <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-950/80 p-3 text-[11px] leading-5 text-slate-300">{preview.diff_text}</pre>
                                      ) : (
                                        <div className="mt-2 text-xs text-slate-400">点击“预览 diff”后，这里会显示修复前后的统一 diff，帮助你确认只修改了目标片段。</div>
                                      )}
                                    </div>
                                  </div>
                                )
                              })}
                            </div>
                          )}

                          <div className="rounded-xl border border-[#1e293b] bg-[#111827] p-4">
                            <div className="flex items-center justify-between gap-3 mb-3">
                              <div>
                                <div className="text-sm font-semibold text-slate-100">版本记录</div>
                                <div className="text-xs text-slate-500">每次修复都会生成新版本，并支持回滚。</div>
                              </div>
                            </div>
                            {episodeVersions.length === 0 ? (
                              <div className="text-sm text-slate-400">当前还没有修复版本。</div>
                            ) : (
                              <div className="space-y-2">
                                {episodeVersions.map((version: any) => (
                                  <div key={version.id} className="rounded-xl border border-slate-800 bg-slate-950/50 px-3 py-3">
                                    <div className="flex flex-wrap items-center justify-between gap-3">
                                      <div>
                                        {(() => {
                                          const recheckMeta = QA_RECHECK_STATUS_META[version.recheck_status || 'not_run'] || QA_RECHECK_STATUS_META.not_run
                                          return (
                                            <>
                                        <div className="text-sm font-semibold text-slate-100">{version.label || `v${version.version_no}`}</div>
                                        <div className="mt-1 text-xs text-slate-400">{version.change_reason || '无修复原因说明'}</div>
                                              <div className={`mt-1 text-[11px] ${recheckMeta.tone}`}>复检：{recheckMeta.label}{version.recheck_summary ? ` · ${version.recheck_summary}` : ''}</div>
                                            </>
                                          )
                                        })()}
                                      </div>
                                      {version.change_type !== 'baseline' && (
                                        <button
                                          onClick={() => setQaPendingRollback({
                                            episode: episodeEntry.episode,
                                            versionId: version.id,
                                            versionLabel: version.label || `v${version.version_no}`,
                                          })}
                                          className="rounded-full border border-rose-700 px-3 py-1 text-xs text-rose-300 hover:border-rose-500"
                                        >
                                          {qaBusyMap[`rollback-${version.id}`] ? '回滚中...' : '回滚到修复前'}
                                        </button>
                                      )}
                                    </div>
                                    {qaPendingRollback?.versionId === version.id ? (
                                      <InlineConfirmBar
                                        title="确认回滚这个修复版本？"
                                        message="回滚后会恢复到这次修复前的剧本内容，并自动触发整集复检。建议在确认前先查看下方 diff。"
                                        confirmLabel="确认回滚并复检"
                                        busy={Boolean(qaBusyMap[`rollback-${version.id}`])}
                                        onConfirm={() => rollbackQaVersion(episodeEntry.episode, version.id)}
                                        onCancel={() => setQaPendingRollback((current) => current?.versionId === version.id ? null : current)}
                                        className="mt-3"
                                      />
                                    ) : null}
                                    {version.diff_text && (
                                      <details className="mt-3">
                                        <summary className="cursor-pointer text-xs text-sky-300">查看 diff</summary>
                                        <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-950/80 p-3 text-[11px] leading-5 text-slate-300">{version.diff_text}</pre>
                                      </details>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>

                          {qaData.find((item: any) => item.episode === episodeEntry.episode)?.result && (
                            <details className="rounded-xl border border-dashed border-slate-800 bg-slate-950/30 p-3">
                              <summary className="cursor-pointer text-xs text-slate-400">查看原始 QA JSON</summary>
                              <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-xs leading-6 text-slate-400">
                                {JSON.stringify(qaData.find((item: any) => item.episode === episodeEntry.episode)?.result, null, 2)}
                              </pre>
                            </details>
                          )}
                        </div>
                      </details>
                    )
                  })}
                </div>
              </div>
            )}


            {/* Empty state */}
            {!bible && outlines.length === 0 && scripts.length === 0 && runState === 'idle' && (
              <div className="text-center py-20">
                <div className="text-3xl mb-3">📝</div>
                <div className="text-sm text-[#64748b]">配置上方参数后点击「一键生产完整剧本」</div>
              </div>
            )}
            {/*
              <div className="text-xs font-semibold text-[#94a3b8] mb-4">旧版交付历史（待清理）</div>
              {exportRecords.length === 0 ? (
                <div className="text-sm text-slate-400">旧版交付历史占位内容，当前请以下方正式交付历史为准。</div>
              ) : (
                <div className="space-y-3">
                  {exportRecords.slice(0, 10).map((record) => (
                    <div key={record.id} className="rounded-lg border border-slate-800 bg-slate-950/60 px-4 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-slate-100">{String(record.export_format || '').toUpperCase()}</span>
                        <span className={`rounded-full px-2 py-0.5 text-[11px] ${
                          record.status === 'completed'
                            ? 'bg-emerald-900/40 text-emerald-300'
                            : 'bg-amber-900/40 text-amber-300'
                        }`}>
                          {record.status === 'completed' ? '\u5df2\u5b8c\u6210' : '\u672a\u901a\u8fc7'}
                        </span>
                        <span className="text-xs text-slate-500">{record.created_at || '-'}</span>
                      </div>
                      <div className="mt-2 text-xs text-slate-300">{getLegacyRecordSummary(record)}</div>
                      <div className="mt-2 grid gap-2 md:grid-cols-4 text-xs text-slate-400">
                        <div>{'\u603b\u955c\u5934\uff1a'}{record.total_shots}</div>
                        <div>{'\u53ef\u4ea4\u4ed8\uff1a'}{record.deliverable_shots}</div>
                        <div>{'\u5f85\u9a8c\u6536\uff1a'}{record.pending_review_shots}</div>
                        <div>{'\u963b\u585e\uff1a'}{record.blocked_shots}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            */}
            <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900/50 p-4">
              <div className="text-xs font-semibold text-slate-300">交付历史</div>
              {exportRecords.length === 0 ? (
                <div className="mt-2 text-sm text-slate-400">还没有已保存的交付记录，可以先登记一次交付或导出 JSON。</div>
              ) : (
                <div className="mt-3 space-y-3">
                  {exportRecords.slice(0, 10).map((record) => (
                    <div key={record.id} className="rounded-lg border border-slate-800 bg-slate-950/60 px-4 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-slate-100">{String(record.export_format || '').toUpperCase()}</span>
                        <span className={`rounded-full px-2 py-0.5 text-[11px] ${
                          record.status === 'completed'
                            ? 'bg-emerald-900/40 text-emerald-300'
                            : 'bg-amber-900/40 text-amber-300'
                        }`}>
                          {record.status === 'completed' ? '已完成' : '阻塞'}
                        </span>
                        <span className="text-xs text-slate-500">{record.created_at || '-'}</span>
                      </div>
                      <div className="mt-2 text-xs text-slate-300">{getLegacyRecordSummary(record)}</div>
                      <div className="mt-2 grid gap-2 text-xs text-slate-400 md:grid-cols-4">
                        <div>总镜头：{record.total_shots}</div>
                        <div>可交付：{record.deliverable_shots}</div>
                        <div>待验收：{record.pending_review_shots}</div>
                        <div>阻塞：{record.blocked_shots}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {activeModule === 'storyboard' && (
          <div className="p-6">
            <div className="mb-4 flex flex-wrap gap-2">
              <button
                disabled={scripts.length === 0 || sbRunState === 'running' || selectedSBEps.size === 0}
                onClick={() => void startStoryboard()}
                className={`text-xs px-4 py-2 rounded-lg transition-colors ${
                  scripts.length === 0 || sbRunState === 'running' || selectedSBEps.size === 0
                    ? 'bg-slate-800 text-slate-500 border border-slate-700 cursor-not-allowed'
                    : 'bg-blue-900/30 border border-blue-600 text-blue-300 hover:bg-blue-900/50'
                }`}
              >
                {sbRunState === 'running' ? '分镜生成中...' : `开始生成分镜（${selectedSBEps.size}集）`}
              </button>
              <button
                onClick={() => setActiveModule('script')}
                className="text-xs px-4 py-2 rounded-lg border border-slate-700 text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
              >
                返回内容准备
              </button>
              {failedStoryboardEpisodes.length > 0 && (
                <button
                  disabled={sbRunState === 'running'}
                  onClick={() => setSelectedSBEps(new Set(failedStoryboardEpisodes))}
                  className="text-xs px-4 py-2 rounded-lg bg-rose-900/20 border border-rose-700/60 text-rose-200 hover:bg-rose-900/40 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                >
                  选择失败集（{failedStoryboardEpisodes.length}）
                </button>
              )}
              {failedStoryboardEpisodes.length > 0 && (
                <button
                  disabled={sbRunState === 'running'}
                  onClick={() => void startStoryboard(failedStoryboardEpisodes)}
                  className="text-xs px-4 py-2 rounded-lg bg-amber-900/30 border border-amber-600 text-amber-200 hover:bg-amber-900/50 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                >
                  只重试失败集
                </button>
              )}
              {resumeableFailedStoryboardEpisodes.length > 0 && (
                <button
                  disabled={sbRunState === 'running'}
                  onClick={() => void startStoryboard(
                    resumeableFailedStoryboardEpisodes,
                    {
                      resumeFromScene: Object.fromEntries(
                        resumeableFailedStoryboardEpisodes
                          .map((episode: number) => [String(episode), storyboardResumeSceneMap[String(episode)]])
                          .filter((entry: [string, string | undefined]): entry is [string, string] => Boolean(entry[1])),
                      ),
                    },
                  )}
                  className="text-xs px-4 py-2 rounded-lg bg-sky-900/30 border border-sky-600 text-sky-200 hover:bg-sky-900/50 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                >
                  从断点继续失败集（推荐）
                </button>
              )}
            </div>
            <div className="flex items-center gap-3 mb-4">
              <h1 className="text-lg font-bold text-[#f1f5f9]">🎬 分镜生产</h1>
              <span className={`text-[15px] px-2 py-0.5 rounded-full ${storyboardData.length > 0 ? 'bg-green-900/40 text-green-400' : 'bg-slate-800 text-slate-500'}`}>
                {storyboardData.length > 0 ? '已生成' : '未生成'}
              </span>
            </div>

            {false && storyboardData.length === 0 && scripts.length === 0 && sbRunState === 'idle' && (
              <div className="mb-4">
                <EmptyStepCard
                  icon="🎬"
                  title="还不能生成分镜"
                  detail="分镜生产依赖剧本内容。先回到“内容准备”生成分集剧本，再回来批量生成分镜。"
                  primaryLabel="去内容准备"
                  onPrimary={() => setActiveModule('script')}
                  secondaryLabel="去高级编排"
                  onSecondary={onSwitchToDev}
                />
              </div>
            )}

            {storyboardData.length === 0 && scripts.length === 0 && sbRunState === 'idle' && (
              <div className="mb-4">
                <EmptyStepCard
                  icon="🎬"
                  title="还不能生成分镜"
                  detail="分镜生产依赖剧本内容。先回到“内容准备”生成分集剧本，再回来批量生成分镜。"
                  primaryLabel="去内容准备"
                  onPrimary={() => setActiveModule('script')}
                  secondaryLabel="去高级编排"
                  onSecondary={onSwitchToDev}
                />
              </div>
            )}

            <div className="mb-4 rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3 text-sm text-slate-300">
              <div className="font-medium text-slate-100">分镜生产</div>
              <div className="mt-1 text-slate-400">基于分集剧本批量生成镜头级分镜，为后续参考图、分镜图和视频准备镜头数据。</div>
            </div>

            <div className="bg-[#111827] border border-[#1e293b] rounded-xl p-5 mb-4">
              <div className="text-xs text-[#64748b] mb-3">🎬 分镜生成</div>
              <div className="text-[14px] text-[#94a3b8] mb-3">
                选择需要生成分镜的集数。已生成分镜的集可单独勾选来重新生成。
              </div>

              {/* Episode selection grid */}
              {scripts.length > 0 && (
                <div className="mb-3">
                  <label className="flex items-center gap-2 text-[13px] text-[#94a3b8] cursor-pointer hover:text-[#cbd5e1] mb-2">
                    <input
                      type="checkbox"
                      checked={selectedSBEps.size === scripts.length}
                      onChange={() => {
                        if (selectedSBEps.size === scripts.length) {
                          setSelectedSBEps(new Set())
                        } else {
                          setSelectedSBEps(new Set(scripts.map(s => s.episode)))
                        }
                      }}
                      className="accent-blue-500"
                    />
                    <span className="font-medium">全选</span>
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {(() => {
                      const sbEpSet = new Set(storyboardData.map(s => s.episode))
                      return scripts.slice().sort((a: any, b: any) => a.episode - b.episode).map((sc: any) => {
                        const hasSb = sbEpSet.has(sc.episode)
                        return (
                          <label
                            key={sc.episode}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg cursor-pointer transition-colors text-[14px] ${
                              selectedSBEps.has(sc.episode)
                                ? 'bg-blue-900/30 border border-blue-700/50'
                                : 'bg-[#1e293b] border border-[#334155] hover:bg-[#263548]'
                            } ${hasSb ? 'text-emerald-400' : 'text-[#94a3b8]'}`}
                          >
                            <input
                              type="checkbox"
                              checked={selectedSBEps.has(sc.episode)}
                              onChange={() => {
                                setSelectedSBEps(prev => {
                                  const next = new Set(prev)
                                  if (next.has(sc.episode)) next.delete(sc.episode)
                                  else next.add(sc.episode)
                                  return next
                                })
                              }}
                              className="accent-blue-500"
                            />
                            第{sc.episode}集{hasSb ? ' ✓' : ''}
                          </label>
                        )
                      })
                    })()}
                  </div>
                </div>
              )}

              <div className="flex items-center gap-2">
                <button
                  disabled={scripts.length === 0 || sbRunState === 'running' || selectedSBEps.size === 0}
                  onClick={() => void startStoryboard()}
                  className={`text-xs px-4 py-2 rounded-lg transition-colors ${
                    sbRunState === 'running' || selectedSBEps.size === 0
                      ? 'bg-amber-900/40 text-amber-400 border border-amber-800/50 cursor-not-allowed'
                      : 'bg-blue-900/30 border border-blue-600 text-blue-400 hover:bg-blue-900/50'
                  }`}
                >
                  {sbRunState === 'running'
                    ? '⏳ 生成中...'
                    : `▶️ 生成选中集的分镜 (${selectedSBEps.size}集)`}
                </button>
                {storyboardData.length > 0 && (
                  <>
                    <button
                      disabled={storyboardBatchState.status === 'running' || selectedSBEps.size === 0}
                      onClick={batchCompileSelectedEpisodes}
                      className="text-xs px-4 py-2 rounded-lg bg-sky-900/30 border border-sky-600 text-sky-300 hover:bg-sky-900/50 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      批量编译已选集
                    </button>
                    <button
                      disabled={storyboardBatchState.status === 'running' || selectedSBEps.size === 0}
                      onClick={autoBindSelectedEpisodes}
                      className="text-xs px-4 py-2 rounded-lg bg-amber-900/30 border border-amber-600 text-amber-200 hover:bg-amber-900/50 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      同步视觉绑定已选集
                    </button>
                    <button
                      disabled={storyboardBatchState.status === 'running' || selectedSBEps.size === 0}
                      onClick={batchGenerateFramesSelectedEpisodes}
                      className="text-xs px-4 py-2 rounded-lg bg-emerald-900/30 border border-emerald-600 text-emerald-300 hover:bg-emerald-900/50 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      批量补首帧已选集
                    </button>
                    <button
                      disabled={storyboardBatchState.status === 'running' || selectedSBEps.size === 0}
                      onClick={batchGenerateVideosSelectedEpisodes}
                      className="text-xs px-4 py-2 rounded-lg bg-fuchsia-900/30 border border-fuchsia-600 text-fuchsia-300 hover:bg-fuchsia-900/50 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      批量补视频已选集
                    </button>
                    <details className="relative">
                      <summary className="cursor-pointer list-none rounded-lg border border-slate-700 px-4 py-2 text-xs text-slate-400 transition-colors hover:border-slate-500 hover:text-slate-200">
                        更多操作
                      </summary>
                      <div className="mt-2 rounded-lg border border-red-900/50 bg-slate-950 p-2">
                        <button
                          onClick={async () => {
                            if (!confirm('确定删除所有分镜数据？删除后可以重新生成。')) return
                            setStoryboardData([])
                            setTimeout(async () => {
                              await fetch(`/api/pipeline/storyboard/book/${book.id}`, { method: 'DELETE' })
                              onRefresh()
                              fetchOutputs()
                            }, 50)
                          }}
                          className="text-xs px-4 py-2 rounded-lg bg-red-900/30 border border-red-600/50 text-red-400 hover:bg-red-900/50 transition-colors"
                        >
                          🗑️ 删除所有分镜
                        </button>
                      </div>
                    </details>
                  </>
                )}
              </div>
            </div>

            {(sbRunState === 'running' || sbRunState === 'error' || sbRunState === 'partial' || storyboardEpisodeTaskRows.length > 0) && (
              <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-4 mb-4">
                <div className="h-1.5 bg-[#0f172a] rounded-full overflow-hidden mb-2">
                  <div className="h-full bg-gradient-to-r from-blue-500 to-purple-500 rounded-full transition-all duration-500" style={{ width: `${Math.max(5, sbProgress)}%` }} />
                </div>
                <div className="flex justify-between text-[15px] text-[#64748b]">
                  <span>{sbStep}</span>
                  <span>{Math.round(sbProgress)}%</span>
                </div>
                {storyboardEpisodeTaskRows.length > 0 && (
                  <div className="mt-3">
                    <div className="mb-2 flex flex-wrap gap-2 text-[11px]">
                      <span className="rounded-full border border-emerald-800/80 bg-emerald-950/30 px-2 py-1 text-emerald-200">成功 {completedStoryboardEpisodes.length}</span>
                      <span className="rounded-full border border-rose-800/80 bg-rose-950/30 px-2 py-1 text-rose-200">失败 {failedStoryboardEpisodes.length}</span>
                      <span className="rounded-full border border-slate-700 bg-slate-950/60 px-2 py-1 text-slate-300">总计 {storyboardEpisodeTaskRows.length}</span>
                    </div>
                    {(resumeableFailedStoryboardEpisodes.length > 0 || retryOnlyFailedStoryboardEpisodes.length > 0 || fallbackStoryboardEpisodes.length > 0) && (
                      <div className="mb-3 rounded-xl border border-slate-700 bg-slate-950/50 p-3">
                        <div className="text-xs font-semibold text-slate-200">推荐下一步</div>
                        <div className="mt-1 text-xs text-slate-400">
                          {resumeableFailedStoryboardEpisodes.length > 0
                            ? `有 ${resumeableFailedStoryboardEpisodes.length} 集已经保留了最近完成场景，适合直接从断点继续。`
                            : retryOnlyFailedStoryboardEpisodes.length > 0
                              ? `有 ${retryOnlyFailedStoryboardEpisodes.length} 集适合直接重试失败集。`
                              : `有 ${fallbackStoryboardEpisodes.length} 集虽然生成完成，但包含保底分镜，建议优先复核。`}
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {resumeableFailedStoryboardEpisodes.length > 0 && (
                            <button
                              disabled={sbRunState === 'running'}
                              onClick={() => void startStoryboard(
                                resumeableFailedStoryboardEpisodes,
                                {
                                  resumeFromScene: Object.fromEntries(
                                    resumeableFailedStoryboardEpisodes
                                      .map((episode: number) => [String(episode), storyboardResumeSceneMap[String(episode)]])
                                      .filter((entry: [string, string | undefined]): entry is [string, string] => Boolean(entry[1])),
                                  ),
                                },
                              )}
                              className="rounded-lg border border-sky-700/70 bg-sky-950/30 px-3 py-1.5 text-xs text-sky-200 transition-colors hover:bg-sky-900/40 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              从断点继续 {resumeableFailedStoryboardEpisodes.length} 集
                            </button>
                          )}
                          {retryOnlyFailedStoryboardEpisodes.length > 0 && (
                            <button
                              disabled={sbRunState === 'running'}
                              onClick={() => void startStoryboard(retryOnlyFailedStoryboardEpisodes)}
                              className="rounded-lg border border-amber-700/70 bg-amber-950/30 px-3 py-1.5 text-xs text-amber-200 transition-colors hover:bg-amber-900/40 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              只重试失败集 {retryOnlyFailedStoryboardEpisodes.length} 集
                            </button>
                          )}
                          {fallbackStoryboardEpisodes.length > 0 && (
                            <button
                              onClick={() => setSelectedSBEps(new Set(fallbackStoryboardEpisodes))}
                              className="rounded-lg border border-emerald-700/70 bg-emerald-950/30 px-3 py-1.5 text-xs text-emerald-200 transition-colors hover:bg-emerald-900/40"
                            >
                              选中需复核集 {fallbackStoryboardEpisodes.length} 集
                            </button>
                          )}
                        </div>
                      </div>
                    )}
                    <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                      {storyboardEpisodeTaskRows.map((item: any) => {
                        const tone =
                          item?.status === 'done'
                            ? 'border-emerald-800/80 bg-emerald-950/20 text-emerald-200'
                            : item?.status === 'error'
                              ? 'border-rose-800/80 bg-rose-950/20 text-rose-200'
                              : item?.status === 'running'
                                ? 'border-sky-800/80 bg-sky-950/20 text-sky-200'
                                : 'border-slate-700 bg-slate-950/40 text-slate-300'
                        const failureMeta = getStoryboardFailureMeta(item?.failure_kind)
                        const hasWarnings = Number(item?.warning_count ?? 0) > 0
                        const nextStep = getStoryboardEpisodeNextStep(item)
                        const episodeResumeAnchor = String(storyboardResumeSceneMap[String(Number(item?.episode ?? 0))] || '').trim()
                        return (
                          <div key={`sb-task-${item?.episode}`} className={`rounded-lg border px-3 py-2 text-xs ${tone}`}>
                            <div className="flex items-center justify-between gap-3">
                              <span className="font-semibold">第 {item?.episode} 集</span>
                              <span>{item?.status === 'done' ? '成功' : item?.status === 'error' ? '失败' : item?.status === 'running' ? '进行中' : '排队中'}</span>
                            </div>
                            {hasWarnings ? (
                              <div className="mt-2">
                                <span className="inline-flex rounded-full border border-amber-700/70 bg-amber-950/30 px-2 py-0.5 text-[11px] text-amber-200">
                                  已降级补全 {Number(item?.fallback_scene_count ?? 0)} 个场景
                                </span>
                              </div>
                            ) : null}
                            {item?.status === 'error' ? (
                              <div className="mt-2">
                                <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] ${failureMeta.tone}`}>
                                  {failureMeta.label}
                                </span>
                              </div>
                            ) : null}
                            <div className="mt-1 text-[11px] opacity-90">
                              {item?.error || item?.current_step || 'queued'}
                            </div>
                            {item?.guidance ? (
                              <div className="mt-1 text-[11px] opacity-75">
                                建议：{item.guidance}
                              </div>
                            ) : null}
                            {nextStep ? (
                              <div className="mt-1 text-[11px] opacity-75">
                                下一步：{nextStep}
                              </div>
                            ) : null}
                            {(typeof item?.completed_scenes === 'number' && item.completed_scenes > 0) || item?.total_scenes ? (
                              <div className="mt-1 text-[11px] opacity-75">
                                场景进度：{Number(item?.completed_scenes ?? 0)}/{Number(item?.total_scenes ?? 0) || '?'}
                              </div>
                            ) : null}
                            {typeof item?.retry_count === 'number' && item.retry_count > 0 ? (
                              <div className="mt-1 text-[11px] opacity-75">
                                自动重试：{item.retry_count} 次{item?.last_retry_reason ? `（${item.last_retry_reason}）` : ''}
                              </div>
                            ) : null}
                            {item?.last_completed_scene_name ? (
                              <div className="mt-1 text-[11px] opacity-75">
                                最近完成：{item.last_completed_scene_name}
                              </div>
                            ) : null}
                            {item?.failed_scene_name && item?.status === 'error' ? (
                              <div className="mt-1 text-[11px] opacity-75">
                                阻塞场景：{item.failed_scene_name}
                              </div>
                            ) : null}
                            {item?.resume_anchor ? (
                              <div className="mt-1 text-[11px] opacity-75">
                                恢复锚点：{item.resume_anchor}
                              </div>
                            ) : null}
                            {typeof item?.shot_count === 'number' && item.shot_count > 0 ? (
                              <div className="mt-1 text-[11px] opacity-70">已写入镜头 {item.shot_count}</div>
                            ) : null}
                            {(item?.status === 'error' || hasWarnings) && (
                              <div className="mt-3 flex flex-wrap gap-2">
                                {item?.status === 'error' && episodeResumeAnchor ? (
                                  <button
                                    disabled={sbRunState === 'running'}
                                    onClick={() => void startStoryboard(
                                      [Number(item.episode)],
                                      { resumeFromScene: { [String(item.episode)]: episodeResumeAnchor } },
                                    )}
                                    className="rounded-lg border border-sky-700/70 bg-sky-950/30 px-3 py-1 text-[11px] text-sky-200 transition-colors hover:bg-sky-900/40 disabled:cursor-not-allowed disabled:opacity-50"
                                  >
                                    从该集断点继续
                                  </button>
                                ) : null}
                                {item?.status === 'error' ? (
                                  <button
                                    disabled={sbRunState === 'running'}
                                    onClick={() => void startStoryboard([Number(item.episode)])}
                                    className="rounded-lg border border-amber-700/70 bg-amber-950/30 px-3 py-1 text-[11px] text-amber-200 transition-colors hover:bg-amber-900/40 disabled:cursor-not-allowed disabled:opacity-50"
                                  >
                                    只重试该集
                                  </button>
                                ) : null}
                                {hasWarnings ? (
                                  <button
                                    onClick={() => setSelectedSBEps(new Set([Number(item.episode)]))}
                                    className="rounded-lg border border-emerald-700/70 bg-emerald-950/30 px-3 py-1 text-[11px] text-emerald-200 transition-colors hover:bg-emerald-900/40"
                                  >
                                    选中该集做复核
                                  </button>
                                ) : null}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
                {sbRunState === 'error' && (
                  <div className="mt-3 p-3 rounded-lg bg-red-900/20 border border-red-800/50 text-[14px] text-red-400 font-mono whitespace-pre-wrap">{sbStep}</div>
                )}
              </div>
            )}

            {/* Storyboard content display */}
            {storyboardData.length > 0 && (
              <div className="bg-[#111827] border border-[#1e293b] rounded-xl p-5">
                <div className="text-xs font-semibold text-[#94a3b8] mb-3">分镜表</div>
                <WorkflowFeedbackBanner
                  status={storyboardBatchState.status}
                  title={getStoryboardBatchModeLabel(storyboardBatchState.mode)}
                  message={storyboardBatchState.status === 'idle' ? '' : storyboardBatchState.message}
                  hint="批量编译、批量首帧、批量视频、视觉绑定同步的结果都会在这里汇总。"
                  className="mb-3"
                />
                <div className="mb-4 grid gap-2 md:grid-cols-8">
                  <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-3">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">选中镜头</div>
                    <div className="mt-1 text-lg text-slate-100">{storyboardReadiness.total}</div>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-3">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">缺提示词</div>
                    <div className="mt-1 text-lg text-amber-300">{storyboardReadiness.missingPrompt}</div>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-3">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">缺首帧</div>
                    <div className="mt-1 text-lg text-amber-300">{storyboardReadiness.missingFrame}</div>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-3">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">缺视频</div>
                    <div className="mt-1 text-lg text-amber-300">{storyboardReadiness.missingVideo}</div>
                  </div>
                  <div className="rounded-lg border border-amber-800/70 bg-amber-950/30 px-3 py-3">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-amber-200">缺锁定参考图</div>
                    <div className="mt-1 text-lg text-amber-200">{storyboardReadiness.missingLockedReference}</div>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-3">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">缺结构/主参考图</div>
                    <div className="mt-1 text-lg text-amber-300">{storyboardReadiness.missingStructure + Math.max(0, storyboardReadiness.missingReference - storyboardReadiness.missingLockedReference)}</div>
                  </div>
                  <div className="rounded-lg border border-amber-800/70 bg-amber-950/20 px-3 py-3">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-amber-200">诊断警告</div>
                    <div className="mt-1 text-lg text-amber-200">{storyboardReadiness.warningShots}</div>
                  </div>
                  <div className="rounded-lg border border-rose-800/70 bg-rose-950/20 px-3 py-3">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-rose-200">诊断阻塞</div>
                    <div className="mt-1 text-lg text-rose-200">{storyboardReadiness.blockedDiagnostics}</div>
                  </div>
                </div>
                {storyboardReadiness.blockedShots.length > 0 && (
                  <details className="mb-4 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                    <summary className="cursor-pointer text-sm text-amber-300">
                      缺失清单 · {storyboardReadiness.blockedShots.length} 个镜头待补齐
                    </summary>
                    <div className="mt-3 space-y-2">
                      {storyboardReadiness.blockedShots.slice(0, 24).map((item) => (
                        <div key={`${item.episode}-${item.shotId}`} className="rounded border border-slate-800 bg-slate-950 px-3 py-2 text-xs text-slate-300">
                          第{item.episode}集 镜头 {item.shotId}：{item.missing.join('、')}
                        </div>
                      ))}
                      {storyboardReadiness.blockedShots.length > 24 && (
                        <div className="text-xs text-slate-500">其余 {storyboardReadiness.blockedShots.length - 24} 个镜头可继续在各集详情中查看。</div>
                      )}
                    </div>
                  </details>
                )}
                <div className="max-h-[500px] overflow-y-auto">
                  {(() => {
                    const epGroups: Record<number, any[]> = {}
                    storyboardData.forEach((s: any) => {
                      if (!epGroups[s.episode]) epGroups[s.episode] = []
                      epGroups[s.episode].push(s)
                    })
                    return Object.entries(epGroups).sort(([a],[b]) => Number(a)-Number(b)).map(([ep, shots]: [string, any[]]) => {
                      const shotReports = shots.map((sh: any) => ({ shot: sh, checklist: getShotChecklist(sh) }))
                      const missingPromptShots = shotReports.filter((item) => !item.checklist.promptReady)
                      const missingFrameShots = shotReports.filter((item) => !item.checklist.frameReady)
                      const missingVideoShots = shotReports.filter((item) => !item.checklist.videoReady)
                      const missingLockedReferenceShots = shotReports.filter((item) => !item.checklist.lockedReferenceReady)
                      const diagnosticWarningShots = shotReports.filter((item) => item.checklist.diagnosticWarning)
                      const diagnosticBlockedShots = shotReports.filter((item) => item.checklist.diagnosticBlocked)
                      const incompleteShots = shotReports.filter((item) => item.checklist.missing.length > 0)
                      const selectedShot = shots.find((sh: any) => `${sh.episode}-${sh.shot_id}` === activeShotKey) ?? shots[0] ?? null
                      const selectedShotIndex = selectedShot
                        ? shots.findIndex((sh: any) => `${sh.episode}-${sh.shot_id}` === `${selectedShot.episode}-${selectedShot.shot_id}`)
                        : -1
                      const previousShot = selectedShotIndex > 0 ? shots[selectedShotIndex - 1] : null
                      const nextShot = selectedShotIndex >= 0 && selectedShotIndex < shots.length - 1 ? shots[selectedShotIndex + 1] : null
                      return (
                      <details key={ep} className="mb-3">
                        <summary className="text-[14px] font-semibold text-[#e2e8f0] cursor-pointer px-3 py-2 rounded-lg bg-[#1e293b] hover:bg-[#334155] transition-colors">
                          第{ep}集 · {shots.length} 个镜头
                        </summary>
                        <div className="mb-3 mt-2 grid gap-2 md:grid-cols-7">
                          <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs text-slate-300">缺提示词：{missingPromptShots.length}</div>
                          <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs text-slate-300">缺首帧：{missingFrameShots.length}</div>
                          <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs text-slate-300">缺视频：{missingVideoShots.length}</div>
                          <div className="rounded-lg border border-amber-800/70 bg-amber-950/30 px-3 py-2 text-xs text-amber-200">缺锁定参考图：{missingLockedReferenceShots.length}</div>
                          <div className="rounded-lg border border-amber-800/70 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">诊断警告：{diagnosticWarningShots.length}</div>
                          <div className="rounded-lg border border-rose-800/70 bg-rose-950/20 px-3 py-2 text-xs text-rose-200">诊断阻塞：{diagnosticBlockedShots.length}</div>
                          <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs text-amber-300">待补信息：{incompleteShots.length}</div>
                        </div>
                        <div className="flex flex-wrap justify-end gap-2 mb-2">
                          <button
                            onClick={() => {
                              const all = shots.map((sh: any) =>
                                `[${sh.shot_id}] ${sh.visual_prompt_static || ''}\n---\n${sh.visual_prompt_motion || ''}`
                              ).join('\n\n')
                              navigator.clipboard.writeText(all)
                            }}
                            className="text-xs px-3 py-1.5 rounded-lg bg-purple-900/30 border border-purple-600 text-purple-400 hover:bg-purple-900/50 transition-colors"
                          >
                            复制本集提示词
                          </button>
                          <button
                            onClick={() => batchCompileShots(shots, 'batch-manual')}
                            disabled={storyboardBatchState.status === 'running'}
                            className="text-xs px-3 py-1.5 rounded-lg bg-sky-900/30 border border-sky-600 text-sky-300 hover:bg-sky-900/50 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            批量编译本集
                          </button>
                          <button
                            onClick={() => batchGenerateFrames(shots)}
                            disabled={storyboardBatchState.status === 'running'}
                            className="text-xs px-3 py-1.5 rounded-lg bg-emerald-900/30 border border-emerald-600 text-emerald-300 hover:bg-emerald-900/50 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            批量补首帧
                          </button>
                          <button
                            onClick={() => batchGenerateVideos(shots)}
                            disabled={storyboardBatchState.status === 'running'}
                            className="text-xs px-3 py-1.5 rounded-lg bg-fuchsia-900/30 border border-fuchsia-600 text-fuchsia-300 hover:bg-fuchsia-900/50 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            批量补视频
                          </button>
                        </div>
                        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
                          <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950/40">
                            <table className="w-full text-[14px] border-collapse">
                              <thead>
                                <tr className="text-[#64748b] border-b border-[#1e293b]">
                                  <th className="text-left py-2 pr-1.5 w-12">镜号</th>
                                  <th className="text-left py-2 pr-1.5 w-10">s</th>
                                  <th className="text-left py-2 pr-1.5 w-12">景别</th>
                                  <th className="text-left py-2 pr-1.5">画面描述</th>
                                  <th className="text-left py-2 pr-1.5">对白</th>
                                  <th className="text-left py-2 pr-1.5">光影/氛围</th>
                                  <th className="text-left py-2 pr-1.5">音效</th>
                                  <th className="text-left py-2 pr-1.5">运镜</th>
                                  <th className="text-left py-2 pr-1.5">提示词</th>
                                  <th className="text-left py-2 pr-1.5">诊断</th>
                                  <th className="text-left py-2 pr-1.5">首帧</th>
                                  <th className="text-left py-2 pr-1.5">视频</th>
                                  <th className="text-left py-2">缺失信息</th>
                                </tr>
                              </thead>
                              <tbody>
                                {shots.map((sh: any) => {
                                  const checklist = getShotChecklist(sh)
                                  const diagnosticMeta = getCompilerDiagnosticMeta(checklist.diagnosticStatus)
                                  const shotKey = `${sh.episode}-${sh.shot_id}`
                                  const isActive = shotKey === activeShotKey
                                  return (
                                  <tr
                                    key={sh.shot_id}
                                    onClick={() => setActiveShotKey(shotKey)}
                                    className={`border-b border-[#1e293b] cursor-pointer transition-colors ${
                                      isActive ? 'bg-sky-950/40' : 'hover:bg-[#0f172a]'
                                    }`}
                                  >
                                    <td className="py-2 pr-1.5 text-blue-400 font-mono">{sh.shot_id}</td>
                                    <td className="py-2 pr-1.5 text-[#94a3b8]">{sh.duration || 3}</td>
                                    <td className="py-2 pr-1.5 text-[#94a3b8]">{sh.camera_angle || 'MS'}</td>
                                    <td className="py-2 pr-1.5 text-[#cbd5e1] text-[13px] max-w-[280px]">
                                      <div className="line-clamp-2">{sh.visual_prompt_static?.slice(0, 120) || sh.start_state || sh.action_process || ''}</div>
                                    </td>
                                    <td className="py-2 pr-1.5 text-[#cbd5e1] text-[13px] truncate max-w-[150px]">{sh.dialogue || ''}</td>
                                    <td className="py-2 pr-1.5 text-[#94a3b8] text-[13px]">{sh.lighting?.slice(0, 30) || ''}</td>
                                    <td className="py-2 pr-1.5 text-[#94a3b8] text-[13px] truncate max-w-[80px]">{Array.isArray(sh.sound_effects) ? sh.sound_effects.join(', ') : sh.sound_effects || ''}</td>
                                    <td className="py-2 pr-1.5 text-[#94a3b8] text-[13px]">{sh.camera_movement || 'static'}</td>
                                    <td className={`py-2 pr-1.5 text-[12px] ${sh.prompt_locked ? 'text-amber-300' : checklist.promptReady ? 'text-emerald-300' : 'text-amber-300'}`}>{sh.prompt_locked ? '已锁定' : checklist.promptReady ? '已编译' : '待补'}</td>
                                    <td className={`py-2 pr-1.5 text-[12px] ${checklist.promptReady ? diagnosticMeta.textTone : 'text-slate-500'}`}>
                                      {checklist.promptReady ? diagnosticMeta.label : '待诊断'}
                                    </td>
                                    <td className={`py-2 pr-1.5 text-[12px] ${checklist.frameReady ? 'text-emerald-300' : 'text-amber-300'}`}>{checklist.frameReady ? '已就绪' : '待生成'}</td>
                                    <td className={`py-2 pr-1.5 text-[12px] ${checklist.videoReady ? 'text-emerald-300' : 'text-amber-300'}`}>{checklist.videoReady ? '已就绪' : '待生成'}</td>
                                    <td className="py-2 text-[12px] text-slate-400 max-w-[280px]">{checklist.missing.length > 0 ? checklist.missing.join('、') : '已补齐'}</td>
                                  </tr>
                                )})}
                              </tbody>
                            </table>
                          </div>
                          <ShotDetailWorkbench
                            shot={selectedShot}
                            previousShot={previousShot}
                            nextShot={nextShot}
                            getChecklist={getShotChecklist}
                            onSelectShot={(shot) => setActiveShotKey(`${shot.episode}-${shot.shot_id}`)}
                            onSaveStructure={patchStoryboardStructure}
                            onCompilePrompt={async (shot, compileReason) => {
                              await compileStoryboardPrompts(shot.episode, shot.shot_id, compileReason)
                              await fetchOutputs()
                            }}
                            onLoadHistory={(shot) => loadPromptVersions(shot.episode, shot.shot_id)}
                            onGenerateFrame={(shot) => generateStoryboardFrame(shot.episode, shot.shot_id)}
                            onGenerateVideo={(shot) => generateStoryboardVideo(shot.episode, shot.shot_id)}
                            onRecoverFrameTask={(taskId) => recoverStoryboardGeneration(taskId, 'frame')}
                            onRecoverVideoTask={(taskId) => recoverStoryboardGeneration(taskId, 'video')}
                            initialRecoverFrameTaskId={pendingStoryboardTaskMap[getStoryboardPendingTaskKey(selectedShot?.episode ?? 0, selectedShot?.shot_id ?? '', 'frame')] ?? null}
                            initialRecoverVideoTaskId={pendingStoryboardTaskMap[getStoryboardPendingTaskKey(selectedShot?.episode ?? 0, selectedShot?.shot_id ?? '', 'video')] ?? null}
                            frameRecoveryMeta={(() => {
                              const taskId = pendingStoryboardTaskMap[getStoryboardPendingTaskKey(selectedShot?.episode ?? 0, selectedShot?.shot_id ?? '', 'frame')]
                              return taskId ? (storyboardRecoveryMeta[taskId] ?? null) : null
                            })()}
                            videoRecoveryMeta={(() => {
                              const taskId = pendingStoryboardTaskMap[getStoryboardPendingTaskKey(selectedShot?.episode ?? 0, selectedShot?.shot_id ?? '', 'video')]
                              return taskId ? (storyboardRecoveryMeta[taskId] ?? null) : null
                            })()}
                            isAutoRecoveringFrame={autoRecoveringStoryboardTaskIds.includes(pendingStoryboardTaskMap[getStoryboardPendingTaskKey(selectedShot?.episode ?? 0, selectedShot?.shot_id ?? '', 'frame')] ?? '')}
                            isAutoRecoveringVideo={autoRecoveringStoryboardTaskIds.includes(pendingStoryboardTaskMap[getStoryboardPendingTaskKey(selectedShot?.episode ?? 0, selectedShot?.shot_id ?? '', 'video')] ?? '')}
                            onToggleLock={(shot, locked) => setPromptLock(shot.episode, shot.shot_id, locked)}
                            onSaveAcceptance={async (shot, payload) => {
                              await saveAcceptanceRecord(shot.episode, shot.shot_id, payload)
                            }}
                            onRecompileAfterFeedback={async (shot) => {
                              await compileStoryboardPrompts(shot.episode, shot.shot_id, 'after-feedback')
                              await fetchOutputs()
                            }}
                          />
                        </div>
                      </details>
                    )})
                  })()}
                </div>
              </div>
            )}
          </div>
        )}

        {activeModule === 'visual' && (
          <div className="p-6">
            <div className="mb-4 flex flex-wrap gap-2">
              <button
                disabled={vsRunState === 'running' || (storyboardData.length === 0 && scripts.length === 0)}
                onClick={startVisualSetup}
                className={`text-xs px-4 py-2 rounded-lg transition-colors ${
                  vsRunState === 'running' || (storyboardData.length === 0 && scripts.length === 0)
                    ? 'bg-slate-800 text-slate-500 border border-slate-700 cursor-not-allowed'
                    : 'bg-purple-900/30 border border-purple-600 text-purple-300 hover:bg-purple-900/50'
                }`}
              >
                {vsRunState === 'running' ? '视觉设定生成中...' : visualReady ? '重新生成视觉设定' : '生成视觉设定'}
              </button>
              <button
                onClick={() => setActiveModule('storyboard')}
                className="text-xs px-4 py-2 rounded-lg border border-slate-700 text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
              >
                返回分镜生产
              </button>
            </div>
            <div className="mb-4 rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3 text-sm text-slate-300">
              <div className="font-medium text-slate-100">视觉资产</div>
              <div className="mt-1 text-slate-400">统一生成时代、场景、道具和定妆设定，作为分镜生产里的视觉参考基础。</div>
            </div>
            <div className="flex items-center gap-3 mb-4">
              <h1 className="text-lg font-bold text-[#f1f5f9]">🎨 视觉资产</h1>
              <span className={`text-[15px] px-2 py-0.5 rounded-full ${
                visualReady
                  ? 'bg-green-900/40 text-green-400'
                  : 'bg-slate-800 text-slate-500'
              }`}>
                {visualReady ? '已生成' : '未生成'}
              </span>
            </div>

            <div className="mb-4 grid gap-3 md:grid-cols-5">
              {[
                { label: '场景资产', value: visualAssetSummary.sceneCount },
                { label: '道具资产', value: visualAssetSummary.propCount },
                { label: '角色定妆', value: visualAssetSummary.characterCount },
                { label: '已选参考图', value: visualAssetSummary.selectedReferenceCount },
                { label: '锁定参考图', value: visualAssetSummary.lockedReferenceCount },
              ].map((item) => (
                <div key={item.label} className="rounded-xl border border-slate-800 bg-slate-950/60 px-4 py-3">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{item.label}</div>
                  <div className="mt-1 text-lg text-slate-100">{item.value}</div>
                </div>
              ))}
            </div>

            <div className="mb-4 rounded-xl border border-slate-800 bg-slate-900/40 p-4">
              <div className="text-xs font-semibold text-slate-300">批量参考图生成</div>
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  disabled={visualBatchState.status === 'running'}
                  onClick={() => runVisualAssetBatch('scene')}
                  className="rounded-lg border border-blue-700/60 px-3 py-2 text-xs text-blue-200 transition hover:border-blue-500 hover:text-white disabled:cursor-not-allowed disabled:border-slate-700 disabled:text-slate-500"
                >
                  批量生成全部场景
                </button>
                <button
                  disabled={visualBatchState.status === 'running'}
                  onClick={() => runVisualAssetBatch('prop')}
                  className="rounded-lg border border-fuchsia-700/60 px-3 py-2 text-xs text-fuchsia-200 transition hover:border-fuchsia-500 hover:text-white disabled:cursor-not-allowed disabled:border-slate-700 disabled:text-slate-500"
                >
                  批量生成全部道具
                </button>
                <button
                  disabled={visualBatchState.status === 'running'}
                  onClick={() => runVisualAssetBatch('character')}
                  className="rounded-lg border border-emerald-700/60 px-3 py-2 text-xs text-emerald-200 transition hover:border-emerald-500 hover:text-white disabled:cursor-not-allowed disabled:border-slate-700 disabled:text-slate-500"
                >
                  批量生成全部角色
                </button>
                <button
                  disabled={visualBatchState.status === 'running'}
                  onClick={() => runVisualAssetBatch('missing')}
                  className="rounded-lg border border-amber-700/60 px-3 py-2 text-xs text-amber-200 transition hover:border-amber-500 hover:text-white disabled:cursor-not-allowed disabled:border-slate-700 disabled:text-slate-500"
                >
                  只补缺图
                </button>
              </div>
              <WorkflowFeedbackBanner
                status={visualBatchState.status}
                title={getVisualBatchScopeLabel(visualBatchState.scope)}
                message={visualBatchState.status === 'idle' ? '' : visualBatchState.message}
                hint="支持一次补齐全场景、全道具、全角色；locked 资产会自动跳过。"
                className="mt-3"
              />
              {visualBatchState.entries.length > 0 ? (
                <div className="mt-3 max-h-48 space-y-2 overflow-y-auto rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                  {visualBatchState.entries.map((entry) => (
                    <div key={entry.key}>
                      <div className="flex items-center justify-between gap-3 text-xs">
                        <span className="text-slate-300">{entry.name}</span>
                        <span className={`rounded-full px-2 py-0.5 ${
                          entry.status === 'done'
                            ? 'bg-emerald-950/40 text-emerald-300'
                            : entry.status === 'error'
                              ? 'bg-red-950/40 text-red-300'
                              : entry.status === 'recovering'
                                ? 'bg-amber-950/40 text-amber-300'
                                : entry.status === 'running'
                                  ? 'bg-blue-950/40 text-blue-300'
                                  : entry.status === 'skipped'
                                    ? 'bg-amber-950/40 text-amber-300'
                                    : 'bg-slate-900 text-slate-400'
                        }`}>
                          {entry.status}
                        </span>
                      </div>
                      {entry.message ? (
                        <div className={`mt-1 text-[11px] ${
                          entry.status === 'done'
                            ? 'text-emerald-300'
                            : entry.status === 'error'
                              ? 'text-red-300'
                              : entry.status === 'recovering'
                                ? 'text-amber-300'
                                : entry.status === 'skipped'
                                  ? 'text-slate-500'
                                  : 'text-slate-400'
                        }`}>
                          {entry.message}
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>

            <div className="mb-4 rounded-xl border border-slate-800 bg-slate-900/40 p-4">
              <div className="text-xs font-semibold text-slate-300">视觉资产完成度</div>
              <div className="mt-3 grid gap-3 md:grid-cols-4">
                {[
                  { label: 'draft', value: visualAssetSummary.draftAssetCount, tone: 'text-slate-300' },
                  { label: 'ref_ready', value: visualAssetSummary.refReadyAssetCount, tone: 'text-sky-300' },
                  { label: 'locked', value: visualAssetSummary.lockedAssetCount, tone: 'text-emerald-300' },
                  { label: 'rejected', value: visualAssetSummary.rejectedAssetCount, tone: 'text-amber-300' },
                ].map((item) => (
                  <div key={item.label} className="rounded-lg border border-slate-800 bg-slate-950/60 px-4 py-3">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{item.label}</div>
                    <div className={`mt-1 text-lg ${item.tone}`}>{item.value}</div>
                  </div>
                ))}
              </div>
              <div className="mt-3 text-xs text-slate-400">
                自动推导规则：无图为 `draft`，有 `selected` 为 `ref_ready`，有 `locked` 为 `locked`，全部都是 `rejected` 为 `rejected`。
              </div>
            </div>

            <div className="bg-[#111827] border border-[#1e293b] rounded-xl p-5 mb-4">
              <div className="text-xs text-[#64748b] mb-3">🎨 视觉设定生成</div>
              <div className="text-[14px] text-[#94a3b8] mb-3">
                基于世界观 Bible 和人物画像，生成时代规范、场景设定、道具清单、角色定妆精调。
              </div>
              <div className="flex items-center gap-2">
                {storyboardData.length === 0 && scripts.length === 0 ? (
                  <span className="text-xs text-[#475569] italic">需要先完成剧本生产和分镜生产才能生成视觉设定</span>
                ) : (
                  <>
                    <button
                      disabled={vsRunState === 'running'}
                      onClick={startVisualSetup}
                      className={`text-xs px-4 py-2 rounded-lg transition-colors ${
                        vsRunState === 'running'
                          ? 'bg-amber-900/40 text-amber-400 border border-amber-800/50 cursor-not-allowed'
                          : 'bg-purple-900/30 border border-purple-600 text-purple-400 hover:bg-purple-900/50'
                      }`}
                    >
                      {vsRunState === 'running' ? '⏳ 生成中...' : visualReady ? '🔄 重新生成视觉设定' : '▶️ 生成视觉设定'}
                    </button>
                    {visualReady && (
                      <details className="relative">
                        <summary className="cursor-pointer list-none rounded-lg border border-slate-700 px-4 py-2 text-xs text-slate-400 transition-colors hover:border-slate-500 hover:text-slate-200">
                          更多操作
                        </summary>
                        <div className="mt-2 rounded-lg border border-red-900/50 bg-slate-950 p-2">
                          <button
                            onClick={async () => {
                              if (!confirm('确定删除所有视觉设定数据？')) return
                              setVisualData(null)
                              setTimeout(async () => {
                                await fetch(`/api/pipeline/visual-setup/book/${book.id}`, { method: 'DELETE' })
                                onRefresh()
                                fetchOutputs()
                              }, 50)
                            }}
                            className="text-xs px-4 py-2 rounded-lg bg-red-900/30 border border-red-600/50 text-red-400 hover:bg-red-900/50 transition-colors"
                          >
                            🗑️ 删除视觉设定
                          </button>
                        </div>
                      </details>
                    )}
                  </>
                )}
              </div>
            </div>

            {(vsRunState === 'running' || vsRunState === 'error') && (
              <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-4 mb-4">
                <div className="h-1.5 bg-[#0f172a] rounded-full overflow-hidden mb-2">
                  <div className="h-full bg-gradient-to-r from-purple-500 to-pink-500 rounded-full transition-all duration-500" style={{ width: `${Math.max(5, vsProgress)}%` }} />
                </div>
                <div className="flex justify-between text-[15px] text-[#64748b]">
                  <span>{vsStep}</span>
                  <span>{Math.round(vsProgress)}%</span>
                </div>
                {vsRunState === 'error' && (
                  <div className="mt-3 p-3 rounded-lg bg-red-900/20 border border-red-800/50 text-[14px] text-red-400 font-mono whitespace-pre-wrap">{vsStep}</div>
                )}
              </div>
            )}

            {/* Visual content display */}
            {visualReady && (
              <div className="space-y-4">
                {/* Era spec */}
                <details className="bg-[#111827] border border-[#1e293b] rounded-xl" open>
                  <summary className="text-[14px] font-semibold text-[#e2e8f0] cursor-pointer px-5 py-3 rounded-xl hover:bg-[#1e293b] transition-colors">
                    📜 时代规范
                  </summary>
                  <div className="px-5 pb-4 space-y-2 text-[14px] text-[#94a3b8]">
                    <div><span className="text-[#64748b]">时间线：</span>{visualAssetData.era.timeline_start} → {visualAssetData.era.timeline_end}</div>
                    <div><span className="text-[#64748b]">服饰：</span>{visualAssetData.era.clothing_spec}</div>
                    <div><span className="text-[#64748b]">色调：</span>{visualAssetData.era.color_palette}</div>
                    <div><span className="text-[#64748b]">建筑：</span>{visualAssetData.era.architecture_spec}</div>
                    <div><span className="text-[#64748b]">色彩曲线：</span>{visualAssetData.era.color_curve}</div>
                  </div>
                </details>

                {/* Locations */}
                <details className="bg-[#111827] border border-[#1e293b] rounded-xl" open>
                  <summary className="text-[14px] font-semibold text-[#e2e8f0] cursor-pointer px-5 py-3 rounded-xl hover:bg-[#1e293b] transition-colors">
                    🏠 场景（{visualAssetData.locations?.length || 0}）
                  </summary>
                  <div className="px-5 pb-4 space-y-2">
                    {(visualAssetData.locations || []).map((loc: any, i: number) => (
                      <details key={i} className="bg-[#0c1222] border border-[#1e293b] rounded p-3" open={i === 0}>
                        <summary className="text-[14px] font-medium text-[#cbd5e1] cursor-pointer">{loc.name} · {loc.category}</summary>
                        <VisualAssetEditorCard
                          asset={loc}
                          assetType="scene"
                          assetName={loc.name}
                          storyboardShots={storyboardData}
                          onSaveAsset={patchVisualAsset}
                          onCreateReference={createVisualReferenceAsset}
                          onPatchReference={patchVisualReferenceAsset}
                          onDeleteReference={deleteVisualReferenceAsset}
                          onGenerateReference={generateVisualReferenceAsset}
                          onRecoverReference={recoverVisualReferenceGeneration}
                          initialRecoverTaskId={pendingVisualReferenceTaskMap[getVisualAssetPendingTaskKey('scene', loc.id)] ?? null}
                          isAutoRecovering={autoRecoveringVisualReferenceTaskIds.includes(pendingVisualReferenceTaskMap[getVisualAssetPendingTaskKey('scene', loc.id)] ?? '')}
                          recoveryMeta={(() => {
                            const taskId = pendingVisualReferenceTaskMap[getVisualAssetPendingTaskKey('scene', loc.id)]
                            return taskId ? (visualReferenceRecoveryMeta[taskId] ?? null) : null
                          })()}
                        >
                          <div><span className="text-[#64748b]">风格：</span>{loc.style}</div>
                          <div><span className="text-[#64748b]">描述：</span>{loc.description}</div>
                          <div><span className="text-[#64748b]">色调：</span>{loc.color_palette}</div>
                          <div><span className="text-[#64748b]">光影：</span>{loc.lighting_mood}</div>
                          {loc.visual_prompt_zh && (
                            <details className="mt-1">
                              <summary className="text-[13px] text-blue-400 cursor-pointer">✨ 提示词</summary>
                              <div className="text-[14px] text-[#cbd5e1] bg-[#0a0e1a] rounded p-2 mt-1 font-mono whitespace-pre-wrap">{loc.visual_prompt_zh}</div>
                            </details>
                          )}
                        </VisualAssetEditorCard>
                      </details>
                    ))}
                  </div>
                </details>

                {/* Props */}
                <details className="bg-[#111827] border border-[#1e293b] rounded-xl">
                  <summary className="text-[14px] font-semibold text-[#e2e8f0] cursor-pointer px-5 py-3 rounded-xl hover:bg-[#1e293b] transition-colors">
                    🎭 道具（{visualAssetData.props?.length || 0}）
                  </summary>
                  <div className="px-5 pb-4 space-y-2">
                    {(visualAssetData.props || []).map((p: any, i: number) => (
                      <details key={i} className="bg-[#0c1222] border border-[#1e293b] rounded p-3" open={i === 0}>
                        <summary className="text-[14px] font-medium text-[#cbd5e1] cursor-pointer">{p.name} · {p.category}</summary>
                        <VisualAssetEditorCard
                          asset={p}
                          assetType="prop"
                          assetName={p.name}
                          storyboardShots={storyboardData}
                          onSaveAsset={patchVisualAsset}
                          onCreateReference={createVisualReferenceAsset}
                          onPatchReference={patchVisualReferenceAsset}
                          onDeleteReference={deleteVisualReferenceAsset}
                          onGenerateReference={generateVisualReferenceAsset}
                          onRecoverReference={recoverVisualReferenceGeneration}
                          initialRecoverTaskId={pendingVisualReferenceTaskMap[getVisualAssetPendingTaskKey('prop', p.id)] ?? null}
                          isAutoRecovering={autoRecoveringVisualReferenceTaskIds.includes(pendingVisualReferenceTaskMap[getVisualAssetPendingTaskKey('prop', p.id)] ?? '')}
                          recoveryMeta={(() => {
                            const taskId = pendingVisualReferenceTaskMap[getVisualAssetPendingTaskKey('prop', p.id)]
                            return taskId ? (visualReferenceRecoveryMeta[taskId] ?? null) : null
                          })()}
                        >
                          <div><span className="text-[#64748b]">描述：</span>{p.description}</div>
                          {p.visual_prompt_zh && (
                            <details className="mt-1">
                              <summary className="text-[13px] text-blue-400 cursor-pointer">✨ 提示词</summary>
                              <div className="text-[14px] text-[#cbd5e1] bg-[#0a0e1a] rounded p-2 mt-1 font-mono whitespace-pre-wrap">{p.visual_prompt_zh}</div>
                            </details>
                          )}
                        </VisualAssetEditorCard>
                      </details>
                    ))}
                  </div>
                </details>

                {/* Makeups grouped by episode */}
                <details className="bg-[#111827] border border-[#1e293b] rounded-xl">
                  <summary className="text-[14px] font-semibold text-[#e2e8f0] cursor-pointer px-5 py-3 rounded-xl hover:bg-[#1e293b] transition-colors">
                    💄 定妆（{visualAssetData.makeups?.length || 0}）
                  </summary>
                  <div className="px-5 pb-4 space-y-2">
                    {(() => {
                      const makeupByEp = groupMakeupsByEpisodeAndCharacter(visualAssetData.makeups || [])
                      return Object.entries(makeupByEp).sort(([a], [b]) => Number(a) - Number(b)).map(([ep, charGroups], groupIndex) => (
                        <details key={ep} className="bg-[#0c1222] border border-[#1e293b] rounded p-3" open={groupIndex === 0}>
                          <summary className="text-[14px] font-medium text-[#cbd5e1] cursor-pointer">第 {ep} 集 · {Object.keys(charGroups).length} 个角色</summary>
                          <div className="mt-2 space-y-3">
                            {Object.entries(charGroups as Record<string, any[]>).map(([characterName, versions]) => (
                              <div key={`${ep}-${characterName}`} className="rounded-lg border border-slate-800 bg-[#0a0e1a] p-3">
                                <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
                                  <div className="font-medium text-[#cbd5e1]">{characterName}</div>
                                  <div className="text-[12px] text-slate-400">{versions.length} 个版本</div>
                                </div>
                                <div className="space-y-2">
                                  {versions.map((m: any, i: number) => (
                                    <VisualAssetEditorCard
                                      key={i}
                                      asset={m}
                                      assetType="character"
                                      assetName={m.character_name}
                                      storyboardShots={storyboardData}
                                      onSaveAsset={patchVisualAsset}
                                      onCreateReference={createVisualReferenceAsset}
                                      onPatchReference={patchVisualReferenceAsset}
                                      onDeleteReference={deleteVisualReferenceAsset}
                                      onGenerateReference={generateVisualReferenceAsset}
                                      onRecoverReference={recoverVisualReferenceGeneration}
                                      initialRecoverTaskId={pendingVisualReferenceTaskMap[getVisualAssetPendingTaskKey('character', m.id)] ?? null}
                                      isAutoRecovering={autoRecoveringVisualReferenceTaskIds.includes(pendingVisualReferenceTaskMap[getVisualAssetPendingTaskKey('character', m.id)] ?? '')}
                                      recoveryMeta={(() => {
                                        const taskId = pendingVisualReferenceTaskMap[getVisualAssetPendingTaskKey('character', m.id)]
                                        return taskId ? (visualReferenceRecoveryMeta[taskId] ?? null) : null
                                      })()}
                                      className="rounded border border-slate-800 bg-[#020617] p-3 text-[14px] text-[#94a3b8]"
                                    >
                                      <div className="flex flex-wrap items-center gap-2">
                                        <span className={`rounded-full border px-2 py-0.5 text-[11px] ${getMakeupScopeTone(m.makeup_scope)}`}>{formatProductionMakeupScopeLabel(m.scope_label, m.makeup_scope)}</span>
                                        {formatProductionMakeupStageLabel(m.stage_name, m.makeup_scope) ? <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">{formatProductionMakeupStageLabel(m.stage_name, m.makeup_scope)}</span> : null}
                                        {Array.isArray(m.shot_ids) && m.shot_ids.length > 0 ? (
                                          <div className="flex flex-wrap gap-1">
                                            {m.shot_ids.map((sid: string | number) => (
                                              <span key={sid} className="rounded border border-blue-800/50 bg-blue-900/40 px-1.5 py-0.5 text-[11px] text-blue-300">镜头 {sid}</span>
                                            ))}
                                          </div>
                                        ) : null}
                                      </div>
                                      <div className="mt-2"><span className="text-[#64748b]">服装:</span>{m.refined_outfit || '-'}</div>
                                      <div><span className="text-[#64748b]">配饰:</span>{m.refined_accessories || '-'}</div>
                                      <div><span className="text-[#64748b]">妆容:</span>{m.makeup_spec || '-'}</div>
                                      <div><span className="text-[#64748b]">发型:</span>{m.hair_style || '-'}</div>
                                      {m.core_prompt_zh ? <div><span className="text-[#64748b]">基础特征:</span>{m.core_prompt_zh}</div> : null}
                                      {m.consistency_notes ? <div><span className="text-[#64748b]">一致性约束:</span>{m.consistency_notes}</div> : null}
                                      {m.visual_prompt_zh ? (
                                        <details className="mt-1">
                                          <summary className="text-[13px] text-blue-400 cursor-pointer">查看固定模板定妆提示词</summary>
                                          <div className="text-[14px] text-[#cbd5e1] bg-[#0a0e1a] rounded p-2 mt-1 font-mono whitespace-pre-wrap">{m.visual_prompt_zh}</div>
                                        </details>
                                      ) : null}
                                    </VisualAssetEditorCard>
                                  ))}
                                </div>
                              </div>
                            ))}
                          </div>
                        </details>
                      ))
                    })()}
                    {false && (() => {
                      const makeupByEp: Record<number, any[]> = {}
                      ;(visualAssetData.makeups || []).forEach((m: any) => {
                        if (!makeupByEp[m.episode]) makeupByEp[m.episode] = []
                        makeupByEp[m.episode].push(m)
                      })
                      return Object.entries(makeupByEp).sort(([a],[b]) => Number(a)-Number(b)).map(([ep, items], groupIndex) => (
                        <details key={ep} className="bg-[#0c1222] border border-[#1e293b] rounded p-3" open={groupIndex === 0}>
                          <summary className="text-[14px] font-medium text-[#cbd5e1] cursor-pointer">第{ep}集 · {items.length} 个角色</summary>
                          <div className="mt-2 space-y-2">
                            {items.map((m: any, i: number) => (
                              <VisualAssetEditorCard
                                key={i}
                                asset={m}
                                assetType="character"
                                assetName={m.character_name}
                                storyboardShots={storyboardData}
                                onSaveAsset={patchVisualAsset}
                                onCreateReference={createVisualReferenceAsset}
                                onPatchReference={patchVisualReferenceAsset}
                                onDeleteReference={deleteVisualReferenceAsset}
                                onGenerateReference={generateVisualReferenceAsset}
                                onRecoverReference={recoverVisualReferenceGeneration}
                                initialRecoverTaskId={pendingVisualReferenceTaskMap[getVisualAssetPendingTaskKey('character', m.id)] ?? null}
                                isAutoRecovering={autoRecoveringVisualReferenceTaskIds.includes(pendingVisualReferenceTaskMap[getVisualAssetPendingTaskKey('character', m.id)] ?? '')}
                                recoveryMeta={(() => {
                                  const taskId = pendingVisualReferenceTaskMap[getVisualAssetPendingTaskKey('character', m.id)]
                                  return taskId ? (visualReferenceRecoveryMeta[taskId] ?? null) : null
                                })()}
                                className="bg-[#0a0e1a] rounded p-2 text-[14px] text-[#94a3b8]"
                              >
                                <div className="font-medium text-[#cbd5e1]">{m.character_name}</div>
                                <div><span className="text-[#64748b]">穿着：</span>{m.refined_outfit}</div>
                                <div><span className="text-[#64748b]">配饰：</span>{m.refined_accessories}</div>
                                <div><span className="text-[#64748b]">妆容：</span>{m.makeup_spec}</div>
                                <div><span className="text-[#64748b]">发型：</span>{m.hair_style}</div>
                                {m.visual_prompt_zh && (
                                  <details className="mt-1">
                                    <summary className="text-[13px] text-blue-400 cursor-pointer">✨ 提示词</summary>
                                    <div className="text-[14px] text-[#cbd5e1] bg-[#0a0e1a] rounded p-2 mt-1 font-mono whitespace-pre-wrap">{m.visual_prompt_zh}</div>
                                  </details>
                                )}
                              </VisualAssetEditorCard>
                            ))}
                          </div>
                        </details>
                      ))
                    })()}
                  </div>
                </details>
              </div>
            )}
          </div>
        )}

        {activeModule === 'export' && (
          <div className="p-6">
            <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
              <div className="text-xs font-semibold text-slate-300">交付动作</div>
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  onClick={handleRegisterDelivery}
                  className="rounded-lg border border-emerald-600/60 px-4 py-2 text-xs text-emerald-200 transition hover:border-emerald-400 hover:text-white"
                >
                  登记交付
                </button>
                <button
                  onClick={handleExportJson}
                  className="rounded-lg border border-sky-600/60 px-4 py-2 text-xs text-sky-200 transition hover:border-sky-400 hover:text-white"
                >
                  导出 JSON 并登记
                </button>
                <button
                  onClick={() => navigator.clipboard.writeText(exportSummaryText())}
                  className="rounded-lg border border-slate-700 px-4 py-2 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
                >
                  复制交付摘要
                </button>
              </div>
              <WorkflowFeedbackBanner
                status={exportActionState.status}
                title="导出与交付反馈"
                message={exportActionState.status === 'idle' ? '' : exportActionState.message}
                hint="导出 JSON / Word / Final Draft / PDF 以及登记交付记录的结果会显示在这里。"
                className="mt-3"
              />
            </div>
            <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900/50 p-4">
              <div className="text-xs font-semibold text-slate-300">交付历史</div>
              {exportRecords.length === 0 ? (
                <div className="mt-2 text-sm text-slate-400">还没有已保存的交付记录，可以先登记一次交付或导出 JSON。</div>
              ) : (
                <div className="mt-3 space-y-3">
                  {exportRecords.slice(0, 10).map((record) => (
                    <div key={record.id} className="rounded-lg border border-slate-800 bg-slate-950/60 px-4 py-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-slate-100">{String(record.export_format || '').toUpperCase()}</span>
                        <span className={`rounded-full px-2 py-0.5 text-[11px] ${
                          record.status === 'completed'
                            ? 'bg-emerald-900/40 text-emerald-300'
                            : 'bg-amber-900/40 text-amber-300'
                        }`}>
                          {record.status === 'completed' ? '已完成' : '阻塞'}
                        </span>
                        <span className="text-xs text-slate-500">{record.created_at || '-'}</span>
                      </div>
                      <div className="mt-2 text-xs text-slate-300">{getLegacyRecordSummary(record)}</div>
                      <div className="mt-2 grid gap-2 text-xs text-slate-400 md:grid-cols-4">
                        <div>总镜头：{record.total_shots}</div>
                        <div>可交付：{record.deliverable_shots}</div>
                        <div>待验收：{record.pending_review_shots}</div>
                        <div>阻塞：{record.blocked_shots}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div>
              <h1 className="text-lg font-bold text-[#f1f5f9]">📥 导出</h1>
              <p className="text-[14px] text-[#64748b] mt-1">先确认交付 readiness，再选择导出格式。</p>
            </div>

            <div className={`mt-4 rounded-xl border px-5 py-4 ${
              exportReadiness.canExport
                ? 'border-emerald-800 bg-emerald-950/30'
                : 'border-amber-800 bg-amber-950/30'
            }`}>
              <div className={`text-sm font-semibold ${exportReadiness.canExport ? 'text-emerald-200' : 'text-amber-200'}`}>
                {exportReadiness.canExport ? '当前项目已具备导出条件' : '当前项目还不能稳定导出'}
              </div>
              <div className="mt-2 grid gap-2 md:grid-cols-4">
                <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-3">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">总镜头</div>
                  <div className="mt-1 text-lg text-slate-100">{exportReadiness.totalShots}</div>
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-3">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">可交付镜头</div>
                  <div className="mt-1 text-lg text-emerald-300">{exportReadiness.deliverableShots}</div>
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-3">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">待验收</div>
                  <div className="mt-1 text-lg text-amber-300">{exportReadiness.pendingReviewShots}</div>
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-3">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">阻塞项</div>
                  <div className="mt-1 text-lg text-amber-300">{exportReadiness.issues.length}</div>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  onClick={() => navigator.clipboard.writeText([
                    `导出状态：${exportReadiness.canExport ? '可导出' : '未完成'}`,
                    `总镜头：${exportReadiness.totalShots}`,
                    `可交付镜头：${exportReadiness.deliverableShots}`,
                    `待验收镜头：${exportReadiness.pendingReviewShots}`,
                    ...exportReadiness.issues.map((item) => `- ${item}`),
                  ].join('\n'))}
                  className="rounded-lg border border-sky-600/60 px-4 py-2 text-xs text-sky-200 transition hover:border-sky-400 hover:text-white"
                >
                  复制交付摘要
                </button>
                {!exportReadiness.canExport && (
                  <button
                    onClick={() => setActiveModule('storyboard')}
                    className="rounded-lg border border-amber-600/60 px-4 py-2 text-xs text-amber-200 transition hover:border-amber-400 hover:text-white"
                  >
                    回到分镜处理阻塞项
                  </button>
                )}
              </div>
              {referencedVisualAssetSummary.totalReferencedAssets > 0 ? (
                <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-3 text-xs text-slate-300">
                  <div className="font-medium text-slate-100">已引用视觉资产 readiness</div>
                  <div className="mt-2 grid gap-2 md:grid-cols-4">
                    <div>总数：{referencedVisualAssetSummary.totalReferencedAssets}</div>
                    <div>已锁定：{referencedVisualAssetSummary.lockedAssetCount}</div>
                    <div>待锁定：{referencedVisualAssetSummary.refReadyAssetCount}</div>
                    <div>缺参考图：{referencedVisualAssetSummary.draftAssetCount}</div>
                  </div>
                  {referencedVisualAssetSummary.rejectedAssetCount > 0 ? (
                    <div className="mt-2 text-amber-300">退回中：{referencedVisualAssetSummary.rejectedAssetCount}</div>
                  ) : null}
                </div>
              ) : null}
            </div>

            <div className="grid grid-cols-3 gap-4 mt-5">
              {[
                { icon: '📜', label: '文字剧本', count: scripts.length > 0 ? scripts.length + ' 集' : '暂无', ready: scripts.length > 0 },
                { icon: '🎬', label: '分镜表', count: storyboardData.length > 0 ? storyboardData.length + ' 个镜头' : '暂无', ready: storyboardData.length > 0 },
                { icon: '🎨', label: '视觉设定', count: visualReady ? `${visualAssetSummary.sceneCount} 场景 · ${visualAssetSummary.propCount} 道具 · ${visualAssetSummary.characterCount} 定妆` : '暂无', ready: visualReady },
              ].map((item, i) => (
                <div key={i} className="bg-[#111827] border border-[#1e293b] rounded-xl p-5">
                  <div className="text-2xl mb-2">{item.icon}</div>
                  <div className="text-[14px] font-semibold text-[#e2e8f0]">{item.label}</div>
                  <div className="text-[13px] text-[#64748b] mt-1">{item.count}</div>
                  {item.ready && (
                    <div className="mt-3">
                      <div className="text-xs text-blue-400 bg-blue-900/30 inline-block px-3 py-1.5 rounded-lg cursor-pointer hover:bg-blue-900/50 transition-colors">
                        复制全部
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="bg-[#111827] border border-[#1e293b] rounded-xl p-5 mt-4">
              <div className="text-xs font-semibold text-[#94a3b8] mb-4">交付阻塞清单</div>
              {exportReadiness.blockedShots.length === 0 ? (
                <div className="text-sm text-emerald-300">当前没有镜头阻塞，已经可以进入导出或交付环节。</div>
              ) : (
                <div className="space-y-2">
                  {exportReadiness.blockedShots.slice(0, 20).map((item) => (
                    <div key={`${item.episode}-${item.shotId}`} className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs text-slate-300">
                      第{item.episode}集 镜头 {item.shotId}：{item.reasons.join('、')}
                    </div>
                  ))}
                  {exportReadiness.blockedShots.length > 20 && (
                    <div className="text-xs text-slate-500">其余 {exportReadiness.blockedShots.length - 20} 个镜头仍待处理。</div>
                  )}
                </div>
              )}
            </div>

            <div className="bg-[#111827] border border-[#1e293b] rounded-xl p-5 mt-4">
              <div className="text-xs font-semibold text-[#94a3b8] mb-4">📥 文件导出</div>
              <div className="flex flex-wrap gap-3">
                <button onClick={handleExportPdf} className={`text-xs px-4 py-2 rounded-lg border transition-colors ${exportReadiness.canExport ? 'bg-[#1e293b] text-[#94a3b8] border-[#334155] hover:bg-[#334155]' : 'bg-slate-900 text-slate-600 border-slate-800 cursor-not-allowed'}`} disabled={!exportReadiness.canExport}>📄 导出 PDF</button>
                <button onClick={handleExportWord} className={`text-xs px-4 py-2 rounded-lg border transition-colors ${exportReadiness.canExport ? 'bg-[#1e293b] text-[#94a3b8] border-[#334155] hover:bg-[#334155]' : 'bg-slate-900 text-slate-600 border-slate-800 cursor-not-allowed'}`} disabled={!exportReadiness.canExport}>📄 导出 Word</button>
                <button onClick={handleExportJson} className="text-xs px-4 py-2 rounded-lg bg-[#1e293b] text-[#94a3b8] border border-[#334155] hover:bg-[#334155] transition-colors">📄 导出 JSON</button>
                <button onClick={handleExportFinalDraft} className={`text-xs px-4 py-2 rounded-lg border transition-colors ${exportReadiness.canExport ? 'bg-[#1e293b] text-[#94a3b8] border-[#334155] hover:bg-[#334155]' : 'bg-slate-900 text-slate-600 border-slate-800 cursor-not-allowed'}`} disabled={!exportReadiness.canExport}>📄 导出 Final Draft</button>
              </div>
            </div>
          </div>
        )}
      </div>
      {modelRegistryOpen && (
        <ModelRegistryModal
          data={modelRegistryData}
          error={modelRegistryError}
          onClose={() => setModelRegistryOpen(false)}
          onSaved={handleModelRegistrySaved}
        />
      )}
    </div>
  )
}

// --- Sub-components ---

function BookTitleInput({ bookId, initialTitle }: { bookId: number; initialTitle: string }) {
  const [title, setTitle] = useState(initialTitle)
  const [saving, setSaving] = useState(false)

  useEffect(() => { setTitle(initialTitle) }, [initialTitle])

  const save = async () => {
    if (title === initialTitle || !title.trim()) return
    setSaving(true)
    try {
      await fetch(`/api/books/${bookId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: title.trim() }),
      })
    } catch {}
    setSaving(false)
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-[15px] text-[#64748b]">📖 项目名称</span>
      <input
        value={title}
        onChange={e => setTitle(e.target.value)}
        onBlur={save}
        onKeyDown={e => { if (e.key === 'Enter') { (e.target as HTMLInputElement).blur() } }}
        className="text-[15px] bg-[#1e293b] border border-[#334155] rounded px-2 py-1 text-[#e2e8f0] outline-none focus:border-blue-500 min-w-[200px]"
        maxLength={50}
      />
      {saving && <span className="text-[12px] text-[#64748b]">保存中...</span>}
    </div>
  )
}

function VisualTab({ data }: { data: any }) {
  const [vTab, setVTab] = useState<'era' | 'location' | 'prop' | 'makeup'>('makeup')
  if (!data) return <div className="bg-[#111827] border border-[#1e293b] rounded-xl p-5 text-[15px] text-[#475569]">暂无视觉设定数据，请先运行 pipeline</div>

  const makeups = data.makeups || []
  const locations = data.locations || []
  const props = data.props || []
  const era = data.era

  const epGroups = groupMakeupsByEpisodeAndCharacter(makeups)

  return (
    <div className="bg-[#111827] border border-[#1e293b] rounded-xl p-5">
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        {[{k:'makeup',l:'🎭 定妆'},{k:'location',l:'🌄 场景'},{k:'prop',l:'🔧 道具'},{k:'era',l:'📜 时代'}].map(({k,l}) => (
          <button key={k} onClick={() => setVTab(k as any)}
            className={`text-[15px] px-3 py-1 rounded-lg border transition-colors ${vTab===k ? 'bg-blue-900/30 border-blue-600 text-blue-400' : 'bg-[#1e293b] border-[#334155] text-[#64748b] hover:text-[#94a3b8]'}`}>{l}</button>
        ))}
      </div>

      {/* Makeups grouped by episode */}
      {vTab === 'makeup' && (
        <div className="max-h-[500px] overflow-y-auto space-y-4">
          {Object.keys(epGroups).length === 0 && <div className="text-[15px] text-[#475569]">暂无定妆数据</div>}
          {Object.entries(epGroups).sort(([a], [b]) => Number(a) - Number(b)).map(([ep, charGroups]) => (
            <div key={ep}>
              <div className="mb-2 text-[15px] font-semibold text-[#94a3b8]">第 {ep} 集</div>
              <div className="space-y-2">
                {Object.entries(charGroups as Record<string, any[]>).map(([characterName, versions]) => (
                  <div key={`${ep}-${characterName}`} className="rounded-lg border border-[#1e293b] bg-[#0f172a] p-4">
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                      <div className="text-[14px] font-semibold text-[#e2e8f0]">{characterName}</div>
                      <div className="text-[12px] text-slate-400">{versions.length} 个定妆版本</div>
                    </div>
                    <div className="space-y-2">
                      {versions.map((m: any, i: number) => (
                        <div key={i} className="rounded-lg border border-slate-800 bg-[#0c1222] p-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={`rounded-full border px-2 py-0.5 text-[11px] ${getMakeupScopeTone(m.makeup_scope)}`}>{formatProductionMakeupScopeLabel(m.scope_label, m.makeup_scope)}</span>
                            {formatProductionMakeupStageLabel(m.stage_name, m.makeup_scope) ? <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">{formatProductionMakeupStageLabel(m.stage_name, m.makeup_scope)}</span> : null}
                            {Array.isArray(m.shot_ids) && m.shot_ids.length > 0 ? (
                              <div className="flex flex-wrap gap-1">
                                {m.shot_ids.map((sid: string | number) => (
                                  <span key={sid} className="rounded border border-blue-800/50 bg-blue-900/40 px-1.5 py-0.5 text-[11px] text-blue-300">镜头 {sid}</span>
                                ))}
                              </div>
                            ) : null}
                          </div>
                          <div className="mt-2 space-y-1 text-[14px] text-[#94a3b8]">
                            {m.core_prompt_zh ? <div><span className="text-[#64748b]">基础特征:</span>{m.core_prompt_zh}</div> : null}
                            {m.refined_outfit ? <div><span className="text-[#64748b]">服装:</span>{m.refined_outfit}</div> : null}
                            {m.makeup_spec ? <div><span className="text-[#64748b]">妆容:</span>{m.makeup_spec}</div> : null}
                            {m.expression_mood ? <div><span className="text-[#64748b]">情绪:</span>{m.expression_mood}</div> : null}
                            {m.consistency_notes ? <div><span className="text-[#64748b]">一致性约束:</span>{m.consistency_notes}</div> : null}
                          </div>
                          {m.visual_prompt_zh ? (
                            <details className="mt-2">
                              <summary className="cursor-pointer text-[15px] text-blue-400">查看固定模板定妆提示词</summary>
                              <div className="mt-2 rounded bg-[#020617] p-3 font-mono text-[15px] leading-relaxed text-[#cbd5e1] whitespace-pre-wrap">{m.visual_prompt_zh}</div>
                              {m.outfit_prompt_zh ? <div className="mt-2 rounded bg-[#020617] p-3 font-mono text-[15px] text-[#cbd5e1] whitespace-pre-wrap">{m.outfit_prompt_zh}</div> : null}
                              {m.scene_prompt_zh ? <div className="mt-2 rounded bg-[#020617] p-3 font-mono text-[15px] text-[#cbd5e1] whitespace-pre-wrap">{m.scene_prompt_zh}</div> : null}
                            </details>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {false && vTab === 'makeup' && (
        <div className="max-h-[500px] overflow-y-auto space-y-4">
          {Object.keys(epGroups).length === 0 && <div className="text-[15px] text-[#475569]">暂无定妆数据</div>}
          {Object.entries(epGroups).sort(([a],[b]) => Number(a)-Number(b)).map(([ep, chars]: [string, Record<string, any[]>]) => (
            <div key={ep}>
              <div className="text-[15px] font-semibold text-[#94a3b8] mb-2">第{ep}集</div>
              <div className="space-y-2">
                {Object.values(chars).flat().map((m: any, i: number) => (
                  <div key={i} className="bg-[#0f172a] border border-[#1e293b] rounded-lg p-4">
                    <div className="flex items-center gap-2 mb-1">
                      <div className="text-[14px] font-semibold text-[#e2e8f0]">{m.character_name}</div>
                      {m.shot_ids && m.shot_ids.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {m.shot_ids.map((sid: number) => (
                            <span key={sid} className="text-[12px] px-1.5 py-0.5 rounded bg-blue-900/40 text-blue-400 border border-blue-800/50">镜号{sid}</span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="text-[14px] text-[#94a3b8] space-y-1">
                      {m.refined_outfit && <div><span className="text-[#64748b]">服饰：</span>{m.refined_outfit}</div>}
                      {m.makeup_spec && <div><span className="text-[#64748b]">妆容：</span>{m.makeup_spec}</div>}
                      {m.expression_mood && <div><span className="text-[#64748b]">情绪：</span>{m.expression_mood}</div>}
                    </div>
                    {m.visual_prompt_zh && (
                      <details className="mt-2">
                        <summary className="text-[15px] text-blue-400 cursor-pointer">✨ 定妆提示词</summary>
                        <div className="text-[15px] text-[#cbd5e1] bg-[#0c1222] rounded p-3 mt-2 font-mono whitespace-pre-wrap leading-relaxed">{m.visual_prompt_zh}</div>
                        {m.outfit_prompt_zh && <div className="text-[15px] text-[#cbd5e1] bg-[#0c1222] rounded p-3 mt-2 font-mono whitespace-pre-wrap">{m.outfit_prompt_zh}</div>}
                        {m.scene_prompt_zh && <div className="text-[15px] text-[#cbd5e1] bg-[#0c1222] rounded p-3 mt-2 font-mono whitespace-pre-wrap">{m.scene_prompt_zh}</div>}
                      </details>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Locations */}
      {vTab === 'location' && (
        <div className="space-y-3 max-h-[500px] overflow-y-auto">
          <div className="text-[15px] text-[#64748b] mb-2">{locations.length} 个场景</div>
          {locations.length === 0 && <div className="text-[15px] text-[#475569]">暂无场景数据</div>}
          {locations.map((l: any, i: number) => (
            <div key={i} className="bg-[#0f172a] border border-[#1e293b] rounded-lg p-4">
              <div className="flex items-center gap-2 mb-1">
                <div className="text-[14px] font-semibold text-[#e2e8f0]">{l.name} <span className="text-[#475569] text-[14px] font-normal">{l.category} · {l.style}</span></div>
                {l.shot_ids && l.shot_ids.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {l.shot_ids.map((sid: number) => (
                      <span key={sid} className="text-[12px] px-1.5 py-0.5 rounded bg-green-900/40 text-green-400 border border-green-800/50">镜号{sid}</span>
                    ))}
                  </div>
                )}
              </div>
              <div className="text-[14px] text-[#94a3b8] space-y-1">
                {l.description && <div>{l.description}</div>}
                {l.lighting_mood && <div><span className="text-[#64748b]">光影：</span>{l.lighting_mood}</div>}
                {l.color_palette && <div><span className="text-[#64748b]">色调：</span>{l.color_palette}</div>}
              </div>
              {l.visual_prompt_zh && (
                <details className="mt-2">
                  <summary className="text-[15px] text-blue-400 cursor-pointer">✨ 场景提示词</summary>
                  <div className="text-[15px] text-[#cbd5e1] bg-[#0c1222] rounded p-3 mt-2 font-mono whitespace-pre-wrap">{l.visual_prompt_zh}</div>
                </details>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Props */}
      {vTab === 'prop' && (
        <div className="space-y-3 max-h-[500px] overflow-y-auto">
          <div className="text-[15px] text-[#64748b] mb-2">{props.length} 个关键道具</div>
          {props.length === 0 && <div className="text-[15px] text-[#475569]">暂无道具数据</div>}
          {props.map((p: any, i: number) => (
            <div key={i} className="bg-[#0f172a] border border-[#1e293b] rounded-lg p-4">
              <div className="flex items-center gap-2 mb-1">
                <div className="text-[14px] font-semibold text-[#e2e8f0]">{p.name} <span className="text-[#475569] text-[14px] font-normal">{p.category}</span></div>
                {p.shot_ids && p.shot_ids.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {p.shot_ids.map((sid: number) => (
                      <span key={sid} className="text-[12px] px-1.5 py-0.5 rounded bg-purple-900/40 text-purple-400 border border-purple-800/50">镜号{sid}</span>
                    ))}
                  </div>
                )}
              </div>
              <div className="text-[14px] text-[#94a3b8] space-y-1">
                {p.description && <div>{p.description}</div>}
                {p.associated_characters && <div><span className="text-[#64748b]">关联角色：</span>{p.associated_characters}</div>}
              </div>
              {p.visual_prompt_zh && (
                <details className="mt-2">
                  <summary className="text-[15px] text-blue-400 cursor-pointer">✨ 道具提示词</summary>
                  <div className="text-[15px] text-[#cbd5e1] bg-[#0c1222] rounded p-3 mt-2 font-mono whitespace-pre-wrap">{p.visual_prompt_zh}</div>
                </details>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Era */}
      {vTab === 'era' && (
        <div className="max-h-[500px] overflow-y-auto space-y-3">
          {!era ? <div className="text-[15px] text-[#475569]">暂无时代规范数据</div> : (
            <>
              {era.clothing_spec && <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg p-4">
                <div className="text-[14px] font-semibold text-[#e2e8f0] mb-1">👘 服饰规范</div>
                <div className="text-[14px] text-[#94a3b8]">{era.clothing_spec}</div>
              </div>}
              {era.color_palette && <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg p-4">
                <div className="text-[14px] font-semibold text-[#e2e8f0] mb-1">🎨 色彩基调</div>
                <div className="text-[14px] text-[#94a3b8]">{era.color_palette}</div>
              </div>}
              {era.architecture_spec && <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg p-4">
                <div className="text-[14px] font-semibold text-[#e2e8f0] mb-1">🏛️ 建筑规范</div>
                <div className="text-[14px] text-[#94a3b8]">{era.architecture_spec}</div>
              </div>}
            </>
          )}
        </div>
      )}
    </div>
  )
}

/* ─── StepBar ─── */
function StepBar({
  steps,
  activeStep,
  stepDone,
  onStepClick,
  onOpenComposer,
}: {
  steps: { key: string; label: string; icon: string }[]
  activeStep: string
  stepDone: Record<string, boolean>
  onStepClick: (k: any) => void
  onOpenComposer?: (() => void) | null
}) {
  const activeIdx = steps.findIndex(s => s.key === activeStep)

  return (
    <div className="w-48 bg-slate-900 border-r border-slate-800 flex flex-col flex-shrink-0">
      <div className="p-4 pb-2">
        <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">流程</div>
      </div>
      <div className="flex-1 px-3 space-y-1">
        {onOpenComposer && (
          <>
            <button
              onClick={onOpenComposer}
              className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all text-[14px] bg-gradient-to-r from-amber-900/20 to-red-900/20 border border-amber-800/30 text-amber-300 hover:from-amber-900/30 hover:to-red-900/30 mb-2"
            >
              <span className="w-5 text-center text-base">🎥</span>
              <span className="flex-1 truncate">视频生产管线</span>
              <svg className="w-3.5 h-3.5 text-amber-400/60" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
            <div className="h-px bg-[#1e293b] mb-2" />
          </>
        )}
        {steps.map((s, i) => {
          const done = stepDone[s.key]
          const isActive = s.key === activeStep
          const locked = s.key === 'export' ? false : !done && i > activeIdx

          return (
            <button
              key={s.key}
              onClick={() => !locked && onStepClick(s.key)}
              disabled={locked}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all text-[14px] ${
                isActive
                  ? 'bg-blue-900/30 border border-blue-700/50 text-blue-300'
                  : done
                    ? 'bg-emerald-900/20 text-emerald-300 hover:bg-emerald-900/30'
                    : locked
                      ? 'text-slate-600 cursor-not-allowed'
                      : 'text-slate-400 hover:bg-slate-800/50'
              }`}
            >
              <span className="w-5 text-center text-base">{s.icon}</span>
              <span className="flex-1 truncate">{s.label}</span>
              {done && (
                <svg className="w-4 h-4 text-emerald-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function ProductionJourneyPanel({
  title,
  detail,
  tone,
  stats,
  primaryLabel,
  primaryAction,
  secondaryLabel,
  secondaryAction,
}: {
  title: string
  detail: string
  tone: 'info' | 'warn' | 'success' | 'running' | 'error'
  stats: Array<{ label: string; value: string; ready: boolean }>
  primaryLabel: string
  primaryAction: () => void
  secondaryLabel?: string
  secondaryAction?: () => void
}) {
  const toneStyle = {
    info: 'border-blue-800/50 bg-blue-950/20',
    warn: 'border-amber-800/50 bg-amber-950/20',
    success: 'border-emerald-800/50 bg-emerald-950/20',
    running: 'border-sky-800/50 bg-sky-950/20',
    error: 'border-red-800/50 bg-red-950/20',
  }[tone]

  return (
    <div className="border-b border-slate-800 bg-slate-950/80 px-6 py-4">
      <div className={`rounded-2xl border px-5 py-4 ${toneStyle}`}>
        <div className="flex flex-wrap items-start gap-4">
          <div className="min-w-[240px] flex-1">
            <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500">当前阶段</div>
            <div className="mt-1 text-base font-semibold text-slate-100">{title}</div>
            <div className="mt-2 text-sm leading-6 text-slate-300">{detail}</div>
          </div>
          <div className="flex flex-wrap gap-2">
            {stats.map((item) => (
              <div key={item.label} className="min-w-[112px] rounded-2xl border border-slate-800 bg-slate-950/70 px-3 py-3">
                <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{item.label}</div>
                <div className={`mt-1 text-sm ${item.ready ? 'text-slate-100' : 'text-slate-300'}`}>{item.value}</div>
              </div>
            ))}
          </div>
          <div className="ml-auto flex flex-wrap gap-2">
            <button onClick={primaryAction} className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-blue-500">
              {primaryLabel}
            </button>
            {secondaryLabel && secondaryAction && (
              <button onClick={secondaryAction} className="rounded-lg border border-slate-700 px-4 py-2 text-xs text-slate-200 transition-colors hover:border-slate-500 hover:text-white">
                {secondaryLabel}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function formatReferenceSyncMessage(message: string | undefined, fallback: string): string {
  const text = String(message || '').trim()
  if (!text) return fallback
  if (text.includes('No related shots found for reference asset')) {
    return '参考图已生成并入库，尚未绑定镜头。可以先在视觉资产页完成镜头绑定。'
  }
  if (text.includes('Reference asset saved, but storyboard sync failed:')) {
    return text.replace('Reference asset saved, but storyboard sync failed:', '参考图已保存，但镜头引用同步失败：')
  }
  return text
}

function formatCreativeTaskMessage(message: string | undefined, fallback: string): string {
  const text = String(message || '').trim()
  if (!text) return fallback
  const normalized = text.toLowerCase()
  if (
    normalized.includes('http 429')
    || normalized.includes('rate limit')
    || text.includes('限流')
  ) {
    return 'PoYo 当前限流，任务可能仍在 provider 侧继续执行。请稍等片刻后点击“继续拉取结果”，不要重复新建任务。'
  }
  return text
}

function isCreativeTaskRecoveryMessage(message: string | undefined): boolean {
  const text = String(message || '').trim().toLowerCase()
  if (!text) return false
  return (
    text.includes('timed out')
    || text.includes('still running on the provider side')
    || text.includes('refresh shortly to recover the finished result')
    || text.includes('结果回收')
    || text.includes('provider side')
    || text.includes('http 429')
    || text.includes('rate limit')
    || text.includes('限流')
  )
}

export function deriveRecoverTaskIdFromError(error: unknown): string | null {
  if (!(error instanceof Error)) return null
  if (!isCreativeTaskRecoveryMessage(error.message)) return null
  return (error as Error & { taskId?: string }).taskId ?? null
}

function getReferenceStatusMeta(status: string | undefined) {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'locked') {
    return { label: '已锁定', tone: 'border-emerald-800/80 bg-emerald-950/40 text-emerald-200' }
  }
  if (normalized === 'selected') {
    return { label: '已采用', tone: 'border-sky-800/80 bg-sky-950/40 text-sky-200' }
  }
  if (normalized === 'rejected') {
    return { label: '已退回', tone: 'border-amber-800/80 bg-amber-950/40 text-amber-200' }
  }
  return { label: normalized || '未标记', tone: 'border-slate-800 bg-slate-950/60 text-slate-300' }
}

function getShotReferenceItems(shot: any) {
  const summary = shot?.locked_reference_summary
  if (Array.isArray(summary?.all) && summary.all.length > 0) {
    return summary.all
  }

  const references = shot?.asset_links?.references
  const items: any[] = []
  if (Array.isArray(references?.scene)) {
    const sceneRef = [...references.scene].reverse().find((item: any) => item?.adopted || ['selected', 'locked'].includes(String(item?.status || item?.label || '')))
    if (sceneRef) items.push({ ...sceneRef, scope: 'scene', subject: shot?.scene_name || '场景', token: sceneRef?.metadata?.referenceToken || '' })
  }
  if (references?.characters && typeof references.characters === 'object') {
    Object.entries(references.characters).forEach(([subject, group]) => {
      if (!Array.isArray(group)) return
      const active = [...group].reverse().find((item: any) => item?.adopted || ['selected', 'locked'].includes(String(item?.status || item?.label || '')))
      if (active) items.push({ ...active, scope: 'character', subject, token: active?.metadata?.referenceToken || '' })
    })
  }
  if (references?.props && typeof references.props === 'object') {
    Object.entries(references.props).forEach(([subject, group]) => {
      if (!Array.isArray(group)) return
      const active = [...group].reverse().find((item: any) => item?.adopted || ['selected', 'locked'].includes(String(item?.status || item?.label || '')))
      if (active) items.push({ ...active, scope: 'prop', subject, token: active?.metadata?.referenceToken || '' })
    })
  }
  return items
}

function getCompilerDiagnosticMeta(status: string | undefined) {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'blocked') {
    return {
      label: '阻塞',
      tone: 'border-rose-800/80 bg-rose-950/40 text-rose-200',
      textTone: 'text-rose-300',
    }
  }
  if (normalized === 'warning') {
    return {
      label: '警告',
      tone: 'border-amber-800/80 bg-amber-950/40 text-amber-200',
      textTone: 'text-amber-300',
    }
  }
  return {
    label: normalized ? '通过' : '未诊断',
    tone: normalized ? 'border-emerald-800/80 bg-emerald-950/40 text-emerald-200' : 'border-slate-800 bg-slate-950/60 text-slate-300',
    textTone: normalized ? 'text-emerald-300' : 'text-slate-400',
  }
}

function stringifyDebugJson(value: unknown) {
  try {
    return JSON.stringify(value ?? {}, null, 2)
  } catch {
    return '{}'
  }
}

function ShotReferenceSummaryCard({ shot }: { shot: any }) {
  const referenceItems = getShotReferenceItems(shot)
  const lockedCount = referenceItems.filter((item: any) => String(item?.status || '').toLowerCase() === 'locked' || item?.locked).length

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">当前视觉参考</div>
        <span className="rounded-full border border-slate-800 bg-slate-950 px-2 py-0.5 text-[11px] text-slate-300">总计 {referenceItems.length}</span>
        <span className="rounded-full border border-emerald-800/80 bg-emerald-950/40 px-2 py-0.5 text-[11px] text-emerald-200">已锁定 {lockedCount}</span>
      </div>
      {referenceItems.length > 0 ? (
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          {referenceItems.map((item: any, index: number) => {
            const meta = getReferenceStatusMeta(item?.status)
            return (
              <div key={`${item?.id || item?.scope || 'ref'}-${index}`} className="rounded-lg border border-slate-800 bg-slate-950/70 p-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full border border-slate-800 bg-slate-950 px-2 py-0.5 text-[11px] text-slate-400">
                    {item?.scope === 'scene' ? '场景' : item?.scope === 'character' ? '角色' : '道具'}
                  </span>
                  <span className={`rounded-full border px-2 py-0.5 text-[11px] ${meta.tone}`}>{meta.label}</span>
                </div>
                <div className="mt-2 text-sm text-slate-100">{String(item?.subject || item?.title || '未命名参考')}</div>
                <div className="mt-1 text-xs text-slate-400">{String(item?.token || '未配置引用 token')}</div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="mt-3 text-xs text-slate-500">当前镜头还没有同步进来的参考图。先在视觉资产页生成并采用参考图，或补充镜头绑定。</div>
      )}
    </div>
  )
}

function VisualAssetEditorCard({
  asset,
  assetType,
  assetName,
  storyboardShots,
  onSaveAsset,
  onCreateReference,
  onPatchReference,
  onDeleteReference,
  onGenerateReference,
  onRecoverReference,
  initialRecoverTaskId,
  isAutoRecovering,
  recoveryMeta,
  className,
  children,
}: {
  asset: any
  assetType: VisualAssetType
  assetName: string
  storyboardShots: any[]
  onSaveAsset: (
    assetType: VisualAssetType,
    assetId: number,
    payload: VisualAssetPatchPayload,
  ) => Promise<any>
  onCreateReference: (
    assetType: VisualAssetType,
    assetId: number,
    assetName: string,
    episode: number | null,
    payload: VisualReferenceCreatePayload,
  ) => Promise<VisualReferenceCreateResult>
  onPatchReference: (
    referenceId: number,
    payload: VisualReferenceUpdatePayload,
  ) => Promise<VisualReferenceCreateResult>
  onDeleteReference: (referenceId: number) => Promise<VisualReferenceDeleteResult>
  onGenerateReference: (
    assetType: VisualAssetType,
    asset: any,
    assetName: string,
  ) => Promise<VisualReferenceCreateResult>
  onRecoverReference: (taskId: string) => Promise<VisualReferenceCreateResult>
  initialRecoverTaskId?: string | null
  isAutoRecovering?: boolean
  recoveryMeta?: VisualReferenceRecoveryMeta | null
  className?: string
  children: ReactNode
}) {
  const [jimengRefName, setJimengRefName] = useState(asset.jimeng_ref_name ?? '')
  const [negativePrompt, setNegativePrompt] = useState(asset.negative_prompt ?? '')
  const [assetStatus, setAssetStatus] = useState(asset.asset_status ?? 'draft')
  const [imageUrl, setImageUrl] = useState('')
  const [referenceToken, setReferenceToken] = useState('')
  const [referenceStatus, setReferenceStatus] = useState('selected')
  const [referenceNotes, setReferenceNotes] = useState('')
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [referenceState, setReferenceState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [referenceMessage, setReferenceMessage] = useState('')
  const [generateState, setGenerateState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [generateMessage, setGenerateMessage] = useState('')
  const [recoverTaskId, setRecoverTaskId] = useState<string | null>(null)
  const [referenceActionState, setReferenceActionState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [referenceActionMessage, setReferenceActionMessage] = useState('')
  const [pendingReferenceDelete, setPendingReferenceDelete] = useState<{
    id: number
    mode: 'primary' | 'reference'
    isLocked: boolean
    label: string
  } | null>(null)
  const [referenceDraftNotes, setReferenceDraftNotes] = useState<Record<number, string>>({})
  const [linkedShotIds, setLinkedShotIds] = useState<string[]>(Array.isArray(asset.shot_ids) ? asset.shot_ids.map((item: unknown) => String(item)) : [])
  const [shotLinkState, setShotLinkState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [shotLinkMessage, setShotLinkMessage] = useState('')

  useEffect(() => {
    setJimengRefName(asset.jimeng_ref_name ?? '')
    setNegativePrompt(asset.negative_prompt ?? '')
    setAssetStatus(asset.asset_status ?? 'draft')
  }, [asset.id, asset.jimeng_ref_name, asset.negative_prompt, asset.asset_status])

  useEffect(() => {
    setLinkedShotIds(Array.isArray(asset.shot_ids) ? asset.shot_ids.map((item: unknown) => String(item)) : [])
  }, [asset.id, asset.shot_ids])

  useEffect(() => {
    setRecoverTaskId(initialRecoverTaskId ?? null)
  }, [asset.id, initialRecoverTaskId])

  const references = Array.isArray(asset.reference_assets) ? asset.reference_assets : []
  useEffect(() => {
    setReferenceDraftNotes(
      Object.fromEntries(
        references.map((reference: any) => [Number(reference.id), String(reference.notes || '')]),
      ),
    )
  }, [references])
  const derivedAssetStatus = String(asset?.derived_asset_status || asset?.asset_status || 'draft')
  const activeReferences = references.filter((reference: any) => ['selected', 'locked'].includes(String(reference?.status || '')))
  const lockedReference = [...references].reverse().find((reference: any) => String(reference?.status || '') === 'locked') ?? null
  const selectedReference = [...references].reverse().find((reference: any) => String(reference?.status || '') === 'selected') ?? null
  const primaryReference = lockedReference ?? selectedReference ?? references[references.length - 1] ?? null
  const primaryReferenceHref = primaryReference?.image_url || primaryReference?.local_path || ''
  const performReferenceDelete = useCallback(async (target: { id: number; mode: 'primary' | 'reference'; isLocked: boolean; label: string }) => {
    setReferenceActionState('saving')
    setReferenceActionMessage('')
    try {
      const result = await onDeleteReference(target.id)
      setReferenceActionState('saved')
      setReferenceActionMessage(
        formatReferenceSyncMessage(
          result.sync_warning,
          `${target.mode === 'primary' ? '主参考图' : '参考图'}已删除${typeof result.removed_storyboard_references === 'number' ? `，并移除 ${result.removed_storyboard_references} 个镜头引用` : ''}`,
        ),
      )
      setPendingReferenceDelete(null)
    } catch (error) {
      setReferenceActionState('error')
      setReferenceActionMessage(error instanceof Error ? error.message : '删除失败')
    }
  }, [onDeleteReference])
  const relatedShots = storyboardShots.filter((shot: any) => linkedShotIds.includes(String(shot?.shot_id)))
  const syncedShotIds = new Set(
    relatedShots
      .filter((shot: any) => {
        const assetLinks = shot?.asset_links?.references
        const items =
          assetType === 'character'
            ? assetLinks?.characters?.[assetName]
            : assetType === 'prop'
              ? assetLinks?.props?.[assetName]
              : assetLinks?.scene
        if (!Array.isArray(items)) return false
        return items.some((item: any) => activeReferences.some((reference: any) => String(item?.id) === `ref-${reference.id}`))
      })
      .map((shot: any) => String(shot?.shot_id)),
  )
  const unsyncedShotIds = linkedShotIds.filter((shotId) => !syncedShotIds.has(String(shotId)))
  const recoveryStatusMeta = recoveryMeta
    ? recoveryMeta.status === 'auto-recovering'
      ? { label: '自动回收中', tone: 'bg-blue-950/40 text-blue-300' }
      : recoveryMeta.status === 'waiting-provider'
        ? { label: '等待 Provider', tone: 'bg-amber-950/40 text-amber-300' }
        : recoveryMeta.status === 'recovered'
          ? { label: '刚刚回收成功', tone: 'bg-emerald-950/40 text-emerald-300' }
          : { label: '回收异常', tone: 'bg-red-950/40 text-red-300' }
    : null
  const shotSyncSummary = !activeReferences.length
    ? '还没有 selected / locked 参考图'
    : linkedShotIds.length === 0
      ? '还没有绑定关联镜头，可在下方手动勾选'
      : unsyncedShotIds.length === 0
        ? `已同步到 ${syncedShotIds.size} 个镜头`
        : `已同步 ${syncedShotIds.size}/${linkedShotIds.length} 个镜头，仍有 ${unsyncedShotIds.length} 个待同步`
  const referenceStatusMeta: Record<string, { label: string; tone: string }> = {
    candidate: { label: '候选', tone: 'bg-slate-800 text-slate-300' },
    selected: { label: '通过', tone: 'bg-sky-950/60 text-sky-300' },
    locked: { label: '锁定', tone: 'bg-emerald-950/50 text-emerald-300' },
    rejected: { label: '退回', tone: 'bg-amber-950/50 text-amber-300' },
  }

  return (
    <div className={className ?? 'mt-2 text-[14px] text-[#94a3b8] space-y-1'}>
      {children}

      <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">参考图快捷操作</div>
          <span className="rounded-full bg-slate-900 px-2 py-0.5 text-[11px] text-slate-300">共 {references.length} 张</span>
          <span className="rounded-full bg-sky-950/40 px-2 py-0.5 text-[11px] text-sky-300">通过 {references.filter((reference: any) => String(reference?.status || '') === 'selected').length}</span>
          <span className="rounded-full bg-emerald-950/40 px-2 py-0.5 text-[11px] text-emerald-300">锁定 {references.filter((reference: any) => String(reference?.status || '') === 'locked').length}</span>
          {recoveryStatusMeta ? (
            <span className={`rounded-full px-2 py-0.5 text-[11px] ${recoveryStatusMeta.tone}`}>{recoveryStatusMeta.label}</span>
          ) : null}
          {isAutoRecovering ? (
            <span className="rounded-full bg-blue-950/40 px-2 py-0.5 text-[11px] text-blue-300">自动检查中</span>
          ) : null}
          {primaryReference?.reference_token ? (
            <span className="rounded-full bg-purple-950/40 px-2 py-0.5 text-[11px] text-purple-300">主图 {primaryReference.reference_token}</span>
          ) : null}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={async () => {
              if (!asset.id) return
              setGenerateState('saving')
              setGenerateMessage('正在提交真实生成任务。通常需要 30-180 秒，请不要重复点击；如果稍后出现可恢复提示，再使用“继续拉取结果”。')
              setRecoverTaskId(null)
              try {
                const result = await onGenerateReference(assetType, asset, assetName)
                setGenerateState('saved')
                setRecoverTaskId(null)
                setGenerateMessage(formatReferenceSyncMessage(result.sync_warning, '参考图已生成并写入资产库，selected 状态会同步回相关镜头引用'))
              } catch (error) {
                setGenerateState('error')
                const nextMessage = formatCreativeTaskMessage(error instanceof Error ? error.message : '', '生成失败')
                setGenerateMessage(nextMessage)
                setRecoverTaskId(deriveRecoverTaskIdFromError(error))
              }
            }}
            className="rounded-lg border border-emerald-700 bg-emerald-950/40 px-4 py-2 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-900/50"
          >
            {generateState === 'saving' ? '生成中...' : '生成参考图'}
          </button>
          {recoverTaskId ? (
            <button
              type="button"
              onClick={async () => {
                setGenerateState('saving')
                setGenerateMessage('正在向 provider 拉取结果，请稍候。')
                try {
                  const result = await onRecoverReference(recoverTaskId)
                  if (result.stillRunning) {
                    setGenerateState('error')
                    setGenerateMessage('任务还在 provider 侧执行，已发起一次结果回收。请稍等片刻后再次点击“继续拉取结果”，不要重复新建任务。')
                    return
                  }
                  setGenerateState('saved')
                  setRecoverTaskId(null)
                  setGenerateMessage(formatReferenceSyncMessage(result.sync_warning, '已成功回收 provider 侧结果，参考图已写入资产库。'))
                } catch (error) {
                  setGenerateState('error')
                  setGenerateMessage(formatCreativeTaskMessage(error instanceof Error ? error.message : '', '结果回收失败'))
                }
              }}
              className="rounded-lg border border-amber-700/70 px-4 py-2 text-xs font-semibold text-amber-200 transition hover:border-amber-500 hover:text-white"
            >
              继续拉取结果
            </button>
          ) : null}
          {primaryReferenceHref ? (
            <a
              href={primaryReferenceHref}
              target="_blank"
              rel="noreferrer"
              className="rounded-lg border border-sky-700/70 px-4 py-2 text-xs font-semibold text-sky-200 transition hover:border-sky-500 hover:text-white"
            >
              查看主参考图
            </a>
          ) : null}
          {primaryReference ? (
            <button
              type="button"
              onClick={() => {
                setPendingReferenceDelete({
                  id: Number(primaryReference.id),
                  mode: 'primary',
                  isLocked: String(primaryReference?.status || '') === 'locked',
                  label: primaryReference.reference_token || assetName,
                })
              }}
              className="rounded-lg border border-red-700/70 px-4 py-2 text-xs font-semibold text-red-200 transition hover:border-red-500 hover:text-white"
            >
              删除主参考图
            </button>
          ) : null}
        </div>
        {pendingReferenceDelete?.mode === 'primary' ? (
          <InlineConfirmBar
            title={pendingReferenceDelete.isLocked ? '确认删除这张 locked 主参考图？' : '确认删除当前主参考图？'}
            message={pendingReferenceDelete.isLocked
              ? `删除后会同步移除相关镜头中的已锁定引用。当前目标：${pendingReferenceDelete.label}。`
              : `删除后这张主参考图会从资产库移除。当前目标：${pendingReferenceDelete.label}。`}
            confirmLabel="确认删除主参考图"
            busy={referenceActionState === 'saving'}
            onConfirm={() => performReferenceDelete(pendingReferenceDelete)}
            onCancel={() => setPendingReferenceDelete((current) => current?.mode === 'primary' ? null : current)}
            className="mt-3"
          />
        ) : null}
        <div className={`mt-3 text-xs ${
          generateState === 'saved'
            ? 'text-emerald-400'
            : generateState === 'error'
              ? (recoverTaskId ? 'text-amber-300' : 'text-red-400')
              : references.length > 0
                ? 'text-slate-400'
                : 'text-slate-500'
        }`}>
          {generateState === 'idle'
            ? (recoverTaskId
              ? '检测到一个仍可回收的真实生成任务。可以直接点击“继续拉取结果”，不需要重新发起生成。'
              : references.length > 0
                ? `当前已存在 ${references.length} 张参考图，主图操作已提升到卡片顶部。`
                : '当前还没有参考图，可以直接从这里生成或在下方登记。')
            : generateMessage}
        </div>
        {recoveryMeta ? (
          <div className="mt-2 text-[11px] text-slate-400">
            最近恢复状态：{recoveryMeta.message} · {String(recoveryMeta.updatedAt).replace('T', ' ').slice(0, 16)}
          </div>
        ) : null}
      </div>

      <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-slate-900 px-2 py-0.5 text-[11px] text-slate-300">状态 {derivedAssetStatus}</span>
          <span className="rounded-full bg-slate-900 px-2 py-0.5 text-[11px] text-slate-300">候选 {asset?.candidate_reference_count ?? 0}</span>
          {asset?.primary_reference_token ? (
            <span className="rounded-full bg-sky-950/40 px-2 py-0.5 text-[11px] text-sky-300">主参考 {asset.primary_reference_token}</span>
          ) : null}
          {asset?.locked_reference_token ? (
            <span className="rounded-full bg-emerald-950/40 px-2 py-0.5 text-[11px] text-emerald-300">锁定图 {asset.locked_reference_token}</span>
          ) : null}
        </div>
        {asset?.latest_generated_at ? (
          <div className="mt-2 text-xs text-slate-400">最近生成：{String(asset.latest_generated_at).replace('T', ' ').slice(0, 16)}</div>
        ) : (
          <div className="mt-2 text-xs text-slate-500">最近生成：暂无</div>
        )}
      </div>

      <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">镜头引用同步</div>
          <span className="rounded-full bg-slate-900 px-2 py-0.5 text-[11px] text-slate-300">关联镜头 {linkedShotIds.length}</span>
          <span className="rounded-full bg-emerald-950/40 px-2 py-0.5 text-[11px] text-emerald-300">已同步 {syncedShotIds.size}</span>
          {unsyncedShotIds.length > 0 ? (
            <span className="rounded-full bg-amber-950/40 px-2 py-0.5 text-[11px] text-amber-300">待同步 {unsyncedShotIds.length}</span>
          ) : null}
        </div>
        <div className={`mt-2 text-xs ${
          unsyncedShotIds.length > 0 && activeReferences.length > 0 ? 'text-amber-300' : 'text-slate-400'
        }`}>
          {shotSyncSummary}
        </div>
        {unsyncedShotIds.length > 0 ? (
          <div className="mt-2 text-xs text-amber-300">
            未同步镜头：{unsyncedShotIds.join(', ')}
          </div>
        ) : null}
        {activeReferences.length === 0 && linkedShotIds.length > 0 ? (
          <div className="mt-2 text-xs text-slate-500">
            原因：当前资产还没有 selected / locked 参考图，所以不会写入镜头引用。
          </div>
        ) : null}
        {linkedShotIds.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {linkedShotIds.map((shotId) => (
              <button
                key={shotId}
                type="button"
                onClick={() => setLinkedShotIds((current) => current.filter((item) => item !== shotId))}
                className={`rounded-lg border px-2.5 py-1 text-[11px] transition ${
                  syncedShotIds.has(String(shotId))
                    ? 'border-emerald-700/70 bg-emerald-950/30 text-emerald-200'
                    : 'border-amber-700/70 bg-amber-950/30 text-amber-200'
                }`}
                title="点击移除绑定"
              >
                镜号 {shotId}
              </button>
            ))}
          </div>
        ) : null}
        <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/70 p-3">
          <div className="text-xs text-slate-400">手动绑定到镜头</div>
          <div className="mt-2 flex max-h-40 flex-wrap gap-2 overflow-y-auto">
            {storyboardShots.map((shot: any) => {
              const shotId = String(shot?.shot_id ?? '')
              const selected = linkedShotIds.includes(shotId)
              return (
                <button
                  key={`${shot.episode}-${shotId}`}
                  type="button"
                  onClick={() => setLinkedShotIds((current) => (
                    current.includes(shotId)
                      ? current.filter((item) => item !== shotId)
                      : [...current, shotId]
                  ))}
                  className={`rounded-lg border px-2.5 py-1 text-[11px] transition ${
                    selected
                      ? 'border-blue-500 bg-blue-950/50 text-blue-200'
                      : 'border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white'
                  }`}
                >
                  E{shot.episode} · 镜号 {shotId}
                </button>
              )
            })}
          </div>
          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              onClick={async () => {
                if (!asset.id) return
                setShotLinkState('saving')
                setShotLinkMessage('')
                try {
                  const result = await onSaveAsset(assetType, asset.id, { shotIds: linkedShotIds })
                  setShotLinkState('saved')
                  setShotLinkMessage(formatReferenceSyncMessage(result?.sync_warning, `已保存 ${linkedShotIds.length} 个关联镜头`))
                } catch (error) {
                  setShotLinkState('error')
                  setShotLinkMessage(error instanceof Error ? error.message : '保存镜头绑定失败')
                }
              }}
              className="rounded-lg border border-sky-700 bg-sky-950/40 px-4 py-2 text-xs font-semibold text-sky-200 transition hover:bg-sky-900/50"
            >
              {shotLinkState === 'saving' ? '保存中...' : '保存镜头绑定'}
            </button>
            <span className={`text-xs ${
              shotLinkState === 'saved'
                ? (shotLinkMessage.includes('sync failed') ? 'text-amber-300' : 'text-emerald-400')
                : shotLinkState === 'error'
                  ? 'text-red-400'
                  : 'text-slate-500'
            }`}>
              {shotLinkState === 'idle' ? '保存后会重新同步 selected / locked 参考图到这些镜头' : shotLinkMessage}
            </span>
          </div>
        </div>
      </div>

      <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
        <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">阶段 1 资产设置</div>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <label className="block">
            <div className="mb-1 text-[12px] text-slate-400">引用名</div>
            <input
              value={jimengRefName}
              onChange={(event) => setJimengRefName(event.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-blue-500"
              placeholder="@forest-camp"
            />
          </label>
          <label className="block">
            <div className="mb-1 text-[12px] text-slate-400">资产状态</div>
            <select
              value={assetStatus}
              onChange={(event) => setAssetStatus(event.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-blue-500"
            >
              <option value="draft">draft</option>
              <option value="ref_ready">ref_ready</option>
              <option value="locked">locked</option>
            </select>
          </label>
        </div>
        <label className="mt-3 block">
          <div className="mb-1 text-[12px] text-slate-400">负向提示词</div>
          <textarea
            value={negativePrompt}
            onChange={(event) => setNegativePrompt(event.target.value)}
            rows={3}
            className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-blue-500"
            placeholder="no modern objects, no extra limbs"
          />
        </label>
        <div className="mt-3 flex items-center gap-3">
          <button
            onClick={async () => {
              if (!asset.id) return
              setSaveState('saving')
              try {
                await onSaveAsset(assetType, asset.id, { jimengRefName, negativePrompt, assetStatus })
                setSaveState('saved')
              } catch {
                setSaveState('error')
              }
            }}
            className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-blue-500"
          >
            {saveState === 'saving' ? '保存中...' : '保存资产设置'}
          </button>
          <span className={`text-xs ${
            saveState === 'saved'
              ? 'text-emerald-400'
              : saveState === 'error'
                ? 'text-red-400'
                : 'text-slate-500'
          }`}>
            {saveState === 'saved' ? '已保存' : saveState === 'error' ? '保存失败' : '保存后会同步到聚合输出'}
          </span>
        </div>
      </div>

      <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
        <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">参考图</div>
        {references.length > 0 ? (
          <div className="mt-3 space-y-2">
            {references.map((reference: any) => (
              <div key={reference.id} className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-slate-100">{reference.asset_name || assetName}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] ${referenceStatusMeta[String(reference.status || 'candidate')]?.tone || referenceStatusMeta.candidate.tone}`}>
                    {referenceStatusMeta[String(reference.status || 'candidate')]?.label || '候选'}
                  </span>
                  {reference.reference_token ? (
                    <span className="rounded-full bg-blue-950/60 px-2 py-0.5 text-[11px] text-blue-300">{reference.reference_token}</span>
                  ) : null}
                  {reference.model ? (
                    <span className="rounded-full bg-emerald-950/50 px-2 py-0.5 text-[11px] text-emerald-300">{reference.model}</span>
                  ) : null}
                  {reference.meta_info?.version ? (
                    <span className="rounded-full bg-slate-900 px-2 py-0.5 text-[11px] text-slate-300">{reference.meta_info.version}</span>
                  ) : null}
                  <button
                    onClick={() => {
                      setPendingReferenceDelete({
                        id: Number(reference.id),
                        mode: 'reference',
                        isLocked: String(reference.status || '') === 'locked',
                        label: reference.reference_token || reference.asset_name || assetName,
                      })
                    }}
                    className="ml-auto rounded-lg border border-red-700/70 px-2.5 py-1 text-[11px] text-red-200 transition hover:border-red-500 hover:text-white"
                  >
                    删除参考图
                  </button>
                </div>
                {pendingReferenceDelete?.mode === 'reference' && pendingReferenceDelete.id === Number(reference.id) ? (
                  <InlineConfirmBar
                    title={pendingReferenceDelete.isLocked ? '确认删除这张 locked 参考图？' : '确认删除这张参考图？'}
                    message={pendingReferenceDelete.isLocked
                      ? `删除后会同步移除相关镜头引用。当前目标：${pendingReferenceDelete.label}。`
                      : `删除后这张参考图会从当前资产中移除。当前目标：${pendingReferenceDelete.label}。`}
                    confirmLabel="确认删除参考图"
                    busy={referenceActionState === 'saving'}
                    onConfirm={() => performReferenceDelete(pendingReferenceDelete)}
                    onCancel={() => setPendingReferenceDelete((current) => current?.id === Number(reference.id) ? null : current)}
                    className="mt-3"
                  />
                ) : null}
                {reference.prompt ? (
                  <div className="mt-2 line-clamp-3 text-xs text-slate-400">{reference.prompt}</div>
                ) : null}
                {reference.image_url || reference.local_path ? (
                  <a
                    href={reference.image_url || reference.local_path}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 block text-xs text-blue-400 hover:text-blue-300"
                  >
                    查看参考图
                  </a>
                ) : null}
                {reference.created_at ? (
                  <div className="mt-2 text-[11px] text-slate-500">
                    生成时间：{String(reference.created_at).replace('T', ' ').slice(0, 16)}
                  </div>
                ) : null}
                {reference.notes ? <div className="mt-2 text-xs text-slate-400">{reference.notes}</div> : null}
                <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/80 p-3">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">审核动作</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {[
                      { status: 'selected', label: '通过' },
                      { status: 'locked', label: '锁定终图' },
                      { status: 'rejected', label: '退回重生' },
                      { status: 'candidate', label: '转为候选' },
                    ].map((action) => (
                      <button
                        key={action.status}
                        onClick={async () => {
                          setReferenceActionState('saving')
                          setReferenceActionMessage('')
                          try {
                            const result = await onPatchReference(reference.id, { status: action.status })
                            setReferenceActionState('saved')
                            setReferenceActionMessage(formatReferenceSyncMessage(result.sync_warning, `参考图已更新为${action.label}`))
                          } catch (error: any) {
                            setReferenceActionState('error')
                            setReferenceActionMessage(error instanceof Error ? error.message : '参考图审核更新失败')
                          }
                        }}
                        className={`rounded-lg border px-2.5 py-1 text-[11px] transition ${
                          String(reference.status || 'candidate') === action.status
                            ? 'border-blue-500 bg-blue-950/50 text-blue-200'
                            : 'border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white'
                        }`}
                      >
                        {action.label}
                      </button>
                    ))}
                  </div>
                  <div className="mt-3">
                    <div className="mb-1 text-[12px] text-slate-400">审核备注</div>
                    <textarea
                      value={referenceDraftNotes[Number(reference.id)] ?? String(reference.notes || '')}
                      onChange={(event) => {
                        const nextValue = event.target.value
                        setReferenceDraftNotes((current) => ({ ...current, [Number(reference.id)]: nextValue }))
                      }}
                      rows={2}
                      className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-blue-500"
                      placeholder="记录通过原因、退回意见或下一轮生成要求"
                    />
                    <div className="mt-2 flex flex-wrap gap-2">
                      <button
                        onClick={async () => {
                          setReferenceActionState('saving')
                          setReferenceActionMessage('')
                          try {
                            const result = await onPatchReference(reference.id, {
                              notes: referenceDraftNotes[Number(reference.id)] ?? String(reference.notes || ''),
                            })
                            setReferenceActionState('saved')
                            setReferenceActionMessage(formatReferenceSyncMessage(result.sync_warning, '审核备注已保存'))
                          } catch (error) {
                            setReferenceActionState('error')
                            setReferenceActionMessage(error instanceof Error ? error.message : '审核备注保存失败')
                          }
                        }}
                        className="rounded-lg border border-slate-700 px-2.5 py-1 text-[11px] text-slate-300 transition hover:border-slate-500 hover:text-white"
                      >
                        保存备注
                      </button>
                      <button
                        onClick={async () => {
                          setGenerateState('saving')
                          setGenerateMessage('正在提交真实生成任务。通常需要 30-180 秒，请不要重复点击；如果稍后出现可恢复提示，再使用“继续拉取结果”。')
                          setRecoverTaskId(null)
                          try {
                            const result = await onGenerateReference(assetType, asset, assetName)
                            setGenerateState('saved')
                            setRecoverTaskId(null)
                            setGenerateMessage(formatReferenceSyncMessage(result.sync_warning, '已基于当前资产配置重新生成参考图'))
                          } catch (error) {
                            setGenerateState('error')
                            const nextMessage = formatCreativeTaskMessage(error instanceof Error ? error.message : '', '重新生成失败')
                            setGenerateMessage(nextMessage)
                            setRecoverTaskId(deriveRecoverTaskIdFromError(error))
                          }
                        }}
                        className="rounded-lg border border-amber-700/70 px-2.5 py-1 text-[11px] text-amber-200 transition hover:border-amber-500 hover:text-white"
                      >
                        基于当前资产重生
                      </button>
                    </div>
                  </div>
                </div>
                <div className="mt-3">
                  <details className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2">
                    <summary className="cursor-pointer list-none text-[11px] text-slate-400 transition hover:text-slate-200">
                      高级操作
                    </summary>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {['candidate', 'selected', 'locked', 'rejected'].map((status) => (
                        <button
                          key={status}
                          onClick={async () => {
                            setReferenceActionState('saving')
                            setReferenceActionMessage('')
                            try {
                              const result = await onPatchReference(reference.id, { status })
                              setReferenceActionState('saved')
                              setReferenceActionMessage(formatReferenceSyncMessage(result.sync_warning, `参考图状态已更新为 ${status}`))
                            } catch (error) {
                              setReferenceActionState('error')
                              setReferenceActionMessage(error instanceof Error ? error.message : '状态更新失败')
                            }
                          }}
                          className={`rounded-lg border px-2.5 py-1 text-[11px] transition ${
                            reference.status === status
                              ? 'border-blue-500 bg-blue-950/50 text-blue-200'
                              : 'border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white'
                          }`}
                        >
                          {status}
                        </button>
                      ))}
                    </div>
                  </details>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-3 text-sm text-slate-500">还没有参考图。</div>
        )}

        {referenceActionState !== 'idle' ? (
          <div className={`mt-3 text-xs ${
            referenceActionState === 'saved'
              ? (referenceActionMessage.includes('sync failed') ? 'text-amber-300' : 'text-emerald-400')
              : referenceActionState === 'error'
                ? 'text-red-400'
                : 'text-slate-500'
          }`}>
            {referenceActionState === 'saving' ? '正在更新参考图...' : referenceActionMessage}
          </div>
        ) : null}

        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <label className="block">
            <div className="mb-1 text-[12px] text-slate-400">图片 URL</div>
            <input
              value={imageUrl}
              onChange={(event) => setImageUrl(event.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-blue-500"
              placeholder="https://example.com/reference.png"
            />
          </label>
          <label className="block">
            <div className="mb-1 text-[12px] text-slate-400">引用 token</div>
            <input
              value={referenceToken}
              onChange={(event) => setReferenceToken(event.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-blue-500"
              placeholder="@forest-camp"
            />
          </label>
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <label className="block">
            <div className="mb-1 text-[12px] text-slate-400">参考图状态</div>
            <select
              value={referenceStatus}
              onChange={(event) => setReferenceStatus(event.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-blue-500"
            >
              <option value="candidate">candidate</option>
              <option value="selected">selected</option>
              <option value="locked">locked</option>
              <option value="rejected">rejected</option>
            </select>
          </label>
          <label className="block">
            <div className="mb-1 text-[12px] text-slate-400">备注</div>
            <input
              value={referenceNotes}
              onChange={(event) => setReferenceNotes(event.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-blue-500"
              placeholder="主参考图"
            />
          </label>
        </div>
        <div className="mt-3 text-xs text-slate-500">用当前资产提示词直接生成候选图并自动入库；快捷入口已置顶。</div>
        <div className="mt-3 flex items-center gap-3">
          <button
            onClick={async () => {
              if (!asset.id || !imageUrl.trim()) return
              setReferenceState('saving')
              setReferenceMessage('')
              try {
                const result = await onCreateReference(assetType, asset.id, assetName, asset.episode ?? null, {
                  imageUrl,
                  referenceToken,
                  status: referenceStatus,
                  notes: referenceNotes,
                })
                setImageUrl('')
                setReferenceToken('')
                setReferenceNotes('')
                setReferenceState('saved')
                setReferenceMessage(formatReferenceSyncMessage(result.sync_warning, '参考图已登记'))
              } catch {
                setReferenceState('error')
                setReferenceMessage('登记失败')
              }
            }}
            className="rounded-lg border border-purple-700 bg-purple-950/40 px-4 py-2 text-xs font-semibold text-purple-200 transition hover:bg-purple-900/50"
          >
            {referenceState === 'saving' ? '登记中...' : '登记参考图'}
          </button>
          <span className={`text-xs ${
            referenceState === 'saved'
              ? (referenceMessage.includes('sync failed') ? 'text-amber-300' : 'text-emerald-400')
              : referenceState === 'error'
                ? 'text-red-400'
                : 'text-slate-500'
          }`}>
            {referenceState === 'saved' ? referenceMessage : referenceState === 'error' ? referenceMessage || '登记失败' : 'selected / locked 会同步回镜头引用'}
          </span>
        </div>
      </div>
    </div>
  )
}

function StoryboardStructureEditor({
  shot,
  onSave,
}: {
  shot: any
  onSave: (
    episode: number,
    shotId: string | number,
    payload: {
      duration: number
      cameraAngle: string
      cameraMovement: string
      transition: string
      sceneAssetId: string
      characterAssetIds: string[]
      propAssetIds: string[]
      styleKey: string
      characterBlocking: Array<Record<string, string>>
      actionBeats: Array<Record<string, string | number>>
    },
  ) => Promise<void>
}) {
  const structured = shot.structured_shot ?? {}
  const POSITION_PRESETS = ['左前', '左中', '左后', '中前', '中心', '中后', '右前', '右中', '右后']
  const FACING_PRESETS = ['镜头', '左', '右', '前方', '背对', '对视']
  const ACTION_PRESETS = ['站定', '走近', '转身', '抬手', '对话', '停顿', '看向对方']
  const DURATION_PRESETS = ['0.5s', '1s', '2s', '3s', '5s']
  const SHOT_DURATION_PRESETS = [1, 2, 3, 5, 8]
  const CAMERA_ANGLE_PRESETS = ['WS', 'MS', 'CU', 'ECU', 'OTS']
  const CAMERA_MOVEMENT_PRESETS = ['static', 'push-in', 'pan', 'dolly', 'zoom']
  const TRANSITION_PRESETS = ['cut', 'dissolve', 'fade', 'whip']
  const toRecordArray = (value: unknown): Array<Record<string, string>> => {
    if (!Array.isArray(value)) return []
    return value.map((item) => {
      if (!item || typeof item !== 'object' || Array.isArray(item)) return {}
      return Object.fromEntries(
        Object.entries(item as Record<string, unknown>).map(([key, itemValue]) => [key, itemValue == null ? '' : String(itemValue)]),
      )
    })
  }
  const toBeatArray = (value: unknown): Array<Record<string, string | number>> => {
    if (!Array.isArray(value)) return []
    return value.map((item) => {
      if (!item || typeof item !== 'object' || Array.isArray(item)) return {}
      return Object.fromEntries(
        Object.entries(item as Record<string, unknown>).map(([key, itemValue]) => [key, typeof itemValue === 'number' ? itemValue : itemValue == null ? '' : String(itemValue)]),
      )
    })
  }
  const formatJson = (value: unknown) => JSON.stringify(value ?? [], null, 2)
  const [sceneAssetId, setSceneAssetId] = useState(String(structured.scene_asset_id ?? ''))
  const [characterAssetIds, setCharacterAssetIds] = useState((structured.character_asset_ids ?? []).join(', '))
  const [propAssetIds, setPropAssetIds] = useState((structured.prop_asset_ids ?? []).join(', '))
  const [styleKey, setStyleKey] = useState(String(structured.style_key ?? 'default'))
  const [duration, setDuration] = useState(Number(structured.duration ?? shot.duration ?? 3))
  const [cameraAngle, setCameraAngle] = useState(String(structured.camera_angle ?? shot.camera_angle ?? 'MS'))
  const [cameraMovement, setCameraMovement] = useState(String(structured.camera_movement ?? shot.camera_movement ?? 'static'))
  const [transition, setTransition] = useState(String(structured.transition ?? shot.transition ?? 'cut'))
  const [characterBlockingRows, setCharacterBlockingRows] = useState<Array<Record<string, string>>>(toRecordArray(structured.character_blocking))
  const [actionBeatRows, setActionBeatRows] = useState<Array<Record<string, string | number>>>(toBeatArray(structured.action_beats))
  const [characterBlockingText, setCharacterBlockingText] = useState(formatJson(structured.character_blocking))
  const [actionBeatsText, setActionBeatsText] = useState(formatJson(structured.action_beats))
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [jsonState, setJsonState] = useState<'idle' | 'synced' | 'error'>('idle')
  const moveRow = useCallback(<T,>(rows: T[], fromIndex: number, toIndex: number) => {
    if (toIndex < 0 || toIndex >= rows.length) return rows
    const next = [...rows]
    const [target] = next.splice(fromIndex, 1)
    next.splice(toIndex, 0, target)
    return next
  }, [])

  useEffect(() => {
    setSceneAssetId(String(structured.scene_asset_id ?? ''))
    setCharacterAssetIds((structured.character_asset_ids ?? []).join(', '))
    setPropAssetIds((structured.prop_asset_ids ?? []).join(', '))
    setStyleKey(String(structured.style_key ?? 'default'))
    setDuration(Number(structured.duration ?? shot.duration ?? 3))
    setCameraAngle(String(structured.camera_angle ?? shot.camera_angle ?? 'MS'))
    setCameraMovement(String(structured.camera_movement ?? shot.camera_movement ?? 'static'))
    setTransition(String(structured.transition ?? shot.transition ?? 'cut'))
    setCharacterBlockingRows(toRecordArray(structured.character_blocking))
    setActionBeatRows(toBeatArray(structured.action_beats))
    setCharacterBlockingText(formatJson(structured.character_blocking))
    setActionBeatsText(formatJson(structured.action_beats))
    setJsonState('idle')
  }, [shot.shot_id, shot.structured_shot])

  const syncFormToJson = useCallback(() => {
    setCharacterBlockingText(formatJson(characterBlockingRows))
    setActionBeatsText(formatJson(actionBeatRows))
    setJsonState('synced')
  }, [actionBeatRows, characterBlockingRows])

  const syncJsonToForm = useCallback(() => {
    try {
      setCharacterBlockingRows(toRecordArray(JSON.parse(characterBlockingText || '[]')))
      setActionBeatRows(toBeatArray(JSON.parse(actionBeatsText || '[]')))
      setJsonState('synced')
    } catch {
      setJsonState('error')
    }
  }, [actionBeatsText, characterBlockingText])

  return (
    <details className="mt-2 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      <summary className="cursor-pointer text-[13px] text-amber-300">结构化镜头</summary>
      <div className="mt-3 space-y-3">
        <div className="grid gap-3 md:grid-cols-2">
          <label className="block">
            <div className="mb-1 text-[12px] text-slate-400">场景资产 ID</div>
            <input
              value={sceneAssetId}
              onChange={(event) => setSceneAssetId(event.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-amber-500"
              placeholder="12"
            />
          </label>
          <label className="block">
            <div className="mb-1 text-[12px] text-slate-400">风格键</div>
            <input
              value={styleKey}
              onChange={(event) => setStyleKey(event.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-amber-500"
              placeholder="default"
            />
          </label>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="block">
            <div className="mb-1 text-[12px] text-slate-400">角色资产 IDs</div>
            <input
              value={characterAssetIds}
              onChange={(event) => setCharacterAssetIds(event.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-amber-500"
              placeholder="21,34"
            />
          </label>
          <label className="block">
            <div className="mb-1 text-[12px] text-slate-400">道具资产 IDs</div>
            <input
              value={propAssetIds}
              onChange={(event) => setPropAssetIds(event.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-amber-500"
              placeholder="55,89"
            />
          </label>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <div className="mb-2 text-[12px] font-medium text-slate-200">镜头参数</div>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <label className="block">
              <div className="mb-1 text-[12px] text-slate-400">时长（秒）</div>
              <input
                type="number"
                min={1}
                value={duration}
                onChange={(event) => setDuration(Number(event.target.value || 0))}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-amber-500"
              />
              <div className="mt-1 flex flex-wrap gap-1">
                {SHOT_DURATION_PRESETS.map((preset) => (
                  <button key={preset} type="button" onClick={() => setDuration(preset)} className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-400 transition hover:border-slate-500 hover:text-white">{preset}s</button>
                ))}
              </div>
            </label>
            <label className="block">
              <div className="mb-1 text-[12px] text-slate-400">景别</div>
              <input
                value={cameraAngle}
                onChange={(event) => setCameraAngle(event.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-amber-500"
              />
              <div className="mt-1 flex flex-wrap gap-1">
                {CAMERA_ANGLE_PRESETS.map((preset) => (
                  <button key={preset} type="button" onClick={() => setCameraAngle(preset)} className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-400 transition hover:border-slate-500 hover:text-white">{preset}</button>
                ))}
              </div>
            </label>
            <label className="block">
              <div className="mb-1 text-[12px] text-slate-400">运镜</div>
              <input
                value={cameraMovement}
                onChange={(event) => setCameraMovement(event.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-amber-500"
              />
              <div className="mt-1 flex flex-wrap gap-1">
                {CAMERA_MOVEMENT_PRESETS.map((preset) => (
                  <button key={preset} type="button" onClick={() => setCameraMovement(preset)} className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-400 transition hover:border-slate-500 hover:text-white">{preset}</button>
                ))}
              </div>
            </label>
            <label className="block">
              <div className="mb-1 text-[12px] text-slate-400">过渡</div>
              <input
                value={transition}
                onChange={(event) => setTransition(event.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-amber-500"
              />
              <div className="mt-1 flex flex-wrap gap-1">
                {TRANSITION_PRESETS.map((preset) => (
                  <button key={preset} type="button" onClick={() => setTransition(preset)} className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-400 transition hover:border-slate-500 hover:text-white">{preset}</button>
                ))}
              </div>
            </label>
          </div>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div>
              <div className="text-[12px] font-medium text-slate-200">角色站位</div>
              <div className="text-[11px] text-slate-500">用表单维护角色、位置、朝向和动作，降低日常编辑成本。</div>
            </div>
            <button
              type="button"
              onClick={() => setCharacterBlockingRows((current) => [...current, { character: '', position: '', facing: '', action: '' }])}
              className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
            >
              添加站位
            </button>
          </div>
          <div className="space-y-2">
            {characterBlockingRows.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-700 px-3 py-3 text-xs text-slate-500">暂无角色站位，点击“添加站位”开始编辑。</div>
            ) : characterBlockingRows.map((row, index) => (
              <div key={`blocking-${index}`} className="grid gap-2 rounded-lg border border-slate-800 bg-slate-950/70 p-2 md:grid-cols-[1fr_1fr_1fr_1.2fr_auto_auto_auto]">
                <input value={row.character || ''} onChange={(event) => setCharacterBlockingRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, character: event.target.value } : item))} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 outline-none transition focus:border-amber-500" placeholder="角色" />
                <div className="space-y-1">
                  <input value={row.position || ''} onChange={(event) => setCharacterBlockingRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, position: event.target.value } : item))} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 outline-none transition focus:border-amber-500" placeholder="站位" />
                  <div className="flex flex-wrap gap-1">
                    {POSITION_PRESETS.slice(0, 3).map((preset) => (
                      <button key={preset} type="button" onClick={() => setCharacterBlockingRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, position: preset } : item))} className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-400 transition hover:border-slate-500 hover:text-white">{preset}</button>
                    ))}
                  </div>
                </div>
                <div className="space-y-1">
                  <input value={row.facing || ''} onChange={(event) => setCharacterBlockingRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, facing: event.target.value } : item))} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 outline-none transition focus:border-amber-500" placeholder="朝向" />
                  <div className="flex flex-wrap gap-1">
                    {FACING_PRESETS.slice(0, 3).map((preset) => (
                      <button key={preset} type="button" onClick={() => setCharacterBlockingRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, facing: preset } : item))} className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-400 transition hover:border-slate-500 hover:text-white">{preset}</button>
                    ))}
                  </div>
                </div>
                <div className="space-y-1">
                  <input value={row.action || ''} onChange={(event) => setCharacterBlockingRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, action: event.target.value } : item))} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 outline-none transition focus:border-amber-500" placeholder="动作" />
                  <div className="flex flex-wrap gap-1">
                    {ACTION_PRESETS.slice(0, 3).map((preset) => (
                      <button key={preset} type="button" onClick={() => setCharacterBlockingRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, action: preset } : item))} className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-400 transition hover:border-slate-500 hover:text-white">{preset}</button>
                    ))}
                  </div>
                </div>
                <button type="button" onClick={() => setCharacterBlockingRows((current) => moveRow(current, index, index - 1))} disabled={index === 0} className={`rounded-lg border px-3 py-2 text-xs transition ${index === 0 ? 'cursor-not-allowed border-slate-800 text-slate-600' : 'border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white'}`}>上移</button>
                <button type="button" onClick={() => setCharacterBlockingRows((current) => moveRow(current, index, index + 1))} disabled={index === characterBlockingRows.length - 1} className={`rounded-lg border px-3 py-2 text-xs transition ${index === characterBlockingRows.length - 1 ? 'cursor-not-allowed border-slate-800 text-slate-600' : 'border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white'}`}>下移</button>
                <button type="button" onClick={() => setCharacterBlockingRows((current) => current.filter((_, itemIndex) => itemIndex !== index))} className="rounded-lg border border-rose-800/60 px-3 py-2 text-xs text-rose-300 transition hover:border-rose-600 hover:text-white">删除</button>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div>
              <div className="text-[12px] font-medium text-slate-200">动作节拍</div>
              <div className="text-[11px] text-slate-500">按镜头节奏记录主体、动作和时长，适合先粗排后细化。</div>
            </div>
            <button
              type="button"
              onClick={() => setActionBeatRows((current) => [...current, { beat: current.length + 1, subject: '', action: '', duration: '' }])}
              className="rounded-lg border border-slate-700 px-3 py-1 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
            >
              添加节拍
            </button>
          </div>
          <div className="space-y-2">
            {actionBeatRows.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-700 px-3 py-3 text-xs text-slate-500">暂无动作节拍，点击“添加节拍”开始编辑。</div>
            ) : actionBeatRows.map((row, index) => (
              <div key={`beat-${index}`} className="grid gap-2 rounded-lg border border-slate-800 bg-slate-950/70 p-2 md:grid-cols-[80px_1fr_1.4fr_100px_auto_auto_auto]">
                <input value={String(row.beat ?? '')} onChange={(event) => setActionBeatRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, beat: event.target.value } : item))} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 outline-none transition focus:border-amber-500" placeholder="节拍" />
                <input value={String(row.subject ?? '')} onChange={(event) => setActionBeatRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, subject: event.target.value } : item))} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 outline-none transition focus:border-amber-500" placeholder="主体" />
                <div className="space-y-1">
                  <input value={String(row.action ?? '')} onChange={(event) => setActionBeatRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, action: event.target.value } : item))} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 outline-none transition focus:border-amber-500" placeholder="动作描述" />
                  <div className="flex flex-wrap gap-1">
                    {ACTION_PRESETS.slice(0, 3).map((preset) => (
                      <button key={preset} type="button" onClick={() => setActionBeatRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, action: preset } : item))} className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-400 transition hover:border-slate-500 hover:text-white">{preset}</button>
                    ))}
                  </div>
                </div>
                <div className="space-y-1">
                  <input value={String(row.duration ?? '')} onChange={(event) => setActionBeatRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, duration: event.target.value } : item))} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 outline-none transition focus:border-amber-500" placeholder="时长" />
                  <div className="flex flex-wrap gap-1">
                    {DURATION_PRESETS.slice(0, 3).map((preset) => (
                      <button key={preset} type="button" onClick={() => setActionBeatRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, duration: preset } : item))} className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-400 transition hover:border-slate-500 hover:text-white">{preset}</button>
                    ))}
                  </div>
                </div>
                <button type="button" onClick={() => setActionBeatRows((current) => moveRow(current, index, index - 1))} disabled={index === 0} className={`rounded-lg border px-3 py-2 text-xs transition ${index === 0 ? 'cursor-not-allowed border-slate-800 text-slate-600' : 'border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white'}`}>上移</button>
                <button type="button" onClick={() => setActionBeatRows((current) => moveRow(current, index, index + 1))} disabled={index === actionBeatRows.length - 1} className={`rounded-lg border px-3 py-2 text-xs transition ${index === actionBeatRows.length - 1 ? 'cursor-not-allowed border-slate-800 text-slate-600' : 'border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white'}`}>下移</button>
                <button type="button" onClick={() => setActionBeatRows((current) => current.filter((_, itemIndex) => itemIndex !== index))} className="rounded-lg border border-rose-800/60 px-3 py-2 text-xs text-rose-300 transition hover:border-rose-600 hover:text-white">删除</button>
              </div>
            ))}
          </div>
        </div>
        <details className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
          <summary className="cursor-pointer text-[12px] text-slate-400">高级 JSON</summary>
          <div className="mt-3 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" onClick={syncFormToJson} className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white">用表单回填 JSON</button>
              <button type="button" onClick={syncJsonToForm} className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white">从 JSON 覆盖表单</button>
              <span className={`text-xs ${jsonState === 'error' ? 'text-red-400' : jsonState === 'synced' ? 'text-emerald-400' : 'text-slate-500'}`}>
                {jsonState === 'error' ? 'JSON 解析失败，请先修正格式' : jsonState === 'synced' ? '表单与 JSON 已同步' : '保留底层 JSON 兼容旧数据结构'}
              </span>
            </div>
            <label className="block">
              <div className="mb-1 text-[12px] text-slate-400">角色站位 JSON</div>
              <textarea
                value={characterBlockingText}
                onChange={(event) => {
                  setCharacterBlockingText(event.target.value)
                  setJsonState('idle')
                }}
                rows={8}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-200 outline-none transition focus:border-amber-500"
              />
            </label>
            <label className="block">
              <div className="mb-1 text-[12px] text-slate-400">动作节拍 JSON</div>
              <textarea
                value={actionBeatsText}
                onChange={(event) => {
                  setActionBeatsText(event.target.value)
                  setJsonState('idle')
                }}
                rows={8}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-200 outline-none transition focus:border-amber-500"
              />
            </label>
          </div>
        </details>
        <div className="flex items-center gap-3">
          <button
            onClick={async () => {
              setSaveState('saving')
              try {
                syncFormToJson()
                await onSave(shot.episode, shot.shot_id, {
                  duration: Math.max(1, Number.isFinite(duration) ? duration : 3),
                  cameraAngle,
                  cameraMovement,
                  transition,
                  sceneAssetId,
                  characterAssetIds: characterAssetIds.split(',').map((item: string) => item.trim()).filter(Boolean),
                  propAssetIds: propAssetIds.split(',').map((item: string) => item.trim()).filter(Boolean),
                  styleKey,
                  characterBlocking: characterBlockingRows,
                  actionBeats: actionBeatRows,
                })
                setSaveState('saved')
              } catch {
                setSaveState('error')
              }
            }}
            className="rounded-lg bg-amber-600 px-4 py-2 text-xs font-semibold text-slate-950 transition hover:bg-amber-500"
          >
            {saveState === 'saving' ? '保存中...' : '保存结构化镜头'}
          </button>
          <span className={`text-xs ${
            saveState === 'saved'
              ? 'text-emerald-400'
              : saveState === 'error'
                ? 'text-red-400'
                : 'text-slate-500'
          }`}>
            {saveState === 'saved' ? '已保存' : saveState === 'error' ? 'JSON 或请求失败' : '旧字段会保留，结构化数据写入 meta_info'}
          </span>
        </div>
      </div>
    </details>
  )
}

function ShotDetailWorkbench({
  shot,
  previousShot,
  nextShot,
  getChecklist,
  onSelectShot,
  onSaveStructure,
  onCompilePrompt,
  onLoadHistory,
  onGenerateFrame,
  onGenerateVideo,
  onRecoverFrameTask,
  onRecoverVideoTask,
  initialRecoverFrameTaskId,
  initialRecoverVideoTaskId,
  frameRecoveryMeta,
  videoRecoveryMeta,
  isAutoRecoveringFrame,
  isAutoRecoveringVideo,
  onToggleLock,
  onSaveAcceptance,
  onRecompileAfterFeedback,
}: {
  shot: any
  previousShot: any
  nextShot: any
  getChecklist: (shot: any) => {
    missing: string[]
    promptReady: boolean
    frameReady: boolean
    videoReady: boolean
    lockedReferenceReady: boolean
    selectedReferenceReady: boolean
    structureReady: boolean
  }
  onSelectShot: (shot: any) => void
  onSaveStructure: (
    episode: number,
    shotId: string | number,
    payload: {
      duration: number
      cameraAngle: string
      cameraMovement: string
      transition: string
      sceneAssetId: string
      characterAssetIds: string[]
      propAssetIds: string[]
      styleKey: string
      characterBlocking: Array<Record<string, string>>
      actionBeats: Array<Record<string, string | number>>
    },
  ) => Promise<void>
  onCompilePrompt: (shot: any, compileReason: string) => Promise<void>
  onLoadHistory: (shot: any) => Promise<{ versions: Array<Record<string, unknown>> }>
  onGenerateFrame: (shot: any) => Promise<void>
  onGenerateVideo: (shot: any) => Promise<void>
  onRecoverFrameTask: (taskId: string) => Promise<{ taskId: string; stillRunning: boolean }>
  onRecoverVideoTask: (taskId: string) => Promise<{ taskId: string; stillRunning: boolean }>
  initialRecoverFrameTaskId?: string | null
  initialRecoverVideoTaskId?: string | null
  frameRecoveryMeta?: VisualReferenceRecoveryMeta | null
  videoRecoveryMeta?: VisualReferenceRecoveryMeta | null
  isAutoRecoveringFrame?: boolean
  isAutoRecoveringVideo?: boolean
  onToggleLock: (shot: any, locked: boolean) => Promise<void>
  onSaveAcceptance: (shot: any, payload: { assetKind: string; assetId: string; status: string; failureTags: string[]; notes: string }) => Promise<void>
  onRecompileAfterFeedback: (shot: any) => Promise<void>
}) {
  if (!shot) {
    return (
      <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
        选择左侧镜头后，这里会直接显示结构化镜头、提示词编译器、生成首帧/视频和验收反馈。
      </div>
    )
  }

  const checklist = getChecklist(shot)
  const activeMakeupVariants = buildActiveMakeupVariants(shot)

  return (
    <div className="xl:sticky xl:top-4">
      <div className="rounded-xl border border-slate-800 bg-[#0c1222] p-3 text-[14px] text-[#94a3b8] space-y-1.5">
        <div className="flex items-center justify-between gap-3 border-b border-slate-800 pb-3">
          <div>
            <div className="text-sm font-semibold text-slate-100">镜号 {shot.shot_id} · {shot.scene_name || '未命名场景'}</div>
            <div className="mt-1 text-xs text-slate-400">当前选中镜头，可直接继续结构化编辑与生成。</div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={!previousShot}
              onClick={() => previousShot && onSelectShot(previousShot)}
              className={`rounded-lg border px-3 py-1 text-xs transition ${
                previousShot
                  ? 'border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white'
                  : 'cursor-not-allowed border-slate-800 text-slate-600'
              }`}
            >
              上一镜
            </button>
            <button
              type="button"
              disabled={!nextShot}
              onClick={() => nextShot && onSelectShot(nextShot)}
              className={`rounded-lg border px-3 py-1 text-xs transition ${
                nextShot
                  ? 'border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white'
                  : 'cursor-not-allowed border-slate-800 text-slate-600'
              }`}
            >
              下一镜
            </button>
            <div className="rounded-full border border-sky-700/50 bg-sky-950/40 px-3 py-1 text-xs text-sky-200">
              缺失 {checklist.missing.length}
            </div>
          </div>
        </div>

        <ShotChecklistCard shot={shot} getChecklist={getChecklist} />
        <div className="grid grid-cols-2 gap-2">
          <div><span className="text-[#64748b]">场景：</span>{shot.scene_name}</div>
          <div><span className="text-[#64748b]">镜头：</span>{shot.camera_angle} · {shot.camera_movement} · 过渡: {shot.transition} · {shot.duration}s</div>
          <div><span className="text-[#64748b]">光影：</span>{shot.lighting || '-'}</div>
          <div><span className="text-[#64748b]">BGM：</span>{shot.bgm_mood || '-'}</div>
          <div><span className="text-[#64748b]">音效：</span>{Array.isArray(shot.sound_effects) ? shot.sound_effects.join(', ') : shot.sound_effects || '-'}</div>
        </div>
        <div><span className="text-[#64748b]">起始：</span>{shot.start_state || '-'}</div>
        <div><span className="text-[#64748b]">过程：</span>{shot.action_process || '-'}</div>
        <div><span className="text-[#64748b]">结束：</span>{shot.end_state || '-'}</div>

        <ShotReferenceSummaryCard shot={shot} />
        <StoryboardStructureEditor shot={shot} onSave={onSaveStructure} />
        <PromptCompilerCard
          shot={shot}
          onCompile={(compileReason) => onCompilePrompt(shot, compileReason)}
          onLoadHistory={() => onLoadHistory(shot)}
          onGenerateFrame={() => onGenerateFrame(shot)}
          onGenerateVideo={() => onGenerateVideo(shot)}
          onRecoverFrameTask={onRecoverFrameTask}
          onRecoverVideoTask={onRecoverVideoTask}
          initialRecoverFrameTaskId={initialRecoverFrameTaskId}
          initialRecoverVideoTaskId={initialRecoverVideoTaskId}
          frameRecoveryMeta={frameRecoveryMeta}
          videoRecoveryMeta={videoRecoveryMeta}
          isAutoRecoveringFrame={isAutoRecoveringFrame}
          isAutoRecoveringVideo={isAutoRecoveringVideo}
          onToggleLock={(locked) => onToggleLock(shot, locked)}
        />
        <AcceptanceReviewCard
          shot={shot}
          onSave={(payload) => onSaveAcceptance(shot, payload)}
          onRecompile={() => onRecompileAfterFeedback(shot)}
        />

        {activeMakeupVariants.length > 0 && (
          <div className="mt-1 rounded border border-amber-500/30 bg-amber-500/5 p-2 text-[13px] text-amber-100">
            <div className="mb-1 font-medium">当前镜头生效定妆</div>
            <div className="space-y-1">
              {activeMakeupVariants.map((variant: any, variantIndex: number) => (
                <div key={`${variant?.asset_id ?? variant?.character_name ?? 'variant'}-${variantIndex}`} className="rounded border border-slate-800 bg-[#0a0e1a] px-2 py-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-amber-50">{variant?.asset_name || variant?.character_name || '角色'}</span>
                    {variant?.scope_label ? <span className="rounded-full border border-amber-400/40 px-2 py-0.5 text-[11px] text-amber-200">{formatProductionMakeupScopeLabel(variant.scope_label, variant.makeup_scope)}</span> : null}
                    {formatProductionMakeupStageLabel(variant?.stage_name, variant?.makeup_scope) ? <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">{formatProductionMakeupStageLabel(variant.stage_name, variant.makeup_scope)}</span> : null}
                  </div>
                  <div className="mt-1 text-[12px] text-amber-50/90">
                    生效版本：{formatProductionMakeupVersionLabel(variant?.scope_label, variant?.stage_name, variant?.makeup_scope)}
                  </div>
                  <div className="mt-1 text-[12px] text-slate-300">
                    参考图来源：{getActiveMakeupReferenceSourceLabel(variant?.reference_source, variant?.makeup_scope)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {shot.makeup_prompts && shot.makeup_prompts.length > 0 && (
          <div className="mt-1">
            <div className="text-[13px] text-[#e2e8f0] font-medium mb-1">💄 角色定妆</div>
            {shot.makeup_prompts.map((m: any, mi: number) => (
              <details key={mi} className="bg-[#0a0e1a] border border-[#1e293b] rounded p-2 mb-1 text-[14px]">
                <summary className="text-[13px] text-rose-300 cursor-pointer font-medium">{m.character_name}</summary>
                <div className="mt-1 text-[#94a3b8] space-y-0.5">
                  <div className="flex flex-wrap items-center gap-2 pb-1">
                    {m.scope_label ? <span className={`rounded-full border px-2 py-0.5 text-[11px] ${getMakeupScopeTone(m.makeup_scope)}`}>{formatProductionMakeupScopeLabel(m.scope_label, m.makeup_scope)}</span> : null}
                    {formatProductionMakeupStageLabel(m.stage_name, m.makeup_scope) ? <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">{formatProductionMakeupStageLabel(m.stage_name, m.makeup_scope)}</span> : null}
                  </div>
                  <div><span className="text-[#64748b]">穿着：</span>{m.refined_outfit || '-'}</div>
                  <div><span className="text-[#64748b]">配饰：</span>{m.refined_accessories || '-'}</div>
                  <div><span className="text-[#64748b]">妆容：</span>{m.makeup_spec || '-'}</div>
                  <div><span className="text-[#64748b]">发型：</span>{m.hair_style || '-'}</div>
                  {m.visual_prompt_zh && (
                    <details className="mt-0.5">
                      <summary className="text-[13px] text-rose-400 cursor-pointer">✨ 定妆提示词</summary>
                      <div className="text-[14px] text-[#cbd5e1] bg-[#080c16] rounded p-2 mt-1 font-mono whitespace-pre-wrap">{m.visual_prompt_zh}</div>
                    </details>
                  )}
                </div>
              </details>
            ))}
          </div>
        )}

        {shot.scene_prompt && (
          <details className="mt-1">
            <summary className="text-[13px] text-emerald-400 cursor-pointer">🏠 场景提示词</summary>
            <div className="text-[14px] text-[#cbd5e1] bg-[#0a0e1a] rounded p-2 mt-1 font-mono whitespace-pre-wrap">{shot.scene_prompt}</div>
          </details>
        )}

        <div className="mt-1">
          <div className="flex gap-2">
            <details className="flex-1">
              <summary className="text-[13px] text-blue-400 cursor-pointer">✨ 静态提示词</summary>
              <div className="text-[14px] text-[#cbd5e1] bg-[#0a0e1a] rounded p-2 mt-1 font-mono whitespace-pre-wrap">{shot.visual_prompt_static || '-'}</div>
            </details>
            <details className="flex-1">
              <summary className="text-[13px] text-purple-400 cursor-pointer">✨ 运动提示词</summary>
              <div className="text-[14px] text-[#cbd5e1] bg-[#0a0e1a] rounded p-2 mt-1 font-mono whitespace-pre-wrap">{shot.visual_prompt_motion || '-'}</div>
            </details>
          </div>
        </div>
      </div>
    </div>
  )
}

function PromptCompilerCard({
  shot,
  onCompile,
  onLoadHistory,
  onGenerateFrame,
  onGenerateVideo,
  onRecoverFrameTask,
  onRecoverVideoTask,
  initialRecoverFrameTaskId,
  initialRecoverVideoTaskId,
  frameRecoveryMeta,
  videoRecoveryMeta,
  isAutoRecoveringFrame,
  isAutoRecoveringVideo,
  onToggleLock,
}: {
  shot: any
  onCompile: (compileReason: string) => Promise<void>
  onLoadHistory: () => Promise<{ versions: Array<Record<string, unknown>> }>
  onGenerateFrame: () => Promise<void>
  onGenerateVideo: () => Promise<void>
  onRecoverFrameTask: (taskId: string) => Promise<{ taskId: string; stillRunning: boolean }>
  onRecoverVideoTask: (taskId: string) => Promise<{ taskId: string; stillRunning: boolean }>
  initialRecoverFrameTaskId?: string | null
  initialRecoverVideoTaskId?: string | null
  frameRecoveryMeta?: VisualReferenceRecoveryMeta | null
  videoRecoveryMeta?: VisualReferenceRecoveryMeta | null
  isAutoRecoveringFrame?: boolean
  isAutoRecoveringVideo?: boolean
  onToggleLock: (locked: boolean) => Promise<void>
}) {
  const [compileReason, setCompileReason] = useState('manual')
  const [compileState, setCompileState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [historyState, setHistoryState] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle')
  const [generationState, setGenerationState] = useState<'idle' | 'frame' | 'video' | 'saved' | 'error'>('idle')
  const [generationMessage, setGenerationMessage] = useState('')
  const [recoverFrameTaskId, setRecoverFrameTaskId] = useState<string | null>(null)
  const [recoverVideoTaskId, setRecoverVideoTaskId] = useState<string | null>(null)
  const [lockState, setLockState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [versions, setVersions] = useState<Array<Record<string, unknown>>>([])
  const hasAdoptedFrame = Array.isArray(shot.assets?.images) && shot.assets.images.some((asset: any) => asset?.adopted)
  const imageCount = Array.isArray(shot.assets?.images) ? shot.assets.images.length : 0
  const videoCount = Array.isArray(shot.assets?.videos) ? shot.assets.videos.length : 0
  const referenceItems = getShotReferenceItems(shot)
  const compilerDiagnostics = shot.compiler_diagnostics ?? {}
  const compilerWarnings = Array.isArray(shot.compiler_warnings) ? shot.compiler_warnings : []
  const usedAssets = Array.isArray(shot.used_assets) ? shot.used_assets : []
  const promptCompileContext = shot.prompt_compile_context ?? {}
  const diagnosticChecks = Array.isArray(compilerDiagnostics?.checks) ? compilerDiagnostics.checks : []
  const diagnosticMetrics = compilerDiagnostics?.metrics && typeof compilerDiagnostics.metrics === 'object' ? compilerDiagnostics.metrics : {}
  const diagnosticMeta = getCompilerDiagnosticMeta(compilerDiagnostics?.status)
  const frameRecoveryStatus = frameRecoveryMeta?.status ?? null
  const videoRecoveryStatus = videoRecoveryMeta?.status ?? null

  useEffect(() => {
    setRecoverFrameTaskId(initialRecoverFrameTaskId ?? null)
  }, [initialRecoverFrameTaskId, shot?.episode, shot?.shot_id])

  useEffect(() => {
    setRecoverVideoTaskId(initialRecoverVideoTaskId ?? null)
  }, [initialRecoverVideoTaskId, shot?.episode, shot?.shot_id])

  return (
    <details className="mt-2 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      <summary className="cursor-pointer text-[13px] text-sky-300">提示词编译器</summary>
      <div className="mt-3 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <input
            value={compileReason}
            onChange={(event) => setCompileReason(event.target.value)}
            className="min-w-[220px] rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-sky-500"
            placeholder="manual / after-feedback"
          />
          <button
            onClick={async () => {
              setCompileState('saving')
              try {
                await onCompile(compileReason)
                setCompileState('saved')
              } catch {
                setCompileState('error')
              }
            }}
            className="rounded-lg bg-sky-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-sky-500"
          >
            {compileState === 'saving' ? '编译中...' : '重新编译'}
          </button>
          <span className="text-xs text-slate-400">
            当前版本：{shot.prompt_version ?? '-'}
          </span>
          <button
            onClick={async () => {
              setLockState('saving')
              try {
                await onToggleLock(!shot.prompt_locked)
                setLockState('saved')
              } catch {
                setLockState('error')
              }
            }}
            className={`rounded-full border px-3 py-1 text-xs transition ${
              shot.prompt_locked
                ? 'border-amber-500/70 text-amber-200 hover:border-amber-400 hover:text-white'
                : 'border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white'
            }`}
          >
            {shot.prompt_locked ? '已锁定提示词' : '锁定当前版本'}
          </button>
          <span className={`text-xs ${
            compileState === 'saved'
              ? 'text-emerald-400'
              : compileState === 'error'
                ? 'text-red-400'
                : 'text-slate-500'
          }`}>
            {compileState === 'saved' ? '已更新静态/运动/负向提示词' : compileState === 'error' ? '编译失败' : '保留现有生成链兼容字段'}
          </span>
          <span className={`text-xs ${
            lockState === 'saved'
              ? 'text-emerald-400'
              : lockState === 'error'
                ? 'text-red-400'
                : 'text-slate-500'
          }`}>
            {lockState === 'saved' ? (shot.prompt_locked ? '已解除锁定' : '已锁定当前提示词版本') : lockState === 'error' ? '锁定操作失败' : '批量编译会默认跳过已锁定镜头'}
          </span>
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">编译诊断</div>
            <span className={`rounded-full border px-2.5 py-0.5 text-[11px] ${diagnosticMeta.tone}`}>{diagnosticMeta.label}</span>
          </div>
          {diagnosticChecks.length > 0 ? (
            <div className="mt-3 space-y-2">
              {diagnosticChecks.map((check: any, index: number) => (
                <div key={`${String(check?.key || 'check')}-${index}`} className="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded-full border px-2 py-0.5 ${check?.passed ? 'border-emerald-800/80 bg-emerald-950/30 text-emerald-200' : 'border-amber-800/80 bg-amber-950/30 text-amber-200'}`}>
                      {check?.passed ? '通过' : '待处理'}
                    </span>
                    <span className="text-slate-200">{String(check?.message || check?.key || '未命名检查')}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-3 text-xs text-slate-500">先编译一次提示词，这里会显示当前镜头是否适合直接进入生产。</div>
          )}
          {compilerWarnings.length > 0 ? (
            <div className="mt-3 rounded-lg border border-amber-800/70 bg-amber-950/20 px-3 py-2 text-xs text-amber-200">
              {compilerWarnings.map((warning: string, index: number) => (
                <div key={`${warning}-${index}`}>• {warning}</div>
              ))}
            </div>
          ) : null}
          {Object.keys(diagnosticMetrics).length > 0 ? (
            <div className="mt-3 grid gap-2 md:grid-cols-5">
              {[
                { label: '静态字数', value: diagnosticMetrics.static_chars },
                { label: '运动字数', value: diagnosticMetrics.motion_chars },
                { label: '使用资产', value: diagnosticMetrics.used_asset_count },
                { label: '警告数', value: diagnosticMetrics.warning_count },
                { label: '阻塞数', value: diagnosticMetrics.blocking_count },
              ].map((item) => (
                <div key={item.label} className="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-xs text-slate-300">
                  <div className="text-[10px] uppercase tracking-[0.16em] text-slate-500">{item.label}</div>
                  <div className="mt-1 text-sm text-slate-100">{String(item.value ?? 0)}</div>
                </div>
              ))}
            </div>
          ) : null}
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">编译输入参考</div>
            <span className="rounded-full border border-slate-800 bg-slate-950 px-2 py-0.5 text-[11px] text-slate-300">{referenceItems.length} 项</span>
          </div>
          {referenceItems.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-2">
              {referenceItems.map((item: any, index: number) => {
                const meta = getReferenceStatusMeta(item?.status)
                const label = item?.token ? `${item.subject || item.title}: ${item.token}` : String(item?.subject || item?.title || '未命名参考')
                return (
                  <span key={`${item?.id || item?.scope || 'ref'}-${index}`} className={`rounded-full border px-2.5 py-1 text-[11px] ${meta.tone}`}>
                    {label}
                  </span>
                )
              })}
            </div>
          ) : (
            <div className="mt-2 text-xs text-slate-500">没有可注入的参考图，当前编译将只基于结构化镜头字段输出。</div>
          )}
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">使用资产</div>
            <span className="rounded-full border border-slate-800 bg-slate-950 px-2 py-0.5 text-[11px] text-slate-300">{usedAssets.length} 项</span>
          </div>
          {usedAssets.length > 0 ? (
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              {usedAssets.map((asset: any) => (
                <div key={`${asset.asset_type}-${asset.asset_id}`} className="rounded-lg border border-slate-800 bg-slate-950/70 p-3 text-xs text-slate-300">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full border border-slate-800 bg-slate-950 px-2 py-0.5 text-[11px] text-slate-400">
                      {asset.asset_type === 'scene' ? '场景' : asset.asset_type === 'character' ? '角色' : '道具'}
                    </span>
                    <span className={`rounded-full border px-2 py-0.5 text-[11px] ${asset.locked_reference ? 'border-emerald-800/80 bg-emerald-950/30 text-emerald-200' : asset.has_reference ? 'border-sky-800/80 bg-sky-950/30 text-sky-200' : 'border-amber-800/80 bg-amber-950/30 text-amber-200'}`}>
                      {asset.locked_reference ? '已锁定参考图' : asset.has_reference ? '已有参考图' : '缺参考图'}
                    </span>
                  </div>
                  <div className="mt-2 text-sm text-slate-100">{String(asset.asset_name || asset.asset_id || '未命名资产')}</div>
                  <div className="mt-1 text-[11px] text-slate-500">状态：{String(asset.asset_status || 'draft')} / 参考图 {String(asset.reference_total ?? 0)} 张</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-3 text-xs text-slate-500">当前镜头还没有被编译器识别出的结构化资产。</div>
          )}
        </div>

        <div className="grid gap-2 md:grid-cols-2">
          <details>
            <summary className="cursor-pointer text-[12px] text-slate-400">首帧提示词</summary>
            <div className="mt-2 rounded bg-slate-950 p-2 font-mono text-xs text-slate-300 whitespace-pre-wrap">
              {shot.visual_prompt_static || '-'}
            </div>
          </details>
          <details>
            <summary className="cursor-pointer text-[12px] text-slate-400">运动提示词</summary>
            <div className="mt-2 rounded bg-slate-950 p-2 font-mono text-xs text-slate-300 whitespace-pre-wrap">
              {shot.visual_prompt_motion || '-'}
            </div>
          </details>
        </div>

        <details>
          <summary className="cursor-pointer text-[12px] text-slate-400">负向提示词</summary>
          <div className="mt-2 rounded bg-slate-950 p-2 font-mono text-xs text-slate-300 whitespace-pre-wrap">
            {shot.negative_prompt || shot.visual_prompt_final || '-'}
          </div>
        </details>

        <details>
          <summary className="cursor-pointer text-[12px] text-slate-400">编译上下文</summary>
          <div className="mt-2 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => { void navigator.clipboard.writeText(stringifyDebugJson(promptCompileContext)) }}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-[11px] text-slate-300 transition hover:border-slate-500 hover:text-white"
              >
                复制上下文
              </button>
              <span className="text-[11px] text-slate-500">用于调试编译输入，不会影响普通生产操作。</span>
            </div>
            <div className="rounded bg-slate-950 p-2 font-mono text-xs text-slate-300 whitespace-pre-wrap">
              {stringifyDebugJson(promptCompileContext)}
            </div>
          </div>
        </details>

        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={async () => {
              setGenerationState('frame')
              setGenerationMessage('正在提交首帧任务。通常需要 30-180 秒，请不要重复点击；如果稍后出现可恢复提示，再继续拉取结果。')
              setRecoverFrameTaskId(null)
              try {
                await onGenerateFrame()
                setGenerationState('saved')
                setGenerationMessage('首帧已写回分镜结果并默认采用最新版本。')
              } catch (error) {
                setGenerationState('error')
                setGenerationMessage(formatCreativeTaskMessage(error instanceof Error ? error.message : '', '首帧生成失败'))
                setRecoverFrameTaskId(deriveRecoverTaskIdFromError(error))
              }
            }}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-emerald-500"
          >
            {generationState === 'frame' ? '生成首帧中...' : '生成首帧'}
          </button>
          {recoverFrameTaskId ? (
            <button
              type="button"
              disabled={generationState === 'frame' || Boolean(isAutoRecoveringFrame)}
              onClick={async () => {
                setGenerationState('frame')
                setGenerationMessage('正在继续拉取首帧结果，请稍等。')
                try {
                  const result = await onRecoverFrameTask(recoverFrameTaskId)
                  if (result.stillRunning) {
                    setGenerationState('error')
                    setGenerationMessage('首帧任务还在 provider 侧执行，参考图已记住。稍后可以继续拉取结果，不需要重新新建任务。')
                    setRecoverFrameTaskId(result.taskId)
                    return
                  }
                  setGenerationState('saved')
                  setGenerationMessage('首帧结果已成功回收并写回当前镜头。')
                  setRecoverFrameTaskId(null)
                } catch (error) {
                  setGenerationState('error')
                  setGenerationMessage(formatCreativeTaskMessage(error instanceof Error ? error.message : '', '首帧回收失败'))
                }
              }}
              className={`rounded-lg border px-3 py-2 text-xs transition ${
                generationState === 'frame' || isAutoRecoveringFrame
                  ? 'cursor-not-allowed border-slate-800 bg-slate-900 text-slate-500'
                  : 'border-amber-700/70 bg-amber-950/20 text-amber-200 hover:border-amber-500 hover:text-amber-100'
              }`}
            >
              {isAutoRecoveringFrame ? '首帧自动回收中...' : '继续拉取首帧结果'}
            </button>
          ) : null}
          <button
            disabled={!hasAdoptedFrame || generationState === 'frame'}
            onClick={async () => {
              setGenerationState('video')
              setGenerationMessage('正在提交视频任务。通常需要 30-180 秒，请不要重复点击；如果稍后出现可恢复提示，再继续拉取结果。')
              setRecoverVideoTaskId(null)
              try {
                await onGenerateVideo()
                setGenerationState('saved')
                setGenerationMessage('视频已写回分镜结果并默认采用最新版本。')
              } catch (error) {
                setGenerationState('error')
                setGenerationMessage(formatCreativeTaskMessage(error instanceof Error ? error.message : '', '视频生成失败'))
                setRecoverVideoTaskId(deriveRecoverTaskIdFromError(error))
              }
            }}
            className={`rounded-lg px-4 py-2 text-xs font-semibold transition ${
              !hasAdoptedFrame || generationState === 'frame'
                ? 'cursor-not-allowed border border-slate-800 bg-slate-900 text-slate-500'
                : 'bg-fuchsia-600 text-white hover:bg-fuchsia-500'
            }`}
          >
            {generationState === 'video' ? '生成视频中...' : '生成视频'}
          </button>
          {recoverVideoTaskId ? (
            <button
              type="button"
              disabled={generationState === 'video' || Boolean(isAutoRecoveringVideo)}
              onClick={async () => {
                setGenerationState('video')
                setGenerationMessage('正在继续拉取视频结果，请稍等。')
                try {
                  const result = await onRecoverVideoTask(recoverVideoTaskId)
                  if (result.stillRunning) {
                    setGenerationState('error')
                    setGenerationMessage('视频任务还在 provider 侧执行，系统会保留任务号。稍后继续拉取结果即可，不需要重复发起生成。')
                    setRecoverVideoTaskId(result.taskId)
                    return
                  }
                  setGenerationState('saved')
                  setGenerationMessage('视频结果已成功回收并写回当前镜头。')
                  setRecoverVideoTaskId(null)
                } catch (error) {
                  setGenerationState('error')
                  setGenerationMessage(formatCreativeTaskMessage(error instanceof Error ? error.message : '', '视频回收失败'))
                }
              }}
              className={`rounded-lg border px-3 py-2 text-xs transition ${
                generationState === 'video' || isAutoRecoveringVideo
                  ? 'cursor-not-allowed border-slate-800 bg-slate-900 text-slate-500'
                  : 'border-amber-700/70 bg-amber-950/20 text-amber-200 hover:border-amber-500 hover:text-amber-100'
              }`}
            >
              {isAutoRecoveringVideo ? '视频自动回收中...' : '继续拉取视频结果'}
            </button>
          ) : null}
          <span className="text-xs text-slate-500">
            首帧 {imageCount} / 视频 {videoCount} / 状态 {shot.asset_status || 'pending'}
          </span>
          <span className={`text-xs ${
            generationState === 'saved'
              ? 'text-emerald-400'
              : generationState === 'error'
                ? 'text-red-400'
                : 'text-slate-500'
          }`}>
            {generationState === 'saved'
              ? generationMessage || '已写回分镜结果并默认采用最新版本'
                : generationState === 'error'
                  ? generationMessage || '生成失败或当前条件不足'
                  : hasAdoptedFrame
                  ? '视频会基于已采用首帧继续生成'
                  : '请先生成并采用一张首帧图'}
          </span>
        </div>
        {(recoverFrameTaskId || recoverVideoTaskId || frameRecoveryStatus || videoRecoveryStatus) ? (
          <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-xs text-slate-300">
            <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">长任务恢复状态</div>
            <div className="mt-2 grid gap-2 md:grid-cols-2">
              <div className="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-slate-100">首帧</span>
                  {frameRecoveryStatus ? (
                    <span className={`rounded-full border px-2 py-0.5 ${
                      frameRecoveryStatus === 'recovered'
                        ? 'border-emerald-800/80 bg-emerald-950/30 text-emerald-200'
                        : frameRecoveryStatus === 'failed'
                          ? 'border-rose-800/80 bg-rose-950/30 text-rose-200'
                          : 'border-amber-800/80 bg-amber-950/30 text-amber-200'
                    }`}>
                      {frameRecoveryStatus === 'recovered' ? '已回收' : frameRecoveryStatus === 'failed' ? '回收异常' : frameRecoveryStatus === 'waiting-provider' ? '等待 Provider' : '自动回收中'}
                    </span>
                  ) : null}
                </div>
                <div className="mt-1 text-slate-400">
                  {recoverFrameTaskId ? `任务号：${recoverFrameTaskId}` : '当前没有待恢复的首帧任务。'}
                </div>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-slate-100">视频</span>
                  {videoRecoveryStatus ? (
                    <span className={`rounded-full border px-2 py-0.5 ${
                      videoRecoveryStatus === 'recovered'
                        ? 'border-emerald-800/80 bg-emerald-950/30 text-emerald-200'
                        : videoRecoveryStatus === 'failed'
                          ? 'border-rose-800/80 bg-rose-950/30 text-rose-200'
                          : 'border-amber-800/80 bg-amber-950/30 text-amber-200'
                    }`}>
                      {videoRecoveryStatus === 'recovered' ? '已回收' : videoRecoveryStatus === 'failed' ? '回收异常' : videoRecoveryStatus === 'waiting-provider' ? '等待 Provider' : '自动回收中'}
                    </span>
                  ) : null}
                </div>
                <div className="mt-1 text-slate-400">
                  {recoverVideoTaskId ? `任务号：${recoverVideoTaskId}` : '当前没有待恢复的视频任务。'}
                </div>
              </div>
            </div>
          </div>
        ) : null}

        <div className="flex items-center gap-3">
          <button
            onClick={async () => {
              setHistoryState('loading')
              try {
                const payload = await onLoadHistory()
                setVersions(payload.versions ?? [])
                setHistoryState('loaded')
              } catch {
                setHistoryState('error')
              }
            }}
            className="rounded-lg border border-slate-700 px-4 py-2 text-xs text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            {historyState === 'loading' ? '加载中...' : '查看历史版本'}
          </button>
          <span className={`text-xs ${
            historyState === 'error' ? 'text-red-400' : 'text-slate-500'
          }`}>
            {historyState === 'loaded' ? `${versions.length} 个版本` : historyState === 'error' ? '历史加载失败' : '版本会记录编译原因'}
          </span>
        </div>

        {versions.length > 0 ? (
          <div className="space-y-2">
            {versions.map((version) => (
              <details key={String(version.id)} className="rounded border border-slate-800 bg-slate-950/70 p-2">
                <summary className="cursor-pointer text-xs text-slate-300">
                  v{String(version.version)} · {String(version.compile_reason || 'manual')}
                </summary>
                <div className="mt-2 space-y-2">
                  {Array.isArray((version as any)?.locked_reference_summary?.all) && (version as any).locked_reference_summary.all.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {(version as any).locked_reference_summary.all.map((item: any, index: number) => {
                        const meta = getReferenceStatusMeta(item?.status)
                        const label = item?.token ? `${item.subject || item.title}: ${item.token}` : String(item?.subject || item?.title || '未命名参考')
                        return (
                          <span key={`${item?.id || item?.scope || 'ref'}-${index}`} className={`rounded-full border px-2 py-1 text-[11px] ${meta.tone}`}>
                            {label}
                          </span>
                        )
                      })}
                    </div>
                  ) : null}
                  {(version as any)?.compiler_diagnostics ? (
                    <div className="rounded border border-slate-800 bg-slate-950/70 p-2 text-xs text-slate-300">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`rounded-full border px-2 py-0.5 text-[11px] ${getCompilerDiagnosticMeta((version as any).compiler_diagnostics?.status).tone}`}>
                          {getCompilerDiagnosticMeta((version as any).compiler_diagnostics?.status).label}
                        </span>
                        <span>{Array.isArray((version as any).compiler_diagnostics?.warnings) ? (version as any).compiler_diagnostics.warnings.length : 0} 条 warning</span>
                      </div>
                    </div>
                  ) : null}
                  <div className="rounded bg-slate-950 p-2 font-mono text-xs text-slate-300 whitespace-pre-wrap">{String(version.prompt_static || '-')}</div>
                  <div className="rounded bg-slate-950 p-2 font-mono text-xs text-slate-300 whitespace-pre-wrap">{String(version.prompt_motion || '-')}</div>
                  <div className="rounded bg-slate-950 p-2 font-mono text-xs text-slate-300 whitespace-pre-wrap">{String(version.negative_prompt || '-')}</div>
                  {(version as any)?.prompt_compile_context ? (
                    <details>
                      <summary className="cursor-pointer text-[11px] text-slate-400">查看当时的编译上下文</summary>
                      <div className="mt-2 rounded bg-slate-950 p-2 font-mono text-xs text-slate-300 whitespace-pre-wrap">
                        {stringifyDebugJson((version as any).prompt_compile_context)}
                      </div>
                    </details>
                  ) : null}
                </div>
              </details>
            ))}
          </div>
        ) : null}
      </div>
    </details>
  )
}

const ACCEPTANCE_TAG_OPTIONS = [
  { value: 'character_count_error', label: '人物数量错误' },
  { value: 'character_blocking_error', label: '角色站位错误' },
  { value: 'character_inconsistency', label: '角色长相不一致' },
  { value: 'costume_error', label: '服装错误' },
  { value: 'prop_missing', label: '道具缺失' },
  { value: 'scene_error', label: '场景错误' },
  { value: 'mood_error', label: '氛围不对' },
  { value: 'composition_error', label: '构图不好' },
  { value: 'hand_error', label: '手部错误' },
  { value: 'new_character_added', label: '新增人物' },
  { value: 'subtitle_watermark_logo', label: '字幕/水印/logo' },
  { value: 'needs_retry', label: '需要重试' },
]

function AcceptanceReviewCard({
  shot,
  onSave,
  onRecompile,
}: {
  shot: any
  onSave: (payload: { assetKind: string; assetId: string; status: string; failureTags: string[]; notes: string }) => Promise<void>
  onRecompile: () => Promise<void>
}) {
  const latestImage = Array.isArray(shot.assets?.images) ? [...shot.assets.images].reverse().find((item: any) => item?.id) : null
  const latestVideo = Array.isArray(shot.assets?.videos) ? [...shot.assets.videos].reverse().find((item: any) => item?.id) : null
  const [assetKind, setAssetKind] = useState(shot.acceptance?.asset_kind || (latestVideo ? 'video' : 'image'))
  const [status, setStatus] = useState(shot.acceptance?.status || 'retrying')
  const [notes, setNotes] = useState(shot.acceptance?.notes || '')
  const [selectedTags, setSelectedTags] = useState<string[]>(Array.isArray(shot.acceptance?.failure_tags) ? shot.acceptance.failure_tags : [])
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [recompileState, setRecompileState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const assetId = assetKind === 'video' ? (latestVideo?.id || '') : (latestImage?.id || '')

  useEffect(() => {
    setAssetKind(shot.acceptance?.asset_kind || (latestVideo ? 'video' : 'image'))
    setStatus(shot.acceptance?.status || 'retrying')
    setNotes(shot.acceptance?.notes || '')
    setSelectedTags(Array.isArray(shot.acceptance?.failure_tags) ? shot.acceptance.failure_tags : [])
  }, [shot.acceptance, latestImage?.id, latestVideo?.id])

  const toggleTag = (value: string) => {
    setSelectedTags((current) => (current.includes(value) ? current.filter((item) => item !== value) : [...current, value]))
  }

  return (
    <details className="mt-2 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      <summary className="cursor-pointer text-[13px] text-amber-300">验收反馈</summary>
      <div className="mt-3 space-y-3">
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
          <span>当前状态：{shot.acceptance?.status || 'pending'}</span>
          <span>最近资产：{assetId || '-'}</span>
          <span>最近更新时间：{shot.acceptance?.updated_at || '-'}</span>
        </div>

        <div className="flex flex-wrap gap-3">
          <label className="text-xs text-slate-300">
            结果
            <select value={status} onChange={(event) => setStatus(event.target.value)} className="ml-2 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200">
              <option value="approved">通过</option>
              <option value="failed">失败</option>
              <option value="retrying">重试中</option>
            </select>
          </label>
          <label className="text-xs text-slate-300">
            类型
            <select value={assetKind} onChange={(event) => setAssetKind(event.target.value)} className="ml-2 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200">
              <option value="image">首帧</option>
              <option value="video">视频</option>
            </select>
          </label>
        </div>

        <div className="flex flex-wrap gap-2">
          {ACCEPTANCE_TAG_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => toggleTag(option.value)}
              className={`rounded-full border px-3 py-1 text-xs transition ${
                selectedTags.includes(option.value)
                  ? 'border-amber-500 bg-amber-500/15 text-amber-200'
                  : 'border-slate-700 text-slate-400 hover:border-slate-500 hover:text-white'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>

        <textarea
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          rows={3}
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-amber-500"
          placeholder="补充失败原因或人工备注，下一版编译会吸收这些反馈"
        />

        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={async () => {
              setSaveState('saving')
              try {
                await onSave({ assetKind, assetId, status, failureTags: selectedTags, notes })
                setSaveState('saved')
              } catch {
                setSaveState('error')
              }
            }}
            className="rounded-lg bg-amber-600 px-4 py-2 text-xs font-semibold text-slate-950 transition hover:bg-amber-500"
          >
            {saveState === 'saving' ? '保存中...' : '保存验收'}
          </button>
          <button
            onClick={async () => {
              setRecompileState('saving')
              try {
                await onRecompile()
                setRecompileState('saved')
              } catch {
                setRecompileState('error')
              }
            }}
            className="rounded-lg border border-amber-500/60 px-4 py-2 text-xs font-semibold text-amber-200 transition hover:border-amber-400 hover:text-white"
          >
            {recompileState === 'saving' ? '重编译中...' : '基于反馈重新编译'}
          </button>
          <span className={`text-xs ${
            saveState === 'saved' || recompileState === 'saved'
              ? 'text-emerald-400'
              : saveState === 'error' || recompileState === 'error'
                ? 'text-red-400'
                : 'text-slate-500'
          }`}>
            {saveState === 'saved'
              ? '验收反馈已保存'
              : recompileState === 'saved'
                ? '新版提示词已吸收失败反馈'
                : saveState === 'error' || recompileState === 'error'
                  ? '保存或重编译失败'
                  : '失败标签会自动进入下一版提示词约束'}
          </span>
        </div>
      </div>
    </details>
  )
}

function ShotChecklistCard({
  shot,
  getChecklist,
}: {
  shot: any
  getChecklist: (shot: any) => {
    missing: string[]
    promptReady: boolean
    frameReady: boolean
    videoReady: boolean
    lockedReferenceReady: boolean
    selectedReferenceReady: boolean
    structureReady: boolean
  }
}) {
  const checklist = getChecklist(shot)

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <span className={checklist.promptReady ? 'text-emerald-300' : 'text-amber-300'}>提示词：{checklist.promptReady ? '已编译' : '待补'}</span>
        <span className={checklist.frameReady ? 'text-emerald-300' : 'text-amber-300'}>首帧：{checklist.frameReady ? '已采用' : '待补'}</span>
        <span className={checklist.videoReady ? 'text-emerald-300' : 'text-amber-300'}>视频：{checklist.videoReady ? '已采用' : '待补'}</span>
        <span className={checklist.lockedReferenceReady ? 'text-emerald-300' : 'text-amber-300'}>锁定参考图：{checklist.lockedReferenceReady ? '已齐' : '待锁定'}</span>
        <span className="text-slate-500">资产状态：{shot.asset_status || 'pending'}</span>
      </div>
      <div className="mt-2 text-xs text-slate-400">
        {checklist.missing.length > 0 ? `当前缺失：${checklist.missing.join('、')}` : '当前镜头已具备进入交付链路的基础条件。'}
      </div>
    </div>
  )
}

function EmptyStepCard({
  icon,
  title,
  detail,
  primaryLabel,
  onPrimary,
  secondaryLabel,
  onSecondary,
}: {
  icon: string
  title: string
  detail: string
  primaryLabel: string
  onPrimary: () => void
  secondaryLabel?: string
  onSecondary?: () => void
}) {
  return (
    <div className="rounded-2xl border border-dashed border-[#334155] bg-[#111827] px-6 py-10 text-center">
      <div className="text-3xl mb-3">{icon}</div>
      <div className="text-base font-semibold text-[#e2e8f0]">{title}</div>
      <div className="mt-2 text-sm leading-6 text-[#94a3b8]">{detail}</div>
      <div className="mt-4 flex flex-wrap justify-center gap-3">
        <button onClick={onPrimary} className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-blue-500">
          {primaryLabel}
        </button>
        {secondaryLabel && onSecondary && (
          <button onClick={onSecondary} className="rounded-lg border border-[#334155] px-4 py-2 text-xs text-[#cbd5e1] transition-colors hover:border-[#475569] hover:text-white">
            {secondaryLabel}
          </button>
        )}
      </div>
    </div>
  )
}


