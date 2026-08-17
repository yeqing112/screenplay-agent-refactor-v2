import { describe, expect, it } from 'vitest'
import { createEmptyOutputsData, normalizeBookOutputs } from './sceneComposerData'

describe('sceneComposerData', () => {
  it('normalizes complete real outputs into episode groups and sorts shot ids', () => {
    const data = normalizeBookOutputs({
      bible: '世界观',
      scripts: [
        { id: 2, episode: 2, content: '第二集' },
        { id: 1, episode: 1, content: '第一集' },
      ],
      storyboard: [
        { episode: 1, shot_id: '1-10', scene_name: '街道' },
        { episode: 1, shot_id: '1-2', scene_name: '街道' },
        { episode: 1, shot_id: 1, scene_name: '街道' },
        { episode: 2, shot_id: 1, scene_name: '天台' },
      ],
      visual: {
        locations: [{ name: '街道', shot_ids: ['1-1', '1-1', '1-2'] }],
        props: [{ name: '钥匙', shot_ids: ['1-1', '1-1'] }],
        makeups: [{ episode: 1, character_name: '老头', shot_ids: ['1-1', '1-2', '1-2'] }],
      },
    })

    expect(data.scripts.map((script) => script.episode)).toEqual([1, 2])
    expect(data.storyboard.episodeShots[1].map((shot) => shot.shot_id)).toEqual(['1', '1-2', '1-10'])
    expect(data.visual.locations[0].shot_ids).toEqual(['1-1', '1-2'])
    expect(data.visual.props[0].shot_ids).toEqual(['1-1'])
    expect(data.visual.makeups[0].shot_ids).toEqual(['1-1', '1-2'])
    expect(data.generatedImages).toEqual([])
  })

  it('provides safe defaults when optional visual fields are missing', () => {
    const data = normalizeBookOutputs({
      scripts: [{ episode: 1, content: '第一集' }],
      storyboard: [{ episode: 1, shot_id: '1-1', scene_name: '室内' }],
      visual: {
        locations: [{ name: '室内' }],
        props: [{ name: '桌子' }],
        makeups: [{ episode: 1, character_name: '女主' }],
      },
    })

    expect(data.visual.locations[0].description).toBe('')
    expect(data.visual.props[0].importance).toBe('medium')
    expect(data.visual.makeups[0].identity).toBe('')
    expect(data.visual.makeups[0].appearance).toBe('')
  })

  it('accepts storyboard payloads returned as keyed objects', () => {
    const data = normalizeBookOutputs({
      storyboard: {
        0: { episode: 1, shot_id: '1-2', scene_name: '街道' },
        1: { episode: 1, shot_id: '1-1', scene_name: '室内' },
        2: { episode: 2, shot_id: '2-1', scene_name: '山门' },
      },
    })

    expect(data.storyboard.episodeShots[1].map((shot) => shot.shot_id)).toEqual(['1-1', '1-2'])
    expect(data.storyboard.episodeShots[2].map((shot) => shot.shot_id)).toEqual(['2-1'])
  })

  it('normalizes real media assets from asset_links payloads', () => {
    const data = normalizeBookOutputs({
      storyboard: [
        {
          episode: 1,
          shot_id: 1,
          scene_name: '街道',
          asset_links: {
            images: [
              {
                id: 'img-a',
                url: 'https://example.com/shot-1-a.png',
                adopted: true,
                metadata: {
                  imageRole: 'storyboard',
                  referenceAssetIds: ['ref-a', 'ref-b'],
                  referenceAssetCount: 2,
                },
              },
              { id: 'img-b', url: 'https://example.com/shot-1-b.png' },
            ],
            videos: {
              items: [
                {
                  id: 'vid-a',
                  url: 'https://example.com/shot-1.mp4',
                  source_asset_id: 'img-a',
                  adopted: true,
                },
              ],
            },
            audio: ['https://example.com/shot-1.wav'],
          },
        },
      ],
    })

    const shot = data.storyboard.episodeShots[1][0]
    expect(shot.assets?.images).toHaveLength(2)
    expect(shot.assets?.images[0]).toMatchObject({
      id: 'img-a',
      adopted: true,
      uri: 'https://example.com/shot-1-a.png',
      metadata: expect.objectContaining({
        imageRole: 'storyboard',
        referenceAssetIds: ['ref-a', 'ref-b'],
        referenceAssetCount: 2,
      }),
    })
    expect(shot.assets?.videos[0]).toMatchObject({
      id: 'vid-a',
      sourceAssetId: 'img-a',
      adopted: true,
    })
    expect(shot.assets?.audios[0]).toMatchObject({
      kind: 'audio',
      adopted: true,
    })
  })

  it('normalizes reference assets from asset_links.references payloads', () => {
    const data = normalizeBookOutputs({
      storyboard: [
        {
          episode: 1,
          shot_id: 1,
          scene_name: '街道',
          asset_links: {
            references: {
              characters: {
                老头: [{ id: 'ref-char-a', url: 'https://example.com/char-a.png', adopted: true }],
              },
              scene: [{ id: 'ref-scene-a', url: 'https://example.com/scene-a.png', adopted: true }],
              props: {
                三轮车: [{ id: 'ref-prop-a', url: 'https://example.com/prop-a.png', adopted: true }],
              },
            },
          },
        },
      ],
    })

    const shot = data.storyboard.episodeShots[1][0]
    expect(shot.assets?.references?.characters['老头'][0]).toMatchObject({
      id: 'ref-char-a',
      kind: 'image',
      metadata: expect.objectContaining({
        imageRole: 'reference',
        assetScope: 'character',
        assetSubject: '老头',
      }),
    })
    expect(shot.assets?.references?.scene[0]).toMatchObject({
      id: 'ref-scene-a',
      metadata: expect.objectContaining({
        assetScope: 'location',
      }),
    })
    expect(shot.assets?.references?.props['三轮车'][0]).toMatchObject({
      id: 'ref-prop-a',
      metadata: expect.objectContaining({
        assetScope: 'prop',
      }),
    })
  })

  it('falls back to readable asset titles when stored titles are corrupted', () => {
    const data = normalizeBookOutputs({
      storyboard: [
        {
          episode: 1,
          shot_id: 1,
          scene_name: '街道',
          asset_links: {
            images: [
              {
                id: 'img-a',
                url: 'https://example.com/shot-1-a.png',
                title: '?????? 参考图 v1',
                label: 'v1',
              },
            ],
          },
        },
      ],
    })

    expect(data.storyboard.episodeShots[1][0].assets?.images[0].title).toBe('分镜图 1 v1')
  })

  it('creates an explicit empty state for new or missing projects', () => {
    const empty = createEmptyOutputsData()

    expect(empty.scripts).toEqual([])
    expect(empty.storyboard.episodeShots).toEqual({})
    expect(empty.visual.locations).toEqual([])
    expect(empty.generatedImages).toEqual([])
  })
})
