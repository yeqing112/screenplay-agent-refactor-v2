export type BatchTaskId = 'task-batch-prompts' | 'task-batch-assets' | 'task-batch-qa'

export type BatchRunRecord = {
  taskId: BatchTaskId
  action:
    | 'batch-compile-prompts'
    | 'batch-generate-frames'
    | 'batch-generate-videos'
    | 'batch-qa-autofix'
    | 'batch-qa-recheck'
  status: 'success' | 'error'
  startedAt: string
  finishedAt: string
  successCount: number
  failedCount: number
  pendingRecoveryCount?: number
  skippedCount?: number
  failedTargets?: string[]
  summary: string
}

const BATCH_RUNS_KEY_PREFIX = 'product-workspace.batch-task-runs'
const MAX_BATCH_RUN_HISTORY = 5

function getBatchRunsStorageKey(bookId: number) {
  return `${BATCH_RUNS_KEY_PREFIX}.${bookId}`
}

export function readBatchRunRecords(bookId: number): Record<string, BatchRunRecord[]> {
  if (typeof window === 'undefined' || !window.localStorage) return {}
  try {
    const raw = window.localStorage.getItem(getBatchRunsStorageKey(bookId))
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return {}

    return Object.fromEntries(
      Object.entries(parsed).map(([taskId, value]) => {
        if (Array.isArray(value)) {
          return [taskId, value.filter((item) => item && typeof item === 'object')]
        }
        if (value && typeof value === 'object') {
          return [taskId, [value]]
        }
        return [taskId, []]
      }),
    )
  } catch {
    return {}
  }
}

export function writeBatchRunRecords(bookId: number, records: Record<string, BatchRunRecord[]>) {
  if (typeof window === 'undefined' || !window.localStorage) return
  window.localStorage.setItem(getBatchRunsStorageKey(bookId), JSON.stringify(records))
}

export function saveBatchRunRecord(bookId: number, record: BatchRunRecord) {
  const current = readBatchRunRecords(bookId)
  const currentList = Array.isArray(current[record.taskId]) ? current[record.taskId] : []
  const next = {
    ...current,
    [record.taskId]: [record, ...currentList].slice(0, MAX_BATCH_RUN_HISTORY),
  }
  writeBatchRunRecords(bookId, next)
  return next
}
