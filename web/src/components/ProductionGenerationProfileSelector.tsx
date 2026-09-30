import { useEffect, useMemo, useState } from 'react'
import {
  fetchProductionGenerationProfiles,
  persistProductionModelSelection,
  profilesForTarget,
  readProductionModelSelection,
  selectedProfileIdForTarget,
  type ProductionGenerationTarget,
  type SharedProductionModelSelection,
} from '../services/productionModelSelection'
import type { ModelProfileRecord } from '../services/modelRegistry'

export interface ProductionGenerationProfileSelectorProps {
  target: ProductionGenerationTarget
  selectedProfileId?: string | null
  disabled?: boolean
  mutationBusy?: boolean
  onChange?: (profileId: string | null) => void
  onRefresh?: () => Promise<void> | void
}

export function ProductionGenerationProfileSelector({ target, selectedProfileId = null, disabled = false, mutationBusy = false, onChange, onRefresh }: ProductionGenerationProfileSelectorProps) {
  const [profiles, setProfiles] = useState<ModelProfileRecord[]>([])
  const [selection, setSelection] = useState<SharedProductionModelSelection>(() => readProductionModelSelection())
  const [error, setError] = useState<string | null>(null)
  const busy = disabled || mutationBusy
  const options = useMemo(() => profilesForTarget(profiles, target), [profiles, target])
  const storedProfileId = selectedProfileIdForTarget(selection, target)
  const value = selectedProfileId && options.some((profile) => profile.id === selectedProfileId) ? selectedProfileId : storedProfileId && options.some((profile) => profile.id === storedProfileId) ? storedProfileId : ''

  useEffect(() => {
    let cancelled = false
    fetchProductionGenerationProfiles().then((next) => {
      if (!cancelled) { setProfiles(next); setError(null) }
    }).catch((reason) => {
      if (!cancelled) { setProfiles([]); setError(reason instanceof Error ? reason.message : '模型注册表读取失败') }
    })
    return () => { cancelled = true }
  }, [])

  const handleChange = async (nextId: string) => {
    const next = { ...selection, ...(target === 'IMAGE' ? { imageModelProfileId: nextId || null } : { videoModelProfileId: nextId || null }) }
    setSelection(next)
    persistProductionModelSelection(next)
    onChange?.(nextId || null)
    await onRefresh?.()
  }

  return <label data-testid={`production-model-selector-${target.toLowerCase()}`} className="block text-xs text-[#A9B4B3]">
    <span className="mb-1 block uppercase tracking-[0.12em] text-[#728082]">{target} 模型配置</span>
    <select aria-label={`${target} 生成模型`} disabled={busy} value={value} onChange={(event) => { void handleChange(event.target.value) }} className="w-full border border-[#2A3437] bg-[#1A2225] px-2 py-2 text-xs text-[#EDF1EF] outline-none focus:border-[#8BC9D9] disabled:cursor-not-allowed disabled:opacity-50">
      <option value="">请选择模型配置</option>
      {options.map((profile) => <option key={profile.id} value={profile.id}>{profile.name} · {profile.id}</option>)}
    </select>
    {error ? <span role="alert" className="mt-1 block text-[10px] text-[#DF8E8C]">{error}</span> : null}
    {!error && !options.length ? <span className="mt-1 block text-[10px] text-[#DBB36F]">当前能力没有可用模型配置。</span> : null}
    {!error && selectedProfileId && !options.some((profile) => profile.id === selectedProfileId) ? <span className="mt-1 block text-[10px] text-[#DF8E8C]">当前模型配置已不可用，请重新选择。</span> : null}
  </label>
}

export default ProductionGenerationProfileSelector
