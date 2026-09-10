import type { ScriptOutput, StoryboardShotOutput } from '../domain/bookOutputs'
import { getScriptDecision, type ScriptDecisionMap } from './productWorkspaceScriptDecisions'
import { buildScriptReleaseSummary } from './productWorkspaceScriptRelease'
import type { ContentTaskState, WorkspaceTaskRouteSection } from './productWorkspaceSectionContracts'

export type TaskCenterStatus = 'queued' | 'running' | 'done' | 'error' | 'blocked' | 'skipped'
export type TaskCenterSection = Exclude<WorkspaceTaskRouteSection, 'tasks'>

export interface TaskCenterEntry {
  id: string
  type: string
  target: string
  status: TaskCenterStatus
  progress: string
  detail: string
  statusReason?: string
  retryable: boolean
  actionLabel: string
  actionTarget: TaskCenterSection
  episode: number | null
  scope?: 'global' | 'episode'
  isBatch?: boolean
  taskId?: string
  shotId?: string
  assetId?: string
  recoveryKind?: 'frame' | 'video' | 'reference' | 'prompt'
  recoveryMeta?: {
    restartedFromTaskId?: string
    restartCount?: number
    lastRestartedAt?: string
  }
  creativeTaskMeta?: {
    modelProfileId?: string
    provider?: string
    externalTaskId?: string | null
    externalStatus?: string | null
    generationChain?: string
    triggeredByPromptRecompile?: boolean
    promptRecompileReason?: string
    promptRecompileTaskId?: string
    promptRecompileVersion?: number | null
    taskPromptVersion?: number | null
    currentShotPromptVersion?: number | null
    promptVersionDrift?: number | null
    firstFrameAssetId?: string
    firstFrameUrl?: string
    providerTaskMode?: string
    referenceAssetIds?: string[]
    assetScope?: string
    assetSubject?: string
    sourceAssetId?: string
    referenceImages?: Array<{
      referenceAssetId?: string
      imageUrl?: string
      title?: string
    }>
  }
  promptHealth?: {
    degradedShotCount?: number
    recommendedRestoreCount?: number
    partialRestoreCount?: number
    fullRestoreCount?: number
    manualRepairCount?: number
    degradedShots?: Array<{
      episode?: number | null
      shotId?: string
      sceneName?: string
      promptVersion?: string | number | null
      recommendedRestoreVersion?: string | number | null
      recommendedRestoreReason?: string | null
      missingCriticalCount?: number
      isSceneOnlyCandidate?: boolean
    }>
  }
  agentMeta?: {
    sessionId: number
    sessionStatus: string
    evidenceFingerprint?: string
    planFingerprint?: string
    operation?: string
  }
}

interface QaEntry {
  episode: number
  error_count?: number
}

export interface TaskCenterQaWorkbenchEpisodeSummary {
  episode: number
  totalIssueCount: number
  openIssueCount: number
  highOpenIssueCount: number
  inProgressCount: number
  resolvedCount: number
}

interface Params {
  contentReady: boolean
  adaptationLocked: boolean
  adaptationReadyForDownstream: boolean
  contentTask: ContentTaskState
  scripts: ScriptOutput[]
  scriptDecisionState: ScriptDecisionMap
  shotsByEpisode: Record<number, StoryboardShotOutput[]>
  qaEntries: QaEntry[]
  qaWorkbenchEpisodes?: TaskCenterQaWorkbenchEpisodeSummary[]
}

function formatEpisodeLabel(episode: number) {
  return `第 ${episode} 集`
}
function normalizeReferenceScope(scope: string | undefined) {
  const normalized = String(scope || '').trim().toLowerCase()
  if (normalized === 'scene' || normalized === 'location') return 'scene'
  if (normalized === 'character') return 'character'
  if (normalized === 'prop') return 'prop'
  return ''
}

function hasPromptPair(shot: StoryboardShotOutput) {
  return Boolean(shot.visual_prompt_static?.trim()) && Boolean(shot.visual_prompt_motion?.trim())
}

function hasShotReferences(shot: StoryboardShotOutput) {
  const lockedSummary = shot.locked_reference_summary?.all ?? []
  if (lockedSummary.length > 0) return true

  const referenceImages = shot.reference_images ?? []
  if (referenceImages.length > 0) return true

  const characterCount = Object.values(shot.assets?.references?.characters ?? {}).reduce((sum, items) => sum + items.length, 0)
  const sceneCount = shot.assets?.references?.scene?.length ?? 0
  const propCount = Object.values(shot.assets?.references?.props ?? {}).reduce((sum, items) => sum + items.length, 0)
  return characterCount + sceneCount + propCount > 0
}

function hasProjectDownstreamArtifacts(params: Pick<Params, 'scripts' | 'shotsByEpisode'>) {
  return params.scripts.some((item) => Boolean(item.content?.trim())) || Object.values(params.shotsByEpisode).some((shots) => shots.length > 0)
}

function buildPromptHealthSummary(shots: StoryboardShotOutput[], episode?: number | null) {
  const degradedShots = shots.filter((shot) => Boolean(shot.prompt_version_audit?.is_degraded_version))
  if (degradedShots.length === 0) return undefined

  const recommendedShots = degradedShots.filter(
    (shot) => shot.recommended_restore_version?.version !== null && shot.recommended_restore_version?.version !== undefined,
  )
  const partialRestoreCount = recommendedShots.filter(
    (shot) => String(shot.recommended_restore_version?.reason || '').trim() === 'best_partial_recovery_version',
  ).length
  const fullRestoreCount = recommendedShots.length - partialRestoreCount

  return {
    degradedShotCount: degradedShots.length,
    recommendedRestoreCount: recommendedShots.length,
    partialRestoreCount,
    fullRestoreCount,
    manualRepairCount: Math.max(degradedShots.length - recommendedShots.length, 0),
    degradedShots: degradedShots.map((shot) => ({
      episode: episode ?? shot.episode ?? null,
      shotId: String(shot.shot_id || '').trim() || undefined,
      sceneName: String(shot.scene_name || '').trim() || undefined,
      promptVersion: shot.prompt_version ?? null,
      recommendedRestoreVersion: shot.recommended_restore_version?.version ?? null,
      recommendedRestoreReason: shot.recommended_restore_version?.reason ?? null,
      missingCriticalCount: Number(shot.prompt_version_audit?.missing_critical_count ?? 0),
      isSceneOnlyCandidate: Boolean(shot.prompt_version_audit?.is_scene_only_candidate),
    })),
  }
}

export function buildTaskCenterEntries(params: Params): TaskCenterEntry[] {
  const entries: TaskCenterEntry[] = []
  entries.push(buildContentTaskEntry(params))
  entries.push(buildAdaptationTaskEntry(params))

  const episodeIds = new Set<number>([
    ...params.scripts.map((item) => item.episode),
    ...Object.keys(params.shotsByEpisode).map((value) => Number(value)),
    ...params.qaEntries.map((item) => item.episode),
    ...(params.qaWorkbenchEpisodes ?? []).map((item) => item.episode),
  ])

  Array.from(episodeIds)
    .filter((episode) => episode > 0)
    .sort((left, right) => left - right)
    .forEach((episode) => {
      const script = params.scripts.find((item) => item.episode === episode && item.content.trim()) ?? null
      const scriptDecision = getScriptDecision(params.scriptDecisionState, episode)
      const shots = params.shotsByEpisode[episode] ?? []
      const qaErrorCount = params.qaEntries
        .filter((item) => item.episode === episode)
        .reduce((sum, item) => sum + (item.error_count ?? 0), 0)
      const qaWorkbenchSummary = params.qaWorkbenchEpisodes?.find((item) => item.episode === episode) ?? null

      entries.push(buildScriptTaskEntry(episode, script, params.adaptationReadyForDownstream, scriptDecision))
      entries.push(buildStoryboardTaskEntry(episode, params.adaptationReadyForDownstream, Boolean(script), shots, scriptDecision))
      entries.push(buildAssetTaskEntry(episode, shots))
      entries.push(buildQaTaskEntry(episode, shots.length > 0 || Boolean(script), qaErrorCount, qaWorkbenchSummary))
    })

  entries.push(buildBatchPromptTaskEntry(params.shotsByEpisode))
  entries.push(buildBatchAssetTaskEntry(params.shotsByEpisode))
  entries.push(buildBatchQaTaskEntry(params.qaWorkbenchEpisodes ?? [], params.qaEntries))

  return entries
}

function buildContentTaskEntry(params: Params): TaskCenterEntry {
  const target = params.contentTask.mode === 'short' ? '短篇录入' : '长篇上传'

  if (params.contentTask.status === 'running' || params.contentTask.status === 'uploading') {
    return {
      id: 'task-content-import',
      type: '内容导入',
      target,
      status: 'running',
      progress: params.contentTask.taskId ? '任务进行中' : '准备中',
      detail: params.contentTask.message || '内容导入进行中。',
      retryable: false,
      actionLabel: '查看内容准备',
      actionTarget: 'content',
      episode: null,
      scope: 'global',
    }
  }

  if (params.contentTask.status === 'error') {
    return {
      id: 'task-content-import',
      type: '内容导入',
      target,
      status: 'error',
      progress: '导入失败',
      detail: params.contentTask.message || '内容导入失败。',
      statusReason: '导入流程中断',
      retryable: true,
      actionLabel: '前往重试',
      actionTarget: 'content',
      episode: null,
      scope: 'global',
    }
  }

  if (params.contentReady || params.contentTask.status === 'done') {
    return {
      id: 'task-content-import',
      type: '内容导入',
      target: '内容准备',
      status: 'done',
      progress: '已完成',
      detail: params.contentTask.message?.trim() || '项目已经具备内容基础，可以继续推进后续生产流程。',
      retryable: false,
      actionLabel: '查看内容准备',
      actionTarget: 'content',
      episode: null,
      scope: 'global',
    }
  }

  return {
    id: 'task-content-import',
    type: '内容导入',
    target,
    status: 'queued',
    progress: '待开始',
    detail: '需要先准备原始内容，后续改编、剧本和分镜链路才能启动。',
    retryable: false,
    actionLabel: '前往内容准备',
    actionTarget: 'content',
    episode: null,
    scope: 'global',
  }
}
function buildAdaptationTaskEntry(params: Params): TaskCenterEntry {
  if (params.adaptationLocked) {
    return {
      id: 'task-adaptation',
      type: '改编方向锁定',
      target: '项目主方向',
      status: 'done',
      progress: '已锁定',
      detail: '项目主改编方向已经锁定，下游模块应继续继承同一约束继续生产。',
      retryable: false,
      actionLabel: '查看改编方向',
      actionTarget: 'adaptation',
      episode: null,
      scope: 'global',
    }
  }

  if (!params.contentReady) {
    return {
      id: 'task-adaptation',
      type: '改编方向锁定',
      target: '项目主方向',
      status: 'blocked',
      progress: '等待上游',
      detail: '需要先完成内容准备，才能进入正式改编方向决策。',
      statusReason: '内容准备尚未完成',
      retryable: false,
      actionLabel: '前往内容准备',
      actionTarget: 'content',
      episode: null,
      scope: 'global',
    }
  }

  if (hasProjectDownstreamArtifacts(params)) {
    return {
      id: 'task-adaptation',
      type: '改编方向锁定',
      target: '项目主方向',
      status: 'blocked',
      progress: '待补锁',
      detail: '当前项目已经有剧本或分镜等下游产物，但还没有正式锁定项目级主方向。',
      statusReason: '历史下游已存在，但主方向未锁定',
      retryable: false,
      actionLabel: '前往改编方向',
      actionTarget: 'adaptation',
      episode: null,
      scope: 'global',
    }
  }

  return {
    id: 'task-adaptation',
    type: '改编方向锁定',
    target: '项目主方向',
    status: 'queued',
    progress: '待确认',
    detail: '内容已经就绪，可以生成候选改编方向并锁定一个主方向。',
    retryable: false,
    actionLabel: '前往锁定',
    actionTarget: 'adaptation',
    episode: null,
    scope: 'global',
  }
}
function buildScriptTaskEntry(
  episode: number,
  script: ScriptOutput | null,
  adaptationReady: boolean,
  scriptDecision: { lockedAt: string | null; releasedAt: string | null; note: string },
): TaskCenterEntry {
  const release = buildScriptReleaseSummary({
    hasLockedAdaptation: adaptationReady,
    hasScript: Boolean(script),
    scriptLocked: Boolean(scriptDecision.lockedAt),
    scriptReleased: Boolean(scriptDecision.releasedAt),
  })

  if (release.phase === 'missing_adaptation') {
    return { id: `task-script-${episode}`, type: '剧本生产', target: formatEpisodeLabel(episode), status: 'blocked', progress: '等待上游', detail: '需要先锁定改编方向，才能继续生产分集剧本。', statusReason: '改编方向未锁定', retryable: false, actionLabel: '前往改编方向', actionTarget: 'adaptation', episode, scope: 'episode' }
  }
  if (release.phase === 'missing_script') {
    return { id: `task-script-${episode}`, type: '剧本生产', target: formatEpisodeLabel(episode), status: 'queued', progress: '待生成', detail: '当前还没有这一集剧本，下一步应进入剧本工作台继续生产。', retryable: false, actionLabel: '前往剧本工作台', actionTarget: 'scripts', episode, scope: 'episode' }
  }
  if (release.phase === 'pending_lock') {
    return { id: `task-script-${episode}`, type: '剧本生产', target: formatEpisodeLabel(episode), status: 'running', progress: '待锁稿', detail: '这一集已经有正式剧本输出，但还没有完成锁稿，建议先确认上游版本。', retryable: false, actionLabel: '前往剧本工作台', actionTarget: 'scripts', episode, scope: 'episode' }
  }
  if (release.phase === 'pending_release') {
    return { id: `task-script-${episode}`, type: '剧本生产', target: formatEpisodeLabel(episode), status: 'running', progress: '待放行', detail: '这一集剧本已经锁稿，但还没有完成“放行到分镜”，镜头工作台仍受约束。', retryable: false, actionLabel: '前往剧本工作台', actionTarget: 'scripts', episode, scope: 'episode' }
  }
  return { id: `task-script-${episode}`, type: '剧本生产', target: formatEpisodeLabel(episode), status: 'done', progress: '已锁稿并放行', detail: '这一集已经完成剧本生产、锁稿和放行，可继续推进分镜、资产和 QA。', retryable: false, actionLabel: '查看剧本工作台', actionTarget: 'scripts', episode, scope: 'episode' }
}
function buildStoryboardTaskEntry(
  episode: number,
  adaptationReady: boolean,
  hasScript: boolean,
  shots: StoryboardShotOutput[],
  scriptDecision: { lockedAt: string | null; releasedAt: string | null; note: string },
): TaskCenterEntry {
  if (shots.length > 0) {
    const promptHealth = buildPromptHealthSummary(shots, episode)
    if (promptHealth?.degradedShotCount) {
      const hasRecommendedRestore = Boolean(promptHealth.recommendedRestoreCount && promptHealth.recommendedRestoreCount > 0)
      const hasManualRepairOnly = Boolean(promptHealth.manualRepairCount && promptHealth.manualRepairCount > 0)
      return {
        id: `task-storyboard-${episode}`,
        type: '分镜生成',
        target: formatEpisodeLabel(episode),
        status: 'error',
        progress: hasRecommendedRestore ? `${promptHealth.degradedShotCount} 个镜头提示词待恢复` : `${promptHealth.degradedShotCount} 个镜头仍需人工修复`,
        detail: hasRecommendedRestore && hasManualRepairOnly ? '这一集已有部分镜头给出推荐恢复版本，但仍有镜头无法一键恢复，需要回到镜头工作台继续人工修复。' : hasRecommendedRestore ? '这一集已有镜头给出推荐恢复版本，但“恢复推荐版本”可能只是部分恢复，恢复后仍需继续核对缺失资产。' : '这一集已有镜头提示词跑偏，但当前没有更健康的推荐恢复版本，需要回到镜头工作台继续人工修复。',
        statusReason: hasRecommendedRestore ? hasManualRepairOnly ? `${promptHealth.recommendedRestoreCount} 个镜头已给出推荐恢复版本，${promptHealth.manualRepairCount} 个镜头仍需人工修复` : promptHealth.partialRestoreCount ? `${promptHealth.partialRestoreCount} 个镜头仅给出部分恢复版本，恢复后仍需继续修复` : `${promptHealth.recommendedRestoreCount} 个镜头已给出推荐恢复版本` : '部分镜头提示词版本跑偏，当前已无推荐恢复版本，需要人工继续修复',
        retryable: false,
        actionLabel: hasRecommendedRestore ? '前往首个恢复镜头' : '前往镜头继续修复',
        actionTarget: 'storyboard',
        episode,
        scope: 'episode',
        promptHealth,
      }
    }
    return { id: `task-storyboard-${episode}`, type: '分镜生成', target: formatEpisodeLabel(episode), status: 'done', progress: `${shots.length} 个镜头`, detail: '这一集已经拆出镜头，可以继续编译提示词、补资产和生成图视频。', retryable: false, actionLabel: '查看镜头工作台', actionTarget: 'storyboard', episode, scope: 'episode' }
  }
  const release = buildScriptReleaseSummary({ hasLockedAdaptation: adaptationReady, hasScript, scriptLocked: Boolean(scriptDecision.lockedAt), scriptReleased: Boolean(scriptDecision.releasedAt), shotCount: shots.length })
  if (!release.canEnterStoryboard) {
    return {
      id: `task-storyboard-${episode}`,
      type: '分镜生成',
      target: formatEpisodeLabel(episode),
      status: 'blocked',
      progress: release.phase === 'pending_release' ? '待剧本放行' : release.phase === 'pending_lock' ? '待剧本锁稿' : release.phase === 'missing_script' ? '等待上游' : '待改编方向',
      detail: release.phase === 'pending_release' ? '剧本已存在，但还没有完成放行到分镜，暂不应继续生成镜头。' : release.phase === 'pending_lock' ? '剧本已存在，但还没有完成锁稿，分镜生成仍受上游版本约束。' : release.phase === 'missing_script' ? '需要先有剧本，才能进行镜头拆解。' : '需要先锁定改编方向，才能进入正式分镜链路。',
      statusReason: release.phase === 'pending_release' ? '剧本未放行到分镜' : release.phase === 'pending_lock' ? '剧本尚未锁稿' : release.phase === 'missing_script' ? '缺少正式剧本' : '改编方向未锁定',
      retryable: false,
      actionLabel: release.phase === 'missing_adaptation' ? '前往改编方向' : '前往剧本工作台',
      actionTarget: release.phase === 'missing_adaptation' ? 'adaptation' : 'scripts',
      episode,
      scope: 'episode',
    }
  }
  return { id: `task-storyboard-${episode}`, type: '分镜生成', target: formatEpisodeLabel(episode), status: 'queued', progress: '待拆镜头', detail: '剧本已放行，但还没有产出镜头列表。', retryable: false, actionLabel: '前往镜头工作台', actionTarget: 'storyboard', episode, scope: 'episode' }
}
function buildAssetTaskEntry(episode: number, shots: StoryboardShotOutput[]): TaskCenterEntry {
  if (shots.length === 0) {
    return { id: `task-assets-${episode}`, type: '资产补全', target: formatEpisodeLabel(episode), status: 'blocked', progress: '等待上游', detail: '需要先有镜头拆解，才能判断角色、场景、道具和参考图是否齐全。', statusReason: '镜头尚未生成', retryable: false, actionLabel: '前往镜头工作台', actionTarget: 'storyboard', episode, scope: 'episode' }
  }
  const referenceReadyShots = shots.filter((shot) => hasShotReferences(shot)).length
  const imageReadyShots = shots.filter((shot) => (shot.assets?.images.length ?? 0) > 0).length
  const videoReadyShots = shots.filter((shot) => (shot.assets?.videos.length ?? 0) > 0).length
  const total = shots.length
  if (referenceReadyShots === total && imageReadyShots === total) {
    return { id: `task-assets-${episode}`, type: '资产补全', target: formatEpisodeLabel(episode), status: 'done', progress: `参考 ${referenceReadyShots}/${total} | 图片 ${imageReadyShots}/${total} | 视频 ${videoReadyShots}/${total}`, detail: '这一集镜头已经基本具备参考资产和首帧图片支持。', retryable: false, actionLabel: '查看资产中心', actionTarget: 'assets', episode, scope: 'episode' }
  }
  return { id: `task-assets-${episode}`, type: '资产补全', target: formatEpisodeLabel(episode), status: referenceReadyShots > 0 || imageReadyShots > 0 || videoReadyShots > 0 ? 'running' : 'queued', progress: `参考 ${referenceReadyShots}/${total} | 图片 ${imageReadyShots}/${total} | 视频 ${videoReadyShots}/${total}`, detail: referenceReadyShots > 0 || imageReadyShots > 0 || videoReadyShots > 0 ? '这一集已经开始补齐参考图或分镜图，但仍未完整覆盖。' : '镜头已经生成，但仍缺少统一参考资产和分镜图产物。', retryable: false, actionLabel: referenceReadyShots > 0 || imageReadyShots > 0 ? '前往资产中心' : '前往镜头工作台', actionTarget: referenceReadyShots > 0 || imageReadyShots > 0 ? 'assets' : 'storyboard', episode, scope: 'episode' }
}
function buildQaTaskEntry(
  episode: number,
  hasDownstream: boolean,
  qaErrorCount: number,
  qaWorkbenchSummary: TaskCenterQaWorkbenchEpisodeSummary | null,
): TaskCenterEntry {
  if (!hasDownstream) {
    return { id: `task-qa-${episode}`, type: 'QA 修复', target: formatEpisodeLabel(episode), status: 'skipped', progress: '暂无可验收对象', detail: '当前这一集还没有足够的下游产物进入 QA。', retryable: false, actionLabel: '查看 QA 修复', actionTarget: 'qa', episode, scope: 'episode' }
  }
  if (qaWorkbenchSummary) {
    if (qaWorkbenchSummary.openIssueCount > 0 || qaWorkbenchSummary.inProgressCount > 0) {
      return { id: `task-qa-${episode}`, type: 'QA 修复', target: formatEpisodeLabel(episode), status: 'error', progress: `待处理 ${qaWorkbenchSummary.openIssueCount}/${qaWorkbenchSummary.totalIssueCount}`, detail: '当前 QA 仍有开放问题，需要进入修复工作台逐条处理。', statusReason: '检测结果仍有未处理问题', retryable: true, actionLabel: '前往 QA 修复', actionTarget: 'qa', episode, scope: 'episode' }
    }
    return { id: `task-qa-${episode}`, type: 'QA 修复', target: formatEpisodeLabel(episode), status: 'done', progress: `已关闭 ${qaWorkbenchSummary.resolvedCount}/${qaWorkbenchSummary.totalIssueCount}`, detail: '真实 QA 工作台中的问题已经全部关闭，可以继续推进到导出阶段。', retryable: false, actionLabel: '查看 QA 修复', actionTarget: 'qa', episode, scope: 'episode' }
  }
  if (qaErrorCount > 0) {
    return { id: `task-qa-${episode}`, type: 'QA 修复', target: formatEpisodeLabel(episode), status: 'error', progress: `${qaErrorCount} 个问题`, detail: '当前 QA 仍有阻塞项，需要进入修复工作台处理。', statusReason: '检测结果仍有未处理问题', retryable: true, actionLabel: '前往 QA 修复', actionTarget: 'qa', episode, scope: 'episode' }
  }
  return { id: `task-qa-${episode}`, type: 'QA 修复', target: formatEpisodeLabel(episode), status: 'done', progress: '当前通过', detail: '当前没有可见 QA 阻塞，可以继续推进到导出阶段。', retryable: false, actionLabel: '查看 QA 修复', actionTarget: 'qa', episode, scope: 'episode' }
}
function buildBatchPromptTaskEntry(shotsByEpisode: Record<number, StoryboardShotOutput[]>): TaskCenterEntry {
  const episodes = Object.entries(shotsByEpisode)
    .map(([episode, shots]) => ({ episode: Number(episode), shots }))
    .filter((item) => item.episode > 0 && item.shots.length > 0)

  if (episodes.length === 0) {
    return { id: 'task-batch-prompts', type: '批量提示词编译', target: '全项目镜头提示词', status: 'skipped', progress: '暂无可编译镜头', detail: '当前还没有进入正式分镜阶段，因此无需启动批量提示词编译。', statusReason: '没有可执行的镜头范围', retryable: false, actionLabel: '前往镜头工作台', actionTarget: 'storyboard', episode: null, scope: 'global', isBatch: true }
  }
  const readyEpisodeCount = episodes.filter(({ shots }) => shots.every((shot) => hasPromptPair(shot))).length
  const startedEpisodeCount = episodes.filter(({ shots }) => shots.some((shot) => Boolean(shot.visual_prompt_static?.trim()) || Boolean(shot.visual_prompt_motion?.trim()))).length
  const degradedPromptHealth = buildPromptHealthSummary(episodes.flatMap(({ episode, shots }) => shots.map((shot) => ({ ...shot, episode }))), null)
  if (degradedPromptHealth?.degradedShotCount) {
    const hasRecommendedRestore = Boolean(degradedPromptHealth.recommendedRestoreCount && degradedPromptHealth.recommendedRestoreCount > 0)
    const hasManualRepairOnly = Boolean(degradedPromptHealth.manualRepairCount && degradedPromptHealth.manualRepairCount > 0)
    return { id: 'task-batch-prompts', type: '批量提示词编译', target: '全项目镜头提示词', status: 'error', progress: hasRecommendedRestore ? `${degradedPromptHealth.degradedShotCount} 个镜头提示词待恢复` : `${degradedPromptHealth.degradedShotCount} 个镜头仍需人工修复`, detail: hasRecommendedRestore && hasManualRepairOnly ? '全项目已有部分镜头给出推荐恢复版本，但仍有镜头无法一键恢复，需要先完成推荐恢复，再回镜头工作台继续人工修复。' : hasRecommendedRestore ? '全项目已有镜头给出推荐恢复版本，但推荐恢复未必等于完全修好，恢复后仍需继续复核剩余缺失资产。' : '全项目已有部分镜头提示词跑偏，但当前没有更健康的推荐恢复版本，需要先在镜头工作台逐个人工修复。', statusReason: hasRecommendedRestore ? hasManualRepairOnly ? `${degradedPromptHealth.recommendedRestoreCount}/${degradedPromptHealth.degradedShotCount} 个镜头已给出推荐恢复版本，其余镜头需人工修复` : degradedPromptHealth.partialRestoreCount ? `${degradedPromptHealth.partialRestoreCount} 个镜头仅给出部分恢复版本` : `${degradedPromptHealth.recommendedRestoreCount}/${degradedPromptHealth.degradedShotCount} 个镜头已给出推荐恢复版本` : `${degradedPromptHealth.degradedShotCount} 个镜头提示词版本跑偏，当前需人工修复`, retryable: false, actionLabel: hasRecommendedRestore ? '前往首个恢复镜头' : '前往镜头继续修复', actionTarget: 'storyboard', episode: null, scope: 'global', isBatch: true, promptHealth: degradedPromptHealth }
  }
  if (readyEpisodeCount === episodes.length) {
    return { id: 'task-batch-prompts', type: '批量提示词编译', target: '全项目镜头提示词', status: 'done', progress: `已完成 ${readyEpisodeCount}/${episodes.length} 集`, detail: '所有已有镜头的集数都已经具备静态和运动提示词，可以继续批量出图或回看 QA。', retryable: false, actionLabel: '查看镜头工作台', actionTarget: 'storyboard', episode: null, scope: 'global', isBatch: true }
  }
  return { id: 'task-batch-prompts', type: '批量提示词编译', target: '全项目镜头提示词', status: startedEpisodeCount > 0 ? 'running' : 'queued', progress: `已完成 ${readyEpisodeCount}/${episodes.length} 集`, detail: startedEpisodeCount > 0 ? '已有部分集数进入提示词编译，但还没有全量完成，适合继续批量补齐。' : '待启动批量提示词编译，可从这里统一推进全项目镜头 prompt 准备度。', statusReason: `${episodes.length - readyEpisodeCount} 集仍未完成静态 / 运动提示词`, retryable: false, actionLabel: '前往镜头工作台', actionTarget: 'storyboard', episode: null, scope: 'global', isBatch: true }
}
function buildBatchAssetTaskEntry(shotsByEpisode: Record<number, StoryboardShotOutput[]>): TaskCenterEntry {
  const episodes = Object.entries(shotsByEpisode).map(([episode, shots]) => ({ episode: Number(episode), shots })).filter((item) => item.episode > 0 && item.shots.length > 0)
  if (episodes.length === 0) {
    return { id: 'task-batch-assets', type: '批量资产补齐', target: '全项目参考图与分镜图', status: 'skipped', progress: '暂无可补齐镜头', detail: '还没有镜头数据，批量参考图、分镜图和视频任务暂时不会启动。', statusReason: '没有可执行的镜头范围', retryable: false, actionLabel: '前往镜头工作台', actionTarget: 'storyboard', episode: null, scope: 'global', isBatch: true }
  }
  const readyEpisodeCount = episodes.filter(({ shots }) => shots.every((shot) => hasShotReferences(shot) && (shot.assets?.images.length ?? 0) > 0)).length
  const startedEpisodeCount = episodes.filter(({ shots }) => shots.some((shot) => hasShotReferences(shot) || (shot.assets?.images.length ?? 0) > 0 || (shot.assets?.videos.length ?? 0) > 0)).length
  if (readyEpisodeCount === episodes.length) {
    return { id: 'task-batch-assets', type: '批量资产补齐', target: '全项目参考图与分镜图', status: 'done', progress: `已完成 ${readyEpisodeCount}/${episodes.length} 集`, detail: '已有镜头的集数都具备参考资产和分镜图，可以继续向视频、QA 和交付推进。', retryable: false, actionLabel: '查看资产中心', actionTarget: 'assets', episode: null, scope: 'global', isBatch: true }
  }
  return { id: 'task-batch-assets', type: '批量资产补齐', target: '全项目参考图与分镜图', status: startedEpisodeCount > 0 ? 'running' : 'queued', progress: `已完成 ${readyEpisodeCount}/${episodes.length} 集`, detail: startedEpisodeCount > 0 ? '已有部分镜头挂接了参考资产或分镜图，但整体覆盖率还不够，适合继续做批量补齐。' : '镜头已生成，但仍缺少统一参考资产和首帧图产物。', statusReason: `${episodes.length - readyEpisodeCount} 集仍未具备完整参考图 / 分镜图`, retryable: false, actionLabel: startedEpisodeCount > 0 ? '前往资产中心' : '前往镜头工作台', actionTarget: startedEpisodeCount > 0 ? 'assets' : 'storyboard', episode: null, scope: 'global', isBatch: true }
}
function buildBatchQaTaskEntry(
  qaWorkbenchEpisodes: TaskCenterQaWorkbenchEpisodeSummary[],
  qaEntries: QaEntry[],
): TaskCenterEntry {
  if (qaWorkbenchEpisodes.length === 0 && qaEntries.length === 0) {
    return {
      id: 'task-batch-qa',
      type: '批量 QA 调度',
      target: '全项目 QA 修复',
      status: 'skipped',
      progress: '暂无 QA 范围',
      detail: '当前还没有进入正式 QA 范围，因此无需触发批量 QA。',
      retryable: false,
      actionLabel: '前往 QA 修复',
      actionTarget: 'qa',
      episode: null,
      scope: 'global',
      isBatch: true,
    }
  }

  const openEpisodeCount = qaWorkbenchEpisodes.filter((item) => item.openIssueCount > 0 || item.inProgressCount > 0).length
  const totalEpisodeCount = qaWorkbenchEpisodes.length || new Set(qaEntries.map((item) => item.episode)).size

  if (openEpisodeCount > 0) {
    return {
      id: 'task-batch-qa',
      type: '批量 QA 调度',
      target: '全项目 QA 修复',
      status: 'running',
      progress: `待处理 ${openEpisodeCount}/${Math.max(totalEpisodeCount, 1)} 集`,
      detail: '当前仍有开放问题或复检中的集数，适合在 QA 工作台继续闭环。',
      retryable: true,
      actionLabel: '前往 QA 修复',
      actionTarget: 'qa',
      episode: null,
      scope: 'global',
      isBatch: true,
    }
  }

  return {
    id: 'task-batch-qa',
    type: '批量 QA 调度',
    target: '全项目 QA 修复',
    status: 'done',
    progress: `已清空 ${Math.max(totalEpisodeCount, 1)}/${Math.max(totalEpisodeCount, 1)} 集`,
    detail: '真实 QA 工作台中的问题已经全部关闭，当前可继续向导出阶段推进。',
    retryable: false,
    actionLabel: '查看 QA 修复',
    actionTarget: 'qa',
    episode: null,
    scope: 'global',
    isBatch: true,
  }
}
