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

export async function fetchProductionWorkspaceV2(bookId: number): Promise<ProductionWorkspaceV2Snapshot> {
  const response = await fetch(`/api/books/${bookId}/production-workspace-v2`)
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const payload = await response.json()
  const errors = validateProductionWorkspaceV2Snapshot(payload)
  if (errors.length > 0) throw new Error(`生产工作区 V2 投影无效：${errors.join('；')}`)
  return normalizeProductionWorkspaceV2Snapshot(payload, bookId)
}
