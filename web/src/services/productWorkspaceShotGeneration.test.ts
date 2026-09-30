import { describe, expect, it, vi } from 'vitest'
import type { ShotStudioViewModel } from '../domain/productionUiV3'
import { createShotStudioGenerationController } from './productWorkspaceShotGeneration'
import { submitCanonicalProductionGeneration, ProductionGenerationServiceError } from './productionGeneration'

function lane(target: 'IMAGE' | 'VIDEO', overrides: Record<string, unknown> = {}) {
  return {
    target,
    state: 'ready',
    generationAllowed: true,
    primaryAction: { kind: target === 'IMAGE' ? 'generate_image' : 'generate_video', enabled: true },
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
      { image: lane('IMAGE', { primaryAction: { kind: 'inspect' } }) },
    ]) {
      const { instance } = controller({ current: view(patch) })
      const result = await instance.start('S1', 'IMAGE')
      expect(result.ok).toBe(false)
      expect(result.snapshot.errorCode).toBe('GENERATION_GATE_BLOCKED')
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
    expect(result.snapshot.errorCode).toBe('GENERATION_LEGACY_TASK_RESPONSE')
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
