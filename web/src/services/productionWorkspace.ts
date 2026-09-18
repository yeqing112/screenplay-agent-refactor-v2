import {
  normalizeProductionWorkspaceSnapshot,
  validateProductionWorkspaceSnapshot,
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
