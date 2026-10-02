import type { ProductionWorkspaceServiceError } from './productionWorkspace'
import type { ProductionLaneTarget, ShotStudioViewModel } from '../domain/productionUiV3'

export type ShotReviewMutationState =
  | 'idle'
  | 'confirming'
  | 'validating'
  | 'promoting'
  | 'refreshing'
  | 'confirmed'
  | 'failed'

export interface ShotReviewCandidateIdentity {
  shotId: string
  lane: ProductionLaneTarget
  candidateId: string
  validationId: string | null
}

export interface ShotReviewMutationSnapshot {
  state: ShotReviewMutationState
  identity: ShotReviewCandidateIdentity | null
  message: string
  errorCode: string | null
}

export interface ShotReviewMutationDependencies {
  getViewModel: (shotId: string) => ShotStudioViewModel | null
  validateCandidate: (candidateId: string) => Promise<unknown>
  promoteCandidate: (candidateId: string, validationId: string) => Promise<unknown>
  refreshCanonical: () => Promise<void>
  onState?: (snapshot: ShotReviewMutationSnapshot) => void
  sleep?: (milliseconds: number, signal?: AbortSignal) => Promise<void>
  maxRefreshAttempts?: number
  refreshDelayMs?: number
  signal?: AbortSignal
}

export interface ShotReviewMutationResult {
  ok: boolean
  state: 'confirmed' | 'failed'
  identity: ShotReviewCandidateIdentity
  message: string
  errorCode: string | null
}

const DEFAULT_REFRESH_ATTEMPTS = 3
const DEFAULT_REFRESH_DELAY_MS = 120

function text(value: unknown) {
  return String(value ?? '').trim()
}

function validationIdFromResponse(response: unknown) {
  if (!response || typeof response !== 'object') return ''
  const payload = response as { validation_id?: unknown; validation?: { validation_id?: unknown } }
  return text(payload.validation_id || payload.validation?.validation_id)
}

function errorDetails(error: unknown) {
  const candidate = error as Partial<ProductionWorkspaceServiceError> & { code?: unknown; status?: unknown; message?: unknown }
  const status = Number(candidate?.status || 0)
  const code = text(candidate?.code) || (status === 409 ? 'MEDIA_REVIEW_CONFLICT' : null)
  const message = text(candidate?.message) || '候选审核操作失败，请重新同步生产状态。'
  return { code, message, status }
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function isReviewCandidateCurrent(view: ShotStudioViewModel | null, identity: ShotReviewCandidateIdentity) {
  if (!view || view.shotId !== identity.shotId || view.stale.isStale) return false
  const lane = identity.lane === 'IMAGE' ? view.image : view.video
  const candidate = lane.candidate.candidate
  // Review eligibility belongs to the selected media lane. Shot-level
  // blockers may coexist with a valid candidate and must not prevent the
  // explicit human validation/promotion path from running.
  if (!lane.candidate.reviewEligibility || !candidate) return false
  if (text(candidate.id) !== identity.candidateId) return false
  // A current Official may coexist with a newer candidate during review.
  // Only malformed Official evidence must fail closed here.  The candidate
  // that already backs the current Official remains non-reviewable below.
  if (lane.official.reasonCodes.length > 0) return false
  if (text(candidate.id) === text(lane.official.version?.candidate_id)) return false
  return true
}

export function isCanonicalConfirmationCurrent(view: ShotStudioViewModel | null, identity: ShotReviewCandidateIdentity) {
  if (!view || view.shotId !== identity.shotId) return false
  const lane = identity.lane === 'IMAGE' ? view.image : view.video
  return lane.official.isCanonicalOfficial && text(lane.official.version?.candidate_id) === identity.candidateId
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

export function createShotStudioMediaReviewController(dependencies: ShotReviewMutationDependencies) {
  let active = false

  const emit = (snapshot: ShotReviewMutationSnapshot) => {
    dependencies.onState?.(snapshot)
    return snapshot
  }

  const fail = (identity: ShotReviewCandidateIdentity, message: string, errorCode: string | null = null): ShotReviewMutationResult => {
    emit({ state: 'failed', identity, message, errorCode })
    return { ok: false, state: 'failed', identity, message, errorCode }
  }

  const approve = async (identity: ShotReviewCandidateIdentity): Promise<ShotReviewMutationResult> => {
    if (active) return fail(identity, '当前已有审核操作进行中，请等待当前操作完成。', 'MEDIA_REVIEW_MUTATION_LOCKED')
    active = true
    const signal = dependencies.signal
    try {
      emit({ state: 'confirming', identity, message: '正在确认当前候选状态…', errorCode: null })
      if (signal?.aborted) return fail(identity, '审核操作已取消。', 'MEDIA_REVIEW_ABORTED')
      if (!isReviewCandidateCurrent(dependencies.getViewModel(identity.shotId), identity)) {
        return fail(identity, '生产状态已经更新，请重新检查当前候选。', 'MEDIA_REVIEW_STALE_CANDIDATE')
      }

      let validationId = text(identity.validationId)
      if (!validationId) {
        emit({ state: 'validating', identity, message: '正在建立候选验证记录…', errorCode: null })
        const validation = await dependencies.validateCandidate(identity.candidateId)
        validationId = validationIdFromResponse(validation)
        if (!validationId) return fail(identity, '当前候选缺少可用于正式确认的验证记录。', 'MEDIA_VALIDATION_ID_MISSING')
      }

      if (!isReviewCandidateCurrent(dependencies.getViewModel(identity.shotId), { ...identity, validationId })) {
        return fail({ ...identity, validationId }, '生产状态已经更新，请重新检查当前候选。', 'MEDIA_REVIEW_STALE_CANDIDATE')
      }

      const resolvedIdentity = { ...identity, validationId }
      emit({ state: 'promoting', identity: resolvedIdentity, message: '正在建立正式版本…', errorCode: null })
      try {
        await dependencies.promoteCandidate(identity.candidateId, validationId)
      } catch (error) {
        const details = errorDetails(error)
        if (details.status !== 409 && details.code !== 'MEDIA_PROMOTION_STALE' && details.code !== 'MEDIA_PROMOTION_CONFLICT') {
          return fail(resolvedIdentity, details.message, details.code)
        }
        emit({ state: 'refreshing', identity: resolvedIdentity, message: '检测到生产状态冲突，正在同步 canonical 状态…', errorCode: details.code })
        try {
          await dependencies.refreshCanonical()
        } catch (refreshError) {
          const refreshDetails = errorDetails(refreshError)
          return fail(resolvedIdentity, refreshDetails.message, refreshDetails.code || details.code)
        }
        if (isCanonicalConfirmationCurrent(dependencies.getViewModel(resolvedIdentity.shotId), resolvedIdentity)) {
          const message = '正式状态已更新。'
          emit({ state: 'confirmed', identity: resolvedIdentity, message, errorCode: null })
          return { ok: true, state: 'confirmed', identity: resolvedIdentity, message, errorCode: null }
        }
        return fail(resolvedIdentity, '生产状态存在冲突，请重新同步并检查当前候选。', details.code)
      }

      const maxAttempts = Math.max(1, dependencies.maxRefreshAttempts ?? DEFAULT_REFRESH_ATTEMPTS)
      const sleep = dependencies.sleep ?? defaultSleep
      const refreshDelayMs = Math.max(0, dependencies.refreshDelayMs ?? DEFAULT_REFRESH_DELAY_MS)
      for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
        emit({ state: 'refreshing', identity: resolvedIdentity, message: attempt === 0 ? '正在同步正式状态…' : `正在等待正式状态同步（${attempt + 1}/${maxAttempts}）…`, errorCode: null })
        await dependencies.refreshCanonical()
        await sleep(25, signal)
        if (isCanonicalConfirmationCurrent(dependencies.getViewModel(resolvedIdentity.shotId), resolvedIdentity)) {
          const message = '已建立正式版本。'
          emit({ state: 'confirmed', identity: resolvedIdentity, message, errorCode: null })
          return { ok: true, state: 'confirmed', identity: resolvedIdentity, message, errorCode: null }
        }
        if (attempt < maxAttempts - 1) await sleep(refreshDelayMs, signal)
      }
      return fail(resolvedIdentity, '确认请求已完成，但正式状态尚未同步。请重新同步生产状态。', 'MEDIA_CANONICAL_CONFIRMATION_PENDING')
    } catch (error) {
      if (isAbortError(error)) return fail(identity, '审核操作已取消。', 'MEDIA_REVIEW_ABORTED')
      const details = errorDetails(error)
      return fail(identity, details.message, details.code)
    } finally {
      active = false
    }
  }

  return { approve, isActive: () => active }
}
