import type { StoryboardShotOutput } from '../prototyping/sceneComposerData'
import type { BatchRunRecord } from './productWorkspaceBatchRuns'
import {
  findAdoptedMediaAsset,
  hasGeneratedFrame,
  hasGeneratedVideo,
  hasPromptPair,
} from './productWorkspaceBatchActions'
import type { TaskCenterEntry, TaskCenterQaWorkbenchEpisodeSummary, TaskCenterStatus } from './productWorkspaceTasks'
import type { WorkspaceTaskRouteOptions } from './productWorkspaceSectionContracts'

export function summarizeTaskCenter(entries: TaskCenterEntry[]) {
  const globalEntries = entries.filter((item) => item.scope === 'global')
  const readyForAction = entries.filter((item) => ['queued', 'running', 'error'].includes(item.status))
  const nextFocus =
    entries.find((item) => item.status === 'blocked' && item.actionTarget === 'adaptation') ??
    entries.find((item) => item.status === 'blocked' && item.scope === 'global') ??
    entries.find((item) => item.status === 'blocked') ??
    entries.find((item) => item.status === 'error') ??
    entries.find((item) => item.status === 'running') ??
    entries.find((item) => item.status === 'queued') ??
    null

  return {
    total: entries.length,
    running: entries.filter((item) => item.status === 'running').length,
    queued: entries.filter((item) => item.status === 'queued').length,
    error: entries.filter((item) => item.status === 'error').length,
    blocked: entries.filter((item) => item.status === 'blocked').length,
    skipped: entries.filter((item) => item.status === 'skipped').length,
    done: entries.filter((item) => item.status === 'done').length,
    globalCount: globalEntries.length,
    actionableCount: readyForAction.length,
    nextFocus,
  }
}

function pickPreferredPromptHealthShot(task: TaskCenterEntry | null) {
  if (!task?.promptHealth?.degradedShots?.length) return null
  return (
    task.promptHealth.degradedShots.find(
      (item) => item.recommendedRestoreVersion !== null && item.recommendedRestoreVersion !== undefined && item.shotId,
    ) ??
    task.promptHealth.degradedShots.find((item) => item.shotId) ??
    null
  )
}

export function inferShotIdFromTask(task: TaskCenterEntry | null) {
  if (!task) return null
  if (task.shotId) return String(task.shotId)
  const preferredPromptShot = pickPreferredPromptHealthShot(task)
  if (preferredPromptShot?.shotId) return String(preferredPromptShot.shotId)
  const match = String(task.target || '').match(/第\s*\d+\s*集\s*[\/|·路-]\s*([^\/|·路-\s]+)/)
  return match?.[1] ? String(match[1]).trim() : null
}

export function inferEpisodeFromTask(task: TaskCenterEntry | null) {
  if (!task) return null
  if (typeof task.episode === 'number' && task.episode > 0) return task.episode
  const preferredPromptShot = pickPreferredPromptHealthShot(task)
  return preferredPromptShot?.episode && Number(preferredPromptShot.episode) > 0 ? Number(preferredPromptShot.episode) : null
}

export function inferAssetIdFromTask(task: TaskCenterEntry | null) {
  if (!task) return null
  if (task.assetId) return String(task.assetId)
  return task.creativeTaskMeta?.assetScope && task.creativeTaskMeta?.sourceAssetId
    ? `${task.creativeTaskMeta.assetScope === 'scene' ? 'location' : task.creativeTaskMeta.assetScope}-${task.creativeTaskMeta.sourceAssetId}`
    : null
}

export function inferRecoveryIntentFromTask(task: TaskCenterEntry | null): WorkspaceTaskRouteOptions['recoveryIntent'] {
  if (!task) return null
  if (task.recoveryKind !== 'reference') return null
  if (!task.shotId) return null
  if (task.creativeTaskMeta?.assetScope === 'character') return 'shot_variant_refinement'
  if (String(task.assetId || '').trim().startsWith('character-')) return 'shot_variant_refinement'
  return 'reference'
}

export function buildBatchCounters(
  shotsByEpisode: Record<number, StoryboardShotOutput[]>,
  qaWorkbenchEpisodes: TaskCenterQaWorkbenchEpisodeSummary[],
) {
  const batchPromptCompileCount = Object.values(shotsByEpisode).reduce(
    (sum, shots) => sum + shots.filter((shot) => !shot.prompt_locked && !hasPromptPair(shot)).length,
    0,
  )

  const batchMissingFrameCount = Object.values(shotsByEpisode).reduce(
    (sum, shots) => sum + shots.filter((shot) => !hasGeneratedFrame(shot)).length,
    0,
  )

  const batchMissingVideoCount = Object.values(shotsByEpisode).reduce((sum, shots) => {
    return (
      sum +
      shots.filter((shot) => {
        const adoptedImage = findAdoptedMediaAsset(shot.assets?.images)
        const adoptedImagePreviewUrl = String(adoptedImage?.previewUrl || adoptedImage?.uri || '').trim()
        return Boolean(adoptedImage?.id) && Boolean(adoptedImagePreviewUrl) && !hasGeneratedVideo(shot)
      }).length
    )
  }, 0)

  const batchOpenQaEpisodeCount = qaWorkbenchEpisodes.filter(
    (item) => item.openIssueCount > 0 || item.inProgressCount > 0,
  ).length

  return {
    batchPromptCompileCount,
    batchMissingFrameCount,
    batchMissingVideoCount,
    batchOpenQaEpisodeCount,
  }
}

export function selectBatchRunRecords(
  selectedTaskId: string | null | undefined,
  batchRunRecords: Record<string, BatchRunRecord[]>,
) {
  if (
    selectedTaskId !== 'task-batch-prompts' &&
    selectedTaskId !== 'task-batch-assets' &&
    selectedTaskId !== 'task-batch-qa'
  ) {
    return {
      selectedBatchRunRecords: [] as BatchRunRecord[],
      latestSelectedBatchRunRecord: null as BatchRunRecord | null,
    }
  }

  const selectedBatchRunRecords = batchRunRecords[selectedTaskId] ?? []
  return {
    selectedBatchRunRecords,
    latestSelectedBatchRunRecord: selectedBatchRunRecords[0] ?? null,
  }
}

export function filterTaskCenterEntries(
  entries: TaskCenterEntry[],
  filters: {
    statusFilter: 'all' | TaskCenterStatus
    scopeFilter: 'all' | 'global' | 'episode'
    episodeFilter: 'all' | number
  },
) {
  return entries.filter((item) => {
    if (filters.statusFilter !== 'all' && item.status !== filters.statusFilter) return false
    if (filters.scopeFilter === 'global' && item.scope !== 'global') return false
    if (filters.scopeFilter === 'episode' && item.scope === 'global') return false
    if (filters.episodeFilter !== 'all' && item.episode !== filters.episodeFilter) return false
    return true
  })
}
