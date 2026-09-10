import { useEffect, useMemo, useState } from 'react'
import type { MediaAssetOutput, StoryboardShotOutput } from '../domain/bookOutputs'
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
import {
  CollapsiblePanel,
  CurrentShotActionHeader,
  DirectorShotLanguageEditor,
  MiniMetric,
  StatusPill,
  StoryboardGateStrip,
  getShotReadinessShortLabel,
} from './ProductWorkspaceStoryboardUi'
import {
  ProductWorkspaceMachinePromptExportPanel,
  type H3ProviderSubmitSummary,
} from './ProductWorkspaceMachinePromptExportPanel'
import { ProductWorkspaceStoryboardAdvancedToolsPanel } from './ProductWorkspaceStoryboardAdvancedToolsPanel'
import { ProductWorkspaceStoryboardAcceptancePanel } from './ProductWorkspaceStoryboardAcceptancePanel'
import { ProductWorkspaceStoryboardMediaPanel } from './ProductWorkspaceStoryboardMediaPanel'
import { ProductWorkspaceStoryboardContinuityPanel } from './ProductWorkspaceStoryboardContinuityPanel'
import { ProductWorkspaceStoryboardDecisionPanel } from './ProductWorkspaceStoryboardDecisionPanel'
import { ProductWorkspacePromptDraftPanel } from './ProductWorkspacePromptDraftPanel'
import {
  ProductWorkspacePromptHistoryPanel,
  buildPromptVersionAuditSummary,
  getPromptRestoreReasonLabel,
  sanitizeCompileContextForDisplay,
} from './ProductWorkspacePromptHistoryPanel'
import { ProductWorkspacePromptAuthorityPanel } from './ProductWorkspacePromptAuthorityPanel'
import { ProductWorkspaceCompileDiagnosticsPanel } from './ProductWorkspaceCompileDiagnosticsPanel'
import { ProductWorkspaceStoryboardRepairPanel } from './ProductWorkspaceStoryboardRepairPanel'
import { fetchModelRegistryDefaults, type ModelProfileRecord } from '../services/modelRegistry'

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
  hasReferenceImages?: boolean
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

  if (!input.hasAdoptedFrame && !input.hasReferenceImages) {
    return {
      action: 'generate_frame',
      label: '先生成首帧',
      detail: '提示词已经就绪，但当前镜头还没有已采纳首帧或可用参考图，下一步先补齐分镜图版本。',
    } satisfies StoryboardCanvasPrimaryActionPlan
  }

  if (!input.hasAdoptedVideo) {
    const videoInputDetail = input.hasReferenceImages
      ? '当前镜头已有多参考图，下一步可以用参考资产继续生成视频。'
      : '当前镜头已经有已采纳首帧，下一步可以直接沿用当前输入继续生成视频。'
    return {
      action: 'generate_video',
      label: '继续生成视频',
      detail: videoInputDetail,
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
  if (message.includes('A video input image is required before generating video')) {
    return '当前镜头还没有可用于视频生成的图片输入。请先生成/上传一张分镜图，或上传并锁定至少一张参考图。'
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

type MachinePromptExportPreview = {
  mode?: string
  book_id?: string | number
  episode?: string | number
  shot_id?: string | number
  api_submission?: boolean
  target_model?: string
  scene_name?: string
  director_shot_text?: string
  bound_asset_count?: number
  reference_image_count?: number
  warnings?: string[]
  system_director_shot_text?: string
  source_layers?: {
    director_shot_text_is_user_editable?: boolean
    director_shot_text_source?: string
    has_user_director_shot_override?: boolean
    has_manual_export_draft?: boolean
    manual_export_draft_updated_at?: string
    machine_prompt_is_compiled?: boolean
    model_export_is_submission_ready_but_not_submitted?: boolean
    history_export_record_id?: string | number
    is_temporary_webui_draft?: boolean
  }
  machine_prompt?: {
    schema_version?: string
    api_submission?: boolean
    visual_timeline?: Array<{
      phase?: string
      time_range_seconds?: string
      visual_action?: string
      camera_instruction?: string
      continuity_goal?: string
    }>
    continuity_constraints?: string[]
    negative_constraints?: string[]
    soundscape?: {
      overall_soundscape?: string
      non_diegetic_music?: string
    }
  }
  model_exports?: Record<
    string,
    {
      target_model?: string
      export_mode?: string
      api_submission?: boolean
      fields?: {
        integrated_multimodal_description?: string
        overall_soundscape?: string
        non_diegetic_music?: string
      }
      prompt?: string
      model_params?: Record<string, unknown>
    }
  >
}

type ProductionReadinessPreview = {
  status?: 'pass' | 'warning' | 'blocked' | string
  summary?: {
    shots?: number
    assets?: number
    blocked_items?: number
    warning_items?: number
    issue_counts?: Record<string, number>
  }
  recommended_order?: string[]
  shots?: Array<{ episode?: number; shot_id?: number | string; status?: string; issues?: Array<{ message?: string }> }>
}

type TransitionOverview = {
  items?: Array<{ shot_id?: number | string; status?: string; label?: string; next_action?: string }>
  counts?: Record<string, number>
}

type ProductionRepairPlanPreview = {
  status?: string
  confirmation_token?: string
  real_data_mutated?: boolean
  requires_operator_confirmation?: boolean
  summary?: { shot_actions?: number; asset_actions?: number; blocked_shots?: number; warning_shots?: number; missing_rollback_anchors?: number }
  shot_actions?: Array<{ action?: string; label?: string; episode?: number; shot_id?: number | string; rollback_anchor?: { version?: number; version_id?: number; kind?: string } | null; executability_suggestions?: Array<{ type?: string; recommended_duration?: number }> }>
  asset_actions?: Array<{ asset_type?: string; asset_id?: string; asset_name?: string; action?: string; label?: string; issue_codes?: string[] }>
}

type StructureGovernancePlanPreview = {
  plan_fingerprint?: string
  confirmation_token?: string
  real_data_mutated?: boolean
  summary?: { affected_shots?: number; identity_repairs?: number; diagnostics_to_mark_stale?: number }
  items?: Array<{ episode?: number; shot_id?: number | string; identity_stale?: boolean; diagnostics_stale?: boolean; operations?: string[] }>
}

type ProductionRepairTaskState = {
  task_id?: string
  status?: string
  progress?: number
  confirmation_token?: string
  results?: Array<{ episode?: number; shot_id?: number | string; status?: string; baseline_version?: number; version?: number; error?: string }>
}

type MachinePromptTemporaryDraftFields = {
  integrated_multimodal_description: string
  overall_soundscape: string
  non_diegetic_music: string
  generic_zh_video_prompt: string
}

type StoryboardImagePromptSections = NonNullable<
  NonNullable<StoryboardShotOutput['prompt_compile_context']>['model_adapter']
>['static_prompt_sections']

type ProductionExportRecordListItem = {
  id?: string | number
  summary?: string
  created_at?: string | null
  export_format?: string
  meta_info?: {
    record_type?: string
    api_submission?: boolean
    target_model?: string
    export_channel?: string
    book_id?: string | number
    episode?: number
    shot_id?: number | string
    scene_name?: string
    director_shot_text?: string
    reference_image_count?: number
    bound_asset_count?: number
    warnings?: unknown[]
    source_layers?: MachinePromptExportPreview['source_layers']
    machine_prompt?: MachinePromptExportPreview['machine_prompt']
    model_exports?: MachinePromptExportPreview['model_exports']
  }
}

function isMachinePromptRecordForShot(record: ProductionExportRecordListItem, episode: number | undefined, shotId: string | number | undefined) {
  const meta = record.meta_info ?? {}
  return (
    meta.record_type === 'storyboard_machine_prompt_export' &&
    Number(meta.episode || 0) === Number(episode || 0) &&
    String(meta.shot_id ?? '').trim() === String(shotId ?? '').trim()
  )
}

function stringifyMachinePromptParam(value: unknown) {
  if (value === undefined || value === null || value === '') return '-'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function getStoryboardPromptSectionRoleLabel(role: string | undefined) {
  const normalized = String(role || '').trim()
  if (normalized === 'scene') return '场景'
  if (normalized === 'character') return '人物'
  if (normalized === 'prop') return '道具'
  return normalized || '资产'
}

function hasStoryboardImagePromptSections(sections: StoryboardImagePromptSections | undefined | null) {
  if (!sections || sections.schema_version !== 'storyboard_image_prompt_sections_v1') return false
  return Boolean(
    String(sections.frame_focus || '').trim() ||
      sections.asset_anchors?.length ||
      String(sections.composition || '').trim() ||
      String(sections.frozen_action || '').trim() ||
      sections.asset_visual_facts?.length ||
      String(sections.lighting_emotion || '').trim() ||
      String(sections.constraints || '').trim(),
  )
}

function StoryboardImagePromptSectionsPanel({
  sections,
}: {
  sections: StoryboardImagePromptSections | undefined | null
}) {
  if (!hasStoryboardImagePromptSections(sections)) {
    return (
      <div className="mt-4 rounded-xl border border-amber-500/20 bg-amber-500/10 p-4">
        <div className="text-sm font-medium text-amber-100">结构化分镜图提示词待刷新</div>
        <div className="mt-2 text-xs leading-6 text-amber-100/80">
          当前镜头还没有新版结构化 sections。点击“重新编译提示词”后，会生成画面定格、资产锚点、构图关系和资产视觉事实。
        </div>
      </div>
    )
  }

  const anchors = sections?.asset_anchors ?? []
  const facts = sections?.asset_visual_facts ?? []
  const requiredFacts = sections?.required_visual_facts ?? []

  return (
    <div className="mt-4 rounded-xl border border-cyan-500/25 bg-cyan-500/10 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-cyan-100">结构化分镜图提示词</div>
          <div className="mt-1 text-xs text-cyan-100/70">系统用于编译首帧生图提示词的可审计结构，不是直接粘给模型的字段清单。</div>
        </div>
        <span className="rounded-full border border-cyan-400/30 bg-cyan-950/50 px-2.5 py-1 text-[11px] text-cyan-100">
          {sections?.schema_version}
        </span>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <div className="rounded-lg border border-cyan-400/20 bg-slate-950/40 p-3">
          <div className="text-xs text-cyan-200/70">画面定格</div>
          <div className="mt-2 text-sm leading-6 text-slate-100">{sections?.frame_focus || '暂无'}</div>
        </div>
        <div className="rounded-lg border border-cyan-400/20 bg-slate-950/40 p-3">
          <div className="text-xs text-cyan-200/70">构图关系</div>
          <div className="mt-2 text-sm leading-6 text-slate-100">{sections?.composition || '暂无'}</div>
        </div>
        <div className="rounded-lg border border-cyan-400/20 bg-slate-950/40 p-3">
          <div className="text-xs text-cyan-200/70">当前帧动作</div>
          <div className="mt-2 text-sm leading-6 text-slate-100">{sections?.frozen_action || '暂无'}</div>
        </div>
        <div className="rounded-lg border border-cyan-400/20 bg-slate-950/40 p-3">
          <div className="text-xs text-cyan-200/70">光线与情绪</div>
          <div className="mt-2 text-sm leading-6 text-slate-100">{sections?.lighting_emotion || '暂无'}</div>
        </div>
      </div>

      <div className="mt-3 rounded-lg border border-cyan-400/20 bg-slate-950/40 p-3">
        <div className="text-xs text-cyan-200/70">资产锚点</div>
        {anchors.length ? (
          <div className="mt-2 flex flex-wrap gap-2">
            {anchors.map((item, index) => (
              <span key={`${item.role || 'asset'}-${item.label || index}`} className="rounded-full border border-slate-700 bg-slate-900/80 px-2.5 py-1 text-xs text-slate-200">
                {getStoryboardPromptSectionRoleLabel(item.role)} · {item.label || '-'}
              </span>
            ))}
          </div>
        ) : (
          <div className="mt-2 text-sm text-slate-400">暂无资产锚点。</div>
        )}
      </div>

      <div className="mt-3 rounded-lg border border-cyan-400/20 bg-slate-950/40 p-3">
        <div className="text-xs text-cyan-200/70">资产视觉事实</div>
        {facts.length ? (
          <div className="mt-2 space-y-2">
            {facts.map((item, index) => (
              <div key={`${item.role || 'fact'}-${item.label || index}`} className="rounded-lg border border-slate-800 bg-slate-950/70 p-2">
                <div className="text-xs text-slate-400">{getStoryboardPromptSectionRoleLabel(item.role)} · {item.label || '-'}</div>
                <div className="mt-1 text-sm leading-6 text-slate-100">{item.fact || '-'}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-2 text-sm text-slate-400">暂无可继承的资产视觉事实。</div>
        )}
      </div>

      {requiredFacts.length ? (
        <div className="mt-3 rounded-lg border border-cyan-400/20 bg-slate-950/40 p-3">
          <div className="text-xs text-cyan-200/70">补充视觉锚点</div>
          <div className="mt-2 space-y-1 text-sm leading-6 text-slate-200">
            {requiredFacts.map((item, index) => (
              <div key={`${item}-${index}`}>• {item}</div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-3 rounded-lg border border-cyan-400/20 bg-slate-950/40 p-3">
        <div className="text-xs text-cyan-200/70">一致性与禁止项</div>
        <div className="mt-2 text-sm leading-6 text-slate-100">{sections?.constraints || '暂无'}</div>
      </div>
    </div>
  )
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function buildMachinePromptDraftFromExportRecord(
  record: ProductionExportRecordListItem | null | undefined,
): MachinePromptExportPreview | null {
  const meta = record?.meta_info
  if (!meta || meta.record_type !== 'storyboard_machine_prompt_export') return null

  const targetModel = String(meta.target_model || 'minimax-h3').trim() || 'minimax-h3'
  const sourceLayers = isPlainRecord(meta.source_layers) ? meta.source_layers : {}
  const machinePrompt = isPlainRecord(meta.machine_prompt) ? meta.machine_prompt as MachinePromptExportPreview['machine_prompt'] : undefined
  const modelExports = isPlainRecord(meta.model_exports) ? meta.model_exports as MachinePromptExportPreview['model_exports'] : undefined
  const warnings = Array.isArray(meta.warnings) ? meta.warnings.map((item) => String(item || '').trim()).filter(Boolean) : []

  return {
    mode: 'history_webui_draft',
    book_id: meta.book_id,
    episode: meta.episode,
    shot_id: meta.shot_id,
    api_submission: false,
    target_model: targetModel,
    scene_name: meta.scene_name,
    director_shot_text: String(meta.director_shot_text || ''),
    bound_asset_count: Number(meta.bound_asset_count || 0),
    reference_image_count: Number(meta.reference_image_count || 0),
    warnings,
    source_layers: {
      ...sourceLayers,
      director_shot_text_source: 'history_export_record',
      machine_prompt_is_compiled: Boolean(machinePrompt || modelExports),
      model_export_is_submission_ready_but_not_submitted: true,
      history_export_record_id: record?.id,
      is_temporary_webui_draft: true,
    },
    machine_prompt: machinePrompt,
    model_exports: modelExports,
  }
}

export function buildMachinePromptTemporaryDraftFields(
  preview: MachinePromptExportPreview | null | undefined,
): MachinePromptTemporaryDraftFields {
  const minimaxH3Export = preview?.model_exports?.['minimax-h3'] ?? null
  const fields = minimaxH3Export?.fields ?? {}
  return {
    integrated_multimodal_description: fields.integrated_multimodal_description || minimaxH3Export?.prompt || '',
    overall_soundscape: fields.overall_soundscape || preview?.machine_prompt?.soundscape?.overall_soundscape || '',
    non_diegetic_music: fields.non_diegetic_music || preview?.machine_prompt?.soundscape?.non_diegetic_music || '',
    generic_zh_video_prompt: preview?.model_exports?.['generic-zh-video']?.prompt || '',
  }
}

export function applyMachinePromptTemporaryDraft(
  preview: MachinePromptExportPreview | null | undefined,
  draft: Partial<MachinePromptTemporaryDraftFields>,
  updatedAt = new Date().toISOString(),
): MachinePromptExportPreview | null {
  if (!preview) return null
  const currentH3 = preview.model_exports?.['minimax-h3'] ?? {}
  const currentGeneric = preview.model_exports?.['generic-zh-video'] ?? {}
  const currentSoundscape = preview.machine_prompt?.soundscape ?? {}
  const normalizedDraft = {
    integrated_multimodal_description: String(draft.integrated_multimodal_description ?? '').trim(),
    overall_soundscape: String(draft.overall_soundscape ?? '').trim(),
    non_diegetic_music: String(draft.non_diegetic_music ?? '').trim(),
    generic_zh_video_prompt: String(draft.generic_zh_video_prompt ?? '').trim(),
  }

  return {
    ...preview,
    api_submission: false,
    source_layers: {
      ...(preview.source_layers ?? {}),
      has_manual_export_draft: true,
      manual_export_draft_updated_at: updatedAt,
      model_export_is_submission_ready_but_not_submitted: true,
    },
    machine_prompt: {
      ...(preview.machine_prompt ?? {}),
      api_submission: false,
      soundscape: {
        ...currentSoundscape,
        overall_soundscape: normalizedDraft.overall_soundscape || currentSoundscape.overall_soundscape,
        non_diegetic_music: normalizedDraft.non_diegetic_music || currentSoundscape.non_diegetic_music,
      },
    },
    model_exports: {
      ...(preview.model_exports ?? {}),
      'minimax-h3': {
        ...currentH3,
        target_model: currentH3.target_model || 'minimax-h3',
        export_mode: currentH3.export_mode || 'webui_fields',
        api_submission: false,
        fields: {
          ...(currentH3.fields ?? {}),
          integrated_multimodal_description:
            normalizedDraft.integrated_multimodal_description ||
            currentH3.fields?.integrated_multimodal_description ||
            currentH3.prompt ||
            '',
          overall_soundscape:
            normalizedDraft.overall_soundscape ||
            currentH3.fields?.overall_soundscape ||
            currentSoundscape.overall_soundscape ||
            '',
          non_diegetic_music:
            normalizedDraft.non_diegetic_music ||
            currentH3.fields?.non_diegetic_music ||
            currentSoundscape.non_diegetic_music ||
            '',
        },
      },
      'generic-zh-video': {
        ...currentGeneric,
        target_model: currentGeneric.target_model || 'generic-zh-video',
        export_mode: currentGeneric.export_mode || 'single_prompt',
        api_submission: false,
        prompt: normalizedDraft.generic_zh_video_prompt || currentGeneric.prompt || '',
      },
    },
  }
}

export function buildMachinePromptWebuiCopyText(
  preview: MachinePromptExportPreview | null | undefined,
  targetModel = 'minimax-h3',
) {
  const modelExport = preview?.model_exports?.[targetModel] ?? preview?.model_exports?.['minimax-h3'] ?? null
  const fields = modelExport?.fields ?? {}
  const params = modelExport?.model_params ?? {}
  const timeline = (preview?.machine_prompt?.visual_timeline ?? [])
    .map((segment, index) => {
      const phase = segment.phase || `阶段 ${index + 1}`
      const timeRange = segment.time_range_seconds || '-'
      const camera = segment.camera_instruction || '默认运镜'
      const action = segment.visual_action || '暂无动作描述'
      return `${index + 1}. ${timeRange}｜${phase}｜${camera}\n${action}`
    })
    .join('\n')

  return [
    `# ${targetModel} WebUI 机器提示词导出`,
    `API 提交：否，仅复制/导出`,
    `场景：${preview?.scene_name || '-'}`,
    `参考图：${preview?.reference_image_count ?? 0}；绑定资产：${preview?.bound_asset_count ?? 0}`,
    `## 导演分镜语言\n${preview?.director_shot_text || '-'}`,
    `## 标准机器时间线\n${timeline || '-'}`,
    `## integrated_multimodal_description\n${fields.integrated_multimodal_description || modelExport?.prompt || '-'}`,
    `## overall_soundscape\n${fields.overall_soundscape || preview?.machine_prompt?.soundscape?.overall_soundscape || '-'}`,
    `## non_diegetic_music\n${fields.non_diegetic_music || preview?.machine_prompt?.soundscape?.non_diegetic_music || '-'}`,
    `## model_params\n${stringifyMachinePromptParam(params)}`,
  ].join('\n\n')
}

function escapeMachinePromptCsvCell(value: unknown) {
  const text = typeof value === 'string' ? value : stringifyMachinePromptParam(value)
  return `"${String(text).replace(/"/g, '""')}"`
}

export function buildMachinePromptMarkdownExportText(
  preview: MachinePromptExportPreview | null | undefined,
  targetModel = 'minimax-h3',
) {
  const modelExport = preview?.model_exports?.[targetModel] ?? preview?.model_exports?.['minimax-h3'] ?? null
  const fields = modelExport?.fields ?? {}
  const timelineRows = (preview?.machine_prompt?.visual_timeline ?? [])
    .map((segment, index) =>
      `| ${index + 1} | ${segment.time_range_seconds || '-'} | ${segment.phase || '-'} | ${segment.camera_instruction || '-'} | ${String(segment.visual_action || '-').replace(/\|/g, '｜')} |`,
    )
    .join('\n')

  return [
    `# 机器提示词导出：${preview?.scene_name || '未命名场景'}`,
    '',
    `- 目标模型：${targetModel}`,
    `- 导出模式：Markdown / 人工审阅`,
    `- API 提交：否，仅导出`,
    `- 参考图：${preview?.reference_image_count ?? 0}`,
    `- 绑定资产：${preview?.bound_asset_count ?? 0}`,
    '',
    '## 导演分镜语言',
    '',
    preview?.director_shot_text || '-',
    '',
    '## 标准机器时间线',
    '',
    '| # | 时间 | 阶段 | 运镜 | 可观察动作 |',
    '|---|---|---|---|---|',
    timelineRows || '| - | - | - | - | - |',
    '',
    '## MiniMax H3 WebUI 字段',
    '',
    '### integrated_multimodal_description',
    '',
    fields.integrated_multimodal_description || modelExport?.prompt || '-',
    '',
    '### overall_soundscape',
    '',
    fields.overall_soundscape || preview?.machine_prompt?.soundscape?.overall_soundscape || '-',
    '',
    '### non_diegetic_music',
    '',
    fields.non_diegetic_music || preview?.machine_prompt?.soundscape?.non_diegetic_music || '-',
    '',
    '## 导出边界',
    '',
    '- 本文件只用于 WebUI / 人工审阅 / 文件交付。',
    '- API 提交必须由独立生成动作进入任务中心。',
  ].join('\n')
}

export function buildMachinePromptCsvExportText(
  preview: MachinePromptExportPreview | null | undefined,
  targetModel = 'minimax-h3',
) {
  const modelExport = preview?.model_exports?.[targetModel] ?? preview?.model_exports?.['minimax-h3'] ?? null
  const fields = modelExport?.fields ?? {}
  const rows = [
    ['book_id', String(preview?.book_id ?? '')],
    ['episode', String(preview?.episode ?? '')],
    ['shot_id', String(preview?.shot_id ?? '')],
    ['scene_name', preview?.scene_name || ''],
    ['target_model', targetModel],
    ['api_submission', 'false'],
    ['reference_image_count', String(preview?.reference_image_count ?? 0)],
    ['bound_asset_count', String(preview?.bound_asset_count ?? 0)],
    ['director_shot_text', preview?.director_shot_text || ''],
    ['integrated_multimodal_description', fields.integrated_multimodal_description || modelExport?.prompt || ''],
    ['overall_soundscape', fields.overall_soundscape || preview?.machine_prompt?.soundscape?.overall_soundscape || ''],
    ['non_diegetic_music', fields.non_diegetic_music || preview?.machine_prompt?.soundscape?.non_diegetic_music || ''],
    ['model_params', stringifyMachinePromptParam(modelExport?.model_params ?? {})],
  ]
  const timelineRows = (preview?.machine_prompt?.visual_timeline ?? []).map((segment, index) => [
    `timeline_${index + 1}`,
    `${segment.time_range_seconds || ''}｜${segment.phase || ''}｜${segment.camera_instruction || ''}｜${segment.visual_action || ''}`,
  ])
  return [['field', 'value'], ...rows, ...timelineRows]
    .map((row) => row.map(escapeMachinePromptCsvCell).join(','))
    .join('\n')
}

export function buildMachinePromptApiJsonExportText(
  preview: MachinePromptExportPreview | null | undefined,
  targetModel = 'minimax-h3',
) {
  const modelExport = preview?.model_exports?.[targetModel] ?? preview?.model_exports?.['minimax-h3'] ?? null
  return JSON.stringify(
    {
      export_contract: {
        schema_version: 'storyboard_machine_prompt_export_v1',
        target_model: targetModel,
        export_mode: 'api_json_preview',
        api_submission: false,
        submission_policy: 'export_only_submit_via_generation_adapter',
      },
      source: {
        book_id: preview?.book_id ?? null,
        episode: preview?.episode ?? null,
        shot_id: preview?.shot_id ?? null,
        scene_name: preview?.scene_name ?? '',
      },
      director_shot_text: preview?.director_shot_text ?? '',
      machine_prompt: {
        ...(preview?.machine_prompt ?? {}),
        api_submission: false,
      },
      model_export: {
        ...(modelExport ?? {}),
        api_submission: false,
      },
    },
    null,
    2,
  )
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

type PromptQualityRepairSummary = {
  hasIssue: boolean
  shortStaticPrompt: boolean
  shortMotionPrompt: boolean
  missingSceneAsset: boolean
  degradedVersion: boolean
  issueLabels: string[]
}

function buildPromptQualityRepairSummary(shot: StoryboardShotOutput | null): PromptQualityRepairSummary {
  const staticPrompt = String(shot?.visual_prompt_static || '').trim()
  const motionPrompt = String(shot?.visual_prompt_motion || '').trim()
  const structuredSceneAssetId = String(shot?.structured_shot?.scene_asset_id || '').trim()
  const shortStaticPrompt = staticPrompt.length > 0 && staticPrompt.length < 80
  const shortMotionPrompt = motionPrompt.length > 0 && motionPrompt.length < 50
  const missingSceneAsset = Boolean(shot?.scene_name) && !structuredSceneAssetId
  const degradedVersion = shot ? hasDegradedPromptVersion(shot) : false
  const issueLabels = [
    shortStaticPrompt ? '静态提示词过短' : '',
    shortMotionPrompt ? '运动提示词过短' : '',
    missingSceneAsset ? '缺场景资产绑定' : '',
    degradedVersion ? '当前提示词版本已标记降级' : '',
  ].filter(Boolean)

  return {
    hasIssue: issueLabels.length > 0,
    shortStaticPrompt,
    shortMotionPrompt,
    missingSceneAsset,
    degradedVersion,
    issueLabels,
  }
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

function downloadTextFile(content: string, mimeType: string, filename: string) {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
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

export function buildStoryboardRepairActions(input: {
  selectedShot: StoryboardShotOutput | null
  storyboardGateStatus: 'ready' | 'blocked'
  hasAdoptedFrame: boolean
  hasAdoptedVideo: boolean
  compilerWarnings: string[]
  missingReferenceBindings: ShotBindingSummary[]
  characterBindings: ShotBindingSummary[]
  promptQualityRepair: PromptQualityRepairSummary
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
    // A blocked upstream gate is the sole actionable state.  Showing asset,
    // compiler, generation or QA actions alongside it turns a hard sequence
    // into a misleading checklist of unavailable choices.
    return actions
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
  if (promptRepairCheck || input.promptQualityRepair.hasIssue) {
    const assetNames = extractAssetNamesFromCheckDetails(promptRepairCheck?.details)
    const canContinueVideo = input.storyboardGateStatus === 'ready' && input.hasAdoptedFrame && !input.hasAdoptedVideo && input.onCompilePromptsAndContinueVideo
    const canContinueFrame = input.storyboardGateStatus === 'ready' && !input.hasAdoptedFrame && input.onCompilePromptsAndContinueFrame
    const repairActionTitle = hasScreenplayResidue
      ? '重编提示词并清理对白稿残留'
      : assetNames.length > 0
        ? `重编提示词并补齐视觉事实：${assetNames.join(' / ')}`
        : hasHighImportancePropGap
          ? '重编提示词并补齐关键道具'
          : input.promptQualityRepair.missingSceneAsset
            ? '重编提示词并补齐场景资产绑定'
            : input.promptQualityRepair.shortStaticPrompt || input.promptQualityRepair.shortMotionPrompt
              ? '重编提示词并补齐画面描述'
              : input.promptQualityRepair.degradedVersion
                ? '重编提示词并修复降级版本'
                : '重编提示词并补齐视觉事实'
    const repairActionDetail =
      hasScreenplayResidue
        ? '当前提示词仍像对白稿或舞台调度文本，继续出图会直接拉低首帧质量。建议基于当前结构化绑定整体重编，把结果收敛成纯画面描述后再继续。'
        : assetNames.length > 0
          ? `当前静态提示词没有稳定继承这些已绑定资产的关键视觉事实：${assetNames.join(' / ')}。${input.promptQualityRepair.hasIssue ? `同时命中提示词质量问题：${input.promptQualityRepair.issueLabels.join('、')}。` : ''}建议基于当前结构化绑定重新编译，先收敛静态提示词，再决定是否继续出图。`
          : hasHighImportancePropGap
            ? `当前静态提示词没有把高重要度道具明确写进首帧画面，后续出图容易出现叙事关键物缺失。${input.promptQualityRepair.hasIssue ? `同时命中提示词质量问题：${input.promptQualityRepair.issueLabels.join('、')}。` : ''}建议先重编提示词，再继续出图。`
            : input.promptQualityRepair.hasIssue
              ? `当前镜头命中提示词质量问题：${input.promptQualityRepair.issueLabels.join('、')}。建议基于当前结构化镜头与资产绑定重新编译，修复后再继续首帧或视频链路。`
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

  // H3 can use locked multi-reference images without a storyboard first
  // frame.  Once a video already exists, suggesting a frame as the next
  // production action is both redundant and misleading.
  if (input.storyboardGateStatus === 'ready' && !input.hasAdoptedFrame && !input.hasAdoptedVideo) {
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

function findLatestAdoptedAsset(items: MediaAssetOutput[] | undefined) {
  if (!Array.isArray(items) || items.length === 0) return null
  return items.find((item) => item.adopted) ?? items[items.length - 1] ?? null
}

function coerceH3DurationSecondsFromStoryboard(value: unknown, minimum = 4, strictMinimum = false) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return {
      rawDurationSeconds: null,
      durationSeconds: 5,
      sourceLabel: `分镜未记录，使用默认 5s${strictMinimum ? '；当前模型要求 5–15s' : ''}`,
    }
  }
  const rounded = Math.round(parsed)
  const durationSeconds = strictMinimum
    ? rounded
    : Math.min(Math.max(rounded, minimum), 15)
  return {
    rawDurationSeconds: rounded,
    durationSeconds,
    sourceLabel: strictMinimum && (rounded < minimum || rounded > 15)
      ? `分镜 ${rounded}s；当前模型要求 ${minimum}–15s，提交会被阻断`
      : durationSeconds === rounded
        ? `分镜 ${rounded}s`
        : `分镜 ${rounded}s，H3 按平台范围提交 ${durationSeconds}s`,
  }
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
  const [promptLockState, setPromptLockState] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [promptLockMessage, setPromptLockMessage] = useState('')
  const [acceptanceDraft, setAcceptanceDraft] = useState({
    assetKind: '',
    assetId: '',
    status: 'pending',
    failureTags: [] as string[],
    notes: '',
  })
  const [acceptanceState, setAcceptanceState] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [acceptanceMessage, setAcceptanceMessage] = useState('')
  const [machinePromptExport, setMachinePromptExport] = useState<MachinePromptExportPreview | null>(null)
  const [machinePromptExportState, setMachinePromptExportState] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle')
  const [machinePromptExportMessage, setMachinePromptExportMessage] = useState('')
  const [machinePromptCopyMessage, setMachinePromptCopyMessage] = useState('')
  const [machinePromptRecordState, setMachinePromptRecordState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [machinePromptRecordMessage, setMachinePromptRecordMessage] = useState('')
  const [machinePromptApiSubmissionState, setMachinePromptApiSubmissionState] = useState<'idle' | 'submitting' | 'submitted' | 'error'>('idle')
  const [machinePromptApiSubmissionMessage, setMachinePromptApiSubmissionMessage] = useState('')
  const [machinePromptApiSubmissionTaskId, setMachinePromptApiSubmissionTaskId] = useState('')
  const [machinePromptExportRecords, setMachinePromptExportRecords] = useState<ProductionExportRecordListItem[]>([])
  const [machinePromptRecordHistoryState, setMachinePromptRecordHistoryState] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle')
  const [directorShotDraft, setDirectorShotDraft] = useState('')
  const [directorShotSaveState, setDirectorShotSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [directorShotSaveMessage, setDirectorShotSaveMessage] = useState('')
  const [splitDraftState, setSplitDraftState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [splitDraftMessage, setSplitDraftMessage] = useState('')
  const [splitApplyState, setSplitApplyState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [splitApplyMessage, setSplitApplyMessage] = useState('')
  const [machinePromptExportBase, setMachinePromptExportBase] = useState<MachinePromptExportPreview | null>(null)
  const [machinePromptTemporaryDraft, setMachinePromptTemporaryDraft] = useState<MachinePromptTemporaryDraftFields>(() =>
    buildMachinePromptTemporaryDraftFields(null),
  )
  const [productionReadiness, setProductionReadiness] = useState<ProductionReadinessPreview | null>(null)
  const [productionReadinessState, setProductionReadinessState] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle')
  const [productionRepairPlan, setProductionRepairPlan] = useState<ProductionRepairPlanPreview | null>(null)
  const [structureGovernancePlan, setStructureGovernancePlan] = useState<StructureGovernancePlanPreview | null>(null)
  const [structureGovernanceState, setStructureGovernanceState] = useState<'idle' | 'previewing' | 'ready' | 'applying' | 'done' | 'error'>('idle')
  const [structureGovernanceMessage, setStructureGovernanceMessage] = useState('')
  const [repairExecutionState, setRepairExecutionState] = useState<'idle' | 'previewing' | 'ready' | 'executing' | 'done' | 'error'>('idle')
  const [repairExecutionMessage, setRepairExecutionMessage] = useState('')
  const [repairTask, setRepairTask] = useState<ProductionRepairTaskState | null>(null)
  const [rollbackAnchorState, setRollbackAnchorState] = useState<'idle' | 'previewing' | 'ready' | 'creating' | 'done' | 'error'>('idle')
  const [rollbackAnchorMessage, setRollbackAnchorMessage] = useState('')
  const [rollbackAnchorShotIds, setRollbackAnchorShotIds] = useState<string[]>([])

  const episodes = useMemo(
    () => Object.keys(shotsByEpisode).map(Number).filter((item) => Number.isFinite(item)).sort((a, b) => a - b),
    [shotsByEpisode],
  )

  const [selectedEpisode, setSelectedEpisode] = useState<number | null>(episodes[0] ?? null)
  const [transitionOverview, setTransitionOverview] = useState<TransitionOverview | null>(null)
  const [videoModelProfile, setVideoModelProfile] = useState<ModelProfileRecord | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchModelRegistryDefaults()
      .then((payload) => {
        if (!cancelled) setVideoModelProfile(payload.default_profiles?.video ?? null)
      })
      .catch(() => {
        if (!cancelled) setVideoModelProfile(null)
      })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!selectedEpisode) { setTransitionOverview(null); return }
    let cancelled = false
    fetch(`/api/books/${_bookId}/storyboard/${selectedEpisode}/transition-overview`, { cache: 'no-store' })
      .then(async (response) => {
        if (!response.ok) throw new Error(`transition overview ${response.status}`)
        return response.json() as Promise<TransitionOverview>
      })
      .then((payload) => { if (!cancelled) setTransitionOverview(payload) })
      .catch(() => { if (!cancelled) setTransitionOverview(null) })
    return () => { cancelled = true }
  }, [_bookId, selectedEpisode])

  useEffect(() => {
    let cancelled = false
    setProductionReadinessState('loading')
    fetch(`/api/books/${_bookId}/production-readiness`, { cache: 'no-store' })
      .then(async (response) => {
        if (!response.ok) throw new Error(`readiness ${response.status}`)
        return response.json() as Promise<ProductionReadinessPreview>
      })
      .then((payload) => {
        if (cancelled) return
        setProductionReadiness(payload)
        setProductionReadinessState('loaded')
      })
      .catch(() => {
        if (!cancelled) setProductionReadinessState('error')
      })
    fetch(`/api/books/${_bookId}/production-readiness/repair-plan`, { cache: 'no-store' })
      .then(async (response) => {
        if (!response.ok) throw new Error(`repair-plan ${response.status}`)
        return response.json() as Promise<ProductionRepairPlanPreview>
      })
      .then((payload) => { if (!cancelled) setProductionRepairPlan(payload) })
      .catch(() => { if (!cancelled) setProductionRepairPlan(null) })
    fetch(`/api/books/${_bookId}/storyboard/structure-governance/plan`, { cache: 'no-store' })
      .then(async (response) => {
        if (!response.ok) throw new Error(`structure-governance ${response.status}`)
        return response.json() as Promise<StructureGovernancePlanPreview>
      })
      .then((payload) => { if (!cancelled) setStructureGovernancePlan(payload) })
      .catch(() => { if (!cancelled) setStructureGovernancePlan(null) })
    return () => { cancelled = true }
  }, [_bookId])

  const previewRepairExecution = async () => {
    if (!productionRepairPlan?.confirmation_token) return
    const shotIds = (productionRepairPlan.shot_actions ?? [])
      .filter((item) => (item.action === 'recompile_prompt' || item.action === 'backfill_prompt_runtime') && item.shot_id !== undefined)
      .map((item) => String(item.shot_id))
    if (shotIds.length === 0) {
      setRepairExecutionMessage('当前没有可直接批量重编译的镜头；blocked 镜头需先人工复核。')
      setRepairExecutionState('error')
      return
    }
    setRepairExecutionState('previewing')
    try {
      const response = await fetch(`/api/books/${_bookId}/production-readiness/repair-plan/execute`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmationToken: productionRepairPlan.confirmation_token, shotIds, confirmed: false, allowWrite: false }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || '修复计划预检失败')
      setRepairExecutionMessage(`预检通过：将处理 ${payload.selected_shots?.length ?? shotIds.length} 个镜头。仅“重编译”会调用 LLM；“回填”只补齐已确认版本的生产元数据。确认后才会写入。`)
      setRepairExecutionState('ready')
    } catch (error) {
      setRepairExecutionMessage(error instanceof Error ? error.message : '修复计划预检失败')
      setRepairExecutionState('error')
    }
  }

  const refreshProductionRepairPlan = async () => {
    const response = await fetch(`/api/books/${_bookId}/production-readiness/repair-plan`, { cache: 'no-store' })
    if (!response.ok) throw new Error(`repair-plan ${response.status}`)
    setProductionRepairPlan(await response.json() as ProductionRepairPlanPreview)
  }

  const previewStructureGovernance = async () => {
    if (!structureGovernancePlan?.plan_fingerprint) return
    setStructureGovernanceState('previewing')
    try {
      const response = await fetch(`/api/books/${_bookId}/storyboard/structure-governance/backfill`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ planFingerprint: structureGovernancePlan.plan_fingerprint }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || '结构治理预检失败')
      setStructureGovernanceMessage(`预检通过：将只修正 ${payload.items?.filter((item: { identity_stale?: boolean }) => item.identity_stale).length ?? 0} 个派生镜头标识，并标记 ${payload.items?.length ?? 0} 份旧诊断为过期。`)
      setStructureGovernanceState('ready')
    } catch (error) {
      setStructureGovernanceMessage(error instanceof Error ? error.message : '结构治理预检失败')
      setStructureGovernanceState('error')
    }
  }

  const applyStructureGovernance = async () => {
    if (!structureGovernancePlan?.plan_fingerprint || !structureGovernancePlan.confirmation_token || structureGovernanceState !== 'ready') return
    if (!window.confirm('确认写入结构化镜头身份治理结果？这会创建每个镜头的回滚快照；不会改导演文本、提示词内容、资产或媒体。')) return
    setStructureGovernanceState('applying')
    try {
      const response = await fetch(`/api/books/${_bookId}/storyboard/structure-governance/backfill`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ planFingerprint: structureGovernancePlan.plan_fingerprint, confirmationToken: structureGovernancePlan.confirmation_token, confirmed: true, allowWrite: true }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || '结构治理写入失败')
      setStructureGovernanceMessage(`已受控治理 ${payload.applied?.length ?? 0} 个镜头；旧提示词诊断已标记过期，需按镜头确认重编译。`)
      setStructureGovernanceState('done')
      const [readinessResponse, planResponse] = await Promise.all([
        fetch(`/api/books/${_bookId}/production-readiness`, { cache: 'no-store' }),
        fetch(`/api/books/${_bookId}/storyboard/structure-governance/plan`, { cache: 'no-store' }),
      ])
      if (readinessResponse.ok) setProductionReadiness(await readinessResponse.json() as ProductionReadinessPreview)
      if (planResponse.ok) setStructureGovernancePlan(await planResponse.json() as StructureGovernancePlanPreview)
    } catch (error) {
      setStructureGovernanceMessage(error instanceof Error ? error.message : '结构治理写入失败')
      setStructureGovernanceState('error')
    }
  }

  const previewRollbackAnchors = async () => {
    if (!productionRepairPlan?.confirmation_token) return
    const shotIds = (productionRepairPlan.shot_actions ?? [])
      .filter((item) => !item.rollback_anchor && item.shot_id !== undefined)
      .map((item) => String(item.shot_id))
    if (shotIds.length === 0) {
      setRollbackAnchorMessage('当前计划中的镜头都已有可回滚锚点。')
      setRollbackAnchorState('done')
      return
    }
    setRollbackAnchorState('previewing')
    try {
      const response = await fetch(`/api/books/${_bookId}/production-readiness/repair-plan/rollback-anchors`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmationToken: productionRepairPlan.confirmation_token, shotIds }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || '状态锚点预检失败')
      const eligible = Array.isArray(payload.eligible_shots) ? payload.eligible_shots : []
      setRollbackAnchorShotIds(eligible.map((item: { shot_id?: number | string }) => String(item.shot_id)).filter(Boolean))
      setRollbackAnchorMessage(eligible.length > 0 ? `预检通过：可为 ${eligible.length} 个已声明结构变换镜头建立状态锚点。` : '缺少锚点的镜头不具备已声明的结构变换来源，不能自动补建。')
      setRollbackAnchorState(eligible.length > 0 ? 'ready' : 'error')
    } catch (error) {
      setRollbackAnchorMessage(error instanceof Error ? error.message : '状态锚点预检失败')
      setRollbackAnchorState('error')
    }
  }

  const createRollbackAnchors = async () => {
    if (!productionRepairPlan?.confirmation_token || rollbackAnchorState !== 'ready' || rollbackAnchorShotIds.length === 0) return
    if (!window.confirm(`确认建立 ${rollbackAnchorShotIds.length} 个结构变换后的状态锚点？这会创建审计版本，但不会重编译提示词。`)) return
    setRollbackAnchorState('creating')
    try {
      const response = await fetch(`/api/books/${_bookId}/production-readiness/repair-plan/rollback-anchors`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmationToken: productionRepairPlan.confirmation_token, shotIds: rollbackAnchorShotIds, confirmed: true, allowWrite: true }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || '创建状态锚点失败')
      await refreshProductionRepairPlan()
      setRollbackAnchorMessage(`已建立 ${payload.created?.length ?? 0} 个状态锚点；请重新预检重编译计划。`)
      setRollbackAnchorState('done')
    } catch (error) {
      setRollbackAnchorMessage(error instanceof Error ? error.message : '创建状态锚点失败')
      setRollbackAnchorState('error')
    }
  }

  const executeRepairPlan = async () => {
    if (!productionRepairPlan?.confirmation_token || repairExecutionState !== 'ready') return
    if (!window.confirm('确认执行当前生产修复？重编译会调用 LLM 并创建新版本；元数据回填不会调用 LLM、不会改提示词文本或创建版本。')) return
    const shotIds = (productionRepairPlan.shot_actions ?? [])
      .filter((item) => (item.action === 'recompile_prompt' || item.action === 'backfill_prompt_runtime') && item.shot_id !== undefined)
      .map((item) => String(item.shot_id))
    setRepairExecutionState('executing')
    try {
      const response = await fetch(`/api/books/${_bookId}/production-readiness/repair-plan/execute`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmationToken: productionRepairPlan.confirmation_token, shotIds, confirmed: true, allowWrite: true }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload?.detail?.message || payload?.message || '修复任务创建失败')
      setRepairExecutionMessage(`已创建受保护修复任务 ${payload.task_id}，请到任务中心跟踪逐镜头结果。`)
      setRepairTask({ task_id: payload.task_id, status: 'queued', progress: 0, confirmation_token: productionRepairPlan.confirmation_token })
      setRepairExecutionState('done')
    } catch (error) {
      setRepairExecutionMessage(error instanceof Error ? error.message : '修复任务创建失败')
      setRepairExecutionState('error')
    }
  }

  useEffect(() => {
    const taskId = repairTask?.task_id
    if (!taskId) return
    let cancelled = false
    const poll = async () => {
      try {
        const response = await fetch(`/api/books/${_bookId}/production-readiness/repair-tasks/${taskId}`, { cache: 'no-store' })
        if (!response.ok) return
        const payload = await response.json() as ProductionRepairTaskState
        if (!cancelled) setRepairTask(payload)
      } catch { /* task center remains the source of truth */ }
    }
    void poll()
    const timer = window.setInterval(() => void poll(), 2500)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [_bookId, repairTask?.task_id])

  const rollbackRepairShot = async (item: NonNullable<ProductionRepairTaskState['results']>[number]) => {
    if (!repairTask?.task_id || !repairTask.confirmation_token || !item.baseline_version || item.episode === undefined || item.shot_id === undefined) return
    if (!window.confirm(`确认将第 ${item.episode} 集 / 镜头 ${item.shot_id} 回滚到 baseline v${item.baseline_version}？`)) return
    const response = await fetch(`/api/books/${_bookId}/production-readiness/repair-tasks/${repairTask.task_id}/rollback`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmationToken: repairTask.confirmation_token, episode: item.episode, shotId: String(item.shot_id), baselineVersion: item.baseline_version, confirmed: true }),
    })
    const payload = await response.json()
    setRepairExecutionMessage(response.ok ? `镜头 ${item.shot_id} 已回滚到 baseline v${item.baseline_version}。` : (payload?.detail || '回滚失败'))
  }

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
  useEffect(() => {
    setMachinePromptExport(null)
    setMachinePromptExportState('idle')
    setMachinePromptExportMessage('')
    setMachinePromptCopyMessage('')
    setMachinePromptRecordState('idle')
    setMachinePromptRecordMessage('')
    setMachinePromptApiSubmissionState('idle')
    setMachinePromptApiSubmissionMessage('')
    setMachinePromptExportRecords([])
    setMachinePromptRecordHistoryState('idle')
    setDirectorShotDraft('')
    setDirectorShotSaveState('idle')
    setDirectorShotSaveMessage('')
  }, [selectedShot?.episode, selectedShot?.shot_id])
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
  const selectedShotStaticPromptSections = selectedShot?.prompt_compile_context?.model_adapter?.static_prompt_sections ?? null
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
  const selectedExecutability = useMemo(() => {
    const contextValue = selectedShot?.prompt_compile_context?.executability
    const structuredValue = selectedShot?.structured_shot?.executability
    return (contextValue && typeof contextValue === 'object' ? contextValue : structuredValue) ?? null
  }, [selectedShot?.prompt_compile_context?.executability, selectedShot?.structured_shot?.executability])
  const selectedActionBeats = (
    selectedShot?.prompt_compile_context?.action_beats
    ?? selectedShot?.structured_shot?.action_beats
    ?? []
  ).filter(Boolean)
  const selectedSplitDraft = selectedShot?.executability_split_draft ?? null
  const hasSplitSuggestion = Boolean(
    selectedExecutability?.recommendations?.some((item) =>
      typeof item !== 'string' && String((item as Record<string, unknown>).type || '') === 'split_shot',
    ),
  )
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
  useEffect(() => {
    setAcceptanceDraft({
      assetKind: acceptanceAssetKind || (adoptedVideo ? 'video' : adoptedImage ? 'image' : 'image'),
      assetId: acceptanceAssetId || '',
      status: acceptance?.status || 'pending',
      failureTags: Array.isArray(acceptance?.failure_tags) ? acceptance.failure_tags : [],
      notes: acceptance?.notes || '',
    })
    setAcceptanceState('idle')
    setAcceptanceMessage('')
    setPromptLockState('idle')
    setPromptLockMessage('')
  }, [
    acceptance?.failure_tags,
    acceptance?.notes,
    acceptance?.status,
    acceptanceAssetId,
    acceptanceAssetKind,
    adoptedImage,
    adoptedVideo,
    selectedShot?.episode,
    selectedShot?.shot_id,
  ])
  const hasAdoptedFrame = Boolean(adoptedImage)
  const adoptedImageUrl = String(adoptedImage?.uri || adoptedImage?.previewUrl || '').trim()
  const predictedVideoTaskMode =
    effectiveReferenceAssetIds.length > 0 ? 'reference_to_video' : hasAdoptedFrame ? 'image_to_video' : 'text_to_video'
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
  const promptQualityRepair = useMemo(
    () => buildPromptQualityRepairSummary(selectedShot),
    [selectedShot],
  )
  const machineTimeline = machinePromptExport?.machine_prompt?.visual_timeline ?? []
  const minimaxH3Export = machinePromptExport?.model_exports?.['minimax-h3'] ?? null
  const minimaxH3Fields = minimaxH3Export?.fields ?? {}
  const genericZhVideoExport = machinePromptExport?.model_exports?.['generic-zh-video'] ?? null
  const h3Duration = coerceH3DurationSecondsFromStoryboard(selectedShot?.duration)
  const h3ProviderSubmitSummary = useMemo<H3ProviderSubmitSummary | null>(() => {
    if (!machinePromptExport) return null
    const promptText = String(minimaxH3Fields.integrated_multimodal_description || '').trim()
    const profile = videoModelProfile
    const provider = String(profile?.provider || '').trim()
    const params = profile?.default_params && typeof profile.default_params === 'object' ? profile.default_params : {}
    const is75Api = provider === '75api-minimax-h3'
    const resolution = String(params.resolution || (is75Api ? '768p' : '768P')).trim() || (is75Api ? '768p' : '768P')
    const baseUrl = String(profile?.base_url || (is75Api ? 'https://www.75api.com' : 'https://metaso.cn/api/minimax')).trim()
    const modelName = String(profile?.model_name || (is75Api ? 'minimax_h3_no_audios' : 'MiniMax-H3')).trim()
    const supportsTextToVideo = params.supports_text_to_video === false
      ? false
      : Array.isArray(params.task_modes)
        ? params.task_modes.includes('text_to_video')
        : !is75Api
    const modelMinimumDuration = is75Api ? 5 : 4
    const effectiveDuration = coerceH3DurationSecondsFromStoryboard(selectedShot?.duration, modelMinimumDuration, is75Api)
    return {
      platformLabel: is75Api ? '75api MiniMax H3' : 'metaso.cn MiniMax H3 兼容 API',
      baseUrl,
      modelName,
      provider,
      supportsTextToVideo,
      resolution,
      durationSeconds: effectiveDuration.durationSeconds,
      durationSourceLabel: effectiveDuration.sourceLabel,
      aspectRatio: '16:9',
      aigcWatermark: Boolean(params.aigc_watermark ?? params.watermark),
      taskMode: effectiveReferenceAssetIds.length > 0 ? 'reference_to_video' : adoptedImageUrl ? 'image_to_video' : 'text_to_video',
      referenceImageCount: effectiveReferenceAssetIds.length,
      firstFrameAssetLabel: adoptedImage ? String(adoptedImage.title || adoptedImage.label || adoptedImage.id || '').trim() : '',
      firstFrameUrl: adoptedImageUrl,
      promptLength: promptText.length,
    }
  }, [adoptedImage, adoptedImageUrl, effectiveReferenceAssetIds.length, machinePromptExport, minimaxH3Fields.integrated_multimodal_description, selectedShot?.duration, videoModelProfile])
  const minimaxH3CopyText = useMemo(
    () => buildMachinePromptWebuiCopyText(machinePromptExport, 'minimax-h3'),
    [machinePromptExport],
  )
  const isMachinePromptManualDraft = Boolean(machinePromptExport?.source_layers?.has_manual_export_draft)
  const storyboardCanvasPrimaryActionPlan = useMemo(
    () =>
      buildStoryboardCanvasPrimaryActionPlan({
        canGenerateFromGate,
        promptRecoveryTaskId,
        frameRecoveryTaskId,
        videoRecoveryTaskId,
        hasCompiledPrompt,
        hasAdoptedFrame,
        hasReferenceImages: effectiveReferenceAssetIds.length > 0,
        hasAdoptedVideo: Boolean(adoptedVideo),
      }),
    [
      adoptedVideo,
      canGenerateFromGate,
      frameRecoveryTaskId,
      effectiveReferenceAssetIds.length,
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
        promptQualityRepair,
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
      promptQualityRepair,
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

  const setMachinePromptExportWithBase = (preview: MachinePromptExportPreview | null) => {
    setMachinePromptExport(preview)
    setMachinePromptExportBase(preview)
    setMachinePromptTemporaryDraft(buildMachinePromptTemporaryDraftFields(preview))
  }

  const loadMachinePromptExportPreview = async () => {
    if (!selectedShot?.episode || !selectedShot?.shot_id) return
    setMachinePromptExportState('loading')
    setMachinePromptExportMessage('正在编译只读机器提示词导出预览，不会提交生成任务。')
    setMachinePromptCopyMessage('')
    setMachinePromptRecordState('idle')
    setMachinePromptRecordMessage('')
    setMachinePromptApiSubmissionState('idle')
    setMachinePromptApiSubmissionMessage('')
    try {
      const response = await fetch(
        `/api/books/${_bookId}/storyboard/${selectedShot.episode}/${selectedShot.shot_id}/machine-prompt-export?target_model=minimax-h3`,
        { cache: 'no-store' },
      )
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
      const payload = (await response.json()) as MachinePromptExportPreview
      setMachinePromptExportWithBase(payload)
      setDirectorShotDraft(payload.director_shot_text || '')
      setDirectorShotSaveState('idle')
      setDirectorShotSaveMessage('')
      setMachinePromptExportState('loaded')
      setMachinePromptExportMessage('已生成机器提示词导出预览：当前仅用于复制或审阅，不会提交 API。')
    } catch (error) {
      setMachinePromptExportState('error')
      setMachinePromptExportMessage(error instanceof Error ? error.message : '机器提示词导出预览加载失败。')
    }
  }

  const saveDirectorShotText = async (resetToSystem = false) => {
    if (!selectedShot?.episode || !selectedShot?.shot_id) return
    const normalized = directorShotDraft.trim()
    if (!resetToSystem && !normalized) {
      setDirectorShotSaveState('error')
      setDirectorShotSaveMessage('导演分镜语言不能为空；如果要恢复系统生成版，请点击“恢复系统版”。')
      return
    }

    setDirectorShotSaveState('saving')
    setDirectorShotSaveMessage(resetToSystem ? '正在恢复系统生成导演分镜语言。' : '正在保存导演分镜语言，并重新编译导出预览。')
    try {
      const response = await fetch(
        `/api/books/${_bookId}/storyboard/${selectedShot.episode}/${selectedShot.shot_id}/director-shot-text?target_model=minimax-h3`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            directorShotText: normalized,
            operatorName: 'formal-workspace',
            resetToSystem,
          }),
        },
      )
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
      const payload = (await response.json()) as MachinePromptExportPreview
      setMachinePromptExportWithBase(payload)
      setDirectorShotDraft(payload.director_shot_text || '')
      setDirectorShotSaveState('saved')
      setDirectorShotSaveMessage(
        resetToSystem
          ? '已恢复系统生成导演分镜语言，并重新编译导出预览；未创建 PromptVersion。'
          : '已保存导演分镜语言，并重新编译机器提示词导出；未创建 PromptVersion。',
      )
      setMachinePromptExportState('loaded')
      setMachinePromptExportMessage('导出预览已基于当前导演分镜语言刷新；API 未提交。')
    } catch (error) {
      setDirectorShotSaveState('error')
      setDirectorShotSaveMessage(error instanceof Error ? error.message : '导演分镜语言保存失败。')
    }
  }

  const copyMachinePromptText = async (label: string, text: string | undefined) => {
    const normalized = String(text || '').trim()
    if (!normalized) {
      setMachinePromptCopyMessage(`${label} 暂无可复制内容，请先加载导出预览。`)
      return
    }

    try {
      await navigator.clipboard.writeText(normalized)
      setMachinePromptCopyMessage(`${label} 已复制，可粘贴到第三方 WebUI。`)
    } catch (error) {
      setMachinePromptCopyMessage(error instanceof Error ? error.message : `${label} 复制失败。`)
    }
  }

  const downloadMachinePromptExportFile = (format: 'markdown' | 'csv' | 'api-json') => {
    if (!machinePromptExport) {
      setMachinePromptCopyMessage('请先加载机器提示词导出预览，再下载文件。')
      return
    }

    const episode = String(machinePromptExport.episode ?? selectedShot?.episode ?? 'episode').replace(/[^\w-]+/g, '-')
    const shotId = String(machinePromptExport.shot_id ?? selectedShot?.shot_id ?? 'shot').replace(/[^\w-]+/g, '-')
    const stem = `book-${_bookId}-ep-${episode}-shot-${shotId}-machine-prompt`
    const exportMap = {
      markdown: {
        content: buildMachinePromptMarkdownExportText(machinePromptExport, 'minimax-h3'),
        mimeType: 'text/markdown',
        filename: `${stem}.md`,
        label: 'Markdown',
      },
      csv: {
        content: buildMachinePromptCsvExportText(machinePromptExport, 'minimax-h3'),
        mimeType: 'text/csv',
        filename: `${stem}.csv`,
        label: 'CSV',
      },
      'api-json': {
        content: buildMachinePromptApiJsonExportText(machinePromptExport, 'minimax-h3'),
        mimeType: 'application/json',
        filename: `${stem}.api-preview.json`,
        label: 'API JSON',
      },
    } as const
    const selectedExport = exportMap[format]
    downloadTextFile(selectedExport.content, selectedExport.mimeType, selectedExport.filename)
    setMachinePromptCopyMessage(`${selectedExport.label} 导出文件已生成；API 仍未提交。`)
  }

  const loadMachinePromptExportRecordHistory = async () => {
    if (!selectedShot?.episode || !selectedShot?.shot_id) return
    setMachinePromptRecordHistoryState('loading')
    setMachinePromptRecordMessage('正在读取当前镜头的机器提示词导出历史。')
    try {
      const params = new URLSearchParams({
        record_type: 'storyboard_machine_prompt_export',
        episode: String(selectedShot.episode),
        limit: '100',
      })
      const response = await fetch(`/api/books/${_bookId}/export-records?${params.toString()}`, { cache: 'no-store' })
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
      const records = Array.isArray(payload?.records) ? payload.records as ProductionExportRecordListItem[] : []
      const filteredRecords = records.filter((record) =>
        isMachinePromptRecordForShot(record, selectedShot.episode, selectedShot.shot_id),
      )
      setMachinePromptExportRecords(filteredRecords)
      setMachinePromptRecordHistoryState('loaded')
      setMachinePromptRecordMessage(
        filteredRecords.length > 0
          ? `已读取 ${filteredRecords.length} 条当前镜头机器提示词导出记录。`
          : '当前镜头暂无机器提示词导出记录。',
      )
    } catch (error) {
      setMachinePromptRecordHistoryState('error')
      setMachinePromptRecordMessage(error instanceof Error ? error.message : '机器提示词导出历史读取失败。')
    }
  }

  const restoreMachinePromptExportRecordDraft = (record: ProductionExportRecordListItem) => {
    const draft = buildMachinePromptDraftFromExportRecord(record)
    if (!draft) {
      setMachinePromptRecordState('error')
      setMachinePromptRecordMessage('这条历史记录缺少可恢复的机器提示词快照，无法生成 WebUI 临时草稿。')
      return
    }

    setMachinePromptExportWithBase(draft)
    setMachinePromptExportState('loaded')
    setMachinePromptExportMessage(
      `已从导出记录 #${record.id ?? '-'} 恢复为 WebUI 临时草稿；仅用于复制、下载或人工审阅，不会反写导演分镜语言、Shot Schema 或 Prompt Version。`,
    )
    setMachinePromptRecordState('saved')
    setMachinePromptRecordMessage(`已恢复历史快照 #${record.id ?? '-'} 为临时导出草稿；API 未提交。`)
    setMachinePromptCopyMessage('')
  }

  const applyMachinePromptManualTemporaryDraft = () => {
    if (!machinePromptExport) {
      setMachinePromptCopyMessage('请先加载机器提示词导出预览，再编辑临时草稿。')
      return
    }
    const nextPreview = applyMachinePromptTemporaryDraft(machinePromptExport, machinePromptTemporaryDraft)
    setMachinePromptExport(nextPreview)
    setMachinePromptExportState('loaded')
    setMachinePromptExportMessage('已应用临时导出草稿：复制与文件导出会使用这份人工修改；不会反写导演分镜语言、Shot Schema 或 Prompt Version。')
    setMachinePromptCopyMessage('')
  }

  const resetMachinePromptManualTemporaryDraft = () => {
    setMachinePromptExport(machinePromptExportBase)
    setMachinePromptTemporaryDraft(buildMachinePromptTemporaryDraftFields(machinePromptExportBase))
    setMachinePromptExportMessage('已撤销临时导出修改，恢复到本次加载或历史恢复的基线草稿。')
    setMachinePromptCopyMessage('')
  }

  const saveMachinePromptExportRecord = async () => {
    if (!selectedShot?.episode || !selectedShot?.shot_id) return
    setMachinePromptRecordState('saving')
    setMachinePromptRecordMessage('正在登记当前镜头的机器提示词导出快照，不会提交生成任务。')
    try {
      const response = await fetch(
        `/api/books/${_bookId}/storyboard/${selectedShot.episode}/${selectedShot.shot_id}/machine-prompt-export-records`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            targetModel: 'minimax-h3',
            exportChannel: 'webui',
            operatorName: 'formal-workspace',
          }),
        },
      )
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
      const record = await response.json()
      setMachinePromptRecordState('saved')
      setMachinePromptRecordMessage(`已登记导出记录 #${record?.id ?? '-'}：API 未提交，仅保存 WebUI 导出快照。`)
      if (isMachinePromptRecordForShot(record, selectedShot.episode, selectedShot.shot_id)) {
        setMachinePromptExportRecords((current) => [
          record,
          ...current.filter((item) => String(item.id ?? '') !== String(record?.id ?? '')),
        ])
        setMachinePromptRecordHistoryState('loaded')
      }
    } catch (error) {
      setMachinePromptRecordState('error')
      setMachinePromptRecordMessage(error instanceof Error ? error.message : '机器提示词导出记录保存失败。')
    }
  }

  const submitMachinePromptApiTask = async () => {
    if (!selectedShot?.episode || !selectedShot?.shot_id) return ''
    if (!machinePromptExport) {
      setMachinePromptApiSubmissionState('error')
      setMachinePromptApiSubmissionMessage('请先加载机器提示词导出预览，再登记 API 提交任务。')
      return ''
    }

    setMachinePromptApiSubmissionState('submitting')
    setMachinePromptApiSubmissionMessage('正在登记机器提示词 API 提交任务；这一步只进入任务中心，不会调用真实 provider。')
    try {
      const rawHistoryRecordId = machinePromptExport.source_layers?.history_export_record_id
      const sourceExportRecordId =
        typeof rawHistoryRecordId === 'number'
          ? rawHistoryRecordId
          : typeof rawHistoryRecordId === 'string' && rawHistoryRecordId.trim() && Number.isFinite(Number(rawHistoryRecordId))
            ? Number(rawHistoryRecordId)
            : null
      const response = await fetch(
        `/api/books/${_bookId}/storyboard/${selectedShot.episode}/${selectedShot.shot_id}/machine-prompt-api-submissions`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            targetModel: 'minimax-h3',
            modelProfileId: videoModelProfile?.id || undefined,
            exportChannel: 'api',
            operatorName: 'formal-workspace',
            submissionMode: 'task_intent_only',
            sourceExportRecordId,
            hasManualExportDraft: Boolean(machinePromptExport.source_layers?.has_manual_export_draft),
            exportPayload: machinePromptExport,
            notes: '由正式工作台登记的机器提示词 API 提交意图；当前不真实调用 provider。',
          }),
        },
      )
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
      const taskId = String(payload?.task_id || '').trim()
      if (!taskId) {
        throw new Error('服务端已响应，但没有返回任务 ID。')
      }
      setMachinePromptApiSubmissionTaskId(taskId)

      upsertPendingStoryboardTask(_bookId, {
        taskId,
        episode: selectedShot.episode,
        shotId: String(selectedShot.shot_id),
        kind: 'prompt',
        updatedAt: new Date().toISOString(),
      })
      setMachinePromptApiSubmissionState('submitted')
      setMachinePromptApiSubmissionMessage(
        `已登记 API 提交任务 ${taskId}；当前尚未调用真实 provider。如需生成视频，请再执行“真实提交 H3”。`,
      )
      setRuntimeVersion((current) => current + 1)
      return taskId
    } catch (error) {
      setMachinePromptApiSubmissionState('error')
      setMachinePromptApiSubmissionMessage(error instanceof Error ? error.message : '机器提示词 API 提交任务登记失败。')
      return ''
    }
  }

  const submitMachinePromptProviderTask = async () => {
    if (!selectedShot?.episode || !selectedShot?.shot_id) return
    if (!machinePromptExport) {
      setMachinePromptApiSubmissionState('error')
      setMachinePromptApiSubmissionMessage('请先加载机器提示词导出预览，再执行真实 H3 提交。')
      return
    }

    const confirmed =
      typeof window === 'undefined'
        ? false
        : window.confirm('确认真实提交 MiniMax H3 视频生成？该操作可能产生平台费用，并会把返回视频写回当前镜头资产。')
    if (!confirmed) {
      setMachinePromptApiSubmissionMessage('已取消真实 H3 提交；当前只保留导出/登记状态。')
      return
    }

    let taskId = machinePromptApiSubmissionTaskId
    if (!taskId) {
      taskId = await submitMachinePromptApiTask()
    }
    if (!taskId) return

    setMachinePromptApiSubmissionState('submitting')
    setMachinePromptApiSubmissionMessage(`正在真实提交 MiniMax H3：任务 ${taskId}。`)
    try {
      const response = await fetch(`/api/prototyping/tasks/${taskId}/submit-machine-prompt-provider`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          confirmationToken: 'CONFIRM_MINIMAX_H3_SUBMIT',
          aspectRatio: '16:9',
          durationSeconds: h3ProviderSubmitSummary?.durationSeconds ?? h3Duration.durationSeconds,
          modelProfileId: videoModelProfile?.id || undefined,
          useReferenceImages: effectiveReferenceAssetIds.length > 0,
          referenceAssetIds: effectiveReferenceAssetIds,
          useFirstFrame: effectiveReferenceAssetIds.length === 0 && Boolean(adoptedImageUrl),
          firstFrameAssetId: effectiveReferenceAssetIds.length === 0 ? (adoptedImage?.id ? String(adoptedImage.id) : undefined) : undefined,
          notes: effectiveReferenceAssetIds.length > 0
            ? '由正式工作台二次确认后真实提交 MiniMax H3；使用多参考图模式，不与首/尾帧模式混用。'
            : '由正式工作台二次确认后真实提交 MiniMax H3；使用当前采纳首帧图生视频模式。',
        }),
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
      upsertPendingStoryboardTask(_bookId, {
        taskId,
        episode: selectedShot.episode,
        shotId: String(selectedShot.shot_id),
        kind: 'video',
        updatedAt: new Date().toISOString(),
      })
      setMachinePromptApiSubmissionState('submitted')
      setMachinePromptApiSubmissionMessage(
        `已真实提交 MiniMax H3：任务 ${taskId}，provider 状态 ${payload?.external_status || 'queued'}。可到任务中心回收视频结果。`,
      )
      setRuntimeVersion((current) => current + 1)
    } catch (error) {
      setMachinePromptApiSubmissionState('error')
      setMachinePromptApiSubmissionMessage(error instanceof Error ? error.message : 'MiniMax H3 真实提交失败。')
    }
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
    if (!window.confirm('确认直接调用 LLM 重编译当前提示词？这可能产生模型费用并创建新的 Prompt Version。建议优先使用“受控 Prompt Compiler 草案”审核流程。')) {
      return { status: 'cancelled' as const, reason: compileReason }
    }
    setCompileActionState('saving')
    setCompileActionMessage('正在提交当前镜头提示词重编译任务，通常需要 30-60 秒。')

    let promptTaskId = ''
    try {
      const response = await fetch(`/api/books/${_bookId}/storyboard/${selectedShot.episode}/${selectedShot.shot_id}/compile-prompts/async`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ compileReason, force: false, confirmed: true, allowExternalCall: true }),
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

  const saveExecutabilitySplitDraft = async () => {
    if (!selectedShot?.episode || !selectedShot?.shot_id) return
    setSplitDraftState('saving')
    setSplitDraftMessage('正在保存拆镜草案；此操作不会改写原镜头。')
    try {
      const response = await fetch(
        `/api/books/${_bookId}/storyboard/${selectedShot.episode}/${selectedShot.shot_id}/executability/split-draft`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ note: '由正式工作台保存，等待人工确认后再应用。' }),
        },
      )
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
      setSplitDraftState('saved')
      setSplitDraftMessage('拆镜草案已保存；原镜头和提示词尚未改动。')
      await onRefresh()
    } catch (error) {
      setSplitDraftState('error')
      setSplitDraftMessage(error instanceof Error ? error.message : '保存拆镜草案失败。')
    }
  }

  const applyExecutabilitySplitDraft = async () => {
    if (!selectedShot?.episode || !selectedShot?.shot_id) return
    const confirmed = typeof window !== 'undefined' && window.confirm(
      '确认应用拆镜草案？系统会按草案段数创建连续镜头、顺延后续镜头号，并清空所有新片段的旧提示词和媒体产物；随后必须重新编译。',
    )
    if (!confirmed) return
    setSplitApplyState('saving')
    setSplitApplyMessage('正在应用拆镜草案并重排后续镜头。')
    try {
      const response = await fetch(
        `/api/books/${_bookId}/storyboard/${selectedShot.episode}/${selectedShot.shot_id}/executability/split-draft/apply`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ confirmed: true }) },
      )
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
      setSplitApplyState('saved')
      const createdShotIds = Array.isArray(payload?.created_shot_ids)
        ? payload.created_shot_ids.map((item: unknown) => String(item)).filter(Boolean)
        : (payload?.created_shot_id ? [String(payload.created_shot_id)] : [])
      setSplitApplyMessage(`已创建 ${createdShotIds.length} 个连续镜头${createdShotIds.length ? `（${createdShotIds.join('、')}）` : ''}；所有片段都需要重新编译。`)
      await onRefresh()
    } catch (error) {
      setSplitApplyState('error')
      setSplitApplyMessage(error instanceof Error ? error.message : '应用拆镜草案失败。')
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
      const endpoint = `/api/books/${_bookId}/storyboard/${selectedShot.episode}/${selectedShot.shot_id}/${kind === 'frame' ? 'generate-frame' : 'generate-video'}`
      const requestBody = kind === 'frame'
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
          }
      let response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      })
      if (!response.ok) {
        let payload: any = null
        try {
          payload = await response.json()
        } catch {
          payload = null
        }
        const detailPayload = payload?.detail && typeof payload.detail === 'object' ? payload.detail : null
        if (kind === 'video' && response.status === 409 && detailPayload?.requires_confirmation) {
          const confirmed = typeof window !== 'undefined' && window.confirm(
            `当前镜头可拍性存在告警：${String(detailPayload.message || '建议先优化镜头')}\n\n仍要提交视频生成吗？`,
          )
          if (confirmed) {
            response = await fetch(endpoint, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ ...requestBody, executabilityOverride: true, executabilityOverrideReason: '用户确认可拍性告警后提交' }),
            })
          } else {
            throw new Error(String(detailPayload.message || '已取消视频提交；请先处理可拍性告警。'))
          }
        }
        if (!response.ok) {
          const detail = String(payload?.detail?.message || payload?.detail || payload?.error || '')
          throw new Error(detail || `HTTP ${response.status}`)
        }
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

  const togglePromptLock = async () => {
    if (!selectedShot?.episode || !selectedShot?.shot_id) return
    const nextLocked = !selectedShot.prompt_locked
    setPromptLockState('saving')
    setPromptLockMessage('')
    try {
      const response = await fetch(`/api/books/${_bookId}/storyboard/${selectedShot.episode}/${selectedShot.shot_id}/prompt-lock`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ locked: nextLocked }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        const message = typeof payload?.detail === 'string' ? payload.detail : `HTTP ${response.status}`
        throw new Error(message)
      }
      await onRefresh()
      setPromptLockState('success')
      setPromptLockMessage(nextLocked ? '已锁定当前提示词版本，批量编译会跳过这个镜头。' : '已解除提示词锁定。')
    } catch (error) {
      setPromptLockState('error')
      setPromptLockMessage(error instanceof Error ? error.message : '提示词锁定操作失败。')
    }
  }

  const saveAcceptanceRecord = async () => {
    if (!selectedShot?.episode || !selectedShot?.shot_id) return
    setAcceptanceState('saving')
    setAcceptanceMessage('')
    try {
      const response = await fetch(`/api/books/${_bookId}/storyboard/${selectedShot.episode}/${selectedShot.shot_id}/acceptance-records`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          assetKind: acceptanceDraft.assetKind,
          assetId: acceptanceDraft.assetId,
          status: acceptanceDraft.status,
          failureTags: acceptanceDraft.failureTags,
          notes: acceptanceDraft.notes,
        }),
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        const message = typeof payload?.detail === 'string' ? payload.detail : `HTTP ${response.status}`
        throw new Error(message)
      }
      await onRefresh()
      setAcceptanceState('success')
      setAcceptanceMessage('验收记录已保存，并会进入下一轮提示词编译上下文。')
    } catch (error) {
      setAcceptanceState('error')
      setAcceptanceMessage(error instanceof Error ? error.message : '验收记录保存失败。')
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

        {transitionOverview?.counts ? (
          <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/45 px-3 py-2 text-[11px] text-slate-400">
            本集画面衔接：
            <span className="ml-1 text-emerald-200">已通过 {transitionOverview.counts.passed ?? 0}</span>
            <span className="ml-2 text-sky-200">待处理 {(transitionOverview.counts.needs_contract ?? 0) + (transitionOverview.counts.needs_handoff ?? 0) + (transitionOverview.counts.waiting_target ?? 0) + (transitionOverview.counts.needs_review ?? 0)}</span>
            {(transitionOverview.counts.stale ?? 0) > 0 ? <span className="ml-2 text-amber-200">需重新检查 {transitionOverview.counts.stale}</span> : null}
          </div>
        ) : null}

        <div className="mt-4 space-y-2">
          {currentShots.map((shot) => {
            const active = String(shot.shot_id) === String(selectedShot?.shot_id ?? '')
            const readiness = buildShotReadiness(shot)
            const degradedPrompt = hasDegradedPromptVersion(shot)
            const shortReadinessLabel = getShotReadinessShortLabel(readiness, shot)
            const transition = transitionOverview?.items?.find((item) => String(item.shot_id) === String(shot.shot_id))
            return (
              <button
                key={String(shot.shot_id)}
                type="button"
                data-episode={shot.episode}
                data-shot-id={String(shot.shot_id)}
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
                <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-400" title={readiness.nextAction}>
                  <span className="rounded-full border border-slate-700 bg-slate-950/60 px-2 py-0.5">
                    下一步 · {shortReadinessLabel}
                  </span>
                  {transition?.label ? (
                    <span className={`rounded-full border px-2 py-0.5 ${
                      transition.status === 'passed' || transition.status === 'not_applicable'
                        ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-200'
                        : transition.status === 'stale' || transition.status === 'needs_attention'
                          ? 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                          : 'border-sky-500/25 bg-sky-500/10 text-sky-200'
                    }`}>
                      衔接 · {transition.label}
                    </span>
                  ) : null}
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
            <StoryboardGateStrip
              gate={storyboardGate}
              selectedEpisode={selectedEpisode}
              lockedAt={selectedScriptDecision.lockedAt}
              releasedAt={selectedScriptDecision.releasedAt}
              onNavigateSection={onNavigateSection}
            />

            {productionReadinessState === 'loaded' && productionReadiness ? (
              <details className={`rounded-xl border p-4 ${
                productionReadiness.status === 'blocked'
                  ? 'border-rose-500/30 bg-rose-500/10'
                  : productionReadiness.status === 'warning'
                    ? 'border-amber-500/30 bg-amber-500/10'
                    : 'border-emerald-500/30 bg-emerald-500/10'
              }`}>
                <summary className="cursor-pointer list-none">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-xs font-medium text-slate-300">生产前质量体检</div>
                      <div className="mt-1 text-sm font-medium text-white">
                        {productionReadiness.status === 'blocked' ? '先处理生产阻塞，再继续批量生成' : productionReadiness.status === 'warning' ? '可继续局部工作，但建议先补质量风险' : '当前项目满足已知生产前检查'}
                      </div>
                    </div>
                    <div className="text-xs text-slate-200">阻塞 {productionReadiness.summary?.blocked_items ?? 0} · 告警 {productionReadiness.summary?.warning_items ?? 0}</div>
                  </div>
                </summary>
                <div className="mt-3 text-xs leading-6 text-slate-300">
                  {(productionReadiness.recommended_order ?? []).map((item) => <div key={item}>{item}</div>)}
                  {productionRepairPlan ? (
                    <div className="mt-3 rounded-lg border border-slate-700/70 bg-slate-950/30 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-medium text-slate-200">受控修复计划（只读）</span>
                        <span className="text-[11px] text-slate-400">
                          镜头 {productionRepairPlan.summary?.shot_actions ?? 0} 项 · 资产 {productionRepairPlan.summary?.asset_actions ?? 0} 项
                        </span>
                      </div>
                      <div className="mt-1 text-[11px] text-slate-400">
                        {productionRepairPlan.real_data_mutated === false ? '当前仅生成审阅计划，不会写入真实数据。' : '请先确认计划后再执行。'}
                      </div>
                      <div className="mt-1 text-[11px] text-slate-500">
                        计划指纹：{productionRepairPlan.confirmation_token || '不可用'} · 缺少回滚锚点：{productionRepairPlan.summary?.missing_rollback_anchors ?? 0}
                      </div>
                      {structureGovernancePlan && (structureGovernancePlan.summary?.affected_shots ?? 0) > 0 ? (
                        <div className="mt-3 rounded-md border border-amber-300/20 bg-amber-950/10 p-2.5 text-[11px] text-amber-100/85">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="font-medium">结构化镜头与旧诊断治理</span>
                            <span>受影响 {structureGovernancePlan.summary?.affected_shots ?? 0} · 身份修正 {structureGovernancePlan.summary?.identity_repairs ?? 0}</span>
                          </div>
                          <div className="mt-1 text-amber-100/65">仅修正派生镜头标识并使旧诊断过期；不会改导演文本、提示词、资产或已生成媒体。</div>
                          <div className="mt-2 flex flex-wrap items-center gap-2">
                            <button
                              type="button"
                              onClick={() => void previewStructureGovernance()}
                              disabled={structureGovernanceState === 'previewing' || structureGovernanceState === 'applying'}
                              className="rounded border border-amber-300/35 bg-amber-400/10 px-2 py-1 text-[11px] font-medium text-amber-100 hover:bg-amber-400/20 disabled:opacity-50"
                            >
                              {structureGovernanceState === 'previewing' ? '治理预检中…' : '预检结构治理'}
                            </button>
                            {structureGovernanceState === 'ready' ? (
                              <button type="button" onClick={() => void applyStructureGovernance()} className="rounded border border-amber-300/45 bg-amber-400/15 px-2 py-1 text-[11px] font-medium text-amber-100 hover:bg-amber-400/25">
                                确认写入治理结果
                              </button>
                            ) : null}
                          </div>
                          {structureGovernanceMessage ? <div className="mt-2 text-amber-100/75">{structureGovernanceMessage}</div> : null}
                        </div>
                      ) : null}
                      <div className="mt-2 flex flex-wrap gap-2">
                        {Array.from(new Set((productionRepairPlan.shot_actions ?? []).map((item) => item.action).filter(Boolean))).map((action) => {
                          const count = (productionRepairPlan.shot_actions ?? []).filter((item) => item.action === action).length
                          const label = (productionRepairPlan.shot_actions ?? []).find((item) => item.action === action)?.label || action
                          return <span key={action} className="rounded-full border border-slate-600 px-2 py-0.5 text-[11px] text-slate-300">{label} · {count}</span>
                        })}
                      </div>
                      {(productionRepairPlan.asset_actions ?? []).length > 0 ? (
                        <div className="mt-2 rounded-md border border-amber-300/15 bg-amber-950/10 px-2 py-1.5 text-[11px] text-amber-100/85">
                          <div className="font-medium">资产人工动作（仅审阅，不会自动锁定参考图）</div>
                          <div className="mt-1 space-y-0.5 text-amber-100/70">
                            {(productionRepairPlan.asset_actions ?? []).slice(0, 6).map((item) => (
                              <div key={`repair-asset-${item.asset_type}-${item.asset_id}`}>
                                {item.asset_type === 'character' ? '人物' : item.asset_type === 'scene' ? '场景' : '道具'} · {item.asset_name || '未命名资产'}：{item.label || '人工复核资产字段'}
                              </div>
                            ))}
                            {(productionRepairPlan.asset_actions ?? []).length > 6 ? <div>另有 {(productionRepairPlan.asset_actions ?? []).length - 6} 项，请前往资产中心按状态筛选处理。</div> : null}
                          </div>
                        </div>
                      ) : null}
                      {(productionRepairPlan.shot_actions ?? []).filter((item) => item.action === 'recompile_prompt').slice(0, 6).map((item) => (
                        <div key={`repair-anchor-${item.episode}-${item.shot_id}`} className="mt-1 text-[11px] text-slate-500">
                          第 {item.episode} 集 / 镜头 {item.shot_id} · baseline {item.rollback_anchor?.version ? `${item.rollback_anchor.kind === 'state_snapshot' ? '状态快照 ' : ''}v${item.rollback_anchor.version}` : '缺失'}
                        </div>
                      ))}
                      {(productionRepairPlan.shot_actions ?? []).filter((item) => item.action === 'review_executability').slice(0, 6).map((item) => {
                        const suggestionTypes = Array.from(new Set((item.executability_suggestions ?? []).map((suggestion) => suggestion.type).filter(Boolean)))
                        return <div key={`repair-suggestion-${item.episode}-${item.shot_id}`} className="mt-1 text-[11px] text-rose-200/80">
                          第 {item.episode} 集 / 镜头 {item.shot_id} · 候选：{suggestionTypes.includes('split_shot') ? '拆镜' : suggestionTypes.includes('extend_duration') ? '延长时长' : '人工复核'}
                        </div>
                      })}
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        {(productionRepairPlan.summary?.missing_rollback_anchors ?? 0) > 0 ? (
                          <>
                            <button
                              type="button"
                              onClick={() => void previewRollbackAnchors()}
                              disabled={rollbackAnchorState === 'previewing' || rollbackAnchorState === 'creating'}
                              className="rounded-lg border border-violet-300/35 bg-violet-400/10 px-3 py-1.5 text-[11px] font-medium text-violet-100 transition hover:border-violet-200 hover:bg-violet-400/20 disabled:opacity-50"
                            >
                              {rollbackAnchorState === 'previewing' ? '锚点预检中…' : '预检补建状态锚点'}
                            </button>
                            {rollbackAnchorState === 'ready' ? (
                              <button
                                type="button"
                                onClick={() => void createRollbackAnchors()}
                                className="rounded-lg border border-violet-300/45 bg-violet-400/15 px-3 py-1.5 text-[11px] font-medium text-violet-100 transition hover:border-violet-200 hover:bg-violet-400/25"
                              >
                                确认建立状态锚点
                              </button>
                            ) : null}
                          </>
                        ) : null}
                        <button
                          type="button"
                          onClick={() => void previewRepairExecution()}
                          disabled={repairExecutionState === 'previewing' || repairExecutionState === 'executing'}
                          className="rounded-lg border border-sky-300/35 bg-sky-400/10 px-3 py-1.5 text-[11px] font-medium text-sky-100 transition hover:border-sky-200 hover:bg-sky-400/20 disabled:opacity-50"
                        >
                          {repairExecutionState === 'previewing' ? '预检中…' : '预检可重编译镜头'}
                        </button>
                        {repairExecutionState === 'ready' ? (
                          <button
                            type="button"
                            onClick={() => void executeRepairPlan()}
                            className="rounded-lg border border-amber-300/40 bg-amber-400/15 px-3 py-1.5 text-[11px] font-medium text-amber-100 transition hover:border-amber-200 hover:bg-amber-400/25"
                          >
                            确认执行并创建任务
                          </button>
                        ) : null}
                      </div>
                      {rollbackAnchorMessage ? <div className="mt-2 text-[11px] text-violet-200/80">{rollbackAnchorMessage}</div> : null}
                      {repairExecutionMessage ? <div className="mt-2 text-[11px] text-slate-400">{repairExecutionMessage}</div> : null}
                      {repairTask ? (
                        <div className="mt-3 rounded-lg border border-slate-700/70 bg-slate-950/40 p-3">
                          <div className="flex items-center justify-between gap-2 text-[11px]">
                            <span className="font-medium text-slate-200">修复任务 {repairTask.task_id}</span>
                            <span className="text-slate-400">{repairTask.status || 'queued'} · {repairTask.progress ?? 0}%</span>
                          </div>
                          {(repairTask.results ?? []).map((item) => (
                            <div key={`repair-result-${item.episode}-${item.shot_id}`} className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400">
                              <span>第 {item.episode} 集 / 镜头 {item.shot_id} · {item.status === 'done' ? `v${item.version} 完成` : item.error || '失败'}</span>
                              {item.status === 'done' && item.baseline_version ? (
                                <button type="button" onClick={() => void rollbackRepairShot(item)} className="rounded border border-rose-400/30 px-2 py-0.5 text-rose-200 hover:bg-rose-400/10">回滚到 v{item.baseline_version}</button>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                  {productionReadiness.shots?.some((item) => item.status === 'blocked') ? (
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <span className="text-rose-100/90">优先阻塞镜头：</span>
                      {productionReadiness.shots.filter((item) => item.status === 'blocked').slice(0, 6).map((item) => (
                        <button
                          key={`${item.episode}-${item.shot_id}`}
                          type="button"
                          onClick={() => {
                            if (typeof item.episode === 'number') setSelectedEpisode(item.episode)
                            if (item.shot_id !== undefined) onSelectShot(String(item.shot_id))
                          }}
                          className="rounded-full border border-rose-400/35 bg-rose-400/10 px-2 py-0.5 text-[11px] text-rose-100 transition hover:border-rose-300 hover:bg-rose-400/20"
                        >
                          {item.episode ? `第 ${item.episode} 集 / ` : ''}镜头 {item.shot_id}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </details>
            ) : null}

            <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
              <CurrentShotActionHeader
                shotId={String(selectedShot.shot_id)}
                sceneName={selectedShot.scene_name}
                diagnosticLabel={diagnosticMeta.label}
                diagnosticToneClass={diagnosticMeta.tone}
                primaryActionLabel={storyboardCanvasPrimaryActionPlan.label}
                primaryActionDetail={storyboardCanvasPrimaryActionPlan.detail}
                primaryActionIsExecutable={storyboardCanvasPrimaryActionPlan.action !== 'view_results'}
                onPrimaryAction={runStoryboardCanvasPrimaryAction}
              />

              <ProductWorkspaceStoryboardContinuityPanel
                bookId={_bookId}
                episode={selectedShot.episode ?? selectedEpisode ?? 0}
                shotId={selectedShot.shot_id}
              />

              <ProductWorkspaceStoryboardDecisionPanel
                bookId={_bookId}
                episode={selectedShot.episode ?? selectedEpisode ?? 0}
                shotId={selectedShot.shot_id}
              />
              <ProductWorkspacePromptDraftPanel bookId={_bookId} episode={selectedShot.episode ?? selectedEpisode ?? 0} shotId={selectedShot.shot_id} onRefresh={onRefresh} />

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

              {selectedExecutability ? (
                <div className={`mt-4 rounded-xl border p-4 ${
                  selectedExecutability.status === 'blocked'
                    ? 'border-rose-500/40 bg-rose-500/10'
                    : selectedExecutability.status === 'warning'
                      ? 'border-amber-500/40 bg-amber-500/10'
                      : 'border-emerald-500/30 bg-emerald-500/10'
                }`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-xs font-medium text-slate-300">可拍性校验</div>
                      <div className="mt-1 text-sm font-medium text-white">{
                        selectedExecutability.status === 'blocked' ? '阻塞：暂不可生成视频' : selectedExecutability.status === 'warning' ? '告警：建议确认后生成' : '通过：动作承载正常'
                      }</div>
                    </div>
                    <span className="rounded-full border border-current/30 px-2 py-0.5 text-[11px] uppercase tracking-wide text-slate-200">{selectedExecutability.status || 'unknown'}</span>
                  </div>
                  {selectedExecutability.summary ? <div className="mt-2 text-xs leading-5 text-slate-300">{selectedExecutability.summary}</div> : null}
                  <div className="mt-3 grid gap-3 md:grid-cols-3">
                    <MiniMetric label="时长" value={`${selectedShot.duration ?? '-'}s`} />
                    <MiniMetric label="核心动作" value={String(selectedShot.prompt_compile_context?.core_action || selectedShot.structured_shot?.core_action || '未提取')} />
                    <MiniMetric label="动作节拍" value={`${selectedActionBeats.length} 段`} />
                  </div>
                  {selectedActionBeats.length > 0 ? (
                    <details className="mt-3 rounded-lg border border-slate-700/70 bg-slate-950/30 p-3">
                      <summary className="cursor-pointer text-[11px] text-slate-300">查看按秒动作节拍</summary>
                      <div className="mt-2 space-y-2">
                        {selectedActionBeats.map((beat, index) => {
                          const item = beat as Record<string, unknown>
                          const time = String(item.start_second ?? item.start ?? item.at ?? '').trim()
                          const description = String(item.description ?? item.action ?? item.text ?? '').trim()
                          return <div key={`action-beat-${index}`} className="text-xs text-slate-400">{time ? `${time}s · ` : ''}{description || JSON.stringify(item)}</div>
                        })}
                      </div>
                    </details>
                  ) : null}
                  {Array.isArray(selectedExecutability.recommendations) && selectedExecutability.recommendations.length > 0 ? (
                    <div className="mt-3 space-y-2">
                      {selectedExecutability.recommendations.slice(0, 3).map((item, index) => {
                        if (typeof item === 'string') return <div key={`exec-recommendation-${index}`} className="text-[11px] text-slate-300">{item}</div>
                        const recommendation = item as Record<string, unknown>
                        const type = String(recommendation.type || recommendation.label || recommendation.action || '优化建议')
                        const candidates = Array.isArray(recommendation.candidates) ? recommendation.candidates : []
                        return (
                          <div key={`exec-recommendation-${index}`} className="rounded-lg border border-slate-700 bg-slate-950/30 p-2 text-[11px] text-slate-300">
                            <span className="font-medium text-white">{type === 'extend_duration' ? `建议延长至 ${String(recommendation.recommended_duration || '')} 秒` : type === 'trim_non_core_actions' ? '建议删减非核心动作' : type === 'split_shot' ? `建议拆为 ${candidates.length || '多'} 个连续镜头` : type}</span>
                            {recommendation.reason ? <span className="ml-2 text-slate-400">{String(recommendation.reason)}</span> : null}
                            {recommendation.keep ? <div className="mt-1 text-slate-400">保留：{String(recommendation.keep)}</div> : null}
                            {candidates.length > 0 ? <div className="mt-2 space-y-1 text-slate-400">{candidates.map((candidate, candidateIndex) => {
                              const row = candidate as Record<string, unknown>
                              const beats = Array.isArray(row.action_beats) ? row.action_beats.join(' → ') : ''
                              return <div key={`exec-candidate-${candidateIndex}`}>镜头 {String(row.sequence || candidateIndex + 1)} · {String(row.recommended_duration || '')} 秒：{beats || String(row.purpose || '')}</div>
                            })}</div> : null}
                          </div>
                        )
                      })}
                    </div>
                  ) : null}
                  {hasSplitSuggestion ? (
                    <div className="mt-3 flex flex-wrap items-center gap-3">
                      <button
                        type="button"
                        onClick={saveExecutabilitySplitDraft}
                        disabled={splitDraftState === 'saving'}
                        className="rounded-lg border border-fuchsia-300/40 bg-fuchsia-400/15 px-3 py-1.5 text-xs font-medium text-white transition hover:border-fuchsia-200 hover:bg-fuchsia-400/20 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {splitDraftState === 'saving' ? '保存中…' : selectedSplitDraft ? '更新拆镜草案' : '保存拆镜草案'}
                      </button>
                      <span className="text-[11px] text-slate-400">保存仅供审阅，不会拆分或覆盖当前镜头。</span>
                    </div>
                  ) : null}
                  {selectedSplitDraft ? (
                    <div className="mt-3 rounded-lg border border-fuchsia-400/25 bg-fuchsia-400/5 p-3 text-[11px] text-slate-300">
                      <div className="font-medium text-fuchsia-100">已保存拆镜草案 · 待人工确认</div>
                      <div className="mt-1 text-slate-400">{selectedSplitDraft.reason || '可拍性校验建议拆镜'}</div>
                      {selectedSplitDraft.candidates?.map((candidate, index) => (
                        <div key={`saved-split-${index}`} className="mt-1 text-slate-400">镜头 {candidate.sequence || index + 1} · {candidate.recommended_duration || '-'} 秒：{candidate.action_beats?.join(' → ') || candidate.purpose || ''}</div>
                      ))}
                      {selectedSplitDraft.status === 'draft' ? (
                        <button
                          type="button"
                          onClick={applyExecutabilitySplitDraft}
                          disabled={splitApplyState === 'saving'}
                          className="mt-3 rounded-lg border border-rose-300/45 bg-rose-400/15 px-3 py-1.5 text-xs font-medium text-white transition hover:border-rose-200 hover:bg-rose-400/20 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {splitApplyState === 'saving' ? '应用中…' : '确认应用拆镜草案'}
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                  {splitDraftMessage ? <div className={`mt-2 text-[11px] ${splitDraftState === 'error' ? 'text-rose-300' : 'text-slate-400'}`}>{splitDraftMessage}</div> : null}
                  {splitApplyMessage ? <div className={`mt-2 text-[11px] ${splitApplyState === 'error' ? 'text-rose-300' : 'text-slate-400'}`}>{splitApplyMessage}</div> : null}
                </div>
              ) : null}

              <DirectorShotLanguageEditor
                draft={directorShotDraft}
                sourceTone={machinePromptExport?.source_layers?.has_user_director_shot_override ? 'cyan' : machinePromptExport ? 'slate' : 'amber'}
                sourceLabel={machinePromptExport?.source_layers?.has_user_director_shot_override ? '用户编辑版' : machinePromptExport ? '系统生成版' : '待加载'}
                saveState={directorShotSaveState}
                saveMessage={directorShotSaveMessage}
                canSave={Boolean(selectedShot)}
                readOnly={!canGenerateFromGate}
                onDraftChange={setDirectorShotDraft}
                onSaveAndRecompile={() => saveDirectorShotText(false)}
                onRestoreSystemVersion={() => saveDirectorShotText(true)}
              />

              <details className="mt-4 rounded-xl border border-slate-800 bg-slate-900 p-4">
                <summary className="cursor-pointer text-sm font-medium text-slate-300">高级：查看结构化分镜图提示词</summary>
                <div className="mt-1 text-xs leading-5 text-slate-500">用于复核画面结构和资产锚点；不是日常创作时需要阅读的机器字段。</div>
                <StoryboardImagePromptSectionsPanel sections={selectedShotStaticPromptSections} />
              </details>

              <CollapsiblePanel
                title="模型提示词（静态 / 运动 / 负向）"
                description="低频复核内容默认折叠；需要检查机器可读提示词时再展开。"
                className="mt-4"
              >
                <div className="grid gap-4 lg:grid-cols-2">
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
              </CollapsiblePanel>

              {canGenerateFromGate ? <ProductWorkspaceMachinePromptExportPanel
                machinePromptExport={machinePromptExport}
                machinePromptExportState={machinePromptExportState}
                machinePromptExportMessage={machinePromptExportMessage}
                machinePromptCopyMessage={machinePromptCopyMessage}
                machinePromptRecordMessage={machinePromptRecordMessage}
                machinePromptRecordState={machinePromptRecordState}
                machinePromptApiSubmissionMessage={machinePromptApiSubmissionMessage}
                machinePromptApiSubmissionState={machinePromptApiSubmissionState}
                machinePromptExportRecords={machinePromptExportRecords}
                machinePromptRecordHistoryState={machinePromptRecordHistoryState}
                minimaxH3CopyText={minimaxH3CopyText}
                minimaxH3Fields={minimaxH3Fields}
                machineTimeline={machineTimeline}
                genericZhVideoExport={genericZhVideoExport}
                h3ProviderSubmitSummary={h3ProviderSubmitSummary}
                temporaryDraft={machinePromptTemporaryDraft}
                isManualTemporaryDraft={isMachinePromptManualDraft}
                canRecordExport={Boolean(selectedShot)}
                onTemporaryDraftChange={setMachinePromptTemporaryDraft}
                onApplyTemporaryDraft={applyMachinePromptManualTemporaryDraft}
                onResetTemporaryDraft={resetMachinePromptManualTemporaryDraft}
                onLoadPreview={loadMachinePromptExportPreview}
                onCopyText={copyMachinePromptText}
                onDownloadFile={downloadMachinePromptExportFile}
                onSaveRecord={saveMachinePromptExportRecord}
                onSubmitApiTask={submitMachinePromptApiTask}
                onSubmitProviderTask={submitMachinePromptProviderTask}
                onLoadHistory={loadMachinePromptExportRecordHistory}
                onRestoreRecordDraft={restoreMachinePromptExportRecordDraft}
              /> : (
                <details className="mt-4 rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-4">
                  <summary className="cursor-pointer text-sm font-medium text-cyan-100">高级：查看机器提示词导出说明</summary>
                  <div className="mt-2 text-xs leading-5 text-cyan-100/75">上游剧本尚未放行。为避免导出或提交与未定稿内容不一致的机器提示词，此镜头暂只保留现有版本的只读信息。</div>
                </details>
              )}

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
                      已有当前镜头采纳视频：<span className="text-white">{adoptedVideo.title || adoptedVideo.label || adoptedVideo.id}</span>
                      <span className="ml-1 text-xs text-slate-400">（标题保留原始生成审计）</span>
                    </div>
                  ) : (
                    <div className="mt-2 text-sm text-slate-400">当前还没有采纳的视频版本。</div>
                  )}
                </div>
              </div>
            </div>

              <ProductWorkspaceStoryboardAdvancedToolsPanel
                episode={selectedShot.episode}
                shotId={String(selectedShot.shot_id)}
                assetStatus={selectedShot.asset_status}
                canGenerateFromGate={canGenerateFromGate}
                hasAdoptedFrame={hasAdoptedFrame}
                isGenerationBusy={isGenerationBusy}
                generationState={generationState}
                generationMessage={generationMessage}
                adoptedFrameLabel={String(adoptedImage?.title || adoptedImage?.label || adoptedImage?.id || '已采纳首帧')}
                adoptedFrameAssetId={String(adoptedImage?.id || '').trim()}
                referenceAssetIds={referenceAssetIds}
                compiledReferenceAssetIds={compiledReferenceAssetIds}
                effectiveReferenceAssetIds={effectiveReferenceAssetIds}
                effectiveReferencePayloadSource={effectiveReferencePayload.source}
                hasReferencePayloadDrift={hasReferencePayloadDrift}
                predictedVideoTaskMode={predictedVideoTaskMode}
                frameRecoveryTaskId={frameRecoveryTaskId}
                videoRecoveryTaskId={videoRecoveryTaskId}
                promptRecoveryTaskId={promptRecoveryTaskId}
                hasRecoveryTask={hasRecoveryTask}
                selectedShotRuntime={selectedShotRuntime}
                selectedShotPendingSummary={selectedShotPendingSummary}
                onNavigateCanvas={
                  onNavigateTaskSection
                    ? (target) => onNavigateTaskSection('canvas', target)
                    : undefined
                }
                onNavigateTasks={
                  onNavigateTaskSection
                    ? (target) => onNavigateTaskSection('tasks', target)
                    : undefined
                }
                onGenerateFrame={() => runStoryboardGeneration('frame')}
                onGenerateVideo={() => runStoryboardGeneration('video')}
              />

            <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
              <div className="space-y-6">
                <ProductWorkspaceCompileDiagnosticsPanel
                  promptVersionAudit={promptVersionAudit}
                  promptVersionAuditSummary={promptVersionAuditSummary}
                  recommendedRestoreVersion={recommendedRestoreVersion}
                  restoreOutcomeMeta={restoreOutcomeMeta}
                  historyActionState={historyActionState}
                  compilerChecks={compilerChecks}
                  compilerFocusCards={compilerFocusCards}
                  compilerWarnings={compilerWarnings}
                  blockingIssues={blockingIssues}
                  compileContextWarnings={compileContextWarnings}
                  compilerMetricItems={compilerMetricItems}
                  onRollbackRecommendedPromptVersion={rollbackRecommendedPromptVersion}
                />

                <ProductWorkspaceStoryboardRepairPanel
                  usedAssets={usedAssets}
                  repairActions={repairActions}
                  compileActionState={compileActionState}
                  compileActionMessage={compileActionMessage}
                />

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

                <ProductWorkspacePromptHistoryPanel
                  promptVersions={promptVersions}
                  historyState={historyState}
                  historyActionState={historyActionState}
                  historyActionMessage={historyActionMessage}
                  promptLockState={promptLockState}
                  promptLockMessage={promptLockMessage}
                  hasCompiledPrompt={hasCompiledPrompt}
                  isPromptLocked={selectedShot?.prompt_locked}
                  recommendedRestoreVersion={recommendedRestoreVersion}
                  onTogglePromptLock={togglePromptLock}
                  onRollbackPromptVersion={rollbackPromptVersion}
                />
              </div>

              <div className="space-y-6">
                <ProductWorkspaceStoryboardAcceptancePanel
                  acceptance={acceptance}
                  acceptanceAssetKind={acceptanceAssetKind}
                  acceptanceAssetId={acceptanceAssetId}
                  acceptanceDraft={acceptanceDraft}
                  acceptanceState={acceptanceState}
                  acceptanceMessage={acceptanceMessage}
                  onDraftChange={setAcceptanceDraft}
                  onSave={saveAcceptanceRecord}
                />

                <ProductWorkspaceStoryboardMediaPanel
                  bookId={_bookId}
                  shot={selectedShot}
                  imageAssets={imageAssets}
                  videoAssets={videoAssets}
                  archivedAssets={selectedShot.split_archived_assets}
                  referenceImages={referenceImages}
                  onUploaded={onRefresh}
                  allowManualUpload={canGenerateFromGate}
                />

                <ProductWorkspacePromptAuthorityPanel
                  promptAuthoritySummary={promptAuthoritySummary}
                  compileContextDisplay={selectedShotCompileContextDisplay}
                />
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
