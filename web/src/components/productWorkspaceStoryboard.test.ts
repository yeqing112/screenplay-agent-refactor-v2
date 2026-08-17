import { describe, expect, it } from 'vitest'
import { buildShotReadiness, buildStoryboardGateSummary, summarizeShotReferences } from './productWorkspaceStoryboard'
import type { StoryboardShotOutput } from '../prototyping/sceneComposerData'

function makeShot(overrides: Partial<StoryboardShotOutput> = {}): StoryboardShotOutput {
  return {
    shot_id: '1-01',
    scene_name: '天台',
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
    ...overrides,
  }
}

describe('productWorkspaceStoryboard', () => {
  it('summarizes shot references across scopes', () => {
    const summary = summarizeShotReferences(
      makeShot({
        assets: {
          images: [],
          videos: [],
          audios: [],
          references: {
            characters: { 姐姐: [{ id: 'a', kind: 'image', title: 'A', label: 'v1' }] },
            scene: [{ id: 'b', kind: 'image', title: 'B', label: 'v1' }],
            props: { 打火机: [{ id: 'c', kind: 'image', title: 'C', label: 'v1' }] },
          },
        },
      }),
    )

    expect(summary).toMatchObject({
      characterCount: 1,
      sceneCount: 1,
      propCount: 1,
      totalCount: 3,
    })
  })

  it('prefers locked reference summary and reference image scopes over legacy reference buckets', () => {
    const summary = summarizeShotReferences(
      makeShot({
        locked_reference_summary: {
          all: [
            { id: 'ref-scene', scope: 'scene', subject: '雨夜寺门', token: '@scene-1', status: 'selected' },
            { id: 'ref-character', scope: 'character', subject: '姐姐', token: '@姐姐-1', status: 'selected' },
          ],
        },
        reference_images: [
          { reference_asset_id: 'ignored-1', asset_type: 'character', asset_id: '11', asset_name: '姐姐' },
          { reference_asset_id: 'ignored-2', asset_type: 'prop', asset_id: '12', asset_name: '灯笼' },
        ],
        assets: {
          images: [],
          videos: [],
          audios: [],
          references: {
            characters: { 旧人物: [{ id: 'old-a', kind: 'image', title: 'old', label: 'v1' }] },
            scene: [{ id: 'old-b', kind: 'image', title: 'old-scene', label: 'v1' }],
            props: { 旧道具: [{ id: 'old-c', kind: 'image', title: 'old-prop', label: 'v1' }] },
          },
        },
      }),
    )

    expect(summary).toMatchObject({
      characterCount: 1,
      sceneCount: 1,
      propCount: 0,
      totalCount: 2,
    })
  })

  it('marks a complete shot as deliverable', () => {
    const readiness = buildShotReadiness(
      makeShot({
        visual_prompt_static: '静态 prompt',
        visual_prompt_motion: '运动 prompt',
        assets: {
          images: [{ id: 'img', kind: 'image', title: 'img', label: 'v1' }],
          videos: [{ id: 'vid', kind: 'video', title: 'vid', label: 'v1' }],
          audios: [],
          references: {
            characters: { 姐姐: [{ id: 'a', kind: 'image', title: 'A', label: 'v1' }] },
            scene: [],
            props: {},
          },
        },
      }),
    )

    expect(readiness.statusLabel).toBe('可交付')
    expect(readiness.blockerCount).toBe(0)
    expect(readiness.nextAction).toBe('进入 QA 或导出')
  })

  it('marks missing assets as blocked with next action', () => {
    const readiness = buildShotReadiness(makeShot())
    expect(readiness.statusLabel).toBe('阻塞')
    expect(readiness.blockerCount).toBe(5)
    expect(readiness.nextAction).toBe('先补齐参考资产')
  })

  it('blocks storyboard actions until script is released', () => {
    const gate = buildStoryboardGateSummary({
      hasLockedAdaptation: true,
      hasScript: true,
      scriptLocked: true,
      scriptReleased: false,
    })

    expect(gate).toMatchObject({
      status: 'blocked',
      actionsEnabled: false,
    })
    expect(gate.message).toContain('放行到分镜')
  })

  it('allows storyboard actions after script is locked and released', () => {
    const gate = buildStoryboardGateSummary({
      hasLockedAdaptation: true,
      hasScript: true,
      scriptLocked: true,
      scriptReleased: true,
    })

    expect(gate).toMatchObject({
      status: 'ready',
      actionsEnabled: true,
    })
  })

  it('marks degraded prompt shots as restore-needed even when prompts already exist', () => {
    const readiness = buildShotReadiness(
      makeShot({
        visual_prompt_static: 'static',
        visual_prompt_motion: 'motion',
        prompt_version: 11,
        prompt_version_audit: {
          is_degraded_version: true,
          missing_critical_count: 3,
        },
        recommended_restore_version: {
          version: 9,
          reason: 'best_partial_recovery_version',
        },
      }),
    )

    expect(readiness.statusLabel).toBe('待恢复')
    expect(readiness.blockerCount).toBe(3)
    expect(readiness.nextAction).toBe('恢复推荐版本 v9')
  })
})
