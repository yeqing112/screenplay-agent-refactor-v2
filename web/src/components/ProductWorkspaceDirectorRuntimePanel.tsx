import { useEffect, useMemo, useState } from 'react'

type StageState = 'idle' | 'loading' | 'ready' | 'saving' | 'approved' | 'error'

type Blocking = {
  id?: number
  scene_name?: string
  status?: string
  participants?: Array<Record<string, unknown>>
  beat_transitions?: Array<Record<string, unknown>>
  spatial_rules?: string[]
  unknowns?: string[]
  evidence_fingerprint?: string
}

type ShotPlanItem = {
  plan_shot_id: string
  beat_id?: string
  purpose?: string
  event?: string
  camera?: { shot_size?: string; movement?: string } | null
  duration_hint_seconds?: number | null
  continuity?: string
}

type ShotPlan = {
  id?: number
  scene_name?: string
  status?: string
  shots?: ShotPlanItem[]
  unknowns?: string[]
  evidence_fingerprint?: string
}

type PreviewResponse = {
  persisted_draft_id?: number | null
  blocking?: Blocking
  plan?: ShotPlan
  message?: string
}

type Benchmark = { status?: string; score?: number; checks?: Array<{ label?: string; passed?: boolean; detail?: string }> }
type SceneSummary = { scene_name?: string; status?: string }

type Props = { bookId: number; episode: number | null }

const button = 'rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-50'
const primary = 'rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-50'

function statusLabel(status: string | undefined, state: StageState) {
  if (state === 'loading') return '读取中'
  if (state === 'saving') return '写入中'
  if (state === 'error') return '需要处理'
  if (status === 'approved') return '已批准'
  if (status === 'draft') return '待确认'
  return '未生成'
}

export default function ProductWorkspaceDirectorRuntimePanel({ bookId, episode }: Props) {
  const [blocking, setBlocking] = useState<Blocking | null>(null)
  const [blockingDraftId, setBlockingDraftId] = useState<number | null>(null)
  const [blockingState, setBlockingState] = useState<StageState>('idle')
  const [blockingMessage, setBlockingMessage] = useState('')
  const [plan, setPlan] = useState<ShotPlan | null>(null)
  const [planDraftId, setPlanDraftId] = useState<number | null>(null)
  const [planState, setPlanState] = useState<StageState>('idle')
  const [planMessage, setPlanMessage] = useState('')
  const [benchmark, setBenchmark] = useState<Benchmark | null>(null)
  const [benchmarkState, setBenchmarkState] = useState<StageState>('idle')
  const [sceneNames, setSceneNames] = useState<string[]>([])
  const [selectedScene, setSelectedScene] = useState('')

  const base = `/api/books/${bookId}/episodes/${episode ?? ''}`

  const refresh = async () => {
    if (!episode) return
    try {
      const [treatmentResponse, blockingResponse, planResponse, benchmarkResponse] = await Promise.all([
        fetch(`${base}/director-treatments`, { cache: 'no-store' }),
        fetch(`${base}/scene-blockings`, { cache: 'no-store' }),
        fetch(`${base}/shot-plans`, { cache: 'no-store' }),
        fetch(`${base}/director-benchmark`, { cache: 'no-store' }),
      ])
      const names = new Set<string>()
      if (treatmentResponse.ok) {
        const payload = await treatmentResponse.json() as { items?: SceneSummary[] }
        for (const item of payload.items ?? []) if (item.scene_name) names.add(item.scene_name)
      }
      if (blockingResponse.ok) {
        const payload = await blockingResponse.json() as { items?: Blocking[] }
        for (const item of payload.items ?? []) if (item.scene_name) names.add(item.scene_name)
        const latest = (payload.items ?? []).find((item) => !selectedScene || item.scene_name === selectedScene)
        if (latest) setBlocking(latest)
      }
      if (planResponse.ok) {
        const payload = await planResponse.json() as { items?: ShotPlan[] }
        for (const item of payload.items ?? []) if (item.scene_name) names.add(item.scene_name)
        const latest = (payload.items ?? []).find((item) => !selectedScene || item.scene_name === selectedScene)
        if (latest) setPlan(latest)
      }
      const orderedNames = Array.from(names).sort((a, b) => a.localeCompare(b, 'zh-CN'))
      setSceneNames(orderedNames)
      if (!selectedScene && orderedNames[0]) setSelectedScene(orderedNames[0])
      if (benchmarkResponse.ok) {
        const payload = await benchmarkResponse.json() as { report?: Benchmark }
        setBenchmark(payload.report ?? null)
      }
    } catch {
      // The individual actions surface actionable errors; background refresh is best effort.
    }
  }

  useEffect(() => {
    setBlocking(null)
    setBlockingDraftId(null)
    setBlockingState('idle')
    setBlockingMessage('')
    setPlan(null)
    setPlanDraftId(null)
    setPlanState('idle')
    setPlanMessage('')
    setBenchmark(null)
    setBenchmarkState('idle')
    setSceneNames([])
    setSelectedScene('')
    void refresh()
    // `base` is derived solely from the stable route props.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookId, episode])

  const previewBlocking = async () => {
    setBlockingState('loading')
    setBlockingMessage('正在读取剧本与已批准导演方案，生成空间调度证据...')
    try {
      const response = await fetch(`${base}/scene-blocking/preview`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sceneName: selectedScene, persist: true }),
      })
      const payload = await response.json() as PreviewResponse & { detail?: string }
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`)
      setBlocking(payload.blocking ?? null)
      setBlockingDraftId(payload.persisted_draft_id ?? null)
      setBlockingState('ready')
      setBlockingMessage(payload.message || '空间调度草案已生成；尚未修改镜头。')
    } catch (error) {
      setBlockingState('error')
      setBlockingMessage(error instanceof Error ? error.message : '空间调度证据生成失败')
    }
  }

  const confirmBlocking = async () => {
    if (!blockingDraftId || !blocking || !window.confirm('确认批准空间调度？这会建立版本并作为后续 ShotPlan 的空间依据。')) return
    setBlockingState('saving')
    setBlockingMessage('正在复验证据并写入空间调度版本...')
    try {
      const response = await fetch(`${base}/scene-blocking/confirm`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ blockingId: blockingDraftId, evidenceFingerprint: blocking.evidence_fingerprint, confirmed: true, blocking }),
      })
      const payload = await response.json() as { scene_blocking?: Blocking; detail?: string }
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`)
      setBlocking(payload.scene_blocking ?? blocking)
      setBlockingDraftId(null)
      setBlockingState('approved')
      setBlockingMessage('空间调度已批准；现在可以生成 ShotPlan。')
    } catch (error) {
      setBlockingState('error')
      setBlockingMessage(error instanceof Error ? error.message : '空间调度批准失败')
    }
  }

  const previewPlan = async () => {
    setPlanState('loading')
    setPlanMessage('正在依据已批准的导演方案和空间调度生成镜头计划...')
    try {
      const response = await fetch(`${base}/shot-plan/preview`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sceneName: selectedScene, persist: true }),
      })
      const payload = await response.json() as PreviewResponse & { detail?: string }
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`)
      setPlan(payload.plan ?? null)
      setPlanDraftId(payload.persisted_draft_id ?? null)
      setPlanState('ready')
      setPlanMessage(payload.message || 'ShotPlan 草案已生成；请补齐每个镜头的景别、运动和时长。')
    } catch (error) {
      setPlanState('error')
      setPlanMessage(error instanceof Error ? error.message : 'ShotPlan 生成失败')
    }
  }

  const confirmPlan = async () => {
    if (!planDraftId || !plan || !window.confirm('确认写入 ShotPlan 正式版本？确认后才会允许正式分镜生成。')) return
    setPlanState('saving')
    setPlanMessage('正在复验证据并写入 ShotPlan 版本...')
    try {
      const response = await fetch(`${base}/shot-plan/confirm`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ planId: planDraftId, evidenceFingerprint: plan.evidence_fingerprint, confirmed: true, plan }),
      })
      const payload = await response.json() as { shot_plan?: ShotPlan; detail?: string }
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`)
      setPlan(payload.shot_plan ?? plan)
      setPlanDraftId(null)
      setPlanState('approved')
      setPlanMessage('ShotPlan 已批准；正式分镜生成门禁已放行。')
    } catch (error) {
      setPlanState('error')
      setPlanMessage(error instanceof Error ? error.message : 'ShotPlan 批准失败')
    }
  }

  const runBenchmark = async () => {
    setBenchmarkState('loading')
    try {
      const response = await fetch(`${base}/director-benchmark`, { cache: 'no-store' })
      const payload = await response.json() as { report?: Benchmark; detail?: string }
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`)
      setBenchmark(payload.report ?? null)
      setBenchmarkState('ready')
    } catch {
      setBenchmarkState('error')
    }
  }

  const updatePlanShot = (index: number, patch: Partial<ShotPlanItem>) => {
    setPlan((current) => {
      if (!current?.shots) return current
      const shots = current.shots.map((shot, shotIndex) => shotIndex === index ? { ...shot, ...patch } : shot)
      return { ...current, shots }
    })
  }

  const changeScene = (scene: string) => {
    setSelectedScene(scene)
    setBlocking(null)
    setBlockingDraftId(null)
    setBlockingState('idle')
    setPlan(null)
    setPlanDraftId(null)
    setPlanState('idle')
    setBlockingMessage('')
    setPlanMessage('')
  }

  const approvedBlocking = blocking?.status === 'approved' || blockingState === 'approved'
  const approvedPlan = plan?.status === 'approved' || planState === 'approved'
  const benchmarkTone = useMemo(() => benchmark?.status === 'pass' ? 'text-emerald-300' : 'text-amber-300', [benchmark?.status])

  if (!episode) return null

  return (
    <section className="rounded-xl border border-sky-500/30 bg-sky-500/5 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-base font-semibold text-white">导演运行时（第 {episode} 集）</div>
          <p className="mt-1 text-sm text-slate-400">把“导演意图 → 空间调度 → 可执行镜头”分成三步。每一步都先预览，再由你确认。</p>
        </div>
        <div className="flex items-center gap-2"><label className="text-xs text-slate-500">当前场景<select value={selectedScene} onChange={(event) => changeScene(event.target.value)} className="ml-2 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-200" disabled={sceneNames.length === 0}><option value="">自动选择</option>{sceneNames.map((scene) => <option key={scene} value={scene}>{scene}</option>)}</select></label><button type="button" className={button} onClick={() => void refresh()}>刷新状态</button></div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <div className="flex items-center justify-between"><span className="text-xs text-slate-400">1 · 空间调度</span><span className="text-xs text-sky-200">{statusLabel(blocking?.status, blockingState)}</span></div>
          <div className="mt-1 text-sm text-white">SceneBlocking</div>
          <div className="mt-1 text-xs text-slate-500">确认人物站位、视线和空间规则</div>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <div className="flex items-center justify-between"><span className="text-xs text-slate-400">2 · 镜头计划</span><span className="text-xs text-sky-200">{statusLabel(plan?.status, planState)}</span></div>
          <div className="mt-1 text-sm text-white">ShotPlan</div>
          <div className="mt-1 text-xs text-slate-500">确认景别、机位、运动和时长</div>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <div className="flex items-center justify-between"><span className="text-xs text-slate-400">3 · 运行检查</span><span className={`text-xs ${benchmarkTone}`}>{benchmark?.status === 'pass' ? '通过' : benchmark ? '需要完善' : '未运行'}</span></div>
          <div className="mt-1 text-sm text-white">Director Benchmark</div>
          <div className="mt-1 text-xs text-slate-500">不调用外部模型，只检查证据和可执行性</div>
        </div>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
          <div className="flex items-center justify-between gap-3"><div className="text-sm font-medium text-white">空间调度证据</div><div className="flex gap-2"><button type="button" className={button} onClick={() => void previewBlocking()} disabled={blockingState === 'loading' || blockingState === 'saving'}>预览 / 更新</button><button type="button" className={approvedBlocking ? button : primary} onClick={() => void confirmBlocking()} disabled={!blockingDraftId || !blocking || approvedBlocking || blockingState === 'saving'}>{approvedBlocking ? '已批准' : '确认批准'}</button></div></div>
          {blocking ? <div className="mt-3 space-y-2 text-xs text-slate-300"><div>场景：{blocking.scene_name || '未命名场景'}</div><div>人物：{(blocking.participants ?? []).map((item) => `${String(item.name || item.character_id || '未知')}（${String(item.position || '位置待确认')}）`).join('、') || '暂无'}</div><div>规则：{(blocking.spatial_rules ?? []).join('；') || '暂无'}</div>{(blocking.unknowns ?? []).length > 0 ? <div className="text-amber-300">待补信息：{blocking.unknowns?.join('；')}</div> : <div className="text-emerald-300">空间信息完整，可进入 ShotPlan</div>}</div> : <div className="mt-3 text-xs text-slate-500">先点击“预览 / 更新”。需要已批准的导演方案。</div>}
          {blockingMessage ? <div className="mt-3 text-xs text-slate-400">{blockingMessage}</div> : null}
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
          <div className="flex items-center justify-between gap-3"><div className="text-sm font-medium text-white">镜头计划证据</div><div className="flex gap-2"><button type="button" className={button} onClick={() => void previewPlan()} disabled={!approvedBlocking || planState === 'loading' || planState === 'saving'}>预览 / 更新</button><button type="button" className={approvedPlan ? button : primary} onClick={() => void confirmPlan()} disabled={!planDraftId || !plan || approvedPlan || planState === 'saving'}>{approvedPlan ? '已写入' : '确认写入'}</button></div></div>
          {plan?.shots?.length ? <div className="mt-3 space-y-2">{plan.shots.map((shot, index) => <div key={shot.plan_shot_id} className="rounded border border-slate-800 p-2"><div className="text-xs font-medium text-slate-200">{shot.plan_shot_id} · {shot.event || shot.purpose || '镜头'}</div><div className="mt-2 grid gap-2 sm:grid-cols-3"><label className="text-[11px] text-slate-500">景别<input disabled={approvedPlan} value={shot.camera?.shot_size || ''} onChange={(event) => updatePlanShot(index, { camera: { ...(shot.camera || {}), shot_size: event.target.value } })} className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-200 disabled:cursor-not-allowed disabled:opacity-60" placeholder="如 MS" /></label><label className="text-[11px] text-slate-500">运动<input disabled={approvedPlan} value={shot.camera?.movement || ''} onChange={(event) => updatePlanShot(index, { camera: { ...(shot.camera || {}), movement: event.target.value } })} className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-200 disabled:cursor-not-allowed disabled:opacity-60" placeholder="如 static" /></label><label className="text-[11px] text-slate-500">时长（秒）<input disabled={approvedPlan} type="number" min="0.1" step="0.1" value={shot.duration_hint_seconds ?? ''} onChange={(event) => updatePlanShot(index, { duration_hint_seconds: Number(event.target.value) })} className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-200 disabled:cursor-not-allowed disabled:opacity-60" /></label></div></div>)}</div> : <div className="mt-3 text-xs text-slate-500">批准空间调度后，这里会出现可编辑的镜头计划。</div>}
          {planMessage ? <div className="mt-3 text-xs text-slate-400">{planMessage}</div> : null}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-950/50 p-3"><div><div className="text-sm font-medium text-white">运行完整性检查</div><div className="mt-1 text-xs text-slate-500">确认三层证据都已批准且镜头参数可执行。</div></div><button type="button" className={button} onClick={() => void runBenchmark()} disabled={benchmarkState === 'loading'}>运行 Benchmark</button>{benchmark ? <div className={`text-sm ${benchmarkTone}`}>{benchmark.status === 'pass' ? `通过 · ${benchmark.score ?? 0} 分` : `需要完善 · ${benchmark.score ?? 0} 分`}</div> : null}</div>
    </section>
  )
}
