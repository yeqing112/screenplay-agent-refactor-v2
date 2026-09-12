import { describe, expect, it } from 'vitest'

import {
  buildPoyoPresetProfiles,
  buildShapiPresetProfiles,
  getLlmFieldValues,
  getPoyoFieldValues,
  providerOptionsForCapability,
  recommendedPoyoPresetId,
  suggestedBaseUrlForProvider,
  suggestedDefaultParamsText,
  updateLlmDefaultParamsText,
  suggestedPoyoModelNames,
  updatePoyoDefaultParamsText,
} from './ModelRegistryModal'

describe('ModelRegistryModal helpers', () => {
  it('offers poyo-async as a selectable provider for image and video capabilities', () => {
    expect(providerOptionsForCapability('image')).toContain('poyo-async')
    expect(providerOptionsForCapability('video')).toContain('poyo-async')
    expect(providerOptionsForCapability('video')).toContain('minimax-h3-async')
    expect(providerOptionsForCapability('video')).toContain('75api-minimax-h3')
    expect(providerOptionsForCapability('image')).not.toContain('minimax-h3-async')
    expect(providerOptionsForCapability('llm')).not.toContain('poyo-async')
    expect(providerOptionsForCapability('embedding')).not.toContain('poyo-async')
    expect(providerOptionsForCapability('image')).toContain('shapi-gemini-image')
    expect(providerOptionsForCapability('image')).toContain('shapi-openai-images')
    expect(providerOptionsForCapability('video')).not.toContain('shapi-gemini-image')
  })

  it('keeps GPT Image 2 as the image default and leaves video waiting for MiniMax H3', () => {
    expect(recommendedPoyoPresetId('image')).toBe('preset-poyo-image-gpt-image-2')
    expect(recommendedPoyoPresetId('video')).toBe('')
  })

  it('builds eight PoYo preset profiles with recommended defaults and capabilities', () => {
    const presets = buildPoyoPresetProfiles()

    expect(presets).toHaveLength(8)
    expect(presets.every((item) => item.provider === 'poyo-async')).toBe(true)

    const seedream = presets.find((item) => item.id === 'preset-poyo-image-seedream-5-lite')
    expect(seedream?.capability).toBe('image')
    expect(seedream?.default_params.max_reference_images).toBe(14)

    const seedance = presets.find((item) => item.id === 'preset-poyo-video-seedance-2')
    expect(seedance?.capability).toBe('video')
    expect(seedance?.default_params.supports_first_frame).toBe(true)
    expect(seedance?.default_params.supports_last_frame).toBe(true)
    expect(seedance?.default_params.supports_audio).toBe(true)

    const klingPro = presets.find((item) => item.id === 'preset-poyo-video-kling-3-pro')
    expect(klingPro?.default_params.resolution).toBe('1080p')

    const kling4k = presets.find((item) => item.id === 'preset-poyo-video-kling-3-4k')
    expect(kling4k?.model_name).toBe('kling-3.0/4K')

    const happyHorse = presets.find((item) => item.id === 'preset-poyo-video-happy-horse-1-1')
    expect(happyHorse?.model_name).toBe('happy-horse-1-1')
    expect(happyHorse?.default_params.task_mode).toBe('reference_to_video')
  })

  it('builds SHAPI image presets with distinct transports and safe reference contracts', () => {
    const presets = buildShapiPresetProfiles()
    expect(presets).toHaveLength(1)
    expect(presets.find((item) => item.model_name === 'nano-banana-2')).toBeUndefined()

    const gpt = presets.find((item) => item.id === 'preset-shapi-image-gpt-image-2')
    expect(gpt?.provider).toBe('shapi-openai-images')
    expect(gpt?.base_url).toBe('https://shapi.vip/v1')
    expect(gpt?.default_params.supports_reference_images).toBe(false)
    expect(gpt?.default_params.response_format).toBe('b64_json')
  })

  it('suggests poyo-specific base url and default params when provider is poyo-async', () => {
    expect(suggestedBaseUrlForProvider('poyo-async')).toBe('https://api.poyo.ai')
    expect(suggestedBaseUrlForProvider('minimax-h3-async')).toBe('https://metaso.cn/api/minimax')
    expect(suggestedBaseUrlForProvider('75api-minimax-h3')).toBe('https://www.75api.com')
    expect(suggestedBaseUrlForProvider('shapi-gemini-image')).toBe('https://shapi.vip')
    expect(suggestedBaseUrlForProvider('shapi-openai-images')).toBe('https://shapi.vip/v1')
    expect(suggestedBaseUrlForProvider('openai-compatible')).toBe('')
    expect(suggestedPoyoModelNames('image')).toContain('seedream-5-0-lite-api')
    expect(suggestedPoyoModelNames('image')).toContain('nano-banana-2')
    expect(suggestedPoyoModelNames('video')).toContain('seedance-2')
    expect(suggestedPoyoModelNames('video')).toContain('kling-3-api')
    expect(suggestedPoyoModelNames('video')).toContain('kling-3.0/pro')
    expect(suggestedPoyoModelNames('video')).toContain('kling-3.0/4K')

    const imageDefaults = suggestedDefaultParamsText('image', 'poyo-async')
    expect(imageDefaults).toContain('"supports_reference_images": true')
    expect(imageDefaults).toContain('"max_reference_images": 14')

    const videoDefaults = suggestedDefaultParamsText('video', 'poyo-async')
    expect(videoDefaults).toContain('"supports_first_frame": true')
    expect(videoDefaults).toContain('"supports_last_frame": true')
    expect(videoDefaults).toContain('"supports_audio": true')

    const nanoDefaults = suggestedDefaultParamsText('image', 'shapi-gemini-image')
    expect(nanoDefaults).toContain('"transport": "gemini-generate-content"')
    expect(nanoDefaults).toContain('"max_reference_images": 14')

    const gptDefaults = suggestedDefaultParamsText('image', 'shapi-openai-images')
    expect(gptDefaults).toContain('"supports_reference_images": false')
    expect(gptDefaults).toContain('"transport": "openai-images-generations"')
  })

  it('suggests MiniMax H3 async defaults with explicit mutually-exclusive input capabilities', () => {
    const h3Defaults = suggestedDefaultParamsText('video', 'minimax-h3-async', 'MiniMax-H3')
    const parsed = JSON.parse(h3Defaults)

    expect(parsed.task_modes).toEqual(['text_to_video', 'image_to_video', 'reference_to_video'])
    expect(parsed.supports_first_frame).toBe(true)
    expect(parsed.supports_last_frame).toBe(true)
    expect(parsed.supports_reference_images).toBe(true)
    expect(parsed.max_reference_images).toBe(9)
    expect(parsed.video_capabilities.reference_and_keyframe_compatible).toBe(false)
    expect(parsed.video_capabilities.evidence_status).toBe('confirmed')
    expect(parsed.resolution).toBe('768P')
    expect(parsed.duration).toBe(5)
    expect(parsed.ratio).toBe('16:9')
    expect(parsed.aigc_watermark).toBe(false)
    expect(parsed.poll_timeout_seconds).toBe(900)
  })

  it('suggests 75api H3 defaults without text-to-video or audio capabilities', () => {
    const defaults = JSON.parse(suggestedDefaultParamsText('video', '75api-minimax-h3', 'minimax_h3_no_audios'))
    expect(defaults.task_modes).toEqual(['image_to_video', 'reference_to_video'])
    expect(defaults.supports_text_to_video).toBe(false)
    expect(defaults.supports_audio).toBe(false)
    expect(defaults.max_reference_images).toBe(8)
    expect(defaults.resolution).toBe('768p')
    expect(defaults.seconds).toBe(5)
    expect(defaults.aspect_ratio).toBe('16:9')
  })

  it('defaults LLM thinking to disabled and updates it through structured helper fields', () => {
    const llmDefaults = suggestedDefaultParamsText('llm', 'openai-compatible')
    const parsedDefaults = JSON.parse(llmDefaults)

    expect(parsedDefaults.thinking).toEqual({ type: 'disabled' })
    expect(getLlmFieldValues(llmDefaults).thinkingType).toBe('disabled')
    expect(getLlmFieldValues(llmDefaults).supportsVision).toBe(false)
    expect(getLlmFieldValues('{"thinking": {"type": "enabled"}}').thinkingType).toBe('enabled')
    expect(getLlmFieldValues('{"supports_vision": true}').supportsVision).toBe(true)

    const enabledText = updateLlmDefaultParamsText(llmDefaults, { thinkingType: 'enabled' })
    expect(JSON.parse(enabledText).thinking).toEqual({ type: 'enabled' })

    const disabledText = updateLlmDefaultParamsText(enabledText, { thinkingType: 'disabled' })
    expect(JSON.parse(disabledText).thinking).toEqual({ type: 'disabled' })
    expect(JSON.parse(updateLlmDefaultParamsText(llmDefaults, { supportsVision: true })).supports_vision).toBe(true)
  })

  it('adjusts poyo defaults based on the chosen model name', () => {
    const gptImageDefaults = suggestedDefaultParamsText('image', 'poyo-async', 'gpt-image-2')
    expect(gptImageDefaults).toContain('"max_reference_images": 8')

    const happyHorseDefaults = suggestedDefaultParamsText('video', 'poyo-async', 'happy-horse-1-1')
    expect(happyHorseDefaults).toContain('"reference_to_video"')
    expect(happyHorseDefaults).toContain('"supports_last_frame": false')
    expect(happyHorseDefaults).toContain('"supports_audio": false')

    const klingDefaults = suggestedDefaultParamsText('video', 'poyo-async', 'kling-3-api')
    expect(klingDefaults).toContain('"supports_first_frame": true')
    expect(klingDefaults).toContain('"supports_audio": false')
  })

  it('updates poyo helper fields back into the JSON payload', () => {
    const nextText = updatePoyoDefaultParamsText(
      'video',
      suggestedDefaultParamsText('video', 'poyo-async'),
      {
        supportsAudio: false,
        supportsLastFrame: false,
        maxReferenceImages: 2,
        pollTimeoutSeconds: 120,
        taskModes: ['text_to_video'],
      },
    )

    const nextValues = getPoyoFieldValues('video', nextText)
    expect(nextValues.supportsAudio).toBe(false)
    expect(nextValues.supportsLastFrame).toBe(false)
    expect(nextValues.maxReferenceImages).toBe(2)
    expect(nextValues.pollTimeoutSeconds).toBe(120)
    expect(nextValues.taskModes).toEqual(['text_to_video'])
  })
})
