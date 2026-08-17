import { describe, expect, it, vi } from 'vitest'
import {
  MOCK_BIBLE,
  MOCK_GENERATED_IMAGES,
  MOCK_QA,
  MOCK_SCRIPTS,
  MOCK_STORYBOARD,
  MOCK_VISUAL,
} from './mockData'
import { createTemplateDocument } from './sceneComposerModel'
import {
  attachTaskIdToNode,
  completeGenerationTask,
  createPendingGenerationBranch,
  failGenerationTask,
  pollCreativeTask,
  restartGenerationTask,
  serializeAdoptVersionRequest,
  serializeCreativeTaskRequest,
  syncCreativeTaskStatus,
} from './sceneComposerTaskService'

const outputs = {
  bible: MOCK_BIBLE,
  scripts: MOCK_SCRIPTS,
  storyboard: MOCK_STORYBOARD,
  visual: MOCK_VISUAL,
  qa: MOCK_QA,
  generatedImages: MOCK_GENERATED_IMAGES,
}

describe('sceneComposerTaskService', () => {
  it('creates a running image task branch and stores task id', () => {
    const document = createTemplateDocument(outputs)
    const pending = createPendingGenerationBranch(document, 'shot-1-1', 'image', {
      modelProfileId: 'builtin-mock-image',
      modelName: 'Mock 图片模型',
      provider: 'prototype-task-adapter',
      usesMock: true,
      prompt: '夜景街道，主角抬头望向霓虹灯牌。',
      sourceAssetId: 'shot-seed-1-1',
      startedAt: '2026-06-26T12:00:00.000Z',
    })
    const withTaskId = attachTaskIdToNode(pending.document, pending.nodeId, 'task-image-1')
    const node = withTaskId.nodes.find((item) => item.id === pending.nodeId)

    expect(node?.data.kind).toBe('image')
    expect(node?.data.status).toBe('running')
    expect(node?.data.metadata?.taskId).toBe('task-image-1')
    expect(node?.data.metadata?.taskStage).toBe('running')
    expect(node?.data.metadata?.modelProfileId).toBe('builtin-mock-image')
    expect(node?.data.metadata?.modelName).toBe('Mock 图片模型')
    expect(node?.data.metadata?.provider).toBe('prototype-task-adapter')
    expect(node?.data.metadata?.usesMock).toBe(true)
    expect(node?.data.metadata?.sourceNodeId).toBe('shot-1-1')
    expect(node?.data.metadata?.sourceAssetId).toBe('shot-seed-1-1')
    expect(node?.data.metadata?.prompt).toBe('夜景街道，主角抬头望向霓虹灯牌。')
    expect(withTaskId.edges.some((edge) => edge.target === pending.nodeId && edge.source === 'shot-1-1')).toBe(true)
  })

  it('marks new task branches as queued before polling starts', () => {
    const document = createTemplateDocument(outputs)
    const pending = createPendingGenerationBranch(document, 'shot-1-1', 'image')
    const node = pending.document.nodes.find((item) => item.id === pending.nodeId)

    expect(node?.data.metadata?.taskStage).toBe('queued')
  })

  it('marks image task failure with an error reason', () => {
    const document = createTemplateDocument(outputs)
    const pending = createPendingGenerationBranch(document, 'shot-1-1', 'image')
    const failed = failGenerationTask(pending.document, pending.nodeId, 'image', '图片服务暂时不可用')
    const node = failed.nodes.find((item) => item.id === pending.nodeId)

    expect(node?.data.status).toBe('error')
    expect(node?.data.errorMessage).toContain('暂时不可用')
  })

  it('syncs external provider task status into node metadata while polling', () => {
    const document = createTemplateDocument(outputs)
    const pending = createPendingGenerationBranch(document, 'shot-1-1', 'image')
    const synced = syncCreativeTaskStatus(pending.document, pending.nodeId, {
      status: 'running',
      provider: 'poyo-async',
      model_profile_id: 'preset-poyo-image-seedream-5-lite',
      uses_mock: false,
      external_task_id: 'poyo-task-123',
      external_status: 'running',
      poll_attempts: 3,
      provider_response: { status: 'running', task_id: 'poyo-task-123' },
    })
    const node = synced.nodes.find((item) => item.id === pending.nodeId)

    expect(node?.data.metadata?.provider).toBe('poyo-async')
    expect(node?.data.metadata?.modelProfileId).toBe('preset-poyo-image-seedream-5-lite')
    expect(node?.data.metadata?.externalTaskId).toBe('poyo-task-123')
    expect(node?.data.metadata?.externalStatus).toBe('running')
    expect(node?.data.metadata?.pollAttempts).toBe(3)
    expect(node?.data.metadata?.providerResponse).toContain('"task_id": "poyo-task-123"')
  })

  it('completes a video task and adopts it into the sequence', () => {
    const document = createTemplateDocument(outputs)
    const pending = createPendingGenerationBranch(document, 'image-seed-1-1', 'video')
    const completed = completeGenerationTask(pending.document, pending.nodeId, {
      id: 'video-real-1',
      kind: 'video',
      title: '视频 1-1 v2',
      label: 'v2',
      uri: 'https://example.com/video-1-1-v2.mp4',
      previewUrl: 'https://example.com/video-1-1-v2.jpg',
      model: 'Kling 1.6',
      adopted: true,
      sourceAssetId: 'image-real-1',
      elapsedSeconds: 12,
      prompt: '镜头 1-1 运动版提示词',
      metadata: {
        provider: 'openai-compatible',
        modelProfileId: 'video-prod-1',
        modelName: 'Kling 1.6',
        sourceNodeId: 'image-seed-1-1',
        sourceAssetId: 'image-real-1',
        usesMock: false,
        createdAt: '2026-06-26T12:05:00.000Z',
      },
    })
    const node = completed.nodes.find((item) => item.id === pending.nodeId)

    expect(node?.data.status).toBe('done')
    expect(node?.data.metadata?.assetId).toBe('video-real-1')
    expect(node?.data.metadata?.taskStage).toBe('done')
    expect(node?.data.metadata?.provider).toBe('openai-compatible')
    expect(node?.data.metadata?.modelProfileId).toBe('video-prod-1')
    expect(node?.data.metadata?.modelName).toBe('Kling 1.6')
    expect(node?.data.metadata?.sourceAssetId).toBe('image-real-1')
    expect(node?.data.metadata?.prompt).toBe('镜头 1-1 运动版提示词')
    expect(node?.data.metadata?.completedAt).toBe('2026-06-26T12:05:00.000Z')
    expect(completed.adoptedVersions.video?.['1-1']).toBe(pending.nodeId)
    expect(
      completed.edges.some(
        (edge) => edge.source === pending.nodeId && edge.target === 'sequence-1' && edge.data?.kind === 'sequence',
      ),
    ).toBe(true)
  })

  it('keeps a failed video node retryable', () => {
    const document = createTemplateDocument(outputs)
    const pending = createPendingGenerationBranch(document, 'image-seed-1-1', 'video')
    const failed = failGenerationTask(pending.document, pending.nodeId, 'video', '视频生成超时')
    const restarted = restartGenerationTask(failed, pending.nodeId)
    const node = restarted.nodes.find((item) => item.id === pending.nodeId)

    expect(node?.data.status).toBe('running')
    expect(node?.data.errorMessage).toBeUndefined()
    expect(node?.data.metadata?.taskStage).toBe('queued')
    expect(typeof node?.data.metadata?.startedAt).toBe('string')
  })

  it('preserves provider diagnostics on failed tasks', () => {
    const document = createTemplateDocument(outputs)
    const pending = createPendingGenerationBranch(document, 'image-seed-1-1', 'video')
    const failed = failGenerationTask(pending.document, pending.nodeId, 'video', 'PoYo 任务失败', {
      provider: 'poyo-async',
      modelProfileId: 'preset-poyo-video-seedance-2',
      usesMock: false,
      externalTaskId: 'poyo-video-321',
      externalStatus: 'failed',
      pollAttempts: 6,
      providerResponse: { status: 'failed', error: 'quota exceeded' },
    })
    const node = failed.nodes.find((item) => item.id === pending.nodeId)

    expect(node?.data.metadata?.provider).toBe('poyo-async')
    expect(node?.data.metadata?.externalTaskId).toBe('poyo-video-321')
    expect(node?.data.metadata?.externalStatus).toBe('failed')
    expect(node?.data.metadata?.pollAttempts).toBe(6)
    expect(node?.data.metadata?.providerResponse).toContain('"quota exceeded"')
  })

  it('times out when polling exceeds max attempts', async () => {
    await expect(
      pollCreativeTask(
        async () => ({ task_id: 'task-timeout', status: 'running', target_kind: 'image' }),
        'task-timeout',
        { intervalMs: 0, maxAttempts: 2 },
      ),
    ).rejects.toThrow('轮询超时')
  })

  it('returns the first completed task state during polling', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce({ task_id: 'task-ok', status: 'running', target_kind: 'image' })
      .mockResolvedValueOnce({
        task_id: 'task-ok',
        status: 'done',
        target_kind: 'image',
        asset: {
          id: 'image-real-1',
          kind: 'image',
          title: '分镜图 1-1 v2',
          label: 'v2',
        },
      })

    const status = await pollCreativeTask(fetcher, 'task-ok', { intervalMs: 0, maxAttempts: 3 })
    expect(status.status).toBe('done')
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('serializes creative task requests to snake_case payloads', () => {
    expect(
      serializeCreativeTaskRequest({
        bookId: 5,
        episode: 1,
        shotId: '1-3',
        sourceNodeId: 'shot-1-3',
        sourceAssetId: 'image-real-1',
        assetScope: 'shot',
        assetSubject: '1-3',
        targetKind: 'image',
        prompt: '夜景街道',
        model: 'Seedream v4.5',
        referenceAssetIds: ['ref-a', 'ref-b'],
        aspectRatio: '16:9',
        durationSeconds: 5,
        count: 1,
        simulateError: false,
      }),
    ).toEqual({
      book_id: 5,
        episode: 1,
        shot_id: '1-3',
        source_node_id: 'shot-1-3',
        source_asset_id: 'image-real-1',
        asset_scope: 'shot',
        asset_subject: '1-3',
        target_kind: 'image',
        prompt: '夜景街道',
        model: 'Seedream v4.5',
        reference_asset_ids: ['ref-a', 'ref-b'],
        aspect_ratio: '16:9',
        duration_seconds: 5,
        count: 1,
        simulate_error: false,
      })
  })

  it('deduplicates reference asset ids during request serialization', () => {
    expect(
      serializeCreativeTaskRequest({
        bookId: 5,
        episode: 1,
        shotId: '1-3',
        sourceNodeId: 'shot-1-3',
        targetKind: 'image',
        prompt: '夜景街道',
        referenceAssetIds: ['ref-a', 'ref-b', 'ref-a', '', 'ref-b'],
        count: 1,
        simulateError: false,
      }),
    ).toMatchObject({
      reference_asset_ids: ['ref-a', 'ref-b'],
    })
  })

  it('serializes adopt-version requests to snake_case payloads', () => {
    expect(
      serializeAdoptVersionRequest({
        bookId: 5,
        episode: 1,
        shotId: '1-3',
        kind: 'video',
        assetId: 'video-real-1',
      }),
    ).toEqual({
      book_id: 5,
      episode: 1,
      shot_id: '1-3',
      kind: 'video',
      asset_id: 'video-real-1',
    })
  })

  it('creates reference image pending branches with reference role', () => {
    const document = createTemplateDocument(outputs)
    const pending = createPendingGenerationBranch(document, 'character-1', 'image')
    const node = pending.document.nodes.find((item) => item.id === pending.nodeId)

    expect(node?.data.imageRole).toBe('reference')
    expect(node?.data.assetScope).toBe('character')
  })

  it('keeps motion notes when creating a real image branch from a shot', () => {
    const document = createTemplateDocument(outputs)
    const pending = createPendingGenerationBranch(document, 'shot-1-1', 'image', { source: 'real' })
    const node = pending.document.nodes.find((item) => item.id === pending.nodeId)

    expect(node?.data.notes).toBeTruthy()
  })

  it('marks mock-completed image assets as mock in summary and metadata', () => {
    const document = createTemplateDocument(outputs)
    const pending = createPendingGenerationBranch(document, 'shot-1-2', 'image', {
      source: 'mock',
      usesMock: true,
      modelName: 'Mock 图片模型',
    })
    const completed = completeGenerationTask(pending.document, pending.nodeId, {
      id: 'image-mock-2',
      kind: 'image',
      title: '分镜图 1-2 v2',
      label: 'v2',
      previewUrl: 'https://example.com/image-mock-2.png',
      uri: 'https://example.com/image-mock-2.png',
      model: 'Mock 图片模型',
      adopted: true,
      metadata: {
        provider: 'prototype-task-adapter',
        modelProfileId: 'builtin-mock-image',
        modelName: 'Mock 图片模型',
        usesMock: true,
      },
    })
    const node = completed.nodes.find((item) => item.id === pending.nodeId)

    expect(node?.data.summary).toContain('Mock')
    expect(node?.data.metadata?.source).toBe('mock')
    expect(node?.data.metadata?.usesMock).toBe(true)
  })

  it('places new storyboard and video branches in separate shot lanes', () => {
    const document = createTemplateDocument(outputs)
    const pendingImage = createPendingGenerationBranch(document, 'shot-1-1', 'image', { source: 'real' })
    const imageNode = pendingImage.document.nodes.find((item) => item.id === pendingImage.nodeId)

    const pendingVideo = createPendingGenerationBranch(pendingImage.document, pendingImage.nodeId, 'video', { source: 'real' })
    const videoNode = pendingVideo.document.nodes.find((item) => item.id === pendingVideo.nodeId)

    expect(imageNode?.position.x).toBe(620)
    expect(videoNode?.position.x).toBe(980)
    expect(videoNode?.position.y).toBeGreaterThanOrEqual(imageNode?.position.y ?? 0)
  })
})
