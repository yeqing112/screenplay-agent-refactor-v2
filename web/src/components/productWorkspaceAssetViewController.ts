import { useCallback, useEffect, useMemo, useState } from 'react'
import type { StoryboardShotOutput } from '../domain/bookOutputs'
import {
  buildAssetEpisodeInsights,
  type AssetCategory,
  type AssetEpisodeInsight,
  type AssetSummary,
} from './productWorkspaceAssets'
import type { CanvasNavigationTarget } from './productWorkspaceSectionContracts'
import { isProductAssetPendingSelection } from './productWorkspaceAssetReferenceState'
import type { CanvasHandoffTarget, TaskNavigationTarget } from './productWorkspaceSectionContracts'

export type WorkspaceSection =
  | 'dashboard'
  | 'content'
  | 'adaptation'
  | 'characters'
  | 'scripts'
  | 'storyboard'
  | 'canvas'
  | 'assets'
  | 'qa'
  | 'tasks'
  | 'delivery'
  | 'models'

export type RecoveryFocusContext = {
  target: 'storyboard' | 'assets'
  taskId?: string | null
  recoveryKind?: 'frame' | 'video' | 'reference' | 'prompt' | null
  recoveryIntent?: 'reference' | 'shot_variant_refinement' | null
  episode?: number | null
  shotId?: string | null
  assetId?: string | null
  assetLabel?: string | null
}

interface UseProductWorkspaceAssetViewParams {
  allAssets: AssetSummary[]
  episodeShots: Record<number, StoryboardShotOutput[]>
  setSection: (section: WorkspaceSection) => void
  setSelectedStoryboardShotId: (shotId: string | null) => void
  setCanvasNavigationTarget: (target: CanvasNavigationTarget | null) => void
  setTaskNavigationTarget: (target: TaskNavigationTarget | null) => void
  setCanvasHandoffTarget: (target: CanvasHandoffTarget | null) => void
  setQaNavigationTarget: (
    target: { episode: number | null; shotId: string | null; qaFocus?: 'delivery_recovery' | null } | null,
  ) => void
}

export type AssetCategoryFilter = 'all' | AssetCategory
export type AssetStatusFilter = 'all' | 'missing_reference' | 'pending_selection' | 'stale_prompt' | 'locked_reference'
export type AssetVersionFilter =
  | 'all'
  | 'base_identity'
  | 'episode_default'
  | 'shot_variant'
  | 'location_variant'
  | 'prop_variant'

export type AssetFilterState = {
  episodeFilteredAssets: AssetSummary[]
  searchFilteredAssets: AssetSummary[]
  categoryFilteredAssets: AssetSummary[]
  filteredAssets: AssetSummary[]
  versionFilteredAssets: AssetSummary[]
  assetCategoryCounts: Record<AssetCategoryFilter, number>
  assetStatusCounts: Record<AssetStatusFilter, number>
  assetVersionCounts: Record<AssetVersionFilter, number>
}

function normalizeShotDraftValue(value: string | null | undefined) {
  return String(value || '').trim()
}

export function buildInitialLinkedShotDraft(savedShotIds: string[], inferredShotIds: string[]) {
  const normalizedSaved = savedShotIds.map(normalizeShotDraftValue).filter(Boolean)
  if (normalizedSaved.length > 0) {
    return Array.from(new Set(normalizedSaved))
  }
  return Array.from(new Set(inferredShotIds.map(normalizeShotDraftValue).filter(Boolean)))
}

export function mergeLinkedShotDraftWithInferredShots(currentShotIds: string[], inferredShotIds: string[]) {
  return Array.from(
    new Set([
      ...currentShotIds.map(normalizeShotDraftValue).filter(Boolean),
      ...inferredShotIds.map(normalizeShotDraftValue).filter(Boolean),
    ]),
  )
}

function normalizeSearchText(value: string) {
  return value.trim().toLocaleLowerCase('zh-CN')
}

function collectCandidateNames(shot: StoryboardShotOutput | null | undefined) {
  const candidateNames = new Set<string>()
  if (!shot) return candidateNames

  for (const asset of shot.used_assets ?? []) {
    if (asset.asset_name) candidateNames.add(asset.asset_name)
  }
  for (const binding of shot.prompt_compile_context?.asset_bindings?.characters ?? []) {
    if (binding.asset_name) candidateNames.add(binding.asset_name)
    if (binding.stage_name) candidateNames.add(binding.stage_name)
  }
  if (shot.scene_name) candidateNames.add(shot.scene_name)
  return candidateNames
}

function matchesAssetIdentifier(asset: AssetSummary, assetId: string) {
  if (!assetId) return false
  const normalizedAssetId = assetId.trim()
  if (!normalizedAssetId) return false

  return (
    asset.id === normalizedAssetId ||
    String(asset.assetRecordId ?? '').trim() === normalizedAssetId
  )
}

function matchesShotBinding(asset: AssetSummary, episode: number | null, shotId: string) {
  if (!shotId.trim()) return false
  const normalizedShotId = shotId.trim()
  const compositeShotId = episode ? `${episode}-${normalizedShotId}` : ''

  return asset.shotIds.some((item) => {
    const normalized = String(item).trim()
    return normalized === normalizedShotId || normalized === compositeShotId
  })
}

function matchesAssetLabel(asset: AssetSummary, assetLabel: string) {
  if (!assetLabel.trim()) return false
  const normalizedAssetLabel = assetLabel.trim()
  return (
    asset.title === normalizedAssetLabel ||
    asset.subtitle === normalizedAssetLabel ||
    asset.variantGroupKey === normalizedAssetLabel ||
    asset.variantLabel === normalizedAssetLabel
  )
}

function normalizeStageToken(value: string | null | undefined) {
  return String(value || '')
    .trim()
    .toLowerCase()
}

export function resolveShotVariantNavigationTarget({
  allAssets,
  baseAsset,
  episode,
  shotId,
}: {
  allAssets: AssetSummary[]
  baseAsset: AssetSummary | null
  episode: number | null
  shotId: string
}) {
  if (!baseAsset || baseAsset.category !== 'character') return null

  const normalizedShotId = shotId.trim()
  const normalizedShotToken = normalizedShotId ? `shot_${normalizedShotId}` : ''
  const siblingIds = new Set((baseAsset.siblingVariants ?? []).map((variant) => variant.id))
  const variantGroupKey = baseAsset.variantGroupKey || baseAsset.title

  const candidates = allAssets
    .filter((asset) => {
      if (asset.category !== 'character' || asset.variantScope !== 'shot_variant') return false
      if (siblingIds.size > 0 && siblingIds.has(asset.id)) return true
      return (asset.variantGroupKey || asset.title) === variantGroupKey
    })
    .map((asset) => {
      const stageToken = normalizeStageToken(asset.variantStageName)
      let score = 0

      if (asset.variantGroupKey === baseAsset.variantGroupKey) score += 100
      if (asset.title === baseAsset.title) score += 80
      if (matchesShotBinding(asset, episode, normalizedShotId)) score += 60
      if (normalizedShotToken && stageToken.includes(normalizedShotToken)) score += 40
      if (normalizedShotId && stageToken.includes(normalizedShotId.toLowerCase())) score += 20
      if (asset.previewCount > 0) score += 5
      if (asset.lockedReferenceCount > 0) score += 3

      return { asset, score }
    })
    .filter((item) => item.score > 0)
    .sort((left, right) => {
      if (right.score !== left.score) return right.score - left.score
      return left.asset.title.localeCompare(right.asset.title, 'zh-CN')
    })

  return candidates[0]?.asset ?? null
}

function resolveAssetNavigationScore({
  asset,
  episode,
  shotId,
  assetId,
  assetLabel,
  candidateNames,
}: {
  asset: AssetSummary
  episode: number | null
  shotId: string
  assetId: string
  assetLabel: string
  candidateNames: Set<string>
}) {
  let score = 0

  if (matchesAssetIdentifier(asset, assetId)) score += 1000
  if (matchesShotBinding(asset, episode, shotId)) score += 700
  if (matchesAssetLabel(asset, assetLabel)) score += 500

  if (episode && asset.episodeIds.includes(episode)) score += 120
  if (candidateNames.has(asset.title)) score += 90
  if (candidateNames.has(asset.subtitle)) score += 80
  if (asset.variantGroupKey && candidateNames.has(asset.variantGroupKey)) score += 70
  if (asset.variantStageName && candidateNames.has(asset.variantStageName)) score += 60

  if (asset.variantScope === 'shot_variant') score += 25
  else if (asset.variantScope === 'episode_default') score += 15
  else if (asset.variantScope === 'base_identity') score += 5

  if (asset.previewCount > 0) score += 3
  if (asset.lockedReferenceCount > 0) score += 2

  return score
}

export function buildAssetFilterState({
  allAssets,
  assetsByEpisode,
  assetEpisodeFilter,
  assetCategoryFilter,
  assetStatusFilter,
  assetVersionFilter,
  assetSearchQuery,
  selectedAssetId,
}: {
  allAssets: AssetSummary[]
  assetsByEpisode: Map<number, Set<string>>
  assetEpisodeFilter: 'all' | number
  assetCategoryFilter: AssetCategoryFilter
  assetStatusFilter: AssetStatusFilter
  assetVersionFilter: AssetVersionFilter
  assetSearchQuery: string
  selectedAssetId: string | null
}): AssetFilterState {
  const keepSelectedAsset = (asset: AssetSummary) => (selectedAssetId ? asset.id === selectedAssetId : false)

  const episodeFilteredAssets =
    assetEpisodeFilter === 'all'
      ? allAssets
      : allAssets.filter((asset) => {
          const assetIds = assetsByEpisode.get(assetEpisodeFilter) ?? new Set<string>()
          return assetIds.has(asset.id) || keepSelectedAsset(asset)
        })

  const normalizedQuery = normalizeSearchText(assetSearchQuery)
  const searchFilteredAssets =
    !normalizedQuery
      ? episodeFilteredAssets
      : episodeFilteredAssets.filter((asset) => {
          const haystack = normalizeSearchText([asset.title, asset.subtitle, asset.prompt].filter(Boolean).join(' '))
          return haystack.includes(normalizedQuery) || keepSelectedAsset(asset)
        })

  const assetCategoryCounts: Record<AssetCategoryFilter, number> = {
    all: searchFilteredAssets.length,
    character: 0,
    location: 0,
    prop: 0,
  }
  for (const asset of searchFilteredAssets) {
    assetCategoryCounts[asset.category] += 1
  }

  const categoryFilteredAssets =
    assetCategoryFilter === 'all'
      ? searchFilteredAssets
      : searchFilteredAssets.filter((asset) => asset.category === assetCategoryFilter || keepSelectedAsset(asset))

  const assetStatusCounts: Record<AssetStatusFilter, number> = {
    all: categoryFilteredAssets.length,
    missing_reference: 0,
    pending_selection: 0,
    stale_prompt: 0,
    locked_reference: 0,
  }
  for (const asset of categoryFilteredAssets) {
    if (asset.previewCount === 0) assetStatusCounts.missing_reference += 1
    if (isProductAssetPendingSelection(asset)) assetStatusCounts.pending_selection += 1
    if (asset.hasStaleReferencePrompt) assetStatusCounts.stale_prompt += 1
    if (asset.lockedReferenceCount > 0) assetStatusCounts.locked_reference += 1
  }

  const filteredAssets =
    assetStatusFilter === 'all'
      ? categoryFilteredAssets
      : categoryFilteredAssets.filter((asset) => {
          if (keepSelectedAsset(asset)) return true
          if (assetStatusFilter === 'missing_reference') return asset.previewCount === 0
          if (assetStatusFilter === 'pending_selection') return isProductAssetPendingSelection(asset)
          if (assetStatusFilter === 'stale_prompt') return asset.hasStaleReferencePrompt
          return asset.lockedReferenceCount > 0
        })

  const assetVersionCounts: Record<AssetVersionFilter, number> = {
    all: filteredAssets.length,
    base_identity: 0,
    episode_default: 0,
    shot_variant: 0,
    location_variant: 0,
    prop_variant: 0,
  }
  for (const asset of filteredAssets) {
    if (asset.variantScope === 'base_identity') assetVersionCounts.base_identity += 1
    if (asset.variantScope === 'episode_default') assetVersionCounts.episode_default += 1
    if (asset.variantScope === 'shot_variant') assetVersionCounts.shot_variant += 1
    if (asset.variantScope === 'scene_variant') assetVersionCounts.location_variant += 1
    if (asset.variantScope === 'prop_variant') assetVersionCounts.prop_variant += 1
  }

  const versionFilteredAssets =
    assetVersionFilter === 'all'
      ? filteredAssets
      : filteredAssets.filter((asset) => {
          if (keepSelectedAsset(asset)) return true
          if (assetVersionFilter === 'base_identity') return asset.variantScope === 'base_identity'
          if (assetVersionFilter === 'episode_default') return asset.variantScope === 'episode_default'
          if (assetVersionFilter === 'shot_variant') return asset.variantScope === 'shot_variant'
          if (assetVersionFilter === 'location_variant') return asset.variantScope === 'scene_variant'
          return asset.variantScope === 'prop_variant'
        })

  return {
    episodeFilteredAssets,
    searchFilteredAssets,
    categoryFilteredAssets,
    filteredAssets,
    versionFilteredAssets,
    assetCategoryCounts,
    assetStatusCounts,
    assetVersionCounts,
  }
}

export function resolveAssetTaskNavigationTarget({
  allAssets,
  episode,
  shotId,
  assetId,
  assetLabel,
  matchedShot,
}: {
  allAssets: AssetSummary[]
  episode: number | null
  shotId: string
  assetId: string
  assetLabel: string
  matchedShot: StoryboardShotOutput | null
}) {
  const candidateNames = collectCandidateNames(matchedShot)
  const rankedCandidates = allAssets
    .map((asset) => ({
      asset,
      score: resolveAssetNavigationScore({
        asset,
        episode,
        shotId,
        assetId,
        assetLabel,
        candidateNames,
      }),
    }))
    .filter((item) => item.score > 0)
    .sort((left, right) => {
      if (right.score !== left.score) return right.score - left.score
      if ((right.asset.previewCount || 0) !== (left.asset.previewCount || 0)) {
        return (right.asset.previewCount || 0) - (left.asset.previewCount || 0)
      }
      return left.asset.title.localeCompare(right.asset.title, 'zh-CN')
    })

  return rankedCandidates[0]?.asset ?? null
}

export function useProductWorkspaceAssetView({
  allAssets,
  episodeShots,
  setSection,
  setSelectedStoryboardShotId,
  setCanvasNavigationTarget,
  setTaskNavigationTarget,
  setCanvasHandoffTarget,
  setQaNavigationTarget,
}: UseProductWorkspaceAssetViewParams) {
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null)
  const [assetEpisodeFilter, setAssetEpisodeFilter] = useState<'all' | number>('all')
  const [assetCategoryFilter, setAssetCategoryFilter] = useState<AssetCategoryFilter>('all')
  const [assetStatusFilter, setAssetStatusFilter] = useState<AssetStatusFilter>('all')
  const [assetVersionFilter, setAssetVersionFilter] = useState<AssetVersionFilter>('all')
  const [assetSearchQuery, setAssetSearchQuery] = useState('')
  const [assetPreviewUrl, setAssetPreviewUrl] = useState<string | null>(null)
  const [assetPreviewLabel, setAssetPreviewLabel] = useState('')
  const [recoveryFocus, setRecoveryFocus] = useState<RecoveryFocusContext | null>(null)
  const [linkedShotDraft, setLinkedShotDraft] = useState<string[]>([])
  const [shotBindingState, setShotBindingState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')

  const assetsByEpisode = useMemo(() => {
    const result = new Map<number, Set<string>>()
    const assetTitleToIds = new Map<string, string[]>()

    for (const asset of allAssets) {
      const titles = [asset.title, asset.subtitle].filter(Boolean)
      for (const title of titles) {
        const bucket = assetTitleToIds.get(title) ?? []
        bucket.push(asset.id)
        assetTitleToIds.set(title, bucket)
      }
      for (const shotId of asset.shotIds) {
        const episode = Number(String(shotId).split('-')[0])
        if (!episode) continue
        const bucket = result.get(episode) ?? new Set<string>()
        bucket.add(asset.id)
        result.set(episode, bucket)
      }
    }

    for (const [episodeKey, shots] of Object.entries(episodeShots)) {
      const episode = Number(episodeKey)
      if (!episode) continue
      const bucket = result.get(episode) ?? new Set<string>()
      for (const shot of shots) {
        const candidateNames = collectCandidateNames(shot)
        for (const name of candidateNames) {
          for (const assetId of assetTitleToIds.get(name) ?? []) {
            bucket.add(assetId)
          }
        }
      }
      result.set(episode, bucket)
    }

    return result
  }, [allAssets, episodeShots])

  const assetFilterState = useMemo(
    () =>
      buildAssetFilterState({
        allAssets,
        assetsByEpisode,
        assetEpisodeFilter,
        assetCategoryFilter,
        assetStatusFilter,
        assetVersionFilter,
        assetSearchQuery,
        selectedAssetId,
      }),
    [
      allAssets,
      assetCategoryFilter,
      assetEpisodeFilter,
      assetSearchQuery,
      assetStatusFilter,
      assetVersionFilter,
      assetsByEpisode,
      selectedAssetId,
    ],
  )
  const {
    filteredAssets,
    versionFilteredAssets,
    assetCategoryCounts,
    assetStatusCounts,
    assetVersionCounts,
  } = assetFilterState

  const assetEpisodeInsights = useMemo<Map<string, AssetEpisodeInsight>>(() => {
    const shots =
      assetEpisodeFilter === 'all'
        ? Object.values(episodeShots).flatMap((episodeShotList) => episodeShotList ?? [])
        : (episodeShots[assetEpisodeFilter] ?? [])
    return buildAssetEpisodeInsights(versionFilteredAssets, shots)
  }, [assetEpisodeFilter, episodeShots, versionFilteredAssets])

  const prioritizedAssets = useMemo(() => {
    return [...versionFilteredAssets].sort((left, right) => {
      const leftInsight = assetEpisodeInsights.get(left.id) ?? { shotIds: [], blockerCount: 0, missingReference: false }
      const rightInsight = assetEpisodeInsights.get(right.id) ?? { shotIds: [], blockerCount: 0, missingReference: false }
      const leftPriority = (leftInsight.missingReference ? 100 : 0) + leftInsight.shotIds.length * 10 + leftInsight.blockerCount
      const rightPriority =
        (rightInsight.missingReference ? 100 : 0) + rightInsight.shotIds.length * 10 + rightInsight.blockerCount
      if (rightPriority !== leftPriority) return rightPriority - leftPriority
      return left.title.localeCompare(right.title, 'zh-CN')
    })
  }, [assetEpisodeInsights, versionFilteredAssets])

  const selectedAsset = useMemo(
    () => prioritizedAssets.find((asset) => asset.id === selectedAssetId) ?? prioritizedAssets[0] ?? null,
    [prioritizedAssets, selectedAssetId],
  )

  const selectedAssetInsight = useMemo(
    () => (selectedAsset ? assetEpisodeInsights.get(selectedAsset.id) ?? null : null),
    [assetEpisodeInsights, selectedAsset],
  )

  useEffect(() => {
    if (prioritizedAssets.length === 0) {
      setSelectedAssetId(null)
      return
    }
    setSelectedAssetId((current) => {
      if (current && prioritizedAssets.some((asset) => asset.id === current)) return current
      return prioritizedAssets[0]?.id ?? null
    })
  }, [prioritizedAssets])

  useEffect(() => {
    setLinkedShotDraft(
      buildInitialLinkedShotDraft(selectedAsset?.shotIds ?? [], selectedAssetInsight?.shotIds ?? []),
    )
    setShotBindingState('idle')
  }, [selectedAsset?.id, selectedAsset?.shotIds, selectedAssetInsight?.shotIds])

  const navigateTaskSection = useCallback(
    (
      target: WorkspaceSection,
      options?: {
        episode?: number | null
        shotId?: string | null
        assetId?: string | null
        assetLabel?: string | null
        taskId?: string | null
        recoveryKind?: 'frame' | 'video' | 'reference' | 'prompt' | null
        recoveryIntent?: 'reference' | 'shot_variant_refinement' | null
        qaFocus?: 'delivery_recovery' | null
        navigationSource?: 'canvas' | 'tasks' | 'delivery' | 'assets' | 'storyboard' | null
        handoffLabel?: string | null
        handoffDetail?: string | null
      },
    ) => {
      const episode = Number(options?.episode ?? 0) || null
      const shotId = String(options?.shotId ?? '').trim()
      const assetId = String(options?.assetId ?? '').trim()
      const assetLabel = String(options?.assetLabel ?? '').trim()
      const navigationSource = options?.navigationSource ?? null
      const nextCanvasHandoff =
        navigationSource === 'canvas' && (target === 'storyboard' || target === 'assets' || target === 'qa' || target === 'delivery')
          ? {
              target,
              episode,
              shotId: shotId || null,
              assetId: assetId || null,
              assetLabel: assetLabel || null,
              taskId: options?.taskId ?? null,
              recoveryKind: options?.recoveryKind ?? null,
              recoveryIntent: options?.recoveryIntent ?? null,
              qaFocus: options?.qaFocus ?? null,
              handoffLabel: options?.handoffLabel ?? null,
              handoffDetail: options?.handoffDetail ?? null,
            }
          : null

      if (episode && target === 'storyboard') {
        const matchedShot =
          (shotId ? episodeShots[episode]?.find((item) => String(item.shot_id) === shotId) : null) ??
          episodeShots[episode]?.[0] ??
          null
        if (matchedShot?.shot_id) {
          setSelectedStoryboardShotId(String(matchedShot.shot_id))
        }
      }

      if (episode && target === 'assets') {
        setAssetEpisodeFilter(episode)
        const matchedShot =
          (shotId ? episodeShots[episode]?.find((item) => String(item.shot_id) === shotId) : null) ??
          episodeShots[episode]?.[0] ??
          null
        const matchedAsset = resolveAssetTaskNavigationTarget({
          allAssets,
          episode,
          shotId,
          assetId,
          assetLabel,
          matchedShot,
        })
        if (matchedAsset) {
          setAssetCategoryFilter(matchedAsset.category)
          setSelectedAssetId(matchedAsset.id)
        }
        const inferredRecoveryIntent =
          options?.recoveryIntent ??
          (!options?.taskId && !options?.recoveryKind && shotId && matchedAsset?.category === 'character'
            ? 'shot_variant_refinement'
            : null)
        const preferredRecoveryAsset =
          inferredRecoveryIntent === 'shot_variant_refinement'
            ? resolveShotVariantNavigationTarget({
                allAssets,
                baseAsset: matchedAsset,
                episode,
                shotId,
              }) ?? matchedAsset
            : matchedAsset
        if (inferredRecoveryIntent === 'shot_variant_refinement') {
          setAssetCategoryFilter('character')
          setAssetVersionFilter('shot_variant')
          setAssetStatusFilter('all')
        }
        if (preferredRecoveryAsset) {
          setSelectedAssetId(preferredRecoveryAsset.id)
        }

        setRecoveryFocus({
          target,
          taskId: options?.taskId ?? null,
          recoveryKind: options?.recoveryKind ?? null,
          recoveryIntent: inferredRecoveryIntent,
          episode,
          shotId: shotId || null,
          assetId: preferredRecoveryAsset?.id ?? (assetId || null),
          assetLabel: assetLabel || preferredRecoveryAsset?.title || null,
        })
      } else if (target === 'storyboard') {
        setRecoveryFocus({
          target,
          taskId: options?.taskId ?? null,
          recoveryKind: options?.recoveryKind ?? null,
          recoveryIntent: options?.recoveryIntent ?? null,
          episode,
          shotId: shotId || null,
          assetId: assetId || null,
          assetLabel: assetLabel || null,
        })
      } else if (target === 'canvas') {
        setRecoveryFocus(null)
        setCanvasNavigationTarget({
          episode,
          shotId: shotId || null,
          assetId: assetId || null,
          assetLabel: assetLabel || null,
          taskId: options?.taskId ?? null,
          recoveryKind: options?.recoveryKind ?? null,
          recoveryIntent: options?.recoveryIntent ?? null,
        })
      } else if (target === 'tasks') {
        setRecoveryFocus(null)
        setTaskNavigationTarget({
          episode,
          shotId: shotId || null,
          assetId: assetId || null,
          assetLabel: assetLabel || null,
          taskId: options?.taskId ?? null,
          recoveryKind: options?.recoveryKind ?? null,
          recoveryIntent: options?.recoveryIntent ?? null,
        })
      } else {
        setRecoveryFocus(null)
      }

      if (target !== 'canvas') {
        setCanvasNavigationTarget(null)
      }
      setCanvasHandoffTarget(nextCanvasHandoff)
      if (target !== 'tasks') {
        setTaskNavigationTarget(null)
      }

      if (target === 'qa') {
        setQaNavigationTarget({
          episode,
          shotId: shotId || null,
          qaFocus: options?.qaFocus ?? null,
        })
      } else {
        setQaNavigationTarget(null)
      }

      setSection(target)
    },
    [allAssets, episodeShots, setCanvasHandoffTarget, setCanvasNavigationTarget, setQaNavigationTarget, setSection, setSelectedStoryboardShotId, setTaskNavigationTarget],
  )

  const openAssetPreview = useCallback((url: string, label: string) => {
    setAssetPreviewUrl(url)
    setAssetPreviewLabel(label)
  }, [])

  const closeAssetPreview = useCallback(() => {
    setAssetPreviewUrl(null)
    setAssetPreviewLabel('')
  }, [])

  const dismissStoryboardRecoveryFocus = useCallback(() => {
    setRecoveryFocus((current) => (current?.target === 'storyboard' ? null : current))
  }, [])

  const dismissAssetsRecoveryFocus = useCallback(() => {
    setRecoveryFocus((current) => (current?.target === 'assets' ? null : current))
  }, [])

  const clearNavigationContext = useCallback(() => {
    setRecoveryFocus(null)
  }, [])

  const navigateAssetShot = useCallback(
    (shotId: string) => {
      setSelectedStoryboardShotId(shotId)
      setSection('storyboard')
    },
    [setSection, setSelectedStoryboardShotId],
  )

  const toggleShotBinding = useCallback((shotId: string) => {
    setLinkedShotDraft((current) => (current.includes(shotId) ? current.filter((item) => item !== shotId) : [...current, shotId]))
  }, [])

  const applyInferredShotBindings = useCallback(() => {
    setLinkedShotDraft((current) =>
      mergeLinkedShotDraftWithInferredShots(current, selectedAssetInsight?.shotIds ?? []),
    )
    setShotBindingState('idle')
  }, [selectedAssetInsight?.shotIds])

  return {
    selectedAssetId,
    setSelectedAssetId,
    assetEpisodeFilter,
    setAssetEpisodeFilter,
    assetCategoryFilter,
    setAssetCategoryFilter,
    assetStatusFilter,
    setAssetStatusFilter,
    assetVersionFilter,
    setAssetVersionFilter,
    assetSearchQuery,
    setAssetSearchQuery,
    assetCategoryCounts,
    assetStatusCounts,
    assetVersionCounts,
    assetPreviewUrl,
    assetPreviewLabel,
    openAssetPreview,
    closeAssetPreview,
    recoveryFocus,
    dismissStoryboardRecoveryFocus,
    dismissAssetsRecoveryFocus,
    clearNavigationContext,
    linkedShotDraft,
    setLinkedShotDraft,
    toggleShotBinding,
    applyInferredShotBindings,
    shotBindingState,
    setShotBindingState,
    assetsByEpisode,
    filteredAssets,
    assetEpisodeInsights,
    prioritizedAssets,
    selectedAsset,
    navigateTaskSection,
    navigateAssetShot,
  }
}
