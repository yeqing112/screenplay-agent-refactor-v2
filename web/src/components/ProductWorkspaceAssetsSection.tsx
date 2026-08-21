import { useMemo, useState } from 'react'
import type { StoryboardShotOutput } from '../domain/bookOutputs'
import type { AssetEpisodeInsight, AssetSummary } from './productWorkspaceAssets'
import type { AssetCategoryFilter, AssetStatusFilter, AssetVersionFilter } from './productWorkspaceAssetViewController'
import type { CanvasHandoffTarget } from './productWorkspaceSectionContracts'
import {
  getProductAssetReferenceStatusLabel,
  getProductAssetReferenceSummary,
} from './productWorkspaceAssetReferenceState'
import { getReferencePreviewUrl } from './productWorkspacePrompt'
import {
  getStoryboardRecoveryKindLabel,
  readShotRuntimeState,
  summarizePendingStoryboardTasks,
} from './productWorkspaceRecovery'

interface Props {
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
  assetActionFollowUp?:
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
  canvasHandoff?: CanvasHandoffTarget | null
  recoveryFocus?: {
    taskId?: string | null
    recoveryKind?: 'frame' | 'video' | 'reference' | 'prompt' | null
    recoveryIntent?: 'reference' | 'shot_variant_refinement' | null
    episode?: number | null
    assetId?: string | null
    assetLabel?: string | null
    shotId?: string | null
  } | null
  onDismissRecoveryFocus?: () => void
  onAssetEpisodeFilterChange: (value: 'all' | number) => void
  onAssetCategoryFilterChange: (value: AssetCategoryFilter) => void
  onAssetStatusFilterChange: (value: AssetStatusFilter) => void
  onAssetVersionFilterChange: (value: AssetVersionFilter) => void
  onAssetSearchQueryChange: (value: string) => void
  onSelectAsset: (assetId: string) => void
  onOpenPreview: (url: string, label: string) => void
  onGenerateReference: () => void
  onGenerateAssetReference: (assetId: string) => void
  onDeleteReferenceAsset: (referenceId: number) => void
  onUpdateReferenceAssetStatus: (referenceId: number, nextStatus: 'candidate' | 'selected' | 'locked') => void
  onNavigateSection: (section: 'storyboard' | 'qa') => void
  onNavigateTaskSection?: (
    section: 'storyboard' | 'canvas' | 'assets' | 'qa' | 'tasks',
    options?: {
      episode?: number | null
      shotId?: string | null
      assetId?: string | null
      assetLabel?: string | null
      taskId?: string | null
      recoveryKind?: 'frame' | 'video' | 'reference' | 'prompt' | null
      recoveryIntent?: 'reference' | 'shot_variant_refinement' | null
    },
  ) => void
  onNavigateShot: (shotId: string) => void
  onToggleShotBinding: (shotId: string) => void
  onApplyInferredShotBindings: () => void
  onSaveShotBindings: () => void
}

type AssetCanvasPrimaryActionPlan =
  | { action: 'tasks'; label: string; detail: string }
  | { action: 'switch_variant'; label: string; detail: string }
  | { action: 'generate_reference'; label: string; detail: string }
  | { action: 'apply_inferred_bindings'; label: string; detail: string }
  | { action: 'save_bindings'; label: string; detail: string }
  | { action: 'storyboard'; label: string; detail: string }

export function buildAssetCanvasPrimaryActionPlan(input: {
  selectedAsset: AssetSummary | null
  selectedAssetRuntimePrimaryTask?: {
    taskId: string
    shotLabel: string
    kindLabel: string
    episode: number
    shotId: string
    kind: 'frame' | 'video' | 'reference' | 'prompt'
  } | null
  shouldOfferShotVariantSwitch: boolean
  hasMissingReference: boolean
  hasStaleReferencePrompt: boolean
  hasUnsyncedBindings: boolean
  draftAlreadyCoversUnsyncedBindings: boolean
}) {
  const asset = input.selectedAsset
  if (!asset) return null

  if (input.selectedAssetRuntimePrimaryTask) {
    return {
      action: 'tasks',
      label: '去任务中心继续回收',
      detail: `当前资产仍有关联待回收任务，建议先把 ${input.selectedAssetRuntimePrimaryTask.shotLabel} 的 ${input.selectedAssetRuntimePrimaryTask.kindLabel} 结果收回来。`,
    } satisfies AssetCanvasPrimaryActionPlan
  }

  if (input.shouldOfferShotVariantSwitch) {
    return {
      action: 'switch_variant',
      label: '切到分镜精调版本',
      detail: '当前已经命中更合适的镜头精调版本，先切到正确版本，再继续补图与绑定。',
    } satisfies AssetCanvasPrimaryActionPlan
  }

  if (input.hasStaleReferencePrompt || input.hasMissingReference) {
    return {
      action: 'generate_reference',
      label: input.hasStaleReferencePrompt ? '重生当前版本参考图' : '生成当前版本参考图',
      detail: input.hasStaleReferencePrompt
        ? '当前参考图仍基于旧提示词，建议先重生当前版本参考图，再继续下游引用。'
        : '当前资产还没有可预览参考图，建议先补图，再继续镜头编译和出图链路。',
    } satisfies AssetCanvasPrimaryActionPlan
  }

  if (input.hasUnsyncedBindings && !input.draftAlreadyCoversUnsyncedBindings) {
    return {
      action: 'apply_inferred_bindings',
      label: '加入待同步镜头',
      detail: '系统已经识别到影响镜头，但这些绑定还没进入当前草稿，建议先一键加入。',
    } satisfies AssetCanvasPrimaryActionPlan
  }

  if (input.hasUnsyncedBindings && input.draftAlreadyCoversUnsyncedBindings) {
    return {
      action: 'save_bindings',
      label: '保存镜头绑定',
      detail: '待同步镜头已经加入当前草稿，下一步就是正式写回资产绑定关系。',
    } satisfies AssetCanvasPrimaryActionPlan
  }

  return {
    action: 'storyboard',
    label: '回镜头工作台复核',
    detail: '当前资产已经具备继续下游的条件，更适合回镜头工作台核对引用、编译与出图结果。',
  } satisfies AssetCanvasPrimaryActionPlan
}

function formatEpisodeLabel(episode?: number | null) {
  return typeof episode === 'number' && Number.isFinite(episode) ? `\u7b2c ${episode} \u96c6` : '\u8de8\u96c6'
}

function assetStatusLabel(asset: AssetSummary) {
  return getProductAssetReferenceStatusLabel({
    status: asset.status,
    referenceCount: asset.referenceCount,
    previewCount: asset.previewCount,
    selectedReferenceCount: asset.selectedReferenceCount,
    lockedReferenceCount: asset.lockedReferenceCount,
  })
}

function assetCategoryLabel(category: AssetSummary['category']) {
  if (category === 'character') return '\u4eba\u7269'
  if (category === 'location') return '\u573a\u666f'
  return '\u9053\u5177'
}

function assetCategoryFilterLabel(category: AssetCategoryFilter) {
  if (category === 'all') return '\u5168\u90e8'
  return assetCategoryLabel(category)
}

function assetStatusFilterLabel(status: AssetStatusFilter) {
  if (status === 'all') return '\u5168\u90e8\u72b6\u6001'
  if (status === 'missing_reference') return '\u7f3a\u53c2\u8003\u56fe'
  if (status === 'pending_selection') return '\u6709\u56fe\u5f85\u9009'
  if (status === 'stale_prompt') return '\u63d0\u793a\u8bcd\u5df2\u8fc7\u671f'
  return '\u5df2\u6709\u9501\u5b9a\u56fe'
}

function assetVersionFilterLabel(version: AssetVersionFilter) {
  if (version === 'all') return '\u5168\u90e8\u7248\u672c'
  if (version === 'base_identity') return '\u57fa\u7840\u5b9a\u5986'
  if (version === 'episode_default') return '\u5206\u96c6\u9ed8\u8ba4'
  if (version === 'shot_variant') return '\u5206\u955c\u7cbe\u8c03'
  if (version === 'location_variant') return '\u573a\u666f\u591a\u7248\u672c'
  return '\u9053\u5177\u591a\u7248\u672c'
}

function referenceStatusLabel(status?: string) {
  if (status === 'locked') return '\u5df2\u9501\u5b9a'
  if (status === 'selected') return '\u9ed8\u8ba4\u53c2\u8003'
  if (status === 'rejected') return '\u5df2\u6dd8\u6c70'
  if (status === 'candidate') return '\u5019\u9009\u56fe'
  return '\u8349\u7a3f'
}

function referenceStatusTone(status?: string) {
  if (status === 'locked') return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
  if (status === 'selected') return 'border-sky-500/40 bg-sky-500/10 text-sky-200'
  if (status === 'rejected') return 'border-rose-500/40 bg-rose-500/10 text-rose-200'
  return 'border-slate-700 text-slate-300'
}

function ActionMessage({ tone, message }: { tone: 'info' | 'error'; message: string }) {
  if (!message) return null
  return (
    <div
      className={`rounded-lg border px-3 py-2 text-xs ${
        tone === 'error'
          ? 'border-rose-500/30 bg-rose-500/10 text-rose-200'
          : 'border-sky-500/30 bg-sky-500/10 text-sky-200'
      }`}
    >
      {message}
    </div>
  )
}

function MetricCard({ title, value, detail }: { title: string; value: string; detail: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
      <div className="text-xs text-slate-500">{title}</div>
      <div className="mt-2 text-lg font-semibold text-white">{value}</div>
      <div className="mt-1 text-xs text-slate-400">{detail}</div>
    </div>
  )
}

function uniqueImpactEpisodeCount(insight: AssetEpisodeInsight | null | undefined) {
  if (!insight) return 0
  return new Set(
    insight.impactShots
      .map((item) => item.episode)
      .filter((episode): episode is number => typeof episode === 'number' && Number.isFinite(episode) && episode > 0),
  ).size
}

function buildSavedBindingLabel(asset: AssetSummary, insight: AssetEpisodeInsight | null | undefined) {
  const resolvedInsight = insight ?? { shotIds: [], blockerCount: 0, missingReference: false, impactShots: [] }
  if (asset.shotIds.length > 0) return `\u5df2\u4fdd\u5b58\u7ed1\u5b9a ${asset.shotIds.length}`
  if (resolvedInsight.shotIds.length > 0) return `\u5f85\u540c\u6b65\u7ed1\u5b9a ${resolvedInsight.shotIds.length}`
  return '\u5df2\u4fdd\u5b58\u7ed1\u5b9a 0'
}

function buildSavedBindingDetail(asset: AssetSummary, insight: AssetEpisodeInsight | null | undefined) {
  const resolvedInsight = insight ?? { shotIds: [], blockerCount: 0, missingReference: false, impactShots: [] }
  if (asset.shotIds.length > 0) return `\u8d44\u4ea7\u8bb0\u5f55\u91cc\u5df2\u4fdd\u5b58 ${asset.shotIds.length} \u4e2a\u76f4\u63a5\u7ed1\u5b9a\u955c\u5934`
  if (resolvedInsight.shotIds.length > 0) return `\u7cfb\u7edf\u5df2\u8bc6\u522b ${resolvedInsight.shotIds.length} \u4e2a\u5f71\u54cd\u955c\u5934\uff0c\u4f46\u5c1a\u672a\u5199\u56de\u8d44\u4ea7\u7ed1\u5b9a`
  return '\u5f53\u524d\u8d44\u4ea7\u8bb0\u5f55\u91cc\u8fd8\u6ca1\u6709\u4fdd\u5b58\u76f4\u63a5\u7ed1\u5b9a\u955c\u5934'
}

function buildCoverageEpisodeLabel(asset: AssetSummary, insight: AssetEpisodeInsight | null | undefined) {
  const savedCount = asset.episodeIds.length
  if (savedCount > 0) return String(savedCount)
  const inferredCount = uniqueImpactEpisodeCount(insight)
  return inferredCount > 0 ? `${inferredCount}*` : '-'
}

function buildCoverageEpisodeDetail(asset: AssetSummary, insight: AssetEpisodeInsight | null | undefined) {
  if (asset.episodeIds.length > 0) {
    return asset.episodeIds.map((episode) => formatEpisodeLabel(episode)).join('\u3001')
  }

  const resolvedInsight = insight ?? { shotIds: [], blockerCount: 0, missingReference: false, impactShots: [] }
  const inferredEpisodes = Array.from(
    new Set(
      resolvedInsight.impactShots
        .map((item) => item.episode)
        .filter((episode): episode is number => typeof episode === 'number' && Number.isFinite(episode) && episode > 0),
    ),
  ).sort((left, right) => left - right)

  if (inferredEpisodes.length > 0) {
    return `\u6309\u5f71\u54cd\u955c\u5934\u63a8\u65ad\uff1a${inferredEpisodes.map((episode) => formatEpisodeLabel(episode)).join('\u3001')}`
  }

  return '\u5c1a\u672a\u8986\u76d6\u5206\u96c6'
}

function normalizeBoundShotCandidates(shotIds: string[]) {
  const normalized = new Set<string>()
  for (const shotId of shotIds) {
    const value = String(shotId || '').trim()
    if (!value) continue
    normalized.add(value)
    const parts = value.split('-')
    if (parts.length >= 2) {
      normalized.add(parts.slice(1).join('-'))
    }
  }
  return normalized
}

function buildPendingBindingInsights(asset: AssetSummary, insight: AssetEpisodeInsight | null | undefined) {
  const boundCandidates = normalizeBoundShotCandidates(asset.shotIds)
  const unsyncedShots = (insight?.impactShots ?? []).filter((shot) => !boundCandidates.has(String(shot.shotId || '').trim()))

  return {
    unsyncedShots,
    unsyncedShotIds: unsyncedShots.map((shot) => String(shot.shotId || '').trim()).filter(Boolean),
  }
}

function AssetDetailPill({ label }: { label: string }) {
  if (!label.trim()) return null
  return (
    <span className="rounded-full border border-slate-700 bg-slate-950 px-2 py-0.5 text-[11px] text-slate-300">
      {label}
    </span>
  )
}

type AssetRuntimeSummary = {
  latestExecutionLabel: string | null
  latestExecutionAt: string | null
  latestExecutionShotLabel: string | null
  latestExecutionEpisode: number | null
  latestExecutionShotId: string | null
  pendingTasks: Array<{
    taskId: string
    shotLabel: string
    kindLabel: string
    assetLabel?: string
    updatedAt: string
    episode: number
    shotId: string
    kind: 'frame' | 'video' | 'reference' | 'prompt'
  }>
}

function getAssetRuntimeRecoveryIntent(asset: AssetSummary): 'reference' | 'shot_variant_refinement' {
  return asset.variantScope === 'shot_variant' ? 'shot_variant_refinement' : 'reference'
}

function parseAssetShotKey(raw: string) {
  const value = String(raw || '').trim()
  if (!value) return null
  const parts = value.split('-')
  if (parts.length >= 2) {
    const episode = Number(parts[0])
    const shotId = parts.slice(1).join('-')
    if (Number.isFinite(episode) && episode > 0 && shotId) {
      return { episode, shotId }
    }
  }
  return { episode: null, shotId: value }
}

function buildAssetRuntimeSummary(bookId: number, asset: AssetSummary, insight: AssetEpisodeInsight | null | undefined): AssetRuntimeSummary | null {
  const impactShots = insight?.impactShots ?? []
  const impactShotKeySet = new Set<string>()
  const shotTargets: Array<{ episode: number; shotId: string; shotLabel: string }> = []

  for (const shot of impactShots) {
    if (!shot.episode || !shot.shotId) continue
    const key = `${shot.episode}:${String(shot.shotId)}`
    if (impactShotKeySet.has(key)) continue
    impactShotKeySet.add(key)
    shotTargets.push({
      episode: shot.episode,
      shotId: String(shot.shotId),
      shotLabel: `${formatEpisodeLabel(shot.episode)} / 镜头 ${shot.shotId}`,
    })
  }

  for (const rawShotId of asset.shotIds) {
    const parsed = parseAssetShotKey(rawShotId)
    if (!parsed?.episode || !parsed.shotId) continue
    const key = `${parsed.episode}:${parsed.shotId}`
    if (impactShotKeySet.has(key)) continue
    impactShotKeySet.add(key)
    shotTargets.push({
      episode: parsed.episode,
      shotId: parsed.shotId,
      shotLabel: `${formatEpisodeLabel(parsed.episode)} / 镜头 ${parsed.shotId}`,
    })
  }

  const pendingTasks: AssetRuntimeSummary['pendingTasks'] = []
  let latestExecutionLabel: string | null = null
  let latestExecutionAt: string | null = null
  let latestExecutionShotLabel: string | null = null
  let latestExecutionEpisode: number | null = null
  let latestExecutionShotId: string | null = null

  for (const shot of shotTargets) {
    const runtimeState = readShotRuntimeState(bookId, shot.episode, shot.shotId)
    if (runtimeState.latestExecutionSummary?.updatedAt) {
      if (!latestExecutionAt || runtimeState.latestExecutionSummary.updatedAt > latestExecutionAt) {
        latestExecutionAt = runtimeState.latestExecutionSummary.updatedAt
        latestExecutionLabel = runtimeState.latestExecutionSummary.label
        latestExecutionShotLabel = shot.shotLabel
        latestExecutionEpisode = shot.episode
        latestExecutionShotId = shot.shotId
      }
    }
    for (const task of runtimeState.pendingTasks) {
      pendingTasks.push({
        taskId: task.taskId,
        shotLabel: shot.shotLabel,
        kindLabel: getStoryboardRecoveryKindLabel(task.kind),
        updatedAt: task.updatedAt,
        episode: shot.episode,
        shotId: shot.shotId,
        kind: task.kind,
        assetLabel: shot.shotLabel,
      })
    }
  }

  pendingTasks.sort((left, right) => String(right.updatedAt || '').localeCompare(String(left.updatedAt || '')))

  if (!latestExecutionLabel && pendingTasks.length === 0) return null
  return {
    latestExecutionLabel,
    latestExecutionAt,
    latestExecutionShotLabel,
    latestExecutionEpisode,
    latestExecutionShotId,
    pendingTasks,
  }
}

function assetDetailLabels(category: AssetSummary['category']) {
  if (category === 'character') return ['\u8eab\u4efd', '\u9636\u6bb5', '\u9020\u578b']
  if (category === 'location') return ['\u7a7a\u95f4', '\u98ce\u683c', '\u6c1b\u56f4']
  return ['\u7c7b\u522b', '\u5173\u8054', '\u8bf4\u660e']
}

function AssetDetailGroup({ asset }: { asset: AssetSummary }) {
  const labels = assetDetailLabels(asset.category)
  const values = [asset.detailPrimary || '', asset.detailSecondary || '', asset.detailTertiary || '']
  if (!values.some((value) => value.trim())) return null

  return (
    <div className="flex flex-wrap gap-2">
      {values.map((value, index) =>
        value.trim() ? <AssetDetailPill key={`${asset.id}-${labels[index]}`} label={`${labels[index]}: ${value}`} /> : null,
      )}
    </div>
  )
}

function assetVariantPanelTitle(category: AssetSummary['category']) {
  if (category === 'character') return '\u540c\u89d2\u8272\u7248\u672c'
  if (category === 'location') return '\u540c\u573a\u666f\u7248\u672c'
  return '\u540c\u9053\u5177\u7248\u672c'
}

function assetVariantPanelDescription(asset: AssetSummary, count: number) {
  if (asset.category === 'character') return `${asset.title} \u5f53\u524d\u5171\u6709 ${count} \u4e2a\u5b9a\u5986\u7248\u672c`
  if (asset.category === 'location') return `${asset.title} \u5f53\u524d\u5171\u6709 ${count} \u4e2a\u573a\u666f\u7248\u672c`
  return `${asset.title} \u5f53\u524d\u5171\u6709 ${count} \u4e2a\u9053\u5177\u7248\u672c`
}

function assetMasterLabel(asset: AssetSummary) {
  return asset.variantGroupKey || asset.title
}

function assetVariantDisplayLabel(asset: AssetSummary) {
  return asset.variantLabel || asset.subtitle || '\u672a\u547d\u540d\u7248\u672c'
}

function buildRecoveryFocusTitle(recoveryFocus: NonNullable<Props['recoveryFocus']>, selectedAsset: AssetSummary) {
  if (recoveryFocus.recoveryIntent === 'shot_variant_refinement') {
    const shotLabel = recoveryFocus.shotId ? `镜头 ${recoveryFocus.shotId}` : '当前镜头'
    return `当前聚焦：为 ${formatEpisodeLabel(recoveryFocus.episode)} / ${shotLabel} 的 ${selectedAsset.title} 补分镜精调定妆`
  }
  return '\u5df2\u4ece\u4efb\u52a1\u4e2d\u5fc3\u6062\u590d\u5230\u5f53\u524d\u8d44\u4ea7'
}

function buildRecoveryFocusDetail(recoveryFocus: NonNullable<Props['recoveryFocus']>, selectedAsset: AssetSummary) {
  if (recoveryFocus.recoveryIntent === 'shot_variant_refinement') {
    const currentVersion = assetVariantScopeLabel(selectedAsset)
    const shotLabel = recoveryFocus.shotId ? `镜头 ${recoveryFocus.shotId}` : '当前镜头'
    return `${formatEpisodeLabel(recoveryFocus.episode)} / ${shotLabel} 当前需要的是“分镜精调”版本。现在选中的还是“${currentVersion}”，可以基于它继续补当前镜头状态下的精调定妆与参考图。`
  }
  return `\u4efb\u52a1 ${recoveryFocus.taskId || '-'} / ${
    recoveryFocus.recoveryKind === 'reference' ? '\u53c2\u8003\u56fe\u7ed3\u679c\u56de\u6536' : '\u521b\u610f\u7ed3\u679c\u56de\u6536'
  } / ${selectedAsset.title}`
}

function normalizeStageToken(value?: string | null) {
  return String(value || '')
    .trim()
    .toLowerCase()
}

function resolveShotVariantSuggestion(asset: AssetSummary, shotId?: string | null) {
  const variants = asset.siblingVariants ?? []
  if (variants.length <= 1) return null

  const shotToken = String(shotId || '').trim()
  const normalizedShotToken = shotToken ? `shot_${shotToken}` : ''
  const shotVariants = variants.filter((variant) => {
    const scope = String(variant.scope || '').trim().toLowerCase()
    const stageName = normalizeStageToken(variant.stageName)
    return scope === 'shot_variant' || stageName.includes('镜头') || (normalizedShotToken ? stageName.includes(normalizedShotToken) : false)
  })

  if (shotVariants.length === 0) return null

  if (normalizedShotToken) {
    const exactMatch = shotVariants.find((variant) => normalizeStageToken(variant.stageName).includes(normalizedShotToken))
    if (exactMatch) return exactMatch
  }

  if (shotToken) {
    const looseMatch = shotVariants.find((variant) => normalizeStageToken(variant.stageName).includes(shotToken.toLowerCase()))
    if (looseMatch) return looseMatch
  }

  return shotVariants[0]
}

function buildShotVariantRecoveryHandoffSummary(
  selectedAsset: AssetSummary,
  recoveryFocus: NonNullable<Props['recoveryFocus']>,
) {
  const shotLabel = recoveryFocus.shotId ? `镜头 ${recoveryFocus.shotId}` : '当前镜头'

  if (selectedAsset.hasStaleReferencePrompt) {
    return {
      toneClassName: 'border-amber-500/30 bg-amber-500/10',
      title: '当前镜头精调版本仍在沿用旧参考图',
      detail: `${formatEpisodeLabel(recoveryFocus.episode)} / ${shotLabel} 的人物精调版本已经定位完成，但现有参考图仍基于旧提示词。建议先重生当前镜头状态下的新参考图，再回镜头工作台继续编译与出图。`,
      actionLabel: '重生当前镜头参考图',
      actionSection: 'storyboard' as const,
      actionMode: 'generate' as const,
    }
  }

  if (selectedAsset.previewCount === 0) {
    return {
      toneClassName: 'border-sky-500/30 bg-sky-500/10',
      title: '当前镜头精调版本还没有参考图',
      detail: `${formatEpisodeLabel(recoveryFocus.episode)} / ${shotLabel} 已经定位到正确的人物精调版本，下一步就可以直接为这个版本生成参考图，再回镜头工作台继续首帧与视频链路。`,
      actionLabel: '生成当前镜头参考图',
      actionSection: 'storyboard' as const,
      actionMode: 'generate' as const,
    }
  }

  return {
    toneClassName: 'border-emerald-500/30 bg-emerald-500/10',
    title: '当前镜头精调版本已经具备参考图',
    detail: `${formatEpisodeLabel(recoveryFocus.episode)} / ${shotLabel} 当前已经命中正确的人物精调版本，并且有可预览的参考图。可以回镜头工作台继续编译、生成首帧或进入 QA 复核。`,
    actionLabel: '回镜头工作台继续出图',
    actionSection: 'storyboard' as const,
    actionMode: 'navigate' as const,
  }
}

function assetVariantScopeLabel(asset: AssetSummary) {
  if (asset.category === 'character') {
    if (asset.variantScope === 'base_identity') return '\u57fa\u7840\u5b9a\u5986'
    if (asset.variantScope === 'episode_default') return '\u5206\u96c6\u9ed8\u8ba4'
    if (asset.variantScope === 'shot_variant') return '\u5206\u955c\u7cbe\u8c03'
  }
  if (asset.category === 'location' && (asset.siblingVariantCount ?? 0) > 1) return '\u573a\u666f\u53d8\u4f53'
  if (asset.category === 'prop' && (asset.siblingVariantCount ?? 0) > 1) return '\u9053\u5177\u53d8\u4f53'
  return '\u5f53\u524d\u7248\u672c'
}

function buildAssetMetaLine(asset: AssetSummary) {
  const parts = [assetMasterLabel(asset), assetVariantScopeLabel(asset)]
  if (asset.variantStageName) parts.push(asset.variantStageName)
  if (asset.variantEpisode) parts.push(formatEpisodeLabel(asset.variantEpisode))
  return parts.join(' / ')
}

function buildFilterSummary({
  allAssetsCount,
  assetEpisodeFilter,
  assetCategoryFilter,
  assetStatusFilter,
  assetVersionFilter,
  prioritizedAssets,
}: {
  allAssetsCount: number
  assetEpisodeFilter: 'all' | number
  assetCategoryFilter: AssetCategoryFilter
  assetStatusFilter: AssetStatusFilter
  assetVersionFilter: AssetVersionFilter
  prioritizedAssets: AssetSummary[]
}) {
  const scope =
    assetEpisodeFilter === 'all' ? `\u5f53\u524d\u67e5\u770b\u5168\u90e8 ${allAssetsCount} \u4e2a\u8d44\u4ea7` : `\u5f53\u524d\u805a\u7126 ${formatEpisodeLabel(assetEpisodeFilter)}`
  return `${scope}\uff0c\u7c7b\u578b\u201c${assetCategoryFilterLabel(assetCategoryFilter)}\u201d\uff0c\u72b6\u6001\u201c${assetStatusFilterLabel(assetStatusFilter)}\u201d\uff0c\u7248\u672c\u201c${assetVersionFilterLabel(assetVersionFilter)}\u201d\uff0c\u7b5b\u51fa ${prioritizedAssets.length} \u9879\u3002`
}

function groupAssetsByMaster(assets: AssetSummary[]) {
  const groups = new Map<
    string,
    {
      key: string
      title: string
      category: AssetSummary['category']
      count: number
      items: AssetSummary[]
    }
  >()

  for (const asset of assets) {
    const key = `${asset.category}:${assetMasterLabel(asset)}`
    const existing = groups.get(key)
    if (existing) {
      existing.items.push(asset)
      existing.count += 1
      continue
    }
    groups.set(key, {
      key,
      title: assetMasterLabel(asset),
      category: asset.category,
      count: 1,
      items: [asset],
    })
  }

  return Array.from(groups.values())
}

function buildAssetHandoffSummary(asset: AssetSummary, insight: AssetEpisodeInsight | null | undefined) {
  const impactCount = insight?.impactShots.length ?? 0
  const blockerCount = insight?.blockerCount ?? 0

  if (asset.hasStaleReferencePrompt) {
    return {
      toneClassName: 'border-amber-500/30 bg-amber-500/10',
      title: '\u5f53\u524d\u53c2\u8003\u56fe\u4ecd\u57fa\u4e8e\u65e7\u63d0\u793a\u8bcd',
      detail:
        asset.staleReferenceCount > 0
          ? `\u68c0\u6d4b\u5230 ${asset.staleReferenceCount} \u5f20\u53c2\u8003\u56fe\u4ecd\u7531\u65e7\u7248\u63d0\u793a\u8bcd\u751f\u6210\u3002\u5efa\u8bae\u5148\u5728\u8d44\u4ea7\u4e2d\u5fc3\u91cd\u751f\u65b0\u7248\u53c2\u8003\u56fe\u5e76\u66ff\u6362\u9ed8\u8ba4\u56fe\uff0c\u518d\u7ee7\u7eed\u540e\u7eed\u5206\u955c\u7ed1\u5b9a\u4e0e QA \u9a8c\u6536\u3002`
          : '\u5f53\u524d\u8d44\u4ea7\u5b58\u5728\u65e7\u7248\u63d0\u793a\u8bcd\u751f\u6210\u7684\u53c2\u8003\u56fe\uff0c\u5efa\u8bae\u5148\u5728\u8d44\u4ea7\u4e2d\u5fc3\u91cd\u751f\u65b0\u7248\u53c2\u8003\u56fe\u5e76\u66ff\u6362\u9ed8\u8ba4\u56fe\uff0c\u518d\u7ee7\u7eed\u540e\u7eed\u5206\u955c\u7ed1\u5b9a\u4e0e QA \u9a8c\u6536\u3002',
      actionLabel: '\u91cd\u751f\u65b0\u7248\u53c2\u8003\u56fe',
      actionSection: 'storyboard' as const,
      actionMode: 'generate' as const,
    }
  }

  if (insight?.missingReference) {
    return {
      toneClassName: 'border-amber-500/30 bg-amber-500/10',
      title: '\u5f53\u524d\u8d44\u4ea7\u4ecd\u672a\u5177\u5907\u53c2\u8003\u56fe',
      detail:
        impactCount > 0
          ? `\u8be5\u8d44\u4ea7\u5df2\u7ecf\u5f71\u54cd ${impactCount} \u4e2a\u955c\u5934\uff0c\u4f46\u8fd8\u6ca1\u6709\u53ef\u9884\u89c8\u7684\u53c2\u8003\u56fe\uff0c\u5efa\u8bae\u5148\u5728\u8fd9\u91cc\u8865\u56fe\uff0c\u518d\u56de\u955c\u5934\u5de5\u4f5c\u53f0\u590d\u6838\u5f15\u7528\u3002`
          : '\u5f53\u524d\u8d44\u4ea7\u8fd8\u6ca1\u6709\u53ef\u9884\u89c8\u7684\u53c2\u8003\u56fe\uff0c\u5efa\u8bae\u5148\u8865\u9f50\u53c2\u8003\u56fe\uff0c\u518d\u7ee7\u7eed\u955c\u5934\u7ed1\u5b9a\u548c\u4e0b\u6e38\u7f16\u8bd1\u3002',
      actionLabel: '\u56de\u955c\u5934\u5de5\u4f5c\u53f0\u590d\u6838',
      actionSection: 'storyboard' as const,
      actionMode: 'navigate' as const,
    }
  }

  if (impactCount === 0) {
    return {
      toneClassName: 'border-sky-500/30 bg-sky-500/10',
      title: '\u5f53\u524d\u8d44\u4ea7\u5c1a\u672a\u63a5\u5165\u955c\u5934\u5f15\u7528',
      detail: '\u8d44\u4ea7\u672c\u8eab\u5df2\u7ecf\u6574\u7406\u8fdb\u8d44\u4ea7\u4e2d\u5fc3\uff0c\u4f46\u8fd8\u6ca1\u6709\u547d\u4e2d\u771f\u5b9e\u955c\u5934\u3002\u5efa\u8bae\u5148\u56de\u955c\u5934\u5de5\u4f5c\u53f0\u8865\u7ed1\u5b9a\uff0c\u518d\u8ba9\u5206\u955c\u7f16\u8bd1\u548c QA \u7ee7\u627f\u3002',
      actionLabel: '\u56de\u955c\u5934\u5de5\u4f5c\u53f0\u8865\u7ed1\u5b9a',
      actionSection: 'storyboard' as const,
      actionMode: 'navigate' as const,
    }
  }

  if (blockerCount > 0) {
    return {
      toneClassName: 'border-amber-500/30 bg-amber-500/10',
      title: '\u5173\u8054\u955c\u5934\u4ecd\u6709\u5f85\u8865\u9f50\u9879',
      detail: `\u8be5\u8d44\u4ea7\u5f71\u54cd ${impactCount} \u4e2a\u955c\u5934\uff0c\u5173\u8054\u955c\u5934\u4e2d\u6700\u9ad8\u4ecd\u6709 ${blockerCount} \u4e2a\u963b\u585e\u9879\u3002\u5efa\u8bae\u5148\u56de\u955c\u5934\u5de5\u4f5c\u53f0\u8865\u9f50\uff0c\u518d\u8fdb\u5165 QA \u4fee\u590d\u3002`,
      actionLabel: '\u56de\u955c\u5934\u5de5\u4f5c\u53f0\u590d\u6838',
      actionSection: 'storyboard' as const,
      actionMode: 'navigate' as const,
    }
  }

  return {
    toneClassName: 'border-emerald-500/30 bg-emerald-500/10',
    title: '\u8d44\u4ea7\u5df2\u5177\u5907\u4e0b\u6e38\u63a5\u529b\u6761\u4ef6',
    detail: `\u5f53\u524d\u8d44\u4ea7\u5df2\u8986\u76d6 ${impactCount} \u4e2a\u955c\u5934\uff0c\u53c2\u8003\u56fe\u3001\u7ed1\u5b9a\u5173\u7cfb\u548c\u955c\u5934\u53ef\u7528\u6027\u90fd\u5df2\u8fbe\u5230\u7ee7\u7eed\u9a8c\u6536\u7684\u6761\u4ef6\uff0c\u53ef\u4ee5\u8fdb\u5165 QA \u4fee\u590d\u505a\u6574\u94fe\u590d\u6838\u3002`,
    actionLabel: '\u8fdb\u5165 QA \u4fee\u590d',
    actionSection: 'qa' as const,
    actionMode: 'navigate' as const,
  }
}

function AssetVariantPanel({
  asset,
  selectedAssetId,
  onSelectAsset,
}: {
  asset: AssetSummary
  selectedAssetId: string
  onSelectAsset: (assetId: string) => void
}) {
  const variants = asset.siblingVariants ?? []
  if (variants.length <= 1) return null

  return (
    <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
      <div>
        <div className="text-sm font-medium text-white">{assetVariantPanelTitle(asset.category)}</div>
        <div className="mt-1 text-xs text-slate-500">{assetVariantPanelDescription(asset, variants.length)}</div>
      </div>

      <div className="mt-3 space-y-2">
        {variants.map((variant) => {
          const active = variant.id === selectedAssetId
          return (
            <button
              key={variant.id}
              type="button"
              onClick={() => onSelectAsset(variant.id)}
              className={`w-full rounded-lg border px-3 py-3 text-left transition ${
                active ? 'border-sky-500/40 bg-sky-500/10' : 'border-slate-800 bg-slate-900/70 hover:border-slate-700'
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-white">{variant.label}</div>
                  <div className="mt-1 text-xs text-slate-500">
                    {[formatEpisodeLabel(variant.episode), variant.stageName].filter(Boolean).join(' / ')}
                  </div>
                </div>
                <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">
                  {getProductAssetReferenceStatusLabel({
                    status: variant.status,
                    referenceCount: 0,
                    previewCount: 0,
                    selectedReferenceCount: 0,
                    lockedReferenceCount: 0,
                  })}
                </span>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}


function ReferenceSourcePromptDialog({
  detail,
  onClose,
}: {
  detail: { title: string; prompt: string; model?: string | null } | null
  onClose: () => void
}) {
  if (!detail) return null

  return (
    <div
      role="presentation"
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/90 p-6"
    >
      <div
        className="w-full max-w-4xl overflow-hidden rounded-2xl border border-slate-800 bg-slate-950 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-slate-800 px-4 py-3">
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-white">{detail.title}</div>
            <div className="mt-1 text-[11px] text-slate-500">{detail.model ? `来源提示词 / ${detail.model}` : '来源提示词'}</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
          >
            关闭
          </button>
        </div>
        <div className="max-h-[75vh] overflow-auto px-4 py-4">
          <div className="whitespace-pre-wrap text-sm leading-6 text-slate-300">{detail.prompt}</div>
        </div>
      </div>
    </div>
  )
}

function FilterChip({
  active,
  label,
  count,
  activeClassName,
  onClick,
}: {
  active: boolean
  label: string
  count: number
  activeClassName: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs transition ${
        active
          ? activeClassName
          : 'border-slate-700 bg-slate-950 text-slate-300 hover:border-slate-500 hover:text-white'
      }`}
    >
      <span>{label}</span>
      <span className={`rounded-full px-1.5 py-0.5 ${active ? 'bg-white/15 text-white' : 'bg-slate-800 text-slate-400'}`}>
        {count}
      </span>
    </button>
  )
}

export default function ProductWorkspaceAssetsSection({
  bookId,
  allAssetsCount,
  shotEpisodes,
  assetEpisodeFilter,
  assetCategoryFilter,
  assetStatusFilter,
  assetVersionFilter,
  assetSearchQuery,
  assetCategoryCounts,
  assetStatusCounts,
  assetVersionCounts,
  prioritizedAssets,
  selectedAsset,
  assetEpisodeInsights,
  assetActionMessage,
  assetActionTone,
  assetActionFollowUp,
  linkedShotDraft,
  shotBindingState,
  isGeneratingReference,
  canvasHandoff,
  recoveryFocus,
  onDismissRecoveryFocus,
  onAssetEpisodeFilterChange,
  onAssetCategoryFilterChange,
  onAssetStatusFilterChange,
  onAssetVersionFilterChange,
  onAssetSearchQueryChange,
  onSelectAsset,
  onOpenPreview,
  onGenerateReference,
  onGenerateAssetReference,
  onDeleteReferenceAsset,
  onUpdateReferenceAssetStatus,
  onNavigateSection,
  onNavigateTaskSection,
  onNavigateShot,
  onToggleShotBinding,
  onApplyInferredShotBindings,
  onSaveShotBindings,
}: Props) {
  const [referenceSourcePromptDetail, setReferenceSourcePromptDetail] = useState<{
    title: string
    prompt: string
    model?: string | null
  } | null>(null)
  const assetGroups = groupAssetsByMaster(prioritizedAssets)
  const selectedInsight = selectedAsset
    ? assetEpisodeInsights.get(selectedAsset.id) ?? { shotIds: [], blockerCount: 0, missingReference: false, impactShots: [] }
    : null
  const selectedAssetRuntimeSummary = useMemo(
    () => (selectedAsset ? buildAssetRuntimeSummary(bookId, selectedAsset, selectedInsight) : null),
    [bookId, selectedAsset, selectedInsight],
  )
  const selectedAssetPendingSummary = useMemo(
    () => summarizePendingStoryboardTasks(selectedAssetRuntimeSummary?.pendingTasks ?? []),
    [selectedAssetRuntimeSummary?.pendingTasks],
  )
  const selectedAssetRuntimePrimaryTask = selectedAssetRuntimeSummary?.pendingTasks[0] ?? null
  const selectedAssetRuntimeRecoveryIntent = selectedAsset ? getAssetRuntimeRecoveryIntent(selectedAsset) : 'reference'
  const pendingBindingInsights = selectedAsset
    ? buildPendingBindingInsights(selectedAsset, selectedInsight)
    : { unsyncedShots: [], unsyncedShotIds: [] }
  const hasUnsyncedBindings = pendingBindingInsights.unsyncedShotIds.length > 0
  const draftAlreadyCoversUnsyncedBindings =
    hasUnsyncedBindings && pendingBindingInsights.unsyncedShotIds.every((shotId) => linkedShotDraft.includes(shotId))

  const shouldHighlightRecoveredReference = Boolean(
    recoveryFocus?.recoveryKind === 'reference' &&
      recoveryFocus?.assetId &&
      selectedAsset &&
      recoveryFocus.assetId === selectedAsset.id &&
      selectedAsset.references.length > 0,
  )
  const suggestedShotVariant =
    selectedAsset && recoveryFocus?.recoveryIntent === 'shot_variant_refinement'
      ? resolveShotVariantSuggestion(selectedAsset, recoveryFocus.shotId)
      : null
  const shouldOfferShotVariantSwitch =
    Boolean(suggestedShotVariant) && suggestedShotVariant?.id !== selectedAsset?.id && selectedAsset?.variantScope !== 'shot_variant'
  const recoveryFocusDetail =
    recoveryFocus?.recoveryIntent === 'shot_variant_refinement' && selectedAsset?.variantScope === 'shot_variant'
      ? `${formatEpisodeLabel(recoveryFocus.episode)} / ${recoveryFocus.shotId ? `镜头 ${recoveryFocus.shotId}` : '当前镜头'} 已经切到当前镜头对应的“${assetVariantScopeLabel(selectedAsset)}”版本，可以直接继续补当前镜头状态下的精调定妆与参考图。`
      : selectedAsset && recoveryFocus
        ? buildRecoveryFocusDetail(recoveryFocus, selectedAsset)
        : ''
  const handoffSummary =
    selectedAsset && recoveryFocus?.recoveryIntent === 'shot_variant_refinement' && selectedAsset.variantScope === 'shot_variant'
      ? buildShotVariantRecoveryHandoffSummary(selectedAsset, recoveryFocus)
      : selectedAsset
        ? buildAssetHandoffSummary(selectedAsset, selectedInsight)
        : null
  const assetCanvasPrimaryActionPlan = useMemo(
    () =>
      canvasHandoff
        ? buildAssetCanvasPrimaryActionPlan({
            selectedAsset,
            selectedAssetRuntimePrimaryTask,
            shouldOfferShotVariantSwitch,
            hasMissingReference: Boolean(selectedAsset && selectedAsset.previewCount === 0),
            hasStaleReferencePrompt: Boolean(selectedAsset?.hasStaleReferencePrompt),
            hasUnsyncedBindings,
            draftAlreadyCoversUnsyncedBindings,
          })
        : null,
    [
      canvasHandoff,
      draftAlreadyCoversUnsyncedBindings,
      hasUnsyncedBindings,
      selectedAsset,
      selectedAssetRuntimePrimaryTask,
      shouldOfferShotVariantSwitch,
    ],
  )
  const showActionFollowUp = Boolean(
    selectedAsset &&
      assetActionFollowUp &&
      (!assetActionFollowUp.assetId || assetActionFollowUp.assetId === selectedAsset.id),
  )

  const runAssetCanvasPrimaryAction = () => {
    if (!selectedAsset || !assetCanvasPrimaryActionPlan) return

    if (assetCanvasPrimaryActionPlan.action === 'tasks') {
      if (!selectedAssetRuntimePrimaryTask) return
      onNavigateTaskSection?.('tasks', {
        taskId: selectedAssetRuntimePrimaryTask.taskId,
        episode: selectedAssetRuntimePrimaryTask.episode,
        shotId: selectedAssetRuntimePrimaryTask.shotId,
        assetId: selectedAsset.id,
        assetLabel: selectedAsset.title,
        recoveryKind: selectedAssetRuntimePrimaryTask.kind,
        recoveryIntent: selectedAssetRuntimeRecoveryIntent,
      })
      return
    }

    if (assetCanvasPrimaryActionPlan.action === 'switch_variant') {
      if (suggestedShotVariant) onSelectAsset(suggestedShotVariant.id)
      return
    }

    if (assetCanvasPrimaryActionPlan.action === 'generate_reference') {
      onGenerateReference()
      return
    }

    if (assetCanvasPrimaryActionPlan.action === 'apply_inferred_bindings') {
      onApplyInferredShotBindings()
      return
    }

    if (assetCanvasPrimaryActionPlan.action === 'save_bindings') {
      onSaveShotBindings()
      return
    }

    const targetEpisode =
      typeof selectedAsset.variantEpisode === 'number' && Number.isFinite(selectedAsset.variantEpisode)
        ? selectedAsset.variantEpisode
        : selectedAsset.episodeIds[0] ?? null
    const targetShotId =
      recoveryFocus?.shotId ??
      selectedAssetRuntimePrimaryTask?.shotId ??
      pendingBindingInsights.unsyncedShotIds[0] ??
      selectedInsight?.impactShots?.[0]?.shotId ??
      null

    onNavigateTaskSection?.('storyboard', {
      episode: targetEpisode,
      shotId: targetShotId,
      assetId: selectedAsset.id,
      assetLabel: selectedAsset.title,
      recoveryIntent: selectedAssetRuntimeRecoveryIntent,
    })
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[0.92fr_1.2fr_0.95fr]">
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="text-sm font-medium text-white">资产列表</div>
          <select
            value={assetEpisodeFilter === 'all' ? 'all' : String(assetEpisodeFilter)}
            onChange={(event) => onAssetEpisodeFilterChange(event.target.value === 'all' ? 'all' : Number(event.target.value))}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-slate-200"
          >
            <option value="all">全部资产</option>
            {shotEpisodes.map(({ episode }) => (
              <option key={episode} value={episode}>
                {formatEpisodeLabel(episode)}
              </option>
            ))}
          </select>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {(['all', 'character', 'location', 'prop'] as const).map((category) => (
            <FilterChip
              key={category}
              active={assetCategoryFilter === category}
              label={assetCategoryFilterLabel(category)}
              count={assetCategoryCounts[category]}
              activeClassName="border-sky-500/50 bg-sky-500/10 text-sky-100"
              onClick={() => onAssetCategoryFilterChange(category)}
            />
          ))}
        </div>

        <div className="mt-3">
          <input
            type="search"
            value={assetSearchQuery}
            onChange={(event) => onAssetSearchQueryChange(event.target.value)}
            placeholder="搜索名称、描述或提示词"
            className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
          />
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {(['all', 'missing_reference', 'pending_selection', 'stale_prompt', 'locked_reference'] as const).map((status) => (
            <FilterChip
              key={status}
              active={assetStatusFilter === status}
              label={assetStatusFilterLabel(status)}
              count={assetStatusCounts[status]}
              activeClassName="border-violet-500/50 bg-violet-500/10 text-violet-100"
              onClick={() => onAssetStatusFilterChange(status)}
            />
          ))}
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {(['all', 'base_identity', 'episode_default', 'shot_variant', 'location_variant', 'prop_variant'] as const).map(
            (version) => (
              <FilterChip
                key={version}
                active={assetVersionFilter === version}
                label={assetVersionFilterLabel(version)}
                count={assetVersionCounts[version]}
                activeClassName="border-cyan-500/50 bg-cyan-500/10 text-cyan-100"
                onClick={() => onAssetVersionFilterChange(version)}
              />
            ),
          )}
        </div>

        <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2 text-xs leading-6 text-slate-400">
          {buildFilterSummary({
            allAssetsCount,
            assetEpisodeFilter,
            assetCategoryFilter,
            assetStatusFilter,
            assetVersionFilter,
            prioritizedAssets,
          })}
        </div>

        <div className="mt-4 space-y-4">
          {prioritizedAssets.length > 0 ? (
            assetGroups.map((group) => (
              <div key={group.key} className="rounded-xl border border-slate-800 bg-slate-950/30 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
                  <div>
                    <div className="text-sm font-medium text-white">{group.title}</div>
                    <div className="mt-1 text-xs text-slate-500">{assetCategoryLabel(group.category)} / {'\u5171'} {group.count} {'\u4e2a\u7248\u672c'}</div>
                  </div>
                  {group.count > 1 ? (
                    <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">{'\u7248\u672c\u7ec4'}</span>
                  ) : null}
                </div>

                <div className="mt-3 space-y-3">
                  {group.items.map((asset) => {
                    const active = selectedAsset?.id === asset.id
                    const insight = assetEpisodeInsights.get(asset.id) ?? {
                      shotIds: [],
                      blockerCount: 0,
                      missingReference: false,
                      impactShots: [],
                    }
                    const runtimeSummary = buildAssetRuntimeSummary(bookId, asset, insight)
                    const canQuickGenerate = asset.previewCount === 0 || asset.hasStaleReferencePrompt

                    return (
                      <div
                        key={asset.id}
                        className={`rounded-xl border p-3 transition ${
                          active ? 'border-sky-500/40 bg-sky-500/10' : 'border-slate-800 bg-slate-950/50 hover:border-slate-700'
                        }`}
                      >
                        <button type="button" onClick={() => onSelectAsset(asset.id)} className="w-full text-left">
                          <div className="flex items-center justify-between gap-3">
                            <div className="text-sm font-medium text-white">{assetVariantDisplayLabel(asset)}</div>
                            <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">
                              {assetStatusLabel(asset)}
                            </span>
                          </div>

                          <div className="mt-1 text-xs text-slate-500">{buildAssetMetaLine(asset)}</div>

                          {(asset.detailPrimary || asset.detailSecondary || asset.detailTertiary) && (
                            <div className="mt-3">
                              <AssetDetailGroup asset={asset} />
                            </div>
                          )}

                          <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
                            {runtimeSummary?.latestExecutionLabel ? (
                              <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-sky-200">
                                最近执行
                              </span>
                            ) : null}
                            {runtimeSummary?.pendingTasks.length ? (
                              <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-200">
                                待回收 {runtimeSummary.pendingTasks.length}
                              </span>
                            ) : null}
                            {asset.hasStaleReferencePrompt ? (
                              <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-200">{'\u63d0\u793a\u8bcd\u5f85\u91cd\u751f'}</span>
                            ) : null}
                            {insight.missingReference ? (
                              <span className="rounded-full border border-rose-500/30 bg-rose-500/10 px-2 py-0.5 text-rose-200">{'\u7f3a\u53ef\u9884\u89c8\u53c2\u8003\u56fe'}</span>
                            ) : null}
                            {asset.lockedReferenceCount > 0 ? (
                              <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-emerald-200">{'\u5df2\u9501\u5b9a'} {asset.lockedReferenceCount}</span>
                            ) : null}
                            {insight.shotIds.length > 0 ? (
                              <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-200">{'\u5f71\u54cd\u955c\u5934'} {insight.shotIds.length}</span>
                            ) : null}
                            {insight.blockerCount > 0 ? (
                              <span className="rounded-full border border-slate-700 px-2 py-0.5 text-slate-300">{'\u963b\u585e'} {insight.blockerCount}</span>
                            ) : null}
                          </div>

                          <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-slate-500 sm:grid-cols-4">
                            <span>{'\u9884\u89c8'} {asset.previewCount}/{asset.referenceCount}</span>
                            <span>{getProductAssetReferenceSummary(asset)}</span>
                            <span>{buildSavedBindingLabel(asset, insight)}</span>
                            <span>{'\u8986\u76d6\u96c6\u6570'} {buildCoverageEpisodeLabel(asset, insight)}</span>
                          </div>
                        </button>

                        {canQuickGenerate ? (
                          <div className="mt-3 flex flex-wrap gap-2 border-t border-slate-800 pt-3">
                            <button
                              type="button"
                              onClick={() => onGenerateAssetReference(asset.id)}
                              className="rounded-lg border border-sky-500/50 px-3 py-1.5 text-xs text-sky-200 transition hover:border-sky-400 hover:text-white"
                            >
                              {asset.hasStaleReferencePrompt ? '\u91cd\u751f\u65b0\u7248\u53c2\u8003\u56fe' : '\u8865\u53c2\u8003\u56fe'}
                            </button>
                            <button
                              type="button"
                              onClick={() => onSelectAsset(asset.id)}
                              className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
                            >
                              {'\u67e5\u770b\u8d44\u4ea7'}
                            </button>
                          </div>
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              </div>
            ))
          ) : (
            <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
              {assetSearchQuery.trim()
                ? '\u6ca1\u6709\u627e\u5230\u7b26\u5408\u5f53\u524d\u641c\u7d22\u8bcd\u7684\u8d44\u4ea7\uff0c\u6362\u4e00\u4e2a\u5173\u952e\u8bcd\u8bd5\u8bd5\u3002'
                : '\u5f53\u524d\u7b5b\u9009\u6761\u4ef6\u4e0b\u6ca1\u6709\u8d44\u4ea7\uff0c\u53ef\u4ee5\u5207\u6362\u7c7b\u578b\u3001\u72b6\u6001\u6216\u7248\u672c\u7ee7\u7eed\u67e5\u770b\u3002'}
            </div>
          )}
        </div>
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        {selectedAsset ? (
          <>
            {!canvasHandoff && recoveryFocus?.assetId && recoveryFocus.assetId === selectedAsset.id ? (
              <div className="mb-5 rounded-xl border border-sky-500/30 bg-sky-500/10 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-sky-100">{buildRecoveryFocusTitle(recoveryFocus, selectedAsset)}</div>
                    <div className="mt-1 text-xs leading-6 text-sky-100/80">
                      {recoveryFocusDetail}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {shouldOfferShotVariantSwitch && suggestedShotVariant ? (
                      <button
                        type="button"
                        onClick={() => onSelectAsset(suggestedShotVariant.id)}
                        className="rounded-lg border border-sky-400/40 bg-sky-500/10 px-3 py-1.5 text-xs text-sky-100 transition hover:border-sky-300 hover:text-white"
                      >
                        切到分镜精调版本
                      </button>
                    ) : null}
                    {onDismissRecoveryFocus ? (
                      <button
                        type="button"
                        onClick={onDismissRecoveryFocus}
                        className="rounded-lg border border-sky-400/40 px-3 py-1.5 text-xs text-sky-100 transition hover:border-sky-300 hover:text-white"
                      >
                        {'\u5173\u95ed\u63d0\u793a'}
                      </button>
                    ) : null}
                  </div>
                </div>
              </div>
            ) : null}

            {canvasHandoff && assetCanvasPrimaryActionPlan ? (
              <div className="mb-5 rounded-xl border border-fuchsia-500/30 bg-fuchsia-500/10 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-xs font-medium tracking-wide text-fuchsia-200">创作画布承接中</div>
                    <div className="mt-2 text-sm font-medium text-white">已从创作画布定位到当前资产上下文</div>
                    <div className="mt-2 text-sm text-fuchsia-100">{selectedAsset.title}</div>
                    <div className="mt-3 rounded-lg border border-fuchsia-400/20 bg-fuchsia-950/20 px-3 py-2">
                      <div className="text-[11px] font-medium text-fuchsia-200">承接后的首个动作</div>
                      <div className="mt-1 text-sm text-white">{assetCanvasPrimaryActionPlan.label}</div>
                      <div className="mt-1 text-xs leading-5 text-fuchsia-100/80">{assetCanvasPrimaryActionPlan.detail}</div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={runAssetCanvasPrimaryAction}
                    disabled={isGeneratingReference || shotBindingState === 'saving'}
                    className="rounded-lg border border-fuchsia-300/40 bg-fuchsia-400/15 px-3 py-2 text-xs font-medium text-white transition hover:border-fuchsia-200 hover:bg-fuchsia-400/20 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    立即继续
                  </button>
                </div>
              </div>
            ) : null}

            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-lg font-semibold text-white">{selectedAsset.title}</div>
                <div className="mt-2 text-sm leading-6 text-slate-400">{selectedAsset.subtitle}</div>
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2">
                {onNavigateTaskSection ? (
                  <button
                    type="button"
                    onClick={() =>
                      onNavigateTaskSection('canvas', {
                        episode: assetEpisodeFilter === 'all' ? selectedAsset.variantEpisode ?? selectedAsset.episodeIds[0] ?? null : assetEpisodeFilter,
                        assetId: selectedAsset.id,
                        assetLabel: selectedAsset.title,
                      })
                    }
                    className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-sky-500 hover:text-white"
                  >
                    在创作画布查看
                  </button>
                ) : null}
                <span className="rounded-full border border-slate-700 px-2.5 py-1 text-xs text-slate-300">
                  {assetStatusLabel(selectedAsset)}
                </span>
              </div>
            </div>

            <div className="mt-5 grid gap-3 md:grid-cols-4">
              <MetricCard
                title={'\u53c2\u8003\u56fe'}
                value={`${selectedAsset.previewCount}`}
                detail={`\u5171 ${selectedAsset.referenceCount} \u5f20\u8bb0\u5f55\uff1b${getProductAssetReferenceSummary(selectedAsset)}`}
              />
              <MetricCard
                title={'\u5df2\u4fdd\u5b58\u7ed1\u5b9a'}
                value={`${selectedAsset.shotIds.length}`}
                detail={buildSavedBindingDetail(selectedAsset, selectedInsight)}
              />
              <MetricCard
                title={'\u5f71\u54cd\u955c\u5934'}
                value={`${selectedInsight?.shotIds.length ?? 0}`}
                detail={'\u6839\u636e\u771f\u5b9e\u5206\u955c\u5f15\u7528\u3001\u7ed3\u6784\u5316\u7ed1\u5b9a\u548c\u63d0\u793a\u8bcd\u4e0a\u4e0b\u6587\u8bc6\u522b'}
              />
              <MetricCard
                title={'\u8986\u76d6\u96c6\u6570'}
                value={buildCoverageEpisodeLabel(selectedAsset, selectedInsight)}
                detail={buildCoverageEpisodeDetail(selectedAsset, selectedInsight)}
              />
              <MetricCard
                title={'\u8d44\u4ea7\u7c7b\u578b'}
                value={assetCategoryLabel(selectedAsset.category)}
                detail={'\u4eba\u7269 / \u573a\u666f / \u9053\u5177\u7edf\u4e00\u7ba1\u7406'}
              />
            </div>

            {selectedAssetRuntimeSummary ? (
              <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="text-sm font-medium text-white">关联镜头运行态</div>
                  <div className="flex flex-wrap gap-2 text-[11px] text-slate-500">
                    {selectedAssetRuntimeSummary.latestExecutionAt ? (
                      <span className="rounded-full border border-slate-800 px-2 py-0.5">
                        更新于 {new Date(selectedAssetRuntimeSummary.latestExecutionAt).toLocaleString('zh-CN', { hour12: false })}
                      </span>
                    ) : null}
                    {selectedAssetPendingSummary.latestUpdatedAt ? (
                      <span className="rounded-full border border-slate-800 px-2 py-0.5">
                        待回收更新于 {new Date(selectedAssetPendingSummary.latestUpdatedAt).toLocaleString('zh-CN', { hour12: false })}
                      </span>
                    ) : null}
                  </div>
                </div>
                <div className="mt-3 grid gap-3 md:grid-cols-3">
                  <MetricCard
                    title="最近执行"
                    value={selectedAssetRuntimeSummary.latestExecutionLabel || '未记录'}
                    detail={selectedAssetRuntimeSummary.latestExecutionShotLabel || '当前还没有关联镜头执行摘要'}
                  />
                  <MetricCard
                    title="待回收任务"
                    value={selectedAssetPendingSummary.count > 0 ? selectedAssetPendingSummary.joinedKindLabels : '无'}
                    detail={
                      selectedAssetRuntimeSummary.pendingTasks.length > 0
                        ? selectedAssetRuntimeSummary.pendingTasks
                            .slice(0, 2)
                            .map((item) => `${item.shotLabel} · ${item.kindLabel}`)
                            .join('；')
                        : '当前关联镜头没有待回收任务'
                    }
                  />
                  <MetricCard
                    title="建议动作"
                    value={selectedAssetRuntimeSummary.pendingTasks.length > 0 ? '先回收任务' : '继续复核资产'}
                    detail={
                      selectedAssetRuntimeSummary.pendingTasks.length > 0
                        ? '建议先回任务中心或镜头工作台收口待回收任务，再决定是否继续重生参考图。'
                        : '当前资产关联镜头没有挂起任务，可以继续检查锁定图、版本和引用范围。'
                    }
                  />
                </div>
                {selectedAssetPendingSummary.latestTaskId && selectedAssetPendingSummary.latestSourceLabel ? (
                  <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-[11px] text-slate-300">
                    最近待回收来源：{selectedAssetPendingSummary.latestSourceLabel} · 任务 ID：{selectedAssetPendingSummary.latestTaskId}
                  </div>
                ) : null}
                {onNavigateTaskSection && selectedAsset ? (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {selectedAssetRuntimePrimaryTask ? (
                      <>
                        <button
                          type="button"
                          onClick={() =>
                            onNavigateTaskSection('tasks', {
                              taskId: selectedAssetRuntimePrimaryTask.taskId,
                              episode: selectedAssetRuntimePrimaryTask.episode,
                              shotId: selectedAssetRuntimePrimaryTask.shotId,
                              assetId: selectedAsset.id,
                              assetLabel: selectedAsset.title,
                              recoveryKind: selectedAssetRuntimePrimaryTask.kind,
                              recoveryIntent: selectedAssetRuntimeRecoveryIntent,
                            })
                          }
                          className="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs font-medium text-sky-100 transition hover:border-sky-400 hover:text-white"
                        >
                          去任务中心继续回收
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            onNavigateTaskSection('storyboard', {
                              episode: selectedAssetRuntimePrimaryTask.episode,
                              shotId: selectedAssetRuntimePrimaryTask.shotId,
                              assetId: selectedAsset.id,
                              assetLabel: selectedAsset.title,
                              recoveryKind: selectedAssetRuntimePrimaryTask.kind,
                              recoveryIntent: selectedAssetRuntimeRecoveryIntent,
                            })
                          }
                          className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-sky-500 hover:text-white"
                        >
                          去镜头工作台定位镜头
                        </button>
                      </>
                    ) : selectedAssetRuntimeSummary.latestExecutionEpisode && selectedAssetRuntimeSummary.latestExecutionShotId ? (
                      <button
                        type="button"
                        onClick={() =>
                          onNavigateTaskSection('storyboard', {
                            episode: selectedAssetRuntimeSummary.latestExecutionEpisode,
                            shotId: selectedAssetRuntimeSummary.latestExecutionShotId,
                            assetId: selectedAsset.id,
                            assetLabel: selectedAsset.title,
                            recoveryIntent: selectedAssetRuntimeRecoveryIntent,
                          })
                        }
                        className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-sky-500 hover:text-white"
                      >
                        去镜头工作台查看结果
                      </button>
                    ) : null}
                  </div>
                ) : null}
                {selectedAssetRuntimeSummary.pendingTasks.length > 0 ? (
                  <div className="mt-4 space-y-2">
                    {selectedAssetRuntimeSummary.pendingTasks.slice(0, 4).map((task) => (
                      <div key={`${task.taskId}-${task.updatedAt}`} className="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-xs text-slate-300">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span>{task.shotLabel} · {task.kindLabel}</span>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-slate-500">
                              {new Date(task.updatedAt).toLocaleString('zh-CN', { hour12: false })}
                            </span>
                            {onNavigateTaskSection ? (
                              <button
                                type="button"
                                onClick={() =>
                                  onNavigateTaskSection('tasks', {
                                    taskId: task.taskId,
                                    episode: task.episode,
                                    shotId: task.shotId,
                                    assetId: selectedAsset.id,
                                    assetLabel: selectedAsset.title,
                                    recoveryKind: task.kind,
                                    recoveryIntent: selectedAssetRuntimeRecoveryIntent,
                                  })
                                }
                                className="rounded border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300 transition hover:border-sky-500 hover:text-white"
                              >
                                继续回收
                              </button>
                            ) : null}
                          </div>
                        </div>
                        <div className="mt-1 break-all text-[11px] text-slate-500">任务 ID：{task.taskId}</div>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}

            <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
              <div className="text-sm font-medium text-white">{'\u4e3b\u6863\u6848\u4e0e\u5f53\u524d\u7248\u672c'}</div>
              <div className="mt-3 flex flex-wrap gap-2">
                <AssetDetailPill label={`\u4e3b\u6863\u6848\uff1a${assetMasterLabel(selectedAsset)}`} />
                <AssetDetailPill label={`\u5f53\u524d\u7248\u672c\uff1a${assetVariantDisplayLabel(selectedAsset)}`} />
                <AssetDetailPill label={`\u7248\u672c\u7c7b\u578b\uff1a${assetVariantScopeLabel(selectedAsset)}`} />
                {selectedAsset.variantStageName ? <AssetDetailPill label={`\u9636\u6bb5\uff1a${selectedAsset.variantStageName}`} /> : null}
                {selectedAsset.variantEpisode ? <AssetDetailPill label={`\u751f\u6548\u96c6\u6570\uff1a${formatEpisodeLabel(selectedAsset.variantEpisode)}`} /> : null}
              </div>
            </div>

            {handoffSummary ? (
              <div className={`mt-5 rounded-xl border p-4 ${handoffSummary.toneClassName}`}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-white">{'\u4e0a\u4e0b\u6e38\u4ea4\u63a5\u72b6\u6001'}</div>
                    <div className="mt-2 text-sm font-medium text-white">{handoffSummary.title}</div>
                    <div className="mt-2 text-sm leading-6 text-slate-300">{handoffSummary.detail}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() =>
                      handoffSummary.actionMode === 'generate'
                        ? onGenerateReference()
                        : onNavigateSection(handoffSummary.actionSection)
                    }
                    className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-100 transition hover:border-sky-500 hover:text-white"
                  >
                    {handoffSummary.actionLabel}
                  </button>
                </div>
              </div>
            ) : null}

            <AssetVariantPanel asset={selectedAsset} selectedAssetId={selectedAsset.id} onSelectAsset={onSelectAsset} />

            {selectedAsset.recordSource === 'character_profile_fallback' ? (
              <div className="mt-5 rounded-xl border border-slate-700 bg-slate-950/70 p-4 text-sm leading-6 text-slate-300">
                {'\u5f53\u524d\u4eba\u7269\u8d44\u4ea7\u6765\u81ea\u65e7\u7248\u89d2\u8272\u6863\u6848\u517c\u5bb9\u56de\u586b\u3002\u9996\u6b21\u4fdd\u5b58\u955c\u5934\u7ed1\u5b9a\u6216\u53c2\u8003\u56fe\u65f6\uff0c\u7cfb\u7edf\u4f1a\u81ea\u52a8\u8865\u5efa\u6b63\u5f0f\u4eba\u7269\u8d44\u4ea7\uff0c\u5e76\u7ee7\u7eed\u540e\u7eed\u6d41\u7a0b\u3002'}
              </div>
            ) : null}

            {selectedAsset.hasStaleReferencePrompt ? (
              <div className="mt-5 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
                <div className="text-sm font-medium text-amber-100">{'\u5f53\u524d\u53c2\u8003\u56fe\u57fa\u4e8e\u65e7\u63d0\u793a\u8bcd\u751f\u6210'}</div>
                <div className="mt-2 text-sm leading-6 text-amber-100/85">
                  {`\u68c0\u6d4b\u5230 ${selectedAsset.staleReferenceCount} \u5f20\u53c2\u8003\u56fe\u7684\u751f\u6210\u63d0\u793a\u8bcd\u4e0e\u5f53\u524d\u8d44\u4ea7\u63d0\u793a\u8bcd\u4e0d\u4e00\u81f4\u3002\u5efa\u8bae\u91cd\u65b0\u751f\u6210\uff0c\u518d\u5c06\u65b0\u7248\u8bbe\u4e3a\u9ed8\u8ba4\u6216\u9501\u5b9a\u3002`}
                </div>
              </div>
            ) : null}

            <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
              {(selectedAsset.detailPrimary || selectedAsset.detailSecondary || selectedAsset.detailTertiary) && (
                <div className="mb-4">
                  <AssetDetailGroup asset={selectedAsset} />
                </div>
              )}
              <div className="text-sm font-medium text-white">{'\u8d44\u4ea7\u63d0\u793a\u8bcd'}</div>
              <div className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-300">
                {selectedAsset.prompt || '\u5f53\u524d\u8d44\u4ea7\u8fd8\u6ca1\u6709\u53ef\u5c55\u793a\u7684\u7ed3\u6784\u5316\u63d0\u793a\u8bcd\u3002'}
              </div>
            </div>

            <div className={`mt-5 rounded-xl border p-4 ${shouldHighlightRecoveredReference ? 'border-sky-500/40 bg-sky-500/5' : 'border-slate-800 bg-slate-950/50'}`}>
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-white">{'\u53c2\u8003\u56fe\u7ba1\u7406'}</div>
                  <div className="mt-1 text-xs text-slate-500">
                    {selectedAsset.hasStaleReferencePrompt
                      ? '\u5f53\u524d\u5b58\u5728\u65e7\u63d0\u793a\u8bcd\u751f\u6210\u7684\u53c2\u8003\u56fe\uff0c\u53ef\u4ee5\u76f4\u63a5\u91cd\u751f\u5e76\u66ff\u6362\u9ed8\u8ba4\u56fe\u3002'
                      : '\u652f\u6301\u9884\u89c8\u3001\u8bbe\u4e3a\u9ed8\u8ba4\u3001\u9501\u5b9a\u548c\u5220\u9664\uff0c\u4e5f\u53ef\u4ee5\u76f4\u63a5\u8865\u751f\u6210\u3002'}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={onGenerateReference}
                  disabled={isGeneratingReference}
                  className="rounded-lg border border-sky-500/50 px-3 py-1.5 text-xs font-medium text-sky-200 transition hover:border-sky-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isGeneratingReference ? '\u751f\u6210\u4e2d...' : selectedAsset.hasStaleReferencePrompt ? '\u91cd\u751f\u5e76\u66ff\u6362\u9ed8\u8ba4\u56fe' : '\u751f\u6210\u53c2\u8003\u56fe'}
                </button>
              </div>

              <div className="mt-3">
                <ActionMessage tone={assetActionTone} message={assetActionMessage} />
              </div>

              {showActionFollowUp && assetActionFollowUp ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      if (assetActionFollowUp.mode === 'tasks') {
                        onNavigateTaskSection?.('tasks', {
                          taskId: assetActionFollowUp.taskId ?? null,
                          episode: assetActionFollowUp.episode ?? null,
                          shotId: assetActionFollowUp.shotId ?? null,
                          assetId: assetActionFollowUp.assetId ?? selectedAsset?.id ?? null,
                          assetLabel: selectedAsset?.title ?? null,
                          recoveryKind: 'reference',
                        })
                        return
                      }
                      onNavigateTaskSection?.('storyboard', {
                        taskId: assetActionFollowUp.taskId ?? null,
                        episode: assetActionFollowUp.episode ?? null,
                        shotId: assetActionFollowUp.shotId ?? null,
                        assetId: assetActionFollowUp.assetId ?? selectedAsset?.id ?? null,
                        assetLabel: selectedAsset?.title ?? null,
                        recoveryKind: 'reference',
                      })
                    }}
                    className="rounded-lg border border-sky-500/50 px-3 py-1.5 text-xs font-medium text-sky-200 transition hover:border-sky-400 hover:text-white"
                  >
                    {assetActionFollowUp.label}
                  </button>
                </div>
              ) : null}

              {shouldHighlightRecoveredReference ? (
                <div className="mt-3 text-xs text-sky-200">{'\u672c\u6b21\u6062\u590d\u7ed3\u679c\u5df2\u56de\u5199\u5230\u4e0b\u65b9\u53c2\u8003\u56fe\u5217\u8868\u3002'}</div>
              ) : null}

              {selectedAsset.hasStaleReferencePrompt ? (
                <div className="mt-3 text-xs text-amber-200/90">
                  {'\u91cd\u751f\u5b8c\u6210\u540e\uff0c\u65b0\u56fe\u4f1a\u81ea\u52a8\u56de\u5199\u8d44\u4ea7\u4e2d\u5fc3\u5e76\u5207\u6362\u4e3a\u9ed8\u8ba4\u53c2\u8003\uff0c\u65e7\u56fe\u4f1a\u4fdd\u7559\u4e3a\u5019\u9009\uff0c\u65b9\u4fbf\u4eba\u5de5\u590d\u6838\u540e\u5220\u9664\u3002'}
                </div>
              ) : null}

              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {selectedAsset.references.length > 0 ? (
                  selectedAsset.references.map((reference, index) => {
                    const previewUrl = getReferencePreviewUrl(reference)
                    const previewLabel = reference.asset_name || reference.reference_token || selectedAsset.title
                    const isRecoveredTarget = Boolean(shouldHighlightRecoveredReference && index === 0)

                    return (
                      <div
                        key={reference.id ?? `${selectedAsset.id}-${reference.reference_token ?? reference.asset_name ?? 'ref'}`}
                        className={`overflow-hidden rounded-xl border ${
                          isRecoveredTarget ? 'border-sky-500/40 bg-sky-500/10' : 'border-slate-800 bg-slate-900/70'
                        }`}
                      >
                        <div className="aspect-[16/10] border-b border-slate-800 bg-slate-950">
                          {previewUrl ? (
                            <button type="button" onClick={() => onOpenPreview(previewUrl, previewLabel)} className="h-full w-full">
                              <img src={previewUrl} alt={previewLabel} className="h-full w-full object-cover" />
                            </button>
                          ) : (
                            <div className="flex h-full items-center justify-center text-xs text-slate-500">{'\u65e0\u53ef\u9884\u89c8\u56fe\u7247'}</div>
                          )}
                        </div>
                        <div className="p-3">
                          <div className="flex items-center justify-between gap-3">
                            <div className="min-w-0">
                              <div className="truncate text-sm text-white">{previewLabel}</div>
                              <div className="mt-1 text-[11px] text-slate-500">
                                {reference.model || reference.reference_token || '\u672a\u8bb0\u5f55\u6a21\u578b'}
                              </div>
                              {selectedAsset.hasStaleReferencePrompt &&
                              reference.prompt &&
                              reference.prompt.trim() !== selectedAsset.prompt.trim() ? (
                                <div className="mt-2 inline-flex rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-200">
                                  {'\u65e7\u63d0\u793a\u8bcd\u751f\u6210'}
                                </div>
                              ) : null}
                            </div>
                            <span className={`rounded-full border px-2 py-0.5 text-[11px] ${referenceStatusTone(reference.status)}`}>
                              {referenceStatusLabel(reference.status)}
                            </span>
                          </div>

                          <div className="mt-3 flex flex-wrap gap-2">
                            {previewUrl ? (
                              <button
                                type="button"
                                onClick={() => onOpenPreview(previewUrl, previewLabel)}
                                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
                              >
                                {'\u9884\u89c8'}
                              </button>
                            ) : null}
                            {reference.prompt ? (
                              <button
                                type="button"
                                onClick={() =>
                                  setReferenceSourcePromptDetail({
                                    title: previewLabel,
                                    prompt: reference.prompt ?? '',
                                    model: reference.model,
                                  })
                                }
                                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
                              >
                                {'\u67e5\u770b\u6765\u6e90'}
                              </button>
                            ) : null}
                            {typeof reference.id === 'number' && reference.status !== 'selected' ? (
                              <button
                                type="button"
                                onClick={() => onUpdateReferenceAssetStatus(reference.id, 'selected')}
                                className="rounded-lg border border-sky-800/60 px-3 py-1.5 text-xs text-sky-300 transition hover:border-sky-500 hover:text-white"
                              >
                                {'\u8bbe\u4e3a\u9ed8\u8ba4'}
                              </button>
                            ) : null}
                            {typeof reference.id === 'number' && reference.status !== 'locked' ? (
                              <button
                                type="button"
                                onClick={() => onUpdateReferenceAssetStatus(reference.id, 'locked')}
                                className="rounded-lg border border-emerald-800/60 px-3 py-1.5 text-xs text-emerald-300 transition hover:border-emerald-500 hover:text-white"
                              >
                                {'\u8bbe\u4e3a\u9501\u5b9a'}
                              </button>
                            ) : null}
                            {typeof reference.id === 'number' && reference.status === 'locked' ? (
                              <button
                                type="button"
                                onClick={() => onUpdateReferenceAssetStatus(reference.id, 'selected')}
                                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
                              >
                                {'\u53d6\u6d88\u9501\u5b9a'}
                              </button>
                            ) : null}
                            {typeof reference.id === 'number' ? (
                              <button
                                type="button"
                                onClick={() => onDeleteReferenceAsset(reference.id)}
                                className="rounded-lg border border-rose-800/60 px-3 py-1.5 text-xs text-rose-300 transition hover:border-rose-600 hover:text-white"
                              >
                                {'\u5220\u9664'}
                              </button>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    )
                  })
                ) : (
                  <div className="sm:col-span-2 rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
                    {'\u5f53\u524d\u8d44\u4ea7\u8fd8\u6ca1\u6709\u53c2\u8003\u56fe\u3002\u53ef\u4ee5\u76f4\u63a5\u5728\u8fd9\u91cc\u751f\u6210\uff0c\u6216\u8005\u5148\u53bb\u955c\u5934\u5de5\u4f5c\u53f0\u8865\u9f50\u7ed1\u5b9a\u540e\u518d\u56de\u6765\u7ba1\u7406\u3002'}
                  </div>
                )}
              </div>
            </div>
          </>
        ) : (
          <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
            {'\u5f53\u524d\u6ca1\u6709\u53ef\u67e5\u770b\u7684\u8d44\u4ea7\u8be6\u60c5\u3002'}
          </div>
        )}
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="text-sm font-medium text-white">{'\u8d44\u4ea7\u5f71\u54cd\u8303\u56f4'}</div>
        {selectedAsset ? (
          <div className="mt-4 space-y-4">
            <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
              <div className="text-xs text-slate-500">{'\u9636\u6bb5\u5efa\u8bae'}</div>
              <div className="mt-2 text-sm leading-6 text-slate-300">
                {selectedInsight?.missingReference
                  ? '\u5f53\u524d\u8d44\u4ea7\u4ecd\u7f3a\u5c11\u53ef\u9884\u89c8\u53c2\u8003\u56fe\uff0c\u5efa\u8bae\u4f18\u5148\u8865\u56fe\uff0c\u518d\u63a8\u8fdb\u955c\u5934\u7ed1\u5b9a\u4e0e\u7f16\u8bd1\u3002'
                  : selectedInsight && selectedInsight.shotIds.length > 0
                    ? `\u5f53\u524d\u8d44\u4ea7\u5df2\u5f71\u54cd ${selectedInsight.shotIds.length} \u4e2a\u955c\u5934\uff0c\u53ef\u4ee5\u7ee7\u7eed\u68c0\u67e5\u9ed8\u8ba4\u53c2\u8003\u3001\u9501\u5b9a\u72b6\u6001\u4e0e\u5f15\u7528\u8303\u56f4\u3002`
                    : '\u5f53\u524d\u8d44\u4ea7\u5df2\u8fdb\u5165\u8d44\u4ea7\u4e2d\u5fc3\uff0c\u4f46\u8fd8\u6ca1\u6709\u76f4\u63a5\u547d\u4e2d\u955c\u5934\u5f15\u7528\u3002'}
              </div>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-xs text-slate-500">{'\u955c\u5934\u7ed1\u5b9a'}</div>
                  <div className="mt-1 text-sm text-slate-300">{'\u5df2\u9009\u62e9'} {linkedShotDraft.length} {'\u4e2a\u955c\u5934'}</div>
                </div>
                <button
                  type="button"
                  onClick={onSaveShotBindings}
                  disabled={!selectedAsset.assetRecordId || shotBindingState === 'saving'}
                  className="rounded-lg border border-sky-500/50 px-3 py-1.5 text-xs font-medium text-sky-200 transition hover:border-sky-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {shotBindingState === 'saving' ? '\u4fdd\u5b58\u4e2d...' : '\u4fdd\u5b58\u955c\u5934\u7ed1\u5b9a'}
                </button>
              </div>

              {hasUnsyncedBindings ? (
                <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="text-xs font-medium text-amber-200">
                        {selectedAsset.shotIds.length > 0
                          ? `\u7cfb\u7edf\u8fd8\u8bc6\u522b\u5230 ${pendingBindingInsights.unsyncedShotIds.length} \u4e2a\u5f85\u540c\u6b65\u955c\u5934`
                          : `\u7cfb\u7edf\u5df2\u8bc6\u522b ${pendingBindingInsights.unsyncedShotIds.length} \u4e2a\u5f85\u540c\u6b65\u955c\u5934\uff0c\u5c1a\u672a\u5199\u56de\u8d44\u4ea7\u7ed1\u5b9a`}
                      </div>
                      <div className="mt-1 text-xs leading-5 text-amber-100/80">
                        {draftAlreadyCoversUnsyncedBindings
                          ? '\u8fd9\u4e9b\u955c\u5934\u5df2\u7ecf\u52a0\u5165\u5f53\u524d\u7ed1\u5b9a\u8349\u7a3f\uff0c\u4fdd\u5b58\u540e\u4f1a\u771f\u6b63\u5199\u56de\u8d44\u4ea7\u8bb0\u5f55\u3002'
                          : '\u53ef\u4ee5\u4e00\u952e\u52a0\u5165\u5f53\u524d\u7ed1\u5b9a\u8349\u7a3f\uff0c\u518d\u4fdd\u5b58\u4e3a\u6b63\u5f0f\u7684\u7ed3\u6784\u5316\u955c\u5934\u7ed1\u5b9a\u3002'}
                      </div>
                    </div>
                    {!draftAlreadyCoversUnsyncedBindings ? (
                      <button
                        type="button"
                        onClick={onApplyInferredShotBindings}
                        className="rounded-lg border border-amber-400/40 px-3 py-1.5 text-xs font-medium text-amber-100 transition hover:border-amber-300 hover:text-white"
                      >
                        {'\u52a0\u5165\u5f85\u540c\u6b65\u955c\u5934'}
                      </button>
                    ) : null}
                  </div>
                </div>
              ) : null}

              <div className="mt-3 space-y-2">
                {(selectedInsight?.impactShots ?? []).length > 0 ? (
                  (selectedInsight?.impactShots ?? []).map((shot) => {
                    const selected = linkedShotDraft.includes(shot.shotId)
                    return (
                      <div key={shot.shotId} className="rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-3">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <div className="text-sm font-medium text-white">
                              {formatEpisodeLabel(shot.episode)} / {'\u955c\u5934'} {shot.shotId}
                            </div>
                            <div className="mt-1 text-xs text-slate-500">{shot.sceneName}</div>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              onClick={() => onNavigateShot(shot.shotId)}
                              className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
                            >
                              {'\u53bb\u955c\u5934'}
                            </button>
                            <button
                              type="button"
                              onClick={() => onToggleShotBinding(shot.shotId)}
                              className={`rounded-lg border px-3 py-1.5 text-xs transition ${
                                selected
                                  ? 'border-sky-500/50 text-sky-200 hover:border-sky-400 hover:text-white'
                                  : 'border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white'
                              }`}
                            >
                              {selected ? '\u5df2\u7ed1\u5b9a' : '\u52a0\u5165\u7ed1\u5b9a'}
                            </button>
                          </div>
                        </div>
                        <div className="mt-2 text-xs text-slate-400">
                          {'\u72b6\u6001\uff1a'}{shot.statusLabel}{'\uff1b\u4e0b\u4e00\u6b65\uff1a'}{shot.nextAction}
                          {shot.missingItems.length > 0 ? `\uff1b\u7f3a\u9879\uff1a${shot.missingItems.join('\u3001')}` : ''}
                        </div>
                      </div>
                    )
                  })
                ) : (
                  <div className="rounded-lg border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
                    {'\u5f53\u524d\u7b5b\u9009\u6761\u4ef6\u4e0b\u8fd8\u6ca1\u6709\u53ef\u56de\u67e5\u7684\u955c\u5934\u5f71\u54cd\u8303\u56f4\u3002'}
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="mt-4 rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
            {'\u5f53\u524d\u6ca1\u6709\u53ef\u67e5\u770b\u7684\u5f71\u54cd\u8303\u56f4\u3002'}
          </div>
        )}
      </div>
      <ReferenceSourcePromptDialog
        detail={referenceSourcePromptDetail}
        onClose={() => setReferenceSourcePromptDetail(null)}
      />
    </div>
  )
}
