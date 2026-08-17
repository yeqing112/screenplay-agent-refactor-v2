import { describe, expect, it } from 'vitest'
import { buildCanvasHandoffSummary } from './ProductWorkspaceSectionContent'

describe('buildCanvasHandoffSummary', () => {
  it('prefers canvas-provided handoff copy for asset continuation', () => {
    const summary = buildCanvasHandoffSummary({
      target: 'assets',
      episode: 1,
      shotId: '3',
      assetId: 'character-1',
      assetLabel: '小和尚',
      handoffLabel: '前往资产中心补齐该镜头参考图',
      handoffDetail: '带着镜头和人物上下文继续补图。',
    })

    expect(summary).toMatchObject({
      title: '当前承接：第 1 集 / 镜头 3 / 小和尚',
      label: '前往资产中心补齐该镜头参考图',
      detail: '带着镜头和人物上下文继续补图。',
    })
  })

  it('falls back to default delivery copy when canvas does not provide custom text', () => {
    const summary = buildCanvasHandoffSummary({
      target: 'delivery',
      episode: 2,
    })

    expect(summary).toMatchObject({
      title: '当前承接：第 2 集',
      label: '前往导出中心确认当前集交付状态',
    })
  })
})
