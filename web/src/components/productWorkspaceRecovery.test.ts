import { describe, expect, it } from 'vitest'

import { summarizePendingStoryboardTasks, type PendingStoryboardTask } from './productWorkspaceRecovery'

function makeTask(overrides: Partial<PendingStoryboardTask> = {}): PendingStoryboardTask {
  return {
    taskId: 'task-001',
    episode: 1,
    shotId: '1-01',
    kind: 'frame',
    updatedAt: '2026-07-29T09:00:00.000Z',
    ...overrides,
  }
}

describe('summarizePendingStoryboardTasks', () => {
  it('returns empty defaults when there are no pending tasks', () => {
    expect(summarizePendingStoryboardTasks([])).toEqual({
      count: 0,
      kindLabels: [],
      joinedKindLabels: '无',
      latestUpdatedAt: null,
      latestTaskId: null,
      latestKindLabel: null,
      latestSourceLabel: null,
    })
  })

  it('sorts by latest update time and includes source label context', () => {
    const summary = summarizePendingStoryboardTasks([
      makeTask({
        taskId: 'task-video-002',
        kind: 'video',
        updatedAt: '2026-07-29T11:00:00.000Z',
        assetLabel: '姐姐 / 夜戏造型',
      }),
      makeTask({
        taskId: 'task-prompt-003',
        kind: 'prompt',
        updatedAt: '2026-07-29T10:00:00.000Z',
      }),
      makeTask({
        taskId: 'task-frame-001',
        kind: 'frame',
        updatedAt: '2026-07-29T09:00:00.000Z',
      }),
    ])

    expect(summary.count).toBe(3)
    expect(summary.kindLabels).toEqual(['视频', '提示词编译', '首帧'])
    expect(summary.joinedKindLabels).toBe('视频 / 提示词编译 / 首帧')
    expect(summary.latestUpdatedAt).toBe('2026-07-29T11:00:00.000Z')
    expect(summary.latestTaskId).toBe('task-video-002')
    expect(summary.latestKindLabel).toBe('视频')
    expect(summary.latestSourceLabel).toBe('视频 / 姐姐 / 夜戏造型')
  })
})
