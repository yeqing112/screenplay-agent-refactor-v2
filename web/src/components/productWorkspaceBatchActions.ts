import type { StoryboardShotOutput } from '../domain/bookOutputs'
import type { PendingStoryboardTask } from './productWorkspaceRecovery'
import { upsertPendingStoryboardTask, removePendingStoryboardTask } from './productWorkspaceRecovery'
import type { TaskCenterQaWorkbenchEpisodeSummary } from './productWorkspaceTasks'
import type { CreativeTaskPayload } from './productWorkspaceGeneration'
import { resolveEffectiveReferenceAssetIds } from './productWorkspaceStoryboardReferencePayload'

export type BatchTaskAction =
  | 'batch-compile-prompts'
  | 'batch-generate-frames'
  | 'batch-generate-videos'
  | 'batch-qa-autofix'
  | 'batch-qa-recheck'

export type BatchTaskExecutionResult = {
  taskIdForRecord: 'task-batch-prompts' | 'task-batch-assets' | 'task-batch-qa'
  status: 'success' | 'error'
  summary: string
  successCount: number
  failedCount: number
  pendingRecoveryCount?: number
  failedTargets?: string[]
  navigateTo: 'storyboard' | 'qa'
  refreshPendingStoryboardTasks?: boolean
  refreshQaWorkbench?: boolean
  refreshProjectData?: boolean
}

type ExecuteBatchTaskActionOptions = {
  action: BatchTaskAction
  bookId: number
  shotsByEpisode: Record<number, StoryboardShotOutput[]>
  pendingTasks: PendingStoryboardTask[]
  qaWorkbenchEpisodes: TaskCenterQaWorkbenchEpisodeSummary[]
  fetchTaskStatus: (taskId: string) => Promise<CreativeTaskPayload>
  waitForCreativeTask: (
    taskId: string,
    fetchTask: (taskId: string) => Promise<CreativeTaskPayload>,
    options?: { softTimeoutMs?: number; pollIntervalMs?: number; maxAttempts?: number },
  ) => Promise<CreativeTaskPayload | { status: 'soft_timeout'; task_id: string }>
}

export function batchActionLabel(action: BatchTaskAction) {
  switch (action) {
    case 'batch-compile-prompts':
      return '批量编译提示词'
    case 'batch-generate-frames':
      return '批量补首帧'
    case 'batch-generate-videos':
      return '批量补视频'
    case 'batch-qa-autofix':
      return '批量自动修复'
    case 'batch-qa-recheck':
      return '批量触发复检'
    default:
      return action
  }
}

export function hasPromptPair(shot: StoryboardShotOutput) {
  return Boolean(shot.visual_prompt_static?.trim()) && Boolean(shot.visual_prompt_motion?.trim())
}

export function hasGeneratedFrame(shot: StoryboardShotOutput) {
  return Array.isArray(shot.assets?.images) && shot.assets.images.length > 0
}

export function hasGeneratedVideo(shot: StoryboardShotOutput) {
  return Array.isArray(shot.assets?.videos) && shot.assets.videos.length > 0
}

export function findAdoptedMediaAsset(
  items: Array<{ id?: string; adopted?: boolean; previewUrl?: string; uri?: string }> | undefined | null,
) {
  if (!Array.isArray(items) || items.length === 0) return null
  return items.find((item) => item?.adopted) ?? items[items.length - 1] ?? null
}

export function getShotReferenceAssetIds(shot: StoryboardShotOutput) {
  return resolveEffectiveReferenceAssetIds(shot).assetIds
}

export async function executeBatchTaskAction(options: ExecuteBatchTaskActionOptions): Promise<BatchTaskExecutionResult> {
  const {
    action,
    bookId,
    shotsByEpisode,
    pendingTasks,
    qaWorkbenchEpisodes,
    fetchTaskStatus,
    waitForCreativeTask,
  } = options

  if (action === 'batch-compile-prompts') {
    throw new Error('批量直接重编译已停用：请逐镜使用“受控 Prompt Compiler 草案”审核并确认，避免批量隐式调用 LLM。')
    const executableShots = Object.entries(shotsByEpisode)
      .flatMap(([episode, shots]) =>
        shots
          .filter((shot) => !shot.prompt_locked && !hasPromptPair(shot))
          .map((shot) => ({ episode: Number(episode), shotId: String(shot.shot_id) })),
      )

    if (executableShots.length === 0) {
      throw new Error('当前没有可批量编译的镜头，未锁定镜头已全部具备静态/运动提示词。')
    }

    let successCount = 0
    let failedCount = 0
    const failedTargets: string[] = []

    for (const target of executableShots) {
      const response = await fetch(`/api/books/${bookId}/storyboard/${target.episode}/${target.shotId}/compile-prompts/async`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ compileReason: 'task-center-batch', force: false }),
      })

      if (!response.ok) {
        failedCount += 1
        failedTargets.push(`第 ${target.episode} 集 / 镜头 ${target.shotId}`)
        continue
      }

      const payload = await response.json().catch(() => ({}))
      const taskId = String(payload.task_id || '').trim()
      if (!taskId) {
        failedCount += 1
        failedTargets.push(`第 ${target.episode} 集 / 镜头 ${target.shotId}`)
        continue
      }

      upsertPendingStoryboardTask(bookId, {
        taskId,
        episode: target.episode,
        shotId: target.shotId,
        kind: 'prompt',
        updatedAt: new Date().toISOString(),
      })

      const taskPayload = await waitForCreativeTask(
        taskId,
        async (currentTaskId) => {
          const taskResponse = await fetch(`/api/storyboard-prompt-compile-tasks/${currentTaskId}`)
          if (!taskResponse.ok) {
            throw new Error(`HTTP ${taskResponse.status}`)
          }
          return taskResponse.json()
        },
        {
          softTimeoutMs: 2000,
          pollIntervalMs: 500,
          maxAttempts: 6,
        },
      )

      if (taskPayload.status === 'done') {
        removePendingStoryboardTask(bookId, taskId)
        successCount += 1
        continue
      }

      if (taskPayload.status === 'soft_timeout') {
        successCount += 1
        continue
      }

      failedCount += 1
      failedTargets.push(`第 ${target.episode} 集 / 镜头 ${target.shotId}`)
    }

    const summary =
      failedCount > 0
        ? `已批量编译 ${successCount} 个镜头，失败 ${failedCount} 个：${failedTargets.slice(0, 3).join('、')}${failedTargets.length > 3 ? ' 等' : ''}。`
        : `已批量编译 ${successCount} 个镜头，并回写到镜头工作台。`

    return {
      taskIdForRecord: 'task-batch-prompts',
      status: failedCount > 0 ? 'error' : 'success',
      summary,
      successCount,
      failedCount,
      failedTargets,
      navigateTo: 'storyboard',
      refreshProjectData: true,
    }
  }

  if (action === 'batch-generate-frames') {
    const runningFrameKeys = new Set(
      pendingTasks
        .filter((task) => task.kind === 'frame')
        .map((task) => `${task.episode}:${String(task.shotId)}`),
    )

    const executableShots = Object.entries(shotsByEpisode).flatMap(([episode, shots]) =>
      shots
        .filter((shot) => !hasGeneratedFrame(shot))
        .filter((shot) => !runningFrameKeys.has(`${Number(episode)}:${String(shot.shot_id)}`))
        .map((shot) => ({ episode: Number(episode), shotId: String(shot.shot_id) })),
    )

    if (executableShots.length === 0) {
      throw new Error('当前没有可批量补首帧的镜头，缺图镜头可能已在执行中或已经完成。')
    }

    let startedCount = 0
    let failedCount = 0
    let pendingRecoveryCount = 0
    const failedTargets: string[] = []

    for (const target of executableShots) {
      const response = await fetch(`/api/books/${bookId}/storyboard/${target.episode}/${target.shotId}/generate-frame`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ compileIfMissing: true, confirmed: true, allowExternalCall: true }),
      })

      if (!response.ok) {
        failedCount += 1
        failedTargets.push(`第 ${target.episode} 集 / 镜头 ${target.shotId}`)
        continue
      }

      const payload = await response.json().catch(() => ({}))
      const taskId = String(payload.task_id || '').trim()
      if (!taskId) {
        failedCount += 1
        failedTargets.push(`第 ${target.episode} 集 / 镜头 ${target.shotId}`)
        continue
      }

      startedCount += 1
      upsertPendingStoryboardTask(bookId, {
        taskId,
        episode: target.episode,
        shotId: target.shotId,
        kind: 'frame',
        updatedAt: new Date().toISOString(),
      })

      const taskPayload = await waitForCreativeTask(taskId, fetchTaskStatus, {
        softTimeoutMs: 2000,
        pollIntervalMs: 500,
        maxAttempts: 6,
      })

      if (taskPayload.status === 'done') {
        removePendingStoryboardTask(bookId, taskId)
      } else if (taskPayload.status === 'error') {
        failedCount += 1
        removePendingStoryboardTask(bookId, taskId)
        failedTargets.push(`第 ${target.episode} 集 / 镜头 ${target.shotId}`)
      } else {
        pendingRecoveryCount += 1
      }
    }

    const summary =
      failedCount > 0
        ? `已启动 ${startedCount} 个首帧任务，待回收 ${pendingRecoveryCount} 个，失败 ${failedCount} 个：${failedTargets.slice(0, 3).join('、')}${failedTargets.length > 3 ? ' 等' : ''}。`
        : `已启动 ${startedCount} 个首帧任务${pendingRecoveryCount > 0 ? `，其中 ${pendingRecoveryCount} 个已接回任务中心继续回收` : '，已尽可能直接回写结果'}。`

    return {
      taskIdForRecord: 'task-batch-assets',
      status: failedCount > 0 ? 'error' : 'success',
      summary,
      successCount: startedCount,
      failedCount,
      pendingRecoveryCount,
      failedTargets,
      navigateTo: 'storyboard',
      refreshPendingStoryboardTasks: true,
      refreshProjectData: true,
    }
  }

  if (action === 'batch-generate-videos') {
    const runningVideoKeys = new Set(
      pendingTasks
        .filter((task) => task.kind === 'video')
        .map((task) => `${task.episode}:${String(task.shotId)}`),
    )

    const executableShots = Object.entries(shotsByEpisode).flatMap(([episode, shots]) =>
      shots
        .map((shot) => {
          const adoptedImage = findAdoptedMediaAsset(shot.assets?.images)
          const adoptedImagePreviewUrl = String(adoptedImage?.previewUrl || adoptedImage?.uri || '').trim()
          return {
            episode: Number(episode),
            shotId: String(shot.shot_id),
            firstFrameAssetId: String(adoptedImage?.id || '').trim(),
            firstFrameUrl: adoptedImagePreviewUrl,
            referenceAssetIds: getShotReferenceAssetIds(shot),
            hasVideo: hasGeneratedVideo(shot),
          }
        })
        .filter((shot) => shot.firstFrameAssetId && shot.firstFrameUrl && !shot.hasVideo)
        .filter((shot) => !runningVideoKeys.has(`${shot.episode}:${shot.shotId}`)),
    )

    if (executableShots.length === 0) {
      throw new Error('当前没有可批量补视频的镜头，需先存在已采纳且可预览的首帧。')
    }

    let startedCount = 0
    let failedCount = 0
    let pendingRecoveryCount = 0
    const failedTargets: string[] = []

    for (const target of executableShots) {
      const response = await fetch(`/api/books/${bookId}/storyboard/${target.episode}/${target.shotId}/generate-video`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          confirmed: true,
          allowExternalCall: true,
          compileIfMissing: true,
          firstFrameAssetId: target.firstFrameAssetId,
          referenceAssetIds: target.referenceAssetIds,
        }),
      })

      if (!response.ok) {
        failedCount += 1
        failedTargets.push(`第 ${target.episode} 集 / 镜头 ${target.shotId}`)
        continue
      }

      const payload = await response.json().catch(() => ({}))
      const taskId = String(payload.task_id || '').trim()
      if (!taskId) {
        failedCount += 1
        failedTargets.push(`第 ${target.episode} 集 / 镜头 ${target.shotId}`)
        continue
      }

      startedCount += 1
      upsertPendingStoryboardTask(bookId, {
        taskId,
        episode: target.episode,
        shotId: target.shotId,
        kind: 'video',
        updatedAt: new Date().toISOString(),
      })

      const taskPayload = await waitForCreativeTask(taskId, fetchTaskStatus, {
        softTimeoutMs: 2000,
        pollIntervalMs: 500,
        maxAttempts: 6,
      })

      if (taskPayload.status === 'done') {
        removePendingStoryboardTask(bookId, taskId)
      } else if (taskPayload.status === 'error') {
        failedCount += 1
        removePendingStoryboardTask(bookId, taskId)
        failedTargets.push(`第 ${target.episode} 集 / 镜头 ${target.shotId}`)
      } else {
        pendingRecoveryCount += 1
      }
    }

    const summary =
      failedCount > 0
        ? `已启动 ${startedCount} 个视频任务，待回收 ${pendingRecoveryCount} 个，失败 ${failedCount} 个：${failedTargets.slice(0, 3).join('、')}${failedTargets.length > 3 ? ' 等' : ''}。`
        : `已启动 ${startedCount} 个视频任务${pendingRecoveryCount > 0 ? `，其中 ${pendingRecoveryCount} 个已接回任务中心继续回收` : '，已尽可能直接回写结果'}。`

    return {
      taskIdForRecord: 'task-batch-assets',
      status: failedCount > 0 ? 'error' : 'success',
      summary,
      successCount: startedCount,
      failedCount,
      pendingRecoveryCount,
      failedTargets,
      navigateTo: 'storyboard',
      refreshPendingStoryboardTasks: true,
      refreshProjectData: true,
    }
  }

  const actionableEpisodes = qaWorkbenchEpisodes
    .filter((item) => item.openIssueCount > 0 || item.inProgressCount > 0)
    .map((item) => item.episode)

  if (actionableEpisodes.length === 0) {
    throw new Error('当前没有需要批量处理的 QA 集数。')
  }

  let successCount = 0
  let failedCount = 0
  const failedEpisodes: number[] = []

  for (const episode of actionableEpisodes) {
    const endpoint =
      action === 'batch-qa-autofix'
        ? `/api/books/${bookId}/qa/episodes/${episode}/auto-fix`
        : `/api/books/${bookId}/qa/episodes/${episode}/recheck`
    const requestInit =
      action === 'batch-qa-autofix'
        ? {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              mode: 'auto',
              rerunQa: true,
              operatorName: 'task-center-batch',
              maxIssues: 10,
            }),
          }
        : { method: 'POST' }

    const response = await fetch(endpoint, requestInit)
    if (response.ok) {
      successCount += 1
    } else {
      failedCount += 1
      failedEpisodes.push(episode)
    }
  }

  const summary =
    action === 'batch-qa-autofix'
      ? failedCount > 0
        ? `已批量提交 ${successCount} 集 QA 自动修复，失败 ${failedCount} 集：${failedEpisodes
            .slice(0, 3)
            .map((episode) => `第 ${episode} 集`)
            .join('、')}。`
        : `已为 ${successCount} 集提交 QA 自动修复，并回到 QA 工作台继续跟进。`
      : failedCount > 0
        ? `已批量触发 ${successCount} 集复检，失败 ${failedCount} 集：${failedEpisodes
            .slice(0, 3)
            .map((episode) => `第 ${episode} 集`)
            .join('、')}。`
        : `已为 ${successCount} 集触发 QA 复检，并回到 QA 工作台继续跟进。`

  return {
    taskIdForRecord: 'task-batch-qa',
    status: failedCount > 0 ? 'error' : 'success',
    summary,
    successCount,
    failedCount,
    failedTargets: failedEpisodes.map((episode) => `第 ${episode} 集`),
    navigateTo: 'qa',
    refreshQaWorkbench: true,
    refreshProjectData: true,
  }
}
