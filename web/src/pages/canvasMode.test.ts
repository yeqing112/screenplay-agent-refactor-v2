import { describe, expect, it } from 'vitest'
import { CANVAS_MODE_LABELS, resolveDefaultMode } from './canvasMode'

describe('canvasMode', () => {
  it('keeps the main product entry on the new production workspace', () => {
    expect(resolveDefaultMode()).toBe('production')
  })

  it('separates the new product workspace from the legacy production page', () => {
    expect(CANVAS_MODE_LABELS.production).toBe('正式工作台')
    expect(CANVAS_MODE_LABELS.legacy).toBe('旧版生产')
    expect(CANVAS_MODE_LABELS.prototype).toBe('创作沙盘')
    expect(CANVAS_MODE_LABELS.dev).toBe('高级编排')
  })
})
