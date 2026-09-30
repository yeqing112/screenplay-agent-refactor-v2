import { describe, expect, it, vi } from 'vitest'
import { toShotStudioViewModels, type ShotStudioViewModel } from '../domain/productionUiV3'
import { createProductionWorkspaceV2OfficialCandidateCoexistenceFixture, createProductionWorkspaceV2ReviewFixture } from '../fixtures/productionWorkspaceV2'
import {
  createShotStudioMediaReviewController,
  isCanonicalConfirmationCurrent,
  isReviewCandidateCurrent,
  type ShotReviewCandidateIdentity,
  type ShotReviewMutationSnapshot,
} from './productWorkspaceShotReview'

function reviewView(lane: 'IMAGE' | 'VIDEO' = 'IMAGE', promoted = false) {
  return toShotStudioViewModels([createProductionWorkspaceV2ReviewFixture({ lane, promoted }).shots[0]])[0]
}

function identityFor(view: ShotStudioViewModel, lane: 'IMAGE' | 'VIDEO' = 'IMAGE'): ShotReviewCandidateIdentity {
  const target = lane === 'IMAGE' ? view.image : view.video
  const candidate = target.candidate.candidate
  if (!candidate) throw new Error('fixture candidate missing')
  return { shotId: view.shotId, lane, candidateId: candidate.id, validationId: candidate.technical_validation.validation_id }
}

function setup(options: { lane?: 'IMAGE' | 'VIDEO'; validationId?: string | null; maxRefreshAttempts?: number } = {}) {
  const lane = options.lane ?? 'IMAGE'
  let current = reviewView(lane)
  const validate = vi.fn(async () => ({ validation: { validation_id: options.validationId || `validated-${lane.toLowerCase()}` } }))
  const promote = vi.fn(async () => ({ official_media_version_id: 'omv-fixture' }))
  const refresh = vi.fn(async () => { current = reviewView(lane, true) })
  const states: ShotReviewMutationSnapshot[] = []
  const controller = createShotStudioMediaReviewController({
    getViewModel: () => current,
    validateCandidate: validate,
    promoteCandidate: promote,
    refreshCanonical: refresh,
    onState: (state) => states.push(state),
    sleep: async () => undefined,
    maxRefreshAttempts: options.maxRefreshAttempts ?? 2,
    refreshDelayMs: 0,
  })
  return { lane, current: () => current, setCurrent: (next: ShotStudioViewModel) => { current = next }, validate, promote, refresh, states, controller }
}

describe('Shot Studio media review mutation controller', () => {
  it('approves IMAGE with an existing validation id, then confirms from canonical V2', async () => {
    const harness = setup()
    const identity = identityFor(harness.current())
    const result = await harness.controller.approve(identity)
    expect(result).toMatchObject({ ok: true, state: 'confirmed' })
    expect(harness.validate).not.toHaveBeenCalled()
    expect(harness.promote).toHaveBeenCalledOnce()
    expect(harness.promote).toHaveBeenCalledWith(identity.candidateId, identity.validationId)
    expect(harness.refresh).toHaveBeenCalledOnce()
    expect(harness.states.map((state) => state.state)).toEqual(['confirming', 'promoting', 'refreshing', 'confirmed'])
  })

  it('validates first when validation_id is missing and fails closed if the contract returns none', async () => {
    const harness = setup({ validationId: null })
    const identity = { ...identityFor(harness.current()), validationId: null }
    harness.validate.mockResolvedValueOnce({ validation: {} } as unknown as { validation: { validation_id: string } })
    const result = await harness.controller.approve(identity)
    expect(result).toMatchObject({ ok: false, errorCode: 'MEDIA_VALIDATION_ID_MISSING' })
    expect(harness.validate).toHaveBeenCalledOnce()
    expect(harness.promote).not.toHaveBeenCalled()
  })

  it('uses the validation response before promotion when validation_id is missing', async () => {
    const harness = setup({ validationId: null })
    const identity = { ...identityFor(harness.current()), validationId: null }
    const result = await harness.controller.approve(identity)
    expect(result.ok).toBe(true)
    expect(harness.validate).toHaveBeenCalledOnce()
    expect(harness.promote).toHaveBeenCalledWith(identity.candidateId, 'validated-image')
  })

  it('locks double submit and calls promotion exactly once', async () => {
    const harness = setup()
    const identity = identityFor(harness.current())
    let resolvePromotion: (() => void) | undefined
    harness.promote.mockImplementationOnce(() => new Promise((resolve) => { resolvePromotion = () => resolve({ official_media_version_id: 'omv-double-submit' }) }))
    const first = harness.controller.approve(identity)
    const second = await harness.controller.approve(identity)
    expect(second).toMatchObject({ ok: false, errorCode: 'MEDIA_REVIEW_MUTATION_LOCKED' })
    ;(resolvePromotion as (() => void) | undefined)?.()
    await first
    expect(harness.promote).toHaveBeenCalledOnce()
  })

  it('does not set official after POST success when canonical refresh still lacks the pointer', async () => {
    const harness = setup({ maxRefreshAttempts: 2 })
    const identity = identityFor(harness.current())
    harness.refresh.mockResolvedValue(undefined)
    const result = await harness.controller.approve(identity)
    expect(result).toMatchObject({ ok: false, errorCode: 'MEDIA_CANONICAL_CONFIRMATION_PENDING' })
    expect(result.message).toContain('正式状态尚未同步')
    expect(harness.promote).toHaveBeenCalledOnce()
    expect(isCanonicalConfirmationCurrent(harness.current(), identity)).toBe(false)
  })

  it('keeps the candidate visible when promotion fails', async () => {
    const harness = setup()
    const identity = identityFor(harness.current())
    harness.promote.mockRejectedValueOnce(new Error('promotion rejected'))
    const result = await harness.controller.approve(identity)
    expect(result).toMatchObject({ ok: false, state: 'failed' })
    expect(result.message).toContain('promotion rejected')
    expect(harness.current().image.candidate.candidate?.id).toBe(identity.candidateId)
    expect(harness.current().image.official.isCanonicalOfficial).toBe(false)
  })

  it('resolves a 409 conflict from canonical state without retrying POST', async () => {
    const harness = setup()
    const identity = identityFor(harness.current())
    harness.promote.mockRejectedValueOnce({ status: 409, code: 'MEDIA_PROMOTION_CONFLICT', message: 'pointer changed' })
    const result = await harness.controller.approve(identity)
    expect(result).toMatchObject({ ok: true, state: 'confirmed' })
    expect(harness.promote).toHaveBeenCalledOnce()
    expect(harness.refresh).toHaveBeenCalledOnce()
  })

  it('rejects stale candidates before any validation or promotion call', async () => {
    const harness = setup()
    const identity = identityFor(harness.current())
    harness.setCurrent({ ...reviewView('IMAGE'), stale: { isStale: true, reasonCodes: ['PROMPT_IR_STALE'] } })
    const result = await harness.controller.approve(identity)
    expect(result).toMatchObject({ ok: false, errorCode: 'MEDIA_REVIEW_STALE_CANDIDATE' })
    expect(harness.validate).not.toHaveBeenCalled()
    expect(harness.promote).not.toHaveBeenCalled()
  })

  it('rejects a canonical contradiction before any promotion call', async () => {
    const harness = setup()
    const identity = identityFor(harness.current())
    harness.setCurrent(reviewView('IMAGE', true))
    const result = await harness.controller.approve(identity)
    expect(result).toMatchObject({ ok: false, errorCode: 'MEDIA_REVIEW_STALE_CANDIDATE' })
    expect(harness.promote).not.toHaveBeenCalled()
  })

  it('re-resolves IMAGE approval to VIDEO generation as a read-only next action', async () => {
    const harness = setup({ lane: 'IMAGE' })
    const identity = identityFor(harness.current(), 'IMAGE')
    const result = await harness.controller.approve(identity)
    expect(result.ok).toBe(true)
    const after = harness.current()
    expect(after.image.official.isCanonicalOfficial).toBe(true)
    expect(after.video.state).toBe('ready')
    expect(after.primaryAction.kind).toBe('generate_video')
    expect(after.primaryAction.enabled).toBe(true)
    expect(after.primaryAction.requiresProviderCall).toBe(true)
  })

  it('re-resolves VIDEO approval to an official shot without invoking a provider', async () => {
    const harness = setup({ lane: 'VIDEO' })
    const identity = identityFor(harness.current(), 'VIDEO')
    const result = await harness.controller.approve(identity)
    expect(result.ok).toBe(true)
    const after = harness.current()
    expect(after.video.official.isCanonicalOfficial).toBe(true)
    expect(after.state).toBe('official')
    expect(after.primaryAction.kind).toBe('view_official')
    expect(after.primaryAction.requiresProviderCall).toBe(false)
  })

  it('keeps REVIEW_REQUIRED and TECHNICALLY_VALID inside the backend review contract', () => {
    const view = reviewView()
    expect(view.image.candidate.validationStatus).toBe('TECHNICALLY_VALID')
    expect(view.image.candidate.reviewEligibility).toBe(true)
    expect(isReviewCandidateCurrent(view, identityFor(view))).toBe(true)
  })

  it('allows a newer candidate to enter review while an older Official remains current', () => {
    const view = toShotStudioViewModels([createProductionWorkspaceV2OfficialCandidateCoexistenceFixture().shots[0]])[0]
    const candidate = view.image.candidate.candidate
    expect(view.image.state).toBe('review')
    expect(view.image.primaryAction.kind).toBe('review_candidate')
    expect(view.image.official.version?.candidate_id).toBe('fixture-candidate-c1')
    expect(candidate?.id).toBe('fixture-candidate-c2')
    expect(isReviewCandidateCurrent(view, { shotId: view.shotId, lane: 'IMAGE', candidateId: 'fixture-candidate-c2', validationId: 'fixture-validation-c2' })).toBe(true)
    expect(isReviewCandidateCurrent(view, { shotId: view.shotId, lane: 'IMAGE', candidateId: 'fixture-candidate-c1', validationId: 'fixture-validation-image' })).toBe(false)
  })

  it('fails closed when the Official pointer is broken even with a valid candidate', () => {
    const snapshot = createProductionWorkspaceV2OfficialCandidateCoexistenceFixture()
    snapshot.shots[0].IMAGE.official = { ...snapshot.shots[0].IMAGE.official, current: true, pointer: null }
    const view = toShotStudioViewModels([snapshot.shots[0]])[0]
    expect(view.image.official.reasonCodes.length).toBeGreaterThan(0)
    expect(isReviewCandidateCurrent(view, { shotId: view.shotId, lane: 'IMAGE', candidateId: 'fixture-candidate-c2', validationId: 'fixture-validation-c2' })).toBe(false)
  })

  it('marks the replacement candidate as canonical after promotion refresh', () => {
    const snapshot = createProductionWorkspaceV2OfficialCandidateCoexistenceFixture()
    const before = toShotStudioViewModels([snapshot.shots[0]])[0]
    expect(isCanonicalConfirmationCurrent(before, { shotId: before.shotId, lane: 'IMAGE', candidateId: 'fixture-candidate-c2', validationId: 'fixture-validation-c2' })).toBe(false)
    snapshot.shots[0].IMAGE.official = {
      ...snapshot.shots[0].IMAGE.official,
      version: { ...snapshot.shots[0].IMAGE.official.version!, id: 'fixture-official-c2', candidate_id: 'fixture-candidate-c2' },
    }
    const after = toShotStudioViewModels([snapshot.shots[0]])[0]
    expect(isCanonicalConfirmationCurrent(after, { shotId: after.shotId, lane: 'IMAGE', candidateId: 'fixture-candidate-c2', validationId: 'fixture-validation-c2' })).toBe(true)
  })
})
