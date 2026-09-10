import { useEffect, useMemo, useState } from 'react'
import { fetchModelRegistry, type ModelProfileRecord } from '../services/modelRegistry'
import {
  fetchAgentModelConfig,
  saveAgentModelConfig,
  type AgentModelConfig,
} from '../services/agentModelConfig'

export default function AgentModelConfigPanel() {
  const [config, setConfig] = useState<AgentModelConfig | null>(null)
  const [profiles, setProfiles] = useState<ModelProfileRecord[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [message, setMessage] = useState('')
  const [saving, setSaving] = useState(false)
  const [budget, setBudget] = useState('0')
  const [thinking, setThinking] = useState<'enabled' | 'disabled'>('disabled')
  const [visionEnabled, setVisionEnabled] = useState(false)

  useEffect(() => {
    void Promise.all([fetchAgentModelConfig(), fetchModelRegistry()])
      .then(([nextConfig, registry]) => {
        setConfig(nextConfig)
        setSelectedId(nextConfig.profile_id)
        setThinking(nextConfig.runtime_policy?.thinking ?? 'disabled')
        setVisionEnabled(nextConfig.runtime_policy?.vision_enabled ?? false)
        setProfiles(registry.profiles.filter((profile) => profile.capability === 'llm' && profile.enabled))
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : '加载智能导演台模型配置失败'))
    void fetch('/api/agent/budget').then((response) => response.json()).then((value) => setBudget(String(value.max_estimated_tokens || 0))).catch(() => undefined)
  }, [])

  const selectedProfile = useMemo(
    () => profiles.find((profile) => profile.id === selectedId) ?? config?.profile ?? null,
    [config?.profile, profiles, selectedId],
  )

  const save = async () => {
    setSaving(true)
    setMessage('正在保存独立 Agent 模型配置…')
    try {
      const next = await saveAgentModelConfig(selectedId, thinking, visionEnabled)
      setConfig(next)
      setSelectedId(next.profile_id)
      setThinking(next.runtime_policy?.thinking ?? 'disabled')
      setVisionEnabled(next.runtime_policy?.vision_enabled ?? false)
      setMessage(next.configured ? '智能导演台模型已保存。它不会替换生产链路默认 LLM。' : '已清除智能导演台独立模型；未配置时不能发起 Agent 模型调用。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '保存智能导演台模型配置失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <details className="mt-4 rounded-lg border border-slate-800 bg-slate-900/50 p-3">
      <summary className="cursor-pointer text-sm font-medium text-slate-300">管理员配置：智能导演台模型</summary>
      <div className="mt-2 text-xs leading-6 text-slate-500">
        智能导演台独立选择一个已注册 LLM Profile；只保存引用，不复制密钥，不替换正式生产链路的默认 LLM。仅当用户在抽屉中预览后逐次确认时，才会调用该模型生成候选草案。
      </div>
      <label className="mt-3 block text-xs text-slate-300" htmlFor="agent-model-profile">Agent 模型</label>
      <select
        id="agent-model-profile"
        value={selectedId}
        onChange={(event) => setSelectedId(event.target.value)}
        className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
      >
        <option value="">暂不配置（不能调用 Agent 模型）</option>
        {profiles.map((profile) => (
          <option key={profile.id} value={profile.id}>
            {profile.name} · {profile.model_name || profile.provider}{profile.key_configured ? '' : '（未配置 Key）'}
          </option>
        ))}
      </select>
      {selectedProfile ? (
        <div className="mt-2 text-[11px] text-slate-400">
          当前候选：{selectedProfile.provider} / {selectedProfile.base_url || '内置路由'} / {selectedProfile.model_name || '未声明模型名'}
          <div className="mt-1">模型客观能力：{selectedProfile.default_params?.supports_vision ? '支持图片理解' : '未声明图片理解'}；模型默认思考参数仅作参考。</div>
        </div>
      ) : null}
      <div className="mt-3 space-y-2 rounded-md border border-slate-800 bg-slate-950/60 p-2.5">
        <div className="text-xs font-medium text-slate-300">Agent 运行策略（独立于模型管理）</div>
        <label className="flex items-center gap-2 text-xs text-slate-300">
          <input type="checkbox" checked={thinking === 'enabled'} onChange={(event) => setThinking(event.target.checked ? 'enabled' : 'disabled')} />
          开启思考
        </label>
        <label className="flex items-center gap-2 text-xs text-slate-300">
          <input type="checkbox" checked={visionEnabled} onChange={(event) => setVisionEnabled(event.target.checked)} />
          允许 Agent 读取对话中的图片
        </label>
        <div className="text-[11px] leading-5 text-slate-500">
          这些开关只影响智能导演台。图片读取必须同时满足模型支持图片理解和这里已允许；不会修改正式生产模型设置。
          {!selectedProfile?.default_params?.supports_vision ? ' 当前模型尚未声明图片理解能力；即使勾选，图片也不会发送，需先在模型能力事实中补充声明。' : ''}
        </div>
      </div>
      <button
        type="button"
        onClick={() => void save()}
        disabled={saving}
        className="mt-3 rounded-md border border-violet-400/50 px-3 py-1.5 text-xs font-medium text-violet-100 transition hover:bg-violet-500/15 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {saving ? '保存中…' : '保存 Agent 模型'}
      </button>
      {message ? <div role="status" aria-live="polite" className="mt-2 text-xs text-slate-400">{message}</div> : null}
      <div className="mt-4 border-t border-slate-800 pt-3">
        <label className="block text-xs text-slate-300" htmlFor="agent-token-budget">单次 Agent token 上限（0 为不限制）</label>
        <div className="mt-1 flex gap-2"><input id="agent-token-budget" type="number" min="0" max="100000" value={budget} onChange={(event) => setBudget(event.target.value)} className="w-32 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-xs" /><button type="button" onClick={() => void fetch('/api/agent/budget', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ maxEstimatedTokens: Number(budget) || 0 }) }).then(() => setMessage('Agent token 上限已保存。')).catch((error) => setMessage(error instanceof Error ? error.message : '保存 token 上限失败'))} className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200">保存上限</button></div>
      </div>
    </details>
  )
}
