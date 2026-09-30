import { describe, expect, it } from 'vitest'
import { classifyGenerationResponse, isCanonicalGenerationResponse, isLegacyTaskResponse } from './legacyProductionGenerationBridge'

describe('legacy production generation response classification', () => {
  it('gives canonical execution priority when task_id is also present', () => {
    const response = { execution: { execution_id: 'exec-1', status: 'RUNNING' }, task_id: 'legacy-diagnostic' }
    expect(classifyGenerationResponse(response)).toBe('mixed_canonical_with_task_diagnostic')
    expect(isCanonicalGenerationResponse(response)).toBe(true)
    expect(isLegacyTaskResponse(response)).toBe(false)
  })

  it('classifies canonical candidate responses without treating them as official media', () => {
    const response = { execution: { execution_id: 'exec-1', status: 'SUCCEEDED' }, candidate: { candidate_id: 'candidate-1', status: 'MEDIA_CANDIDATE' } }
    expect(classifyGenerationResponse(response)).toBe('canonical_candidate')
  })

  it('keeps execution-only responses on the canonical path', () => {
    expect(classifyGenerationResponse({ execution: { execution_id: 'exec-1', status: 'RUNNING' } })).toBe('canonical_execution')
  })

  it('keeps task_id-only responses on the legacy recovery path', () => {
    const response = { task_id: 'legacy-1', status: 'queued' }
    expect(classifyGenerationResponse(response)).toBe('legacy_task')
    expect(isLegacyTaskResponse(response)).toBe(true)
    expect(isCanonicalGenerationResponse(response)).toBe(false)
  })

  it.each([null, {}, { candidate: { candidate_id: 'candidate-only' } }, { status: 'queued' }])('fails closed for invalid response shape %j', (response) => {
    expect(classifyGenerationResponse(response)).toBe('invalid_response')
  })
})
