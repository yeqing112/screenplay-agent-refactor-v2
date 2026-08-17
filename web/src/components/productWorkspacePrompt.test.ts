import { describe, expect, it } from 'vitest'
import {
  buildPromptAuthoritySummary,
  getCompilerDiagnosticMeta,
  getPromptReferenceItems,
  getPromptReferenceScopeLabel,
  getPromptReferenceStatusLabel,
  getReferencePreviewUrl,
} from './productWorkspacePrompt'

describe('productWorkspacePrompt', () => {
  it('maps compiler diagnostic statuses to display metadata', () => {
    expect(getCompilerDiagnosticMeta('blocked').label).toBe('阻塞')
    expect(getCompilerDiagnosticMeta('warning').label).toBe('警告')
    expect(getCompilerDiagnosticMeta('done').label).toBe('通过')
    expect(getCompilerDiagnosticMeta('').label).toBe('未诊断')
  })

  it('renders readable prompt reference labels', () => {
    expect(getPromptReferenceScopeLabel('character')).toBe('人物')
    expect(getPromptReferenceScopeLabel('location')).toBe('场景')
    expect(getPromptReferenceStatusLabel('locked')).toBe('已锁定')
    expect(getPromptReferenceStatusLabel('missing')).toBe('缺参考图')
  })

  it('prefers locked reference summary and falls back to normalized shot references', () => {
    const lockedItems = getPromptReferenceItems({
      shot_id: '1-01',
      scene_name: '天台',
      locked_reference_summary: {
        all: [{ id: 1, scope: 'character', subject: '姐姐', token: '@姐姐', status: 'locked' }],
      },
    } as any)

    expect(lockedItems[0]).toMatchObject({
      scope: 'character',
      subject: '姐姐',
      token: '@姐姐',
    })

    const fallbackItems = getPromptReferenceItems({
      shot_id: '1-02',
      scene_name: '客厅',
      assets: {
        references: {
          scene: [{ id: 'scene-ref', label: 'scene-v1', status: 'selected' }],
          characters: { 阿宁: [{ id: 'char-ref', label: 'char-v1', status: 'selected' }] },
          props: { 木盆: [{ id: 'prop-ref', label: 'prop-v1', status: 'locked' }] },
        },
      },
    } as any)

    expect(fallbackItems.map((item) => item.scope)).toEqual(
      expect.arrayContaining(['scene', 'character', 'prop']),
    )
  })

  it('builds readable authority summary labels from compiled asset bindings', () => {
    const summary = buildPromptAuthoritySummary({
      shot_id: '1-03',
      scene_name: '暴雨中的厨房',
      prompt_compile_context: {
        asset_bindings: {
          scene: {
            asset_id: 'scene-1',
            asset_name: '暴雨中的厨房',
            reference_token: '@厨房',
            reference_status: 'locked',
            variant_scope: 'scene_variant',
            stage_name: 'shot_3_rain_kitchen',
            reference_source: 'locked',
          },
          characters: [
            {
              asset_id: 'char-1',
              asset_name: '姐姐',
              reference_token: '@姐姐',
              reference_status: 'locked',
              reference_source: 'active_variant',
              variant_scope: 'shot_variant',
              stage_name: 'shot_3_rain_kitchen',
            },
            {
              asset_id: 'char-2',
              asset_name: '阿宁',
              reference_token: '@阿宁',
              reference_status: 'selected',
              reference_source: 'resolved_makeup',
              variant_scope: 'episode_default',
              stage_name: 'episode_1_default',
              authority_prompt_source: 'character_makeup',
              authority_prompt_raw:
                '人物集默认定妆设定板，当前集默认定妆。角色在 episode_1_default 下保持一致，并承接 shot_3_rain_kitchen。',
            },
          ],
          props: [
            {
              asset_id: 'prop-1',
              asset_name: '旧木盆',
              reference_token: '@旧木盆',
              reference_status: 'selected',
              reference_source: 'selected',
              stage_name: 'shot_3_rain_kitchen',
            },
          ],
        },
        acceptance_feedback: {
          constraints: ['保持雨夜冷色调'],
          notes: ['姐姐视线需要压住'],
          failure_tags: ['camera_motion_wrong'],
        },
        warnings: ['当前镜头建议补一条分镜精调定妆。'],
      },
    } as any)

    expect(summary.items).toHaveLength(4)
    expect(summary.items[0]).toMatchObject({
      scope: 'scene',
      name: '暴雨中的厨房',
      token: '@厨房',
      referenceSourceLabel: '锁定参考',
      variantLabel: '场景变体 / 镜头 3 · rain kitchen',
    })
    expect(summary.items[1]).toMatchObject({
      scope: 'character',
      referenceSourceLabel: '当前精调定妆',
      variantLabel: '分镜精调 / 镜头 3 · rain kitchen',
    })
    expect(summary.items[2]).toMatchObject({
      referenceSourceLabel: '当前分集默认定妆',
      variantLabel: '分集默认 / 第1集默认造型',
      authorityPromptSource: '人物定妆权威源',
    })
    expect(summary.items[2].authorityPromptExcerpt).toContain('人物分集默认定妆设定板')
    expect(summary.items[2].authorityPromptExcerpt).not.toContain('confirmed_prompt_raw:')
    expect(summary.items[2].authorityPromptExcerpt).not.toContain('episode_1_default')
    expect(summary.items[2].authorityPromptExcerpt).not.toContain('当前集默认定妆')
    expect(summary.items[3].variantLabel).toBe('镜头 3 · rain kitchen')
    expect(summary.warningCount).toBe(1)
    expect(summary.constraintCount).toBe(1)
    expect(summary.noteCount).toBe(1)
    expect(summary.failureTagCount).toBe(1)
  })

  it('keeps authority prompt excerpt and source when compiled payload provides them', () => {
    const summary = buildPromptAuthoritySummary({
      shot_id: '1-04',
      scene_name: '厨房',
      prompt_compile_context: {
        asset_bindings: {
          characters: [
            {
              asset_id: 'char-2',
              asset_name: '阿宁',
              authority_prompt_raw:
                '人物分镜精调定妆设定板，展示同一个角色在当前分镜状态下的六个视角。六个视角必须是同一个人。',
              authority_prompt_source: 'character_makeup',
            },
          ],
        },
      },
    } as any)

    expect(summary.items[0].authorityPromptSource).toBe('人物定妆权威源')
    expect(summary.items[0].authorityPromptExcerpt).toContain('人物分镜精调定妆设定板')
    expect(summary.items[0].authorityPromptExcerpt).not.toContain('confirmed_prompt_raw:')
  })

  it('compresses long authority excerpts into short keyword previews', () => {
    const summary = buildPromptAuthoritySummary({
      shot_id: '1-04b',
      scene_name: '寺庙后院水房',
      prompt_compile_context: {
        asset_bindings: {
          scene: {
            asset_id: 'scene-1',
            asset_name: '寺庙后院水房',
            authority_prompt_raw:
              '古代寺庙后院水房，清晨，宏观，背景层：青石板地面、中央老井、灰白墙壁、木结构梁柱，前景层：青石井台与木架，氛围：清冷、静谧、简朴。',
            authority_prompt_source: 'scene_asset',
          },
        },
      },
    } as any)

    expect(summary.items[0].authorityPromptExcerpt).toContain('古代寺庙后院水房')
    expect(summary.items[0].authorityPromptExcerpt).toContain('清晨')
    expect(summary.items[0].authorityPromptExcerpt.length).toBeLessThanOrEqual(92)
    expect(summary.items[0].authorityPromptExcerpt).not.toContain('木结构梁柱')
  })


  it('uses the variant scope to label character reference source in authority summary', () => {
    const summary = buildPromptAuthoritySummary({
      shot_id: '1-05',
      scene_name: '??',
      prompt_compile_context: {
        asset_bindings: {
          characters: [
            {
              asset_id: 'char-episode',
              asset_name: '???',
              reference_token: '@???',
              reference_status: 'selected',
              reference_source: 'active_variant',
              variant_scope: 'episode_default',
              stage_name: 'episode_1_default',
            },
            {
              asset_id: 'char-shot',
              asset_name: '???',
              reference_token: '@???',
              reference_status: 'selected',
              reference_source: 'active_variant',
              variant_scope: 'shot_variant',
              stage_name: 'shot_5_splash',
            },
          ],
        },
      },
    } as any)

    expect(summary.items[0]?.referenceSourceLabel).toBe('\u5f53\u524d\u5206\u96c6\u9ed8\u8ba4\u5b9a\u5986')
    expect(summary.items[1]?.referenceSourceLabel).toBe('\u5f53\u524d\u7cbe\u8c03\u5b9a\u5986')
  })

  it('picks the best preview url from reference image payload', () => {
    expect(getReferencePreviewUrl({ image_url: 'https://example.com/ref.png', local_path: 'C:/tmp/ref.png' })).toBe(
      'https://example.com/ref.png',
    )
    expect(getReferencePreviewUrl({ local_path: 'C:/tmp/ref.png' })).toBe('C:/tmp/ref.png')
    expect(getReferencePreviewUrl({})).toBe('')
  })

  it('falls back to current binding labels when scene and prop have no formal variant scope', () => {
    const summary = buildPromptAuthoritySummary({
      shot_id: '1-06',
      scene_name: 'Temple Yard',
      prompt_compile_context: {
        asset_bindings: {
          scene: {
            asset_id: 'scene-2',
            asset_name: 'Temple Yard',
            reference_status: 'missing',
            reference_source: 'missing',
            variant_scope: '',
            scope_label: '',
            stage_name: '',
          },
          props: [
            {
              asset_id: 'prop-2',
              asset_name: 'Wooden Bucket',
              reference_status: 'missing',
              reference_source: 'missing',
              variant_scope: '',
              scope_label: '',
              stage_name: '',
            },
          ],
        },
      },
    } as any)

    expect(summary.items[0]?.variantLabel).toBe('当前场景绑定')
    expect(summary.items[1]?.variantLabel).toBe('当前道具绑定')
  })
})
