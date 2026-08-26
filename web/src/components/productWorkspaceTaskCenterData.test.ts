import { describe, expect, it } from 'vitest'

import {
  buildQaWorkbenchSummary,
  buildRecoveryTaskEntries,
  normalizeTaskPreviewImageUrl,
} from './productWorkspaceTaskCenterData'

describe('productWorkspaceTaskCenterData', () => {
  it('drops legacy prototyping asset preview urls before the browser requests missing files', () => {
    expect(normalizeTaskPreviewImageUrl('/api/prototyping/assets/image-stale')).toBe('')
    expect(normalizeTaskPreviewImageUrl('http://127.0.0.1:5173/api/prototyping/assets/image-stale')).toBe('')
    expect(normalizeTaskPreviewImageUrl('data:image/svg+xml,%3Csvg%3E%3C/svg%3E')).toContain('data:image')
    expect(normalizeTaskPreviewImageUrl('https://example.com/frame.png')).toBe('https://example.com/frame.png')
  })

  it('keeps legacy creative task ids but omits missing preview urls from task-center meta', () => {
    const entries = buildRecoveryTaskEntries(
      [],
      {},
      [
        {
          task_id: 'task-stale-preview',
          status: 'done',
          kind: 'video',
          episode: 1,
          shot_id: '1',
          first_frame_asset_id: 'image-stale',
          first_frame_url: '/api/prototyping/assets/image-stale',
          reference_asset_ids: ['ref-stale', 'ref-live'],
          reference_images: [
            {
              reference_asset_id: 'ref-stale',
              image_url: '/api/prototyping/assets/image-stale-ref',
              asset_name: '旧占位参考图',
            },
            {
              reference_asset_id: 'ref-live',
              image_url: 'https://example.com/live-ref.png',
              asset_name: '有效参考图',
            },
          ],
        },
      ] as any,
      {},
      {
        1: [
          {
            shot_id: '1',
            scene_name: 'Tea house',
          },
        ] as any,
      },
    )

    expect(entries[0].creativeTaskMeta).toMatchObject({
      firstFrameAssetId: 'image-stale',
      firstFrameUrl: undefined,
      referenceAssetIds: ['ref-stale', 'ref-live'],
      referenceImages: [
        {
          referenceAssetId: 'ref-live',
          imageUrl: 'https://example.com/live-ref.png',
          title: '有效参考图',
        },
      ],
    })
  })

  it('treats recheck_passed issues as resolved instead of open', () => {
    const summary = buildQaWorkbenchSummary({
      episodes: [
        {
          episode: 1,
          issues: [
            { severity: 'high', fix_status: 'pending' },
            { severity: 'medium', fix_status: 'rechecking' },
            { severity: 'low', fix_status: 'recheck_passed' },
          ],
        },
      ],
    })

    expect(summary[0]).toMatchObject({
      episode: 1,
      totalIssueCount: 3,
      openIssueCount: 1,
      highOpenIssueCount: 1,
      inProgressCount: 1,
      resolvedCount: 1,
    })
  })

  it('uses shot-variant recovery routing for character reference tasks with shot context', () => {
    const entries = buildRecoveryTaskEntries(
      [
        {
          taskId: 'task-ref-13',
          episode: 1,
          shotId: '13',
          kind: 'reference',
          updatedAt: '2026-07-26T12:00:00.000Z',
          assetLabel: 'Monk A',
          assetId: 'character-21',
        },
      ],
      {
        'task-ref-13': {
          task_id: 'task-ref-13',
          status: 'running',
          kind: 'reference',
          episode: 1,
          shot_id: '13',
          request_payload: {
            asset_scope: 'character',
            asset_subject: 'Monk A',
            source_asset_id: '21',
          },
        },
      },
      [],
      {},
      {
        1: [
          {
            shot_id: '13',
            scene_name: 'Temple yard',
          },
        ] as any,
      },
    )

    expect(entries[0]).toMatchObject({
      actionTarget: 'assets',
      assetId: 'character-21',
      recoveryKind: 'reference',
    })
    expect(entries[0].detail).toContain('task-ref-13')
  })

  it('surfaces prompt-recompile generation chain metadata for storyboard video tasks', () => {
    const entries = buildRecoveryTaskEntries(
      [
        {
          taskId: 'task-video-21',
          episode: 2,
          shotId: '21',
          kind: 'video',
          updatedAt: '2026-07-27T09:00:00.000Z',
        },
      ],
      {
        'task-video-21': {
          task_id: 'task-video-21',
          status: 'running',
          kind: 'video',
          episode: 2,
          shot_id: '21',
          request_payload: {
            generation_chain: 'recompile_then_video',
            triggered_by_prompt_recompile: true,
            prompt_recompile_reason: 'manual-recompile-before-video',
            prompt_recompile_task_id: 'prompt-7788',
            prompt_recompile_version: 12,
            first_frame_asset_id: 'frame-001',
            reference_asset_ids: ['asset-a', 'asset-b'],
          },
        },
      },
      [],
      {},
      {
        2: [
          {
            shot_id: '21',
            scene_name: 'Kitchen',
            prompt_version: 15,
          },
        ] as any,
      },
    )

    expect(entries[0].detail).toContain('task-video-21')
    expect(entries[0].creativeTaskMeta).toMatchObject({
      generationChain: 'recompile_then_video',
      triggeredByPromptRecompile: true,
      promptRecompileReason: 'manual-recompile-before-video',
      promptRecompileTaskId: 'prompt-7788',
      promptRecompileVersion: 12,
      taskPromptVersion: 12,
      currentShotPromptVersion: 15,
      promptVersionDrift: 3,
      firstFrameAssetId: 'frame-001',
      referenceAssetIds: ['asset-a', 'asset-b'],
    })
  })

  it('describes latest-state regeneration tasks with current-shot input semantics', () => {
    const entries = buildRecoveryTaskEntries(
      [
        {
          taskId: 'task-video-22',
          episode: 2,
          shotId: '22',
          kind: 'video',
          updatedAt: '2026-07-27T11:00:00.000Z',
        },
      ],
      {
        'task-video-22': {
          task_id: 'task-video-22',
          status: 'running',
          kind: 'video',
          episode: 2,
          shot_id: '22',
          request_payload: {
            generation_chain: 'task_center_regenerate_latest_video',
            first_frame_asset_id: 'image-latest-01',
            reference_asset_ids: ['ref-a'],
            prompt_version: 19,
          },
        },
      },
      [],
      {},
      {
        2: [
          {
            shot_id: '22',
            scene_name: 'Courtyard',
            prompt_version: 19,
          },
        ] as any,
      },
    )

    expect(entries[0].detail).toContain('按最新镜头状态重生成视频')
    expect(entries[0].creativeTaskMeta).toMatchObject({
      generationChain: 'task_center_regenerate_latest_video',
      taskPromptVersion: 19,
      currentShotPromptVersion: 19,
      promptVersionDrift: 0,
      firstFrameAssetId: 'image-latest-01',
      referenceAssetIds: ['ref-a'],
    })
  })

  it('describes recovery-continue generation chains as recovery-derived follow-up work', () => {
    const entries = buildRecoveryTaskEntries(
      [
        {
          taskId: 'task-video-23',
          episode: 1,
          shotId: '1',
          kind: 'video',
          updatedAt: '2026-07-29T20:00:00.000Z',
        },
      ],
      {
        'task-video-23': {
          task_id: 'task-video-23',
          status: 'running',
          kind: 'video',
          episode: 1,
          shot_id: '1',
          request_payload: {
            generation_chain: 'canvas_recovery_continue_after_frame',
          },
        },
      },
      [],
      {},
      {
        1: [
          {
            shot_id: '1',
            scene_name: 'Water room',
          },
        ] as any,
      },
    )

    expect(entries[0].detail).toContain('真实创意任务恢复链路')
    expect(entries[0].creativeTaskMeta).toMatchObject({
      generationChain: 'canvas_recovery_continue_after_frame',
    })
  })
})
