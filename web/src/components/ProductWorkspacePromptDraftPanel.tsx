import { useEffect, useState } from 'react'

type Candidate = {
  prompt_static?: string; prompt_motion?: string; negative_prompt?: string
  used_assets?: Array<{ asset_name?: string }>
  warnings?: string[]
  diagnostics?: { status?: string; warnings?: string[]; blocking_issues?: string[]; checks?: Array<{ passed?: boolean; message?: string }> }
  baseline?: { version?: number; prompt_static?: string; prompt_motion?: string; negative_prompt?: string }
}
type LlmRequestAudit = {
  attempt_count?: number
  vendor_models?: string[]
  vendor_hosts?: string[]
  has_repair_request?: boolean
  last_http_status?: number
  last_parse_ok?: boolean
  last_response_sha256?: string
}
type Packet = {
  id: number
  packet_fingerprint: string
  proposal: { candidate?: Candidate }
  model_info?: {
    llm_generated?: boolean
    invalidated?: boolean
    invalidation_reason?: string
    continuity_revision?: boolean
    source_agent_audit_id?: number | null
    llm_request_audit?: LlmRequestAudit
  }
}
export function ProductWorkspacePromptDraftPanel({ bookId, episode, shotId, onRefresh }: { bookId: number; episode: number; shotId: string | number; onRefresh?: () => void }) {
  const [packet, setPacket] = useState<Packet | null>(null); const [draft, setDraft] = useState<Record<string, string>>({}); const [message, setMessage] = useState(''); const [busy, setBusy] = useState(false)
  const run = async (url: string, init?: RequestInit) => { const r = await fetch(url, init); const p = await r.json(); if (!r.ok) throw new Error(p.detail || `HTTP ${r.status}`); return p }
  const hasCompleteCandidate = (candidate: Record<string, unknown> | undefined) => Boolean(candidate && ['prompt_static', 'prompt_motion', 'negative_prompt'].every((key) => typeof candidate[key] === 'string' && candidate[key].trim()))
  const recheckDiagnostics = async (nextPacket: Packet) => {
    if (!nextPacket.model_info?.llm_generated) return
    try {
      const result = await run(`/api/books/${bookId}/storyboard/${episode}/${shotId}/prompt-drafts/${nextPacket.id}/diagnostics`)
      if (!result.diagnostics) return
      setPacket((current) => current && current.id === nextPacket.id ? {
        ...current,
        proposal: {
          ...current.proposal,
          candidate: { ...current.proposal?.candidate, diagnostics: result.diagnostics },
        },
      } : current)
    } catch {
      // A stale packet is surfaced when the reviewer acts; loading the panel
      // should remain usable even if a background read-only check fails.
    }
  }
  useEffect(() => {
    let cancelled = false
    setPacket(null); setDraft({}); setMessage('')
    void run(`/api/books/${bookId}/decision-packets?domain=prompt`).then((result) => {
      if (cancelled) return
      const existing = Array.isArray(result.items) ? result.items.find((item: Packet & { scope?: { episode?: number; shot_id?: string | number } }) => (
        Number(item.scope?.episode) === Number(episode) && String(item.scope?.shot_id) === String(shotId)
      )) : null
      if (!existing) return
      const candidate = existing.proposal?.candidate
      setPacket(existing)
      setDraft(existing.model_info?.llm_generated && hasCompleteCandidate(candidate) ? candidate : {})
      if (existing.model_info?.llm_generated) setMessage('已载入此前生成的候选提示词；请复核、编辑后再确认创建版本。')
      else if (existing.model_info?.invalidated) setMessage('候选草案已因绑定资产的权威事实变更而失效。请重新生成证据包，并在确认后调用 LLM 生成新草案。')
      void recheckDiagnostics(existing)
    }).catch(() => undefined)
    return () => { cancelled = true }
  }, [bookId, episode, shotId])
  const evidence = async () => { setBusy(true); try { const p = await run(`/api/books/${bookId}/storyboard/${episode}/${shotId}/prompt-drafts`, { method: 'POST' }); const candidate = p.packet?.proposal?.candidate; setPacket(p.packet); setDraft(p.packet?.model_info?.llm_generated && hasCompleteCandidate(candidate) ? candidate : {}); setMessage(p.packet?.model_info?.llm_generated ? '已恢复此前生成的候选提示词；请复核、编辑后再确认创建版本。' : '提示词证据包已生成；尚未调用 LLM。'); if (p.packet) void recheckDiagnostics(p.packet) } catch (e) { setMessage(e instanceof Error ? e.message : '失败') } finally { setBusy(false) } }
  const llm = async () => { if (!packet || !window.confirm('确认调用 LLM 生成候选提示词？这可能产生费用，且不会自动创建版本或触发生成。')) return; setBusy(true); try { const p = await run(`/api/books/${bookId}/storyboard/${episode}/${shotId}/prompt-drafts/${packet.id}/llm`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ packetFingerprint: packet.packet_fingerprint, confirmed: true, allowExternalCall: true }) }); setPacket(p.packet); setDraft(p.packet.proposal?.candidate || {}); setMessage('候选提示词已生成，请编辑并确认创建版本。') } catch (e) { setMessage(e instanceof Error ? e.message : '失败') } finally { setBusy(false) } }
  const confirm = async () => { if (!packet || !window.confirm('确认创建新的 Prompt Version？这不会触发生图或视频生成。')) return; setBusy(true); try { const p = await run(`/api/books/${bookId}/storyboard/${episode}/${shotId}/prompt-drafts/${packet.id}/confirm`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ packetFingerprint: packet.packet_fingerprint, action: 'confirmed', confirmed: true, allowWrite: true, reviewedCandidate: draft }) }); setMessage(`已创建 Prompt Version v${p.prompt_version}。`); onRefresh?.() } catch (e) { setMessage(e instanceof Error ? e.message : '失败') } finally { setBusy(false) } }
  const canConfirm = hasCompleteCandidate(draft); const candidate = packet?.proposal?.candidate; const diagnostics = candidate?.diagnostics; const failedChecks = diagnostics?.checks?.filter((item) => item.passed === false) || []; const changedFields = candidate?.baseline ? [['静态', 'prompt_static'], ['运动', 'prompt_motion'], ['负向', 'negative_prompt']].filter(([, key]) => candidate[String(key) as keyof Candidate] !== candidate.baseline?.[`${String(key).replace('prompt_', 'prompt_')}` as keyof Candidate['baseline']]) : []
  const requestAudit = packet?.model_info?.llm_request_audit
  const requestAuditText = requestAudit ? [
    requestAudit.vendor_models?.length ? `模型：${requestAudit.vendor_models.join('、')}` : '',
    requestAudit.vendor_hosts?.length ? `服务：${requestAudit.vendor_hosts.join('、')}` : '',
    requestAudit.last_http_status ? `请求状态：${requestAudit.last_http_status}` : '',
    requestAudit.last_parse_ok ? '返回已解析' : '返回待复核',
    packet?.model_info?.continuity_revision ? `连续性修订（Agent 审计 #${packet.model_info.source_agent_audit_id ?? '—'}）` : '',
  ].filter(Boolean).join('；') : ''
  return <details className="mt-4 rounded-xl border border-slate-800 bg-slate-950/40 p-3"><summary className="cursor-pointer text-xs font-medium text-slate-300">受控 Prompt Compiler 草案</summary><div className="mt-3 flex gap-2"><button type="button" onClick={() => void evidence()} disabled={busy} className="rounded border border-sky-400/35 px-3 py-1.5 text-[11px] text-sky-100">生成证据包</button>{packet && !packet.model_info?.llm_generated ? <button type="button" onClick={() => void llm()} disabled={busy} className="rounded border border-violet-400/35 px-3 py-1.5 text-[11px] text-violet-100">确认调用 LLM</button> : null}</div>{message ? <div role="status" aria-live="polite" className="mt-2 text-[11px] text-slate-400">{message}</div> : null}{packet?.model_info?.llm_generated ? <div className="mt-3 space-y-2">{requestAuditText ? <div className="rounded border border-cyan-400/20 bg-cyan-950/20 p-2 text-[11px] text-cyan-100">调用审计：{requestAuditText}{requestAudit?.has_repair_request ? '；已附带修订证据。' : ''}</div> : null}{diagnostics ? <div className="rounded border border-slate-700 bg-slate-900/50 p-2 text-[11px] text-slate-300">生产诊断：{diagnostics.status === 'pass' ? '通过' : diagnostics.status === 'blocked' ? '阻塞' : '需复核'}；关联资产：{candidate?.used_assets?.map((item) => item.asset_name).filter(Boolean).join('、') || '未返回'}。{candidate?.baseline ? `相对 v${candidate.baseline.version ?? '当前'}：${changedFields.length ? changedFields.map(([label]) => label).join('、') + '提示词已变化' : '提示词无变化'}。` : ''}{[...(diagnostics.blocking_issues || []), ...(diagnostics.warnings || []), ...failedChecks.map((item) => item.message || '')].filter(Boolean).slice(0, 4).map((item) => <div key={item} className="mt-1 text-amber-200">• {item}</div>)}</div> : null}{[['prompt_static','静态提示词'],['prompt_motion','运动提示词'],['negative_prompt','负向提示词']].map(([key,label]) => <label key={key} className="block text-[11px] text-slate-400">{label}<textarea value={draft[key] || ''} onChange={(e) => setDraft((v) => ({ ...v, [key]: e.target.value }))} className="mt-1 min-h-20 w-full rounded border border-slate-700 bg-slate-950 p-2 text-xs text-slate-200" /></label>)}{!canConfirm ? <div className="text-[11px] text-amber-200">候选内容不完整，不能创建新版本。</div> : null}<button type="button" onClick={() => void confirm()} disabled={busy || !canConfirm} className="rounded border border-emerald-400/40 px-3 py-1.5 text-[11px] text-emerald-100 disabled:cursor-not-allowed disabled:opacity-50">确认创建新版本</button></div> : null}</details>
}
