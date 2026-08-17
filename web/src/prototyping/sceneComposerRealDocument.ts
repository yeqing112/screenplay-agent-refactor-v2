import type { CanvasDocument, CreativeEdge, CreativeNode, VersionKind } from './sceneComposerModel'
import { createEdge, createNode, makePlaceholderAsset } from './sceneComposerModel'
import {
  toDisplayText,
} from './sceneComposerData'
import type {
  MediaAssetOutput,
  OutputsData,
  StoryboardShotOutput,
  VisualLocationOutput,
  VisualMakeupOutput,
  VisualPropOutput,
} from './sceneComposerData'

export function createRealEpisodeDocument(
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
      title: toDisplayText(item.name, `场景 ${index + 1}`),
      summary: toDisplayText(item.description ?? item.style, '待补充场景描述'),
      prompt: item.visual_prompt_zh ?? item.zh_prompt ?? item.core_prompt_zh ?? '',
      assetScope: 'location',
      assetSubject: toDisplayText(item.name, `场景 ${index + 1}`),
      position: { x: -480, y: 40 + index * 190 },
      content: [item.style, item.lighting_mood, item.color_palette].filter(Boolean).join('\n'),
      metadata: {
        category: item.category,
        shotIds: (item.shot_ids ?? []).join(','),
      },
    }),
  )

  const characterNodes = characterAssets.map((item, index) =>
    createNode(`character-${index + 1}`, 'character', {
      title: toDisplayText(item.character_name, `角色 ${index + 1}`),
      summary: toDisplayText(item.temperament ?? item.expression_mood, '待补充角色描述'),
      prompt: item.visual_prompt_zh ?? '',
      assetScope: 'character',
      assetSubject: toDisplayText(item.character_name, `角色 ${index + 1}`),
      notes: [item.refined_outfit, item.refined_accessories].filter(Boolean).join(' / '),
      content: [item.identity, item.appearance, item.makeup_spec].filter(Boolean).join('\n'),
      position: { x: -480, y: 250 + index * 190 },
      metadata: {
        outfit: item.refined_outfit,
        hair: item.hair_style,
        shotIds: (item.shot_ids ?? []).join(','),
      },
    }),
  )

  const propNodes = propAssets.map((item, index) =>
    createNode(`prop-${index + 1}`, 'prop', {
      title: toDisplayText(item.name, `道具 ${index + 1}`),
      summary: toDisplayText(item.description, '待补充道具描述'),
      prompt: item.visual_prompt_zh ?? item.zh_prompt ?? item.core_prompt_zh ?? '',
      assetScope: 'prop',
      assetSubject: toDisplayText(item.name, `道具 ${index + 1}`),
      position: { x: -480, y: 640 + index * 170 },
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

  const shotLaneLayout = new Map<string, { y: number; laneHeight: number }>()
  let laneCursor = 120
  for (const shot of shots) {
    const media = shot.assets ?? { images: [], videos: [], audios: [] }
    const laneHeight = Math.max(1, media.images.length, media.videos.length, media.audios.length) * 240 + 80
    shotLaneLayout.set(shot.shot_id, { y: laneCursor, laneHeight })
    laneCursor += laneHeight
  }

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
      position: { x: 200, y: shotLaneLayout.get(shot.shot_id)?.y ?? 120 + index * 320 },
      content: [
        `场景：${shot.scene_name}`,
        `机位：${shot.camera_angle ?? '待补充'} / ${shot.camera_movement ?? '待补充'}`,
        `时长：${shot.duration ?? 0} 秒`,
      ].join('\n'),
      metadata: {
        scene: shot.scene_name,
        camera: shot.camera_angle,
        movement: shot.camera_movement,
        assetStatus: shot.asset_status,
        duration: shot.duration,
      },
    }),
  )

  const sequenceNode = createNode('sequence-1', 'sequence', {
    title: `第 ${episode} 集成片序列`,
    summary: '按当前采用版本汇总的镜头视频与音频序列。',
    status: 'done',
    content: '当前集的已采用视频、音频会汇总到这里，形成成片时间线。',
    position: { x: 1580, y: Math.max(220, Math.round((laneCursor - 120) / 2)) },
    metadata: {
      shots: shotNodes.length,
      adopted: 0,
    },
  })

  const imageNodes: CreativeNode[] = []
  const videoNodes: CreativeNode[] = []
  const audioNodes: CreativeNode[] = []
  const referenceImageNodes: CreativeNode[] = []
  const derivedEdges: CreativeEdge[] = []
  const adoptedVersions: CanvasDocument['adoptedVersions'] = {
    image: {},
    video: {},
    audio: {},
  }

  const imageNodeByAssetId = new Map<string, CreativeNode>()
  const imageNodeByShotId = new Map<string, CreativeNode[]>()
  const referenceNodeByKey = new Map<string, CreativeNode>()
  const referenceShotLinks = new Map<string, Set<string>>()

  for (const shot of shots) {
    const shotNode = shotNodes.find((node) => node.data.shotId === shot.shot_id)
    if (!shotNode) {
      continue
    }

    const media = shot.assets ?? { images: [], videos: [], audios: [] }
    const references = media.references ?? { characters: {}, scene: [], props: {} }

    for (const [characterName, assets] of Object.entries(references.characters ?? {})) {
      const readableCharacterName = toDisplayText(characterName, '角色')
      const characterNode = characterNodes.find((node) => node.data.title === readableCharacterName)
      upsertReferenceNodes(
        assets,
        shot,
        shotNode,
        characterNode?.id ?? `character-missing-${sanitizeId(characterName)}`,
        'character',
        readableCharacterName,
        referenceImageNodes,
        derivedEdges,
        referenceNodeByKey,
        referenceShotLinks,
      )
    }

    if ((references.scene ?? []).length > 0) {
      const readableSceneName = toDisplayText(shot.scene_name, '场景')
      const locationNode = locationNodes.find((node) => node.data.title === readableSceneName)
      upsertReferenceNodes(
        references.scene,
        shot,
        shotNode,
        locationNode?.id ?? `location-missing-${sanitizeId(readableSceneName)}`,
        'location',
        readableSceneName,
        referenceImageNodes,
        derivedEdges,
        referenceNodeByKey,
        referenceShotLinks,
      )
    }

    for (const [propName, assets] of Object.entries(references.props ?? {})) {
      const readablePropName = toDisplayText(propName, '道具')
      const propNode = propNodes.find((node) => node.data.title === readablePropName)
      upsertReferenceNodes(
        assets,
        shot,
        shotNode,
        propNode?.id ?? `prop-missing-${sanitizeId(propName)}`,
        'prop',
        readablePropName,
        referenceImageNodes,
        derivedEdges,
        referenceNodeByKey,
        referenceShotLinks,
      )
    }

    const shotImageNodes = media.images.map((asset, assetIndex) =>
      createMediaNode('image', asset, shot, shotNode, assetIndex, {
        x: 620,
        y: shotNode.position.y + assetIndex * 240,
      }),
    )

    shotImageNodes.forEach((node) => {
      imageNodes.push(node)
      imageNodeByAssetId.set(String(node.data.metadata?.assetId ?? node.id), node)
      imageNodeByShotId.set(node.data.shotId ?? '', [...(imageNodeByShotId.get(node.data.shotId ?? '') ?? []), node])
    })

    for (const node of shotImageNodes) {
      derivedEdges.push(createEdge(`shot-${shot.shot_id}-to-${node.id}`, shotNode.id, node.id, 'derived'))
    }

    const adoptedImageNode = pickAdoptedNode(shotImageNodes, media.images)
    if (adoptedImageNode && shot.shot_id) {
      adoptedVersions.image![shot.shot_id] = adoptedImageNode.id
    }

    const shotVideoNodes = media.videos.map((asset, assetIndex) => {
      const sourceImageNode = resolveVideoSourceNode(asset, shot.shot_id, imageNodeByAssetId, imageNodeByShotId)
      const node = createMediaNode('video', asset, shot, shotNode, assetIndex, {
        x: 980,
        y: shotNode.position.y + assetIndex * 240,
      }, sourceImageNode?.id ?? shotNode.id)

      derivedEdges.push(
        createEdge(
          `${sourceImageNode?.id ?? shotNode.id}-to-${node.id}`,
          sourceImageNode?.id ?? shotNode.id,
          node.id,
          'derived',
        ),
      )

      return node
    })

    shotVideoNodes.forEach((node) => videoNodes.push(node))
    const adoptedVideoNode = pickAdoptedNode(shotVideoNodes, media.videos)
    if (adoptedVideoNode && shot.shot_id) {
      adoptedVersions.video![shot.shot_id] = adoptedVideoNode.id
    }

    const shotAudioNodes = media.audios.map((asset, assetIndex) => {
      const node = createMediaNode('audio', asset, shot, shotNode, assetIndex, {
        x: 1260,
        y: shotNode.position.y + assetIndex * 240,
      }, shotNode.id)

      derivedEdges.push(createEdge(`${shotNode.id}-to-${node.id}`, shotNode.id, node.id, 'derived'))
      return node
    })

    shotAudioNodes.forEach((node) => audioNodes.push(node))
    const adoptedAudioNode = pickAdoptedNode(shotAudioNodes, media.audios)
    if (adoptedAudioNode && shot.shot_id) {
      adoptedVersions.audio![shot.shot_id] = adoptedAudioNode.id
    }
  }

  sequenceNode.data.metadata = {
    ...sequenceNode.data.metadata,
    adopted:
      Object.keys(adoptedVersions.video ?? {}).length +
      Object.keys(adoptedVersions.audio ?? {}).length,
  }

  const nodes = [
    scriptNode,
    ...locationNodes,
    ...characterNodes,
    ...propNodes,
    ...referenceImageNodes,
    ...shotNodes,
    ...imageNodes,
    ...videoNodes,
    ...audioNodes,
    sequenceNode,
  ]

  const locationNodeByName = new Map(locationNodes.map((node) => [node.data.title, node]))
  const characterNodeByName = new Map(characterNodes.map((node) => [node.data.title, node]))

  const edges = dedupeEdges([
    ...shotNodes.map((shotNode) => createEdge(`script-to-${shotNode.id}`, scriptNode.id, shotNode.id, 'reference')),
    ...buildLocationReferenceEdges(shots, shotNodes, locationAssets, locationNodeByName),
    ...buildCharacterReferenceEdges(shots, shotNodes, characterAssets, characterNodeByName),
    ...buildPropReferenceEdges(shots, shotNodes, propAssets, propNodes),
    ...buildReferenceImageEdges(referenceImageNodes, referenceShotLinks, shotNodes),
    ...derivedEdges,
    ...buildSequenceEdges(sequenceNode, adoptedVersions),
  ])

  return {
    version: 2,
    projectTitle: options?.projectTitle ?? '未命名项目',
    episodeTitle: options?.episodeTitle ?? `第 ${episode} 集创作沙盒`,
    nodes,
    edges,
    viewport: { x: 220, y: 120, zoom: 0.72 },
    adoptedVersions,
    tutorialDismissed: false,
    lastSavedAt: now.toISOString(),
  }
}

function upsertReferenceNodes(
  assets: MediaAssetOutput[],
  shot: StoryboardShotOutput,
  shotNode: CreativeNode,
  sourceAssetNodeId: string,
  scope: 'character' | 'location' | 'prop',
  subject: string,
  referenceImageNodes: CreativeNode[],
  derivedEdges: CreativeEdge[],
  referenceNodeByKey: Map<string, CreativeNode>,
  referenceShotLinks: Map<string, Set<string>>,
) {
  assets.forEach((asset, assetIndex) => {
    const nodeKey = `${scope}:${subject}:${asset.id}`
    if (!referenceNodeByKey.has(nodeKey)) {
      const referenceNode = createReferenceImageNode(asset, shot, sourceAssetNodeId, scope, subject, assetIndex)
      referenceNodeByKey.set(nodeKey, referenceNode)
      referenceImageNodes.push(referenceNode)
      derivedEdges.push(createEdge(`${sourceAssetNodeId}-to-${referenceNode.id}`, sourceAssetNodeId, referenceNode.id, 'derived'))
    }

    const referenceNode = referenceNodeByKey.get(nodeKey)!
    const linkedShots = referenceShotLinks.get(referenceNode.id) ?? new Set<string>()
    linkedShots.add(shotNode.id)
    referenceShotLinks.set(referenceNode.id, linkedShots)
  })
}

function createReferenceImageNode(
  asset: MediaAssetOutput,
  shot: StoryboardShotOutput,
  sourceAssetNodeId: string,
  scope: 'character' | 'location' | 'prop',
  subject: string,
  assetIndex: number,
) {
  const previewUrl = resolvePreviewUrl('image', asset)
  const version = extractVersionNumber(asset.label, assetIndex + 1)
  const readableSubject = toDisplayText(subject, scope === 'location' ? '场景' : scope === 'character' ? '角色' : '道具')
  const readableTitle = toDisplayText(asset.title, `${readableSubject} 参考图 v${version}`)
  const readableSummary = toDisplayText(referenceAssetSummary(scope), '后端已存在的参考图。')

  return createNode(`reference-${scope}-${sanitizeId(readableSubject)}-${sanitizeId(asset.id || `${assetIndex + 1}`)}-${hashString(`${scope}:${subject}:${asset.id || assetIndex + 1}`)}`, 'image', {
    title: readableTitle,
    summary: readableSummary,
    prompt: toDisplayText(asset.prompt, ''),
    shotId: shot.shot_id,
    episode: shot.episode,
    imageRole: 'reference',
    assetScope: scope,
    assetSubject: readableSubject,
    status: asset.status === 'failed' ? 'error' : 'done',
    previewUrl,
    position: referenceNodePosition(scope, assetIndex),
    content: asset.uri,
    versionInfo: {
      version,
      label: asset.label,
      shotId: shot.shot_id,
      sourceNodeId: sourceAssetNodeId,
      createdAt: new Date().toISOString(),
    },
    metadata: {
      source: 'real',
      assetId: asset.id,
      assetUri: asset.uri,
      model: asset.model,
      ...(asset.metadata ?? {}),
    },
  })
}

function referenceNodePosition(scope: 'character' | 'location' | 'prop', assetIndex: number) {
  const base = scope === 'location'
    ? { x: -280, y: 60 }
    : scope === 'character'
      ? { x: -280, y: 280 }
      : { x: -280, y: 620 }

  return {
    x: base.x + (assetIndex % 2) * 170,
    y: base.y + Math.floor(assetIndex / 2) * 130,
  }
}

function buildReferenceImageEdges(
  referenceImageNodes: CreativeNode[],
  referenceShotLinks: Map<string, Set<string>>,
  shotNodes: CreativeNode[],
) {
  return referenceImageNodes.flatMap((node) => {
    const linkedShots = Array.from(referenceShotLinks.get(node.id) ?? [])
    return linkedShots
      .map((shotNodeId) => {
        const shotNode = shotNodes.find((item) => item.id === shotNodeId)
        return shotNode
          ? createEdge(`reference-${node.id}-to-${shotNode.id}`, node.id, shotNode.id, 'reference')
          : null
      })
      .filter(Boolean) as CreativeEdge[]
  })
}

function referenceAssetSummary(scope: 'character' | 'location' | 'prop') {
  if (scope === 'character') return '后端已存在的人物参考图。'
  if (scope === 'location') return '后端已存在的场景参考图。'
  return '后端已存在的道具参考图。'
}

function createMediaNode(
  kind: VersionKind,
  asset: MediaAssetOutput,
  shot: StoryboardShotOutput,
  shotNode: CreativeNode,
  assetIndex: number,
  position: { x: number; y: number },
  sourceNodeId?: string,
): CreativeNode {
  const fallbackPrompt = kind === 'video'
    ? shot.visual_prompt_motion || shot.visual_prompt_static || ''
    : shot.visual_prompt_static || shot.visual_prompt_motion || ''
  const previewUrl = resolvePreviewUrl(kind, asset)
  const version = extractVersionNumber(asset.label, assetIndex + 1)
  const readableShotId = toDisplayText(shot.shot_id, `镜头${assetIndex + 1}`)
  const readableTitle = toDisplayText(asset.title, `${kind === 'image' ? '分镜图' : kind === 'video' ? '视频' : '音频'} ${readableShotId} v${version}`)

  return createNode(`${kind}-real-${shot.shot_id}-${sanitizeId(asset.id || `${assetIndex + 1}`)}`, kind, {
    title: readableTitle,
    summary: realAssetSummary(kind),
    prompt: toDisplayText(asset.prompt, fallbackPrompt),
    notes: kind === 'image' ? shot.visual_prompt_motion || '' : undefined,
    shotId: shot.shot_id,
    episode: shot.episode,
    imageRole: kind === 'image' ? 'storyboard' : undefined,
    assetScope: 'shot',
    assetSubject: readableShotId,
    status: asset.status === 'failed' ? 'error' : 'done',
    previewUrl,
    position,
    content: asset.uri,
    versionInfo: {
      version,
      label: asset.label,
      shotId: shot.shot_id,
      sourceNodeId,
      createdAt: new Date().toISOString(),
    },
    metadata: {
      source: 'real',
      assetId: asset.id,
      assetUri: asset.uri,
      model: asset.model,
      ...(asset.metadata ?? {}),
    },
  })
}

function resolvePreviewUrl(kind: VersionKind, asset: MediaAssetOutput) {
  if (asset.previewUrl && isBrowserReachable(asset.previewUrl)) {
    return asset.previewUrl
  }
  if (kind === 'image' && asset.uri && isBrowserReachable(asset.uri)) {
    return asset.uri
  }
  if (kind === 'audio') {
    return undefined
  }
  return makePlaceholderAsset(asset.title, kind === 'image' ? '#eab308' : '#22c55e', kind === 'image' ? '真实图片资产' : '真实视频资产')
}

function isBrowserReachable(value: string) {
  return /^(https?:|data:|blob:|\/)/.test(value)
}

function realAssetSummary(kind: VersionKind) {
  switch (kind) {
    case 'image':
      return '后端已存在的分镜图片资产。'
    case 'video':
      return '后端已存在的视频资产。'
    case 'audio':
      return '后端已存在的音频资产。'
  }
}

function resolveVideoSourceNode(
  asset: MediaAssetOutput,
  shotId: string,
  imageNodeByAssetId: Map<string, CreativeNode>,
  imageNodeByShotId: Map<string, CreativeNode[]>,
) {
  if (asset.sourceAssetId && imageNodeByAssetId.has(asset.sourceAssetId)) {
    return imageNodeByAssetId.get(asset.sourceAssetId) ?? null
  }

  const candidates = imageNodeByShotId.get(shotId) ?? []
  return candidates[0] ?? null
}

function pickAdoptedNode(nodes: CreativeNode[], assets: MediaAssetOutput[]) {
  if (nodes.length === 0) {
    return null
  }

  const adoptedIndex = assets.findIndex((asset) => asset.adopted)
  if (adoptedIndex >= 0 && nodes[adoptedIndex]) {
    return nodes[adoptedIndex]
  }

  return nodes[0]
}

function buildSequenceEdges(
  sequenceNode: CreativeNode,
  adoptedVersions: CanvasDocument['adoptedVersions'],
) {
  return [
    ...Object.entries(adoptedVersions.video ?? {}).map(([shotId, nodeId]) =>
      createEdge(`sequence-video-${shotId}`, nodeId, sequenceNode.id, 'sequence', `镜头 ${shotId}`),
    ),
    ...Object.entries(adoptedVersions.audio ?? {}).map(([shotId, nodeId]) =>
      createEdge(`sequence-audio-${shotId}`, nodeId, sequenceNode.id, 'sequence', `音频 ${shotId}`),
    ),
  ]
}

function extractVersionNumber(label: string, fallback: number) {
  const match = label.match(/(\d+)/)
  return match ? Number(match[1]) : fallback
}

function sanitizeId(value: string) {
  const raw = String(value ?? '').trim()
  const encoded = Array.from(raw)
    .map((char) => (/^[a-zA-Z0-9_-]$/.test(char) ? char : `u${char.codePointAt(0)?.toString(16)}`))
    .join('-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')

  return encoded.slice(0, 96) || `id-${hashString(raw || 'empty')}`
}

function hashString(value: string) {
  let hash = 0
  for (const char of value) {
    hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  }
  return hash.toString(16)
}

function dedupeByName<T>(items: T[], getKey: (item: T) => string): T[] {
  const seen = new Set<string>()
  return items.filter((item) => {
    const key = getKey(item)
    if (!key || seen.has(key)) {
      return false
    }
    seen.add(key)
    return true
  })
}

function dedupeEdges(edges: CreativeEdge[]) {
  const seen = new Set<string>()
  return edges.filter((edge) => {
    const key = `${edge.source}:${edge.target}:${edge.data?.kind ?? 'unknown'}`
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
        const locationNode = locationNodeByName.get(toDisplayText(location.name, '场景'))
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

    const promptNames = new Set((shot.makeup_prompts ?? []).map((prompt) => toDisplayText(prompt.character_name, '角色')))
    return makeups
      .filter((makeup) => promptNames.has(toDisplayText(makeup.character_name, '角色')) || (makeup.shot_ids ?? []).includes(shot.shot_id))
      .map((makeup) => {
        const characterNode = characterNodeByName.get(toDisplayText(makeup.character_name, '角色'))
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
        const propNode = propNodeByName.get(toDisplayText(prop.name, '道具'))
        return propNode
          ? createEdge(`prop-${propNode.id}-to-${shotNode.id}`, propNode.id, shotNode.id, 'reference')
          : null
      })
      .filter(Boolean) as CreativeEdge[]
  })
}
