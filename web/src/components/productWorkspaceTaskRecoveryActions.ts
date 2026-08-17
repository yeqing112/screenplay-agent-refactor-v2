import {
  fetchStoryboardRecoveryTaskStatus,
  reconcileStoryboardRecoveryTask,
  removePendingStoryboardTask,
  restartStoryboardRecoveryTask,
  upsertRecoveryTaskMeta,
  upsertPendingStoryboardTask,
  type CreativeTaskStatusPayload,
} from './productWorkspaceRecovery'

export type RecoveryTaskAction =
  | 'recovery-refresh'
  | 'recovery-reconcile'
  | 'recovery-restart'
  | 'recovery-regenerate-latest'

export type RecoveryTaskExecutionInput = {
  bookId: number
  taskId: string
  episode: number
  shotId: string
  kind: 'frame' | 'video' | 'reference' | 'prompt'
  assetId?: string
  assetLabel?: string
  restartCount?: number
}

export type RecoveryTaskExecutionResult =
  | {
      outcome: 'restarted'
      action: RecoveryTaskAction
      previousTaskId: string
      newTaskId: string
      message: string
      statusPayload: CreativeTaskStatusPayload & { restarted_from_task_id?: string }
      refreshProjectData: false
    }
  | {
      outcome: 'status'
      action: RecoveryTaskAction
      taskId: string
      message: string
      statusPayload: CreativeTaskStatusPayload
      removedFromPending: boolean
      refreshProjectData: boolean
    }

export async function executeRecoveryTaskAction(
  action: RecoveryTaskAction,
  input: RecoveryTaskExecutionInput,
): Promise<RecoveryTaskExecutionResult> {
  if (action === 'recovery-restart') {
    const payload = await restartStoryboardRecoveryTask({ taskId: input.taskId, kind: input.kind, bookId: input.bookId, episode: input.episode, shotId: input.shotId })
    const newTaskId = String(payload.task_id || '').trim()
    if (!newTaskId) {
      throw new Error('重新发起失败：服务端未返回新的 task_id。')
    }

    const restartedAt = new Date().toISOString()
    removePendingStoryboardTask(input.bookId, input.taskId)
    upsertPendingStoryboardTask(input.bookId, {
      taskId: newTaskId,
      episode: input.episode,
      shotId: input.shotId,
      kind: input.kind,
      updatedAt: restartedAt,
      assetId: input.assetId,
      assetLabel: input.assetLabel,
      restartedFromTaskId: String(payload.restarted_from_task_id || input.taskId || '').trim() || undefined,
      restartCount: Number(input.restartCount ?? 0) + 1,
      lastRestartedAt: restartedAt,
    })
    upsertRecoveryTaskMeta(input.bookId, newTaskId, {
      restartedFromTaskId: String(payload.restarted_from_task_id || input.taskId || '').trim() || undefined,
      restartCount: Number(input.restartCount ?? 0) + 1,
      lastRestartedAt: restartedAt,
    })

    return {
      outcome: 'restarted',
      action,
      previousTaskId: input.taskId,
      newTaskId,
      message: `已重新发起任务 ${newTaskId}，来源任务 ${input.taskId}，并重新接回任务中心。`,
      statusPayload: payload,
      refreshProjectData: false,
    }
  }

  const payload =
    action === 'recovery-refresh'
      ? await fetchStoryboardRecoveryTaskStatus({ taskId: input.taskId, kind: input.kind })
      : await reconcileStoryboardRecoveryTask({ taskId: input.taskId, kind: input.kind })

  let removedFromPending = false
  if (payload.status === 'done') {
    removePendingStoryboardTask(input.bookId, input.taskId)
    removedFromPending = true
  }

  const message =
    payload.status === 'done'
      ? '任务结果已回收并回写到项目数据。'
      : payload.status === 'error'
        ? String(payload.error || '任务恢复失败。')
        : payload.status === 'not_found'
          ? '任务在服务端已不存在，请直接重新发起。'
          : action === 'recovery-refresh'
            ? `任务仍在执行${payload.external_status ? `，provider 状态：${payload.external_status}` : ''}。`
            : `已继续回收任务${payload.external_status ? `，provider 状态：${payload.external_status}` : ''}。`

  return {
    outcome: 'status',
    action,
    taskId: input.taskId,
    message,
    statusPayload: payload,
    removedFromPending,
    refreshProjectData: removedFromPending,
  }
}
