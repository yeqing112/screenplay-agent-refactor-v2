import type { StoryboardShotOutput } from '../domain/bookOutputs'
import {
  getStoryboardRecoveryKindLabel,
  type CreativeTaskStatusPayload,
  type PendingStoryboardTask,
  type RecoveryTaskLocalMeta,
} from './productWorkspaceRecovery'
import type { TaskCenterEntry, TaskCenterQaWorkbenchEpisodeSummary, TaskCenterStatus } from './productWorkspaceTasks'

type QaWorkbenchIssue = {
  severity?: string
  fix_status?: string
}

type QaWorkbenchEpisode = {
  episode?: number
  issues?: QaWorkbenchIssue[]
  qa_summary?: {
    open_issue_count?: number
  }
}

export type QaWorkbenchResponse = {
  episodes?: QaWorkbenchEpisode[]
}

function normalizeQaWorkbenchFixStatus(value: string | undefined) {
  return String(value || '').trim().toLowerCase()
}

function isQaWorkbenchIssueResolved(statusValue: string | undefined) {
  const normalized = normalizeQaWorkbenchFixStatus(statusValue)
  return normalized === 'recheck_passed' || normalized === 'resolved' || normalized === 'closed' || normalized === 'accepted'
}

function isQaWorkbenchIssueInProgress(statusValue: string | undefined) {
  const normalized = normalizeQaWorkbenchFixStatus(statusValue)
  return normalized === 'fixing' || normalized === 'fixed' || normalized === 'rechecking' || normalized === 'in_progress'
}

function isQaWorkbenchIssueOpen(statusValue: string | undefined) {
  return !isQaWorkbenchIssueResolved(statusValue) && !isQaWorkbenchIssueInProgress(statusValue)
}

function inferRecoveryKind(kindValue: string | undefined) {
  const normalized = String(kindValue || '').trim().toLowerCase()
  if (normalized === 'reference' || normalized === 'reference-image') return 'reference' as const
  if (normalized === 'image' || normalized === 'frame') return 'frame' as const
  if (normalized === 'prompt' || normalized === 'storyboard-prompt-compile') return 'prompt' as const
  return 'video' as const
}

function isCharacterReferenceRecovery(input: {
  recoveryKind: 'frame' | 'video' | 'reference' | 'prompt'
  shotId: string
  assetScope: string
  inferredAssetId: string
}) {
  if (input.recoveryKind !== 'reference') return false
  if (!input.shotId) return false
  if (input.assetScope === 'character') return true
  return input.inferredAssetId.startsWith('character-')
}

function normalizeTaskStatus(statusValue: string | undefined): TaskCenterStatus {
  const normalized = String(statusValue || '').trim().toLowerCase()
  if (normalized === 'queued') return 'queued'
  if (normalized === 'done') return 'done'
  if (normalized === 'error' || normalized === 'not_found') return 'error'
  return 'running'
}

function buildTaskStatusReason(statusPayload: CreativeTaskStatusPayload | undefined, status: TaskCenterStatus) {
  const externalStatus = String(statusPayload?.external_status || '').trim()
  if (status === 'queued') return '任务已提交，等待 provider 开始执行。'
  if (status === 'error') {
    if (String(statusPayload?.status || '').trim() === 'not_found') {
      return '任务在服务端不存在，可能已过期或丢失。'
    }
    return String(statusPayload?.error || '任务在恢复链路中失败。')
  }
  if (externalStatus) return `provider 状态：${externalStatus}`
  return '任务仍在 provider 侧执行，等待继续回收结果。'
}

function buildTaskProgress(statusPayload: CreativeTaskStatusPayload | undefined, status: TaskCenterStatus) {
  const progressValue = Number(statusPayload?.progress ?? 0)
  if (progressValue > 0) return `${progressValue}%`
  if (status === 'queued') return '等待 provider 执行'
  if (status === 'done') return '已回收完成'
  if (status === 'error') return '回收失败'
  return '待回收'
}

function buildReferenceImages(items: unknown) {
  if (!Array.isArray(items)) return []
  return items
    .map((item) => {
      if (!item || typeof item !== 'object') return null
      const record = item as Record<string, unknown>
      const imageUrl = String(record.image_url || record.imageUrl || '').trim()
      if (!imageUrl) return null
      return {
        referenceAssetId: String(record.reference_asset_id || record.referenceAssetId || '').trim() || undefined,
        imageUrl,
        title: String(record.title || record.asset_name || record.assetName || record.reference_token || '').trim() || undefined,
      }
    })
    .filter((item): item is NonNullable<typeof item> => Boolean(item))
}

function describeGenerationChain(generationChain: string) {
  if (generationChain === 'recompile_then_video') return '重编后继续生成视频'
  if (generationChain === 'recompile_then_frame') return '重编后生成首帧'
  if (generationChain === 'canvas_recovery_continue_after_frame') return '恢复后继续生成视频'
  if (generationChain === 'canvas_recovery_continue_after_prompt') return '恢复后继续生成首帧/视频'
  if (generationChain === 'canvas_recovery_recompile_then_video') return '恢复后重编再继续生成视频'
  if (generationChain === 'canvas_recovery_recompile_then_frame') return '恢复后重编再生成首帧'
  if (generationChain === 'task_center_regenerate_latest_video') return '按最新镜头状态重生成视频'
  if (generationChain === 'task_center_regenerate_latest_frame') return '按最新镜头状态重生成首帧'
  return generationChain
}

export function buildQaWorkbenchSummary(payload: QaWorkbenchResponse): TaskCenterQaWorkbenchEpisodeSummary[] {
  return (payload.episodes ?? [])
    .map((episode) => {
      const issues = episode.issues ?? []
      const openIssues = issues.filter((item) => isQaWorkbenchIssueOpen(item.fix_status))
      const inProgressIssues = issues.filter((item) => isQaWorkbenchIssueInProgress(item.fix_status))
      const resolvedIssues = issues.filter((item) => isQaWorkbenchIssueResolved(item.fix_status))
      return {
        episode: Number(episode.episode ?? 0),
        totalIssueCount: issues.length,
        openIssueCount: Number(episode.qa_summary?.open_issue_count ?? openIssues.length),
        highOpenIssueCount: openIssues.filter((item) => String(item.severity || '').toLowerCase() === 'high').length,
        inProgressCount: inProgressIssues.length,
        resolvedCount: resolvedIssues.length,
      }
    })
    .filter((item) => item.episode > 0)
}

export function buildRecoveryTaskEntries(
  pendingTasks: PendingStoryboardTask[],
  taskStatuses: Record<string, CreativeTaskStatusPayload>,
  creativeTasks: CreativeTaskStatusPayload[],
  recoveryTaskMetaById: Record<string, RecoveryTaskLocalMeta>,
  shotsByEpisode: Record<number, StoryboardShotOutput[]>,
): TaskCenterEntry[] {
  const pendingByTaskId = new Map(pendingTasks.map((task) => [task.taskId, task] as const))
  const creativeTaskById = new Map(
    creativeTasks
      .map((task) => [String(task.task_id || '').trim(), task] as const)
      .filter(([taskId]) => Boolean(taskId)),
  )
  const taskIds = new Set<string>([
    ...pendingTasks.map((task) => task.taskId),
    ...Array.from(creativeTaskById.keys()),
  ])

  return Array.from(taskIds)
    .map((taskId) => {
      const pendingTask = pendingByTaskId.get(taskId)
      const creativeTask = creativeTaskById.get(taskId)
      const statusPayload = taskStatuses[taskId] ?? creativeTask ?? undefined
      const recoveryKind = inferRecoveryKind(
        pendingTask?.kind || String(statusPayload?.kind || statusPayload?.target_kind || ''),
      )
      const episode = Number(pendingTask?.episode ?? statusPayload?.episode ?? 0)
      const shotId = String(pendingTask?.shotId ?? statusPayload?.shot_id ?? '').trim()
      const shot =
        (shotsByEpisode[episode] ?? []).find((item) => String(item.shot_id) === shotId) ?? null
      const requestPayload =
        statusPayload?.request_payload && typeof statusPayload.request_payload === 'object'
          ? statusPayload.request_payload
          : {}
      const firstFrameAssetId = String(
        statusPayload?.first_frame_asset_id ||
          requestPayload.first_frame_asset_id ||
          requestPayload.firstFrameAssetId ||
          '',
      ).trim()
      const firstFrameUrl = String(
        statusPayload?.first_frame_url ||
          requestPayload.first_frame_url ||
          requestPayload.firstFrameUrl ||
          '',
      ).trim()
      const referenceAssetIds = Array.isArray(statusPayload?.reference_asset_ids)
        ? statusPayload.reference_asset_ids
        : Array.isArray(requestPayload.reference_asset_ids)
          ? requestPayload.reference_asset_ids.map((item) => String(item || '').trim()).filter(Boolean)
          : []
      const referenceImages = buildReferenceImages(
        Array.isArray(statusPayload?.reference_images) ? statusPayload.reference_images : requestPayload.reference_images,
      )
      const rawTaskPromptVersion =
        statusPayload?.prompt_version ??
        requestPayload.prompt_version ??
        requestPayload.promptVersion
      const taskPromptVersion =
        typeof rawTaskPromptVersion === 'number'
          ? rawTaskPromptVersion
          : typeof rawTaskPromptVersion === 'string' && rawTaskPromptVersion.trim()
            ? Number(rawTaskPromptVersion)
            : null
      const currentShotPromptVersion =
        typeof shot?.prompt_version === 'number'
          ? shot.prompt_version
          : typeof shot?.prompt_version === 'string' && String(shot.prompt_version).trim()
            ? Number(shot.prompt_version)
            : null
      const assetScope = String(requestPayload.asset_scope || requestPayload.assetScope || '').trim()
      const assetSubject = String(requestPayload.asset_subject || requestPayload.assetSubject || '').trim()
      const sourceAssetId = String(requestPayload.source_asset_id || requestPayload.sourceAssetId || '').trim()
      const inferredAssetId =
        pendingTask?.assetId ||
        (assetScope && sourceAssetId ? `${assetScope === 'scene' ? 'location' : assetScope}-${sourceAssetId}` : '')
      const status = normalizeTaskStatus(statusPayload?.status)
      const providerTaskMode = String(
        statusPayload?.provider_task_mode ||
          requestPayload.provider_task_mode ||
          requestPayload.providerTaskMode ||
          (firstFrameAssetId ? 'image_to_video' : referenceAssetIds.length > 0 ? 'reference_to_video' : 'text_to_video') ||
          '',
      ).trim()
      const generationChain = String(
        statusPayload?.generation_chain ||
          requestPayload.generation_chain ||
          requestPayload.generationChain ||
          '',
      ).trim()
      const promptRecompileReason = String(
        statusPayload?.prompt_recompile_reason ||
          requestPayload.prompt_recompile_reason ||
          requestPayload.promptRecompileReason ||
          '',
      ).trim()
      const promptRecompileTaskId = String(
        statusPayload?.prompt_recompile_task_id ||
          requestPayload.prompt_recompile_task_id ||
          requestPayload.promptRecompileTaskId ||
          '',
      ).trim()
      const rawPromptRecompileVersion =
        statusPayload?.prompt_recompile_version ??
        requestPayload.prompt_recompile_version ??
        requestPayload.promptRecompileVersion
      const promptRecompileVersion =
        typeof rawPromptRecompileVersion === 'number'
          ? rawPromptRecompileVersion
          : typeof rawPromptRecompileVersion === 'string' && rawPromptRecompileVersion.trim()
            ? Number(rawPromptRecompileVersion)
            : null
      const effectiveTaskPromptVersion =
        Number.isFinite(taskPromptVersion)
          ? taskPromptVersion
          : Number.isFinite(promptRecompileVersion)
            ? promptRecompileVersion
            : null
      const promptVersionDrift =
        Number.isFinite(effectiveTaskPromptVersion) && Number.isFinite(currentShotPromptVersion)
          ? Number(currentShotPromptVersion) - Number(effectiveTaskPromptVersion)
          : null
      const triggeredByPromptRecompile =
        Boolean(statusPayload?.triggered_by_prompt_recompile) ||
        Boolean(requestPayload.triggered_by_prompt_recompile) ||
        Boolean(requestPayload.triggeredByPromptRecompile)
      const persistedRestartedFromTaskId = String(statusPayload?.restarted_from_task_id || '').trim()
      const persistedLastRestartedAt = String(statusPayload?.last_restarted_at || '').trim()
      const actionTarget = recoveryKind === 'reference' ? 'assets' : 'storyboard'
      const isCharacterShotVariantRecovery = isCharacterReferenceRecovery({
        recoveryKind,
        shotId,
        assetScope,
        inferredAssetId,
      })
      const actionLabel =
        recoveryKind === 'reference'
          ? isCharacterShotVariantRecovery
            ? '前往资产中心补人物分镜精调'
            : '前往资产中心'
          : '前往镜头工作台'
      const detail =
        status === 'error'
          ? `任务 ${taskId} 当前无法继续自动回收，建议检查版本状态，或直接从任务中心重新发起。`
          : triggeredByPromptRecompile && generationChain
            ? `任务 ${taskId} 来自“${describeGenerationChain(generationChain)}”链路，可在任务中心追溯本次生成所使用的重编任务与提示词版本。`
            : generationChain.startsWith('task_center_regenerate_latest_')
              ? `任务 ${taskId} 来自“${describeGenerationChain(generationChain)}”链路，本次生成直接采用了镜头当前状态下的提示词版本、首帧与静态参考图。`
            : recoveryKind === 'reference'
              ? isCharacterShotVariantRecovery
                ? `任务 ${taskId} 已进入人物分镜精调参考图的恢复链路，回到资产中心后会直接定位当前镜头对应的人物精调版本。`
              : `任务 ${taskId} 已进入参考图恢复链路，可继续查询状态并回收结果。`
            : `任务 ${taskId} 已进入真实创意任务恢复链路，可继续查询状态并回收结果。`

      return {
        id: `task-recovery-${taskId}`,
        type: `${getStoryboardRecoveryKindLabel(recoveryKind)}结果回收`,
        target:
          recoveryKind === 'reference'
            ? `第 ${episode} 集 · ${pendingTask?.assetLabel || assetSubject || shotId || taskId}`
            : `第 ${episode} 集 · ${shotId}${shot?.scene_name ? ` · ${shot.scene_name}` : ''}`,
        status,
        progress: buildTaskProgress(statusPayload, status),
        detail,
        statusReason: buildTaskStatusReason(statusPayload, status),
        retryable: true,
        actionLabel,
        actionTarget,
        episode: episode || null,
        scope: 'episode',
        taskId,
        shotId,
        assetId: inferredAssetId || undefined,
        recoveryKind,
        recoveryMeta: {
          restartedFromTaskId:
            pendingTask?.restartedFromTaskId ??
            (persistedRestartedFromTaskId || undefined) ??
            recoveryTaskMetaById[taskId]?.restartedFromTaskId,
          restartCount:
            pendingTask?.restartCount ??
            (typeof statusPayload?.restart_count === 'number' ? statusPayload.restart_count : undefined) ??
            recoveryTaskMetaById[taskId]?.restartCount,
          lastRestartedAt:
            pendingTask?.lastRestartedAt ??
            (persistedLastRestartedAt || undefined) ??
            recoveryTaskMetaById[taskId]?.lastRestartedAt,
        },
        creativeTaskMeta: {
          modelProfileId: String(statusPayload?.model_profile_id || '').trim() || undefined,
          provider: String(statusPayload?.provider || '').trim() || undefined,
          externalTaskId: statusPayload?.external_task_id ?? null,
          externalStatus: statusPayload?.external_status ?? null,
          generationChain: generationChain || undefined,
          triggeredByPromptRecompile,
          promptRecompileReason: promptRecompileReason || undefined,
          promptRecompileTaskId: promptRecompileTaskId || undefined,
          promptRecompileVersion: Number.isFinite(promptRecompileVersion) ? promptRecompileVersion : null,
          taskPromptVersion: Number.isFinite(effectiveTaskPromptVersion) ? effectiveTaskPromptVersion : null,
          currentShotPromptVersion: Number.isFinite(currentShotPromptVersion) ? currentShotPromptVersion : null,
          promptVersionDrift: Number.isFinite(promptVersionDrift) ? promptVersionDrift : null,
          firstFrameAssetId: firstFrameAssetId || undefined,
          firstFrameUrl: firstFrameUrl || undefined,
          providerTaskMode: providerTaskMode || undefined,
          referenceAssetIds,
          assetScope: assetScope || undefined,
          assetSubject: assetSubject || pendingTask?.assetLabel || undefined,
          sourceAssetId: sourceAssetId || undefined,
          referenceImages,
        },
      } satisfies TaskCenterEntry
    })
    .sort((left, right) => {
      if ((left.episode ?? 0) !== (right.episode ?? 0)) return (left.episode ?? 0) - (right.episode ?? 0)
      return left.target.localeCompare(right.target, 'zh-CN')
    })
}
