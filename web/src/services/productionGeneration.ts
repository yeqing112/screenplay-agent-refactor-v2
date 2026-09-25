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
}

export async function submitCanonicalProductionGeneration(options: SubmitProductionGenerationOptions): Promise<Record<string, any>> {
  const endpoint = `/api/books/${options.bookId}/storyboard/${options.episode}/${options.shotId}/${options.target === 'IMAGE' ? 'generate-frame' : 'generate-video'}`
  const body: Record<string, unknown> = {
    modelProfileId: options.modelProfileId,
    confirmed: true,
    allowExternalCall: true,
    compileIfMissing: true,
    generationChain: options.generationChain ?? 'production_workspace_v2',
  }
  if (options.target === 'VIDEO') {
    if (options.firstFrameAssetId) body.firstFrameAssetId = options.firstFrameAssetId
    if (options.referenceAssetIds?.length) body.referenceAssetIds = options.referenceAssetIds
  }
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    let detail = ''
    try {
      const payload = await response.json()
      detail = String(payload?.detail?.message || payload?.detail || payload?.error || '').trim()
    } catch {
      detail = await response.text()
    }
    throw new Error(detail || `HTTP ${response.status}`)
  }
  return response.json()
}
