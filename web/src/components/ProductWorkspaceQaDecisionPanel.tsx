import { useEffect, useState } from 'react'

type Packet = { id: number; packet_fingerprint: string; unknowns: string[]; conflicts: string[]; proposal: { decision?: string; confidence?: number; proposals?: Array<{ operation?: string; summary?: string; proposed_content?: string }> }; model_info?: { llm_generated?: boolean } }

export function ProductWorkspaceQaDecisionPanel({ bookId, issueKey, onUseProposal }: { bookId: number; issueKey: string; onUseProposal?: (content: string) => void }) {
  const [packet, setPacket] = useState<Packet | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState('')
  useEffect(() => { setPacket(null); setMessage(''); setPreview('') }, [bookId, issueKey])
  const request = async (url: string, options?: RequestInit) => {
    const response = await fetch(url, options); const payload = await response.json()
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`)
    return payload
  }
  const createPacket = async () => {
    setBusy(true); setMessage(''); setPreview('')
    try { const p = await request(`/api/books/${bookId}/qa/issues/${encodeURIComponent(issueKey)}/decision-packet/draft`, { method: 'POST' }); setPacket(p.packet); setMessage(p.deduplicated ? '已载入当前证据包。' : '剧本 QA 证据包已生成；尚未调用 LLM。') }
    catch (e) { setMessage(e instanceof Error ? e.message : '生成证据包失败') } finally { setBusy(false) }
  }
  const previewPrompt = async () => {
    if (!packet) return; setBusy(true); setMessage('')
    try { const p = await request(`/api/books/${bookId}/decision-packets/${packet.id}/llm-draft-preview?packetFingerprint=${encodeURIComponent(packet.packet_fingerprint)}`); setPreview(String(p.prompt || '')) }
    catch (e) { setMessage(e instanceof Error ? e.message : '读取预览失败') } finally { setBusy(false) }
  }
  const callLlm = async () => {
    if (!packet || !window.confirm('确认调用当前默认 LLM 生成剧本 QA 修复草案？这可能产生模型费用；结果只保存为草案，不会写入剧本或启动复检。')) return
    setBusy(true); setMessage('')
    try { const p = await request(`/api/books/${bookId}/decision-packets/${packet.id}/llm-draft`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ packetFingerprint: packet.packet_fingerprint, confirmed: true, allowExternalCall: true }) }); setPacket(p.packet); setMessage(p.deduplicated ? '已有草案，未重复调用。' : 'LLM 草案已生成，需人工审核后再转为修复操作。') }
    catch (e) { setMessage(e instanceof Error ? e.message : '调用 LLM 失败') } finally { setBusy(false) }
  }
  const blockers = [...(packet?.unknowns || []), ...(packet?.conflicts || [])]
  return <details className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
    <summary className="cursor-pointer list-none text-sm font-medium text-slate-200">受控 LLM 修复草案 <span className="ml-1 text-xs font-normal text-slate-500">（基于当前剧本与 QA 证据）</span></summary>
    <div className="mt-3 flex flex-wrap gap-2"><button type="button" onClick={() => void createPacket()} disabled={busy} className="rounded-lg border border-sky-400/35 bg-sky-400/10 px-3 py-1.5 text-xs text-sky-100 disabled:opacity-50">生成证据包</button>{packet ? <button type="button" onClick={() => void previewPrompt()} disabled={busy} className="rounded-lg border border-slate-600 px-3 py-1.5 text-xs text-slate-200 disabled:opacity-50">预览 LLM 提示词</button> : null}{packet && !packet.model_info?.llm_generated ? <button type="button" onClick={() => void callLlm()} disabled={busy} className="rounded-lg border border-violet-400/35 bg-violet-400/10 px-3 py-1.5 text-xs text-violet-100 disabled:opacity-50">确认调用 LLM</button> : null}</div>
    {message ? <div role="status" aria-live="polite" className="mt-2 text-xs text-slate-400">{message}</div> : null}
    {packet ? <div className="mt-3 space-y-2 text-xs text-slate-400">{blockers.length ? <div className="rounded-lg border border-amber-400/25 bg-amber-400/5 p-2 text-amber-100">信息缺口 / 冲突：{blockers.join('、')}</div> : null}<div>当前决断：<span className="text-slate-200">{packet.proposal?.decision || '待分析'}</span>{typeof packet.proposal?.confidence === 'number' ? ` · 置信度 ${Math.round(packet.proposal.confidence * 100)}%` : ''}</div>{(packet.proposal?.proposals || []).map((item, index) => <div key={`${item.operation}-${index}`} className="rounded-lg border border-slate-800 px-2 py-1.5"><span className="text-slate-300">{item.operation}</span>{item.summary ? `：${item.summary}` : ''}{item.proposed_content && onUseProposal ? <button type="button" onClick={() => onUseProposal(item.proposed_content || '')} className="ml-2 rounded border border-emerald-400/35 px-2 py-0.5 text-[11px] text-emerald-200 hover:bg-emerald-400/10">带入人工编辑器</button> : null}</div>)}</div> : null}
    {preview ? <details className="mt-3 rounded-lg border border-slate-800 p-2"><summary className="cursor-pointer text-xs text-slate-400">查看 LLM 提示词全文</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-[10px] leading-5 text-slate-500">{preview}</pre></details> : null}
  </details>
}
