import { useMemo, useState } from 'react'
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  CircleDashed,
  Image as ImageIcon,
  Info,
  Layers3,
  LockKeyhole,
  Video,
} from 'lucide-react'
import {
  humanizeProductionState,
  type MediaCandidateProjection,
  type ProductionMediaLane,
  type ProductionWorkspaceLoadState,
  type ProductionWorkspaceV2Snapshot,
  type ProductionWorkspaceViewMode,
} from '../domain/productionWorkspace'
import { promoteProductionMediaCandidate, validateProductionMediaCandidate } from '../services/productionWorkspace'
import { submitCanonicalProductionGeneration } from '../services/productionGeneration'
import { readExplicitGenerationProfileSelection } from './productWorkspaceGeneration'

interface Props {
  snapshot?: ProductionWorkspaceV2Snapshot | null
  state?: ProductionWorkspaceLoadState
  error?: string | null
  mode: ProductionWorkspaceViewMode
  onNavigateSection?: (section: 'assets' | 'storyboard') => void
  onSelectAsset?: (entityId: string) => void
  focusShotId?: string | null
  onRefresh?: () => void
  imageModelProfileId?: string | null
  videoModelProfileId?: string | null
}

function StatePill({ state, label }: { state: string; label?: string }) {
  const tone = ['blocked', 'stale', 'needs_action'].includes(state)
    ? 'border-rose-500/30 bg-rose-500/10 text-rose-100'
    : ['complete', 'ready'].includes(state)
      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100'
      : 'border-slate-700 bg-slate-950/50 text-slate-300'
  return <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${tone}`}>{label ?? humanizeProductionState(state)}</span>
}

function LaneSummary({ lane, target, mode, onGenerate, selectedProfileId, actionMessage }: { lane: ProductionMediaLane; target: 'IMAGE' | 'VIDEO'; mode: ProductionWorkspaceViewMode; onGenerate?: () => void; selectedProfileId?: string | null; actionMessage?: string }) {
  const Icon = target === 'IMAGE' ? ImageIcon : Video
  const official = lane.official.current
  const candidateCount = lane.candidates.count
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3" aria-label={`${target} production lane`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-200"><Icon className="h-3.5 w-3.5" />{target}</div>
        <div className="flex flex-wrap justify-end gap-1">{official ? <StatePill state="complete" label="当前正式版本" /> : null}{candidateCount > 0 ? <StatePill state="needs_action" label="候选待审核" /> : null}{!official && candidateCount === 0 ? <StatePill state={lane.prompt_ir.stale ? 'stale' : 'not_started'} label={lane.prompt_ir.stale ? '需要更新' : '尚未生成'} /> : null}</div>
      </div>
      <div className="mt-3 grid gap-2 text-xs text-slate-400 sm:grid-cols-3">
        <div><div className="text-slate-600">生成准备</div><div className="mt-1 text-slate-200">{lane.prompt_ir.current ? '已确认' : lane.prompt_ir.stale ? '需要更新' : '未完成'}</div></div>
        <div><div className="text-slate-600">候选结果</div><div className="mt-1 text-slate-200">{candidateCount > 0 ? `${candidateCount} 个候选` : '暂无候选'}</div></div>
        <div><div className="text-slate-600">正式版本</div><div className="mt-1 text-slate-200">{official ? '当前正式版本' : '尚未建立'}</div></div>
      </div>
      {target === 'VIDEO' ? <div className="mt-3 rounded-md border border-slate-800 bg-slate-900/60 px-2.5 py-2 text-xs text-slate-400">视频来源：{lane.source_official_image?.current ? '当前正式图片' : lane.generation_mode === 'IMAGE_TO_VIDEO' ? '等待当前正式图片' : lane.generation_mode === 'TEXT_TO_VIDEO' ? '文本生成' : '等待当前 VIDEO PromptIR'}</div> : null}
      <div className="mt-3 flex items-center justify-between gap-2">
        <span className="text-[11px] text-slate-500">{selectedProfileId ? `本次选择：${selectedProfileId}` : '请选择已配置的生成模型'}{lane.model.last_execution_profile_id ? ` · 上次执行：${lane.model.last_execution_profile_id}` : ''}</span>
        <button type="button" disabled={!onGenerate || !selectedProfileId || (lane.generation_readiness ? !lane.generation_readiness.ready : (!lane.prompt_ir.current || official))} onClick={onGenerate} className="rounded-md border border-slate-700 px-2.5 py-1.5 text-[11px] text-slate-300 disabled:cursor-not-allowed disabled:opacity-50">{target === 'IMAGE' ? '生成图片' : '生成视频'}</button>
      </div>
      {lane.generation_readiness && !lane.generation_readiness.ready && lane.generation_readiness.primary_blocker ? <div className="mt-2 text-[11px] text-rose-200/80">{lane.generation_readiness.primary_blocker.message}</div> : null}
      {actionMessage ? <div className="mt-2 text-[11px] text-violet-200">{actionMessage}</div> : null}
      {mode === 'professional' ? (
        <details className="mt-3 rounded-md border border-slate-800 bg-slate-900/40 px-2.5 py-2">
          <summary className="flex cursor-pointer list-none items-center justify-between text-[11px] text-slate-400"><span>查看专业链路</span><ChevronDown className="h-3.5 w-3.5" /></summary>
          <div className="mt-2 space-y-1 font-mono text-[10px] leading-5 text-slate-500">
            <div>PromptIR: {String(lane.prompt_ir.version ?? '—')} · {lane.prompt_ir.payload_hash || 'no hash'}</div>
            <div>ModelProfile: {lane.model.selected_profile_id || '未显式选择'}</div>
            <div>Execution: {lane.latest_execution?.id || '—'} · {lane.latest_execution?.state || '—'}</div>
            <div>OfficialMedia: {lane.official.version?.id || '—'} · {lane.official.authority?.id || '—'}</div>
          </div>
        </details>
      ) : null}
    </div>
  )
}

function CandidateList({ lane, mode, onRefresh }: { lane: ProductionMediaLane; mode: ProductionWorkspaceViewMode; onRefresh?: () => void }) {
  const [actionState, setActionState] = useState<Record<string, 'idle' | 'working' | 'error'>>({})
  const [actionMessage, setActionMessage] = useState<Record<string, string>>({})

  const runCandidateAction = async (candidate: MediaCandidateProjection) => {
    const candidateId = String(candidate.id || '').trim()
    if (!candidateId) return
    const validationId = String(candidate.technical_validation.validation_id || '').trim()
    const canPromote = candidate.technical_validation.status.toUpperCase() === 'PASS' && Boolean(validationId)
    setActionState((current) => ({ ...current, [candidateId]: 'working' }))
    setActionMessage((current) => ({ ...current, [candidateId]: '' }))
    try {
      if (canPromote) await promoteProductionMediaCandidate(candidateId, validationId)
      else await validateProductionMediaCandidate(candidateId)
      setActionState((current) => ({ ...current, [candidateId]: 'idle' }))
      setActionMessage((current) => ({ ...current, [candidateId]: canPromote ? '已设为正式版本，正在刷新投影。' : '候选已完成技术验证，正在刷新投影。' }))
      onRefresh?.()
    } catch (error) {
      setActionState((current) => ({ ...current, [candidateId]: 'error' }))
      setActionMessage((current) => ({ ...current, [candidateId]: error instanceof Error ? error.message : '候选操作失败，请查看专业详情。' }))
    }
  }

  if (lane.candidates.items.length === 0) return <div className="mt-3 text-xs text-slate-500">暂无候选结果。生成后会先进入候选区，审核通过后才会成为正式版本。</div>
  return (
    <div className="mt-3 space-y-2">
      {lane.candidates.items.map((candidate) => (
          <div key={candidate.id} className="rounded-md border border-amber-500/20 bg-amber-500/5 p-2.5">
          <div className="flex items-center justify-between gap-2"><span className="text-xs font-medium text-amber-100">候选结果</span><span className="text-[10px] text-slate-500">{candidate.technical_validation.status}</span></div>
          <div className="mt-1 text-[11px] text-slate-400">{candidate.created_at ? new Date(candidate.created_at).toLocaleString() : '生成时间未知'} · {candidate.model_profile_id || '模型未记录'}</div>
          {candidate.preview ? <a className="mt-2 inline-block text-[11px] text-violet-200 underline" href={candidate.preview} target="_blank" rel="noreferrer">预览候选结果</a> : null}
          {mode === 'professional' ? <div className="mt-1 font-mono text-[10px] text-slate-600">candidate_id={candidate.id} · validation_id={candidate.technical_validation.validation_id || '—'}</div> : null}
          <div className="mt-2 text-[11px] text-amber-100/80">这只是候选结果，不是当前正式版本。</div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={!onRefresh || actionState[candidate.id] === 'working' || (candidate.technical_validation.status.toUpperCase() !== 'PASS' && Boolean(candidate.technical_validation.validation_id))}
              onClick={() => { void runCandidateAction(candidate) }}
              className="rounded-md border border-amber-400/40 px-2.5 py-1.5 text-[11px] text-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {actionState[candidate.id] === 'working'
                ? '处理中…'
                : candidate.technical_validation.status.toUpperCase() === 'PASS' && candidate.technical_validation.validation_id
                  ? '设为正式版本'
                  : '验证候选'}
            </button>
            {actionMessage[candidate.id] ? <span className="text-[11px] text-slate-400">{actionMessage[candidate.id]}</span> : null}
          </div>
        </div>
      ))}
    </div>
  )
}

function ShotCard({ shot, mode, focused, onRefresh, onGenerate, selectedImageProfileId, selectedVideoProfileId, actionMessages }: { shot: ProductionWorkspaceV2Snapshot['shots'][number]; mode: ProductionWorkspaceViewMode; focused: boolean; onRefresh?: () => void; onGenerate?: (target: 'IMAGE' | 'VIDEO') => void; selectedImageProfileId?: string | null; selectedVideoProfileId?: string | null; actionMessages?: Record<string, string> }) {
  return (
    <article className={`rounded-xl border bg-slate-900 p-4 ${focused ? 'border-violet-400/60 ring-1 ring-violet-400/30' : 'border-slate-800'}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-white"><span>镜头 {shot.identity.shot_id}</span><StatePill state={shot.asset_readiness.state} /></div>
          <div className="mt-1 text-xs text-slate-500">第 {shot.identity.episode} 集 · {shot.scene.name || shot.scene.id} · {shot.duration} 秒</div>
        </div>
        <div className="rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-right"><div className="text-[10px] text-sky-200/70">唯一下一步</div><div className="mt-1 text-xs font-medium text-sky-100">{shot.next_action.label}</div></div>
      </div>
      {shot.blockers.length > 0 ? <div className="mt-3 flex items-start gap-2 rounded-lg border border-rose-500/20 bg-rose-500/5 px-3 py-2 text-xs text-rose-100"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /><span>{shot.blockers[0].message}</span></div> : null}
      <div className="mt-4 grid gap-3 xl:grid-cols-2">
        <LaneSummary lane={shot.IMAGE} target="IMAGE" mode={mode} selectedProfileId={selectedImageProfileId} actionMessage={actionMessages?.IMAGE} onGenerate={() => onGenerate?.('IMAGE')} />
        <LaneSummary lane={shot.VIDEO} target="VIDEO" mode={mode} selectedProfileId={selectedVideoProfileId} actionMessage={actionMessages?.VIDEO} onGenerate={() => onGenerate?.('VIDEO')} />
      </div>
      <div className="mt-3 grid gap-3 xl:grid-cols-2">
        <CandidateList lane={shot.IMAGE} mode={mode} onRefresh={onRefresh} />
        <CandidateList lane={shot.VIDEO} mode={mode} onRefresh={onRefresh} />
      </div>
      {mode === 'professional' ? <div className="mt-3 rounded-md border border-slate-800 bg-slate-950/40 p-2.5 font-mono text-[10px] leading-5 text-slate-600">storyboard_shot_id={shot.identity.storyboard_shot_id} · plan_shot_id={shot.identity.plan_shot_id || '—'} · scene_id={shot.scene.id || '—'}</div> : null}
    </article>
  )
}

export default function ProductionWorkspaceV2Panel({ snapshot, state, error, mode, onNavigateSection, onSelectAsset, focusShotId, onRefresh, imageModelProfileId, videoModelProfileId }: Props) {
  const [showAllAssets, setShowAllAssets] = useState(false)
  const [actionMessages, setActionMessages] = useState<Record<string, string>>({})
  const assets = snapshot?.assets ?? []
  const missingAssets = useMemo(() => assets.filter((asset) => !asset.media.present), [assets])
  const visibleAssets = showAllAssets ? assets : (missingAssets.length > 0 ? missingAssets : assets).slice(0, 8)
  const profileSelection = readExplicitGenerationProfileSelection()
  const selectedImageProfileId = imageModelProfileId ?? profileSelection.imageModelProfileId
  const selectedVideoProfileId = videoModelProfileId ?? profileSelection.videoModelProfileId

  const runGeneration = async (shot: ProductionWorkspaceV2Snapshot['shots'][number], target: 'IMAGE' | 'VIDEO') => {
    const modelProfileId = target === 'IMAGE' ? selectedImageProfileId : selectedVideoProfileId
    if (!modelProfileId) return
    const lane = shot[target]
    if (lane.generation_readiness && !lane.generation_readiness.ready) {
      setActionMessages((current) => ({ ...current, [`${shot.identity.storyboard_shot_id}:${target}`]: lane.generation_readiness?.primary_blocker?.message || '当前生产状态不允许生成。' }))
      return
    }
    setActionMessages((current) => ({ ...current, [`${shot.identity.storyboard_shot_id}:${target}`]: '正在提交 canonical 生成任务…' }))
    try {
      await submitCanonicalProductionGeneration({
        bookId: snapshot!.book_id,
        episode: Number(shot.identity.episode),
        shotId: shot.identity.shot_id,
        target,
        modelProfileId,
        generationChain: 'production_workspace_v2',
      })
      setActionMessages((current) => ({ ...current, [`${shot.identity.storyboard_shot_id}:${target}`]: '已提交，候选结果生成后会出现在本工作区。' }))
      onRefresh?.()
    } catch (generationError) {
      setActionMessages((current) => ({ ...current, [`${shot.identity.storyboard_shot_id}:${target}`]: generationError instanceof Error ? generationError.message : '生成提交失败。' }))
    }
  }

  if (state === 'loading' || (!snapshot && state !== 'unavailable')) return <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 text-sm text-slate-400">正在读取 Production Workspace…</div>
  if (state === 'unavailable' || !snapshot) return <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-5 text-sm text-rose-100"><div className="font-medium">Production Workspace 暂时不可用</div><div className="mt-2 text-xs text-rose-100/80">{error || '请刷新后重试。不会用浏览器缓存替代权威生产状态。'}</div></div>

  const projectBlocker = snapshot.project.current_blockers[0]
  return (
    <section className="space-y-5" aria-label="Production Workspace V2">
      <div className="rounded-xl border border-violet-500/25 bg-violet-500/5 p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><div className="flex items-center gap-2 text-sm font-semibold text-white"><Layers3 className="h-4 w-4 text-violet-300" />Production Workspace</div><div className="mt-1 text-xs text-slate-400">同一份后端权威投影 · {snapshot.project.overall_progress}% · {humanizeProductionState(snapshot.project.overall_state)}</div></div>
          <div className="flex items-center gap-2 text-xs text-slate-400"><LockKeyhole className="h-3.5 w-3.5" />只读投影</div>
        </div>
        {projectBlocker ? <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-rose-500/25 bg-rose-500/10 p-3"><div><div className="text-sm font-medium text-rose-50">{projectBlocker.title}</div><div className="mt-1 text-xs text-rose-100/80">{projectBlocker.description}</div></div>{onNavigateSection ? <button type="button" onClick={() => onNavigateSection('assets')} className="inline-flex items-center gap-2 rounded-lg bg-rose-600 px-3 py-2 text-xs font-medium text-white hover:bg-rose-500">前往资产中心<ArrowRight className="h-3.5 w-3.5" /></button> : null}</div> : <div className="mt-4 rounded-lg border border-emerald-500/25 bg-emerald-500/10 p-3 text-sm text-emerald-100"><CheckCircle2 className="mr-2 inline h-4 w-4" />当前项目没有权威生产阻塞。</div>}
        {mode === 'professional' ? <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 text-xs text-slate-500">Legacy adopted：仅历史展示，不等于当前正式版本。</div> : null}
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="text-sm font-semibold text-white">资产准备</div><div className="mt-1 text-xs text-slate-400">实体优先 · {assets.length} 个 Production Assets · {missingAssets.length} 个缺少真实视觉资产</div></div><Info className="h-4 w-4 text-slate-500" /></div>
        {visibleAssets.length > 0 ? <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{visibleAssets.map((asset) => {
          const state = !asset.media.present ? 'blocked' : asset.stale_status.toUpperCase() === 'STALE' ? 'stale' : 'ready'
          const label = !asset.media.present ? '缺少真实视觉资产' : state === 'stale' ? '需要更新' : '当前有效'
          return <button key={asset.entity_id} type="button" onClick={() => { onSelectAsset?.(asset.entity_id); onNavigateSection?.('assets') }} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-left hover:border-violet-400/40">
            {asset.media.preview_url ? <img src={asset.media.preview_url} alt={`${asset.entity_id} 当前媒体预览`} className="mb-2 h-20 w-full rounded object-cover" /> : null}
            <div className="flex items-center justify-between gap-2"><span className="truncate text-sm font-medium text-white">{asset.entity_id}</span><StatePill state={state} label={label} /></div>
            <div className="mt-1 text-[11px] text-slate-500">{asset.asset_type} · 绑定 {asset.bindings.length} 个镜头 · {asset.current_version_id ? `版本 ${asset.current_version_id}` : '尚无正式版本'}</div>
            <div className="mt-2 text-[11px] text-violet-200">{asset.media.present ? '查看实体详情与绑定 →' : '选择实体并上传绑定 →'}</div>
          </button>
        })}</div> : <div className="mt-4 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3 text-sm text-emerald-100">当前没有 Production Asset 记录。</div>}
        {((missingAssets.length > 8) || (missingAssets.length === 0 && assets.length > 8)) ? <button type="button" onClick={() => setShowAllAssets((value) => !value)} className="mt-3 text-xs text-violet-200 hover:text-white">{showAllAssets ? '收起资产' : missingAssets.length > 0 ? `查看全部 ${missingAssets.length} 个缺失资产` : `查看全部 ${assets.length} 个资产`}</button> : null}
      </div>

      <div className="space-y-3"><div className="flex items-center justify-between gap-3"><div><div className="text-sm font-semibold text-white">镜头生产</div><div className="mt-1 text-xs text-slate-500">IMAGE 与 VIDEO 是两条独立泳道；候选结果不会自动成为正式版本。</div></div><CircleDashed className="h-4 w-4 text-slate-500" /></div>{snapshot.shots.length > 0 ? snapshot.shots.map((shot) => <ShotCard key={`${shot.identity.episode}-${shot.identity.storyboard_shot_id}`} shot={shot} mode={mode} focused={String(shot.identity.shot_id) === String(focusShotId ?? '')} onRefresh={onRefresh} onGenerate={(target) => { void runGeneration(shot, target) }} selectedImageProfileId={selectedImageProfileId} selectedVideoProfileId={selectedVideoProfileId} actionMessages={{ IMAGE: actionMessages[`${shot.identity.storyboard_shot_id}:IMAGE`], VIDEO: actionMessages[`${shot.identity.storyboard_shot_id}:VIDEO`] }} />) : <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900 p-5 text-sm text-slate-400">当前投影还没有可展示的镜头。</div>}</div>
    </section>
  )
}
