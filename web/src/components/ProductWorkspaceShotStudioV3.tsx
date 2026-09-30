import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Film,
  Image as ImageIcon,
  Info,
  PanelRight,
  RefreshCw,
  Search,
  SlidersHorizontal,
} from 'lucide-react'
import type {
  ProductionWorkspaceLoadState,
  ProductionWorkspaceV2Snapshot,
  ProductionWorkspaceViewMode,
} from '../domain/productionWorkspace'
import {
  toShotStudioViewModels,
  type ProductionMediaLaneViewModel,
  type ProductionUiState,
  type ShotStudioViewModel,
} from '../domain/productionUiV3'
import {
  createShotStudioMediaReviewController,
  type ShotReviewCandidateIdentity,
  type ShotReviewMutationSnapshot,
} from '../services/productWorkspaceShotReview'
import {
  createShotStudioGenerationController,
  type ShotGenerationMutationSnapshot,
} from '../services/productWorkspaceShotGeneration'
import { approveProductionMediaCandidate, validateProductionMediaCandidate } from '../services/productionWorkspace'

interface ProductWorkspaceShotStudioV3Props {
  snapshot: ProductionWorkspaceV2Snapshot | null
  state?: ProductionWorkspaceLoadState
  error?: string | null
  mode?: ProductionWorkspaceViewMode
  focusShotId?: string | null
  onSelectShot: (shotId: string | null) => void
  onRefresh?: () => void
  onRefreshProductionWorkspaceV2?: () => Promise<void>
}

type StateFilter = 'all' | ProductionUiState
type MediaLane = 'IMAGE' | 'VIDEO'

const FILTERS: Array<{ value: StateFilter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'ready', label: '待处理' },
  { value: 'running', label: '生成中' },
  { value: 'review', label: '待审核' },
  { value: 'waiting', label: '等待' },
  { value: 'blocked', label: '阻塞' },
  { value: 'stale', label: '已更新' },
  { value: 'failed', label: '失败' },
  { value: 'official', label: '正式' },
]

const STATE_TONE: Record<ProductionUiState, { marker: string; text: string; border: string; bg: string }> = {
  ready: { marker: 'bg-[#8BC9D9]', text: 'text-[#8BC9D9]', border: 'border-[#8BC9D9]/40', bg: 'bg-[#8BC9D9]/10' },
  running: { marker: 'bg-[#8BC9D9]', text: 'text-[#8BC9D9]', border: 'border-[#8BC9D9]/40', bg: 'bg-[#8BC9D9]/10' },
  review: { marker: 'bg-[#C4B5E5]', text: 'text-[#C4B5E5]', border: 'border-[#C4B5E5]/40', bg: 'bg-[#C4B5E5]/10' },
  waiting: { marker: 'bg-[#DBB36F]', text: 'text-[#DBB36F]', border: 'border-[#DBB36F]/40', bg: 'bg-[#DBB36F]/10' },
  blocked: { marker: 'bg-[#DF8E8C]', text: 'text-[#DF8E8C]', border: 'border-[#DF8E8C]/40', bg: 'bg-[#DF8E8C]/10' },
  stale: { marker: 'bg-[#D68F62]', text: 'text-[#D68F62]', border: 'border-[#D68F62]/40', bg: 'bg-[#D68F62]/10' },
  failed: { marker: 'bg-[#DF8E8C]', text: 'text-[#DF8E8C]', border: 'border-[#DF8E8C]/40', bg: 'bg-[#DF8E8C]/10' },
  official: { marker: 'bg-[#9FCBAB]', text: 'text-[#9FCBAB]', border: 'border-[#9FCBAB]/40', bg: 'bg-[#9FCBAB]/10' },
}

function tone(state: ProductionUiState) {
  return STATE_TONE[state] ?? STATE_TONE.waiting
}

function normalize(value: unknown) {
  return String(value ?? '').trim().toLocaleLowerCase('zh-CN')
}

function lanePreview(lane: ProductionMediaLaneViewModel) {
  if (lane.official.isCanonicalOfficial) return lane.official.preview
  if (lane.candidate.reviewEligibility) {
    return lane.candidate.candidate?.preview ?? lane.candidate.candidate?.preview_url ?? null
  }
  return null
}

function laneEvidenceLabel(lane: ProductionMediaLaneViewModel) {
  if (lane.official.isCanonicalOfficial) return '正式版本'
  if (lane.candidate.reviewEligibility) return '候选 · 不是正式版本'
  return lane.stateLabel
}

function preferredMediaLane(shot: ShotStudioViewModel): MediaLane {
  if (shot.video.official.isCanonicalOfficial || shot.video.candidate.reviewEligibility) return 'VIDEO'
  if (shot.image.official.isCanonicalOfficial || shot.image.candidate.reviewEligibility) return 'IMAGE'
  if (shot.primaryAction.lane === 'VIDEO') return 'VIDEO'
  return 'IMAGE'
}

function stateFilterLabel(value: StateFilter) {
  return FILTERS.find((item) => item.value === value)?.label ?? '全部'
}

function StatusBadge({ state, compact = false }: { state: ProductionUiState; compact?: boolean }) {
  const styles = tone(state)
  return (
    <span className={`inline-flex items-center gap-1.5 border px-2 py-1 text-[10px] font-medium ${styles.border} ${styles.bg} ${styles.text}`}>
      <span aria-hidden className={`h-1.5 w-1.5 shrink-0 rounded-full ${styles.marker}`} />
      <span>{compact ? stateFilterLabel(state) : state === 'official' ? '正式版本' : state === 'ready' ? '待处理' : state === 'review' ? '待审核' : state === 'running' ? '生成中' : state === 'waiting' ? '等待上游' : state === 'blocked' ? '真正阻塞' : state === 'stale' ? '上游已更新' : '执行失败'}</span>
    </span>
  )
}

function Panel({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <section className={`border border-[#2A3437] bg-[#141A1D] ${className}`}>{children}</section>
}

function LoadingSurface() {
  return (
    <div data-testid="shot-studio-loading" className="space-y-4" aria-label="Shot Studio 正在加载">
      <div className="h-16 animate-pulse border border-[#2A3437] bg-[#141A1D]" />
      <div className="grid gap-4 xl:grid-cols-[240px_minmax(0,1fr)_300px]">
        {[240, 640, 300].map((width) => <div key={width} className="h-[420px] animate-pulse border border-[#2A3437] bg-[#141A1D]" style={{ minWidth: width }} />)}
      </div>
    </div>
  )
}

function EmptySurface() {
  return (
    <div data-testid="shot-studio-empty" className="flex min-h-[420px] items-center justify-center border border-dashed border-[#2A3437] bg-[#141A1D] p-8 text-center">
      <div>
        <div className="text-sm font-medium text-[#EDF1EF]">当前还没有可查看的镜头。</div>
        <p className="mt-2 max-w-md text-xs leading-6 text-[#A9B4B3]">完成上游镜头规划后，这里会出现生产状态。</p>
      </div>
    </div>
  )
}

function UnavailableSurface({ error, onRefresh }: { error?: string | null; onRefresh?: () => void }) {
  return (
    <div data-testid="shot-studio-unavailable" className="flex min-h-[420px] items-center justify-center border border-[#DF8E8C]/40 bg-[#DF8E8C]/5 p-8 text-center">
      <div>
        <div className="text-sm font-medium text-[#EDF1EF]">生产状态暂不可用</div>
        <p className="mt-2 max-w-md text-xs leading-6 text-[#A9B4B3]">无法安全展示正式生产状态。{error ? ` ${error}` : ''}</p>
        {onRefresh ? <button type="button" onClick={onRefresh} className="mt-4 inline-flex items-center gap-2 border border-[#8BC9D9]/40 px-3 py-2 text-xs text-[#8BC9D9] hover:bg-[#8BC9D9]/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#8BC9D9]"><RefreshCw className="h-3.5 w-3.5" />重新同步</button> : null}
      </div>
    </div>
  )
}

function ShotNavigator({
  shots,
  selectedId,
  onSelect,
}: {
  shots: ShotStudioViewModel[]
  selectedId: string | null
  onSelect: (shotId: string) => void
}) {
  const [episodeFilter, setEpisodeFilter] = useState<'all' | number>('all')
  const [sceneFilter, setSceneFilter] = useState('all')
  const [stateFilter, setStateFilter] = useState<StateFilter>('all')
  const [query, setQuery] = useState('')
  const [collapsedScenes, setCollapsedScenes] = useState<Set<string>>(new Set())

  const episodes = useMemo(() => Array.from(new Set(shots.map((shot) => shot.episode))).sort((a, b) => a - b), [shots])
  const scenes = useMemo(() => {
    const source = episodeFilter === 'all' ? shots : shots.filter((shot) => shot.episode === episodeFilter)
    return Array.from(new Map(source.map((shot) => [shot.scene.id, shot.scene.name])).entries()).sort((a, b) => a[0].localeCompare(b[0]))
  }, [episodeFilter, shots])
  const filtered = useMemo(() => {
    const needle = normalize(query)
    return shots.filter((shot) => {
      if (episodeFilter !== 'all' && shot.episode !== episodeFilter) return false
      if (sceneFilter !== 'all' && shot.scene.id !== sceneFilter) return false
      if (stateFilter !== 'all' && shot.state !== stateFilter) return false
      if (!needle) return true
      return [shot.shotId, shot.scene.name, shot.action].some((value) => normalize(value).includes(needle))
    })
  }, [episodeFilter, query, sceneFilter, shots, stateFilter])
  const grouped = useMemo(() => {
    const groups = new Map<string, { episode: number; sceneId: string; sceneName: string; shots: ShotStudioViewModel[] }>()
    filtered.forEach((shot) => {
      const key = `${shot.episode}:${shot.scene.id}`
      const current = groups.get(key) ?? { episode: shot.episode, sceneId: shot.scene.id, sceneName: shot.scene.name, shots: [] }
      current.shots.push(shot)
      groups.set(key, current)
    })
    return Array.from(groups.values())
  }, [filtered])

  useEffect(() => {
    if (filtered.length > 0 && !filtered.some((shot) => shot.shotId === selectedId)) onSelect(filtered[0].shotId)
  }, [filtered, onSelect, selectedId])

  return (
    <Panel className="flex min-h-[560px] min-w-0 flex-col overflow-hidden" aria-label="Shot Navigator">
      <div className="border-b border-[#2A3437] p-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <div className="text-xs uppercase tracking-[0.16em] text-[#728082]">Shot Navigator</div>
            <div className="mt-1 text-sm font-medium text-[#EDF1EF]">镜头导航</div>
          </div>
          <span className="text-[10px] text-[#728082]">{filtered.length} / {shots.length}</span>
        </div>
        <label className="mt-3 flex items-center gap-2 border border-[#2A3437] bg-[#1A2225] px-2.5 py-2 focus-within:border-[#8BC9D9]">
          <Search className="h-3.5 w-3.5 shrink-0 text-[#728082]" />
          <span className="sr-only">搜索镜头、场景或动作</span>
          <input aria-label="搜索镜头、场景或动作" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索镜头 / 场景 / 动作" className="min-w-0 flex-1 bg-transparent text-xs text-[#EDF1EF] outline-none placeholder:text-[#728082]" />
        </label>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <label className="sr-only" htmlFor="shot-studio-episode-filter">集数筛选</label>
          <select id="shot-studio-episode-filter" aria-label="集数筛选" value={episodeFilter} onChange={(event) => { setEpisodeFilter(event.target.value === 'all' ? 'all' : Number(event.target.value)); setSceneFilter('all') }} className="min-w-0 border border-[#2A3437] bg-[#1A2225] px-2 py-2 text-[11px] text-[#A9B4B3] outline-none focus:border-[#8BC9D9]">
            <option value="all">全部集数</option>
            {episodes.map((episode) => <option key={episode} value={episode}>第 {episode} 集</option>)}
          </select>
          <label className="sr-only" htmlFor="shot-studio-scene-filter">场景筛选</label>
          <select id="shot-studio-scene-filter" aria-label="场景筛选" value={sceneFilter} onChange={(event) => setSceneFilter(event.target.value)} className="min-w-0 border border-[#2A3437] bg-[#1A2225] px-2 py-2 text-[11px] text-[#A9B4B3] outline-none focus:border-[#8BC9D9]">
            <option value="all">全部场景</option>
            {scenes.map(([sceneId, sceneName]) => <option key={sceneId} value={sceneId}>{sceneName || sceneId}</option>)}
          </select>
        </div>
        <label className="sr-only" htmlFor="shot-studio-state-filter">状态筛选</label>
        <select id="shot-studio-state-filter" aria-label="状态筛选" value={stateFilter} onChange={(event) => setStateFilter(event.target.value as StateFilter)} className="mt-2 w-full border border-[#2A3437] bg-[#1A2225] px-2 py-2 text-[11px] text-[#A9B4B3] outline-none focus:border-[#8BC9D9]">
          {FILTERS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {grouped.length === 0 ? <div className="p-4 text-xs leading-6 text-[#728082]">没有符合筛选条件的镜头。</div> : grouped.map((group) => {
          const groupKey = `${group.episode}:${group.sceneId}`
          const collapsed = collapsedScenes.has(groupKey)
          return (
            <div key={groupKey} className="mb-2 last:mb-0">
              <button type="button" aria-expanded={!collapsed} onClick={() => setCollapsedScenes((current) => { const next = new Set(current); if (next.has(groupKey)) next.delete(groupKey); else next.add(groupKey); return next })} className="flex w-full items-center gap-1.5 px-2 py-2 text-left text-[10px] uppercase tracking-[0.12em] text-[#A9B4B3] hover:bg-[#202A2D] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#8BC9D9]">
                {collapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                <span className="truncate">E{String(group.episode).padStart(2, '0')} · {group.sceneName || group.sceneId}</span>
                <span className="ml-auto text-[#728082]">{group.shots.length}</span>
              </button>
              {!collapsed ? <div className="space-y-1">{group.shots.map((shot) => {
                const selected = shot.shotId === selectedId
                return <button key={shot.shotId} data-testid={`shot-studio-shot-${shot.shotId}`} type="button" aria-current={selected ? 'true' : undefined} onClick={() => onSelect(shot.shotId)} className={`group w-full border px-2.5 py-2.5 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#8BC9D9] ${selected ? 'border-[#D8A47C]/70 bg-[#202A2D]' : 'border-transparent hover:border-[#2A3437] hover:bg-[#1A2225]'}`}>
                  <div className="flex items-center gap-2"><span className="font-mono text-[11px] text-[#EDF1EF]">{shot.shotId}</span><StatusBadge state={shot.state} compact /></div>
                  <div className="mt-1 truncate text-[11px] leading-5 text-[#A9B4B3]">{shot.action || shot.scene.name}</div>
                </button>
              })}</div> : null}
            </div>
          )
        })}
      </div>
    </Panel>
  )
}

function generationStateLabel(state: ShotGenerationMutationSnapshot['state']) {
  if (state === 'confirming') return '等待费用确认'
  if (state === 'submitting') return '提交中'
  if (state === 'refreshing') return '同步中'
  if (state === 'running') return '系统处理中'
  if (state === 'waiting_candidate') return '等待候选'
  if (state === 'candidate_ready') return '候选已就绪'
  if (state === 'failed') return '生成失败'
  if (state === 'cancelled') return '已取消'
  return ''
}

function GenerationControls({ shot, lane, mutation, reviewBusy, onGenerate, onCancel }: { shot: ShotStudioViewModel; lane: MediaLane; mutation: ShotGenerationMutationSnapshot; reviewBusy?: boolean; onGenerate: (target: MediaLane) => void; onCancel: () => void }) {
  const selected = lane === 'VIDEO' ? shot.video : shot.image
  const expectedKind = lane === 'IMAGE' ? 'generate_image' : 'generate_video'
  const canGenerate = selected.primaryAction.kind === expectedKind && selected.primaryAction.lane === lane && selected.generationAllowed && Boolean(selected.professional.model.selected_profile_id) && !shot.stale.isStale && !reviewBusy
  const isCurrent = mutation.shotId === shot.shotId && mutation.target === lane
  const mutating = isCurrent && ['confirming', 'submitting', 'refreshing', 'running'].includes(mutation.state)
  const model = selected.professional.model.selected_profile_id
  return <div data-testid="shot-studio-generation-controls" className="border-t border-[#2A3437] bg-[#1A2225] px-4 py-3">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><div className="text-[10px] uppercase tracking-[0.16em] text-[#D8A47C]">Generation Action</div><div className="mt-1 text-xs text-[#A9B4B3]">{canGenerate ? `模型配置：${model || '未选择'}` : selected.state === 'review' ? '当前候选需要人工审核。' : selected.state === 'official' ? '当前 lane 已是正式版本。' : selected.detail}</div></div>
      <div className="flex flex-wrap items-center gap-2"><button type="button" data-testid={`shot-studio-generate-${lane.toLowerCase()}`} disabled={!canGenerate || mutating} onClick={() => onGenerate(lane)} className="border border-[#D8A47C]/70 bg-[#D8A47C]/15 px-3 py-2 text-xs font-medium text-[#F0C6A4] disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D8A47C]">{lane === 'IMAGE' ? '生成 IMAGE' : '生成 VIDEO'}</button>{mutating ? <button type="button" onClick={onCancel} className="border border-[#DF8E8C]/50 px-3 py-2 text-xs text-[#DF8E8C]">取消</button> : null}</div>
    </div>
    {isCurrent && mutation.state !== 'idle' ? <div className={`mt-2 text-[11px] ${mutation.state === 'failed' ? 'text-[#DF8E8C]' : mutation.state === 'candidate_ready' ? 'text-[#9FCBAB]' : 'text-[#8BC9D9]'}`} role={mutation.state === 'failed' ? 'alert' : 'status'}>{generationStateLabel(mutation.state)} · {mutation.message}</div> : null}
    {canGenerate ? <div className="mt-2 text-[10px] text-[#DBB36F]">该操作可能调用外部模型并产生费用。</div> : null}
  </div>
}

function MediaCanvas({ shot, lane, onLaneChange, mutation, reviewBusy, onGenerate, onCancel }: { shot: ShotStudioViewModel; lane: MediaLane; onLaneChange: (lane: MediaLane) => void; mutation: ShotGenerationMutationSnapshot; reviewBusy?: boolean; onGenerate: (target: MediaLane) => void; onCancel: () => void }) {
  const selectedLane = lane === 'VIDEO' ? shot.video : shot.image
  const preview = lanePreview(selectedLane)
  const isVideo = lane === 'VIDEO'
  return (
    <Panel className="min-w-0 overflow-hidden" aria-label="Media Canvas">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#2A3437] px-4 py-3">
        <div><div className="text-xs uppercase tracking-[0.16em] text-[#728082]">Media Canvas</div><div className="mt-1 text-sm font-medium text-[#EDF1EF]">{isVideo ? '视频检查' : '图片检查'}</div></div>
        <div className="flex items-center border border-[#2A3437] bg-[#1A2225] p-0.5" aria-label="媒体检查切换">
          {(['IMAGE', 'VIDEO'] as const).map((value) => <button key={value} type="button" aria-pressed={lane === value} onClick={() => onLaneChange(value)} className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] ${lane === value ? 'bg-[#D8A47C]/15 text-[#D8A47C]' : 'text-[#728082] hover:text-[#EDF1EF]'}`}>{value === 'IMAGE' ? <ImageIcon className="h-3.5 w-3.5" /> : <Film className="h-3.5 w-3.5" />}{value === 'IMAGE' ? '图片' : '视频'}</button>)}
        </div>
      </div>
      <div className="flex min-h-[330px] items-center justify-center bg-[#0E1214] p-4 md:min-h-[390px]">
        {preview ? (isVideo ? <video key={preview} controls className="max-h-[390px] max-w-full border border-[#2A3437] bg-black" src={preview}><track kind="captions" /></video> : <img key={preview} src={preview} alt={`${shot.shotId} ${lane === 'IMAGE' ? '图片' : '视频'}预览`} className="max-h-[390px] max-w-full border border-[#2A3437] object-contain" />) : <div className="max-w-sm text-center"><div className="mx-auto flex h-12 w-12 items-center justify-center border border-[#2A3437] bg-[#141A1D] text-[#728082]">{isVideo ? <Film className="h-5 w-5" /> : <ImageIcon className="h-5 w-5" />}</div><div className="mt-4 text-sm font-medium text-[#EDF1EF]">{laneEvidenceLabel(selectedLane)}</div><p className="mt-2 text-xs leading-6 text-[#A9B4B3]">{selectedLane.official.isCanonicalOfficial ? `正式${isVideo ? '视频' : '图片'}已建立，当前投影没有可预览 URL。` : selectedLane.candidate.reviewEligibility ? `这是${isVideo ? '视频' : '图片'}候选结果，不是正式版本。当前投影没有可预览 URL。` : selectedLane.detail}</p></div>}
      </div>
      <div className="grid gap-3 border-t border-[#2A3437] p-4 sm:grid-cols-3">
        <div><div className="text-[10px] uppercase tracking-[0.12em] text-[#728082]">State</div><div className="mt-1"><StatusBadge state={selectedLane.state} /></div></div>
        <div><div className="text-[10px] uppercase tracking-[0.12em] text-[#728082]">Evidence</div><div className="mt-2 truncate text-xs text-[#A9B4B3]">{laneEvidenceLabel(selectedLane)}</div></div>
        <div><div className="text-[10px] uppercase tracking-[0.12em] text-[#728082]">Prompt</div><div className="mt-2 text-xs text-[#A9B4B3]">v{selectedLane.prompt.version ?? '—'} · {selectedLane.prompt.current ? '当前' : '待更新'}</div></div>
      </div>
      <GenerationControls shot={shot} lane={lane} mutation={mutation} reviewBusy={reviewBusy} onGenerate={onGenerate} onCancel={onCancel} />
    </Panel>
  )
}

function reviewCandidateForLane(shot: ShotStudioViewModel, lane: MediaLane) {
  const selected = lane === 'VIDEO' ? shot.video : shot.image
  return selected.candidate.candidate ?? selected.professional.candidateItems[0] ?? null
}

function reviewStateLabel(state: ShotReviewMutationSnapshot['state']) {
  if (state === 'confirming') return '正在确认'
  if (state === 'validating') return '正在建立验证记录'
  if (state === 'promoting') return '正在建立正式版本'
  if (state === 'refreshing') return '正在同步正式状态'
  if (state === 'confirmed') return '已建立正式版本'
  if (state === 'failed') return '审核未完成'
  return ''
}

function ReviewEvidence({ label, preview, emptyLabel, mediaType = 'IMAGE' }: { label: string; preview: string | null; emptyLabel: string; mediaType?: MediaLane }) {
  return <div className="border border-[#2A3437] bg-[#0E1214] p-3"><div className="text-[10px] uppercase tracking-[0.12em] text-[#728082]">{label}</div>{preview ? mediaType === 'VIDEO' ? <video controls src={preview} aria-label={label} className="mt-2 max-h-36 w-full object-contain"><track kind="captions" /></video> : <img src={preview} alt={label} className="mt-2 max-h-36 w-full object-contain" /> : <div className="mt-2 flex min-h-20 items-center justify-center border border-dashed border-[#2A3437] text-center text-[11px] text-[#728082]">{emptyLabel}</div>}</div>
}

function ReviewDesk({ shot, lane, mode, mutation, generationBusy, onApprove }: { shot: ShotStudioViewModel; lane: MediaLane; mode: ProductionWorkspaceViewMode; mutation: ShotReviewMutationSnapshot; generationBusy?: boolean; onApprove: (identity: ShotReviewCandidateIdentity) => void }) {
  const selectedLane = lane === 'VIDEO' ? shot.video : shot.image
  const candidate = reviewCandidateForLane(shot, lane)
  const identity = candidate ? { shotId: shot.shotId, lane: selectedLane.target, candidateId: candidate.id, validationId: candidate.technical_validation.validation_id } satisfies ShotReviewCandidateIdentity : null
  const isCurrentReview = selectedLane.state === 'review' && selectedLane.candidate.reviewEligibility && Boolean(candidate)
  const isMutationForCurrent = Boolean(mutation.identity && identity && mutation.identity.shotId === identity.shotId && mutation.identity.lane === identity.lane && mutation.identity.candidateId === identity.candidateId)
  const visible = isCurrentReview || isMutationForCurrent
  if (!visible || !candidate) return null
  const official = selectedLane.official.isCanonicalOfficial ? selectedLane.official : null
  const confirmed = isMutationForCurrent && mutation.state === 'confirmed'
  const mutating = isMutationForCurrent && ['confirming', 'validating', 'promoting', 'refreshing'].includes(mutation.state)
  const approveEnabled = isCurrentReview && !generationBusy && !mutating && mutation.state !== 'confirmed' && !selectedLane.official.current && selectedLane.official.reasonCodes.length === 0 && !shot.stale.isStale
  const canonicalPreview = confirmed ? official?.preview ?? null : null
  const candidatePreview = candidate.preview_url ?? candidate.preview
  const displayedPreview = confirmed ? canonicalPreview : candidatePreview
  return <div data-testid="shot-studio-review-desk"><Panel className="mt-4 overflow-hidden" aria-label="Review Desk">
    <div className="border-b border-[#2A3437] px-4 py-3"><div className="text-xs uppercase tracking-[0.16em] text-[#C4B5E5]">Review Desk</div><div className="mt-1 text-sm font-medium text-[#EDF1EF]">{confirmed ? '正式状态确认' : '候选媒体审核'}</div><div className="mt-1 text-xs text-[#A9B4B3]">{shot.shotId} · {shot.scene.name} · {selectedLane.target}</div></div>
    <div className="grid gap-3 p-4 md:grid-cols-2">
      <ReviewEvidence label={confirmed ? 'Canonical Official · 已确认' : 'Candidate · 非正式版本'} preview={displayedPreview} mediaType={selectedLane.target} emptyLabel={confirmed ? '正式版本没有可预览 URL；保留真实证据占位。' : '候选没有可预览 URL；保留真实证据占位。'} />
      {official ? <ReviewEvidence label="Current Official" preview={official.preview} mediaType={selectedLane.target} emptyLabel="当前正式版本没有可预览 URL。" /> : <div className="border border-dashed border-[#2A3437] bg-[#0E1214] p-3"><div className="text-[10px] uppercase tracking-[0.12em] text-[#728082]">Current Official</div><div className="mt-2 text-[11px] text-[#728082]">当前 lane 尚未建立正式版本。</div></div>}
    </div>
    <div className="grid gap-2 border-t border-[#2A3437] px-4 py-3 text-xs text-[#A9B4B3] sm:grid-cols-2 lg:grid-cols-4"><div><span className="text-[#728082]">审核原因</span><div className="mt-1">{selectedLane.candidate.reviewReason || selectedLane.detail}</div></div><div><span className="text-[#728082]">验证状态</span><div className="mt-1">{candidate.technical_validation.status}</div></div><div><span className="text-[#728082]">版本 / 模型</span><div className="mt-1">v{selectedLane.prompt.version ?? '—'} · {candidate.model_profile_id || '—'}</div></div>{mode === 'professional' ? <div><span className="text-[#728082]">Candidate ID</span><div className="mt-1 break-all font-mono text-[10px]">{candidate.id}</div></div> : null}</div>
    <div className="border-t border-[#2A3437] bg-[#1A2225] px-4 py-3"><div className="flex flex-wrap items-center justify-between gap-3"><div><div className="text-[10px] uppercase tracking-[0.16em] text-[#8BC9D9]">Decision Bar</div><div className="mt-1 text-sm font-medium text-[#EDF1EF]">{confirmed ? '已建立正式版本' : mutating ? reviewStateLabel(mutation.state) : '确认当前候选媒体'}</div></div><div className="flex flex-wrap items-center gap-2"><button type="button" disabled={!approveEnabled} onClick={() => identity && onApprove(identity)} className="border border-[#8BC9D9]/60 bg-[#8BC9D9]/15 px-3 py-2 text-xs font-medium text-[#BDE8F0] disabled:cursor-not-allowed disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#8BC9D9]">{mutating ? `${reviewStateLabel(mutation.state)}…` : confirmed ? '已确认' : '批准并继续'}</button><button type="button" disabled className="border border-[#2A3437] px-3 py-2 text-xs text-[#728082] disabled:cursor-not-allowed">要求修改</button></div></div><div className="mt-2 text-[11px] text-[#728082]">{confirmed ? mutation.message : '要求修改：统一修改意见契约尚未接入。'} </div>{mutation.errorCode && isMutationForCurrent ? <div role="alert" className="mt-2 text-xs text-[#DF8E8C]">{mutation.message}</div> : null}{mutating && isMutationForCurrent ? <div role="status" aria-live="polite" className="mt-2 text-xs text-[#8BC9D9]">{mutation.message}</div> : null}</div>
  </Panel></div>
}

function LaneSummary({ label, lane }: { label: string; lane: ProductionMediaLaneViewModel }) {
  return <div className="border border-[#2A3437] bg-[#1A2225] p-3"><div className="flex items-center justify-between gap-2"><span className="text-xs font-medium text-[#EDF1EF]">{label}</span><StatusBadge state={lane.state} compact /></div><div className="mt-2 text-[11px] leading-5 text-[#A9B4B3]">{lane.detail}</div><div className="mt-3 grid grid-cols-2 gap-2 text-[10px] text-[#728082]"><span>Prompt v{lane.prompt.version ?? '—'}</span><span>{lane.generationMode ?? '模式未映射'}</span><span>候选 {lane.candidate.reviewableCount}/{lane.candidate.candidateCount}</span><span>{lane.execution.rawState ?? '无执行'}</span></div></div>
}

function ShotPipeline({ shot }: { shot: ShotStudioViewModel }) {
  const assetValue = shot.professional.assetReadiness.current ? '已绑定' : shot.professional.assetReadiness.state || '未映射'
  const officialValue = shot.image.official.isCanonicalOfficial && shot.video.official.isCanonicalOfficial ? '正式版本' : shot.image.official.isCanonicalOfficial || shot.video.official.isCanonicalOfficial ? '部分建立' : '未建立'
  return <Panel className="mt-4 overflow-hidden" aria-label="Shot Pipeline"><div className="border-b border-[#2A3437] px-4 py-3"><div className="text-xs uppercase tracking-[0.16em] text-[#728082]">Shot Pipeline</div><div className="mt-1 text-sm font-medium text-[#EDF1EF]">生产链路</div></div><div className="grid gap-px bg-[#2A3437] sm:grid-cols-4"><div className="bg-[#141A1D] p-3"><div className="text-[10px] text-[#728082]">素材</div><div className="mt-2 text-xs text-[#A9B4B3]">{assetValue}</div><div className="mt-1 text-[10px] text-[#728082]">上游数据</div></div><div className="bg-[#141A1D] p-3"><div className="text-[10px] text-[#728082]">图片</div><div className="mt-2"><StatusBadge state={shot.image.state} compact /></div></div><div className="bg-[#141A1D] p-3"><div className="text-[10px] text-[#728082]">视频</div><div className="mt-2"><StatusBadge state={shot.video.state} compact /></div></div><div className="bg-[#141A1D] p-3"><div className="text-[10px] text-[#728082]">正式</div><div className="mt-2 text-xs text-[#A9B4B3]">{officialValue}</div><div className="mt-1 text-[10px] text-[#728082]">authority evidence</div></div></div><div className="border-t border-[#2A3437] px-4 py-3 text-xs text-[#A9B4B3]">当前镜头动作：{shot.action || '未提供动作描述'} · Director / Keyframe rail 未映射，保持中性状态。</div></Panel>
}

function DetailsRows({ rows }: { rows: Array<[string, unknown]> }) {
  return <div className="space-y-2">{rows.map(([label, value]) => <div key={label} className="flex items-start justify-between gap-3 border-b border-[#2A3437]/70 pb-2 text-[11px] last:border-0"><span className="shrink-0 text-[#728082]">{label}</span><span className="min-w-0 break-words text-right text-[#A9B4B3]">{value == null || value === '' ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value)}</span></div>)}</div>
}

function ShotContext({ shot, mode, detailsOpen, onToggleDetails }: { shot: ShotStudioViewModel; mode: ProductionWorkspaceViewMode; detailsOpen: boolean; onToggleDetails: () => void }) {
  const showDetails = detailsOpen || mode === 'professional'
  return <Panel className="min-w-0 overflow-hidden" aria-label="Shot Context"><div className="flex items-start justify-between gap-3 border-b border-[#2A3437] p-4"><div><div className="text-xs uppercase tracking-[0.16em] text-[#728082]">Shot Context</div><div className="mt-1 text-base font-medium text-[#EDF1EF]">{shot.shotId} · {shot.scene.name}</div></div><button type="button" aria-expanded={showDetails} aria-label={showDetails ? '收起生产详情' : '展开生产详情'} onClick={onToggleDetails} className="border border-[#2A3437] p-2 text-[#A9B4B3] hover:border-[#8BC9D9] hover:text-[#8BC9D9] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#8BC9D9]"><PanelRight className="h-4 w-4" /></button></div><div className="space-y-4 p-4"><div><div className="text-[10px] uppercase tracking-[0.12em] text-[#728082]">Production state</div><div className="mt-2 flex flex-wrap items-center gap-2"><StatusBadge state={shot.state} /><span className="text-xs text-[#A9B4B3]">{shot.detail}</span></div></div><DetailsRows rows={[["Scene", shot.scene.name || shot.scene.id], ['Shot', shot.shotId], ['Duration', `${shot.duration}s`], ['Camera angle', shot.camera.angle], ['Camera movement', shot.camera.movement], ['Camera speed', shot.camera.speed], ['Action', shot.action], ['Next action', shot.primaryAction.label], ['Asset readiness', shot.professional.assetReadiness.current ? '当前绑定' : shot.professional.assetReadiness.state], ['IMAGE mode', shot.image.generationMode], ['VIDEO mode', shot.video.generationMode]]} /></div>{showDetails ? <div data-testid="shot-studio-professional-details" className="border-t border-[#2A3437] bg-[#1A2225] p-4"><div className="mb-3 flex items-center gap-2 text-xs font-medium text-[#D8A47C]"><Info className="h-3.5 w-3.5" />Production Details · 只读证据</div><div className="space-y-4"><div><div className="mb-2 text-[10px] uppercase tracking-[0.12em] text-[#728082]">Authority source</div><DetailsRows rows={[["source", shot.professional.authoritySource], ['backend next action', `${shot.professional.backendNextAction.key} · ${shot.professional.backendNextAction.label}`], ['raw blockers', shot.professional.rawBlockers.map((item) => item.code).join(', ')], ['asset readiness', shot.professional.assetReadiness], ['legacy', shot.professional.legacy]]} /></div><div><div className="mb-2 text-[10px] uppercase tracking-[0.12em] text-[#728082]">IMAGE evidence</div><DetailsRows rows={[["model", shot.image.professional.model.model_name], ['provider', shot.image.execution.provider], ['execution', shot.image.execution.rawState], ['request fingerprint', shot.image.execution.requestFingerprint], ['official version', shot.image.official.version?.id], ['authority', shot.image.official.authority?.id], ['pointer', shot.image.official.pointer?.id], ['reason codes', shot.image.reasonCodes.join(', ')]]} /></div><div><div className="mb-2 text-[10px] uppercase tracking-[0.12em] text-[#728082]">VIDEO evidence</div><DetailsRows rows={[["model", shot.video.professional.model.model_name], ['provider', shot.video.execution.provider], ['execution', shot.video.execution.rawState], ['request fingerprint', shot.video.execution.requestFingerprint], ['official version', shot.video.official.version?.id], ['authority', shot.video.official.authority?.id], ['pointer', shot.video.official.pointer?.id], ['reason codes', shot.video.reasonCodes.join(', ')]]} /></div></div></div> : null}</Panel>
}

function nextActionCategory(shot: ShotStudioViewModel) {
  if (shot.primaryAction.kind === 'generate_image' || shot.primaryAction.kind === 'generate_video') return '可执行生产操作'
  if (shot.primaryAction.kind === 'review_candidate' || shot.state === 'review') return '人工审核'
  if (shot.primaryAction.kind === 'wait' || shot.state === 'running' || shot.state === 'waiting') return '系统处理中'
  if (shot.primaryAction.kind === 'retry_generation') return '该操作尚未接入'
  return '状态与执行证据'
}

function NextAction({ shot }: { shot: ShotStudioViewModel }) {
  return <div data-testid="shot-studio-next-action" className="mt-4 border border-[#8BC9D9]/40 bg-[#8BC9D9]/5 p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><div className="text-[10px] uppercase tracking-[0.16em] text-[#8BC9D9]">Canonical next action</div><div className="mt-1 text-base font-medium text-[#EDF1EF]">下一步 · {shot.primaryAction.label}</div></div><div className="flex items-center gap-2 text-[10px] text-[#A9B4B3]"><SlidersHorizontal className="h-3.5 w-3.5" />{nextActionCategory(shot)}</div></div><div className="mt-2 text-xs leading-6 text-[#A9B4B3]">{shot.primaryAction.reason || shot.detail}</div>{shot.primaryAction.requiresProviderCall ? <div className="mt-3 inline-flex items-center gap-2 border border-[#DBB36F]/30 bg-[#DBB36F]/5 px-2 py-1.5 text-[10px] text-[#DBB36F]"><CircleHelp className="h-3.5 w-3.5" />生成按钮会先请求费用确认，并由 canonical execution 记录真实状态。</div> : null}</div>
}

export default function ProductWorkspaceShotStudioV3({ snapshot, state = snapshot ? 'ready' : 'loading', error, mode = 'standard', focusShotId = null, onSelectShot, onRefresh, onRefreshProductionWorkspaceV2 }: ProductWorkspaceShotStudioV3Props) {
  const viewModels = useMemo(() => toShotStudioViewModels(snapshot?.shots ?? []), [snapshot])
  const selectedByFocus = viewModels.find((shot) => shot.shotId === String(focusShotId ?? '')) ?? null
  const selected = selectedByFocus ?? viewModels[0] ?? null
  const [detailsOpen, setDetailsOpen] = useState(mode === 'professional')
  const [mediaLane, setMediaLane] = useState<MediaLane>(() => selected ? preferredMediaLane(selected) : 'IMAGE')
  const [mutation, setMutation] = useState<ShotReviewMutationSnapshot>({ state: 'idle', identity: null, message: '', errorCode: null })
  const [generationMutation, setGenerationMutation] = useState<ShotGenerationMutationSnapshot>({ state: 'idle', shotId: null, target: null, message: '', errorCode: null, status: null, response: null })
  const latestViewModels = useRef(viewModels)
  latestViewModels.current = viewModels
  const refreshCanonical = useRef(onRefreshProductionWorkspaceV2)
  refreshCanonical.current = onRefreshProductionWorkspaceV2
  const reviewController = useRef<ReturnType<typeof createShotStudioMediaReviewController> | null>(null)
  const generationController = useRef<ReturnType<typeof createShotStudioGenerationController> | null>(null)
  if (!reviewController.current) {
    reviewController.current = createShotStudioMediaReviewController({
      getViewModel: (shotId) => latestViewModels.current.find((item) => item.shotId === shotId) ?? null,
      validateCandidate: validateProductionMediaCandidate,
      promoteCandidate: (candidateId, validationId) => approveProductionMediaCandidate(candidateId, validationId),
      refreshCanonical: async () => { await refreshCanonical.current?.() },
      onState: setMutation,
    })
  }
  if (!generationController.current && snapshot) {
    generationController.current = createShotStudioGenerationController({
      bookId: snapshot?.book_id ?? 0,
      getViewModel: (shotId) => latestViewModels.current.find((item) => item.shotId === shotId) ?? null,
      refreshCanonical: async () => { await refreshCanonical.current?.() },
      confirmCost: async (target) => typeof window === 'undefined' ? true : window.confirm(`确认生成${target === 'IMAGE' ? '图片' : '视频'}？\n该操作可能调用外部模型并产生费用。`),
      isReviewMutationActive: () => reviewController.current?.isActive() ?? false,
      onState: setGenerationMutation,
    })
  }

  useEffect(() => setDetailsOpen(mode === 'professional'), [mode])
  useEffect(() => () => { generationController.current?.dispose() }, [])
  useEffect(() => setMediaLane(selected ? preferredMediaLane(selected) : 'IMAGE'), [selected?.shotId])
  useEffect(() => {
    if (selected && selected.shotId !== String(focusShotId ?? '')) onSelectShot(selected.shotId)
  }, [focusShotId, onSelectShot, selected])
  useEffect(() => {
    if (typeof window === 'undefined' || !selected) return
    const url = new URL(window.location.href)
    url.searchParams.set('section', 'storyboard')
    url.searchParams.set('episode', String(selected.episode))
    url.searchParams.set('shot', selected.shotId)
    window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`)
  }, [selected])

  if (state === 'loading') return <LoadingSurface />
  if (state === 'unavailable' || !snapshot) return <UnavailableSurface error={error} onRefresh={onRefresh} />
  if (snapshot.shots.length === 0) return <EmptySurface />

  return <div data-testid="shot-studio-v3" className="min-w-0 space-y-4 bg-[#0E1214] text-[#EDF1EF]" style={{ fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' }}>
    <Panel className="flex flex-wrap items-center justify-between gap-4 px-4 py-4"><div><div className="text-[10px] uppercase tracking-[0.2em] text-[#728082]">Shot Studio · V3 Canary</div><div className="mt-1 flex flex-wrap items-center gap-3"><h2 className="text-xl font-medium tracking-tight text-[#EDF1EF]">镜头工坊</h2>{selected ? <StatusBadge state={selected.state} /> : null}</div><div className="mt-2 text-xs text-[#A9B4B3]">Production Workspace V2 状态、canonical 执行与人工审核在此衔接</div></div><div className="flex items-center gap-2"><span className="border border-[#2A3437] px-2.5 py-1.5 text-[10px] text-[#728082]">{snapshot.shots.length} shots</span>{onRefresh ? <button type="button" onClick={onRefresh} aria-label="重新同步 Shot Studio" className="inline-flex items-center gap-2 border border-[#2A3437] px-3 py-2 text-xs text-[#A9B4B3] hover:border-[#8BC9D9] hover:text-[#8BC9D9] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#8BC9D9]"><RefreshCw className="h-3.5 w-3.5" />重新同步</button> : null}</div></Panel>
    {!selected ? <EmptySurface /> : <>
      <div className="grid min-w-0 gap-4 xl:grid-cols-[240px_minmax(0,1fr)_300px]">
        <ShotNavigator shots={viewModels} selectedId={selected.shotId} onSelect={onSelectShot} />
        <div className="min-w-0"><MediaCanvas shot={selected} lane={mediaLane} onLaneChange={setMediaLane} mutation={generationMutation} reviewBusy={reviewController.current?.isActive()} onGenerate={(target) => { void generationController.current?.start(selected.shotId, target) }} onCancel={() => { generationController.current?.cancel() }} /><ReviewDesk shot={selected} lane={mediaLane} mode={mode} mutation={mutation} generationBusy={generationController.current?.isActive()} onApprove={(identity) => { if (!generationController.current?.isActive()) void reviewController.current?.approve(identity) }} /><ShotPipeline shot={selected} /></div>
        <ShotContext shot={selected} mode={mode} detailsOpen={detailsOpen} onToggleDetails={() => setDetailsOpen((current) => !current)} />
      </div>
      <NextAction shot={selected} />
    </>}
  </div>
}
