import { describe, expect, it } from 'vitest'
import {
  getProductAssetReferenceStatusLabel,
  getProductAssetReferenceSummary,
  isProductAssetPendingSelection,
} from './productWorkspaceAssetReferenceState'

describe('productWorkspaceAssetReferenceState', () => {
  it('marks assets with selected references as ready to reference', () => {
    expect(
      getProductAssetReferenceStatusLabel({
        status: 'ref_ready',
        referenceCount: 1,
        previewCount: 1,
        selectedReferenceCount: 1,
        lockedReferenceCount: 0,
      }),
    ).toBe('可引用')
    expect(
      getProductAssetReferenceSummary({
        status: 'ref_ready',
        referenceCount: 1,
        previewCount: 1,
        selectedReferenceCount: 1,
        lockedReferenceCount: 0,
      }),
    ).toBe('默认 1 / 锁定 0')
  })

  it('marks preview-only assets as pending selection instead of ready', () => {
    const input = {
      status: 'ref_ready',
      referenceCount: 1,
      previewCount: 1,
      selectedReferenceCount: 0,
      lockedReferenceCount: 0,
    }

    expect(isProductAssetPendingSelection(input)).toBe(true)
    expect(getProductAssetReferenceStatusLabel(input)).toBe('有图待选')
    expect(getProductAssetReferenceSummary(input)).toBe('已预览 1 / 待定 参考')
  })

  it('keeps rejected assets explicitly rejected', () => {
    expect(
      getProductAssetReferenceStatusLabel({
        status: 'rejected',
        referenceCount: 2,
        previewCount: 2,
        selectedReferenceCount: 0,
        lockedReferenceCount: 0,
      }),
    ).toBe('已淘汰')
  })

  it('does not treat rejected preview assets as pending selection', () => {
    expect(
      isProductAssetPendingSelection({
        status: 'rejected',
        referenceCount: 1,
        previewCount: 1,
        selectedReferenceCount: 0,
        lockedReferenceCount: 0,
      }),
    ).toBe(false)
  })
})
