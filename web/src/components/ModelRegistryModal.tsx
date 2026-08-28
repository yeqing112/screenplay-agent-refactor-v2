import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  saveModelRegistry,
  testModelProfile,
  type ModelCapability,
  type ModelProfileRecord,
  type ModelRegistryPayload,
} from '../services/modelRegistry'
import {
  isPoyoHappyHorseModel,
  isPoyoKlingFamilyModel,
  POYO_IMAGE_MODEL_SUGGESTIONS,
  POYO_VIDEO_MODEL_SUGGESTIONS,
} from './poyoModelCatalog'

type EditableProfileDraft = {
  id?: string
  name: string
  capability: ModelCapability
  provider: string
  base_url: string
  model_name: string
  api_key: string
  default_params_text: string
  enabled: boolean
}

type FeedbackTone = 'info' | 'success' | 'error'
type TestResultMeta = { tone: FeedbackTone; text: string }
type ProfileFilter = 'all' | 'default' | 'missing-key' | 'live'
type LlmThinkingType = 'enabled' | 'disabled'

const MOCK_PROVIDER = 'prototype-task-adapter'
const POYO_ASYNC_PROVIDER = 'poyo-async'
const MINIMAX_H3_ASYNC_PROVIDER = 'minimax-h3-async'

const CAPABILITY_LABELS: Record<ModelCapability, string> = {
  llm: 'LLM',
  embedding: 'Embedding',
  image: 'Image',
  video: 'Video',
}

function isMockProvider(provider: string) {
  return provider.trim() === MOCK_PROVIDER
}

function isPoyoAsyncProvider(provider: string) {
  return provider.trim() === POYO_ASYNC_PROVIDER
}

function isMiniMaxH3AsyncProvider(provider: string) {
  return provider.trim() === MINIMAX_H3_ASYNC_PROVIDER
}

function canUseAsDefault(profile: Pick<ModelProfileRecord, 'capability' | 'provider' | 'uses_mock'>) {
  if (profile.capability !== 'video') return true
  return profile.uses_mock || isPoyoAsyncProvider(profile.provider) || isMiniMaxH3AsyncProvider(profile.provider)
}

export function providerOptionsForCapability(capability: ModelCapability) {
  if (capability === 'embedding') return ['ollama']
  if (capability === 'llm') return ['openai-compatible']
  return capability === 'video'
    ? [MOCK_PROVIDER, 'openai-compatible', POYO_ASYNC_PROVIDER, MINIMAX_H3_ASYNC_PROVIDER]
    : [MOCK_PROVIDER, 'openai-compatible', POYO_ASYNC_PROVIDER]
}

export function buildPoyoPresetProfiles(): ModelProfileRecord[] {
  const base_url = 'https://api.poyo.ai'
  return [
    {
      id: 'preset-poyo-image-gpt-image-2',
      name: 'PoYo GPT Image 2',
      capability: 'image',
      provider: POYO_ASYNC_PROVIDER,
      base_url,
      model_name: 'gpt-image-2',
      default_params: {
        task_mode: 'text_to_image',
        task_modes: ['text_to_image', 'image_to_image'],
        supports_reference_images: true,
        max_reference_images: 8,
        supports_image_url: true,
        supports_file_upload: false,
        supports_negative_prompt: true,
        supports_async_tasks: true,
        poll_interval_seconds: 3,
        poll_timeout_seconds: 180,
      },
      enabled: true,
      is_default: false,
      key_configured: false,
      builtin: false,
      source: 'saved',
      uses_mock: false,
    },
    {
      id: 'preset-poyo-image-nano-banana-2-new',
      name: 'PoYo Nano Banana 2',
      capability: 'image',
      provider: POYO_ASYNC_PROVIDER,
      base_url,
      model_name: 'nano-banana-2',
      default_params: {
        task_mode: 'text_to_image',
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
      is_default: false,
      key_configured: false,
      builtin: false,
      source: 'saved',
      uses_mock: false,
    },
    {
      id: 'preset-poyo-image-seedream-5-lite',
      name: 'PoYo Seedream 5 Lite',
      capability: 'image',
      provider: POYO_ASYNC_PROVIDER,
      base_url,
      model_name: 'seedream-5-0-lite-api',
      default_params: {
        task_mode: 'text_to_image',
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
      is_default: false,
      key_configured: false,
      builtin: false,
      source: 'saved',
      uses_mock: false,
    },
    {
      id: 'preset-poyo-video-seedance-2',
      name: 'PoYo Seedance 2',
      capability: 'video',
      provider: POYO_ASYNC_PROVIDER,
      base_url,
      model_name: 'seedance-2',
      default_params: {
        task_mode: 'image_to_video',
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
      is_default: false,
      key_configured: false,
      builtin: false,
      source: 'saved',
      uses_mock: false,
    },
    {
      id: 'preset-poyo-video-kling-3-standard',
      name: 'PoYo Kling 3 Standard',
      capability: 'video',
      provider: POYO_ASYNC_PROVIDER,
      base_url,
      model_name: 'kling-3.0/standard',
      default_params: {
        task_mode: 'image_to_video',
        task_modes: ['image_to_video', 'text_to_video'],
        supports_reference_images: true,
        max_reference_images: 4,
        supports_first_frame: true,
        supports_last_frame: true,
        resolution: '720p',
        supports_image_url: true,
        supports_file_upload: false,
        supports_negative_prompt: false,
        supports_async_tasks: true,
        poll_interval_seconds: 5,
        poll_timeout_seconds: 600,
      },
      enabled: true,
      is_default: false,
      key_configured: false,
      builtin: false,
      source: 'saved',
      uses_mock: false,
    },
    {
      id: 'preset-poyo-video-kling-3-pro',
      name: 'PoYo Kling 3 API',
      capability: 'video',
      provider: POYO_ASYNC_PROVIDER,
      base_url,
      model_name: 'kling-3-api',
      default_params: {
        task_mode: 'image_to_video',
        task_modes: ['image_to_video', 'text_to_video'],
        supports_reference_images: true,
        max_reference_images: 4,
        supports_first_frame: true,
        supports_last_frame: true,
        resolution: '1080p',
        supports_image_url: true,
        supports_file_upload: false,
        supports_negative_prompt: false,
        supports_async_tasks: true,
        poll_interval_seconds: 5,
        poll_timeout_seconds: 600,
      },
      enabled: true,
      is_default: false,
      key_configured: false,
      builtin: false,
      source: 'saved',
      uses_mock: false,
    },
    {
      id: 'preset-poyo-video-kling-3-4k',
      name: 'PoYo Kling 3 4K',
      capability: 'video',
      provider: POYO_ASYNC_PROVIDER,
      base_url,
      model_name: 'kling-3.0/4K',
      default_params: {
        task_mode: 'image_to_video',
        task_modes: ['image_to_video', 'text_to_video'],
        supports_reference_images: true,
        max_reference_images: 4,
        supports_first_frame: true,
        supports_last_frame: true,
        resolution: '4K',
        supports_image_url: true,
        supports_file_upload: false,
        supports_negative_prompt: false,
        supports_async_tasks: true,
        poll_interval_seconds: 5,
        poll_timeout_seconds: 600,
      },
      enabled: true,
      is_default: false,
      key_configured: false,
      builtin: false,
      source: 'saved',
      uses_mock: false,
    },
    {
      id: 'preset-poyo-video-happy-horse-1-1',
      name: 'PoYo Happy Horse 1.1',
      capability: 'video',
      provider: POYO_ASYNC_PROVIDER,
      base_url,
      model_name: 'happy-horse-1-1',
      default_params: {
        task_mode: 'reference_to_video',
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
      },
      enabled: true,
      is_default: false,
      key_configured: false,
      builtin: false,
      source: 'saved',
      uses_mock: false,
    },
  ]
}

export function suggestedBaseUrlForProvider(provider: string) {
  if (isMiniMaxH3AsyncProvider(provider)) return 'https://metaso.cn/api/minimax'
  return isPoyoAsyncProvider(provider) ? 'https://api.poyo.ai' : ''
}

export function suggestedPoyoModelNames(capability: ModelCapability) {
  return capability === 'image'
    ? [...POYO_IMAGE_MODEL_SUGGESTIONS]
    : [...POYO_VIDEO_MODEL_SUGGESTIONS]
}

export function recommendedPoyoPresetId(capability: Extract<ModelCapability, 'image' | 'video'>) {
  return capability === 'image' ? 'preset-poyo-image-gpt-image-2' : ''
}

export function recommendedPoyoPresetLabel(capability: Extract<ModelCapability, 'image' | 'video'>) {
  return capability === 'image' ? 'PoYo GPT Image 2' : 'MiniMax H3'
}

export function suggestedDefaultParamsText(capability: ModelCapability, provider: string, modelName = '') {
  if (capability === 'llm') return `{\n  "temperature": 0.3,\n  "max_tokens": 8192,\n  "thinking": {\n    "type": "disabled"\n  }\n}`
  if (capability === 'embedding') return `{\n  "dimension": 768\n}`
  if (capability === 'image') {
    if (isPoyoAsyncProvider(provider)) {
      const maxReferenceImages = modelName === 'gpt-image-2' ? 8 : 14
      return `{\n  "task_modes": ["text_to_image", "image_to_image"],\n  "supports_reference_images": true,\n  "max_reference_images": ${maxReferenceImages},\n  "supports_image_url": true,\n  "supports_file_upload": false,\n  "supports_negative_prompt": true,\n  "supports_async_tasks": true,\n  "poll_interval_seconds": 3,\n  "poll_timeout_seconds": 180\n}`
    }
    return `{\n  "size": "1024x1024"\n}`
  }
  if (isPoyoAsyncProvider(provider)) {
    if (isPoyoHappyHorseModel(modelName)) {
      return `{\n  "task_modes": ["text_to_video", "image_to_video", "reference_to_video"],\n  "supports_reference_images": true,\n  "max_reference_images": 4,\n  "supports_first_frame": true,\n  "supports_last_frame": false,\n  "supports_audio": false,\n  "supports_image_url": true,\n  "supports_file_upload": false,\n  "supports_negative_prompt": false,\n  "supports_async_tasks": true,\n  "poll_interval_seconds": 5,\n  "poll_timeout_seconds": 600\n}`
    }
    if (isPoyoKlingFamilyModel(modelName)) {
      return `{\n  "task_modes": ["image_to_video", "text_to_video"],\n  "supports_reference_images": true,\n  "max_reference_images": 4,\n  "supports_first_frame": true,\n  "supports_last_frame": true,\n  "supports_audio": false,\n  "supports_image_url": true,\n  "supports_file_upload": false,\n  "supports_negative_prompt": false,\n  "supports_async_tasks": true,\n  "poll_interval_seconds": 5,\n  "poll_timeout_seconds": 600\n}`
    }
    return `{\n  "task_modes": ["image_to_video", "text_to_video"],\n  "supports_reference_images": true,\n  "max_reference_images": 4,\n  "supports_first_frame": true,\n  "supports_last_frame": true,\n  "supports_audio": true,\n  "supports_image_url": true,\n  "supports_file_upload": false,\n  "supports_negative_prompt": false,\n  "supports_async_tasks": true,\n  "poll_interval_seconds": 5,\n  "poll_timeout_seconds": 600\n}`
  }
  if (isMiniMaxH3AsyncProvider(provider)) {
    return `{\n  "task_modes": ["text_to_video", "image_to_video"],\n  "supports_reference_images": false,\n  "max_reference_images": 0,\n  "supports_first_frame": true,\n  "supports_last_frame": true,\n  "supports_audio": false,\n  "supports_image_url": true,\n  "supports_file_upload": false,\n  "supports_negative_prompt": false,\n  "supports_async_tasks": true,\n  "resolution": "768P",\n  "duration": 5,\n  "ratio": "16:9",\n  "aigc_watermark": false,\n  "poll_interval_seconds": 5,\n  "poll_timeout_seconds": 900\n}`
  }
  return `{\n  "duration_seconds": 5\n}`
}

function safeParseDefaultParamsText(text: string) {
  const raw = text.trim()
  if (!raw) return {} as Record<string, unknown>
  try {
    const parsed = JSON.parse(raw)
    return parsed && !Array.isArray(parsed) && typeof parsed === 'object'
      ? parsed as Record<string, unknown>
      : {}
  } catch {
    return {}
  }
}

function stringifyDefaultParams(params: Record<string, unknown>) {
  return JSON.stringify(params, null, 2)
}

function normalizeLlmThinkingType(value: unknown): LlmThinkingType {
  if (value === 'enabled') return 'enabled'
  if (value === 'disabled') return 'disabled'
  if (typeof value === 'boolean') return value ? 'enabled' : 'disabled'
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const type = (value as Record<string, unknown>).type
    return type === 'enabled' ? 'enabled' : 'disabled'
  }
  return 'disabled'
}

export function getLlmFieldValues(defaultParamsText: string) {
  const params = safeParseDefaultParamsText(defaultParamsText)
  return {
    thinkingType: normalizeLlmThinkingType(params.thinking),
  }
}

export function updateLlmDefaultParamsText(
  defaultParamsText: string,
  updates: Partial<ReturnType<typeof getLlmFieldValues>>,
) {
  const current = safeParseDefaultParamsText(defaultParamsText)
  const nextValues = { ...getLlmFieldValues(defaultParamsText), ...updates }
  return stringifyDefaultParams({
    ...current,
    thinking: {
      type: nextValues.thinkingType,
    },
  })
}

function buildLlmThinkingLabel(defaultParams: unknown) {
  const params = defaultParams && typeof defaultParams === 'object' && !Array.isArray(defaultParams)
    ? defaultParams as Record<string, unknown>
    : {}
  return normalizeLlmThinkingType(params.thinking) === 'enabled' ? '思考：开启' : '思考：关闭'
}

export function getPoyoFieldValues(capability: ModelCapability, defaultParamsText: string) {
  const params = safeParseDefaultParamsText(defaultParamsText)
  const taskModes = Array.isArray(params.task_modes)
    ? params.task_modes.filter((item): item is string => typeof item === 'string')
    : []
  return {
    taskModes,
    supportsReferenceImages: Boolean(params.supports_reference_images),
    maxReferenceImages: Number(params.max_reference_images ?? (capability === 'image' ? 14 : 4)),
    supportsFirstFrame: Boolean(params.supports_first_frame),
    supportsLastFrame: Boolean(params.supports_last_frame),
    supportsAudio: Boolean(params.supports_audio),
    pollIntervalSeconds: Number(params.poll_interval_seconds ?? (capability === 'image' ? 3 : 5)),
    pollTimeoutSeconds: Number(params.poll_timeout_seconds ?? (capability === 'image' ? 180 : 600)),
  }
}

export function updatePoyoDefaultParamsText(
  capability: ModelCapability,
  defaultParamsText: string,
  updates: Partial<ReturnType<typeof getPoyoFieldValues>>,
) {
  const current = safeParseDefaultParamsText(defaultParamsText)
  const nextValues = { ...getPoyoFieldValues(capability, defaultParamsText), ...updates }
  const nextParams: Record<string, unknown> = {
    ...current,
    task_modes: nextValues.taskModes,
    supports_reference_images: nextValues.supportsReferenceImages,
    max_reference_images: nextValues.maxReferenceImages,
    poll_interval_seconds: nextValues.pollIntervalSeconds,
    poll_timeout_seconds: nextValues.pollTimeoutSeconds,
  }
  if (capability === 'video') {
    nextParams.supports_first_frame = nextValues.supportsFirstFrame
    nextParams.supports_last_frame = nextValues.supportsLastFrame
    nextParams.supports_audio = nextValues.supportsAudio
  } else {
    delete nextParams.supports_first_frame
    delete nextParams.supports_last_frame
    delete nextParams.supports_audio
  }
  return stringifyDefaultParams(nextParams)
}

function createDraft(capability: ModelCapability): EditableProfileDraft {
  const provider =
    capability === 'llm'
      ? 'openai-compatible'
      : capability === 'embedding'
        ? 'ollama'
        : capability === 'image'
          ? 'openai-compatible'
          : MOCK_PROVIDER
  return {
    name: '',
    capability,
    provider,
    base_url: suggestedBaseUrlForProvider(provider),
    model_name: '',
    api_key: '',
    default_params_text: suggestedDefaultParamsText(capability, provider),
    enabled: true,
  }
}

function draftDiffers(a: EditableProfileDraft, b: EditableProfileDraft): boolean {
  return (
    a.id !== b.id ||
    a.name !== b.name ||
    a.capability !== b.capability ||
    a.provider !== b.provider ||
    a.base_url !== b.base_url ||
    a.model_name !== b.model_name ||
    a.api_key !== b.api_key ||
    a.default_params_text !== b.default_params_text ||
    a.enabled !== b.enabled
  )
}

function getCapabilityDescription(capability: ModelCapability) {
  if (capability === 'embedding') return 'Retrieval steps will prefer this default embedding model.'
  if (capability === 'image') return 'Storyboard frames and visual assets will prefer this default image model.'
  if (capability === 'video') return 'Video generation will prefer this default video model.'
  return 'LLM profiles are used for structured generation, compilation, and text-heavy workflows.'
}

function getResultToneClass(tone: FeedbackTone) {
  if (tone === 'error') return 'border-rose-500/20 bg-rose-500/10 text-rose-100'
  if (tone === 'success') return 'border-emerald-500/20 bg-emerald-500/10 text-emerald-100'
  return 'border-slate-700 bg-slate-900/60 text-slate-300'
}

export function EditorField({
  label,
  value,
  onChange,
  textarea,
  placeholder,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  textarea?: boolean
  placeholder?: string
}) {
  return (
    <label className="mb-3 block">
      <div className="mb-2 text-xs text-slate-400">{label}</div>
      {textarea ? (
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className="min-h-[92px] w-full rounded-2xl border border-slate-800 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-sky-500/60"
        />
      ) : (
        <input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className="w-full rounded-2xl border border-slate-800 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-sky-500/60"
        />
      )}
    </label>
  )
}

function InlineConfirmBar({
  title,
  message,
  confirmLabel,
  cancelLabel = '取消',
  busy = false,
  onConfirm,
  onCancel,
}: {
  title: string
  message: string
  confirmLabel: string
  cancelLabel?: string
  busy?: boolean
  onConfirm: () => void | Promise<void>
  onCancel: () => void
}) {
  return (
    <div className="mt-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 px-3 py-3 text-xs text-rose-100">
      <div className="font-semibold text-rose-200">{title}</div>
      <div className="mt-1 leading-5 text-rose-100/90">{message}</div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => { void onConfirm() }}
          disabled={busy}
          className="rounded-full border border-rose-500/60 px-3 py-1.5 text-xs text-rose-100 transition hover:border-rose-300 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy ? 'Working...' : confirmLabel}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
        >
          {cancelLabel}
        </button>
      </div>
    </div>
  )
}

function ModelNameField({
  capability,
  provider,
  value,
  placeholder,
  onChange,
}: {
  capability: ModelCapability
  provider: string
  value: string
  placeholder?: string
  onChange: (value: string) => void
}) {
  const suggestedModels = isPoyoAsyncProvider(provider) ? suggestedPoyoModelNames(capability) : []
  const datalistId = suggestedModels.length > 0 ? `model-name-options-${capability}` : undefined

  return (
    <label className="mb-3 block">
      <div className="mb-2 text-xs text-slate-400">模型名称</div>
      <input
        value={value}
        list={datalistId}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full rounded-2xl border border-slate-800 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-sky-500/60"
      />
      {datalistId ? (
        <datalist id={datalistId}>
          {suggestedModels.map((model) => <option key={model} value={model} />)}
        </datalist>
      ) : null}
    </label>
  )
}

export default function ModelRegistryModal({
  data,
  error,
  onClose,
  onSaved,
}: {
  data: ModelRegistryPayload | null
  error: string | null
  onClose: () => void
  onSaved: (payload: ModelRegistryPayload) => void
}) {
  const [profiles, setProfiles] = useState<ModelProfileRecord[]>(data?.profiles ?? [])
  const [defaults, setDefaults] = useState<Partial<Record<ModelCapability, string | null>>>(data?.defaults ?? {})
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState<EditableProfileDraft>(createDraft('image'))
  const [draftSnapshot, setDraftSnapshot] = useState<EditableProfileDraft>(createDraft('image'))
  const [busyState, setBusyState] = useState<'idle' | 'saving' | 'testing'>('idle')
  const [testingTarget, setTestingTarget] = useState<string | 'draft' | null>(null)
  const [feedback, setFeedback] = useState<TestResultMeta | null>(null)
  const [pendingDeleteProfileId, setPendingDeleteProfileId] = useState<string | null>(null)
  const [pendingSwitchProfileId, setPendingSwitchProfileId] = useState<string | null>(null)
  const [profileQuery, setProfileQuery] = useState('')
  const [profileFilter, setProfileFilter] = useState<ProfileFilter>('all')
  const [testResultsByProfile, setTestResultsByProfile] = useState<Record<string, TestResultMeta>>({})
  const isDraftDirty = useMemo(() => draftDiffers(draft, draftSnapshot), [draft, draftSnapshot])

  useEffect(() => {
    setProfiles(data?.profiles ?? [])
    setDefaults(data?.defaults ?? {})
    const fresh = createDraft('image')
    setDraft(fresh)
    setDraftSnapshot(fresh)
    setEditingId(null)
    setPendingDeleteProfileId(null)
    setPendingSwitchProfileId(null)
  }, [data])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [onClose])

  const grouped = useMemo(() => ({
    llm: profiles.filter((item) => item.capability === 'llm'),
    embedding: profiles.filter((item) => item.capability === 'embedding'),
    image: profiles.filter((item) => item.capability === 'image'),
    video: profiles.filter((item) => item.capability === 'video'),
  }), [profiles])

  const filteredGrouped = useMemo(() => {
    const query = profileQuery.trim().toLowerCase()
    const matchesQuery = (item: ModelProfileRecord) => {
      const haystack = [
        item.name,
        item.provider,
        item.model_name,
        item.base_url,
        item.id,
      ].join(' ').toLowerCase()
      return haystack.includes(query)
    }
    const matchesFilter = (item: ModelProfileRecord) => {
      if (profileFilter === 'default') {
        return defaults[item.capability] === item.id
      }
      if (profileFilter === 'missing-key') {
        return !item.key_configured
      }
      if (profileFilter === 'live') {
        return !item.uses_mock && !isMockProvider(item.provider) && !item.name.toLowerCase().includes('mock')
      }
      return true
    }
    const matches = (item: ModelProfileRecord) => (!query || matchesQuery(item)) && matchesFilter(item)
    const rankProfile = (item: ModelProfileRecord) => {
      let rank = 0
      if (defaults[item.capability] === item.id) rank -= 100
      if (!item.key_configured) rank -= 50
      if (testResultsByProfile[item.id]?.tone === 'error') rank -= 25
      if (testResultsByProfile[item.id]?.tone === 'success') rank -= 5
      return rank
    }
    const sortProfiles = (items: ModelProfileRecord[]) => items.sort((a, b) => rankProfile(a) - rankProfile(b) || a.name.localeCompare(b.name, 'en'))
    return {
      llm: sortProfiles(grouped.llm.filter(matches)),
      embedding: sortProfiles(grouped.embedding.filter(matches)),
      image: sortProfiles(grouped.image.filter(matches)),
      video: sortProfiles(grouped.video.filter(matches)),
    }
  }, [defaults, grouped, profileFilter, profileQuery, testResultsByProfile])

  const filteredProfileCount = useMemo(
    () => filteredGrouped.llm.length + filteredGrouped.embedding.length + filteredGrouped.image.length + filteredGrouped.video.length,
    [filteredGrouped],
  )

  const poyoFieldValues = useMemo(
    () => isPoyoAsyncProvider(draft.provider) ? getPoyoFieldValues(draft.capability, draft.default_params_text) : null,
    [draft.capability, draft.default_params_text, draft.provider],
  )

  const llmFieldValues = useMemo(
    () => draft.capability === 'llm' && draft.provider === 'openai-compatible'
      ? getLlmFieldValues(draft.default_params_text)
      : null,
    [draft.capability, draft.default_params_text, draft.provider],
  )

  const parseDraftDefaultParams = useCallback(() => {
    const raw = draft.default_params_text.trim()
    if (!raw) {
      return draft.capability === 'llm' && draft.provider === 'openai-compatible'
        ? safeParseDefaultParamsText(updateLlmDefaultParamsText('', getLlmFieldValues('')))
        : {} as Record<string, unknown>
    }
    const parsed = JSON.parse(raw)
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
      throw new Error('Default params must be a JSON object.')
    }
    const params = parsed as Record<string, unknown>
    if (draft.capability === 'llm' && draft.provider === 'openai-compatible') {
      return safeParseDefaultParamsText(updateLlmDefaultParamsText(JSON.stringify(params), getLlmFieldValues(JSON.stringify(params))))
    }
    return params
  }, [draft.capability, draft.default_params_text, draft.provider])

  const updatePoyoDraftDefaults = useCallback((updates: Partial<ReturnType<typeof getPoyoFieldValues>>) => {
    setDraft((current) => ({
      ...current,
      default_params_text: updatePoyoDefaultParamsText(current.capability, current.default_params_text, updates),
    }))
  }, [])

  const updateLlmDraftDefaults = useCallback((updates: Partial<ReturnType<typeof getLlmFieldValues>>) => {
    setDraft((current) => ({
      ...current,
      default_params_text: updateLlmDefaultParamsText(current.default_params_text, updates),
    }))
  }, [])

  const beginCreate = useCallback((capability: ModelCapability) => {
    setEditingId(null)
    setPendingDeleteProfileId(null)
    setPendingSwitchProfileId(null)
    const next = createDraft(capability)
    setDraft(next)
    setDraftSnapshot(next)
    setFeedback({ tone: 'info', text: `Creating a new ${CAPABILITY_LABELS[capability]} profile.` })
  }, [])

  const requestCreate = useCallback((capability: ModelCapability) => {
    if (isDraftDirty) {
      setPendingSwitchProfileId(`__new__:${capability}`)
      return
    }
    beginCreate(capability)
  }, [beginCreate, isDraftDirty])

  const beginEdit = useCallback((profile: ModelProfileRecord) => {
    setEditingId(profile.id)
    setPendingDeleteProfileId(null)
    setPendingSwitchProfileId(null)
    const nextDraft = {
      id: profile.id,
      name: profile.name,
      capability: profile.capability,
      provider: profile.provider,
      base_url: profile.base_url,
      model_name: profile.model_name,
      api_key: '',
      default_params_text: JSON.stringify(profile.default_params ?? {}, null, 2),
      enabled: profile.enabled,
    }
    setDraft(nextDraft)
    setDraftSnapshot(nextDraft)
    setFeedback({ tone: 'info', text: `Editing ${profile.name}. Leave API key blank to keep the current value.` })
  }, [])

  const requestEdit = useCallback((profile: ModelProfileRecord) => {
    if (editingId && editingId !== profile.id && isDraftDirty) {
      setPendingSwitchProfileId(profile.id)
      return
    }
    beginEdit(profile)
  }, [beginEdit, editingId, isDraftDirty])

  const confirmProfileSwitch = useCallback(() => {
    if (!pendingSwitchProfileId) return
    setPendingSwitchProfileId(null)
    if (pendingSwitchProfileId.startsWith('__new__:')) {
      beginCreate(pendingSwitchProfileId.replace('__new__:', '') as ModelCapability)
      return
    }
    const nextProfile = profiles.find((item) => item.id === pendingSwitchProfileId)
    if (nextProfile) {
      beginEdit(nextProfile)
    }
  }, [beginEdit, pendingSwitchProfileId, profiles])

  const saveProfiles = useCallback(async (nextProfiles: ModelProfileRecord[], nextDefaults: Partial<Record<ModelCapability, string | null>>) => {
    setBusyState('saving')
    setFeedback(null)
    try {
      const payload = await saveModelRegistry({
        profiles: nextProfiles
          .filter((item) => !item.builtin)
          .map((item) => ({
            id: item.id,
            name: item.name,
            capability: item.capability,
            provider: item.provider,
            base_url: item.base_url,
            model_name: item.model_name,
            enabled: item.enabled,
            default_params: item.default_params,
            ...(item.api_key ? { api_key: item.api_key } : {}),
          })),
        defaults: Object.fromEntries(
          Object.entries(nextDefaults).filter((entry): entry is [string, string] => typeof entry[1] === 'string' && entry[1].length > 0),
        ) as Partial<Record<ModelCapability, string>>,
      })
      setProfiles(payload.profiles)
      setDefaults(payload.defaults)
      onSaved(payload)
      setFeedback({ tone: 'success', text: 'Profiles saved.' })
      return payload
    } catch (saveError) {
      setFeedback({ tone: 'error', text: saveError instanceof Error ? saveError.message : 'Failed to save profiles.' })
      throw saveError
    } finally {
      setBusyState('idle')
    }
  }, [onSaved])

  const deleteProfile = useCallback(async (profileId: string) => {
    const nextProfiles = profiles.filter((item) => item.id !== profileId)
    const nextDefaults = { ...defaults }
    ;(['llm', 'embedding', 'image', 'video'] as const).forEach((capability) => {
      if (nextDefaults[capability] === profileId) delete nextDefaults[capability]
    })
    const payload = await saveProfiles(nextProfiles, nextDefaults)
    if (editingId === profileId) {
      setEditingId(null)
      const fresh = createDraft('image')
      setDraft(fresh)
      setDraftSnapshot(fresh)
    }
    setProfiles(payload.profiles)
    setDefaults(payload.defaults)
    setPendingDeleteProfileId(null)
    setFeedback({ tone: 'success', text: 'Profile deleted.' })
  }, [defaults, editingId, profiles, saveProfiles])

  const submitDraft = useCallback(async () => {
    if (!draft.name.trim()) {
      setFeedback({ tone: 'error', text: 'Please enter a profile name.' })
      return
    }
    if (!draft.provider.trim()) {
      setFeedback({ tone: 'error', text: 'Please enter a provider.' })
      return
    }

    let parsedDefaultParams: Record<string, unknown>
    try {
      parsedDefaultParams = parseDraftDefaultParams()
    } catch (parseError) {
      setFeedback({ tone: 'error', text: parseError instanceof Error ? parseError.message : 'Failed to parse default params.' })
      return
    }

    const profileId = editingId ?? `local-${draft.capability}-${Math.random().toString(36).slice(2, 8)}`
    const nextProfile: ModelProfileRecord = {
      id: profileId,
      name: draft.name.trim(),
      capability: draft.capability,
      provider: draft.provider.trim(),
      base_url: draft.base_url.trim(),
      model_name: draft.model_name.trim(),
      default_params: parsedDefaultParams,
      enabled: draft.enabled,
      is_default: false,
      key_configured: Boolean(draft.api_key.trim()),
      builtin: false,
      source: 'saved',
      uses_mock: isMockProvider(draft.provider),
      api_key: draft.api_key.trim() || undefined,
    }

    const nextProfiles = editingId
      ? profiles.map((item) => (item.id === editingId ? { ...item, ...nextProfile } : item))
      : [...profiles, nextProfile]

    const payload = await saveProfiles(nextProfiles, defaults)
    setEditingId(null)
    const fresh = createDraft(draft.capability)
    setDraft(fresh)
    setDraftSnapshot(fresh)
    setProfiles(payload.profiles)
    setDefaults(payload.defaults)
  }, [defaults, draft, editingId, parseDraftDefaultParams, profiles, saveProfiles])

  const applyDefault = useCallback(async (capability: ModelCapability, profileId: string) => {
    await saveProfiles(profiles, { ...defaults, [capability]: profileId })
  }, [defaults, profiles, saveProfiles])

  const applyRecommendedPoyoDefault = useCallback(async (capability: Extract<ModelCapability, 'image'>) => {
    const profileId = recommendedPoyoPresetId(capability)
    const exists = profiles.some((item) => item.id === profileId)
    if (!exists) {
      setFeedback({ tone: 'error', text: `Missing recommended preset ${recommendedPoyoPresetLabel(capability)}. Import PoYo presets first.` })
      return
    }
    await applyDefault(capability, profileId)
    setFeedback({ tone: 'success', text: `${recommendedPoyoPresetLabel(capability)} is now the default ${capability} profile.` })
  }, [applyDefault, profiles])

  const installPoyoPresets = useCallback(async () => {
    const presetMap = new Map(buildPoyoPresetProfiles().map((item) => [item.id, item]))
    let createdCount = 0
    let updatedCount = 0
    let unchangedCount = 0
    const nextProfiles = profiles.map((item) => {
      const preset = presetMap.get(item.id)
      if (!preset) return item
      const nextItem = { ...preset, api_key: item.api_key, key_configured: item.key_configured }
      const previousComparable = JSON.stringify({ ...item, api_key: undefined, key_configured: undefined })
      const nextComparable = JSON.stringify({ ...nextItem, api_key: undefined, key_configured: undefined })
      if (previousComparable === nextComparable) unchangedCount += 1
      else updatedCount += 1
      return nextItem
    })
    presetMap.forEach((preset, id) => {
      if (!nextProfiles.some((item) => item.id === id)) {
        nextProfiles.push(preset)
        createdCount += 1
      }
    })
    const nextDefaults = { ...defaults }
    if (!nextDefaults.image || !nextProfiles.some((item) => item.id === nextDefaults.image)) nextDefaults.image = recommendedPoyoPresetId('image')
    await saveProfiles(nextProfiles, nextDefaults)
    const summary = [
      createdCount > 0 ? `created ${createdCount}` : null,
      updatedCount > 0 ? `updated ${updatedCount}` : null,
      unchangedCount > 0 ? `${unchangedCount} unchanged` : null,
    ].filter(Boolean).join(', ')
    setFeedback({
      tone: 'success',
      text: `PoYo presets synced${summary ? `: ${summary}.` : '.'} Image default remains PoYo GPT Image 2; video default is preserved until MiniMax H3 is added.`,
    })
  }, [defaults, profiles, saveProfiles])

  const runProfileTest = useCallback(async (profile?: ModelProfileRecord) => {
    setBusyState('testing')
    setTestingTarget(profile?.id ?? 'draft')
    setFeedback(null)
    try {
      const parsedDefaultParams = profile ? profile.default_params : parseDraftDefaultParams()
      const result = profile
        ? await testModelProfile({
            profile_id: profile.id,
            profile: {
              id: profile.id,
              name: profile.name,
              capability: profile.capability,
              provider: profile.provider,
              base_url: profile.base_url,
              model_name: profile.model_name,
              enabled: profile.enabled,
              api_key: profile.api_key,
              default_params: profile.default_params,
            },
          })
        : await testModelProfile({
            profile: {
              id: draft.id,
              name: draft.name || 'Untitled profile',
              capability: draft.capability,
              provider: draft.provider,
              base_url: draft.base_url,
              model_name: draft.model_name,
              enabled: draft.enabled,
              api_key: draft.api_key,
              default_params: parsedDefaultParams,
            },
          })
      setFeedback({ tone: 'success', text: result.message })
      if (profile?.id) {
        setTestResultsByProfile((current) => ({
          ...current,
          [profile.id]: { tone: 'success', text: result.message },
        }))
      }
    } catch (testError) {
      const message = testError instanceof Error ? testError.message : 'Test failed.'
      setFeedback({ tone: 'error', text: message })
      if (profile?.id) {
        setTestResultsByProfile((current) => ({
          ...current,
          [profile.id]: { tone: 'error', text: message },
        }))
      }
    } finally {
      setBusyState('idle')
      setTestingTarget(null)
    }
  }, [draft, parseDraftDefaultParams])

  const feedbackClass = feedback ? getResultToneClass(feedback.tone) : ''

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-slate-950/80 px-3 py-3 backdrop-blur-sm sm:px-6 sm:py-8">
      <div role="dialog" aria-modal="true" aria-label="模型管理" className="flex h-[min(92vh,960px)] w-full max-w-6xl flex-col overflow-hidden rounded-[28px] border border-slate-800 bg-slate-950 shadow-[0_24px_80px_rgba(2,6,23,0.48)]">
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-5">
          <div>
            <div className="text-[11px] uppercase tracking-[0.28em] text-violet-300">模型配置</div>
            <div className="mt-2 text-lg font-semibold text-slate-100">模型管理</div>
            <div className="mt-1 text-sm text-slate-400">在同一个工作面里管理 LLM、Embedding、图片和视频模型配置。</div>
          </div>
          <button onClick={onClose} className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white">关闭</button>
        </div>

        {feedback ? (
          <div className="border-b border-slate-800 px-6 py-4">
            <div className={`rounded-2xl border px-4 py-3 text-sm ${feedbackClass}`}>{feedback.text}</div>
          </div>
        ) : null}

        <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden xl:grid-cols-[minmax(0,1.3fr)_360px]">
          <div className="min-h-0 overflow-y-auto px-6 py-5">
            {error ? (
              <div className="rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">{error}</div>
            ) : null}
            {!error && !data ? (
              <div className="mt-4 rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-sm text-slate-300">正在加载模型配置...</div>
            ) : null}

            <div className="mt-4 rounded-3xl border border-slate-800 bg-slate-900/40 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-xs uppercase tracking-[0.24em] text-slate-500">列表工具</div>
                  <div className="mt-2 text-sm text-slate-300">支持按名称、供应商、模型名、URL 或配置 ID 搜索。</div>
                </div>
                <div className="rounded-full border border-slate-700 bg-slate-950 px-3 py-1 text-xs text-slate-300">
                  可见 {filteredProfileCount} / 总计 {profiles.length}
                </div>
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_180px]">
                <input
                  value={profileQuery}
                  onChange={(event) => setProfileQuery(event.target.value)}
                  placeholder="搜索模型配置"
                  className="w-full rounded-2xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-sky-500/60"
                />
                <button
                  type="button"
                  onClick={() => setProfileQuery('')}
                  disabled={!profileQuery.trim()}
                  className="rounded-2xl border border-slate-700 px-3 py-2 text-sm text-slate-300 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  清空搜索
                </button>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {([
                  { key: 'all', label: '全部' },
                  { key: 'default', label: '仅默认' },
                  { key: 'missing-key', label: '缺少密钥' },
                  { key: 'live', label: '仅生产可用' },
                ] as const).map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => setProfileFilter(item.key)}
                    className={`rounded-full border px-3 py-1 text-xs transition ${
                      profileFilter === item.key
                        ? 'border-sky-500/60 bg-sky-500/10 text-sky-100'
                        : 'border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            {(['llm', 'embedding', 'image', 'video'] as const).map((capability) => (
              <div key={capability} className="mt-4 rounded-3xl border border-slate-800 bg-slate-900/40 p-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="text-xs uppercase tracking-[0.24em] text-slate-500">{CAPABILITY_LABELS[capability]}</div>
                    <div className="mt-2 text-sm text-slate-300">
                      默认模型：{profiles.find((item) => item.id === defaults[capability])?.name ?? data?.default_profiles?.[capability]?.name ?? '未设置'}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">{getCapabilityDescription(capability)}</div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="rounded-full border border-slate-700 bg-slate-950 px-3 py-1 text-xs text-slate-300">显示 {filteredGrouped[capability].length} 个</div>
                    {capability === 'image' ? (
                      <button onClick={() => void applyRecommendedPoyoDefault(capability)} className="rounded-full border border-emerald-600/60 px-3 py-1 text-xs text-emerald-200 transition hover:border-emerald-400 hover:text-white">
                        使用 GPT Image 2 默认
                      </button>
                    ) : null}
                    {(capability === 'image' || capability === 'video') ? (
                      <button onClick={() => void installPoyoPresets()} className="rounded-full border border-sky-600/60 px-3 py-1 text-xs text-sky-200 transition hover:border-sky-400 hover:text-white">
                        导入 PoYo 预设
                      </button>
                    ) : null}
                    <button onClick={() => requestCreate(capability)} className="rounded-full border border-violet-600/60 px-3 py-1 text-xs text-violet-200 transition hover:border-violet-400 hover:text-white">新增</button>
                  </div>
                </div>

                <div className="mt-4 space-y-3">
                  {filteredGrouped[capability].map((profile) => {
                    const testMeta = testResultsByProfile[profile.id]
                    const isEditing = editingId === profile.id
                    return (
                      <div
                        key={profile.id}
                        onClick={() => !profile.builtin && requestEdit(profile)}
                        className={`rounded-2xl border px-4 py-3 text-sm text-slate-300 transition ${
                          isEditing
                            ? 'border-violet-500/70 bg-violet-950/20 shadow-[0_0_0_1px_rgba(139,92,246,0.25)]'
                            : 'border-slate-800 bg-slate-950/70 hover:border-slate-700'
                        } ${profile.builtin ? 'cursor-default' : 'cursor-pointer'}`}
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium text-slate-100">{profile.name}</span>
                          {isEditing ? <span className="rounded-full border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[11px] text-violet-200">编辑中</span> : null}
                          {defaults[capability] === profile.id ? <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-200">默认</span> : null}
                          {profile.uses_mock ? <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-200">模拟</span> : <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-[11px] text-sky-200">生产</span>}
                          {profile.capability === 'llm' ? <span className="rounded-full border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[11px] text-violet-200">{buildLlmThinkingLabel(profile.default_params)}</span> : null}
                          {!profile.key_configured ? <span className="rounded-full border border-rose-500/30 bg-rose-500/10 px-2 py-0.5 text-[11px] text-rose-200">缺少密钥</span> : null}
                          {profile.builtin ? <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-400">内置</span> : null}
                        </div>

                        <div className="mt-2 text-xs leading-6 text-slate-400">
                          供应商：{profile.provider} · 模型：{profile.model_name || '未设置'} · Base URL：{profile.base_url || '未设置'}
                        </div>

                        {testMeta ? (
                          <div className={`mt-2 rounded-2xl border px-3 py-2 text-xs leading-5 ${getResultToneClass(testMeta.tone)}`}>
                            最近一次测试：{testMeta.text}
                          </div>
                        ) : (
                          <div className="mt-2 rounded-2xl border border-slate-800 bg-slate-900/40 px-3 py-2 text-xs leading-5 text-slate-400">
                            最近一次测试：尚未执行。
                          </div>
                        )}

                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation()
                              void applyDefault(capability, profile.id)
                            }}
                            disabled={!canUseAsDefault(profile)}
                            title={
                              !canUseAsDefault(profile)
                                ? '当前只有模拟视频模型、PoYo 异步视频模型或 MiniMax H3 异步视频模型可以设为默认。'
                                : undefined
                            }
                            className="rounded-full border border-emerald-600/60 px-3 py-1 text-xs text-emerald-200 transition hover:border-emerald-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            设为默认
                          </button>
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation()
                              void runProfileTest(profile)
                            }}
                            disabled={busyState === 'testing'}
                            className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white disabled:opacity-50"
                          >
                            {busyState === 'testing' && testingTarget === profile.id ? '测试中...' : '测试连接'}
                          </button>
                          {!profile.builtin ? (
                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation()
                                requestEdit(profile)
                              }}
                              className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
                            >
                              编辑
                            </button>
                          ) : null}
                          {!profile.builtin ? (
                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation()
                                setPendingDeleteProfileId(profile.id)
                              }}
                              className="rounded-full border border-rose-600/60 px-3 py-1 text-xs text-rose-200 transition hover:border-rose-400 hover:text-white"
                            >
                              删除
                            </button>
                          ) : null}
                        </div>

                        {pendingDeleteProfileId === profile.id ? (
                          <InlineConfirmBar
                            title="确认删除该配置？"
                            message="删除后会从模型注册表中移除；如果它当前正被设为默认模型，对应默认绑定也会一并清除。"
                            confirmLabel="确认删除"
                            busy={busyState === 'saving'}
                            onConfirm={() => deleteProfile(profile.id)}
                            onCancel={() => setPendingDeleteProfileId((current) => current === profile.id ? null : current)}
                          />
                        ) : null}
                      </div>
                    )
                  })}

                  {filteredGrouped[capability].length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-slate-700 px-4 py-3 text-sm text-slate-500">
                      {profileQuery.trim() ? '当前搜索条件下没有匹配的模型配置。' : '当前能力下还没有模型配置。'}
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
          </div>

          <div className="relative min-h-0 overflow-y-auto border-t border-slate-800 bg-slate-950/80 px-5 py-5 pr-3 xl:border-l xl:border-t-0" style={{ scrollbarGutter: 'stable' }}>
            <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">编辑面板</div>
            <div className="mt-2 text-lg font-semibold text-slate-100">{editingId ? '编辑模型配置' : '新建模型配置'}</div>
            <div className="mt-2 text-sm leading-6 text-slate-400">右侧面板一次只专注维护一个模型配置，方便逐项核对能力、参数和密钥状态。</div>
            {editingId && isDraftDirty ? (
              <div className="mt-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm leading-6 text-amber-100">
                当前模型配置存在未保存修改。
              </div>
            ) : null}
            {pendingSwitchProfileId ? (
              <div className="mt-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm leading-6 text-amber-100">
                <div className="font-medium text-amber-50">切换配置并放弃当前修改？</div>
                <div className="mt-1 text-amber-100/80">当前表单还有未保存内容。你可以继续编辑，或者放弃修改后切换到另一个模型配置。</div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button onClick={confirmProfileSwitch} className="rounded-full border border-amber-400/60 px-3 py-1 text-xs text-amber-50 transition hover:border-amber-300 hover:bg-amber-500/10">放弃并切换</button>
                  <button onClick={() => setPendingSwitchProfileId(null)} className="rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-200 transition hover:border-slate-500 hover:text-white">继续编辑</button>
                </div>
              </div>
            ) : null}

            <div className="sticky top-0 z-10 -mx-5 mt-4 border-y border-slate-800 bg-slate-950/95 px-5 py-2 backdrop-blur-sm">
              <div className="flex items-center justify-between gap-3 text-[11px] text-slate-400">
                <span>向下滚动可继续编辑供应商专属能力项和默认参数。</span>
                <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] tracking-[0.18em] text-slate-300">滚动</span>
              </div>
            </div>

            <div className="mt-5 space-y-4 pb-24">
              {draft.capability === 'embedding' ? (
                <div className="rounded-2xl border border-cyan-500/20 bg-cyan-500/10 px-4 py-3 text-sm leading-6 text-cyan-100">
                  在当前工作区中，Embedding 模型建议优先使用 Ollama 的 `/api/embed` 形态。
                </div>
              ) : null}
              {draft.capability === 'image' && draft.provider !== MOCK_PROVIDER ? (
                <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm leading-6 text-emerald-100">
                  该图片模型已经可以驱动真实的分镜首帧和视觉资产生成链路。
                </div>
              ) : null}
              {draft.capability === 'video' && draft.provider !== MOCK_PROVIDER && !isPoyoAsyncProvider(draft.provider) && !isMiniMaxH3AsyncProvider(draft.provider) ? (
                <div className="rounded-2xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm leading-6 text-amber-100">
                  该视频模型当前支持保存和连通性测试，但还没有完全接入正式生产工作流。
                </div>
              ) : null}
              {draft.capability === 'video' && isPoyoAsyncProvider(draft.provider) ? (
                <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm leading-6 text-emerald-100">
                  PoYo 异步视频模型已经兼容当前正式生产链路。
                </div>
              ) : null}
              {draft.capability === 'video' && isMiniMaxH3AsyncProvider(draft.provider) ? (
                <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm leading-6 text-emerald-100">
                  metaso.cn MiniMax H3 兼容 API 已接入后端适配层；测试配置不会提交真实任务，真实生成仍需在工作台显式发起。
                </div>
              ) : null}

              <EditorField label="名称" value={draft.name} onChange={(value) => setDraft((current) => ({ ...current, name: value }))} />
              <div>
                <div className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-500">能力类型</div>
                <select
                  value={draft.capability}
                  onChange={(event) => {
                    const capability = event.target.value as ModelCapability
                    setDraft((current) => ({
                      ...createDraft(capability),
                      id: current.id,
                      name: current.name,
                      enabled: current.enabled,
                    }))
                  }}
                  className="w-full rounded-2xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none"
                >
                  <option value="llm">LLM</option>
                  <option value="embedding">Embedding</option>
                  <option value="image">图片</option>
                  <option value="video">视频</option>
                </select>
              </div>
              <div>
                <div className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-500">供应商</div>
                <select
                  value={draft.provider}
                  onChange={(event) => setDraft((current) => {
                    const provider = event.target.value
                    const nextBaseUrl = current.base_url.trim() ? current.base_url : suggestedBaseUrlForProvider(provider)
                    const currentDefaults = current.default_params_text.trim()
                    const shouldRefreshDefaults =
                      !currentDefaults || currentDefaults === suggestedDefaultParamsText(current.capability, current.provider, current.model_name)
                    const nextModelName = isMiniMaxH3AsyncProvider(provider) && !current.model_name.trim() ? 'MiniMax-H3' : current.model_name
                    return {
                      ...current,
                      provider,
                      base_url: nextBaseUrl,
                      model_name: nextModelName,
                      default_params_text: shouldRefreshDefaults
                        ? suggestedDefaultParamsText(current.capability, provider, nextModelName)
                        : current.default_params_text,
                    }
                  })}
                  className="w-full rounded-2xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none"
                >
                  {providerOptionsForCapability(draft.capability).map((provider) => (
                    <option key={provider} value={provider}>{provider}</option>
                  ))}
                </select>
              </div>
              <EditorField label="Base URL" value={draft.base_url} onChange={(value) => setDraft((current) => ({ ...current, base_url: value }))} />
              <ModelNameField
                capability={draft.capability}
                provider={draft.provider}
                value={draft.model_name}
                placeholder={
                  isMiniMaxH3AsyncProvider(draft.provider)
                    ? 'MiniMax-H3'
                    : isPoyoAsyncProvider(draft.provider)
                      ? '例如：seedream-5.0-lite 或 seedance-2'
                      : undefined
                }
                onChange={(value) => setDraft((current) => {
                  const currentDefaults = current.default_params_text.trim()
                  const shouldRefreshDefaults =
                    !currentDefaults || currentDefaults === suggestedDefaultParamsText(current.capability, current.provider, current.model_name)
                  return {
                    ...current,
                    model_name: value,
                    default_params_text: shouldRefreshDefaults
                      ? suggestedDefaultParamsText(current.capability, current.provider, value)
                      : current.default_params_text,
                  }
                })}
              />
              {isPoyoAsyncProvider(draft.provider) ? (
                <div className="-mt-2 text-xs text-slate-500">推荐模型：{suggestedPoyoModelNames(draft.capability).join(' · ')}</div>
              ) : null}
              {isMiniMaxH3AsyncProvider(draft.provider) ? (
                <div className="-mt-2 text-xs text-slate-500">官方模型名：MiniMax-H3。测试当前草稿只校验配置结构，不发起真实扣费任务。</div>
              ) : null}
              <EditorField
                label="API Key"
                value={draft.api_key}
                placeholder={editingId ? '留空则保持当前密钥不变' : '粘贴新的 API Key'}
                onChange={(value) => setDraft((current) => ({ ...current, api_key: value }))}
              />

              {llmFieldValues ? (
                <div className="rounded-2xl border border-violet-500/20 bg-violet-500/5 px-4 py-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="text-xs uppercase tracking-[0.2em] text-violet-300">LLM 推理配置</div>
                      <div className="mt-2 text-sm leading-6 text-slate-300">
                        关闭思考适合分镜 Prompt Compiler、JSON 编译和低延迟结构化输出；开启思考适合更复杂的文本推理任务。
                      </div>
                    </div>
                    <span className="rounded-full border border-violet-500/30 bg-violet-500/10 px-3 py-1 text-xs text-violet-100">
                      thinking.type = {llmFieldValues.thinkingType}
                    </span>
                  </div>
                  <label className="mt-4 flex items-center gap-2 text-sm text-slate-200">
                    <input
                      type="checkbox"
                      checked={llmFieldValues.thinkingType === 'enabled'}
                      onChange={(event) => updateLlmDraftDefaults({ thinkingType: event.target.checked ? 'enabled' : 'disabled' })}
                    />
                    开启思考
                  </label>
                </div>
              ) : null}

              {poyoFieldValues ? (
                <div className="rounded-2xl border border-sky-500/20 bg-sky-500/5 px-4 py-4">
                  <div className="text-xs uppercase tracking-[0.2em] text-sky-300">PoYo 能力配置</div>
                  <div className="mt-3 grid gap-3">
                    <label className="flex items-center gap-2 text-sm text-slate-300">
                      <input
                        type="checkbox"
                        checked={poyoFieldValues.supportsReferenceImages}
                        onChange={(event) => updatePoyoDraftDefaults({ supportsReferenceImages: event.target.checked })}
                      />
                      支持参考图
                    </label>
                    <label className="block text-sm text-slate-300">
                      <div className="mb-2 text-xs text-slate-400">任务模式</div>
                      <div className="flex flex-wrap gap-2">
                        {(draft.capability === 'image'
                          ? ['text_to_image', 'image_to_image']
                          : ['text_to_video', 'image_to_video', 'reference_to_video']
                        ).map((taskMode) => {
                          const checked = poyoFieldValues.taskModes.includes(taskMode)
                          return (
                            <label key={taskMode} className="flex items-center gap-2 rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-300">
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={(event) => updatePoyoDraftDefaults({
                                  taskModes: event.target.checked
                                    ? Array.from(new Set([...poyoFieldValues.taskModes, taskMode]))
                                    : poyoFieldValues.taskModes.filter((item) => item !== taskMode),
                                })}
                              />
                              {taskMode}
                            </label>
                          )
                        })}
                      </div>
                    </label>
                    <div className="grid grid-cols-2 gap-3">
                      <EditorField label="最大参考图数量" value={String(poyoFieldValues.maxReferenceImages)} onChange={(value) => updatePoyoDraftDefaults({ maxReferenceImages: Number(value || 0) })} />
                      <EditorField label="轮询间隔（秒）" value={String(poyoFieldValues.pollIntervalSeconds)} onChange={(value) => updatePoyoDraftDefaults({ pollIntervalSeconds: Number(value || 0) })} />
                      <EditorField label="轮询超时（秒）" value={String(poyoFieldValues.pollTimeoutSeconds)} onChange={(value) => updatePoyoDraftDefaults({ pollTimeoutSeconds: Number(value || 0) })} />
                    </div>
                    {draft.capability === 'video' ? (
                      <div className="flex flex-wrap gap-3 text-sm text-slate-300">
                        <label className="flex items-center gap-2">
                          <input type="checkbox" checked={poyoFieldValues.supportsFirstFrame} onChange={(event) => updatePoyoDraftDefaults({ supportsFirstFrame: event.target.checked })} />
                          支持首帧
                        </label>
                        <label className="flex items-center gap-2">
                          <input type="checkbox" checked={poyoFieldValues.supportsLastFrame} onChange={(event) => updatePoyoDraftDefaults({ supportsLastFrame: event.target.checked })} />
                          支持尾帧
                        </label>
                        <label className="flex items-center gap-2">
                          <input type="checkbox" checked={poyoFieldValues.supportsAudio} onChange={(event) => updatePoyoDraftDefaults({ supportsAudio: event.target.checked })} />
                          支持音频
                        </label>
                      </div>
                    ) : null}
                  </div>
                </div>
              ) : null}

              <EditorField
                label="默认参数 JSON"
                value={draft.default_params_text}
                textarea
                placeholder={`例如 {\n  "temperature": 0.3,\n  "max_tokens": 8192,\n  "thinking": {\n    "type": "disabled"\n  }\n}`}
                onChange={(value) => setDraft((current) => ({ ...current, default_params_text: value }))}
              />
              <label className="flex items-center gap-2 rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-2 text-sm text-slate-300">
                <input type="checkbox" checked={draft.enabled} onChange={(event) => setDraft((current) => ({ ...current, enabled: event.target.checked }))} />
                启用
              </label>
            </div>

            <div className="pointer-events-none sticky bottom-[72px] z-10 -mx-5 h-10 bg-gradient-to-b from-transparent to-slate-950/90" />
            <div className="sticky bottom-0 mt-5 -mx-5 border-t border-slate-800 bg-slate-950/95 px-5 pb-5 pt-4 shadow-[0_-18px_36px_rgba(2,6,23,0.34)] backdrop-blur-sm">
              <div className="flex flex-wrap gap-2">
                <button onClick={() => void runProfileTest()} disabled={busyState === 'testing'} className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white disabled:opacity-50">
                  {busyState === 'testing' && testingTarget === 'draft' ? '测试中...' : '测试当前草稿'}
                </button>
                <button onClick={() => void submitDraft()} disabled={busyState === 'saving'} className="rounded-full bg-violet-400 px-3 py-1.5 text-xs font-medium text-slate-950 transition hover:brightness-110 disabled:opacity-50">
                  {busyState === 'saving' ? '保存中...' : editingId ? '更新配置' : '创建配置'}
                </button>
                <button onClick={() => { setEditingId(null); setPendingSwitchProfileId(null); const fresh = createDraft(draft.capability); setDraft(fresh); setDraftSnapshot(fresh); setFeedback(null) }} className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white">
                  重置表单
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
