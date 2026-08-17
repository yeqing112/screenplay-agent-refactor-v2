import type { Edge, Node, Viewport } from 'reactflow'
import type {
  OutputsData,
  StoryboardShotOutput,
  VisualLocationOutput,
  VisualMakeupOutput,
  VisualPropOutput,
} from './sceneComposerData'

export type CreativeNodeKind =
  | 'script'
  | 'shot'
  | 'character'
  | 'location'
  | 'prop'
  | 'image'
  | 'video'
  | 'audio'
  | 'sequence'

export type CreativeNodeStatus = 'idle' | 'running' | 'done' | 'error' | 'stale'
export type ConnectionKind = 'reference' | 'derived' | 'sequence'
export type VersionKind = 'image' | 'video' | 'audio'
export type ImageRole = 'reference' | 'storyboard' | 'video_preview'
export type AssetScope = 'character' | 'location' | 'prop' | 'shot'
export type ReviewStatus = 'pending' | 'approved' | 'changes_requested' | 'accepted'
export type MetadataValue = string | number | boolean | string[] | undefined

export interface GenerationConfig {
  model: string
  prompt: string
  aspectRatio: string
  durationSeconds?: number
  count: number
}

export interface VersionInfo {
  version: number
  label: string
  shotId?: string
  sourceNodeId?: string
  createdAt: string
}

export interface CreativeNodeData {
  kind: CreativeNodeKind
  title: string
  summary: string
  status: CreativeNodeStatus
  prompt: string
  notes?: string
  metadata?: Record<string, MetadataValue>
  shotId?: string
  episode?: number
  scriptEpisode?: number
  versionInfo?: VersionInfo
  generation?: GenerationConfig
  previewUrl?: string
  content?: string
  references?: string[]
  errorMessage?: string
  imageRole?: ImageRole
  assetScope?: AssetScope
  assetSubject?: string
  ui?: {
    dimmed?: boolean
    emphasized?: boolean
    referenceSummary?: string
    outputSummary?: string
    production?: {
      referenceState?: string
      imageState?: string
      videoState?: string
      sequenceState?: string
      riskHint?: string
    }
  }
}

export type CreativeNode = Node<CreativeNodeData, 'creative'>
export type CreativeEdge = Edge<{ kind: ConnectionKind }>

export interface CanvasDocument {
  version: number
  projectTitle: string
  episodeTitle: string
  nodes: CreativeNode[]
  edges: CreativeEdge[]
  viewport: Viewport
  adoptedVersions: Partial<Record<VersionKind, Record<string, string>>>
  tutorialDismissed: boolean
  lastSavedAt?: string
  deliveryRecords?: Array<{
    id: string
    createdAt: string
    versionLabel: string
    status: 'delivered' | 'stale'
    summary: string
    shotCount: number
  }>
}

export interface ConnectionValidation {
  ok: boolean
  kind?: ConnectionKind
  reason?: string
}

export interface GenerationOutcome {
  node: CreativeNode
  edge: CreativeEdge
}

export const SCENE_COMPOSER_STORAGE_KEY = 'scene-composer-document-v2'

const VERSION_COUNTERS: Record<VersionKind, number> = {
  image: 0,
  video: 0,
  audio: 0,
}

const EDGE_COLORS: Record<ConnectionKind, string> = {
  reference: '#64748b',
  derived: '#f59e0b',
  sequence: '#22c55e',
}

export function serializeDocument(document: CanvasDocument): string {
  return JSON.stringify(document)
}

export function deserializeDocument(raw: string): CanvasDocument {
  const parsed = JSON.parse(raw) as CanvasDocument
  return {
    ...parsed,
    viewport: parsed.viewport ?? { x: 0, y: 0, zoom: 1 },
    adoptedVersions: parsed.adoptedVersions ?? {},
    tutorialDismissed: parsed.tutorialDismissed ?? false,
    deliveryRecords: parsed.deliveryRecords ?? [],
  }
}

function buildSequenceEdges(document: CanvasDocument): CreativeEdge[] {
  const sequenceNode = document.nodes.find((node) => node.data.kind === 'sequence')
  if (!sequenceNode) {
    return []
  }

  const videoEdges = Object.entries(document.adoptedVersions.video ?? {})
    .filter(([, nodeId]) => document.nodes.some((node) => node.id === nodeId))
    .map(([shotId, nodeId]) =>
      createEdge(`sequence-video-${shotId}`, nodeId, sequenceNode.id, 'sequence', `镜头 ${shotId}`),
    )

  const audioEdges = Object.entries(document.adoptedVersions.audio ?? {})
    .filter(([, nodeId]) => document.nodes.some((node) => node.id === nodeId))
    .map(([shotId, nodeId]) => {
      const audioNode = document.nodes.find((node) => node.id === nodeId)
      return createEdge(
        `sequence-audio-${shotId}`,
        nodeId,
        sequenceNode.id,
        'sequence',
        audioNode?.data.title ?? `音频 ${shotId}`,
      )
    })

  return [...videoEdges, ...audioEdges]
}

function syncSequenceEdges(document: CanvasDocument): CanvasDocument {
  return {
    ...document,
    edges: [
      ...document.edges.filter((edge) => edge.data?.kind !== 'sequence'),
      ...buildSequenceEdges(document),
    ],
  }
}

export function createTemplateDocument(data: OutputsData): CanvasDocument {
  const shots = data.storyboard.episodeShots[1] ?? []
  const visual = data.visual
  const now = new Date()

  const locationNodes = (visual.locations ?? []).slice(0, 1).map((item, index) =>
    createNode(`location-${index + 1}`, 'location', {
      title: item.name,
      summary: item.description,
      prompt: item.visual_prompt_zh ?? item.zh_prompt ?? '',
      assetScope: 'location',
      assetSubject: item.name,
      position: { x: -560, y: 40 + index * 190 },
      content: [item.style, item.lighting_mood, item.color_palette].filter(Boolean).join('\n'),
      metadata: {
        era: item.era,
        category: item.category,
      },
    }),
  )

  const characterNodes = (visual.makeups ?? []).slice(0, 2).map((item, index) =>
    createNode(`character-${index + 1}`, 'character', {
      title: item.character_name,
      summary: item.temperament,
      prompt: item.visual_prompt_zh ?? '',
      assetScope: 'character',
      assetSubject: item.character_name,
      notes: item.refined_outfit,
      content: [item.identity, item.appearance, item.makeup_spec].filter(Boolean).join('\n'),
      position: { x: -560, y: 250 + index * 190 },
      metadata: {
        outfit: item.refined_outfit,
        hair: item.hair_style,
      },
    }),
  )

  const propNodes = (visual.props ?? []).slice(0, 2).map((item, index) =>
    createNode(`prop-${index + 1}`, 'prop', {
      title: item.name,
      summary: item.description,
      prompt: item.zh_prompt ?? '',
      assetScope: 'prop',
      assetSubject: item.name,
      position: { x: -560, y: 640 + index * 170 },
      content: item.description,
      metadata: {
        importance: item.importance,
        category: item.category,
      },
    }),
  )

  const scriptNode = createNode('script-1', 'script', {
    title: '第 1 集剧本',
    summary: '单集短剧剧本与本集创作目标。',
    position: { x: -160, y: 140 },
    content: data.scripts[0]?.content ?? '',
    notes: data.bible,
    metadata: {
      episode: 1,
      shots: shots.length,
    },
  })

  const shotNodes = shots.slice(0, 5).map((shot, index) =>
    createNode(`shot-${shot.shot_id}`, 'shot', {
      title: `镜头 ${shot.shot_id}`,
      summary: shot.dialogue || shot.start_state || shot.scene_name,
      prompt: shot.visual_prompt_static || '',
      notes: shot.visual_prompt_motion || '',
      shotId: shot.shot_id,
      assetScope: 'shot',
      assetSubject: shot.shot_id,
      episode: 1,
      position: { x: 220 + index * 280, y: 100 + (index % 2) * 250 },
      content: [
        `场景：${shot.scene_name}`,
        `机位：${shot.camera_angle} / ${shot.camera_movement}`,
        `时长：${shot.duration} 秒`,
      ].join('\n'),
      metadata: {
        scene: shot.scene_name,
        camera: shot.camera_angle,
        movement: shot.camera_movement,
      },
    }),
  )

  const imageNodes = shots.slice(0, 2).map((shot, index) =>
    createNode(`image-seed-${shot.shot_id}`, 'image', {
      title: `分镜图 ${shot.shot_id} v1`,
      summary: '当前镜头的首版分镜图候选。',
      prompt: shot.visual_prompt_static || '',
      shotId: shot.shot_id,
      imageRole: 'storyboard',
      assetScope: 'shot',
      assetSubject: shot.shot_id,
      episode: 1,
      status: 'done',
      previewUrl: makePlaceholderAsset(`分镜图 ${shot.shot_id}`, '#f59e0b', 'Seedream v4.5'),
      position: { x: 380 + index * 320, y: 540 },
      versionInfo: {
        version: 1,
        label: 'v1',
        shotId: shot.shot_id,
        sourceNodeId: `shot-${shot.shot_id}`,
        createdAt: new Date('2026-06-22T20:00:00Z').toISOString(),
      },
      generation: {
        model: 'Seedream v4.5',
        prompt: shot.visual_prompt_static || '',
        aspectRatio: '16:9',
        count: 1,
      },
    }),
  )

  const videoNode = createNode('video-seed-1-1', 'video', {
    title: '视频 1-1 v1',
    summary: '镜头 1-1 当前采用的运动版本。',
    prompt: shots[0]?.visual_prompt_motion || '',
    shotId: shots[0]?.shot_id,
    assetScope: 'shot',
    assetSubject: shots[0]?.shot_id,
    episode: 1,
    status: 'done',
    previewUrl: makePlaceholderAsset('视频 1-1', '#22c55e', 'Kling 1.6'),
    position: { x: 760, y: 810 },
    versionInfo: {
      version: 1,
      label: 'v1',
      shotId: shots[0]?.shot_id,
      sourceNodeId: 'image-seed-1-1',
      createdAt: new Date('2026-06-22T20:05:00Z').toISOString(),
    },
    generation: {
      model: 'Kling 1.6',
      prompt: shots[0]?.visual_prompt_motion || '',
      aspectRatio: '16:9',
      durationSeconds: 5,
      count: 1,
    },
  })

  const videoNode2 = createNode('video-seed-1-2', 'video', {
    title: '视频 1-2 v1',
    summary: '镜头 1-2 当前采用的运动版本。',
    prompt: shots[1]?.visual_prompt_motion || '',
    shotId: shots[1]?.shot_id,
    assetScope: 'shot',
    assetSubject: shots[1]?.shot_id,
    episode: 1,
    status: 'done',
    previewUrl: makePlaceholderAsset('视频 1-2', '#22c55e', 'Kling 1.6'),
    position: { x: 1080, y: 810 },
    versionInfo: {
      version: 1,
      label: 'v1',
      shotId: shots[1]?.shot_id,
      sourceNodeId: 'image-seed-1-2',
      createdAt: new Date('2026-06-22T20:06:00Z').toISOString(),
    },
    generation: {
      model: 'Kling 1.6',
      prompt: shots[1]?.visual_prompt_motion || '',
      aspectRatio: '16:9',
      durationSeconds: 5,
      count: 1,
    },
  })

  const audioNode = createNode('audio-1', 'audio', {
    title: '对白 / 环境音',
    summary: '临时对白、音效与路边环境氛围音。',
    status: 'done',
    content: '对白参考、轻微车流声、链条晃动声与城市底噪混合轨。',
    prompt: '低音量城市环境声，保持生活化现场感。',
    position: { x: 1080, y: 600 },
    versionInfo: {
      version: 1,
      label: 'mix-a',
      shotId: shots[0]?.shot_id,
      createdAt: new Date('2026-06-22T20:09:00Z').toISOString(),
    },
  })

  const sequenceNode = createNode('sequence-1', 'sequence', {
    title: '第 1 集成片序列',
    summary: '按当前采用版本汇总的镜头视频与音频序列。',
    status: 'done',
    content: '用于演示交付顺序的成片预览组合。',
    position: { x: 1420, y: 710 },
    metadata: {
      shots: shotNodes.length,
      adopted: 2,
    },
  })

  const nodes = [
    scriptNode,
    ...locationNodes,
    ...characterNodes,
    ...propNodes,
    ...shotNodes,
    ...imageNodes,
    videoNode,
    videoNode2,
    audioNode,
    sequenceNode,
  ]

  const edges: CreativeEdge[] = [
    ...shotNodes.map((shotNode) =>
      createEdge(`script-to-${shotNode.id}`, scriptNode.id, shotNode.id, 'reference'),
    ),
    ...shotNodes.flatMap((shotNode) => {
      const shared: CreativeEdge[] = []
      if (locationNodes[0]) {
        shared.push(createEdge(`location-to-${shotNode.id}`, locationNodes[0].id, shotNode.id, 'reference'))
      }
      if (characterNodes[0]) {
        shared.push(createEdge(`character-a-to-${shotNode.id}`, characterNodes[0].id, shotNode.id, 'reference'))
      }
      if (characterNodes[1] && shotNode.id !== 'shot-1-1') {
        shared.push(createEdge(`character-b-to-${shotNode.id}`, characterNodes[1].id, shotNode.id, 'reference'))
      }
      if (propNodes[0] && shotNode.id === 'shot-1-1') {
        shared.push(createEdge(`prop-a-to-${shotNode.id}`, propNodes[0].id, shotNode.id, 'reference'))
      }
      if (propNodes[1] && shotNode.id === 'shot-1-4') {
        shared.push(createEdge(`prop-b-to-${shotNode.id}`, propNodes[1].id, shotNode.id, 'reference'))
      }
      return shared
    }),
    createEdge('shot-1-1-to-image', 'shot-1-1', 'image-seed-1-1', 'derived'),
    createEdge('shot-1-2-to-image', 'shot-1-2', 'image-seed-1-2', 'derived'),
    createEdge('image-to-video', 'image-seed-1-1', 'video-seed-1-1', 'derived'),
    createEdge('image2-to-video2', 'image-seed-1-2', 'video-seed-1-2', 'derived'),
    createEdge('video-to-sequence', 'video-seed-1-1', 'sequence-1', 'sequence', '镜头 1-1'),
    createEdge('video2-to-sequence', 'video-seed-1-2', 'sequence-1', 'sequence', '镜头 1-2'),
    createEdge('audio-to-sequence', 'audio-1', 'sequence-1', 'sequence', '环境音轨'),
  ]

  return syncSequenceEdges({
    version: 2,
    projectTitle: '最大的傲慢',
    episodeTitle: '第 1 集创作沙盘',
    nodes,
    edges,
    viewport: { x: 80, y: 120, zoom: 0.72 },
    adoptedVersions: {
      image: { [shots[0]?.shot_id ?? '1-1']: 'image-seed-1-1' },
      video: {
        [shots[0]?.shot_id ?? '1-1']: 'video-seed-1-1',
        ...(shots[1]?.shot_id ? { [shots[1].shot_id]: 'video-seed-1-2' } : {}),
      },
      audio: { [shots[0]?.shot_id ?? '1-1']: 'audio-1' },
    },
    tutorialDismissed: false,
    lastSavedAt: now.toISOString(),
  })
}

export function createEpisodeTemplateDocument(
  data: OutputsData,
  options?: { episode?: number; projectTitle?: string; episodeTitle?: string },
): CanvasDocument {
  const availableEpisodes = data.scripts.map((script) => script.episode).sort((a, b) => a - b)
  const episode = options?.episode ?? availableEpisodes[0] ?? 1
  const shots = (data.storyboard.episodeShots[episode] ?? []).slice(0, 8)
  const visual = data.visual
  const now = new Date()
  const script = data.scripts.find((item) => item.episode === episode) ?? data.scripts[0]
  const shotIds = new Set(shots.map((shot) => shot.shot_id))

  const locationAssets = (visual.locations ?? []).filter(
    (location) =>
      (location.shot_ids ?? []).some((shotId) => shotIds.has(shotId)) ||
      shots.some((shot) => shot.scene_name === location.name),
  )
  const characterAssets = dedupeByName(
    (visual.makeups ?? [])
      .filter((makeup) => makeup.episode === episode || (makeup.shot_ids ?? []).some((shotId) => shotIds.has(shotId)))
      .filter(
        (makeup) =>
          (makeup.shot_ids ?? []).some((shotId) => shotIds.has(shotId)) ||
          shots.some((shot) => (shot.makeup_prompts ?? []).some((prompt) => prompt.character_name === makeup.character_name)),
      ),
    (item) => item.character_name,
  )
  const propAssets = (visual.props ?? []).filter((prop) => (prop.shot_ids ?? []).some((shotId) => shotIds.has(shotId)))

  const locationNodes = locationAssets.map((item, index) =>
    createNode(`location-${index + 1}`, 'location', {
      title: item.name,
      summary: item.description ?? item.style ?? '待补充场景描述',
      prompt: item.visual_prompt_zh ?? item.zh_prompt ?? item.core_prompt_zh ?? '',
      assetScope: 'location',
      assetSubject: item.name,
      position: { x: -560, y: 40 + index * 190 },
      content: [item.style, item.lighting_mood, item.color_palette].filter(Boolean).join('\n'),
      metadata: {
        category: item.category,
        shotIds: (item.shot_ids ?? []).join(','),
      },
    }),
  )

  const characterNodes = characterAssets.map((item, index) =>
    createNode(`character-${index + 1}`, 'character', {
      title: item.character_name,
      summary: item.temperament ?? item.expression_mood ?? '待补充角色描述',
      prompt: item.visual_prompt_zh ?? '',
      assetScope: 'character',
      assetSubject: item.character_name,
      notes: [item.refined_outfit, item.refined_accessories].filter(Boolean).join(' / '),
      content: [item.identity, item.appearance, item.makeup_spec].filter(Boolean).join('\n'),
      position: { x: -560, y: 250 + index * 190 },
      metadata: {
        outfit: item.refined_outfit,
        hair: item.hair_style,
        shotIds: (item.shot_ids ?? []).join(','),
      },
    }),
  )

  const propNodes = propAssets.map((item, index) =>
    createNode(`prop-${index + 1}`, 'prop', {
      title: item.name,
      summary: item.description ?? '待补充道具描述',
      prompt: item.visual_prompt_zh ?? item.zh_prompt ?? item.core_prompt_zh ?? '',
      assetScope: 'prop',
      assetSubject: item.name,
      position: { x: -560, y: 640 + index * 170 },
      content: item.description,
      metadata: {
        importance: item.importance,
        category: item.category,
        shotIds: (item.shot_ids ?? []).join(','),
      },
    }),
  )

  const scriptNode = createNode('script-1', 'script', {
    title: `第 ${episode} 集剧本`,
    summary: '单集短剧剧本与本集创作目标。',
    position: { x: -160, y: 140 },
    content: script?.content ?? '',
    notes: data.bible,
    metadata: {
      episode,
      shots: shots.length,
    },
  })

  const shotNodes = shots.map((shot, index) =>
    createNode(`shot-${shot.shot_id}`, 'shot', {
      title: `镜头 ${shot.shot_id}`,
      summary: shot.dialogue || shot.start_state || shot.scene_name,
      prompt: shot.visual_prompt_static || '',
      notes: shot.visual_prompt_motion || '',
      shotId: shot.shot_id,
      assetScope: 'shot',
      assetSubject: shot.shot_id,
      episode,
      position: { x: 220 + index * 280, y: 100 + (index % 2) * 250 },
      content: [
        `场景：${shot.scene_name}`,
        `机位：${shot.camera_angle ?? '待补充'} / ${shot.camera_movement ?? '待补充'}`,
        `时长：${shot.duration ?? 0} 秒`,
      ].join('\n'),
      metadata: {
        scene: shot.scene_name,
        camera: shot.camera_angle,
        movement: shot.camera_movement,
      },
    }),
  )

  const seededShots = shots.slice(0, Math.min(2, shots.length))
  const imageNodes = seededShots.map((shot, index) =>
    createNode(`image-seed-${shot.shot_id}`, 'image', {
      title: `分镜图 ${shot.shot_id} v1`,
      summary: '当前镜头的首版分镜图候选。',
      prompt: shot.visual_prompt_static || '',
      shotId: shot.shot_id,
      imageRole: 'storyboard',
      assetScope: 'shot',
      assetSubject: shot.shot_id,
      episode,
      status: 'done',
      previewUrl: makePlaceholderAsset(`分镜图 ${shot.shot_id}`, '#f59e0b', 'Seedream v4.5'),
      position: { x: 380 + index * 320, y: 540 },
      versionInfo: {
        version: 1,
        label: 'v1',
        shotId: shot.shot_id,
        sourceNodeId: `shot-${shot.shot_id}`,
        createdAt: new Date('2026-06-22T20:00:00Z').toISOString(),
      },
      generation: {
        model: 'Seedream v4.5',
        prompt: shot.visual_prompt_static || '',
        aspectRatio: '16:9',
        count: 1,
      },
    }),
  )

  const videoNodes = seededShots.map((shot, index) =>
    createNode(`video-seed-${shot.shot_id}`, 'video', {
      title: `视频 ${shot.shot_id} v1`,
      summary: `镜头 ${shot.shot_id} 当前采用的运动版本。`,
      prompt: shot.visual_prompt_motion || '',
      shotId: shot.shot_id,
      assetScope: 'shot',
      assetSubject: shot.shot_id,
      episode,
      status: 'done',
      previewUrl: makePlaceholderAsset(`视频 ${shot.shot_id}`, '#22c55e', 'Kling 1.6'),
      position: { x: 760 + index * 320, y: 810 },
      versionInfo: {
        version: 1,
        label: 'v1',
        shotId: shot.shot_id,
        sourceNodeId: `image-seed-${shot.shot_id}`,
        createdAt: new Date(`2026-06-22T20:0${5 + index}:00Z`).toISOString(),
      },
      generation: {
        model: 'Kling 1.6',
        prompt: shot.visual_prompt_motion || '',
        aspectRatio: '16:9',
        durationSeconds: 5,
        count: 1,
      },
    }),
  )

  const audioNode = createNode('audio-1', 'audio', {
    title: '对白 / 环境音',
    summary: '临时对白、音效与路边环境氛围音轨。',
    status: 'done',
    content: '对白参考、轻微车流声、链条晃动声与城市底噪混合轨。',
    prompt: '低音量城市环境声，保持生活化现场感。',
    shotId: shots[0]?.shot_id,
    position: { x: 1080, y: 600 },
    versionInfo: {
      version: 1,
      label: 'mix-a',
      shotId: shots[0]?.shot_id,
      createdAt: new Date('2026-06-22T20:09:00Z').toISOString(),
    },
  })

  const sequenceNode = createNode('sequence-1', 'sequence', {
    title: `第 ${episode} 集成片序列`,
    summary: '按当前采用版本汇总的镜头视频与音频序列。',
    status: 'done',
    content: '用于演示交付顺序的成片预览组合。',
    position: { x: 1420, y: 710 },
    metadata: {
      shots: shotNodes.length,
      adopted: videoNodes.length,
    },
  })

  const nodes = [
    scriptNode,
    ...locationNodes,
    ...characterNodes,
    ...propNodes,
    ...shotNodes,
    ...imageNodes,
    ...videoNodes,
    audioNode,
    sequenceNode,
  ]

  const locationNodeByName = new Map(locationNodes.map((node) => [node.data.title, node]))
  const characterNodeByName = new Map(characterNodes.map((node) => [node.data.title, node]))
  const imageNodeByShotId = new Map(imageNodes.map((node) => [node.data.shotId, node]))
  const videoNodeByShotId = new Map(videoNodes.map((node) => [node.data.shotId, node]))

  const edges: CreativeEdge[] = [
    ...shotNodes.map((shotNode) => createEdge(`script-to-${shotNode.id}`, scriptNode.id, shotNode.id, 'reference')),
    ...buildLocationReferenceEdges(shots, shotNodes, locationAssets, locationNodeByName),
    ...buildCharacterReferenceEdges(shots, shotNodes, characterAssets, characterNodeByName),
    ...buildPropReferenceEdges(shots, shotNodes, propAssets, propNodes),
    ...seededShots.flatMap((shot) => {
      const derived: CreativeEdge[] = []
      const imageNode = imageNodeByShotId.get(shot.shot_id)
      const videoNode = videoNodeByShotId.get(shot.shot_id)
      if (imageNode) {
        derived.push(createEdge(`shot-${shot.shot_id}-to-image`, `shot-${shot.shot_id}`, imageNode.id, 'derived'))
      }
      if (imageNode && videoNode) {
        derived.push(createEdge(`${imageNode.id}-to-${videoNode.id}`, imageNode.id, videoNode.id, 'derived'))
      }
      return derived
    }),
  ]

  return syncSequenceEdges({
    version: 2,
    projectTitle: options?.projectTitle ?? '未命名项目',
    episodeTitle: options?.episodeTitle ?? `第 ${episode} 集创作沙盒`,
    nodes,
    edges,
    viewport: { x: 80, y: 120, zoom: 0.72 },
    adoptedVersions: {
      image: Object.fromEntries(imageNodes.map((node) => [node.data.shotId ?? '', node.id]).filter(([shotId]) => shotId)),
      video: Object.fromEntries(videoNodes.map((node) => [node.data.shotId ?? '', node.id]).filter(([shotId]) => shotId)),
      audio: shots[0]?.shot_id ? { [shots[0].shot_id]: 'audio-1' } : {},
    },
    tutorialDismissed: false,
    lastSavedAt: now.toISOString(),
  })
}

export function createNode(
  id: string,
  kind: CreativeNodeKind,
  options: Partial<CreativeNodeData> & { position: { x: number; y: number } },
): CreativeNode {
  return {
    id,
    type: 'creative',
    position: options.position,
    data: {
      kind,
      title: options.title ?? kindLabel(kind),
      summary: options.summary ?? '',
      status: options.status ?? 'idle',
      prompt: options.prompt ?? '',
      notes: options.notes,
      metadata: options.metadata,
      shotId: options.shotId,
      episode: options.episode,
      scriptEpisode: options.scriptEpisode,
      versionInfo: options.versionInfo,
      generation: options.generation,
      previewUrl: options.previewUrl,
      content: options.content,
      references: options.references ?? [],
      errorMessage: options.errorMessage,
      imageRole: options.imageRole,
      assetScope: options.assetScope,
      assetSubject: options.assetSubject,
    },
  }
}

export function createEdge(
  id: string,
  source: string,
  target: string,
  kind: ConnectionKind,
  label?: string,
): CreativeEdge {
  return {
    id,
    source,
    target,
    type: 'smoothstep',
    animated: kind !== 'reference',
    label,
    style: {
      stroke: EDGE_COLORS[kind],
      strokeWidth: kind === 'reference' ? 1.3 : kind === 'sequence' ? 2.2 : 1.8,
      strokeDasharray: kind === 'reference' ? '6 6' : undefined,
    },
    data: { kind },
  }
}

export function validateConnection(
  sourceKind?: CreativeNodeKind,
  targetKind?: CreativeNodeKind,
): ConnectionValidation {
  if (!sourceKind || !targetKind) {
    return { ok: false, reason: '缺少来源节点或目标节点。' }
  }

  if (sourceKind === targetKind && sourceKind !== 'shot') {
    return { ok: false, reason: '这类节点之间不能形成有效的创作依赖。' }
  }

  const rules: Record<string, ConnectionKind> = {
    'script:shot': 'reference',
    'character:shot': 'reference',
    'location:shot': 'reference',
    'prop:shot': 'reference',
    'shot:image': 'derived',
    'shot:video': 'derived',
    'shot:audio': 'derived',
    'image:video': 'derived',
    'video:sequence': 'sequence',
    'audio:sequence': 'sequence',
  }

  const key = `${sourceKind}:${targetKind}`
  const kind = rules[key]
  if (!kind) {
    return {
      ok: false,
      reason: '只允许剧本或资产连接到镜头，镜头或图片连接到媒体，媒体连接到成片序列。',
    }
  }

  return { ok: true, kind }
}

export function updateNode(
  document: CanvasDocument,
  nodeId: string,
  updater: (node: CreativeNode) => CreativeNode,
): CanvasDocument {
  return {
    ...document,
    nodes: document.nodes.map((node) => (node.id === nodeId ? updater(node) : node)),
  }
}

export function deleteNode(document: CanvasDocument, nodeId: string): CanvasDocument {
  return {
    ...document,
    nodes: document.nodes.filter((node) => node.id !== nodeId),
    edges: document.edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId),
    adoptedVersions: Object.fromEntries(
      Object.entries(document.adoptedVersions).map(([kind, entries]) => [
        kind,
        Object.fromEntries(
          Object.entries(entries ?? {}).filter(([, adoptedNodeId]) => adoptedNodeId !== nodeId),
        ),
      ]),
    ) as CanvasDocument['adoptedVersions'],
  }
}

export function addNode(
  document: CanvasDocument,
  kind: CreativeNodeKind,
  position: { x: number; y: number },
): CanvasDocument {
  const id = `${kind}-${Math.random().toString(36).slice(2, 8)}`
  return {
    ...document,
    nodes: [
      ...document.nodes,
      createNode(id, kind, {
        position,
        title: `${kindLabel(kind)}草稿`,
        summary: '新节点已创建，可以继续编辑。',
        content: '',
        prompt: '',
      }),
    ],
  }
}

export function addConnection(document: CanvasDocument, source: string, target: string): CanvasDocument {
  const sourceNode = document.nodes.find((node) => node.id === source)
  const targetNode = document.nodes.find((node) => node.id === target)
  const validation = validateConnection(sourceNode?.data.kind, targetNode?.data.kind)

  if (!validation.ok || !validation.kind) {
    throw new Error(validation.reason ?? 'Invalid connection')
  }

  const edgeId = `${source}-${target}-${validation.kind}`
  const exists = document.edges.some((edge) => edge.source === source && edge.target === target)
  if (exists) {
    return document
  }

  return {
    ...document,
    edges: [...document.edges, createEdge(edgeId, source, target, validation.kind)],
  }
}

export function removeConnection(document: CanvasDocument, source: string, target: string): CanvasDocument {
  const nextEdges = document.edges.filter((edge) => !(edge.source === source && edge.target === target))
  if (nextEdges.length === document.edges.length) {
    return document
  }

  return {
    ...document,
    edges: nextEdges,
  }
}

export function setReferenceLink(
  document: CanvasDocument,
  assetNodeId: string,
  shotNodeId: string,
  linked: boolean,
): CanvasDocument {
  const assetNode = document.nodes.find((node) => node.id === assetNodeId)
  const shotNode = document.nodes.find((node) => node.id === shotNodeId)
  const validation = validateConnection(assetNode?.data.kind, shotNode?.data.kind)

  if (!assetNode || !shotNode || validation.kind !== 'reference') {
    throw new Error('这里只允许把共享资产关联到镜头。')
  }

  const next = linked
    ? addConnection(document, assetNodeId, shotNodeId)
    : removeConnection(document, assetNodeId, shotNodeId)
  return markDownstreamStale(next, shotNodeId)
}

export function markDownstreamStale(document: CanvasDocument, nodeId: string): CanvasDocument {
  const downstream = collectDownstreamNodeIds(document, nodeId)
  if (downstream.size === 0) {
    return document
  }

  return {
    ...document,
    nodes: document.nodes.map((node) => {
      if (!downstream.has(node.id)) {
        return node
      }
      return {
        ...node,
        data: {
          ...node.data,
          status: node.data.kind === 'sequence' ? node.data.status : 'stale',
        },
      }
    }),
  }
}

export function adoptVersion(document: CanvasDocument, nodeId: string): CanvasDocument {
  const node = document.nodes.find((item) => item.id === nodeId)
  if (!node) {
    return document
  }
  const shotId = node.data.shotId
  if (!shotId) {
    return document
  }

  const versionKind = node.data.kind === 'image' || node.data.kind === 'video' || node.data.kind === 'audio'
    ? node.data.kind
    : null
  if (!versionKind) {
    return document
  }

  return syncSequenceEdges({
    ...document,
    adoptedVersions: {
      ...document.adoptedVersions,
      [versionKind]: {
        ...(document.adoptedVersions[versionKind] ?? {}),
        [shotId]: nodeId,
      },
    },
  })
}

export function unadoptVersion(document: CanvasDocument, nodeId: string): CanvasDocument {
  const node = document.nodes.find((item) => item.id === nodeId)
  if (!node?.data.shotId) {
    return document
  }

  const versionKind = node.data.kind === 'image' || node.data.kind === 'video' || node.data.kind === 'audio'
    ? node.data.kind
    : null
  if (!versionKind) {
    return document
  }

  const currentEntry = document.adoptedVersions[versionKind]?.[node.data.shotId]
  if (currentEntry !== nodeId) {
    return document
  }

  const nextEntries = { ...(document.adoptedVersions[versionKind] ?? {}) }
  delete nextEntries[node.data.shotId]

  return syncSequenceEdges({
    ...document,
    adoptedVersions: {
      ...document.adoptedVersions,
      [versionKind]: nextEntries,
    },
  })
}

export function generateDerivedNode(
  document: CanvasDocument,
  sourceNodeId: string,
  targetKind: VersionKind,
): GenerationOutcome {
  const sourceNode = document.nodes.find((node) => node.id === sourceNodeId)
  if (!sourceNode) {
    throw new Error('未找到来源节点。')
  }

  const labelPrefix = targetKind === 'image' ? '分镜图' : targetKind === 'video' ? '视频' : '音频'
  VERSION_COUNTERS[targetKind] += 1
  const version = countExistingVersions(document, sourceNode.data.shotId, targetKind) + 1
  const nodeId = `${targetKind}-${Math.random().toString(36).slice(2, 9)}`
  const model = targetKind === 'image' ? 'Seedream v4.5' : targetKind === 'video' ? 'Kling 1.6' : 'Studio Voice Temp'
  const prompt = targetKind === 'image'
    ? sourceNode.data.prompt || sourceNode.data.summary
    : targetKind === 'video'
      ? sourceNode.data.notes || sourceNode.data.prompt || sourceNode.data.summary
      : `${sourceNode.data.title} 的临时音频草稿`
  const derivedPosition = getDerivedBranchPosition(document, sourceNode, targetKind, version)

  const node = createNode(nodeId, targetKind, {
    title: `${labelPrefix} ${sourceNode.data.shotId ?? VERSION_COUNTERS[targetKind]} v${version}`,
    summary: `由 ${sourceNode.data.title} 派生生成`,
    shotId: sourceNode.data.shotId,
    imageRole: targetKind === 'image' ? 'storyboard' : undefined,
    assetScope: sourceNode.data.assetScope ?? 'shot',
    assetSubject: sourceNode.data.assetSubject ?? sourceNode.data.shotId,
    episode: sourceNode.data.episode,
    status: 'done',
    prompt,
    previewUrl: targetKind === 'audio'
      ? undefined
      : makePlaceholderAsset(
          `${labelPrefix} v${version}`,
          targetKind === 'image' ? '#eab308' : '#22c55e',
          model,
        ),
    position: derivedPosition,
    versionInfo: {
      version,
      label: `v${version}`,
      shotId: sourceNode.data.shotId,
      sourceNodeId,
      createdAt: new Date().toISOString(),
    },
    generation: {
      model,
      prompt,
      aspectRatio: '16:9',
      durationSeconds: targetKind === 'video' ? 5 : undefined,
      count: 1,
    },
    content: targetKind === 'audio' ? '临时对白、音效与环境氛围混合轨。' : undefined,
  })

  const edge = createEdge(`${sourceNodeId}-${nodeId}`, sourceNodeId, nodeId, 'derived')
  return { node, edge }
}

export function duplicateNode(document: CanvasDocument, nodeId: string): CanvasDocument {
  const node = document.nodes.find((item) => item.id === nodeId)
  if (!node) {
    return document
  }

  const cloneId = `${node.data.kind}-${Math.random().toString(36).slice(2, 8)}`
  const versionInfo = node.data.versionInfo
    ? {
        ...node.data.versionInfo,
        label: `${node.data.versionInfo.label}-copy`,
      }
    : undefined

  const clone = createNode(cloneId, node.data.kind, {
    ...node.data,
    title: `${node.data.title} 副本`,
    status: node.data.kind === 'image' || node.data.kind === 'video' || node.data.kind === 'audio'
      ? 'idle'
      : node.data.status,
    position: {
      x: node.position.x + 80,
      y: node.position.y + 60,
    },
    versionInfo,
  })

  return {
    ...document,
    nodes: [...document.nodes, clone],
  }
}

export function countExistingVersions(
  document: CanvasDocument,
  shotId: string | undefined,
  kind: VersionKind,
): number {
  return document.nodes.filter(
    (node) => node.data.kind === kind && node.data.shotId === shotId,
  ).length
}

export function getDerivedBranchPosition(
  document: CanvasDocument,
  sourceNode: CreativeNode,
  targetKind: VersionKind,
  version: number,
) {
  if (targetKind === 'image' && sourceNode.data.assetScope && sourceNode.data.assetScope !== 'shot') {
    return {
      x: sourceNode.position.x + 260,
      y: sourceNode.position.y + (version - 1) * 240,
    }
  }

  const shotAnchor = sourceNode.data.shotId
    ? document.nodes.find((node) => node.data.kind === 'shot' && node.data.shotId === sourceNode.data.shotId) ?? sourceNode
    : sourceNode

  return {
    x: targetKind === 'image' ? 620 : targetKind === 'video' ? 980 : 1260,
    y: shotAnchor.position.y + (version - 1) * 240,
  }
}

function dedupeByName<T>(items: T[], getKey: (item: T) => string): T[] {
  const seen = new Set<string>()
  return items.filter((item) => {
    const key = getKey(item)
    if (seen.has(key)) {
      return false
    }
    seen.add(key)
    return true
  })
}

function buildLocationReferenceEdges(
  shots: StoryboardShotOutput[],
  shotNodes: CreativeNode[],
  locations: VisualLocationOutput[],
  locationNodeByName: Map<string, CreativeNode>,
): CreativeEdge[] {
  return shots.flatMap((shot) => {
    const shotNode = shotNodes.find((node) => node.data.shotId === shot.shot_id)
    if (!shotNode) {
      return []
    }
    return locations
      .filter((location) => location.name === shot.scene_name || (location.shot_ids ?? []).includes(shot.shot_id))
      .map((location) => {
        const locationNode = locationNodeByName.get(location.name)
        return locationNode
          ? createEdge(`location-${locationNode.id}-to-${shotNode.id}`, locationNode.id, shotNode.id, 'reference')
          : null
      })
      .filter(Boolean) as CreativeEdge[]
  })
}

function buildCharacterReferenceEdges(
  shots: StoryboardShotOutput[],
  shotNodes: CreativeNode[],
  makeups: VisualMakeupOutput[],
  characterNodeByName: Map<string, CreativeNode>,
): CreativeEdge[] {
  return shots.flatMap((shot) => {
    const shotNode = shotNodes.find((node) => node.data.shotId === shot.shot_id)
    if (!shotNode) {
      return []
    }
    const promptNames = new Set((shot.makeup_prompts ?? []).map((prompt) => prompt.character_name))
    return makeups
      .filter((makeup) => promptNames.has(makeup.character_name) || (makeup.shot_ids ?? []).includes(shot.shot_id))
      .map((makeup) => {
        const characterNode = characterNodeByName.get(makeup.character_name)
        return characterNode
          ? createEdge(`character-${characterNode.id}-to-${shotNode.id}`, characterNode.id, shotNode.id, 'reference')
          : null
      })
      .filter(Boolean) as CreativeEdge[]
  })
}

function buildPropReferenceEdges(
  shots: StoryboardShotOutput[],
  shotNodes: CreativeNode[],
  props: VisualPropOutput[],
  propNodes: CreativeNode[],
): CreativeEdge[] {
  const propNodeByName = new Map(propNodes.map((node) => [node.data.title, node]))
  return shots.flatMap((shot) => {
    const shotNode = shotNodes.find((node) => node.data.shotId === shot.shot_id)
    if (!shotNode) {
      return []
    }
    return props
      .filter((prop) => (prop.shot_ids ?? []).includes(shot.shot_id))
      .map((prop) => {
        const propNode = propNodeByName.get(prop.name)
        return propNode
          ? createEdge(`prop-${propNode.id}-to-${shotNode.id}`, propNode.id, shotNode.id, 'reference')
          : null
      })
      .filter(Boolean) as CreativeEdge[]
  })
}

export function autoLayout(document: CanvasDocument): CanvasDocument {
  const assetColumns: Record<'location' | 'character' | 'prop', { x: number; startY: number; gapY: number }> = {
    location: { x: -480, startY: 40, gapY: 210 },
    character: { x: -480, startY: 320, gapY: 210 },
    prop: { x: -480, startY: 700, gapY: 190 },
  }

  const shotNodes = document.nodes
    .filter((node) => node.data.kind === 'shot')
    .sort((left, right) => compareShotIdText(left.data.shotId, right.data.shotId))

  const shotLayout = new Map<string, { y: number; laneHeight: number }>()
  let laneCursor = 120
  for (const shotNode of shotNodes) {
    const shotId = shotNode.data.shotId
    const imageCount = document.nodes.filter((node) => node.data.kind === 'image' && node.data.shotId === shotId && node.data.imageRole !== 'reference').length
    const videoCount = document.nodes.filter((node) => node.data.kind === 'video' && node.data.shotId === shotId).length
    const audioCount = document.nodes.filter((node) => node.data.kind === 'audio' && node.data.shotId === shotId).length
    const laneHeight = Math.max(1, imageCount, videoCount, audioCount) * 240 + 80
    shotLayout.set(shotId ?? shotNode.id, { y: laneCursor, laneHeight })
    laneCursor += laneHeight
  }

  const kindRows = new Map<string, number>()
  const nodes = document.nodes.map((node) => {
    if (node.data.kind === 'script') {
      return {
        ...node,
        position: { x: -120, y: 140 },
      }
    }

    if (node.data.kind === 'location' || node.data.kind === 'character' || node.data.kind === 'prop') {
      const column = assetColumns[node.data.kind]
      const row = kindRows.get(node.data.kind) ?? 0
      kindRows.set(node.data.kind, row + 1)
      return {
        ...node,
        position: {
          x: column.x,
          y: column.startY + row * column.gapY,
        },
      }
    }

    if (node.data.imageRole === 'reference' && node.data.assetScope && node.data.assetScope !== 'shot') {
      const groupKey = `reference:${node.data.assetScope}:${node.data.assetSubject ?? node.id}`
      const row = kindRows.get(groupKey) ?? 0
      kindRows.set(groupKey, row + 1)
      const startY = node.data.assetScope === 'location' ? 40 : node.data.assetScope === 'character' ? 320 : 700
      return {
        ...node,
        position: {
          x: -160 + (row % 2) * 180,
          y: startY + Math.floor(row / 2) * 150,
        },
      }
    }

    if (node.data.kind === 'shot') {
      return {
        ...node,
        position: {
          x: 200,
          y: shotLayout.get(node.data.shotId ?? node.id)?.y ?? laneCursor,
        },
      }
    }

    if (node.data.shotId && (node.data.kind === 'image' || node.data.kind === 'video' || node.data.kind === 'audio')) {
      const mediaNodes = document.nodes
        .filter((item) => item.data.kind === node.data.kind && item.data.shotId === node.data.shotId && item.data.imageRole !== 'reference')
        .sort(compareVersionNodes)
      const mediaIndex = Math.max(0, mediaNodes.findIndex((item) => item.id === node.id))
      return {
        ...node,
        position: {
          x: node.data.kind === 'image' ? 620 : node.data.kind === 'video' ? 980 : 1260,
          y: (shotLayout.get(node.data.shotId)?.y ?? 120) + mediaIndex * 240,
        },
      }
    }

    if (node.data.kind === 'sequence') {
      return {
        ...node,
        position: {
          x: 1580,
          y: Math.max(220, Math.round((laneCursor - 120) / 2)),
        },
      }
    }

    return node
  })

  return {
    ...document,
    nodes,
  }
}

function compareVersionNodes(left: CreativeNode, right: CreativeNode) {
  const leftVersion = left.data.versionInfo?.version ?? 0
  const rightVersion = right.data.versionInfo?.version ?? 0
  if (leftVersion !== rightVersion) {
    return leftVersion - rightVersion
  }
  return left.id.localeCompare(right.id, 'zh-Hans-CN')
}

function compareShotIdText(left?: string, right?: string) {
  const tokenize = (value: string) =>
    value
      .split(/[^0-9A-Za-z\u4e00-\u9fa5]+/)
      .filter(Boolean)
      .map((part) => (/^\d+$/.test(part) ? Number(part) : part))

  const leftText = left ?? ''
  const rightText = right ?? ''
  const leftParts = tokenize(leftText)
  const rightParts = tokenize(rightText)
  const maxLength = Math.max(leftParts.length, rightParts.length)

  for (let index = 0; index < maxLength; index += 1) {
    const leftPart = leftParts[index]
    const rightPart = rightParts[index]
    if (leftPart === undefined) return -1
    if (rightPart === undefined) return 1
    if (typeof leftPart === 'number' && typeof rightPart === 'number') {
      if (leftPart !== rightPart) {
        return leftPart - rightPart
      }
      continue
    }
    const result = String(leftPart).localeCompare(String(rightPart), 'zh-Hans-CN')
    if (result !== 0) {
      return result
    }
  }

  return leftText.localeCompare(rightText, 'zh-Hans-CN')
}

export function kindLabel(kind: CreativeNodeKind): string {
  switch (kind) {
    case 'script':
      return '剧本'
    case 'shot':
      return '镜头'
    case 'character':
      return '角色'
    case 'location':
      return '场景'
    case 'prop':
      return '道具'
    case 'image':
      return '图片'
    case 'video':
      return '视频'
    case 'audio':
      return '音频'
    case 'sequence':
      return '成片序列'
  }
}

export function makePlaceholderAsset(title: string, accent: string, subtitle: string): string {
  const width = 540
  const height = 304
  return `data:image/svg+xml,${encodeURIComponent(`
    <svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
      <defs>
        <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#111827" />
          <stop offset="100%" stop-color="#020617" />
        </linearGradient>
      </defs>
      <rect width="${width}" height="${height}" fill="url(#bg)" />
      <rect x="18" y="18" width="${width - 36}" height="${height - 36}" rx="18" fill="#0f172a" stroke="#1e293b" />
      <circle cx="118" cy="112" r="46" fill="${accent}" opacity="0.24" />
      <circle cx="398" cy="210" r="60" fill="${accent}" opacity="0.16" />
      <text x="44" y="64" fill="#94a3b8" font-size="16" font-family="Segoe UI, sans-serif">分镜生产输出</text>
      <text x="44" y="114" fill="#f8fafc" font-size="28" font-family="Segoe UI, sans-serif">${escapeXml(title)}</text>
      <text x="44" y="146" fill="${accent}" font-size="18" font-family="Segoe UI, sans-serif">${escapeXml(subtitle)}</text>
      <text x="44" y="250" fill="#64748b" font-size="15" font-family="Segoe UI, sans-serif">用于画布演示的派生 Mock 资产</text>
    </svg>
  `)}`
}

function collectDownstreamNodeIds(document: CanvasDocument, startId: string): Set<string> {
  const visited = new Set<string>()
  const queue = [startId]

  while (queue.length > 0) {
    const current = queue.shift()!
    for (const edge of document.edges) {
      if (edge.source !== current || visited.has(edge.target)) {
        continue
      }
      visited.add(edge.target)
      queue.push(edge.target)
    }
  }

  return visited
}

function escapeXml(input: string): string {
  return input
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}
