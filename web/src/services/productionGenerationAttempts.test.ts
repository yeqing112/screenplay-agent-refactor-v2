import { describe, expect, it, vi } from 'vitest'
import { createGenerationAttempt, executeGenerationAttempt, previewGenerationAttempt, ProductionGenerationAttemptServiceError } from './productionGenerationAttempts'

describe('production generation attempt facade service', () => {
  it('uses only shot-level facade and sends retry source execution', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ attempt: { attempt_lineage_id: 'a1' }, attemptConfirmationToken: 't1' }), { status: 201, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)
    await createGenerationAttempt({ bookId: 1, episode: 2, shotId: '3', operation: 'RETRY', target: 'IMAGE', operationIdempotencyKey: 'k1', sourceExecutionId: 'e1' })
    expect(fetchMock.mock.calls[0][0]).toContain('/api/books/1/episodes/2/shots/3/generation-attempts')
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body).toEqual({ operationKind: 'RETRY', targetMedia: 'IMAGE', operationIdempotencyKey: 'k1', reason: '', sourceExecutionId: 'e1' })
    expect(String(fetchMock.mock.calls[0][0])).not.toContain('attempt-intents')
  })

  it('does not send source ids for regenerate and chains preview/execute tokens', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ attempt: { attempt_lineage_id: 'a2' }, attemptConfirmationToken: 't2' }), { status: 201 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ execution: { execution_id: 'e2' }, execution_confirmation_token: 'et2' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ execution: { execution_id: 'e2' } }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await createGenerationAttempt({ bookId: 1, episode: 2, shotId: 3, operation: 'REGENERATE', target: 'VIDEO', operationIdempotencyKey: 'k2' })
    await previewGenerationAttempt({ bookId: 1, episode: 2, shotId: 3, attemptLineageId: 'a2', attemptConfirmationToken: 't2' })
    await executeGenerationAttempt({ bookId: 1, episode: 2, shotId: 3, attemptLineageId: 'a2', attemptConfirmationToken: 't2', previewExecutionId: 'e2', executionConfirmationToken: 'et2' })
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).not.toHaveProperty('sourceExecutionId')
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ attemptConfirmationToken: 't2' })
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ execute: true, confirmed: true, allowExternalCall: true, attemptConfirmationToken: 't2', previewExecutionId: 'e2', executionConfirmationToken: 'et2' })
  })

  it('normalizes typed backend errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { code: 'GENERATION_REGENERATE_ACTIVE_EXECUTION', message: 'active' } }), { status: 409 })))
    await expect(createGenerationAttempt({ bookId: 1, episode: 1, shotId: 1, operation: 'REGENERATE', target: 'IMAGE', operationIdempotencyKey: 'k' })).rejects.toMatchObject({ status: 409, code: 'GENERATION_REGENERATE_ACTIVE_EXECUTION', message: 'active' } satisfies Partial<ProductionGenerationAttemptServiceError>)
  })
})
