import { describe, expect, it } from 'vitest'
import {
  buildAssetEpisodeInsights,
  buildCharacterAssetSummaries,
  buildLocationAssetSummaries,
  buildPropAssetSummaries,
} from './productWorkspaceAssets'

describe('productWorkspaceAssets', () => {
  it('builds character asset summaries with preview and reference status counts', () => {
    const summaries = buildCharacterAssetSummaries([
      {
        id: 12,
        episode: 1,
        character_name: '姐姐',
        derived_asset_status: 'locked',
        asset_status: 'ready',
        visual_prompt_zh: '人物六宫格定妆 prompt',
        scene_prompt_zh: '场景影响 prompt',
        shot_ids: ['1-01', '1-02', '2-01'],
        reference_assets: [
          { id: 1, asset_type: 'character', asset_id: 'c1', image_url: '/a.png', status: 'selected' },
          { id: 2, asset_type: 'character', asset_id: 'c1', status: 'locked' },
        ],
      },
    ])

    expect(summaries[0]).toMatchObject({
      title: '姐姐',
      assetRecordId: 12,
      referenceCount: 2,
      previewCount: 1,
      selectedReferenceCount: 1,
      lockedReferenceCount: 1,
      staleReferenceCount: 0,
      hasStaleReferencePrompt: false,
      status: 'locked',
      shotIds: ['1-01', '1-02', '2-01'],
      episodeIds: [1, 2],
      prompt: '人物六宫格定妆 prompt',
    })
    expect(summaries[0]?.references).toHaveLength(2)
  })

  it('builds location and prop summaries', () => {
    const locations = buildLocationAssetSummaries([{ id: 7, name: '天台夜景', shot_ids: ['1-01'], derived_asset_status: 'ref_ready' }])
    const props = buildPropAssetSummaries([{ id: 9, name: '旧手机', shot_ids: ['1-01', '1-03'] }])

    expect(locations[0]?.category).toBe('location')
    expect(locations[0]?.assetRecordId).toBe(7)
    expect(locations[0]?.status).toBe('ref_ready')
    expect(locations[0]?.episodeIds).toEqual([1])
    expect(locations[0]?.hasStaleReferencePrompt).toBe(false)
    expect(props[0]?.category).toBe('prop')
    expect(props[0]?.assetRecordId).toBe(9)
    expect(props[0]?.shotIds).toHaveLength(2)
    expect(props[0]?.episodeIds).toEqual([1])
  })

  it('builds structured asset impact insights for episode shots', () => {
    const assets = buildCharacterAssetSummaries([
      {
        id: 12,
        episode: 1,
        character_name: '姐姐',
        derived_asset_status: 'locked',
        visual_prompt_zh: '人物定妆 prompt',
        shot_ids: ['1-01'],
        reference_assets: [{ id: 1, asset_type: 'character', asset_id: 'c1', image_url: '/a.png', status: 'selected' }],
      },
      {
        id: 19,
        episode: 1,
        character_name: '阿宁',
        derived_asset_status: 'draft',
        visual_prompt_zh: '人物定妆 prompt',
        shot_ids: [],
        reference_assets: [],
      },
    ])

    const insights = buildAssetEpisodeInsights(assets, [
      {
        episode: 1,
        shot_id: '1-01',
        scene_name: '屋内对话',
        used_assets: [{ asset_name: '姐姐' }],
        visual_prompt_static: '',
        visual_prompt_motion: 'motion',
        assets: { images: [], videos: [], audios: [], references: { characters: {}, scene: [], props: {} } },
      } as any,
      {
        episode: 1,
        shot_id: '1-02',
        scene_name: '走廊跟拍',
        prompt_compile_context: { asset_bindings: { characters: [{ asset_name: '阿宁' }] } },
        visual_prompt_static: 'static',
        visual_prompt_motion: 'motion',
        assets: { images: [{ id: 'img-1' }], videos: [], audios: [], references: { characters: { 阿宁: [{ id: 'ref-1' }] }, scene: [], props: {} } },
      } as any,
    ])

    expect(insights.get(assets[0]!.id)).toMatchObject({
      shotIds: ['1-01'],
      blockerCount: 4,
      missingReference: false,
    })
    expect(insights.get(assets[0]!.id)?.impactShots[0]).toMatchObject({
      shotId: '1-01',
      sceneName: '屋内对话',
      blockerCount: 4,
    })
    expect(insights.get(assets[0]!.id)?.impactShots[0]?.missingItems).toContain('静态提示词')

    expect(insights.get(assets[1]!.id)).toMatchObject({
      shotIds: ['1-02'],
      missingReference: true,
    })
    expect(insights.get(assets[1]!.id)?.impactShots[0]).toMatchObject({
      shotId: '1-02',
      sceneName: '走廊跟拍',
      blockerCount: 1,
    })
  })

  it('matches legacy character assets from structured shot bindings and makeup prompts', () => {
    const summaries = buildCharacterAssetSummaries([
      {
        id: 399,
        episode: 0,
        character_name: '胡涂',
        makeup_scope: 'base_identity',
        scope_label: '基础定妆',
        record_source: 'character_profile_fallback',
        visual_prompt_zh: 'legacy prompt',
        reference_assets: [],
      },
    ])

    const insights = buildAssetEpisodeInsights(summaries, [
      {
        episode: 1,
        shot_id: '3',
        scene_name: '原始丛林上空',
        structured_shot: { character_asset_ids: ['399'] },
        makeup_prompts: [{ id: 399, character_name: '胡涂', stage_name: 'base_identity' }],
        visual_prompt_static: 'static',
        visual_prompt_motion: 'motion',
        assets: { images: [], videos: [], audios: [], references: { characters: {}, scene: [], props: {} } },
      } as any,
    ])

    expect(insights.get(summaries[0]!.id)).toMatchObject({
      shotIds: ['3'],
      missingReference: true,
    })
    expect(insights.get(summaries[0]!.id)?.impactShots[0]).toMatchObject({
      shotId: '3',
      sceneName: '原始丛林上空',
    })
  })

  it('marks character references stale when stored prompt differs from current asset prompt', () => {
    const summaries = buildCharacterAssetSummaries([
      {
        id: 15,
        episode: 1,
        character_name: '和尚甲',
        visual_prompt_zh: '人物六宫格 prompt',
        scene_prompt_zh: '场景影响 prompt',
        reference_assets: [
          { id: 9, asset_type: 'character', asset_id: 'c9', image_url: '/ref.png', status: 'selected', prompt: '场景影响 prompt' },
        ],
      },
    ])

    expect(summaries[0]).toMatchObject({
      staleReferenceCount: 1,
      hasStaleReferencePrompt: true,
      prompt: '人物六宫格 prompt',
    })
  })

  it('does not corrupt already-normalized episode default wording in asset prompts', () => {
    const summaries = buildCharacterAssetSummaries([
      {
        id: 41,
        episode: 1,
        character_name: '和尚甲',
        visual_prompt_zh: '人物分集默认定妆设定板，当前分集默认定妆。',
        reference_assets: [],
      },
    ])

    expect(summaries[0]?.prompt).toContain('人物分集默认定妆设定板')
    expect(summaries[0]?.prompt).not.toContain('人物分分集默认设定板')
  })

  it('groups location variants with the same scene name', () => {
    const locations = buildLocationAssetSummaries([
      { id: 7, name: '寺庙院落', style: '白日版', lighting_mood: '正午硬光' },
      { id: 8, name: '寺庙院落', style: '黄昏版', lighting_mood: '低照度暖光' },
    ])

    expect(locations[0]?.siblingVariantCount).toBe(2)
    expect(locations[0]?.siblingVariants).toHaveLength(2)
    expect(locations[1]?.siblingVariantCount).toBe(2)
  })

  it('groups prop variants with the same prop name', () => {
    const props = buildPropAssetSummaries([
      { id: 11, name: '念珠', importance: 'high', associated_characters: '阿宁' },
      { id: 12, name: '念珠', importance: 'medium', associated_characters: '阿宁' },
    ])

    expect(props[0]?.siblingVariantCount).toBe(2)
    expect(props[0]?.siblingVariants).toHaveLength(2)
    expect(props[1]?.siblingVariantCount).toBe(2)
  })

  it('keeps character variant scope for version filtering', () => {
    const summaries = buildCharacterAssetSummaries([
      { id: 21, episode: 1, character_name: '和尚甲', makeup_scope: 'base_identity', scope_label: '基础定妆' },
      { id: 22, episode: 1, character_name: '和尚乙', makeup_scope: 'episode_default', scope_label: '分集默认' },
      { id: 23, episode: 1, character_name: '和尚丙', makeup_scope: 'shot_variant', scope_label: '分镜精调' },
    ])

    expect(summaries[0]?.variantScope).toBe('base_identity')
    expect(summaries[1]?.variantScope).toBe('episode_default')
    expect(summaries[2]?.variantScope).toBe('shot_variant')
  })

  it('formats episode and shot stage names into product-facing labels', () => {
    const summaries = buildCharacterAssetSummaries([
      { id: 31, episode: 1, character_name: '胡涂', makeup_scope: 'episode_default', stage_name: 'episode_1_default' },
      { id: 32, episode: 1, character_name: '胡涂', makeup_scope: 'shot_variant', stage_name: 'shot_3_泥坑坠落前瞬间' },
    ])

    expect(summaries[0]?.variantLabel).toBe('分集默认')
    expect(summaries[0]?.variantStageName).toBe('第 1 集默认造型')
    expect(summaries[1]?.variantLabel).toBe('分镜精调')
    expect(summaries[1]?.variantStageName).toBe('镜头 3 · 泥坑坠落前瞬间')
  })

  it('formal scene/prop variant scopes stay explicit in asset summaries', () => {
    const locations = buildLocationAssetSummaries([
      { id: 7, name: '寺庙院落', style: '白日版', lighting_mood: '正午硬光' },
      { id: 8, name: '寺庙院落', style: '黄昏版', lighting_mood: '低照度暖光' },
    ])
    const props = buildPropAssetSummaries([
      { id: 11, name: '念珠', importance: 'high', associated_characters: '阿宁' },
      { id: 12, name: '念珠', importance: 'medium', associated_characters: '阿宁' },
    ])

    expect(locations[0]?.variantScope).toBe('scene_variant')
    expect(locations[1]?.variantScope).toBe('scene_variant')
    expect(props[0]?.variantScope).toBe('prop_variant')
    expect(props[1]?.variantScope).toBe('prop_variant')
  })


  it('decodes escaped unicode text inside asset detail summaries', () => {
    const summaries = buildCharacterAssetSummaries([
      {
        id: 88,
        episode: 1,
        character_name: '???',
        refined_outfit: '\u7070\u8272\u68c9\u9ebb\u50e7\u888d\u659c\u62ab\u8888\u88df\u9732\u53f3\u80a9',
        reference_assets: [],
      },
    ])

    expect(summaries[0]?.detailTertiary).toBe('\u7070\u8272\u68c9\u9ebb\u50e7\u888d\u659c\u62ab\u8888\u88df\u9732\u53f3\u80a9')
  })
})
