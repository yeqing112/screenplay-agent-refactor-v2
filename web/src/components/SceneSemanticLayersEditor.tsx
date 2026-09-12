import { useEffect, useMemo, useState } from 'react'
import type { AssetSummary } from './productWorkspaceAssets'
import type { GenerateReferenceOptions } from './productWorkspaceAssetActions'

type SceneLayerMode = NonNullable<GenerateReferenceOptions['sceneLayerMode']>
type LayerRecord = Record<string, unknown>

const EMPTY_LAYERS = {
  canonical: {} as LayerRecord,
  state: {} as LayerRecord,
  look: {} as LayerRecord,
  board: {
    layout: '2x2',
    aspect_ratio: '16:9',
    views: ['master_wide', 'reverse_wide', 'side_wide', 'spatial_verification_wide'],
    people: false,
    text: false,
  } as LayerRecord,
}

function readLayers(asset: AssetSummary) {
  const raw = asset.structuredVariantFields?.semantic_layers
  const semantic = raw && typeof raw === 'object' ? raw as Record<string, unknown> : {}
  return {
    canonical: semantic.canonical && typeof semantic.canonical === 'object' ? { ...(semantic.canonical as LayerRecord) } : { ...EMPTY_LAYERS.canonical },
    state: semantic.state && typeof semantic.state === 'object' ? { ...(semantic.state as LayerRecord) } : { ...EMPTY_LAYERS.state },
    look: semantic.look && typeof semantic.look === 'object' ? { ...(semantic.look as LayerRecord) } : { ...EMPTY_LAYERS.look },
    board: semantic.board_spec && typeof semantic.board_spec === 'object' ? { ...EMPTY_LAYERS.board, ...(semantic.board_spec as LayerRecord) } : { ...EMPTY_LAYERS.board },
  }
}

function fieldValue(layer: LayerRecord, key: string) {
  const value = layer[key]
  if (Array.isArray(value)) return value.join('、')
  if (value && typeof value === 'object') return JSON.stringify(value)
  return String(value ?? '')
}

function fieldEntries(layer: LayerRecord, keys: string[]) {
  return keys.map((key) => ({ key, value: fieldValue(layer, key) }))
}

function setLayerField(layer: LayerRecord, key: string, value: string) {
  const next = { ...layer }
  if (key === 'fixed_assets' || key === 'spatial_relations' || key === 'views') {
    next[key] = value.split(/[、,，\n]/).map((item) => item.trim()).filter(Boolean)
  } else if (key === 'architecture' && value.trim().startsWith('{')) {
    try {
      next[key] = JSON.parse(value)
    } catch {
      next[key] = value
    }
  } else {
    next[key] = value
  }
  return next
}

function layerTitle(mode: SceneLayerMode) {
  if (mode === 'canonical') return '中性空间基准图'
  if (mode === 'state') return '指定状态图'
  if (mode === 'look') return '指定 Look 图'
  return '状态 + Look 合成图'
}

export default function SceneSemanticLayersEditor({
  bookId,
  asset,
  onRefresh,
  onGenerate,
}: {
  bookId: number
  asset: AssetSummary
  onRefresh?: () => void
  onGenerate?: (options?: GenerateReferenceOptions) => void
}) {
  const initial = useMemo(() => readLayers(asset), [asset])
  const [canonical, setCanonical] = useState<LayerRecord>(initial.canonical)
  const [state, setState] = useState<LayerRecord>(initial.state)
  const [look, setLook] = useState<LayerRecord>(initial.look)
  const [board, setBoard] = useState<LayerRecord>(initial.board)
  const [mode, setMode] = useState<SceneLayerMode>('combined')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [migrationPlan, setMigrationPlan] = useState<Array<{ term: string; target_layer: string; reason: string }> | null>(null)
  const [qualityPlan, setQualityPlan] = useState<{ problematic_active_references: Array<{ reference_id: number; issues: string[] }>; replacement_candidates: Array<{ reference_id: number }>; recommendation: string } | null>(null)

  useEffect(() => {
    setCanonical(initial.canonical)
    setState(initial.state)
    setLook(initial.look)
    setBoard(initial.board)
  }, [initial])

  if (asset.category !== 'location' || !asset.assetRecordId) return null

  const update = (setter: (value: LayerRecord) => void, layer: LayerRecord, key: string, value: string) => {
    setter(setLayerField(layer, key, value))
  }

  const save = async () => {
    setSaving(true)
    setMessage('')
    try {
      const response = await fetch(`/api/books/${bookId}/visual-assets/scene/${asset.assetRecordId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ canonicalFacts: canonical, stateVariants: state, lookProfile: look, boardSpec: board }),
      })
      if (!response.ok) throw new Error(`保存场景语义失败：HTTP ${response.status}`)
      setMessage('已保存。下次生成可选择中性空间、指定状态或 Look。')
      onRefresh?.()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '保存场景语义失败')
    } finally {
      setSaving(false)
    }
  }

  const loadMigrationPlan = async () => {
    try {
      const response = await fetch(`/api/books/${bookId}/visual-assets/scene/${asset.assetRecordId}/semantic-migration-plan`)
      if (!response.ok) throw new Error(`读取迁移建议失败：HTTP ${response.status}`)
      const payload = await response.json()
      setMigrationPlan(Array.isArray(payload.suggestions) ? payload.suggestions : [])
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '读取迁移建议失败')
    }
  }

  const loadQualityPlan = async () => {
    try {
      const response = await fetch(`/api/books/${bookId}/visual-assets/scene/${asset.assetRecordId}/reference-quality-plan`)
      if (!response.ok) throw new Error(`读取参考图质量计划失败：HTTP ${response.status}`)
      setQualityPlan(await response.json())
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '读取参考图质量计划失败')
    }
  }

  const renderFields = (title: string, layer: LayerRecord, setter: (value: LayerRecord) => void, keys: string[]) => (
    <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
      <div className="text-xs font-medium text-slate-200">{title}</div>
      <div className="mt-2 space-y-2">
        {fieldEntries(layer, keys).map(({ key, value }) => (
          <label key={key} className="block">
            <span className="text-[11px] text-slate-500">{key}</span>
            <textarea
              value={value}
              onChange={(event) => update(setter, layer, key, event.target.value)}
              rows={key === 'description' || key === 'spatial_relations' ? 2 : 1}
              className="mt-1 w-full resize-y rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-sky-500"
              placeholder="可留空；只填写该层负责的事实"
            />
          </label>
        ))}
      </div>
    </div>
  )

  return (
    <div className="mt-4 rounded-lg border border-sky-500/25 bg-sky-500/5 p-3" data-testid="scene-semantic-layers-editor">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs font-medium text-sky-100">场景四层语义（可编辑）</div>
          <div className="mt-1 text-[11px] leading-5 text-sky-100/70">把空间事实、临时状态、摄影 Look 分开保存，避免雨夜或灯光永久污染场景本体。</div>
        </div>
        <span className="rounded-full border border-sky-500/30 px-2 py-0.5 text-[11px] text-sky-200">四视图 · 16:9</span>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        {renderFields('1. 场景本体（长期不变）', canonical, setCanonical, ['location_type', 'description', 'architecture', 'fixed_assets', 'spatial_relations'])}
        {renderFields('2. 场景状态（本次天气 / 时间 / 使用状态）', state, setState, ['active', 'time', 'weather', 'lighting', 'atmosphere', 'floor'])}
        {renderFields('3. 场景 Look（摄影与调色）', look, setLook, ['style', 'palette', 'contrast', 'lens', 'depth_of_field'])}
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <div className="text-xs font-medium text-slate-200">4. 四视图版式（系统合同）</div>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            <div className="rounded border border-slate-800 px-2 py-1.5 text-xs text-slate-300">布局：2×2</div>
            <div className="rounded border border-slate-800 px-2 py-1.5 text-xs text-slate-300">画幅：16:9</div>
          </div>
          <label className="mt-2 block"><span className="text-[11px] text-slate-500">视图槽位（逗号分隔）</span><textarea value={fieldValue(board, 'views')} onChange={(event) => setBoard(setLayerField(board, 'views', event.target.value))} rows={2} className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-slate-200" /></label>
          <div className="mt-2 text-[11px] leading-5 text-slate-500">默认：主视角全景、反向全景、侧向全景、空间校验全景。材质细节请另建道具资产。</div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select value={mode} onChange={(event) => setMode(event.target.value as SceneLayerMode)} className="rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-slate-200">
          <option value="combined">生成：状态 + Look 合成图</option>
          <option value="canonical">生成：中性空间基准图</option>
          <option value="state">生成：指定状态图</option>
          <option value="look">生成：指定 Look 图</option>
        </select>
        <button type="button" onClick={() => onGenerate?.({ sceneLayerMode: mode })} disabled={!onGenerate} className="rounded border border-sky-500/50 bg-sky-500/10 px-3 py-1.5 text-xs text-sky-100 hover:border-sky-400 disabled:opacity-50">{layerTitle(mode)}</button>
        <button type="button" onClick={() => void save()} disabled={saving} className="rounded border border-emerald-500/50 bg-emerald-500/10 px-3 py-1.5 text-xs text-emerald-100 hover:border-emerald-400 disabled:opacity-50">{saving ? '保存中…' : '保存四层语义'}</button>
        <button type="button" onClick={() => void loadMigrationPlan()} className="rounded border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:border-slate-500">读取旧资产迁移建议</button>
        <button type="button" onClick={() => void loadQualityPlan()} className="rounded border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:border-slate-500">检查参考图质量</button>
        {message ? <span role="status" className="text-[11px] text-slate-300">{message}</span> : null}
      </div>
      {migrationPlan ? <div className="mt-3 rounded border border-slate-800 bg-slate-950/60 p-2 text-[11px] text-slate-300">
        {migrationPlan.length ? <ul className="space-y-1">{migrationPlan.map((item, index) => <li key={`${item.term}-${index}`}>“{item.term}” → {item.target_layer}：{item.reason}</li>)}</ul> : '未发现需要迁移的状态或 Look 词。'}
        <div className="mt-2 text-slate-500">仅供人工审核，不会自动写入。</div>
      </div> : null}
      {qualityPlan ? <div className="mt-3 rounded border border-slate-800 bg-slate-950/60 p-2 text-[11px] text-slate-300">
        {qualityPlan.problematic_active_references.length ? <div>当前主参考图存在 {qualityPlan.problematic_active_references.length} 个待处理项：{qualityPlan.problematic_active_references.map((item) => `#${item.reference_id}（${item.issues.join('、')}）`).join('；')}</div> : '当前没有发现主参考图质量问题。'}
        {qualityPlan.replacement_candidates.length ? <div className="mt-1">可供人工复核的候选图：{qualityPlan.replacement_candidates.map((item) => `#${item.reference_id}`).join('、')}</div> : null}
        <div className="mt-2 text-slate-500">{qualityPlan.recommendation}</div>
      </div> : null}
    </div>
  )
}
