import type { ShotStudioViewModel, ProductionMediaLaneViewModel } from '../domain/productionUiV3'
import {
  ProductionGenerationServiceError,
  submitCanonicalProductionGeneration,
  type ProductionGenerationResponse,
  type ProductionGenerationTarget,
  type SubmitProductionGenerationOptions,
} from './productionGeneration'

export type ShotGenerationMutationState =
  | 'idle'
  | 'confirming'
  | 'submitting'
  | 'refreshing'
  | 'running'
  | 'waiting_candidate'
  | 'candidate_ready'
  | 'failed'
  | 'cancelled'

export interface ShotGenerationMutationSnapshot {
  state: ShotGenerationMutationState
  shotId: string | null
  target: ProductionGenerationTarget | null
  message: string
  errorCode: string | null
  status: number | null
  response: ProductionGenerationResponse | null
}

export interface ShotGenerationControllerDependencies {
  bookId: number
  getViewModel: (shotId: string) => ShotStudioViewModel | null
  refreshCanonical: (signal?: AbortSignal) => Promise<void>
  submit?: (options: SubmitProductionGenerationOptions) => Promise<ProductionGenerationResponse>
  confirmCost?: (target: ProductionGenerationTarget, shot: ShotStudioViewModel) => boolean | Promise<boolean>
  onState?: (snapshot: ShotGenerationMutationSnapshot) => void
  isReviewMutationActive?: () => boolean
  sleep?: (milliseconds: number, signal?: AbortSignal) => Promise<void>
  maxRefreshAttempts?: number
  refreshDelayMs?: number
}

export interface ShotGenerationResult {
  ok: boolean
  state: 'candidate_ready' | 'failed' | 'cancelled'
  snapshot: ShotGenerationMutationSnapshot
}

const DEFAULT_REFRESH_ATTEMPTS = 5
const DEFAULT_REFRESH_DELAY_MS = 180

function text(value: unknown) {
  return String(value ?? '').trim()
}

function laneFor(shot: ShotStudioViewModel, target: ProductionGenerationTarget): ProductionMediaLaneViewModel {
  return target === 'IMAGE' ? shot.image : shot.video
}

function errorDetails(error: unknown) {
  const candidate = error as { code?: unknown; status?: unknown; message?: unknown }
  const status = Number(candidate?.status || 0) || null
  return {
    status,
    code: text(candidate?.code) || (status === 409 ? 'GENERATION_CONFLICT' : 'GENERATION_FAILED'),
    message: text(candidate?.message) || '生成请求未完成，请重新同步生产状态。',
  }
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError'
}

function defaultSleep(milliseconds: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('The operation was aborted.', 'AbortError'))
      return
    }
    const timer = setTimeout(resolve, milliseconds)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(new DOMException('The operation was aborted.', 'AbortError'))
    }, { once: true })
  })
}

function initialSnapshot(): ShotGenerationMutationSnapshot {
  return { state: 'idle', shotId: null, target: null, message: '', errorCode: null, status: null, response: null }
}

function sourceIdentity(lane: ProductionMediaLaneViewModel) {
  const source = lane.sourceOfficialImage
  if (!source) return ''
  return [
    source.isCanonicalOfficial,
    source.current,
    source.currentness,
    source.version?.id ?? '',
    source.pointer?.id ?? '',
  ].join('|')
}

function promptIdentity(lane: ProductionMediaLaneViewModel) {
  const prompt = lane.prompt
  return [prompt?.current, prompt?.stale, prompt?.state, prompt?.version ?? ''].join('|')
}

/**
 * Coordinates one canonical Shot Studio generation click. The controller never
 * fabricates running/candidate state: every post-submit state is projected by
 * the read-only Production Workspace V2 refresh.
 */
export function createShotStudioGenerationController(dependencies: ShotGenerationControllerDependencies) {
  let active = false
  let abortController: AbortController | null = null
  let current = initialSnapshot()

  const emit = (next: ShotGenerationMutationSnapshot) => {
    current = next
    dependencies.onState?.(next)
    return next
  }

  const fail = (shotId: string, target: ProductionGenerationTarget, message: string, errorCode: string, status: number | null = null, response: ProductionGenerationResponse | null = null): ShotGenerationResult => {
    const snapshot = emit({ state: 'failed', shotId, target, message, errorCode, status, response })
    return { ok: false, state: 'failed', snapshot }
  }

  const cancel = () => {
    if (!active) return current
    abortController?.abort()
    return emit({ ...current, state: 'cancelled', message: '生成操作已取消。', errorCode: 'GENERATION_CANCELLED' })
  }

  const start = async (shotId: string, target: ProductionGenerationTarget): Promise<ShotGenerationResult> => {
    if (active) return fail(shotId, target, '当前已有生成操作进行中，请等待当前操作完成。', 'GENERATION_MUTATION_LOCKED')
    const shot = dependencies.getViewModel(shotId)
    if (!shot) return fail(shotId, target, '镜头已不在当前 V2 投影中，请重新同步。', 'V3_SHOT_NOT_VISIBLE')
    const lane = laneFor(shot, target)
    const expectedKind = target === 'IMAGE' ? 'generate_image' : 'generate_video'
    if (dependencies.isReviewMutationActive?.()) return fail(shotId, target, '当前审核操作仍在进行中，请等待审核完成。', 'GENERATION_REVIEW_MUTATION_LOCKED')
    if (target === 'VIDEO' && lane.generationMode === 'IMAGE_TO_VIDEO' && !lane.sourceOfficialImage?.isCanonicalOfficial) {
      return fail(shotId, target, 'IMAGE_TO_VIDEO 必须使用当前 canonical official IMAGE。', 'OFFICIAL_IMAGE_REQUIRED')
    }
    if (shot.stale.isStale || ['blocked', 'stale', 'review', 'official'].includes(lane.state) || lane.primaryAction.kind !== expectedKind || lane.primaryAction.lane !== target || !lane.generationAllowed) {
      return fail(shotId, target, '当前镜头状态不允许生成，请先处理阻塞、审核或上游更新。', 'GENERATION_GATE_BLOCKED')
    }
    const modelProfileId = text(lane.professional.model.selected_profile_id)
    if (!modelProfileId) return fail(shotId, target, '生成前必须选择明确的模型配置。', 'PRODUCTION_MODEL_SELECTION_REQUIRED')

    const submissionIdentity = {
      episode: shot.episode,
      generationMode: lane.generationMode,
      modelProfileId,
      prompt: promptIdentity(lane),
      source: sourceIdentity(lane),
    }

    active = true
    abortController = new AbortController()
    const signal = abortController.signal
    try {
      emit({ state: 'confirming', shotId, target, message: '请确认该操作可能调用外部模型并产生费用。', errorCode: null, status: null, response: null })
      const confirmed = await (dependencies.confirmCost?.(target, shot) ?? true)
      if (!confirmed) {
        const snapshot = emit({ state: 'cancelled', shotId, target, message: '已取消生成。', errorCode: 'GENERATION_COST_CONFIRMATION_DECLINED', status: null, response: null })
        return { ok: false, state: 'cancelled', snapshot }
      }
      if (signal.aborted) {
        const snapshot = emit({ state: 'cancelled', shotId, target, message: '生成操作已取消。', errorCode: 'GENERATION_CANCELLED', status: null, response: null })
        return { ok: false, state: 'cancelled', snapshot }
      }

      // The confirmation dialog can remain open while another mutation or a
      // V2 refresh changes the selected shot. Re-read the projection at the
      // exact submission boundary and fail closed if the captured identity is
      // no longer the executable one.
      const latestShot = dependencies.getViewModel(shotId)
      const latestLane = latestShot ? laneFor(latestShot, target) : null
      const latestModelProfileId = latestLane ? text(latestLane.professional.model.selected_profile_id) : ''
      const latestIdentityChanged = !latestShot
        || latestShot.episode !== submissionIdentity.episode
        || latestShot.stale.isStale
        || latestLane?.state !== 'ready'
        || latestLane?.primaryAction.kind !== expectedKind
        || latestLane?.primaryAction.lane !== target
        || !latestLane?.generationAllowed
        || !latestModelProfileId
        || latestModelProfileId !== submissionIdentity.modelProfileId
        || latestLane?.generationMode !== submissionIdentity.generationMode
        || (latestLane ? promptIdentity(latestLane) !== submissionIdentity.prompt : true)
        || (latestLane ? sourceIdentity(latestLane) !== submissionIdentity.source : true)
        || (target === 'VIDEO' && latestLane?.generationMode === 'IMAGE_TO_VIDEO' && !latestLane.sourceOfficialImage?.isCanonicalOfficial)
        || Boolean(dependencies.isReviewMutationActive?.())
      if (latestIdentityChanged) {
        return fail(shotId, target, '生产状态已经更新，请重新确认当前镜头。', 'GENERATION_FRESHNESS_CONFLICT')
      }

      emit({ state: 'submitting', shotId, target, message: '正在提交 canonical 生成请求…', errorCode: null, status: null, response: null })
      const submit = dependencies.submit ?? submitCanonicalProductionGeneration
      const response = await submit({
        bookId: dependencies.bookId,
        episode: latestShot!.episode,
        shotId,
        target,
        modelProfileId: latestModelProfileId,
        generationChain: 'production_workspace_v2',
        signal,
      })
      if (text(response.task_id)) return fail(shotId, target, '当前生成返回了旧版任务协议，V3 无法安全跟踪 canonical production state。', 'V3_LEGACY_GENERATION_TASK_RESPONSE_UNSUPPORTED', null, response)

      const maxAttempts = Math.max(1, dependencies.maxRefreshAttempts ?? DEFAULT_REFRESH_ATTEMPTS)
      const sleep = dependencies.sleep ?? defaultSleep
      const delay = Math.max(0, dependencies.refreshDelayMs ?? DEFAULT_REFRESH_DELAY_MS)
      for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
        emit({ state: 'refreshing', shotId, target, message: attempt === 0 ? '正在同步 Production Workspace V2…' : `正在等待 canonical 投影同步（${attempt + 1}/${maxAttempts}）…`, errorCode: null, status: null, response })
        await dependencies.refreshCanonical(signal)
        if (signal.aborted) {
          const snapshot = emit({ state: 'cancelled', shotId, target, message: '生成操作已取消。', errorCode: 'GENERATION_CANCELLED', status: null, response })
          return { ok: false, state: 'cancelled', snapshot }
        }
        const refreshed = dependencies.getViewModel(shotId)
        const refreshedLane = refreshed ? laneFor(refreshed, target) : null
        if (refreshedLane?.candidate.reviewEligibility || refreshedLane?.official.isCanonicalOfficial) {
          const snapshot = emit({ state: 'candidate_ready', shotId, target, message: refreshedLane.official.isCanonicalOfficial ? '正式媒体已在 canonical 投影中可见。' : '候选已在 canonical 投影中可见，等待人工审核。', errorCode: null, status: null, response })
          return { ok: true, state: 'candidate_ready', snapshot }
        }
        if (refreshedLane?.execution.isActive || refreshedLane?.state === 'running') {
          emit({ state: 'running', shotId, target, message: '生成已提交，系统正在处理中。', errorCode: null, status: null, response })
          if (attempt < maxAttempts - 1) await sleep(delay, signal)
          continue
        }
        if (refreshedLane?.state === 'waiting') {
          emit({ state: 'waiting_candidate', shotId, target, message: '执行已提交，正在等待候选投影出现。', errorCode: null, status: null, response })
          if (attempt < maxAttempts - 1) await sleep(delay, signal)
          continue
        }
        if (attempt < maxAttempts - 1) await sleep(delay, signal)
      }
      return fail(shotId, target, '生成请求已提交，但候选尚未在 V2 投影中出现；请稍后重新同步。', 'V3_EXECUTION_CANDIDATE_NOT_VISIBLE', null, response)
    } catch (error) {
      if (isAbortError(error)) {
        const snapshot = emit({ ...current, state: 'cancelled', shotId, target, message: '生成操作已取消。', errorCode: 'GENERATION_CANCELLED' })
        return { ok: false, state: 'cancelled', snapshot }
      }
      const details = errorDetails(error)
      if ((error instanceof ProductionGenerationServiceError && error.status === 409) || details.status === 409) {
        emit({ state: 'refreshing', shotId, target, message: '检测到生产状态冲突，正在同步 canonical 状态…', errorCode: details.code, status: details.status, response: null })
        try {
          await dependencies.refreshCanonical(signal)
        } catch {
          // Preserve the original 409 as the actionable error.
        }
      }
      return fail(shotId, target, details.message, details.code, details.status)
    } finally {
      active = false
      abortController = null
    }
  }

  return {
    start,
    cancel,
    dispose: () => {
      abortController?.abort()
      active = false
    },
    isActive: () => active,
    getSnapshot: () => current,
  }
}
