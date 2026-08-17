import { describe, expect, it } from 'vitest'

import type { StoryboardShotOutput } from '../prototyping/sceneComposerData'
import {
  buildCharacterBindingSummaries,
  getCharacterReferenceSourceLabel,
  getReferenceStatusLabel,
} from './productWorkspaceStoryboardBindings'

function makeShot(overrides: Partial<StoryboardShotOutput> = {}): StoryboardShotOutput {
  return {
    shot_id: '1-01',
    scene_name: '寺庙后院',
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

describe('productWorkspaceStoryboardBindings', () => {
  it('builds user-facing character binding summaries from compile bindings and references', () => {
    const shot = makeShot({
      structured_shot: {
        character_asset_ids: ['201'],
      },
      prompt_compile_context: {
        asset_bindings: {
          characters: [
            {
              asset_id: '201',
              asset_name: '姐姐',
              stage_name: 'episode_2_default',
              variant_scope: 'episode_default',
              variant_name: '',
              scope_label: '分集默认定妆',
              reference_source: 'resolved_makeup',
            },
          ],
        },
      },
      reference_images: [
        {
          asset_type: 'character',
          asset_id: '201',
          asset_name: '姐姐',
          reference_token: '@姐姐',
          reference_status: 'selected',
        },
      ],
    })

    expect(buildCharacterBindingSummaries(shot)).toMatchObject([
      {
        key: 'character-201',
        title: '姐姐',
        detail: '第2集默认造型 · 分集默认 · 当前分集默认定妆',
        token: '@姐姐',
        status: '默认参考',
        assetId: '201',
        bindingSourceLabel: '正式结构化绑定',
      },
    ])
  })

  it('hides internal variant keys and renders a human-friendly stage label', () => {
    const shot = makeShot({
      prompt_compile_context: {
        asset_bindings: {
          characters: [
            {
              asset_id: '88',
              asset_name: '和尚甲',
              stage_name: 'episode_1_default',
              variant_scope: 'episode_default',
              variant_name: 'episode_1_default',
              scope_label: '分集默认定妆',
              reference_source: 'missing',
            },
          ],
        },
      },
    })

    expect(buildCharacterBindingSummaries(shot)).toMatchObject([
      {
        key: 'character-88',
        title: '和尚甲',
        detail: '第1集默认造型 · 分集默认 · 未绑定参考图',
        token: '',
        status: '缺参考图',
        assetId: '88',
      },
    ])
  })

  it('marks compile-time variant resolution when a binding was not formally saved yet', () => {
    const shot = makeShot({
      prompt_compile_context: {
        asset_bindings: {
          characters: [
            {
              asset_id: '66',
              asset_name: '阿宁',
              stage_name: 'shot_6_对峙湿衣',
              variant_scope: 'shot_variant',
              variant_name: '',
              scope_label: '分镜精调',
              reference_source: 'active_variant',
            },
          ],
        },
      },
      reference_images: [
        {
          asset_type: 'character',
          asset_id: '66',
          asset_name: '阿宁',
          reference_token: '@阿宁',
          reference_status: 'locked',
        },
      ],
    })

    expect(buildCharacterBindingSummaries(shot)).toMatchObject([
      {
        key: 'character-66',
        title: '阿宁',
        bindingSourceLabel: '编译期变体命中',
      },
    ])
  })

  it('falls back to makeup prompts when compile bindings are absent', () => {
    const shot = makeShot({
      makeup_prompts: [
        {
          id: 31,
          character_name: '阿宁',
          stage_name: 'base_identity',
          makeup_scope: 'base_identity',
          scope_label: '基础定妆',
        } as any,
      ],
    })

    expect(buildCharacterBindingSummaries(shot)).toMatchObject([
      {
        key: 'character-31',
        title: '阿宁',
        detail: '基础定妆 · 基础定妆回退',
        token: '',
        status: '缺参考图',
        assetId: '31',
        bindingSourceLabel: '基础定妆回退',
      },
    ])
  })

  it('marks fallback-only makeup summaries as non-actionable missing references', () => {
    const shot = makeShot({
      makeup_prompts: [
        {
          id: 32,
          character_name: 'fallback-char',
          stage_name: 'episode_1_default',
          makeup_scope: 'episode_default',
          scope_label: 'episode default',
        } as any,
      ],
    })

    expect(buildCharacterBindingSummaries(shot)).toMatchObject([
      {
        key: 'character-32',
        actionableMissingReference: false,
        status: '缺参考图',
      },
    ])
  })

  it('maps source and reference statuses to readable labels', () => {
    expect(getCharacterReferenceSourceLabel('active_variant', 'episode_default')).toBe('当前分集默认定妆')
    expect(getCharacterReferenceSourceLabel('active_variant', 'shot_variant')).toBe('当前精调定妆')
    expect(getCharacterReferenceSourceLabel('resolved_makeup', 'episode_default')).toBe('当前分集默认定妆')
    expect(getCharacterReferenceSourceLabel('base_identity', 'base_identity')).toBe('基础定妆回退')
    expect(getCharacterReferenceSourceLabel('missing', 'shot_variant')).toBe('未绑定参考图')
    expect(getReferenceStatusLabel('candidate')).toBe('候选参考')
  })
})
