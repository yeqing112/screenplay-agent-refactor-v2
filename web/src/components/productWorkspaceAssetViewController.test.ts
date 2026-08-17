import { describe, expect, it } from 'vitest'

import type { StoryboardShotOutput } from '../prototyping/sceneComposerData'
import type { AssetSummary } from './productWorkspaceAssets'
import {
  buildInitialLinkedShotDraft,
  mergeLinkedShotDraftWithInferredShots,
  resolveAssetTaskNavigationTarget,
  resolveShotVariantNavigationTarget,
} from './productWorkspaceAssetViewController'

function buildAsset(overrides: Partial<AssetSummary> = {}): AssetSummary {
  return {
    id: 'character-1',
    category: 'character',
    assetRecordId: 1,
    title: '姐姐',
    subtitle: '第 1 集默认造型',
    status: 'ref_ready',
    prompt: '人物提示词',
    shotIds: ['1-01'],
    episodeIds: [1],
    referenceCount: 1,
    previewCount: 1,
    selectedReferenceCount: 1,
    lockedReferenceCount: 0,
    staleReferenceCount: 0,
    hasStaleReferencePrompt: false,
    references: [],
    variantGroupKey: '姐姐',
    variantLabel: '分集默认',
    variantScope: 'episode_default',
    variantStageName: '第 1 集默认造型',
    siblingVariantCount: 2,
    siblingVariants: [],
    ...overrides,
  }
}

function buildShot(overrides: Partial<StoryboardShotOutput> = {}): StoryboardShotOutput {
  return {
    episode: 1,
    shot_id: '03',
    scene_name: '出租屋门口',
    used_assets: [{ asset_name: '姐姐', asset_id: '2', asset_type: 'character' }],
    prompt_compile_context: {
      asset_bindings: {
        characters: [
          {
            asset_id: '2',
            asset_name: '姐姐',
            stage_name: '镜头 3 · 淋雨状态',
          },
        ],
      },
    },
    ...overrides,
  }
}

describe('productWorkspaceAssetViewController', () => {
  it('prefers explicit saved shot bindings over inferred shot ids when seeding the draft', () => {
    expect(buildInitialLinkedShotDraft(['1-01', '1-02'], ['03', '04'])).toEqual(['1-01', '1-02'])
  })

  it('falls back to inferred impact shots when no saved binding exists yet', () => {
    expect(buildInitialLinkedShotDraft([], ['03', '03', '04'])).toEqual(['03', '04'])
  })

  it('merges inferred shots into the current draft without duplicating ids', () => {
    expect(mergeLinkedShotDraftWithInferredShots(['03', '04'], ['04', '05'])).toEqual(['03', '04', '05'])
  })

  it('prefers the current shot variant over a generic episode default asset', () => {
    const episodeDefault = buildAsset()
    const shotVariant = buildAsset({
      id: 'character-2',
      assetRecordId: 2,
      subtitle: '镜头 3 · 淋雨状态',
      shotIds: ['1-03'],
      variantLabel: '分镜精调',
      variantScope: 'shot_variant',
      variantStageName: '镜头 3 · 淋雨状态',
    })

    const resolved = resolveAssetTaskNavigationTarget({
      allAssets: [episodeDefault, shotVariant],
      episode: 1,
      shotId: '03',
      assetId: '',
      assetLabel: '姐姐',
      matchedShot: buildShot(),
    })

    expect(resolved?.id).toBe('character-2')
  })

  it('always honors an explicit task asset id before weaker label matches', () => {
    const wrongButNamed = buildAsset({
      id: 'character-1',
      assetRecordId: 1,
      shotIds: ['1-03'],
      subtitle: '第 1 集默认造型',
    })
    const exactAsset = buildAsset({
      id: 'character-99',
      assetRecordId: 99,
      subtitle: '镜头 8 · 受伤状态',
      shotIds: [],
      variantLabel: '分镜精调',
      variantScope: 'shot_variant',
      variantStageName: '镜头 8 · 受伤状态',
    })

    const resolved = resolveAssetTaskNavigationTarget({
      allAssets: [wrongButNamed, exactAsset],
      episode: 1,
      shotId: '03',
      assetId: 'character-99',
      assetLabel: '姐姐',
      matchedShot: buildShot(),
    })

    expect(resolved?.id).toBe('character-99')
  })

  it('can recover from an explicit default asset id to the matching shot variant for storyboard refinement', () => {
    const episodeDefault = buildAsset({
      id: 'character-21',
      assetRecordId: 21,
      shotIds: ['1-01'],
      siblingVariants: [
        { id: 'character-21', label: '分集默认', stageName: '第 1 集默认造型', episode: 1, status: 'ref_ready', scope: 'episode_default' },
        { id: 'character-31', label: '分镜精调', stageName: 'shot_13_episode_1', episode: 1, status: 'ref_ready', scope: 'shot_variant' },
      ],
    })
    const shotVariant = buildAsset({
      id: 'character-31',
      assetRecordId: 31,
      subtitle: 'shot 13 variant',
      shotIds: ['1-13'],
      variantLabel: '分镜精调',
      variantScope: 'shot_variant',
      variantStageName: 'shot_13_episode_1',
    })

    const resolved = resolveShotVariantNavigationTarget({
      allAssets: [episodeDefault, shotVariant],
      baseAsset: episodeDefault,
      episode: 1,
      shotId: '13',
    })

    expect(resolved?.id).toBe('character-31')
  })
})
