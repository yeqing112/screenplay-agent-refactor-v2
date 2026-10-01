import type { ProductionGenerationTarget } from './productionGeneration'

export type GenerationAttemptOperation = 'RETRY' | 'REGENERATE'

export interface CreateGenerationAttemptOptions {
  bookId: number
  episode: number
  shotId: string | number
  operation?: GenerationAttemptOperation
  operationKind?: GenerationAttemptOperation
  target?: ProductionGenerationTarget
  targetMedia?: ProductionGenerationTarget
  operationIdempotencyKey: string
  sourceExecutionId?: string
  reason?: string
  signal?: AbortSignal
}

export interface GenerationAttemptRecord {
  attempt_lineage_id?: string
  attemptLineageId?: string
  operation_kind?: GenerationAttemptOperation
  operationKind?: GenerationAttemptOperation
  target_media?: ProductionGenerationTarget
  targetMedia?: ProductionGenerationTarget
  status?: string
  confirmation_token?: string
  confirmationToken?: string
  [key: string]: unknown
}

export interface GenerationAttemptResponse {
  attempt: GenerationAttemptRecord
  attemptConfirmationToken: string
  providerCalls: number
  executionCreated: boolean
  mediaGenerated: boolean
  reused?: boolean
  [key: string]: unknown
}

export interface GenerationAttemptPreviewResponse {
  attempt: GenerationAttemptRecord
  execution: Record<string, unknown>
  candidate?: Record<string, unknown> | null
  execution_confirmation_token: string
  executionConfirmationToken?: string
  attemptConfirmationToken?: string
  provider_calls?: number
  reused?: boolean
  [key: string]: unknown
}

export interface GenerationAttemptExecuteResponse extends GenerationAttemptPreviewResponse {
  provider_calls?: number
  media_generated?: boolean
}

export class ProductionGenerationAttemptServiceError extends Error {
  readonly status: number
  readonly code: string | null
  readonly details: unknown

  constructor(message: string, status: number, code: string | null = null, details: unknown = null) {
    super(message)
    this.name = 'ProductionGenerationAttemptServiceError'
    this.status = status
    this.code = code
    this.details = details
  }
}

function text(value: unknown) { return String(value ?? '').trim() }

async function request<T>(url: string, init: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (response.ok) return response.json() as Promise<T>
  let payload: unknown = null
  let message = ''
  try {
    payload = await response.json()
    const body = payload as { detail?: unknown; message?: unknown; error?: unknown; code?: unknown }
    const detail = body.detail && typeof body.detail === 'object' ? body.detail as { message?: unknown; code?: unknown } : null
    message = text(detail?.message || body.message || body.error || body.detail)
    const code = text(detail?.code || body.code) || (response.status === 409 ? 'GENERATION_ATTEMPT_CONFLICT' : null)
    throw new ProductionGenerationAttemptServiceError(message || `HTTP ${response.status}`, response.status, code, payload)
  } catch (error) {
    if (error instanceof ProductionGenerationAttemptServiceError) throw error
    throw new ProductionGenerationAttemptServiceError(message || `HTTP ${response.status}`, response.status, response.status === 409 ? 'GENERATION_ATTEMPT_CONFLICT' : null, payload)
  }
}

function basePath(options: { bookId: number; episode: number; shotId: string | number }) {
  return `/api/books/${options.bookId}/episodes/${options.episode}/shots/${options.shotId}/generation-attempts`
}

export async function createGenerationAttempt(options: CreateGenerationAttemptOptions): Promise<GenerationAttemptResponse> {
  const operation = options.operation ?? options.operationKind
  const target = options.target ?? options.targetMedia
  if (!operation || !target) throw new ProductionGenerationAttemptServiceError('Attempt operation and target are required.', 400, 'GENERATION_ATTEMPT_REQUEST_INVALID')
  const body: Record<string, unknown> = {
    operationKind: operation,
    targetMedia: target,
    operationIdempotencyKey: options.operationIdempotencyKey,
    reason: options.reason ?? '',
  }
  if (operation === 'RETRY') body.sourceExecutionId = options.sourceExecutionId
  return request<GenerationAttemptResponse>(basePath(options), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: options.signal,
  })
}

export async function previewGenerationAttempt(options: { bookId: number; episode: number; shotId: string | number; attemptLineageId: string; attemptConfirmationToken: string; signal?: AbortSignal }): Promise<GenerationAttemptPreviewResponse> {
  return request<GenerationAttemptPreviewResponse>(`${basePath(options)}/${encodeURIComponent(options.attemptLineageId)}/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ attemptConfirmationToken: options.attemptConfirmationToken }),
    signal: options.signal,
  })
}

export async function executeGenerationAttempt(options: { bookId: number; episode: number; shotId: string | number; attemptLineageId: string; attemptConfirmationToken: string; previewExecutionId: string; executionConfirmationToken: string; signal?: AbortSignal }): Promise<GenerationAttemptExecuteResponse> {
  return request<GenerationAttemptExecuteResponse>(`${basePath(options)}/${encodeURIComponent(options.attemptLineageId)}/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ execute: true, confirmed: true, allowExternalCall: true, attemptConfirmationToken: options.attemptConfirmationToken, previewExecutionId: options.previewExecutionId, executionConfirmationToken: options.executionConfirmationToken }),
    signal: options.signal,
  })
}

export const createShotGenerationAttempt = createGenerationAttempt
export const createShotGenerationAttemptIntent = createGenerationAttempt
export const previewShotGenerationAttempt = previewGenerationAttempt
export const executeShotGenerationAttempt = executeGenerationAttempt
