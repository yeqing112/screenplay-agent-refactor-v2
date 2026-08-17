import { describe, expect, it } from 'vitest'

import {
  buildActiveMakeupVariants,
  formatProductionMakeupScopeLabel,
  formatProductionMakeupStageLabel,
  formatProductionMakeupVersionLabel,
  getActiveMakeupReferenceSourceLabel,
} from './ProductionMode'

describe('ProductionMode makeup helpers', () => {
  it('prefers compiled character variants when prompt compile context is present', () => {
    const shot = {
      prompt_compile_context: {
        character_variants: [
          {
            asset_id: 11,
            character_name: '和尚甲',
            scope_label: '分镜精调',
            stage_name: 'shot_6_对峙湿衣',
            makeup_scope: 'shot_variant',
            reference_source: 'active_variant',
          },
        ],
      },
      makeup_prompts: [
        {
          id: 5,
          character_name: '和尚甲',
          scope_label: '基础定妆',
          stage_name: 'base_identity',
          makeup_scope: 'base_identity',
          reference_images: [{ id: 1 }],
        },
      ],
    }

    expect(buildActiveMakeupVariants(shot as any)).toEqual(shot.prompt_compile_context.character_variants)
  })

  it('falls back to resolved makeup prompts before compile and normalizes labels', () => {
    const shot = {
      makeup_prompts: [
        {
          id: 1,
          character_name: '和尚甲',
          scope_label: '基础定妆',
          stage_name: 'base_identity',
          makeup_scope: 'base_identity',
          reference_images: [{ id: 101 }],
        },
        {
          id: 2,
          character_name: '和尚乙',
          scope_label: '分集默认',
          stage_name: 'episode_1_default',
          makeup_scope: 'episode_default',
          reference_images: [{ id: 102 }],
        },
        {
          id: 3,
          character_name: '和尚丙',
          scope_label: '分镜精调',
          stage_name: 'shot_1_rain',
          makeup_scope: 'shot_variant',
          reference_images: [],
        },
      ],
    }

    const variants = buildActiveMakeupVariants(shot as any)

    expect(variants).toHaveLength(3)
    expect(variants[0]).toMatchObject({
      asset_id: 1,
      character_name: '和尚甲',
      scope_label: '基础定妆',
      stage_name: '基础身份阶段',
      makeup_scope: 'base_identity',
      reference_source: 'base_identity',
    })
    expect(variants[1]).toMatchObject({
      asset_id: 2,
      character_name: '和尚乙',
      scope_label: '分集默认',
      stage_name: '第1集默认造型',
      makeup_scope: 'episode_default',
      reference_source: 'resolved_makeup',
    })
    expect(variants[2]).toMatchObject({
      asset_id: 3,
      character_name: '和尚丙',
      scope_label: '分镜精调',
      stage_name: '镜头 1 · rain',
      makeup_scope: 'shot_variant',
      reference_source: 'missing',
    })
  })

  it('formats scope, stage, and version labels for production display', () => {
    expect(formatProductionMakeupScopeLabel('基础定妆', 'base_identity')).toBe('基础定妆')
    expect(formatProductionMakeupScopeLabel('集默认定妆', 'episode_default')).toBe('分集默认')
    expect(formatProductionMakeupStageLabel('base_identity', 'base_identity')).toBe('基础身份阶段')
    expect(formatProductionMakeupStageLabel('episode_2_default', 'episode_default')).toBe('第2集默认造型')
    expect(formatProductionMakeupStageLabel('shot_6_对峙湿衣', 'shot_variant')).toBe('镜头 6 · 对峙湿衣')
    expect(formatProductionMakeupVersionLabel('分镜精调', 'shot_6_对峙湿衣', 'shot_variant')).toBe(
      '分镜精调 / 镜头 6 · 对峙湿衣',
    )
  })

  it('maps reference source and scope to user-facing labels', () => {
    expect(getActiveMakeupReferenceSourceLabel('active_variant', 'shot_variant')).toBe('当前精调定妆')
    expect(getActiveMakeupReferenceSourceLabel('resolved_makeup', 'episode_default')).toBe('当前分集默认定妆')
    expect(getActiveMakeupReferenceSourceLabel('base_identity', 'base_identity')).toBe('基础定妆回退')
    expect(getActiveMakeupReferenceSourceLabel('missing', 'shot_variant')).toBe('未绑定参考图')
  })
})
