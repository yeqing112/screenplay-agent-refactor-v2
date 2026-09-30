import { useCallback, useEffect, useState } from 'react'
import {
  activateProductionAssetReview,
  bindCurrentProductionAssets,
  decideProductionAssetReview,
  fetchProductionAssetBridgeState,
  ingestProductionAsset,
  type ProductionAssetBridgeRequirement,
  type ProductionAssetBridgeState,
} from '../services/productionAssets'

type AssetReadiness = { current?: boolean; missing?: string[]; stale?: string[]; required_entities?: string[] }

function fallbackRequirements(readiness: AssetReadiness): ProductionAssetBridgeRequirement[] {
  const keys = Array.from(new Set([...(readiness.missing || []), ...(readiness.stale || []), ...(readiness.required_entities || [])]))
  return keys.map((entityKey) => {
    const [assetType, ...rest] = entityKey.split(':')
    return {
      entity_key: entityKey,
      asset_type: assetType as ProductionAssetBridgeRequirement['asset_type'],
      entity_id: rest.join(':'),
      requirement_status: (readiness.stale || []).includes(entityKey) ? 'BINDING_STALE' : 'MISSING',
      current_authority_id: null,
      current_version_id: null,
      current_pointer: null,
      current_media: null,
      active_binding: null,
      binding_current: false,
      latest_version: null,
      pending_review: null,
      pending_review_id: null,
      human_decision: null,
      can_upload: true,
      can_approve: false,
      can_activate: false,
      can_bind: false,
    }
  })
}

function statusCopy(status: ProductionAssetBridgeRequirement['requirement_status']) {
  switch (status) {
    case 'REVIEW_PENDING': return '该版本等待人工审核'
    case 'HUMAN_APPROVED_NOT_ACTIVATED': return '当前版本已批准，等待激活'
    case 'CURRENT_NOT_BOUND': return '当前版本已激活，需要显式绑定到镜头'
    case 'BINDING_STALE': return '当前生产资产已更新，请重新绑定当前版本'
    case 'BOUND_CURRENT': return '当前版本已绑定'
    case 'REJECTED': return '该版本已拒绝，请重新上传'
    case 'REQUEST_CHANGE': return '该版本需要修改后重新上传'
    default: return '缺少当前 Production Asset'
  }
}

export default function ProductionAssetBridgePanel({ bookId, storyboardShotId, readiness, onRefresh }: { bookId: number; storyboardShotId: number; readiness: AssetReadiness; onRefresh?: () => Promise<void> }) {
  const [bridgeState, setBridgeState] = useState<ProductionAssetBridgeState | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const requirements = bridgeState?.requirements || fallbackRequirements(readiness)
  const bridgeUnavailable = Boolean(error && !bridgeState)

  const refreshBridgeState = useCallback(async () => {
    try {
      const next = await fetchProductionAssetBridgeState(bookId, storyboardShotId)
      setBridgeState(next)
      setError('')
      return next
    } catch (reason) {
      setBridgeState(null)
      setError(reason instanceof Error ? reason.message : '生产资产状态读取失败。')
      return null
    }
  }, [bookId, storyboardShotId])

  useEffect(() => {
    setBridgeState(null)
    setError('')
    setMessage('')
    void refreshBridgeState()
  }, [refreshBridgeState])

  const mutateAndRefresh = useCallback(async (action: () => Promise<unknown>, success: string) => {
    setBusy(true); setMessage('正在同步 canonical 资产状态…'); setError('')
    try {
      await action()
      await refreshBridgeState()
      setMessage(success)
      await onRefresh?.()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '生产资产操作失败。')
    } finally { setBusy(false) }
  }, [onRefresh, refreshBridgeState])

  const upload = async (requirement: ProductionAssetBridgeRequirement, file: File) => {
    await mutateAndRefresh(() => ingestProductionAsset(bookId, requirement.asset_type, requirement.entity_id, file), '资产版本已创建，等待人工批准。')
  }

  const approve = async (requirement: ProductionAssetBridgeRequirement) => {
    if (!requirement.pending_review_id) return
    await mutateAndRefresh(async () => {
      await decideProductionAssetReview(bookId, requirement.pending_review_id as string, 'APPROVE')
      await activateProductionAssetReview(bookId, requirement.pending_review_id as string)
    }, '资产已批准并激活，请继续显式绑定到当前镜头。')
  }

  const activate = async (requirement: ProductionAssetBridgeRequirement) => {
    if (!requirement.pending_review_id) return
    await mutateAndRefresh(() => activateProductionAssetReview(bookId, requirement.pending_review_id as string), '资产已激活，请继续显式绑定到当前镜头。')
  }

  const canBind = Boolean(bridgeState?.can_bind)
  const isComplete = Boolean(bridgeState?.binding_current || (readiness.current && !requirements.length))
  if (isComplete) return null

  return <section data-testid="production-asset-bridge" className="border border-[#D8A47C]/40 bg-[#D8A47C]/5 p-4" aria-label="Production Asset Bridge">
    <div className="text-xs uppercase tracking-[0.16em] text-[#D8A47C]">Production Asset Bridge</div>
    <div className="mt-1 text-sm font-medium text-[#EDF1EF]">需要补齐生产资产</div>
    <p className="mt-2 text-xs leading-5 text-[#A9B4B3]">状态来自 backend bridge-state；批准、激活与绑定仍需人工明确点击。</p>
    {error ? <div className="mt-3 border border-[#DF8E8C]/40 bg-[#DF8E8C]/5 p-2 text-[11px] text-[#DF8E8C]" role="alert">{error} 暂停资产操作，重新同步后再试。</div> : null}
    <div className="mt-3 grid gap-2 sm:grid-cols-2">
      {requirements.map((requirement) => <div key={requirement.entity_key} className="border border-[#2A3437] bg-[#141A1D] px-3 py-2 text-xs">
        <div className="flex items-center justify-between gap-2"><span className="font-mono text-[#EDF1EF]">{requirement.entity_key}</span><span className="text-[10px] text-[#DBB36F]">{statusCopy(requirement.requirement_status)}</span></div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {!bridgeUnavailable && bridgeState && requirement.can_upload ? <label className="cursor-pointer border border-[#8BC9D9]/40 px-2 py-1 text-[#8BC9D9]">上传<input type="file" accept="image/*,video/*" className="sr-only" disabled={busy} onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(requirement, file) }} /></label> : null}
          {!bridgeUnavailable && bridgeState && requirement.can_approve ? <button type="button" disabled={busy} onClick={() => void approve(requirement)} className="border border-[#9FCBAB]/40 px-2 py-1 text-[#9FCBAB] disabled:opacity-50">批准并激活</button> : null}
          {!bridgeUnavailable && bridgeState && requirement.can_activate ? <button type="button" disabled={busy} onClick={() => void activate(requirement)} className="border border-[#9FCBAB]/40 px-2 py-1 text-[#9FCBAB] disabled:opacity-50">激活 Pointer</button> : null}
        </div>
      </div>)}
    </div>
    {message ? <div className="mt-3 text-[11px] text-[#DBB36F]" role="status">{message}</div> : null}
    {!bridgeUnavailable && canBind ? <button type="button" disabled={busy} onClick={() => void mutateAndRefresh(() => bindCurrentProductionAssets(bookId, storyboardShotId), '资产已显式绑定，正在刷新 V2 readiness。')} className="mt-3 border border-[#9FCBAB]/50 px-3 py-2 text-xs text-[#9FCBAB] disabled:opacity-50">{requirements.some((item) => item.requirement_status === 'BINDING_STALE') ? '重新绑定当前版本' : '显式绑定到当前镜头'}</button> : null}
    <div className="mt-3 text-[10px] text-[#728082]">Shot #{storyboardShotId} · 只有 GET production-workspace-v2 的 asset_readiness.current=true 才表示镜头 ready。</div>
  </section>
}
