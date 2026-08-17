import { describe, expect, it } from 'vitest'
import {
  MOCK_BIBLE,
  MOCK_GENERATED_IMAGES,
  MOCK_QA,
  MOCK_SCRIPTS,
  MOCK_STORYBOARD,
  MOCK_VISUAL,
} from './mockData'
import { addNode, createTemplateDocument } from './sceneComposerModel'
import {
  createResetDocument,
  pushHistoryState,
  redoHistoryState,
  undoHistoryState,
  type HistoryState,
} from './sceneComposerState'

const outputs = {
  bible: MOCK_BIBLE,
  scripts: MOCK_SCRIPTS,
  storyboard: MOCK_STORYBOARD,
  visual: MOCK_VISUAL,
  qa: MOCK_QA,
  generatedImages: MOCK_GENERATED_IMAGES,
}

describe('sceneComposerState', () => {
  it('pushes the previous document into undo history and clears redo history', () => {
    const initial = createTemplateDocument(outputs)
    const modified = addNode(initial, 'audio', { x: 120, y: 120 })
    const history: HistoryState = {
      past: [],
      future: [initial],
    }

    const nextHistory = pushHistoryState(history, initial)

    expect(nextHistory.past).toHaveLength(1)
    expect(nextHistory.past[0].nodes).toHaveLength(initial.nodes.length)
    expect(nextHistory.future).toHaveLength(0)
    expect(modified.nodes.length).toBeGreaterThan(initial.nodes.length)
  })

  it('undo restores the previous document and moves current state into redo history', () => {
    const initial = createTemplateDocument(outputs)
    const modified = addNode(initial, 'audio', { x: 120, y: 120 })
    const history: HistoryState = {
      past: [initial],
      future: [],
    }

    const result = undoHistoryState(history, modified)

    expect(result.document?.nodes).toHaveLength(initial.nodes.length)
    expect(result.history.past).toHaveLength(0)
    expect(result.history.future).toHaveLength(1)
    expect(result.history.future[0].nodes).toHaveLength(modified.nodes.length)
  })

  it('redo reapplies a future document and records the current state in undo history', () => {
    const initial = createTemplateDocument(outputs)
    const modified = addNode(initial, 'audio', { x: 120, y: 120 })
    const history: HistoryState = {
      past: [],
      future: [modified],
    }

    const result = redoHistoryState(history, initial)

    expect(result.document?.nodes).toHaveLength(modified.nodes.length)
    expect(result.history.past).toHaveLength(1)
    expect(result.history.past[0].nodes).toHaveLength(initial.nodes.length)
    expect(result.history.future).toHaveLength(0)
  })

  it('reset document recreates the clean template state', () => {
    const initial = createTemplateDocument(outputs)
    const modified = addNode(initial, 'audio', { x: 120, y: 120 })
    const reset = createResetDocument(outputs)

    expect(modified.nodes.length).toBeGreaterThan(reset.nodes.length)
    expect(reset.projectTitle).toBeTruthy()
    expect(reset.nodes.some((node) => node.data.kind === 'script')).toBe(true)
  })
})
