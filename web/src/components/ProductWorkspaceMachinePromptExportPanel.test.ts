import { describe, expect, it } from 'vitest'

import { buildH3ProviderSubmitSummaryLines } from './ProductWorkspaceMachinePromptExportPanel'

describe('ProductWorkspaceMachinePromptExportPanel helpers', () => {
  it('summarizes metaso MiniMax H3 confirmed submit settings with first frame', () => {
    const lines = buildH3ProviderSubmitSummaryLines({
      platformLabel: 'metaso.cn MiniMax H3 兼容 API',
      baseUrl: 'https://metaso.cn/api/minimax',
      modelName: 'MiniMax-H3',
      resolution: '768P',
      durationSeconds: 7,
      durationSourceLabel: '分镜 7s',
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
    expect(lines).toContain('规格：768P / 7s / 16:9')
    expect(lines).toContain('时长来源：分镜 7s')
    expect(lines).toContain('模式：首帧图生视频（当前采纳首帧）')
    expect(lines).toContain('AIGC 水印：关闭')
    expect(lines).toContain('Prompt 长度：561 字')
  })

  it('summarizes metaso MiniMax H3 confirmed submit settings with reference images', () => {
    const lines = buildH3ProviderSubmitSummaryLines({
      platformLabel: 'metaso.cn MiniMax H3 兼容 API',
      baseUrl: 'https://metaso.cn/api/minimax',
      modelName: 'MiniMax-H3',
      resolution: '768P',
      durationSeconds: 4,
      aspectRatio: '16:9',
      aigcWatermark: false,
      taskMode: 'reference_to_video',
      referenceImageCount: 3,
      promptLength: 561,
    })

    expect(lines).toContain('模式：多参考视频（3 张参考图）')
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

    expect(lines).toContain('模式：文生视频（当前未检测到可用参考图或采纳首帧）')
    expect(lines).toContain('AIGC 水印：开启')
  })

  it('does not present text-to-video as a valid mode for 75api image-conditioned H3', () => {
    const lines = buildH3ProviderSubmitSummaryLines({
      platformLabel: '75api MiniMax H3',
      baseUrl: 'https://www.75api.com',
      modelName: 'minimax_h3_no_audios',
      provider: '75api-minimax-h3',
      supportsTextToVideo: false,
      resolution: '768p',
      durationSeconds: 6,
      aspectRatio: '16:9',
      aigcWatermark: false,
      taskMode: 'text_to_video',
      promptLength: 300,
    })

    expect(lines).toContain('模式：缺少图片输入（当前模型不支持文生视频，提交会被阻断）')
  })
})
