import { useEffect, useState } from 'react'

type Treatment = {
  scene_name: string
  dramatic_objective: string
  audience_question: string
  visual_strategy: string
  performance_direction?: string
  sound_strategy?: string
  beat_map?: Array<Record<string, unknown>>
  character_intents?: Record<string, Record<string, unknown>>
  [key: string]: unknown
}

type Preview = {
  packet_fingerprint: string
  treatment: Treatment
  evidence: { scene_name?: string; evidence_fingerprint?: string }
}

type Props = { bookId: number; episode: number | null }
type HistoryItem = { packet_id?: number; packet_fingerprint?: string; scene_name?: string; status?: string; candidate?: Treatment; model_info?: Record<string, unknown>; created_at?: string | null; confirmed_at?: string | null }

export default function ProductWorkspaceDirectorTreatmentPanel({ bookId, episode }: Props) {
  const [preview, setPreview] = useState<Preview | null>(null)
  const [candidate, setCandidate] = useState<Treatment | null>(null)
  const [packetId, setPacketId] = useState<number | null>(null)
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [historyOpen, setHistoryOpen] = useState(false)
  const [state, setState] = useState<'idle' | 'loading' | 'ready' | 'calling' | 'review' | 'saving' | 'approved' | 'error'>('idle')
  const [message, setMessage] = useState('')

  useEffect(() => {
    setPreview(null)
    setCandidate(null)
    setPacketId(null)
    setHistory([])
    setHistoryOpen(false)
    setState('idle')
    setMessage('')
  }, [bookId, episode])

  if (!episode) return null

  const loadPreview = async () => {
    setState('loading')
    setMessage('正在读取本集导演方案证据...')
    try {
      const response = await fetch(`/api/books/${bookId}/episodes/${episode}/director-treatment/preview`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const payload = await response.json() as Preview
      setPreview(payload)
      setCandidate(payload.treatment)
      // Recover an already-generated candidate for the same frozen evidence
      // packet so reopening the workspace never looks like the LLM result was
      // lost or requires a second paid call.
      try {
        const historyResponse = await fetch(`/api/books/${bookId}/episodes/${episode}/director-treatment/candidates`, { cache: 'no-store' })
        const historyPayload = historyResponse.ok ? await historyResponse.json() as { items?: HistoryItem[] } : { items: [] }
        const existing = (historyPayload.items || []).find((item) => item.packet_fingerprint === payload.packet_fingerprint && item.model_info?.llm_generated === true)
        if (existing?.candidate && existing.packet_id) {
          setCandidate(existing.candidate)
          setPacketId(existing.packet_id)
          setState('review')
          setMessage('已恢复同一证据包的候选草案；未重复调用模型，请审核后确认写入。')
          return
        }
      } catch {
        // Preview remains useful even if history recovery is unavailable.
      }
      setState('ready')
      setMessage('已生成只读方案；尚未调用模型，也未写入生产数据。')
    } catch (error) {
      setState('error')
      setMessage(error instanceof Error ? error.message : '读取导演方案失败')
    }
  }

  const callLlm = async () => {
    if (!preview || !window.confirm('确认调用当前配置的真实 LLM 生成候选方案？这一步只保存可审核草案，不会修改剧本或镜头。')) return
    setState('calling')
    setMessage('正在调用 LLM；完成后仍需人工审核。')
    try {
      const response = await fetch(`/api/books/${bookId}/episodes/${episode}/director-treatment/llm-draft`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ packetFingerprint: preview.packet_fingerprint, confirmed: true, allowExternalCall: true }),
      })
      const payload = await response.json() as { packet_id?: number; candidate?: Treatment; deduplicated?: boolean; detail?: string }
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`)
      setCandidate(payload.candidate || null)
      setPacketId(payload.packet_id || null)
      setState('review')
      setMessage(payload.deduplicated ? '已有相同证据的候选草案，未重复计费。' : '候选草案已生成，请审核或编辑后再确认写入。')
    } catch (error) {
      setState('error')
      setMessage(error instanceof Error ? error.message : '生成候选方案失败')
    }
  }

  const confirmCandidate = async () => {
    if (!preview || !candidate || !window.confirm('确认写入导演方案正式版本？系统会创建新修订并保留旧版本回滚锚点。')) return
    setState('saving')
    setMessage('正在复验证据并写入版本...')
    try {
      const response = await fetch(`/api/books/${bookId}/episodes/${episode}/director-treatment/confirm`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ packetId, packetFingerprint: preview.packet_fingerprint, confirmed: true, candidate }),
      })
      const payload = await response.json() as { treatment?: Treatment; detail?: string }
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`)
      setCandidate(payload.treatment || candidate)
      setState('approved')
      setMessage('导演方案已写入正式版本；下一步才能进入场景调度。')
    } catch (error) {
      setState('error')
      setMessage(error instanceof Error ? error.message : '确认写入失败')
    }
  }

  const loadHistory = async () => {
    try {
      const response = await fetch(`/api/books/${bookId}/episodes/${episode}/director-treatment/candidates`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const payload = await response.json() as { items?: HistoryItem[] }
      setHistory(payload.items || [])
      setHistoryOpen(true)
    } catch (error) {
      setState('error')
      setMessage(error instanceof Error ? error.message : '读取导演方案历史失败')
    }
  }

  const update = (field: keyof Treatment, value: string) => setCandidate((current) => current ? { ...current, [field]: value } : current)

  return (
    <section className="mb-6 rounded-xl border border-violet-500/30 bg-violet-500/5 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-base font-semibold text-white">导演方案（第 {episode} 集）</div>
          <p className="mt-1 text-sm text-slate-400">先看证据，再让 AI 提建议；只有你确认后才会形成正式版本。</p>
        </div>
        <span className="rounded-full border border-violet-400/30 px-2 py-1 text-xs text-violet-200">
          {state === 'approved' ? '已生效' : state === 'review' ? '待你审核' : state === 'calling' ? 'AI 处理中' : '未生成'}
        </span>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" onClick={loadPreview} disabled={state === 'loading' || state === 'calling' || state === 'saving'} className="rounded-lg border border-slate-600 px-3 py-2 text-sm text-slate-200 hover:border-slate-400 disabled:opacity-50">查看导演方案</button>
        <button type="button" onClick={callLlm} disabled={!preview || state === 'calling' || state === 'saving' || state === 'approved'} className="rounded-lg bg-violet-600 px-3 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-50">让 AI 优化方案</button>
        <button type="button" onClick={confirmCandidate} disabled={!preview || !packetId || !candidate || state === 'saving' || state === 'approved' || state !== 'review'} className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50">确认写入正式版本</button>
        <button type="button" onClick={loadHistory} className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:border-slate-500">查看历史修订</button>
      </div>
      {candidate ? (
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {([['dramatic_objective', '本场目标'], ['audience_question', '观众问题'], ['visual_strategy', '视觉策略']] as const).map(([field, label]) => (
            <label key={field} className="text-xs text-slate-400">
              {label}
              <textarea value={String(candidate[field] || '')} onChange={(event) => update(field, event.target.value)} rows={3} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950/80 p-2 text-sm text-slate-200 outline-none focus:border-violet-400" />
            </label>
          ))}
        </div>
      ) : null}
      {message ? <div className="mt-3 text-xs text-slate-400">{message}</div> : null}
      {preview ? <div className="mt-2 text-[11px] text-slate-500">场景：{preview.evidence.scene_name || preview.treatment.scene_name} · 证据指纹：{preview.evidence.evidence_fingerprint || preview.packet_fingerprint}</div> : null}
      {historyOpen ? (
        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
          <div className="text-xs font-medium text-slate-300">候选与修订历史</div>
          {history.length === 0 ? <div className="mt-2 text-xs text-slate-500">暂无历史记录。</div> : (
            <div className="mt-2 space-y-2">
              {history.map((item) => (
                <div key={item.packet_id} className="flex items-center justify-between gap-3 rounded border border-slate-800 px-3 py-2 text-xs">
                  <span className="text-slate-300">{item.scene_name || '未命名场景'} · 草案 #{item.packet_id}</span>
                  <span className={item.status === 'confirmed' ? 'text-emerald-300' : item.status === 'superseded' ? 'text-slate-500' : 'text-amber-300'}>{item.status === 'confirmed' ? '已确认' : item.status === 'superseded' ? '已过期' : '待审核'}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}
    </section>
  )
}
