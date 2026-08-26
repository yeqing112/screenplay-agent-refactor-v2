import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import ModelRegistryModal, {
  buildPoyoPresetProfiles,
  recommendedPoyoPresetId,
  recommendedPoyoPresetLabel,
} from './ModelRegistryModal'
import {
  fetchModelRegistry,
  fetchModelRegistryDefaults,
  saveModelRegistry,
  type ModelCapability,
  type ModelProfileRecord,
  type ModelRegistryPayload,
} from '../services/modelRegistry'
import {
  buildCapabilityHealthLine,
  buildCapabilitySummary,
  buildReferenceModeLabel,
  buildSyncedCapabilityParams,
  buildTaskModesLabel,
} from './productWorkspaceModels'
import {
  isPoyoHappyHorseModel,
  isPoyoKlingFamilyModel,
  isPoyoNanoBananaModel,
  isPoyoSeedreamLiteModel,
  normalizePoyoModelName,
} from './poyoModelCatalog'

const CAPABILITY_ORDER: ModelCapability[] = ['llm', 'embedding', 'image', 'video']

const CAPABILITY_LABELS: Record<ModelCapability, string> = {
  llm: '文本 / LLM',
  embedding: '向量 / Embedding',
  image: '图像 / Image',
  video: '视频 / Video',
}

type ActionState = 'idle' | 'saving' | 'error' | 'success'

type GuidanceCard = {
  key: string
  family: 'image' | 'video'
  name: string
  modelName: string
  useCase: string
  recommendation: string
  referenceMode: string
  taskModes: string
}

function toSaveableDefaults(
  value: Partial<Record<ModelCapability, string | null | undefined>>,
): Partial<Record<ModelCapability, string>> {
  const next: Partial<Record<ModelCapability, string>> = {}
  for (const capability of CAPABILITY_ORDER) {
    const current = value[capability]
    if (typeof current === 'string' && current.trim()) {
      next[capability] = current
    }
  }
  return next
}

export default function ProductWorkspaceModelsSection() {
  const [defaults, setDefaults] = useState<ModelRegistryPayload['default_profiles']>({})
  const [defaultsState, setDefaultsState] = useState<'idle' | 'loading' | 'error'>('loading')
  const [registryOpen, setRegistryOpen] = useState(false)
  const [registryData, setRegistryData] = useState<ModelRegistryPayload | null>(null)
  const [registryError, setRegistryError] = useState<string | null>(null)
  const [actionState, setActionState] = useState<ActionState>('idle')
  const [actionMessage, setActionMessage] = useState('')

  const refreshDefaults = useCallback(async () => {
    setDefaultsState('loading')
    try {
      const payload = await fetchModelRegistryDefaults()
      setDefaults(payload.default_profiles ?? {})
      setDefaultsState('idle')
    } catch {
      setDefaultsState('error')
    }
  }, [])

  useEffect(() => {
    void refreshDefaults()
  }, [refreshDefaults])

  const openRegistry = useCallback(() => {
    setRegistryOpen(true)
    setRegistryError(null)
    fetchModelRegistry()
      .then((payload) => setRegistryData(payload))
      .catch((error) => setRegistryError(error instanceof Error ? error.message : '加载模型注册表失败'))
  }, [])

  const summaries = useMemo(
    () => CAPABILITY_ORDER.map((capability) => buildCapabilitySummary(capability, defaults[capability])),
    [defaults],
  )

  const syncableDefaultSummaries = useMemo(
    () => summaries.filter((item) => item.configNeedsSync),
    [summaries],
  )

  const recommendedIds = useMemo(
    () => ({
      image: recommendedPoyoPresetId('image'),
      video: recommendedPoyoPresetId('video'),
    }),
    [],
  )

  const recommendationStatus = useMemo(() => {
    const imageReady = defaults.image?.id === recommendedIds.image
    const videoReady = defaults.video?.id === recommendedIds.video
    return { imageReady, videoReady, allReady: imageReady && videoReady }
  }, [defaults.image?.id, defaults.video?.id, recommendedIds.image, recommendedIds.video])

  const overview = useMemo(() => {
    const missingCapabilities = summaries.filter((item) => item.readinessTone === 'blocked')
    const warningCapabilities = summaries.filter((item) => item.readinessTone === 'warning')
    if (missingCapabilities.length > 0) {
      return {
        tone: 'blocked' as const,
        title: '默认模型链路还不完整',
        detail: `当前仍有 ${missingCapabilities.length} 类默认能力未配置，正式生产链路还没有完全打通。`,
      }
    }
    if (warningCapabilities.length > 0) {
      return {
        tone: 'warning' as const,
        title: '模型已接入，但仍有生产风险',
        detail: `当前有 ${warningCapabilities.length} 类能力仍需补密钥、切换默认值，或把旧能力字段同步到统一适配配置。`,
      }
    }
    return {
      tone: 'ready' as const,
      title: '默认模型链路已齐备',
      detail: '文本、向量、图像、视频四类能力都已具备正式工作台可用的默认接入条件。',
    }
  }, [summaries])

  const poyoGuidance = useMemo(() => {
    const presets = buildPoyoPresetProfiles()
    return presets.map((preset) => ({
      key: preset.id,
      family: preset.capability as 'image' | 'video',
      name: preset.name,
      modelName: preset.model_name,
      useCase: describePresetUseCase(preset),
      recommendation: describePresetRecommendation(preset),
      referenceMode: buildReferenceModeLabel(buildCapabilitySummary(preset.capability, preset)),
      taskModes: buildTaskModesLabel(
        Array.isArray(preset.default_params?.task_modes)
          ? preset.default_params.task_modes.filter((item): item is string => typeof item === 'string')
          : [],
      ),
    })) satisfies GuidanceCard[]
  }, [])

  const persistRegistrySnapshot = useCallback(
    async (
      payload: ModelRegistryPayload,
      nextProfiles: ModelProfileRecord[],
      nextDefaults: Partial<Record<ModelCapability, string>>,
    ) => {
      const saved = await saveModelRegistry({
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
        defaults: nextDefaults,
      })
      setRegistryData(saved)
      setDefaults(saved.default_profiles ?? {})
      setDefaultsState('idle')
      return saved
    },
    [],
  )

  const syncRecommendedPoyoDefaults = useCallback(async () => {
    setActionState('saving')
    setActionMessage('')
    try {
      const payload = registryData ?? (await fetchModelRegistry())
      const presetMap = new Map(buildPoyoPresetProfiles().map((item) => [item.id, item]))
      let createdCount = 0
      let updatedCount = 0

      const mergedProfiles = payload.profiles.map((item) => {
        const preset = presetMap.get(item.id)
        if (!preset) return item

        const nextItem: ModelProfileRecord = {
          ...preset,
          api_key: item.api_key,
          key_configured: item.key_configured || Boolean(item.api_key),
          builtin: item.builtin,
          is_default: item.is_default,
          source: item.source,
        }

        if (JSON.stringify({ ...item, api_key: undefined }) !== JSON.stringify({ ...nextItem, api_key: undefined })) {
          updatedCount += 1
        }
        presetMap.delete(item.id)
        return nextItem
      })

      for (const preset of presetMap.values()) {
        mergedProfiles.push(preset)
        createdCount += 1
      }

      await persistRegistrySnapshot(payload, mergedProfiles, {
        ...toSaveableDefaults(payload.defaults ?? {}),
        image: recommendedIds.image,
        video: recommendedIds.video,
      })

      setActionState('success')
      setActionMessage(
        [
          createdCount > 0 ? `新增 ${createdCount} 个 PoYo 预设` : null,
          updatedCount > 0 ? `更新 ${updatedCount} 个预设能力字段` : null,
          '图像默认切到 PoYo Seedream 5 Lite',
          '视频默认切到 PoYo Seedance 2',
        ]
          .filter(Boolean)
          .join('，') + '。',
      )
    } catch (error) {
      setActionState('error')
      setActionMessage(error instanceof Error ? error.message : '同步 PoYo 预设失败')
    }
  }, [persistRegistrySnapshot, recommendedIds.image, recommendedIds.video, registryData])

  const switchVideoDefaultToSeedance = useCallback(async () => {
    setActionState('saving')
    setActionMessage('')
    try {
      const payload = registryData ?? (await fetchModelRegistry())
      await persistRegistrySnapshot(payload, payload.profiles, {
        ...toSaveableDefaults(payload.defaults ?? {}),
        video: recommendedIds.video,
      })
      setActionState('success')
      setActionMessage('默认视频模型已切换为 PoYo Seedance 2。')
    } catch (error) {
      setActionState('error')
      setActionMessage(error instanceof Error ? error.message : '切换默认视频模型失败')
    }
  }, [persistRegistrySnapshot, recommendedIds.video, registryData])

  const syncCurrentDefaultCapabilities = useCallback(async () => {
    setActionState('saving')
    setActionMessage('')
    try {
      const payload = registryData ?? (await fetchModelRegistry())
      const defaultIds = new Set(
        Object.values(payload.defaults ?? {}).filter((item): item is string => typeof item === 'string' && item.trim().length > 0),
      )
      let updatedCount = 0

      const nextProfiles = payload.profiles.map((item) => {
        if (!defaultIds.has(item.id)) return item
        const nextParams = buildSyncedCapabilityParams(item)
        if (JSON.stringify(item.default_params ?? {}) === JSON.stringify(nextParams)) return item
        updatedCount += 1
        return { ...item, default_params: nextParams }
      })

      if (updatedCount === 0) {
        setActionState('success')
        setActionMessage('当前默认模型的能力字段已经是最新状态，无需补齐。')
        return
      }

      await persistRegistrySnapshot(payload, nextProfiles, toSaveableDefaults(payload.defaults ?? {}))
      setActionState('success')
      setActionMessage(`已补齐 ${updatedCount} 个默认模型的能力字段，正式工作台会统一按最新适配能力展示。`)
    } catch (error) {
      setActionState('error')
      setActionMessage(error instanceof Error ? error.message : '补齐默认模型能力字段失败')
    }
  }, [persistRegistrySnapshot, registryData])

  return (
    <>
      <div className="grid gap-6 xl:grid-cols-[1.12fr_minmax(0,0.88fr)]">
        <div className="min-w-0 rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-lg font-semibold text-white">模型管理</div>
              <div className="mt-2 text-sm leading-6 text-slate-400">
                这里统一查看当前项目使用的文本、向量、图像、视频模型，以及它们对参考图、首尾帧、音频输入和异步轮询的支持情况。
              </div>
            </div>
            <button
              type="button"
              onClick={openRegistry}
              className="rounded-lg border border-violet-500/50 px-4 py-2 text-sm font-medium text-violet-200 transition hover:border-violet-400 hover:text-white"
            >
              打开注册表
            </button>
          </div>

          <div
            className={`mt-5 rounded-xl border p-4 ${
              overview.tone === 'ready'
                ? 'border-emerald-500/30 bg-emerald-500/10'
                : overview.tone === 'warning'
                  ? 'border-amber-500/30 bg-amber-500/10'
                  : 'border-rose-500/30 bg-rose-500/10'
            }`}
          >
            <div className="text-sm font-medium text-white">{overview.title}</div>
            <div className="mt-2 text-sm leading-6 text-slate-200">{overview.detail}</div>
          </div>

          <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm font-medium text-white">推荐默认链路</div>
                <div className="mt-2 text-sm leading-6 text-slate-400">
                  图像建议优先使用 {recommendedPoyoPresetLabel('image')}，视频建议优先使用 {recommendedPoyoPresetLabel('video')}。
                  这套默认链路更贴近当前项目的“多参考图资产生成 + 首尾帧视频生成”方式。
                </div>
              </div>
              <span
                className={`rounded-full border px-2 py-0.5 text-[11px] ${
                  recommendationStatus.allReady
                    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
                    : 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                }`}
              >
                {recommendationStatus.allReady ? '推荐默认已到位' : '推荐默认未完全到位'}
              </span>
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <Metric
                title="图像默认"
                value={
                  recommendationStatus.imageReady
                    ? `${recommendedPoyoPresetLabel('image')}（已生效）`
                    : `${defaults.image?.name ?? '未配置'}（建议切到 ${recommendedPoyoPresetLabel('image')}）`
                }
              />
              <Metric
                title="视频默认"
                value={
                  recommendationStatus.videoReady
                    ? `${recommendedPoyoPresetLabel('video')}（已生效）`
                    : `${defaults.video?.name ?? '未配置'}（建议切到 ${recommendedPoyoPresetLabel('video')}）`
                }
              />
            </div>

            <div className="mt-4 flex flex-wrap gap-3">
              <ActionButton
                disabled={actionState === 'saving'}
                tone="emerald"
                onClick={() => {
                  void syncRecommendedPoyoDefaults()
                }}
              >
                {actionState === 'saving' ? '正在同步...' : '同步 PoYo 预设并设为默认'}
              </ActionButton>

              {!recommendationStatus.videoReady ? (
                <ActionButton
                  disabled={actionState === 'saving'}
                  tone="sky"
                  onClick={() => {
                    void switchVideoDefaultToSeedance()
                  }}
                >
                  仅切默认视频到 Seedance 2
                </ActionButton>
              ) : null}

              {syncableDefaultSummaries.length > 0 ? (
                <ActionButton
                  disabled={actionState === 'saving'}
                  tone="amber"
                  onClick={() => {
                    void syncCurrentDefaultCapabilities()
                  }}
                >
                  补齐当前默认模型能力字段
                </ActionButton>
              ) : null}
            </div>

            {actionMessage ? (
              <div className={`mt-3 text-xs leading-6 ${actionState === 'error' ? 'text-rose-300' : 'text-slate-400'}`}>
                {actionMessage}
              </div>
            ) : null}
          </div>

          <div className="mt-5 grid gap-4">
            {summaries.map((summary) => (
              <div key={summary.capability} className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-white">{CAPABILITY_LABELS[summary.capability]}</div>
                    <div className="mt-2 break-words text-sm text-slate-200">{summary.defaultLabel}</div>
                    <div className="mt-1 break-all text-xs text-slate-500">{summary.providerLabel}</div>
                    <div className="mt-1 text-xs text-slate-500">适配层：{summary.adapterLabel}</div>
                    <div className="mt-1 text-xs text-slate-500">配置来源：{summary.configSourceLabel}</div>
                  </div>
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[11px] ${
                      summary.readinessTone === 'ready'
                        ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
                        : summary.readinessTone === 'warning'
                          ? 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                          : 'border-rose-500/30 bg-rose-500/10 text-rose-200'
                    }`}
                  >
                    {summary.readinessLabel}
                  </span>
                </div>

                <div className="mt-3 text-xs leading-6 text-slate-400">{buildCapabilityHealthLine(summary)}</div>

                {summary.configNeedsSync ? (
                  <div className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs leading-6 text-amber-100">
                    当前默认模型缺少部分显式能力字段，页面已按已知模型预设补齐展示。使用上方“补齐当前默认模型能力字段”可把这些字段写回注册表。
                  </div>
                ) : null}

                <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <Metric title="生产用途" value={summary.routeLabel} />
                  <Metric title="任务模式" value={buildTaskModesLabel(summary.taskModes)} />
                  <Metric title={summary.capability === 'llm' ? '思考模式' : '参考图能力'} value={summary.capability === 'llm' ? summary.llmThinkingLabel : buildReferenceModeLabel(summary)} />
                  <Metric title={summary.capability === 'llm' ? '调用形态' : '轮询策略'} value={summary.capability === 'llm' ? 'Chat Completions' : summary.pollStrategy} />
                </div>

                <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <Metric title="图片 URL" value={summary.supportsImageUrl ? '支持' : '不支持'} />
                  <Metric title="文件上传" value={summary.supportsFileUpload ? '支持' : '不支持'} />
                  <Metric title="负向提示词" value={summary.supportsNegativePrompt ? '支持' : '不支持'} />
                  <Metric title="异步任务" value={summary.supportsAsyncTasks ? '支持' : '不支持'} />
                </div>

                {summary.capability === 'video' ? (
                  <div className="mt-3 grid gap-3 md:grid-cols-3">
                    <Metric title="首帧支持" value={summary.supportsFirstFrame ? '支持' : '不支持'} />
                    <Metric title="尾帧支持" value={summary.supportsLastFrame ? '支持' : '不支持'} />
                    <Metric title="音频支持" value={summary.supportsAudio ? '支持' : '不支持'} />
                  </div>
                ) : null}
              </div>
            ))}

            {defaultsState === 'error' ? (
              <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-100">
                默认模型信息加载失败。当前可以先打开注册表检查配置、密钥和连通性。
              </div>
            ) : null}
          </div>
        </div>

        <div className="min-w-0 space-y-6">
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
            <div className="text-sm font-medium text-white">能力矩阵</div>
            <div className="mt-3 text-sm leading-6 text-slate-400">
              这里强调“默认生产链路”能不能真正支撑当前项目，而不是只看是否存在某个模型配置。
            </div>
            <div className="mt-4 space-y-3">
              {summaries.map((summary) => (
                <div key={summary.capability} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-xs text-slate-500">{CAPABILITY_LABELS[summary.capability]}</div>
                    <span className="text-[11px] text-slate-400">{summary.modelName}</span>
                  </div>
                  <div className="mt-2 text-sm text-slate-300">{buildReferenceModeLabel(summary)}</div>
                  <div className="mt-2 text-[11px] leading-5 text-slate-500">{summary.routeLabel}</div>
                  <div className="mt-2 text-[11px] leading-5 text-slate-500">适配层：{summary.adapterLabel}</div>
                  <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
                    <Pill>{summary.supportsAsyncTasks ? '异步任务' : '同步任务'}</Pill>
                    {summary.capability === 'llm' ? <Pill>{summary.llmThinkingLabel}</Pill> : null}
                    <Pill>图片 URL {summary.supportsImageUrl ? '支持' : '不支持'}</Pill>
                    <Pill>文件上传 {summary.supportsFileUpload ? '支持' : '不支持'}</Pill>
                    <Pill>负向提示词 {summary.supportsNegativePrompt ? '支持' : '不支持'}</Pill>
                    <Pill>任务模式 {buildTaskModesLabel(summary.taskModes)}</Pill>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
            <div className="text-sm font-medium text-white">供应商适配配置</div>
            <div className="mt-3 text-sm leading-6 text-slate-400">
              业务页不直接硬编码供应商差异，统一从模型注册表读取默认模型，再交给统一适配层处理请求、轮询和结果回收。
            </div>
            <div className="mt-4 space-y-3">
              {summaries.map((summary) => (
                <div key={`${summary.capability}-adapter`} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-white">{CAPABILITY_LABELS[summary.capability]}</div>
                      <div className="mt-1 text-xs text-slate-500">{summary.modelName}</div>
                    </div>
                    <Pill>{summary.configSourceLabel}</Pill>
                  </div>
                  <div className="mt-3 grid gap-3 md:grid-cols-3">
                    <Metric title="统一适配层" value={summary.adapterLabel} />
                    <Metric title="输入契约" value={buildReferenceModeLabel(summary)} />
                    <Metric title="回收方式" value={summary.supportsAsyncTasks ? summary.pollStrategy : '同步直返'} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
            <div className="text-sm font-medium text-white">PoYo 模型接入建议</div>
            <div className="mt-3 text-sm leading-6 text-slate-400">
              这里把已经确认过的 PoYo 模型家族按“适用场景、参考图方式、任务模式”展开，避免业务页面再自己猜模型差异。
            </div>
            <div className="mt-4 space-y-4">
              {(['image', 'video'] as const).map((family) => (
                <div key={family} className="space-y-3">
                  <div className="text-xs uppercase tracking-[0.2em] text-slate-500">
                    {family === 'image' ? 'Image Models' : 'Video Models'}
                  </div>
                  <div className="grid gap-3">
                    {poyoGuidance
                      .filter((item) => item.family === family)
                      .map((item) => (
                        <div key={item.key} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <div className="text-sm font-medium text-white">{item.name}</div>
                              <div className="mt-1 text-xs text-slate-500">{item.modelName}</div>
                            </div>
                            <Pill>{item.referenceMode}</Pill>
                          </div>
                          <div className="mt-3 grid gap-3 md:grid-cols-3">
                            <Metric title="适用场景" value={item.useCase} />
                            <Metric title="推荐定位" value={item.recommendation} />
                            <Metric title="任务模式" value={item.taskModes} />
                          </div>
                        </div>
                      ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {registryOpen ? (
        <ModelRegistryModal
          data={registryData}
          error={registryError}
          onClose={() => setRegistryOpen(false)}
          onSaved={(payload) => {
            setRegistryData(payload)
            setDefaults(payload.default_profiles ?? {})
            setDefaultsState('idle')
          }}
        />
      ) : null}
    </>
  )
}

function Metric({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
      <div className="text-xs text-slate-500">{title}</div>
      <div className="mt-2 break-words text-sm leading-6 text-slate-300">{value}</div>
    </div>
  )
}

function Pill({ children }: { children: ReactNode }) {
  return <span className="rounded-full border border-slate-700 px-2 py-0.5 text-slate-300">{children}</span>
}

function ActionButton({
  children,
  disabled,
  tone,
  onClick,
}: {
  children: ReactNode
  disabled?: boolean
  tone: 'emerald' | 'sky' | 'amber'
  onClick: () => void
}) {
  const toneClass =
    tone === 'emerald'
      ? 'border-emerald-500/50 text-emerald-200 hover:border-emerald-400'
      : tone === 'sky'
        ? 'border-sky-500/50 text-sky-200 hover:border-sky-400'
        : 'border-amber-500/50 text-amber-200 hover:border-amber-400'

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-lg border px-4 py-2 text-sm font-medium transition hover:text-white disabled:cursor-not-allowed disabled:opacity-50 ${toneClass}`}
    >
      {children}
    </button>
  )
}

function describePresetUseCase(profile: ModelProfileRecord) {
  switch (normalizePoyoModelName(profile.model_name)) {
    case 'gpt-image-2':
      return '适合高遵循度静帧、资产补图和已有提示词精修。'
    case 'nano-banana-2':
      return '适合快速做风格探索、方案对比和低成本多轮试稿。'
    case 'seedream-5-0-lite-api':
      return '适合作为资产中心与分镜静帧的主力默认图像模型。'
    case 'seedance-2':
      return '适合作为默认视频生产链路，兼顾首尾帧、音频和分镜交付。'
    case 'kling-3.0/standard':
      return '适合做标准清晰度的视频预演与节奏验证。'
    case 'kling-3-api':
    case 'kling-3.0/pro':
      return '适合追求更高画质的正式镜头草稿输出。'
    case 'kling-3.0/4k':
      return '适合高分辨率交付前复核或重点镜头放大检查。'
    case 'happy-horse-1-1':
      return '适合从参考图直接起视频，快速做角色状态验证。'
    default:
      if (isPoyoKlingFamilyModel(profile.model_name)) {
        return '适合追求更高画质的正式镜头草稿输出。'
      }
      if (isPoyoSeedreamLiteModel(profile.model_name)) {
        return '适合作为资产中心与分镜静帧的主力默认图像模型。'
      }
      if (isPoyoNanoBananaModel(profile.model_name)) {
        return '适合快速做风格探索、方案对比和低成本多轮试稿。'
      }
      if (isPoyoHappyHorseModel(profile.model_name)) {
        return '适合从参考图直接起视频，快速做角色状态验证。'
      }
      return '适合接入当前创作链路中的对应媒体生成任务。'
  }
}

function describePresetRecommendation(profile: ModelProfileRecord) {
  switch (normalizePoyoModelName(profile.model_name)) {
    case 'seedream-5-0-lite-api':
      return '建议设为图像默认。'
    case 'seedance-2':
      return '建议设为视频默认。'
    case 'gpt-image-2':
      return '建议作为高要求补图与精修备选。'
    case 'nano-banana-2':
      return '建议作为探索型备选。'
    case 'happy-horse-1-1':
      return '建议保留为参考图驱动视频的补充链路。'
    default:
      return '建议作为专项镜头或高规格输出的补充模型。'
  }
}
