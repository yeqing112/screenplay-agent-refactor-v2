import { describe, expect, it } from 'vitest'

import {
  buildExportReadiness,
  buildReferencedVisualAssetSummary,
  buildShotChecklist,
  buildStoryboardReadiness,
  buildVisualAssetSummary,
} from './productionReadiness'

const hasReference = (keys: string[]) => (assetType: 'scene' | 'prop' | 'character', assetId: string) =>
  keys.includes(`${assetType}:${assetId}`)

describe('productionReadiness', () => {
  it('summarizes visual asset readiness from the same data source used by the page', () => {
    const summary = buildVisualAssetSummary({
      era: { timeline_start: 'modern' },
      locations: [
        { reference_assets: [{ status: 'selected' }, { status: 'draft' }] },
        { reference_assets: [{ status: 'locked' }] },
      ],
      props: [{ reference_assets: [{ status: 'selected' }] }],
      makeups: [{ reference_assets: [{ status: 'locked' }] }, {}],
    })

    expect(summary.ready).toBe(true)
    expect(summary.sceneCount).toBe(2)
    expect(summary.propCount).toBe(1)
    expect(summary.characterCount).toBe(2)
    expect(summary.totalAssetCount).toBe(5)
    expect(summary.selectedReferenceCount).toBe(2)
    expect(summary.lockedReferenceCount).toBe(2)
  })

  it('builds a shot checklist with structural, reference, and media gaps', () => {
    const shot = {
      episode: 1,
      shot_id: '1-1',
      prompt_version: null,
      structured_shot: {
        scene_asset_id: '11',
        character_asset_ids: ['21'],
        prop_asset_ids: ['31'],
        character_blocking: [],
        action_beats: [],
      },
      makeup_prompts: [{ character_name: 'A' }],
      assets: {
        images: [],
        videos: [],
      },
    }

    const checklist = buildShotChecklist(shot as any, hasReference([]), hasReference([]))

    expect(checklist.promptReady).toBe(false)
    expect(checklist.frameReady).toBe(false)
    expect(checklist.videoReady).toBe(false)
    expect(checklist.selectedReferenceReady).toBe(false)
    expect(checklist.lockedReferenceReady).toBe(false)
    expect(checklist.structureReady).toBe(false)
    expect(checklist.missing).toEqual(expect.arrayContaining([
      '缺提示词版本',
      '缺角色站位',
      '缺动作节拍',
      '缺已采用首帧',
      '缺已采用视频',
      '缺场景主参考图',
      '缺角色主参考图',
      '缺道具主参考图',
    ]))
  })

  it('summarizes storyboard readiness for selected episodes', () => {
    const readyShot = {
      episode: 1,
      shot_id: '1-1',
      prompt_version: 2,
      acceptance: { status: 'approved' },
      structured_shot: {
        scene_asset_id: '11',
        character_asset_ids: ['21'],
        prop_asset_ids: [],
        character_blocking: [{ character_id: '21' }],
        action_beats: [{ sequence: 1 }],
      },
      makeup_prompts: [{ character_name: 'A' }],
      assets: {
        images: [{ adopted: true }],
        videos: [{ adopted: true }],
      },
    }
    const blockedShot = {
      episode: 2,
      shot_id: '2-3',
      prompt_version: null,
      acceptance: { status: 'retrying' },
      structured_shot: {
        scene_asset_id: '',
        character_asset_ids: [],
        prop_asset_ids: [],
        character_blocking: [],
        action_beats: [],
      },
      makeup_prompts: [],
      assets: {
        images: [],
        videos: [],
      },
    }

    const getChecklist = (shot: any) =>
      buildShotChecklist(
        shot,
        hasReference(['scene:11', 'character:21']),
        hasReference(['scene:11', 'character:21']),
      )

    const summary = buildStoryboardReadiness([readyShot, blockedShot] as any, new Set([2]), getChecklist as any)

    expect(summary.total).toBe(1)
    expect(summary.missingPrompt).toBe(1)
    expect(summary.missingFrame).toBe(1)
    expect(summary.missingVideo).toBe(1)
    expect(summary.blockedShots[0]?.shotId).toBe('2-3')
  })

  it('builds export readiness and blocks export on missing video and review', () => {
    const shots = [
      {
        episode: 1,
        shot_id: '1-1',
        prompt_version: 1,
        acceptance: { status: 'approved' },
        structured_shot: {
          scene_asset_id: '11',
          character_asset_ids: [],
          prop_asset_ids: [],
          character_blocking: [],
          action_beats: [{ sequence: 1 }],
        },
        makeup_prompts: [],
        assets: {
          images: [{ adopted: true }],
          videos: [{ adopted: true }],
        },
      },
      {
        episode: 1,
        shot_id: '1-2',
        prompt_version: 1,
        acceptance: { status: 'retrying' },
        structured_shot: {
          scene_asset_id: '11',
          character_asset_ids: [],
          prop_asset_ids: [],
          character_blocking: [],
          action_beats: [{ sequence: 1 }],
        },
        makeup_prompts: [],
        assets: {
          images: [{ adopted: true }],
          videos: [],
        },
      },
    ]

    const getChecklist = (shot: any) => buildShotChecklist(shot, hasReference(['scene:11']), hasReference([]))
    const storyboardReadiness = buildStoryboardReadiness(shots as any, new Set([1]), getChecklist as any)
    const referencedVisualAssets = buildReferencedVisualAssetSummary(shots as any, {
      locations: [{ id: '11', derived_asset_status: 'ref_ready' }],
      props: [],
      makeups: [],
    })
    const exportReadiness = buildExportReadiness(shots as any, 1, true, storyboardReadiness, getChecklist as any, referencedVisualAssets)

    expect(exportReadiness.canExport).toBe(false)
    expect(exportReadiness.deliverableShots).toBe(1)
    expect(exportReadiness.pendingReviewShots).toBe(1)
    expect(exportReadiness.issues).toEqual(expect.arrayContaining([
      '仍有 1 个已引用视觉资产尚未锁定终图',
      '仍有 1 个镜头缺视频',
      '仍有 1 个镜头未通过验收',
    ]))
    expect(exportReadiness.blockedShots.find((item) => item.shotId === '1-2')?.reasons).toEqual(
      expect.arrayContaining(['场景参考图未锁定', '缺已采用视频', '待验收']),
    )
  })

  it('summarizes only storyboard-referenced visual assets for export readiness', () => {
    const shots = [
      {
        episode: 1,
        shot_id: '1-1',
        structured_shot: {
          scene_asset_id: '11',
          character_asset_ids: ['21'],
          prop_asset_ids: ['31'],
        },
      },
    ]

    const referenced = buildReferencedVisualAssetSummary(shots as any, {
      locations: [{ id: '11', derived_asset_status: 'locked' }, { id: '12', derived_asset_status: 'draft' }],
      props: [{ id: '31', derived_asset_status: 'ref_ready' }, { id: '32', derived_asset_status: 'locked' }],
      makeups: [{ id: '21', derived_asset_status: 'rejected' }],
    })

    expect(referenced.totalReferencedAssets).toBe(3)
    expect(referenced.lockedAssetCount).toBe(1)
    expect(referenced.refReadyAssetCount).toBe(1)
    expect(referenced.rejectedAssetCount).toBe(1)
    expect(referenced.draftAssetCount).toBe(0)
  })
})
