export type CanvasMode = 'production' | 'legacy' | 'dev' | 'prototype'

export const CANVAS_MODE_LABELS: Record<CanvasMode, string> = {
  production: '正式工作台',
  legacy: '旧版生产',
  prototype: '创作沙盘',
  dev: '高级编排',
}

export function resolveDefaultMode(): CanvasMode {
  return 'production'
}
