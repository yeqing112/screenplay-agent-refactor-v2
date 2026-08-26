import { describe, expect, it } from 'vitest'
import {
  buildCapabilityHealthLine,
  buildCapabilitySummary,
  buildReferenceModeLabel,
  buildSyncedCapabilityParams,
  buildTaskModesLabel,
} from './productWorkspaceModels'

describe('productWorkspaceModels', () => {
  it('summarizes LLM thinking mode for model management visibility', () => {
    const summary = buildCapabilitySummary('llm', {
      id: 'llm-mimo',
      name: 'Mimo 2.5',
      capability: 'llm',
      provider: 'openai-compatible',
      base_url: 'https://api.xiaomimimo.com/v1',
      model_name: 'mimo-v2.5',
      default_params: {
        temperature: 0.3,
        max_tokens: 8192,
        thinking: { type: 'disabled' },
      },
      enabled: true,
      is_default: true,
      key_configured: true,
      builtin: false,
      source: 'saved',
      uses_mock: false,
    })

    expect(summary.llmThinkingLabel).toBe('思考关闭')
    expect(buildCapabilityHealthLine(summary)).toContain('思考关闭')
  })

  it('builds an image capability summary with explicit integration capability flags', () => {
    const summary = buildCapabilitySummary('image', {
      id: 'img-1',
      name: 'PoYo Seedream 5 Lite',
      capability: 'image',
      provider: 'poyo-async',
      base_url: 'https://api.poyo.ai',
      model_name: 'seedream-5-0-lite-api',
      default_params: {
        task_modes: ['text_to_image', 'image_to_image'],
        supports_reference_images: true,
        max_reference_images: 14,
        supports_image_url: true,
        supports_file_upload: false,
        supports_negative_prompt: true,
        supports_async_tasks: true,
        poll_interval_seconds: 3,
        poll_timeout_seconds: 180,
      },
      enabled: true,
      is_default: true,
      key_configured: true,
      builtin: false,
      source: 'saved',
      uses_mock: false,
    })

    expect(summary.defaultLabel).toContain('PoYo Seedream 5 Lite')
    expect(summary.taskModes).toEqual(['text_to_image', 'image_to_image'])
    expect(summary.supportsReferenceImages).toBe(true)
    expect(summary.maxReferenceImages).toBe(14)
    expect(summary.supportsImageUrl).toBe(true)
    expect(summary.supportsFileUpload).toBe(false)
    expect(summary.supportsNegativePrompt).toBe(true)
    expect(summary.supportsAsyncTasks).toBe(true)
    expect(summary.routeLabel).toContain('资产参考图')
    expect(summary.readinessLabel).toBe('已配置真实生产链路')
    expect(summary.adapterLabel).toContain('PoYo')
    expect(summary.configSourceLabel).toBe('已显式保存能力字段')
    expect(buildReferenceModeLabel(summary)).toContain('最多 14 张')
    expect(buildCapabilityHealthLine(summary)).toContain('已配置真实生产链路')
    expect(buildCapabilityHealthLine(summary)).toContain('异步任务')
    expect(buildTaskModesLabel(summary.taskModes)).toBe('text_to_image / image_to_image')
  })

  it('builds a video capability summary with first/last frame and async support', () => {
    const summary = buildCapabilitySummary('video', {
      id: 'video-1',
      name: 'PoYo Seedance 2',
      capability: 'video',
      provider: 'poyo-async',
      base_url: 'https://api.poyo.ai',
      model_name: 'seedance-2',
      default_params: {
        task_modes: ['image_to_video', 'text_to_video'],
        supports_reference_images: true,
        max_reference_images: 4,
        supports_first_frame: true,
        supports_last_frame: true,
        supports_audio: true,
        supports_image_url: true,
        supports_file_upload: false,
        supports_negative_prompt: false,
        supports_async_tasks: true,
        poll_interval_seconds: 5,
        poll_timeout_seconds: 600,
      },
      enabled: true,
      is_default: true,
      key_configured: true,
      builtin: false,
      source: 'saved',
      uses_mock: false,
    })

    expect(summary.supportsFirstFrame).toBe(true)
    expect(summary.supportsLastFrame).toBe(true)
    expect(summary.supportsAudio).toBe(true)
    expect(summary.supportsImageUrl).toBe(true)
    expect(summary.supportsAsyncTasks).toBe(true)
    expect(summary.pollStrategy).toBe('5s 轮询 / 600s 超时')
    expect(buildReferenceModeLabel(summary)).toContain('支持首尾帧 + 参考图')
  })

  it('marks mock video defaults as warnings instead of ready production', () => {
    const summary = buildCapabilitySummary('video', {
      id: 'video-mock',
      name: 'Mock Video',
      capability: 'video',
      provider: 'prototype-task-adapter',
      base_url: '',
      model_name: 'mock-video-v1',
      default_params: {
        duration_seconds: 5,
      },
      enabled: true,
      is_default: true,
      key_configured: true,
      builtin: true,
      source: 'builtin',
      uses_mock: true,
    })

    expect(summary.usesMock).toBe(true)
    expect(summary.readinessTone).toBe('warning')
    expect(summary.readinessLabel).toBe('当前使用 Mock 视频链路')
    expect(summary.pollStrategy).toBe('Mock 本地即时返回')
    expect(summary.supportsAsyncTasks).toBe(false)
  })

  it('fills known poyo capability fields when saved defaults are stale', () => {
    const summary = buildCapabilitySummary('image', {
      id: 'img-stale',
      name: 'PoYo GPT Image 2',
      capability: 'image',
      provider: 'poyo-async',
      base_url: 'https://api.poyo.ai',
      model_name: 'gpt-image-2',
      default_params: {
        task_modes: ['text_to_image', 'image_to_image'],
        supports_reference_images: true,
        max_reference_images: 8,
      },
      enabled: true,
      is_default: true,
      key_configured: true,
      builtin: false,
      source: 'saved',
      uses_mock: false,
    })

    expect(summary.supportsImageUrl).toBe(true)
    expect(summary.supportsNegativePrompt).toBe(true)
    expect(summary.supportsAsyncTasks).toBe(true)
    expect(summary.configNeedsSync).toBe(true)
    expect(summary.configSourceLabel).toBe('按已知模型预设补齐')

    expect(buildSyncedCapabilityParams({
      id: 'video-stale',
      name: 'PoYo Happy Horse 1.1',
      capability: 'video',
      provider: 'poyo-async',
      base_url: 'https://api.poyo.ai',
      model_name: 'happy-horse-1-1',
      default_params: {},
      enabled: true,
      is_default: true,
      key_configured: true,
      builtin: false,
      source: 'saved',
      uses_mock: false,
    })).toMatchObject({
      supports_first_frame: true,
      supports_last_frame: false,
      supports_audio: false,
      supports_reference_images: true,
      supports_image_url: true,
    })
  })

  it('keeps legacy poyo aliases compatible with the normalized capability rules', () => {
    const legacySeedream = buildCapabilitySummary('image', {
      id: 'img-legacy',
      name: 'Legacy Seedream',
      capability: 'image',
      provider: 'poyo-async',
      base_url: 'https://api.poyo.ai',
      model_name: 'seedream-5.0-lite',
      default_params: {},
      enabled: true,
      is_default: true,
      key_configured: true,
      builtin: false,
      source: 'saved',
      uses_mock: false,
    })

    const legacyHappyHorse = buildCapabilitySummary('video', {
      id: 'video-legacy',
      name: 'Legacy Happy Horse',
      capability: 'video',
      provider: 'poyo-async',
      base_url: 'https://api.poyo.ai',
      model_name: 'happy-horse-1.1',
      default_params: {},
      enabled: true,
      is_default: true,
      key_configured: true,
      builtin: false,
      source: 'saved',
      uses_mock: false,
    })

    expect(legacySeedream.supportsNegativePrompt).toBe(true)
    expect(legacyHappyHorse.supportsLastFrame).toBe(false)
    expect(legacyHappyHorse.supportsAudio).toBe(false)
  })
})
