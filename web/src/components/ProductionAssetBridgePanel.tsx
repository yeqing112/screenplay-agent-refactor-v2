import { useState } from 'react'
import { activateProductionAssetReview, bindProductionAssets, decideProductionAssetReview, ingestProductionAsset } from '../services/productionAssets'

type AssetReadiness = { current?: boolean; missing?: string[]; stale?: string[]; required_entities?: string[] }

export default function ProductionAssetBridgePanel({ bookId, storyboardShotId, readiness, onRefresh }: { bookId: number; storyboardShotId: number; readiness: AssetReadiness; onRefresh?: () => Promise<void> }) {
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [pendingReviews, setPendingReviews] = useState<Record<string, string>>({})
  const [versions, setVersions] = useState<Record<string, { authority_id: string; version_id: string }>>({})
  const required = Array.from(new Set([...(readiness.missing || []), ...(readiness.stale || []), ...(readiness.required_entities || [])]))
  if (readiness.current && !required.length) return null

  const upload = async (entity: string, file: File) => {
    const [rawType, ...rest] = entity.split(':')
    const assetType = rawType.toUpperCase()
    const entityId = rest.join(':')
    if (!entityId || !['CHARACTER', 'SCENE', 'PROP'].includes(assetType)) return
    setBusy(true); setMessage('正在写入 canonical 资产版本…')
    try {
      const payload = await ingestProductionAsset(bookId, assetType, entityId, file)
      const reviewId = String(payload?.review?.review_id || '')
      if (reviewId) setPendingReviews((current) => ({ ...current, [entity]: reviewId }))
      setMessage('资产版本已创建，等待人工批准。')
      await onRefresh?.()
    } catch (error) { setMessage(error instanceof Error ? error.message : '资产上传失败。') }
    finally { setBusy(false) }
  }

  const approve = async (entity: string) => {
    const reviewId = pendingReviews[entity]
    if (!reviewId) return
    setBusy(true); setMessage('正在记录人工批准并激活 Pointer…')
    try { await decideProductionAssetReview(bookId, reviewId, 'APPROVE'); const activated = await activateProductionAssetReview(bookId, reviewId); const switched = activated?.switch || {}; setVersions((current) => ({ ...current, [entity]: { authority_id: String(switched.authority_id || ''), version_id: String(switched.version_id || '') } })); setPendingReviews((current) => { const next = { ...current }; delete next[entity]; return next }); setMessage('资产已激活，请继续显式绑定到当前镜头。'); await onRefresh?.() }
    catch (error) { setMessage(error instanceof Error ? error.message : '资产审核失败。') }
    finally { setBusy(false) }
  }

  const canBind = required.length > 0 && required.every((entity) => versions[entity]?.authority_id && versions[entity]?.version_id)

  return <section data-testid="production-asset-bridge" className="border border-[#D8A47C]/40 bg-[#D8A47C]/5 p-4" aria-label="Production Asset Bridge">
    <div className="text-xs uppercase tracking-[0.16em] text-[#D8A47C]">Production Asset Bridge</div>
    <div className="mt-1 text-sm font-medium text-[#EDF1EF]">需要补齐生产资产</div>
    <p className="mt-2 text-xs leading-5 text-[#A9B4B3]">资产必须经过 canonical 版本、人工批准和显式绑定；Legacy 采纳记录不会直接满足生产门槛。</p>
    <div className="mt-3 grid gap-2 sm:grid-cols-2">
      {required.map((entity) => <div key={entity} className="flex items-center justify-between gap-2 border border-[#2A3437] bg-[#141A1D] px-3 py-2 text-xs"><span className="font-mono text-[#EDF1EF]">{entity}</span><div className="flex items-center gap-2"><label className="cursor-pointer border border-[#8BC9D9]/40 px-2 py-1 text-[#8BC9D9]">上传<input type="file" accept="image/*,video/*" className="sr-only" disabled={busy} onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(entity, file) }} /></label>{pendingReviews[entity] ? <button type="button" disabled={busy} onClick={() => void approve(entity)} className="border border-[#9FCBAB]/40 px-2 py-1 text-[#9FCBAB] disabled:opacity-50">批准并激活</button> : null}</div></div>)}
    </div>
    {message ? <div className="mt-3 text-[11px] text-[#DBB36F]" role="status">{message}</div> : null}
    {canBind ? <button type="button" disabled={busy} onClick={async () => { setBusy(true); try { await bindProductionAssets(bookId, storyboardShotId, versions); setMessage('资产已显式绑定，正在刷新 V2 readiness。'); await onRefresh?.() } catch (error) { setMessage(error instanceof Error ? error.message : '资产绑定失败。') } finally { setBusy(false) } }} className="mt-3 border border-[#9FCBAB]/50 px-3 py-2 text-xs text-[#9FCBAB] disabled:opacity-50">显式绑定到当前镜头</button> : null}
    <div className="mt-3 text-[10px] text-[#728082]">Shot #{storyboardShotId} · 当前绑定完成后 V2 才会显示 asset_readiness.current=true。</div>
  </section>
}
