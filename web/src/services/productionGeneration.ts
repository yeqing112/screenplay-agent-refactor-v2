/** Shared UI controller for the canonical Production generation routes. */

export type ProductionGenerationTarget = 'IMAGE' | 'VIDEO'

export interface SubmitProductionGenerationOptions {
  bookId: number
  episode: number
  shotId: string | number
  target: ProductionGenerationTarget
  modelProfileId: string
  firstFrameAssetId?: string | null
  referenceAssetIds?: string[]
  generationChain?: string
  signal?: AbortSignal
}

export interface ProductionGenerationExecution {
  execution_id?: string
  status?: string
  target_media?: string
  provider?: string | null
  model?: string | null
  provider_task_id?: string | null
  provider_request_id?: string | null
  failure_code?: string | null
  failure_message?: string | null
  [key: string]: unknown
}

export interface ProductionGenerationCandidate {
  candidate_id?: string
  id?: string
  status?: string
  media_type?: string
  preview?: string | null
  preview_url?: string | null
  [key: string]: unknown
}

export interface ProductionGenerationResponse {
  execution?: ProductionGenerationExecution | null
  candidate?: ProductionGenerationCandidate | null
  provider_calls?: number
  reused?: boolean
  confirmation_token?: string
  task_id?: string
  [key: string]: unknown
}

export class ProductionGenerationServiceError extends Error {
  readonly status: number
  readonly code: string | null
  readonly details: unknown

  constructor(message: string, status: number, code: string | null = null, details: unknown = null) {
    super(message)
    this.name = 'ProductionGenerationServiceError'
    this.status = status
    this.code = code
    this.details = details
  }
}

export async function submitCanonicalProductionGeneration(options: SubmitProductionGenerationOptions): Promise<ProductionGenerationResponse> {
  const endpoint = `/api/books/${options.bookId}/storyboard/${options.episode}/${options.shotId}/${options.target === 'IMAGE' ? 'generate-frame' : 'generate-video'}`
  const body: Record<string, unknown> = {
    modelProfileId: options.modelProfileId,
    confirmed: true,
    allowExternalCall: true,
    // Generation must consume the current PromptIR. Compilation is a separate
    // user action and must never be hidden inside a paid generation click.
    compileIfMissing: false,
    generationChain: options.generationChain ?? 'production_workspace_v2',
  }
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: options.signal,
  })
  if (!response.ok) {
    let detail = ''
    let code: string | null = null
    let payload: unknown = null
    try {
      payload = await response.json()
      const candidate = payload as { detail?: unknown; code?: unknown; message?: unknown; error?: unknown }
      const rawDetail = candidate?.detail
      code = typeof (rawDetail as { code?: unknown })?.code === 'string'
        ? String((rawDetail as { code: string }).code)
        : typeof candidate?.code === 'string' ? candidate.code : null
      detail = String((rawDetail as { message?: unknown })?.message || rawDetail || candidate?.message || candidate?.error || '').trim()
    } catch {
      detail = await response.text()
    }
    throw new ProductionGenerationServiceError(detail || `HTTP ${response.status}`, response.status, code, payload)
  }
  return response.json()
}
