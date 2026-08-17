import { describe, expect, it } from 'vitest'

import {
  collectCompiledReferenceAssetIds,
  collectStructuredReferenceAssetIds,
  resolveEffectiveReferenceAssetIds,
} from './productWorkspaceStoryboardReferencePayload'
import type { StoryboardShotOutput } from '../prototyping/sceneComposerData'

function makeShot(overrides: Partial<StoryboardShotOutput> = {}): StoryboardShotOutput {
  return {
    shot_id: '1-01',
    scene_name: '寺庙后院',
    assets: {
      images: [],
      videos: [],
      audios: [],
      references: { characters: {}, scene: [], props: {} },
    },
    ...overrides,
  }
}

describe('productWorkspaceStoryboardReferencePayload', () => {
  it('collects structured reference ids from shot reference images', () => {
    const shot = makeShot({
      reference_images: [
        { reference_asset_id: 'ref-character-1' },
        { reference_asset_id: ' ref-scene-1 ' },
        { reference_asset_id: 'ref-character-1' },
      ],
    })

    expect(collectStructuredReferenceAssetIds(shot)).toEqual(['ref-character-1', 'ref-scene-1'])
  })

  it('prefers compiled reference ids when compile context has an explicit list', () => {
    const shot = makeShot({
      reference_images: [{ reference_asset_id: 'ref-structured-1' }],
      prompt_compile_context: {
        compiled_reference_asset_ids: ['ref-compiled-1', ' ref-compiled-2 ', 'ref-compiled-1'],
      },
    })

    expect(collectCompiledReferenceAssetIds(shot)).toEqual(['ref-compiled-1', 'ref-compiled-2'])
    expect(resolveEffectiveReferenceAssetIds(shot)).toEqual({
      assetIds: ['ref-compiled-1', 'ref-compiled-2'],
      source: 'compiled',
    })
  })

  it('falls back to asset bindings when explicit compiled ids are absent', () => {
    const shot = makeShot({
      prompt_compile_context: {
        asset_bindings: {
          scene: {
            reference_asset_id: 'ref-scene-1',
            image_url: 'https://example.com/scene.png',
            has_reference: true,
          },
          characters: [
            {
              reference_asset_id: 'ref-character-1',
              image_url: 'https://example.com/char.png',
              has_reference: true,
            },
            {
              reference_asset_id: 'ref-character-2',
              image_url: '',
              has_reference: true,
            },
          ],
          props: [
            {
              reference_asset_id: 'ref-prop-1',
              image_url: 'https://example.com/prop.png',
              has_reference: true,
            },
          ],
        },
      },
    })

    expect(collectCompiledReferenceAssetIds(shot)).toEqual(['ref-scene-1', 'ref-character-1', 'ref-prop-1'])
  })

  it('falls back to structured ids when compile context has no usable references', () => {
    const shot = makeShot({
      reference_images: [{ reference_asset_id: 'ref-structured-1' }],
      prompt_compile_context: {
        asset_bindings: {
          scene: {
            reference_asset_id: 'ref-scene-ignored',
            image_url: '',
            has_reference: true,
          },
        },
      },
    })

    expect(resolveEffectiveReferenceAssetIds(shot)).toEqual({
      assetIds: ['ref-structured-1'],
      source: 'structured',
    })
  })
})
