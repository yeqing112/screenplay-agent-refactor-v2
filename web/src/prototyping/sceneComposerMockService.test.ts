import { describe, expect, it } from 'vitest'
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
  failMockGeneration,
  finishMockGeneration,
  startMockGeneration,
} from './sceneComposerMockService'

const outputs = {
  bible: MOCK_BIBLE,
  scripts: MOCK_SCRIPTS,
  storyboard: MOCK_STORYBOARD,
  visual: MOCK_VISUAL,
  qa: MOCK_QA,
  generatedImages: MOCK_GENERATED_IMAGES,
}

describe('sceneComposerMockService', () => {
  it('moves a node into running state when generation starts', () => {
    const document = createTemplateDocument(outputs)
    const next = startMockGeneration(document, 'shot-1-1')

    expect(next.nodes.find((node) => node.id === 'shot-1-1')?.data.status).toBe('running')
  })

  it('records an error when mock generation fails', () => {
    const document = createTemplateDocument(outputs)
    const running = startMockGeneration(document, 'shot-1-1')
    const failed = failMockGeneration(running, 'shot-1-1', 'image')

    expect(failed.nodes.find((node) => node.id === 'shot-1-1')?.data.status).toBe('error')
    expect(failed.nodes.find((node) => node.id === 'shot-1-1')?.data.errorMessage).toContain('临时模型超时')
  })

  it('creates a new adopted branch when generation succeeds', () => {
    const document = createTemplateDocument(outputs)
    const running = startMockGeneration(document, 'shot-1-2')
    const finished = finishMockGeneration(running, 'shot-1-2', 'image')
    const newImageNode = finished.nodes.find(
      (node) => node.id !== 'image-seed-1-2' && node.data.kind === 'image' && node.data.shotId === '1-2',
    )

    expect(newImageNode).toBeTruthy()
    expect(newImageNode?.data.summary).toContain('Mock')
    expect(finished.adoptedVersions.image?.['1-2']).toBe(newImageNode?.id)
    expect(finished.edges.some((edge) => edge.source === 'shot-1-2' && edge.target === newImageNode?.id)).toBe(true)
  })

  it('adds a sequence edge automatically when a new video branch is generated and adopted', () => {
    const document = createTemplateDocument(outputs)
    const running = startMockGeneration(document, 'shot-1-3')
    const finished = finishMockGeneration(running, 'shot-1-3', 'video')
    const newVideoNode = finished.nodes.find(
      (node) => node.data.kind === 'video' && node.data.shotId === '1-3',
    )

    expect(newVideoNode).toBeTruthy()
    expect(finished.adoptedVersions.video?.['1-3']).toBe(newVideoNode?.id)
    expect(
      finished.edges.some(
        (edge) =>
          edge.source === newVideoNode?.id &&
          edge.target === 'sequence-1' &&
          edge.data?.kind === 'sequence',
      ),
    ).toBe(true)
  })
})
