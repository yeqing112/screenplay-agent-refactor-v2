import { describe, expect, it, vi } from 'vitest'
import type { ShotStudioViewModel } from '../domain/productionUiV3'
import { createShotStudioGenerationController } from './productWorkspaceShotGeneration'
import { submitCanonicalProductionGeneration, ProductionGenerationServiceError } from './productionGeneration'
import { createShotStudioMediaReviewController } from './productWorkspaceShotReview'

function lane(target: 'IMAGE' | 'VIDEO', overrides: Record<string, unknown> = {}) {
  return {
    target,
    state: 'ready',
    generationAllowed: true,
    primaryAction: { kind: target === 'IMAGE' ? 'generate_image' : 'generate_video', lane: target, enabled: true },
    professional: { model: { selected_profile_id: `${target.toLowerCase()}-profile` } },
    execution: { isActive: false },
    candidate: { reviewEligibility: false },
    official: { isCanonicalOfficial: false },
    ...overrides,
  } as any
}

function view(overrides: Record<string, unknown> = {}) {
  return {
    shotId: 'S1',
    episode: 1,
    stale: { isStale: false },
    image: lane('IMAGE'),
    video: lane('VIDEO'),
    ...overrides,
  } as unknown as ShotStudioViewModel
}

function controller(options: { current?: ShotStudioViewModel; refresh?: () => Promise<void>; submit?: any; confirmCost?: () => boolean | Promise<boolean>; onState?: any } = {}) {
  let current = options.current ?? view()
  const refresh = options.refresh ?? vi.fn(async () => undefined)
  const instance = createShotStudioGenerationController({
    bookId: 1,
    getViewModel: () => current,
    refreshCanonical: async () => { await refresh() },
    submit: options.submit ?? vi.fn(async () => ({ execution: { status: 'RUNNING' } })),
    confirmCost: options.confirmCost,
    onState: options.onState,
    sleep: async () => undefined,
    maxRefreshAttempts: 2,
  })
  return { instance, setCurrent: (next: ShotStudioViewModel) => { current = next }, refresh }
}

describe('Shot Studio canonical generation controller', () => {
  it('requires the exact lane generation action and blocks stale/review/official/blocked states', async () => {
    for (const patch of [
      { stale: { isStale: true } },
      { image: lane('IMAGE', { state: 'review' }) },
      { image: lane('IMAGE', { state: 'official' }) },
      { image: lane('IMAGE', { state: 'blocked' }) },
      { image: lane('IMAGE', { primaryAction: { kind: 'inspect', lane: 'IMAGE' } }) },
    ]) {
      const submit = vi.fn()
      const { instance } = controller({ current: view(patch), submit })
      const result = await instance.start('S1', 'IMAGE')
      expect(result.ok).toBe(false)
      expect(result.snapshot.errorCode).toBe('GENERATION_GATE_BLOCKED')
      expect(submit).not.toHaveBeenCalled()
    }
  })

  it('requires an explicit model profile', async () => {
    const { instance } = controller({ current: view({ image: lane('IMAGE', { professional: { model: { selected_profile_id: null } } }) }) })
    const result = await instance.start('S1', 'IMAGE')
    expect(result.snapshot.errorCode).toBe('PRODUCTION_MODEL_SELECTION_REQUIRED')
  })

  it('confirms cost before submit and supports cancellation by declining', async () => {
    const submit = vi.fn()
    const { instance } = controller({ submit, confirmCost: () => false })
    const result = await instance.start('S1', 'IMAGE')
    expect(result.state).toBe('cancelled')
    expect(submit).not.toHaveBeenCalled()
  })

  it('does not submit when cancelled while the confirmation is pending', async () => {
    let release!: (value: boolean) => void
    const submit = vi.fn()
    const { instance } = controller({ submit, confirmCost: () => new Promise<boolean>((resolve) => { release = resolve }) })
    const pending = instance.start('S1', 'IMAGE')
    instance.cancel()
    release(true)
    const result = await pending
    expect(result.state).toBe('cancelled')
    expect(submit).not.toHaveBeenCalled()
  })

  it('rechecks the latest V2 identity after confirmation and blocks a changed state', async () => {
    let current = view()
    const submit = vi.fn()
    const generation = createShotStudioGenerationController({
      bookId: 1,
      getViewModel: () => current,
      refreshCanonical: async () => undefined,
      submit,
      confirmCost: () => {
        current = view({ image: lane('IMAGE', { state: 'running', generationAllowed: false, primaryAction: { kind: 'wait', lane: 'IMAGE' }, execution: { isActive: true } }) })
        return true
      },
    })
    const result = await generation.start('S1', 'IMAGE')
    expect(result.snapshot.errorCode).toBe('GENERATION_FRESHNESS_CONFLICT')
    expect(result.snapshot.message).toContain('生产状态已经更新')
    expect(submit).not.toHaveBeenCalled()
  })

  it('prevents double submit while the first canonical request is active', async () => {
    let release!: () => void
    const submit = vi.fn(() => new Promise((resolve) => { release = () => resolve({ execution: { status: 'RUNNING' } }) }))
    const { instance } = controller({ submit })
    const first = instance.start('S1', 'IMAGE')
    const second = await instance.start('S1', 'IMAGE')
    expect(second.snapshot.errorCode).toBe('GENERATION_MUTATION_LOCKED')
    release()
    await first
    expect(submit).toHaveBeenCalledTimes(1)
  })

  it('uses V2 refresh to project running then candidate_ready without optimistic state', async () => {
    const states: string[] = []
    const submit = vi.fn(async () => ({ execution: { status: 'RUNNING' } }))
    let current = view()
    let refreshCount = 0
    const instance = createShotStudioGenerationController({
      bookId: 1,
      getViewModel: () => current,
      submit,
      refreshCanonical: async () => {
        refreshCount += 1
        current = refreshCount === 1
          ? view({ image: lane('IMAGE', { state: 'running', execution: { isActive: true }, primaryAction: { kind: 'wait' } }) })
          : view({ image: lane('IMAGE', { state: 'review', primaryAction: { kind: 'review_candidate' }, candidate: { reviewEligibility: true } }) })
      },
      onState: (next: any) => states.push(next.state),
      sleep: async () => undefined,
      maxRefreshAttempts: 3,
    })
    const result = await instance.start('S1', 'IMAGE')
    expect(result.ok).toBe(true)
    expect(states).toContain('running')
    expect(result.state).toBe('candidate_ready')
  })

  it('fails closed on a legacy task_id response', async () => {
    const { instance } = controller({ submit: async () => ({ task_id: 'legacy-task' }) })
    const result = await instance.start('S1', 'IMAGE')
    expect(result.snapshot.errorCode).toBe('V3_LEGACY_GENERATION_TASK_RESPONSE_UNSUPPORTED')
  })

  it('refreshes once on a 409 and never retries the POST', async () => {
    const submit = vi.fn(async () => { throw new ProductionGenerationServiceError('stale', 409, 'GENERATION_PREVIEW_STALE') })
    const refresh = vi.fn(async () => undefined)
    const { instance } = controller({ submit, refresh })
    const result = await instance.start('S1', 'IMAGE')
    expect(result.snapshot.status).toBe(409)
    expect(submit).toHaveBeenCalledTimes(1)
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('keeps IMAGE_TO_VIDEO disabled without canonical official source', async () => {
    const submit = vi.fn()
    const { instance } = controller({ current: view({ video: lane('VIDEO', { generationMode: 'IMAGE_TO_VIDEO', generationAllowed: false, primaryAction: { kind: 'resolve_blocker', lane: 'VIDEO' }, sourceOfficialImage: { isCanonicalOfficial: false } }) }), submit })
    const result = await instance.start('S1', 'VIDEO')
    expect(result.snapshot.errorCode).toBe('OFFICIAL_IMAGE_REQUIRED')
    expect(submit).not.toHaveBeenCalled()
  })

  it('allows VIDEO only after the V2 lane exposes a canonical source', async () => {
    const submit = vi.fn(async () => ({ execution: { status: 'RUNNING' } }))
    const { instance } = controller({ current: view({ video: lane('VIDEO', { generationMode: 'IMAGE_TO_VIDEO', sourceOfficialImage: { isCanonicalOfficial: true } }) }), submit })
    const result = await instance.start('S1', 'VIDEO')
    expect(submit).toHaveBeenCalledTimes(1)
    expect(result.snapshot.state).toBe('failed')
  })

  it('allows a ready IMAGE lane to submit exactly once', async () => {
    const submit = vi.fn(async () => ({ execution: { status: 'RUNNING' } }))
    const { instance } = controller({ submit, refresh: async () => undefined })
    await instance.start('S1', 'IMAGE')
    expect(submit).toHaveBeenCalledTimes(1)
  })

  it('allows a ready VIDEO lane with canonical source to submit exactly once', async () => {
    const submit = vi.fn(async () => ({ execution: { status: 'RUNNING' } }))
    const { instance } = controller({ current: view({ image: lane('IMAGE', { state: 'official', primaryAction: { kind: 'view_official', lane: 'IMAGE' }, generationAllowed: false, official: { current: true, isCanonicalOfficial: true } }), video: lane('VIDEO', { sourceOfficialImage: { isCanonicalOfficial: true } }) }), submit })
    await instance.start('S1', 'VIDEO')
    expect(submit).toHaveBeenCalledTimes(1)
  })

  it('does not optimistically expose running or candidate state', async () => {
    const states: string[] = []
    const { instance } = controller({ onState: (next: any) => states.push(next.state), submit: async () => ({ execution: { status: 'SUCCEEDED' }, candidate: { id: 'candidate' } }) })
    const result = await instance.start('S1', 'IMAGE')
    expect(result.snapshot.state).toBe('failed')
    expect(states).not.toContain('candidate_ready')
    expect(states).not.toContain('running')
  })

  it('blocks generation while review mutation is active', async () => {
    const submit = vi.fn()
    const { instance } = controller({ submit, onState: undefined })
    const locked = createShotStudioGenerationController({ bookId: 1, getViewModel: () => view(), refreshCanonical: async () => undefined, submit, isReviewMutationActive: () => true })
    const result = await locked.start('S1', 'IMAGE')
    expect(result.snapshot.errorCode).toBe('GENERATION_REVIEW_MUTATION_LOCKED')
    expect(submit).not.toHaveBeenCalled()
    void instance
  })

  it('recovers a running state from a V2 refresh after reload without local storage', async () => {
    const states: string[] = []
    let current = view()
    const { instance } = controller({ onState: (next: any) => states.push(next.state), refresh: async () => { current = view({ image: lane('IMAGE', { state: 'running', primaryAction: { kind: 'wait', lane: 'IMAGE' }, execution: { isActive: true } }) }) } })
    const recovery = createShotStudioGenerationController({ bookId: 1, getViewModel: () => current, refreshCanonical: async () => { current = view({ image: lane('IMAGE', { state: 'running', primaryAction: { kind: 'wait', lane: 'IMAGE' }, execution: { isActive: true } }) }) }, submit: async () => ({ execution: { status: 'RUNNING' } }), onState: (next) => states.push(next.state), sleep: async () => undefined, maxRefreshAttempts: 1 })
    const result = await recovery.start('S1', 'IMAGE')
    expect(states).toContain('running')
    expect(result.ok).toBe(true)
    expect(result.state).toBe('in_progress')
    expect(result.snapshot.state).toBe('running')
    expect(result.snapshot.errorCode).toBeNull()
    void instance
  })

  it('keeps a persistent canonical running execution in progress after the observation window', async () => {
    const submit = vi.fn(async () => ({ execution: { execution_id: 'exec-running', status: 'RUNNING' } }))
    let current = view()
    const instance = createShotStudioGenerationController({ bookId: 1, getViewModel: () => current, refreshCanonical: async () => { current = view({ image: lane('IMAGE', { state: 'running', generationAllowed: false, primaryAction: { kind: 'wait', lane: 'IMAGE' }, execution: { id: 'exec-running', state: 'running', isActive: true } }) }) }, submit, sleep: async () => undefined, maxRefreshAttempts: 2 })
    const result = await instance.start('S1', 'IMAGE')
    expect(result.ok).toBe(true)
    expect(result.state).toBe('in_progress')
    expect(result.snapshot.state).toBe('running')
    expect(result.snapshot.errorCode).toBeNull()
  })

  it('keeps a succeeded execution with a pending candidate projection in progress', async () => {
    const submit = vi.fn(async () => ({ execution: { execution_id: 'exec-succeeded', status: 'SUCCEEDED' } }))
    let current = view()
    const instance = createShotStudioGenerationController({ bookId: 1, getViewModel: () => current, refreshCanonical: async () => { current = view({ image: lane('IMAGE', {
      state: 'waiting',
      generationAllowed: false,
      primaryAction: { kind: 'wait', lane: 'IMAGE' },
      execution: { id: 'exec-succeeded', state: 'succeeded', isActive: false, raw: { candidate_id: 'candidate-pending' } },
    }) }) }, submit, sleep: async () => undefined, maxRefreshAttempts: 2 })
    const result = await instance.start('S1', 'IMAGE')
    expect(result.ok).toBe(true)
    expect(result.state).toBe('in_progress')
    expect(result.snapshot.state).toBe('waiting_candidate')
    expect(result.snapshot.errorCode).toBeNull()
    expect(submit).toHaveBeenCalledTimes(1)
  })

  it('fails with an independent projection anomaly when V2 never exposes execution evidence', async () => {
    const submit = vi.fn(async () => ({ execution: { status: 'SUCCEEDED' }, candidate: null }))
    const { instance } = controller({ submit, current: view({ image: lane('IMAGE', { state: 'ready' }) }) })
    const result = await instance.start('S1', 'IMAGE')
    expect(result.snapshot.errorCode).toBe('V3_GENERATION_PROJECTION_NOT_VISIBLE')
    expect(submit).toHaveBeenCalledTimes(1)
  })

  it('stops immediately on canonical failure and preserves its reason', async () => {
    let refreshCount = 0
    const submit = vi.fn(async () => ({ execution: { execution_id: 'exec-failed', status: 'RUNNING' } }))
    let current = view()
    const instance = createShotStudioGenerationController({ bookId: 1, getViewModel: () => current, refreshCanonical: async () => { refreshCount += 1; current = view({ image: lane('IMAGE', { state: 'failed', generationAllowed: false, primaryAction: { kind: 'retry_generation', lane: 'IMAGE', enabled: false }, execution: { id: 'exec-failed', state: 'failed', failureCode: 'PROVIDER_ERROR', isActive: false } }) }) }, submit, sleep: async () => undefined, maxRefreshAttempts: 2 })
    const result = await instance.start('S1', 'IMAGE')
    expect(result.ok).toBe(false)
    expect(result.state).toBe('failed')
    expect(result.snapshot.errorCode).toBe('PROVIDER_ERROR')
    expect(refreshCount).toBe(1)
  })

  it('fails closed when observation becomes stale or blocked', async () => {
    for (const state of ['stale', 'blocked'] as const) {
      const submit = vi.fn(async () => ({ execution: { execution_id: `exec-${state}`, status: 'RUNNING' } }))
      let current = view()
      const instance = createShotStudioGenerationController({ bookId: 1, getViewModel: () => current, refreshCanonical: async () => { current = view({ image: lane('IMAGE', { state, generationAllowed: false, primaryAction: { kind: state === 'stale' ? 'refresh_stale_source' : 'resolve_blocker', lane: 'IMAGE' }, reasonCodes: [state === 'stale' ? 'PROMPT_IR_STALE' : 'MODEL_PROFILE_REQUIRED'], execution: { id: `exec-${state}`, state: state === 'stale' ? 'stale' : 'running', isActive: false } }) }) }, submit, sleep: async () => undefined, maxRefreshAttempts: 2 })
      const result = await instance.start('S1', 'IMAGE')
      expect(result.ok).toBe(false)
      expect(result.snapshot.errorCode).toBe(state === 'stale' ? 'PROMPT_IR_STALE' : 'MODEL_PROFILE_REQUIRED')
    }
  })

  it('stops foreground observation without claiming backend cancellation after submit', async () => {
    let releaseSubmit!: (value: any) => void
    const submit = vi.fn(() => new Promise((resolve) => { releaseSubmit = resolve }))
    const { instance } = controller({ submit })
    const pending = instance.start('S1', 'IMAGE')
    await Promise.resolve()
    await Promise.resolve()
    expect(submit).toHaveBeenCalledTimes(1)
    instance.stopObserving()
    releaseSubmit({ execution: { execution_id: 'exec-running', status: 'RUNNING' } })
    const result = await pending
    expect(result.ok).toBe(true)
    expect(result.state).toBe('in_progress')
    expect(result.snapshot.errorCode).toBeNull()
    expect(result.snapshot.message).toContain('后台生成任务可能仍在运行')
  })

  it('cancels an in-flight submission with AbortController', async () => {
    const submit = vi.fn((_options: any) => new Promise((_resolve, reject) => { setTimeout(() => reject(new DOMException('aborted', 'AbortError')), 0) }))
    const { instance } = controller({ submit })
    const pending = instance.start('S1', 'IMAGE')
    instance.cancel()
    const result = await pending
    expect(result.state).toBe('cancelled')
  })
})

describe('canonical generation service contract', () => {
  it('sends compileIfMissing=false and no legacy asset fields', async () => {
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => ({ ok: true, json: async () => ({ execution: { status: 'RUNNING' } }), init }))
    vi.stubGlobal('fetch', fetchMock)
    await submitCanonicalProductionGeneration({ bookId: 1, episode: 1, shotId: 'S1', target: 'VIDEO', modelProfileId: 'video-profile', firstFrameAssetId: 'legacy', referenceAssetIds: ['legacy-ref'] })
    const init = fetchMock.mock.calls[0][1] as RequestInit
    const body = JSON.parse(String(init.body))
    expect(body.compileIfMissing).toBe(false)
    expect(body.firstFrameAssetId).toBeUndefined()
    expect(body.referenceAssetIds).toBeUndefined()
  })

  it('preserves HTTP status and backend code', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 409, json: async () => ({ detail: { code: 'GENERATION_PREVIEW_STALE', message: 'stale' } }) })))
    await expect(submitCanonicalProductionGeneration({ bookId: 1, episode: 1, shotId: 'S1', target: 'IMAGE', modelProfileId: 'image-profile' })).rejects.toMatchObject({ status: 409, code: 'GENERATION_PREVIEW_STALE' } satisfies Partial<ProductionGenerationServiceError>)
  })
})

describe('full IMAGE -> VIDEO canonical loop', () => {
  it('submits each lane once, promotes explicitly, and never auto-generates VIDEO', async () => {
    let phase = 'image-ready'
    let refreshCount = 0
    const posts: string[] = []
    const candidate = (id: string, lane: 'IMAGE' | 'VIDEO') => ({ id, state: 'MEDIA_CANDIDATE', preview: null, preview_url: null, model_profile_id: `${lane.toLowerCase()}-profile`, technical_validation: { status: 'TECHNICALLY_VALID', validation_id: `${id}-validation` } })
    const makeView = (): any => {
      const imageOfficial = ['image-approved', 'video-submitted', 'video-review', 'shot-official'].includes(phase)
      const videoOfficial = phase === 'shot-official'
      const imageReview = phase === 'image-review'
      const videoReview = phase === 'video-review'
      const imageRunning = phase === 'image-running'
      const videoRunning = phase === 'video-running'
      const image = imageOfficial
        ? { target: 'IMAGE', state: 'official', generationAllowed: false, primaryAction: { kind: 'view_official', lane: 'IMAGE' }, professional: { model: { selected_profile_id: 'image-profile' } }, execution: { isActive: false }, candidate: { reviewEligibility: false, candidate: null }, official: { current: true, isCanonicalOfficial: true, version: { candidate_id: 'image-candidate' } } }
        : imageReview
          ? { target: 'IMAGE', state: 'review', generationAllowed: false, primaryAction: { kind: 'review_candidate', lane: 'IMAGE' }, professional: { model: { selected_profile_id: 'image-profile', candidateItems: [candidate('image-candidate', 'IMAGE')] } }, execution: { isActive: false }, candidate: { reviewEligibility: true, candidate: candidate('image-candidate', 'IMAGE') }, official: { current: false, isCanonicalOfficial: false, reasonCodes: [] } }
          : { target: 'IMAGE', state: imageRunning ? 'running' : 'ready', generationAllowed: !imageRunning, primaryAction: { kind: imageRunning ? 'wait' : 'generate_image', lane: 'IMAGE' }, professional: { model: { selected_profile_id: 'image-profile' } }, execution: { isActive: imageRunning }, candidate: { reviewEligibility: false, candidate: null }, official: { current: false, isCanonicalOfficial: false, reasonCodes: [] } }
      const video = videoOfficial
        ? { target: 'VIDEO', state: 'official', generationAllowed: false, primaryAction: { kind: 'view_official', lane: 'VIDEO' }, professional: { model: { selected_profile_id: 'video-profile' } }, execution: { isActive: false }, candidate: { reviewEligibility: false, candidate: null }, official: { current: true, isCanonicalOfficial: true, version: { candidate_id: 'video-candidate' } }, sourceOfficialImage: { isCanonicalOfficial: true } }
        : videoReview
          ? { target: 'VIDEO', state: 'review', generationAllowed: false, primaryAction: { kind: 'review_candidate', lane: 'VIDEO' }, professional: { model: { selected_profile_id: 'video-profile', candidateItems: [candidate('video-candidate', 'VIDEO')] } }, execution: { isActive: false }, candidate: { reviewEligibility: true, candidate: candidate('video-candidate', 'VIDEO') }, official: { current: false, isCanonicalOfficial: false, reasonCodes: [] }, sourceOfficialImage: { isCanonicalOfficial: true } }
          : { target: 'VIDEO', state: videoRunning ? 'running' : imageOfficial ? 'ready' : 'waiting', generationAllowed: imageOfficial && !videoRunning, primaryAction: { kind: videoRunning ? 'wait' : imageOfficial ? 'generate_video' : 'wait', lane: 'VIDEO' }, professional: { model: { selected_profile_id: 'video-profile' } }, execution: { isActive: videoRunning }, candidate: { reviewEligibility: false, candidate: null }, official: { current: false, isCanonicalOfficial: false, reasonCodes: [] }, sourceOfficialImage: { isCanonicalOfficial: imageOfficial } }
      return { shotId: 'S1', episode: 1, stale: { isStale: false }, state: phase === 'shot-official' ? 'official' : 'ready', image, video }
    }
    let current = makeView()
    const refreshCanonical = vi.fn(async () => {
      refreshCount += 1
      if (phase === 'image-submitted' && refreshCount === 1) phase = 'image-running'
      else if (phase === 'image-running' && refreshCount >= 2) phase = 'image-review'
      else if (phase === 'video-submitted' && refreshCount === 1) phase = 'video-running'
      else if (phase === 'video-running' && refreshCount >= 2) phase = 'video-review'
      current = makeView()
    })
    const submit = vi.fn(async ({ target }: { target: 'IMAGE' | 'VIDEO' }) => {
      posts.push(target)
      phase = target === 'IMAGE' ? 'image-submitted' : 'video-submitted'
      refreshCount = 0
      return { execution: { execution_id: `${target}-execution`, status: 'RUNNING' } }
    })
    const generation = createShotStudioGenerationController({ bookId: 1, getViewModel: () => current, refreshCanonical, submit, confirmCost: () => true, sleep: async () => undefined, maxRefreshAttempts: 3 })
    const imageResult = await generation.start('S1', 'IMAGE')
    expect(imageResult.ok).toBe(true)
    expect(posts).toEqual(['IMAGE'])
    expect(current.image.state).toBe('review')

    const review = createShotStudioMediaReviewController({ getViewModel: () => current, validateCandidate: async (id) => ({ validation_id: `${id}-validation` }), promoteCandidate: async (id) => { posts.push(`PROMOTE_${id}`); phase = id.startsWith('image') ? 'image-approved' : 'shot-official'; current = makeView() }, refreshCanonical, sleep: async () => undefined })
    const imageApproval = await review.approve({ shotId: 'S1', lane: 'IMAGE', candidateId: 'image-candidate', validationId: 'image-candidate-validation' })
    expect(imageApproval.ok).toBe(true)
    expect(current.video.primaryAction.kind).toBe('generate_video')
    expect(posts).toEqual(['IMAGE', 'PROMOTE_image-candidate'])

    const videoResult = await generation.start('S1', 'VIDEO')
    expect(videoResult.ok).toBe(true)
    expect(posts).toEqual(['IMAGE', 'PROMOTE_image-candidate', 'VIDEO'])
    const videoApproval = await review.approve({ shotId: 'S1', lane: 'VIDEO', candidateId: 'video-candidate', validationId: 'video-candidate-validation' })
    expect(videoApproval.ok).toBe(true)
    expect(posts).toEqual(['IMAGE', 'PROMOTE_image-candidate', 'VIDEO', 'PROMOTE_video-candidate'])
    expect(current.image.official.isCanonicalOfficial).toBe(true)
    expect(current.video.official.isCanonicalOfficial).toBe(true)
  })
})
