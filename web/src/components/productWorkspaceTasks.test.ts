import { describe, expect, it } from 'vitest'
import { buildTaskCenterEntries } from './productWorkspaceTasks'

describe('productWorkspaceTasks', () => {
  it('builds episode tasks and batch tasks together', () => {
    const entries = buildTaskCenterEntries({
      contentReady: true,
      adaptationLocked: true,
      adaptationReadyForDownstream: true,
      contentTask: {
        mode: 'upload',
        status: 'done',
        message: '导入完成',
        taskId: 'task-1',
      },
      scripts: [{ episode: 1, content: 'script' }],
      scriptDecisionState: {
        '1': {
          lockedAt: '2026-07-06T10:00:00.000Z',
          releasedAt: '2026-07-06T10:10:00.000Z',
          note: '',
        },
      },
      shotsByEpisode: {
        1: [
          {
            shot_id: '1-01',
            scene_name: '天台',
            visual_prompt_static: 'static',
            visual_prompt_motion: 'motion',
            assets: {
              images: [{ id: 'img-1' }],
              videos: [],
              audios: [],
              references: {
                characters: { 姐姐: [{ id: 'ref-1' }] },
                scene: [{ id: 'ref-scene' }],
                props: {},
              },
            },
          },
        ] as any,
      },
      qaEntries: [{ episode: 1, error_count: 2 }],
      qaWorkbenchEpisodes: [
        {
          episode: 1,
          totalIssueCount: 5,
          openIssueCount: 3,
          highOpenIssueCount: 2,
          inProgressCount: 1,
          resolvedCount: 2,
        },
      ],
    })

    expect(entries.find((item) => item.id === 'task-content-import')).toMatchObject({
      status: 'done',
      scope: 'global',
    })
    expect(entries.find((item) => item.id === 'task-script-1')).toMatchObject({
      status: 'done',
      progress: '已锁稿并放行',
      scope: 'episode',
    })
    expect(entries.find((item) => item.id === 'task-storyboard-1')).toMatchObject({
      status: 'done',
      progress: '1 个镜头',
    })
    expect(entries.find((item) => item.id === 'task-assets-1')).toMatchObject({
      status: 'done',
    })
    expect(entries.find((item) => item.id === 'task-qa-1')).toMatchObject({
      status: 'error',
      progress: '待处理 3/5',
      retryable: true,
      actionTarget: 'qa',
    })
    expect(entries.find((item) => item.id === 'task-batch-prompts')).toMatchObject({
      status: 'done',
      isBatch: true,
      scope: 'global',
    })
    expect(entries.find((item) => item.id === 'task-batch-assets')).toMatchObject({
      status: 'done',
      isBatch: true,
    })
    expect(entries.find((item) => item.id === 'task-batch-qa')).toMatchObject({
      status: 'running',
      isBatch: true,
    })
  })

  it('marks script and storyboard as upstream-blocked when release decision is missing', () => {
    const entries = buildTaskCenterEntries({
      contentReady: true,
      adaptationLocked: true,
      adaptationReadyForDownstream: true,
      contentTask: {
        mode: 'short',
        status: 'done',
        message: 'ok',
      },
      scripts: [{ episode: 2, content: 'script ready' }],
      scriptDecisionState: {
        '2': {
          lockedAt: '2026-07-06T10:00:00.000Z',
          releasedAt: null,
          note: '',
        },
      },
      shotsByEpisode: {},
      qaEntries: [],
      qaWorkbenchEpisodes: [],
    })

    expect(entries.find((item) => item.id === 'task-script-2')).toMatchObject({
      status: 'running',
      progress: '待放行',
      actionTarget: 'scripts',
    })
    expect(entries.find((item) => item.id === 'task-storyboard-2')).toMatchObject({
      status: 'blocked',
      progress: '待剧本放行',
      actionTarget: 'scripts',
      statusReason: '剧本未放行到分镜',
    })
  })

  it('marks storyboard blocked by adaptation before scripts exist', () => {
    const entries = buildTaskCenterEntries({
      contentReady: true,
      adaptationLocked: false,
      adaptationReadyForDownstream: false,
      contentTask: {
        mode: 'short',
        status: 'done',
        message: 'ok',
      },
      scripts: [],
      scriptDecisionState: {},
      shotsByEpisode: {},
      qaEntries: [{ episode: 5, error_count: 0 }],
      qaWorkbenchEpisodes: [],
    })

    expect(entries.find((item) => item.id === 'task-script-5')).toMatchObject({
      status: 'blocked',
      actionTarget: 'adaptation',
    })
    expect(entries.find((item) => item.id === 'task-storyboard-5')).toMatchObject({
      status: 'blocked',
      progress: '待改编方向',
      actionTarget: 'adaptation',
    })
  })

  it('marks blocked, queued, and skipped tasks when upstream is missing', () => {
    const entries = buildTaskCenterEntries({
      contentReady: false,
      adaptationLocked: false,
      adaptationReadyForDownstream: false,
      contentTask: {
        mode: 'short',
        status: 'idle',
        message: '',
      },
      scripts: [{ episode: 3, content: '' }],
      scriptDecisionState: {},
      shotsByEpisode: {},
      qaEntries: [],
      qaWorkbenchEpisodes: [],
    })

    expect(entries.find((item) => item.id === 'task-content-import')).toMatchObject({
      status: 'queued',
    })
    expect(entries.find((item) => item.id === 'task-adaptation')).toMatchObject({
      status: 'blocked',
      actionTarget: 'content',
    })
    expect(entries.find((item) => item.id === 'task-storyboard-3')).toMatchObject({
      status: 'blocked',
    })
    expect(entries.find((item) => item.id === 'task-assets-3')).toMatchObject({
      status: 'blocked',
    })
    expect(entries.find((item) => item.id === 'task-batch-prompts')).toMatchObject({
      status: 'skipped',
    })
    expect(entries.find((item) => item.id === 'task-batch-assets')).toMatchObject({
      status: 'skipped',
    })
    expect(entries.find((item) => item.id === 'task-batch-qa')).toMatchObject({
      status: 'skipped',
    })
  })

  it('marks batch QA as done when open issues are cleared', () => {
    const entries = buildTaskCenterEntries({
      contentReady: true,
      adaptationLocked: true,
      adaptationReadyForDownstream: true,
      contentTask: {
        mode: 'upload',
        status: 'done',
        message: 'ok',
      },
      scripts: [{ episode: 4, content: 'script' }],
      scriptDecisionState: {
        '4': {
          lockedAt: '2026-07-06T10:00:00.000Z',
          releasedAt: '2026-07-06T10:10:00.000Z',
          note: '',
        },
      },
      shotsByEpisode: {},
      qaEntries: [{ episode: 4, error_count: 9 }],
      qaWorkbenchEpisodes: [
        {
          episode: 4,
          totalIssueCount: 4,
          openIssueCount: 0,
          highOpenIssueCount: 0,
          inProgressCount: 0,
          resolvedCount: 4,
        },
      ],
    })

    expect(entries.find((item) => item.id === 'task-qa-4')).toMatchObject({
      status: 'done',
      progress: '已关闭 4/4',
      retryable: false,
    })
    expect(entries.find((item) => item.id === 'task-batch-qa')).toMatchObject({
      status: 'done',
      progress: '已清空 1/1 集',
    })
  })

  it('marks adaptation lock as backfill-blocked for legacy downstream projects that only borrowed the recovery path', () => {
    const entries = buildTaskCenterEntries({
      contentReady: true,
      adaptationLocked: false,
      adaptationReadyForDownstream: true,
      contentTask: {
        mode: 'upload',
        status: 'done',
        message: 'ok',
      },
      scripts: [{ episode: 1, content: 'script ready' }],
      scriptDecisionState: {
        '1': {
          lockedAt: '2026-07-06T10:00:00.000Z',
          releasedAt: '2026-07-06T10:10:00.000Z',
          note: '',
        },
      },
      shotsByEpisode: {
        1: [] as any,
      },
      qaEntries: [],
      qaWorkbenchEpisodes: [],
    })

    expect(entries.find((item) => item.id === 'task-adaptation')).toMatchObject({
      status: 'blocked',
      progress: '待补锁',
      statusReason: '历史下游已存在，但主方向未锁定',
      actionTarget: 'adaptation',
    })
    expect(entries.find((item) => item.id === 'task-script-1')).toMatchObject({
      status: 'done',
    })
  })

  it('surfaces degraded prompt versions through episode and batch task entries', () => {
    const entries = buildTaskCenterEntries({
      contentReady: true,
      adaptationLocked: true,
      adaptationReadyForDownstream: true,
      contentTask: {
        mode: 'upload',
        status: 'done',
        message: 'ok',
      },
      scripts: [{ episode: 1, content: 'script ready' }],
      scriptDecisionState: {
        '1': {
          lockedAt: '2026-07-06T10:00:00.000Z',
          releasedAt: '2026-07-06T10:10:00.000Z',
          note: '',
        },
      },
      shotsByEpisode: {
        1: [
          {
            shot_id: '1-01',
            scene_name: '寺庙院落',
            visual_prompt_static: 'static',
            visual_prompt_motion: 'motion',
            prompt_version: 11,
            prompt_version_audit: {
              is_degraded_version: true,
              missing_critical_count: 3,
              is_scene_only_candidate: true,
            },
            recommended_restore_version: {
              version: 9,
              reason: 'best_partial_recovery_version',
            },
            assets: {
              images: [],
              videos: [],
              audios: [],
              references: {
                characters: {},
                scene: [],
                props: {},
              },
            },
          },
        ] as any,
      },
      qaEntries: [],
      qaWorkbenchEpisodes: [],
    })

    expect(entries.find((item) => item.id === 'task-storyboard-1')).toMatchObject({
      status: 'error',
      actionTarget: 'storyboard',
      actionLabel: '前往首个恢复镜头',
      statusReason: '1 个镜头仅给出部分恢复版本，恢复后仍需继续修复',
      promptHealth: {
        degradedShotCount: 1,
        recommendedRestoreCount: 1,
        partialRestoreCount: 1,
        manualRepairCount: 0,
      },
    })
    expect(entries.find((item) => item.id === 'task-batch-prompts')).toMatchObject({
      status: 'error',
      isBatch: true,
      actionTarget: 'storyboard',
      actionLabel: '前往首个恢复镜头',
      statusReason: '1 个镜头仅给出部分恢复版本',
      promptHealth: {
        degradedShotCount: 1,
        recommendedRestoreCount: 1,
        partialRestoreCount: 1,
        manualRepairCount: 0,
      },
    })
  })

  it('marks degraded prompts as manual-repair-only when no recommendation remains', () => {
    const entries = buildTaskCenterEntries({
      contentReady: true,
      adaptationLocked: true,
      adaptationReadyForDownstream: true,
      contentTask: {
        mode: 'upload',
        status: 'done',
        message: 'ok',
      },
      scripts: [{ episode: 1, content: 'script ready' }],
      scriptDecisionState: {
        '1': {
          lockedAt: '2026-07-06T10:00:00.000Z',
          releasedAt: '2026-07-06T10:10:00.000Z',
          note: '',
        },
      },
      shotsByEpisode: {
        1: [
          {
            shot_id: '1-01',
            scene_name: '寺庙后院水房',
            visual_prompt_static: 'static',
            visual_prompt_motion: 'motion',
            prompt_version: 12,
            prompt_version_audit: {
              is_degraded_version: true,
              missing_critical_count: 1,
              is_scene_only_candidate: false,
            },
            recommended_restore_version: null,
            assets: {
              images: [],
              videos: [],
              audios: [],
              references: {
                characters: {},
                scene: [],
                props: {},
              },
            },
          },
        ] as any,
      },
      qaEntries: [],
      qaWorkbenchEpisodes: [],
    })

    expect(entries.find((item) => item.id === 'task-storyboard-1')).toMatchObject({
      status: 'error',
      actionLabel: '前往镜头继续修复',
      progress: '1 个镜头仍需人工修复',
      promptHealth: {
        degradedShotCount: 1,
        recommendedRestoreCount: 0,
        manualRepairCount: 1,
      },
    })
    expect(entries.find((item) => item.id === 'task-batch-prompts')).toMatchObject({
      status: 'error',
      actionLabel: '前往镜头继续修复',
      progress: '1 个镜头仍需人工修复',
      promptHealth: {
        degradedShotCount: 1,
        recommendedRestoreCount: 0,
        manualRepairCount: 1,
      },
    })
  })
})
