import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Boxes,
  Clapperboard,
  Compass,
  FileOutput,
  FileText,
  Library,
  ListTodo,
  Network,
  Settings2,
  Wrench,
} from 'lucide-react'
import { useBookOutputs } from '../hooks/useBookOutputs'
import { useProductWorkspaceUpstream } from './productWorkspaceUpstreamController'
import {
  buildCharacterAssetSummaries,
  buildLocationAssetSummaries,
  buildPropAssetSummaries,
} from './productWorkspaceAssets'
import {
  useProductWorkspaceAssetView,
  type WorkspaceSection,
} from './productWorkspaceAssetViewController'
import {
  type GenerateReferenceOutcome,
  runDeleteReferenceAsset,
  runGenerateSelectedAssetReference,
  runSaveAssetShotBindings,
  runUpdateReferenceAssetStatus,
} from './productWorkspaceAssetActions'
import { useProductWorkspaceOverview } from './productWorkspaceOverviewController'
import { useProductWorkspaceProjectData } from './productWorkspaceProjectDataController'
import type { CanvasHandoffTarget, CanvasNavigationTarget, TaskNavigationTarget } from './productWorkspaceSectionContracts'
import { useProductWorkspaceSectionBundles } from './productWorkspaceSectionBundlesController'
import {
  readProductWorkspaceNavigationState,
  writeProductWorkspaceNavigationState,
} from './productWorkspaceNavigationState'
import ProductWorkspaceSectionContent from './ProductWorkspaceSectionContent'
import ProductWorkspaceShell from './ProductWorkspaceShell'

interface Props {
  book: { id: number; title: string }
  bookData: any
  onRefresh: () => void
  onBookChange: (bookId: number) => void
}

const sections: Array<{ id: WorkspaceSection; label: string; icon: typeof Library; group: '创作' | '生产与检查' | '管理' }> = [
  { id: 'dashboard', label: '项目控制台', icon: Library, group: '创作' },
  { id: 'content', label: '内容准备', icon: Library, group: '创作' },
  { id: 'adaptation', label: '改编方向', icon: Compass, group: '创作' },
  { id: 'scripts', label: '剧本工作台', icon: FileText, group: '创作' },
  { id: 'storyboard', label: '镜头工作台', icon: Clapperboard, group: '创作' },
  { id: 'canvas', label: '创作画布', icon: Network, group: '创作' },
  { id: 'assets', label: '资产中心', icon: Boxes, group: '生产与检查' },
  { id: 'qa', label: 'QA 修复', icon: Wrench, group: '生产与检查' },
  { id: 'tasks', label: '任务中心', icon: ListTodo, group: '生产与检查' },
  { id: 'delivery', label: '导出中心', icon: FileOutput, group: '生产与检查' },
  { id: 'models', label: '模型管理', icon: Settings2, group: '管理' },
]

function toVisualAssetType(category: 'character' | 'location' | 'prop') {
  if (category === 'location') return 'scene'
  return category
}

export function buildEpisodeSequence(episodeCount: number) {
  const count = Math.max(1, Math.floor(Number(episodeCount) || 1))
  return Array.from({ length: count }, (_, index) => index + 1)
}

export default function ProductWorkspace({
  book,
  bookData,
  onRefresh,
  onBookChange,
}: Props) {
  const persistedNavigationState = useMemo(() => readProductWorkspaceNavigationState(book.id), [book.id])
  const [section, setSection] = useState<WorkspaceSection>(persistedNavigationState?.section ?? 'dashboard')
  const [selectedStoryboardShotId, setSelectedStoryboardShotId] = useState<string | null>(null)
  const [canvasNavigationTarget, setCanvasNavigationTarget] = useState<CanvasNavigationTarget | null>(
    persistedNavigationState?.canvasNavigationTarget ?? null,
  )
  const [taskNavigationTarget, setTaskNavigationTarget] = useState<TaskNavigationTarget | null>(null)
  const [canvasHandoffTarget, setCanvasHandoffTarget] = useState<CanvasHandoffTarget | null>(null)
  const [qaNavigationTarget, setQaNavigationTarget] = useState<{
    episode: number | null
    shotId: string | null
    qaFocus?: 'delivery_recovery' | null
  } | null>(null)
  const [assetActionMessage, setAssetActionMessage] = useState('')
  const [assetActionTone, setAssetActionTone] = useState<'info' | 'error'>('info')
  const [assetActionFollowUp, setAssetActionFollowUp] = useState<{
    mode: 'tasks' | 'storyboard'
    label: string
    taskId?: string
    episode?: number | null
    shotId?: string | null
    assetId?: string | null
  } | null>(null)
  const [assetGenerationState, setAssetGenerationState] = useState<'idle' | 'saving'>('idle')
  const [isGeneratingScripts, setIsGeneratingScripts] = useState(false)
  const [isGeneratingStoryboard, setIsGeneratingStoryboard] = useState(false)
  const { data, loading, error, refresh } = useBookOutputs(book.id)

  const handleRefreshAll = useCallback(() => {
    onRefresh()
    refresh()
  }, [onRefresh, refresh])

  const {
    firstScript,
    scripts,
    shotsByEpisode,
    qaEntries,
    makeups,
    locations,
    props,
  } = useProductWorkspaceProjectData(data)

  const {
    uploadFile,
    setUploadFile,
    shortTitle,
    setShortTitle,
    shortText,
    setShortText,
    episodeCount,
    setEpisodeCount,
    contentTask,
    adaptationOptions,
    selectedAdaptationId,
    setSelectedAdaptationId,
    adaptationCustomNote,
    setAdaptationCustomNote,
    adaptationLockedAt,
    selectedAdaptation,
    productionSkillSectionState,
    handleNovelUpload,
    handleShortCreate,
    setSelectedProductionSkillId,
    updateProductionSkillField,
    toggleProductionSkillPriority,
    lockProductionSkill,
    unlockProductionSkill,
    regenerateAdaptationOptions,
    lockSelectedAdaptation,
    unlockAdaptation,
  } = useProductWorkspaceUpstream({
    bookId: book.id,
    bookTitle: book.title,
    chapterCount: bookData?.chapters ?? 0,
    wordCount: bookData?.words ?? 0,
    scriptExcerpt: firstScript?.content,
    episodeCountDefault: Math.max(1, Number(bookData?.episodes ?? bookData?.chapters ?? 1) || 1),
    onBookChange,
    onRefreshAll: handleRefreshAll,
  })

  const handleGenerateScripts = useCallback(async () => {
    if (isGeneratingScripts) return
    setIsGeneratingScripts(true)
    try {
      const genre = 'short_drama'
      const res = await fetch('/api/pipeline/script', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          book_id: book.id,
          genre,
          episode_count: episodeCount || 1,
        }),
      })
      const data = await res.json()
      if (data.task_id) {
        const poll = async () => {
          try {
            const pr = await fetch(`/api/pipeline/task/${data.task_id}`)
            const pd = await pr.json()
            if (pd.status === 'running' || pd.status === 'queued') {
              setTimeout(poll, 3000)
            } else if (pd.status === 'done') {
              setIsGeneratingScripts(false)
              handleRefreshAll()
            } else {
              setIsGeneratingScripts(false)
              console.error('Pipeline failed:', pd.error)
            }
          } catch {
            setIsGeneratingScripts(false)
          }
        }
        poll()
      } else {
        setIsGeneratingScripts(false)
      }
    } catch {
      setIsGeneratingScripts(false)
    }
  }, [book.id, episodeCount, isGeneratingScripts, handleRefreshAll])

  const handleGenerateStoryboard = useCallback(async () => {
    if (isGeneratingStoryboard) return
    setIsGeneratingStoryboard(true)
    try {
      const genre = 'short_drama'
      const res = await fetch('/api/pipeline/storyboard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          book_id: book.id,
          genre,
          generation_mode: 'director_llm',
          episodes: buildEpisodeSequence(episodeCount),
        }),
      })
      const data = await res.json()
      if (data.task_id) {
        const poll = async () => {
          try {
            const pr = await fetch(`/api/pipeline/storyboard/task/${data.task_id}`)
            const pd = await pr.json()
            if (pd.status === 'running') {
              setTimeout(poll, 3000)
            } else if (pd.status === 'done' || pd.status === 'partial') {
              setIsGeneratingStoryboard(false)
              handleRefreshAll()
            } else {
              setIsGeneratingStoryboard(false)
              console.error('Storyboard generation failed:', pd.error)
            }
          } catch {
            setIsGeneratingStoryboard(false)
          }
        }
        poll()
      } else {
        setIsGeneratingStoryboard(false)
      }
    } catch {
      setIsGeneratingStoryboard(false)
    }
  }, [book.id, episodeCount, isGeneratingStoryboard, handleRefreshAll])

  const characterAssets = useMemo(
    () => buildCharacterAssetSummaries(makeups),
    [makeups],
  )
  const locationAssets = useMemo(
    () => buildLocationAssetSummaries(locations),
    [locations],
  )
  const propAssets = useMemo(
    () => buildPropAssetSummaries(props),
    [props],
  )
  const allAssets = useMemo(
    () => [...characterAssets, ...locationAssets, ...propAssets],
    [characterAssets, locationAssets, propAssets],
  )

  const {
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
    linkedShotDraft,
    toggleShotBinding,
    applyInferredShotBindings,
    shotBindingState,
    setShotBindingState,
    assetEpisodeInsights,
    prioritizedAssets,
    selectedAsset,
    navigateTaskSection,
    navigateAssetShot,
    setSelectedAssetId,
    clearNavigationContext,
  } = useProductWorkspaceAssetView({
    allAssets,
    episodeShots: shotsByEpisode,
    setSection,
    setSelectedStoryboardShotId,
    setCanvasNavigationTarget,
    setTaskNavigationTarget,
    setCanvasHandoffTarget,
    setQaNavigationTarget,
  })

  const {
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
  } = useProductWorkspaceOverview({
    book,
    bookData,
    data,
    contentTaskStatus: contentTask.status,
    selectedAdaptationId,
    selectedAdaptation,
    adaptationLockedAt,
  })

  const handleSelectSection = useCallback((nextSection: WorkspaceSection) => {
    setCanvasNavigationTarget(null)
    setTaskNavigationTarget(null)
    setQaNavigationTarget(null)
    setCanvasHandoffTarget(null)
    clearNavigationContext()
    setSection(nextSection)
  }, [clearNavigationContext])

  useEffect(() => {
    const handleAgentNavigation = (event: Event) => {
      const detail = (event as CustomEvent<Record<string, unknown>>).detail
      if (!detail || typeof detail !== 'object') return
      const target = String(detail.section || '').trim() as WorkspaceSection
      const allowed: WorkspaceSection[] = ['dashboard', 'content', 'adaptation', 'scripts', 'storyboard', 'canvas', 'assets', 'qa', 'tasks', 'delivery', 'models']
      if (!allowed.includes(target)) return
      navigateTaskSection(target, {
        episode: Number(detail.episode || 0) || null,
        shotId: detail.shot_id == null ? null : String(detail.shot_id),
        assetId: detail.asset_id == null ? null : String(detail.asset_id),
        navigationSource: 'tasks',
        handoffLabel: typeof detail.label === 'string' ? detail.label : null,
        handoffDetail: typeof detail.guard === 'string' ? detail.guard : null,
      })
    }
    window.addEventListener('smart-director:navigate', handleAgentNavigation)
    return () => window.removeEventListener('smart-director:navigate', handleAgentNavigation)
  }, [navigateTaskSection])

  useEffect(() => {
    writeProductWorkspaceNavigationState(
      book.id,
      section === 'canvas' && canvasNavigationTarget
        ? {
            section: 'canvas',
            canvasNavigationTarget,
          }
        : null,
    )
  }, [book.id, canvasNavigationTarget, section])

  const buildAssetReferenceToken = (title: string) => {
    const normalized = title
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9\u4e00-\u9fa5]+/gi, '-')
      .replace(/^-+|-+$/g, '')
    return `${normalized || 'asset'}-${Date.now().toString(36)}`
  }

  const applyAssetReferenceOutcomeFollowUp = (outcome: GenerateReferenceOutcome) => {
    if (outcome.status === 'pending') {
      setAssetActionFollowUp({
        mode: 'tasks',
        label: '去任务中心继续回收',
        taskId: outcome.taskId,
        episode: outcome.episode,
        shotId: outcome.shotId,
        assetId: outcome.assetId,
      })
      return
    }

    if (outcome.status === 'done') {
      setAssetActionFollowUp({
        mode: 'storyboard',
        label: '回镜头工作台继续出图',
        taskId: outcome.taskId,
        episode: outcome.episode,
        shotId: outcome.shotId,
        assetId: outcome.assetId,
      })
      return
    }

    setAssetActionFollowUp(null)
  }

  const handleGenerateSelectedAssetReference = async () => {
    setAssetActionFollowUp(null)
    const inferredShotIds =
      selectedAsset
        ? (assetEpisodeInsights.get(selectedAsset.id)?.impactShots ?? []).map((item) =>
            item.episode ? `${item.episode}-${item.shotId}` : String(item.shotId),
          )
        : []
    const outcome = await runGenerateSelectedAssetReference({
      bookId: book.id,
      assetEpisodeFilter,
      selectedAsset,
      buildAssetReferenceToken,
      toVisualAssetType,
      inferredShotIds,
      setAssetActionTone,
      setAssetActionMessage,
      setAssetGenerationState,
      setShotBindingState,
      closeAssetPreview,
      refreshAll: handleRefreshAll,
    })
    applyAssetReferenceOutcomeFollowUp(outcome)
  }

  const handleGenerateAssetReference = async (assetId: string) => {
    const targetAsset = allAssets.find((asset) => asset.id === assetId) ?? null
    if (!targetAsset) return
    setSelectedAssetId(assetId)
    setAssetActionFollowUp(null)
    const inferredShotIds = (assetEpisodeInsights.get(targetAsset.id)?.impactShots ?? []).map((item) =>
      item.episode ? `${item.episode}-${item.shotId}` : String(item.shotId),
    )
    const outcome = await runGenerateSelectedAssetReference({
      bookId: book.id,
      assetEpisodeFilter,
      selectedAsset: targetAsset,
      buildAssetReferenceToken,
      toVisualAssetType,
      inferredShotIds,
      setAssetActionTone,
      setAssetActionMessage,
      setAssetGenerationState,
      setShotBindingState,
      closeAssetPreview,
      refreshAll: handleRefreshAll,
    })
    applyAssetReferenceOutcomeFollowUp(outcome)
  }

  const handleDeleteReferenceAsset = async (referenceId: number) => {
    await runDeleteReferenceAsset({
      bookId: book.id,
      referenceId,
      selectedAsset,
      assetPreviewUrl,
      setAssetActionTone,
      setAssetActionMessage,
      setAssetGenerationState,
      setShotBindingState,
      closeAssetPreview,
      refreshAll: handleRefreshAll,
    })
  }

  const handleUpdateReferenceAssetStatus = async (
    referenceId: number,
    nextStatus: 'candidate' | 'selected' | 'locked',
  ) => {
    await runUpdateReferenceAssetStatus({
      bookId: book.id,
      referenceId,
      nextStatus,
      setAssetActionTone,
      setAssetActionMessage,
      setAssetGenerationState,
      setShotBindingState,
      closeAssetPreview,
      refreshAll: handleRefreshAll,
    })
  }

  const handleSaveAssetShotBindings = async () => {
    await runSaveAssetShotBindings({
      bookId: book.id,
      selectedAsset,
      linkedShotDraft,
      toVisualAssetType,
      setAssetActionTone,
      setAssetActionMessage,
      setAssetGenerationState,
      setShotBindingState,
      closeAssetPreview,
      refreshAll: handleRefreshAll,
    })
  }

  const sectionBundles = useProductWorkspaceSectionBundles({
    section,
    loading,
    bookTitle: book.title,
    chapterCount: bookData?.chapters ?? 0,
    wordCount: bookData?.words ?? 0,
    summary,
    adaptationSummary,
    dashboardActions,
    episodeProgress,
    bookId: book.id,
    contentTask,
    uploadFile,
    setUploadFile,
    episodeCount,
    setEpisodeCount,
    shortTitle,
    setShortTitle,
    shortText,
    setShortText,
    onOpenModelSettings: () => {
      handleSelectSection('models')
    },
    onSubmitNovelUpload: () => {
      void handleNovelUpload()
    },
    onSubmitShortCreate: () => {
      void handleShortCreate()
    },
    adaptationOptions,
    selectedAdaptationId,
    selectedAdaptationName: selectedAdaptation?.name,
    setSelectedAdaptationId,
    adaptationCustomNote,
    adaptationLockedAt,
    setAdaptationCustomNote,
    hasLockedAdaptation: hasLockedAdaptation || legacyAdaptationReady,
    adaptationSectionState: {
      selectedAdaptationId,
      selectedAdaptationName: selectedAdaptation?.name,
      adaptationCustomNote,
      hasLockedAdaptation,
      adaptationStateLabel: adaptationSummary.label,
      adaptationStateDetail: adaptationSummary.detail,
      canGenerateCandidates: adaptationSummary.canGenerateCandidates,
      canLockAdaptation: adaptationSummary.canLock && Boolean(productionSkillSectionState.lockedAt),
      productionSkill: productionSkillSectionState,
      canLockProductionSkill: summary.contentReady && Boolean(productionSkillSectionState.selectedSkillId),
    },
    productionSkillSectionState,
    canLockProductionSkill: summary.contentReady && Boolean(productionSkillSectionState.selectedSkillId),
    onSelectProductionSkill: setSelectedProductionSkillId,
    onProductionSkillFieldChange: updateProductionSkillField,
    onToggleProductionSkillPriority: toggleProductionSkillPriority,
    onLockProductionSkill: lockProductionSkill,
    onUnlockProductionSkill: unlockProductionSkill,
    onRegenerateAdaptation: regenerateAdaptationOptions,
    onLockAdaptation: lockSelectedAdaptation,
    onUnlockAdaptation: unlockAdaptation,
    scripts,
    shotsByEpisode,
    scriptDecisionState,
    setScriptDecisionState,
    selectedStoryboardShotId,
    setSelectedStoryboardShotId,
    recoveryFocus,
    onRefreshAll: handleRefreshAll,
    onDismissStoryboardRecoveryFocus: dismissStoryboardRecoveryFocus,
    onGenerateScripts: handleGenerateScripts,
    isGeneratingScripts,
    onGenerateStoryboard: handleGenerateStoryboard,
    isGeneratingStoryboard,
    allAssetsCount: allAssets.length,
    shotEpisodes,
    assetEpisodeFilter,
    assetCategoryFilter,
    assetStatusFilter,
    assetVersionFilter,
    assetSearchQuery,
    assetCategoryCounts,
    assetStatusCounts,
    assetVersionCounts,
    setAssetEpisodeFilter,
    setAssetCategoryFilter,
    setAssetStatusFilter,
    setAssetVersionFilter,
    setAssetSearchQuery,
    prioritizedAssets,
    selectedAsset,
    allAssets,
    assetEpisodeInsights,
    assetActionMessage,
    assetActionTone,
    assetActionFollowUp,
    linkedShotDraft,
    shotBindingState,
    isGeneratingReference: assetGenerationState === 'saving',
    onDismissAssetsRecoveryFocus: dismissAssetsRecoveryFocus,
    setSelectedAssetId,
    onOpenAssetPreview: openAssetPreview,
    onGenerateReference: () => {
      void handleGenerateSelectedAssetReference()
    },
    onGenerateAssetReference: (assetId) => {
      void handleGenerateAssetReference(assetId)
    },
    onDeleteReferenceAsset: (referenceId) => {
      void handleDeleteReferenceAsset(referenceId)
    },
    onUpdateReferenceAssetStatus: (referenceId, nextStatus) => {
      void handleUpdateReferenceAssetStatus(referenceId, nextStatus)
    },
    onNavigateAssetShot: navigateAssetShot,
    onToggleShotBinding: toggleShotBinding,
    onApplyInferredShotBindings: applyInferredShotBindings,
    onSaveShotBindings: () => {
      void handleSaveAssetShotBindings()
    },
    qaEntries,
    canvasNavigationTarget,
    canvasHandoffTarget,
    taskNavigationTarget,
    qaNavigationTarget,
    onNavigateSection: handleSelectSection,
    onNavigateTaskSection: navigateTaskSection,
    makeups,
    locations,
    props,
    assetPreviewUrl,
    assetPreviewLabel,
    onCloseAssetPreview: closeAssetPreview,
  })

  return (
    <ProductWorkspaceShell
      bookTitle={book.title}
      projectStatus={summary.projectStatus}
      section={section}
      sections={sections}
      loading={loading}
      error={error}
      onSelectSection={handleSelectSection}
      getSectionBlockedReason={getSectionBlockedReason}
      onRefreshAll={handleRefreshAll}
    >
      <ProductWorkspaceSectionContent {...sectionBundles} />
    </ProductWorkspaceShell>
  )
}
