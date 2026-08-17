import { useCallback, useEffect, useMemo, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { ScriptOutput, StoryboardShotOutput } from '../prototyping/sceneComposerData'
import {
  buildTaskCenterEntries,
  type TaskCenterEntry,
  type TaskCenterQaWorkbenchEpisodeSummary,
  type TaskCenterSection,
  type TaskCenterStatus,
} from './productWorkspaceTasks'
import type {
  ContentTaskState,
  TaskNavigationTarget,
  WorkspaceTaskRouteOptions,
} from './productWorkspaceSectionContracts'
import {
  fetchBookCreativeTasks,
  readPendingStoryboardTasks,
  readRecoveryTaskMeta,
  readShotExecutionSummaries,
  fetchStoryboardRecoveryTaskStatus,
  reconcileStoryboardRecoveryTask,
  removePendingStoryboardTask,
  upsertPendingStoryboardTask,
  upsertRecoveryTaskMeta,
  type CreativeTaskStatusPayload,
  type PendingStoryboardTask,
  type RecoveryTaskLocalMeta,
  type ShotExecutionSummary,
} from './productWorkspaceRecovery'
import type { ScriptDecisionMap } from './productWorkspaceScriptDecisions'
import { waitForCreativeTask } from './productWorkspaceGeneration'
import {
  readBatchRunRecords,
  saveBatchRunRecord,
  type BatchRunRecord,
} from './productWorkspaceBatchRuns'
import { executeBatchTaskAction, type BatchTaskAction } from './productWorkspaceBatchActions'
import {
  executeRecoveryTaskAction,
  type RecoveryTaskAction,
} from './productWorkspaceTaskRecoveryActions'
import { findAdoptedMediaAsset, getShotReferenceAssetIds } from './productWorkspaceBatchActions'
import {
  buildBatchCounters as buildTaskCenterBatchCounters,
  inferEpisodeFromTask as inferEpisodeFromTaskCenterEntry,
  filterTaskCenterEntries as filterVisibleTaskCenterEntries,
  inferAssetIdFromTask as inferAssetIdFromTaskCenterEntry,
  inferRecoveryIntentFromTask as inferRecoveryIntentFromTaskCenterEntry,
  inferShotIdFromTask as inferShotIdFromTaskCenterEntry,
  selectBatchRunRecords as selectTaskCenterBatchRunRecords,
  summarizeTaskCenter as summarizeTaskCenterEntries,
} from './productWorkspaceTaskCenterState'
import {
  buildQaWorkbenchSummary as buildTaskCenterQaWorkbenchSummary,
  buildRecoveryTaskEntries as buildTaskCenterRecoveryEntries,
  type QaWorkbenchResponse,
} from './productWorkspaceTaskCenterData'
import TaskCenterListPanel from './productWorkspaceTaskCenterListPanel'
import TaskCenterOverviewPanel from './productWorkspaceTaskCenterOverviewPanel'
import TaskCenterSelectedTaskPanel from './productWorkspaceTaskCenterSelectedTaskPanel'

interface Props {
  bookId: number
  contentReady: boolean
  adaptationLocked: boolean
  adaptationReadyForDownstream: boolean
  contentTask: ContentTaskState
  scripts: ScriptOutput[]
  scriptDecisionState: ScriptDecisionMap
  shotsByEpisode: Record<number, StoryboardShotOutput[]>
  qaEntries: Array<{ episode: number; error_count?: number }>
  navigationTarget?: TaskNavigationTarget | null
  onRefresh: () => void
  onNavigate: (
    section: TaskCenterSection,
    options?: WorkspaceTaskRouteOptions,
  ) => void
}

type TaskActionState = {
  mode: 'idle' | 'loading' | 'success' | 'error'
  action:
    | 'qa-autofix'
    | 'qa-recheck'
    | 'recovery-refresh'
    | 'recovery-reconcile'
    | 'recovery-restart'
    | 'recovery-regenerate-latest'
    | BatchTaskAction
    | null
  message: string
}

type TaskOperationSummary = {
  title: string
  detail: string
  primaryLabel?: string
  primaryTarget?: TaskCenterSection | null
  options?: WorkspaceTaskRouteOptions
  secondaryCanvasOptions?: WorkspaceTaskRouteOptions | null
}

const STATUS_OPTIONS: Array<{ value: 'all' | TaskCenterStatus; label: string }> = [
  { value: 'all', label: '全部状态' },
  { value: 'running', label: '进行中' },
  { value: 'queued', label: '待执行' },
  { value: 'error', label: '待修复' },
  { value: 'blocked', label: '等待上游' },
  { value: 'done', label: '已完成' },
  { value: 'skipped', label: '已跳过' },
]

const SCOPE_OPTIONS = [
  { value: 'all', label: '全部范围' },
  { value: 'global', label: '批量/全局' },
  { value: 'episode', label: '单集任务' },
] as const

function persistBatchRun(bookId: number, record: BatchRunRecord, setRecords: Dispatch<SetStateAction<Record<string, BatchRunRecord[]>>>) {
  const next = saveBatchRunRecord(bookId, record)
  setRecords(next)
}


export default function ProductWorkspaceTasksSection({
  bookId,
  contentReady,
  adaptationLocked,
  adaptationReadyForDownstream,
  contentTask,
  scripts,
  scriptDecisionState,
  shotsByEpisode,
  qaEntries,
  navigationTarget,
  onRefresh,
  onNavigate,
}: Props) {
  const [statusFilter, setStatusFilter] = useState<'all' | TaskCenterStatus>('all')
  const [scopeFilter, setScopeFilter] = useState<'all' | 'global' | 'episode'>('all')
  const [episodeFilter, setEpisodeFilter] = useState<'all' | number>('all')
  const [pendingTasks, setPendingTasks] = useState<PendingStoryboardTask[]>([])
  const [recoveryTaskStatuses, setRecoveryTaskStatuses] = useState<Record<string, CreativeTaskStatusPayload>>({})
  const [recoveryTaskMetaById, setRecoveryTaskMetaById] = useState<Record<string, RecoveryTaskLocalMeta>>({})
  const [shotExecutionSummaries, setShotExecutionSummaries] = useState<ShotExecutionSummary[]>([])
  const [creativeTasks, setCreativeTasks] = useState<CreativeTaskStatusPayload[]>([])
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [taskActionStateById, setTaskActionStateById] = useState<Record<string, TaskActionState>>({})
  const [taskOperationSummary, setTaskOperationSummary] = useState<TaskOperationSummary | null>(null)
  const [previewImage, setPreviewImage] = useState<{ url: string; title: string } | null>(null)
  const [qaWorkbenchEpisodes, setQaWorkbenchEpisodes] = useState<TaskCenterQaWorkbenchEpisodeSummary[]>([])
  const [batchRunRecords, setBatchRunRecords] = useState<Record<string, BatchRunRecord[]>>({})

  const openPreview = useCallback((url: string, title: string) => {
    if (!url) return
    setPreviewImage({ url, title })
  }, [])

  const loadPendingStoryboardTasks = useCallback(() => {
    const tasks = readPendingStoryboardTasks(bookId)
    setPendingTasks(tasks)
    setRecoveryTaskMetaById(readRecoveryTaskMeta(bookId))
    setShotExecutionSummaries(readShotExecutionSummaries(bookId))

    if (tasks.length === 0) return
    void Promise.all(
      tasks.map(async (task) => {
        try {
          const payload = await fetchStoryboardRecoveryTaskStatus(task)
          if (payload.status === 'done') {
            removePendingStoryboardTask(bookId, task.taskId)
            return [task.taskId, payload] as const
          }
          const shouldReconcile =
            payload.status === 'error' ||
            payload.status === 'soft_timeout' ||
            payload.external_status === 'running' ||
            payload.external_status === 'queued'
          if (!shouldReconcile) {
            return [task.taskId, payload] as const
          }
          const reconciled = await reconcileStoryboardRecoveryTask(task)
          if (reconciled.status === 'done') {
            removePendingStoryboardTask(bookId, task.taskId)
          }
          return [task.taskId, reconciled] as const
        } catch {
          try {
            const reconciled = await reconcileStoryboardRecoveryTask(task)
            if (reconciled.status === 'done') {
              removePendingStoryboardTask(bookId, task.taskId)
            }
            return [task.taskId, reconciled] as const
          } catch {
            return [task.taskId, { task_id: task.taskId, status: 'not_found' } satisfies CreativeTaskStatusPayload] as const
          }
        }
      }),
    ).then((records) => {
      const recoveredAnyTask = records.some(([, payload]) => payload.status === 'done')
      setPendingTasks(readPendingStoryboardTasks(bookId))
      setShotExecutionSummaries(readShotExecutionSummaries(bookId))
      setRecoveryTaskStatuses((current) => ({
        ...current,
        ...Object.fromEntries(records),
      }))
      if (recoveredAnyTask) {
        onRefresh()
      }
    })
  }, [bookId, onRefresh])

  const loadQaWorkbench = useCallback(async () => {
    try {
      const response = await fetch(`/api/books/${bookId}/qa/workbench`)
      if (!response.ok) return
      const payload = (await response.json()) as QaWorkbenchResponse
      setQaWorkbenchEpisodes(buildTaskCenterQaWorkbenchSummary(payload))
    } catch {
      // noop
    }
  }, [bookId])

  const loadCreativeTasks = useCallback(async () => {
    try {
      const tasks = await fetchBookCreativeTasks(bookId, 30)
      setCreativeTasks(tasks)
    } catch {
      setCreativeTasks([])
    }
  }, [bookId])

  useEffect(() => {
    loadPendingStoryboardTasks()
    void loadQaWorkbench()
    void loadCreativeTasks()
    setBatchRunRecords(readBatchRunRecords(bookId))
    const onFocus = () => loadPendingStoryboardTasks()
    const intervalId = window.setInterval(() => loadPendingStoryboardTasks(), 15000)
    window.addEventListener('focus', onFocus)
    return () => {
      window.removeEventListener('focus', onFocus)
      window.clearInterval(intervalId)
    }
  }, [loadCreativeTasks, loadPendingStoryboardTasks, loadQaWorkbench])

  const baseEntries = useMemo(
    () =>
      buildTaskCenterEntries({
        contentReady,
        adaptationLocked,
        adaptationReadyForDownstream,
        contentTask,
        scripts,
        scriptDecisionState,
        shotsByEpisode,
        qaEntries,
        qaWorkbenchEpisodes,
      }),
    [
      adaptationLocked,
      adaptationReadyForDownstream,
      contentReady,
      contentTask,
      qaEntries,
      qaWorkbenchEpisodes,
      scriptDecisionState,
      scripts,
      shotsByEpisode,
    ],
  )

  const recoveryEntries = useMemo(
    () => buildTaskCenterRecoveryEntries(pendingTasks, recoveryTaskStatuses, creativeTasks, recoveryTaskMetaById, shotsByEpisode),
    [creativeTasks, pendingTasks, recoveryTaskMetaById, recoveryTaskStatuses, shotsByEpisode],
  )

  const allEntries = useMemo(() => [...baseEntries, ...recoveryEntries], [baseEntries, recoveryEntries])
  const episodeOptions = useMemo(
    () =>
      Array.from(new Set(allEntries.map((item) => item.episode).filter((item): item is number => Boolean(item))))
        .sort((a, b) => a - b),
    [allEntries],
  )

  const filteredEntries = useMemo(
    () =>
      filterVisibleTaskCenterEntries(allEntries, {
        statusFilter,
        scopeFilter,
        episodeFilter,
      }),
    [allEntries, episodeFilter, scopeFilter, statusFilter],
  )

  useEffect(() => {
    if (filteredEntries.length === 0) {
      setSelectedTaskId(null)
      return
    }

    const preferredEntry =
      filteredEntries.find((item) => item.status === 'blocked' && item.actionTarget === 'adaptation') ??
      filteredEntries.find((item) => item.status === 'blocked' && item.scope === 'global') ??
      filteredEntries.find((item) => item.status === 'blocked') ??
      filteredEntries.find((item) => item.status === 'error') ??
      filteredEntries.find((item) => item.status === 'running') ??
      filteredEntries.find((item) => item.status === 'queued') ??
      filteredEntries.find((item) => item.status !== 'done' && item.status !== 'skipped') ??
      filteredEntries[0] ??
      null

    setSelectedTaskId((current) => {
      if (current && filteredEntries.some((item) => item.id === current)) return current
      return preferredEntry?.id ?? null
    })
  }, [filteredEntries])

  const selectedTask = useMemo(
    () => filteredEntries.find((item) => item.id === selectedTaskId) ?? filteredEntries[0] ?? null,
    [filteredEntries, selectedTaskId],
  )
  const navigationTargetSummary = useMemo(() => {
    if (!navigationTarget) return null
    const episode = Number(navigationTarget.episode ?? 0) || null
    const shotId = String(navigationTarget.shotId ?? '').trim()
    const recoveryKind =
      navigationTarget.recoveryKind === 'prompt'
        ? '提示词'
        : navigationTarget.recoveryKind === 'frame'
          ? '首帧'
          : navigationTarget.recoveryKind === 'video'
            ? '视频'
            : navigationTarget.recoveryKind === 'reference'
              ? '参考图'
              : null
    const lines = [
      episode ? `第 ${episode} 集` : null,
      shotId ? `镜头 ${shotId}` : null,
      recoveryKind ? `${recoveryKind}回收` : null,
    ].filter(Boolean)
    return {
      title: lines.length > 0 ? lines.join(' / ') : '已按恢复上下文进入任务中心',
      detail: navigationTarget.taskId
        ? `当前正在尝试定位任务 ${navigationTarget.taskId}；如果列表中暂未命中原任务，请优先查看同镜头恢复任务。`
        : '当前入口带有镜头恢复上下文，可先查看同镜头的恢复任务或继续跳回镜头工作台。',
    }
  }, [navigationTarget])

  useEffect(() => {
    if (!navigationTarget) return
    const targetEpisode = Number(navigationTarget.episode ?? 0) || null
    const targetShotId = String(navigationTarget.shotId ?? '').trim()
    const targetTaskId = String(navigationTarget.taskId ?? '').trim()

    setStatusFilter('all')
    setScopeFilter('all')
    setEpisodeFilter(targetEpisode ?? 'all')

    const matchedEntry =
      allEntries.find((item) => targetTaskId && String(item.taskId ?? '').trim() === targetTaskId) ??
      allEntries.find((item) => {
        const entryEpisode = inferEpisodeFromTaskCenterEntry(item)
        const entryShotId = String(inferShotIdFromTaskCenterEntry(item) ?? '').trim()
        if (targetEpisode && entryEpisode !== targetEpisode) return false
        if (targetShotId && entryShotId !== targetShotId) return false
        if (navigationTarget.recoveryKind && item.recoveryKind !== navigationTarget.recoveryKind) return false
        return Boolean(entryEpisode || entryShotId)
      }) ??
      null

    if (matchedEntry?.id) {
      setSelectedTaskId(matchedEntry.id)
    }
  }, [allEntries, navigationTarget])

  const selectedTaskActionState: TaskActionState = selectedTask
    ? taskActionStateById[selectedTask.id] ?? { mode: 'idle', action: null, message: '' }
    : { mode: 'idle', action: null, message: '' }
  const selectedTaskEpisode = useMemo(() => inferEpisodeFromTaskCenterEntry(selectedTask), [selectedTask])
  const selectedTaskShotId = useMemo(() => inferShotIdFromTaskCenterEntry(selectedTask), [selectedTask])
  const selectedTaskAssetId = useMemo(() => inferAssetIdFromTaskCenterEntry(selectedTask), [selectedTask])
  const stats = useMemo(() => summarizeTaskCenterEntries(allEntries), [allEntries])
  const { batchPromptCompileCount, batchMissingFrameCount, batchMissingVideoCount, batchOpenQaEpisodeCount } = useMemo(
    () => buildTaskCenterBatchCounters(shotsByEpisode, qaWorkbenchEpisodes),
    [qaWorkbenchEpisodes, shotsByEpisode],
  )
  const { selectedBatchRunRecords, latestSelectedBatchRunRecord } = useMemo(
    () => selectTaskCenterBatchRunRecords(selectedTask?.id, batchRunRecords),
    [batchRunRecords, selectedTask?.id],
  )
  const taskRuntimeById = useMemo(() => {
    const result: Record<string, { latestExecutionLabel?: string | null; pendingKindLabels: string[] }> = {}
    for (const entry of filteredEntries) {
      const episode = inferEpisodeFromTaskCenterEntry(entry)
      const shotId = inferShotIdFromTaskCenterEntry(entry)
      if (!episode || !shotId) continue
      const latestExecution =
        shotExecutionSummaries.find(
          (item) => item.episode === episode && String(item.shotId) === String(shotId),
        ) ?? null
      const pendingKindLabels = pendingTasks
        .filter((item) => item.episode === episode && String(item.shotId) === String(shotId))
        .map((item) => item.kind === 'prompt' ? '提示词' : item.kind === 'frame' ? '首帧' : item.kind === 'video' ? '视频' : '参考图')
      if (!latestExecution && pendingKindLabels.length === 0) continue
      result[entry.id] = {
        latestExecutionLabel: latestExecution?.label ?? null,
        pendingKindLabels,
      }
    }
    return result
  }, [filteredEntries, pendingTasks, shotExecutionSummaries])

  const navigateFromTaskEntry = useCallback(
    (entry: TaskCenterEntry) => {
      const episode = inferEpisodeFromTaskCenterEntry(entry)
      const shotId = inferShotIdFromTaskCenterEntry(entry)
      const assetId = inferAssetIdFromTaskCenterEntry(entry)
      onNavigate(entry.actionTarget, {
        episode,
        shotId,
        assetId,
        assetLabel: entry.creativeTaskMeta?.assetSubject || entry.target,
        taskId: entry.taskId ?? null,
        recoveryKind: entry.recoveryKind ?? null,
        recoveryIntent: inferRecoveryIntentFromTaskCenterEntry(entry),
      })
    },
    [onNavigate],
  )

  async function runQaTaskAction(action: 'qa-autofix' | 'qa-recheck') {
    if (!selectedTask || selectedTask.actionTarget !== 'qa' || !selectedTask.episode) return

    setTaskActionStateById((current) => ({
      ...current,
      [selectedTask.id]: { mode: 'loading', action, message: '' },
    }))

    try {
      const response = await fetch(
        action === 'qa-autofix'
          ? `/api/books/${bookId}/qa/episodes/${selectedTask.episode}/auto-fix`
          : `/api/books/${bookId}/qa/episodes/${selectedTask.episode}/recheck`,
        action === 'qa-autofix'
          ? {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                mode: 'auto',
                rerunQa: true,
                operatorName: 'task-center',
                maxIssues: 10,
              }),
            }
          : { method: 'POST' },
      )

      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(typeof payload?.detail === 'string' ? payload.detail : `HTTP ${response.status}`)
      }

      const message =
        action === 'qa-autofix'
          ? `已提交整集自动修复：成功 ${Number(payload.applied_count ?? 0)} 条，失败 ${Number(payload.failed_count ?? 0)} 条。`
          : `第 ${selectedTask.episode} 集已触发复检。`

      setTaskActionStateById((current) => ({
        ...current,
        [selectedTask.id]: { mode: 'success', action, message },
      }))
      void loadQaWorkbench()
    } catch (error) {
      setTaskActionStateById((current) => ({
        ...current,
        [selectedTask.id]: {
          mode: 'error',
          action,
          message: error instanceof Error ? error.message : 'QA 任务执行失败，请稍后重试。',
        },
      }))
    }
  }

  async function runBatchTaskAction(
    action: BatchTaskAction,
  ) {
    if (!selectedTask) return
    const startedAt = new Date().toISOString()

    setTaskActionStateById((current) => ({
      ...current,
      [selectedTask.id]: { mode: 'loading', action, message: '' },
    }))

    try {
      const result = await executeBatchTaskAction({
        action,
        bookId,
        shotsByEpisode,
        pendingTasks,
        qaWorkbenchEpisodes,
        fetchTaskStatus: fetchStoryboardRecoveryTaskStatus as any,
        waitForCreativeTask,
      })

      if (result.refreshPendingStoryboardTasks) {
        loadPendingStoryboardTasks()
      }
      void loadCreativeTasks()
      if (result.refreshQaWorkbench) {
        void loadQaWorkbench()
      }
      onNavigate(result.navigateTo)
      if (result.refreshProjectData) {
        onRefresh()
      }

      persistBatchRun(
        bookId,
        {
          taskId: result.taskIdForRecord,
          action,
          status: result.status,
          startedAt,
          finishedAt: new Date().toISOString(),
          successCount: result.successCount,
          failedCount: result.failedCount,
          pendingRecoveryCount: result.pendingRecoveryCount,
          failedTargets: result.failedTargets,
          summary: result.summary,
        },
        setBatchRunRecords,
      )
      setTaskActionStateById((current) => ({
        ...current,
        [selectedTask.id]: {
          mode: result.status === 'error' ? 'error' : 'success',
          action,
          message: result.summary,
        },
      }))
    } catch (error) {
      persistBatchRun(
        bookId,
        {
          taskId:
            selectedTask.id === 'task-batch-prompts' || selectedTask.id === 'task-batch-assets' || selectedTask.id === 'task-batch-qa'
              ? selectedTask.id
              : 'task-batch-prompts',
          action,
          status: 'error',
          startedAt,
          finishedAt: new Date().toISOString(),
          successCount: 0,
          failedCount: 1,
          summary: error instanceof Error ? error.message : '批量任务执行失败，请稍后重试。',
        },
        setBatchRunRecords,
      )
      setTaskActionStateById((current) => ({
        ...current,
        [selectedTask.id]: {
          mode: 'error',
          action,
          message: error instanceof Error ? error.message : '批量任务执行失败，请稍后重试。',
        },
      }))
    }
  }

  async function runRecoveryTaskAction(action: RecoveryTaskAction) {
    if (!selectedTask?.taskId) return

    const selectedTaskOptions: WorkspaceTaskRouteOptions = {
      episode: selectedTask.episode ?? selectedTaskEpisode ?? null,
      shotId: String(selectedTask.shotId || selectedTaskShotId || '') || null,
      assetId: selectedTask.assetId ?? selectedTaskAssetId ?? null,
      assetLabel: selectedTask.creativeTaskMeta?.assetSubject || selectedTask.target,
      taskId: selectedTask.taskId ?? null,
      recoveryKind: selectedTask.recoveryKind ?? null,
      recoveryIntent: inferRecoveryIntentFromTaskCenterEntry(selectedTask),
    }
    setTaskOperationSummary(null)

    setTaskActionStateById((current) => ({
      ...current,
      [selectedTask.id]: { mode: 'loading', action, message: '' },
    }))

    try {
      if (action === 'recovery-regenerate-latest') {
        const selectedEpisode = selectedTask.episode ?? 0
        const selectedShotId = String(selectedTask.shotId || selectedTaskShotId || '')
        const shot = (shotsByEpisode[selectedEpisode] ?? []).find((item) => String(item.shot_id) === selectedShotId) ?? null
        if (!shot) {
          throw new Error('未能找到当前镜头数据，请先刷新项目数据后重试。')
        }
        if (selectedTask.recoveryKind !== 'frame' && selectedTask.recoveryKind !== 'video') {
          throw new Error('当前仅支持对首帧或视频任务按最新镜头状态重新生成。')
        }

        const generationKind = selectedTask.recoveryKind === 'frame' ? 'frame' : 'video'
        const latestPayload =
          generationKind === 'frame'
            ? {
                generationChain: 'task_center_regenerate_latest_frame',
              }
            : (() => {
                const adoptedImage = findAdoptedMediaAsset(shot.assets?.images)
                const adoptedImageId = String(adoptedImage?.id || '').trim()
                if (!adoptedImageId) {
                  throw new Error('当前镜头还没有已采纳首帧，不能按最新状态重新生成视频。')
                }
                return {
                  compileIfMissing: true,
                  firstFrameAssetId: adoptedImageId,
                  referenceAssetIds: getShotReferenceAssetIds(shot),
                  generationChain: 'task_center_regenerate_latest_video',
                }
              })()

        const response = await fetch(
          `/api/books/${bookId}/storyboard/${selectedEpisode}/${selectedShotId}/${generationKind === 'frame' ? 'generate-frame' : 'generate-video'}`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(latestPayload),
          },
        )
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

        const payload = await response.json()
        const newTaskId = String(payload?.task_id || '').trim()
        if (!newTaskId) {
          throw new Error('按最新镜头状态重新生成失败：服务端未返回任务号。')
        }

        const restartedAt = new Date().toISOString()
        removePendingStoryboardTask(bookId, selectedTask.taskId)
        upsertPendingStoryboardTask(bookId, {
          taskId: newTaskId,
          episode: selectedEpisode,
          shotId: selectedShotId,
          kind: generationKind === 'frame' ? 'frame' : 'video',
          updatedAt: restartedAt,
          assetId: selectedTask.assetId,
          assetLabel: selectedTask.creativeTaskMeta?.assetSubject,
          restartedFromTaskId: selectedTask.taskId,
          restartCount: Number(selectedTask.recoveryMeta?.restartCount ?? 0) + 1,
          lastRestartedAt: restartedAt,
        })
        upsertRecoveryTaskMeta(bookId, newTaskId, {
          restartedFromTaskId: selectedTask.taskId,
          restartCount: Number(selectedTask.recoveryMeta?.restartCount ?? 0) + 1,
          lastRestartedAt: restartedAt,
        })

        const nextId = `task-recovery-${newTaskId}`
        setRecoveryTaskStatuses((current) => {
          const next = {
            ...current,
            [newTaskId]: {
              ...(payload as CreativeTaskStatusPayload),
              restarted_from_task_id: selectedTask.taskId,
            },
          }
          delete next[selectedTask.taskId!]
          return next
        })
        setTaskActionStateById((current) => ({
          ...current,
          [nextId]: {
            mode: 'success',
            action,
            message: `已按镜头当前最新状态重新生成任务 ${newTaskId}，并接回任务中心。`,
          },
        }))
        setTaskOperationSummary({
          title: '已重新接回任务中心',
          detail: `新的${generationKind === 'frame' ? '首帧' : '视频'}任务 ${newTaskId} 已创建。建议继续留在任务中心跟踪状态，确认任务真正收口后，再回镜头或画布检查产物。`,
          secondaryCanvasOptions: {
            ...selectedTaskOptions,
            taskId: newTaskId,
            recoveryKind: generationKind,
          },
        })
        setSelectedTaskId(nextId)
        loadPendingStoryboardTasks()
        void loadCreativeTasks()
        return
      }

      const result = await executeRecoveryTaskAction(action, {
        bookId,
        taskId: selectedTask.taskId,
        episode: selectedTask.episode ?? 0,
        shotId: String(selectedTask.shotId || selectedTaskShotId || ''),
        kind: selectedTask.recoveryKind ?? 'video',
        assetId: selectedTask.assetId,
        assetLabel: selectedTask.creativeTaskMeta?.assetSubject,
        restartCount: selectedTask.recoveryMeta?.restartCount,
      })

      if (result.outcome === 'restarted') {
        setRecoveryTaskStatuses((current) => {
          const next = { ...current, [result.newTaskId]: result.statusPayload }
          delete next[result.previousTaskId]
          return next
        })

        const nextId = `task-recovery-${result.newTaskId}`
        setTaskActionStateById((current) => ({
          ...current,
          [nextId]: {
            mode: 'success',
            action,
            message: result.message,
          },
        }))
        setTaskOperationSummary({
          title: '已重新发起恢复任务',
          detail: `新的恢复任务 ${result.newTaskId} 已接回任务中心。建议继续在这里刷新或回收结果，再决定是否回镜头或画布继续处理。`,
          secondaryCanvasOptions: {
            ...selectedTaskOptions,
            taskId: result.newTaskId,
          },
        })
        setSelectedTaskId(nextId)
        loadPendingStoryboardTasks()
        void loadCreativeTasks()
        return
      }

      setRecoveryTaskStatuses((current) => ({
        ...current,
        [result.taskId]: result.statusPayload,
      }))

      if (result.removedFromPending) {
        loadPendingStoryboardTasks()
      }
      void loadCreativeTasks()
      if (result.refreshProjectData) {
        onRefresh()
      }

      setTaskActionStateById((current) => ({
        ...current,
        [selectedTask.id]: {
          mode:
            result.statusPayload.status === 'error' || result.statusPayload.status === 'not_found'
              ? 'error'
              : 'success',
          action,
          message: result.message,
        },
      }))
      if (result.statusPayload.status === 'done') {
        setTaskOperationSummary({
          title: '建议回看结果并确认下游',
          detail: '这次恢复已经把结果回写到项目链路。建议回镜头工作台或创作画布确认输出、采纳状态，以及下游是否可以继续推进。',
          primaryLabel: selectedTask.actionLabel,
          primaryTarget: selectedTask.actionTarget,
          options: selectedTaskOptions,
          secondaryCanvasOptions:
            selectedTaskOptions.episode || selectedTaskOptions.shotId || selectedTaskOptions.assetId
              ? selectedTaskOptions
              : null,
        })
      }
    } catch (error) {
      setTaskActionStateById((current) => ({
        ...current,
        [selectedTask.id]: {
          mode: 'error',
          action,
          message: error instanceof Error ? error.message : '任务恢复失败，请稍后重试。',
        },
      }))
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[0.95fr_minmax(0,1.2fr)_0.95fr]">
      <TaskCenterListPanel
        statusFilter={statusFilter}
        scopeFilter={scopeFilter}
        episodeFilter={episodeFilter}
        episodeOptions={episodeOptions}
        filteredEntries={filteredEntries}
        taskRuntimeById={taskRuntimeById}
        selectedTaskId={selectedTask?.id ?? selectedTaskId}
        statusOptions={STATUS_OPTIONS}
        scopeOptions={SCOPE_OPTIONS}
        onStatusFilterChange={setStatusFilter}
        onScopeFilterChange={setScopeFilter}
        onEpisodeFilterChange={setEpisodeFilter}
        onSelectTask={setSelectedTaskId}
        onRunTaskAction={navigateFromTaskEntry}
      />

      <TaskCenterSelectedTaskPanel
        bookId={bookId}
        selectedTask={selectedTask}
        navigationSummary={navigationTargetSummary}
        operationSummary={taskOperationSummary}
        selectedTaskActionState={selectedTaskActionState}
        selectedTaskEpisode={selectedTaskEpisode}
        selectedTaskShotId={selectedTaskShotId}
        selectedTaskAssetId={selectedTaskAssetId}
        latestSelectedBatchRunRecord={latestSelectedBatchRunRecord}
        selectedBatchRunRecords={selectedBatchRunRecords}
        batchPromptCompileCount={batchPromptCompileCount}
        batchMissingFrameCount={batchMissingFrameCount}
        batchMissingVideoCount={batchMissingVideoCount}
        batchOpenQaEpisodeCount={batchOpenQaEpisodeCount}
        onNavigate={onNavigate}
        onOpenPreview={openPreview}
        onRunBatchTaskAction={(action) => void runBatchTaskAction(action)}
        onRunRecoveryTaskAction={(action) => void runRecoveryTaskAction(action)}
        onRunQaTaskAction={(action) => void runQaTaskAction(action)}
      />

      <TaskCenterOverviewPanel stats={stats} />

      {previewImage ? (
        <div
          role="presentation"
          onClick={() => setPreviewImage(null)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/90 p-6"
        >
          <div
            className="w-full max-w-5xl overflow-hidden rounded-2xl border border-slate-800 bg-slate-950 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-3 border-b border-slate-800 px-4 py-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-white">{previewImage.title}</div>
                <div className="mt-1 text-[11px] text-slate-500">任务中心图片预览</div>
              </div>
              <button
                type="button"
                onClick={() => setPreviewImage(null)}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
              >
                关闭
              </button>
            </div>
            <div className="flex max-h-[80vh] items-center justify-center bg-slate-950 p-4">
              <img
                src={previewImage.url}
                alt={previewImage.title}
                className="max-h-[72vh] w-auto max-w-full rounded-xl border border-slate-800 object-contain"
              />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
