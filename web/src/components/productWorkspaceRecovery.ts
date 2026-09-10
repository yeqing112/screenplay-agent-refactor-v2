export type StoryboardRecoveryKind = 'frame' | 'video' | 'reference' | 'prompt'

export type PendingStoryboardTask = {
  taskId: string
  episode: number
  shotId: string
  kind: StoryboardRecoveryKind
  updatedAt: string
  assetLabel?: string
  assetId?: string
  restartedFromTaskId?: string
  restartCount?: number
  lastRestartedAt?: string
}

export type RecoveryTaskLocalMeta = {
  restartedFromTaskId?: string
  restartCount?: number
  lastRestartedAt?: string
}

export type ShotExecutionSummary = {
  episode: number
  shotId: string
  action: 'compile' | 'frame' | 'video'
  label: string
  generationChain?: string | null
  promptVersion?: number | null
  taskId?: string | null
  updatedAt: string
}

export type ShotRuntimeState = {
  latestExecutionSummary: ShotExecutionSummary | null
  pendingTasks: PendingStoryboardTask[]
}

export type CreativeTaskStatusPayload = {
  created_at?: string
  updated_at?: string
  kind?: string
  task_id?: string
  status?: string
  progress?: number
  target_kind?: string
  book_id?: number
  episode?: number
  shot_id?: string
  provider?: string
  uses_mock?: boolean
  external_task_id?: string | null
  external_status?: string | null
  poll_attempts?: number
  error?: string
  version?: number
  prompt_version?: number | null
  model_profile_id?: string | null
  request_payload?: Record<string, unknown>
  reference_asset_ids?: string[]
  reference_images?: Array<Record<string, unknown>>
  first_frame_asset_id?: string | null
  first_frame_url?: string | null
  provider_task_mode?: string | null
  generation_chain?: string | null
  api_submission?: boolean
  actual_provider_submission?: boolean
  target_model?: string
  submission_mode?: string
  source_export_record_id?: number | null
  has_manual_export_draft?: boolean
  triggered_by_prompt_recompile?: boolean | null
  prompt_recompile_reason?: string | null
  prompt_recompile_task_id?: string | null
  prompt_recompile_version?: number | null
  restarted_from_task_id?: string | null
  restart_count?: number | null
  last_restarted_at?: string | null
}

export type BookCreativeTaskListPayload = {
  tasks?: CreativeTaskStatusPayload[]
}

const PENDING_STORYBOARD_TASKS_KEY_PREFIX = 'product-workspace.pending-storyboard-tasks'
const RECOVERY_TASK_META_KEY_PREFIX = 'product-workspace.recovery-task-meta'
const SHOT_EXECUTION_SUMMARY_KEY_PREFIX = 'product-workspace.shot-execution-summary'

export function getPendingStoryboardTasksStorageKey(bookId: number) {
  return `${PENDING_STORYBOARD_TASKS_KEY_PREFIX}.${bookId}`
}

export function getRecoveryTaskMetaStorageKey(bookId: number) {
  return `${RECOVERY_TASK_META_KEY_PREFIX}.${bookId}`
}

export function getShotExecutionSummaryStorageKey(bookId: number) {
  return `${SHOT_EXECUTION_SUMMARY_KEY_PREFIX}.${bookId}`
}

export function getStoryboardPendingTaskKey(episode: number, shotId: string | number, kind: StoryboardRecoveryKind) {
  return `${episode}:${String(shotId)}:${kind}`
}

export function readPendingStoryboardTasks(bookId: number): PendingStoryboardTask[] {
  if (typeof window === 'undefined' || !window.localStorage) return []
  try {
    const raw = window.localStorage.getItem(getPendingStoryboardTasksStorageKey(bookId))
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item): item is PendingStoryboardTask => (
      item &&
      typeof item === 'object' &&
      typeof item.taskId === 'string' &&
      typeof item.episode === 'number' &&
      typeof item.shotId === 'string' &&
      (item.kind === 'frame' || item.kind === 'video' || item.kind === 'reference' || item.kind === 'prompt')
    ))
  } catch {
    return []
  }
}

export function writePendingStoryboardTasks(bookId: number, tasks: PendingStoryboardTask[]) {
  if (typeof window === 'undefined' || !window.localStorage) return
  if (tasks.length === 0) {
    window.localStorage.removeItem(getPendingStoryboardTasksStorageKey(bookId))
    return
  }
  window.localStorage.setItem(getPendingStoryboardTasksStorageKey(bookId), JSON.stringify(tasks))
}

export function upsertPendingStoryboardTask(bookId: number, task: PendingStoryboardTask) {
  const current = readPendingStoryboardTasks(bookId)
  const next = [
    task,
    ...current.filter(
      (item) =>
        item.taskId !== task.taskId &&
        getStoryboardPendingTaskKey(item.episode, item.shotId, item.kind) !==
          getStoryboardPendingTaskKey(task.episode, task.shotId, task.kind),
    ),
  ]
  writePendingStoryboardTasks(bookId, next)
  return next
}

export function removePendingStoryboardTask(bookId: number, taskId: string) {
  const current = readPendingStoryboardTasks(bookId)
  const next = current.filter((item) => item.taskId !== taskId)
  writePendingStoryboardTasks(bookId, next)
  return next
}

export function findPendingStoryboardTask(
  bookId: number,
  episode: number,
  shotId: string,
  kind: StoryboardRecoveryKind,
) {
  return readPendingStoryboardTasks(bookId).find(
    (item) => item.episode === episode && item.shotId === shotId && item.kind === kind,
  ) ?? null
}

export function readShotExecutionSummaries(bookId: number): ShotExecutionSummary[] {
  if (typeof window === 'undefined' || !window.localStorage) return []
  try {
    const raw = window.localStorage.getItem(getShotExecutionSummaryStorageKey(bookId))
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((item): item is ShotExecutionSummary => (
      item &&
      typeof item === 'object' &&
      typeof item.episode === 'number' &&
      typeof item.shotId === 'string' &&
      typeof item.label === 'string' &&
      typeof item.updatedAt === 'string' &&
      (item.action === 'compile' || item.action === 'frame' || item.action === 'video')
    ))
  } catch {
    return []
  }
}

export function writeShotExecutionSummaries(bookId: number, summaries: ShotExecutionSummary[]) {
  if (typeof window === 'undefined' || !window.localStorage) return
  if (summaries.length === 0) {
    window.localStorage.removeItem(getShotExecutionSummaryStorageKey(bookId))
    return
  }
  window.localStorage.setItem(getShotExecutionSummaryStorageKey(bookId), JSON.stringify(summaries))
}

export function upsertShotExecutionSummary(bookId: number, summary: ShotExecutionSummary) {
  const current = readShotExecutionSummaries(bookId)
  const next = [
    summary,
    ...current.filter(
      (item) =>
        !(item.episode === summary.episode && item.shotId === summary.shotId && item.action === summary.action),
    ),
  ]
  writeShotExecutionSummaries(bookId, next.slice(0, 200))
  return next
}

export function readShotRuntimeState(bookId: number, episode: number, shotId: string): ShotRuntimeState {
  const normalizedShotId = String(shotId || '').trim()
  if (!episode || !normalizedShotId) {
    return {
      latestExecutionSummary: null,
      pendingTasks: [],
    }
  }

  return {
    latestExecutionSummary:
      readShotExecutionSummaries(bookId).find(
        (item) => item.episode === episode && String(item.shotId) === normalizedShotId,
      ) ?? null,
    pendingTasks: readPendingStoryboardTasks(bookId).filter(
      (item) => item.episode === episode && String(item.shotId) === normalizedShotId,
    ),
  }
}

export function readRecoveryTaskMeta(bookId: number): Record<string, RecoveryTaskLocalMeta> {
  if (typeof window === 'undefined' || !window.localStorage) return {}
  try {
    const raw = window.localStorage.getItem(getRecoveryTaskMetaStorageKey(bookId))
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

export function writeRecoveryTaskMeta(bookId: number, metaByTaskId: Record<string, RecoveryTaskLocalMeta>) {
  if (typeof window === 'undefined' || !window.localStorage) return
  if (Object.keys(metaByTaskId).length === 0) {
    window.localStorage.removeItem(getRecoveryTaskMetaStorageKey(bookId))
    return
  }
  window.localStorage.setItem(getRecoveryTaskMetaStorageKey(bookId), JSON.stringify(metaByTaskId))
}

export function upsertRecoveryTaskMeta(bookId: number, taskId: string, meta: RecoveryTaskLocalMeta) {
  const current = readRecoveryTaskMeta(bookId)
  const next = {
    ...current,
    [taskId]: {
      ...(current[taskId] ?? {}),
      ...meta,
    },
  }
  writeRecoveryTaskMeta(bookId, next)
  return next
}

export async function fetchCreativeTaskStatus(taskId: string): Promise<CreativeTaskStatusPayload> {
  const response = await fetch(`/api/prototyping/tasks/${taskId}`)
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  const payload = (await response.json()) as CreativeTaskStatusPayload & { error?: string | null }
  return {
    ...payload,
    error: payload.error ?? undefined,
  }
}

export async function fetchStoryboardRecoveryTaskStatus(task: Pick<PendingStoryboardTask, 'taskId' | 'kind'>): Promise<CreativeTaskStatusPayload> {
  if (task.kind === 'prompt') {
    const response = await fetch(`/api/storyboard-prompt-compile-tasks/${task.taskId}`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const payload = (await response.json()) as CreativeTaskStatusPayload & { error?: string | null }
    return {
      ...payload,
      error: payload.error ?? undefined,
    }
  }
  return fetchCreativeTaskStatus(task.taskId)
}

export async function fetchBookCreativeTasks(bookId: number, limit = 20): Promise<CreativeTaskStatusPayload[]> {
  const response = await fetch(`/api/books/${bookId}/creative-tasks?limit=${encodeURIComponent(String(limit))}`)
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  const payload = (await response.json()) as BookCreativeTaskListPayload
  return Array.isArray(payload.tasks) ? payload.tasks : []
}

export async function reconcileCreativeTask(taskId: string): Promise<CreativeTaskStatusPayload> {
  const response = await fetch(`/api/prototyping/tasks/${taskId}/reconcile`, { method: 'POST' })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  const payload = (await response.json()) as CreativeTaskStatusPayload & { error?: string | null }
  return {
    ...payload,
    error: payload.error ?? undefined,
  }
}

export async function reconcileStoryboardRecoveryTask(task: Pick<PendingStoryboardTask, 'taskId' | 'kind'>): Promise<CreativeTaskStatusPayload> {
  if (task.kind === 'prompt') {
    return fetchStoryboardRecoveryTaskStatus(task)
  }
  return reconcileCreativeTask(task.taskId)
}

export async function restartCreativeTask(taskId: string): Promise<CreativeTaskStatusPayload & { restarted_from_task_id?: string }> {
  const response = await fetch(`/api/prototyping/tasks/${taskId}/restart`, { method: 'POST' })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  const payload = (await response.json()) as CreativeTaskStatusPayload & { error?: string | null; restarted_from_task_id?: string }
  return {
    ...payload,
    error: payload.error ?? undefined,
  }
}

export async function restartStoryboardRecoveryTask(input: {
  taskId: string
  kind: StoryboardRecoveryKind
  bookId: number
  episode: number
  shotId: string
}): Promise<CreativeTaskStatusPayload & { restarted_from_task_id?: string }> {
  if (input.kind === 'prompt') {
    throw new Error('提示词恢复不会自动调用 LLM。请打开对应镜头的“受控 Prompt Compiler 草案”重新审核并创建版本。')
    const response = await fetch(`/api/books/${input.bookId}/storyboard/${input.episode}/${input.shotId}/compile-prompts/async`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ compileReason: 'task-center-restart', force: false }),
    })
    if (!response.ok) {
      let detail = ''
      try {
        const payload = await response.json()
        detail = String(payload?.detail || payload?.error || '').trim()
      } catch {
        detail = await response.text()
      }
      throw new Error(detail || `HTTP ${response.status}`)
    }
    const payload = (await response.json()) as CreativeTaskStatusPayload & { error?: string | null }
    return {
      ...payload,
      restarted_from_task_id: input.taskId,
      error: payload.error ?? undefined,
    }
  }
  return restartCreativeTask(input.taskId)
}

export function getStoryboardRecoveryKindLabel(kind: StoryboardRecoveryKind) {
  if (kind === 'frame') return '\u9996\u5e27'
  if (kind === 'video') return '\u89c6\u9891'
  if (kind === 'prompt') return '\u63d0\u793a\u8bcd\u7f16\u8bd1'
  return '\u53c2\u8003\u56fe'
}

export type PendingStoryboardTaskSummary = {
  count: number
  kindLabels: string[]
  joinedKindLabels: string
  latestUpdatedAt: string | null
  latestTaskId: string | null
  latestKindLabel: string | null
  latestSourceLabel: string | null
}

export function summarizePendingStoryboardTasks(tasks: PendingStoryboardTask[]): PendingStoryboardTaskSummary {
  const sortedTasks = [...tasks].sort((left, right) => String(right.updatedAt).localeCompare(String(left.updatedAt)))
  const latestTask = sortedTasks[0] ?? null
  const kindLabels = sortedTasks.map((task) => getStoryboardRecoveryKindLabel(task.kind))
  const latestKindLabel = latestTask ? getStoryboardRecoveryKindLabel(latestTask.kind) : null
  const latestSourceLabel = latestTask
    ? latestTask.assetLabel
      ? `${latestKindLabel} / ${latestTask.assetLabel}`
      : latestKindLabel
    : null

  return {
    count: sortedTasks.length,
    kindLabels,
    joinedKindLabels: kindLabels.length > 0 ? kindLabels.join(' / ') : '\u65e0',
    latestUpdatedAt: latestTask?.updatedAt ?? null,
    latestTaskId: latestTask?.taskId ?? null,
    latestKindLabel,
    latestSourceLabel,
  }
}

