import { useEffect, useMemo, useState } from 'react'
import type { ScriptOutput, StoryboardShotOutput } from '../prototyping/sceneComposerData'
import {
  buildAdaptationSetupSummary,
  buildContentPreparationSummary,
  type ContentPreparationSummary,
} from './productWorkspaceUpstream'
import {
  buildDashboardActions,
  buildEpisodeProgress,
  type DashboardAction,
  type EpisodeProgress,
} from './productWorkspaceProgress'
import { buildQaWorkbenchSummary, type QaWorkbenchResponse } from './productWorkspaceTaskCenterData'
import {
  getScriptDecision,
  isScriptDecisionLocked,
  isScriptDecisionReleased,
  normalizeScriptDecisionState,
  type ScriptDecisionMap,
} from './productWorkspaceScriptDecisions'
import { buildScriptReleaseSummary } from './productWorkspaceScriptRelease'
import type { WorkspaceSection } from './productWorkspaceAssetViewController'

interface BookLike {
  id: number
}

interface BookDataLike {
  chapters?: number
  words?: number
  status?: string
}

interface AdaptationLike {
  name?: string
}

interface UseProductWorkspaceOverviewParams {
  book: BookLike
  bookData: BookDataLike | null | undefined
  data: {
    scripts?: ScriptOutput[]
    qa?: Array<{ episode: number; error_count?: number }>
    storyboard?: { episodeShots?: Record<number, StoryboardShotOutput[]> }
    visual?: {
      makeups?: unknown[]
      locations?: unknown[]
      props?: unknown[]
    }
  } | null | undefined
  contentTaskStatus: 'idle' | 'uploading' | 'running' | 'done' | 'error'
  selectedAdaptationId: string | null
  selectedAdaptation: AdaptationLike | null | undefined
  adaptationLockedAt: string | null | undefined
}

export interface WorkspaceSummary {
  contentReady: boolean
  chapterCount: number
  wordCount: number
  projectStatus: string
  episodesWithScripts: number
  totalShots: number
  visualCount: number
  qaCount: number
  hasDownstreamOutput: boolean
  contentSummary: ContentPreparationSummary
}

export function useProductWorkspaceOverview({
  book,
  bookData,
  data,
  contentTaskStatus,
  selectedAdaptationId,
  selectedAdaptation,
  adaptationLockedAt,
}: UseProductWorkspaceOverviewParams) {
  const [scriptDecisionState, setScriptDecisionState] = useState<ScriptDecisionMap>({})
  const [qaWorkbenchSummary, setQaWorkbenchSummary] = useState<ReturnType<typeof buildQaWorkbenchSummary>>([])

  const shotEpisodes = useMemo(
    () =>
      Object.entries(data?.storyboard?.episodeShots ?? {})
        .map(([episode, shots]) => ({ episode: Number(episode), shots }))
        .sort((left, right) => left.episode - right.episode),
    [data?.storyboard?.episodeShots],
  )

  const summary = useMemo<WorkspaceSummary>(() => {
    const scripts = data?.scripts ?? []
    const episodeShots = data?.storyboard?.episodeShots ?? {}
    const episodesWithScripts = scripts.length
    const totalShots = Object.values(episodeShots).reduce((sum, shots) => sum + shots.length, 0)
    const visualCount =
      (data?.visual?.makeups?.length ?? 0) +
      (data?.visual?.locations?.length ?? 0) +
      (data?.visual?.props?.length ?? 0)
    const qaCount =
      qaWorkbenchSummary.length > 0
        ? qaWorkbenchSummary.reduce((sum, item) => sum + item.openIssueCount + item.inProgressCount, 0)
        : (data?.qa ?? []).reduce((sum, item) => sum + (item.error_count ?? 0), 0)

    const chapterCount = bookData?.chapters ?? 0
    const wordCount = bookData?.words ?? 0
    const projectStatus = bookData?.status ?? 'draft'
    const hasDownstreamOutput = episodesWithScripts > 0 || totalShots > 0
    const contentSummary = buildContentPreparationSummary({
      chapterCount,
      wordCount,
      projectStatus,
      contentTaskStatus,
      hasDownstreamOutput,
    })

    return {
      contentReady: contentSummary.canProceedToAdaptation,
      chapterCount,
      wordCount,
      projectStatus,
      episodesWithScripts,
      totalShots,
      visualCount,
      qaCount,
      hasDownstreamOutput,
      contentSummary,
    }
  }, [bookData, contentTaskStatus, data, qaWorkbenchSummary])

  const legacyAdaptationReady = summary.hasDownstreamOutput
  const hasLockedAdaptation = Boolean(selectedAdaptation && adaptationLockedAt)

  const adaptationSummary = useMemo(
    () =>
      buildAdaptationSetupSummary({
        content: summary.contentSummary,
        hasLockedAdaptation,
        selectedAdaptationName: selectedAdaptation?.name,
        hasSelectedAdaptation: Boolean(selectedAdaptationId),
        hasDownstreamOutput: summary.hasDownstreamOutput,
      }),
    [hasLockedAdaptation, selectedAdaptation?.name, selectedAdaptationId, summary.contentSummary, summary.hasDownstreamOutput],
  )

  useEffect(() => {
    if (book.id <= 0) {
      setScriptDecisionState({})
      return
    }

    let cancelled = false

    fetch(`/api/books/${book.id}/script-decisions`, { cache: 'no-store' })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        return response.json()
      })
      .then((payload) => {
        if (cancelled) return
        setScriptDecisionState(normalizeScriptDecisionState(payload))
      })
      .catch(() => {
        if (cancelled) return
        setScriptDecisionState({})
      })

    return () => {
      cancelled = true
    }
  }, [book.id])

  useEffect(() => {
    if (book.id <= 0) {
      setQaWorkbenchSummary([])
      return
    }

    let cancelled = false

    fetch(`/api/books/${book.id}/qa/workbench`, { cache: 'no-store' })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        return response.json()
      })
      .then((payload: QaWorkbenchResponse) => {
        if (cancelled) return
        setQaWorkbenchSummary(buildQaWorkbenchSummary(payload))
      })
      .catch(() => {
        if (cancelled) return
        setQaWorkbenchSummary([])
      })

    return () => {
      cancelled = true
    }
  }, [book.id])

  const dashboardActions = useMemo<DashboardAction[]>(
    () =>
      buildDashboardActions({
        contentReady: summary.contentReady,
        adaptationLocked: hasLockedAdaptation,
        episodesWithScripts: summary.episodesWithScripts,
        scriptReleasePendingCount: (data?.scripts ?? []).filter((script) => {
          const decision = getScriptDecision(scriptDecisionState, script.episode)
          return buildScriptReleaseSummary({
            hasLockedAdaptation: hasLockedAdaptation || legacyAdaptationReady,
            hasScript: Boolean(script.content?.trim()),
            scriptLocked: isScriptDecisionLocked(decision),
            scriptReleased: isScriptDecisionReleased(decision),
          }).pendingDecision
        }).length,
        totalShots: summary.totalShots,
        visualCount: summary.visualCount,
        qaCount: summary.qaCount,
      }),
    [data?.scripts, hasLockedAdaptation, legacyAdaptationReady, scriptDecisionState, summary],
  )

  const episodeProgress = useMemo<EpisodeProgress[]>(() => {
    const shotsByEpisode = data?.storyboard?.episodeShots ?? {}
    const imagesByEpisode = new Map<number, number>()
    const videosByEpisode = new Map<number, number>()
    const qaByEpisode = new Map<number, number>()

    for (const [episodeKey, shots] of Object.entries(shotsByEpisode)) {
      const episode = Number(episodeKey)
      imagesByEpisode.set(episode, shots.reduce((sum, shot) => sum + (shot.assets?.images.length ?? 0), 0))
      videosByEpisode.set(episode, shots.reduce((sum, shot) => sum + (shot.assets?.videos.length ?? 0), 0))
    }

    if (qaWorkbenchSummary.length > 0) {
      for (const item of qaWorkbenchSummary) {
        qaByEpisode.set(item.episode, item.openIssueCount + item.inProgressCount)
      }
    } else {
      for (const item of data?.qa ?? []) {
        qaByEpisode.set(item.episode, item.error_count ?? 0)
      }
    }

    const episodeIds = new Set<number>([
      ...Object.keys(shotsByEpisode).map((value) => Number(value)),
      ...(data?.scripts ?? []).map((script) => script.episode),
      ...(qaWorkbenchSummary.length > 0 ? qaWorkbenchSummary.map((item) => item.episode) : (data?.qa ?? []).map((item) => item.episode)),
    ])

    return buildEpisodeProgress(
      Array.from(episodeIds)
        .filter((episode) => episode > 0)
        .map((episode) => ({
          episode,
          hasLockedAdaptation,
          hasScript: Boolean((data?.scripts ?? []).find((script) => script.episode === episode)),
          scriptLocked: isScriptDecisionLocked(getScriptDecision(scriptDecisionState, episode)),
          scriptReleased: isScriptDecisionReleased(getScriptDecision(scriptDecisionState, episode)),
          shotCount: shotsByEpisode[episode]?.length ?? 0,
          imageCount: imagesByEpisode.get(episode) ?? 0,
          videoCount: videosByEpisode.get(episode) ?? 0,
          qaCount: qaByEpisode.get(episode) ?? 0,
        })),
    )
  }, [data, hasLockedAdaptation, qaWorkbenchSummary, scriptDecisionState])

  const getSectionBlockedReason = (target: WorkspaceSection) => {
    if (target === 'dashboard' || target === 'content' || target === 'tasks' || target === 'models' || target === 'canvas') return null
    if (target === 'adaptation') return summary.contentReady ? null : summary.contentSummary.detail
    if (legacyAdaptationReady || hasLockedAdaptation) return null
    return summary.contentReady ? adaptationSummary.detail : summary.contentSummary.detail
  }

  return {
    shotEpisodes,
    summary,
    scriptDecisionState,
    setScriptDecisionState,
    legacyAdaptationReady,
    hasLockedAdaptation,
    adaptationSummary,
    dashboardActions,
    episodeProgress,
    getSectionBlockedReason,
  }
}
