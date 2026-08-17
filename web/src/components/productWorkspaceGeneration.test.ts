import { describe, expect, it, vi } from 'vitest'
import { getStoryboardGenerationLabels, waitForCreativeTask } from './productWorkspaceGeneration'

describe('productWorkspaceGeneration', () => {
  it('returns copy for frame and video actions', () => {
    expect(getStoryboardGenerationLabels('frame').noun).toBe('首帧')
    expect(getStoryboardGenerationLabels('video').noun).toBe('视频')
  })

  it('resolves when task finishes before timeout', async () => {
    const fetchTask = vi
      .fn()
      .mockResolvedValueOnce({ task_id: 'abc', status: 'running' })
      .mockResolvedValueOnce({ task_id: 'abc', status: 'done' })

    const result = await waitForCreativeTask('abc', fetchTask, {
      softTimeoutMs: 1000,
      pollIntervalMs: 0,
      maxAttempts: 3,
    })

    expect(result).toMatchObject({ task_id: 'abc', status: 'done' })
  })

  it('returns soft timeout when task keeps running', async () => {
    const fetchTask = vi.fn().mockResolvedValue({ task_id: 'abc', status: 'running' })
    const result = await waitForCreativeTask('abc', fetchTask, {
      softTimeoutMs: 0,
      pollIntervalMs: 0,
      maxAttempts: 1,
    })

    expect(result).toEqual({ status: 'soft_timeout', task_id: 'abc' })
  })

  it('reconciles after soft timeout and returns done result', async () => {
    const fetchTask = vi.fn().mockResolvedValue({ task_id: 'abc', status: 'running' })
    const reconcileTask = vi.fn().mockResolvedValue({ task_id: 'abc', status: 'done' })

    const result = await waitForCreativeTask('abc', fetchTask, {
      softTimeoutMs: 0,
      pollIntervalMs: 0,
      maxAttempts: 1,
      reconcileTask,
      reconcileAttempts: 1,
      reconcilePollIntervalMs: 0,
    })

    expect(reconcileTask).toHaveBeenCalledWith('abc')
    expect(result).toMatchObject({ task_id: 'abc', status: 'done' })
  })

  it('reconciles provider-running error tasks before surfacing error', async () => {
    const fetchTask = vi.fn().mockResolvedValue({
      task_id: 'abc',
      status: 'error',
      external_task_id: 'ext-1',
      external_status: 'running',
      error: 'timeout',
    })
    const reconcileTask = vi.fn().mockResolvedValue({ task_id: 'abc', status: 'done' })

    const result = await waitForCreativeTask('abc', fetchTask, {
      softTimeoutMs: 1000,
      pollIntervalMs: 0,
      maxAttempts: 1,
      reconcileTask,
      reconcileAttempts: 1,
      reconcilePollIntervalMs: 0,
    })

    expect(reconcileTask).toHaveBeenCalledWith('abc')
    expect(result).toMatchObject({ task_id: 'abc', status: 'done' })
  })
})
