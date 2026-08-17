import { useMemo } from 'react'
import type {
  ScriptOutput,
  StoryboardShotOutput,
  VisualLocationOutput,
  VisualMakeupOutput,
  VisualPropOutput,
} from '../prototyping/sceneComposerData'

export interface WorkspaceQaEntry {
  id?: number
  episode: number
  result: unknown
  error_count?: number
}

interface WorkspaceProjectOutputs {
  scripts?: ScriptOutput[]
  qa?: Array<{ id?: number; episode: number; result?: unknown; error_count?: number }>
  storyboard?: { episodeShots?: Record<number, StoryboardShotOutput[]> }
  visual?: {
    makeups?: VisualMakeupOutput[]
    locations?: VisualLocationOutput[]
    props?: VisualPropOutput[]
  }
}

export function useProductWorkspaceProjectData(data: WorkspaceProjectOutputs | null | undefined) {
  return useMemo(() => {
    const scripts = data?.scripts ?? []
    const shotsByEpisode = data?.storyboard?.episodeShots ?? {}
    const qaEntries: WorkspaceQaEntry[] = (data?.qa ?? []).map((item) => ({
      id: item.id,
      episode: item.episode,
      result: item.result ?? null,
      error_count: item.error_count,
    }))
    const makeups = data?.visual?.makeups ?? []
    const locations = data?.visual?.locations ?? []
    const props = data?.visual?.props ?? []

    return {
      firstScript: scripts[0] ?? null,
      scripts,
      shotsByEpisode,
      qaEntries,
      makeups,
      locations,
      props,
    }
  }, [data])
}
