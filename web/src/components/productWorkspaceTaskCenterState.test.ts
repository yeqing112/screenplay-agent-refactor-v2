import { describe, expect, it } from 'vitest'
import { inferEpisodeFromTask, inferRecoveryIntentFromTask, inferShotIdFromTask } from './productWorkspaceTaskCenterState'
import type { TaskCenterEntry } from './productWorkspaceTasks'

function makeTask(overrides: Partial<TaskCenterEntry> = {}): TaskCenterEntry {
  return {
    id: 'task-batch-prompts',
    type: '批量提示词编译',
    target: '全项目镜头提示词',
    status: 'error',
    progress: '2 个镜头提示词待恢复',
    detail: '存在跑偏镜头',
    retryable: false,
    actionLabel: '前往首个恢复镜头',
    actionTarget: 'storyboard',
    episode: null,
    scope: 'global',
    isBatch: true,
    ...overrides,
  }
}

describe('productWorkspaceTaskCenterState', () => {
  it('infers the first recommended restore shot and episode from prompt health payload', () => {
    const task = makeTask({
      promptHealth: {
        degradedShotCount: 2,
        recommendedRestoreCount: 1,
        degradedShots: [
          {
            episode: 2,
            shotId: '2-03',
            recommendedRestoreVersion: null,
          },
          {
            episode: 1,
            shotId: '1-02',
            recommendedRestoreVersion: 9,
          },
        ],
      },
    })

    expect(inferEpisodeFromTask(task)).toBe(1)
    expect(inferShotIdFromTask(task)).toBe('1-02')
  })

  it('falls back to the first degraded shot when no recommended restore version exists', () => {
    const task = makeTask({
      promptHealth: {
        degradedShotCount: 2,
        recommendedRestoreCount: 0,
        degradedShots: [
          {
            episode: 3,
            shotId: '3-01',
            recommendedRestoreVersion: null,
          },
          {
            episode: 3,
            shotId: '3-02',
            recommendedRestoreVersion: null,
          },
        ],
      },
    })

    expect(inferEpisodeFromTask(task)).toBe(3)
    expect(inferShotIdFromTask(task)).toBe('3-01')
  })

  it('marks character reference recovery tasks as shot-variant refinement when a shot context exists', () => {
    const task = makeTask({
      id: 'task-recovery-ref-1',
      recoveryKind: 'reference',
      shotId: '13',
      creativeTaskMeta: {
        assetScope: 'character',
        assetSubject: '和尚甲',
        sourceAssetId: '21',
      },
    })

    expect(inferRecoveryIntentFromTask(task)).toBe('shot_variant_refinement')
  })

  it('keeps non-character reference recovery tasks on generic reference intent', () => {
    const task = makeTask({
      id: 'task-recovery-ref-2',
      recoveryKind: 'reference',
      shotId: '13',
      creativeTaskMeta: {
        assetScope: 'scene',
        assetSubject: '寺庙后山乱葬岗',
        sourceAssetId: '137',
      },
    })

    expect(inferRecoveryIntentFromTask(task)).toBe('reference')
  })

  it('can still infer shot-variant refinement from a local character asset id without provider metadata', () => {
    const task = makeTask({
      id: 'task-recovery-ref-3',
      recoveryKind: 'reference',
      shotId: '13',
      assetId: 'character-21',
      creativeTaskMeta: undefined,
    })

    expect(inferRecoveryIntentFromTask(task)).toBe('shot_variant_refinement')
  })
})
