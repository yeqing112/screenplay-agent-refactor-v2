import { useEffect, useMemo, useState } from 'react'
import type { MediaAssetOutput, StoryboardShotOutput } from '../prototyping/sceneComposerData'
import {
  fetchCreativeTaskStatus,
  getStoryboardRecoveryKindLabel,
  readPendingStoryboardTasks,
  readShotRuntimeState,
  reconcileCreativeTask,
  removePendingStoryboardTask,
  summarizePendingStoryboardTasks,
  upsertShotExecutionSummary,
  upsertPendingStoryboardTask,
  type StoryboardRecoveryKind,
} from './productWorkspaceRecovery'
import { getStoryboardGenerationLabels, waitForCreativeTask } from './productWorkspaceGeneration'
import {
  buildPromptAuthoritySummary,
  getCompilerDiagnosticMeta,
  getPromptReferenceItems,
  getPromptReferenceScopeLabel,
  getPromptReferenceStatusLabel,
  getReferencePreviewUrl,
} from './productWorkspacePrompt'
import {
  buildCharacterBindingSummaries,
  getBindingVariantTypeLabel,
  getReferenceStatusLabel,
  normalizeReferenceAssetType,
  type ShotBindingSummary,
} from './productWorkspaceStoryboardBindings'
import type { CanvasHandoffTarget, TaskNavigateHandler } from './productWorkspaceSectionContracts'
import { getScriptDecision, type ScriptDecisionMap } from './productWorkspaceScriptDecisions'
import { buildShotReadiness, buildStoryboardGateSummary, hasDegradedPromptVersion } from './productWorkspaceStoryboard'
import {
  collectCompiledReferenceAssetIds,
  collectStructuredReferenceAssetIds,
  resolveEffectiveReferenceAssetIds,
} from './productWorkspaceStoryboardReferencePayload'

interface Props {
  bookId: number
  shotsByEpisode: Record<number, StoryboardShotOutput[]>
  scriptDecisionState: ScriptDecisionMap
  hasExplicitLockedAdaptation: boolean
  selectedShotId: string | null
  onSelectShot: (shotId: string | null) => void
  onRefresh: () => void
  onNavigateSection?: (section: 'scripts') => void
  onNavigateTaskSection?: TaskNavigateHandler
  canvasHandoff?: CanvasHandoffTarget | null
  recoveryFocus?: {
    taskId?: string | null
    recoveryKind?: 'frame' | 'video' | 'reference' | 'prompt' | null
    episode?: number | null
    shotId?: string | null
  } | null
  onDismissRecoveryFocus?: () => void
  onGenerateStoryboard?: () => void
  isGeneratingStoryboard?: boolean
}

export function buildStoryboardCanvasHandoffSummary(input: {
  handoff?: CanvasHandoffTarget | null
  shot?: StoryboardShotOutput | null
}) {
  const handoff = input.handoff
  if (!handoff) return null

  const shot = input.shot
  const episode =
    typeof shot?.episode === 'number' && Number.isFinite(shot.episode) ? shot.episode : handoff.episode ?? null
  const shotId = String(shot?.shot_id ?? handoff.shotId ?? '').trim() || null
  const sceneName = String(shot?.scene_name ?? '').trim() || null

  const contextParts: string[] = []
  if (typeof episode === 'number' && Number.isFinite(episode)) contextParts.push(`第 ${episode} 集`)
  if (shotId) contextParts.push(`镜头 ${shotId}`)
  if (sceneName) contextParts.push(sceneName)

  return {
    title:
      contextParts.length > 0
        ? `已从创作画布定位到 ${contextParts.join(' / ')}`
        : '已从创作画布定位到当前镜头上下文',
    label: handoff.handoffLabel || '继续当前镜头创作',
    detail:
      handoff.handoffDetail ||
      '当前镜头已经根据创作画布上下文自动定位，可以直接继续提示词编译、首帧生成、视频生成与结果确认。',
  }
}

type StoryboardMissingRecoveryState = {
  episode: number
  shotId: string
  taskId?: string | null
  recoveryKind?: 'frame' | 'video' | 'reference' | 'prompt' | null
}

type GenerationUiState = 'idle' | 'frame' | 'video' | 'success' | 'error'

type StoryboardCanvasPrimaryActionPlan =
  | { action: 'scripts_gate'; label: string; detail: string }
  | { action: 'tasks_prompt'; label: string; detail: string }
  | { action: 'tasks_frame'; label: string; detail: string }
  | { action: 'tasks_video'; label: string; detail: string }
  | { action: 'compile_prompts'; label: string; detail: string }
  | { action: 'generate_frame'; label: string; detail: string }
  | { action: 'generate_video'; label: string; detail: string }
  | { action: 'view_results'; label: string; detail: string }

export function buildStoryboardCanvasPrimaryActionPlan(input: {
  canGenerateFromGate: boolean
  promptRecoveryTaskId?: string | null
  frameRecoveryTaskId?: string | null
  videoRecoveryTaskId?: string | null
  hasCompiledPrompt: boolean
  hasAdoptedFrame: boolean
  hasAdoptedVideo: boolean
}) {
  if (!input.canGenerateFromGate) {
    return {
      action: 'scripts_gate',
      label: '返回剧本工作台补放行',
      detail: '当前镜头还没有满足上游放行条件，先回剧本工作台完成锁稿与放行，再继续镜头执行链路。',
    } satisfies StoryboardCanvasPrimaryActionPlan
  }

  if (input.videoRecoveryTaskId) {
    return {
      action: 'tasks_video',
      label: '去任务中心继续回收视频',
      detail: `当前镜头已有待回收视频任务 ${input.videoRecoveryTaskId}，先把结果收回来，再决定是否继续生成或采纳。`,
    } satisfies StoryboardCanvasPrimaryActionPlan
  }

  if (input.frameRecoveryTaskId) {
    return {
      action: 'tasks_frame',
      label: '去任务中心继续回收首帧',
      detail: `当前镜头已有待回收首帧任务 ${input.frameRecoveryTaskId}，建议先确认结果是否已返回。`,
    } satisfies StoryboardCanvasPrimaryActionPlan
  }

  if (input.promptRecoveryTaskId) {
    return {
      action: 'tasks_prompt',
      label: '去任务中心继续回收提示词',
      detail: `当前镜头已有待回收提示词任务 ${input.promptRecoveryTaskId}，先收口这次重编译，再继续首帧或视频链路。`,
    } satisfies StoryboardCanvasPrimaryActionPlan
  }

  if (!input.hasCompiledPrompt) {
    return {
      action: 'compile_prompts',
      label: '先重编译提示词',
      detail: '当前镜头还没有稳定提示词，先编到最新版本，再继续出图或出视频。',
    } satisfies StoryboardCanvasPrimaryActionPlan
  }

  if (!input.hasAdoptedFrame) {
    return {
      action: 'generate_frame',
      label: '先生成首帧',
      detail: '提示词已经就绪，但当前镜头还没有已采纳首帧，下一步先补齐分镜图版本。',
    } satisfies StoryboardCanvasPrimaryActionPlan
  }

  if (!input.hasAdoptedVideo) {
    return {
      action: 'generate_video',
      label: '继续生成视频',
      detail: '当前镜头已经有已采纳首帧，下一步可以直接沿用当前输入继续生成视频。',
    } satisfies StoryboardCanvasPrimaryActionPlan
  }

  return {
    action: 'view_results',
    label: '继续检查当前结果',
    detail: '当前镜头的提示词、首帧和视频都已有结果，更适合继续核对采纳状态和后续衔接。',
  } satisfies StoryboardCanvasPrimaryActionPlan
}

function formatGenerationErrorMessage(raw: string, fallback: string) {
  const message = String(raw || '').trim()
  if (!message) return fallback
  if (message.includes('An adopted first-frame image is required before generating video.')) {
    return '\u5f53\u524d\u955c\u5934\u8fd8\u6ca1\u6709\u5df2\u91c7\u7eb3\u9996\u5e27\uff0c\u4e0d\u80fd\u76f4\u63a5\u751f\u6210\u89c6\u9891\u3002\u8bf7\u5148\u751f\u6210\u5e76\u91c7\u7eb3\u4e00\u5f20\u5206\u955c\u56fe\u3002'
  }
  if (message.includes('The selected first-frame image is missing a usable preview URL.')) {
    return '\u5f53\u524d\u5df2\u91c7\u7eb3\u9996\u5e27\u7f3a\u5c11\u53ef\u7528\u9884\u89c8\u5730\u5740\uff0c\u6682\u65f6\u4e0d\u80fd\u751f\u6210\u89c6\u9891\u3002\u8bf7\u91cd\u65b0\u751f\u6210\u6216\u91cd\u65b0\u91c7\u7eb3\u9996\u5e27\u3002'
  }
  return message
}

type PromptVersionRecord = Record<string, unknown> & {
  id?: string | number
  version?: string | number
  compile_reason?: string
  prompt_static?: string
  prompt_motion?: string
  negative_prompt?: string
  is_current?: boolean
  is_locked_version?: boolean
  compiler_warnings?: string[]
  compiler_diagnostics?: StoryboardShotOutput['compiler_diagnostics']
  version_audit?: StoryboardShotOutput['prompt_version_audit']
  locked_reference_summary?: StoryboardShotOutput['locked_reference_summary']
  prompt_compile_context?: StoryboardShotOutput['prompt_compile_context']
  created_at?: string | null
}

type StoryboardRepairAction = {
  key: string
  title: string
  detail: string
  cta: string
  onClick?: () => void
  disabled?: boolean
}

type CompilerDiagnosticFocusCard = {
  key: string
  title: string
  detail: string
  items: string[]
  tone: string
}

function buildSceneBindingSummary(shot: StoryboardShotOutput | null): ShotBindingSummary | null {
  if (!shot) return null

  const sceneBinding = shot.prompt_compile_context?.asset_bindings?.scene
  const sceneAssetId = String(shot.structured_shot?.scene_asset_id || '').trim()
  const sceneReference = (shot.reference_images ?? []).find((item) => {
    const assetType = normalizeReferenceAssetType(item.asset_type)
    return assetType === 'scene' || assetType === 'location'
  })

  if (!sceneAssetId && !sceneReference) return null

  const normalizeSceneReferenceSourceLabel = (value: string) => {
    const normalized = value.trim().toLowerCase()
    if (!normalized) return '当前场景绑定'
    if (normalized === 'selected') return '默认参考'
    if (normalized === 'locked') return '已锁定'
    if (normalized === 'candidate') return '候选参考'
    if (normalized === 'rejected') return '已淘汰'
    if (normalized === 'missing') return '未绑定参考图'
    return value
  }

  const buildSceneBindingSourceSummary = () => {
    const bindingAssetId = String(sceneBinding?.asset_id || sceneAssetId || sceneReference?.asset_id || '').trim()
    if (sceneAssetId && bindingAssetId && bindingAssetId === sceneAssetId) {
      return {
        label: '正式结构化绑定',
        detail: '当前场景来自镜头结构化绑定，可作为提示词编译与版本回溯的正式场景资产关系。',
      }
    }
    if (sceneReference) {
      return {
        label: '参考图回填',
        detail: '当前场景主要通过已存在参考图回填进入编译上下文，仍建议补成正式结构化场景绑定。',
      }
    }
    return {
      label: '待确认绑定',
      detail: '当前场景还没有稳定的正式结构化绑定，建议回镜头结构化或资产中心继续收敛。',
    }
  }

  const variantScope = String(sceneBinding?.variant_scope || '').trim()
  const rawScopeLabel = String(sceneBinding?.scope_label || '').trim()
  const rawStageName = String(sceneBinding?.stage_name || '').trim()
  const scopeLabel = getBindingVariantTypeLabel(variantScope, rawScopeLabel)
  const normalizedStageName = rawStageName || rawScopeLabel || String(shot.scene_name || '').trim()
  const variantLabel =
    normalizedStageName && normalizedStageName !== scopeLabel
      ? `${scopeLabel} / ${normalizedStageName}`
      : scopeLabel || normalizedStageName || '当前场景绑定'
  const statusLabel = getReferenceStatusLabel(
    String(sceneBinding?.reference_status || sceneReference?.reference_status || 'missing'),
  )
  const referenceSourceLabel = normalizeSceneReferenceSourceLabel(String(sceneBinding?.reference_source || '').trim())
  const bindingSource = buildSceneBindingSourceSummary()
  const detail =
    normalizedStageName && normalizedStageName !== scopeLabel
      ? `${scopeLabel} · ${normalizedStageName} · ${statusLabel}`
      : `${scopeLabel || '当前场景绑定'} · ${statusLabel}`

  return {
    key: `scene-${sceneAssetId || sceneBinding?.asset_id || sceneReference?.asset_id || 'binding'}`,
    title: String(sceneBinding?.asset_name || sceneReference?.asset_name || shot.scene_name || '未命名场景'),
    detail: normalizedStageName
      ? detail
      : sceneAssetId
        ? `场景资产 ID · ${sceneAssetId}`
        : '当前场景尚未绑定结构化资产 ID',
    token: String(sceneReference?.reference_token || ''),
    status: statusLabel,
    assetId: String(sceneBinding?.asset_id || sceneAssetId || sceneReference?.asset_id || ''),
    masterLabel: String(sceneBinding?.asset_name || sceneReference?.asset_name || shot.scene_name || '未命名场景'),
    variantLabel,
    referenceSourceLabel,
    scopeLabel,
    bindingSourceLabel: bindingSource.label,
    bindingSourceDetail: bindingSource.detail,
  }
}

function buildPropBindingSummaries(shot: StoryboardShotOutput | null): ShotBindingSummary[] {
  if (!shot) return []

  const propIds = shot.structured_shot?.prop_asset_ids ?? []
  const propBindings = shot.prompt_compile_context?.asset_bindings?.props ?? []
  const propReferences = (shot.reference_images ?? []).filter(
    (item) => normalizeReferenceAssetType(item.asset_type) === 'prop',
  )
  const propUsedAssets = (shot.used_assets ?? []).filter(
    (item) => normalizeReferenceAssetType(item.asset_type) === 'prop',
  )

  const normalizePropReferenceSourceLabel = (value: string) => {
    const normalized = value.trim().toLowerCase()
    if (!normalized) return '当前道具绑定'
    if (normalized === 'selected') return '默认参考'
    if (normalized === 'locked') return '已锁定'
    if (normalized === 'candidate') return '候选参考'
    if (normalized === 'rejected') return '已淘汰'
    if (normalized === 'missing') return '未绑定参考图'
    return value
  }

  const buildPropBindingSourceSummary = (input: {
    assetId: string
    hasReference: boolean
    referenceSource?: string
  }) => {
    const normalizedPropIds = new Set((propIds ?? []).map((item) => String(item || '').trim()).filter(Boolean))
    const normalizedReferenceSource = String(input.referenceSource || '').trim().toLowerCase()

    if (input.assetId && normalizedPropIds.has(input.assetId)) {
      return {
        label: '正式结构化绑定',
        detail: '当前道具来自镜头结构化绑定，可作为提示词编译与下游镜头回溯的正式道具关系。',
      }
    }
    if (input.hasReference || normalizedReferenceSource === 'selected' || normalizedReferenceSource === 'locked') {
      return {
        label: '参考图回填',
        detail: '当前道具通过已有参考图回填进入编译上下文，仍建议补成正式结构化道具绑定。',
      }
    }
    return {
      label: '待确认绑定',
      detail: '当前道具还没有稳定的正式结构化绑定，建议回镜头结构化或资产中心继续收敛。',
    }
  }

  const namesById = new Map<string, string>()
  for (const item of propUsedAssets) {
    const id = String(item.asset_id || '').trim()
    if (id) namesById.set(id, String(item.asset_name || id))
  }
  for (const item of propBindings) {
    const id = String(item.asset_id || '').trim()
    if (id) namesById.set(id, String(item.asset_name || id))
  }
  for (const item of propReferences) {
    const id = String(item.asset_id || '').trim()
    if (id) namesById.set(id, String(item.asset_name || namesById.get(id) || id))
  }

  const summaries = new Map<string, ShotBindingSummary>()

  for (const item of propBindings) {
    const assetId = String(item.asset_id || '').trim()
    const key = assetId || String(item.reference_token || item.asset_name || Math.random())
    const title = String(item.asset_name || namesById.get(assetId) || assetId || '未命名道具')
    const statusLabel = getReferenceStatusLabel(item.reference_status)
    const variantScope = String(item.variant_scope || '').trim()
    const rawScopeLabel = String(item.scope_label || '').trim()
    const rawStageName = String(item.stage_name || '').trim()
    const scopeLabel = getBindingVariantTypeLabel(variantScope, rawScopeLabel)
    const variantLabel =
      rawStageName && rawStageName !== scopeLabel ? `${scopeLabel} / ${rawStageName}` : title ? `${scopeLabel} / ${title}` : scopeLabel
    summaries.set(key, {
      key: `prop-${key}`,
      title,
      detail:
        rawStageName && rawStageName !== scopeLabel
          ? `${scopeLabel} · ${rawStageName} · ${statusLabel}`
          : title
            ? `${scopeLabel} · ${title} · ${statusLabel}`
            : `${scopeLabel} · ${statusLabel}`,
      token: String(item.reference_token || ''),
      status: statusLabel,
      assetId,
      masterLabel: title,
      variantLabel,
      referenceSourceLabel: normalizePropReferenceSourceLabel(String(item.reference_source || '')),
      scopeLabel,
      bindingSourceLabel: buildPropBindingSourceSummary({
        assetId,
        hasReference: Boolean(item.reference_asset_id || item.reference_token || item.image_url || item.reference_status),
        referenceSource: String(item.reference_source || ''),
      }).label,
      bindingSourceDetail: buildPropBindingSourceSummary({
        assetId,
        hasReference: Boolean(item.reference_asset_id || item.reference_token || item.image_url || item.reference_status),
        referenceSource: String(item.reference_source || ''),
      }).detail,
    })
  }

  for (const item of propReferences) {
    const assetId = String(item.asset_id || '').trim()
    const key = assetId || String(item.reference_asset_id || item.reference_token || Math.random())
    if (summaries.has(key)) continue
    const title = String(item.asset_name || namesById.get(assetId) || assetId || '未命名道具')
    const scopeLabel = getBindingVariantTypeLabel('', '')
    summaries.set(key, {
      key: `prop-${key}`,
      title,
      detail: title
        ? `${scopeLabel} · ${title} · ${getReferenceStatusLabel(item.reference_status)}`
        : assetId
          ? `道具资产 ID · ${assetId}`
          : '当前道具引用未记录结构化资产 ID',
      token: String(item.reference_token || ''),
      status: getReferenceStatusLabel(item.reference_status),
      assetId,
      masterLabel: title,
      variantLabel: title ? `${scopeLabel} / ${title}` : '当前道具',
      referenceSourceLabel: '默认参考',
      scopeLabel,
      bindingSourceLabel: buildPropBindingSourceSummary({ assetId, hasReference: true }).label,
      bindingSourceDetail: buildPropBindingSourceSummary({ assetId, hasReference: true }).detail,
    })
  }

  for (const assetId of propIds) {
    const normalizedId = String(assetId || '').trim()
    if (!normalizedId || summaries.has(normalizedId)) continue
    const title = namesById.get(normalizedId) || normalizedId
    const scopeLabel = getBindingVariantTypeLabel('', '')
    summaries.set(normalizedId, {
      key: `prop-${normalizedId}`,
      title,
      detail: title && title !== normalizedId ? `${scopeLabel} · ${title} · 缺参考图` : `道具资产 ID · ${normalizedId}`,
      token: '',
      status: '缺参考图',
      assetId: normalizedId,
      masterLabel: title,
      variantLabel: title ? `${scopeLabel} / ${title}` : normalizedId,
      referenceSourceLabel: '未绑定参考图',
      scopeLabel,
      bindingSourceLabel: buildPropBindingSourceSummary({ assetId: normalizedId, hasReference: false }).label,
      bindingSourceDetail: buildPropBindingSourceSummary({ assetId: normalizedId, hasReference: false }).detail,
    })
  }

  return Array.from(summaries.values())
}

function buildCompilerMetricItems(metrics: Record<string, unknown> | undefined) {
  if (!metrics) return []

  const metricDefinitions = [
    { key: 'static_chars', label: '静态提示词字数', unit: '' },
    { key: 'motion_chars', label: '运动提示词字数', unit: '' },
    { key: 'used_asset_count', label: '本次引用资产', unit: ' 个' },
    { key: 'reference_image_count', label: '参考图载荷', unit: ' 张' },
    { key: 'warning_count', label: '告警数', unit: ' 条' },
    { key: 'blocking_count', label: '阻塞数', unit: ' 条' },
  ] as const

  return metricDefinitions
    .filter((item) => metrics[item.key] !== undefined && metrics[item.key] !== null)
    .map((item) => ({
      key: item.key,
      label: item.label,
      value: `${Number(metrics[item.key] || 0)}${item.unit}`,
    }))
}

function getDisplayAssetTypeLabel(assetType: string | undefined) {
  return getPromptReferenceScopeLabel(normalizeReferenceAssetType(assetType) || 'reference')
}

function BindingSummaryCard({ binding }: { binding: ShotBindingSummary }) {
  const isLegacyFallback = binding.bindingSourceLabel === '旧链路回填'
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-3 text-xs text-slate-300">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-300">
          {binding.scopeLabel || '当前绑定'}
        </span>
        <div className="break-all font-medium text-white">{binding.title}</div>
      </div>
      <div className="mt-2 grid gap-2 text-[11px] text-slate-400 lg:grid-cols-2">
        <div>主档案：<span className="text-slate-300">{binding.masterLabel || binding.title}</span></div>
        <div>当前变体：<span className="text-slate-300">{binding.variantLabel || '-'}</span></div>
        <div>资产 ID：<span className="break-all text-slate-300">{binding.assetId || '-'}</span></div>
        <div>参考状态：<span className="text-slate-300">{binding.status || '-'}</span></div>
        <div>绑定来源：<span className="text-slate-300">{binding.bindingSourceLabel || '-'}</span></div>
        <div>参考来源：<span className="text-slate-300">{binding.referenceSourceLabel || '-'}</span></div>
        <div>引用 token：<span className="break-all text-slate-300">{binding.token || '-'}</span></div>
      </div>
      <div className="mt-2 break-all text-slate-500">{binding.detail}</div>
      {binding.bindingSourceDetail ? (
        <div
          className={`mt-2 text-[11px] leading-5 ${
            isLegacyFallback
              ? 'rounded-lg border border-amber-500/20 bg-amber-500/5 px-2.5 py-2 text-amber-100/80'
              : 'text-slate-500'
          }`}
        >
          {isLegacyFallback ? `历史回填：${binding.bindingSourceDetail}` : binding.bindingSourceDetail}
        </div>
      ) : null}
    </div>
  )
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mt-1 text-sm font-medium text-slate-100">{value}</div>
    </div>
  )
}

function findFailedCompilerCheck(
  checks: NonNullable<StoryboardShotOutput['compiler_diagnostics']>['checks'] | undefined,
  key: string,
) {
  return (checks ?? []).find(
    (item) => item && String(item.key || '').trim() === key && item.passed === false,
  )
}

function extractAssetNamesFromCheckDetails(details: string[] | undefined) {
  return (details ?? [])
    .map((detail) => String(detail || '').split('：', 1)[0]?.trim() || '')
    .filter(Boolean)
}

function summarizeVisualFactText(text: string | undefined, maxParts = 2) {
  const normalized = String(text || '').trim()
  if (!normalized) return ''
  const parts = normalized
    .split(/[，,。；;：:\n\r\t（）()\[\]{}|]+/)
    .map((item) => item.trim())
    .filter(Boolean)
  if (parts.length === 0) return normalized.length > 40 ? `${normalized.slice(0, 40)}...` : normalized
  return parts.slice(0, maxParts).join(' / ')
}

function summarizeCompileContractLine(line: string | undefined) {
  const text = String(line || '').trim()
  if (!text) return ''
  const separatorIndex = text.indexOf('：')
  if (separatorIndex === -1) return text.length > 88 ? `${text.slice(0, 88)}...` : text
  const head = text.slice(0, separatorIndex).trim()
  const tail = text.slice(separatorIndex + 1).trim()
  const summarizedTail = summarizeVisualFactText(tail, 3)
  return `${head}：${summarizedTail || tail}`
}

function buildCompilerDiagnosticFocusCards(
  checks: NonNullable<StoryboardShotOutput['compiler_diagnostics']>['checks'] | undefined,
): CompilerDiagnosticFocusCard[] {
  const definitions: Array<{
    key: string
    title: string
    detail: string
    tone: string
  }> = [
    {
      key: 'character_variant_state',
      title: '人物定妆继承缺失',
      detail: '当前静态提示词没有稳定吸收人物当前变体的关键事实，建议先校正人物状态，再继续出图。',
      tone: 'border-fuchsia-500/20 bg-fuchsia-500/5 text-fuchsia-100',
    },
    {
      key: 'scene_variant_state',
      title: '场景变体继承缺失',
      detail: '当前静态提示词没有稳定继承当前场景状态，容易导致场景时段、空间结构或氛围跑偏。',
      tone: 'border-cyan-500/20 bg-cyan-500/5 text-cyan-100',
    },
    {
      key: 'prop_variant_state',
      title: '道具变体继承缺失',
      detail: '当前静态提示词没有稳定继承关键道具的状态与外观，出图后容易出现道具错版或消失。',
      tone: 'border-orange-500/20 bg-orange-500/5 text-orange-100',
    },
    {
      key: 'high_importance_prop_presence',
      title: '关键道具没有进提示词',
      detail: '当前静态提示词没有把高重要度道具明确写进首帧画面，后续生成很容易漏道具或弱化叙事锚点。',
      tone: 'border-amber-500/20 bg-amber-500/5 text-amber-100',
    },
    {
      key: 'screenplay_prompt_residue',
      title: '提示词仍像对白稿',
      detail: '当前提示词仍残留对白、舞台提示或剪辑口令，不适合继续直接出图，建议先整体重编。',
      tone: 'border-rose-500/20 bg-rose-500/5 text-rose-100',
    },
  ]

  return definitions.flatMap((definition) => {
    const failedCheck = findFailedCompilerCheck(checks, definition.key)
    if (!failedCheck) return []
    return [{
      key: definition.key,
      title: definition.title,
      detail: failedCheck.message ? `${definition.detail} ${failedCheck.message}` : definition.detail,
      items: Array.isArray(failedCheck.details) ? failedCheck.details.filter(Boolean) : [],
      tone: definition.tone,
    }]
  })
}

function buildStoryboardRepairActions(input: {
  selectedShot: StoryboardShotOutput | null
  storyboardGateStatus: 'ready' | 'blocked'
  hasAdoptedFrame: boolean
  hasAdoptedVideo: boolean
  compilerWarnings: string[]
  missingReferenceBindings: ShotBindingSummary[]
  characterBindings: ShotBindingSummary[]
  hasCompilerWarnings: boolean
  hasBlockingIssues: boolean
  compilerChecks: NonNullable<StoryboardShotOutput['compiler_diagnostics']>['checks'] | undefined
  hasRecoveryTask: boolean
  onNavigateSection?: (section: 'scripts') => void
  onNavigateTaskSection?: TaskNavigateHandler
  onCompilePrompts?: () => void
  onCompilePromptsAndContinueFrame?: () => void
  onCompilePromptsAndContinueVideo?: () => void
  onGenerateFrame?: () => void
  onGenerateVideo?: () => void
}) {
  const actions: StoryboardRepairAction[] = []
  const selectedShot = input.selectedShot

  if (!selectedShot) return actions

  if (input.storyboardGateStatus !== 'ready') {
    actions.push({
      key: 'scripts-release',
      title: '先补上游放行',
      detail: '当前镜头仍受剧本锁稿或放行约束，应先回剧本工作台完成放行，再继续分镜生产。',
      cta: '回剧本工作台',
      onClick: input.onNavigateSection ? () => input.onNavigateSection?.('scripts') : undefined,
      disabled: !input.onNavigateSection,
    })
  }

  for (const binding of input.missingReferenceBindings) {
    actions.push({
      key: `asset-${binding.assetId || binding.title}`,
      title: `补齐参考图：${binding.title}`,
      detail: `当前镜头已绑定该资产，但还没有可用参考图。应先到资产中心补齐 ${binding.scopeLabel || '当前版本'}。`,
      cta: '去资产中心',
      onClick: input.onNavigateTaskSection
        ? () =>
            input.onNavigateTaskSection?.('assets', {
              episode: selectedShot.episode,
              shotId: String(selectedShot.shot_id),
              assetId: binding.assetId || null,
              assetLabel: binding.title,
              recoveryIntent: 'shot_variant_refinement',
            })
        : undefined,
      disabled: !input.onNavigateTaskSection,
    })
  }

  const variantWarningBindings = input.characterBindings.filter((binding) =>
    input.compilerWarnings.some((warning) => warning.includes(binding.title) && warning.includes('建议补一条分镜精调定妆')),
  )
  for (const binding of variantWarningBindings) {
    actions.push({
      key: `variant-${binding.assetId || binding.title}`,
      title: `补人物分镜精调定妆：${binding.title}`,
      detail: '当前镜头里该人物存在明显状态变化，继续直接出图会影响人设稳定性。建议先去资产中心补一条当前镜头状态下的分镜精调定妆，再继续编译和出图。',
      cta: '去资产中心',
      onClick: input.onNavigateTaskSection
        ? () =>
            input.onNavigateTaskSection?.('assets', {
              episode: selectedShot.episode,
              shotId: String(selectedShot.shot_id),
              assetId: binding.assetId || null,
              assetLabel: binding.title,
            })
        : undefined,
      disabled: !input.onNavigateTaskSection,
    })
  }

  const promptRepairCheck =
    findFailedCompilerCheck(input.compilerChecks, 'screenplay_prompt_residue') ||
    findFailedCompilerCheck(input.compilerChecks, 'visual_fact_target_coverage') ||
    findFailedCompilerCheck(input.compilerChecks, 'authority_prompt_inheritance') ||
    findFailedCompilerCheck(input.compilerChecks, 'character_variant_state') ||
    findFailedCompilerCheck(input.compilerChecks, 'scene_variant_state') ||
    findFailedCompilerCheck(input.compilerChecks, 'prop_variant_state') ||
    findFailedCompilerCheck(input.compilerChecks, 'high_importance_prop_presence')
  const hasScreenplayResidue = Boolean(findFailedCompilerCheck(input.compilerChecks, 'screenplay_prompt_residue'))
  const hasHighImportancePropGap = Boolean(findFailedCompilerCheck(input.compilerChecks, 'high_importance_prop_presence'))
  if (promptRepairCheck) {
    const assetNames = extractAssetNamesFromCheckDetails(promptRepairCheck.details)
    const canContinueVideo = input.storyboardGateStatus === 'ready' && input.hasAdoptedFrame && !input.hasAdoptedVideo && input.onCompilePromptsAndContinueVideo
    const canContinueFrame = input.storyboardGateStatus === 'ready' && !input.hasAdoptedFrame && input.onCompilePromptsAndContinueFrame
    const repairActionTitle = hasScreenplayResidue
      ? '重编提示词并清理对白稿残留'
      : assetNames.length > 0
        ? `重编提示词并补齐视觉事实：${assetNames.join(' / ')}`
        : hasHighImportancePropGap
          ? '重编提示词并补齐关键道具'
          : '重编提示词并补齐视觉事实'
    const repairActionDetail =
      hasScreenplayResidue
        ? '当前提示词仍像对白稿或舞台调度文本，继续出图会直接拉低首帧质量。建议基于当前结构化绑定整体重编，把结果收敛成纯画面描述后再继续。'
        : assetNames.length > 0
        ? `当前静态提示词没有稳定继承这些已绑定资产的关键视觉事实：${assetNames.join(' / ')}。建议基于当前结构化绑定重新编译，先收敛静态提示词，再决定是否继续出图。`
        : hasHighImportancePropGap
          ? '当前静态提示词没有把高重要度道具明确写进首帧画面，后续出图容易出现叙事关键物缺失。建议先重编提示词，再继续出图。'
          : '当前静态提示词没有稳定继承已绑定资产的关键视觉事实，建议基于当前结构化绑定重新编译后再继续出图。'
    actions.push({
      key: 'recompile-visual-facts',
      title: repairActionTitle,
      detail: repairActionDetail,
      cta: canContinueVideo ? '重编后继续生成视频' : canContinueFrame ? '重编后生成首帧' : '重新编译提示词',
      onClick: canContinueVideo
        ? input.onCompilePromptsAndContinueVideo
        : canContinueFrame
          ? input.onCompilePromptsAndContinueFrame
          : input.onCompilePrompts,
      disabled: canContinueVideo
        ? !input.onCompilePromptsAndContinueVideo
        : canContinueFrame
          ? !input.onCompilePromptsAndContinueFrame
          : !input.onCompilePrompts,
    })
  }

  if (input.storyboardGateStatus === 'ready' && !input.hasAdoptedFrame) {
    actions.push({
      key: 'generate-frame',
      title: '先生成首帧',
      detail: '当前镜头还没有采纳首帧，后续视频生成也无法继续，建议先补齐分镜图版本。',
      cta: '生成首帧',
      onClick: input.onGenerateFrame,
      disabled: !input.onGenerateFrame,
    })
  }

  if (input.storyboardGateStatus === 'ready' && input.hasAdoptedFrame && !input.hasAdoptedVideo) {
    actions.push({
      key: 'generate-video',
      title: '继续生成视频',
      detail: '当前镜头已有采纳首帧，但还没有采纳视频，可以直接继续当前镜头的视频生成。',
      cta: '生成视频',
      onClick: input.onGenerateVideo,
      disabled: !input.onGenerateVideo,
    })
  }

  if (input.hasCompilerWarnings || input.hasBlockingIssues) {
    actions.push({
      key: 'qa-review',
      title: '带着诊断去 QA 修复',
      detail: '当前镜头已有编译告警或阻塞问题，建议在 QA 修复里继续收敛问题并记录修复结果。',
      cta: '去 QA 修复',
      onClick: input.onNavigateTaskSection
        ? () =>
            input.onNavigateTaskSection?.('qa', {
              episode: selectedShot.episode,
              shotId: String(selectedShot.shot_id),
            })
        : undefined,
      disabled: !input.onNavigateTaskSection,
    })
  }

  if (input.hasRecoveryTask) {
    actions.push({
      key: 'task-recovery',
      title: '继续回收长任务',
      detail: '当前镜头已有待恢复任务，建议回任务中心继续跟进任务结果，不要重复提交。',
      cta: '去任务中心',
      onClick: input.onNavigateTaskSection
        ? () =>
            input.onNavigateTaskSection?.('tasks', {
              episode: selectedShot.episode,
              shotId: String(selectedShot.shot_id),
            })
        : undefined,
      disabled: !input.onNavigateTaskSection,
    })
  }

  return actions
}

function getAcceptanceStatusLabel(status: string | undefined) {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'passed' || normalized === 'approved') return '通过采纳'
  if (normalized === 'failed' || normalized === 'rejected') return '打回重做'
  if (normalized === 'pending') return '继续观察'
  return normalized ? status || '' : '未验收'
}

function getAcceptanceStatusTone(status: string | undefined) {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'passed' || normalized === 'approved') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
  if (normalized === 'failed' || normalized === 'rejected') return 'border-rose-500/30 bg-rose-500/10 text-rose-200'
  if (normalized === 'pending') return 'border-amber-500/30 bg-amber-500/10 text-amber-200'
  return 'border-slate-700 bg-slate-950/60 text-slate-300'
}

function getMediaAssetKindLabel(kind: string | undefined) {
  const normalized = String(kind || '').trim().toLowerCase()
  if (normalized === 'image') return '分镜图'
  if (normalized === 'video') return '视频'
  if (normalized === 'audio') return '音频'
  return normalized ? kind || '' : '资产'
}

function getMediaAssetStatusLabel(status: string | undefined) {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'done' || normalized === 'completed' || normalized === 'ready') return '已生成'
  if (normalized === 'running' || normalized === 'processing') return '生成中'
  if (normalized === 'error' || normalized === 'failed') return '生成失败'
  if (normalized === 'pending') return '待处理'
  return normalized ? status || '' : '未记录'
}

function getPromptCompileReasonMeta(reason: string | undefined) {
  const normalized = String(reason || '').trim()
  if (!normalized || normalized === 'manual') {
    return { label: '手动编译', detail: '由当前镜头手动触发编译。' }
  }
  if (normalized.startsWith('manual-')) {
    const manualReason = normalized.replace(/^manual-/, '').replace(/-/g, ' ').trim()
    return {
      label: '手动重编译',
      detail: manualReason ? `触发原因：${manualReason}` : '由当前镜头手动重新编译。', 
    }
  }
  if (normalized === 'history-rollback') {
    return { label: '历史回滚', detail: '从历史提示词版本恢复当前镜头。' }
  }

  const rollbackMatch = normalized.match(/^rollback:v([^:]+):(.+)$/i)
  if (rollbackMatch) {
    const sourceVersion = String(rollbackMatch[1] || '').trim()
    const rollbackReason = String(rollbackMatch[2] || '').trim()
    const rollbackReasonLabel =
      rollbackReason === 'manual-rollback'
        ? '从历史版本恢复当前镜头'
        : rollbackReason.replace(/-/g, ' ').trim()
    return {
      label: `版本回滚 · 源自 v${sourceVersion || '-'}`,
      detail: rollbackReasonLabel ? `回滚说明：${rollbackReasonLabel}` : '从历史版本恢复当前镜头。',
    }
  }

  if (normalized.startsWith('batch-')) {
    const batchReason = normalized.replace(/^batch-/, '').replace(/-/g, ' ').trim()
    return {
      label: '批量编译',
      detail: batchReason ? `批量来源：${batchReason}` : '由批量操作触发编译。',
    }
  }

  return { label: normalized, detail: '保留原始编译原因。' }
}

function getPromptRestoreReasonLabel(reason: string | undefined) {
  const normalized = String(reason || '').trim()
  if (normalized === 'latest_recoverable_version') return '最新可恢复版本'
  if (normalized === 'best_partial_recovery_version') return '最佳部分恢复版本'
  return normalized ? normalized.replace(/_/g, ' ') : '推荐恢复版本'
}

function getPromptRestoreOutcomeMeta(
  reason: string | undefined,
  audit: StoryboardShotOutput['prompt_version_audit'] | null | undefined,
) {
  const normalized = String(reason || '').trim()
  if (normalized === 'latest_recoverable_version') {
    return {
      isPartial: false,
      label: '恢复后预计可回到更健康的提示词版本。',
      tone: 'text-emerald-100/80',
    }
  }
  if (normalized === 'best_partial_recovery_version') {
    return {
      isPartial: true,
      label: `这是一次部分恢复，恢复后仍需继续处理剩余关键资产${Number(audit?.missing_critical_count ?? 0) > 0 ? `（当前缺失 ${Number(audit?.missing_critical_count ?? 0)} 个）` : ''}。`,
      tone: 'text-amber-100/80',
    }
  }
  return {
    isPartial: true,
    label: '恢复后仍建议继续复核当前镜头的关键资产引用。',
    tone: 'text-amber-100/80',
  }
}

function buildPromptVersionAuditSummary(audit: StoryboardShotOutput['prompt_version_audit'] | null | undefined) {
  if (!audit) return null
  const missingCriticalAssets = Array.isArray(audit.missing_critical_assets) ? audit.missing_critical_assets.filter(Boolean) : []
  const missingUsedAssetNames = Array.isArray(audit.missing_used_asset_names) ? audit.missing_used_asset_names.filter(Boolean) : []
  const lines: string[] = []

  if (audit.is_scene_only_candidate) {
    lines.push('当前版本接近“只有场景、缺角色/关键道具”的退化状态。')
  }
  if (missingCriticalAssets.length > 0) {
    lines.push(`缺失关键资产：${missingCriticalAssets.join(' / ')}`)
  }
  if (missingUsedAssetNames.length > 0) {
    lines.push(`used_assets 未覆盖：${missingUsedAssetNames.join(' / ')}`)
  }
  if (audit.is_recoverable_version) {
    lines.push('该版本仍可作为恢复候选。')
  }
  if (!lines.length && audit.is_degraded_version) {
    lines.push('当前版本存在结构化引用退化风险，建议复核并考虑恢复。')
  }

  return {
    missingCriticalAssets,
    missingUsedAssetNames,
    summary: lines.join(' '),
  }
}

function formatVersionTimestamp(value: string | undefined | null) {
  if (!value) return '未记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function getCompileContextReferenceSourceLabel(value: string) {
  const normalized = value.trim().toLowerCase()
  if (!normalized) return value
  if (normalized === 'selected') return '默认参考'
  if (normalized === 'locked') return '已锁定'
  if (normalized === 'candidate') return '候选参考'
  if (normalized === 'rejected') return '已淘汰'
  if (normalized === 'missing') return '未绑定参考图'
  if (normalized === 'current_makeup') return '当前精调定妆'
  if (normalized === 'current_variant') return '当前变体'
  return value
}

function sanitizeCompileContextString(key: string, value: string) {
  const trimmed = value.trim()
  if (!trimmed) return value
  if (/^episode_(\d+)_default$/i.test(trimmed)) {
    const match = trimmed.match(/^episode_(\d+)_default$/i)
    return `第${match?.[1] || '?'}集默认造型`
  }
  if (trimmed === 'episode_default') return '分集默认'
  if (trimmed === 'scene_variant') return '场景变体'
  if (trimmed === 'prop_variant') return '道具变体'
  if (trimmed === 'active_variant') return '当前变体'
  if (trimmed === 'scene_asset') return '场景资产权威源'
  if (trimmed === 'character_makeup') return '人物定妆权威源'
  if (trimmed === 'prop_asset') return '道具资产权威源'
  if (key === 'image_url' && trimmed.startsWith('data:image/')) {
    const mimeMatch = trimmed.match(/^data:(image\/[a-zA-Z0-9.+-]+);/i)
    const mimeType = mimeMatch?.[1] || 'image/*'
    return `[内嵌参考图已省略：${mimeType}]`
  }
  if (key === 'reference_status') return getPromptReferenceStatusLabel(trimmed)
  if (key === 'reference_source') return getCompileContextReferenceSourceLabel(trimmed)
  if (key === 'authority_prompt_raw' || key === 'canonical_prompt_raw') {
    return '[详细提示词已折叠，请以上方权威源摘要为准]'
  }
  if (trimmed.length > 600) {
    return `${trimmed.slice(0, 240)}... [内容过长，已截断，共 ${trimmed.length} 字符]`
  }
  return value
}

function sanitizeCompileContextForDisplay(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeCompileContextForDisplay(item))
  }

  if (!value || typeof value !== 'object') return value

  const entries = Object.entries(value as Record<string, unknown>).map(([key, itemValue]) => {
    if (key === 'reference_summary') {
      return [key, '[已省略内部引用统计，请以上方 Prompt 引用摘要为准]']
    }
    if (key === 'reference_asset_ids') {
      return [key, '[已省略内部引用 ID 列表]']
    }
    if (key === 'reference_images') {
      return [key, '[已省略参考图载荷明细，请以上方参考图预览为准]']
    }
    if (key === 'authority_prompt_parts' || key === 'canonical_prompt_parts') {
      return [key, '[已省略详细拆解，请以上方权威源摘要为准]']
    }

    if (Array.isArray(itemValue) && key === 'reference_statuses') {
      return [key, itemValue.map((status) => (typeof status === 'string' ? getPromptReferenceStatusLabel(status) : status))]
    }

    if (typeof itemValue === 'string') {
      return [key, sanitizeCompileContextString(key, itemValue)]
    }
    return [key, sanitizeCompileContextForDisplay(itemValue)]
  })

  return Object.fromEntries(entries)
}

function findLatestAdoptedAsset(items: MediaAssetOutput[] | undefined) {
  if (!Array.isArray(items) || items.length === 0) return null
  return items.find((item) => item.adopted) ?? items[items.length - 1] ?? null
}

function buildStoryboardMissingRecoveryState(
  recoveryFocus: Props['recoveryFocus'],
  shotsByEpisode: Record<number, StoryboardShotOutput[]>,
): StoryboardMissingRecoveryState | null {
  if (!recoveryFocus?.episode || !recoveryFocus?.shotId) return null
  const targetEpisode = Number(recoveryFocus.episode ?? 0) || null
  const targetShotId = String(recoveryFocus.shotId ?? '').trim()
  if (!targetEpisode || !targetShotId) return null
  const hasExactShot = (shotsByEpisode[targetEpisode] ?? []).some(
    (shot) => String(shot.shot_id) === targetShotId,
  )
  if (hasExactShot) return null
  return {
    episode: targetEpisode,
    shotId: targetShotId,
    taskId: recoveryFocus.taskId ?? null,
    recoveryKind: recoveryFocus.recoveryKind ?? null,
  }
}

function inferAcceptanceAssetKind(
  acceptanceKind: string | undefined,
  adoptedImage: MediaAssetOutput | null,
  adoptedVideo: MediaAssetOutput | null,
) {
  if (String(acceptanceKind || '').trim()) return acceptanceKind || ''
  if (adoptedVideo) return 'video'
  if (adoptedImage) return 'image'
  return ''
}

function inferAcceptanceAssetId(
  acceptanceAssetId: string | undefined,
  adoptedImage: MediaAssetOutput | null,
  adoptedVideo: MediaAssetOutput | null,
) {
  if (String(acceptanceAssetId || '').trim()) return acceptanceAssetId || ''
  if (adoptedVideo?.id) return adoptedVideo.id
  if (adoptedImage?.id) return adoptedImage.id
  return ''
}

function MediaAssetCard({ item }: { item: MediaAssetOutput }) {
  const href = String(item.previewUrl || item.uri || '').trim()

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-300">
          {getMediaAssetKindLabel(String(item.kind || ''))}
        </span>
        {item.adopted ? (
          <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-200">
            当前采纳
          </span>
        ) : null}
      </div>
      <div className="mt-2 text-sm font-medium text-white">{item.title || item.label || item.id}</div>
      <div className="mt-2 space-y-1 text-[11px] text-slate-400">
        <div>版本标签：<span className="text-slate-300">{item.label || '-'}</span></div>
        <div>生成状态：<span className="text-slate-300">{getMediaAssetStatusLabel(item.status)}</span></div>
        <div>模型：<span className="text-slate-300">{item.model || '未记录'}</span></div>
      </div>
      {href ? (
        <a href={href} target="_blank" rel="noreferrer" className="mt-2 inline-flex text-[11px] text-sky-300 transition hover:text-sky-200">
          查看原始文件
        </a>
      ) : null}
    </div>
  )
}

export default function ProductWorkspaceStoryboardSection({
  bookId: _bookId,
  shotsByEpisode,
  scriptDecisionState,
  hasExplicitLockedAdaptation,
  selectedShotId,
  onSelectShot,
  onRefresh,
  onNavigateSection,
  onNavigateTaskSection,
  canvasHandoff,
  recoveryFocus,
  onDismissRecoveryFocus,
  onGenerateStoryboard,
  isGeneratingStoryboard,
}: Props) {
  const [promptVersions, setPromptVersions] = useState<PromptVersionRecord[]>([])
  const [historyState, setHistoryState] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle')
  const [historyActionState, setHistoryActionState] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [historyActionMessage, setHistoryActionMessage] = useState('')
  const [compileActionState, setCompileActionState] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [compileActionMessage, setCompileActionMessage] = useState('')
  const [generationState, setGenerationState] = useState<GenerationUiState>('idle')
  const [generationMessage, setGenerationMessage] = useState('')
  const [frameRecoveryTaskId, setFrameRecoveryTaskId] = useState<string | null>(null)
  const [videoRecoveryTaskId, setVideoRecoveryTaskId] = useState<string | null>(null)
  const [runtimeVersion, setRuntimeVersion] = useState(0)
  const [missingRecoveryState, setMissingRecoveryState] = useState<StoryboardMissingRecoveryState | null>(() =>
    buildStoryboardMissingRecoveryState(recoveryFocus, shotsByEpisode),
  )

  const episodes = useMemo(
    () => Object.keys(shotsByEpisode).map(Number).filter((item) => Number.isFinite(item)).sort((a, b) => a - b),
    [shotsByEpisode],
  )

  const [selectedEpisode, setSelectedEpisode] = useState<number | null>(episodes[0] ?? null)

  useEffect(() => {
    if (episodes.length === 0) {
      setSelectedEpisode(null)
      if (selectedShotId) onSelectShot(null)
      return
    }

    if (selectedShotId) {
      const matchedEpisode = episodes.find((episode) =>
        (shotsByEpisode[episode] ?? []).some((shot) => String(shot.shot_id) === String(selectedShotId)),
      )
      if (matchedEpisode) {
        setSelectedEpisode(matchedEpisode)
        return
      }
    }

    const nextEpisode = episodes[0]
    setSelectedEpisode(nextEpisode)
    const nextShot = shotsByEpisode[nextEpisode]?.[0]
    if (nextShot && !selectedShotId) onSelectShot(String(nextShot.shot_id))
  }, [episodes, onSelectShot, selectedShotId, shotsByEpisode])

  const currentShots = selectedEpisode ? shotsByEpisode[selectedEpisode] ?? [] : []
  const selectedShot = useMemo(() => {
    if (!selectedShotId) return currentShots[0] ?? null
    return currentShots.find((shot) => String(shot.shot_id) === String(selectedShotId)) ?? currentShots[0] ?? null
  }, [currentShots, selectedShotId])
  const storyboardCanvasHandoffSummary = useMemo(
    () => buildStoryboardCanvasHandoffSummary({ handoff: canvasHandoff, shot: selectedShot }),
    [canvasHandoff, selectedShot],
  )
  const taskRecoveryHandoffSummary = useMemo(() => {
    if (!recoveryFocus?.taskId || !selectedShot) return null
    const recoveryKindLabel = recoveryFocus.recoveryKind
      ? getStoryboardRecoveryKindLabel(recoveryFocus.recoveryKind)
      : '创意任务'
    return {
      title: `已从任务中心定位到第 ${selectedShot.episode ?? selectedEpisode ?? '-'} 集 / 镜头 ${selectedShot.shot_id}`,
      label: `${recoveryKindLabel}恢复任务 · ${selectedShot.scene_name || '未命名场景'}`,
      detail: `当前正在承接任务 ${recoveryFocus.taskId} 的恢复链路，建议先确认当前镜头状态，再决定继续回收、重发还是回到创作画布。`,
    }
  }, [recoveryFocus, selectedEpisode, selectedShot])
  const selectedScriptDecision = useMemo(
    () => getScriptDecision(scriptDecisionState, selectedEpisode ?? selectedShot?.episode ?? null),
    [scriptDecisionState, selectedEpisode, selectedShot?.episode],
  )
  const storyboardGate = useMemo(
    () =>
      buildStoryboardGateSummary({
        hasLockedAdaptation: hasExplicitLockedAdaptation,
        hasScript: Boolean(selectedEpisode || selectedShot),
        scriptLocked: Boolean(selectedScriptDecision.lockedAt),
        scriptReleased: Boolean(selectedScriptDecision.releasedAt),
      }),
    [
      hasExplicitLockedAdaptation,
      selectedEpisode,
      selectedScriptDecision.lockedAt,
      selectedScriptDecision.releasedAt,
      selectedShot,
    ],
  )
  const selectedShotCompileContextDisplay = useMemo(
    () => sanitizeCompileContextForDisplay(selectedShot?.prompt_compile_context ?? {}),
    [selectedShot?.prompt_compile_context],
  )

  const promptReferenceItems = useMemo(() => (selectedShot ? getPromptReferenceItems(selectedShot) : []), [selectedShot])
  const promptAuthoritySummary = useMemo(
    () => (selectedShot ? buildPromptAuthoritySummary(selectedShot) : { items: [], warningCount: 0, constraintCount: 0, noteCount: 0, failureTagCount: 0 }),
    [selectedShot],
  )
  const characterBindingSummaries = useMemo(() => buildCharacterBindingSummaries(selectedShot), [selectedShot])
  const sceneBinding = useMemo(() => buildSceneBindingSummary(selectedShot), [selectedShot])
  const propBindings = useMemo(() => buildPropBindingSummaries(selectedShot), [selectedShot])
  const compilerMetricItems = useMemo(
    () => buildCompilerMetricItems((selectedShot?.compiler_diagnostics?.metrics as Record<string, unknown> | undefined) ?? undefined),
    [selectedShot?.compiler_diagnostics?.metrics],
  )
  const diagnosticMeta = useMemo(
    () => getCompilerDiagnosticMeta(selectedShot?.compiler_diagnostics?.status),
    [selectedShot?.compiler_diagnostics?.status],
  )

  const usedAssets = selectedShot?.used_assets ?? []
  const referenceImages = selectedShot?.reference_images ?? []
  const compilerChecks = selectedShot?.compiler_diagnostics?.checks ?? []
  const compilerWarnings = selectedShot?.compiler_diagnostics?.warnings ?? []
  const blockingIssues = selectedShot?.compiler_diagnostics?.blocking_issues ?? []
  const compilerFocusCards = useMemo(() => buildCompilerDiagnosticFocusCards(compilerChecks), [compilerChecks])
  const promptVersionAudit = selectedShot?.prompt_version_audit ?? null
  const recommendedRestoreVersion = selectedShot?.recommended_restore_version ?? null
  const restoreOutcomeMeta = getPromptRestoreOutcomeMeta(recommendedRestoreVersion?.reason, promptVersionAudit)
  const promptVersionAuditSummary = useMemo(
    () => buildPromptVersionAuditSummary(promptVersionAudit),
    [promptVersionAudit],
  )
  const compileContextWarnings = selectedShot?.prompt_compile_context?.warnings ?? []
  const acceptanceFeedback = selectedShot?.prompt_compile_context?.acceptance_feedback ?? null
  const compilePromptContract = selectedShot?.prompt_compile_context?.compile_prompt_contract ?? null
  const compileVisualFactTargets = (
    selectedShot?.prompt_compile_context?.visual_fact_targets
    ?? compilePromptContract?.visual_fact_targets
    ?? []
  ).filter((item) => item && (item.asset_name || item.asset_id))
  const compileRequiredUsedAssets = (
    selectedShot?.prompt_compile_context?.required_used_assets
    ?? compilePromptContract?.required_used_assets
    ?? []
  ).filter((item) => item && (item.asset_name || item.asset_id))
  const compilePromptSummaryLines = (
    compilePromptContract?.summary_lines
    ?? []
  ).filter(Boolean)
  const imageAssets = selectedShot?.assets?.images ?? []
  const videoAssets = selectedShot?.assets?.videos ?? []
  const adoptedImage = useMemo(() => findLatestAdoptedAsset(imageAssets), [imageAssets])
  const adoptedVideo = useMemo(() => findLatestAdoptedAsset(videoAssets), [videoAssets])
  const referenceAssetIds = useMemo(() => collectStructuredReferenceAssetIds(selectedShot), [selectedShot])
  const compiledReferenceAssetIds = useMemo(() => collectCompiledReferenceAssetIds(selectedShot), [selectedShot])
  const effectiveReferencePayload = useMemo(() => resolveEffectiveReferenceAssetIds(selectedShot), [selectedShot])
  const effectiveReferenceAssetIds = effectiveReferencePayload.assetIds
  const acceptance = selectedShot?.acceptance ?? null
  const acceptanceAssetKind = inferAcceptanceAssetKind(acceptance?.asset_kind, adoptedImage, adoptedVideo)
  const acceptanceAssetId = inferAcceptanceAssetId(acceptance?.asset_id, adoptedImage, adoptedVideo)
  const hasAdoptedFrame = Boolean(adoptedImage)
  const predictedVideoTaskMode =
    hasAdoptedFrame ? 'image_to_video' : effectiveReferenceAssetIds.length > 0 ? 'reference_to_video' : 'text_to_video'
  const hasReferencePayloadDrift =
    referenceAssetIds.length !== compiledReferenceAssetIds.length ||
    referenceAssetIds.some((item) => !compiledReferenceAssetIds.includes(item))
  const hasRecoveryTask = Boolean(frameRecoveryTaskId || videoRecoveryTaskId)
  const selectedShotRuntime = useMemo(
    () =>
      selectedShot?.episode && selectedShot?.shot_id
        ? readShotRuntimeState(_bookId, selectedShot.episode, String(selectedShot.shot_id))
        : { latestExecutionSummary: null, pendingTasks: [] },
    [_bookId, runtimeVersion, selectedShot?.episode, selectedShot?.shot_id],
  )
  const selectedShotPendingSummary = useMemo(
    () => summarizePendingStoryboardTasks(selectedShotRuntime.pendingTasks),
    [selectedShotRuntime.pendingTasks],
  )
  const promptRecoveryTaskId =
    selectedShotRuntime.pendingTasks.find((item) => item.kind === 'prompt')?.taskId ?? null
  const isGenerationBusy = generationState === 'frame' || generationState === 'video'
  const canGenerateFromGate = storyboardGate.status === 'ready'
  const hasCompiledPrompt = Boolean(
    selectedShot?.prompt_version ||
      String(selectedShot?.visual_prompt_static || '').trim() ||
      String(selectedShot?.visual_prompt_motion || '').trim(),
  )
  const storyboardCanvasPrimaryActionPlan = useMemo(
    () =>
      canvasHandoff
        ? buildStoryboardCanvasPrimaryActionPlan({
            canGenerateFromGate,
            promptRecoveryTaskId,
            frameRecoveryTaskId,
            videoRecoveryTaskId,
            hasCompiledPrompt,
            hasAdoptedFrame,
            hasAdoptedVideo: Boolean(adoptedVideo),
          })
        : null,
    [
      adoptedVideo,
      canGenerateFromGate,
      canvasHandoff,
      frameRecoveryTaskId,
      hasAdoptedFrame,
      hasCompiledPrompt,
      promptRecoveryTaskId,
      videoRecoveryTaskId,
    ],
  )
  const missingReferenceBindings = useMemo(
    () =>
      [
        ...characterBindingSummaries,
        ...(sceneBinding ? [sceneBinding] : []),
        ...propBindings,
      ].filter(
        (binding) =>
          String(binding.status || '').trim() === '缺参考图' &&
          binding.actionableMissingReference !== false,
      ),
    [characterBindingSummaries, propBindings, sceneBinding],
  )
  const repairActions = useMemo(
    () =>
      buildStoryboardRepairActions({
        selectedShot,
        storyboardGateStatus: storyboardGate.status,
        hasAdoptedFrame,
        hasAdoptedVideo: Boolean(adoptedVideo),
        compilerWarnings,
        missingReferenceBindings,
        characterBindings: characterBindingSummaries,
        hasCompilerWarnings: compilerWarnings.length > 0 || compileContextWarnings.length > 0,
        hasBlockingIssues: blockingIssues.length > 0,
        compilerChecks,
        hasRecoveryTask,
        onNavigateSection,
        onNavigateTaskSection,
        onCompilePrompts:
          canGenerateFromGate && compileActionState !== 'saving'
            ? () => { void compileSelectedShotPrompts() }
            : undefined,
        onCompilePromptsAndContinueFrame:
          canGenerateFromGate && compileActionState !== 'saving' && !isGenerationBusy
            ? () => { void runPromptRepairAndContinue('frame') }
            : undefined,
        onCompilePromptsAndContinueVideo:
          canGenerateFromGate && hasAdoptedFrame && !isGenerationBusy
            ? () => { void runPromptRepairAndContinue('video') }
            : undefined,
        onGenerateFrame:
          canGenerateFromGate && !isGenerationBusy ? () => { void runStoryboardGeneration('frame') } : undefined,
        onGenerateVideo:
          canGenerateFromGate && hasAdoptedFrame && !isGenerationBusy ? () => { void runStoryboardGeneration('video') } : undefined,
      }),
    [
      adoptedVideo,
      blockingIssues.length,
      canGenerateFromGate,
      characterBindingSummaries,
      compilerWarnings,
      compilerChecks,
      compileContextWarnings.length,
      compileActionState,
      compilerWarnings.length,
      hasAdoptedFrame,
      hasRecoveryTask,
      isGenerationBusy,
      missingReferenceBindings,
      onNavigateSection,
      onNavigateTaskSection,
      propBindings,
      sceneBinding,
      selectedShot,
      storyboardGate.status,
    ],
  )

  const syncRecoveryTaskIds = () => {
    if (!selectedShot?.episode || !selectedShot?.shot_id) {
      setFrameRecoveryTaskId(null)
      setVideoRecoveryTaskId(null)
      setRuntimeVersion((current) => current + 1)
      return
    }
    const tasks = readPendingStoryboardTasks(_bookId).filter(
      (item) => item.episode === selectedShot.episode && String(item.shotId) === String(selectedShot.shot_id),
    )
    setFrameRecoveryTaskId(tasks.find((item) => item.kind === 'frame')?.taskId ?? null)
    setVideoRecoveryTaskId(tasks.find((item) => item.kind === 'video')?.taskId ?? null)
    setRuntimeVersion((current) => current + 1)
  }

  const persistShotExecutionSummary = (
    action: 'compile' | 'frame' | 'video',
    label: string,
    options?: {
      generationChain?: string | null
      promptVersion?: number | null
      taskId?: string | null
    },
  ) => {
    if (!selectedShot?.episode || !selectedShot?.shot_id) return
    upsertShotExecutionSummary(_bookId, {
      episode: selectedShot.episode,
      shotId: String(selectedShot.shot_id),
      action,
      label,
      generationChain: options?.generationChain ?? null,
      promptVersion: options?.promptVersion ?? null,
      taskId: options?.taskId ?? null,
      updatedAt: new Date().toISOString(),
    })
    setRuntimeVersion((current) => current + 1)
  }

  const compileSelectedShotPrompts = async (compileReason = 'manual-visual-fact-repair') => {
    if (!selectedShot?.episode || !selectedShot?.shot_id) return { status: 'invalid' as const }
    setCompileActionState('saving')
    setCompileActionMessage('正在提交当前镜头提示词重编译任务，通常需要 30-60 秒。')

    let promptTaskId = ''
    try {
      const response = await fetch(`/api/books/${_bookId}/storyboard/${selectedShot.episode}/${selectedShot.shot_id}/compile-prompts/async`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ compileReason, force: false }),
      })
      if (!response.ok) {
        let detail = ''
        try {
          const payload = await response.json()
          detail = String(payload?.detail || payload?.error || '').trim()
        } catch {
          detail = await response.text()
        }
        throw new Error(detail || `HTTP ${response.status}`)
      }

      const payload = await response.json()
      promptTaskId = String(payload?.task_id || '').trim()
      if (!promptTaskId) {
        throw new Error('未能获取提示词重编译任务号。')
      }

      upsertPendingStoryboardTask(_bookId, {
        taskId: promptTaskId,
        episode: selectedShot.episode,
        shotId: String(selectedShot.shot_id),
        kind: 'prompt',
        updatedAt: new Date().toISOString(),
      })

      setCompileActionMessage(`已提交重编译任务，正在后台执行。任务 ID：${promptTaskId}`)

      const settled = await waitForCreativeTask(
        promptTaskId,
        async (currentTaskId) => {
          const taskResponse = await fetch(`/api/storyboard-prompt-compile-tasks/${currentTaskId}`)
          if (!taskResponse.ok) {
            let detail = ''
            try {
              const taskPayload = await taskResponse.json()
              detail = String(taskPayload?.detail || taskPayload?.error || '').trim()
            } catch {
              detail = await taskResponse.text()
            }
            throw new Error(detail || `HTTP ${taskResponse.status}`)
          }
          return await taskResponse.json()
        },
        {
          softTimeoutMs: 45000,
          pollIntervalMs: 1000,
          maxAttempts: 90,
        },
      )

      if (settled.status === 'done') {
        removePendingStoryboardTask(_bookId, promptTaskId)
        await reloadPromptVersions()
        await onRefresh()
        setCompileActionState('success')
        setCompileActionMessage(
          `已重新编译到 v${String(settled?.version ?? settled?.prompt_version ?? '-')}${settled?.repair_attempted ? '，并已执行自动修复复编。' : '。'}`,
        )
        persistShotExecutionSummary('compile', `提示词重编译 v${String(settled?.version ?? settled?.prompt_version ?? '-')}`, {
          promptVersion:
            typeof settled?.version === 'number'
              ? settled.version
              : typeof settled?.prompt_version === 'number'
                ? settled.prompt_version
                : null,
          taskId: promptTaskId,
        })
        syncRecoveryTaskIds()
        return {
          status: 'done' as const,
          taskId: promptTaskId,
          version:
            typeof settled?.version === 'number'
              ? settled.version
              : typeof settled?.prompt_version === 'number'
                ? settled.prompt_version
                : null,
          reason: compileReason,
        }
      }

      if (settled.status === 'soft_timeout') {
        setCompileActionState('success')
        setCompileActionMessage(`重编译任务仍在后台执行，可稍后刷新查看新版本。任务 ID：${promptTaskId}`)
        syncRecoveryTaskIds()
        return { status: 'pending' as const, taskId: promptTaskId, reason: compileReason }
      }

      const settledError = 'error' in settled ? String(settled.error || '') : ''
      throw new Error(settledError || `提示词重编译失败，任务 ID：${promptTaskId}`)
    } catch (error) {
      setCompileActionState('error')
      const message = error instanceof Error ? error.message : '重新编译失败，请稍后重试。'
      setCompileActionMessage(message)
      return { status: 'error' as const, message, reason: compileReason }
    }
  }

  const runPromptRepairAndContinue = async (nextKind: 'frame' | 'video') => {
    const compileResult = await compileSelectedShotPrompts(
      nextKind === 'video' ? 'manual-recompile-before-video' : 'manual-recompile-before-frame',
    )
    if (compileResult?.status !== 'done') return
    await runStoryboardGeneration(nextKind, {
      generationChain: nextKind === 'video' ? 'recompile_then_video' : 'recompile_then_frame',
      triggeredByPromptRecompile: true,
      promptRecompileReason: compileResult.reason,
      promptRecompileTaskId: compileResult.taskId,
      promptRecompileVersion: typeof compileResult.version === 'number' ? compileResult.version : undefined,
    })
  }

  const runStoryboardGeneration = async (
    kind: 'frame' | 'video',
    chainMeta?: {
      generationChain?: string
      triggeredByPromptRecompile?: boolean
      promptRecompileReason?: string
      promptRecompileTaskId?: string
      promptRecompileVersion?: number
    },
  ) => {
    if (!selectedShot?.episode || !selectedShot?.shot_id) return
    const labels = getStoryboardGenerationLabels(kind)
    const targetTaskSetter = kind === 'frame' ? setFrameRecoveryTaskId : setVideoRecoveryTaskId
    setGenerationState(kind)
    setGenerationMessage(
      kind === 'frame'
        ? '\u6b63\u5728\u63d0\u4ea4\u9996\u5e27\u751f\u6210\u4efb\u52a1\uff0c\u8bf7\u4e0d\u8981\u91cd\u590d\u70b9\u51fb\u3002'
        : '\u6b63\u5728\u63d0\u4ea4\u89c6\u9891\u751f\u6210\u4efb\u52a1\uff0c\u8bf7\u4e0d\u8981\u91cd\u590d\u70b9\u51fb\u3002',
    )
    targetTaskSetter(null)

    try {
      const response = await fetch(`/api/books/${_bookId}/storyboard/${selectedShot.episode}/${selectedShot.shot_id}/${kind === 'frame' ? 'generate-frame' : 'generate-video'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(
          kind === 'frame'
            ? {
                generationChain: chainMeta?.generationChain,
                triggeredByPromptRecompile: chainMeta?.triggeredByPromptRecompile,
                promptRecompileReason: chainMeta?.promptRecompileReason,
                promptRecompileTaskId: chainMeta?.promptRecompileTaskId,
                promptRecompileVersion: chainMeta?.promptRecompileVersion,
              }
            : {
                compileIfMissing: true,
                firstFrameAssetId: String(adoptedImage?.id || '').trim(),
                referenceAssetIds: effectiveReferenceAssetIds,
                generationChain: chainMeta?.generationChain,
                triggeredByPromptRecompile: chainMeta?.triggeredByPromptRecompile,
                promptRecompileReason: chainMeta?.promptRecompileReason,
                promptRecompileTaskId: chainMeta?.promptRecompileTaskId,
                promptRecompileVersion: chainMeta?.promptRecompileVersion,
              },
        ),
      })
      if (!response.ok) {
        let detail = ''
        try {
          const payload = await response.json()
          detail = String(payload?.detail || payload?.error || '')
        } catch {
          detail = await response.text()
        }
        throw new Error(detail || `HTTP ${response.status}`)
      }

      const payload = await response.json()
      const taskId = String(payload?.task_id || '').trim()
      if (!taskId) {
        throw new Error(`\u672a\u80fd\u83b7\u53d6${labels.noun}\u4efb\u52a1\u53f7\u3002`)
      }

      upsertPendingStoryboardTask(_bookId, {
        taskId,
        episode: selectedShot.episode,
        shotId: String(selectedShot.shot_id),
        kind,
        updatedAt: new Date().toISOString(),
      })
      targetTaskSetter(taskId)

      const settled = await waitForCreativeTask(taskId, fetchCreativeTaskStatus, {
        reconcileTask: reconcileCreativeTask,
        softTimeoutMs: 45000,
      })

      if (settled.status === 'done') {
        removePendingStoryboardTask(_bookId, taskId)
        targetTaskSetter(null)
        setGenerationState('success')
        setGenerationMessage(labels.success)
        persistShotExecutionSummary(kind, kind === 'frame'
          ? chainMeta?.generationChain === 'recompile_then_frame' ? '重编后生成首帧' : '生成首帧'
          : chainMeta?.generationChain === 'recompile_then_video' ? '重编后继续生成视频' : '生成视频', {
          generationChain: chainMeta?.generationChain ?? (kind === 'frame' ? 'storyboard_generate_frame' : 'storyboard_generate_video'),
          taskId,
        })
        await onRefresh()
        return
      }

      if (settled.status === 'soft_timeout') {
        setGenerationState('error')
        setGenerationMessage(`${labels.pending} \u4efb\u52a1 ID\uff1a${taskId}`)
        return
      }

      const settledError = 'error' in settled ? String(settled.error || '') : ''
      setGenerationState('error')
      setGenerationMessage(formatGenerationErrorMessage(settledError, `${labels.action}\u5931\u8d25\uff0c\u4efb\u52a1 ID\uff1a${taskId}`))
    } catch (error) {
      const fallback = kind === 'frame' ? '\u9996\u5e27\u751f\u6210\u5931\u8d25\u3002' : '\u89c6\u9891\u751f\u6210\u5931\u8d25\u3002'
      setGenerationState('error')
      setGenerationMessage(formatGenerationErrorMessage(error instanceof Error ? error.message : '', fallback))
    } finally {
      syncRecoveryTaskIds()
    }
  }

  useEffect(() => {
    syncRecoveryTaskIds()
  }, [_bookId, selectedShot?.episode, selectedShot?.shot_id, selectedShot?.assets?.images?.length, selectedShot?.assets?.videos?.length])

  useEffect(() => {
    if (!recoveryFocus?.episode || !recoveryFocus?.shotId) return
    const nextMissingState = buildStoryboardMissingRecoveryState(recoveryFocus, shotsByEpisode)
    setMissingRecoveryState(nextMissingState)
    if (selectedEpisode !== recoveryFocus.episode) setSelectedEpisode(recoveryFocus.episode)
    if (!nextMissingState && String(selectedShotId || '') !== String(recoveryFocus.shotId)) {
      onSelectShot(String(recoveryFocus.shotId))
    }
    if (recoveryFocus.taskId) {
      if (recoveryFocus.recoveryKind === 'video') setVideoRecoveryTaskId(recoveryFocus.taskId)
      if (recoveryFocus.recoveryKind === 'frame') setFrameRecoveryTaskId(recoveryFocus.taskId)
      if (nextMissingState) {
        setGenerationState('error')
        setGenerationMessage(
          `\u6062\u590d\u4efb\u52a1 ${recoveryFocus.taskId} \u5bf9\u5e94\u7684\u955c\u5934 ${recoveryFocus.shotId} \u6682\u672a\u51fa\u73b0\u5728\u5f53\u524d\u955c\u5934\u5217\u8868\u4e2d\uff0c\u5df2\u5148\u56de\u5230\u5f53\u524d\u5206\u96c6\u4f9b\u4f60\u7ee7\u7eed\u786e\u8ba4\u3002`,
        )
      } else {
        setGenerationState('error')
        setGenerationMessage(`\u5df2\u4ece\u4efb\u52a1\u4e2d\u5fc3\u5b9a\u4f4d\u5230${recoveryFocus.recoveryKind === 'video' ? '\u89c6\u9891' : '\u9996\u5e27'}\u6062\u590d\u4efb\u52a1\uff0c\u4efb\u52a1 ID\uff1a${recoveryFocus.taskId}`)
      }
    }
  }, [onSelectShot, recoveryFocus, selectedEpisode, selectedShotId, shotsByEpisode])

  const reloadPromptVersions = async () => {
    if (!selectedShot?.episode || !selectedShot?.shot_id) return
    setHistoryState('loading')
    const response = await fetch(`/api/books/${_bookId}/storyboard/${selectedShot.episode}/${selectedShot.shot_id}/prompt-versions`)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const payload = await response.json()
    setPromptVersions(Array.isArray(payload?.versions) ? payload.versions : [])
    setHistoryState('loaded')
  }

  const rollbackPromptVersion = async (versionId: string | number | undefined) => {
    if (!selectedShot?.episode || !selectedShot?.shot_id || versionId === undefined || versionId === null) return
    setHistoryActionState('saving')
    setHistoryActionMessage('')
    try {
      const response = await fetch(
        `/api/books/${_bookId}/storyboard/${selectedShot.episode}/${selectedShot.shot_id}/prompt-versions/${versionId}/rollback`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reason: 'manual-rollback' }),
        },
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      await response.json()
      await onRefresh()
      await reloadPromptVersions()
      setHistoryActionState('success')
      setHistoryActionMessage('已回滚到所选历史版本，当前镜头详情已刷新。')
    } catch {
      setHistoryActionState('error')
      setHistoryActionMessage('历史版本回滚失败，请稍后重试。')
    }
  }

  const rollbackRecommendedPromptVersion = async () => {
    if (!selectedShot?.episode || !selectedShot?.shot_id || !recommendedRestoreVersion?.version) return
    setHistoryActionState('saving')
    setHistoryActionMessage('')
    try {
      const response = await fetch(
        `/api/books/${_bookId}/storyboard/${selectedShot.episode}/${selectedShot.shot_id}/prompt-versions/recommended-rollback`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reason: 'recommended-rollback' }),
        },
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const payload = await response.json()
      await onRefresh()
      await reloadPromptVersions()
      const nextRestoreOutcomeMeta = getPromptRestoreOutcomeMeta(
        String(payload?.recommended_restore_version?.reason || recommendedRestoreVersion.reason || ''),
        promptVersionAudit,
      )
      setHistoryActionState('success')
      setHistoryActionMessage(
        `已恢复到推荐版本 v${String(payload?.restored_from_version || recommendedRestoreVersion.version)}，原因：${getPromptRestoreReasonLabel(String(payload?.recommended_restore_version?.reason || recommendedRestoreVersion.reason || ''))}。${
          nextRestoreOutcomeMeta.isPartial ? ' 这次恢复只完成了部分收敛，仍需继续修复剩余关键资产。' : ''
        }`,
      )
    } catch {
      setHistoryActionState('error')
      setHistoryActionMessage('推荐版本恢复失败，请稍后重试。')
    }
  }

  const runStoryboardCanvasPrimaryAction = () => {
    if (!selectedShot?.episode || !selectedShot?.shot_id || !storyboardCanvasPrimaryActionPlan) return

    if (storyboardCanvasPrimaryActionPlan.action === 'scripts_gate') {
      onNavigateSection?.('scripts')
      return
    }

    if (storyboardCanvasPrimaryActionPlan.action === 'tasks_prompt') {
      onNavigateTaskSection?.('tasks', {
        episode: selectedShot.episode,
        shotId: String(selectedShot.shot_id),
        taskId: promptRecoveryTaskId ?? undefined,
        recoveryKind: promptRecoveryTaskId ? 'prompt' : undefined,
      })
      return
    }

    if (storyboardCanvasPrimaryActionPlan.action === 'tasks_frame') {
      onNavigateTaskSection?.('tasks', {
        episode: selectedShot.episode,
        shotId: String(selectedShot.shot_id),
        taskId: frameRecoveryTaskId ?? undefined,
        recoveryKind: frameRecoveryTaskId ? 'frame' : undefined,
      })
      return
    }

    if (storyboardCanvasPrimaryActionPlan.action === 'tasks_video') {
      onNavigateTaskSection?.('tasks', {
        episode: selectedShot.episode,
        shotId: String(selectedShot.shot_id),
        taskId: videoRecoveryTaskId ?? undefined,
        recoveryKind: videoRecoveryTaskId ? 'video' : undefined,
      })
      return
    }

    if (storyboardCanvasPrimaryActionPlan.action === 'compile_prompts') {
      void compileSelectedShotPrompts('canvas-handoff-recompile')
      return
    }

    if (storyboardCanvasPrimaryActionPlan.action === 'generate_frame') {
      void runStoryboardGeneration('frame')
      return
    }

    if (storyboardCanvasPrimaryActionPlan.action === 'generate_video') {
      void runStoryboardGeneration('video')
      return
    }
  }

  useEffect(() => {
    if (!selectedShot?.episode || !selectedShot?.shot_id) {
      setPromptVersions([])
      setHistoryState('idle')
      return
    }

    let cancelled = false
    setHistoryState('loading')

    reloadPromptVersions()
      .then(() => {
        if (cancelled) return
      })
      .catch(() => {
        if (cancelled) return
        setPromptVersions([])
        setHistoryState('error')
      })

    return () => {
      cancelled = true
    }
  }, [_bookId, selectedShot?.episode, selectedShot?.shot_id])

  return (
    <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-medium text-white">镜头列表</div>
            <div className="mt-1 text-xs text-slate-500">按集查看当前项目已有分镜，并进入单镜头工作台。</div>
          </div>
          <button
            type="button"
            onClick={onRefresh}
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
          >
            刷新
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {episodes.map((episode) => {
            const active = episode === selectedEpisode
            return (
              <button
                key={episode}
                type="button"
                onClick={() => {
                  setSelectedEpisode(episode)
                  const firstShot = shotsByEpisode[episode]?.[0]
                  onSelectShot(firstShot ? String(firstShot.shot_id) : null)
                }}
                className={`rounded-full border px-3 py-1 text-xs transition ${
                  active ? 'border-sky-500/40 bg-sky-500/10 text-sky-200' : 'border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white'
                }`}
              >
                第 {episode} 集
              </button>
            )
          })}
        </div>

        <div className="mt-4 space-y-2">
          {currentShots.map((shot) => {
            const active = String(shot.shot_id) === String(selectedShot?.shot_id ?? '')
            const readiness = buildShotReadiness(shot)
            const degradedPrompt = hasDegradedPromptVersion(shot)
            return (
              <button
                key={String(shot.shot_id)}
                type="button"
                onClick={() => onSelectShot(String(shot.shot_id))}
                className={`w-full rounded-xl border p-3 text-left transition ${
                  active ? 'border-sky-500/40 bg-sky-500/10' : 'border-slate-800 bg-slate-950/50 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-2">
                    <div className="text-sm font-medium text-white">{String(shot.shot_id)}</div>
                    {degradedPrompt ? (
                      <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-200">
                        提示词跑偏
                      </span>
                    ) : null}
                  </div>
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[10px] ${
                      degradedPrompt ? 'border-amber-500/30 bg-amber-500/10 text-amber-200' : 'border-slate-700 text-slate-300'
                    }`}
                  >
                    {readiness.statusLabel}
                  </span>
                </div>
                <div className="mt-2 text-sm text-slate-300">{shot.scene_name || '未命名场景'}</div>
                <div className="mt-2 text-[11px] text-slate-500">
                  图片 {(shot.assets?.images?.length ?? 0)} / 视频 {(shot.assets?.videos?.length ?? 0)} / 阻塞 {readiness.blockerCount}
                </div>
                <div className="mt-1 line-clamp-2 text-[11px] text-slate-400">
                  下一步：{readiness.nextAction}
                </div>
              </button>
            )
          })}
          {currentShots.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-6 text-center">
              <div className="text-sm text-slate-400">当前分集还没有镜头数据。</div>
              <div className="mt-3 text-xs text-slate-500">需要先完成剧本锁稿和放行，再生成分镜。</div>
              {onGenerateStoryboard ? (
                <button
                  type="button"
                  onClick={onGenerateStoryboard}
                  disabled={isGeneratingStoryboard}
                  className="mt-4 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-500 disabled:bg-blue-900/50 disabled:text-slate-500"
                >
                  {isGeneratingStoryboard ? (
                    <>
                      <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
                      生成中...
                    </>
                  ) : (
                    '一键生成分镜'
                  )}
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      <div className="space-y-6">
        {missingRecoveryState ? (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm font-medium text-amber-100">恢复目标未命中</div>
                <div className="mt-2 text-sm text-white">
                  第 {missingRecoveryState.episode} 集 / 镜头 {missingRecoveryState.shotId}
                </div>
                <div className="mt-2 text-xs leading-6 text-amber-100/85">
                  当前恢复任务对应的镜头暂未出现在镜头列表中。系统已经先带你回到第 {missingRecoveryState.episode} 集，方便继续确认该镜头是被删除、改号，还是尚未重新同步回来。
                </div>
                {missingRecoveryState.taskId ? (
                  <div className="mt-2 text-xs text-amber-100/80">任务 ID：{missingRecoveryState.taskId}</div>
                ) : null}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setMissingRecoveryState(null)}
                  className="rounded-lg border border-slate-600 bg-slate-900/60 px-3 py-1.5 text-xs font-medium text-slate-100 transition hover:border-slate-400 hover:text-white"
                >
                  查看同集镜头
                </button>
                {onNavigateTaskSection ? (
                  <button
                    type="button"
                    onClick={() =>
                      onNavigateTaskSection('tasks', {
                        episode: missingRecoveryState.episode,
                        shotId: missingRecoveryState.shotId,
                        taskId: missingRecoveryState.taskId ?? null,
                        recoveryKind: missingRecoveryState.recoveryKind ?? null,
                      })
                    }
                    className="rounded-lg border border-amber-300/60 bg-amber-300/15 px-3 py-1.5 text-xs font-medium text-white transition hover:border-amber-200 hover:bg-amber-300/20"
                  >
                    回任务中心
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={() => setMissingRecoveryState(null)}
                  className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:border-slate-500 hover:text-white"
                >
                  我知道了
                </button>
              </div>
            </div>
          </div>
        ) : null}
        {selectedShot ? (
          <>
            {storyboardCanvasHandoffSummary ? (
              <div className="rounded-xl border border-fuchsia-500/30 bg-fuchsia-500/10 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-xs font-medium tracking-wide text-fuchsia-200">创作画布承接中</div>
                    <div className="mt-2 text-sm font-medium text-white">{storyboardCanvasHandoffSummary.title}</div>
                    <div className="mt-2 text-sm text-fuchsia-100">{storyboardCanvasHandoffSummary.label}</div>
                    <div className="mt-2 text-xs leading-6 text-fuchsia-100/80">{storyboardCanvasHandoffSummary.detail}</div>
                    {storyboardCanvasPrimaryActionPlan ? (
                      <div className="mt-3 rounded-lg border border-fuchsia-400/20 bg-fuchsia-950/20 px-3 py-2">
                        <div className="text-[11px] font-medium text-fuchsia-200">承接后的首个动作</div>
                        <div className="mt-1 text-sm text-white">{storyboardCanvasPrimaryActionPlan.label}</div>
                        <div className="mt-1 text-xs leading-5 text-fuchsia-100/80">{storyboardCanvasPrimaryActionPlan.detail}</div>
                      </div>
                    ) : null}
                  </div>
                  {storyboardCanvasPrimaryActionPlan && storyboardCanvasPrimaryActionPlan.action !== 'view_results' ? (
                    <button
                      type="button"
                      onClick={runStoryboardCanvasPrimaryAction}
                      className="rounded-lg border border-fuchsia-300/40 bg-fuchsia-400/15 px-3 py-2 text-xs font-medium text-white transition hover:border-fuchsia-200 hover:bg-fuchsia-400/20"
                    >
                      {storyboardCanvasPrimaryActionPlan.label}
                    </button>
                  ) : null}
                </div>
              </div>
            ) : null}
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-lg font-semibold text-white">上游放行状态</div>
                  <div className="mt-1 text-sm text-slate-400">
                    镜头工作台需要继承剧本工作台的锁稿与放行决策，再决定当前镜头是否适合继续编译、出图和出视频。
                  </div>
                </div>
                <span
                  className={`rounded-full border px-2.5 py-1 text-xs ${
                    storyboardGate.tone === 'ready'
                      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
                      : 'border-rose-500/30 bg-rose-500/10 text-rose-200'
                  }`}
                >
                  {storyboardGate.status === 'ready' ? '已放行' : '未放行'}
                </span>
              </div>

              <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/50 p-4 text-sm leading-6 text-slate-300">
                {storyboardGate.message}
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-3">
                <MiniMetric label="当前集" value={selectedEpisode ? `第 ${selectedEpisode} 集` : '未选择'} />
                <MiniMetric label="锁稿状态" value={selectedScriptDecision.lockedAt ? '已锁稿' : '未锁稿'} />
                <MiniMetric label="分镜放行" value={selectedScriptDecision.releasedAt ? '已放行' : '未放行'} />
              </div>

              {onNavigateSection ? (
                <button
                  type="button"
                  onClick={() => onNavigateSection('scripts')}
                  className="mt-4 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 transition hover:border-sky-500 hover:text-white"
                >
                  {storyboardGate.status === 'ready' ? '回剧本工作台复核' : '返回剧本工作台补放行'}
                </button>
              ) : null}
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-lg font-semibold text-white">{selectedShot.shot_id} {selectedShot.scene_name || '未命名场景'}</div>
                  <div className="mt-1 text-sm text-slate-400">正式工作台镜头详情，优先查看提示词、绑定资产、参考图和编译权威源。</div>
                </div>
                <span className={`rounded-full border px-2.5 py-1 text-xs ${diagnosticMeta.tone}`}>
                  {diagnosticMeta.label}
                </span>
              </div>

              {taskRecoveryHandoffSummary ? (
                <div className="mt-4 rounded-xl border border-sky-500/30 bg-sky-500/10 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="text-xs font-medium tracking-wide text-sky-200">任务中心承接中</div>
                    {onDismissRecoveryFocus ? (
                      <button
                        type="button"
                        onClick={onDismissRecoveryFocus}
                        className="rounded-lg border border-sky-400/30 bg-sky-950/40 px-2.5 py-1 text-[11px] font-medium text-sky-100 transition hover:border-sky-300 hover:text-white"
                      >
                        关闭提示
                      </button>
                    ) : null}
                  </div>
                  <div className="mt-2 text-sm font-medium text-white">{taskRecoveryHandoffSummary.title}</div>
                  <div className="mt-2 text-sm text-sky-100">{taskRecoveryHandoffSummary.label}</div>
                  <div className="mt-2 text-xs leading-6 text-sky-100/80">{taskRecoveryHandoffSummary.detail}</div>
                </div>
              ) : null}

              <div className="mt-4 grid gap-3 md:grid-cols-4">
                <MiniMetric label="提示词版本" value={selectedShot.prompt_version ? `v${selectedShot.prompt_version}` : '未编译'} />
                <MiniMetric label="参考资产" value={`${referenceImages.length} 张`} />
                <MiniMetric label="分镜图版本" value={`${selectedShot.assets?.images?.length ?? 0}`} />
                <MiniMetric label="视频版本" value={`${selectedShot.assets?.videos?.length ?? 0}`} />
              </div>

              <div className="mt-5 grid gap-4 lg:grid-cols-2">
                <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                  <div className="text-xs text-slate-500">静态提示词</div>
                  <div className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-200">{selectedShot.visual_prompt_static || '当前还没有静态提示词。'}</div>
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                  <div className="text-xs text-slate-500">运动提示词</div>
                  <div className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-200">{selectedShot.visual_prompt_motion || '当前还没有运动提示词。'}</div>
                </div>
              </div>

              <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                <div className="text-xs text-slate-500">负向提示词</div>
                <div className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-200">{selectedShot.negative_prompt || '当前还没有负向提示词。'}</div>
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                  <div className="text-xs text-slate-500">当前分镜图结论</div>
                  {adoptedImage ? (
                    <div className="mt-2 text-sm text-slate-200">
                      已有当前采纳分镜图：<span className="text-white">{adoptedImage.title || adoptedImage.label || adoptedImage.id}</span>
                    </div>
                  ) : (
                    <div className="mt-2 text-sm text-slate-400">当前还没有采纳的分镜图版本。</div>
                  )}
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                  <div className="text-xs text-slate-500">当前视频结论</div>
                  {adoptedVideo ? (
                    <div className="mt-2 text-sm text-slate-200">
                      已有当前采纳视频：<span className="text-white">{adoptedVideo.title || adoptedVideo.label || adoptedVideo.id}</span>
                    </div>
                  ) : (
                    <div className="mt-2 text-sm text-slate-400">当前还没有采纳的视频版本。</div>
                  )}
                </div>
              </div>
            </div>

              <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/40 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-white">{'单镜头生成动作'}</div>
                    <div className="mt-1 text-xs text-slate-500">{'在新版镜头工作台直接发起首帧和视频任务；长任务会自动接回任务中心恢复链路。'}</div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {onNavigateTaskSection ? (
                      <button
                        type="button"
                        onClick={() =>
                          onNavigateTaskSection('canvas', {
                            episode: selectedShot.episode,
                            shotId: String(selectedShot.shot_id),
                          })
                        }
                        className="rounded-lg border border-slate-700 px-3 py-2 text-xs transition border-slate-700 text-slate-300 hover:border-sky-500 hover:text-white"
                      >
                        在创作画布查看
                      </button>
                    ) : null}
                    <button
                      type="button"
                      disabled={!canGenerateFromGate || isGenerationBusy}
                      onClick={() => { void runStoryboardGeneration('frame') }}
                      className={`rounded-lg px-3 py-2 text-xs font-medium transition ${
                        !canGenerateFromGate || isGenerationBusy
                          ? 'cursor-not-allowed border border-slate-800 bg-slate-900 text-slate-500'
                          : 'bg-emerald-600 text-white hover:bg-emerald-500'
                      }`}
                    >
                      {generationState === 'frame' ? '生成首帧中...' : '生成首帧'}
                    </button>
                    <button
                      type="button"
                      disabled={!canGenerateFromGate || !hasAdoptedFrame || isGenerationBusy}
                      onClick={() => { void runStoryboardGeneration('video') }}
                      className={`rounded-lg px-3 py-2 text-xs font-medium transition ${
                        !canGenerateFromGate || !hasAdoptedFrame || isGenerationBusy
                          ? 'cursor-not-allowed border border-slate-800 bg-slate-900 text-slate-500'
                          : 'bg-fuchsia-600 text-white hover:bg-fuchsia-500'
                      }`}
                    >
                      {generationState === 'video' ? '生成视频中...' : '生成视频'}
                    </button>
                    {onNavigateTaskSection ? (
                      <button
                        type="button"
                        disabled={!hasRecoveryTask}
                        onClick={() =>
                          onNavigateTaskSection('tasks', {
                            episode: selectedShot.episode,
                            shotId: String(selectedShot.shot_id),
                            taskId: videoRecoveryTaskId || frameRecoveryTaskId || undefined,
                            recoveryKind: videoRecoveryTaskId ? 'video' : frameRecoveryTaskId ? 'frame' : undefined,
                          })
                        }
                        className={`rounded-lg border px-3 py-2 text-xs transition ${
                          hasRecoveryTask
                            ? 'border-slate-700 text-slate-300 hover:border-sky-500 hover:text-white'
                            : 'cursor-not-allowed border-slate-800 text-slate-600'
                        }`}
                      >
                        {'去任务中心继续回收'}
                      </button>
                    ) : null}
                  </div>
                </div>

                <div className="mt-3 grid gap-3 md:grid-cols-3">
                  <MiniMetric label={'首帧状态'} value={hasAdoptedFrame ? '已有采纳首帧' : '缺采纳首帧'} />
                  <MiniMetric label={'待恢复任务'} value={`${Number(Boolean(frameRecoveryTaskId)) + Number(Boolean(videoRecoveryTaskId))} 个`} />
                  <MiniMetric label={'当前资产状态'} value={selectedShot.asset_status || 'pending'} />
                </div>

                {selectedShotRuntime.latestExecutionSummary || selectedShotRuntime.pendingTasks.length > 0 ? (
                  <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="text-xs text-slate-500">当前镜头运行态</div>
                      <div className="flex flex-wrap gap-2 text-[10px] text-slate-500">
                        {selectedShotRuntime.latestExecutionSummary?.updatedAt ? (
                          <span className="rounded-full border border-slate-800 px-2 py-0.5">
                            更新于 {new Date(selectedShotRuntime.latestExecutionSummary.updatedAt).toLocaleString('zh-CN', { hour12: false })}
                          </span>
                        ) : null}
                        {selectedShotPendingSummary.latestUpdatedAt ? (
                          <span className="rounded-full border border-slate-800 px-2 py-0.5">
                            待回收更新于 {new Date(selectedShotPendingSummary.latestUpdatedAt).toLocaleString('zh-CN', { hour12: false })}
                          </span>
                        ) : null}
                        {promptRecoveryTaskId ? (
                          <span className="rounded-full border border-slate-800 px-2 py-0.5">
                            提示词待回收
                          </span>
                        ) : null}
                      </div>
                    </div>
                    <div className="mt-3 grid gap-3 md:grid-cols-3">
                      <MiniMetric
                        label="最近执行"
                        value={selectedShotRuntime.latestExecutionSummary?.label || '未记录'}
                      />
                      <MiniMetric
                        label="待回收任务"
                        value={
                          selectedShotPendingSummary.count > 0
                            ? selectedShotPendingSummary.joinedKindLabels
                            : '无'
                        }
                      />
                      <MiniMetric
                        label="建议动作"
                        value={
                          selectedShotRuntime.pendingTasks.length > 0
                            ? '先回收任务'
                            : selectedShotRuntime.latestExecutionSummary
                              ? '继续复核结果'
                              : '可发起执行'
                        }
                      />
                    </div>
                    {promptRecoveryTaskId ? (
                      <div className="mt-3 text-[11px] text-slate-400">
                        当前镜头还有提示词重编译任务在后台执行，建议先等任务回收完成，再决定是否继续出图或出视频。
                      </div>
                    ) : null}
                    {selectedShotPendingSummary.latestTaskId && selectedShotPendingSummary.latestSourceLabel ? (
                      <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-[11px] text-slate-300">
                        最近待回收来源：{selectedShotPendingSummary.latestSourceLabel} · 任务 ID：{selectedShotPendingSummary.latestTaskId}
                      </div>
                    ) : null}
                    {selectedShotRuntime.pendingTasks.length > 0 ? (
                      <div className="mt-4 space-y-2">
                        {selectedShotRuntime.pendingTasks.slice(0, 4).map((task) => (
                          <div key={`${task.taskId}-${task.updatedAt}`} className="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-xs text-slate-300">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span>{getStoryboardRecoveryKindLabel(task.kind)} · 任务 ID：{task.taskId}</span>
                              <span className="text-slate-500">
                                {new Date(task.updatedAt).toLocaleString('zh-CN', { hour12: false })}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}

                <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                  <div className="text-xs text-slate-500">本次视频输入摘要</div>
                  <div className="mt-3 grid gap-3 md:grid-cols-3">
                    <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
                      <div className="text-[11px] text-slate-500">{'首帧来源'}</div>
                      <div className="mt-1 text-sm font-medium text-slate-100 break-all">
                        {hasAdoptedFrame ? String(adoptedImage?.title || adoptedImage?.label || adoptedImage?.id || '已采纳首帧') : '未采纳首帧'}
                      </div>
                      <div className="mt-2 break-all text-[11px] text-slate-500">
                        {hasAdoptedFrame ? `资产 ID：${String(adoptedImage?.id || '').trim() || '未记录'}` : '没有首帧时视频生成保持禁用'}
                      </div>
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
                      <div className="text-[11px] text-slate-500">{'参考图输入'}</div>
                      <div className="mt-1 text-sm font-medium text-slate-100">{`${referenceAssetIds.length} 张`}</div>
                      <div className="mt-2 break-all text-[11px] text-slate-500">
                        {referenceAssetIds.length > 0 ? referenceAssetIds.join(' / ') : '当前未记录结构化参考图 ID'}
                      </div>
                      <div className="mt-2 break-all text-[11px] text-slate-500">
                        {compiledReferenceAssetIds.length > 0
                          ? `当前编译实际使用：${compiledReferenceAssetIds.length} 张 · ${compiledReferenceAssetIds.join(' / ')}`
                          : '当前编译尚未沉淀可用参考图载荷'}
                      </div>
                      <div className="mt-2 break-all text-[11px] text-sky-200">
                        {effectiveReferenceAssetIds.length > 0
                          ? `本次视频实际提交：${effectiveReferenceAssetIds.length} 张 · ${effectiveReferenceAssetIds.join(' / ')}`
                          : '本次视频不提交静态参考图 ID'}
                      </div>
                      <div className="mt-2 break-all text-[11px] text-slate-500">
                        {effectiveReferencePayload.source === 'compiled'
                          ? '当前会优先沿用已编译版本实际使用的参考图，保证提示词、参考图与任务记录保持一致。'
                          : '当前会直接使用结构化绑定里的参考图。'}
                      </div>
                      {hasReferencePayloadDrift ? (
                        <div className="mt-2 text-[11px] text-amber-300">
                          {'结构化绑定数量与当前编译载荷不一致。本次会优先沿用已编译载荷；如果要切换到最新绑定，建议先重编提示词。'}
                        </div>
                      ) : null}
                    </div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
                      <div className="text-[11px] text-slate-500">{'任务模式'}</div>
                      <div className="mt-1 text-sm font-medium text-slate-100">{predictedVideoTaskMode}</div>
                      <div className="mt-2 break-all text-[11px] text-slate-500">
                        {'优先使用 image_to_video，其次 reference_to_video，最后 text_to_video'}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-3 text-sm text-slate-300">
                  {!canGenerateFromGate
                    ? '当前镜头仍受上游锁稿/放行约束，暂不建议直接出图或出视频。'
                    : hasAdoptedFrame
                      ? '当前镜头已具备采纳首帧，视频会显式使用这张首帧与当前结构化参考图继续生成。'
                      : '当前镜头还没有采纳首帧，视频生成按钮会保持禁用。'}
                </div>

                {generationMessage ? (
                  <div className={`mt-3 rounded-lg border px-3 py-2 text-sm ${
                    generationState === 'success'
                      ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-200'
                      : generationState === 'error'
                        ? 'border-amber-500/20 bg-amber-500/5 text-amber-100'
                        : 'border-slate-700 bg-slate-950/60 text-slate-300'
                  }`}>
                    {generationMessage}
                  </div>
                ) : null}

                {hasRecoveryTask ? (
                  <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-slate-400">
                    {frameRecoveryTaskId ? <span className="rounded-full border border-slate-700 px-2 py-1">{'首帧任务：'}{frameRecoveryTaskId}</span> : null}
                    {videoRecoveryTaskId ? <span className="rounded-full border border-slate-700 px-2 py-1">{'视频任务：'}{videoRecoveryTaskId}</span> : null}
                  </div>
                ) : null}
              </div>

            <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
              <div className="space-y-6">
                <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-medium text-white">编译诊断</div>
                    <div className="text-xs text-slate-500">当前镜头的诊断状态、检查项和量化指标</div>
                  </div>

                  {promptVersionAudit?.is_degraded_version ? (
                    <div className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium text-amber-200">当前提示词版本疑似跑偏</div>
                          <div className="mt-1 text-xs leading-5 text-amber-100/90">
                            {promptVersionAuditSummary?.summary || '当前版本存在关键资产缺失或退化风险，建议优先检查提示词历史版本。'}
                          </div>
                          <div className="mt-3 grid gap-2 sm:grid-cols-3">
                            <MiniMetric label="缺失关键资产" value={`${promptVersionAudit.missing_critical_count ?? 0} 个`} />
                            <MiniMetric label="可恢复版本" value={`${promptVersionAudit.recoverable_version_count ?? 0} 个`} />
                            <MiniMetric label="场景孤岛风险" value={promptVersionAudit.is_scene_only_candidate ? '是' : '否'} />
                          </div>
                        </div>
                        {recommendedRestoreVersion?.version ? (
                          <button
                            type="button"
                            onClick={() => { void rollbackRecommendedPromptVersion() }}
                            disabled={historyActionState === 'saving'}
                            className="rounded-lg border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-100 transition hover:border-amber-300 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            {historyActionState === 'saving'
                              ? '恢复中...'
                              : `恢复推荐版本 v${String(recommendedRestoreVersion.version)}`}
                          </button>
                        ) : null}
                      </div>
                      {recommendedRestoreVersion?.version ? (
                        <div className="mt-3 text-[11px] text-amber-100/80">
                          推荐原因：{getPromptRestoreReasonLabel(recommendedRestoreVersion.reason)}
                        </div>
                      ) : null}
                      {recommendedRestoreVersion?.version ? (
                        <div className={`mt-1 text-[11px] ${restoreOutcomeMeta.tone}`}>
                          {restoreOutcomeMeta.label}
                        </div>
                      ) : null}
                    </div>
                  ) : null}

                  {compilerChecks.length > 0 ? (
                    <div className="mt-4 space-y-2">
                      {compilerChecks.map((check, index) => {
                        const passed = check.passed !== false
                        return (
                          <div key={`${check.key || 'check'}-${index}`} className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className={`rounded-full border px-2 py-0.5 text-[11px] ${passed ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200' : 'border-amber-500/30 bg-amber-500/10 text-amber-200'}`}>
                                {passed ? '通过' : '待处理'}
                              </span>
                              <span className="text-sm text-slate-200">{check.label || check.key || `检查项 ${index + 1}`}</span>
                            </div>
                            {check.message ? <div className="mt-2 text-xs leading-5 text-slate-400">{check.message}</div> : null}
                            {Array.isArray(check.details) && check.details.length > 0 ? (
                              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-500">
                                {check.details.map((detail, detailIndex) => <li key={`${index}-${detailIndex}`}>{detail}</li>)}
                              </ul>
                            ) : null}
                          </div>
                        )
                      })}
                    </div>
                  ) : null}

                  {compilerFocusCards.length > 0 ? (
                    <div className="mt-4 grid gap-3 xl:grid-cols-2">
                      {compilerFocusCards.map((card) => (
                        <div key={card.key} className={`rounded-lg border p-4 ${card.tone}`}>
                          <div className="text-sm font-medium">{card.title}</div>
                          <div className="mt-1 text-xs leading-5 opacity-90">{card.detail}</div>
                          {card.items.length > 0 ? (
                            <ul className="mt-3 list-disc space-y-1 pl-5 text-xs opacity-90">
                              {card.items.map((item, index) => <li key={`${card.key}-${index}`}>{item}</li>)}
                            </ul>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : null}

                  {compilerWarnings.length > 0 ? (
                    <div className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                      <div className="text-xs font-medium text-amber-200">编译告警</div>
                      <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-amber-100/90">
                        {compilerWarnings.map((item, index) => <li key={`warning-${index}`}>{item}</li>)}
                      </ul>
                    </div>
                  ) : null}

                  {blockingIssues.length > 0 ? (
                    <div className="mt-4 rounded-lg border border-rose-500/20 bg-rose-500/5 p-3">
                      <div className="text-xs font-medium text-rose-200">阻塞问题</div>
                      <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-rose-100/90">
                        {blockingIssues.map((item, index) => <li key={`blocking-${index}`}>{item}</li>)}
                      </ul>
                    </div>
                  ) : null}

                  {compileContextWarnings.length > 0 ? (
                    <div className="mt-4 rounded-lg border border-slate-700 bg-slate-950/60 p-3">
                      <div className="text-xs font-medium text-slate-200">编译上下文补充提示</div>
                      <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-400">
                        {compileContextWarnings.map((item, index) => <li key={`context-warning-${index}`}>{item}</li>)}
                      </ul>
                    </div>
                  ) : null}

                  {compilerMetricItems.length > 0 ? (
                    <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                      {compilerMetricItems.map((item) => <MiniMetric key={item.key} label={item.label} value={item.value} />)}
                    </div>
                  ) : null}
                </div>

                {usedAssets.length > 0 ? (
                  <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                    <div className="text-sm font-medium text-white">本次实际引用资产</div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {usedAssets.map((asset, index) => (
                        <span
                          key={`${asset.asset_id || asset.asset_name || 'asset'}-${index}`}
                          className="rounded-full border border-slate-700 px-2 py-1 text-[11px] text-slate-300"
                        >
                          {getDisplayAssetTypeLabel(asset.asset_type)} · {asset.asset_name || asset.asset_id || '未命名资产'}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}

                {repairActions.length > 0 ? (
                  <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-sm font-medium text-white">当前修复入口</div>
                      <div className="text-xs text-slate-500">把当前镜头最该先做的动作直接串到对应工作台</div>
                    </div>
                    <div className="mt-4 grid gap-3">
                      {repairActions.map((action) => (
                        <div key={action.key} className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div className="min-w-0 flex-1">
                              <div className="text-sm text-slate-100">{action.title}</div>
                              <div className="mt-1 text-xs leading-5 text-slate-400">{action.detail}</div>
                            </div>
                            <button
                              type="button"
                              onClick={action.onClick}
                              disabled={action.disabled}
                              className={`rounded-lg border px-3 py-2 text-xs transition ${
                                action.disabled
                                  ? 'cursor-not-allowed border-slate-800 text-slate-600'
                                  : 'border-slate-700 text-slate-300 hover:border-sky-500 hover:text-white'
                              }`}
                            >
                              {action.cta}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                    {compileActionMessage ? (
                      <div
                        className={`mt-4 rounded-xl border p-3 text-sm ${
                          compileActionState === 'error'
                            ? 'border-rose-500/20 bg-rose-500/5 text-rose-200'
                            : compileActionState === 'success'
                              ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-200'
                              : 'border-slate-700 bg-slate-950/60 text-slate-300'
                        }`}
                      >
                        {compileActionMessage}
                      </div>
                    ) : null}
                  </div>
                ) : null}

                <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="text-sm font-medium text-white">编译上下文</div>

                  <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                    <div className="text-xs text-slate-500">Prompt 引用摘要</div>
                    <div className="mt-2 flex min-w-0 flex-wrap gap-2">
                      {promptReferenceItems.length > 0 ? (
                        promptReferenceItems.map((item) => (
                          <span key={item.key} className="max-w-full break-all rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">
                            {getPromptReferenceScopeLabel(item.scope)} · {item.subject}
                            {item.token ? ` · ${item.token}` : ''}
                            {item.status ? ` · ${getPromptReferenceStatusLabel(item.status)}` : ''}
                          </span>
                        ))
                      ) : (
                        <span className="text-sm text-slate-500">当前还没有可展示的锁定参考摘要。</span>
                      )}
                    </div>
                  </div>

                  {compilePromptSummaryLines.length > 0 || compileVisualFactTargets.length > 0 || compileRequiredUsedAssets.length > 0 ? (
                    <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="text-xs text-slate-500">首轮编译硬约束摘要</div>
                        <div className="flex flex-wrap gap-2 text-[10px] text-slate-500">
                          {compilePromptSummaryLines.length > 0 ? (
                            <span className="rounded-full border border-slate-800 px-2 py-0.5">
                              摘要 {compilePromptSummaryLines.length}
                            </span>
                          ) : null}
                          {compileVisualFactTargets.length > 0 ? (
                            <span className="rounded-full border border-slate-800 px-2 py-0.5">
                              目标 {compileVisualFactTargets.length}
                            </span>
                          ) : null}
                          {compileRequiredUsedAssets.length > 0 ? (
                            <span className="rounded-full border border-slate-800 px-2 py-0.5">
                              必保资产 {compileRequiredUsedAssets.length}
                            </span>
                          ) : null}
                        </div>
                      </div>

                      {compilePromptSummaryLines.length > 0 ? (
                        <details className="mt-3 rounded-lg border border-slate-800 bg-slate-950/60 p-3" open>
                          <summary className="cursor-pointer text-[11px] text-slate-300">
                            查看首轮编译摘要
                          </summary>
                          <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-slate-300">
                            {compilePromptSummaryLines.map((item, index) => (
                              <li key={`compile-contract-${index}`}>{summarizeCompileContractLine(item)}</li>
                            ))}
                          </ul>
                        </details>
                      ) : null}

                      {compileVisualFactTargets.length > 0 ? (
                        <details className="mt-3 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                          <summary className="cursor-pointer text-[11px] text-slate-300">
                            查看视觉事实目标
                          </summary>
                          <div className="mt-3 space-y-2">
                            {compileVisualFactTargets.map((target, index) => (
                              <div key={`${target.asset_id || target.asset_name || 'target'}-${index}`} className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-300">
                                    {getDisplayAssetTypeLabel(target.asset_type)}
                                  </span>
                                  <div className="text-xs text-white">{target.asset_name || target.asset_id || '未命名资产'}</div>
                                  {target.reference_token ? (
                                    <span className="break-all text-[10px] text-sky-300">{target.reference_token}</span>
                                  ) : null}
                                </div>
                                <div className="mt-2 text-[11px] text-slate-400">
                                  静态提示词至少吸收 {target.min_facts_to_include || 1} 条关键视觉事实。
                                </div>
                                {Array.isArray(target.required_facts) && target.required_facts.length > 0 ? (
                                  <>
                                    <ul className="mt-2 list-disc space-y-1 pl-5 text-[11px] text-slate-400">
                                      {target.required_facts.slice(0, 2).map((fact, factIndex) => (
                                        <li key={`${index}-preview-${factIndex}`}>{summarizeVisualFactText(fact, 2)}</li>
                                      ))}
                                    </ul>
                                    {target.required_facts.length > 2 ? (
                                      <details className="mt-2 rounded border border-slate-800 bg-slate-950/60 p-2">
                                        <summary className="cursor-pointer text-[11px] text-slate-500">
                                          查看完整视觉事实
                                        </summary>
                                        <ul className="mt-2 list-disc space-y-1 pl-5 text-[11px] text-slate-500">
                                          {target.required_facts.map((fact, factIndex) => <li key={`${index}-${factIndex}`}>{fact}</li>)}
                                        </ul>
                                      </details>
                                    ) : null}
                                  </>
                                ) : null}
                              </div>
                            ))}
                          </div>
                        </details>
                      ) : null}

                      {compileRequiredUsedAssets.length > 0 ? (
                        <details className="mt-3 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                          <summary className="cursor-pointer text-[11px] text-slate-300">
                            查看必须保留在 used_assets 的关键资产
                          </summary>
                          <div className="mt-3 flex flex-wrap gap-2">
                            {compileRequiredUsedAssets.map((asset, index) => (
                              <span
                                key={`${asset.asset_id || asset.asset_name || 'required-asset'}-${index}`}
                                className="max-w-full break-all rounded-full border border-slate-700 px-2 py-1 text-[11px] text-slate-300"
                              >
                                {getDisplayAssetTypeLabel(asset.asset_type)} · {asset.asset_name || asset.asset_id || '未命名资产'}
                                {asset.reference_token ? ` · ${asset.reference_token}` : ''}
                              </span>
                            ))}
                          </div>
                        </details>
                      ) : null}
                    </div>
                  ) : null}

                  <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                    <div className="text-xs text-slate-500">人物定妆绑定</div>
                    {characterBindingSummaries.length > 0 ? (
                      <div className="mt-2 space-y-2">
                        {characterBindingSummaries.map((binding) => <BindingSummaryCard key={binding.key} binding={binding} />)}
                      </div>
                    ) : (
                      <div className="mt-2 text-sm text-slate-500">当前镜头还没有结构化的人物定妆绑定信息。</div>
                    )}
                  </div>

                  <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                    <div className="text-xs text-slate-500">场景绑定</div>
                    {sceneBinding ? <div className="mt-2"><BindingSummaryCard binding={sceneBinding} /></div> : <div className="mt-2 text-sm text-slate-500">当前镜头还没有可展示的场景参考绑定。</div>}
                  </div>

                  <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                    <div className="text-xs text-slate-500">道具绑定</div>
                    {propBindings.length > 0 ? (
                      <div className="mt-2 space-y-2">
                        {propBindings.map((binding) => <BindingSummaryCard key={binding.key} binding={binding} />)}
                      </div>
                    ) : (
                      <div className="mt-2 text-sm text-slate-500">当前镜头还没有可展示的道具参考绑定。</div>
                    )}
                  </div>

                  {acceptanceFeedback ? (
                    <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                      <div className="text-xs text-slate-500">反馈与约束摘要</div>
                      <div className="mt-3 grid gap-3 md:grid-cols-3">
                        <MiniMetric label="失败标签" value={`${acceptanceFeedback.failure_tags?.length ?? 0} 条`} />
                        <MiniMetric label="反馈备注" value={`${acceptanceFeedback.notes?.length ?? 0} 条`} />
                        <MiniMetric label="额外约束" value={`${acceptanceFeedback.constraints?.length ?? 0} 条`} />
                      </div>
                      {Array.isArray(acceptanceFeedback.failure_tags) && acceptanceFeedback.failure_tags.length > 0 ? (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {acceptanceFeedback.failure_tags.map((tag) => (
                            <span key={tag} className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-200">
                              {tag}
                            </span>
                          ))}
                        </div>
                      ) : null}
                      {Array.isArray(acceptanceFeedback.notes) && acceptanceFeedback.notes.length > 0 ? (
                        <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-slate-400">
                          {acceptanceFeedback.notes.map((item, index) => <li key={`feedback-note-${index}`}>{item}</li>)}
                        </ul>
                      ) : null}
                      {Array.isArray(acceptanceFeedback.constraints) && acceptanceFeedback.constraints.length > 0 ? (
                        <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-slate-500">
                          {acceptanceFeedback.constraints.map((item, index) => <li key={`feedback-constraint-${index}`}>{item}</li>)}
                        </ul>
                      ) : null}
                    </div>
                  ) : null}
                </div>

                <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-medium text-white">提示词历史版本</div>
                    <div className="text-xs text-slate-500">
                      {historyState === 'loading'
                        ? '正在加载历史版本'
                        : historyState === 'error'
                          ? '历史版本加载失败'
                          : historyState === 'loaded'
                            ? `${promptVersions.length} 个版本`
                            : '当前镜头会保留编译版本记录'}
                    </div>
                  </div>

                  {promptVersions.length > 0 ? (
                    <div className="mt-4 space-y-3">
                      {promptVersions.map((version) => (
                        <details key={String(version.id || version.version || Math.random())} className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
                          <summary className="cursor-pointer text-sm text-slate-300">
                            v{String(version.version ?? '-')} · {getPromptCompileReasonMeta(version.compile_reason).label}
                          </summary>
                          <div className="mt-3 space-y-3">
                            <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                              <span className={`rounded-full border px-2 py-0.5 ${getCompilerDiagnosticMeta(version.compiler_diagnostics?.status).tone}`}>
                                {getCompilerDiagnosticMeta(version.compiler_diagnostics?.status).label}
                              </span>
                              {version.is_current ? (
                                <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-sky-200">
                                  当前版本
                                </span>
                              ) : null}
                              {version.is_locked_version ? (
                                <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-200">
                                  锁定版本
                                </span>
                              ) : null}
                              <span>创建时间：{formatVersionTimestamp(version.created_at)}</span>
                            </div>
                            <div className="text-xs leading-5 text-slate-500">
                              {getPromptCompileReasonMeta(version.compile_reason).detail}
                            </div>

                            {version.version_audit?.is_degraded_version ? (
                              <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                                <div className="text-[11px] font-medium text-amber-200">该历史版本也存在退化风险</div>
                                <div className="mt-1 text-[11px] leading-5 text-amber-100/90">
                                  {buildPromptVersionAuditSummary(version.version_audit)?.summary || '该版本存在关键资产缺失，请谨慎恢复。'}
                                </div>
                              </div>
                            ) : null}

                            {recommendedRestoreVersion?.version !== undefined &&
                            String(version.version ?? '') === String(recommendedRestoreVersion.version) ? (
                              <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3 text-[11px] text-emerald-100">
                                系统建议优先恢复到这个版本。原因：{getPromptRestoreReasonLabel(recommendedRestoreVersion.reason)}
                              </div>
                            ) : null}

                            {Array.isArray(version.locked_reference_summary?.all) && version.locked_reference_summary.all.length > 0 ? (
                              <div className="flex flex-wrap gap-2">
                                {version.locked_reference_summary.all.map((item, index) => (
                                  <span
                                    key={`${item.id || item.scope || 'ref'}-${index}`}
                                    className="rounded-full border border-slate-700 px-2 py-1 text-[11px] text-slate-300"
                                  >
                                    {item.subject || item.title || '未命名参考'}
                                    {item.token ? ` · ${item.token}` : ''}
                                    {item.status ? ` · ${getPromptReferenceStatusLabel(item.status)}` : ''}
                                  </span>
                                ))}
                              </div>
                            ) : null}

                            <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                              <div className="text-[11px] text-slate-500">静态提示词</div>
                              <div className="mt-2 whitespace-pre-wrap text-xs leading-5 text-slate-300">{String(version.prompt_static || '-')}</div>
                            </div>
                            <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                              <div className="text-[11px] text-slate-500">运动提示词</div>
                              <div className="mt-2 whitespace-pre-wrap text-xs leading-5 text-slate-300">{String(version.prompt_motion || '-')}</div>
                            </div>
                            <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                              <div className="text-[11px] text-slate-500">负向提示词</div>
                              <div className="mt-2 whitespace-pre-wrap text-xs leading-5 text-slate-300">{String(version.negative_prompt || '-')}</div>
                            </div>

                            {version.prompt_compile_context ? (
                              <details className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                                <summary className="cursor-pointer text-[11px] text-slate-400">查看当时的编译上下文</summary>
                                <pre className="mt-3 max-w-full overflow-auto rounded bg-slate-950 p-2 text-xs text-slate-300">
                                  {JSON.stringify(sanitizeCompileContextForDisplay(version.prompt_compile_context), null, 2)}
                                </pre>
                              </details>
                            ) : null}

                            <div className="flex flex-wrap gap-2">
                              <button
                                type="button"
                                onClick={() => { void rollbackPromptVersion(version.id) }}
                                disabled={historyActionState === 'saving' || Boolean(version.is_current)}
                                className="rounded-lg border border-slate-700 px-3 py-1.5 text-[11px] text-slate-300 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
                              >
                                {version.is_current
                                  ? '当前使用中'
                                  : historyActionState === 'saving'
                                    ? '回滚中...'
                                    : '回滚到此版本'}
                              </button>
                            </div>
                          </div>
                        </details>
                      ))}
                    </div>
                  ) : historyState === 'loaded' ? (
                    <div className="mt-4 rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
                      当前镜头还没有历史版本记录。
                    </div>
                  ) : historyState === 'error' ? (
                    <div className="mt-4 rounded-xl border border-rose-500/20 bg-rose-500/5 p-4 text-sm text-rose-200">
                      历史版本暂时加载失败，刷新镜头后可重试。
                    </div>
                  ) : null}

                  {historyActionMessage ? (
                    <div
                      className={`mt-4 rounded-xl border p-3 text-sm ${
                        historyActionState === 'error'
                          ? 'border-rose-500/20 bg-rose-500/5 text-rose-200'
                          : historyActionState === 'success'
                            ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-200'
                            : 'border-slate-700 bg-slate-950/60 text-slate-300'
                      }`}
                    >
                      {historyActionMessage}
                    </div>
                  ) : null}
                </div>
              </div>

              <div className="space-y-6">
                <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-medium text-white">当前验收结论</div>
                    <span className={`rounded-full border px-2.5 py-1 text-[11px] ${getAcceptanceStatusTone(acceptance?.status)}`}>
                      {getAcceptanceStatusLabel(acceptance?.status)}
                    </span>
                  </div>
                  <div className="mt-3 space-y-2 text-[11px] text-slate-400">
                    <div>验收对象：<span className="text-slate-300">{getMediaAssetKindLabel(acceptanceAssetKind)}</span></div>
                    <div>当前资产：<span className="break-all text-slate-300">{acceptanceAssetId || '未记录'}</span></div>
                    <div>最近更新时间：<span className="text-slate-300">{acceptance?.updated_at || '未记录'}</span></div>
                  </div>
                  {Array.isArray(acceptance?.failure_tags) && acceptance.failure_tags.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {acceptance.failure_tags.map((tag) => (
                        <span key={tag} className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-200">
                          {tag}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  <div className="mt-3 text-xs leading-5 text-slate-500">{acceptance?.notes || '当前还没有记录验收备注。'}</div>
                </div>

                <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="text-sm font-medium text-white">已生成分镜图</div>
                  {imageAssets.length > 0 ? (
                    <div className="mt-3 space-y-3">
                      {imageAssets.map((item) => <MediaAssetCard key={item.id} item={item} />)}
                    </div>
                  ) : (
                    <div className="mt-3 rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
                      当前还没有生成的分镜图版本。
                    </div>
                  )}
                </div>

                <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="text-sm font-medium text-white">已生成视频</div>
                  {videoAssets.length > 0 ? (
                    <div className="mt-3 space-y-3">
                      {videoAssets.map((item) => <MediaAssetCard key={item.id} item={item} />)}
                    </div>
                  ) : (
                    <div className="mt-3 rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
                      当前还没有生成的视频版本。
                    </div>
                  )}
                </div>

                <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="text-sm font-medium text-white">参考图预览</div>
                  {referenceImages.length > 0 ? (
                    <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                      {referenceImages.map((reference, index) => {
                        const previewUrl = getReferencePreviewUrl(reference)
                        return (
                          <div key={`${reference.reference_asset_id || reference.asset_id || 'reference'}-${index}`} className="min-w-0 rounded-lg border border-slate-800 bg-slate-950/70 p-2">
                            <div className="aspect-[4/3] overflow-hidden rounded bg-slate-900">
                              {previewUrl ? (
                                <img src={previewUrl} alt={reference.asset_name || reference.reference_token || '参考图'} className="h-full w-full object-cover" />
                              ) : (
                                <div className="flex h-full items-center justify-center text-xs text-slate-500">无可预览图片</div>
                              )}
                            </div>
                            <div className="mt-2 break-all text-xs text-slate-300">{reference.asset_name || reference.reference_token || '未命名参考图'}</div>
                            <div className="mt-1 break-all text-[11px] text-slate-500">
                              {getDisplayAssetTypeLabel(reference.asset_type)}
                              {reference.reference_token ? ` · ${reference.reference_token}` : ''}
                              {reference.reference_status ? ` · ${getReferenceStatusLabel(reference.reference_status)}` : ''}
                            </div>
                            {previewUrl ? (
                              <a href={previewUrl} target="_blank" rel="noreferrer" className="mt-2 inline-flex text-[11px] text-sky-300 transition hover:text-sky-200">
                                查看大图
                              </a>
                            ) : null}
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <div className="mt-3 rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
                      当前镜头还没有参考图。
                    </div>
                  )}
                </div>

                <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-sm font-medium text-white">编译权威源摘要</div>
                    <div className="flex flex-wrap gap-2 text-[11px] text-slate-400">
                      <span>绑定资产 {promptAuthoritySummary.items.length}</span>
                      <span>约束 {promptAuthoritySummary.constraintCount}</span>
                      <span>反馈 {promptAuthoritySummary.noteCount}</span>
                      <span>告警 {promptAuthoritySummary.warningCount}</span>
                    </div>
                  </div>

                  {promptAuthoritySummary.items.length > 0 ? (
                    <div className="mt-3 space-y-2">
                      {promptAuthoritySummary.items.map((item) => (
                        <details key={item.key} className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
                          <summary className="cursor-pointer list-none">
                            <div className="flex flex-wrap items-start justify-between gap-3">
                              <div className="min-w-0 flex-1">
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-300">
                                    {getPromptReferenceScopeLabel(item.scope)}
                                  </span>
                                  <div className="font-medium text-white">{item.name}</div>
                                  {item.variantLabel ? (
                                    <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-400">
                                      {item.variantLabel}
                                    </span>
                                  ) : null}
                                </div>
                                <div className="mt-2 text-xs leading-5 text-slate-500">
                                  {item.authorityPromptExcerpt || '当前还没有可展示的权威摘要。'}
                                </div>
                              </div>
                              <div className="text-[11px] text-slate-500">展开详情</div>
                            </div>
                          </summary>
                          <div className="mt-3 space-y-1 border-t border-slate-800 pt-3 text-[11px] text-slate-400">
                            <div>资产 ID：<span className="text-slate-300">{item.assetId || '-'}</span></div>
                            <div>引用 token：<span className="text-slate-300">{item.token || '-'}</span></div>
                            <div>生效版本：<span className="text-slate-300">{item.variantLabel || '-'}</span></div>
                            <div>参考来源：<span className="text-slate-300">{item.referenceSourceLabel || '-'}</span></div>
                            <div>参考状态：<span className="text-slate-300">{item.referenceStatusLabel || '-'}</span></div>
                            <div>权威来源：<span className="text-slate-300">{item.authorityPromptSource || '-'}</span></div>
                          </div>
                        </details>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-3 rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
                      当前还没有可读的编译权威源摘要。
                    </div>
                  )}

                  <details className="mt-3 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                    <summary className="cursor-pointer text-xs text-slate-400">查看原始编译上下文 JSON</summary>
                    <pre className="mt-3 max-w-full overflow-auto rounded bg-slate-950 p-2 text-xs text-slate-300">{JSON.stringify(selectedShotCompileContextDisplay, null, 2)}</pre>
                  </details>
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-6 text-sm text-slate-400">
            当前没有可查看的镜头详情。
          </div>
        )}
      </div>
    </div>
  )
}
