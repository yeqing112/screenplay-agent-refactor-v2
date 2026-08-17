import {
  adoptVersion,
  countExistingVersions,
  createEdge,
  createNode,
  makePlaceholderAsset,
  updateNode,
  type CanvasDocument,
  type VersionKind,
} from './sceneComposerModel'

export function startMockGeneration(document: CanvasDocument, sourceNodeId: string): CanvasDocument {
  return updateNode(document, sourceNodeId, (node) => ({
    ...node,
    data: {
      ...node.data,
      status: 'running',
      errorMessage: undefined,
    },
  }))
}

export function failMockGeneration(
  document: CanvasDocument,
  sourceNodeId: string,
  targetKind: VersionKind,
): CanvasDocument {
  const label = targetKind === 'image' ? '图片' : targetKind === 'video' ? '视频' : '音频'

  return updateNode(document, sourceNodeId, (node) => ({
    ...node,
    data: {
      ...node.data,
      status: 'error',
      errorMessage: `${label}模拟生成遇到临时模型超时。`,
    },
  }))
}

export function finishMockGeneration(
  document: CanvasDocument,
  sourceNodeId: string,
  targetKind: VersionKind,
): CanvasDocument {
  const sourceNode = document.nodes.find((node) => node.id === sourceNodeId)
  if (!sourceNode) {
    return document
  }

  const version = countExistingVersions(document, sourceNode.data.shotId, targetKind) + 1
  const nodeId = `${targetKind}-${Math.random().toString(36).slice(2, 9)}`
  const label = targetKind === 'image' ? '分镜图' : targetKind === 'video' ? '视频' : '音频'
  const model = targetKind === 'image' ? 'Seedream v4.5' : targetKind === 'video' ? 'Kling 1.6' : 'Studio Voice Temp'
  const prompt = targetKind === 'image'
    ? sourceNode.data.prompt || sourceNode.data.summary
    : targetKind === 'video'
      ? sourceNode.data.notes || sourceNode.data.prompt || sourceNode.data.summary
      : `${sourceNode.data.title} 的临时音频草稿`
  const positionOffset = targetKind === 'image'
    ? { x: 240, y: 0 }
    : targetKind === 'video'
      ? { x: 260, y: 160 }
      : { x: 260, y: -160 }

  const mockNode = createNode(nodeId, targetKind, {
    title: `${label} ${sourceNode.data.shotId ?? version} v${version}`,
    summary: `由 ${sourceNode.data.title} 派生的 Mock 分支`,
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
          `${label} v${version}`,
          targetKind === 'image' ? '#eab308' : '#22c55e',
          `${model} · Mock`,
        ),
    position: {
      x: sourceNode.position.x + positionOffset.x,
      y: sourceNode.position.y + positionOffset.y,
    },
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
    content: targetKind === 'audio' ? '用于当前镜头演示的临时 Mock 音频。' : undefined,
    metadata: {
      source: 'mock',
      model,
    },
  })

  const appended: CanvasDocument = {
    ...document,
    nodes: [
      ...document.nodes.map((node) =>
        node.id === sourceNodeId
          ? {
              ...node,
              data: {
                ...node.data,
                status: 'done' as const,
                errorMessage: undefined,
              },
            }
          : node,
      ),
      mockNode,
    ],
    edges: [...document.edges, createEdge(`${sourceNodeId}-${nodeId}`, sourceNodeId, nodeId, 'derived')],
  }

  return adoptVersion(appended, mockNode.id)
}
