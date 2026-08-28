import { describe, expect, it } from 'vitest'

import { buildH3ProviderSubmitSummaryLines } from './ProductWorkspaceMachinePromptExportPanel'

describe('ProductWorkspaceMachinePromptExportPanel helpers', () => {
  it('summarizes metaso MiniMax H3 confirmed submit settings with first frame', () => {
    const lines = buildH3ProviderSubmitSummaryLines({
      platformLabel: 'metaso.cn MiniMax H3 兼容 API',
      baseUrl: 'https://metaso.cn/api/minimax',
      modelName: 'MiniMax-H3',
      resolution: '768P',
      durationSeconds: 5,
      aspectRatio: '16:9',
      aigcWatermark: false,
      taskMode: 'image_to_video',
      firstFrameAssetLabel: '当前采纳首帧',
      firstFrameUrl: 'https://cdn.example.com/frame.png',
      promptLength: 561,
    })

    expect(lines).toContain('平台：metaso.cn MiniMax H3 兼容 API')
    expect(lines).toContain('Base URL：https://metaso.cn/api/minimax')
    expect(lines).toContain('模型：MiniMax-H3')
    expect(lines).toContain('规格：768P / 5s / 16:9')
    expect(lines).toContain('模式：首帧图生视频（当前采纳首帧）')
    expect(lines).toContain('AIGC 水印：关闭')
    expect(lines).toContain('Prompt 长度：561 字')
  })

  it('makes the text-to-video fallback explicit when no adopted first frame exists', () => {
    const lines = buildH3ProviderSubmitSummaryLines({
      platformLabel: 'metaso.cn MiniMax H3 兼容 API',
      baseUrl: 'https://metaso.cn/api/minimax',
      modelName: 'MiniMax-H3',
      resolution: '768P',
      durationSeconds: 5,
      aspectRatio: '16:9',
      aigcWatermark: true,
      taskMode: 'text_to_video',
      promptLength: 300,
    })

    expect(lines).toContain('模式：文生视频（当前未检测到采纳首帧）')
    expect(lines).toContain('AIGC 水印：开启')
  })
})
