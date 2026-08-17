import { createTemplateDocument, type CanvasDocument } from './sceneComposerModel'
import { createRealEpisodeDocument } from './sceneComposerRealDocument'
import type { OutputsData } from './sceneComposerData'

export interface HistoryState {
  past: CanvasDocument[]
  future: CanvasDocument[]
}

export function pushHistoryState(
  history: HistoryState,
  current: CanvasDocument,
): HistoryState {
  return {
    past: [...history.past.slice(-39), current],
    future: [],
  }
}

export function undoHistoryState(
  history: HistoryState,
  current: CanvasDocument,
): { document: CanvasDocument | null; history: HistoryState } {
  const previous = history.past[history.past.length - 1]
  if (!previous) {
    return { document: null, history }
  }

  return {
    document: previous,
    history: {
      past: history.past.slice(0, -1),
      future: [current, ...history.future].slice(0, 40),
    },
  }
}

export function redoHistoryState(
  history: HistoryState,
  current: CanvasDocument,
): { document: CanvasDocument | null; history: HistoryState } {
  const next = history.future[0]
  if (!next) {
    return { document: null, history }
  }

  return {
    document: next,
    history: {
      past: [...history.past, current].slice(-40),
      future: history.future.slice(1),
    },
  }
}

export function createResetDocument(
  data: OutputsData,
  options?: { episode?: number; projectTitle?: string; episodeTitle?: string },
): CanvasDocument {
  if (!options) {
    return createTemplateDocument(data)
  }
  return createRealEpisodeDocument(data, options)
}
