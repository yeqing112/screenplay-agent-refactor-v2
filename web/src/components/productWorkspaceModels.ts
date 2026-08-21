import type { ModelCapability, ModelProfileRecord } from '../services/modelRegistry'
import {
  isPoyoHappyHorseModel,
  isPoyoKlingFamilyModel,
} from './poyoModelCatalog'

export interface ModelCapabilitySummary {
  capability: ModelCapability
  defaultLabel: string
  providerLabel: string
  modelName: string
  routeLabel: string
  adapterLabel: string
  configSourceLabel: string
  configNeedsSync: boolean
  readinessLabel: string
  readinessTone: 'ready' | 'warning' | 'blocked'
  usesMock: boolean
  supportsReferenceImages: boolean
  maxReferenceImages: number | null
  taskModes: string[]
  supportsFirstFrame: boolean
  supportsLastFrame: boolean
  supportsAudio: boolean
  supportsImageUrl: boolean
  supportsFileUpload: boolean
  supportsNegativePrompt: boolean
  supportsAsyncTasks: boolean
  pollStrategy: string
}

export function buildCapabilitySummary(
  capability: ModelCapability,
  profile: ModelProfileRecord | null | undefined,
): ModelCapabilitySummary {
  const params = resolveCapabilityParams(profile)
  const taskModes = Array.isArray(params.task_modes)
    ? params.task_modes.filter((item): item is string => typeof item === 'string')
    : []
  const supportsReferenceImages = Boolean(params.supports_reference_images)
  const maxReferenceImages = numberOrNull(params.max_reference_images)
  const pollInterval = numberOrNull(params.poll_interval_seconds)
  const pollTimeout = numberOrNull(params.poll_timeout_seconds)
  const usesMock = Boolean(profile?.uses_mock)

  return {
    capability,
    defaultLabel: profile ? `${profile.name} (${profile.model_name || '未设置模型名'})` : '未配置默认模型',
    providerLabel: profile?.provider || '未配置提供商',
    modelName: profile?.model_name || '未设置模型名',
    routeLabel: buildRouteLabel(capability),
    adapterLabel: buildAdapterLabel(profile),
    configSourceLabel: buildConfigSourceLabel(profile),
    configNeedsSync: shouldSuggestCapabilitySync(profile),
    readinessLabel: buildReadinessLabel(capability, profile),
    readinessTone: buildReadinessTone(capability, profile),
    usesMock,
    supportsReferenceImages,
    maxReferenceImages,
    taskModes,
    supportsFirstFrame: Boolean(params.supports_first_frame),
    supportsLastFrame: Boolean(params.supports_last_frame),
    supportsAudio: Boolean(params.supports_audio),
    supportsImageUrl: Boolean(params.supports_image_url),
    supportsFileUpload: Boolean(params.supports_file_upload),
    supportsNegativePrompt: Boolean(params.supports_negative_prompt),
    supportsAsyncTasks: Boolean(params.supports_async_tasks) || Boolean(pollInterval && pollTimeout),
    pollStrategy:
      pollInterval && pollTimeout
        ? `${pollInterval}s 轮询 / ${pollTimeout}s 超时`
        : usesMock
          ? 'Mock 本地即时返回'
          : '未声明',
  }
}

export function buildReferenceModeLabel(summary: ModelCapabilitySummary) {
  if (!summary.supportsReferenceImages) {
    return '不支持参考图'
  }

  const maxLabel =
    summary.maxReferenceImages && summary.maxReferenceImages > 0
      ? `最多 ${summary.maxReferenceImages} 张`
      : '张数未声明'

  if (summary.capability === 'video') {
    if (summary.supportsFirstFrame && summary.supportsLastFrame) {
      return `支持首尾帧 + 参考图，${maxLabel}`
    }
    if (summary.supportsFirstFrame) {
      return `支持首帧 + 参考图，${maxLabel}`
    }
  }

  return `支持参考图，${maxLabel}`
}

export function buildCapabilityHealthLine(summary: ModelCapabilitySummary) {
  return [
    summary.routeLabel,
    summary.readinessLabel,
    buildReferenceModeLabel(summary),
    summary.supportsAsyncTasks ? '异步任务' : '同步任务',
  ].join(' | ')
}

export function buildTaskModesLabel(taskModes: string[]) {
  return taskModes.length > 0 ? taskModes.join(' / ') : '未声明'
}

export function buildSyncedCapabilityParams(profile: ModelProfileRecord | null | undefined) {
  return {
    ...resolveCapabilityParams(profile),
  }
}

function buildRouteLabel(capability: ModelCapability) {
  if (capability === 'llm') return '用于改编方向、提示词编译与结构化生成'
  if (capability === 'embedding') return '用于检索、召回与上下文辅助'
  if (capability === 'image') return '用于资产参考图与分镜静帧生成'
  return '用于分镜视频生成与交付前视频版本输出'
}

function buildAdapterLabel(profile: ModelProfileRecord | null | undefined) {
  const provider = String(profile?.provider || '').trim()
  if (!provider) return '未配置供应商适配层'
  if (provider === 'prototype-task-adapter') return 'Prototype / Mock 适配层'
  if (provider === 'ollama') return 'Ollama Embedding 适配层'
  if (provider === 'openai-compatible') return 'OpenAI Compatible 适配层'
  if (provider === 'poyo-async') return 'PoYo 异步适配层 + Provider 轮询回收'
  return `${provider} 统一适配层`
}

function buildConfigSourceLabel(profile: ModelProfileRecord | null | undefined) {
  if (!profile) return '未配置'
  if (shouldSuggestCapabilitySync(profile)) return '按已知模型预设补齐'
  if (profile.builtin) return '内置配置'
  return '已显式保存能力字段'
}

function buildReadinessTone(
  capability: ModelCapability,
  profile: ModelProfileRecord | null | undefined,
): ModelCapabilitySummary['readinessTone'] {
  if (!profile) return 'blocked'
  if (!profile.enabled) return 'blocked'
  if (!profile.key_configured && capability !== 'embedding' && !profile.uses_mock) return 'warning'
  if (profile.uses_mock) return capability === 'image' || capability === 'video' ? 'warning' : 'ready'
  return 'ready'
}

function buildReadinessLabel(capability: ModelCapability, profile: ModelProfileRecord | null | undefined) {
  if (!profile) return '未配置默认模型'
  if (!profile.enabled) return '默认模型已禁用'
  if (profile.uses_mock) {
    if (capability === 'image') return '当前使用 Mock 图像链路'
    if (capability === 'video') return '当前使用 Mock 视频链路'
    return '当前使用 Mock 链路'
  }
  if (!profile.key_configured && capability !== 'embedding') {
    return '配置已保存，但未检测到可用密钥'
  }
  return '已配置真实生产链路'
}

function resolveCapabilityParams(profile: ModelProfileRecord | null | undefined) {
  const params = normalizeParams(profile?.default_params)
  const inferred = inferKnownProviderParams(profile)
  if (!inferred) return params

  const merged: Record<string, unknown> = { ...params }
  for (const [key, value] of Object.entries(inferred)) {
    if (!(key in merged)) {
      merged[key] = value
    }
  }
  return merged
}

function shouldSuggestCapabilitySync(profile: ModelProfileRecord | null | undefined) {
  const inferred = inferKnownProviderParams(profile)
  if (!profile || !inferred) return false
  const params = normalizeParams(profile.default_params)
  return Object.keys(inferred).some((key) => !(key in params))
}

function inferKnownProviderParams(profile: ModelProfileRecord | null | undefined) {
  if (!profile) return null
  const provider = String(profile.provider || '').trim()
  const modelName = String(profile.model_name || '').trim()
  if (provider !== 'poyo-async' || !modelName) return null

  if (profile.capability === 'image') {
    const maxReferenceImages = modelName === 'gpt-image-2' ? 8 : 14
    return {
      task_modes: ['text_to_image', 'image_to_image'],
      supports_reference_images: true,
      max_reference_images: maxReferenceImages,
      supports_image_url: true,
      supports_file_upload: false,
      supports_negative_prompt: true,
      supports_async_tasks: true,
      poll_interval_seconds: 3,
      poll_timeout_seconds: 180,
    }
  }

  if (profile.capability !== 'video') return null

  if (isPoyoHappyHorseModel(modelName)) {
    return {
      task_modes: ['text_to_video', 'image_to_video', 'reference_to_video'],
      supports_reference_images: true,
      max_reference_images: 4,
      supports_first_frame: true,
      supports_last_frame: false,
      supports_audio: false,
      supports_image_url: true,
      supports_file_upload: false,
      supports_negative_prompt: false,
      supports_async_tasks: true,
      poll_interval_seconds: 5,
      poll_timeout_seconds: 600,
    }
  }

  if (isPoyoKlingFamilyModel(modelName)) {
    return {
      task_modes: ['image_to_video', 'text_to_video'],
      supports_reference_images: true,
      max_reference_images: 4,
      supports_first_frame: true,
      supports_last_frame: true,
      supports_audio: false,
      supports_image_url: true,
      supports_file_upload: false,
      supports_negative_prompt: false,
      supports_async_tasks: true,
      poll_interval_seconds: 5,
      poll_timeout_seconds: 600,
    }
  }

  return {
    task_modes: ['image_to_video', 'text_to_video'],
    supports_reference_images: true,
    max_reference_images: 4,
    supports_first_frame: true,
    supports_last_frame: true,
    supports_audio: true,
    supports_image_url: true,
    supports_file_upload: false,
    supports_negative_prompt: false,
    supports_asyncTasks: true,
    supports_async_tasks: true,
    poll_interval_seconds: 5,
    poll_timeout_seconds: 600,
  }
}

function normalizeParams(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {}
  }
  return value as Record<string, unknown>
}

function numberOrNull(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}
