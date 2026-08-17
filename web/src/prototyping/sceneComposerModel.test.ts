import { describe, expect, it } from 'vitest'
import {
  MOCK_BIBLE,
  MOCK_GENERATED_IMAGES,
  MOCK_QA,
  MOCK_SCRIPTS,
  MOCK_STORYBOARD,
  MOCK_VISUAL,
} from './mockData'
import {
  addConnection,
  adoptVersion,
  autoLayout,
  createTemplateDocument,
  deserializeDocument,
  duplicateNode,
  markDownstreamStale,
  serializeDocument,
  setReferenceLink,
  unadoptVersion,
  validateConnection,
} from './sceneComposerModel'
import { createRealEpisodeDocument } from './sceneComposerRealDocument'

const outputs = {
  bible: MOCK_BIBLE,
  scripts: MOCK_SCRIPTS,
  storyboard: MOCK_STORYBOARD,
  visual: MOCK_VISUAL,
  qa: MOCK_QA,
  generatedImages: MOCK_GENERATED_IMAGES,
}

describe('sceneComposerModel', () => {
  it('accepts only supported connection directions', () => {
    expect(validateConnection('script', 'shot')).toMatchObject({ ok: true, kind: 'reference' })
    expect(validateConnection('shot', 'image')).toMatchObject({ ok: true, kind: 'derived' })
    expect(validateConnection('video', 'sequence')).toMatchObject({ ok: true, kind: 'sequence' })
    expect(validateConnection('image', 'shot')).toMatchObject({ ok: false })
    expect(validateConnection('sequence', 'video')).toMatchObject({ ok: false })
  })

  it('marks downstream derived outputs stale after editing an upstream shot', () => {
    const document = createTemplateDocument(outputs)
    const updated = markDownstreamStale(document, 'shot-1-1')

    expect(updated.nodes.find((node) => node.id === 'image-seed-1-1')?.data.status).toBe('stale')
    expect(updated.nodes.find((node) => node.id === 'video-seed-1-1')?.data.status).toBe('stale')
    expect(updated.nodes.find((node) => node.id === 'sequence-1')?.data.status).toBe('done')
  })

  it('stores adopted versions by shot and media type', () => {
    const document = createTemplateDocument(outputs)
    const next = adoptVersion(document, 'image-seed-1-2')

    expect(next.adoptedVersions.image?.['1-2']).toBe('image-seed-1-2')
    expect(next.adoptedVersions.image?.['1-1']).toBe('image-seed-1-1')
  })

  it('removes adopted versions and sequence edges when unadopting a version', () => {
    const document = createTemplateDocument(outputs)
    const next = unadoptVersion(document, 'video-seed-1-1')

    expect(next.adoptedVersions.video?.['1-1']).toBeUndefined()
    expect(next.edges.some((edge) => edge.source === 'video-seed-1-1' && edge.target === 'sequence-1')).toBe(false)
  })

  it('serializes and restores the document shape', () => {
    const document = createTemplateDocument(outputs)
    const restored = deserializeDocument(serializeDocument(document))

    expect(restored.projectTitle).toBe(document.projectTitle)
    expect(restored.nodes).toHaveLength(document.nodes.length)
    expect(restored.edges).toHaveLength(document.edges.length)
    expect(restored.adoptedVersions.video?.['1-1']).toBe('video-seed-1-1')
  })

  it('adds valid connections and rejects invalid ones', () => {
    const document = createTemplateDocument(outputs)
    const connected = addConnection(document, 'prop-1', 'shot-1-2')

    expect(connected.edges.some((edge) => edge.source === 'prop-1' && edge.target === 'shot-1-2')).toBe(true)
    expect(() => addConnection(document, 'video-seed-1-1', 'shot-1-2')).toThrow()
  })

  it('toggles asset reference links for shots and marks downstream stale', () => {
    const document = createTemplateDocument(outputs)
    const linked = setReferenceLink(document, 'prop-1', 'shot-1-2', true)
    const unlinked = setReferenceLink(linked, 'prop-1', 'shot-1-2', false)

    expect(linked.edges.some((edge) => edge.source === 'prop-1' && edge.target === 'shot-1-2')).toBe(true)
    expect(linked.nodes.find((node) => node.id === 'image-seed-1-2')?.data.status).toBe('stale')
    expect(unlinked.edges.some((edge) => edge.source === 'prop-1' && edge.target === 'shot-1-2')).toBe(false)
  })

  it('duplicates a node into a separate branch draft', () => {
    const document = createTemplateDocument(outputs)
    const next = duplicateNode(document, 'image-seed-1-1')
    const duplicate = next.nodes[next.nodes.length - 1]

    expect(duplicate).toBeTruthy()
    expect(duplicate?.data.status).toBe('idle')
    expect(duplicate?.position.x).toBeGreaterThan(
      document.nodes.find((node) => node.id === 'image-seed-1-1')!.position.x,
    )
  })

  it('builds the template with reference, derived, and sequence edges', () => {
    const document = createTemplateDocument(outputs)

    expect(document.edges.some((edge) => edge.source === 'script-1' && edge.target === 'shot-1-1' && edge.data?.kind === 'reference')).toBe(true)
    expect(document.edges.some((edge) => edge.source === 'character-1' && edge.target === 'shot-1-1' && edge.data?.kind === 'reference')).toBe(true)
    expect(document.edges.some((edge) => edge.source === 'shot-1-1' && edge.target === 'image-seed-1-1' && edge.data?.kind === 'derived')).toBe(true)
    expect(document.edges.some((edge) => edge.source === 'image-seed-1-1' && edge.target === 'video-seed-1-1' && edge.data?.kind === 'derived')).toBe(true)
    expect(document.edges.some((edge) => edge.source === 'video-seed-1-1' && edge.target === 'sequence-1' && edge.data?.kind === 'sequence')).toBe(true)
  })

  it('auto layout keeps the workflow ordered from assets to sequence', () => {
    const document = autoLayout(createTemplateDocument(outputs))

    const location = document.nodes.find((node) => node.data.kind === 'location')
    const shot = document.nodes.find((node) => node.data.kind === 'shot')
    const image = document.nodes.find((node) => node.data.kind === 'image')
    const video = document.nodes.find((node) => node.data.kind === 'video')
    const sequence = document.nodes.find((node) => node.data.kind === 'sequence')

    expect(location && shot && image && video && sequence).toBeTruthy()
    expect(location!.position.x).toBeLessThan(shot!.position.x)
    expect(shot!.position.x).toBeLessThan(image!.position.x)
    expect(image!.position.x).toBeLessThan(video!.position.x)
    expect(video!.position.x).toBeLessThan(sequence!.position.x)
  })

  it('auto layout separates same-shot media versions into non-overlapping rows', () => {
    const base = createTemplateDocument(outputs)
    const expanded = {
      ...base,
      nodes: [
        ...base.nodes,
        {
          ...base.nodes.find((node) => node.id === 'image-seed-1-1')!,
          id: 'image-seed-1-1-v2',
          data: {
            ...base.nodes.find((node) => node.id === 'image-seed-1-1')!.data,
            title: '分镜图 1-1 v2',
            versionInfo: {
              ...base.nodes.find((node) => node.id === 'image-seed-1-1')!.data.versionInfo!,
              version: 2,
              label: 'v2',
            },
          },
        },
      ],
    }
    const laidOut = autoLayout(expanded)
    const imageV1 = laidOut.nodes.find((node) => node.id === 'image-seed-1-1')!
    const imageV2 = laidOut.nodes.find((node) => node.id === 'image-seed-1-1-v2')!
    const shot = laidOut.nodes.find((node) => node.id === 'shot-1-1')!

    expect(imageV1.position.x).toBe(620)
    expect(imageV2.position.x).toBe(620)
    expect(imageV2.position.y - imageV1.position.y).toBeGreaterThanOrEqual(240)
    expect(imageV1.position.y).toBeGreaterThanOrEqual(shot.position.y)
  })

  it('builds a real episode document without seeded demo media nodes', () => {
    const real = createRealEpisodeDocument(outputs, {
      episode: 1,
      projectTitle: '真实项目',
      episodeTitle: '第 1 集创作沙盒',
    })

    expect(real.projectTitle).toBe('真实项目')
    expect(real.nodes.some((node) => node.data.kind === 'script' && node.data.title === '第 1 集剧本')).toBe(true)
    expect(real.nodes.some((node) => node.data.kind === 'shot')).toBe(true)
    expect(real.nodes.some((node) => node.data.kind === 'image')).toBe(false)
    expect(real.nodes.some((node) => node.data.kind === 'video')).toBe(false)
    expect(real.edges.some((edge) => edge.source === 'script-1' && edge.target === 'shot-1-1')).toBe(true)
    expect(real.adoptedVersions.video).toEqual({})
  })

  it('dedupes repeated asset relationships in real data mapping', () => {
    const real = createRealEpisodeDocument({
      ...outputs,
      scripts: [{ episode: 1, content: '第一集' }],
      storyboard: {
        episodeShots: {
          1: [
            {
              episode: 1,
              shot_id: '1-1',
              scene_name: '街道',
              makeup_prompts: [{ character_name: '老头' }, { character_name: '老头' }],
            },
          ],
        },
      },
      visual: {
        ...outputs.visual,
        locations: [{ name: '街道', shot_ids: ['1-1', '1-1'] }],
        props: [{ name: '三轮车', shot_ids: ['1-1', '1-1'] }],
        makeups: [{ episode: 1, character_name: '老头', shot_ids: ['1-1', '1-1'] }],
      },
    })

    const referenceEdges = real.edges.filter((edge) => edge.target === 'shot-1-1' && edge.data?.kind === 'reference')
    expect(referenceEdges).toHaveLength(4)
  })

  it('supports empty episodes in real data mapping', () => {
    const real = createRealEpisodeDocument({
      ...outputs,
      scripts: [{ episode: 2, content: '第二集' }],
      storyboard: { episodeShots: {} },
      visual: { era: null, locations: [], props: [], makeups: [] },
      generatedImages: [],
    }, {
      episode: 2,
      projectTitle: '空项目',
    })

    expect(real.nodes.some((node) => node.data.kind === 'script')).toBe(true)
    expect(real.nodes.some((node) => node.data.kind === 'shot')).toBe(false)
    expect(real.nodes.some((node) => node.data.kind === 'sequence')).toBe(true)
    expect(real.edges).toHaveLength(0)
  })

  it('builds different episode documents for multi-episode real projects', () => {
    const multiEpisode = {
      ...outputs,
      scripts: [
        { episode: 1, content: '第一集内容' },
        { episode: 2, content: '第二集内容' },
      ],
      storyboard: {
        episodeShots: {
          1: [{ episode: 1, shot_id: '1-1', scene_name: '街道' }],
          2: [{ episode: 2, shot_id: '2-1', scene_name: '山洞' }],
        },
      },
      visual: { era: null, locations: [], props: [], makeups: [] },
    }

    const episode1 = createRealEpisodeDocument(multiEpisode, { episode: 1, projectTitle: '多集项目' })
    const episode2 = createRealEpisodeDocument(multiEpisode, { episode: 2, projectTitle: '多集项目' })

    expect(episode1.episodeTitle).toContain('第 1 集')
    expect(episode2.episodeTitle).toContain('第 2 集')
    expect(episode1.nodes.some((node) => node.data.title === '镜头 1-1')).toBe(true)
    expect(episode2.nodes.some((node) => node.data.title === '镜头 2-1')).toBe(true)
    expect(episode2.nodes.some((node) => node.data.title === '镜头 1-1')).toBe(false)
  })

  it('keeps per-episode documents distinct when switching storage scopes', () => {
    const episode1 = createRealEpisodeDocument({
      ...outputs,
      scripts: [{ episode: 1, content: '第一集内容' }],
      storyboard: { episodeShots: { 1: [{ episode: 1, shot_id: '1-1', scene_name: '街道' }] } },
      visual: { era: null, locations: [], props: [], makeups: [] },
    }, { episode: 1, projectTitle: '项目 A' })
    const episode2 = createRealEpisodeDocument({
      ...outputs,
      scripts: [{ episode: 2, content: '第二集内容' }],
      storyboard: { episodeShots: { 2: [{ episode: 2, shot_id: '2-1', scene_name: '山洞' }] } },
      visual: { era: null, locations: [], props: [], makeups: [] },
    }, { episode: 2, projectTitle: '项目 A' })

    expect(episode1.episodeTitle).toContain('第 1 集')
    expect(episode2.episodeTitle).toContain('第 2 集')
    expect(episode1.nodes.some((node) => node.data.title === '镜头 1-1')).toBe(true)
    expect(episode2.nodes.some((node) => node.data.title === '镜头 2-1')).toBe(true)
  })

  it('maps real image, video, and audio assets into canvas nodes and edges', () => {
    const real = createRealEpisodeDocument({
      ...outputs,
      scripts: [{ episode: 1, content: '第一集内容' }],
      storyboard: {
        episodeShots: {
          1: [
            {
              episode: 1,
              shot_id: '1-1',
              scene_name: '街道',
              visual_prompt_static: '老头推着三轮车',
              visual_prompt_motion: '镜头缓慢推进',
              assets: {
                images: [
                  {
                    id: 'img-a',
                    kind: 'image',
                    title: '分镜图 1-1 v1',
                    label: 'v1',
                    uri: 'https://example.com/storyboard-1-1.png',
                    adopted: true,
                  },
                ],
                videos: [
                  {
                    id: 'vid-a',
                    kind: 'video',
                    title: '视频 1-1 v1',
                    label: 'v1',
                    uri: 'https://example.com/video-1-1.mp4',
                    sourceAssetId: 'img-a',
                    adopted: true,
                  },
                ],
                audios: [
                  {
                    id: 'aud-a',
                    kind: 'audio',
                    title: '音频 1-1 v1',
                    label: 'v1',
                    uri: 'https://example.com/audio-1-1.wav',
                    adopted: true,
                  },
                ],
              },
            },
          ],
        },
      },
      visual: { era: null, locations: [], props: [], makeups: [] },
      generatedImages: [],
    }, {
      episode: 1,
      projectTitle: '真实媒体项目',
    })

    expect(real.nodes.some((node) => node.data.kind === 'image' && node.data.metadata?.source === 'real')).toBe(true)
    expect(real.nodes.some((node) => node.data.kind === 'video' && node.data.metadata?.source === 'real')).toBe(true)
    expect(real.nodes.some((node) => node.data.kind === 'audio' && node.data.metadata?.source === 'real')).toBe(true)
    expect(real.edges.some((edge) => edge.source === 'shot-1-1' && edge.data?.kind === 'derived')).toBe(true)
    expect(real.edges.some((edge) => edge.data?.kind === 'sequence' && edge.label === '镜头 1-1')).toBe(true)
    expect(real.adoptedVersions.video?.['1-1']).toBeTruthy()
    expect(real.adoptedVersions.audio?.['1-1']).toBeTruthy()
  })

  it('tags shot production nodes and asset nodes with product-facing scopes', () => {
    const document = createTemplateDocument(outputs)
    const shotNode = document.nodes.find((node) => node.id === 'shot-1-1')
    const characterNode = document.nodes.find((node) => node.id === 'character-1')
    const imageNode = document.nodes.find((node) => node.id === 'image-seed-1-1')

    expect(shotNode?.data.assetScope).toBe('shot')
    expect(characterNode?.data.assetScope).toBe('character')
    expect(imageNode?.data.imageRole).toBe('storyboard')
    expect(imageNode?.data.assetSubject).toBe('1-1')
  })

  it('marks real mapped storyboard images as storyboard-role assets', () => {
    const real = createRealEpisodeDocument({
      ...outputs,
      scripts: [{ episode: 1, content: '第一集内容' }],
      storyboard: {
        episodeShots: {
          1: [
            {
              episode: 1,
              shot_id: '1-1',
              scene_name: '街道',
              assets: {
                images: [
                  {
                    id: 'img-a',
                    kind: 'image',
                    title: '分镜图 1-1 v1',
                    label: 'v1',
                    uri: 'https://example.com/storyboard-1-1.png',
                    adopted: true,
                  },
                ],
                videos: [],
                audios: [],
              },
            },
          ],
        },
      },
      visual: { era: null, locations: [], props: [], makeups: [] },
      generatedImages: [],
    }, {
      episode: 1,
      projectTitle: '真实媒体项目',
    })

    const imageNode = real.nodes.find((node) => node.data.kind === 'image')
    expect(imageNode?.data.imageRole).toBe('storyboard')
    expect(imageNode?.data.assetScope).toBe('shot')
    expect(imageNode?.data.assetSubject).toBe('1-1')
  })

  it('maps reference assets into reference image nodes linked to assets and shots', () => {
    const real = createRealEpisodeDocument({
      ...outputs,
      scripts: [{ episode: 1, content: '第一集内容' }],
      storyboard: {
        episodeShots: {
          1: [
            {
              episode: 1,
              shot_id: '1-1',
              scene_name: '街道',
              makeup_prompts: [{ character_name: '老头' }],
              assets: {
                references: {
                  characters: {
                    老头: [
                      {
                        id: 'ref-char-a',
                        kind: 'image',
                        title: '老头 参考图 v1',
                        label: 'v1',
                        uri: 'https://example.com/char-a.png',
                        adopted: true,
                        metadata: { imageRole: 'reference', assetScope: 'character', assetSubject: '老头' },
                      },
                    ],
                  },
                  scene: [],
                  props: {},
                },
                images: [],
                videos: [],
                audios: [],
              },
            },
          ],
        },
      },
      visual: {
        era: null,
        locations: [],
        props: [],
        makeups: [{ episode: 1, character_name: '老头', shot_ids: ['1-1'] }],
      },
      generatedImages: [],
    }, {
      episode: 1,
      projectTitle: '参考图项目',
    })

    const referenceNode = real.nodes.find((node) => node.data.imageRole === 'reference')
    expect(referenceNode?.data.assetScope).toBe('character')
    expect(real.edges.some((edge) => edge.source === 'character-1' && edge.target === referenceNode?.id && edge.data?.kind === 'derived')).toBe(true)
    expect(real.edges.some((edge) => edge.source === referenceNode?.id && edge.target === 'shot-1-1' && edge.data?.kind === 'reference')).toBe(true)
  })

  it('creates unique readable reference node ids even when subjects contain chinese text', () => {
    const real = createRealEpisodeDocument({
      ...outputs,
      scripts: [{ episode: 1, content: '第一集内容' }],
      storyboard: {
        episodeShots: {
          1: [
            {
              episode: 1,
              shot_id: '1-1',
              scene_name: '城市道路边',
              assets: {
                references: {
                  characters: {},
                  scene: [
                    {
                      id: 'image-5ae83adf68',
                      kind: 'image',
                      title: '?????? 参考图 v1',
                      label: 'v1',
                      uri: 'https://example.com/scene-a.png',
                      adopted: true,
                    },
                  ],
                  props: {},
                },
                images: [],
                videos: [],
                audios: [],
              },
            },
            {
              episode: 1,
              shot_id: '1-2',
              scene_name: '林间空地',
              assets: {
                references: {
                  characters: {},
                  scene: [
                    {
                      id: 'image-0088a26e6b',
                      kind: 'image',
                      title: '97??? 参考图 v1',
                      label: 'v1',
                      uri: 'https://example.com/scene-b.png',
                      adopted: true,
                    },
                  ],
                  props: {},
                },
                images: [],
                videos: [],
                audios: [],
              },
            },
          ],
        },
      },
      visual: {
        era: null,
        locations: [
          { name: '城市道路边', shot_ids: ['1-1'] },
          { name: '林间空地', shot_ids: ['1-2'] },
        ],
        props: [],
        makeups: [],
      },
      generatedImages: [],
    }, {
      episode: 1,
      projectTitle: '参考图唯一键项目',
    })

    const referenceNodes = real.nodes.filter((node) => node.data.imageRole === 'reference')
    const ids = referenceNodes.map((node) => node.id)
    expect(new Set(ids).size).toBe(ids.length)
    expect(referenceNodes.map((node) => node.data.title)).toEqual(['城市道路边 参考图 v1', '林间空地 参考图 v1'])
  })
})
