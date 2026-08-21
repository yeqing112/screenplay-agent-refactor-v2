import type { Dispatch, SetStateAction } from 'react'
import type {
  ScriptOutput,
  StoryboardShotOutput,
  VisualLocationOutput,
  VisualMakeupOutput,
  VisualPropOutput,
} from '../domain/bookOutputs'
import type { AssetEpisodeInsight, AssetSummary } from './productWorkspaceAssets'
import type {
  AssetCategoryFilter,
  AssetStatusFilter,
  AssetVersionFilter,
  RecoveryFocusContext,
  WorkspaceSection,
} from './productWorkspaceAssetViewController'
import type { DashboardAction, EpisodeProgress } from './productWorkspaceProgress'
import type { ScriptDecisionMap } from './productWorkspaceScriptDecisions'

export type ContentTaskState = {
  mode: 'upload' | 'short'
  status: 'idle' | 'uploading' | 'running' | 'done' | 'error'
  message: string
  taskId?: string
}

export interface ProductionSkillRuntimeSummary {
  skill_name: string
  track: string
  platform: string
  emotion_goal: string
  rhythm_strength: string
  visual_style: string
  priorities: string[]
  enforcement: string
  locked: boolean
  custom_note: string
}

export interface ProductionSkillOption {
  id: string
  name: string
  summary: string
  tracks: string[]
  platforms: string[]
}

export interface ProductionSkillSectionState {
  skillOptions: ProductionSkillOption[]
  selectedSkillId: string | null
  platform: string
  track: string
  emotionGoal: string
  rhythmStrength: string
  visualStyle: string
  priorities: string[]
  enforcement: string
  customNote: string
  lockedAt: string | null
  runtimeSummary: ProductionSkillRuntimeSummary | null
}

export type SummaryState = {
  contentReady: boolean
  chapterCount: number
  wordCount: number
  projectStatus: string
  episodesWithScripts: number
  totalShots: number
  visualCount: number
  qaCount: number
  contentSummary: {
    label: string
    detail: string
  }
}

export type WorkspaceTaskRouteSection =
  | 'content'
  | 'adaptation'
  | 'scripts'
  | 'storyboard'
  | 'canvas'
  | 'assets'
  | 'qa'
  | 'tasks'
  | 'delivery'

export interface WorkspaceTaskRouteOptions {
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
}

export interface CanvasNavigationTarget {
  episode?: number | null
  shotId?: string | null
  assetId?: string | null
  assetLabel?: string | null
  taskId?: string | null
  recoveryKind?: 'frame' | 'video' | 'reference' | 'prompt' | null
  recoveryIntent?: 'reference' | 'shot_variant_refinement' | null
}

export interface TaskNavigationTarget {
  episode?: number | null
  shotId?: string | null
  assetId?: string | null
  assetLabel?: string | null
  taskId?: string | null
  recoveryKind?: 'frame' | 'video' | 'reference' | 'prompt' | null
  recoveryIntent?: 'reference' | 'shot_variant_refinement' | null
}

export interface CanvasHandoffTarget {
  target: 'storyboard' | 'assets' | 'qa' | 'delivery'
  episode?: number | null
  shotId?: string | null
  assetId?: string | null
  assetLabel?: string | null
  taskId?: string | null
  recoveryKind?: 'frame' | 'video' | 'reference' | 'prompt' | null
  recoveryIntent?: 'reference' | 'shot_variant_refinement' | null
  qaFocus?: 'delivery_recovery' | null
  handoffLabel?: string | null
  handoffDetail?: string | null
}

export type TaskNavigateHandler = (
  section: WorkspaceTaskRouteSection,
  options?: WorkspaceTaskRouteOptions,
) => void

export interface DashboardBundle {
  summary: SummaryState
  adaptationStateLabel: string
  adaptationStateDetail: string
  dashboardActions: DashboardAction[]
  episodeProgress: EpisodeProgress[]
  onNavigateSection: (section: WorkspaceSection) => void
}

export interface ContentBundle {
  bookId: number
  summary: SummaryState
  contentTask: ContentTaskState
  uploadFile: File | null
  episodeCount: number
  shortTitle: string
  shortText: string
  productionSkill: ProductionSkillSectionState
  onOpenModelSettings: () => void
  onUploadFileChange: (file: File | null) => void
  onEpisodeCountChange: (value: number) => void
  onShortTitleChange: (value: string) => void
  onShortTextChange: (value: string) => void
  onSubmitNovelUpload: () => void
  onSubmitShortCreate: () => void
}

export interface AdaptationBundle {
  contentReady: boolean
  productionSkill: ProductionSkillSectionState
  adaptationOptions: any[]
  selectedAdaptationId: string | null
  selectedAdaptationName?: string
  adaptationCustomNote: string
  hasLockedAdaptation: boolean
  adaptationStateLabel: string
  adaptationStateDetail: string
  canGenerateCandidates: boolean
  canLockAdaptation: boolean
  canLockProductionSkill: boolean
  onSelectProductionSkill: (value: string | null) => void
  onProductionSkillFieldChange: (field: 'platform' | 'track' | 'emotionGoal' | 'rhythmStrength' | 'visualStyle' | 'enforcement' | 'customNote', value: string) => void
  onToggleProductionSkillPriority: (value: string) => void
  onLockProductionSkill: () => void
  onUnlockProductionSkill: () => void
  onRegenerateAdaptation: () => void
  onSelectAdaptation: (value: string | null) => void
  onAdaptationCustomNoteChange: (value: string) => void
  onLockAdaptation: () => void
  onUnlockAdaptation: () => void
  onNavigateSection: (section: WorkspaceSection) => void
}

export interface ScriptsBundle {
  bookId: number
  scripts: ScriptOutput[]
  shotsByEpisode: Record<number, StoryboardShotOutput[]>
  episodeProgress: EpisodeProgress[]
  scriptDecisionState: ScriptDecisionMap
  onScriptDecisionStateChange: Dispatch<SetStateAction<ScriptDecisionMap>>
  hasLockedAdaptation: boolean
  hasExplicitLockedAdaptation: boolean
  adaptationStateLabel: string
  adaptationStateDetail: string
  selectedAdaptationName?: string
  onNavigateTaskSection: TaskNavigateHandler
  onGenerateScripts: () => void
  isGeneratingScripts: boolean
}

export interface StoryboardBundle {
  bookId: number
  shotsByEpisode: Record<number, StoryboardShotOutput[]>
  scriptDecisionState: ScriptDecisionMap
  hasExplicitLockedAdaptation: boolean
  selectedStoryboardShotId: string | null
  recoveryFocus: RecoveryFocusContext | null
  canvasHandoff: CanvasHandoffTarget | null
  onSelectShot: (shotId: string | null) => void
  onRefreshAll: () => void
  onDismissStoryboardRecoveryFocus: () => void
  onNavigateSection: (section: WorkspaceSection) => void
  onNavigateTaskSection: TaskNavigateHandler
  onGenerateStoryboard: () => void
  isGeneratingStoryboard: boolean
}

export interface AssetsBundle {
  bookId: number
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
  prioritizedAssets: AssetSummary[]
  selectedAsset: AssetSummary | null
  assetEpisodeInsights: Map<string, AssetEpisodeInsight>
  assetActionMessage: string
  assetActionTone: 'info' | 'error'
  assetActionFollowUp:
    | {
        mode: 'tasks' | 'storyboard'
        label: string
        taskId?: string
        episode?: number | null
        shotId?: string | null
        assetId?: string | null
      }
    | null
  linkedShotDraft: string[]
  shotBindingState: 'idle' | 'saving' | 'saved' | 'error'
  isGeneratingReference: boolean
  recoveryFocus: RecoveryFocusContext | null
  canvasHandoff: CanvasHandoffTarget | null
  onDismissAssetsRecoveryFocus: () => void
  onAssetEpisodeFilterChange: (value: 'all' | number) => void
  onAssetCategoryFilterChange: (value: AssetCategoryFilter) => void
  onAssetStatusFilterChange: (value: AssetStatusFilter) => void
  onAssetVersionFilterChange: (value: AssetVersionFilter) => void
  onAssetSearchQueryChange: (value: string) => void
  onSelectAsset: (value: string | null) => void
  onOpenAssetPreview: (url: string, label: string) => void
  onGenerateReference: () => void
  onGenerateAssetReference: (assetId: string) => void
  onDeleteReferenceAsset: (referenceId: number) => void
  onUpdateReferenceAssetStatus: (referenceId: number, nextStatus: 'candidate' | 'selected' | 'locked') => void
  onNavigateSection: (section: WorkspaceSection) => void
  onNavigateTaskSection: TaskNavigateHandler
  onNavigateAssetShot: (shotId: string) => void
  onToggleShotBinding: (shotId: string) => void
  onApplyInferredShotBindings: () => void
  onSaveShotBindings: () => void
}

export interface CanvasBundle {
  bookId: number
  bookTitle: string
  isProjectDataLoading: boolean
  scripts: ScriptOutput[]
  shotsByEpisode: Record<number, StoryboardShotOutput[]>
  allAssets: AssetSummary[]
  qaEntries: Array<{ id?: number; episode: number; result: unknown; error_count?: number }>
  navigationTarget: CanvasNavigationTarget | null
  onRefreshAll: () => void
  onNavigateTaskSection: TaskNavigateHandler
}

export interface QaBundle {
  bookId: number
  scripts: ScriptOutput[]
  scriptDecisionState: ScriptDecisionMap
  hasExplicitLockedAdaptation: boolean
  qaEntries: Array<{ id?: number; episode: number; result: unknown; error_count?: number }>
  shotsByEpisode: Record<number, StoryboardShotOutput[]>
  qaNavigationTarget: { episode: number | null; shotId: string | null; qaFocus?: 'delivery_recovery' | null } | null
  canvasHandoff: CanvasHandoffTarget | null
  onNavigateSection: (section: WorkspaceSection) => void
  onSelectShot: (shotId: string | null) => void
}

export interface TasksBundle {
  bookId: number
  contentReady: boolean
  adaptationLocked: boolean
  adaptationReadyForDownstream: boolean
  contentTask: ContentTaskState
  scripts: ScriptOutput[]
  scriptDecisionState: ScriptDecisionMap
  shotsByEpisode: Record<number, StoryboardShotOutput[]>
  qaEntries: Array<{ id?: number; episode: number; result: unknown; error_count?: number }>
  taskNavigationTarget: TaskNavigationTarget | null
  onRefreshAll: () => void
  onNavigateTaskSection: TaskNavigateHandler
}

export interface DeliveryBundle {
  bookId: number
  isProjectDataLoading: boolean
  bookTitle: string
  chapterCount: number
  wordCount: number
  contentStatusLabel: string
  contentStatusDetail: string
  adaptationStateLabel: string
  adaptationStateDetail: string
  selectedAdaptationName?: string
  adaptationCustomNote?: string
  adaptationLockedAt?: string | null
  scripts: ScriptOutput[]
  scriptDecisionState: ScriptDecisionMap
  shotsByEpisode: Record<number, StoryboardShotOutput[]>
  qaEntries: Array<{ id?: number; episode: number; result: unknown; error_count?: number }>
  makeups: VisualMakeupOutput[]
  locations: VisualLocationOutput[]
  props: VisualPropOutput[]
  canvasHandoff: CanvasHandoffTarget | null
  onNavigateTaskSection: TaskNavigateHandler
}

export interface PreviewBundle {
  assetPreviewUrl: string | null
  assetPreviewLabel: string
  onCloseAssetPreview: () => void
}

export interface ProductWorkspaceSectionContentProps {
  section: WorkspaceSection
  dashboard: DashboardBundle
  content: ContentBundle
  adaptation: AdaptationBundle
  scripts: ScriptsBundle
  storyboard: StoryboardBundle
  canvas: CanvasBundle
  assets: AssetsBundle
  qa: QaBundle
  tasks: TasksBundle
  delivery: DeliveryBundle
  preview: PreviewBundle
}

export interface AdaptationSectionState {
  selectedAdaptationId: string | null
  selectedAdaptationName?: string
  adaptationCustomNote: string
  hasLockedAdaptation: boolean
  adaptationStateLabel: string
  adaptationStateDetail: string
  canGenerateCandidates: boolean
  canLockAdaptation: boolean
  productionSkill: ProductionSkillSectionState
  canLockProductionSkill: boolean
}
