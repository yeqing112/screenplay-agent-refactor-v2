import {
  normalizeProductionWorkspaceSnapshot,
  type ProductionWorkspaceSnapshot,
} from '../domain/productionWorkspace'

export async function fetchProductionWorkspace(bookId: number): Promise<ProductionWorkspaceSnapshot> {
  const response = await fetch(`/api/books/${bookId}/production-workspace`)
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return normalizeProductionWorkspaceSnapshot(await response.json(), bookId)
}
