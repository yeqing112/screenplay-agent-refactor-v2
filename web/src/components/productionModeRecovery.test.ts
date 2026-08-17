import { describe, expect, it } from 'vitest'

import { deriveRecoverTaskIdFromError } from './ProductionMode'

describe('ProductionMode recovery helpers', () => {
  it('returns task id for recoverable timeout errors', () => {
    const error = new Error('Generation timed out. The task may still be running on the provider side.') as Error & { taskId?: string }
    error.taskId = 'task-123'

    expect(deriveRecoverTaskIdFromError(error)).toBe('task-123')
  })

  it('returns task id for recoverable rate-limit errors', () => {
    const error = new Error('PoYo 查询任务状态时遇到限流（HTTP 429），任务可能仍在 provider 侧继续执行。请稍后重试或继续拉取结果。') as Error & { taskId?: string }
    error.taskId = 'task-429'

    expect(deriveRecoverTaskIdFromError(error)).toBe('task-429')
  })

  it('returns null for non-recoverable errors', () => {
    const error = new Error('Provider authentication failed') as Error & { taskId?: string }
    error.taskId = 'task-456'

    expect(deriveRecoverTaskIdFromError(error)).toBeNull()
  })

  it('returns null for unknown thrown values', () => {
    expect(deriveRecoverTaskIdFromError('timeout')).toBeNull()
  })
})
