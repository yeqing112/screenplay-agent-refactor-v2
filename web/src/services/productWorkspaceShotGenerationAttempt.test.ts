import { describe, expect, it, vi } from 'vitest'
import type { ShotStudioViewModel } from '../domain/productionUiV3'
import { createShotStudioGenerationAttemptController } from './productWorkspaceShotGenerationAttempt'

function lane(overrides: Record<string, unknown> = {}) {
  return {
    target: 'IMAGE', state: 'failed', primaryAction: { kind: 'retry_generation', enabled: true, lane: 'IMAGE' }, regenerateAction: { kind: 'regenerate_media', enabled: false, lane: 'IMAGE' }, generationAllowed: false, generationReady: true, generationMode: 'TEXT_TO_IMAGE', professional: { candidateItems: [], model: {} }, execution: { id: 'failed-1', rawState: 'FAILED', state: 'failed', isActive: false, failureCode: 'MODEL_FAILED', raw: { candidate_id: null } }, candidate: { candidate: null, candidateCount: 0, reviewEligibility: false, reasonCodes: [] }, official: { isCanonicalOfficial: false, current: false, currentness: 'missing', version: null, reasonCodes: [] }, sourceOfficialImage: null, stale: false, ...overrides,
  } as any
}
function shot(current = lane()): ShotStudioViewModel {
  return { shotId: 'shot-1', episode: 1, stale: { isStale: false }, image: current, video: { ...current, target: 'VIDEO' }, scene: { id: 's', name: 'Scene' } } as any
}

describe('shot generation attempt controller', () => {
  it('does not create an intent when cost confirmation is declined', async () => {
    const create = vi.fn()
    const controller = createShotStudioGenerationAttemptController({ bookId: 1, getViewModel: () => shot(), refreshCanonical: vi.fn(), confirmCost: () => false, create })
    const result = await controller.retry('shot-1', 'IMAGE')
    expect(result.state).toBe('cancelled')
    expect(create).not.toHaveBeenCalled()
  })

  it('chains one idempotent retry and waits for the produced execution candidate', async () => {
    const create = vi.fn().mockResolvedValue({ attempt: { attempt_lineage_id: 'a1' }, attemptConfirmationToken: 'at' })
    const preview = vi.fn().mockResolvedValue({ execution: { execution_id: 'produced-1' }, execution_confirmation_token: 'et' })
    const execute = vi.fn().mockResolvedValue({})
    const views = [shot(), shot(lane({ state: 'running', execution: { id: 'produced-1', rawState: 'RUNNING', state: 'running', isActive: true, raw: {} } })), shot(lane({ state: 'review', execution: { id: 'produced-1', rawState: 'SUCCESS', state: 'succeeded', isActive: false, raw: { candidate_id: 'candidate-1' } }, candidate: { candidate: { id: 'candidate-1' }, candidateCount: 1, reviewEligibility: true, reasonCodes: ['CANDIDATE_REVIEW_REQUIRED'] }, professional: { candidateItems: [{ id: 'candidate-1' }], model: {} } }))]
    let index = 0
    const refreshCanonical = vi.fn(async () => { index = Math.min(index + 1, views.length - 1) })
    const controller = createShotStudioGenerationAttemptController({ bookId: 1, getViewModel: () => views[index], refreshCanonical, confirmCost: () => true, create, preview, execute, randomUUID: () => 'fixed-key', maxRefreshAttempts: 3, sleep: async () => undefined })
    const result = await controller.retry('shot-1', 'IMAGE')
    expect(result.state).toBe('candidate_ready')
    expect(create).toHaveBeenCalledTimes(1)
    expect(create.mock.calls[0][0]).toMatchObject({ operation: 'RETRY', operationIdempotencyKey: 'fixed-key', sourceExecutionId: 'failed-1' })
    expect(preview).toHaveBeenCalledWith(expect.objectContaining({ attemptConfirmationToken: 'at', attemptLineageId: 'a1' }))
    expect(execute).toHaveBeenCalledWith(expect.objectContaining({ previewExecutionId: 'produced-1', executionConfirmationToken: 'et' }))
  })
})

