export type StoryboardGenerationKind = 'frame' | 'video'

export interface CreativeTaskPayload {
  task_id?: string
  status?: string
  error?: string
  external_task_id?: string | null
  external_status?: string | null
  version?: string | number | null
  prompt_version?: string | number | null
  repair_attempted?: boolean | null
}

export interface WaitForCreativeTaskOptions {
  softTimeoutMs?: number
  pollIntervalMs?: number
  maxAttempts?: number
  reconcileTask?: ((taskId: string) => Promise<CreativeTaskPayload>) | null
  reconcileAttempts?: number
  reconcilePollIntervalMs?: number
}

export function getStoryboardGenerationLabels(kind: StoryboardGenerationKind) {
  if (kind === 'frame') {
    return {
      noun: '首帧',
      action: '生成分镜图',
      success: '首帧已生成并写回镜头。',
      pending: '首帧任务仍在模型侧执行，可以稍后继续回收结果。',
      recovered: '首帧结果已回收并写回镜头。',
    }
  }

  return {
    noun: '视频',
    action: '生成视频',
    success: '视频已生成并写回镜头。',
    pending: '视频任务仍在模型侧执行，可以稍后继续回收结果。',
    recovered: '视频结果已回收并写回镜头。',
  }
}

export async function waitForCreativeTask(
  taskId: string,
  fetchTask: (taskId: string) => Promise<CreativeTaskPayload>,
  options: WaitForCreativeTaskOptions = {},
): Promise<CreativeTaskPayload | { status: 'soft_timeout'; task_id: string }> {
  const startedAt = Date.now()
  const softTimeoutMs = options.softTimeoutMs ?? 45000
  const pollIntervalMs = options.pollIntervalMs ?? 1000
  const maxAttempts = options.maxAttempts ?? 180
  const reconcileTask = options.reconcileTask ?? null
  const reconcileAttempts = options.reconcileAttempts ?? 6
  const reconcilePollIntervalMs = options.reconcilePollIntervalMs ?? 3000

  async function waitLoop(maxLoopAttempts: number, delayMs: number) {
    for (let attempt = 0; attempt < maxLoopAttempts; attempt += 1) {
      const payload = await fetchTask(taskId)
      if (payload.status === 'done' || payload.status === 'error') {
        return payload
      }
      if (Date.now() - startedAt >= softTimeoutMs) {
        return { status: 'soft_timeout', task_id: taskId } as const
      }
      await new Promise((resolve) => globalThis.setTimeout(resolve, delayMs))
    }
    return { status: 'soft_timeout', task_id: taskId } as const
  }

  const initial = await waitLoop(maxAttempts, pollIntervalMs)
  if (initial.status === 'done') {
    return initial
  }
  if (initial.status === 'error') {
    const canRecover = Boolean(reconcileTask && (initial.external_task_id || initial.external_status === 'running'))
    if (!canRecover) {
      return initial
    }
  }
  if (!reconcileTask) {
    return initial
  }

  const shouldReconcile = initial.status === 'soft_timeout' || initial.status === 'error' || initial.status === 'running'
  if (!shouldReconcile) {
    return initial
  }

  for (let attempt = 0; attempt < reconcileAttempts; attempt += 1) {
    const reconciled = await reconcileTask(taskId)
    if (reconciled.status === 'done' || reconciled.status === 'error') {
      return reconciled
    }
    await new Promise((resolve) => globalThis.setTimeout(resolve, reconcilePollIntervalMs))
  }

  return { status: 'soft_timeout', task_id: taskId }
}
