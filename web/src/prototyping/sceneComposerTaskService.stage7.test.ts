import { describe, expect, it } from 'vitest'
import {
  completeGenerationTask,
  createPendingGenerationBranch,
  serializeCreativeTaskRequest,
} from './sceneComposerTaskService'
import {
  MOCK_BIBLE,
  MOCK_GENERATED_IMAGES,
  MOCK_QA,
  MOCK_SCRIPTS,
  MOCK_STORYBOARD,
  MOCK_VISUAL,
} from './mockData'
import { createTemplateDocument } from './sceneComposerModel'

const outputs = {
  bible: MOCK_BIBLE,
  scripts: MOCK_SCRIPTS,
  storyboard: MOCK_STORYBOARD,
  visual: MOCK_VISUAL,
  qa: MOCK_QA,
  generatedImages: MOCK_GENERATED_IMAGES,
}

describe('sceneComposerTaskService stage7 payloads', () => {
  it('includes model_profile_id when serializing creative task requests', () => {
    expect(
      serializeCreativeTaskRequest({
        bookId: 8,
        episode: 2,
        shotId: '2-1',
        sourceNodeId: 'shot-2-1',
        targetKind: 'image',
        prompt: 'É½Â·Ò¹¾°',
        model: 'gpt-image-1',
        modelProfileId: 'image-prod-1',
        count: 1,
      }),
    ).toMatchObject({
      model_profile_id: 'image-prod-1',
      model: 'gpt-image-1',
    })
  })

  it('preserves mock source metadata when a backend task uses the mock provider', () => {
    const document = createTemplateDocument(outputs)
    const pending = createPendingGenerationBranch(document, 'shot-1-1', 'image', { source: 'mock' })
    const completed = completeGenerationTask(pending.document, pending.nodeId, {
      id: 'image-mock-1',
      kind: 'image',
      title: '·Ö¾µÍ¼ 1-1 v2',
      label: 'v2',
      previewUrl: 'data:image/png;base64,mock',
      model: 'Mock Image',
      adopted: true,
      metadata: {
        source: 'mock',
        provider: 'prototype-task-adapter',
        modelProfileId: 'builtin-mock-image',
      },
    })
    const node = completed.nodes.find((item) => item.id === pending.nodeId)

    expect(node?.data.metadata?.source).toBe('mock')
    expect(node?.data.metadata?.provider).toBe('prototype-task-adapter')
  })
})
