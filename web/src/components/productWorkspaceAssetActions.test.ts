import { describe, expect, it } from 'vitest'

import { buildAssetGenerationReferenceImages, resolveAssetReferenceShotTarget } from './productWorkspaceAssetActions'

describe('resolveAssetReferenceShotTarget', () => {
  it('prefers explicit shot ids when the asset already has saved bindings', () => {
    const result = resolveAssetReferenceShotTarget({
      assetEpisodeFilter: 2,
      selectedAsset: {
        episodeIds: [1, 2],
        shotIds: ['2-08', '1-03'],
      },
      inferredShotIds: ['2-09', '1-07'],
    })

    expect(result.preferredEpisode).toBe(2)
    expect(result.shotId).toBe('2-08')
    expect(result.relatedShotIds).toEqual(['2-08', '1-03', '2-09', '1-07'])
    expect(result.usedInferredShot).toBe(false)
  })

  it('falls back to inferred impact shots when there are no saved shot bindings yet', () => {
    const result = resolveAssetReferenceShotTarget({
      assetEpisodeFilter: 1,
      selectedAsset: {
        episodeIds: [1],
        shotIds: [],
      },
      inferredShotIds: ['1-06', '1-04'],
    })

    expect(result.preferredEpisode).toBe(1)
    expect(result.shotId).toBe('1-06')
    expect(result.relatedShotIds).toEqual(['1-06', '1-04'])
    expect(result.usedInferredShot).toBe(true)
  })

  it('falls back to an episode-based default when neither explicit nor inferred shots exist', () => {
    const result = resolveAssetReferenceShotTarget({
      assetEpisodeFilter: 3,
      selectedAsset: {
        episodeIds: [],
        shotIds: [],
      },
      inferredShotIds: [],
    })

    expect(result.preferredEpisode).toBe(3)
    expect(result.shotId).toBe('3-1')
    expect(result.relatedShotIds).toEqual([])
    expect(result.usedInferredShot).toBe(false)
  })
})

describe('buildAssetGenerationReferenceImages', () => {
  it('only carries locked or selected references, retaining their stable identity order', () => {
    const references = buildAssetGenerationReferenceImages({
      category: 'character',
      title: '林晚',
      references: [
        { id: 7, image_url: '/candidate.png', status: 'candidate' },
        { id: 9, image_url: '/selected.png', status: 'selected', reference_token: '@林晚' },
        { id: 4, image_url: '/locked.png', status: 'locked', asset_type: 'character', asset_id: '587' },
        { id: 3, status: 'locked' },
      ],
    })

    expect(references).toHaveLength(2)
    expect(references.map((item) => item.reference_asset_id)).toEqual(['ref-4', 'ref-9'])
    expect(references[0]).toMatchObject({
      image_url: '/locked.png',
      role: 'character',
      reference_purpose: 'identity_costume_face_hair',
      asset_id: '587',
    })
    expect(references[1].image_url).toBe('/selected.png')
  })
})
