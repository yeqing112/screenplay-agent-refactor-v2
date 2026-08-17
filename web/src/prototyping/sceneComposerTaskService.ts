import {
  adoptVersion,
  countExistingVersions,
  createEdge,
  createNode,
  getDerivedBranchPosition,
  makePlaceholderAsset,
  updateNode,
  type CanvasDocument,
  type MetadataValue,
  type VersionKind,
} from './sceneComposerModel'

export interface CreativeTaskAsset {
  id: string
  kind: VersionKind
  title: string
  label: string
  uri?: string
  previewUrl?: string
  prompt?: string
  model?: string
  status?: string
  adopted?: boolean
  sourceAssetId?: string
  metadata?: Record<string, MetadataValue>
  elapsedSeconds?: number
}

export interface CreativeTaskRequest {
  bookId: number
  episode: number
  shotId: string
  sourceNodeId: string
  sourceAssetId?: string
  assetScope?: 'character' | 'location' | 'prop' | 'shot'
  assetSubject?: string
  targetKind?: 'image' | 'video'
  prompt: string
  model?: string
  modelProfileId?: string
  referenceAssetIds?: string[]
  aspectRatio?: string
  durationSeconds?: number
  count?: number
  simulateError?: boolean
}

export interface CreativeTaskStatus {
  task_id: string
  status: 'queued' | 'running' | 'done' | 'error' | 'not_found'
  target_kind: VersionKind
  progress?: number
  error?: string
  asset?: CreativeTaskAsset
  model_profile_id?: string
  provider?: string
  uses_mock?: boolean
  external_task_id?: string | null
  external_status?: string | null
  poll_attempts?: number | null
  provider_response?: Record<string, unknown> | null
}

export interface PollCreativeTaskOptions {
  intervalMs?: number
  maxAttempts?: number
  onUpdate?: (status: CreativeTaskStatus) => void
}

const API = '/api/prototyping'

function serializeProviderResponse(value: Record<string, unknown> | null | undefined) {
  if (!value) return undefined
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return JSON.stringify({ message: 'provider response unavailable' })
  }
}

function serializeCreativeTaskRequest(request: CreativeTaskRequest) {
  const referenceAssetIds = request.referenceAssetIds
    ? Array.from(new Set(request.referenceAssetIds.filter(Boolean)))
    : undefined
  return {
    book_id: request.bookId,
    episode: request.episode,
    shot_id: request.shotId,
    source_node_id: request.sourceNodeId,
    source_asset_id: request.sourceAssetId,
    asset_scope: request.assetScope,
    asset_subject: request.assetSubject,
    target_kind: request.targetKind,
    prompt: request.prompt,
    model: request.model,
    model_profile_id: request.modelProfileId,
    reference_asset_ids: referenceAssetIds,
    aspect_ratio: request.aspectRatio,
    duration_seconds: request.durationSeconds,
    count: request.count,
    simulate_error: request.simulateError,
  }
}

function serializeAdoptVersionRequest(request: {
  bookId: number
  episode: number
  shotId: string
  kind: VersionKind
  assetId: string
}) {
  return {
    book_id: request.bookId,
    episode: request.episode,
    shot_id: request.shotId,
    kind: request.kind,
    asset_id: request.assetId,
  }
}

async function readErrorMessage(response: Response, fallback: string) {
  const text = (await response.text()).trim()
  if (!text) return fallback
  try {
    const parsed = JSON.parse(text)
    if (typeof parsed?.detail === 'string' && parsed.detail.trim()) {
      return parsed.detail.trim()
    }
    if (typeof parsed?.message === 'string' && parsed.message.trim()) {
      return parsed.message.trim()
    }
  } catch {
    // noop
  }
  return text
}

export async function startCreativeTask(
  targetKind: Extract<VersionKind, 'image' | 'video'>,
  request: CreativeTaskRequest,
) {
  const endpoint = targetKind === 'image' ? 'generate-image' : 'generate-video'
  const response = await fetch(`${API}/${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(serializeCreativeTaskRequest(request)),
  })

  if (!response.ok) {
    const detail = await readErrorMessage(response, `HTTP ${response.status}`)
    throw new Error(`启动${targetKind === 'image' ? '图片' : '视频'}任务失败：${detail}`)
  }

  return response.json() as Promise<{ task_id: string; status: 'queued' | 'running'; model_profile_id?: string; uses_mock?: boolean }>
}

export async function startReferenceImageTask(request: CreativeTaskRequest) {
  const response = await fetch(`${API}/generate-reference-image`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(serializeCreativeTaskRequest({
      ...request,
      targetKind: 'image',
    })),
  })

  if (!response.ok) {
    const detail = await readErrorMessage(response, `HTTP ${response.status}`)
    throw new Error(`启动参考图任务失败：${detail}`)
  }

  return response.json() as Promise<{ task_id: string; status: 'queued' | 'running'; model_profile_id?: string; uses_mock?: boolean }>
}

export async function fetchCreativeTask(taskId: string) {
  const response = await fetch(`${API}/tasks/${taskId}`)
  if (!response.ok) {
    const detail = await readErrorMessage(response, `HTTP ${response.status}`)
    throw new Error(`任务 ${taskId} 查询失败：${detail}`)
  }
  return response.json() as Promise<CreativeTaskStatus>
}

export async function persistAdoptedVersion(request: {
  bookId: number
  episode: number
  shotId: string
  kind: VersionKind
  assetId: string
}) {
  const response = await fetch(`${API}/adopt-version`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(serializeAdoptVersionRequest(request)),
  })
  if (!response.ok) {
    const detail = await readErrorMessage(response, `HTTP ${response.status}`)
    throw new Error(`采用版本保存失败：${detail}`)
  }
  return response.json() as Promise<{ ok: true }>
}

export async function pollCreativeTask(
  fetcher: (taskId: string) => Promise<CreativeTaskStatus>,
  taskId: string,
  options: PollCreativeTaskOptions = {},
): Promise<CreativeTaskStatus> {
  const intervalMs = options.intervalMs ?? 1200
  const maxAttempts = options.maxAttempts ?? 50

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const status = await fetcher(taskId)
    options.onUpdate?.(status)
    if (status.status !== 'queued' && status.status !== 'running') {
      return status
    }
    await new Promise((resolve) => globalThis.setTimeout(resolve, intervalMs))
  }

  throw new Error('任务轮询超时，请稍后刷新或重试。')
}

export function createPendingGenerationBranch(
  document: CanvasDocument,
  sourceNodeId: string,
  targetKind: VersionKind,
  options?: {
    taskId?: string
    source?: 'real' | 'mock'
    nodeId?: string
    modelProfileId?: string
    modelName?: string
    provider?: string
    usesMock?: boolean
    prompt?: string
    sourceAssetId?: string
    startedAt?: string
  },
): { document: CanvasDocument; nodeId: string } {
  const sourceNode = document.nodes.find((node) => node.id === sourceNodeId)
  if (!sourceNode) {
    throw new Error('未找到来源节点。')
  }

  const version = countExistingVersions(document, sourceNode.data.shotId, targetKind) + 1
  const nodeId = options?.nodeId ?? `${targetKind}-${Math.random().toString(36).slice(2, 9)}`
  const labelPrefix = targetKind === 'image' ? '分镜图' : targetKind === 'video' ? '视频' : '音频'
  const nodeSubject = sourceNode.data.assetScope && sourceNode.data.assetScope !== 'shot'
    ? sourceNode.data.assetSubject ?? sourceNode.data.title
    : sourceNode.data.shotId ?? String(version)
  const model = options?.modelName
    || (targetKind === 'image' ? 'Seedream v4.5' : targetKind === 'video' ? 'Kling 1.6' : 'Studio Voice Temp')
  const prompt = options?.prompt
    || (targetKind === 'image'
      ? sourceNode.data.prompt || sourceNode.data.summary
      : targetKind === 'video'
        ? sourceNode.data.notes || sourceNode.data.prompt || sourceNode.data.summary
        : `${sourceNode.data.title} 的临时音频草稿`)
  const position = getDerivedBranchPosition(document, sourceNode, targetKind, version)
  const startedAt = options?.startedAt ?? new Date().toISOString()
  const usesMock = options?.usesMock ?? options?.source === 'mock'
  const provider = options?.provider
    ?? (usesMock ? 'prototype-task-adapter' : 'openai-compatible')

  const pendingNode = createNode(nodeId, targetKind, {
    title: `${targetKind === 'image' && sourceNode.data.assetScope && sourceNode.data.assetScope !== 'shot' ? `${nodeSubject} 参考图` : `${labelPrefix} ${nodeSubject}`} v${version}`,
    summary: `${sourceNode.data.title} 派生生成中 · ${model}${usesMock ? '（Mock）' : '（真实）'}`,
    shotId: sourceNode.data.shotId,
    imageRole: targetKind === 'image' ? (sourceNode.data.assetScope && sourceNode.data.assetScope !== 'shot' ? 'reference' : 'storyboard') : undefined,
    assetScope: sourceNode.data.assetScope ?? 'shot',
    assetSubject: sourceNode.data.assetSubject ?? sourceNode.data.shotId,
    episode: sourceNode.data.episode,
    status: 'running',
    prompt,
    notes: targetKind === 'image' ? sourceNode.data.notes : undefined,
    previewUrl:
      targetKind === 'audio'
        ? undefined
        : makePlaceholderAsset(
            `${labelPrefix} v${version}`,
            targetKind === 'image' ? '#eab308' : '#22c55e',
            `${model} 正在生成`,
          ),
    position,
    versionInfo: {
      version,
      label: `v${version}`,
      shotId: sourceNode.data.shotId,
      sourceNodeId,
      createdAt: startedAt,
    },
    generation: {
      model,
      prompt,
      aspectRatio: '16:9',
      durationSeconds: targetKind === 'video' ? 5 : undefined,
      count: 1,
    },
    metadata: {
      source: options?.source ?? 'real',
      taskId: options?.taskId,
      runMode: 'task',
      taskStage: 'queued',
      startedAt,
      createdAt: startedAt,
      provider,
      usesMock,
      modelProfileId: options?.modelProfileId,
      modelName: model,
      sourceNodeId,
      sourceAssetId: options?.sourceAssetId,
      prompt,
    },
  })

  const edge = createEdge(`${sourceNodeId}-${nodeId}`, sourceNodeId, nodeId, 'derived')
  return {
    nodeId,
    document: {
      ...document,
      nodes: [...document.nodes, pendingNode],
      edges: [...document.edges, edge],
    },
  }
}

export function attachTaskIdToNode(document: CanvasDocument, nodeId: string, taskId: string): CanvasDocument {
  return updateNode(document, nodeId, (node) => ({
    ...node,
    data: {
      ...node.data,
      metadata: {
        ...(node.data.metadata ?? {}),
        taskId,
        taskStage: 'running',
        pollingStartedAt: new Date().toISOString(),
      },
    },
  }))
}

export function syncCreativeTaskStatus(
  document: CanvasDocument,
  nodeId: string,
  status: Pick<CreativeTaskStatus, 'status' | 'provider' | 'model_profile_id' | 'uses_mock' | 'external_task_id' | 'external_status' | 'poll_attempts' | 'provider_response'>,
): CanvasDocument {
  return updateNode(document, nodeId, (node) => ({
    ...node,
    data: {
      ...node.data,
      metadata: {
        ...(node.data.metadata ?? {}),
        taskStage: status.status === 'done' ? 'done' : status.status === 'error' ? 'error' : 'running',
        provider: status.provider ?? node.data.metadata?.provider,
        modelProfileId: status.model_profile_id ?? node.data.metadata?.modelProfileId,
        usesMock: typeof status.uses_mock === 'boolean' ? status.uses_mock : node.data.metadata?.usesMock,
        externalTaskId: status.external_task_id ?? node.data.metadata?.externalTaskId,
        externalStatus: status.external_status ?? node.data.metadata?.externalStatus,
        pollAttempts: status.poll_attempts ?? node.data.metadata?.pollAttempts,
        providerResponse: serializeProviderResponse(status.provider_response) ?? node.data.metadata?.providerResponse,
      },
    },
  }))
}

export function completeGenerationTask(
  document: CanvasDocument,
  nodeId: string,
  asset: CreativeTaskAsset,
): CanvasDocument {
  const isReferenceImage = asset.kind === 'image' && asset.metadata?.imageRole === 'reference'
  const usesMock = Boolean(asset.metadata?.usesMock)
  const next = updateNode(document, nodeId, (node) => ({
    ...node,
    data: {
      ...node.data,
      title: asset.title || node.data.title,
      summary: isReferenceImage ? `${usesMock ? 'Mock' : '真实'}参考图资产` : taskSummary(asset.kind, 'done', usesMock),
      status: 'done',
      prompt: asset.prompt ?? node.data.prompt,
      previewUrl: asset.previewUrl ?? node.data.previewUrl,
      content: asset.uri ?? node.data.content,
      errorMessage: undefined,
      versionInfo: node.data.versionInfo
        ? {
            ...node.data.versionInfo,
            label: asset.label || node.data.versionInfo.label,
          }
        : node.data.versionInfo,
      generation: node.data.generation
        ? {
            ...node.data.generation,
            model: asset.model ?? node.data.generation.model,
          }
        : node.data.generation,
      metadata: {
        ...(node.data.metadata ?? {}),
        source: asset.metadata?.usesMock ? 'mock' : 'real',
        taskId: undefined,
        taskStage: 'done',
        assetId: asset.id,
        assetUri: asset.uri,
        model: asset.model,
        elapsedSeconds: asset.elapsedSeconds,
        sourceAssetId: asset.sourceAssetId ?? node.data.metadata?.sourceAssetId,
        completedAt: typeof asset.metadata?.createdAt === 'string' ? asset.metadata.createdAt : new Date().toISOString(),
        prompt: asset.prompt ?? node.data.prompt,
        ...(asset.metadata ?? {}),
      },
      imageRole: asset.metadata?.imageRole === 'reference'
        ? 'reference'
        : asset.kind === 'image'
          ? node.data.imageRole ?? 'storyboard'
          : node.data.imageRole,
      assetScope: typeof asset.metadata?.assetScope === 'string'
        ? asset.metadata.assetScope as 'character' | 'location' | 'prop' | 'shot'
        : node.data.assetScope,
      assetSubject: typeof asset.metadata?.assetSubject === 'string'
        ? asset.metadata.assetSubject
        : node.data.assetSubject,
    },
  }))

  return asset.adopted === false ? next : adoptVersion(next, nodeId)
}

export function failGenerationTask(
  document: CanvasDocument,
  nodeId: string,
  targetKind: VersionKind,
  message: string,
  metadata?: {
    provider?: string
    modelProfileId?: string
    usesMock?: boolean
    externalTaskId?: string | null
    externalStatus?: string | null
    pollAttempts?: number | null
    providerResponse?: Record<string, unknown> | null
  },
): CanvasDocument {
  return updateNode(document, nodeId, (node) => ({
    ...node,
    data: {
      ...node.data,
      status: 'error',
      summary: taskSummary(targetKind, 'error'),
      errorMessage: message,
      metadata: {
        ...(node.data.metadata ?? {}),
        lastErrorAt: new Date().toISOString(),
        taskStage: 'error',
        provider: metadata?.provider ?? node.data.metadata?.provider,
        modelProfileId: metadata?.modelProfileId ?? node.data.metadata?.modelProfileId,
        usesMock: typeof metadata?.usesMock === 'boolean' ? metadata.usesMock : node.data.metadata?.usesMock,
        externalTaskId: metadata?.externalTaskId ?? node.data.metadata?.externalTaskId,
        externalStatus: metadata?.externalStatus ?? node.data.metadata?.externalStatus,
        pollAttempts: metadata?.pollAttempts ?? node.data.metadata?.pollAttempts,
        providerResponse: serializeProviderResponse(metadata?.providerResponse) ?? node.data.metadata?.providerResponse,
      },
    },
  }))
}

export function restartGenerationTask(document: CanvasDocument, nodeId: string): CanvasDocument {
  return updateNode(document, nodeId, (node) => ({
    ...node,
    data: {
      ...node.data,
      status: 'running',
      summary: taskSummary(
        node.data.kind === 'image' || node.data.kind === 'video' || node.data.kind === 'audio'
          ? node.data.kind
          : 'image',
        'running',
      ),
      errorMessage: undefined,
      metadata: {
        ...(node.data.metadata ?? {}),
        taskStage: 'queued',
        startedAt: new Date().toISOString(),
        failureHandledAt: undefined,
      },
    },
  }))
}

function taskSummary(kind: VersionKind, state: 'running' | 'done' | 'error', usesMock = false) {
  const label = kind === 'image' ? '分镜图' : kind === 'video' ? '视频' : '音频'
  if (state === 'running') return `${label}${usesMock ? ' Mock' : '真实'}任务生成中`
  if (state === 'error') return `${label}生成失败`
  return `${usesMock ? 'Mock' : '真实'}${label}资产`
}

export {
  serializeAdoptVersionRequest,
  serializeCreativeTaskRequest,
}
