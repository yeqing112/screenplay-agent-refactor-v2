import {
  normalizeProductionWorkspaceV2Snapshot,
  validateProductionWorkspaceV2Snapshot,
  normalizeProductionWorkspaceSnapshot,
  validateProductionWorkspaceSnapshot,
  type ProductionWorkspaceV2Snapshot,
  type ProductionWorkspaceSnapshot,
} from '../domain/productionWorkspace'

export async function fetchProductionWorkspace(bookId: number): Promise<ProductionWorkspaceSnapshot> {
  const response = await fetch(`/api/books/${bookId}/production-workspace`)
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const payload = await response.json()
  const errors = validateProductionWorkspaceSnapshot(payload)
  if (errors.length > 0) throw new Error(`生产状态投影无效：${errors.join('；')}`)
  return normalizeProductionWorkspaceSnapshot(payload, bookId)
}

export async function fetchProductionWorkspaceV2(bookId: number, selection?: { imageModelProfileId?: string | null; videoModelProfileId?: string | null }): Promise<ProductionWorkspaceV2Snapshot> {
  const params = new URLSearchParams()
  if (selection?.imageModelProfileId) params.set('image_model_profile_id', selection.imageModelProfileId)
  if (selection?.videoModelProfileId) params.set('video_model_profile_id', selection.videoModelProfileId)
  const query = params.toString()
  const response = await fetch(`/api/books/${bookId}/production-workspace-v2${query ? `?${query}` : ''}`)
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const payload = await response.json()
  const errors = validateProductionWorkspaceV2Snapshot(payload)
  if (errors.length > 0) throw new Error(`生产工作区 V2 投影无效：${errors.join('；')}`)
  return normalizeProductionWorkspaceV2Snapshot(payload, bookId)
}

export async function reconcileCanonicalGeneration(options: { bookId: number; episode: number; shotId: string | number; executionId: string; confirmationToken: string }) {
  const response = await fetch(`/api/books/${options.bookId}/episodes/${options.episode}/shots/${options.shotId}/generation/reconcile`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ execution_id: options.executionId, confirmation_token: options.confirmationToken }),
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return response.json() as Promise<Record<string, unknown>>
}

export class ProductionWorkspaceServiceError extends Error {
  readonly status: number
  readonly code: string | null

  constructor(message: string, status: number, code: string | null = null) {
    super(message)
    this.name = 'ProductionWorkspaceServiceError'
    this.status = status
    this.code = code
  }
}

async function postProductionMediaAuthority(path: string, body?: Record<string, unknown>) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    ...(body ? { body: JSON.stringify(body) } : {}),
  })
  if (!response.ok) {
    let detail = ''
    let code: string | null = null
    try {
      const payload = await response.json()
      const rawDetail = payload?.detail
      code = typeof rawDetail?.code === 'string' ? rawDetail.code : typeof payload?.code === 'string' ? payload.code : null
      detail = String(rawDetail?.message || rawDetail || payload?.message || '').trim()
    } catch {
      detail = await response.text()
    }
    throw new ProductionWorkspaceServiceError(detail || `HTTP ${response.status}`, response.status, code)
  }
  return response.json()
}

/** Validate one immutable MediaCandidate through the canonical authority API. */
export function validateProductionMediaCandidate(candidateId: string) {
  return postProductionMediaAuthority(`/api/media-authority/candidates/${encodeURIComponent(candidateId)}/validate`)
}

/** Promote one validated MediaCandidate through the canonical authority API. */
export function promoteProductionMediaCandidate(candidateId: string, validationId: string) {
  return postProductionMediaAuthority('/api/media-authority/promote', {
    candidate_id: candidateId,
    validation_id: validationId,
    confirmation: true,
  })
}

/**
 * Record an explicit human APPROVE decision through the existing asset
 * promotion contract. This is intentionally separate from the legacy
 * confirmation-only wrapper used by the older production panel.
 */
export function approveProductionMediaCandidate(
  candidateId: string,
  validationId: string,
  options: { reviewer?: string; reviewNotes?: string; promotionId?: string } = {},
) {
  return postProductionMediaAuthority(`/api/assets/candidates/${encodeURIComponent(candidateId)}/promote`, {
    validation_id: validationId,
    promotion_id: options.promotionId,
    reviewer: options.reviewer || 'shot-studio-human',
    decision: 'APPROVE',
    review_notes: options.reviewNotes || 'Approved from Shot Studio Review Desk.',
    confirmation: true,
  })
}
