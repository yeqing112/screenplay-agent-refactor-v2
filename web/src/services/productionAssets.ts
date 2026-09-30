export type ProductionAssetDecision = 'APPROVE' | 'REJECT' | 'REQUEST_CHANGE'

async function readJson(response: Response) {
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(String(payload?.detail?.message || payload?.detail || `HTTP ${response.status}`))
  return payload
}

export async function ingestProductionAsset(bookId: number, assetType: string, entityId: string, file: File, metadata: Record<string, unknown> = {}) {
  const body = new FormData()
  body.set('assetType', assetType)
  body.set('entityId', entityId)
  body.set('metadata', JSON.stringify(metadata))
  body.set('file', file)
  return readJson(await fetch(`/api/books/${bookId}/production-assets/ingest`, { method: 'POST', body }))
}

export async function decideProductionAssetReview(bookId: number, reviewId: string, decision: ProductionAssetDecision, reviewerType = 'DIRECTOR') {
  return readJson(await fetch(`/api/books/${bookId}/production-assets/reviews/${reviewId}/decision`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision, reviewer_type: reviewerType }) }))
}

export async function activateProductionAssetReview(bookId: number, reviewId: string) {
  return readJson(await fetch(`/api/books/${bookId}/production-assets/reviews/${reviewId}/activate`, { method: 'POST' }))
}

export async function readProductionAssetReadiness(bookId: number, storyboardShotId: number) {
  return readJson(await fetch(`/api/books/${bookId}/production-assets/shots/${storyboardShotId}/readiness`, { cache: 'no-store' }))
}

export async function bindProductionAssets(bookId: number, storyboardShotId: number, versions: Record<string, { authority_id: string; version_id: string }>) {
  const characters = Object.entries(versions).filter(([key]) => key.startsWith('CHARACTER:')).map(([, value]) => value)
  const sceneEntry = Object.entries(versions).find(([key]) => key.startsWith('SCENE:'))
  const props = Object.entries(versions).filter(([key]) => key.startsWith('PROP:')).map(([, value]) => value)
  if (!sceneEntry) throw new Error('SCENE 资产仍未准备好。')
  return readJson(await fetch(`/api/books/${bookId}/production-assets/bindings`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ storyboardShotId, characters, scene: sceneEntry[1], props }) }))
}
