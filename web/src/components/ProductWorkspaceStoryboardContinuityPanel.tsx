import { useEffect, useMemo, useState } from 'react'

type Contract = { continuity_level?: string; status?: string; source_shot_id?: number; target_shot_id?: number; entry_state?: string; exit_state?: string; inherit_rules?: Record<string, string>; allowed_changes?: string[]; forbidden_changes?: string[]; required_transition_frame?: string }
type ContractResponse = { not_applicable?: boolean; contract?: Contract | null; draft?: Contract | null }
type Frame = { id: number; status: string; evidence_status?: 'current' | 'stale'; public_url?: string; frame_kind?: string }
type Review = { id: number; status: string; evidence_status?: 'current' | 'stale'; review_result?: string; drift_categories?: string[]; target_first_frame_url?: string }
type Retry = { id: number; attempt_number: number; status: string; retry_task_id?: string }
type Operations = { frames: Frame[]; reviews: Review[]; retry_attempts?: Retry[]; readiness?: { status?: string; label?: string; frame_status?: string; review_status?: string }; source?: { ready_for_handoff: boolean }; target?: { has_adopted_video: boolean; video_id?: string } }

const humanLevel = (level?: string) => level === 'strict' ? '画面必须紧接上一镜' : level === 'soft' ? '尽量保持人物与场景一致' : level === 'narrative' ? '只保持剧情承接' : '可独立生成'
const technicalLevel = (level?: string) => level === 'strict' ? '强连续' : level === 'soft' ? '弱连续' : level === 'narrative' ? '叙事连续' : '独立镜头'

export function ProductWorkspaceStoryboardContinuityPanel({ bookId, episode, shotId }: { bookId: number; episode: number; shotId: string | number }) {
  const [data, setData] = useState<ContractResponse | null>(null)
  const [state, setState] = useState<'loading' | 'loaded' | 'first-shot' | 'error'>('loading')
  const [operations, setOperations] = useState<Operations | null>(null)
  const [message, setMessage] = useState('')
  const [reviewResult, setReviewResult] = useState<'pass' | 'warning' | 'fail'>('pass')
  const [drifts, setDrifts] = useState<string[]>([])

  const refreshOperations = async () => {
    const response = await fetch(`/api/books/${bookId}/storyboard/${episode}/${shotId}/transition-state`)
    if (response.ok) setOperations(await response.json() as Operations)
  }
  const refresh = async () => {
    const response = await fetch(`/api/books/${bookId}/storyboard/${episode}/${shotId}/transition-contract`)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const payload = await response.json() as ContractResponse
    if (payload.not_applicable) { setState('first-shot'); setData(null); setOperations(null); return }
    setData(payload); setState('loaded'); await refreshOperations()
  }

  useEffect(() => {
    let cancelled = false
    if (!episode) { setState('error'); return () => { cancelled = true } }
    setState('loading'); setData(null); setOperations(null); setMessage('')
    void refresh().catch(() => { if (!cancelled) setState('error') })
    return () => { cancelled = true }
  // The request must reload whenever the selected shot changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookId, episode, shotId])

  const contract = data?.contract
  const draft = data?.draft
  const sourceShotId = contract?.source_shot_id ?? draft?.source_shot_id
  const lockedFrame = useMemo(() => (operations?.frames || []).find((item) => item.status === 'locked' && item.evidence_status !== 'stale'), [operations?.frames])
  const candidateReview = useMemo(() => (operations?.reviews || []).find((item) => item.status === 'candidate' && item.evidence_status !== 'stale'), [operations?.reviews])
  const reviewed = useMemo(() => (operations?.reviews || []).find((item) => item.status === 'reviewed' && item.evidence_status !== 'stale'), [operations?.reviews])
  const evidenceStale = operations?.readiness?.status === 'stale'

  const confirmContract = async () => {
    if (!draft || sourceShotId == null || !window.confirm('确认采用系统建议，让当前镜头承接上一镜吗？不会生成视频，也不会修改镜头内容。')) return
    const response = await fetch(`/api/books/${bookId}/storyboard/${episode}/${shotId}/transition-contract/confirm`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sourceShotId, continuityLevel: draft.continuity_level || 'soft', entryState: draft.entry_state || '', exitState: draft.exit_state || '', inheritRules: draft.inherit_rules || {}, allowedChanges: draft.allowed_changes || [], forbiddenChanges: draft.forbidden_changes || [], requiredTransitionFrame: draft.required_transition_frame || '', confirmed: true, allowWrite: true }) })
    const payload = await response.json(); setMessage(response.ok ? '已确认画面承接规则。接下来按提示继续即可。' : String(payload.detail || '确认失败')); if (response.ok) await refresh()
  }
  const extract = async () => {
    if (sourceShotId == null || !window.confirm('确认从上一镜已验收的视频提取交接画面吗？系统只会生成候选，不会自动生成新视频。')) return
    const response = await fetch(`/api/books/${bookId}/storyboard/${episode}/${shotId}/transition-frames/extract`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sourceShotId, frameKind: 'near_last', confirmed: true, allowWrite: true }) })
    const payload = await response.json(); setMessage(response.ok ? '交接画面已生成，请在高级区确认使用。' : String(payload.detail || '提取失败')); if (response.ok) await refreshOperations()
  }
  const lock = async (frameId: number) => {
    if (!window.confirm('确认使用这张交接画面吗？之后生成或复核时会以它作为相邻镜头的共同依据。')) return
    const response = await fetch(`/api/books/${bookId}/storyboard/${episode}/${shotId}/transition-frames/${frameId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'locked', confirmed: true, allowWrite: true }) })
    const payload = await response.json(); setMessage(response.ok ? '交接画面已确认。' : String(payload.detail || '确认失败')); if (response.ok) await refreshOperations()
  }
  const extractReview = async () => {
    if (sourceShotId == null || !window.confirm('确认提取当前视频的起始画面，用来和上一镜进行对比吗？不会自动给出通过结论。')) return
    const response = await fetch(`/api/books/${bookId}/storyboard/${episode}/${shotId}/transition-continuity-reviews/extract`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sourceShotId, targetVideoAssetId: operations?.target?.video_id || undefined, confirmed: true, allowWrite: true }) })
    const payload = await response.json(); setMessage(response.ok ? '对比画面已准备好，请完成检查。' : String(payload.detail || '提取失败')); if (response.ok) await refreshOperations()
  }
  const saveReview = async (reviewId: number) => {
    if (!window.confirm('确认保存这次画面衔接检查结果吗？')) return
    const response = await fetch(`/api/books/${bookId}/storyboard/${episode}/${shotId}/transition-continuity-reviews/${reviewId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reviewResult, driftCategories: drifts, confirmed: true, allowWrite: true }) })
    const payload = await response.json(); setMessage(response.ok ? '画面衔接检查已保存。' : String(payload.detail || '保存失败')); if (response.ok) await refreshOperations()
  }

  if (state === 'loading') return <div role="status" aria-live="polite" className="mt-4 text-xs text-slate-500">正在整理上一镜与当前镜的关系…</div>
  if (state === 'first-shot') return <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/40 px-3 py-3 text-xs text-slate-300"><div className="font-medium text-white">这是本集的第一个镜头</div><div className="mt-1 text-slate-400">不需要承接上一镜，直接按上方主操作继续制作即可。</div></div>
  if (state === 'error' || sourceShotId == null) return null

  let title = '确认画面承接方式'; let description = `系统建议当前镜头与镜头 ${sourceShotId} 保持人物、场景和剧情上的连续。`; let label = '确认系统建议'; let action: (() => void) | undefined = confirmContract; let disabled = false
  if (contract && !operations?.source?.ready_for_handoff) { title = `先完成镜头 ${sourceShotId}`; description = '上一镜视频还没有完成验收。先完成并确认上一镜，当前镜才能获得可靠的衔接依据。'; label = '等待上一镜完成'; action = undefined; disabled = true }
  else if (contract && evidenceStale) { title = '上一镜或当前镜的视频已更新'; description = '之前的对比依据来自旧视频版本，系统已保留历史记录但不会再把它当作当前结论。请重新提取交接画面，再完成一次检查。'; label = '重新提取交接画面'; action = extract }
  else if (contract && !lockedFrame) { title = '准备两镜之间的交接画面'; description = '系统会从上一镜视频末尾提取一张画面，供你确认后用于后续检查或强连续生成。'; label = '提取交接画面'; action = extract }
  else if (contract && !operations?.target?.has_adopted_video) { title = '生成当前镜头的视频'; description = '上一镜的交接条件已经准备好。请使用上方“生成视频”主按钮制作当前镜头；系统会自动带入已确认的承接规则。'; label = '请使用上方生成视频'; action = undefined; disabled = true }
  else if (contract && !candidateReview && !reviewed) { title = '检查两镜画面是否自然衔接'; description = '当前镜视频已生成。先提取它的起始画面，再与上一镜交接画面对比人物、服装、场景、道具和画面方向。'; label = '准备对比画面'; action = extractReview }
  else if (candidateReview) { title = '确认画面衔接结果'; description = '请查看两张对比画面；没有发现变化就选“通过”，否则标记需要修复的内容。'; label = '在下方填写检查结果'; action = undefined; disabled = true }
  else if (reviewed?.review_result === 'pass') { title = '两镜衔接已完成'; description = '人物、服装、场景、道具与构图检查已留存。可以继续处理下一镜。'; label = '已通过'; action = undefined; disabled = true }

  return <section className="mt-4 rounded-xl border border-sky-400/25 bg-sky-400/5 p-4">
    <div className="flex flex-wrap items-center justify-between gap-2"><div><div className="text-sm font-medium text-white">和上一镜保持衔接</div><div className="mt-1 text-xs text-slate-400">镜头 {sourceShotId} → 镜头 {shotId}</div></div><span className="rounded-full border border-sky-300/30 bg-slate-950/30 px-2 py-1 text-[11px] text-sky-100">{contract ? humanLevel(contract.continuity_level) : '系统已准备建议'}</span></div>
    <div className="mt-4 rounded-lg border border-slate-700/70 bg-slate-950/35 p-3"><div className="text-sm font-medium text-white">下一步：{title}</div><div className="mt-1 text-xs leading-5 text-slate-400">{description}</div><button type="button" onClick={action} disabled={disabled} className="mt-3 rounded-lg border border-sky-300/40 bg-sky-400/10 px-3 py-1.5 text-xs font-medium text-sky-50 transition hover:bg-sky-400/20 disabled:cursor-default disabled:border-slate-700 disabled:bg-slate-900/60 disabled:text-slate-400">{label}</button></div>
    {message ? <div role="status" aria-live="polite" className="mt-3 text-xs text-slate-300">{message}</div> : null}
    {candidateReview ? <div className="mt-3 rounded-lg border border-amber-300/25 bg-amber-300/5 p-3 text-xs text-slate-300">{candidateReview.target_first_frame_url ? <a href={candidateReview.target_first_frame_url} target="_blank" rel="noreferrer" className="text-sky-200 underline">查看当前镜起始画面</a> : null}<div className="mt-3 flex flex-wrap gap-2"><select value={reviewResult} onChange={(event) => setReviewResult(event.target.value as 'pass' | 'warning' | 'fail')} className="rounded border border-slate-600 bg-slate-950 px-2 py-1 text-slate-100"><option value="pass">画面衔接通过</option><option value="warning">有小问题，后续留意</option><option value="fail">不通过，需要修复</option></select><button type="button" onClick={() => void saveReview(candidateReview.id)} className="rounded border border-emerald-300/40 px-2 py-1 text-emerald-100">保存检查结果</button></div><div className="mt-3 flex flex-wrap gap-3 text-[11px] text-slate-400">{[['identity_drift', '人物变样'], ['costume_drift', '服装变化'], ['scene_drift', '场景变化'], ['prop_drift', '道具变化'], ['composition_jump', '画面方向跳变']].map(([value, text]) => <label key={value}><input type="checkbox" checked={drifts.includes(value)} onChange={() => setDrifts((items) => items.includes(value) ? items.filter((item) => item !== value) : [...items, value])} /> {text}</label>)}</div></div> : null}
    <details className="mt-3 rounded-lg border border-slate-800 bg-slate-950/30 p-3"><summary className="cursor-pointer text-xs text-slate-300">高级：查看合同、交接画面与历史记录</summary><div className="mt-3 space-y-2 text-[11px] leading-5 text-slate-400">{contract ? <><div>连续级别：{technicalLevel(contract.continuity_level)} · {contract.status === 'confirmed' ? '已确认' : '待确认'}</div><div>入镜状态：{contract.entry_state || '未填写'}</div><div>出镜状态：{contract.exit_state || '未填写'}</div></> : <div>系统草案尚未写入，确认前不会改变任何内容。</div>}{(operations?.frames || []).map((frame) => <div key={frame.id} className="flex flex-wrap items-center gap-2"><span>交接画面 · {frame.evidence_status === 'stale' ? '旧视频版本，需重新提取' : frame.status}</span>{frame.public_url ? <a href={frame.public_url} target="_blank" rel="noreferrer" className="text-sky-300">查看</a> : null}{frame.status !== 'locked' ? <button type="button" onClick={() => void lock(frame.id)} className="rounded border border-slate-600 px-2 py-0.5 text-slate-200">确认使用</button> : null}</div>)}{reviewed ? <div>最近检查：{reviewed.review_result === 'pass' ? '通过' : reviewed.review_result || '未记录'}{reviewed.drift_categories?.length ? ` · ${reviewed.drift_categories.join('、')}` : ''}</div> : null}</div></details>
  </section>
}
