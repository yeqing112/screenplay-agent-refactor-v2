import type { ScriptOutput, StoryboardShotOutput } from '../prototyping/sceneComposerData'
import type { AssetSummary } from './productWorkspaceAssets'
import type { CanvasNavigationTarget } from './productWorkspaceSectionContracts'
import type { WorkspaceTaskRouteOptions, WorkspaceTaskRouteSection } from './productWorkspaceSectionContracts'
import type { PendingStoryboardTask, ShotExecutionSummary } from './productWorkspaceRecovery'

type CanvasNodeKind = 'script' | 'shot' | 'character' | 'location' | 'prop' | 'image' | 'video' | 'qa' | 'delivery'
type RecoveryKind = 'prompt' | 'frame' | 'video' | 'reference'
type RecoveryStatusTone = 'resolved' | 'syncing' | 'missing' | 'pending' | 'closed' | 'changed'

export interface CanvasBetaRoute {
  section: WorkspaceTaskRouteSection
  options?: WorkspaceTaskRouteOptions
}

export interface CanvasBetaNode {
  id: string
  kind: CanvasNodeKind
  title: string
  subtitle: string
  meta: string[]
  runtimeSummary?: {
    latestExecutionLabel?: string | null
    pendingKinds?: RecoveryKind[]
    hasAdoptedFrame?: boolean
    hasAdoptedVideo?: boolean
  }
  x: number
  y: number
  previewUrl?: string | null
  hasOutput?: boolean
  hasBlocker?: boolean
  missingReference?: boolean
  route?: CanvasBetaRoute
}

export interface CanvasBetaEdge {
  id: string
  source: string
  target: string
}

export interface CanvasBetaGraph {
  nodes: CanvasBetaNode[]
  edges: CanvasBetaEdge[]
  summary: {
    episodeCount: number
    shotCount: number
    assetCount: number
    imageCount: number
    videoCount: number
    qaCount: number
  }
}

export interface CanvasRecoveryActionPlan {
  primaryAction: 'tasks' | 'storyboard' | 'assets' | 'refocus' | null
  allowRefocus: boolean
  helperText: string
}

export interface CanvasRecoveryContinueActionPlan {
  action: 'generate_frame' | 'generate_video' | 'recompile_then_frame' | 'recompile_then_video'
  label: string
  detail: string
}

export function buildCanvasRecoveryActionLabel({
  action,
  targetStatusTone,
  closureStatusTone,
}: {
  action: CanvasRecoveryActionPlan['primaryAction']
  targetStatusTone?: RecoveryStatusTone | null
  closureStatusTone?: RecoveryStatusTone | null
}) {
  if (action === 'tasks') {
    if (closureStatusTone === 'pending' || closureStatusTone === 'syncing') {
      return '继续回收任务'
    }
    if (closureStatusTone === 'changed' || closureStatusTone === 'missing' || targetStatusTone === 'missing') {
      return '回任务中心确认'
    }
    return '回任务中心'
  }

  if (action === 'storyboard') {
    if (closureStatusTone === 'closed') {
      return '继续当前镜头创作'
    }
    if (closureStatusTone === 'missing' || targetStatusTone === 'missing') {
      return '检查当前集镜头'
    }
    return '前往镜头工作台'
  }

  if (action === 'assets') {
    if (closureStatusTone === 'closed') {
      return '继续当前资产创作'
    }
    return '前往资产中心'
  }

  if (action === 'refocus') {
    if (targetStatusTone === 'resolved') {
      return '回到恢复节点'
    }
    return '定位恢复节点'
  }

  return null
}

export function buildCanvasRecoveryContinueActionPlan({
  recoveryKind,
  closureStatusTone,
  hasSelectedShot,
  hasCompiledPrompt,
  hasAdoptedFrame,
  hasAdoptedVideo,
}: {
  recoveryKind?: RecoveryKind | null
  closureStatusTone?: RecoveryStatusTone | null
  hasSelectedShot: boolean
  hasCompiledPrompt?: boolean
  hasAdoptedFrame?: boolean
  hasAdoptedVideo?: boolean
}): CanvasRecoveryContinueActionPlan | null {
  if (closureStatusTone !== 'closed' || !hasSelectedShot || !recoveryKind || hasAdoptedVideo) {
    return null
  }

  if (recoveryKind === 'frame' && hasAdoptedFrame) {
    return {
      action: 'generate_video',
      label: '继续生成视频',
      detail: '这次恢复已经补齐首帧，可以直接在画布里继续提交视频生成。',
    }
  }

  if (recoveryKind === 'prompt' && hasCompiledPrompt) {
    if (hasAdoptedFrame) {
      return {
        action: 'generate_video',
        label: '继续生成视频',
        detail: '提示词已经恢复到当前链路，可直接沿用当前首帧继续生成视频。',
      }
    }
    return {
      action: 'generate_frame',
      label: '继续生成首帧',
      detail: '提示词已经恢复到当前链路，可以直接在画布里继续提交首帧生成。',
    }
  }

  if (recoveryKind === 'reference') {
    if (hasAdoptedFrame) {
      return {
        action: 'recompile_then_video',
        label: '重编后继续生成视频',
        detail: '参考资源已经恢复，建议先把最新引用重编进提示词，再继续提交视频生成。',
      }
    }
    return {
      action: 'recompile_then_frame',
      label: '重编后生成首帧',
      detail: '参考资源已经恢复，建议先重编提示词，再继续提交首帧生成。',
    }
  }

  return null
}

interface BuildCanvasBetaGraphParams {
  bookTitle: string
  scripts: ScriptOutput[]
  shotsByEpisode: Record<number, StoryboardShotOutput[]>
  allAssets: AssetSummary[]
  qaEntries: Array<{ id?: number; episode: number; result: unknown; error_count?: number }>
  pendingStoryboardTasks?: PendingStoryboardTask[]
  shotExecutionSummaries?: ShotExecutionSummary[]
  selectedEpisode?: 'all' | number
}

const LANE_X = {
  assets: -360,
  scripts: 0,
  shots: 330,
  images: 690,
  videos: 1010,
  qa: 1320,
  delivery: 1620,
} as const

const VERTICAL_GAP = 170
const EPISODE_GAP = 90
const ASSET_GROUP_GAP = 60

function normalizeText(value: unknown) {
  return String(value ?? '').trim()
}

function normalizeEpisode(episode: unknown) {
  const value = Number(episode ?? 0)
  return Number.isFinite(value) && value > 0 ? value : null
}

function compareShotId(left: string, right: string) {
  return left.localeCompare(right, 'zh-Hans-CN', { numeric: true })
}

function normalizeShotKey(episode: number | null | undefined, shotId: string | null | undefined) {
  const normalizedShotId = normalizeText(shotId)
  if (!normalizedShotId) return ''
  return episode ? `${episode}-${normalizedShotId}` : normalizedShotId
}

function resolvePrimaryShotContextForAsset(
  asset: AssetSummary,
  selectedEpisode?: 'all' | number,
  inferredShotContexts: Array<{ episode: number; shotId: string }> = [],
) {
  const shotCandidates = (asset.shotIds ?? [])
    .map((rawShotId) => {
      const normalized = normalizeText(rawShotId)
      if (!normalized) return null
      const compositeMatch = normalized.match(/^(\d+)-(.+)$/)
      if (compositeMatch) {
        return {
          episode: Number(compositeMatch[1]),
          shotId: normalizeText(compositeMatch[2]),
        }
      }
      const inferredEpisode = asset.episodeIds[0] ?? (typeof selectedEpisode === 'number' ? selectedEpisode : null)
      return inferredEpisode
        ? {
            episode: inferredEpisode,
            shotId: normalized,
          }
        : null
    })
    .filter(Boolean) as Array<{ episode: number; shotId: string }>

  const combinedCandidates = [...shotCandidates]
  for (const inferred of inferredShotContexts) {
    if (
      !combinedCandidates.some(
        (item) => item.episode === inferred.episode && normalizeText(item.shotId) === normalizeText(inferred.shotId),
      )
    ) {
      combinedCandidates.push(inferred)
    }
  }

  const filteredCandidates =
    typeof selectedEpisode === 'number'
      ? combinedCandidates.filter((item) => item.episode === selectedEpisode)
      : combinedCandidates

  return filteredCandidates[0] ?? combinedCandidates[0] ?? null
}

function getEpisodeList(params: BuildCanvasBetaGraphParams) {
  const episodes = new Set<number>()
  for (const script of params.scripts) {
    const episode = normalizeEpisode(script.episode)
    if (episode) episodes.add(episode)
  }
  for (const episodeKey of Object.keys(params.shotsByEpisode)) {
    const episode = normalizeEpisode(episodeKey)
    if (episode) episodes.add(episode)
  }
  for (const qaEntry of params.qaEntries) {
    const episode = normalizeEpisode(qaEntry.episode)
    if (episode) episodes.add(episode)
  }
  for (const asset of params.allAssets) {
    for (const episode of asset.episodeIds ?? []) {
      const normalized = normalizeEpisode(episode)
      if (normalized) episodes.add(normalized)
    }
  }
  const sorted = Array.from(episodes).sort((left, right) => left - right)
  if (params.selectedEpisode === 'all' || !params.selectedEpisode) return sorted
  return sorted.filter((episode) => episode === params.selectedEpisode)
}

function shotAssets(shot: StoryboardShotOutput) {
  const assets = (shot as StoryboardShotOutput & {
    assets?: { images?: any[]; videos?: any[]; audios?: any[] }
  }).assets
  return {
    images: Array.isArray(assets?.images) ? assets.images : [],
    videos: Array.isArray(assets?.videos) ? assets.videos : [],
  }
}

function pickAssetPreviewUrl(asset: AssetSummary) {
  const reference = asset.references.find((item) => item.image_url || item.local_path)
  return reference?.image_url || reference?.local_path || null
}

function shotUsesAsset(asset: AssetSummary, episode: number, shotId: string, shot: StoryboardShotOutput) {
  const shotKey = normalizeShotKey(episode, shotId)
  if (asset.shotIds.some((item) => normalizeText(item) === shotKey || normalizeText(item) === shotId)) {
    return true
  }
  if (asset.category === 'location') {
    const sceneName = normalizeText(shot.scene_name)
    if (
      sceneName &&
      (sceneName === normalizeText(asset.title) ||
        sceneName === normalizeText(asset.subtitle) ||
        sceneName === normalizeText(asset.detailPrimary))
    ) {
      return true
    }
  }
  const usedAssets = Array.isArray(shot.used_assets) ? shot.used_assets : []
  return usedAssets.some((item) => {
    const usedAssetId = normalizeText(item.asset_id)
    const usedAssetName = normalizeText(item.asset_name)
    return (
      usedAssetId === normalizeText(asset.assetRecordId) ||
      usedAssetId === asset.id ||
      usedAssetName === asset.title ||
      usedAssetName === asset.subtitle
    )
  })
}

function findAssetsForShot(allAssets: AssetSummary[], episode: number, shot: StoryboardShotOutput) {
  const shotId = normalizeText(shot.shot_id)
  return allAssets.filter((asset) => shotUsesAsset(asset, episode, shotId, shot))
}

function hasUsablePrompt(shot: StoryboardShotOutput) {
  return Boolean(normalizeText(shot.visual_prompt_static) || normalizeText(shot.visual_prompt_motion))
}

function buildShotRuntimeSummary(
  shot: StoryboardShotOutput,
  pendingTasks: PendingStoryboardTask[],
  latestExecutionSummary: ShotExecutionSummary | null,
) {
  const assets = shotAssets(shot)
  const adoptedImage = assets.images.find((item) => item?.adopted) ?? null
  const adoptedVideo = assets.videos.find((item) => item?.adopted) ?? null
  return {
    latestExecutionLabel: latestExecutionSummary?.label ?? null,
    pendingKinds: pendingTasks.map((item) => item.kind),
    hasAdoptedFrame: Boolean(adoptedImage),
    hasAdoptedVideo: Boolean(adoptedVideo),
  }
}

function buildShotMeta(shot: StoryboardShotOutput) {
  const assets = shotAssets(shot)
  return [
    shot.scene_name ? `场景：${shot.scene_name}` : '',
    shot.camera_angle || shot.camera_movement
      ? `镜头：${shot.camera_angle || '待补充'} / ${shot.camera_movement || '待补充'}`
      : '',
    typeof shot.duration === 'number' ? `时长：${shot.duration}s` : '',
    assets.images.length ? `图片 ${assets.images.length}` : '',
    assets.videos.length ? `视频 ${assets.videos.length}` : '',
  ].filter(Boolean)
}

function buildAssetMeta(asset: AssetSummary) {
  return [
    asset.variantLabel ? `版本：${asset.variantLabel}` : '',
    asset.episodeIds.length ? `集数：${asset.episodeIds.join(' / ')}` : '',
    asset.shotIds.length ? `镜头：${asset.shotIds.length}` : '',
    `参考图：${asset.previewCount}/${asset.referenceCount}`,
  ].filter(Boolean)
}

function buildScriptMeta(script: ScriptOutput, shotCount: number, bookTitle: string) {
  return [
    script.status ? `状态：${script.status}` : 'draft',
    script.content ? `文本长度：${script.content.length}` : '',
    shotCount ? `镜头数：${shotCount}` : '',
    bookTitle,
  ].filter(Boolean)
}

function buildQaMeta(qaEntry: { id?: number; episode: number; result: unknown; error_count?: number }, shotCount: number) {
  return [
    `${qaEntry.error_count ?? 0} 个待处理问题`,
    shotCount ? `镜头覆盖：${shotCount}` : '',
    '建议进入 QA 修复',
  ].filter(Boolean)
}

function buildDeliveryMeta(shotCount: number, imageCount: number, videoCount: number, hasBlocker: boolean) {
  return [
    hasBlocker ? '未达可交付状态' : '可继续推进交付',
    `镜头：${shotCount}`,
    `图片：${imageCount}`,
    `视频：${videoCount}`,
  ]
}

function kindFromAssetCategory(category: AssetSummary['category']): CanvasNodeKind {
  if (category === 'character') return 'character'
  if (category === 'location') return 'location'
  return 'prop'
}

function findLatestExecutionSummary(
  shotExecutionSummaries: ShotExecutionSummary[],
  episode: number,
  shotId: string,
) {
  return (
    shotExecutionSummaries.find(
      (item) => item.episode === episode && normalizeText(item.shotId) === normalizeText(shotId),
    ) ?? null
  )
}

function findPendingTasksForShot(pendingStoryboardTasks: PendingStoryboardTask[], episode: number, shotId: string) {
  return pendingStoryboardTasks.filter(
    (item) => item.episode === episode && normalizeText(item.shotId) === normalizeText(shotId),
  )
}

function createNode(
  node: Omit<CanvasBetaNode, 'x' | 'y'>,
  laneX: number,
  y: number,
): CanvasBetaNode {
  return {
    ...node,
    x: laneX,
    y,
  }
}

export function shouldShowCanvasSyncingState({
  graphNodeCount,
  isProjectDataLoading,
}: {
  graphNodeCount: number
  isProjectDataLoading: boolean
}) {
  return graphNodeCount === 0 && isProjectDataLoading
}

export function resolveCanvasEpisodeSelection({
  selectedEpisode,
  availableEpisodes,
  navigationTargetEpisode,
}: {
  selectedEpisode: 'all' | number
  availableEpisodes: number[]
  navigationTargetEpisode?: number | null
}) {
  if (selectedEpisode === 'all') return 'all' as const
  if (availableEpisodes.includes(selectedEpisode)) return selectedEpisode

  const normalizedNavigationEpisode = normalizeEpisode(navigationTargetEpisode)
  if (normalizedNavigationEpisode && availableEpisodes.includes(normalizedNavigationEpisode)) {
    return normalizedNavigationEpisode
  }
  return availableEpisodes[0] ?? ('all' as const)
}

export function shouldShowCanvasNavigationRefocusAction({
  target,
  targetNodeId,
}: {
  target: CanvasNavigationTarget | null
  targetNodeId: string | null
}) {
  return Boolean(target && targetNodeId)
}

export function buildCanvasNavigationTargetStatus({
  target,
  targetNodeId,
  isProjectDataLoading,
}: {
  target: CanvasNavigationTarget | null
  targetNodeId: string | null
  isProjectDataLoading: boolean
}) {
  if (!target) return null
  if (isProjectDataLoading) {
    return {
      tone: 'syncing' as const,
      label: '正在等待目标节点',
      detail: '创作画布仍在同步真实项目数据，目标节点会在数据到齐后自动恢复定位。',
    }
  }
  if (targetNodeId) {
    return {
      tone: 'resolved' as const,
      label: '已定位到恢复目标',
      detail: '当前画布已经接住这次恢复链路的目标节点，可继续围绕该镜头或资产推进创作。',
    }
  }
  return {
    tone: 'missing' as const,
    label: '暂未定位到恢复目标',
    detail: '当前恢复上下文仍然保留，但目标节点暂未出现在画布中。可能是上游数据已变化，也可能需要回任务中心或镜头工作台继续确认。',
  }
}

export function buildCanvasRecoveryClosureStatus({
  target,
  targetNodeId,
  isProjectDataLoading,
  pendingPromptTaskId,
  pendingFrameTaskId,
  pendingVideoTaskId,
  latestExecutionTaskId,
  hasCompiledPrompt,
  hasAdoptedFrame,
  hasAdoptedVideo,
  hasReferenceAssets,
}: {
  target: CanvasNavigationTarget | null
  targetNodeId: string | null
  isProjectDataLoading: boolean
  pendingPromptTaskId?: string | null
  pendingFrameTaskId?: string | null
  pendingVideoTaskId?: string | null
  latestExecutionTaskId?: string | null
  hasCompiledPrompt?: boolean
  hasAdoptedFrame?: boolean
  hasAdoptedVideo?: boolean
  hasReferenceAssets?: boolean
}) {
  if (!target?.recoveryKind) return null

  if (isProjectDataLoading) {
    return {
      tone: 'syncing' as const,
      label: '恢复收口同步中',
      detail: '画布仍在同步恢复链路的最新运行态，稍后会自动判断这次恢复是否已经真正收口。',
    }
  }

  const pendingTaskId =
    target.recoveryKind === 'prompt'
      ? pendingPromptTaskId
      : target.recoveryKind === 'frame'
        ? pendingFrameTaskId
        : target.recoveryKind === 'video'
          ? pendingVideoTaskId
          : null

  if (target.taskId && pendingTaskId && pendingTaskId === target.taskId) {
    return {
      tone: 'pending' as const,
      label: '恢复结果仍待回收',
      detail: '当前这条恢复任务仍在后台执行或等待回收，建议优先回任务中心继续刷新状态，确认结果真正写回后再继续下游创作。',
    }
  }

  const exactTaskRecovered = Boolean(target.taskId && latestExecutionTaskId && latestExecutionTaskId === target.taskId)
  const latestExecutionChanged = Boolean(target.taskId && latestExecutionTaskId && latestExecutionTaskId !== target.taskId)
  const kindRecovered =
    target.recoveryKind === 'prompt'
      ? Boolean(hasCompiledPrompt)
      : target.recoveryKind === 'frame'
        ? Boolean(hasAdoptedFrame)
        : target.recoveryKind === 'video'
          ? Boolean(hasAdoptedVideo)
          : Boolean(hasReferenceAssets)

  if (latestExecutionChanged && targetNodeId) {
    return {
      tone: 'changed' as const,
      label: '恢复目标已变化',
      detail: '恢复上下文仍然保留，但当前镜头的最近执行任务已经切换到其他任务，说明这次恢复结果与画布最新版本不再完全一致。建议回任务中心或镜头工作台继续确认版本变化。',
    }
  }

  if (exactTaskRecovered || (!latestExecutionChanged && kindRecovered)) {
    return {
      tone: 'closed' as const,
      label: '恢复链路已收口',
      detail: '当前恢复结果已经回写到画布链路中，可以继续在镜头、资产或分镜产物侧推进后续创作，不必继续停留在恢复流程里。',
    }
  }

  if (targetNodeId) {
    return {
      tone: 'changed' as const,
      label: '恢复目标已变化',
      detail: '恢复上下文仍然保留，但这次链路的原始任务结果没有直接映射到当前最新画布状态。建议回任务中心或镜头工作台继续确认版本变化。',
    }
  }

  return {
    tone: 'missing' as const,
    label: '恢复收口待人工确认',
    detail: '当前恢复上下文存在，但画布里暂未确认这条链路是否已经真正收口。建议回任务中心复核运行态，或在镜头工作台检查产物采纳情况。',
  }
}

export function buildCanvasRecoveryActionPlan({
  target,
  targetStatusTone,
  closureStatusTone,
  canRefocus,
}: {
  target: CanvasNavigationTarget | null
  targetStatusTone?: RecoveryStatusTone | null
  closureStatusTone?: RecoveryStatusTone | null
  canRefocus: boolean
}): CanvasRecoveryActionPlan | null {
  if (!target) return null

  const hasTask = Boolean(target.taskId)
  const hasShot = Boolean(target.shotId)
  const hasAsset = Boolean(target.assetId)
  const storyboardOrAssetAction = hasShot ? 'storyboard' : hasAsset ? 'assets' : null

  if (targetStatusTone === 'missing') {
    return {
      primaryAction: hasTask ? 'tasks' : storyboardOrAssetAction,
      allowRefocus: false,
      helperText: '当前更适合先回任务中心或业务工作台确认最新链路，再决定是否继续在画布里推进。',
    }
  }

  if (closureStatusTone === 'syncing' || closureStatusTone === 'pending') {
    return {
      primaryAction: hasTask ? 'tasks' : canRefocus ? 'refocus' : storyboardOrAssetAction,
      allowRefocus: canRefocus,
      helperText: '这条恢复链路还在回收中，优先回到任务中心查看最新状态会更稳妥。',
    }
  }

  if (closureStatusTone === 'closed') {
    return {
      primaryAction: storyboardOrAssetAction,
      allowRefocus: canRefocus,
      helperText: '恢复结果已经写回当前链路，下一步应直接回到镜头或资产继续创作，而不是停留在恢复说明里。',
    }
  }

  if (closureStatusTone === 'changed' || closureStatusTone === 'missing') {
    return {
      primaryAction: hasTask ? 'tasks' : storyboardOrAssetAction,
      allowRefocus: closureStatusTone === 'changed' ? canRefocus : false,
      helperText: '原始恢复任务和当前画布状态已经不完全一致，先回上游确认版本变化会更安全。',
    }
  }

  if (targetStatusTone === 'resolved' && canRefocus) {
    return {
      primaryAction: 'refocus',
      allowRefocus: true,
      helperText: '如果你已经在画布里切走了，可以先重新定位到恢复节点，再继续处理下游动作。',
    }
  }

  return {
    primaryAction: storyboardOrAssetAction ?? (hasTask ? 'tasks' : null),
    allowRefocus: canRefocus,
    helperText: '可以继续围绕当前恢复上下文推进，也可以切回上游工作面核对最新状态。',
  }
}

export function buildCanvasNavigationSummary(target: CanvasNavigationTarget | null) {
  if (!target) return null

  const episode = normalizeEpisode(target.episode)
  const shotId = normalizeText(target.shotId)
  const assetLabel = normalizeText(target.assetLabel)
  const taskId = normalizeText(target.taskId)
  const recoveryKindLabel =
    target.recoveryKind === 'prompt'
      ? '提示词回收'
      : target.recoveryKind === 'frame'
        ? '首帧回收'
        : target.recoveryKind === 'video'
          ? '视频回收'
          : target.recoveryKind === 'reference'
            ? '参考图回收'
            : null
  const recoveryIntentDetail =
    target.recoveryIntent === 'shot_variant_refinement'
      ? '当前入口更偏向镜头精调与变体收口。'
      : target.recoveryIntent === 'reference'
        ? '当前入口更偏向参考图回收与结果确认。'
        : '当前入口来自跨工作面的恢复链路。'

  const titleParts = [
    episode ? `第 ${episode} 集` : null,
    shotId ? `镜头 ${shotId}` : null,
    assetLabel || null,
    recoveryKindLabel,
  ].filter(Boolean)

  return {
    title: titleParts.length > 0 ? titleParts.join(' / ') : '已按恢复上下文进入创作画布',
    detail: taskId
      ? `当前正在围绕任务 ${taskId} 的恢复结果继续定位与确认。${recoveryIntentDetail}`
      : recoveryIntentDetail,
  }
}

export function buildProductWorkspaceCanvasBetaGraph(params: BuildCanvasBetaGraphParams): CanvasBetaGraph {
  const pendingStoryboardTasks = params.pendingStoryboardTasks ?? []
  const shotExecutionSummaries = params.shotExecutionSummaries ?? []
  const nodes: CanvasBetaNode[] = []
  const edges: CanvasBetaEdge[] = []
  const episodes = getEpisodeList(params)
  const inferredAssetShotContexts = new Map<string, Array<{ episode: number; shotId: string }>>()
  const edgeKeys = new Set<string>()

  for (const episode of episodes) {
    const shots = params.shotsByEpisode[episode] ?? []
    for (const shot of shots) {
      const shotId = normalizeText(shot.shot_id)
      if (!shotId) continue
      const linkedAssets = findAssetsForShot(params.allAssets, episode, shot)
      for (const asset of linkedAssets) {
        const inferredContexts = inferredAssetShotContexts.get(asset.id) ?? []
        if (
          !inferredContexts.some(
            (item) => item.episode === episode && normalizeText(item.shotId) === normalizeText(shotId),
          )
        ) {
          inferredContexts.push({ episode, shotId })
          inferredAssetShotContexts.set(asset.id, inferredContexts)
        }
      }
    }
  }

  const pushEdge = (source: string, target: string) => {
    const key = `${source}:${target}`
    if (edgeKeys.has(key)) return
    edgeKeys.add(key)
    edges.push({ id: `edge-${source}-${target}`, source, target })
  }

  for (const asset of params.allAssets) {
    const relevant = params.selectedEpisode === 'all' || params.selectedEpisode === undefined
      ? true
      : asset.episodeIds.includes(params.selectedEpisode as number) ||
        asset.shotIds.some((item) => normalizeText(item).startsWith(`${params.selectedEpisode}-`))
    if (!relevant) continue

    const episode = asset.episodeIds[0] ?? episodes[0] ?? 1
    const primaryShotContext = resolvePrimaryShotContextForAsset(
      asset,
      params.selectedEpisode,
      inferredAssetShotContexts.get(asset.id) ?? [],
    )
    const y = episode * (VERTICAL_GAP * 2 + EPISODE_GAP) + nodes.filter((node) => node.kind === kindFromAssetCategory(asset.category)).length * ASSET_GROUP_GAP
    nodes.push(
      createNode(
        {
          id: `canvas-asset-${asset.id}`,
          kind: kindFromAssetCategory(asset.category),
          title: asset.title,
          subtitle: asset.subtitle,
          meta: buildAssetMeta(asset),
          previewUrl: pickAssetPreviewUrl(asset),
          hasOutput: asset.previewCount > 0 || asset.references.length > 0,
          hasBlocker: asset.previewCount === 0 || asset.status === 'draft',
          missingReference: asset.previewCount === 0,
          route: {
            section: 'assets',
            options: {
              episode,
              shotId: primaryShotContext?.shotId ?? null,
              assetId: asset.id,
              assetLabel: asset.title,
            },
          },
        },
        LANE_X.assets,
        y,
      ),
    )
  }

  for (const episode of episodes) {
    const script = params.scripts.find((item) => item.episode === episode) ?? null
    const shots = [...(params.shotsByEpisode[episode] ?? [])].sort((left, right) =>
      compareShotId(normalizeText(left.shot_id), normalizeText(right.shot_id)),
    )
    const qaEntry = params.qaEntries.find((item) => item.episode === episode) ?? null
    const episodeOffset = (episode - 1) * (shots.length * VERTICAL_GAP + EPISODE_GAP + 120)

    if (script) {
      nodes.push(
        createNode(
          {
            id: `canvas-script-episode-${episode}`,
            kind: 'script',
            title: `第 ${episode} 集剧本`,
            subtitle: script.status || 'draft',
            meta: buildScriptMeta(script, shots.length, params.bookTitle),
            hasOutput: Boolean(normalizeText(script.content)),
            hasBlocker: !normalizeText(script.content),
            route: {
              section: 'scripts',
              options: { episode },
            },
          },
          LANE_X.scripts,
          episodeOffset,
        ),
      )
    }

    let imageCount = 0
    let videoCount = 0
    let episodeHasBlocker = false

    shots.forEach((shot, index) => {
      const shotId = normalizeText(shot.shot_id)
      const shotY = episodeOffset + index * VERTICAL_GAP
      const linkedAssets = findAssetsForShot(params.allAssets, episode, shot)
      const pendingTasks = findPendingTasksForShot(pendingStoryboardTasks, episode, shotId)
      const latestExecutionSummary = findLatestExecutionSummary(shotExecutionSummaries, episode, shotId)
      const runtimeSummary = buildShotRuntimeSummary(shot, pendingTasks, latestExecutionSummary)
      const media = shotAssets(shot)
      const missingReference = linkedAssets.some((asset) => asset.previewCount === 0)
      const hasOutput = media.images.length > 0 || media.videos.length > 0
      const hasBlocker = !hasUsablePrompt(shot) || missingReference
      if (hasBlocker) episodeHasBlocker = true

      nodes.push(
        createNode(
          {
            id: `canvas-shot-${episode}-${shotId}`,
            kind: 'shot',
            title: `镜头 ${shotId}`,
            subtitle: normalizeText(shot.dialogue) || `[${normalizeText(shot.scene_name)}]`,
            meta: buildShotMeta(shot),
            runtimeSummary,
            hasOutput,
            hasBlocker,
            missingReference,
            route: {
              section: 'storyboard',
              options: { episode, shotId },
            },
          },
          LANE_X.shots,
          shotY,
        ),
      )

      if (script) {
        pushEdge(`canvas-script-episode-${episode}`, `canvas-shot-${episode}-${shotId}`)
      }

      linkedAssets.forEach((asset) => {
        pushEdge(`canvas-asset-${asset.id}`, `canvas-shot-${episode}-${shotId}`)
      })

      media.images.forEach((image, mediaIndex) => {
        imageCount += 1
        const imageId = normalizeText(image?.id) || `${episode}-${shotId}-image-${mediaIndex + 1}`
        nodes.push(
          createNode(
            {
              id: `canvas-image-${imageId}`,
              kind: 'image',
              title: normalizeText(image?.title) || `分镜图 ${shotId} v${mediaIndex + 1}`,
              subtitle: normalizeText(image?.model) || normalizeText(image?.label) || '候选图',
              meta: [
                image?.label ? `版本：${image.label}` : '',
                image?.adopted ? '已采用' : '候选图',
                normalizeText(image?.prompt) ? '已绑定静态提示词' : '',
              ].filter(Boolean),
              previewUrl: image?.uri || image?.previewUrl || null,
              hasOutput: true,
              hasBlocker: false,
              route: {
                section: 'storyboard',
                options: { episode, shotId },
              },
            },
            LANE_X.images,
            shotY + mediaIndex * 48,
          ),
        )
        pushEdge(`canvas-shot-${episode}-${shotId}`, `canvas-image-${imageId}`)
      })

      media.videos.forEach((video, mediaIndex) => {
        videoCount += 1
        const videoId = normalizeText(video?.id) || `${episode}-${shotId}-video-${mediaIndex + 1}`
        nodes.push(
          createNode(
            {
              id: `canvas-video-${videoId}`,
              kind: 'video',
              title: normalizeText(video?.title) || `视频 ${shotId} v${mediaIndex + 1}`,
              subtitle: normalizeText(video?.model) || normalizeText(video?.label) || '候选视频',
              meta: [
                video?.label ? `版本：${video.label}` : '',
                video?.adopted ? '已采用' : '候选视频',
                normalizeText(video?.prompt) ? '已绑定运动提示词' : '',
              ].filter(Boolean),
              previewUrl: video?.previewUrl || null,
              hasOutput: true,
              hasBlocker: false,
              route: {
                section: 'storyboard',
                options: { episode, shotId },
              },
            },
            LANE_X.videos,
            shotY + mediaIndex * 48,
          ),
        )
        pushEdge(`canvas-shot-${episode}-${shotId}`, `canvas-video-${videoId}`)
      })
    })

    if (qaEntry) {
      const qaId = `canvas-qa-episode-${episode}`
      const qaY = episodeOffset + Math.max((shots.length - 1) * VERTICAL_GAP, 0)
      nodes.push(
        createNode(
          {
            id: qaId,
            kind: 'qa',
            title: `第 ${episode} 集质检`,
            subtitle: `${qaEntry.error_count ?? 0} 个待处理问题`,
            meta: buildQaMeta(qaEntry, shots.length),
            hasOutput: true,
            hasBlocker: (qaEntry.error_count ?? 0) > 0,
            route: {
              section: 'qa',
              options: { episode },
            },
          },
          LANE_X.qa,
          qaY,
        ),
      )
    }

    const deliveryId = `canvas-delivery-episode-${episode}`
    const deliveryHasBlocker = episodeHasBlocker || (qaEntry?.error_count ?? 0) > 0
    const deliveryY = episodeOffset + Math.max((shots.length - 1) * VERTICAL_GAP, 0)
    nodes.push(
      createNode(
        {
          id: deliveryId,
          kind: 'delivery',
          title: `第 ${episode} 集交付`,
          subtitle: deliveryHasBlocker ? '未达可交付状态' : '可继续推进交付',
          meta: buildDeliveryMeta(shots.length, imageCount, videoCount, deliveryHasBlocker),
          hasOutput: imageCount > 0 || videoCount > 0,
          hasBlocker: deliveryHasBlocker,
          route: {
            section: 'delivery',
            options: { episode },
          },
        },
        LANE_X.delivery,
        deliveryY,
      ),
    )

    if (qaEntry) {
      pushEdge(`canvas-qa-episode-${episode}`, deliveryId)
    }
  }

  return {
    nodes,
    edges,
    summary: {
      episodeCount: episodes.length,
      shotCount: nodes.filter((node) => node.kind === 'shot').length,
      assetCount: nodes.filter((node) => node.kind === 'character' || node.kind === 'location' || node.kind === 'prop').length,
      imageCount: nodes.filter((node) => node.kind === 'image').length,
      videoCount: nodes.filter((node) => node.kind === 'video').length,
      qaCount: nodes.filter((node) => node.kind === 'qa').length,
    },
  }
}

export function resolveCanvasNavigationNodeId(graph: CanvasBetaGraph, target: CanvasNavigationTarget | null) {
  if (!target) return null

  const targetShotId = normalizeText(target.shotId)
  const targetAssetId = normalizeText(target.assetId)
  const targetAssetLabel = normalizeText(target.assetLabel)
  const targetEpisode = normalizeEpisode(target.episode)

  if (targetShotId && targetEpisode) {
    const shotNodeId = `canvas-shot-${targetEpisode}-${targetShotId}`
    if (graph.nodes.some((node) => node.id === shotNodeId)) return shotNodeId
  }

  if (targetAssetId) {
    const assetNode = graph.nodes.find(
      (node) => (node.kind === 'character' || node.kind === 'location' || node.kind === 'prop') && node.route?.options?.assetId === targetAssetId,
    )
    if (assetNode) return assetNode.id
  }

  if (targetAssetLabel) {
    const assetNode = graph.nodes.find(
      (node) =>
        (node.kind === 'character' || node.kind === 'location' || node.kind === 'prop') &&
        (node.title === targetAssetLabel || node.route?.options?.assetLabel === targetAssetLabel),
    )
    if (assetNode) return assetNode.id
  }

  return null
}
