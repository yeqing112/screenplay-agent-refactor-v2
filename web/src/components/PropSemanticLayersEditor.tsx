import { useEffect, useMemo, useState } from 'react'
import type { AssetSummary } from './productWorkspaceAssets'
import type { GenerateReferenceOptions } from './productWorkspaceAssetActions'

type Layer = Record<string, unknown>
type Mode = NonNullable<GenerateReferenceOptions['sceneLayerMode']>

function read(asset: AssetSummary) {
  const raw = asset.structuredVariantFields?.semantic_layers
  const layers = raw && typeof raw === 'object' ? raw as Record<string, unknown> : {}
  return {
    canonical: layers.canonical && typeof layers.canonical === 'object' ? { ...(layers.canonical as Layer) } : {},
    state: layers.state && typeof layers.state === 'object' ? { ...(layers.state as Layer) } : {},
    look: layers.look && typeof layers.look === 'object' ? { ...(layers.look as Layer) } : {},
  }
}

function value(layer: Layer, key: string) {
  const item = layer[key]
  return Array.isArray(item) ? item.join('、') : item && typeof item === 'object' ? JSON.stringify(item) : String(item ?? '')
}

function update(layer: Layer, key: string, text: string) {
  return { ...layer, [key]: key === 'tags' || key === 'state_notes' ? text.split(/[、,，\n]/).map((item) => item.trim()).filter(Boolean) : text }
}

export default function PropSemanticLayersEditor({ bookId, asset, onRefresh, onGenerate }: { bookId: number; asset: AssetSummary; onRefresh?: () => void; onGenerate?: (options?: GenerateReferenceOptions) => void }) {
  const initial = useMemo(() => read(asset), [asset])
  const [canonical, setCanonical] = useState<Layer>(initial.canonical)
  const [state, setState] = useState<Layer>(initial.state)
  const [look, setLook] = useState<Layer>(initial.look)
  const [mode, setMode] = useState<Mode>('combined')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  useEffect(() => { setCanonical(initial.canonical); setState(initial.state); setLook(initial.look) }, [initial])
  if (asset.category !== 'prop' || !asset.assetRecordId) return null

  const fields = (title: string, layer: Layer, setter: (next: Layer) => void, keys: string[]) => (
    <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
      <div className="text-xs font-medium text-slate-200">{title}</div>
      <div className="mt-2 space-y-2">{keys.map((key) => <label key={key} className="block"><span className="text-[11px] text-slate-500">{key}</span><textarea value={value(layer, key)} onChange={(event) => setter(update(layer, key, event.target.value))} rows={key === 'description' ? 2 : 1} className="mt-1 w-full resize-y rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-slate-200" placeholder="可留空；只填写该层负责的事实" /></label>)}</div>
    </div>
  )

  const save = async () => {
    setSaving(true); setMessage('')
    try {
      const response = await fetch(`/api/books/${bookId}/visual-assets/prop/${asset.assetRecordId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ canonicalFacts: canonical, stateVariants: state, lookProfile: look }) })
      if (!response.ok) throw new Error(`保存道具语义失败：HTTP ${response.status}`)
      setMessage('已保存。生成时可选择中性、状态或 Look 版本。'); onRefresh?.()
    } catch (error) { setMessage(error instanceof Error ? error.message : '保存道具语义失败') } finally { setSaving(false) }
  }

  return <div className="mt-4 rounded-lg border border-amber-500/25 bg-amber-500/5 p-3" data-testid="prop-semantic-layers-editor">
    <div className="text-xs font-medium text-amber-100">道具三层语义（可编辑）</div>
    <div className="mt-1 text-[11px] leading-5 text-amber-100/70">把道具身份、使用状态和材质 Look 分开，避免磨损或临时状态污染基础资产。</div>
    <div className="mt-3 grid gap-3 lg:grid-cols-3">
      {fields('道具本体', canonical, setCanonical, ['category', 'description', 'associated_characters'])}
      {fields('道具状态', state, setState, ['active', 'condition', 'usage', 'state_notes'])}
      {fields('道具 Look', look, setLook, ['material', 'style', 'palette', 'surface'])}
    </div>
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <select value={mode} onChange={(event) => setMode(event.target.value as Mode)} className="rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-slate-200"><option value="combined">生成：状态 + Look 合成图</option><option value="canonical">生成：中性道具图</option><option value="state">生成：指定状态图</option><option value="look">生成：指定 Look 图</option></select>
      <button type="button" onClick={() => onGenerate?.({ sceneLayerMode: mode })} disabled={!onGenerate} className="rounded border border-sky-500/50 bg-sky-500/10 px-3 py-1.5 text-xs text-sky-100 disabled:opacity-50">生成当前版本</button>
      <button type="button" onClick={() => void save()} disabled={saving} className="rounded border border-emerald-500/50 bg-emerald-500/10 px-3 py-1.5 text-xs text-emerald-100 disabled:opacity-50">{saving ? '保存中…' : '保存三层语义'}</button>
      {message ? <span role="status" className="text-[11px] text-slate-300">{message}</span> : null}
    </div>
  </div>
}

