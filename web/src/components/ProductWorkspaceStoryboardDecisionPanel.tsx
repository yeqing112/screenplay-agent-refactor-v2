import { useEffect, useState } from 'react'

type Packet = {
  id: number
  packet_fingerprint: string
  unknowns: string[]
  conflicts: string[]
  proposal: {
    decision?: string
    confidence?: number
    proposals?: Array<{ operation?: string; summary?: string }>
  }
  model_info?: { llm_generated?: boolean }
}

export function ProductWorkspaceStoryboardDecisionPanel({ bookId, episode, shotId }: {
  bookId: number
  episode: number
  shotId: string | number
}) {
  const [packet, setPacket] = useState<Packet | null>(null)
  const [state, setState] = useState<'idle' | 'loading' | 'calling' | 'error'>('idle')
  const [message, setMessage] = useState('')
  const [preview, setPreview] = useState('')

  useEffect(() => {
    setPacket(null); setState('idle'); setMessage(''); setPreview('')
  }, [bookId, episode, shotId])

  const createPacket = async () => {
    setState('loading'); setMessage(''); setPreview('')
    try {
      const response = await fetch(`/api/books/${bookId}/storyboard/${episode}/${shotId}/decision-packet/draft`, { method: 'POST' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`)
      setPacket(payload.packet as Packet)
      setMessage(payload.deduplicated ? '已载入当前证据包。' : '证据包已生成；尚未调用 LLM。')
      setState('idle')
    } catch (error) { setState('error'); setMessage(error instanceof Error ? error.message : '生成证据包失败') }
  }
  const previewPrompt = async () => {
    if (!packet) return
    setState('loading'); setMessage('')
    try {
      const response = await fetch(`/api/books/${bookId}/decision-packets/${packet.id}/llm-draft-preview?packetFingerprint=${encodeURIComponent(packet.packet_fingerprint)}`)
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`)
      setPreview(String(payload.prompt || ''))
      setState('idle')
    } catch (error) { setState('error'); setMessage(error instanceof Error ? error.message : '读取预览失败') }
  }
  const callLlm = async () => {
    if (!packet || !window.confirm('确认调用当前默认 LLM 生成决断草案？这可能产生模型费用；结果只保存为可审核草案，不会修改镜头或触发生成。')) return
    setState('calling'); setMessage('')
    try {
      const response = await fetch(`/api/books/${bookId}/decision-packets/${packet.id}/llm-draft`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ packetFingerprint: packet.packet_fingerprint, confirmed: true, allowExternalCall: true }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`)
      setPacket(payload.packet as Packet); setState('idle')
      setMessage(payload.deduplicated ? '该证据包已有 LLM 草案，未重复调用。' : 'LLM 草案已生成，等待人工审核。')
    } catch (error) { setState('error'); setMessage(error instanceof Error ? error.message : '调用 LLM 失败') }
  }

  const blockers = [...(packet?.unknowns || []), ...(packet?.conflicts || [])]
  return <details className="mt-4 rounded-xl border border-slate-800 bg-slate-950/40 p-3">
    <summary className="cursor-pointer list-none text-xs font-medium text-slate-300">受控 LLM 决断草案 <span className="ml-1 text-slate-500">（证据优先，默认不调用模型）</span></summary>
    <div className="mt-3 flex flex-wrap gap-2">
      <button type="button" onClick={() => void createPacket()} disabled={state === 'loading' || state === 'calling'} className="rounded-lg border border-sky-400/35 bg-sky-400/10 px-3 py-1.5 text-[11px] font-medium text-sky-100 disabled:opacity-50">生成证据包</button>
      {packet ? <button type="button" onClick={() => void previewPrompt()} disabled={state === 'loading' || state === 'calling'} className="rounded-lg border border-slate-600 px-3 py-1.5 text-[11px] text-slate-200 disabled:opacity-50">预览 LLM 提示词</button> : null}
      {packet && !packet.model_info?.llm_generated ? <button type="button" onClick={() => void callLlm()} disabled={state === 'loading' || state === 'calling'} className="rounded-lg border border-violet-400/35 bg-violet-400/10 px-3 py-1.5 text-[11px] font-medium text-violet-100 disabled:opacity-50">{state === 'calling' ? '正在生成草案…' : '确认调用 LLM'}</button> : null}
    </div>
    {message ? <div role="status" aria-live="polite" className={`mt-2 text-[11px] ${state === 'error' ? 'text-rose-300' : 'text-slate-400'}`}>{message}</div> : null}
    {packet ? <div className="mt-3 space-y-2 text-[11px] text-slate-400">
      {blockers.length > 0 ? <div className="rounded-lg border border-amber-400/25 bg-amber-400/5 p-2 text-amber-100">信息缺口 / 冲突：{blockers.join('、')}</div> : null}
      <div>当前决断：<span className="text-slate-200">{packet.proposal?.decision || '待分析'}</span>{typeof packet.proposal?.confidence === 'number' ? ` · 置信度 ${Math.round(packet.proposal.confidence * 100)}%` : ''}</div>
      {(packet.proposal?.proposals || []).map((item, index) => <div key={`${item.operation}-${index}`} className="rounded-lg border border-slate-800 px-2 py-1.5"><span className="text-slate-300">{item.operation}</span>{item.summary ? `：${item.summary}` : ''}</div>)}
    </div> : null}
    {preview ? <details className="mt-3 rounded-lg border border-slate-800 p-2"><summary className="cursor-pointer text-[11px] text-slate-400">查看 LLM 提示词全文</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-[10px] leading-5 text-slate-500">{preview}</pre></details> : null}
  </details>
}
