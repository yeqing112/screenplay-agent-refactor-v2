import type {
  ScriptOutput,
  StoryboardShotOutput,
  VisualLocationOutput,
  VisualMakeupOutput,
  VisualPropOutput,
} from '../domain/bookOutputs'
import { useMemo } from 'react'
import type {
  AdaptationSectionState,
  CanvasHandoffTarget,
  TaskNavigationTarget,
  ContentTaskState,
  SummaryState,
  TaskNavigateHandler,
} from './productWorkspaceSectionContracts'
import type { Dispatch, SetStateAction } from 'react'
import type { AssetEpisodeInsight, AssetSummary } from './productWorkspaceAssets'
import type { AssetCategoryFilter, AssetStatusFilter, AssetVersionFilter, RecoveryFocusContext, WorkspaceSection } from './productWorkspaceAssetViewController'
import type { DashboardAction, EpisodeProgress } from './productWorkspaceProgress'
import type { ScriptDecisionMap } from './productWorkspaceScriptDecisions'

interface UseProductWorkspaceSectionBundlesParams {
  section: WorkspaceSection
  loading: boolean
  bookTitle: string
  chapterCount: number
  wordCount: number
  summary: SummaryState
  adaptationSummary: {
    label: string
    detail: string
    canGenerateCandidates: boolean
    canLock: boolean
  }
  dashboardActions: DashboardAction[]
  episodeProgress: EpisodeProgress[]
  bookId: number
  contentTask: ContentTaskState
  uploadFile: File | null
  setUploadFile: (file: File | null) => void
  episodeCount: number
  setEpisodeCount: (value: number) => void
  shortTitle: string
  setShortTitle: (value: string) => void
  shortText: string
  setShortText: (value: string) => void
  onOpenModelSettings: () => void
  onSubmitNovelUpload: () => void
  onSubmitShortCreate: () => void
  adaptationOptions: any[]
  selectedAdaptationId: string | null
  selectedAdaptationName?: string
  setSelectedAdaptationId: (value: string | null) => void
  adaptationCustomNote: string
  adaptationLockedAt: string | null
  setAdaptationCustomNote: (value: string) => void
  hasLockedAdaptation: boolean
  adaptationSectionState: AdaptationSectionState
  productionSkillSectionState: import('./productWorkspaceSectionContracts').ProductionSkillSectionState
  canLockProductionSkill: boolean
  onSelectProductionSkill: (value: string | null) => void
  onProductionSkillFieldChange: (field: 'platform' | 'track' | 'emotionGoal' | 'rhythmStrength' | 'visualStyle' | 'enforcement' | 'customNote', value: string) => void
  onToggleProductionSkillPriority: (value: string) => void
  onLockProductionSkill: () => void
  onUnlockProductionSkill: () => void
  onRegenerateAdaptation: () => void
  onLockAdaptation: () => void
  onUnlockAdaptation: () => void
  scripts: ScriptOutput[]
  shotsByEpisode: Record<number, StoryboardShotOutput[]>
  scriptDecisionState: ScriptDecisionMap
  setScriptDecisionState: Dispatch<SetStateAction<ScriptDecisionMap>>
  selectedStoryboardShotId: string | null
  setSelectedStoryboardShotId: (shotId: string | null) => void
  recoveryFocus: RecoveryFocusContext | null
  onRefreshAll: () => void
  onDismissStoryboardRecoveryFocus: () => void
  onGenerateScripts: () => void
  isGeneratingScripts: boolean
  onGenerateStoryboard: () => void
  isGeneratingStoryboard: boolean
  allAssetsCount: number
  shotEpisodes: Array<{ episode: number; shots: StoryboardShotOutput[] }>
  assetEpisodeFilter: 'all' | number
  assetCategoryFilter: AssetCategoryFilter
  assetStatusFilter: AssetStatusFilter
  assetVersionFilter: AssetVersionFilter
  assetSearchQuery: string
  assetCategoryCounts: Record<AssetCategoryFilter, number>
  assetStatusCounts: Record<AssetStatusFilter, number>
  assetVersionCounts: Record<AssetVersionFilter, number>
  setAssetEpisodeFilter: (value: 'all' | number) => void
  setAssetCategoryFilter: (value: AssetCategoryFilter) => void
  setAssetStatusFilter: (value: AssetStatusFilter) => void
  setAssetVersionFilter: (value: AssetVersionFilter) => void
  setAssetSearchQuery: (value: string) => void
  prioritizedAssets: AssetSummary[]
  selectedAsset: AssetSummary | null
  allAssets: AssetSummary[]
  assetEpisodeInsights: Map<string, AssetEpisodeInsight>
  assetActionMessage: string
  assetActionTone: 'info' | 'error'
  assetActionFollowUp: {
    mode: 'tasks' | 'storyboard'
    label: string
    taskId?: string
    episode?: number | null
    shotId?: string | null
    assetId?: string | null
  } | null
  linkedShotDraft: string[]
  shotBindingState: 'idle' | 'saving' | 'saved' | 'error'
  isGeneratingReference: boolean
  onDismissAssetsRecoveryFocus: () => void
  setSelectedAssetId: (value: string | null) => void
  onOpenAssetPreview: (url: string, label: string) => void
  onGenerateReference: () => void
  onGenerateAssetReference: (assetId: string) => void
  onDeleteReferenceAsset: (referenceId: number) => void
  onUpdateReferenceAssetStatus: (referenceId: number, nextStatus: 'candidate' | 'selected' | 'locked') => void
  onNavigateAssetShot: (shotId: string) => void
  onToggleShotBinding: (shotId: string) => void
  onApplyInferredShotBindings: () => void
  onSaveShotBindings: () => void
  qaEntries: Array<{ id?: number; episode: number; result: unknown; error_count?: number }>
  canvasNavigationTarget: import('./productWorkspaceSectionContracts').CanvasNavigationTarget | null
  canvasHandoffTarget: CanvasHandoffTarget | null
  taskNavigationTarget: TaskNavigationTarget | null
  qaNavigationTarget: { episode: number | null; shotId: string | null } | null
  onNavigateSection: (section: WorkspaceSection) => void
  onNavigateTaskSection: TaskNavigateHandler
  makeups: VisualMakeupOutput[]
  locations: VisualLocationOutput[]
  props: VisualPropOutput[]
  assetPreviewUrl: string | null
  assetPreviewLabel: string
  onCloseAssetPreview: () => void
}

export function useProductWorkspaceSectionBundles(params: UseProductWorkspaceSectionBundlesParams) {
  const adaptationSectionState =
    params.adaptationSectionState ??
    ({
      selectedAdaptationId: params.selectedAdaptationId,
      selectedAdaptationName: params.selectedAdaptationName,
      adaptationCustomNote: params.adaptationCustomNote,
      hasLockedAdaptation: params.hasLockedAdaptation,
      adaptationStateLabel: params.adaptationSummary.label,
      adaptationStateDetail: params.adaptationSummary.detail,
      canGenerateCandidates: params.adaptationSummary.canGenerateCandidates,
      canLockAdaptation: params.adaptationSummary.canLock,
      productionSkill: params.productionSkillSectionState,
      canLockProductionSkill: params.canLockProductionSkill,
    } satisfies AdaptationSectionState)

  return useMemo(
    () => ({
      section: params.section,
      dashboard: {
        summary: params.summary,
        adaptationStateLabel: params.adaptationSummary.label,
        adaptationStateDetail: params.adaptationSummary.detail,
        dashboardActions: params.dashboardActions,
        episodeProgress: params.episodeProgress,
        onNavigateSection: params.onNavigateSection,
      },
      content: {
        bookId: params.bookId,
        summary: params.summary,
        contentTask: params.contentTask,
        uploadFile: params.uploadFile,
        episodeCount: params.episodeCount,
        shortTitle: params.shortTitle,
        shortText: params.shortText,
        productionSkill: params.productionSkillSectionState,
        onOpenModelSettings: params.onOpenModelSettings,
        onUploadFileChange: params.setUploadFile,
        onEpisodeCountChange: params.setEpisodeCount,
        onShortTitleChange: params.setShortTitle,
        onShortTextChange: params.setShortText,
        onSubmitNovelUpload: params.onSubmitNovelUpload,
        onSubmitShortCreate: params.onSubmitShortCreate,
      },
      adaptation: {
        contentReady: params.summary.contentReady,
        productionSkill: params.productionSkillSectionState,
        adaptationOptions: params.adaptationOptions,
        selectedAdaptationId: adaptationSectionState.selectedAdaptationId,
        selectedAdaptationName: adaptationSectionState.selectedAdaptationName,
        adaptationCustomNote: adaptationSectionState.adaptationCustomNote,
        hasLockedAdaptation: adaptationSectionState.hasLockedAdaptation,
        adaptationStateLabel: adaptationSectionState.adaptationStateLabel,
        adaptationStateDetail: adaptationSectionState.adaptationStateDetail,
        canGenerateCandidates: adaptationSectionState.canGenerateCandidates,
        canLockAdaptation: adaptationSectionState.canLockAdaptation,
        canLockProductionSkill: params.canLockProductionSkill,
        onSelectProductionSkill: params.onSelectProductionSkill,
        onProductionSkillFieldChange: params.onProductionSkillFieldChange,
        onToggleProductionSkillPriority: params.onToggleProductionSkillPriority,
        onLockProductionSkill: params.onLockProductionSkill,
        onUnlockProductionSkill: params.onUnlockProductionSkill,
        onRegenerateAdaptation: params.onRegenerateAdaptation,
        onSelectAdaptation: params.setSelectedAdaptationId,
        onAdaptationCustomNoteChange: params.setAdaptationCustomNote,
        onLockAdaptation: params.onLockAdaptation,
        onUnlockAdaptation: params.onUnlockAdaptation,
        onNavigateSection: params.onNavigateSection,
      },
      scripts: {
        bookId: params.bookId,
        scripts: params.scripts,
        shotsByEpisode: params.shotsByEpisode,
        episodeProgress: params.episodeProgress,
        scriptDecisionState: params.scriptDecisionState,
        onScriptDecisionStateChange: params.setScriptDecisionState,
        hasLockedAdaptation: params.hasLockedAdaptation,
        hasExplicitLockedAdaptation: adaptationSectionState.hasLockedAdaptation,
        adaptationStateLabel: adaptationSectionState.adaptationStateLabel,
        adaptationStateDetail: adaptationSectionState.adaptationStateDetail,
        selectedAdaptationName: adaptationSectionState.selectedAdaptationName,
        onNavigateTaskSection: params.onNavigateTaskSection,
        onGenerateScripts: params.onGenerateScripts,
        isGeneratingScripts: params.isGeneratingScripts,
      },
      storyboard: {
        bookId: params.bookId,
        shotsByEpisode: params.shotsByEpisode,
        scriptDecisionState: params.scriptDecisionState,
        hasExplicitLockedAdaptation: adaptationSectionState.hasLockedAdaptation,
        selectedStoryboardShotId: params.selectedStoryboardShotId,
        recoveryFocus: params.recoveryFocus,
        canvasHandoff: params.canvasHandoffTarget?.target === 'storyboard' ? params.canvasHandoffTarget : null,
        onSelectShot: params.setSelectedStoryboardShotId,
        onRefreshAll: params.onRefreshAll,
        onDismissStoryboardRecoveryFocus: params.onDismissStoryboardRecoveryFocus,
        onNavigateSection: params.onNavigateSection,
        onNavigateTaskSection: params.onNavigateTaskSection,
        onGenerateStoryboard: params.onGenerateStoryboard,
        isGeneratingStoryboard: params.isGeneratingStoryboard,
      },
      canvas: {
        bookId: params.bookId,
        bookTitle: params.bookTitle,
        isProjectDataLoading: params.loading,
        scripts: params.scripts,
        shotsByEpisode: params.shotsByEpisode,
        allAssets: params.allAssets,
        qaEntries: params.qaEntries,
        navigationTarget: params.canvasNavigationTarget,
        onRefreshAll: params.onRefreshAll,
        onNavigateTaskSection: params.onNavigateTaskSection,
      },
      assets: {
        bookId: params.bookId,
        allAssetsCount: params.allAssetsCount,
        shotEpisodes: params.shotEpisodes,
        assetEpisodeFilter: params.assetEpisodeFilter,
        assetCategoryFilter: params.assetCategoryFilter,
        assetStatusFilter: params.assetStatusFilter,
        assetVersionFilter: params.assetVersionFilter,
        assetSearchQuery: params.assetSearchQuery,
        assetCategoryCounts: params.assetCategoryCounts,
        assetStatusCounts: params.assetStatusCounts,
        assetVersionCounts: params.assetVersionCounts,
        prioritizedAssets: params.prioritizedAssets,
        selectedAsset: params.selectedAsset,
        assetEpisodeInsights: params.assetEpisodeInsights,
        assetActionMessage: params.assetActionMessage,
        assetActionTone: params.assetActionTone,
        assetActionFollowUp: params.assetActionFollowUp,
        linkedShotDraft: params.linkedShotDraft,
        shotBindingState: params.shotBindingState,
        isGeneratingReference: params.isGeneratingReference,
        recoveryFocus: params.recoveryFocus,
        canvasHandoff: params.canvasHandoffTarget?.target === 'assets' ? params.canvasHandoffTarget : null,
        onDismissAssetsRecoveryFocus: params.onDismissAssetsRecoveryFocus,
        onAssetEpisodeFilterChange: params.setAssetEpisodeFilter,
        onAssetCategoryFilterChange: params.setAssetCategoryFilter,
        onAssetStatusFilterChange: params.setAssetStatusFilter,
        onAssetVersionFilterChange: params.setAssetVersionFilter,
        onAssetSearchQueryChange: params.setAssetSearchQuery,
        onSelectAsset: params.setSelectedAssetId,
        onOpenAssetPreview: params.onOpenAssetPreview,
        onGenerateReference: params.onGenerateReference,
        onGenerateAssetReference: params.onGenerateAssetReference,
        onDeleteReferenceAsset: params.onDeleteReferenceAsset,
        onUpdateReferenceAssetStatus: params.onUpdateReferenceAssetStatus,
        onRefreshAll: params.onRefreshAll,
        onNavigateSection: params.onNavigateSection,
        onNavigateTaskSection: params.onNavigateTaskSection,
        onNavigateAssetShot: params.onNavigateAssetShot,
        onToggleShotBinding: params.onToggleShotBinding,
        onApplyInferredShotBindings: params.onApplyInferredShotBindings,
        onSaveShotBindings: params.onSaveShotBindings,
      },
      qa: {
        bookId: params.bookId,
        scripts: params.scripts,
        scriptDecisionState: params.scriptDecisionState,
        hasExplicitLockedAdaptation: adaptationSectionState.hasLockedAdaptation,
        qaEntries: params.qaEntries,
        shotsByEpisode: params.shotsByEpisode,
        qaNavigationTarget: params.qaNavigationTarget,
        canvasHandoff: params.canvasHandoffTarget?.target === 'qa' ? params.canvasHandoffTarget : null,
        onNavigateSection: params.onNavigateSection,
        onSelectShot: params.setSelectedStoryboardShotId,
      },
      tasks: {
        bookId: params.bookId,
        contentReady: params.summary.contentReady,
        adaptationLocked: adaptationSectionState.hasLockedAdaptation,
        adaptationReadyForDownstream: params.hasLockedAdaptation,
        contentTask: params.contentTask,
        scripts: params.scripts,
        scriptDecisionState: params.scriptDecisionState,
        shotsByEpisode: params.shotsByEpisode,
        qaEntries: params.qaEntries,
        taskNavigationTarget: params.taskNavigationTarget,
        onRefreshAll: params.onRefreshAll,
        onNavigateTaskSection: params.onNavigateTaskSection,
      },
      delivery: {
        bookId: params.bookId,
        isProjectDataLoading: params.loading,
        bookTitle: params.bookTitle,
        chapterCount: params.chapterCount,
        wordCount: params.wordCount,
        contentStatusLabel: params.summary.contentSummary.label,
        contentStatusDetail: params.summary.contentSummary.detail,
        adaptationStateLabel: adaptationSectionState.adaptationStateLabel,
        adaptationStateDetail: adaptationSectionState.adaptationStateDetail,
        selectedAdaptationName: adaptationSectionState.selectedAdaptationName,
        adaptationCustomNote: adaptationSectionState.adaptationCustomNote,
        adaptationLockedAt: params.adaptationLockedAt,
        scripts: params.scripts,
        scriptDecisionState: params.scriptDecisionState,
        shotsByEpisode: params.shotsByEpisode,
        qaEntries: params.qaEntries,
        makeups: params.makeups,
        locations: params.locations,
        props: params.props,
        canvasHandoff: params.canvasHandoffTarget?.target === 'delivery' ? params.canvasHandoffTarget : null,
        onNavigateTaskSection: params.onNavigateTaskSection,
      },
      preview: {
        assetPreviewUrl: params.assetPreviewUrl,
        assetPreviewLabel: params.assetPreviewLabel,
        onCloseAssetPreview: params.onCloseAssetPreview,
      },
    }),
    [params],
  )
}
