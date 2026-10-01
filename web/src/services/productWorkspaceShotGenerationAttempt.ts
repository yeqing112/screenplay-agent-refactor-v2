import type { ProductionLaneTarget, ProductionMediaLaneViewModel, ShotStudioViewModel } from '../domain/productionUiV3'
import {
  createGenerationAttempt,
  executeGenerationAttempt,
  previewGenerationAttempt,
  ProductionGenerationAttemptServiceError,
  type GenerationAttemptOperation,
} from './productionGenerationAttempts'

export type ShotGenerationAttemptMutationState = 'idle' | 'confirming' | 'preparing' | 'submitting' | 'refreshing' | 'running' | 'waiting_candidate' | 'candidate_ready' | 'failed' | 'cancelled'

export interface ShotGenerationAttemptMutationSnapshot {
  state: ShotGenerationAttemptMutationState
  operation: GenerationAttemptOperation | null
  shotId: string | null
  target: ProductionLaneTarget | null
  attemptLineageId: string | null
  producedExecutionId: string | null
  message: string
  errorCode: string | null
  status: number | null
}

export interface ShotGenerationAttemptDependencies {
  bookId: number
  getViewModel: (shotId: string) => ShotStudioViewModel | null
  refreshCanonical: () => Promise<void>
  confirmCost?: (operation: GenerationAttemptOperation, target: ProductionLaneTarget, shot: ShotStudioViewModel) => Promise<boolean> | boolean
  isReviewMutationActive?: () => boolean
  isOrdinaryGenerationActive?: () => boolean
  onState?: (snapshot: ShotGenerationAttemptMutationSnapshot) => void
  create?: typeof createGenerationAttempt
  preview?: typeof previewGenerationAttempt
  execute?: typeof executeGenerationAttempt
  randomUUID?: () => string
  maxRefreshAttempts?: number
  refreshDelayMs?: number
  sleep?: (milliseconds: number, signal?: AbortSignal) => Promise<void>
}

export interface ShotGenerationAttemptResult {
  ok: boolean
  state: 'candidate_ready' | 'in_progress' | 'failed' | 'cancelled'
  snapshot: ShotGenerationAttemptMutationSnapshot
}

const ACTIVE_STATES = new Set<ShotGenerationAttemptMutationState>(['confirming', 'preparing', 'submitting', 'refreshing', 'running', 'waiting_candidate'])
const DEFAULT_REFRESH_ATTEMPTS = 3
const DEFAULT_REFRESH_DELAY_MS = 120

function text(value: unknown) { return String(value ?? '').trim() }
function laneFor(shot: ShotStudioViewModel, target: ProductionLaneTarget) { return target === 'IMAGE' ? shot.image : shot.video }
function executionId(lane: ProductionMediaLaneViewModel) { return text(lane.execution.id) }
function candidateId(lane: ProductionMediaLaneViewModel) { return text(lane.execution.raw?.candidate_id) }
function hasCandidate(lane: ProductionMediaLaneViewModel, id: string) {
  if (!id) return false
  return lane.candidate.candidate?.id === id || lane.professional.candidateItems.some((item) => text(item.id) === id)
}
function isAbortError(error: unknown) { return error instanceof DOMException && error.name === 'AbortError' }
function sleepDefault(milliseconds: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException('The operation was aborted.', 'AbortError'))
    const timer = setTimeout(resolve, milliseconds)
    signal?.addEventListener('abort', () => { clearTimeout(timer); reject(new DOMException('The operation was aborted.', 'AbortError')) }, { once: true })
  })
}
function errorDetails(error: unknown) {
  const value = error as { status?: unknown; code?: unknown; message?: unknown }
  const status = Number(value?.status || 0) || null
  return { status, code: text(value?.code) || (status === 409 ? 'GENERATION_ATTEMPT_CONFLICT' : 'GENERATION_ATTEMPT_FAILED'), message: text(value?.message) || '生成操作失败，请重新同步当前镜头。' }
}
function initialSnapshot(): ShotGenerationAttemptMutationSnapshot {
  return { state: 'idle', operation: null, shotId: null, target: null, attemptLineageId: null, producedExecutionId: null, message: '', errorCode: null, status: null }
}

export function createShotStudioGenerationAttemptController(dependencies: ShotGenerationAttemptDependencies) {
  let active = false
  let disposed = false
  let abortController: AbortController | null = null
  let stopRequested = false
  let current = initialSnapshot()

  const emit = (snapshot: ShotGenerationAttemptMutationSnapshot) => { current = snapshot; if (!disposed) dependencies.onState?.(snapshot); return snapshot }
  const fail = (base: Partial<ShotGenerationAttemptMutationSnapshot>, message: string, errorCode: string, status: number | null = null): ShotGenerationAttemptResult => {
    const snapshot = emit({ ...current, ...base, state: 'failed', message, errorCode, status })
    return { ok: false, state: 'failed', snapshot }
  }

  const start = async (operation: GenerationAttemptOperation, shotId: string, target: ProductionLaneTarget): Promise<ShotGenerationAttemptResult> => {
    if (active) return fail({ operation, shotId, target }, '当前已有生成操作进行中，请等待当前操作完成。', 'GENERATION_ATTEMPT_MUTATION_LOCKED')
    const shot = dependencies.getViewModel(shotId)
    if (!shot) return fail({ operation, shotId, target }, '镜头已不在当前 V2 投影中，请重新同步。', 'V3_SHOT_NOT_VISIBLE')
    if (dependencies.isReviewMutationActive?.()) return fail({ operation, shotId, target }, '当前审核操作仍在进行中，请等待审核完成。', 'GENERATION_ATTEMPT_REVIEW_MUTATION_LOCKED')
    if (dependencies.isOrdinaryGenerationActive?.()) return fail({ operation, shotId, target }, '普通生成操作仍在进行中，请等待生成完成。', 'GENERATION_ATTEMPT_GENERATION_MUTATION_LOCKED')
    const lane = laneFor(shot, target)
    const retry = operation === 'RETRY'
    const eligible = retry
      ? lane.state === 'failed' && lane.primaryAction.kind === 'retry_generation' && lane.primaryAction.enabled && lane.execution.rawState === 'FAILED' && Boolean(lane.execution.id)
      : lane.regenerateAction.enabled && lane.state === 'official' && lane.official.isCanonicalOfficial
    if (!eligible) return fail({ operation, shotId, target }, retry ? '当前失败执行已不是可重试状态。' : '当前正式版本不允许生成新版本，请先处理候选或运行中的任务。', retry ? 'GENERATION_ATTEMPT_RETRY_NOT_ELIGIBLE' : 'GENERATION_ATTEMPT_REGENERATE_NOT_ELIGIBLE')
    const sourceExecutionId = retry ? text(lane.execution.id) : ''
    const captured = { shotId, episode: shot.episode, target, sourceExecutionId, failureCode: text(lane.execution.failureCode), state: lane.execution.rawState }
    active = true
    abortController = new AbortController()
    stopRequested = false
    const signal = abortController.signal
    const operationIdempotencyKey = dependencies.randomUUID?.() ?? (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `v3-attempt-${Date.now()}-${Math.random().toString(16).slice(2)}`)
    const base = { operation, shotId, target, attemptLineageId: null, producedExecutionId: null }
    try {
      emit({ ...current, ...base, state: 'confirming', message: retry ? '重试本次生成会保留失败记录，并再次调用外部模型，可能产生费用。\n\n是否继续？' : '生成新版本会保留当前正式版本。\n\n只有新候选审核通过后，才会替换当前正式版本。\n此次操作可能调用外部模型并产生费用。\n\n是否继续？', errorCode: null, status: null })
      if (!(await (dependencies.confirmCost?.(operation, target, shot) ?? (typeof window === 'undefined' ? true : window.confirm(current.message))))) {
        const snapshot = emit({ ...current, ...base, state: 'cancelled', message: '已取消生成操作。', errorCode: 'GENERATION_COST_CONFIRMATION_DECLINED', status: null })
        return { ok: false, state: 'cancelled', snapshot }
      }
      const latestShot = dependencies.getViewModel(shotId)
      const latestLane = latestShot ? laneFor(latestShot, target) : null
      const stillEligible = Boolean(latestShot && latestShot.episode === captured.episode && latestShot.shotId === captured.shotId && !latestShot.stale.isStale && latestLane && (retry
        ? latestLane.state === 'failed' && latestLane.primaryAction.kind === 'retry_generation' && latestLane.primaryAction.enabled && latestLane.execution.rawState === 'FAILED' && latestLane.execution.id === captured.sourceExecutionId
        : latestLane.regenerateAction.enabled && latestLane.state === 'official' && latestLane.official.isCanonicalOfficial))
      if (!stillEligible) return fail(base, '生产状态已经更新，请重新检查当前镜头。', 'ATTEMPT_FRESHNESS_CONFLICT')

      emit({ ...current, ...base, state: 'preparing', message: '正在创建 Attempt Intent…', errorCode: null, status: null })
      const create = dependencies.create ?? createGenerationAttempt
      const created = await create({ bookId: dependencies.bookId, episode: captured.episode, shotId, operation, target, operationIdempotencyKey, sourceExecutionId: retry ? captured.sourceExecutionId : undefined, reason: retry ? `Retry ${captured.failureCode}` : 'Regenerate current official', signal })
      const attemptLineageId = text(created.attempt?.attempt_lineage_id || created.attempt?.attemptLineageId)
      const attemptToken = text(created.attemptConfirmationToken || created.attempt?.confirmation_token || created.attempt?.confirmationToken)
      if (!attemptLineageId || !attemptToken) return fail({ ...base, attemptLineageId }, 'Attempt Intent 响应缺少确认信息。', 'GENERATION_ATTEMPT_CONFIRMATION_MISSING')
      emit({ ...current, ...base, attemptLineageId, state: 'submitting', message: '正在预览 canonical execution…', errorCode: null, status: null })
      const preview = dependencies.preview ?? previewGenerationAttempt
      const previewed = await preview({ bookId: dependencies.bookId, episode: captured.episode, shotId, attemptLineageId, attemptConfirmationToken: attemptToken, signal })
      const producedExecutionId = text(previewed.execution?.execution_id || previewed.execution?.id)
      const executionToken = text(previewed.execution_confirmation_token || previewed.executionConfirmationToken)
      if (!producedExecutionId || !executionToken) return fail({ ...base, attemptLineageId }, 'Attempt Preview 响应缺少 execution 确认信息。', 'GENERATION_ATTEMPT_EXECUTION_CONFIRMATION_MISSING')
      emit({ ...current, ...base, attemptLineageId, producedExecutionId, state: 'submitting', message: '正在提交 canonical execution…', errorCode: null, status: null })
      const execute = dependencies.execute ?? executeGenerationAttempt
      await execute({ bookId: dependencies.bookId, episode: captured.episode, shotId, attemptLineageId, attemptConfirmationToken: attemptToken, previewExecutionId: producedExecutionId, executionConfirmationToken: executionToken, signal })
      if (signal.aborted || stopRequested) {
        const snapshot = emit({ ...current, state: 'running', message: '已停止前台等待；后台生成任务可能仍在运行。', errorCode: null })
        return { ok: true, state: 'in_progress', snapshot }
      }
      const maxAttempts = Math.max(1, dependencies.maxRefreshAttempts ?? DEFAULT_REFRESH_ATTEMPTS)
      const wait = dependencies.sleep ?? sleepDefault
      let lastState: 'running' | 'waiting_candidate' = 'running'
      for (let index = 0; index < maxAttempts; index += 1) {
        emit({ ...current, state: 'refreshing', message: index === 0 ? '正在同步 Production Workspace V2…' : `正在等待 canonical 投影同步（${index + 1}/${maxAttempts}）…`, errorCode: null })
        await dependencies.refreshCanonical()
        if (signal.aborted) {
          const snapshot = emit({ ...current, state: 'running', message: '已停止前台等待；后台生成任务可能仍在运行。', errorCode: null })
          return { ok: true, state: 'in_progress', snapshot }
        }
        const refreshed = dependencies.getViewModel(shotId)
        const refreshedLane = refreshed ? laneFor(refreshed, target) : null
        const latestId = refreshedLane ? executionId(refreshedLane) : ''
        if (latestId && latestId !== producedExecutionId && latestId !== captured.sourceExecutionId) return fail({ attemptLineageId, producedExecutionId }, '当前镜头出现了另一条更新的执行，已停止自动判断。', 'V3_ATTEMPT_EXECUTION_SUPERSEDED')
        if (!refreshedLane || latestId !== producedExecutionId) {
          lastState = 'running'
        } else if (refreshedLane.execution.state === 'failed' || refreshedLane.execution.rawState === 'FAILED') {
          return fail({ attemptLineageId, producedExecutionId }, refreshedLane.detail || 'canonical GenerationExecution 已失败。', text(refreshedLane.execution.failureCode) || 'GENERATION_EXECUTION_FAILED')
        } else if (refreshedLane.execution.isActive || refreshedLane.state === 'running' || (refreshedLane.state === 'waiting' && refreshedLane.execution.state !== 'succeeded')) {
          lastState = 'running'
          emit({ ...current, state: 'running', message: '生成已提交，系统正在处理中。', errorCode: null })
        } else {
          const producedCandidateId = candidateId(refreshedLane)
          const officialCandidateId = text(refreshedLane.official.version?.candidate_id)
          if (producedCandidateId && (hasCandidate(refreshedLane, producedCandidateId) || officialCandidateId === producedCandidateId)) {
            const snapshot = emit({ ...current, state: 'candidate_ready', message: officialCandidateId === producedCandidateId ? '新版本已经在 canonical 状态中生效。' : (operation === 'RETRY' ? '重试已产生新的候选版本，等待人工审核。' : '新候选已生成。当前正式版本仍在使用，批准新候选后才会更新。'), errorCode: null })
            return { ok: true, state: 'candidate_ready', snapshot }
          }
          lastState = 'waiting_candidate'
          emit({ ...current, state: 'waiting_candidate', message: '生成已完成，正在同步候选结果。', errorCode: null })
        }
        if (index < maxAttempts - 1) await wait(Math.max(0, dependencies.refreshDelayMs ?? DEFAULT_REFRESH_DELAY_MS), signal)
      }
      const snapshot = emit({ ...current, state: lastState, message: lastState === 'running' ? '生成任务仍在后台进行；重新进入时会从 Production Workspace V2 恢复。' : '生成已完成，正在同步候选结果。', errorCode: null })
      return { ok: true, state: 'in_progress', snapshot }
    } catch (error) {
      if (isAbortError(error)) {
        if (stopRequested) {
          const snapshot = emit({ ...current, state: current.state === 'waiting_candidate' ? 'waiting_candidate' : 'running', message: '已停止前台等待；后台生成任务可能仍在运行。', errorCode: null, status: null })
          return { ok: true, state: 'in_progress', snapshot }
        }
        const snapshot = emit({ ...current, state: 'cancelled', message: '已停止前台等待。', errorCode: 'GENERATION_ATTEMPT_OBSERVATION_STOPPED', status: null })
        return { ok: false, state: 'cancelled', snapshot }
      }
      const details = errorDetails(error)
      if (details.status === 409) {
        try { await dependencies.refreshCanonical() } catch { /* preserve original conflict */ }
      }
      return fail({}, details.message, details.code, details.status)
    } finally {
      active = false
      abortController = null
    }
  }

  const stopObserving = () => {
    if (!active) return current
    stopRequested = true
    abortController?.abort()
    return emit({ ...current, state: current.state === 'running' ? 'running' : 'waiting_candidate', message: '已停止前台等待；后台生成任务可能仍在运行。', errorCode: null })
  }
  return {
    start,
    retry: (shotId: string, target: ProductionLaneTarget) => start('RETRY', shotId, target),
    regenerate: (shotId: string, target: ProductionLaneTarget) => start('REGENERATE', shotId, target),
    stopObserving,
    dispose: () => { disposed = true; stopRequested = true; abortController?.abort(); active = false },
    isActive: () => active,
    getSnapshot: () => current,
  }
}

export { ProductionGenerationAttemptServiceError }
