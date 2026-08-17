import { beforeEach, describe, expect, it, vi } from 'vitest'

const recoveryMocks = vi.hoisted(() => ({
  fetchStoryboardRecoveryTaskStatus: vi.fn(),
  reconcileStoryboardRecoveryTask: vi.fn(),
  removePendingStoryboardTask: vi.fn(),
  restartStoryboardRecoveryTask: vi.fn(),
  upsertRecoveryTaskMeta: vi.fn(),
  upsertPendingStoryboardTask: vi.fn(),
}))

vi.mock('./productWorkspaceRecovery', () => recoveryMocks)

import { executeRecoveryTaskAction } from './productWorkspaceTaskRecoveryActions'

describe('productWorkspaceTaskRecoveryActions', () => {
  beforeEach(() => {
    Object.values(recoveryMocks).forEach((mock) => mock.mockReset())
  })

  it('marks refreshProjectData when reconcile finishes and removes the pending task', async () => {
    recoveryMocks.reconcileStoryboardRecoveryTask.mockResolvedValue({
      task_id: 'task-1',
      status: 'done',
    })

    const result = await executeRecoveryTaskAction('recovery-reconcile', {
      bookId: 12,
      taskId: 'task-1',
      episode: 1,
      shotId: '3',
      kind: 'video',
    })

    expect(recoveryMocks.removePendingStoryboardTask).toHaveBeenCalledWith(12, 'task-1')
    expect(result).toMatchObject({
      outcome: 'status',
      taskId: 'task-1',
      removedFromPending: true,
      refreshProjectData: true,
    })
  })

  it('does not mark refreshProjectData when restart only requeues the task', async () => {
    recoveryMocks.restartStoryboardRecoveryTask.mockResolvedValue({
      task_id: 'task-2b',
      restarted_from_task_id: 'task-2a',
      status: 'queued',
    })

    const result = await executeRecoveryTaskAction('recovery-restart', {
      bookId: 12,
      taskId: 'task-2a',
      episode: 1,
      shotId: '5',
      kind: 'frame',
      restartCount: 1,
    })

    expect(recoveryMocks.upsertPendingStoryboardTask).toHaveBeenCalled()
    expect(result).toMatchObject({
      outcome: 'restarted',
      previousTaskId: 'task-2a',
      newTaskId: 'task-2b',
      refreshProjectData: false,
    })
  })
})
