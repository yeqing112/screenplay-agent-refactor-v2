export interface ProductAssetReferenceStateInput {
  status?: string
  referenceCount: number
  previewCount: number
  selectedReferenceCount: number
  lockedReferenceCount: number
}

export function isProductAssetPendingSelection(input: ProductAssetReferenceStateInput) {
  const status = String(input.status || '').trim().toLowerCase()
  return status !== 'rejected' && input.previewCount > 0 && input.selectedReferenceCount === 0 && input.lockedReferenceCount === 0
}

export function getProductAssetReferenceStatusLabel(input: ProductAssetReferenceStateInput) {
  const status = String(input.status || '').trim().toLowerCase()
  if (status === 'rejected') return '已淘汰'
  if (input.lockedReferenceCount > 0) return '已锁定'
  if (input.selectedReferenceCount > 0) return '可引用'
  if (isProductAssetPendingSelection(input)) return '有图待选'
  if (input.referenceCount > 0) return '记录待补图'
  if (status === 'draft') return '待补图'
  return status || '待处理'
}

export function getProductAssetReferenceSummary(input: ProductAssetReferenceStateInput) {
  if (input.lockedReferenceCount > 0) {
    return `默认 ${input.selectedReferenceCount} / 锁定 ${input.lockedReferenceCount}`
  }
  if (input.selectedReferenceCount > 0) {
    return `默认 ${input.selectedReferenceCount} / 锁定 0`
  }
  if (isProductAssetPendingSelection(input)) {
    return `已预览 ${input.previewCount} / 待定 参考`
  }
  if (input.referenceCount > 0) {
    return `记录 ${input.referenceCount} / 无可预览图`
  }
  return '暂无参考记录'
}
