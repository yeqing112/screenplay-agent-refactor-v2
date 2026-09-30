import type { ProductionGenerationResponse } from './productionGeneration'

export type LegacyProductionGenerationResponseClass =
  | 'canonical_execution'
  | 'canonical_candidate'
  | 'legacy_task'
  | 'mixed_canonical_with_task_diagnostic'
  | 'invalid_response'

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

function hasText(value: unknown) {
  return typeof value === 'string' ? value.trim().length > 0 : Boolean(value)
}

/**
 * Classifies the response shape without changing it. Canonical execution is
 * authoritative whenever it is present; task_id is only a compatibility
 * diagnostic in that case.
 */
export function classifyGenerationResponse(value: unknown): LegacyProductionGenerationResponseClass {
  if (!isRecord(value)) return 'invalid_response'
  const hasExecution = isRecord(value.execution)
  const hasCandidate = isRecord(value.candidate)
  const hasTaskId = hasText(value.task_id)
  if (hasExecution && hasTaskId) return 'mixed_canonical_with_task_diagnostic'
  if (hasExecution && hasCandidate) return 'canonical_candidate'
  if (hasExecution) return 'canonical_execution'
  if (hasTaskId) return 'legacy_task'
  return 'invalid_response'
}

export function isCanonicalGenerationResponse(value: unknown): value is ProductionGenerationResponse {
  const kind = classifyGenerationResponse(value)
  return kind === 'canonical_execution' || kind === 'canonical_candidate' || kind === 'mixed_canonical_with_task_diagnostic'
}

export function isLegacyTaskResponse(value: unknown): value is ProductionGenerationResponse {
  return classifyGenerationResponse(value) === 'legacy_task'
}
