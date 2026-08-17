import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import ProductWorkspaceStoryboardSection, {
  buildStoryboardCanvasHandoffSummary,
  buildStoryboardCanvasPrimaryActionPlan,
} from './ProductWorkspaceStoryboardSection'

function makeShot(overrides: Record<string, unknown> = {}) {
  return {
    episode: 1,
    shot_id: '1-01',
    scene_name: '\u5bfa\u5e99\u540e\u9662',
    visual_prompt_static: '\u9759\u6001\u63d0\u793a\u8bcd',
    visual_prompt_motion: '\u8fd0\u52a8\u63d0\u793a\u8bcd',
    asset_status: 'pending',
    assets: {
      images: [],
      videos: [],
      audios: [],
      references: { characters: {}, scene: [], props: {} },
    },
    reference_images: [],
    ...overrides,
  } as any
}

function renderStoryboard(shots: any[], overrides: Record<string, unknown> = {}) {
  return renderToStaticMarkup(
    <ProductWorkspaceStoryboardSection
      bookId={14}
      shotsByEpisode={{ 1: shots }}
      scriptDecisionState={{
        '1': {
          lockedAt: '2026-07-17T09:00:00.000Z',
          releasedAt: '2026-07-17T09:10:00.000Z',
          note: '',
        },
      }}
      hasExplicitLockedAdaptation
      selectedShotId={String(shots[0]?.shot_id || '1-01')}
      onSelectShot={() => {}}
      onRefresh={() => {}}
      onNavigateSection={() => {}}
      onNavigateTaskSection={() => {}}
      {...overrides}
    />,
  )
}

describe('ProductWorkspaceStoryboardSection', () => {
  it('shows blocked upstream gate guidance before storyboard release', () => {
    const html = renderToStaticMarkup(
      <ProductWorkspaceStoryboardSection
        bookId={14}
        shotsByEpisode={{ 1: [makeShot({ visual_prompt_static: '', visual_prompt_motion: '' })] }}
        scriptDecisionState={{
          '1': {
            lockedAt: '2026-07-17T09:00:00.000Z',
            releasedAt: null,
            note: '',
          },
        }}
        hasExplicitLockedAdaptation
        selectedShotId={null}
        onSelectShot={() => {}}
        onRefresh={() => {}}
        onNavigateSection={() => {}}
      />,
    )

    expect(html).toContain('\u4e0a\u6e38\u653e\u884c\u72b6\u6001')
    expect(html).toContain('\u672a\u653e\u884c')
    expect(html).toContain('\u56de\u5267\u672c\u5de5\u4f5c\u53f0\u8865\u653e\u884c')
  })

  it('shows ready upstream gate guidance after storyboard release', () => {
    const html = renderStoryboard([makeShot()])

    expect(html).toContain('\u5df2\u653e\u884c')
    expect(html).toContain('\u53ef\u4ee5\u7ee7\u7eed\u8fdb\u884c\u63d0\u793a\u8bcd\u7f16\u8bd1\u3001\u51fa\u56fe\u548c\u51fa\u89c6\u9891')
    expect(html).toContain('\u56de\u5267\u672c\u5de5\u4f5c\u53f0\u590d\u6838')
  })

  it('keeps storyboard in review-only mode when adaptation is not explicitly locked', () => {
    const html = renderStoryboard([makeShot()], { hasExplicitLockedAdaptation: false })

    expect(html).toContain('\u9879\u76ee\u6539\u7f16\u65b9\u5411\u5c1a\u672a\u6b63\u5f0f\u9501\u5b9a')
    expect(html).toContain('\u5f53\u524d\u4e5f\u53ea\u5e94\u505a\u53ea\u8bfb\u590d\u6838')
  })

  it('shows single-shot generation guidance and keeps video blocked before an adopted frame exists', () => {
    const html = renderStoryboard([makeShot()])

    expect(html).toContain('\u5355\u955c\u5934\u751f\u6210\u52a8\u4f5c')
    expect(html).toContain('\u751f\u6210\u9996\u5e27')
    expect(html).toContain('\u751f\u6210\u89c6\u9891')
    expect(html).toContain('\u5f53\u524d\u955c\u5934\u8fd8\u6ca1\u6709\u91c7\u7eb3\u9996\u5e27')
  })

  it('shows adopted-frame video guidance and task-center recovery entry in the storyboard workspace', () => {
    const html = renderStoryboard([
      makeShot({
        reference_images: [
          {
            reference_asset_id: 'ref-scene-1',
            asset_name: '\u5bfa\u5e99\u540e\u9662',
          },
        ],
        prompt_compile_context: {
          asset_bindings: {
            scene: {
              asset_id: 'scene-1',
              asset_name: '\u5bfa\u5e99\u540e\u9662',
              reference_asset_id: 'ref-scene-1',
              image_url: 'https://example.com/scene-ref.png',
              has_reference: true,
            },
          },
        },
        assets: {
          images: [
            {
              id: 'img-1',
              title: '\u9996\u5e27 v1',
              previewUrl: 'https://example.com/frame.png',
              adopted: true,
            },
          ],
          videos: [],
          audios: [],
          references: { characters: {}, scene: [], props: {} },
        },
      }),
    ])

    expect(html).toContain('\u672c\u6b21\u89c6\u9891\u8f93\u5165\u6458\u8981')
    expect(html).toContain('\u5f53\u524d\u7f16\u8bd1\u5b9e\u9645\u4f7f\u7528\uff1a1 \u5f20')
    expect(html).toContain('image_to_video')
    expect(html).toContain('\u53bb\u4efb\u52a1\u4e2d\u5fc3\u7ee7\u7eed\u56de\u6536')
  })

  it('shows effective submitted reference payload in the video summary', () => {
    const html = renderStoryboard([
      makeShot({
        reference_images: [
          { reference_asset_id: 'ref-structured-1', asset_name: '\u548c\u5c1a\u7532' },
        ],
        prompt_compile_context: {
          compiled_reference_asset_ids: ['ref-compiled-1', 'ref-compiled-2'],
        },
      }),
    ])

    expect(html).toContain('\u672c\u6b21\u89c6\u9891\u5b9e\u9645\u63d0\u4ea4\uff1a2 \u5f20')
    expect(html).toContain('\u5f53\u524d\u4f1a\u4f18\u5148\u6cbf\u7528\u5df2\u7f16\u8bd1\u7248\u672c\u5b9e\u9645\u4f7f\u7528\u7684\u53c2\u8003\u56fe')
  })

  it('shows direct repair entries for missing references and QA follow-up', () => {
    const html = renderStoryboard([
      makeShot({
        compiler_diagnostics: {
          status: 'warning',
          warnings: ['\u89d2\u8272\u8d44\u4ea7\u300c\u548c\u5c1a\u4e59\u300d\u8fd8\u6ca1\u6709\u53c2\u8003\u56fe\u3002'],
        },
        prompt_compile_context: {
          asset_bindings: {
            characters: [
              {
                asset_id: '22',
                asset_name: '\u548c\u5c1a\u4e59',
                stage_name: 'episode_1_default',
                variant_scope: 'episode_default',
                scope_label: '\u5206\u96c6\u9ed8\u8ba4',
                reference_source: 'missing',
              },
            ],
          },
        },
      }),
    ])

    expect(html).toContain('\u5f53\u524d\u4fee\u590d\u5165\u53e3')
    expect(html).toContain('\u8865\u9f50\u53c2\u8003\u56fe\uff1a\u548c\u5c1a\u4e59')
    expect(html).toContain('\u53bb\u8d44\u4ea7\u4e2d\u5fc3')
    expect(html).toContain('\u53bb QA \u4fee\u590d')
  })

  it('shows chained prompt repair CTA to recompile then generate frame when no adopted frame exists', () => {
    const html = renderStoryboard([
      makeShot({
        shot_id: '1-02',
        compiler_diagnostics: {
          status: 'warning',
          checks: [
            {
              key: 'visual_fact_target_coverage',
              passed: false,
              message: '\u8fd9\u4e9b\u8d44\u4ea7\u6ca1\u6709\u6ee1\u8db3\u9996\u8f6e\u7f16\u8bd1\u8981\u6c42\u7684\u89c6\u89c9\u4e8b\u5b9e\u8986\u76d6\uff1a\u548c\u5c1a\u7532\u3001\u6728\u6876',
              details: [
                '\u548c\u5c1a\u7532\uff1a\u81f3\u5c11\u8865\u5165 1 \u6761\u89c6\u89c9\u4e8b\u5b9e / \u6e7f\u900f\u7684\u7070\u8272\u50e7\u888d / \u53f3\u80a9\u88f8\u9732',
                '\u6728\u6876\uff1a\u81f3\u5c11\u8865\u5165 1 \u6761\u89c6\u89c9\u4e8b\u5b9e / \u65e7\u6728\u6876 / \u8fb9\u7f18\u78e8\u635f',
              ],
            },
          ],
        },
      }),
    ])

    expect(html).toContain('\u91cd\u7f16\u63d0\u793a\u8bcd\u5e76\u8865\u9f50\u89c6\u89c9\u4e8b\u5b9e\uff1a\u548c\u5c1a\u7532 / \u6728\u6876')
    expect(html).toContain('\u91cd\u7f16\u540e\u751f\u6210\u9996\u5e27')
  })

  it('shows chained prompt repair CTA to recompile then generate video when an adopted frame exists', () => {
    const html = renderStoryboard([
      makeShot({
        shot_id: '1-03',
        compiler_diagnostics: {
          status: 'warning',
          checks: [
            {
              key: 'visual_fact_target_coverage',
              passed: false,
              message: '\u8fd9\u4e9b\u8d44\u4ea7\u6ca1\u6709\u6ee1\u8db3\u9996\u8f6e\u7f16\u8bd1\u8981\u6c42\u7684\u89c6\u89c9\u4e8b\u5b9e\u8986\u76d6\uff1a\u548c\u5c1a\u7532',
              details: ['\u548c\u5c1a\u7532\uff1a\u81f3\u5c11\u8865\u5165 1 \u6761\u89c6\u89c9\u4e8b\u5b9e / \u53f3\u80a9\u88f8\u9732 / \u7070\u8272\u50e7\u888d'],
            },
          ],
        },
        assets: {
          images: [
            {
              id: 'img-1',
              title: '\u9996\u5e27 v1',
              previewUrl: 'https://example.com/frame.png',
              adopted: true,
            },
          ],
          videos: [],
          audios: [],
          references: { characters: {}, scene: [], props: {} },
        },
      }),
    ])

    expect(html).toContain('\u91cd\u7f16\u540e\u7ee7\u7eed\u751f\u6210\u89c6\u9891')
  })

  it('surfaces a missing recovery target banner when storyboard handoff cannot find the shot', () => {
    const html = renderStoryboard([makeShot({ shot_id: '3' })], {
      recoveryFocus: {
        episode: 1,
        shotId: '999',
        taskId: 'missing-task-001',
        recoveryKind: 'frame',
      },
    })

    expect(html).toContain('\u6062\u590d\u76ee\u6807\u672a\u547d\u4e2d')
    expect(html).toContain('\u7b2c 1 \u96c6 / \u955c\u5934 999')
    expect(html).toContain('missing-task-001')
    expect(html).toContain('\u67e5\u770b\u540c\u96c6\u955c\u5934')
    expect(html).toContain('\u56de\u4efb\u52a1\u4e2d\u5fc3')
  })

  it('routes character state-change warnings to storyboard makeup refinement in assets', () => {
    const html = renderStoryboard([
      makeShot({
        shot_id: '13',
        scene_name: '\u5bfa\u5e99\u540e\u5c71\u4e71\u846c\u5c97',
        compiler_diagnostics: {
          status: 'warning',
          warnings: ['\u548c\u5c1a\u7532 \u5f53\u524d\u955c\u5934\u5b58\u5728\u660e\u663e\u72b6\u6001\u53d8\u5316\uff0c\u5efa\u8bae\u8865\u4e00\u6761\u5206\u955c\u7cbe\u8c03\u5b9a\u5986\u3002'],
        },
        prompt_compile_context: {
          asset_bindings: {
            characters: [
              {
                asset_id: '21',
                asset_name: '\u548c\u5c1a\u7532',
                stage_name: 'episode_1_default',
                variant_scope: 'episode_default',
                scope_label: '\u5206\u96c6\u9ed8\u8ba4',
                reference_source: 'resolved_makeup',
              },
            ],
          },
        },
      }),
    ])

    expect(html).toContain('\u8865\u4eba\u7269\u5206\u955c\u7cbe\u8c03\u5b9a\u5986\uff1a\u548c\u5c1a\u7532')
    expect(html).toContain('\u53bb\u8d44\u4ea7\u4e2d\u5fc3')
  })

  it('surfaces degraded prompt warning and recommended rollback entry', () => {
    const html = renderStoryboard([
      makeShot({
        prompt_version_audit: {
          is_degraded_version: true,
          missing_critical_count: 2,
          recoverable_version_count: 1,
          is_scene_only_candidate: false,
        },
        recommended_restore_version: {
          version: 7,
          reason: 'best_recoverable_version',
        },
      }),
    ])

    expect(html).toContain('\u5f53\u524d\u63d0\u793a\u8bcd\u7248\u672c\u7591\u4f3c\u8dd1\u504f')
    expect(html).toContain('\u6062\u590d\u63a8\u8350\u7248\u672c v7')
  })

  it('builds a readable canvas handoff summary for storyboard continuation', () => {
    expect(
      buildStoryboardCanvasHandoffSummary({
        handoff: {
          target: 'storyboard',
          episode: 1,
          shotId: '1-01',
          handoffLabel: '前往镜头工作台继续该镜头创作',
          handoffDetail: '继续提示词、首帧和视频链路。',
        },
        shot: makeShot({ shot_id: '1-01', scene_name: '寺庙后院' }),
      }),
    ).toEqual({
      title: '已从创作画布定位到 第 1 集 / 镜头 1-01 / 寺庙后院',
      label: '前往镜头工作台继续该镜头创作',
      detail: '继续提示词、首帧和视频链路。',
    })
  })

  it('builds a primary action plan for storyboard handoff continuation', () => {
    expect(
      buildStoryboardCanvasPrimaryActionPlan({
        canGenerateFromGate: true,
        hasCompiledPrompt: true,
        hasAdoptedFrame: true,
        hasAdoptedVideo: false,
      }),
    ).toEqual({
      action: 'generate_video',
      label: '继续生成视频',
      detail: '当前镜头已经有已采纳首帧，下一步可以直接沿用当前输入继续生成视频。',
    })
  })

  it('renders canvas handoff state inside the storyboard detail panel', () => {
    const html = renderStoryboard([makeShot({ shot_id: '1-01', scene_name: '寺庙后院' })], {
      canvasHandoff: {
        target: 'storyboard',
        episode: 1,
        shotId: '1-01',
        handoffLabel: '前往镜头工作台继续该镜头创作',
        handoffDetail: '继续提示词、首帧和视频链路。',
      },
    })

    expect(html).toContain('创作画布承接中')
    expect(html).toContain('已从创作画布定位到 第 1 集 / 镜头 1-01 / 寺庙后院')
    expect(html).toContain('继续提示词、首帧和视频链路。')
    expect(html).toContain('承接后的首个动作')
    expect(html).toContain('先生成首帧')
  })
})
