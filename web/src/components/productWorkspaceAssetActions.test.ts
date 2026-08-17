import { describe, expect, it } from 'vitest'

import { resolveAssetReferenceShotTarget } from './productWorkspaceAssetActions'

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
