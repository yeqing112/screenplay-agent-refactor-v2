import { useEffect, useMemo, useState } from 'react'
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  type Edge,
  type Node,
  type ReactFlowInstance,
} from 'reactflow'
import 'reactflow/dist/style.css'
import type { ScriptOutput, StoryboardShotOutput } from '../domain/bookOutputs'
import { getStoryboardGenerationLabels, waitForCreativeTask } from './productWorkspaceGeneration'
import type { AssetSummary } from './productWorkspaceAssets'
import {
  fetchCreativeTaskStatus,
  readPendingStoryboardTasks,
  readShotExecutionSummaries,
  readShotRuntimeState,
  reconcileCreativeTask,
  removePendingStoryboardTask,
  summarizePendingStoryboardTasks,
  upsertShotExecutionSummary,
  upsertPendingStoryboardTask,
} from './productWorkspaceRecovery'
import type { CanvasNavigationTarget, TaskNavigateHandler } from './productWorkspaceSectionContracts'
import {
  buildCanvasRecoveryActionLabel,
  buildCanvasRecoveryContinueActionPlan,
  buildCanvasRecoveryActionPlan,
  buildCanvasRecoveryClosureStatus,
  buildCanvasNavigationSummary,
  buildCanvasNavigationTargetStatus,
  buildProductWorkspaceCanvasBetaGraph,
  resolveCanvasEpisodeSelection,
  resolveCanvasNavigationNodeId,
  shouldShowCanvasSyncingState,
  shouldShowCanvasNavigationRefocusAction,
} from './productWorkspaceCanvasBeta'
import { resolveEffectiveReferenceAssetIds } from './productWorkspaceStoryboardReferencePayload'

interface Props {
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

type CanvasGraph = ReturnType<typeof buildProductWorkspaceCanvasBetaGraph>
type CanvasGraphNode = CanvasGraph['nodes'][number]
type CanvasNodeKind = CanvasGraphNode['kind']
type CanvasStatusFilter = 'all' | 'blocker' | 'output' | 'missing_reference'
type CollapsibleCanvasKind = 'character' | 'location' | 'prop'
type GenerationState = 'idle' | 'submitting' | 'success' | 'error'
type CompileState = 'idle' | 'submitting' | 'success' | 'error'
type CanvasCompileResult =
  | { status: 'done'; taskId: string; version: number | null; reason: string }
  | { status: 'pending'; taskId: string; reason: string }
  | { status: 'error'; message: string; reason: string }
  | { status: 'invalid' }
type CanvasShotPrimaryAction =
  | 'tasks_prompt'
  | 'tasks_frame'
  | 'tasks_video'
  | 'compile_prompts'
  | 'generate_frame'
  | 'generate_video'
  | 'open_storyboard'
type CanvasShotPrimaryActionPlan = {
  action: CanvasShotPrimaryAction
  label: string
  detail: string
}
type CanvasNodePrimaryActionPlan = {
  label: string
  detail: string
}
type CanvasShotRuntimeSummaryCard = {
  latestExecutionLabel: string
  pendingTaskLabel: string
  suggestedActionLabel: string
  latestSourceLine: string | null
}

export type CanvasViewNode = CanvasGraphNode & {
  isGroup?: boolean
  groupedNodeIds?: string[]
}

const FILTERABLE_KINDS: CanvasNodeKind[] = [
  'script',
  'shot',
  'character',
  'location',
  'prop',
  'image',
  'video',
  'qa',
  'delivery',
]

const COLLAPSIBLE_KINDS: CollapsibleCanvasKind[] = ['character', 'location', 'prop']

const STATUS_FILTERS: Array<{ key: CanvasStatusFilter; label: string }> = [
  { key: 'all', label: '全部状态' },
  { key: 'blocker', label: '阻塞' },
  { key: 'output', label: '有产出' },
  { key: 'missing_reference', label: '缺参考图' },
]

function kindAccent(kind: string) {
  switch (kind) {
    case 'script':
      return 'border-cyan-500/40 bg-cyan-500/10 text-cyan-200'
    case 'shot':
      return 'border-amber-500/40 bg-amber-500/10 text-amber-200'
    case 'character':
      return 'border-violet-500/40 bg-violet-500/10 text-violet-200'
    case 'location':
      return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
    case 'prop':
      return 'border-fuchsia-500/40 bg-fuchsia-500/10 text-fuchsia-200'
    case 'image':
      return 'border-orange-500/40 bg-orange-500/10 text-orange-200'
    case 'video':
      return 'border-blue-500/40 bg-blue-500/10 text-blue-200'
    case 'qa':
      return 'border-rose-500/40 bg-rose-500/10 text-rose-200'
    case 'delivery':
      return 'border-slate-500/40 bg-slate-500/10 text-slate-200'
    default:
      return 'border-slate-700 bg-slate-900 text-slate-200'
  }
}

function kindLabel(kind: string) {
  switch (kind) {
    case 'script':
      return '剧本'
    case 'shot':
      return '分镜'
    case 'character':
      return '人物'
    case 'location':
      return '场景'
    case 'prop':
      return '道具'
    case 'image':
      return '图片'
    case 'video':
      return '视频'
    case 'qa':
      return '质检'
    case 'delivery':
      return '交付'
    default:
      return '节点'
  }
}

function collapseToggleLabel(kind: CollapsibleCanvasKind) {
  if (kind === 'character') return '人物'
  if (kind === 'location') return '场景'
  return '道具'
}

function normalizeSearchText(value: string) {
  return value.trim().toLocaleLowerCase('zh-CN')
}

function statusFilterLabel(status: CanvasStatusFilter) {
  return STATUS_FILTERS.find((item) => item.key === status)?.label ?? '全部状态'
}

function nodeMatchesStatus(node: CanvasGraphNode, status: CanvasStatusFilter) {
  if (status === 'all') return true
  if (status === 'blocker') return Boolean(node.hasBlocker)
  if (status === 'output') return Boolean(node.hasOutput)
  return Boolean(node.missingReference)
}

function nodeStatusBadges(node: CanvasGraphNode) {
  return [
    node.hasBlocker
      ? { key: 'blocker', label: '阻塞', className: 'border-rose-500/40 bg-rose-500/10 text-rose-200' }
      : null,
    node.hasOutput
      ? { key: 'output', label: '有产出', className: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200' }
      : null,
    node.missingReference
      ? {
          key: 'missing_reference',
          label: '缺参考图',
          className: 'border-amber-500/40 bg-amber-500/10 text-amber-200',
        }
      : null,
  ].filter(Boolean) as Array<{ key: string; label: string; className: string }>
}

function buildGroupTitle(kind: CollapsibleCanvasKind) {
  return `${collapseToggleLabel(kind)}分组`
}

function buildGroupSubtitle(episode: number | null, count: number) {
  if (episode) return `第 ${episode} 集 · ${count} 个节点`
  return `${count} 个节点`
}

function buildGroupMeta(kind: CollapsibleCanvasKind, bucket: CanvasGraphNode[]) {
  const blockerCount = bucket.filter((item) => item.hasBlocker).length
  const outputCount = bucket.filter((item) => item.hasOutput).length
  const missingReferenceCount = bucket.filter((item) => item.missingReference).length
  const titles = Array.from(new Set(bucket.map((item) => item.title))).slice(0, 3)

  return [
    `已折叠 ${collapseToggleLabel(kind)} 节点：${bucket.length}`,
    blockerCount ? `阻塞：${blockerCount}` : '',
    outputCount ? `有产出：${outputCount}` : '',
    missingReferenceCount ? `缺参考图：${missingReferenceCount}` : '',
    titles.length ? `示例：${titles.join(' / ')}` : '',
  ].filter(Boolean)
}

export function collapseCanvasGraphByKind(
  nodes: CanvasGraphNode[],
  edges: CanvasGraph['edges'],
  collapsedKinds: CollapsibleCanvasKind[],
): { nodes: CanvasViewNode[]; edges: CanvasGraph['edges'] } {
  if (collapsedKinds.length === 0) {
    return { nodes, edges }
  }

  const collapsedKindSet = new Set<CanvasNodeKind>(collapsedKinds)
  const groupedNodeIds = new Map<string, string>()
  const groups = new Map<string, CanvasGraphNode[]>()
  const passthroughNodes: CanvasViewNode[] = []

  for (const node of nodes) {
    if (!collapsedKindSet.has(node.kind)) {
      passthroughNodes.push(node)
      continue
    }

    const episode = Number(node.route?.options?.episode ?? 0) || 0
    const groupId = `canvas-group-${node.kind}-${episode || 'all'}`
    groupedNodeIds.set(node.id, groupId)
    const bucket = groups.get(groupId) ?? []
    bucket.push(node)
    groups.set(groupId, bucket)
  }

  const groupedNodes: CanvasViewNode[] = []
  for (const [groupId, bucket] of groups.entries()) {
    const first = bucket[0]
    const episode = Number(first.route?.options?.episode ?? 0) || null
    const titles = Array.from(new Set(bucket.map((item) => item.title)))
    const previewUrl = bucket.find((item) => item.previewUrl)?.previewUrl ?? null
    const averageY = bucket.reduce((sum, item) => sum + item.y, 0) / bucket.length
    const kind = first.kind as CollapsibleCanvasKind

    groupedNodes.push({
      ...first,
      id: groupId,
      title: buildGroupTitle(kind),
      subtitle: buildGroupSubtitle(episode, bucket.length),
      meta: buildGroupMeta(kind, bucket),
      y: averageY,
      previewUrl,
      hasOutput: bucket.some((item) => item.hasOutput),
      hasBlocker: bucket.some((item) => item.hasBlocker),
      missingReference: bucket.some((item) => item.missingReference),
      isGroup: true,
      groupedNodeIds: bucket.map((item) => item.id),
      route: {
        section: 'assets',
        options: {
          episode,
          assetId: first.route?.options?.assetId ?? null,
          assetLabel: titles[0] ?? null,
        },
      },
    })
  }

  const dedupedEdges = new Map<string, CanvasGraph['edges'][number]>()
  for (const edge of edges) {
    const source = groupedNodeIds.get(edge.source) ?? edge.source
    const target = groupedNodeIds.get(edge.target) ?? edge.target
    if (source === target) continue
    const key = `${source}:${target}`
    if (!dedupedEdges.has(key)) {
      dedupedEdges.set(key, {
        ...edge,
        id: `collapsed-${key}`,
        source,
        target,
      })
    }
  }

  return {
    nodes: [...passthroughNodes, ...groupedNodes],
    edges: Array.from(dedupedEdges.values()),
  }
}

function resolveVisibleSelectedNodeId(
  visibleNodes: CanvasViewNode[],
  currentSelectedNodeId: string | null,
  targetNodeId: string | null,
) {
  if (targetNodeId) {
    const directHit = visibleNodes.find((node) => node.id === targetNodeId)
    if (directHit) return directHit.id

    const groupedHit = visibleNodes.find((node) => node.groupedNodeIds?.includes(targetNodeId))
    if (groupedHit) return groupedHit.id
  }

  if (currentSelectedNodeId && visibleNodes.some((node) => node.id === currentSelectedNodeId)) {
    return currentSelectedNodeId
  }

  return visibleNodes[0]?.id ?? null
}

function toFlowNode(node: CanvasViewNode, selectedNodeId: string | null): Node {
  const isSelected = selectedNodeId === node.id
  const badges = nodeStatusBadges(node)
  const runtimePendingKinds = node.runtimeSummary?.pendingKinds ?? []
  const hasRuntimePending = runtimePendingKinds.length > 0
  const latestExecutionLabel = node.runtimeSummary?.latestExecutionLabel ?? ''
  const hasRuntimeSummary = Boolean(latestExecutionLabel)

  return {
    id: node.id,
    position: { x: node.x, y: node.y },
    data: {
      label: (
        <div className="w-[240px]">
          <div className="flex items-start justify-between gap-3">
            <span className={`rounded-md border px-2 py-0.5 text-[10px] font-medium ${kindAccent(node.kind)}`}>
              {kindLabel(node.kind)}
            </span>
            {badges.length ? (
              <div className="flex flex-wrap justify-end gap-1">
                {badges.slice(0, 2).map((badge) => (
                  <span key={badge.key} className={`rounded-md border px-1.5 py-0.5 text-[10px] ${badge.className}`}>
                    {badge.label}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
          <div className="mt-3 text-sm font-semibold text-white">{node.title}</div>
          {node.isGroup ? <div className="mt-1 text-[11px] text-sky-300">已折叠分组</div> : null}
          <div className="mt-1 text-xs leading-5 text-slate-400">{node.subtitle}</div>
          {hasRuntimeSummary || hasRuntimePending ? (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {hasRuntimeSummary ? (
                <span className="rounded-md border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-[10px] text-sky-200">
                  最近执行
                </span>
              ) : null}
              {hasRuntimePending ? (
                <span className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-200">
                  待回收 {runtimePendingKinds.length}
                </span>
              ) : null}
              {node.runtimeSummary?.hasAdoptedFrame ? (
                <span className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-200">
                  已采纳首帧
                </span>
              ) : null}
              {node.runtimeSummary?.hasAdoptedVideo ? (
                <span className="rounded-md border border-fuchsia-500/30 bg-fuchsia-500/10 px-2 py-0.5 text-[10px] text-fuchsia-200">
                  已采纳视频
                </span>
              ) : null}
            </div>
          ) : null}
          {node.meta.length ? (
            <div className="mt-3 space-y-1 text-[11px] leading-4 text-slate-500">
              {node.meta.slice(0, 4).map((item) => (
                <div key={item}>{item}</div>
              ))}
            </div>
          ) : null}
          {node.previewUrl ? (
            <img
              src={node.previewUrl}
              alt={node.title}
              className="mt-3 h-24 w-full rounded-md border border-slate-700 object-cover"
            />
          ) : null}
        </div>
      ),
      route: node.route,
    },
    draggable: false,
    selectable: true,
    connectable: false,
    style: {
      width: 260,
      borderRadius: 10,
      border: isSelected
        ? '1px solid rgba(56, 189, 248, 0.95)'
        : hasRuntimePending
          ? '1px solid rgba(245, 158, 11, 0.75)'
          : hasRuntimeSummary
            ? '1px solid rgba(14, 165, 233, 0.65)'
            : '1px solid rgba(51, 65, 85, 0.9)',
      background: isSelected ? '#04111f' : '#020617',
      padding: 14,
      boxShadow: isSelected
        ? '0 0 0 1px rgba(56, 189, 248, 0.2), 0 18px 40px rgba(2, 6, 23, 0.5)'
        : hasRuntimePending
          ? '0 0 0 1px rgba(245, 158, 11, 0.12), 0 12px 30px rgba(2, 6, 23, 0.35)'
          : hasRuntimeSummary
            ? '0 0 0 1px rgba(14, 165, 233, 0.1), 0 12px 30px rgba(2, 6, 23, 0.35)'
        : '0 12px 30px rgba(2, 6, 23, 0.35)',
    },
  }
}

function toFlowEdge(edge: CanvasGraph['edges'][number], selectedNodeId: string | null): Edge {
  const isHighlighted = selectedNodeId === edge.source || selectedNodeId === edge.target
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    animated: false,
    style: {
      stroke: isHighlighted ? '#38bdf8' : '#475569',
      strokeWidth: isHighlighted ? 2.1 : 1.5,
      opacity: selectedNodeId ? (isHighlighted ? 1 : 0.28) : 1,
    },
  }
}

function buildEpisodeOptions(
  scripts: ScriptOutput[],
  shotsByEpisode: Record<number, StoryboardShotOutput[]>,
  qaEntries: Array<{ id?: number; episode: number; result: unknown; error_count?: number }>,
) {
  return Array.from(
    new Set([
      ...scripts.map((item) => item.episode),
      ...Object.keys(shotsByEpisode).map((value) => Number(value)),
      ...qaEntries.map((item) => item.episode),
    ]),
  )
    .filter((value) => Number.isFinite(value) && value > 0)
    .sort((left, right) => left - right)
}

function findSelectedShot(
  node: CanvasViewNode | null,
  shotsByEpisode: Record<number, StoryboardShotOutput[]>,
) {
  if (!node || node.kind !== 'shot' || node.route?.section !== 'storyboard') return null
  const episode = Number(node.route.options?.episode ?? 0)
  const shotId = String(node.route.options?.shotId ?? '').trim()
  if (!episode || !shotId) return null
  return (
    (shotsByEpisode[episode] ?? []).find((shot) => String(shot.shot_id) === shotId) ?? null
  )
}

function formatGenerationErrorMessage(raw: string, fallback: string) {
  const message = String(raw || '').trim()
  if (!message) return fallback
  if (message.includes('Storyboard prompts are empty')) {
    return '当前镜头提示词为空，需要先补齐或重编译提示词后再生成首帧。'
  }
  if (message.includes('This episode does not have a usable script yet')) {
    return '当前集还没有可用剧本，先完成剧本再生成首帧。'
  }
  if (message.includes('An adopted first-frame image is required before generating video.')) {
    return '当前镜头还没有已采纳首帧，不能直接生成视频。请先生成并采纳一张分镜图。'
  }
  if (message.includes('The selected first-frame image is missing a usable preview URL.')) {
    return '当前已采纳首帧缺少可用预览地址，暂时不能生成视频。请重新生成或重新采纳首帧。'
  }
  return message
}

function findLatestAdoptedAsset<T extends { adopted?: boolean }>(items: T[] | undefined) {
  if (!Array.isArray(items) || items.length === 0) return null
  return items.find((item) => item.adopted) ?? items[items.length - 1] ?? null
}

function canvasRecoveryActionButtonClass(isPrimary: boolean) {
  return isPrimary
    ? 'rounded-lg border border-sky-400 bg-sky-400/15 px-3 py-1.5 text-xs font-medium text-white transition hover:border-sky-300 hover:bg-sky-400/20'
    : 'rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:border-sky-500 hover:text-white'
}

export function getCanvasExecutionSummaryLabel(action: 'frame' | 'video', generationChain?: string | null) {
  if (action === 'frame') {
    if (generationChain === 'recompile_then_frame' || generationChain === 'canvas_recovery_recompile_then_frame') {
      return '重编后生成首帧'
    }
    if (generationChain === 'canvas_recovery_continue_after_prompt') {
      return '恢复后继续生成首帧'
    }
    return '生成首帧'
  }

  if (generationChain === 'recompile_then_video' || generationChain === 'canvas_recovery_recompile_then_video') {
    return '重编后继续生成视频'
  }
  if (
    generationChain === 'canvas_recovery_continue_after_frame' ||
    generationChain === 'canvas_recovery_continue_after_prompt'
  ) {
    return '恢复后继续生成视频'
  }
  return '生成视频'
}

export function buildCanvasShotRuntimeSummaryCard(input: {
  latestExecutionLabel?: string | null
  pendingTaskSummary: {
    count: number
    joinedKindLabels: string
    latestTaskId: string | null
    latestSourceLabel: string | null
  }
}): CanvasShotRuntimeSummaryCard {
  return {
    latestExecutionLabel: input.latestExecutionLabel || '未记录',
    pendingTaskLabel: input.pendingTaskSummary.count > 0 ? input.pendingTaskSummary.joinedKindLabels : '无',
    suggestedActionLabel:
      input.pendingTaskSummary.count > 0
        ? '先回收任务'
        : input.latestExecutionLabel
          ? '继续复核结果'
          : '可继续执行',
    latestSourceLine:
      input.pendingTaskSummary.latestTaskId && input.pendingTaskSummary.latestSourceLabel
        ? `最近待回收来源：${input.pendingTaskSummary.latestSourceLabel} · 任务 ID：${input.pendingTaskSummary.latestTaskId}`
        : null,
  }
}

export function buildNavigationContinueChainMeta(input: {
  action: 'generate_frame' | 'generate_video' | 'recompile_then_frame' | 'recompile_then_video'
  recoveryKind?: 'prompt' | 'frame' | 'video' | 'reference' | null
}) {
  if (input.action === 'generate_video') {
    if (input.recoveryKind === 'frame') {
      return { generationChain: 'canvas_recovery_continue_after_frame' }
    }
    if (input.recoveryKind === 'prompt') {
      return { generationChain: 'canvas_recovery_continue_after_prompt' }
    }
    return { generationChain: 'canvas_generate_video' }
  }

  if (input.action === 'generate_frame') {
    if (input.recoveryKind === 'prompt') {
      return { generationChain: 'canvas_recovery_continue_after_prompt' }
    }
    return { generationChain: 'canvas_generate_frame' }
  }

  if (input.action === 'recompile_then_video') {
    return {
      generationChain: 'canvas_recovery_recompile_then_video',
      compileReason: 'canvas-recovery-reference-before-video',
    }
  }

  return {
    generationChain: 'canvas_recovery_recompile_then_frame',
    compileReason: 'canvas-recovery-reference-before-frame',
  }
}

export function buildCanvasShotPrimaryActionPlan(input: {
  promptRecoveryTaskId?: string | null
  frameRecoveryTaskId?: string | null
  videoRecoveryTaskId?: string | null
  hasCompiledPrompt?: boolean
  hasAdoptedFrame?: boolean
  hasAdoptedVideo?: boolean
}) {
  if (input.videoRecoveryTaskId) {
    return {
      action: 'tasks_video',
      label: '继续回收视频任务',
      detail: `当前镜头已有待回收视频任务 ${input.videoRecoveryTaskId}，优先先把结果回收到项目链路，再决定是否继续重发或采纳。`,
    } satisfies CanvasShotPrimaryActionPlan
  }

  if (input.frameRecoveryTaskId) {
    return {
      action: 'tasks_frame',
      label: '继续回收首帧任务',
      detail: `当前镜头已有待回收首帧任务 ${input.frameRecoveryTaskId}，建议先确认结果是否已返回，再继续视频链路。`,
    } satisfies CanvasShotPrimaryActionPlan
  }

  if (input.promptRecoveryTaskId) {
    return {
      action: 'tasks_prompt',
      label: '继续回收提示词任务',
      detail: `当前镜头已有待回收提示词任务 ${input.promptRecoveryTaskId}，建议先收口这次重编译，再继续首帧或视频生成。`,
    } satisfies CanvasShotPrimaryActionPlan
  }

  if (!input.hasCompiledPrompt) {
    return {
      action: 'compile_prompts',
      label: '先重编译提示词',
      detail: '当前镜头还没有稳定的静态提示词，先把提示词编译到最新版本，再继续首帧和视频生成。',
    } satisfies CanvasShotPrimaryActionPlan
  }

  if (!input.hasAdoptedFrame) {
    return {
      action: 'generate_frame',
      label: '先生成首帧',
      detail: '提示词已经就绪，但当前镜头还没有已采纳首帧，下一步应先补齐分镜图参考。',
    } satisfies CanvasShotPrimaryActionPlan
  }

  if (!input.hasAdoptedVideo) {
    return {
      action: 'generate_video',
      label: '继续生成视频',
      detail: '当前镜头已经有已采纳首帧，下一步可以直接沿用首帧与参考图提交视频生成。',
    } satisfies CanvasShotPrimaryActionPlan
  }

  return {
    action: 'open_storyboard',
    label: '前往镜头工作台确认结果',
    detail: '当前镜头的提示词、首帧和视频链路都已经有结果，更适合回镜头工作台确认采纳状态与下游衔接。',
  } satisfies CanvasShotPrimaryActionPlan
}

export function buildCanvasNodePrimaryActionPlan(node: CanvasViewNode | null) {
  if (!node) return null

  if (node.kind === 'script') {
    return {
      label: node.hasBlocker ? '前往剧本工作台补齐内容' : '前往剧本工作台确认分集内容',
      detail: node.hasBlocker
        ? '当前分集剧本仍有待补信息，建议先回剧本工作台收口文本，再继续分镜和视觉链路。'
        : '当前分集剧本已经进入可用状态，适合回剧本工作台确认台词、节奏和下游交接。 ',
    } satisfies CanvasNodePrimaryActionPlan
  }

  if (node.kind === 'character' || node.kind === 'location' || node.kind === 'prop') {
    const hasShotContext = Boolean(String(node.route?.options?.shotId ?? '').trim())
    if (node.missingReference) {
      return {
        label: hasShotContext ? '前往资产中心补齐该镜头参考图' : '前往资产中心补齐参考图',
        detail: hasShotContext
          ? '当前资产节点仍缺少可用参考图，并且已经命中具体镜头。建议直接在资产中心补齐该镜头所需版本，再继续提示词继承、首帧生成和视频链路。'
          : '当前资产节点仍缺少可用参考图，建议先在资产中心补图，再继续提示词继承、首帧生成和视频链路。',
      } satisfies CanvasNodePrimaryActionPlan
    }
    if (node.hasBlocker) {
      return {
        label: hasShotContext ? '前往资产中心处理该镜头阻塞' : '前往资产中心处理阻塞',
        detail: hasShotContext
          ? '当前资产已经命中具体镜头，但这一镜头下仍存在阻塞项。建议先回资产中心整理版本、引用和镜头命中关系。'
          : '当前资产已经接入创作链路，但仍存在阻塞项，建议先回资产中心整理版本、引用或命中镜头关系。',
      } satisfies CanvasNodePrimaryActionPlan
    }
    if (node.hasOutput) {
      return {
        label: hasShotContext ? '前往资产中心确认该镜头引用状态' : '前往资产中心确认引用状态',
        detail: hasShotContext
          ? '当前资产已经有可用产出，并且命中具体镜头。下一步更适合确认这一镜头下的默认图、精调版本和下游继承是否稳定。'
          : '当前资产已经有可用产出，下一步更适合确认默认图、分镜命中关系与下游继承是否稳定。',
      } satisfies CanvasNodePrimaryActionPlan
    }
    return {
      label: '前往资产中心继续整理',
      detail: '当前资产节点已经进入画布链路，但还需要在资产中心继续整理版本、标签和镜头绑定。',
    } satisfies CanvasNodePrimaryActionPlan
  }

  if (node.kind === 'image' || node.kind === 'video') {
    return {
      label: node.hasBlocker ? '前往镜头工作台处理产出问题' : '前往镜头工作台确认产出采纳',
      detail: node.hasBlocker
        ? '当前产出节点已经暴露出问题，建议回镜头工作台复核采纳状态、参考图引用和重生成路径。'
        : '当前产出节点已经存在结果，下一步应回镜头工作台确认是否采纳并继续下游链路。',
    } satisfies CanvasNodePrimaryActionPlan
  }

  if (node.kind === 'qa') {
    return {
      label: node.hasBlocker ? '前往 QA 修复处理问题' : '前往 QA 修复复核结果',
      detail: node.hasBlocker
        ? '当前 QA 节点仍有待处理问题，建议先回 QA 修复工作台逐项收口，再决定是否放行交付。'
        : '当前 QA 节点没有明显阻塞，更适合回 QA 修复工作台做最终复核与放行确认。',
    } satisfies CanvasNodePrimaryActionPlan
  }

  if (node.kind === 'delivery') {
    return {
      label: node.hasBlocker ? '前往导出中心处理交付阻塞' : '前往导出中心确认可交付状态',
      detail: node.hasBlocker
        ? '当前交付节点仍未达到稳定可导出状态，建议先回导出中心确认阻塞来源和缺失项。'
        : '当前交付节点已经接近收口，更适合回导出中心确认导出包、版本和最终放行状态。',
    } satisfies CanvasNodePrimaryActionPlan
  }

  return {
    label: '打开对应模块继续处理',
    detail: '当前节点已经映射到正式工作区，下一步更适合进入对应模块继续推进真实创作链路。',
  } satisfies CanvasNodePrimaryActionPlan
}

export default function ProductWorkspaceCanvasBetaSection({
  bookId,
  bookTitle,
  isProjectDataLoading,
  scripts,
  shotsByEpisode,
  allAssets,
  qaEntries,
  navigationTarget,
  onRefreshAll,
  onNavigateTaskSection,
}: Props) {
  const [selectedEpisode, setSelectedEpisode] = useState<'all' | number>('all')
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [activeKinds, setActiveKinds] = useState<CanvasNodeKind[]>(FILTERABLE_KINDS)
  const [statusFilter, setStatusFilter] = useState<CanvasStatusFilter>('all')
  const [collapsedKinds, setCollapsedKinds] = useState<CollapsibleCanvasKind[]>([])
  const [compileState, setCompileState] = useState<CompileState>('idle')
  const [compileMessage, setCompileMessage] = useState('')
  const [promptRecoveryTaskId, setPromptRecoveryTaskId] = useState<string | null>(null)
  const [generationState, setGenerationState] = useState<GenerationState>('idle')
  const [generationMessage, setGenerationMessage] = useState('')
  const [frameRecoveryTaskId, setFrameRecoveryTaskId] = useState<string | null>(null)
  const [videoRecoveryTaskId, setVideoRecoveryTaskId] = useState<string | null>(null)
  const [canvasRuntimeVersion, setCanvasRuntimeVersion] = useState(0)

  const pendingStoryboardTasks = useMemo(
    () => readPendingStoryboardTasks(bookId),
    [bookId, canvasRuntimeVersion],
  )

  const shotExecutionSummaries = useMemo(
    () => readShotExecutionSummaries(bookId),
    [bookId, canvasRuntimeVersion],
  )
  const refreshCanvasRuntimeState = () => {
    setCanvasRuntimeVersion((current) => current + 1)
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
    upsertShotExecutionSummary(bookId, {
      episode: selectedShot.episode,
      shotId: String(selectedShot.shot_id),
      action,
      label,
      generationChain: options?.generationChain ?? null,
      promptVersion: options?.promptVersion ?? null,
      taskId: options?.taskId ?? null,
      updatedAt: new Date().toISOString(),
    })
    refreshCanvasRuntimeState()
  }

  const episodeOptions = useMemo(
    () => buildEpisodeOptions(scripts, shotsByEpisode, qaEntries),
    [qaEntries, scripts, shotsByEpisode],
  )

  useEffect(() => {
    const normalizedSelection = resolveCanvasEpisodeSelection({
      selectedEpisode,
      availableEpisodes: episodeOptions,
      navigationTargetEpisode: navigationTarget?.episode ?? null,
    })
    if (normalizedSelection !== selectedEpisode) {
      setSelectedEpisode(normalizedSelection)
    }
  }, [episodeOptions, navigationTarget?.episode, selectedEpisode])

  const graph = useMemo(
    () =>
      buildProductWorkspaceCanvasBetaGraph({
        bookTitle,
        scripts,
        shotsByEpisode,
        allAssets,
        qaEntries,
        pendingStoryboardTasks,
        shotExecutionSummaries,
        selectedEpisode,
      }),
    [allAssets, bookTitle, pendingStoryboardTasks, qaEntries, scripts, selectedEpisode, shotExecutionSummaries, shotsByEpisode],
  )

  const targetNodeId = useMemo(
    () => resolveCanvasNavigationNodeId(graph, navigationTarget),
    [graph, navigationTarget],
  )
  const navigationSummary = useMemo(
    () => buildCanvasNavigationSummary(navigationTarget),
    [navigationTarget],
  )
  const navigationTargetStatus = useMemo(
    () =>
      buildCanvasNavigationTargetStatus({
        target: navigationTarget,
        targetNodeId,
        isProjectDataLoading,
      }),
    [isProjectDataLoading, navigationTarget, targetNodeId],
  )
  const showSyncingState = useMemo(
    () =>
      shouldShowCanvasSyncingState({
        graphNodeCount: graph.nodes.length,
        isProjectDataLoading,
      }),
    [graph.nodes.length, isProjectDataLoading],
  )
  const canRefocusNavigationTarget = useMemo(
    () =>
      shouldShowCanvasNavigationRefocusAction({
        target: navigationTarget,
        targetNodeId,
      }),
    [navigationTarget, targetNodeId],
  )

  const statusCounts = useMemo(
    () => ({
      all: graph.nodes.length,
      blocker: graph.nodes.filter((node) => node.hasBlocker).length,
      output: graph.nodes.filter((node) => node.hasOutput).length,
      missing_reference: graph.nodes.filter((node) => node.missingReference).length,
    }),
    [graph.nodes],
  )

  const visibleGraph = useMemo(() => {
    const normalizedQuery = normalizeSearchText(searchQuery)
    const filteredNodes = graph.nodes.filter((node) => {
      if (!activeKinds.includes(node.kind)) return false
      if (!nodeMatchesStatus(node, statusFilter)) return false
      if (!normalizedQuery) return true

      const haystack = normalizeSearchText(
        [
          node.title,
          node.subtitle,
          ...node.meta,
          kindLabel(node.kind),
          ...nodeStatusBadges(node).map((item) => item.label),
        ].join(' '),
      )
      return haystack.includes(normalizedQuery)
    })
    const filteredNodeIds = new Set(filteredNodes.map((node) => node.id))
    const filteredEdges = graph.edges.filter(
      (edge) => filteredNodeIds.has(edge.source) && filteredNodeIds.has(edge.target),
    )

    return collapseCanvasGraphByKind(filteredNodes, filteredEdges, collapsedKinds)
  }, [activeKinds, collapsedKinds, graph.edges, graph.nodes, searchQuery, statusFilter])

  useEffect(() => {
    if (!navigationTarget) return

    const targetEpisode = Number(navigationTarget.episode ?? 0) || 'all'
    setSelectedEpisode(targetEpisode)
    setStatusFilter('all')
    setActiveKinds(FILTERABLE_KINDS)
    setCollapsedKinds([])
    setSearchQuery('')
  }, [navigationTarget])

  const refocusNavigationTarget = () => {
    if (!navigationTarget || !targetNodeId) return
    const targetEpisode = Number(navigationTarget.episode ?? 0) || 'all'
    setSelectedEpisode(targetEpisode)
    setStatusFilter('all')
    setActiveKinds(FILTERABLE_KINDS)
    setCollapsedKinds([])
    setSearchQuery('')
    setSelectedNodeId(targetNodeId)
  }

  useEffect(() => {
    setSelectedNodeId((current) => resolveVisibleSelectedNodeId(visibleGraph.nodes, current, targetNodeId))
  }, [targetNodeId, visibleGraph.nodes])

  const selectedNode = useMemo(
    () => visibleGraph.nodes.find((node) => node.id === selectedNodeId) ?? null,
    [selectedNodeId, visibleGraph.nodes],
  )
  const selectedNodePrimaryActionPlan = useMemo(
    () => (selectedNode && selectedNode.kind !== 'shot' ? buildCanvasNodePrimaryActionPlan(selectedNode) : null),
    [selectedNode],
  )

  const selectedShot = useMemo(
    () => findSelectedShot(selectedNode, shotsByEpisode),
    [selectedNode, shotsByEpisode],
  )
  const selectedShotRuntime = useMemo(
    () =>
      selectedShot?.episode && selectedShot?.shot_id
        ? readShotRuntimeState(bookId, selectedShot.episode, String(selectedShot.shot_id))
        : { latestExecutionSummary: null, pendingTasks: [] },
    [bookId, canvasRuntimeVersion, selectedShot?.episode, selectedShot?.shot_id],
  )
  const selectedShotPendingSummary = useMemo(
    () => summarizePendingStoryboardTasks(selectedShotRuntime.pendingTasks),
    [selectedShotRuntime.pendingTasks],
  )
  const selectedShotRuntimeCard = useMemo(
    () =>
      buildCanvasShotRuntimeSummaryCard({
        latestExecutionLabel: selectedShotRuntime.latestExecutionSummary?.label ?? null,
        pendingTaskSummary: selectedShotPendingSummary,
      }),
    [selectedShotPendingSummary, selectedShotRuntime.latestExecutionSummary?.label],
  )

  const adoptedImage = useMemo(
    () => findLatestAdoptedAsset(selectedShot?.assets?.images ?? []),
    [selectedShot?.assets?.images],
  )
  const adoptedVideo = useMemo(
    () => findLatestAdoptedAsset(selectedShot?.assets?.videos ?? []),
    [selectedShot?.assets?.videos],
  )
  const selectedShotLatestExecutionSummary = useMemo(
    () =>
      selectedShot?.episode && selectedShot?.shot_id
        ? shotExecutionSummaries.find(
            (item) =>
              item.episode === selectedShot.episode &&
              String(item.shotId) === String(selectedShot.shot_id),
          ) ?? null
        : null,
    [selectedShot?.episode, selectedShot?.shot_id, shotExecutionSummaries],
  )

  const effectiveReferencePayload = useMemo(
    () => resolveEffectiveReferenceAssetIds(selectedShot),
    [selectedShot],
  )

  const effectiveReferenceAssetIds = effectiveReferencePayload.assetIds
  const shotPrimaryActionPlan = useMemo(
    () =>
      selectedShot
        ? buildCanvasShotPrimaryActionPlan({
            promptRecoveryTaskId,
            frameRecoveryTaskId,
            videoRecoveryTaskId,
            hasCompiledPrompt: Boolean(selectedShot.visual_prompt_static?.trim()),
            hasAdoptedFrame: Boolean(adoptedImage),
            hasAdoptedVideo: Boolean(adoptedVideo),
          })
        : null,
    [
      adoptedImage,
      adoptedVideo,
      frameRecoveryTaskId,
      promptRecoveryTaskId,
      selectedShot,
      videoRecoveryTaskId,
    ],
  )
  const navigationClosureStatus = useMemo(
    () =>
      buildCanvasRecoveryClosureStatus({
        target: navigationTarget,
        targetNodeId,
        isProjectDataLoading,
        pendingPromptTaskId: promptRecoveryTaskId,
        pendingFrameTaskId: frameRecoveryTaskId,
        pendingVideoTaskId: videoRecoveryTaskId,
        latestExecutionTaskId: selectedShotLatestExecutionSummary?.taskId ?? null,
        hasCompiledPrompt: Boolean(selectedShot?.visual_prompt_static?.trim()),
        hasAdoptedFrame: Boolean(adoptedImage),
        hasAdoptedVideo: Boolean(adoptedVideo),
        hasReferenceAssets: effectiveReferenceAssetIds.length > 0,
      }),
    [
      adoptedImage,
      adoptedVideo,
      effectiveReferenceAssetIds.length,
      frameRecoveryTaskId,
      isProjectDataLoading,
      navigationTarget,
      promptRecoveryTaskId,
      selectedShot?.visual_prompt_static,
      selectedShotLatestExecutionSummary?.taskId,
      targetNodeId,
      videoRecoveryTaskId,
    ],
  )
  const navigationActionPlan = useMemo(
    () =>
      buildCanvasRecoveryActionPlan({
        target: navigationTarget,
        targetStatusTone: navigationTargetStatus?.tone ?? null,
        closureStatusTone: navigationClosureStatus?.tone ?? null,
        canRefocus: canRefocusNavigationTarget,
      }),
    [canRefocusNavigationTarget, navigationClosureStatus?.tone, navigationTarget, navigationTargetStatus?.tone],
  )
  const refocusActionLabel = useMemo(
    () =>
      buildCanvasRecoveryActionLabel({
        action: 'refocus',
        targetStatusTone: navigationTargetStatus?.tone ?? null,
        closureStatusTone: navigationClosureStatus?.tone ?? null,
      }) ?? '定位恢复节点',
    [navigationClosureStatus?.tone, navigationTargetStatus?.tone],
  )
  const tasksActionLabel = useMemo(
    () =>
      buildCanvasRecoveryActionLabel({
        action: 'tasks',
        targetStatusTone: navigationTargetStatus?.tone ?? null,
        closureStatusTone: navigationClosureStatus?.tone ?? null,
      }) ?? '回任务中心',
    [navigationClosureStatus?.tone, navigationTargetStatus?.tone],
  )
  const storyboardActionLabel = useMemo(
    () =>
      buildCanvasRecoveryActionLabel({
        action: 'storyboard',
        targetStatusTone: navigationTargetStatus?.tone ?? null,
        closureStatusTone: navigationClosureStatus?.tone ?? null,
      }) ?? '前往镜头工作台',
    [navigationClosureStatus?.tone, navigationTargetStatus?.tone],
  )
  const assetsActionLabel = useMemo(
    () =>
      buildCanvasRecoveryActionLabel({
        action: 'assets',
        targetStatusTone: navigationTargetStatus?.tone ?? null,
        closureStatusTone: navigationClosureStatus?.tone ?? null,
      }) ?? '前往资产中心',
    [navigationClosureStatus?.tone, navigationTargetStatus?.tone],
  )
  const selectedRecoveryShotMatches = useMemo(
    () =>
      Boolean(
        selectedShot &&
        navigationTarget?.shotId &&
        Number(navigationTarget?.episode ?? 0) === Number(selectedShot.episode ?? 0) &&
        String(navigationTarget.shotId) === String(selectedShot.shot_id),
      ),
    [navigationTarget?.episode, navigationTarget?.shotId, selectedShot],
  )
  const navigationContinueAction = useMemo(
    () =>
      buildCanvasRecoveryContinueActionPlan({
        recoveryKind: navigationTarget?.recoveryKind ?? null,
        closureStatusTone: navigationClosureStatus?.tone ?? null,
        hasSelectedShot: selectedRecoveryShotMatches,
        hasCompiledPrompt: Boolean(selectedShot?.visual_prompt_static?.trim()),
        hasAdoptedFrame: Boolean(adoptedImage),
        hasAdoptedVideo: Boolean(adoptedVideo),
      }),
    [
      adoptedImage,
      adoptedVideo,
      navigationClosureStatus?.tone,
      navigationTarget?.recoveryKind,
      selectedRecoveryShotMatches,
      selectedShot?.visual_prompt_static,
    ],
  )
  const navigationContinueChainMeta = useMemo(
    () =>
      navigationContinueAction
        ? buildNavigationContinueChainMeta({
            action: navigationContinueAction.action,
            recoveryKind: navigationTarget?.recoveryKind ?? null,
          })
        : null,
    [navigationContinueAction, navigationTarget?.recoveryKind],
  )

  const navigateToTasks = () => {
    if (!navigationTarget?.taskId) return
    onNavigateTaskSection('tasks', {
      episode: navigationTarget.episode ?? null,
      shotId: navigationTarget.shotId ?? null,
      assetId: navigationTarget.assetId ?? null,
      assetLabel: navigationTarget.assetLabel ?? null,
      taskId: navigationTarget.taskId ?? null,
      recoveryKind: navigationTarget.recoveryKind ?? null,
      recoveryIntent: navigationTarget.recoveryIntent ?? null,
      navigationSource: 'canvas',
    })
  }

  const navigateToStoryboard = () => {
    if (!navigationTarget?.shotId) return
    onNavigateTaskSection('storyboard', {
      episode: navigationTarget.episode ?? null,
      shotId: navigationTarget.shotId ?? null,
      assetId: navigationTarget.assetId ?? null,
      assetLabel: navigationTarget.assetLabel ?? null,
      taskId: navigationTarget.taskId ?? null,
      recoveryKind: navigationTarget.recoveryKind ?? null,
      recoveryIntent: navigationTarget.recoveryIntent ?? null,
      navigationSource: 'canvas',
    })
  }

  const navigateToAssets = () => {
    if (!navigationTarget?.assetId) return
    onNavigateTaskSection('assets', {
      episode: navigationTarget.episode ?? null,
      assetId: navigationTarget.assetId ?? null,
      assetLabel: navigationTarget.assetLabel ?? null,
      navigationSource: 'canvas',
      handoffLabel: '前往资产中心确认当前资产承接状态',
      handoffDetail: '当前恢复上下文已经带着资产进入资产中心，建议先确认参考图、版本与镜头引用，再继续后续生成。',
    })
  }

  const runNavigationContinueAction = () => {
    if (!navigationContinueAction) return
    if (navigationContinueAction.action === 'generate_frame') {
      void handleGenerateFrame({
        generationChain: navigationContinueChainMeta?.generationChain ?? 'canvas_generate_frame',
      })
      return
    }
    if (navigationContinueAction.action === 'generate_video') {
      void handleGenerateVideo({
        generationChain: navigationContinueChainMeta?.generationChain ?? 'canvas_generate_video',
      })
      return
    }
    if (navigationContinueAction.action === 'recompile_then_frame') {
      void handleRecompileThenGenerateFrame({
        compileReason: navigationContinueChainMeta?.compileReason ?? 'manual-recompile-before-frame',
        generationChain: navigationContinueChainMeta?.generationChain ?? 'recompile_then_frame',
      })
      return
    }
    if (navigationContinueAction.action === 'recompile_then_video') {
      void handleRecompileThenGenerateVideo({
        compileReason: navigationContinueChainMeta?.compileReason ?? 'manual-recompile-before-video',
        generationChain: navigationContinueChainMeta?.generationChain ?? 'recompile_then_video',
      })
    }
  }

  useEffect(() => {
    if (!selectedShot?.episode || !selectedShot?.shot_id) {
      setPromptRecoveryTaskId(null)
      setFrameRecoveryTaskId(null)
      setVideoRecoveryTaskId(null)
      return
    }
    const pendingTasks = readPendingStoryboardTasks(bookId)
    const matchedPromptTask =
      pendingTasks.find(
        (item) =>
          item.kind === 'prompt' &&
          item.episode === selectedShot.episode &&
          String(item.shotId) === String(selectedShot.shot_id),
      ) ?? null
    const matchedTask =
      pendingTasks.find(
        (item) =>
          item.kind === 'frame' &&
          item.episode === selectedShot.episode &&
          String(item.shotId) === String(selectedShot.shot_id),
      ) ?? null
    const matchedVideoTask =
      pendingTasks.find(
        (item) =>
          item.kind === 'video' &&
          item.episode === selectedShot.episode &&
          String(item.shotId) === String(selectedShot.shot_id),
      ) ?? null
    setPromptRecoveryTaskId(matchedPromptTask?.taskId ?? null)
    setFrameRecoveryTaskId(matchedTask?.taskId ?? null)
    setVideoRecoveryTaskId(matchedVideoTask?.taskId ?? null)
  }, [bookId, canvasRuntimeVersion, selectedShot?.episode, selectedShot?.shot_id, selectedShot?.assets?.images?.length, selectedShot?.assets?.videos?.length])

  useEffect(() => {
    if (!flowInstance || !selectedNode) return
    flowInstance.setCenter(selectedNode.x + 130, selectedNode.y + 70, {
      zoom: Math.max(flowInstance.getZoom(), 0.62),
      duration: 450,
    })
  }, [flowInstance, selectedNode])

  const nodes = useMemo(
    () => visibleGraph.nodes.map((node) => toFlowNode(node, selectedNodeId)),
    [selectedNodeId, visibleGraph.nodes],
  )

  const edges = useMemo(
    () => visibleGraph.edges.map((edge) => toFlowEdge(edge, selectedNodeId)),
    [selectedNodeId, visibleGraph.edges],
  )

  const hasAdoptedFrame = Boolean(adoptedImage)

  const isShotGenerationBusy = generationState === 'submitting'
  const isCompileBusy = compileState === 'submitting'
  const canGenerateFrame = Boolean(selectedShot?.episode && selectedShot?.shot_id) && !isShotGenerationBusy
  const canGenerateVideo =
    Boolean(selectedShot?.episode && selectedShot?.shot_id) && hasAdoptedFrame && !isShotGenerationBusy
  const resultCount = visibleGraph.nodes.length
  const hasActiveKindFilter = activeKinds.length !== FILTERABLE_KINDS.length
  const hasActiveStatusFilter = statusFilter !== 'all'
  const hasCollapsedKinds = collapsedKinds.length > 0

  const toggleKind = (kind: CanvasNodeKind) => {
    setActiveKinds((current) => {
      if (current.length === FILTERABLE_KINDS.length) return [kind]
      if (current.includes(kind)) {
        if (current.length === 1) return FILTERABLE_KINDS
        return current.filter((item) => item !== kind)
      }
      return [...current, kind]
    })
  }

  const toggleCollapsedKind = (kind: CollapsibleCanvasKind) => {
    setCollapsedKinds((current) =>
      current.includes(kind) ? current.filter((item) => item !== kind) : [...current, kind],
    )
  }

  const handleGenerateFrame = async (chainMeta?: {
    generationChain?: string
    triggeredByPromptRecompile?: boolean
    promptRecompileReason?: string
    promptRecompileTaskId?: string
    promptRecompileVersion?: number
  }) => {
    if (!selectedShot?.episode || !selectedShot?.shot_id) return
    const labels = getStoryboardGenerationLabels('frame')
    const confirmed = typeof window === 'undefined' || window.confirm(
      '确认提交分镜图生成？该操作可能产生平台费用，并会把返回图片写回当前镜头。',
    )
    if (!confirmed) {
      setGenerationState('idle')
      setGenerationMessage('已取消分镜图生成。')
      return
    }
    setGenerationState('submitting')
    setGenerationMessage('正在从创作画布提交首帧生成任务，请不要重复点击。')
    setFrameRecoveryTaskId(null)

    try {
      const response = await fetch(
        `/api/books/${bookId}/storyboard/${selectedShot.episode}/${selectedShot.shot_id}/generate-frame`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            confirmed: true,
            allowExternalCall: true,
            compileIfMissing: true,
            generationChain: chainMeta?.generationChain ?? 'canvas_generate_frame',
            triggeredByPromptRecompile: chainMeta?.triggeredByPromptRecompile,
            promptRecompileReason: chainMeta?.promptRecompileReason,
            promptRecompileTaskId: chainMeta?.promptRecompileTaskId,
            promptRecompileVersion: chainMeta?.promptRecompileVersion,
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
      if (!taskId) throw new Error('未能获取首帧任务 ID。')

      upsertPendingStoryboardTask(bookId, {
        taskId,
        episode: selectedShot.episode,
        shotId: String(selectedShot.shot_id),
        kind: 'frame',
        updatedAt: new Date().toISOString(),
      })
      setFrameRecoveryTaskId(taskId)
      refreshCanvasRuntimeState()

      const settled = await waitForCreativeTask(taskId, fetchCreativeTaskStatus, {
        reconcileTask: reconcileCreativeTask,
        softTimeoutMs: 45000,
      })

      if (settled.status === 'done') {
        removePendingStoryboardTask(bookId, taskId)
        setFrameRecoveryTaskId(null)
        refreshCanvasRuntimeState()
        setGenerationState('success')
        setGenerationMessage(labels.success)
        persistShotExecutionSummary('frame', getCanvasExecutionSummaryLabel('frame', chainMeta?.generationChain), {
          generationChain: chainMeta?.generationChain ?? 'canvas_generate_frame',
          taskId,
        })
        onRefreshAll()
        return
      }

      if (settled.status === 'soft_timeout') {
        setGenerationState('error')
        setGenerationMessage(`${labels.pending} 任务 ID：${taskId}`)
        return
      }

      const settledError = 'error' in settled ? String(settled.error || '') : ''
      setGenerationState('error')
      setGenerationMessage(formatGenerationErrorMessage(settledError, `${labels.action}失败，任务 ID：${taskId}`))
    } catch (error) {
      setGenerationState('error')
      setGenerationMessage(
        formatGenerationErrorMessage(error instanceof Error ? error.message : '', '首帧生成失败。'),
      )
    }
  }

  const handleGenerateVideo = async (chainMeta?: {
    generationChain?: string
    triggeredByPromptRecompile?: boolean
    promptRecompileReason?: string
    promptRecompileTaskId?: string
    promptRecompileVersion?: number
  }) => {
    if (!selectedShot?.episode || !selectedShot?.shot_id || !adoptedImage?.id) return
    const labels = getStoryboardGenerationLabels('video')
    const confirmed = typeof window === 'undefined' || window.confirm(
      '确认提交视频生成？该操作可能产生平台费用，并会把返回视频写回当前镜头。',
    )
    if (!confirmed) {
      setGenerationState('idle')
      setGenerationMessage('已取消视频生成。')
      return
    }
    setGenerationState('submitting')
    setGenerationMessage('正在从创作画布提交视频生成任务，请不要重复点击。')
    setVideoRecoveryTaskId(null)

    try {
      const response = await fetch(
        `/api/books/${bookId}/storyboard/${selectedShot.episode}/${selectedShot.shot_id}/generate-video`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            confirmed: true,
            allowExternalCall: true,
            compileIfMissing: true,
            firstFrameAssetId: String(adoptedImage.id).trim(),
            referenceAssetIds: effectiveReferenceAssetIds,
            generationChain: chainMeta?.generationChain ?? 'canvas_generate_video',
            triggeredByPromptRecompile: chainMeta?.triggeredByPromptRecompile,
            promptRecompileReason: chainMeta?.promptRecompileReason,
            promptRecompileTaskId: chainMeta?.promptRecompileTaskId,
            promptRecompileVersion: chainMeta?.promptRecompileVersion,
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
      if (!taskId) throw new Error('未能获取视频任务 ID。')

      upsertPendingStoryboardTask(bookId, {
        taskId,
        episode: selectedShot.episode,
        shotId: String(selectedShot.shot_id),
        kind: 'video',
        updatedAt: new Date().toISOString(),
      })
      setVideoRecoveryTaskId(taskId)
      refreshCanvasRuntimeState()

      const settled = await waitForCreativeTask(taskId, fetchCreativeTaskStatus, {
        reconcileTask: reconcileCreativeTask,
        softTimeoutMs: 45000,
      })

      if (settled.status === 'done') {
        removePendingStoryboardTask(bookId, taskId)
        setVideoRecoveryTaskId(null)
        refreshCanvasRuntimeState()
        setGenerationState('success')
        setGenerationMessage(labels.success)
        persistShotExecutionSummary('video', getCanvasExecutionSummaryLabel('video', chainMeta?.generationChain), {
          generationChain: chainMeta?.generationChain ?? 'canvas_generate_video',
          taskId,
        })
        onRefreshAll()
        return
      }

      if (settled.status === 'soft_timeout') {
        setGenerationState('error')
        setGenerationMessage(`${labels.pending} 任务 ID：${taskId}`)
        return
      }

      const settledError = 'error' in settled ? String(settled.error || '') : ''
      setGenerationState('error')
      setGenerationMessage(formatGenerationErrorMessage(settledError, `${labels.action}失败，任务 ID：${taskId}`))
    } catch (error) {
      setGenerationState('error')
      setGenerationMessage(
        formatGenerationErrorMessage(error instanceof Error ? error.message : '', '视频生成失败。'),
      )
    }
  }

  const handleCompilePrompts = async (compileReason = 'canvas-manual-recompile'): Promise<CanvasCompileResult> => {
    if (!selectedShot?.episode || !selectedShot?.shot_id) return { status: 'invalid' }
    if (!window.confirm('确认从创作画布直接调用 LLM 重编译？建议优先使用正式工作台的受控 Prompt Compiler 草案。')) return { status: 'invalid' }
    setCompileState('submitting')
    setCompileMessage('正在从创作画布提交当前镜头提示词重编译任务，通常需要 30-60 秒。')
    setPromptRecoveryTaskId(null)

    try {
      const response = await fetch(
        `/api/books/${bookId}/storyboard/${selectedShot.episode}/${selectedShot.shot_id}/compile-prompts/async`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ compileReason, force: false, confirmed: true, allowExternalCall: true }),
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
      if (!taskId) throw new Error('未能获取提示词重编译任务 ID。')

      upsertPendingStoryboardTask(bookId, {
        taskId,
        episode: selectedShot.episode,
        shotId: String(selectedShot.shot_id),
        kind: 'prompt',
        updatedAt: new Date().toISOString(),
      })
      setPromptRecoveryTaskId(taskId)
      refreshCanvasRuntimeState()
      setCompileMessage(`已提交重编译任务，正在后台执行。任务 ID：${taskId}`)

      const settled = await waitForCreativeTask(
        taskId,
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
        removePendingStoryboardTask(bookId, taskId)
        setPromptRecoveryTaskId(null)
        refreshCanvasRuntimeState()
        setCompileState('success')
        setCompileMessage(
          `已重新编译到 v${String(settled?.version ?? settled?.prompt_version ?? '-')}${settled?.repair_attempted ? '，并已执行自动修复复编。' : '。'}`,
        )
        persistShotExecutionSummary('compile', `提示词重编译 v${String(settled?.version ?? settled?.prompt_version ?? '-')}`, {
          promptVersion:
            typeof settled?.version === 'number'
              ? settled.version
              : typeof settled?.prompt_version === 'number'
                ? settled.prompt_version
                : null,
          taskId,
        })
        onRefreshAll()
        return {
          status: 'done',
          taskId,
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
        setCompileState('success')
        setCompileMessage(`重编译任务仍在后台执行，可去任务中心继续回收。任务 ID：${taskId}`)
        return { status: 'pending', taskId, reason: compileReason }
      }

      const settledError = 'error' in settled ? String(settled.error || '') : ''
      throw new Error(settledError || `提示词重编译失败，任务 ID：${taskId}`)
    } catch (error) {
      setCompileState('error')
      const message = error instanceof Error ? error.message : '提示词重编译失败，请稍后重试。'
      setCompileMessage(message)
      return { status: 'error', message, reason: compileReason }
    }
  }

  const handleRecompileThenGenerateVideo = async (options?: {
    compileReason?: string
    generationChain?: string
  }) => {
    const compileResult = await handleCompilePrompts(options?.compileReason ?? 'manual-recompile-before-video')
    if (!compileResult || compileResult.status !== 'done') return
    await handleGenerateVideo({
      generationChain: options?.generationChain ?? 'recompile_then_video',
      triggeredByPromptRecompile: true,
      promptRecompileReason: compileResult.reason,
      promptRecompileTaskId: compileResult.taskId,
      promptRecompileVersion: typeof compileResult.version === 'number' ? compileResult.version : undefined,
    })
  }

  const handleRecompileThenGenerateFrame = async (options?: {
    compileReason?: string
    generationChain?: string
  }) => {
    const compileResult = await handleCompilePrompts(options?.compileReason ?? 'manual-recompile-before-frame')
    if (!compileResult || compileResult.status !== 'done') return
    await handleGenerateFrame({
      generationChain: options?.generationChain ?? 'recompile_then_frame',
      triggeredByPromptRecompile: true,
      promptRecompileReason: compileResult.reason,
      promptRecompileTaskId: compileResult.taskId,
      promptRecompileVersion: typeof compileResult.version === 'number' ? compileResult.version : undefined,
    })
  }

  const runShotPrimaryAction = () => {
    if (!selectedShot?.episode || !selectedShot?.shot_id || !shotPrimaryActionPlan) return

    if (shotPrimaryActionPlan.action === 'tasks_prompt') {
      onNavigateTaskSection('tasks', {
        episode: selectedShot.episode,
        shotId: String(selectedShot.shot_id),
        taskId: promptRecoveryTaskId ?? undefined,
        recoveryKind: promptRecoveryTaskId ? 'prompt' : undefined,
        navigationSource: 'canvas',
      })
      return
    }

    if (shotPrimaryActionPlan.action === 'tasks_frame') {
      onNavigateTaskSection('tasks', {
        episode: selectedShot.episode,
        shotId: String(selectedShot.shot_id),
        taskId: frameRecoveryTaskId ?? undefined,
        recoveryKind: frameRecoveryTaskId ? 'frame' : undefined,
        navigationSource: 'canvas',
      })
      return
    }

    if (shotPrimaryActionPlan.action === 'tasks_video') {
      onNavigateTaskSection('tasks', {
        episode: selectedShot.episode,
        shotId: String(selectedShot.shot_id),
        taskId: videoRecoveryTaskId ?? undefined,
        recoveryKind: videoRecoveryTaskId ? 'video' : undefined,
        navigationSource: 'canvas',
      })
      return
    }

    if (shotPrimaryActionPlan.action === 'compile_prompts') {
      void handleCompilePrompts()
      return
    }

    if (shotPrimaryActionPlan.action === 'generate_frame') {
      void handleGenerateFrame()
      return
    }

    if (shotPrimaryActionPlan.action === 'generate_video') {
      void handleGenerateVideo()
      return
    }

    onNavigateTaskSection('storyboard', {
      episode: selectedShot.episode,
      shotId: String(selectedShot.shot_id),
      navigationSource: 'canvas',
      handoffLabel: shotPrimaryActionPlan.label,
      handoffDetail: shotPrimaryActionPlan.detail,
    })
  }

  const runSelectedNodePrimaryAction = () => {
    if (!selectedNode?.route) return
    onNavigateTaskSection(selectedNode.route.section, {
      ...selectedNode.route.options,
      navigationSource: 'canvas',
      handoffLabel: selectedNodePrimaryActionPlan?.label ?? null,
      handoffDetail: selectedNodePrimaryActionPlan?.detail ?? null,
    })
  }

  if (graph.nodes.length === 0) {
    return (
      <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6">
        <div className="text-lg font-semibold text-white">创作画布</div>
        <div className="mt-2 text-sm leading-6 text-slate-400">
          {showSyncingState
            ? '正在同步真实项目数据。画布会在数据到齐后自动恢复节点与上下文，不会丢失当前恢复入口。'
            : '这里会把剧本、分镜、资产、图片、视频、QA 与交付串成一张真实项目画布。当前项目还没有可映射的数据，先完成内容准备和下游产物生成后再回来看。'}
        </div>
        {showSyncingState ? (
          <div className="mt-4 rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3">
            <div className="text-sm font-medium text-white">正在同步项目数据</div>
            <div className="mt-2 text-xs leading-6 text-amber-100/85">
              {navigationSummary
                ? `${navigationSummary.title}。${navigationSummary.detail}`
                : '当前正在从正式产品工作区同步分镜、资产与运行态，请稍候片刻。'}
            </div>
          </div>
        ) : null}
      </section>
    )
  }

  return (
    <section className="space-y-4">
      <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <div className="text-lg font-semibold text-white">创作画布</div>
            <div className="mt-2 text-sm leading-6 text-slate-400">
              这一版先把真实剧本、分镜、资产、图片、视频、QA 与交付节点串起来。现在已经支持在画布里对单镜头直接发起提示词重编译、
              首帧生成和视频生成，再回任务中心继续回收长任务结果。
            </div>
          </div>
          <details className="rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2">
            <summary className="cursor-pointer text-sm font-medium text-slate-300">高级：筛选、整理与重置画布</summary>
            <div className="mt-3 flex flex-wrap items-end gap-3">
            <label className="text-xs text-slate-500">
              搜索节点
              <input
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="角色、镜头、场景、视频"
                className="mt-1 block min-w-[220px] rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition placeholder:text-slate-600 focus:border-cyan-500"
              />
            </label>
            <label className="text-xs text-slate-500">
              当前分集
              <select
                value={selectedEpisode}
                onChange={(event) => {
                  const value = event.target.value
                  setSelectedEpisode(value === 'all' ? 'all' : Number(value))
                }}
                className="mt-1 block min-w-[140px] rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-cyan-500"
              >
                <option value="all">全部分集</option>
                {episodeOptions.map((episode) => (
                  <option key={episode} value={episode}>
                    第 {episode} 集
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              disabled={!searchQuery.trim()}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-300 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:border-slate-800 disabled:text-slate-600"
            >
              清空搜索
            </button>
            <button
              type="button"
              onClick={() => setActiveKinds(FILTERABLE_KINDS)}
              disabled={activeKinds.length === FILTERABLE_KINDS.length}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-300 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:border-slate-800 disabled:text-slate-600"
            >
              全部类型
            </button>
            <button
              type="button"
              onClick={() => setStatusFilter('all')}
              disabled={statusFilter === 'all'}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-300 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:border-slate-800 disabled:text-slate-600"
            >
              全部状态
            </button>
            <button
              type="button"
              onClick={() => setCollapsedKinds([])}
              disabled={collapsedKinds.length === 0}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-300 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:border-slate-800 disabled:text-slate-600"
            >
              展开全部分组
            </button>
            <button
              type="button"
              onClick={() => flowInstance?.fitView({ padding: 0.2, duration: 450 })}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-300 transition hover:border-slate-500 hover:text-white"
            >
              重置视图
            </button>
            </div>
          </details>
        </div>

        <details className="mt-4 rounded-xl border border-slate-800 bg-slate-950/30 p-3">
          <summary className="cursor-pointer text-sm font-medium text-slate-300">高级：按节点类型、状态和资产分组查看</summary>
          <div className="mt-3 text-xs leading-6 text-slate-500">
            日常创作通常不需要调整这些筛选；只有排查某类资产、缺图或阻塞关系时再展开使用。
          </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {FILTERABLE_KINDS.map((kind) => {
            const active = activeKinds.includes(kind)
            return (
              <button
                key={kind}
                type="button"
                onClick={() => toggleKind(kind)}
                className={`rounded-lg border px-3 py-1.5 text-xs transition ${
                  active
                    ? `${kindAccent(kind)}`
                    : 'border-slate-700 bg-slate-950 text-slate-500 hover:border-slate-600 hover:text-slate-300'
                }`}
              >
                {kindLabel(kind)}
              </button>
            )
          })}
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {STATUS_FILTERS.map((item) => {
            const active = statusFilter === item.key
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => setStatusFilter(item.key)}
                className={`rounded-lg border px-3 py-1.5 text-xs transition ${
                  active
                    ? 'border-cyan-500/40 bg-cyan-500/10 text-cyan-200'
                    : 'border-slate-700 bg-slate-950 text-slate-500 hover:border-slate-600 hover:text-slate-300'
                }`}
              >
                {item.label} {statusCounts[item.key]}
              </button>
            )
          })}
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {COLLAPSIBLE_KINDS.map((kind) => {
            const active = collapsedKinds.includes(kind)
            return (
              <button
                key={kind}
                type="button"
                onClick={() => toggleCollapsedKind(kind)}
                className={`rounded-lg border px-3 py-1.5 text-xs transition ${
                  active
                    ? 'border-violet-500/40 bg-violet-500/10 text-violet-200'
                    : 'border-slate-700 bg-slate-950 text-slate-500 hover:border-slate-600 hover:text-slate-300'
                }`}
              >
                {active ? `已折叠 ${collapseToggleLabel(kind)}` : `折叠${collapseToggleLabel(kind)}`}
              </button>
            )
          })}
        </div>
        </details>

        {navigationSummary ? (
          <div className="mt-4 rounded-2xl border border-sky-500/30 bg-sky-500/10 px-5 py-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm font-medium text-sky-100">恢复上下文</div>
                <div className="mt-2 text-sm text-white">{navigationSummary.title}</div>
                <div className="mt-2 text-xs leading-6 text-sky-100/85">{navigationSummary.detail}</div>
                {navigationTargetStatus ? (
                  <div className="mt-3 flex flex-wrap items-start gap-2">
                    <span
                      className={`rounded-md border px-2 py-0.5 text-[10px] font-medium ${
                        navigationTargetStatus.tone === 'resolved'
                          ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100'
                          : navigationTargetStatus.tone === 'syncing'
                            ? 'border-amber-500/40 bg-amber-500/10 text-amber-100'
                            : 'border-rose-500/40 bg-rose-500/10 text-rose-100'
                      }`}
                    >
                      {navigationTargetStatus.label}
                    </span>
                    <div className="max-w-2xl text-xs leading-6 text-sky-100/80">{navigationTargetStatus.detail}</div>
                  </div>
                ) : null}
                {navigationClosureStatus ? (
                  <div className="mt-3 flex flex-wrap items-start gap-2">
                    <span
                      className={`rounded-md border px-2 py-0.5 text-[10px] font-medium ${
                        navigationClosureStatus.tone === 'closed'
                          ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-100'
                          : navigationClosureStatus.tone === 'pending' || navigationClosureStatus.tone === 'syncing'
                            ? 'border-amber-500/40 bg-amber-500/10 text-amber-100'
                            : 'border-rose-500/40 bg-rose-500/10 text-rose-100'
                      }`}
                    >
                      {navigationClosureStatus.label}
                    </span>
                    <div className="max-w-2xl text-xs leading-6 text-sky-100/80">{navigationClosureStatus.detail}</div>
                  </div>
                ) : null}
                {navigationActionPlan ? (
                  <div className="mt-3 text-xs leading-6 text-sky-100/75">{navigationActionPlan.helperText}</div>
                ) : null}
                {navigationContinueAction ? (
                  <div className="mt-3 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-3 py-3">
                    <div className="text-xs font-medium text-emerald-100">继续创作建议</div>
                    <div className="mt-1 text-xs leading-6 text-emerald-100/80">{navigationContinueAction.detail}</div>
                  </div>
                ) : null}
              </div>
              <div className="flex flex-wrap gap-2">
                {navigationContinueAction ? (
                  <button
                    type="button"
                    onClick={runNavigationContinueAction}
                    disabled={
                      navigationContinueAction.action === 'generate_frame'
                        ? !canGenerateFrame
                        : navigationContinueAction.action === 'generate_video'
                          ? !canGenerateVideo
                          : navigationContinueAction.action === 'recompile_then_frame'
                            ? !canGenerateFrame || isCompileBusy
                            : !canGenerateVideo || isCompileBusy
                    }
                    className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                      (
                        navigationContinueAction.action === 'generate_frame'
                          ? canGenerateFrame
                          : navigationContinueAction.action === 'generate_video'
                            ? canGenerateVideo
                            : navigationContinueAction.action === 'recompile_then_frame'
                              ? canGenerateFrame && !isCompileBusy
                              : canGenerateVideo && !isCompileBusy
                      )
                        ? 'border border-emerald-400 bg-emerald-400/15 text-white hover:border-emerald-300 hover:bg-emerald-400/20'
                        : 'cursor-not-allowed border border-slate-800 bg-slate-950 text-slate-600'
                    }`}
                  >
                    {navigationContinueAction.label}
                  </button>
                ) : null}
                {navigationActionPlan?.allowRefocus && canRefocusNavigationTarget ? (
                  <button
                    type="button"
                    onClick={refocusNavigationTarget}
                    className={canvasRecoveryActionButtonClass(navigationActionPlan?.primaryAction === 'refocus')}
                  >
                    {refocusActionLabel}
                  </button>
                ) : null}
                {navigationTarget?.taskId ? (
                  <button
                    type="button"
                    onClick={navigateToTasks}
                    className={canvasRecoveryActionButtonClass(navigationActionPlan?.primaryAction === 'tasks')}
                  >
                    {tasksActionLabel}
                  </button>
                ) : null}
                {navigationTarget?.shotId ? (
                  <button
                    type="button"
                    onClick={navigateToStoryboard}
                    className={canvasRecoveryActionButtonClass(navigationActionPlan?.primaryAction === 'storyboard')}
                  >
                    {storyboardActionLabel}
                  </button>
                ) : navigationTarget?.assetId ? (
                  <button
                    type="button"
                    onClick={navigateToAssets}
                    className={canvasRecoveryActionButtonClass(navigationActionPlan?.primaryAction === 'assets')}
                  >
                    {assetsActionLabel}
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}

        <div className="mt-5 grid min-w-[320px] grid-cols-3 gap-3 text-sm lg:grid-cols-4 xl:max-w-5xl">
          <div className="rounded-xl border border-slate-800 bg-slate-950 px-4 py-3">
            <div className="text-xs text-slate-500">集数</div>
            <div className="mt-1 text-lg font-semibold text-white">{graph.summary.episodeCount}</div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950 px-4 py-3">
            <div className="text-xs text-slate-500">镜头</div>
            <div className="mt-1 text-lg font-semibold text-white">{graph.summary.shotCount}</div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950 px-4 py-3">
            <div className="text-xs text-slate-500">资产</div>
            <div className="mt-1 text-lg font-semibold text-white">{graph.summary.assetCount}</div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950 px-4 py-3">
            <div className="text-xs text-slate-500">图片</div>
            <div className="mt-1 text-lg font-semibold text-white">{graph.summary.imageCount}</div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950 px-4 py-3">
            <div className="text-xs text-slate-500">视频</div>
            <div className="mt-1 text-lg font-semibold text-white">{graph.summary.videoCount}</div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950 px-4 py-3">
            <div className="text-xs text-slate-500">QA 问题</div>
            <div className="mt-1 text-lg font-semibold text-white">{graph.summary.qaCount}</div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950 px-4 py-3">
            <div className="text-xs text-slate-500">当前结果</div>
            <div className="mt-1 text-lg font-semibold text-white">{resultCount}</div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950 px-4 py-3">
            <div className="text-xs text-slate-500">当前状态筛选</div>
            <div className="mt-1 text-sm font-semibold text-white">{statusFilterLabel(statusFilter)}</div>
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-950">
          <div className="h-[820px] w-full bg-slate-950">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              fitView
              fitViewOptions={{ padding: 0.2 }}
              minZoom={0.3}
              maxZoom={1.2}
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable
              onInit={setFlowInstance}
              onNodeClick={(_event, node) => setSelectedNodeId(node.id)}
            >
              <MiniMap pannable zoomable nodeColor="#334155" style={{ background: '#020617' }} />
              <Controls showInteractive={false} />
              <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} color="#1e293b" />
            </ReactFlow>
          </div>
        </div>

        <aside className="space-y-4">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
            <div className="text-sm font-semibold text-white">筛选结果</div>
            <div className="mt-2 text-sm leading-6 text-slate-400">
              {selectedEpisode === 'all' ? '当前查看全部分集。' : `当前查看第 ${selectedEpisode} 集。`}
              {searchQuery.trim() ? ` 搜索词：${searchQuery.trim()}。` : ''}
              {hasActiveKindFilter ? ' 已启用类型筛选。' : ' 当前显示全部节点类型。'}
              {hasActiveStatusFilter ? ` 状态筛选：${statusFilterLabel(statusFilter)}。` : ' 当前显示全部节点状态。'}
              {hasCollapsedKinds
                ? ` 已折叠：${collapsedKinds.map((item) => collapseToggleLabel(item)).join(' / ')}。`
                : ' 当前未折叠节点分组。'}
            </div>
            <div className="mt-3 max-h-[260px] space-y-2 overflow-y-auto pr-1">
              {visibleGraph.nodes.slice(0, 24).map((node) => {
                const active = selectedNodeId === node.id
                const badges = nodeStatusBadges(node)
                return (
                  <button
                    key={node.id}
                    type="button"
                    onClick={() => setSelectedNodeId(node.id)}
                    className={`w-full rounded-xl border px-3 py-2 text-left transition ${
                      active
                        ? 'border-cyan-500/50 bg-cyan-500/10'
                        : 'border-slate-800 bg-slate-950 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className={`rounded-md border px-2 py-0.5 text-[10px] font-medium ${kindAccent(node.kind)}`}>
                        {kindLabel(node.kind)}
                      </span>
                      {badges.length ? (
                        <div className="flex flex-wrap justify-end gap-1">
                          {badges.slice(0, 2).map((badge) => (
                            <span key={badge.key} className={`rounded-md border px-1.5 py-0.5 text-[10px] ${badge.className}`}>
                              {badge.label}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                    <div className="mt-2 text-sm font-medium text-white">{node.title}</div>
                    <div className="mt-1 line-clamp-2 text-xs text-slate-500">{node.subtitle}</div>
                  </button>
                )
              })}
              {visibleGraph.nodes.length === 0 ? (
                <div className="rounded-xl border border-slate-800 bg-slate-950 px-3 py-3 text-sm text-slate-500">
                  当前筛选条件下没有节点。
                </div>
              ) : null}
              {visibleGraph.nodes.length > 24 ? (
                <div className="text-xs text-slate-500">仅显示前 24 个结果，建议继续缩小搜索范围。</div>
              ) : null}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-white">节点详情</div>
                <div className="mt-1 text-xs text-slate-500">当前选中的创作节点</div>
              </div>
              {selectedNode ? (
                <span className={`rounded-md border px-2 py-0.5 text-[10px] font-medium ${kindAccent(selectedNode.kind)}`}>
                  {kindLabel(selectedNode.kind)}
                </span>
              ) : null}
            </div>

            {selectedNode ? (
              <>
                <div className="mt-4 text-base font-semibold text-white">{selectedNode.title}</div>
                <div className="mt-1 text-sm leading-6 text-slate-400">{selectedNode.subtitle}</div>
                {selectedNodePrimaryActionPlan ? (
                  <div className="mt-4 rounded-xl border border-sky-500/25 bg-sky-500/5 p-4">
                    <div className="text-xs font-medium text-sky-200">推荐下一步</div>
                    <div className="mt-2 text-sm font-medium text-white">{selectedNodePrimaryActionPlan.label}</div>
                    <div className="mt-1 text-xs leading-5 text-slate-300">{selectedNodePrimaryActionPlan.detail}</div>
                    <div className="mt-3">
                      <button
                        type="button"
                        onClick={runSelectedNodePrimaryAction}
                        disabled={!selectedNode.route}
                        className="rounded-lg border border-sky-400 bg-sky-400/15 px-3 py-2 text-sm font-medium text-white transition hover:border-sky-300 hover:bg-sky-400/20 disabled:cursor-not-allowed disabled:border-slate-800 disabled:bg-slate-950 disabled:text-slate-600"
                      >
                        {selectedNodePrimaryActionPlan.label}
                      </button>
                    </div>
                  </div>
                ) : null}
                {selectedNode.isGroup ? (
                  <div className="mt-2 text-xs leading-5 text-sky-300">
                    当前是折叠分组节点，适合先回资产中心统一处理，再回来展开具体节点。
                  </div>
                ) : null}
                {nodeStatusBadges(selectedNode).length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {nodeStatusBadges(selectedNode).map((badge) => (
                      <span key={badge.key} className={`rounded-md border px-2 py-1 text-xs ${badge.className}`}>
                        {badge.label}
                      </span>
                    ))}
                  </div>
                ) : null}
                {selectedNode.meta.length ? (
                  <div className="mt-4 space-y-2 text-sm text-slate-300">
                    {selectedNode.meta.map((item) => (
                      <div key={item} className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2">
                        {item}
                      </div>
                    ))}
                  </div>
                ) : null}
                {selectedNode.previewUrl ? (
                  <img
                    src={selectedNode.previewUrl}
                    alt={selectedNode.title}
                    className="mt-4 w-full rounded-xl border border-slate-800 object-cover"
                  />
                ) : null}

                {selectedNode.kind === 'shot' && selectedShot ? (
                  <div className="mt-4 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
                    <div className="text-sm font-medium text-white">单镜头执行</div>
                    <div className="mt-1 text-xs leading-5 text-slate-400">
                      这里接入的是最短闭环：从创作画布直接发起提示词重编译、首帧生成和视频生成，长任务结果仍可回任务中心继续回收。
                    </div>
                    {shotPrimaryActionPlan ? (
                      <div className="mt-3 rounded-xl border border-sky-500/25 bg-sky-500/5 p-3">
                        <div className="text-xs font-medium text-sky-200">推荐下一步</div>
                        <div className="mt-2 text-sm font-medium text-white">{shotPrimaryActionPlan.label}</div>
                        <div className="mt-1 text-xs leading-5 text-slate-300">{shotPrimaryActionPlan.detail}</div>
                        <div className="mt-3">
                          <button
                            type="button"
                            onClick={runShotPrimaryAction}
                            className="rounded-lg border border-sky-400 bg-sky-400/15 px-3 py-2 text-sm font-medium text-white transition hover:border-sky-300 hover:bg-sky-400/20"
                          >
                            {shotPrimaryActionPlan.label}
                          </button>
                        </div>
                      </div>
                    ) : null}
                    {selectedShotRuntime.latestExecutionSummary || selectedShotRuntime.pendingTasks.length > 0 ? (
                      <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950/60 p-3">
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
                          </div>
                        </div>
                        <div className="mt-3 grid gap-2 md:grid-cols-3">
                          <div className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2">
                            <div className="text-[11px] text-slate-500">最近执行</div>
                            <div className="mt-1 text-xs text-slate-200">
                              {selectedShotRuntimeCard.latestExecutionLabel}
                            </div>
                          </div>
                          <div className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2">
                            <div className="text-[11px] text-slate-500">待回收任务</div>
                            <div className="mt-1 text-xs text-slate-200">
                              {selectedShotRuntimeCard.pendingTaskLabel}
                            </div>
                          </div>
                          <div className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2">
                            <div className="text-[11px] text-slate-500">建议动作</div>
                            <div className="mt-1 text-xs text-slate-200">
                              {selectedShotRuntimeCard.suggestedActionLabel}
                            </div>
                          </div>
                        </div>
                        {selectedShotRuntimeCard.latestSourceLine ? (
                          <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-[11px] text-slate-300">
                            {selectedShotRuntimeCard.latestSourceLine}
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                    <div className="mt-3 grid gap-2 text-xs text-slate-300">
                      <div className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2">
                        提示词源：{selectedShot.visual_prompt_static?.trim() ? '已具备' : '缺失，提交时会尝试自动补齐'}
                      </div>
                      <div className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2">
                        当前静态提示词：{selectedShot.visual_prompt_static?.trim() ? '已编译' : '未编译'}
                      </div>
                      {promptRecoveryTaskId ? (
                        <div className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2">
                          待回收提示词任务：{promptRecoveryTaskId}
                        </div>
                      ) : null}
                      <div className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2">
                        已采纳首帧：{hasAdoptedFrame ? '是' : '否'}
                      </div>
                      {frameRecoveryTaskId ? (
                        <div className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2">
                          待回收首帧任务：{frameRecoveryTaskId}
                        </div>
                      ) : null}
                    </div>
                    <div className="mt-3 grid gap-2 text-xs text-slate-300">
                      <div className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2">
                        结构化参考图：
                        {effectiveReferenceAssetIds.length > 0
                          ? `${effectiveReferenceAssetIds.length} 张（${effectiveReferencePayload.source}）`
                          : '未记录'}
                      </div>
                      {videoRecoveryTaskId ? (
                        <div className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2">
                          待回收视频任务：{videoRecoveryTaskId}
                        </div>
                      ) : null}
                    </div>
                    {generationMessage ? (
                      <div
                        role="status"
                        aria-live="polite"
                        className={`mt-3 rounded-lg border px-3 py-2 text-xs leading-5 ${
                          generationState === 'error'
                            ? 'border-amber-500/30 bg-amber-500/10 text-amber-100'
                            : generationState === 'success'
                              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100'
                              : 'border-slate-700 bg-slate-950 text-slate-300'
                        }`}
                      >
                        {generationMessage}
                      </div>
                    ) : null}
                    {compileMessage ? (
                      <div
                        role="status"
                        aria-live="polite"
                        className={`mt-3 rounded-lg border px-3 py-2 text-xs leading-5 ${
                          compileState === 'error'
                            ? 'border-rose-500/30 bg-rose-500/10 text-rose-100'
                            : compileState === 'success'
                              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100'
                              : 'border-slate-700 bg-slate-950 text-slate-300'
                        }`}
                      >
                        {compileMessage}
                      </div>
                    ) : null}
                    <div className="mt-4 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          void handleCompilePrompts()
                        }}
                        disabled={!selectedShot?.episode || !selectedShot?.shot_id || isCompileBusy}
                        className={`rounded-lg px-3 py-2 text-sm transition ${
                          selectedShot?.episode && selectedShot?.shot_id && !isCompileBusy
                            ? 'bg-sky-600 text-white hover:bg-sky-500'
                            : 'cursor-not-allowed border border-slate-800 bg-slate-950 text-slate-600'
                        }`}
                      >
                        {isCompileBusy ? '重编译中...' : '重编译提示词'}
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          onNavigateTaskSection('tasks', {
                            episode: selectedShot.episode,
                            shotId: String(selectedShot.shot_id),
                            taskId: promptRecoveryTaskId ?? undefined,
                            recoveryKind: promptRecoveryTaskId ? 'prompt' : undefined,
                          })
                        }
                        disabled={!promptRecoveryTaskId}
                        className={`rounded-lg border px-3 py-2 text-sm transition ${
                          promptRecoveryTaskId
                            ? 'border-slate-700 bg-slate-950 text-slate-300 hover:border-sky-500 hover:text-white'
                            : 'cursor-not-allowed border-slate-800 bg-slate-950 text-slate-600'
                        }`}
                      >
                        去任务中心继续回收提示词
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          void handleGenerateFrame()
                        }}
                        disabled={!canGenerateFrame}
                        className={`rounded-lg px-3 py-2 text-sm transition ${
                          canGenerateFrame
                            ? 'bg-emerald-600 text-white hover:bg-emerald-500'
                            : 'cursor-not-allowed border border-slate-800 bg-slate-950 text-slate-600'
                        }`}
                      >
                        {isShotGenerationBusy ? '提交中...' : '生成首帧'}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          void handleRecompileThenGenerateFrame()
                        }}
                        disabled={!canGenerateFrame || isCompileBusy}
                        className={`rounded-lg px-3 py-2 text-sm transition ${
                          canGenerateFrame && !isCompileBusy
                            ? 'bg-teal-600 text-white hover:bg-teal-500'
                            : 'cursor-not-allowed border border-slate-800 bg-slate-950 text-slate-600'
                        }`}
                      >
                        {isCompileBusy ? '重编译中...' : '重编后生成首帧'}
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          onNavigateTaskSection('tasks', {
                            episode: selectedShot.episode,
                            shotId: String(selectedShot.shot_id),
                            taskId: frameRecoveryTaskId ?? undefined,
                            recoveryKind: frameRecoveryTaskId ? 'frame' : undefined,
                          })
                        }
                        disabled={!frameRecoveryTaskId}
                        className={`rounded-lg border px-3 py-2 text-sm transition ${
                          frameRecoveryTaskId
                            ? 'border-slate-700 bg-slate-950 text-slate-300 hover:border-sky-500 hover:text-white'
                            : 'cursor-not-allowed border-slate-800 bg-slate-950 text-slate-600'
                        }`}
                      >
                        去任务中心继续回收首帧
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          void handleGenerateVideo()
                        }}
                        disabled={!canGenerateVideo}
                        className={`rounded-lg px-3 py-2 text-sm transition ${
                          canGenerateVideo
                            ? 'bg-fuchsia-600 text-white hover:bg-fuchsia-500'
                            : 'cursor-not-allowed border border-slate-800 bg-slate-950 text-slate-600'
                        }`}
                      >
                        {isShotGenerationBusy ? '提交中...' : '生成视频'}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          void handleRecompileThenGenerateVideo()
                        }}
                        disabled={!canGenerateVideo || isCompileBusy}
                        className={`rounded-lg px-3 py-2 text-sm transition ${
                          canGenerateVideo && !isCompileBusy
                            ? 'bg-violet-600 text-white hover:bg-violet-500'
                            : 'cursor-not-allowed border border-slate-800 bg-slate-950 text-slate-600'
                        }`}
                      >
                        {isCompileBusy ? '重编译中...' : '重编后继续生成视频'}
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          onNavigateTaskSection('tasks', {
                            episode: selectedShot.episode,
                            shotId: String(selectedShot.shot_id),
                            taskId: videoRecoveryTaskId ?? undefined,
                            recoveryKind: videoRecoveryTaskId ? 'video' : undefined,
                          })
                        }
                        disabled={!videoRecoveryTaskId}
                        className={`rounded-lg border px-3 py-2 text-sm transition ${
                          videoRecoveryTaskId
                            ? 'border-slate-700 bg-slate-950 text-slate-300 hover:border-sky-500 hover:text-white'
                            : 'cursor-not-allowed border-slate-800 bg-slate-950 text-slate-600'
                        }`}
                      >
                        去任务中心继续回收视频
                      </button>
                    </div>
                  </div>
                ) : null}

                <div className="mt-4 flex gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      if (!selectedNode.route) return
                      onNavigateTaskSection(selectedNode.route.section, {
                        ...selectedNode.route.options,
                        navigationSource: 'canvas',
                        handoffLabel: selectedNodePrimaryActionPlan?.label ?? null,
                        handoffDetail: selectedNodePrimaryActionPlan?.detail ?? null,
                      })
                    }}
                    disabled={!selectedNode.route}
                    className="rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 text-sm text-cyan-200 transition hover:border-cyan-400 hover:text-cyan-100 disabled:cursor-not-allowed disabled:border-slate-800 disabled:bg-slate-950 disabled:text-slate-600"
                  >
                    打开对应模块
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      flowInstance?.fitView({
                        nodes: [{ id: selectedNode.id }],
                        padding: 1.1,
                        duration: 450,
                        maxZoom: 0.9,
                      })
                    }
                    className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-300 transition hover:border-slate-500 hover:text-white"
                  >
                    聚焦节点
                  </button>
                </div>
              </>
            ) : (
              <div className="mt-4 text-sm leading-6 text-slate-500">当前没有选中节点。</div>
            )}
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
            <div className="text-sm font-semibold text-white">当前视角</div>
            <div className="mt-2 text-sm leading-6 text-slate-400">
              {selectedEpisode === 'all'
                ? '正在查看全部分集的创作关系，适合检查全局链路、卡点分布和产出覆盖。'
                : `正在查看第 ${selectedEpisode} 集的创作关系，适合回看单集剧本、分镜、资产和 QA 交接状态。`}
            </div>
          </div>
        </aside>
      </div>
    </section>
  )
}

