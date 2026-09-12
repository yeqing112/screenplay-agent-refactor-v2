import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import ModelRegistryModal, {
  buildPoyoPresetProfiles,
  buildShapiPresetProfiles,
} from './ModelRegistryModal'
import AgentModelConfigPanel from './AgentModelConfigPanel'
import {
  fetchModelRegistry,
  fetchModelRegistryDefaults,
  saveModelRegistry,
  type ModelCapability,
  type ModelProfileRecord,
  type ModelRegistryPayload,
} from '../services/modelRegistry'
import {
  fetchPublicAssetStorageConfig,
  fetchPublicAssetStorageMigrationPlan,
  executePublicAssetStorageMigration,
  fetchPublicAssetStorageMigrationRecord,
  savePublicAssetStorageConfig,
  type PublicAssetStorageConfig,
  type PublicAssetStorageMigrationPlan,
  type PublicAssetStorageMigrationRecord,
} from '../services/publicAssetStorage'
import {
  buildCapabilityHealthLine,
  buildCapabilitySummary,
  buildPublicAssetDomainRequirement,
  buildReferenceModeLabel,
  buildSyncedCapabilityParams,
  buildTaskModesLabel,
  isProductionSafePublicAssetDomain,
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
  const [storageConfig, setStorageConfig] = useState<PublicAssetStorageConfig | null>(null)
  const [storageDraft, setStorageDraft] = useState({
    provider: 'qiniu',
    local_base_url: 'http://127.0.0.1:18765',
    qiniu_access_key: '',
    qiniu_secret_key: '',
    qiniu_bucket: '',
    qiniu_region: 'z2',
    qiniu_public_base_url: '',
    qiniu_bucket_private: true,
    qiniu_key_prefix: 'screenplay-agent',
    qiniu_upload_token_expires_seconds: 3600,
    qiniu_public_url_ttl_seconds: 86400,
  })
  const [storageState, setStorageState] = useState<ActionState | 'loading'>('loading')
  const [storageMessage, setStorageMessage] = useState('')
  const [migrationPlan, setMigrationPlan] = useState<PublicAssetStorageMigrationPlan | null>(null)
  const [migrationRecord, setMigrationRecord] = useState<PublicAssetStorageMigrationRecord | null>(null)

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

  const refreshStorageConfig = useCallback(async () => {
    setStorageState('loading')
    try {
      const payload = await fetchPublicAssetStorageConfig()
      setStorageConfig(payload)
      setStorageDraft((current) => ({
        ...current,
        provider: payload.provider || 'qiniu',
        local_base_url: payload.local_base_url || 'http://127.0.0.1:18765',
        qiniu_access_key: '',
        qiniu_secret_key: '',
        qiniu_bucket: payload.qiniu_bucket || '',
        qiniu_region: payload.qiniu_region || 'z2',
        qiniu_public_base_url: payload.qiniu_public_base_url || '',
        qiniu_bucket_private: payload.qiniu_bucket_private,
        qiniu_key_prefix: payload.qiniu_key_prefix || 'screenplay-agent',
        qiniu_upload_token_expires_seconds: payload.qiniu_upload_token_expires_seconds || 3600,
        qiniu_public_url_ttl_seconds: payload.qiniu_public_url_ttl_seconds || 86400,
      }))
      setStorageState('idle')
    } catch (error) {
      setStorageState('error')
      setStorageMessage(error instanceof Error ? error.message : '对象存储配置加载失败')
    }
  }, [])

  useEffect(() => {
    void refreshStorageConfig()
  }, [refreshStorageConfig])

  const saveStorageConfig = useCallback(async () => {
    setStorageState('saving')
    setStorageMessage('')
    try {
      const saved = await savePublicAssetStorageConfig(storageDraft)
      setStorageConfig(saved)
      setStorageDraft((current) => ({ ...current, qiniu_access_key: '', qiniu_secret_key: '' }))
      setStorageState('success')
      setStorageMessage(
        saved.enabled && isProductionSafePublicAssetDomain(saved.qiniu_public_base_url)
          ? '对象存储配置已保存，H3 参考资产公网中转可用。'
          : saved.enabled
            ? `对象存储配置已保存，但${buildPublicAssetDomainRequirement(saved.qiniu_public_base_url)}`
            : '对象存储配置已保存，但密钥、Bucket 或访问域名仍未完整。',
      )
    } catch (error) {
      setStorageState('error')
      setStorageMessage(error instanceof Error ? error.message : '对象存储配置保存失败')
    }
  }, [storageDraft])

  const loadMigrationPlan = useCallback(async () => {
    setStorageState('saving')
    setStorageMessage('正在生成迁移计划；默认先快扫来源类型，不会写入或改库。')
    try {
      const plan = await fetchPublicAssetStorageMigrationPlan(200)
      setMigrationPlan(plan)
      setStorageState('success')
      setStorageMessage('迁移计划已生成；当前只做规划，不会搬迁或改写资产。')
    } catch (error) {
      setStorageState('error')
      setStorageMessage(error instanceof Error ? error.message : '迁移计划生成失败')
    }
  }, [])

  const executeMigrationPlan = useCallback(async () => {
    if (!migrationPlan) return
    if (!window.confirm(`确认迁移 ${migrationPlan.summary.requires_migration} 个资产引用到当前对象存储吗？\n\n此操作会上传新对象并改写对应引用；旧对象不会被删除。失败项不会自动重试。`)) return
    setStorageState('saving')
    setStorageMessage('正在提交受保护的对象存储迁移任务…')
    try {
      const submitted = await executePublicAssetStorageMigration(migrationPlan)
      const refreshRecord = async () => {
        const record = await fetchPublicAssetStorageMigrationRecord(submitted.record_id)
        setMigrationRecord(record)
        if (record.status === 'queued' || record.status === 'running') {
          window.setTimeout(() => { void refreshRecord() }, 1200)
          return
        }
        setStorageState(record.status === 'completed' ? 'success' : 'error')
        setStorageMessage(record.status === 'completed' ? '对象存储迁移已完成；旧对象未删除。' : `迁移结束：成功 ${record.result.migrated || 0}，失败 ${record.result.failed || 0}。失败项可重新生成计划后人工确认重试。`)
      }
      await refreshRecord()
    } catch (error) {
      setStorageState('error')
      setStorageMessage(error instanceof Error ? error.message : '对象存储迁移提交失败')
    }
  }, [migrationPlan])

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

  const shapiGuidance = useMemo(() => buildShapiPresetProfiles().map((preset) => ({
    key: preset.id,
    name: preset.name,
    modelName: preset.model_name,
    useCase: preset.provider === 'shapi-gemini-image'
      ? '正式资产与分镜静帧：将锁定的 HTTPS 参考资产以内联图片方式提交。'
      : '无参考图的高质量文生图备选；参考图请求会被明确拒绝，避免静默失真。',
    referenceMode: buildReferenceModeLabel(buildCapabilitySummary(preset.capability, preset)),
    taskModes: buildTaskModesLabel(
      Array.isArray(preset.default_params?.task_modes)
        ? preset.default_params.task_modes.filter((item): item is string => typeof item === 'string')
        : [],
    ),
  })), [])

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

  const syncPoyoPresetCatalog = useCallback(async () => {
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

      // Presets are optional catalog entries.  They must never silently replace
      // a user's current production default (or its configured key).
      await persistRegistrySnapshot(payload, mergedProfiles, toSaveableDefaults(payload.defaults ?? {}))

      setActionState('success')
      setActionMessage(
        [
          createdCount > 0 ? `新增 ${createdCount} 个 PoYo 预设` : null,
          updatedCount > 0 ? `更新 ${updatedCount} 个预设能力字段` : null,
          '未修改任何当前默认模型、密钥或生产路由',
        ]
          .filter(Boolean)
          .join('，') + '。',
      )
    } catch (error) {
      setActionState('error')
      setActionMessage(error instanceof Error ? error.message : '同步 PoYo 预设失败')
    }
  }, [persistRegistrySnapshot, registryData])

  const addShapiImagePresets = useCallback(async () => {
    setActionState('saving')
    setActionMessage('')
    try {
      const payload = registryData ?? (await fetchModelRegistry())
      const presetMap = new Map(buildShapiPresetProfiles().map((item) => [item.id, item]))
      const nextProfiles = payload.profiles.map((item) => {
        const preset = presetMap.get(item.id)
        if (!preset) return item
        presetMap.delete(item.id)
        return {
          ...preset,
          api_key: item.api_key,
          key_configured: item.key_configured || Boolean(item.api_key),
          builtin: item.builtin,
          is_default: item.is_default,
          source: item.source,
        }
      })
      nextProfiles.push(...presetMap.values())
      await persistRegistrySnapshot(payload, nextProfiles, toSaveableDefaults(payload.defaults ?? {}))
      setActionState('success')
      setActionMessage('SHAPI GPT Image 2 预设已添加；未修改任何默认模型或已有密钥。')
    } catch (error) {
      setActionState('error')
      setActionMessage(error instanceof Error ? error.message : '添加 SHAPI 图像预设失败')
    }
  }, [persistRegistrySnapshot, registryData])

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

  const hasProductionSafeStorageDomain = Boolean(storageConfig?.enabled) && isProductionSafePublicAssetDomain(storageDraft.qiniu_public_base_url)
  const storageDomainRequirement = buildPublicAssetDomainRequirement(storageDraft.qiniu_public_base_url)

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
            <div className="text-sm font-medium text-white">当前实际生效的生产模型</div>
            <div className="mt-2 text-sm leading-6 text-slate-400">
              以下是正式工作台现在真正会使用的模型。不会因为目录里存在候选模型而自动切换；修改默认值、密钥或协议请进入注册表并人工保存。
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              {summaries.map((summary) => (
                <Metric key={`current-${summary.capability}`} title={CAPABILITY_LABELS[summary.capability]} value={summary.defaultLabel} />
              ))}
            </div>

            <details className="mt-4 rounded-lg border border-slate-800 bg-slate-900/50 p-3">
              <summary className="cursor-pointer text-sm font-medium text-slate-300">高级：添加候选模型与同步能力字段</summary>
              <div className="mt-2 text-xs leading-6 text-slate-500">
                这些操作只维护模型目录或补齐当前默认模型的能力描述；不会更换默认模型、覆盖密钥，也不会触发任何生成。
              </div>
              <div className="mt-3 flex flex-wrap gap-3">
                <ActionButton disabled={actionState === 'saving'} tone="emerald" onClick={() => void syncPoyoPresetCatalog()}>
                  {actionState === 'saving' ? '正在同步...' : '同步 PoYo 候选预设'}
                </ActionButton>
                <ActionButton disabled={actionState === 'saving'} tone="sky" onClick={() => void addShapiImagePresets()}>
                  添加 SHAPI 图片候选预设
                </ActionButton>
                {syncableDefaultSummaries.length > 0 ? (
                  <ActionButton disabled={actionState === 'saving'} tone="amber" onClick={() => void syncCurrentDefaultCapabilities()}>
                    补齐当前默认模型能力字段
                  </ActionButton>
                ) : null}
              </div>
            </details>

            {actionMessage ? (
              <div role="status" aria-live="polite" className={`mt-3 text-xs leading-6 ${actionState === 'error' ? 'text-rose-300' : 'text-slate-400'}`}>
                {actionMessage}
              </div>
            ) : null}
            <AgentModelConfigPanel />
          </div>

          <details className="mt-5 rounded-xl border border-slate-800 bg-slate-950/30 p-4">
            <summary className="cursor-pointer text-sm font-medium text-slate-300">高级：查看模型能力、协议与健康详情</summary>
            <div className="mt-2 text-xs leading-6 text-slate-500">
              这里用于排查供应商适配、参考图能力与轮询策略。日常创作只需关注上方的生产模型状态。
            </div>
            <div className="mt-4 grid gap-4">
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
              <div role="alert" className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-100">
                默认模型信息加载失败。当前可以先打开注册表检查配置、密钥和连通性。
              </div>
            ) : null}
            </div>
          </details>
        </div>

        <div className="min-w-0 space-y-6">
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-white">对象存储 / 参考资产公网中转</div>
                <div className="mt-2 text-sm leading-6 text-slate-400">
                  本地工作台生成或手动上传的参考图、分镜图需要先进入公网对象存储，MiniMax H3 才能稳定拉取。Secret 不会回显；留空会保留后台已保存密钥。
                </div>
              </div>
              <span
                className={`rounded-full border px-2 py-0.5 text-[11px] ${
                  hasProductionSafeStorageDomain
                    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
                    : 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                }`}
              >
                {storageConfig?.enabled
                  ? hasProductionSafeStorageDomain
                    ? '中转可用'
                    : '需 HTTPS 域名'
                  : storageState === 'loading'
                    ? '读取中'
                    : '待配置'}
              </span>
            </div>

            <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-sm leading-6 text-slate-300">
              {storageConfig?.enabled && !hasProductionSafeStorageDomain
                ? `对象存储密钥和 Bucket 已配置，但${storageDomainRequirement}`
                : storageConfig?.enabled
                  ? '参考资产可通过已配置的公网中转供视频模型读取。'
                : '视频生成需要先由管理员完成对象存储配置，确保参考资产可被外部模型读取。'}
            </div>
            {storageConfig?.enabled && !hasProductionSafeStorageDomain ? (
              <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs leading-6 text-amber-100">
                {storageDomainRequirement}
              </div>
            ) : null}

            <details className="mt-4 rounded-lg border border-slate-800 bg-slate-950/30 p-3">
              <summary className="cursor-pointer text-sm font-medium text-slate-300">管理员配置：对象存储、密钥与迁移</summary>
              <div className="mt-2 text-xs leading-6 text-slate-500">
                此处包含 Bucket、访问域名、密钥和资产迁移。保存或迁移都会影响生产基础设施，请仅由管理员操作。
              </div>

            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <Field label="Provider">
                <select
                  value={storageDraft.provider}
                  onChange={(event) => setStorageDraft((current) => ({ ...current, provider: event.target.value }))}
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                >
                  <option value="qiniu">七牛 Kodo</option>
                </select>
              </Field>
              <Field label="本地后端地址">
                <input
                  value={storageDraft.local_base_url}
                  onChange={(event) => setStorageDraft((current) => ({ ...current, local_base_url: event.target.value }))}
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                />
              </Field>
              <Field label="Bucket">
                <input
                  value={storageDraft.qiniu_bucket}
                  onChange={(event) => setStorageDraft((current) => ({ ...current, qiniu_bucket: event.target.value }))}
                  placeholder="例如：ai-ku01"
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                />
              </Field>
              <Field label="Region">
                <input
                  value={storageDraft.qiniu_region}
                  onChange={(event) => setStorageDraft((current) => ({ ...current, qiniu_region: event.target.value }))}
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                />
              </Field>
              <Field label="公网访问域名">
                <input
                  value={storageDraft.qiniu_public_base_url}
                  onChange={(event) => setStorageDraft((current) => ({ ...current, qiniu_public_base_url: event.target.value }))}
                  placeholder="例如：https://assets.example.com"
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                />
              </Field>
              <Field label="对象前缀">
                <input
                  value={storageDraft.qiniu_key_prefix}
                  onChange={(event) => setStorageDraft((current) => ({ ...current, qiniu_key_prefix: event.target.value }))}
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                />
              </Field>
              <Field label={`AccessKey${storageConfig?.qiniu_access_key_configured ? '（已保存，留空不改）' : ''}`}>
                <input
                  value={storageDraft.qiniu_access_key}
                  onChange={(event) => setStorageDraft((current) => ({ ...current, qiniu_access_key: event.target.value }))}
                  type="password"
                  autoComplete="off"
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                />
              </Field>
              <Field label={`SecretKey${storageConfig?.qiniu_secret_key_configured ? '（已保存，留空不改）' : ''}`}>
                <input
                  value={storageDraft.qiniu_secret_key}
                  onChange={(event) => setStorageDraft((current) => ({ ...current, qiniu_secret_key: event.target.value }))}
                  type="password"
                  autoComplete="off"
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                />
              </Field>
            </div>

            <label className="mt-3 flex items-center gap-2 text-xs text-slate-300">
              <input
                type="checkbox"
                checked={storageDraft.qiniu_bucket_private}
                onChange={(event) => setStorageDraft((current) => ({ ...current, qiniu_bucket_private: event.target.checked }))}
              />
              私有 Bucket，提交给 H3 时使用限时签名 URL
            </label>

            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <Metric title="AccessKey" value={storageConfig?.qiniu_access_key_configured ? '已保存' : '未保存'} />
              <Metric title="SecretKey" value={storageConfig?.qiniu_secret_key_configured ? '已保存' : '未保存'} />
              <Metric title="当前限制" value={hasProductionSafeStorageDomain ? 'HTTPS 自定义域名' : '需 HTTPS 自定义域名'} />
            </div>

            <div className="mt-4 flex flex-wrap gap-3">
              <ActionButton disabled={storageState === 'saving'} tone="emerald" onClick={() => void saveStorageConfig()}>
                {storageState === 'saving' ? '处理中...' : '保存对象存储配置'}
              </ActionButton>
              <ActionButton disabled={storageState === 'saving'} tone="amber" onClick={() => void loadMigrationPlan()}>
                生成迁移计划
              </ActionButton>
              {migrationPlan?.migration_apply_supported && migrationPlan.summary.requires_migration > 0 ? <ActionButton disabled={storageState === 'saving'} tone="amber" onClick={() => void executeMigrationPlan()}>
                确认执行迁移
              </ActionButton> : null}
              <ActionButton disabled={storageState === 'saving'} tone="slate" onClick={() => void refreshStorageConfig()}>
                刷新配置
              </ActionButton>
            </div>

            {storageMessage ? (
              <div role="status" aria-live="polite" className={`mt-3 text-xs leading-6 ${storageState === 'error' ? 'text-rose-300' : 'text-slate-400'}`}>
                {storageMessage}
              </div>
            ) : null}

            {migrationPlan ? (
              <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/70 p-3 text-xs leading-6 text-slate-300">
                <div className="font-medium text-white">迁移规划摘要</div>
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  <div>扫描资产：{migrationPlan.summary.total_scanned}</div>
                  <div>建议迁移：{migrationPlan.summary.requires_migration}</div>
                  <div>本地/内联待发布：{migrationPlan.summary.needs_publish}</div>
                  <div>外部待深度检查：{migrationPlan.summary.external_unchecked}</div>
                  <div>外部不可读：{migrationPlan.summary.external_unreachable}</div>
                </div>
                <div className="mt-2 text-slate-500">{migrationPlan.migration_apply_note}</div>
              </div>
            ) : null}
            {migrationRecord ? <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/70 p-3 text-xs leading-6 text-slate-300">
              <div className="font-medium text-white">迁移执行记录 · {migrationRecord.status}</div>
              <div className="mt-1">成功：{migrationRecord.result.migrated || 0} · 失败：{migrationRecord.result.failed || 0} · 旧对象删除：否</div>
              {migrationRecord.error_report.length ? <div className="mt-1 text-amber-200">存在 {migrationRecord.error_report.length} 个失败项；系统未自动重试，请重新生成当前计划后再人工确认。</div> : null}
            </div> : null}
            </details>
          </div>

          <details className="rounded-xl border border-slate-800 bg-slate-900 p-5">
            <summary className="cursor-pointer text-sm font-medium text-slate-300">管理员参考：能力矩阵、供应商适配与候选模型</summary>
            <div className="mt-2 text-xs leading-6 text-slate-500">
              这些是接入和排障资料，不会改变当前默认模型或触发生成。
            </div>
            <div className="mt-5 space-y-6">
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

          <div className="rounded-xl border border-sky-500/20 bg-slate-900 p-5">
            <div className="text-sm font-medium text-white">SHAPI 图片模型接入</div>
            <div className="mt-3 text-sm leading-6 text-slate-400">
              当前仅提供 SHAPI GPT Image 2：走 OpenAI Images 协议，仅开放无参考图文生图；检测到参考图时会明确拒绝，避免把资产约束静默丢弃。
            </div>
            <div className="mt-4 grid gap-3">
              {shapiGuidance.map((item) => (
                <div key={item.key} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-white">{item.name}</div>
                      <div className="mt-1 text-xs text-slate-500">{item.modelName}</div>
                    </div>
                    <Pill>{item.referenceMode}</Pill>
                  </div>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    <Metric title="适用场景" value={item.useCase} />
                    <Metric title="任务模式" value={item.taskModes} />
                  </div>
                </div>
              ))}
            </div>
          </div>
            </div>
          </details>
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

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <div className="mb-1 text-xs text-slate-500">{label}</div>
      {children}
    </label>
  )
}

function ActionButton({
  children,
  disabled,
  tone,
  onClick,
}: {
  children: ReactNode
  disabled?: boolean
  tone: 'emerald' | 'sky' | 'amber' | 'slate'
  onClick: () => void
}) {
  const toneClass =
    tone === 'emerald'
      ? 'border-emerald-500/50 text-emerald-200 hover:border-emerald-400'
      : tone === 'sky'
        ? 'border-sky-500/50 text-sky-200 hover:border-sky-400'
        : tone === 'amber'
          ? 'border-amber-500/50 text-amber-200 hover:border-amber-400'
          : 'border-slate-600 text-slate-300 hover:border-slate-400'

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
      return '适合当前项目的正式生图主链路、资产补图和已有提示词精修。'
    case 'nano-banana-2':
      return '适合快速做风格探索、方案对比和低成本多轮试稿。'
    case 'seedream-5-0-lite-api':
      return '适合作为资产中心与分镜静帧的备选图像模型。'
    case 'seedance-2':
      return '适合作为可选视频链路，兼顾首尾帧、音频和分镜交付。'
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
        return '适合作为资产中心与分镜静帧的备选图像模型。'
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
    case 'gpt-image-2':
      return '可选的正式生图候选；只有在注册表中人工设为默认后才会生效。'
    case 'seedream-5-0-lite-api':
      return '保留为可选图像备选，不替换当前默认。'
    case 'seedance-2':
      return '保留为可选视频备选，暂不设为默认。'
    case 'nano-banana-2':
      return '可作为探索型候选；不代表当前默认。'
    case 'happy-horse-1-1':
      return '建议保留为参考图驱动视频的补充链路。'
    default:
      return '可作为专项镜头或高规格输出候选；不代表当前默认。'
  }
}
