import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactFlow, {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Panel,
  Position,
  ReactFlowProvider,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type EdgeChange,
  type EdgeProps,
  type Node,
  type NodeChange,
  type NodeProps,
  type OnSelectionChangeParams,
  type Viewport,
} from 'reactflow'
import 'reactflow/dist/style.css'
import ModelRegistryModal, { EditorField } from '../components/ModelRegistryModal'
import type { OutputsData } from './sceneComposerData'
import {
  addConnection,
  addNode,
  adoptVersion,
  autoLayout,
  deleteNode,
  deserializeDocument,
  duplicateNode,
  markDownstreamStale,
  setReferenceLink,
  serializeDocument,
  unadoptVersion,
  validateConnection,
  type CanvasDocument,
  type CreativeEdge,
  type CreativeNode,
  type CreativeNodeKind,
  type ReviewStatus,
  type VersionKind,
} from './sceneComposerModel'
import { createRealEpisodeDocument } from './sceneComposerRealDocument'
import {
  fetchModelRegistry,
  fetchModelRegistryDefaults,
  type ModelRegistryPayload,
} from './sceneComposerModelRegistry'
import {
  failMockGeneration,
  finishMockGeneration,
  startMockGeneration,
} from './sceneComposerMockService'
import {
  attachTaskIdToNode,
  completeGenerationTask,
  createPendingGenerationBranch,
  failGenerationTask,
  fetchCreativeTask,
  persistAdoptedVersion,
  pollCreativeTask,
  restartGenerationTask,
  syncCreativeTaskStatus,
  startReferenceImageTask,
  startCreativeTask,
  type CreativeTaskAsset,
} from './sceneComposerTaskService'
import {
  createResetDocument,
  pushHistoryState,
  redoHistoryState,
  undoHistoryState,
  type HistoryState,
} from './sceneComposerState'

const NODE_STYLE: Record<CreativeNodeKind, { accent: string; badge: string; card: string }> = {
  script: { accent: '#38bdf8', badge: 'text-cyan-200', card: 'from-cyan-500/10 to-cyan-500/0' },
  shot: { accent: '#f59e0b', badge: 'text-amber-200', card: 'from-amber-500/10 to-amber-500/0' },
  character: { accent: '#8b5cf6', badge: 'text-violet-200', card: 'from-violet-500/10 to-violet-500/0' },
  location: { accent: '#14b8a6', badge: 'text-teal-200', card: 'from-teal-500/10 to-teal-500/0' },
  prop: { accent: '#f97316', badge: 'text-orange-200', card: 'from-orange-500/10 to-orange-500/0' },
  image: { accent: '#eab308', badge: 'text-yellow-200', card: 'from-yellow-500/10 to-yellow-500/0' },
  video: { accent: '#22c55e', badge: 'text-emerald-200', card: 'from-emerald-500/10 to-emerald-500/0' },
  audio: { accent: '#ec4899', badge: 'text-pink-200', card: 'from-pink-500/10 to-pink-500/0' },
  sequence: { accent: '#ef4444', badge: 'text-rose-200', card: 'from-rose-500/10 to-rose-500/0' },
}

const ADDABLE_KINDS: CreativeNodeKind[] = ['shot', 'character', 'location', 'prop', 'image', 'video', 'audio', 'sequence']
const COLUMN_GROUPS: Array<{ key: string; label: string; left: string }> = [
  { key: 'text', label: '文本层', left: '8%' },
  { key: 'asset', label: '参考资产层', left: '24%' },
  { key: 'shot', label: '镜头节点', left: '29%' },
  { key: 'image', label: '图片版本', left: '53%' },
  { key: 'video', label: '视频版本', left: '73%' },
  { key: 'sequence', label: '成片序列', left: '88%' },
]

const POYO_ASYNC_PROVIDER = 'poyo-async'

function isVideoProfileReadyForRealGeneration(profile: ModelRegistryPayload['default_profiles']['video'] | null | undefined) {
  if (!profile) return false
  return profile.uses_mock || profile.provider === POYO_ASYNC_PROVIDER
}

type Notice = {
  tone: 'info' | 'success' | 'error'
  message: string
}

type EdgeVisibilityMode = 'all' | 'focus'
type LeftRailTab = 'outline' | 'assets' | 'add'
type SequenceEntry = {
  shotId: string
  shotNode: CreativeNode | null
  adoptedNode: CreativeNode | null
  status: 'adopted' | 'missing'
}
type ShotReviewState = {
  status: ReviewStatus
  note: string
  reviewedAt?: string
}
type EpisodeInspectionIssue = {
  shotId: string
  shotNode: CreativeNode
  title: string
  detail: string
}
type EpisodeInspectionReport = {
  totalShots: number
  referencedShots: number
  imageReadyShots: number
  videoReadyShots: number
  adoptedVideoShots: number
  sequenceShots: number
  failedTasks: number
  missingImageShots: EpisodeInspectionIssue[]
  missingVideoShots: EpisodeInspectionIssue[]
  unadoptedVideoShots: EpisodeInspectionIssue[]
  missingSequenceShots: EpisodeInspectionIssue[]
  riskShots: EpisodeInspectionIssue[]
  exportReady: boolean
}
type FailureTaskEntry = {
  nodeId: string
  kind: CreativeNodeKind
  title: string
  shotId?: string
  shotNodeId?: string
  sourceLabel: string
  modelLabel?: string
  errorMessage: string
  handled: boolean
  handledAt?: string
}
type ExportReadinessIssue = {
  key: string
  title: string
  detail: string
  shotNodeId?: string
}
type ProblemQueueEntry = {
  key: string
  shotId?: string
  shotNodeId?: string
  title: string
  detail: string
  type: 'review' | 'failure' | 'risk' | 'missing_video' | 'unadopted_video' | 'missing_sequence'
  severity: 'high' | 'medium' | 'low'
  statusLabel: string
}
type ExportReadinessReport = {
  canExport: boolean
  summary: string
  sequenceCoverage: string
  issues: ExportReadinessIssue[]
}
type DeliveryChecklistShot = {
  shotId: string
  shotTitle: string
  adoptedVideoTitle: string
  reviewStatus: ReviewStatus
  reviewNote: string
  durationSeconds?: number
  referenceCount: number
  hasFailureHistory: boolean
  riskHint?: string
}
type DeliveryChecklistReport = {
  projectTitle: string
  episodeTitle: string
  shotCount: number
  adoptedVideoCount: number
  totalDurationSeconds: number
  canDeliver: boolean
  blockedReasons: string[]
  riskSummary: string[]
  failureSummary: string[]
  latestDeliveryLabel?: string
  latestDeliveryStatus?: 'delivered' | 'stale'
  shots: DeliveryChecklistShot[]
}
type NextStepGuide = {
  title: string
  detail: string
  tone?: 'info' | 'warn' | 'success'
}
type ActionAvailability = {
  enabled: boolean
  reason?: string
}
type SaveState = 'saving' | 'saved' | 'error'

function statusLabel(status: CreativeNode['data']['status']) {
  switch (status) {
    case 'idle':
      return '待处理'
    case 'running':
      return '生成中'
    case 'done':
      return '已完成'
    case 'error':
      return '失败'
    case 'stale':
      return '已过期'
  }
}

function WorkflowEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, markerEnd, style, data, label }: EdgeProps<CreativeEdge['data']>) {
  const centerX = (sourceX + targetX) / 2
  const centerY = (sourceY + targetY) / 2
  const controlOffset = data?.kind === 'sequence' ? 70 : 35
  const path = `M ${sourceX},${sourceY} C ${sourceX + controlOffset},${sourceY} ${targetX - controlOffset},${targetY} ${targetX},${targetY}`

  return (
    <>
      <path
        id={id}
        d={path}
        fill="none"
        markerEnd={markerEnd}
        style={style}
        className="react-flow__edge-path"
      />
      {label ? (
        <foreignObject x={centerX - 42} y={centerY - 14} width={84} height={28}>
          <div className="flex h-7 items-center justify-center rounded-full border border-slate-700/80 bg-slate-950/90 px-2 text-[10px] font-medium text-slate-200 shadow-[0_6px_20px_rgba(2,6,23,0.35)]">
            {String(label)}
          </div>
        </foreignObject>
      ) : null}
    </>
  )
}

function CreativeNodeCard({ data, selected }: NodeProps<CreativeNode['data']>) {
  const style = NODE_STYLE[data.kind]
  const sourceLabel =
    data.metadata?.source === 'mock'
      ? 'Mock'
      : data.metadata?.source === 'real'
        ? '真实'
        : null
  const statusTone = data.status === 'error'
    ? 'bg-red-500/15 text-red-300 border-red-500/30'
    : data.status === 'running'
      ? 'bg-amber-500/15 text-amber-200 border-amber-500/30'
      : data.status === 'stale'
        ? 'bg-slate-500/15 text-slate-300 border-slate-500/30'
        : data.status === 'done'
          ? 'bg-emerald-500/15 text-emerald-200 border-emerald-500/30'
          : 'bg-slate-700/30 text-slate-300 border-slate-600/30'
  const canReceive = !['script', 'character', 'location', 'prop'].includes(data.kind)
  const canSend = data.kind !== 'sequence'

  return (
    <div
      className={`min-w-[246px] max-w-[270px] rounded-2xl border bg-gradient-to-br ${style.card} p-3 shadow-[0_18px_60px_rgba(2,6,23,0.35)] backdrop-blur transition ${
        selected ? 'border-slate-100/40 ring-2 ring-sky-300/50' : data.ui?.emphasized ? 'border-sky-400/50 ring-1 ring-sky-400/30' : 'border-slate-800/90'
      } ${data.ui?.dimmed ? 'opacity-25' : 'opacity-100'}`}
      title={[data.ui?.referenceSummary, data.ui?.outputSummary].filter(Boolean).join('\n')}
    >
      {canReceive && (
        <Handle
          type="target"
          position={Position.Left}
          className="!h-3 !w-3 !border-2 !border-slate-950 !bg-slate-200"
        />
      )}
      {canSend && (
        <Handle
          type="source"
          position={Position.Right}
          className="!h-3 !w-3 !border-2 !border-slate-950"
          style={{ background: style.accent }}
        />
      )}
      <div className="mb-3 flex items-start gap-3">
        <div className="mt-0.5 h-3 w-3 rounded-full" style={{ backgroundColor: style.accent }} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className={`rounded-full border border-white/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.24em] ${style.badge}`}>
              {kindText(data.kind)}
            </span>
            {sourceLabel ? (
              <span className="rounded-full border border-slate-600/80 bg-slate-900/70 px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] text-slate-300">
                {sourceLabel}
              </span>
            ) : null}
            <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] ${statusTone}`}>
              {nodeStatusLabel(data)}
            </span>
          </div>
          <div className="mt-2 truncate text-sm font-semibold text-slate-100">{data.title}</div>
          <div className="mt-1 line-clamp-2 text-xs leading-5 text-slate-400">{data.summary}</div>
        </div>
      </div>

      {data.previewUrl ? (
        <img
          src={data.previewUrl}
          alt={data.title}
          className="mb-3 h-28 w-full rounded-xl border border-slate-800 object-cover"
        />
      ) : (
        <div className="mb-3 flex h-24 items-center justify-center rounded-xl border border-dashed border-slate-700 bg-slate-950/70 text-[11px] uppercase tracking-[0.2em] text-slate-500">
          等待补充内容
        </div>
      )}

      <div className="flex items-center justify-between text-[11px] text-slate-500">
        <span>
          {data.assetScope === 'character'
            ? '人物定妆'
            : data.assetScope === 'location'
              ? '场景资产'
              : data.assetScope === 'prop'
                ? '道具资产'
                : data.shotId
                  ? `镜头 ${data.shotId}`
                  : '共享资产'}
        </span>
        <span>{data.versionInfo?.label ?? '草稿'}</span>
      </div>
      {data.kind === 'shot' && data.ui?.production && (
        <div className="mt-2 grid grid-cols-2 gap-1 border-t border-slate-800/80 pt-2 text-[10px] leading-4 text-slate-400">
          <div>参考图：{data.ui.production.referenceState}</div>
          <div>分镜图：{data.ui.production.imageState}</div>
          <div>视频：{data.ui.production.videoState}</div>
          <div>序列：{data.ui.production.sequenceState}</div>
        </div>
      )}
      {(data.ui?.referenceSummary || data.ui?.outputSummary) && (
        <div className="mt-2 space-y-1 border-t border-slate-800/80 pt-2 text-[10px] leading-4 text-slate-500">
          {data.ui?.referenceSummary && <div>{data.ui.referenceSummary}</div>}
          {data.ui?.outputSummary && <div>{data.ui.outputSummary}</div>}
        </div>
      )}
    </div>
  )
}

const nodeTypes = {
  creative: CreativeNodeCard,
}

const edgeTypes = {
  workflow: WorkflowEdge,
}

export default function SceneComposer({
  data,
  onBack,
  onOpenPreparation,
  projectId,
  projectTitle,
  episode = 1,
  availableEpisodes = [],
  onEpisodeChange,
  storageScope = 'mock',
}: {
  data: OutputsData
  onBack?: () => void
  onOpenPreparation?: () => void
  projectId?: number
  projectTitle?: string
  episode?: number
  availableEpisodes?: number[]
  onEpisodeChange?: (episode: number) => void
  storageScope?: string
}) {
  return (
    <ReactFlowProvider>
      <ComposerCanvas
        data={data}
        onBack={onBack}
        onOpenPreparation={onOpenPreparation}
        projectId={projectId}
        projectTitle={projectTitle}
        episode={episode}
        availableEpisodes={availableEpisodes}
        onEpisodeChange={onEpisodeChange}
        storageScope={storageScope}
      />
    </ReactFlowProvider>
  )
}

function ComposerCanvas({
  data,
  onBack,
  onOpenPreparation,
  projectId,
  projectTitle,
  episode,
  availableEpisodes,
  onEpisodeChange,
  storageScope,
}: {
  data: OutputsData
  onBack?: () => void
  onOpenPreparation?: () => void
  projectId?: number
  projectTitle?: string
  episode: number
  availableEpisodes: number[]
  onEpisodeChange?: (episode: number) => void
  storageScope: string
}) {
  const storageKey = getSceneComposerStorageKey(storageScope)
  const [document, setDocument] = useState<CanvasDocument>(() =>
    sanitizeDocument(loadInitialDocument(data, storageKey, { episode, projectTitle })),
  )
  const [history, setHistory] = useState<HistoryState>({ past: [], future: [] })
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [edgeVisibilityMode, setEdgeVisibilityMode] = useState<EdgeVisibilityMode>('all')
  const [notice, setNotice] = useState<Notice | null>({
    tone: 'info',
    message: projectId
      ? '当前项目已载入真实内容。默认展示镜头生产主线，可按需展开参考资产层查看依赖关系。'
      : '当前仅使用 Mock 数据演示。每次生成都会新增一个分支，不会覆盖旧版本。',
  })
  const [activeTab, setActiveTab] = useState<LeftRailTab>('outline')
  const [modelDefaults, setModelDefaults] = useState<ModelRegistryPayload['default_profiles']>({})
  const [modelRegistryState, setModelRegistryState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [modelRegistryOpen, setModelRegistryOpen] = useState(false)
  const [modelRegistryData, setModelRegistryData] = useState<ModelRegistryPayload | null>(null)
  const [modelRegistryError, setModelRegistryError] = useState<string | null>(null)
  const [savePulse, setSavePulse] = useState(false)
  const [saveState, setSaveState] = useState<SaveState>('saved')
  const [reactFlowInstance, setReactFlowInstance] = useState<any>(null)
  const [leftRailCollapsed, setLeftRailCollapsed] = useState(false)
  const [rightPanelCollapsed, setRightPanelCollapsed] = useState(false)
  const [referenceLayerVisible, setReferenceLayerVisible] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [inspectionOpen, setInspectionOpen] = useState(false)
  const [failureCenterOpen, setFailureCenterOpen] = useState(false)
  const [exportCheckOpen, setExportCheckOpen] = useState(false)
  const [problemQueueOpen, setProblemQueueOpen] = useState(false)
  const runningTimers = useRef<number[]>([])
  const activeTaskPolls = useRef(new Set<string>())

  const refreshModelDefaults = useCallback(async () => {
    setModelRegistryState('loading')
    try {
      const payload = await fetchModelRegistryDefaults()
      setModelDefaults(payload.default_profiles ?? {})
      setModelRegistryState('idle')
      return payload
    } catch (error) {
      setModelDefaults({})
      setModelRegistryState('error')
      throw error
    }
  }, [])

  useEffect(() => {
    void refreshModelDefaults().catch(() => undefined)
  }, [refreshModelDefaults])

  const selectedImageProfile = modelDefaults.image ?? null
  const selectedVideoProfile = modelDefaults.video ?? null
  const videoProfileBlockedReason = useMemo(() => {
    if (!selectedVideoProfile) {
      return '当前还没有默认视频模型配置，请先到模型管理中设置一个视频配置。'
    }
    if (!isVideoProfileReadyForRealGeneration(selectedVideoProfile)) {
      return `当前默认视频模型为 ${selectedVideoProfile.name}（${selectedVideoProfile.provider}），但工作台目前只支持 Mock 视频或 PoYo 异步视频，请先切换默认模型。`
    }
    return null
  }, [selectedVideoProfile])

  const handleOpenModelRegistry = useCallback(() => {
    setModelRegistryOpen(true)
    setModelRegistryError(null)
    fetchModelRegistry()
      .then((payload) => setModelRegistryData(payload))
      .catch((error) => setModelRegistryError(error instanceof Error ? error.message : '加载模型配置失败'))
  }, [])

  const handleModelRegistryUpdated = useCallback((payload: ModelRegistryPayload) => {
    setModelRegistryData(payload)
    setModelDefaults(payload.default_profiles ?? {})
    setModelRegistryState('idle')
  }, [])

  const activeModelHint = useMemo(() => {
    const imageLabel = selectedImageProfile
      ? `${selectedImageProfile.name} · ${selectedImageProfile.provider}${selectedImageProfile.uses_mock ? '（Mock）' : '（真实计费）'}`
      : '未设置'
    const videoLabel = selectedVideoProfile
      ? `${selectedVideoProfile.name} · ${selectedVideoProfile.provider}${selectedVideoProfile.uses_mock ? '（Mock）' : '（真实计费）'}`
      : '未设置'
    return `图片模型：${imageLabel}；视频模型：${videoLabel}`
  }, [selectedImageProfile, selectedVideoProfile])

  const selectedNode = useMemo(
    () => document.nodes.find((node) => node.id === selectedNodeId) ?? null,
    [document.nodes, selectedNodeId],
  )
  const shotNodes = useMemo(
    () => document.nodes.filter((node) => node.data.kind === 'shot'),
    [document.nodes],
  )
  const assetNodes = useMemo(
    () => document.nodes.filter((node) => ['character', 'location', 'prop'].includes(node.data.kind)),
    [document.nodes],
  )
  const sequenceNode = useMemo(
    () => document.nodes.find((node) => node.data.kind === 'sequence') ?? null,
    [document.nodes],
  )
  const sequenceEntries = useMemo(
    () => buildSequenceEntries(document, shotNodes),
    [document, shotNodes],
  )
  const failedNodes = useMemo(
    () => document.nodes.filter((node) => node.data.status === 'error'),
    [document.nodes],
  )
  const failureTaskEntries = useMemo(
    () => buildFailureTaskEntries(document),
    [document],
  )
  const activeFailureTaskEntries = useMemo(
    () => failureTaskEntries.filter((entry) => !entry.handled),
    [failureTaskEntries],
  )
  const inspectionReport = useMemo(
    () => buildEpisodeInspectionReport(document, shotNodes),
    [document, shotNodes],
  )
  const exportReadinessReport = useMemo(
    () => buildExportReadinessReport({
      document,
      shotNodes,
      inspectionReport,
      failureTaskEntries: activeFailureTaskEntries,
      sequenceEntries,
      saveState,
    }),
    [activeFailureTaskEntries, document, inspectionReport, saveState, sequenceEntries, shotNodes],
  )
  const problemQueueEntries = useMemo(
    () => buildProblemQueueEntries(document, shotNodes, inspectionReport, activeFailureTaskEntries),
    [document, shotNodes, inspectionReport, activeFailureTaskEntries],
  )
  const deliveryChecklist = useMemo(
    () => buildDeliveryChecklistReport({
      document,
      shotNodes,
      sequenceEntries,
      failureTaskEntries: activeFailureTaskEntries,
      inspectionReport,
      exportReadinessReport,
      failedNodes,
    }),
    [activeFailureTaskEntries, document, exportReadinessReport, failedNodes, inspectionReport, sequenceEntries, shotNodes],
  )
  const latestDeliveryRecord = useMemo(
    () => getLatestDeliveryRecord(document),
    [document],
  )
  const productionSummary = useMemo(() => {
    const totalShots = shotNodes.length
    const referencedShots = shotNodes.filter((node) => getShotProductionState(document, node).referenceCount > 0).length
    const imageReadyShots = shotNodes.filter((node) => document.nodes.some((item) => item.data.kind === 'image' && item.data.shotId === node.data.shotId && item.data.imageRole !== 'reference')).length
    const videoReadyShots = shotNodes.filter((node) => document.nodes.some((item) => item.data.kind === 'video' && item.data.shotId === node.data.shotId)).length
    const sequenceShots = Object.keys(document.adoptedVersions.video ?? {}).length
    const reviewedApprovedShots = shotNodes.filter((node) => getShotReviewState(document, node).status === 'approved').length
    return {
      totalShots,
      referencedShots,
      imageReadyShots,
      videoReadyShots,
      sequenceShots,
      reviewedApprovedShots,
      failedTasks: failedNodes.length,
      missingSequenceShots: Math.max(totalShots - sequenceShots, 0),
    }
  }, [document, failedNodes.length, shotNodes])

  useEffect(() => {
    if (!isDocumentCompatible(document, { episode, projectTitle })) {
      return
    }
    setSaveState('saving')
    try {
      localStorage.setItem(storageKey, serializeDocument(document))
      setSaveState('saved')
      setSavePulse(true)
      const timer = window.setTimeout(() => setSavePulse(false), 900)
      return () => window.clearTimeout(timer)
    } catch {
      setSaveState('error')
      setSavePulse(false)
    }
  }, [document, storageKey, episode, projectTitle])

  useEffect(() => {
    setDocument(sanitizeDocument(loadInitialDocument(data, storageKey, { episode, projectTitle })))
    setHistory({ past: [], future: [] })
    setSelectedNodeId(null)
    setHoveredNodeId(null)
  }, [data, episode, projectTitle, storageKey])

  useEffect(() => () => {
    runningTimers.current.forEach((timerId) => window.clearTimeout(timerId))
  }, [])

  useEffect(() => {
    const raw = localStorage.getItem(UI_STATE_STORAGE_KEY)
    if (!raw) return
    try {
      const parsed = JSON.parse(raw) as { leftRailCollapsed?: boolean; rightPanelCollapsed?: boolean }
      setLeftRailCollapsed(Boolean(parsed.leftRailCollapsed))
      setRightPanelCollapsed(Boolean(parsed.rightPanelCollapsed))
    } catch {
      // ignore invalid local UI state
    }
  }, [])

  useEffect(() => {
    localStorage.setItem(UI_STATE_STORAGE_KEY, JSON.stringify({ leftRailCollapsed, rightPanelCollapsed }))
  }, [leftRailCollapsed, rightPanelCollapsed])

  useEffect(() => {
    if (activeTab === 'assets') {
      setReferenceLayerVisible(true)
    }
  }, [activeTab])

  useEffect(() => {
    if (selectedNode?.data.kind && ['character', 'location', 'prop'].includes(selectedNode.data.kind)) {
      setReferenceLayerVisible(true)
    }
  }, [selectedNode])

  const commitDocument = useCallback((updater: (current: CanvasDocument) => CanvasDocument) => {
    setDocument((current) => {
      const next = sanitizeDocument(updater(current))
      if (next === current) {
        return current
      }
      setHistory((historyState) => pushHistoryState(historyState, current))
      return {
        ...next,
        lastSavedAt: new Date().toISOString(),
      }
    })
  }, [])

  const watchCreativeTask = useCallback((taskId: string, pendingNodeId: string) => {
    if (activeTaskPolls.current.has(taskId)) {
      return
    }
    activeTaskPolls.current.add(taskId)

    pollCreativeTask(fetchCreativeTask, taskId, {
      intervalMs: 1200,
      maxAttempts: 60,
      onUpdate: (status) => {
        commitDocument((current) => syncCreativeTaskStatus(current, pendingNodeId, status))
      },
    })
      .then((status) => {
        if (status.status === 'done' && status.asset) {
          const completedAsset: CreativeTaskAsset = {
            ...(status.asset as CreativeTaskAsset),
            metadata: {
              ...((status.asset as CreativeTaskAsset).metadata ?? {}),
              provider: status.provider ?? (status.asset as CreativeTaskAsset).metadata?.provider,
              modelProfileId: status.model_profile_id ?? (status.asset as CreativeTaskAsset).metadata?.modelProfileId,
              usesMock: status.uses_mock ?? (status.asset as CreativeTaskAsset).metadata?.usesMock,
              externalTaskId: status.external_task_id ?? '',
              externalStatus: status.external_status ?? '',
              pollAttempts: status.poll_attempts ?? 0,
              providerResponse: status.provider_response ? JSON.stringify(status.provider_response, null, 2) : undefined,
            },
          }
          commitDocument((current) => markDeliveryRecordsStale(autoLayout(completeGenerationTask(current, pendingNodeId, completedAsset))))
          setNotice({
            tone: 'success',
            message: `新的${kindText(status.target_kind as CreativeNodeKind)}真实分支已生成，并默认设为当前镜头的采用版本。`,
          })
          return
        }

        const errorMessage = status.error || '任务未完成，请稍后重试。'
        commitDocument((current) => markDeliveryRecordsStale(failGenerationTask(current, pendingNodeId, status.target_kind, errorMessage, {
          provider: status.provider,
          modelProfileId: status.model_profile_id,
          usesMock: status.uses_mock,
          externalTaskId: status.external_task_id,
          externalStatus: status.external_status,
          pollAttempts: status.poll_attempts,
          providerResponse: status.provider_response ?? null,
        })))
        setNotice({ tone: 'error', message: errorMessage })
      })
      .catch((error) => {
        const message = error instanceof Error ? error.message : '任务轮询失败。'
        const targetKind = document.nodes.find((node) => node.id === pendingNodeId)?.data.kind
        commitDocument((current) =>
          markDeliveryRecordsStale(failGenerationTask(
            current,
            pendingNodeId,
            targetKind === 'image' || targetKind === 'video' || targetKind === 'audio' ? targetKind : 'image',
            message,
          )),
        )
        setNotice({ tone: 'error', message })
      })
      .finally(() => {
        activeTaskPolls.current.delete(taskId)
      })
  }, [commitDocument, document.nodes])

  useEffect(() => {
    document.nodes.forEach((node) => {
      const taskId = typeof node.data.metadata?.taskId === 'string' ? node.data.metadata.taskId : undefined
      if (node.data.status === 'running' && taskId) {
        watchCreativeTask(taskId, node.id)
      }
    })
  }, [document.nodes, watchCreativeTask])

  const focusNode = useCallback((nodeId: string, options?: { center?: boolean }) => {
    if (!document.tutorialDismissed) {
      setDocument((current) => ({ ...current, tutorialDismissed: true }))
    }
    setSelectedNodeId(nodeId)

    const node = document.nodes.find((item) => item.id === nodeId)
    if (!node) {
      return
    }

    if (node.data.kind === 'shot') {
      setActiveTab('outline')
    } else if (['character', 'location', 'prop'].includes(node.data.kind)) {
      setActiveTab('assets')
    }

    if (options?.center === false || !reactFlowInstance?.setCenter) {
      return
    }

    const viewport = reactFlowInstance.getViewport?.()
    reactFlowInstance.setCenter(node.position.x + 130, node.position.y + 90, {
      duration: 280,
      zoom: Math.max(viewport?.zoom ?? document.viewport.zoom ?? 0.72, 0.72),
    })
  }, [document.nodes, document.tutorialDismissed, document.viewport.zoom, reactFlowInstance])

  const relatedEdgeIds = useMemo(
    () => selectedNodeId ? collectRelatedEdgeIds(document, selectedNodeId) : new Set<string>(),
    [document, selectedNodeId],
  )

  const displayNodes = useMemo(
    () => document.nodes
      .filter((node) => referenceLayerVisible || !isReferenceLayerNode(node))
      .map((node) => {
      const production = node.data.kind === 'shot'
        ? getShotProductionState(document, node)
        : undefined
      const inputKinds = document.edges
        .filter((edge) => edge.target === node.id)
        .map((edge) => document.nodes.find((item) => item.id === edge.source)?.data.title)
        .filter(Boolean) as string[]
      const outputKinds = document.edges
        .filter((edge) => edge.source === node.id)
        .map((edge) => document.nodes.find((item) => item.id === edge.target)?.data.title)
        .filter(Boolean) as string[]

      return {
        ...node,
        selected: node.id === selectedNodeId,
        data: {
          ...node.data,
          ui: {
            dimmed: false,
            emphasized: false,
            referenceSummary: inputKinds.length > 0 ? `引用：${inputKinds.slice(0, 2).join('、')}${inputKinds.length > 2 ? '…' : ''}` : undefined,
            outputSummary: outputKinds.length > 0 ? `将生成：${outputKinds.slice(0, 2).join('、')}${outputKinds.length > 2 ? '…' : ''}` : undefined,
            production,
          },
        },
      }
    }),
    [document, selectedNodeId, referenceLayerVisible],
  )

  const displayShotNodes = useMemo(
    () => displayNodes.filter((node) => node.data.kind === 'shot'),
    [displayNodes],
  )

  const panelAssetNodes = useMemo(
    () => [
      ...assetNodes,
      ...document.nodes.filter((node) => node.data.imageRole === 'reference'),
    ],
    [assetNodes, document.nodes],
  )

  const displayEdges = useMemo(() => {
    const activeShotId = (selectedNode?.data.kind === 'shot' ? selectedNode.id : hoveredNodeId && document.nodes.find((node) => node.id === hoveredNodeId)?.data.kind === 'shot' ? hoveredNodeId : null)
    return document.edges
      .filter((edge) => {
        if (!referenceLayerVisible && edge.data?.kind === 'reference') {
          const sourceNode = document.nodes.find((node) => node.id === edge.source)
          if (sourceNode && isReferenceLayerNode(sourceNode)) {
            return false
          }
        }
        if (edgeVisibilityMode === 'all') {
          return true
        }
        if (edge.data?.kind !== 'reference') {
          return true
        }
        return activeShotId ? edge.target === activeShotId : false
      })
      .map((edge) => {
        const highlighted = selectedNodeId ? relatedEdgeIds.has(edge.id) : false
        const dimmed = selectedNodeId ? !relatedEdgeIds.has(edge.id) : false
        return {
          ...edge,
          type: 'workflow',
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 18,
            height: 18,
            color: edge.data?.kind === 'reference' ? '#64748b' : edge.data?.kind === 'sequence' ? '#22c55e' : '#f59e0b',
          },
          style: {
            ...(edge.style ?? {}),
            opacity: dimmed ? 0.12 : highlighted ? 1 : 0.8,
            strokeWidth: edge.data?.kind === 'sequence' ? 2.4 : highlighted ? 2.2 : (edge.style?.strokeWidth as number | undefined) ?? 1.8,
            filter: highlighted ? 'drop-shadow(0 0 8px rgba(56,189,248,0.45))' : undefined,
          },
        } as CreativeEdge
      })
  }, [document, edgeVisibilityMode, selectedNodeId, relatedEdgeIds, selectedNode, hoveredNodeId, referenceLayerVisible])

  const onNodesChange = useCallback((changes: NodeChange[]) => {
    commitDocument((current) => ({
      ...current,
      nodes: applyNodeChanges(changes, current.nodes) as CreativeNode[],
    }))
  }, [commitDocument])

  const onEdgesChange = useCallback((changes: EdgeChange[]) => {
    commitDocument((current) => ({
      ...current,
      edges: applyEdgeChanges(changes, current.edges) as CreativeEdge[],
    }))
  }, [commitDocument])

  const onConnect = useCallback((connection: Connection) => {
    if (!connection.source || !connection.target) {
      return
    }
    try {
      commitDocument((current) => addConnection(current, connection.source!, connection.target!))
      setNotice({ tone: 'success', message: '连线已添加，后续依赖关系会按新引用重新判断。' })
    } catch (error) {
      setNotice({ tone: 'error', message: error instanceof Error ? error.message : '连线创建失败。' })
    }
  }, [commitDocument])

  const isValidConnection = useCallback((connection: Connection) => {
    const sourceNode = document.nodes.find((node) => node.id === connection.source)
    const targetNode = document.nodes.find((node) => node.id === connection.target)
    return validateConnection(sourceNode?.data.kind, targetNode?.data.kind).ok
  }, [document.nodes])

  const handleSelectionChange = useCallback((selection: OnSelectionChangeParams) => {
    const selected = selection.nodes[0]
    if (!selected) {
      setSelectedNodeId(null)
      return
    }
    focusNode(selected.id, { center: false })
  }, [focusNode])

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    focusNode(node.id)
  }, [focusNode])

  const handlePaneDoubleClick = useCallback((event: React.MouseEvent) => {
    if (!reactFlowInstance) {
      return
    }
    const position = reactFlowInstance.screenToFlowPosition({ x: event.clientX, y: event.clientY })
    commitDocument((current) => addNode(current, 'shot', position))
    setNotice({ tone: 'info', message: '已在当前位置新增镜头草稿节点。' })
  }, [commitDocument, reactFlowInstance])

  const handleAddNode = useCallback((kind: CreativeNodeKind) => {
    const position = reactFlowInstance
      ? reactFlowInstance.screenToFlowPosition({ x: 780, y: 360 })
      : { x: 180, y: 180 }
    commitDocument((current) => markDeliveryRecordsStale(addNode(current, kind, position)))
    setNotice({ tone: 'info', message: `已新增节点，可在右侧面板补充内容。` })
  }, [commitDocument, reactFlowInstance])

  const handleReset = useCallback(() => {
    const next = createResetDocument(data, {
      episode,
      projectTitle,
      episodeTitle: `第 ${episode} 集创作沙盒`,
    })
    localStorage.setItem(storageKey, serializeDocument(next))
    setDocument(sanitizeDocument(next))
    setHistory({ past: [], future: [] })
    setSelectedNodeId(null)
    setNotice({ tone: 'success', message: '演示模板已恢复，之前的本地沙盘改动已清空。' })
  }, [data, episode, projectTitle, storageKey])

  const handleUndo = useCallback(() => {
    setHistory((currentHistory) => {
      const result = undoHistoryState(currentHistory, document)
      if (!result.document) {
        return currentHistory
      }
      setDocument(result.document)
      return result.history
    })
  }, [document])

  const handleRedo = useCallback(() => {
    setHistory((currentHistory) => {
      const result = redoHistoryState(currentHistory, document)
      if (!result.document) {
        return currentHistory
      }
      setDocument(result.document)
      return result.history
    })
  }, [document])

  const handleDeleteNode = useCallback((nodeId: string) => {
    commitDocument((current) => markDeliveryRecordsStale(deleteNode(current, nodeId)))
    setSelectedNodeId((current) => current === nodeId ? null : current)
    setNotice({ tone: 'info', message: '节点已删除，相关连线和采用版本也一并清理。' })
  }, [commitDocument])

  const handleAutoLayout = useCallback(() => {
    commitDocument((current) => autoLayout(current))
    setNotice({ tone: 'success', message: '已执行自动布局，画布结构更适合继续审阅。' })
  }, [commitDocument])

  const handlePreview = useCallback(() => {
    if (!sequenceNode) {
      setNotice({ tone: 'error', message: '请先添加成片序列节点，再进行预览。' })
      return
    }
    focusNode(sequenceNode.id)
    setPreviewOpen(true)
  }, [focusNode, sequenceNode])

  const handleInspectEpisode = useCallback(() => {
    setInspectionOpen(true)
  }, [])

  const handleOpenFailureCenter = useCallback(() => {
    setFailureCenterOpen(true)
  }, [])

  const handleOpenExportCheck = useCallback(() => {
    setExportCheckOpen(true)
  }, [])

  const handleOpenProblemQueue = useCallback(() => {
    setProblemQueueOpen(true)
  }, [])

  const handleCreateDeliveryRecord = useCallback(() => {
    if (!exportReadinessReport.canExport) {
      setNotice({ tone: 'error', message: '当前仍有阻塞项，先完成导出前检查后才能创建交付版本。' })
      setExportCheckOpen(true)
      return
    }

    let versionLabel = 'delivery-v1'
    commitDocument((current) => {
      const nextIndex = (current.deliveryRecords?.length ?? 0) + 1
      versionLabel = `delivery-v${nextIndex}`
      return {
        ...current,
        deliveryRecords: [
          ...(current.deliveryRecords ?? []),
          {
            id: `delivery-record-${Date.now()}`,
            createdAt: new Date().toISOString(),
            versionLabel,
            status: 'delivered',
            summary: `${current.projectTitle} / ${current.episodeTitle} 已完成交付快照`,
            shotCount: shotNodes.length,
          },
        ],
      }
    })
    setNotice({ tone: 'success', message: `已创建交付版本 ${versionLabel}，当前这集已标记为可交付快照。` })
  }, [commitDocument, exportReadinessReport.canExport, shotNodes.length])

  const handleCopyDeliveryChecklist = useCallback(async (format: 'markdown' | 'json') => {
    const payload = format === 'json'
      ? JSON.stringify(deliveryChecklist, null, 2)
      : formatDeliveryChecklistMarkdown(deliveryChecklist)

    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(payload)
        setNotice({ tone: 'success', message: `交付清单已复制为${format === 'json' ? ' JSON' : ' Markdown'}。` })
        return
      }
    } catch {
      // fall through
    }

    setNotice({ tone: 'info', message: '当前环境不支持直接复制，但交付清单已可在弹窗中查看。' })
  }, [deliveryChecklist])

  const handleDismissTutorial = useCallback(() => {
    commitDocument((current) => ({ ...current, tutorialDismissed: true }))
  }, [commitDocument])

  const handleDuplicateNode = useCallback((nodeId: string) => {
    commitDocument((current) => markDeliveryRecordsStale(duplicateNode(current, nodeId)))
    setNotice({ tone: 'success', message: '节点已复制，新副本会作为独立分支继续使用。' })
  }, [commitDocument])

  const handleNodeFieldChange = useCallback((field: 'title' | 'summary' | 'prompt' | 'content' | 'notes', value: string) => {
    if (!selectedNode) {
      return
    }
    commitDocument((current) => {
      const updated = startFieldEdit(current, selectedNode.id, field, value)
      return markDeliveryRecordsStale(markDownstreamStale(updated, selectedNode.id))
    })
    setNotice({ tone: 'info', message: '节点内容已更新，受影响的下游结果已标记为过期。' })
  }, [commitDocument, selectedNode])

  const runMockGeneration = useCallback((sourceNodeId: string, targetKind: VersionKind, shouldFail = false) => {
    commitDocument((current) => markDeliveryRecordsStale(autoLayout(startMockGeneration(current, sourceNodeId))))
    const timerId = window.setTimeout(() => {
      if (shouldFail) {
        commitDocument((current) => markDeliveryRecordsStale(autoLayout(failMockGeneration(current, sourceNodeId, targetKind))))
        setNotice({ tone: 'error', message: `${kindText(targetKind as CreativeNodeKind)}模拟生成失败，可在右侧重试。` })
        return
      }
      commitDocument((current) => markDeliveryRecordsStale(autoLayout(finishMockGeneration(current, sourceNodeId, targetKind))))
      setNotice({
        tone: 'success',
        message: `新的${kindText(targetKind as CreativeNodeKind)}分支已生成，并默认设为当前镜头的采用版本。`,
      })
    }, 900)
    runningTimers.current.push(timerId)
  }, [commitDocument])

  const runRealGeneration = useCallback(async (sourceNode: CreativeNode, targetKind: Extract<VersionKind, 'image' | 'video'>, shouldFail = false, existingNodeId?: string) => {
      const bookId = projectId
      const episodeValue = sourceNode.data.episode ?? episode
      const shotId = sourceNode.data.shotId ?? resolveReferenceShotId(document, sourceNode)
      const selectedProfile = targetKind === 'image' ? selectedImageProfile : selectedVideoProfile
      const usesMockProfile = selectedProfile?.uses_mock ?? false
      const profileLabel = selectedProfile?.name ? `${selectedProfile.name}${usesMockProfile ? '（Mock）' : '（真实）'}` : '默认模型配置'
      const resolvedPrompt = resolveGenerationPrompt(document, sourceNode, targetKind)
      const startedAt = new Date().toISOString()
      if (targetKind === 'video' && videoProfileBlockedReason) {
        const message = `视频生成暂不可用：${videoProfileBlockedReason}`
        if (existingNodeId) {
          const failedNodeId = existingNodeId
          commitDocument((current) => markDeliveryRecordsStale(autoLayout(failGenerationTask(current, failedNodeId, targetKind, message))))
        }
        setNotice({ tone: 'error', message })
        return
      }
      if (!bookId || !shotId) {
        runMockGeneration(sourceNode.id, targetKind, shouldFail)
        return
      }

    if (existingNodeId) {
      const retryNodeId = existingNodeId
      commitDocument((current) => markDeliveryRecordsStale(autoLayout(restartGenerationTask(current, retryNodeId))))
      } else {
        const pendingNodeId = `${targetKind}-${Math.random().toString(36).slice(2, 9)}`
        commitDocument((current) =>
          markDeliveryRecordsStale(autoLayout(
            createPendingGenerationBranch(current, sourceNode.id, targetKind, {
              source: usesMockProfile ? 'mock' : 'real',
              nodeId: pendingNodeId,
              modelProfileId: selectedProfile?.id,
              modelName: selectedProfile?.model_name || sourceNode.data.generation?.model,
              provider: selectedProfile?.provider,
              usesMock: usesMockProfile,
              prompt: resolvedPrompt,
              sourceAssetId: typeof sourceNode.data.metadata?.assetId === 'string' ? sourceNode.data.metadata.assetId : undefined,
              startedAt,
            }).document,
          )),
        )
        existingNodeId = pendingNodeId
    }

      try {
        const requestPayload = {
          bookId,
          episode: episodeValue,
          shotId,
          sourceNodeId: sourceNode.id,
          sourceAssetId: typeof sourceNode.data.metadata?.assetId === 'string' ? sourceNode.data.metadata.assetId : undefined,
          assetScope: sourceNode.data.assetScope,
          assetSubject: sourceNode.data.assetSubject ?? sourceNode.data.title,
          targetKind,
          prompt: resolvedPrompt,
          model: selectedProfile?.model_name || sourceNode.data.generation?.model,
          modelProfileId: selectedProfile?.id,
          referenceAssetIds: collectReferenceAssetIds(document, sourceNode),
          aspectRatio: sourceNode.data.generation?.aspectRatio ?? '16:9',
          durationSeconds: resolveGenerationDurationSeconds(document, sourceNode, targetKind),
          count: sourceNode.data.generation?.count ?? 1,
          simulateError: shouldFail,
        }
        const response = ['character', 'location', 'prop'].includes(sourceNode.data.kind)
          ? await startReferenceImageTask(requestPayload)
          : await startCreativeTask(targetKind, requestPayload)
        commitDocument((current) => attachTaskIdToNode(current, existingNodeId!, response.task_id))
        watchCreativeTask(response.task_id, existingNodeId!)
        setNotice({
          tone: 'info',
          message: `${['character', 'location', 'prop'].includes(sourceNode.data.kind) ? '参考图' : kindText(targetKind as CreativeNodeKind)}任务已启动，当前使用 ${profileLabel}，正在轮询生成状态。`,
        })
      } catch (error) {
        const message = error instanceof Error ? `${profileLabel}：${error.message}` : `启动真实生成任务失败，请检查 ${profileLabel}。`
        commitDocument((current) => markDeliveryRecordsStale(autoLayout(failGenerationTask(current, existingNodeId!, targetKind, message))))
        setNotice({ tone: 'error', message })
      }
    }, [commitDocument, document, episode, projectId, runMockGeneration, selectedImageProfile, selectedVideoProfile, videoProfileBlockedReason, watchCreativeTask])

  const handleBatchGenerateVideos = useCallback(async (shotNodeIds: string[]) => {
    if (videoProfileBlockedReason) {
      setNotice({ tone: 'error', message: `批量视频生成暂不可用：${videoProfileBlockedReason}` })
      return
    }
    const shotTargets = shotNodeIds
      .map((shotNodeId) => document.nodes.find((node) => node.id === shotNodeId))
      .filter((node): node is CreativeNode => node !== undefined && node.data.kind === 'shot')
      .map((shotNode) => ({
        shotNode,
        sourceNode: resolvePreferredVideoSourceNode(document, shotNode),
      }))

    const runnable = shotTargets.filter((item): item is { shotNode: CreativeNode; sourceNode: CreativeNode } => item.sourceNode !== null)
    const blocked = shotTargets.filter((item) => !item.sourceNode)
    const alreadyRunning = runnable.filter(({ sourceNode }) => findRunningGenerationNode(document, sourceNode.id, 'video'))
    const readyToRun = runnable.filter(({ sourceNode }) => !findRunningGenerationNode(document, sourceNode.id, 'video'))

    if (readyToRun.length === 0) {
      setNotice({
        tone: 'error',
        message: blocked.length > 0
          ? '这些镜头还没有可用分镜图，暂时不能批量生成视频。请先补齐已采用分镜图或最新完成分镜图。'
          : '目标镜头当前都已有视频任务在生成中，请先等待当前任务完成。',
      })
      return
    }

    const results = await Promise.allSettled(
      readyToRun.map(({ sourceNode }) => runRealGeneration(sourceNode!, 'video')),
    )
    const startedCount = results.filter((result) => result.status === 'fulfilled').length
    const failedCount = results.length - startedCount
    const blockedCount = blocked.length
    const runningCount = alreadyRunning.length

    setNotice({
      tone: failedCount > 0 ? 'error' : 'success',
      message:
        failedCount > 0
          ? `已为 ${startedCount} 个镜头启动视频任务，${failedCount} 个启动失败${blockedCount > 0 ? `，另有 ${blockedCount} 个因缺少可用分镜图被跳过` : ''}${runningCount > 0 ? `，${runningCount} 个因任务进行中未重复启动` : ''}。`
        : `已为 ${startedCount} 个镜头批量启动视频生成${blockedCount > 0 ? `，并跳过 ${blockedCount} 个缺少可用分镜图的镜头` : ''}${runningCount > 0 ? `，${runningCount} 个因任务进行中未重复启动` : ''}。`,
    })
  }, [document, runRealGeneration, videoProfileBlockedReason])

  const handleBatchGenerateImages = useCallback(async (shotNodeIds: string[]) => {
    const shotTargets = shotNodeIds
      .map((shotNodeId) => document.nodes.find((node) => node.id === shotNodeId))
      .filter((node): node is CreativeNode => node !== undefined && node.data.kind === 'shot')

    if (shotTargets.length === 0) {
      setNotice({
        tone: 'error',
        message: '当前没有可批量生成分镜图的镜头。',
      })
      return
    }

    const lowReferenceCount = shotTargets.filter((shotNode) => getShotProductionState(document, shotNode).referenceCount < 3).length

    if (projectId) {
      const alreadyRunning = shotTargets.filter((shotNode) => findRunningGenerationNode(document, shotNode.id, 'image'))
      const readyToRun = shotTargets.filter((shotNode) => !findRunningGenerationNode(document, shotNode.id, 'image'))
      if (readyToRun.length === 0) {
        setNotice({
          tone: 'info',
          message: '这些镜头当前都已有分镜图任务在生成中，请先等待当前任务完成。',
        })
        return
      }
      const results = await Promise.allSettled(
        readyToRun.map((shotNode) => runRealGeneration(shotNode, 'image')),
      )
      const startedCount = results.filter((result) => result.status === 'fulfilled').length
      const failedCount = results.length - startedCount
      const runningCount = alreadyRunning.length

      setNotice({
        tone: failedCount > 0 ? 'error' : lowReferenceCount > 0 ? 'info' : 'success',
        message:
          failedCount > 0
            ? `已为 ${startedCount} 个镜头启动分镜图任务，${failedCount} 个启动失败${lowReferenceCount > 0 ? `；其中 ${lowReferenceCount} 个镜头参考图仍未补齐` : ''}${runningCount > 0 ? `；另有 ${runningCount} 个镜头因任务进行中未重复启动` : ''}。`
            : `已为 ${startedCount} 个镜头批量启动分镜图生成${lowReferenceCount > 0 ? `；其中 ${lowReferenceCount} 个镜头会带着未补齐的参考图继续生成` : ''}${runningCount > 0 ? `；另有 ${runningCount} 个镜头因任务进行中未重复启动` : ''}。`,
      })
      return
    }

    shotTargets.forEach((shotNode) => runMockGeneration(shotNode.id, 'image'))
    setNotice({
      tone: lowReferenceCount > 0 ? 'info' : 'success',
      message: `已为 ${shotTargets.length} 个镜头批量生成 Mock 分镜图${lowReferenceCount > 0 ? `；其中 ${lowReferenceCount} 个镜头参考图尚未补齐` : ''}。`,
    })
  }, [document, projectId, runMockGeneration, runRealGeneration])

  const handleGenerateFromNode = useCallback((node: CreativeNode, targetKind: VersionKind, fail = false) => {
      const generationSource =
        targetKind === 'video' && node.data.kind === 'video'
          ? resolveVideoGenerationSourceNode(document, node) ?? node
          : node

      const runningNode = findRunningGenerationNode(document, generationSource.id, targetKind)
      if (runningNode) {
        focusNode(runningNode.id)
        setNotice({
          tone: 'info',
          message: `当前已经有一个${kindText(targetKind as CreativeNodeKind)}任务在生成中，请等待它完成后再决定是否生成新版本。`,
        })
        return
      }

      if (projectId && node.data.kind === 'shot' && targetKind === 'image') {
        const production = getShotProductionState(document, node)
        if (production.referenceCount < 3) {
          setNotice({
            tone: 'info',
            message: `当前镜头参考图仅 ${production.referenceCount}/3，仍会继续生成分镜图，但存在一致性风险。`,
          })
        }
      }

      if (!projectId || targetKind === 'audio') {
        runMockGeneration(generationSource.id, targetKind, fail)
        return
      }

      if (targetKind === 'image' || targetKind === 'video') {
        void runRealGeneration(generationSource, targetKind, fail)
        return
      }

      runMockGeneration(generationSource.id, targetKind, fail)
    }, [projectId, runMockGeneration, runRealGeneration, document, setNotice, focusNode])

  const handleRetryNode = useCallback((node: CreativeNode) => {
    const sourceNodeId = node.data.versionInfo?.sourceNodeId
    const sourceNode = sourceNodeId
      ? document.nodes.find((item) => item.id === sourceNodeId)
      : null

    if (!sourceNode) {
      setNotice({ tone: 'error', message: '未找到这个失败节点的上游来源，暂时无法重试。' })
      return
    }

    if (projectId && (node.data.kind === 'image' || node.data.kind === 'video')) {
      void runRealGeneration(sourceNode, node.data.kind, false, node.id)
      return
    }

    runMockGeneration(sourceNode.id, node.data.kind === 'image' || node.data.kind === 'video' || node.data.kind === 'audio' ? node.data.kind : 'image')
  }, [document.nodes, projectId, runMockGeneration, runRealGeneration])

  const handleMarkFailureHandled = useCallback((nodeId: string) => {
    commitDocument((current) => ({
      ...current,
      nodes: current.nodes.map((node) =>
        node.id === nodeId
          ? {
              ...node,
              data: {
                ...node.data,
                metadata: {
                  ...(node.data.metadata ?? {}),
                  failureHandledAt: new Date().toISOString(),
                },
              },
            }
          : node,
      ),
    }))
    setNotice({ tone: 'info', message: '这个失败任务已标记为已处理，仍可随时回到节点继续重试。' })
  }, [commitDocument])

  const handleAdoptVersion = useCallback((nodeId: string) => {
    const targetNode = document.nodes.find((node) => node.id === nodeId)
    commitDocument((current) => markDeliveryRecordsStale(adoptVersion(current, nodeId)))

    if (
      projectId &&
      targetNode?.data.shotId &&
      (targetNode.data.kind === 'image' || targetNode.data.kind === 'video' || targetNode.data.kind === 'audio') &&
      typeof targetNode.data.metadata?.source === 'string' &&
      targetNode.data.metadata.source === 'real' &&
      typeof targetNode.data.metadata?.assetId === 'string'
    ) {
      void persistAdoptedVersion({
        bookId: projectId,
        episode: targetNode.data.episode ?? episode,
        shotId: targetNode.data.shotId,
        kind: targetNode.data.kind,
        assetId: targetNode.data.metadata.assetId,
      }).catch((error) => {
        setNotice({
          tone: 'error',
          message: error instanceof Error ? error.message : '采用版本保存失败。',
        })
      })
    }

    setNotice({ tone: 'success', message: '版本已采用，成片序列会优先使用这个分支。' })
  }, [commitDocument, document.nodes, episode, projectId])

  const handleUnadoptVersion = useCallback((nodeId: string) => {
    const targetNode = document.nodes.find((node) => node.id === nodeId)
    commitDocument((current) => markDeliveryRecordsStale(unadoptVersion(current, nodeId)))
    setNotice({
      tone: 'info',
      message: targetNode?.data.kind === 'video'
        ? '已取消当前视频版本的采用关系，这个镜头会暂时从成片序列中移出。'
        : '已取消当前版本的采用关系。',
    })
  }, [commitDocument, document.nodes])

  const handleCopyVersionInfo = useCallback(async (node: CreativeNode) => {
    const payload = [
      `节点：${node.data.title}`,
      `类型：${kindText(node.data.kind)}`,
      `镜头：${node.data.shotId ?? '无'}`,
      `版本：${node.data.versionInfo?.label ?? '草稿'}`,
      `生成时间：${node.data.versionInfo?.createdAt ? new Date(node.data.versionInfo.createdAt).toLocaleString() : '未知'}`,
      `来源：${node.data.metadata?.source === 'real' ? '真实资产' : node.data.metadata?.source === 'mock' ? 'Mock 分支' : '本地节点'}`,
      `资产 ID：${typeof node.data.metadata?.assetId === 'string' ? node.data.metadata.assetId : '无'}`,
      `提示词：${node.data.prompt || '无'}`,
    ].join('\n')

    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(payload)
        setNotice({ tone: 'success', message: '版本信息已复制，方便同步给团队或记录验收。' })
        return
      }
    } catch {
      // Fallback to notice below.
    }

    setNotice({ tone: 'info', message: `当前环境不支持直接复制，请手动记录：${node.data.versionInfo?.label ?? '草稿'} / ${node.data.title}` })
  }, [])

  const handleToggleReference = useCallback((assetNodeId: string, shotNodeId: string, linked: boolean) => {
    try {
      commitDocument((current) => markDeliveryRecordsStale(setReferenceLink(current, assetNodeId, shotNodeId, linked)))
      setNotice({
        tone: 'info',
        message: linked ? '资产已关联到镜头，下游结果已标记为过期。' : '资产已取消关联，下游结果已标记为过期。',
      })
    } catch (error) {
      setNotice({ tone: 'error', message: error instanceof Error ? error.message : '更新镜头引用失败。' })
    }
  }, [commitDocument])

  const handleSaveViewport = useCallback((viewport: Viewport) => {
    setDocument((current) => ({ ...current, viewport }))
  }, [])

  const handleUpdateShotReview = useCallback((shotId: string, status: ReviewStatus, note?: string) => {
    commitDocument((current) => ({
      ...current,
      nodes: current.nodes.map((node) => {
        if (node.data.kind !== 'shot' || node.data.shotId !== shotId) {
          return node
        }
        return {
          ...node,
          data: {
            ...node.data,
            metadata: {
              ...(node.data.metadata ?? {}),
              reviewStatus: status,
              reviewNote: note ?? (typeof node.data.metadata?.reviewNote === 'string' ? node.data.metadata.reviewNote : ''),
              reviewedAt: new Date().toISOString(),
            },
          },
        }
      }),
      deliveryRecords: (current.deliveryRecords ?? []).map((record) => ({
        ...record,
        status: 'stale' as const,
      })),
    }))
    setNotice({
      tone: status === 'changes_requested' ? 'info' : 'success',
      message: `镜头 ${shotId} 的审片状态已更新为${reviewStatusText(status)}。`,
    })
  }, [commitDocument])

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-[#020617] text-slate-100">
      <TopBar
        onBack={onBack}
        onUndo={handleUndo}
        onRedo={handleRedo}
        onPreview={handlePreview}
        onAutoLayout={handleAutoLayout}
        onReset={handleReset}
        onDuplicateSelected={selectedNode ? () => handleDuplicateNode(selectedNode.id) : undefined}
        edgeVisibilityMode={edgeVisibilityMode}
        onToggleEdgeVisibility={() => setEdgeVisibilityMode((current) => current === 'all' ? 'focus' : 'all')}
        referenceLayerVisible={referenceLayerVisible}
        onToggleReferenceLayer={() => setReferenceLayerVisible((current) => !current)}
        canUndo={history.past.length > 0}
        canRedo={history.future.length > 0}
        projectTitle={document.projectTitle}
        projectId={projectId}
        episodeTitle={document.episodeTitle}
        episode={episode}
        availableEpisodes={availableEpisodes}
        onEpisodeChange={onEpisodeChange}
        savedAt={document.lastSavedAt}
        savePulse={savePulse}
        productionSummary={productionSummary}
        saveState={saveState}
        onInspectEpisode={handleInspectEpisode}
        onOpenFailureCenter={handleOpenFailureCenter}
        activeFailureCount={activeFailureTaskEntries.length}
        onOpenExportCheck={handleOpenExportCheck}
        exportReady={exportReadinessReport.canExport}
        latestDeliveryRecord={latestDeliveryRecord}
        onOpenProblemQueue={handleOpenProblemQueue}
        problemCount={problemQueueEntries.length}
        activeModelHint={activeModelHint}
        modelWarning={videoProfileBlockedReason}
        modelRegistryState={modelRegistryState}
        onOpenModelRegistry={handleOpenModelRegistry}
      />
      <ProductionOverviewBar
        productionSummary={productionSummary}
        exportReady={exportReadinessReport.canExport}
        latestDeliveryRecord={latestDeliveryRecord}
        problemCount={problemQueueEntries.length}
        onOpenInspection={handleInspectEpisode}
        onOpenProblemQueue={handleOpenProblemQueue}
        onOpenFailureCenter={handleOpenFailureCenter}
      />

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <LeftRail
          activeTab={activeTab}
          onTabChange={setActiveTab}
          onAddNode={handleAddNode}
          shots={displayShotNodes}
          assets={panelAssetNodes}
          adoptedVersions={document.adoptedVersions}
          document={document}
          onSelectNode={focusNode}
          onOpenPreview={handlePreview}
          onOpenFailureCenter={handleOpenFailureCenter}
          selectedNodeId={selectedNodeId}
          collapsed={leftRailCollapsed}
          onToggleCollapse={() => setLeftRailCollapsed((current) => !current)}
        />

        <div className="relative min-w-0 flex-1">
          <CanvasGroups referenceLayerVisible={referenceLayerVisible} />
          <ReactFlow
            nodes={displayNodes}
            edges={displayEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onInit={setReactFlowInstance}
            onSelectionChange={handleSelectionChange}
            onNodeClick={handleNodeClick}
            onNodeMouseEnter={(_, node) => setHoveredNodeId(node.id)}
            onNodeMouseLeave={() => setHoveredNodeId(null)}
            isValidConnection={isValidConnection}
            onDoubleClick={handlePaneDoubleClick}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            fitView
            fitViewOptions={{ padding: 0.24, minZoom: 0.45 }}
            minZoom={0.35}
            maxZoom={1.5}
            defaultViewport={document.viewport}
            onMoveEnd={(_, viewport) => handleSaveViewport(viewport)}
            deleteKeyCode="Delete"
            multiSelectionKeyCode="Shift"
            selectionKeyCode="Meta"
            className="bg-[radial-gradient(circle_at_top,#152342_0%,#020617_55%)]"
          >
            <Background color="#1e293b" gap={28} size={1.2} />
            <Controls className="!rounded-xl !border !border-slate-800 !bg-slate-950/90 !text-slate-200" />
            <MiniMap
              pannable
              zoomable
              nodeColor={(node) => NODE_STYLE[(node.data as CreativeNode['data']).kind].accent}
              maskColor="rgba(2,6,23,0.72)"
              style={{
                background: '#020617',
                border: '1px solid rgba(30,41,59,0.9)',
                borderRadius: 14,
              }}
            />
          {notice && (
            <Panel position="top-center" className="!mt-4">
              <NoticeBanner notice={notice} onDismiss={() => setNotice(null)} />
            </Panel>
          )}
            <Panel position="top-right" className="!mr-4 !mt-20">
              <CanvasLegend edgeVisibilityMode={edgeVisibilityMode} selectedNode={selectedNode} />
            </Panel>
          </ReactFlow>

          {shotNodes.length === 0 && (
            <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center">
              <div className="pointer-events-auto max-w-xl rounded-[28px] border border-slate-800/90 bg-slate-950/92 px-6 py-6 text-center shadow-[0_20px_60px_rgba(2,6,23,0.4)]">
                <div className="text-[11px] uppercase tracking-[0.24em] text-sky-300">半成品状态</div>
                <div className="text-sm font-semibold text-slate-100">当前集还没有分镜数据</div>
                <div className="mt-2 text-sm leading-6 text-slate-400">
                  后端已返回真实项目与剧本信息，但这一集暂时还没有可映射到画布的镜头、图片或视频资产。
                  下一步建议先去内容准备补齐剧本或分镜表，再回到这里继续做参考图、分镜图、视频和交付。
                </div>
                <div className="mt-5 flex flex-wrap justify-center gap-3">
                  {onOpenPreparation ? (
                    <button
                      onClick={onOpenPreparation}
                      className="rounded-full bg-sky-400 px-4 py-2 text-sm font-medium text-slate-950 transition hover:brightness-110"
                    >
                      去内容准备补齐分镜
                    </button>
                  ) : null}
                  <button
                    onClick={handleInspectEpisode}
                    className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-500 hover:text-white"
                  >
                    查看当前缺口
                  </button>
                  {onBack ? (
                    <button
                      onClick={onBack}
                      className="rounded-full border border-slate-700 px-4 py-2 text-sm text-slate-200 transition hover:border-slate-500 hover:text-white"
                    >
                      返回项目列表
                    </button>
                  ) : null}
                </div>
              </div>
            </div>
          )}

          {!document.tutorialDismissed && (
            <TutorialCard onDismiss={handleDismissTutorial} />
          )}
        </div>

        <RightPanel
          node={displayNodes.find((node) => node.id === selectedNodeId) ?? selectedNode}
          document={document}
          onFieldChange={handleNodeFieldChange}
          onDeleteNode={handleDeleteNode}
          onGenerateFromNode={handleGenerateFromNode}
          onRetryNode={handleRetryNode}
          onAdoptVersion={handleAdoptVersion}
          onUnadoptVersion={handleUnadoptVersion}
          onCopyVersionInfo={handleCopyVersionInfo}
          onSelectNode={focusNode}
          onDuplicateNode={handleDuplicateNode}
          onUpdateShotReview={handleUpdateShotReview}
          onToggleReference={handleToggleReference}
          assetNodes={panelAssetNodes}
          videoProfileBlockedReason={videoProfileBlockedReason}
          referenceLayerVisible={referenceLayerVisible}
          onShowReferenceLayer={() => setReferenceLayerVisible(true)}
          collapsed={rightPanelCollapsed}
          onToggleCollapse={() => setRightPanelCollapsed((current) => !current)}
        />
      </div>
      {modelRegistryOpen && (
        <ModelRegistryModal
          data={modelRegistryData}
          error={modelRegistryError}
          onClose={() => setModelRegistryOpen(false)}
          onSaved={handleModelRegistryUpdated}
        />
      )}
      {previewOpen && (
        <PreviewModal
          projectTitle={document.projectTitle}
          episodeTitle={document.episodeTitle}
          document={document}
          entries={sequenceEntries}
          failedNodes={failedNodes}
          onClose={() => setPreviewOpen(false)}
          onSelectNode={focusNode}
          onRetryNode={handleRetryNode}
          onUpdateShotReview={handleUpdateShotReview}
        />
      )}
      {inspectionOpen && (
        <EpisodeInspectionModal
          projectTitle={document.projectTitle}
          episodeTitle={document.episodeTitle}
          report={inspectionReport}
          onBatchGenerateImages={() =>
            void handleBatchGenerateImages(inspectionReport.missingImageShots.map((issue) => issue.shotNode.id))
          }
          onBatchGenerateVideos={() =>
            void handleBatchGenerateVideos(inspectionReport.missingVideoShots.map((issue) => issue.shotNode.id))
          }
          onClose={() => setInspectionOpen(false)}
          onSelectShot={(nodeId) => {
            setInspectionOpen(false)
            focusNode(nodeId)
          }}
        />
      )}
      {failureCenterOpen && (
        <FailureTaskCenterModal
          entries={failureTaskEntries}
          onClose={() => setFailureCenterOpen(false)}
          onSelectNode={(nodeId) => {
            setFailureCenterOpen(false)
            focusNode(nodeId)
          }}
          onRetryNode={(nodeId) => {
            const targetNode = document.nodes.find((node) => node.id === nodeId)
            if (targetNode) {
              handleRetryNode(targetNode)
            }
          }}
          onMarkHandled={handleMarkFailureHandled}
        />
      )}
      {exportCheckOpen && (
        <ExportReadinessModal
          report={exportReadinessReport}
          checklist={deliveryChecklist}
          onClose={() => setExportCheckOpen(false)}
          onSelectNode={(nodeId) => {
            setExportCheckOpen(false)
            focusNode(nodeId)
          }}
          onCreateDeliveryRecord={handleCreateDeliveryRecord}
          onCopyChecklist={handleCopyDeliveryChecklist}
        />
      )}
      {problemQueueOpen && (
        <ProblemQueueModal
          entries={problemQueueEntries}
          onClose={() => setProblemQueueOpen(false)}
          onSelectNode={(nodeId) => {
            setProblemQueueOpen(false)
            focusNode(nodeId)
          }}
        />
      )}
    </div>
  )
}

function TopBar({
  onBack,
  onUndo,
  onRedo,
  onPreview,
  onAutoLayout,
  onReset,
  onDuplicateSelected,
  edgeVisibilityMode,
  onToggleEdgeVisibility,
  referenceLayerVisible,
  onToggleReferenceLayer,
  canUndo,
  canRedo,
  projectTitle,
  projectId,
  episodeTitle,
  episode,
  availableEpisodes,
  onEpisodeChange,
  savedAt,
  savePulse,
  productionSummary,
  saveState,
  onInspectEpisode,
  onOpenFailureCenter,
  activeFailureCount,
  onOpenProblemQueue,
  problemCount,
  onOpenExportCheck,
  exportReady,
  latestDeliveryRecord,
  activeModelHint,
  modelWarning,
  modelRegistryState,
  onOpenModelRegistry,
}: {
  onBack?: () => void
  onUndo: () => void
  onRedo: () => void
  onPreview: () => void
  onAutoLayout: () => void
  onReset: () => void
  onDuplicateSelected?: () => void
  edgeVisibilityMode: EdgeVisibilityMode
  onToggleEdgeVisibility: () => void
  referenceLayerVisible: boolean
  onToggleReferenceLayer: () => void
  canUndo: boolean
  canRedo: boolean
  projectTitle: string
  projectId?: number
  episodeTitle: string
  episode: number
  availableEpisodes: number[]
  onEpisodeChange?: (episode: number) => void
  savedAt?: string
  savePulse: boolean
  productionSummary: {
    totalShots: number
    referencedShots: number
    imageReadyShots: number
    videoReadyShots: number
    sequenceShots: number
    reviewedApprovedShots: number
    failedTasks: number
    missingSequenceShots: number
  }
  saveState: SaveState
  onInspectEpisode: () => void
  onOpenFailureCenter: () => void
  activeFailureCount: number
  onOpenProblemQueue: () => void
  problemCount: number
  onOpenExportCheck: () => void
  exportReady: boolean
  latestDeliveryRecord?: NonNullable<CanvasDocument['deliveryRecords']>[number]
  activeModelHint: string
  modelWarning?: string | null
  modelRegistryState: 'idle' | 'loading' | 'error'
  onOpenModelRegistry: () => void
}) {
  const deliveryButtonLabel = latestDeliveryRecord
    ? latestDeliveryRecord.status === 'delivered'
      ? `已交付 ${latestDeliveryRecord.versionLabel}`
      : '有变更，需重新交付'
    : exportReady
      ? '本集可交付'
      : '导出前检查'

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-slate-800 bg-slate-950/90 px-4 py-3 backdrop-blur">
      {onBack && (
        <button onClick={onBack} className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white">
          返回
        </button>
      )}
      <div>
        <div className="text-[11px] uppercase tracking-[0.28em] text-slate-500">分镜生产</div>
        <div className="mt-1 text-sm font-semibold text-slate-100">{projectTitle} / {episodeTitle}</div>
        {typeof projectId === 'number' && projectId > 0 ? (
          <div className="mt-1 text-[11px] text-slate-500">项目 ID：{projectId}</div>
        ) : null}
      </div>
      {availableEpisodes.length > 1 && onEpisodeChange ? (
        <div className="flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900/80 px-2 py-1">
          <span className="px-2 text-[11px] text-slate-500">集数</span>
          <select
            value={episode}
            onChange={(event) => onEpisodeChange(Number(event.target.value))}
            className="rounded-full border border-slate-700 bg-slate-950 px-3 py-1 text-xs text-slate-200 outline-none"
          >
            {availableEpisodes.map((item) => (
              <option key={item} value={item}>
                第 {item} 集
              </option>
            ))}
          </select>
        </div>
      ) : null}
      <div className="h-8 w-px bg-slate-800" />
      <button onClick={onUndo} disabled={!canUndo} className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 disabled:opacity-40">
        撤销
      </button>
      <button onClick={onRedo} disabled={!canRedo} className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 disabled:opacity-40">
        重做
      </button>
      <button onClick={onAutoLayout} className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white">
        自动布局
      </button>
      <button onClick={onReset} className="rounded-full border border-rose-700/60 px-3 py-1.5 text-xs text-rose-200 transition hover:border-rose-500 hover:text-white">
        重置模板
      </button>
      {onDuplicateSelected && (
        <button onClick={onDuplicateSelected} className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white">
          复制选中
        </button>
      )}
      <button onClick={onToggleReferenceLayer} className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white">
        {referenceLayerVisible ? '收起参考资产层' : '展开参考资产层'}
      </button>
      <button onClick={onToggleEdgeVisibility} className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white">
        {edgeVisibilityMode === 'all' ? '聚焦当前镜头引用线' : '显示全部引用线'}
      </button>
      <button onClick={onInspectEpisode} className="rounded-full border border-sky-700/60 px-3 py-1.5 text-xs text-sky-200 transition hover:border-sky-500 hover:text-white">
        检查本集
      </button>
      <button onClick={onOpenFailureCenter} className="rounded-full border border-red-700/60 px-3 py-1.5 text-xs text-red-200 transition hover:border-red-500 hover:text-white">
        失败任务 {activeFailureCount > 0 ? activeFailureCount : ''}
      </button>
      <button onClick={onOpenProblemQueue} className="rounded-full border border-amber-700/60 px-3 py-1.5 text-xs text-amber-200 transition hover:border-amber-500 hover:text-white">
        问题清单 {problemCount > 0 ? problemCount : ''}
      </button>
      <button
        onClick={onOpenExportCheck}
        className={`rounded-full px-3 py-1.5 text-xs transition ${latestDeliveryRecord?.status === 'delivered' ? 'border border-sky-500/60 bg-sky-500/10 text-sky-100 hover:border-sky-400' : latestDeliveryRecord?.status === 'stale' ? 'border border-amber-600/60 text-amber-200 hover:border-amber-400 hover:text-white' : exportReady ? 'border border-emerald-500/60 bg-emerald-500/10 text-emerald-100 hover:border-emerald-400' : 'border border-amber-600/60 text-amber-200 hover:border-amber-400 hover:text-white'}`}
      >
        {deliveryButtonLabel}
      </button>
      <div className="flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900/70 px-2 py-1">
        <SummaryPill label="镜头" value={`${productionSummary.totalShots}`} />
        <SummaryPill label="参考" value={`${productionSummary.referencedShots}` + '/' + `${productionSummary.totalShots || 0}`} />
        <SummaryPill label="分镜图" value={`${productionSummary.imageReadyShots}`} />
        <SummaryPill label="视频" value={`${productionSummary.videoReadyShots}`} />
        <SummaryPill label="成片" value={`${productionSummary.sequenceShots}`} />
        {productionSummary.totalShots > productionSummary.sequenceShots ? (
          <SummaryPill label="待入成片" value={`${productionSummary.totalShots - productionSummary.sequenceShots}`} danger />
        ) : null}
        {productionSummary.failedTasks > 0 ? <SummaryPill label="失败" value={`${productionSummary.failedTasks}`} danger /> : null}
      </div>
      <div className="ml-auto flex items-center gap-2">
        {modelWarning ? (
          <div className="max-w-[320px] truncate rounded-full border border-amber-500/40 bg-amber-500/10 px-3 py-1 text-[11px] text-amber-100" title={modelWarning}>
            视频配置提示：{modelWarning}
          </div>
        ) : null}
        <div className={`max-w-[320px] truncate rounded-full border px-3 py-1 text-[11px] ${modelRegistryState === 'error' ? 'border-amber-600/60 text-amber-200' : 'border-slate-700 bg-slate-900 text-slate-400'}`} title={activeModelHint}>
          {modelRegistryState === 'loading' ? '正在加载模型配置' : modelRegistryState === 'error' ? '模型配置加载失败，请打开模型管理重试' : activeModelHint}
        </div>
        <button onClick={onOpenModelRegistry} className="rounded-full border border-violet-600/60 px-3 py-1.5 text-xs text-violet-200 transition hover:border-violet-400 hover:text-white">
          模型管理
        </button>
        <div className={`rounded-full border px-3 py-1 text-[11px] uppercase tracking-[0.18em] ${saveState === 'error' ? 'border-red-500/50 bg-red-500/10 text-red-200' : saveState === 'saving' ? 'border-amber-400/60 bg-amber-500/10 text-amber-200' : savePulse ? 'border-emerald-400/60 bg-emerald-500/10 text-emerald-200' : 'border-slate-700 bg-slate-900 text-slate-400'}`}>
          {saveState === 'error'
            ? '保存失败'
            : saveState === 'saving'
              ? '保存中'
              : savedAt
                ? `已保存 ${new Date(savedAt).toLocaleTimeString()}`
                : '仅本地'}
        </div>
        <button onClick={onPreview} className="rounded-full bg-gradient-to-r from-sky-500 to-cyan-400 px-4 py-1.5 text-xs font-semibold text-slate-950 shadow-[0_8px_30px_rgba(34,211,238,0.28)] transition hover:brightness-110">
          播放预览
        </button>
      </div>
    </div>
  )
}

function CanvasGroups({ referenceLayerVisible }: { referenceLayerVisible: boolean }) {
  return (
    <div className="pointer-events-none absolute inset-x-0 top-4 z-10 px-6">
      <div className="relative h-12">
        {COLUMN_GROUPS
          .filter((group) => referenceLayerVisible || group.key !== 'asset')
          .map((group) => (
          <div key={group.key} className="absolute top-0" style={{ left: group.left, transform: 'translateX(-50%)' }}>
            <div className="rounded-full border border-slate-700/80 bg-slate-950/85 px-4 py-1 text-[11px] uppercase tracking-[0.22em] text-slate-300 shadow-[0_10px_30px_rgba(2,6,23,0.32)]">
              {group.label}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function SummaryPill({ label, value, danger }: { label: string; value: string; danger?: boolean }) {
  return (
    <div className={`rounded-full px-2 py-1 text-[11px] ${danger ? 'bg-red-500/12 text-red-200' : 'bg-slate-950/80 text-slate-300'}`}>
      <span className="text-slate-500">{label}</span>
      <span className="ml-1 font-semibold text-inherit">{value}</span>
    </div>
  )
}

function ProductionOverviewBar({
  productionSummary,
  exportReady,
  latestDeliveryRecord,
  problemCount,
  onOpenInspection,
  onOpenProblemQueue,
  onOpenFailureCenter,
}: {
  productionSummary: {
    totalShots: number
    referencedShots: number
    imageReadyShots: number
    videoReadyShots: number
    sequenceShots: number
    reviewedApprovedShots: number
    failedTasks: number
    missingSequenceShots: number
  }
  exportReady: boolean
  latestDeliveryRecord?: NonNullable<CanvasDocument['deliveryRecords']>[number]
  problemCount: number
  onOpenInspection: () => void
  onOpenProblemQueue: () => void
  onOpenFailureCenter: () => void
}) {
  const deliveryText = latestDeliveryRecord
    ? latestDeliveryRecord.status === 'delivered'
      ? latestDeliveryRecord.versionLabel
      : `${latestDeliveryRecord.versionLabel} 待重交`
    : exportReady
      ? '可交付'
      : '未交付'

  return (
    <div className="border-b border-slate-900 bg-slate-950/80 px-4 py-3">
      <div className="flex flex-wrap items-center gap-3 rounded-3xl border border-slate-800 bg-slate-900/50 px-4 py-3">
        <div className="min-w-[180px]">
          <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500">生产进度总览</div>
          <div className="mt-1 text-sm text-slate-300">
            {exportReady
              ? '当前这一集已经达到可交付状态。'
              : productionSummary.failedTasks > 0
                ? '当前有失败任务，建议先处理失败和问题清单。'
                : productionSummary.sequenceShots < productionSummary.totalShots
                  ? '当前还有镜头未进入成片序列。'
                  : '当前还在生产或审片阶段。'}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusTile label="总镜头" value={String(productionSummary.totalShots)} />
          <StatusTile label="参考图镜头" value={`${productionSummary.referencedShots}/${productionSummary.totalShots || 0}`} />
          <StatusTile label="分镜图镜头" value={String(productionSummary.imageReadyShots)} />
          <StatusTile label="视频镜头" value={String(productionSummary.videoReadyShots)} />
          <StatusTile label="已采用视频" value={String(productionSummary.sequenceShots)} />
          <StatusTile label="审片通过" value={`${productionSummary.reviewedApprovedShots}/${productionSummary.totalShots || 0}`} />
          <StatusTile label="交付状态" value={exportReady ? '可交付' : '未完成'} />
          <StatusTile label="当前交付版本" value={deliveryText} />
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          <ActionButton label="检查缺口" onClick={onOpenInspection} muted />
          <ActionButton label="查看问题清单" onClick={onOpenProblemQueue} muted={problemCount === 0} />
          <ActionButton label="查看失败任务" onClick={onOpenFailureCenter} muted={productionSummary.failedTasks === 0} />
        </div>
      </div>
    </div>
  )
}

function LeftRail({
  activeTab,
  onTabChange,
  onAddNode,
  shots,
  assets,
  document,
  adoptedVersions,
  onSelectNode,
  onOpenPreview,
  onOpenFailureCenter,
  selectedNodeId,
  collapsed,
  onToggleCollapse,
}: {
  activeTab: LeftRailTab
  onTabChange: (tab: LeftRailTab) => void
  onAddNode: (kind: CreativeNodeKind) => void
  shots: CreativeNode[]
  assets: CreativeNode[]
  document: CanvasDocument
  adoptedVersions: CanvasDocument['adoptedVersions']
  onSelectNode: (nodeId: string) => void
  onOpenPreview: () => void
  onOpenFailureCenter: () => void
  selectedNodeId: string | null
  collapsed: boolean
  onToggleCollapse: () => void
}) {
  if (collapsed) {
    return (
      <aside className="flex w-[60px] flex-col items-center border-r border-slate-800 bg-slate-950/95 py-4">
        <button onClick={onToggleCollapse} className="rounded-2xl border border-slate-700 px-2 py-3 text-[11px] text-slate-300 transition hover:border-slate-500 hover:text-white">
          展开
        </button>
        <div className="mt-4 flex flex-col gap-2">
          {[ 
            ['outline', '镜头'],
            ['assets', '参考'],
            ['add', '添加'],
          ].map(([tab, label]) => (
            <button
              key={tab}
              onClick={() => onTabChange(tab as LeftRailTab)}
              className={`rounded-2xl px-2 py-3 text-[11px] transition ${
                activeTab === tab
                  ? 'bg-slate-100 text-slate-950'
                  : 'border border-slate-700 text-slate-400 hover:border-slate-500 hover:text-white'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </aside>
    )
  }

  return (
    <aside className="flex w-[320px] flex-col border-r border-slate-800 bg-slate-950/95">
      <div className="border-b border-slate-800 px-4 py-4">
        <div className="mb-2 flex justify-end">
          <button onClick={onToggleCollapse} className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white">
            收起
          </button>
        </div>
        <div className="text-[11px] uppercase tracking-[0.28em] text-slate-500">创作沙盘</div>
        <div className="mt-2 text-sm leading-6 text-slate-300">剧本、参考资产、镜头版本分支与成片序列都集中在同一个工作台里。</div>
        <div className="mt-4 flex gap-2">
          {[
            ['outline', '镜头'],
            ['assets', '参考资产'],
            ['add', '添加'],
          ].map(([tab, label]) => (
            <button
              key={tab}
              onClick={() => onTabChange(tab as LeftRailTab)}
              className={`rounded-full px-3 py-1.5 text-xs transition ${
                activeTab === tab
                  ? 'bg-slate-100 text-slate-950'
                  : 'border border-slate-700 text-slate-300 hover:border-slate-500'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {activeTab === 'outline' && (
          <div className="space-y-3">
            {shots.map((node) => {
              const adoptedImage = adoptedVersions.image?.[node.data.shotId ?? '']
              const adoptedVideo = adoptedVersions.video?.[node.data.shotId ?? '']
              const production = node.data.ui?.production
              const review = getShotReviewState(document, node)
              const nextStep =
                production?.sequenceState === '已进入'
                  ? '已进入成片，可继续检查其他镜头。'
                  : production?.sequenceState === '待采用' || production?.videoState === '已生成视频'
                    ? '优先采用一个视频版本并编入成片。'
                    : production?.videoState === '生成中'
                      ? '视频正在生成，稍后会自动回填到镜头分支。'
                      : production?.videoState === '生成失败'
                        ? '先查看失败原因并重试视频生成。'
                        : production?.imageState === '已生成图片'
                          ? '下一步生成视频。'
                          : production?.imageState === '生成中'
                            ? '分镜图正在生成，完成后可继续生成视频。'
                            : production?.imageState === '生成失败'
                              ? '先查看失败原因并重试分镜图生成。'
                              : production?.referenceState === '完整'
                                ? '下一步生成分镜图。'
                              : '先补齐参考资产或直接生成第一版分镜图。'
              const quickAction = getShotQuickAction({
                node,
                document,
                adoptedVersions,
                onSelectNode,
                onOpenPreview,
                onOpenFailureCenter,
              })
              return (
                <button
                  key={node.id}
                  onClick={() => onSelectNode(node.id)}
                  className={`w-full rounded-2xl px-4 py-3 text-left transition ${
                    selectedNodeId === node.id
                      ? 'border border-sky-400/60 bg-sky-500/10 ring-1 ring-sky-400/30'
                      : 'border border-slate-800 bg-slate-900/70 hover:border-slate-600 hover:bg-slate-900'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-semibold text-slate-100">{node.data.title}</div>
                    <div className="rounded-full bg-amber-500/12 px-2 py-0.5 text-[10px] uppercase tracking-[0.18em] text-amber-200">
                      {nodeStatusLabel(node.data)}
                    </div>
                  </div>
                  <div className="mt-2 line-clamp-2 text-xs leading-5 text-slate-400">{node.data.summary}</div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-slate-400">
                    <span>参考图：{production?.referenceState ?? '待检查'}</span>
                    <span>分镜图：{production?.imageState ?? (adoptedImage ? '已生成' : '待生成')}</span>
                    <span>视频：{production?.videoState ?? (adoptedVideo ? '已生成' : '待生成')}</span>
                    <span>序列：{production?.sequenceState ?? (adoptedVideo ? '已进入' : '未进入')}</span>
                  </div>
                  <div className="mt-2 text-[11px] text-slate-400">
                    审片：<span className={reviewStatusClass(review.status)}>{reviewStatusText(review.status)}</span>
                  </div>
                  <div className="mt-3 rounded-2xl border border-slate-800/80 bg-slate-950/70 px-3 py-2 text-[11px] leading-5 text-slate-300">
                    <span className="text-slate-500">推荐下一步：</span>
                    {nextStep}
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation()
                        quickAction.onClick()
                      }}
                      className="rounded-full bg-slate-100 px-3 py-1.5 text-[11px] font-semibold text-slate-950 transition hover:bg-white"
                    >
                      {quickAction.label}
                    </button>
                    {quickAction.secondaryLabel ? (
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation()
                          onSelectNode(node.id)
                        }}
                        className="rounded-full border border-slate-700 px-3 py-1.5 text-[11px] text-slate-300 transition hover:border-slate-500 hover:text-white"
                      >
                        {quickAction.secondaryLabel}
                      </button>
                    ) : null}
                  </div>
                  <div className="mt-3 text-[10px] uppercase tracking-[0.18em] text-slate-500">
                    {production?.riskHint ?? '按主链路推进即可'}
                  </div>
                </button>
              )
            })}
          </div>
        )}

        {activeTab === 'assets' && (
          <div className="space-y-3">
            {assets.map((node) => (
              <button
                key={node.id}
                onClick={() => onSelectNode(node.id)}
                className={`w-full rounded-2xl px-4 py-3 text-left transition ${
                  selectedNodeId === node.id
                    ? 'border border-sky-400/60 bg-sky-500/10 ring-1 ring-sky-400/30'
                    : 'border border-slate-800 bg-slate-900/70 hover:border-slate-600 hover:bg-slate-900'
                }`}
              >
                <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500">
                  {node.data.imageRole === 'reference' ? '参考图' : kindText(node.data.kind)}
                </div>
                <div className="mt-1 text-sm font-semibold text-slate-100">{node.data.title}</div>
                <div className="mt-2 line-clamp-3 text-xs leading-5 text-slate-400">{node.data.summary}</div>
              </button>
            ))}
          </div>
        )}

        {activeTab === 'add' && (
          <div className="grid grid-cols-2 gap-3">
            {ADDABLE_KINDS.map((kind) => (
              <button
                key={kind}
                onClick={() => onAddNode(kind)}
                className="rounded-2xl border border-slate-800 bg-slate-900/70 px-3 py-4 text-left transition hover:border-slate-600 hover:bg-slate-900"
              >
                <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500">{kindText(kind)}</div>
                <div className="mt-1 text-sm font-semibold text-slate-100">添加{kindText(kind)}</div>
                <div className="mt-2 text-xs leading-5 text-slate-400">将新节点插入画布，并在右侧面板中继续编辑。</div>
              </button>
            ))}
          </div>
        )}
      </div>
    </aside>
  )
}

function RightPanel({
  node,
  document,
  onFieldChange,
  onDeleteNode,
  onGenerateFromNode,
  onRetryNode,
  onAdoptVersion,
  onUnadoptVersion,
  onCopyVersionInfo,
  onSelectNode,
  onDuplicateNode,
  onUpdateShotReview,
  onToggleReference,
  assetNodes,
  videoProfileBlockedReason,
  referenceLayerVisible,
  onShowReferenceLayer,
  collapsed,
  onToggleCollapse,
}: {
  node: CreativeNode | null
  document: CanvasDocument
  onFieldChange: (field: 'title' | 'summary' | 'prompt' | 'content' | 'notes', value: string) => void
  onDeleteNode: (nodeId: string) => void
  onGenerateFromNode: (node: CreativeNode, targetKind: VersionKind, fail?: boolean) => void
  onRetryNode: (node: CreativeNode) => void
  onAdoptVersion: (nodeId: string) => void
  onUnadoptVersion: (nodeId: string) => void
  onCopyVersionInfo: (node: CreativeNode) => void
  onSelectNode: (nodeId: string) => void
  onDuplicateNode: (nodeId: string) => void
  onUpdateShotReview: (shotId: string, status: ReviewStatus, note?: string) => void
  onToggleReference: (assetNodeId: string, shotNodeId: string, linked: boolean) => void
  assetNodes: CreativeNode[]
  videoProfileBlockedReason?: string | null
  referenceLayerVisible: boolean
  onShowReferenceLayer: () => void
  collapsed: boolean
  onToggleCollapse: () => void
}) {
  if (collapsed) {
    return (
      <aside className="flex w-[60px] flex-col items-center border-l border-slate-800 bg-slate-950/95 py-4">
        <button onClick={onToggleCollapse} className="rounded-2xl border border-slate-700 px-2 py-3 text-[11px] text-slate-300 transition hover:border-slate-500 hover:text-white">
          展开
        </button>
        <div className="mt-4 max-w-[36px] text-center text-[11px] leading-5 text-slate-500">{node ? '属性' : '面板'}</div>
      </aside>
    )
  }

  if (!node) {
    return (
      <aside className="flex w-[360px] flex-col border-l border-slate-800 bg-slate-950/95 px-5 py-6">
        <div className="mb-4 flex justify-end">
          <button onClick={onToggleCollapse} className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white">
            收起
          </button>
        </div>
        <div className="rounded-3xl border border-slate-800 bg-slate-900/60 p-5">
          <div className="text-[11px] uppercase tracking-[0.28em] text-slate-500">属性面板</div>
          <div className="mt-3 text-base font-semibold text-slate-100">请选择一个节点</div>
          <div className="mt-2 text-sm leading-6 text-slate-400">右侧会显示当前节点的内容、提示词、版本控制和快捷生成操作。</div>
        </div>
      </aside>
    )
  }

  const incoming = document.edges.filter((edge) => edge.target === node.id)
  const outgoing = document.edges.filter((edge) => edge.source === node.id)
  const adoptedForShot = node.data.shotId
    ? Object.entries(document.adoptedVersions).flatMap(([kind, entries]) =>
        Object.entries(entries ?? {})
          .filter(([shotId, adoptedNodeId]) => shotId === node.data.shotId && adoptedNodeId === node.id)
          .map(([shotId]) => `${kind}:${shotId}`),
      )
    : []
  const sourceLabel =
    node.data.metadata?.source === 'mock'
      ? 'Mock'
      : node.data.metadata?.source === 'real'
        ? '真实资产'
        : null
  const sequenceEntries = node.data.kind === 'sequence'
    ? buildSequenceEntries(document, document.nodes.filter((item) => item.data.kind === 'shot'))
    : []
  const production = node.data.ui?.production
  const nextStepGuide = getNextStepGuide(document, node)
  const referenceableAssets = assetNodes.filter((assetNode) => ['character', 'location', 'prop'].includes(assetNode.data.kind))
  const referencedAssetsForShot =
    node.data.shotId && (node.data.kind === 'shot' || (node.data.kind === 'image' && node.data.imageRole !== 'reference'))
      ? collectReferenceNodesForShot(document, node.data.shotId)
      : []
  const sourceAssetNode =
    typeof node.data.metadata?.sourceAssetId === 'string'
      ? document.nodes.find((item) => item.data.metadata?.assetId === node.data.metadata?.sourceAssetId) ?? null
      : null
  const referenceAssetCount =
    typeof node.data.metadata?.referenceAssetCount === 'number'
      ? node.data.metadata.referenceAssetCount
      : Array.isArray(node.data.metadata?.referenceAssetIds)
        ? node.data.metadata.referenceAssetIds.length
        : referencedAssetsForShot.length
  const shotVersions =
    node.data.kind === 'shot' && node.data.shotId
      ? collectShotVersions(document, node.data.shotId)
      : { images: [], videos: [], audios: [] }
  const canGenerateImage = getActionAvailability(document, node, 'image')
  const canGenerateVideo = mergeActionAvailability(
    getActionAvailability(document, node, 'video'),
    (node.data.kind === 'image' || node.data.kind === 'video') ? videoProfileBlockedReason : null,
  )
  const canGenerateAudio = getActionAvailability(document, node, 'audio')
  const reviewTargetShot =
    node.data.kind === 'shot'
      ? node
      : node.data.shotId
        ? document.nodes.find((item) => item.data.kind === 'shot' && item.data.shotId === node.data.shotId) ?? null
        : null
  const reviewState = reviewTargetShot ? getShotReviewState(document, reviewTargetShot) : null
  const siblingVersions =
    node.data.shotId && (node.data.kind === 'image' || node.data.kind === 'video' || node.data.kind === 'audio')
      ? document.nodes
          .filter(
            (item) =>
              item.data.kind === node.data.kind &&
              item.data.shotId === node.data.shotId &&
              item.data.imageRole === node.data.imageRole,
          )
          .sort(
            (left, right) =>
              (left.data.versionInfo?.version ?? 0) - (right.data.versionInfo?.version ?? 0) ||
              left.data.title.localeCompare(right.data.title, 'zh-Hans-CN'),
          )
      : []

  return (
    <aside className="flex w-[360px] flex-col border-l border-slate-800 bg-slate-950/95">
      <div className="flex items-start justify-between border-b border-slate-800 px-5 py-5">
        <div>
          <div className="text-[11px] uppercase tracking-[0.28em] text-slate-500">{kindText(node.data.kind)}</div>
          <div className="mt-2 text-lg font-semibold text-slate-100">{node.data.title}</div>
          <div className="mt-1 text-sm text-slate-400">{nodeStatusLabel(node.data)} · 输入 {incoming.length} · 输出 {outgoing.length}</div>
          {sourceLabel ? <div className="mt-1 text-[11px] text-slate-500">来源：{sourceLabel}</div> : null}
        </div>
        <div className="flex gap-2">
          <button onClick={onToggleCollapse} className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white">收起</button>
          <button onClick={() => onDuplicateNode(node.id)} className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white">复制</button>
          <button onClick={() => onDeleteNode(node.id)} className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-rose-500 hover:text-rose-200">删除</button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
        {node.data.previewUrl && <img src={node.data.previewUrl} alt={node.data.title} className="mb-5 h-44 w-full rounded-2xl border border-slate-800 object-cover" />}

        <PanelSection title="基础信息">
          <EditorField label="标题" value={node.data.title} onChange={(value) => onFieldChange('title', value)} />
          <EditorField label="摘要" value={node.data.summary} textarea onChange={(value) => onFieldChange('summary', value)} />
        </PanelSection>

        {node.data.kind === 'shot' && production && (
          <PanelSection title="生产状态">
            <div className="grid grid-cols-2 gap-2 text-sm text-slate-300">
              <StatusTile label="参考图完整度" value={production.referenceState ?? '待检查'} />
              <StatusTile label="分镜图状态" value={production.imageState ?? '待生成'} />
              <StatusTile label="视频状态" value={production.videoState ?? '待生成'} />
              <StatusTile label="成片序列" value={production.sequenceState ?? '未进入'} />
            </div>
            {production.riskHint ? (
              <div className="mt-3 rounded-2xl border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs leading-5 text-amber-100">
                {production.riskHint}
              </div>
            ) : null}
          </PanelSection>
        )}

        {typeof node.data.metadata?.runMode === 'string' && (
          <PanelSection title="任务状态">
            <div className="grid grid-cols-2 gap-2 text-sm text-slate-300">
              <StatusTile label="当前阶段" value={nodeStatusLabel(node.data)} />
              <StatusTile label="任务来源" value={node.data.metadata?.source === 'real' ? '真实任务' : node.data.metadata?.source === 'mock' ? 'Mock 分支' : '本地节点'} />
              <StatusTile label="当前模型" value={describeNodeModel(node)} />
              <StatusTile label="Provider" value={describeNodeProvider(node)} />
            </div>
            {typeof node.data.metadata?.taskId === 'string' ? (
              <div className="mt-3 rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs leading-5 text-slate-400">
                任务 ID：{node.data.metadata.taskId}
              </div>
            ) : null}
            {typeof node.data.metadata?.externalTaskId === 'string' && node.data.metadata.externalTaskId ? (
              <div className="mt-3 rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs leading-5 text-slate-400">
                外部任务 ID：{node.data.metadata.externalTaskId}
              </div>
            ) : null}
            {typeof node.data.metadata?.modelProfileId === 'string' && node.data.metadata.modelProfileId ? (
              <div className="mt-3 rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs leading-5 text-slate-400">
                模型配置：{node.data.metadata.modelProfileId}
              </div>
            ) : null}
            {typeof node.data.metadata?.externalStatus === 'string' && node.data.metadata.externalStatus ? (
              <div className="mt-3 rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs leading-5 text-slate-400">
                外部状态：{node.data.metadata.externalStatus}
                {typeof node.data.metadata?.pollAttempts === 'number' ? ` · 轮询次数：${node.data.metadata.pollAttempts}` : ''}
              </div>
            ) : null}
            {typeof node.data.metadata?.startedAt === 'string' ? (
              <div className="mt-3 rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs leading-5 text-slate-400">
                开始时间：{new Date(node.data.metadata.startedAt).toLocaleString()}
              </div>
            ) : null}
            {node.data.status === 'error' && node.data.errorMessage ? (
              <div className="mt-3 rounded-2xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs leading-5 text-red-100">
                失败原因：{node.data.errorMessage}
              </div>
            ) : null}
            {typeof node.data.metadata?.providerResponse === 'string' && node.data.metadata.providerResponse ? (
              <details className="mt-3 rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs leading-5 text-slate-400">
                <summary className="cursor-pointer list-none text-slate-300">Provider 返回详情</summary>
                <pre className="mt-2 overflow-x-auto whitespace-pre-wrap text-[11px] leading-5 text-slate-400">{node.data.metadata.providerResponse}</pre>
              </details>
            ) : null}
          </PanelSection>
        )}

        <PanelSection title="推荐下一步">
          <div
            className={`rounded-2xl border px-4 py-3 text-sm leading-6 ${
              nextStepGuide.tone === 'success'
                ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-100'
                : nextStepGuide.tone === 'warn'
                  ? 'border-amber-500/20 bg-amber-500/10 text-amber-100'
                  : 'border-slate-800 bg-slate-900/60 text-slate-300'
            }`}
          >
            <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">系统建议</div>
            <div className="mt-2 font-medium text-slate-100">{nextStepGuide.title}</div>
            <div className="mt-2 text-sm leading-6 text-inherit">{nextStepGuide.detail}</div>
          </div>
        </PanelSection>

        {reviewTargetShot && reviewState && reviewTargetShot.data.shotId && (
          <PanelSection title="审片状态">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-sm text-slate-300">
              <div className="flex items-center justify-between gap-3">
                <div>当前状态：<span className={reviewStatusClass(reviewState.status)}>{reviewStatusText(reviewState.status)}</span></div>
                {reviewState.reviewedAt ? (
                  <div className="text-xs text-slate-500">{new Date(reviewState.reviewedAt).toLocaleString()}</div>
                ) : null}
              </div>
              <div className="mt-2 text-xs leading-5 text-slate-500">
                这个状态会同步到左侧镜头列表和成片审片台，并在刷新后保留。
              </div>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <ActionButton label="标记通过" onClick={() => onUpdateShotReview(reviewTargetShot.data.shotId!, 'approved')} />
              <ActionButton label="暂时接受" muted onClick={() => onUpdateShotReview(reviewTargetShot.data.shotId!, 'accepted')} />
              <ActionButton label="需修改" onClick={() => onUpdateShotReview(reviewTargetShot.data.shotId!, 'changes_requested')} />
              <ActionButton label="重置未审片" muted onClick={() => onUpdateShotReview(reviewTargetShot.data.shotId!, 'pending', '')} />
            </div>
            <div className="mt-3">
              <EditorField
                label="审片备注"
                value={reviewState.note}
                textarea
                placeholder="填写审片修改意见，会同步进入问题清单，方便后续统一处理。"
                onChange={(value) => onUpdateShotReview(reviewTargetShot.data.shotId!, reviewState.status, value)}
              />
            </div>
          </PanelSection>
        )}

        <PanelSection title="提示词">
          <EditorField label="静态提示词" value={node.data.prompt} textarea onChange={(value) => onFieldChange('prompt', value)} />
          <EditorField label="补充说明 / 运动提示词" value={node.data.notes ?? ''} textarea onChange={(value) => onFieldChange('notes', value)} />
        </PanelSection>

        <PanelSection title="正文内容">
          <EditorField label="正文" value={node.data.content ?? ''} textarea onChange={(value) => onFieldChange('content', value)} />
        </PanelSection>

        <PanelSection title="工作流关系">
          <ConnectionList label="它引用了" edges={incoming} nodes={document.nodes} onSelectNode={onSelectNode} />
          <ConnectionList label="它将生成" edges={outgoing} nodes={document.nodes} onSelectNode={onSelectNode} source />
        </PanelSection>

        {(node.data.kind === 'image' || node.data.kind === 'video') && (node.data.metadata?.source === 'real' || node.data.metadata?.source === 'mock') && (
          <PanelSection title="任务与模型来源">
            <div className="space-y-2 text-sm text-slate-300">
              {typeof node.data.metadata?.assetId === 'string' && (
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-2">
                  资产 ID：{node.data.metadata.assetId}
                </div>
              )}
              <div className="grid grid-cols-2 gap-2">
                <StatusTile label="模型名称" value={describeNodeModel(node)} />
                <StatusTile label="模型类型" value={node.data.metadata?.usesMock ? 'Mock' : '真实'} />
                <StatusTile label="Provider" value={describeNodeProvider(node)} />
                <StatusTile label="版本时间" value={formatNodeTimestamp(node)} />
              </div>
              {node.data.metadata?.assetScope || node.data.metadata?.assetSubject ? (
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs leading-5 text-slate-400">
                  用途：
                  {describeNodeUsage(node)}
                </div>
              ) : null}
              <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs leading-5 text-slate-400">
                提示词摘要：{summarizePrompt(node.data.metadata?.prompt, node.data.prompt)}
              </div>
              {sourceAssetNode && (
                <button
                  onClick={() => onSelectNode(sourceAssetNode.id)}
                  className="flex w-full items-center justify-between rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-3 text-left transition hover:border-slate-600"
                >
                  <div>
                    <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">来源节点</div>
                    <div className="mt-1 text-sm text-slate-200">{sourceAssetNode.data.title}</div>
                  </div>
                  <div className="text-xs text-slate-500">{kindText(sourceAssetNode.data.kind)}</div>
                </button>
              )}
              {typeof node.data.metadata?.sourceNodeId === 'string' && node.data.metadata.sourceNodeId ? (
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs leading-5 text-slate-400">
                  上游节点：{node.data.metadata.sourceNodeId}
                  {typeof node.data.metadata?.sourceAssetId === 'string' && node.data.metadata.sourceAssetId ? ` · 上游资产 ${node.data.metadata.sourceAssetId}` : ''}
                </div>
              ) : null}
              {node.data.kind === 'video' && (
                <>
                  <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-2">
                    运动提示词：{node.data.prompt || '待补充'}
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <StatusTile label="参考图数量" value={String(referenceAssetCount)} />
                    <StatusTile label="时长" value={`${node.data.metadata?.durationSeconds ?? node.data.generation?.durationSeconds ?? 0} 秒`} />
                  </div>
                </>
              )}
            </div>
          </PanelSection>
        )}

        {referencedAssetsForShot.length > 0 && (
          <PanelSection title={node.data.kind === 'shot' ? '已关联参考图' : '生成所用参考图'}>
            <div className="space-y-2">
              {referencedAssetsForShot.map((assetNode) => (
                <button
                  key={assetNode.id}
                  onClick={() => onSelectNode(assetNode.id)}
                  className="flex w-full items-center justify-between rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-3 text-left transition hover:border-slate-600"
                >
                  <div>
                    <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
                      {assetNode.data.assetScope === 'character'
                        ? '人物参考图'
                        : assetNode.data.assetScope === 'location'
                          ? '场景参考图'
                          : '道具参考图'}
                    </div>
                    <div className="mt-1 text-sm text-slate-200">{assetNode.data.title}</div>
                  </div>
                  <div className="text-xs text-slate-500">{assetNode.data.assetSubject}</div>
                </button>
              ))}
            </div>
          </PanelSection>
        )}

        {node.data.kind === 'shot' && (
          <PanelSection title="资产引用">
            <div className="space-y-2">
              {referenceableAssets.map((assetNode) => {
                const linked = document.edges.some((edge) => edge.source === assetNode.id && edge.target === node.id)
                return (
                  <label key={assetNode.id} className="flex items-center justify-between rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-3 text-sm text-slate-200">
                    <div>
                      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{kindText(assetNode.data.kind)}</div>
                      <div className="mt-1">{assetNode.data.title}</div>
                    </div>
                    <input type="checkbox" checked={linked} onChange={(event) => onToggleReference(assetNode.id, node.id, event.target.checked)} className="h-4 w-4 accent-sky-400" />
                  </label>
                )
              })}
            </div>
          </PanelSection>
        )}

        {node.data.kind === 'shot' && (
          <PanelSection title="镜头版本">
            {document.adoptedVersions.video?.[node.data.shotId ?? ''] || shotVersions.images.some((item) => item.data.status === 'error') || shotVersions.videos.some((item) => item.data.status === 'error') ? (
              <div className="mb-3 grid grid-cols-2 gap-2">
                <ActionButton
                  label="取消当前采用视频"
                  onClick={() => {
                    const adoptedVideoId = document.adoptedVersions.video?.[node.data.shotId ?? '']
                    if (adoptedVideoId) onUnadoptVersion(adoptedVideoId)
                  }}
                  muted
                  disabled={!document.adoptedVersions.video?.[node.data.shotId ?? '']}
                  disabledReason="当前镜头还没有已采用的视频版本。"
                />
                <ActionButton
                  label="重试最近失败任务"
                  onClick={() => {
                    const failedVideo = shotVersions.videos.find((item) => item.data.status === 'error')
                    const failedImage = shotVersions.images.find((item) => item.data.status === 'error')
                    const target = failedVideo ?? failedImage
                    if (target) {
                      onSelectNode(target.id)
                      onRetryNode(target)
                    }
                  }}
                  muted
                  disabled={!shotVersions.images.some((item) => item.data.status === 'error') && !shotVersions.videos.some((item) => item.data.status === 'error')}
                  disabledReason="当前镜头没有失败中的分镜图或视频任务。"
                />
              </div>
            ) : null}
            <div className="mb-3 grid grid-cols-2 gap-2">
              <ActionButton
                label={shotVersions.images[0] ? '查看最新分镜图' : '暂无分镜图'}
                onClick={() => shotVersions.images[0] && onSelectNode(shotVersions.images[0].id)}
                muted={!shotVersions.images[0]}
                disabled={!shotVersions.images[0]}
                disabledReason="当前镜头还没有分镜图版本。"
              />
              <ActionButton
                label={shotVersions.videos[0] ? '查看最新视频' : '暂无视频'}
                onClick={() => shotVersions.videos[0] && onSelectNode(shotVersions.videos[0].id)}
                muted={!shotVersions.videos[0]}
                disabled={!shotVersions.videos[0]}
                disabledReason="当前镜头还没有视频版本。"
              />
            </div>
            <VersionJumpList
              title="分镜图版本"
              nodes={shotVersions.images}
              adoptedNodeId={document.adoptedVersions.image?.[node.data.shotId ?? '']}
              onSelectNode={onSelectNode}
            />
            <VersionJumpList
              title="视频版本"
              nodes={shotVersions.videos}
              adoptedNodeId={document.adoptedVersions.video?.[node.data.shotId ?? '']}
              onSelectNode={onSelectNode}
              onAdoptNode={onAdoptVersion}
            />
            <VersionJumpList
              title="音频版本"
              nodes={shotVersions.audios}
              adoptedNodeId={document.adoptedVersions.audio?.[node.data.shotId ?? '']}
              onSelectNode={onSelectNode}
            />
          </PanelSection>
        )}

        {(['character', 'location', 'prop', 'shot', 'image', 'video'] as CreativeNodeKind[]).includes(node.data.kind) && (
          <PanelSection title="生成操作">
            {videoProfileBlockedReason && (node.data.kind === 'image' || node.data.kind === 'video') ? (
              <div className="mb-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm leading-6 text-amber-100">
                当前视频默认配置暂不可直接生产：{videoProfileBlockedReason}
              </div>
            ) : null}
            {node.data.status === 'error' && (node.data.kind === 'image' || node.data.kind === 'video') && (
              <div className="mb-3 grid grid-cols-1 gap-2">
                <ActionButton label="重试当前任务" onClick={() => onRetryNode(node)} />
              </div>
            )}
            {['character', 'location', 'prop'].includes(node.data.kind) && (
              <div className="space-y-3">
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-sm leading-6 text-slate-300">
                  当前节点属于参考资产层。生成后的真实参考图会回填到相关镜头的引用关系中。
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <ActionButton
                    label="生成参考图"
                    onClick={() => onGenerateFromNode(node, 'image')}
                    disabled={!canGenerateImage.enabled}
                    disabledReason={canGenerateImage.reason}
                  />
                  <ActionButton
                    label={referenceLayerVisible ? '参考资产层已展开' : '展开参考资产层'}
                    onClick={onShowReferenceLayer}
                    muted={referenceLayerVisible}
                  />
                </div>
              </div>
            )}
            {node.data.kind === 'shot' && (
              <div className="grid grid-cols-2 gap-2">
                <ActionButton
                  label="生成图片"
                  onClick={() => onGenerateFromNode(node, 'image')}
                  disabled={!canGenerateImage.enabled}
                  disabledReason={canGenerateImage.reason}
                />
                <ActionButton label="模拟图片失败" muted onClick={() => onGenerateFromNode(node, 'image', true)} />
                <ActionButton
                  label="生成音频"
                  onClick={() => onGenerateFromNode(node, 'audio')}
                  disabled={!canGenerateAudio.enabled}
                  disabledReason={canGenerateAudio.reason}
                />
              </div>
            )}
            {node.data.kind === 'image' && node.data.imageRole !== 'reference' && (
              <div className="grid grid-cols-2 gap-2">
                <ActionButton
                  label="生成视频"
                  onClick={() => onGenerateFromNode(node, 'video')}
                  disabled={!canGenerateVideo.enabled}
                  disabledReason={canGenerateVideo.reason}
                />
                <ActionButton label="模拟重试失败" muted onClick={() => onGenerateFromNode(node, 'video', true)} />
              </div>
            )}
            {node.data.kind === 'video' && (
              <div className="grid grid-cols-2 gap-2">
                <ActionButton
                  label="生成新视频分支"
                  onClick={() => onGenerateFromNode(node, 'video')}
                  disabled={!canGenerateVideo.enabled}
                  disabledReason={canGenerateVideo.reason}
                />
                <ActionButton label="采用当前版本" onClick={() => onAdoptVersion(node.id)} />
              </div>
            )}
            {((node.data.kind === 'shot' && (!canGenerateImage.enabled || !canGenerateAudio.enabled)) ||
              ((node.data.kind === 'image' || node.data.kind === 'video' || ['character', 'location', 'prop'].includes(node.data.kind)) &&
                (!canGenerateImage.enabled || !canGenerateVideo.enabled))) && (
              <div className="mt-3 space-y-2">
                {!canGenerateImage.enabled && canGenerateImage.reason ? (
                  <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs leading-5 text-slate-400">
                    图片相关操作暂不可用：{canGenerateImage.reason}
                  </div>
                ) : null}
                {!canGenerateVideo.enabled && canGenerateVideo.reason ? (
                  <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs leading-5 text-slate-400">
                    视频相关操作暂不可用：{canGenerateVideo.reason}
                  </div>
                ) : null}
                {!canGenerateAudio.enabled && canGenerateAudio.reason ? (
                  <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs leading-5 text-slate-400">
                    音频相关操作暂不可用：{canGenerateAudio.reason}
                  </div>
                ) : null}
              </div>
            )}
          </PanelSection>
        )}

        {(node.data.kind === 'image' || node.data.kind === 'video' || node.data.kind === 'audio') && node.data.shotId && node.data.imageRole !== 'reference' && (
          <PanelSection title="版本管理">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-sm text-slate-300">
              <div>{node.data.versionInfo?.label ?? '草稿'} / 镜头 {node.data.shotId}</div>
              <div className="mt-2 text-xs text-slate-500">
                生成时间：{node.data.versionInfo?.createdAt ? new Date(node.data.versionInfo.createdAt).toLocaleString() : '未知'}
              </div>
              <div className="mt-1 text-xs text-slate-500">
                来源：{sourceLabel ?? '本地分支'}{node.data.versionInfo?.sourceNodeId ? ` / 上游 ${node.data.versionInfo.sourceNodeId}` : ''}
              </div>
              <div className="mt-1 text-xs text-slate-500">
                采用状态：{adoptedForShot.length > 0 ? '当前采用中' : '未采用'}
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <ActionButton label="采用版本" onClick={() => onAdoptVersion(node.id)} />
              {adoptedForShot.length > 0 ? (
                <ActionButton label="取消采用" muted onClick={() => onUnadoptVersion(node.id)} />
              ) : null}
              <ActionButton label="复制版本信息" muted onClick={() => onCopyVersionInfo(node)} />
              {adoptedForShot.length > 0 && <ActionButton label="当前已采用" muted onClick={() => undefined} />}
            </div>
            <div className="mt-3 space-y-2">
              {siblingVersions.map((versionNode) => {
                const adopted = versionNode.id === (document.adoptedVersions[versionNode.data.kind as VersionKind]?.[versionNode.data.shotId ?? ''] ?? '')
                return (
                  <button
                    key={versionNode.id}
                    onClick={() => onSelectNode(versionNode.id)}
                    className={`flex w-full items-center justify-between rounded-2xl border px-3 py-3 text-left transition ${
                      versionNode.id === node.id
                        ? 'border-sky-400/40 bg-sky-500/10'
                        : 'border-slate-800 bg-slate-900/60 hover:border-slate-600'
                    }`}
                  >
                    <div>
                      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
                        {versionNode.data.versionInfo?.label ?? '草稿'}
                      </div>
                      <div className="mt-1 text-sm text-slate-200">{versionNode.data.title}</div>
                      <div className="mt-1 text-xs text-slate-500">
                        {versionNode.data.versionInfo?.createdAt ? new Date(versionNode.data.versionInfo.createdAt).toLocaleString() : '未知时间'}
                      </div>
                    </div>
                    <div className={`rounded-full px-2 py-1 text-[11px] ${adopted ? 'bg-emerald-500/12 text-emerald-200' : 'bg-slate-800 text-slate-400'}`}>
                      {adopted ? '已采用' : nodeStatusLabel(versionNode.data)}
                    </div>
                  </button>
                )
              })}
            </div>
          </PanelSection>
        )}

        {node.data.kind === 'sequence' && (
          <PanelSection title="成片汇总">
            <div className="mb-3 grid grid-cols-2 gap-2">
              <StatusTile label="已入成片" value={`${sequenceEntries.filter((entry) => entry.status === 'adopted').length}`} />
              <StatusTile label="待补镜头" value={`${sequenceEntries.filter((entry) => entry.status === 'missing').length}`} />
            </div>
            <div className="space-y-2">
              {sequenceEntries.map(({ shotId, adoptedNode }) => (
                <button key={shotId} onClick={() => onSelectNode(adoptedNode?.id ?? `shot-${shotId}`)} className="flex w-full items-center justify-between rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-left transition hover:border-slate-600">
                  <div>
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-500">镜头 {shotId}</div>
                    <div className="mt-1 text-sm text-slate-200">{adoptedNode?.data.title ?? '暂无采用视频'}</div>
                  </div>
                  <div className={`text-[11px] uppercase tracking-[0.18em] ${adoptedNode ? 'text-emerald-300' : 'text-amber-300'}`}>
                    {adoptedNode ? '已采用' : '待补齐'}
                  </div>
                </button>
              ))}
            </div>
          </PanelSection>
        )}
      </div>
    </aside>
  )
}

function NoticeBanner({ notice, onDismiss }: { notice: Notice; onDismiss: () => void }) {
  const toneClass = notice.tone === 'success'
    ? 'border-emerald-500/30 bg-emerald-500/12 text-emerald-100'
    : notice.tone === 'error'
      ? 'border-red-500/30 bg-red-500/12 text-red-100'
      : 'border-slate-600/60 bg-slate-900/85 text-slate-100'

  return (
    <div className={`flex items-center gap-3 rounded-full border px-4 py-2 text-sm shadow-[0_14px_40px_rgba(2,6,23,0.35)] ${toneClass}`}>
      <span>{notice.message}</span>
      <button onClick={onDismiss} className="text-xs uppercase tracking-[0.18em] text-slate-300">
        关闭
      </button>
    </div>
  )
}

function PreviewModal({
  projectTitle,
  episodeTitle,
  document,
  entries,
  failedNodes,
  onClose,
  onSelectNode,
  onRetryNode,
  onUpdateShotReview,
}: {
  projectTitle: string
  episodeTitle: string
  document: CanvasDocument
  entries: SequenceEntry[]
  failedNodes: CreativeNode[]
  onClose: () => void
  onSelectNode: (nodeId: string) => void
  onRetryNode: (node: CreativeNode) => void
  onUpdateShotReview: (shotId: string, status: ReviewStatus, note?: string) => void
}) {
  const [filterMode, setFilterMode] = useState<'all' | 'problem' | 'unreviewed'>('all')
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const reviewedEntries = useMemo(() => {
    return entries.map((entry) => {
      const review = entry.shotNode ? getShotReviewState(document, entry.shotNode) : { status: 'pending' as ReviewStatus, note: '' }
      const failedHistory = failedNodes.some((node) => node.data.shotId === entry.shotId)
      const riskText = entry.shotNode ? getShotProductionState(document, entry.shotNode).riskHint : undefined
      const problem = entry.status === 'missing' || failedHistory || review.status === 'changes_requested'
      return {
        ...entry,
        review,
        failedHistory,
        riskText,
        problem,
      }
    }).filter((entry) => {
      if (filterMode === 'problem') return entry.problem
      if (filterMode === 'unreviewed') return entry.review.status === 'pending'
      return true
    })
  }, [document, entries, failedNodes, filterMode])

  return (
    <div
      className="absolute inset-0 z-50 flex items-center justify-center bg-slate-950/78 px-6 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="整集预览"
        className="relative max-h-[86vh] w-full max-w-5xl overflow-hidden rounded-[32px] border border-slate-800 bg-slate-950 shadow-[0_32px_120px_rgba(2,6,23,0.6)]"
        onClick={(event) => event.stopPropagation()}
      >
        <ModalCloseButton label="关闭成片审片台" text="关闭预览" onClick={onClose} />
        <div className="relative z-10 border-b border-slate-800 px-6 py-5 pr-24">
          <div>
            <div className="text-[11px] uppercase tracking-[0.28em] text-sky-300">成片审片台</div>
            <div className="mt-2 text-xl font-semibold text-slate-100">{projectTitle} / {episodeTitle}</div>
            <div className="mt-2 text-sm text-slate-400">按镜头顺序审看当前成片，检查采用视频、风险、失败历史和审片结论。</div>
          </div>
        </div>
        <div className="grid max-h-[calc(86vh-88px)] grid-cols-[1.4fr,0.9fr] gap-0 overflow-hidden">
          <div className="min-h-0 overflow-y-auto border-r border-slate-800 px-6 py-5">
            <div className="mb-4 flex flex-wrap gap-2">
              {[
                ['all', '全部镜头'],
                ['problem', '只看问题镜头'],
                ['unreviewed', '只看未审片镜头'],
              ].map(([mode, label]) => (
                <button
                  key={mode}
                  onClick={() => setFilterMode(mode as 'all' | 'problem' | 'unreviewed')}
                  className={`rounded-full px-3 py-1.5 text-xs transition ${
                    filterMode === mode
                      ? 'bg-slate-100 text-slate-950'
                      : 'border border-slate-700 text-slate-300 hover:border-slate-500'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="mb-4 text-[11px] uppercase tracking-[0.24em] text-slate-500">成片序列</div>
            <div className="space-y-3">
              {reviewedEntries.length === 0 ? (
                <div className="rounded-3xl border border-slate-800 bg-slate-900/60 px-5 py-6 text-sm text-slate-400">
                  当前筛选条件下没有镜头可显示。
                </div>
              ) : (
                reviewedEntries.map(({ shotId, adoptedNode, shotNode, review, failedHistory, riskText, problem }, index) => (
                  <button
                    key={`${shotId}-${adoptedNode?.id ?? 'empty'}`}
                    onClick={() => onSelectNode(adoptedNode?.id ?? shotNode?.id ?? `shot-${shotId}`)}
                    className="flex w-full gap-4 rounded-3xl border border-slate-800 bg-slate-900/60 p-4 text-left transition hover:border-slate-600"
                  >
                    {adoptedNode?.data.previewUrl ? (
                      <img
                        src={adoptedNode.data.previewUrl}
                        alt={adoptedNode.data.title}
                        className="h-24 w-40 shrink-0 rounded-2xl border border-slate-800 object-cover"
                      />
                    ) : (
                      <div className="flex h-24 w-40 shrink-0 items-center justify-center rounded-2xl border border-dashed border-slate-800 bg-slate-900/60 text-xs leading-5 text-slate-500">
                        未生成或未采用视频
                      </div>
                    )}
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-sky-500/15 text-sm font-semibold text-sky-200">
                      {index + 1}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">镜头 {shotId}</div>
                      <div className="mt-1 text-base font-semibold text-slate-100">{adoptedNode?.data.title ?? '暂无采用视频'}</div>
                      <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-400">
                        {adoptedNode?.data.generation?.model ? (
                          <span className="rounded-full border border-slate-700 px-2 py-1">{adoptedNode.data.generation.model}</span>
                        ) : null}
                        {adoptedNode?.data.metadata?.durationSeconds || adoptedNode?.data.generation?.durationSeconds ? (
                          <span className="rounded-full border border-slate-700 px-2 py-1">
                            {adoptedNode.data.metadata?.durationSeconds ?? adoptedNode.data.generation?.durationSeconds} 秒
                          </span>
                        ) : null}
                        {Array.isArray(adoptedNode?.data.metadata?.referenceAssetIds) ? (
                          <span className="rounded-full border border-slate-700 px-2 py-1">
                            参考图 {adoptedNode?.data.metadata?.referenceAssetIds.length}
                          </span>
                        ) : null}
                        <span className="rounded-full border border-slate-700 px-2 py-1">
                          审片 {reviewStatusText(review.status)}
                        </span>
                        {failedHistory ? <span className="rounded-full border border-red-500/30 px-2 py-1 text-red-200">有失败历史</span> : null}
                        {problem ? <span className="rounded-full border border-amber-500/30 px-2 py-1 text-amber-200">问题镜头</span> : null}
                      </div>
                      <div className="mt-2 text-sm text-slate-400">
                        {adoptedNode?.data.prompt || adoptedNode?.data.summary || '这个镜头还没有可用于预览的已采用视频，请先生成视频并采用。'}
                      </div>
                      {riskText ? (
                        <div className="mt-2 text-xs leading-5 text-slate-500">{riskText}</div>
                      ) : null}
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          onClick={(event) => {
                            event.stopPropagation()
                            onUpdateShotReview(shotId, 'approved')
                          }}
                          className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-950 transition hover:bg-white"
                        >
                          通过
                        </button>
                        <button
                          onClick={(event) => {
                            event.stopPropagation()
                            onUpdateShotReview(shotId, 'accepted')
                          }}
                          className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
                        >
                          暂时接受
                        </button>
                        <button
                          onClick={(event) => {
                            event.stopPropagation()
                            onUpdateShotReview(shotId, 'changes_requested')
                          }}
                          className="rounded-full border border-amber-500/40 px-3 py-1.5 text-xs text-amber-200 transition hover:border-amber-400"
                        >
                          需修改
                        </button>
                      </div>
                    </div>
                    <div className={`shrink-0 rounded-full border px-3 py-1 text-[11px] uppercase tracking-[0.18em] ${
                      adoptedNode
                        ? 'border-emerald-500/30 bg-emerald-500/12 text-emerald-200'
                        : 'border-amber-500/30 bg-amber-500/12 text-amber-200'
                    }`}>
                      {adoptedNode ? '已采用' : '缺视频'}
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>
          <div className="min-h-0 overflow-y-auto px-6 py-5">
            <div className="mb-4 text-[11px] uppercase tracking-[0.24em] text-slate-500">失败队列</div>
            <div className="space-y-3">
              {failedNodes.length === 0 ? (
                <div className="rounded-3xl border border-emerald-500/20 bg-emerald-500/10 px-5 py-6 text-sm text-emerald-100">
                  当前没有失败任务，可以直接沿主链路继续生产。
                </div>
              ) : (
                failedNodes.map((node) => (
                  <div
                    key={node.id}
                    className="rounded-3xl border border-red-500/25 bg-red-500/8 p-4"
                  >
                    <button
                      onClick={() => onSelectNode(node.id)}
                      className="w-full text-left transition"
                    >
                      <div className="text-[11px] uppercase tracking-[0.2em] text-red-200">{kindText(node.data.kind)}</div>
                      <div className="mt-1 text-sm font-semibold text-slate-100">{node.data.title}</div>
                      <div className="mt-2 text-sm text-slate-300">{node.data.errorMessage ?? '任务失败，等待重试。'}</div>
                    </button>
                    <div className="mt-3 flex gap-2">
                      <button
                        onClick={() => onRetryNode(node)}
                        className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-950 transition hover:bg-white"
                      >
                        立即重试
                      </button>
                      <button
                        onClick={() => onSelectNode(node.id)}
                        className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
                      >
                        查看节点
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function EpisodeInspectionModal({
  projectTitle,
  episodeTitle,
  report,
  onBatchGenerateImages,
  onBatchGenerateVideos,
  onClose,
  onSelectShot,
}: {
  projectTitle: string
  episodeTitle: string
  report: EpisodeInspectionReport
  onBatchGenerateImages: () => void
  onBatchGenerateVideos: () => void
  onClose: () => void
  onSelectShot: (nodeId: string) => void
}) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div
      className="absolute inset-0 z-50 flex items-center justify-center bg-slate-950/78 px-6 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="本集检查"
        className="relative max-h-[86vh] w-full max-w-6xl overflow-hidden rounded-[32px] border border-slate-800 bg-slate-950 shadow-[0_32px_120px_rgba(2,6,23,0.6)]"
        onClick={(event) => event.stopPropagation()}
      >
        <ModalCloseButton label="关闭本集检查" text="关闭检查" onClick={onClose} />
        <div className="relative z-10 border-b border-slate-800 px-6 py-5 pr-24">
          <div>
            <div className="text-[11px] uppercase tracking-[0.28em] text-sky-300">本集检查</div>
            <div className="mt-2 text-xl font-semibold text-slate-100">{projectTitle} / {episodeTitle}</div>
            <div className="mt-2 text-sm text-slate-400">先定位缺图、缺视频、未采用和未入成片镜头，再继续整集批量生产。</div>
          </div>
        </div>
        <div className="grid max-h-[calc(86vh-88px)] grid-cols-[1fr,1.25fr] gap-0 overflow-hidden">
          <div className="min-h-0 overflow-y-auto border-r border-slate-800 px-6 py-5">
            <div className="grid grid-cols-2 gap-3">
              <StatusTile label="总镜头" value={String(report.totalShots)} />
              <StatusTile label="参考已覆盖" value={`${report.referencedShots}/${report.totalShots || 0}`} />
              <StatusTile label="已有分镜图" value={String(report.imageReadyShots)} />
              <StatusTile label="已有视频" value={String(report.videoReadyShots)} />
              <StatusTile label="已采用视频" value={String(report.adoptedVideoShots)} />
              <StatusTile label="已入成片" value={String(report.sequenceShots)} />
            </div>
            <div className={`mt-4 rounded-3xl border px-4 py-4 text-sm leading-6 ${
              report.exportReady
                ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-100'
                : 'border-amber-500/25 bg-amber-500/10 text-amber-100'
            }`}>
              <div className="text-[11px] uppercase tracking-[0.2em] text-current/80">整集结论</div>
              <div className="mt-2 font-medium">
                {report.exportReady ? '当前本集已经具备交付条件。' : '当前本集还不能交付，请先处理右侧问题列表。'}
              </div>
              <div className="mt-2 text-sm text-current/90">
                {report.exportReady
                  ? '所有镜头都已有采用视频并进入成片，当前没有失败任务或高风险镜头。'
                  : `仍有 ${report.missingImageShots.length} 个缺分镜图、${report.missingVideoShots.length} 个缺视频、${report.unadoptedVideoShots.length} 个未采用、${report.missingSequenceShots.length} 个未入成片。`}
              </div>
            </div>
          </div>
          <div className="min-h-0 overflow-y-auto px-6 py-5">
            <div className="space-y-5">
              <InspectionSection
                title="缺分镜图镜头"
                issues={report.missingImageShots}
                emptyText="所有镜头都已经有分镜图。"
                onSelectShot={onSelectShot}
                actionLabel="为缺分镜图镜头批量生成分镜图"
                actionHint="每个镜头会独立创建生成任务。即使参考图尚未补齐，也允许继续推进，但会保留一致性风险提示。"
                onAction={report.missingImageShots.length > 0 ? onBatchGenerateImages : undefined}
              />
              <InspectionSection
                title="缺视频镜头"
                issues={report.missingVideoShots}
                emptyText="所有镜头都已经有视频版本。"
                onSelectShot={onSelectShot}
                actionLabel="为缺视频镜头批量生成视频"
                actionHint="默认优先使用已采用分镜图；若当前镜头尚未采用分镜图，则使用最新已完成分镜图。成功后会沿用当前工作台的自动采用规则。"
                onAction={report.missingVideoShots.length > 0 ? onBatchGenerateVideos : undefined}
              />
              <InspectionSection
                title="未采用视频镜头"
                issues={report.unadoptedVideoShots}
                emptyText="当前所有有视频的镜头都已完成采用。"
                onSelectShot={onSelectShot}
              />
              <InspectionSection
                title="未进入成片镜头"
                issues={report.missingSequenceShots}
                emptyText="所有镜头都已经进入成片序列。"
                onSelectShot={onSelectShot}
              />
              <InspectionSection
                title="风险镜头"
                issues={report.riskShots}
                emptyText="当前没有检测到高风险镜头。"
                onSelectShot={onSelectShot}
                tone="warn"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function FailureTaskCenterModal({
  entries,
  onClose,
  onSelectNode,
  onRetryNode,
  onMarkHandled,
}: {
  entries: FailureTaskEntry[]
  onClose: () => void
  onSelectNode: (nodeId: string) => void
  onRetryNode: (nodeId: string) => void
  onMarkHandled: (nodeId: string) => void
}) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const activeEntries = entries.filter((entry) => !entry.handled)
  const handledEntries = entries.filter((entry) => entry.handled)

  return (
    <div
      className="absolute inset-0 z-50 flex items-center justify-center bg-slate-950/78 px-6 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="失败任务中心"
        className="relative max-h-[86vh] w-full max-w-5xl overflow-hidden rounded-[32px] border border-slate-800 bg-slate-950 shadow-[0_32px_120px_rgba(2,6,23,0.6)]"
        onClick={(event) => event.stopPropagation()}
      >
        <ModalCloseButton label="关闭失败任务中心" onClick={onClose} />
        <div className="relative z-10 border-b border-slate-800 px-6 py-5 pr-24">
          <div>
            <div className="text-[11px] uppercase tracking-[0.28em] text-red-300">失败任务中心</div>
            <div className="mt-2 text-xl font-semibold text-slate-100">集中查看、重试与处理失败任务</div>
            <div className="mt-2 text-sm text-slate-400">批量生产过程中出现的失败任务会集中展示在这里，刷新页面后仍能继续处理。</div>
          </div>
        </div>
        <div className="grid max-h-[calc(86vh-88px)] grid-cols-[1fr,1fr] gap-0 overflow-hidden">
          <div className="min-h-0 overflow-y-auto border-r border-slate-800 px-6 py-5">
            <div className="mb-4 flex items-center justify-between">
              <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">待处理失败</div>
              <div className="rounded-full bg-red-500/12 px-2 py-1 text-[11px] text-red-200">{activeEntries.length}</div>
            </div>
            {activeEntries.length === 0 ? (
              <div className="rounded-3xl border border-emerald-500/20 bg-emerald-500/10 px-5 py-6 text-sm text-emerald-100">
                当前没有待处理失败任务，可以继续整集生产。
              </div>
            ) : (
              <div className="space-y-3">
                {activeEntries.map((entry) => (
                  <FailureTaskCard
                    key={entry.nodeId}
                    entry={entry}
                    onSelectNode={onSelectNode}
                    onRetryNode={onRetryNode}
                    onMarkHandled={onMarkHandled}
                  />
                ))}
              </div>
            )}
          </div>
          <div className="min-h-0 overflow-y-auto px-6 py-5">
            <div className="mb-4 flex items-center justify-between">
              <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">已标记处理</div>
              <div className="rounded-full bg-slate-800 px-2 py-1 text-[11px] text-slate-400">{handledEntries.length}</div>
            </div>
            {handledEntries.length === 0 ? (
              <div className="rounded-3xl border border-slate-800 bg-slate-900/60 px-5 py-6 text-sm text-slate-400">
                还没有已处理的失败任务。
              </div>
            ) : (
              <div className="space-y-3">
                {handledEntries.map((entry) => (
                  <FailureTaskCard
                    key={entry.nodeId}
                    entry={entry}
                    onSelectNode={onSelectNode}
                    onRetryNode={onRetryNode}
                    onMarkHandled={onMarkHandled}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function FailureTaskCard({
  entry,
  onSelectNode,
  onRetryNode,
  onMarkHandled,
}: {
  entry: FailureTaskEntry
  onSelectNode: (nodeId: string) => void
  onRetryNode: (nodeId: string) => void
  onMarkHandled: (nodeId: string) => void
}) {
  return (
    <div className={`rounded-3xl border p-4 ${entry.handled ? 'border-slate-800 bg-slate-900/60' : 'border-red-500/25 bg-red-500/8'}`}>
      <button onClick={() => onSelectNode(entry.nodeId)} className="w-full text-left transition">
        <div className="flex items-center justify-between gap-3">
          <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">
            {kindText(entry.kind)}{entry.shotId ? ` · 镜头 ${entry.shotId}` : ''}
          </div>
          <div className={`rounded-full px-2 py-1 text-[11px] ${entry.handled ? 'bg-slate-800 text-slate-400' : 'bg-red-500/12 text-red-200'}`}>
            {entry.handled ? '已处理' : '待处理'}
          </div>
        </div>
        <div className="mt-1 text-sm font-semibold text-slate-100">{entry.title}</div>
        <div className="mt-2 text-sm leading-6 text-slate-300">{entry.errorMessage}</div>
        <div className="mt-2 text-xs text-slate-500">
          来源：{entry.sourceLabel}
          {entry.modelLabel ? ` · 模型 ${entry.modelLabel}` : ''}
          {entry.handledAt ? ` · 处理时间 ${new Date(entry.handledAt).toLocaleString()}` : ''}
        </div>
      </button>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          onClick={() => onRetryNode(entry.nodeId)}
          className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-950 transition hover:bg-white"
        >
          重试
        </button>
        <button
          onClick={() => onSelectNode(entry.nodeId)}
          className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
        >
          查看节点
        </button>
        {!entry.handled ? (
          <button
            onClick={() => onMarkHandled(entry.nodeId)}
            className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
          >
            标记已处理
          </button>
        ) : null}
      </div>
    </div>
  )
}

function ProblemQueueModal({
  entries,
  onClose,
  onSelectNode,
}: {
  entries: ProblemQueueEntry[]
  onClose: () => void
  onSelectNode: (nodeId: string) => void
}) {
  const [filter, setFilter] = useState<'all' | 'review' | 'system'>('all')

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const filteredEntries = entries.filter((entry) => {
    if (filter === 'review') return entry.type === 'review'
    if (filter === 'system') return entry.type !== 'review'
    return true
  })

  return (
    <div
      className="absolute inset-0 z-50 flex items-center justify-center bg-slate-950/78 px-6 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="问题清单"
        className="relative max-h-[86vh] w-full max-w-5xl overflow-hidden rounded-[32px] border border-slate-800 bg-slate-950 shadow-[0_32px_120px_rgba(2,6,23,0.6)]"
        onClick={(event) => event.stopPropagation()}
      >
        <ModalCloseButton label="关闭问题清单" onClick={onClose} />
        <div className="relative z-10 border-b border-slate-800 px-6 py-5 pr-24">
          <div>
            <div className="text-[11px] uppercase tracking-[0.28em] text-amber-300">问题清单</div>
            <div className="mt-2 text-xl font-semibold text-slate-100">人工审片问题与系统风险统一处理</div>
            <div className="mt-2 text-sm text-slate-400">这里会汇总需修改镜头、失败任务、风险镜头以及尚未进入成片的阻塞项。</div>
          </div>
        </div>
        <div className="min-h-0 overflow-y-auto px-6 py-5">
          <div className="mb-4 flex flex-wrap gap-2">
            {[
              ['all', '全部问题'],
              ['review', '人工问题'],
              ['system', '系统问题'],
            ].map(([mode, label]) => (
              <button
                key={mode}
                onClick={() => setFilter(mode as 'all' | 'review' | 'system')}
                className={`rounded-full px-3 py-1.5 text-xs transition ${
                  filter === mode
                    ? 'bg-slate-100 text-slate-950'
                    : 'border border-slate-700 text-slate-300 hover:border-slate-500'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {filteredEntries.length === 0 ? (
            <div className="rounded-3xl border border-emerald-500/20 bg-emerald-500/10 px-5 py-6 text-sm text-emerald-100">
              当前没有待处理问题，审片和交付流程可以继续推进。
            </div>
          ) : (
            <div className="space-y-3">
              {filteredEntries.map((entry) => (
                <div
                  key={entry.key}
                  className="rounded-3xl border border-slate-800 bg-slate-900/60 px-4 py-4 text-left transition hover:border-slate-600"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">
                      {entry.shotId ? `镜头 ${entry.shotId}` : '全局问题'} · {problemTypeText(entry.type)}
                    </div>
                    <div className={`rounded-full px-2 py-1 text-[11px] ${problemSeverityClass(entry.severity)}`}>
                      {problemSeverityText(entry.severity)}
                    </div>
                  </div>
                  <div className="mt-1 text-sm font-semibold text-slate-100">{entry.title}</div>
                  <div className="mt-2 text-sm leading-6 text-slate-400">{entry.detail}</div>
                  <div className="mt-2 text-xs text-slate-500">当前状态：{entry.statusLabel}</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <ActionButton
                      label="定位镜头"
                      onClick={() => entry.shotNodeId && onSelectNode(entry.shotNodeId)}
                      muted
                      disabled={!entry.shotNodeId}
                      disabledReason="当前问题没有对应的镜头节点。"
                    />
                    <ActionButton
                      label="查看问题"
                      onClick={() => entry.shotNodeId && onSelectNode(entry.shotNodeId)}
                      disabled={!entry.shotNodeId}
                      disabledReason="当前问题没有可查看的镜头节点。"
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ExportReadinessModal({
  report,
  checklist,
  onClose,
  onSelectNode,
  onCreateDeliveryRecord,
  onCopyChecklist,
}: {
  report: ExportReadinessReport
  checklist: DeliveryChecklistReport
  onClose: () => void
  onSelectNode: (nodeId: string) => void
  onCreateDeliveryRecord: () => void
  onCopyChecklist: (format: 'markdown' | 'json') => void
}) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div
      className="absolute inset-0 z-50 flex items-center justify-center bg-slate-950/78 px-6 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="导出前检查"
        className="relative max-h-[86vh] w-full max-w-5xl overflow-hidden rounded-[32px] border border-slate-800 bg-slate-950 shadow-[0_32px_120px_rgba(2,6,23,0.6)]"
        onClick={(event) => event.stopPropagation()}
      >
        <ModalCloseButton label="关闭导出前检查" onClick={onClose} />
        <div className="relative z-10 border-b border-slate-800 px-6 py-5 pr-24">
          <div>
            <div className="text-[11px] uppercase tracking-[0.28em] text-emerald-300">导出前检查</div>
            <div className="mt-2 text-xl font-semibold text-slate-100">{report.canExport ? '本集可导出 / 可交付' : '当前还不能导出'}</div>
            <div className="mt-2 text-sm text-slate-400">{report.summary}</div>
          </div>
        </div>
        <div className="grid max-h-[calc(86vh-88px)] grid-cols-[0.9fr,1.1fr] gap-0 overflow-hidden">
          <div className="min-h-0 overflow-y-auto border-r border-slate-800 px-6 py-5">
            <div className={`rounded-3xl border px-4 py-4 text-sm leading-6 ${
              report.canExport
                ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-100'
                : 'border-amber-500/25 bg-amber-500/10 text-amber-100'
            }`}>
              <div className="text-[11px] uppercase tracking-[0.2em] text-current/80">导出结论</div>
              <div className="mt-2 font-medium">{report.canExport ? '可以进入交付或发布流程。' : '请先清掉右侧问题，再进行导出。'}</div>
              <div className="mt-2 text-sm text-current/90">{report.sequenceCoverage}</div>
            </div>
            <div className="mt-4 rounded-3xl border border-slate-800 bg-slate-900/60 px-4 py-4">
              <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">交付清单</div>
              <div className="mt-3 grid grid-cols-2 gap-3">
                <StatusTile label="镜头总数" value={String(checklist.shotCount)} />
                <StatusTile label="已采用视频" value={String(checklist.adoptedVideoCount)} />
                <StatusTile label="总时长" value={`${checklist.totalDurationSeconds} 秒`} />
                <StatusTile
                  label="交付状态"
                  value={checklist.canDeliver ? '可交付' : '不可交付'}
                />
              </div>
              <div className="mt-3 text-sm leading-6 text-slate-400">
                {checklist.latestDeliveryLabel
                  ? `当前版本：${checklist.latestDeliveryLabel}${checklist.latestDeliveryStatus === 'stale' ? '（有变更）' : '（已交付）'}`
                  : '当前还没有创建交付版本。'}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  onClick={() => onCopyChecklist('markdown')}
                  className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
                >
                  复制 Markdown
                </button>
                <button
                  onClick={() => onCopyChecklist('json')}
                  className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
                >
                  复制 JSON
                </button>
                <button
                  onClick={onCreateDeliveryRecord}
                  disabled={!report.canExport}
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                    report.canExport
                      ? 'bg-emerald-400 text-slate-950 hover:brightness-110'
                      : 'cursor-not-allowed border border-slate-700 text-slate-500'
                  }`}
                >
                  导出本集
                </button>
              </div>
            </div>
          </div>
          <div className="min-h-0 overflow-y-auto px-6 py-5">
            <div className="mb-4 flex items-center justify-between">
              <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">阻塞与风险</div>
              <div className={`rounded-full px-2 py-1 text-[11px] ${report.canExport ? 'bg-emerald-500/12 text-emerald-200' : 'bg-amber-500/12 text-amber-200'}`}>
                {report.issues.length}
              </div>
            </div>
            <div className="mb-4 rounded-3xl border border-slate-800 bg-slate-900/60 px-4 py-4">
              <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">镜头交付清单</div>
              <div className="mt-3 space-y-2">
                {checklist.shots.map((shot) => (
                  <div key={shot.shotId} className="rounded-2xl border border-slate-800 bg-slate-950/60 px-3 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">镜头 {shot.shotId}</div>
                        <div className="mt-1 text-sm font-semibold text-slate-100">{shot.adoptedVideoTitle}</div>
                      </div>
                      <div className={`text-xs ${reviewStatusClass(shot.reviewStatus)}`}>{reviewStatusText(shot.reviewStatus)}</div>
                    </div>
                    <div className="mt-2 text-xs leading-5 text-slate-400">
                      {shot.shotTitle} · 参考图 {shot.referenceCount} · {shot.durationSeconds ?? 0} 秒
                    </div>
                    {shot.reviewNote ? <div className="mt-1 text-xs text-amber-200">备注：{shot.reviewNote}</div> : null}
                    {shot.riskHint ? <div className="mt-1 text-xs text-slate-500">{shot.riskHint}</div> : null}
                  </div>
                ))}
              </div>
            </div>
            {report.issues.length === 0 ? (
              <div className="rounded-3xl border border-emerald-500/20 bg-emerald-500/10 px-5 py-6 text-sm text-emerald-100">
                所有镜头都有采用视频，成片序列完整，当前没有失败任务，也没有待保存风险。
              </div>
            ) : (
              <div className="space-y-3">
                {report.issues.map((issue) => (
                  <button
                    key={issue.key}
                    onClick={() => issue.shotNodeId && onSelectNode(issue.shotNodeId)}
                    className="w-full rounded-3xl border border-slate-800 bg-slate-900/60 px-4 py-4 text-left transition hover:border-slate-600"
                  >
                    <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">{issue.shotNodeId ? '可跳转' : '全局检查'}</div>
                    <div className="mt-1 text-sm font-semibold text-slate-100">{issue.title}</div>
                    <div className="mt-2 text-sm leading-6 text-slate-400">{issue.detail}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function InspectionSection({
  title,
  issues,
  emptyText,
  onSelectShot,
  tone = 'default',
  actionLabel,
  actionHint,
  onAction,
}: {
  title: string
  issues: EpisodeInspectionIssue[]
  emptyText: string
  onSelectShot: (nodeId: string) => void
  tone?: 'default' | 'warn'
  actionLabel?: string
  actionHint?: string
  onAction?: () => void
}) {
  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">{title}</div>
        <div className={`rounded-full px-2 py-1 text-[11px] ${
          tone === 'warn'
            ? 'bg-amber-500/12 text-amber-200'
            : 'bg-slate-900 text-slate-400'
        }`}>
          {issues.length}
        </div>
      </div>
      {onAction && actionLabel ? (
        <div className="mb-3 rounded-3xl border border-slate-800 bg-slate-900/60 px-4 py-4">
          <button
            onClick={onAction}
            className="rounded-full bg-sky-400 px-4 py-2 text-xs font-semibold text-slate-950 transition hover:brightness-110"
          >
            {actionLabel}
          </button>
          {actionHint ? (
            <div className="mt-3 text-sm leading-6 text-slate-400">{actionHint}</div>
          ) : null}
        </div>
      ) : null}
      {issues.length === 0 ? (
        <div className="rounded-3xl border border-slate-800 bg-slate-900/60 px-4 py-4 text-sm text-slate-400">
          {emptyText}
        </div>
      ) : (
        <div className="space-y-2">
          {issues.map((issue) => (
            <button
              key={`${title}-${issue.shotNode.id}`}
              onClick={() => onSelectShot(issue.shotNode.id)}
              className={`w-full rounded-3xl border px-4 py-4 text-left transition ${
                tone === 'warn'
                  ? 'border-amber-500/20 bg-amber-500/8 hover:border-amber-400/40'
                  : 'border-slate-800 bg-slate-900/60 hover:border-slate-600'
              }`}
            >
              <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">镜头 {issue.shotId}</div>
              <div className="mt-1 text-sm font-semibold text-slate-100">{issue.title}</div>
              <div className="mt-2 text-sm leading-6 text-slate-400">{issue.detail}</div>
            </button>
          ))}
        </div>
      )}
    </section>
  )
}

function CanvasLegend({
  edgeVisibilityMode,
  selectedNode,
}: {
  edgeVisibilityMode: EdgeVisibilityMode
  selectedNode: CreativeNode | null
}) {
  return (
    <div className="w-[240px] rounded-3xl border border-slate-800/90 bg-slate-950/88 p-4 shadow-[0_16px_50px_rgba(2,6,23,0.35)] backdrop-blur">
      <div className="text-[11px] tracking-[0.24em] text-slate-400">画布图例</div>
      <div className="mt-3 space-y-2 text-xs text-slate-300">
        <LegendRow color="#f59e0b" label="实线：派生关系" />
        <LegendRow color="#64748b" label="虚线：引用关系" dashed />
        <LegendRow color="#22c55e" label="序列线：进入成片" />
      </div>
      <div className="mt-4 rounded-2xl border border-slate-800 bg-slate-900/70 px-3 py-2 text-xs leading-5 text-slate-400">
        {selectedNode
          ? `当前聚焦：${selectedNode.data.title}`
          : '当前未选中节点，点击左栏或画布节点可聚焦并联动高亮。'}
      </div>
      <div className="mt-2 text-[11px] text-slate-500">
        {edgeVisibilityMode === 'all' ? '当前显示全部引用线' : '当前仅显示聚焦镜头的引用线'}
      </div>
    </div>
  )
}

function LegendRow({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <span
        className="block h-px w-8 shrink-0"
        style={{
          background: dashed
            ? `repeating-linear-gradient(to right, ${color}, ${color} 5px, transparent 5px, transparent 9px)`
            : color,
        }}
      />
      <span>{label}</span>
    </div>
  )
}

function TutorialCard({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div className="pointer-events-none absolute left-6 top-6 max-w-[360px] rounded-[28px] border border-sky-500/20 bg-slate-950/92 p-5 shadow-[0_22px_90px_rgba(14,165,233,0.2)] backdrop-blur">
      <div className="pointer-events-auto">
        <div className="text-[11px] uppercase tracking-[0.28em] text-sky-300">新手引导</div>
        <div className="mt-3 text-lg font-semibold text-slate-100">像制片人一样推进这一集的创作</div>
        <div className="mt-3 space-y-2 text-sm leading-6 text-slate-300">
          <div>1. 先从左侧选中一个镜头，完善它的静态提示词或运动提示词。</div>
          <div>2. 生成一个或多个图片、视频分支，旧结果会保留为备选版本。</div>
          <div>3. 采用你满意的版本，再到成片序列节点里检查当前组装顺序。</div>
        </div>
        <button onClick={onDismiss} className="mt-4 rounded-full bg-sky-400 px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-950">
          开始使用
        </button>
      </div>
    </div>
  )
}

function ModalCloseButton({
  label,
  text = '关闭',
  onClick,
}: {
  label: string
  text?: string
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      className="absolute right-6 top-5 z-30 rounded-full border border-slate-700 bg-slate-950/95 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
    >
      {text}
    </button>
  )
}

function PanelSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-5">
      <div className="mb-3 text-[11px] uppercase tracking-[0.28em] text-slate-500">{title}</div>
      {children}
    </section>
  )
}

function ActionButton({
  label,
  onClick,
  muted,
  disabled,
  disabledReason,
}: {
  label: string
  onClick: () => void
  muted?: boolean
  disabled?: boolean
  disabledReason?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={disabled ? disabledReason : undefined}
      className={`rounded-2xl px-3 py-2 text-xs font-semibold transition ${
        disabled
          ? 'cursor-not-allowed border border-slate-800 bg-slate-900 text-slate-500'
          : muted
            ? 'border border-slate-700 bg-slate-900 text-slate-200 hover:border-slate-500'
            : 'bg-slate-100 text-slate-950 hover:bg-white'
      }`}
    >
      {label}
    </button>
  )
}

function StatusTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-3">
      <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">{label}</div>
      <div className="mt-1 text-sm text-slate-100">{value}</div>
    </div>
  )
}

function ConnectionList({
  label,
  edges,
  nodes,
  onSelectNode,
  source,
}: {
  label: string
  edges: CreativeEdge[]
  nodes: CreativeNode[]
  onSelectNode: (nodeId: string) => void
  source?: boolean
}) {
  return (
    <div className="mb-3">
      <div className="mb-2 text-xs text-slate-400">{label}</div>
      <div className="space-y-2">
        {edges.length === 0 && (
          <div className="rounded-2xl border border-dashed border-slate-800 px-3 py-3 text-xs text-slate-500">当前还没有关联。</div>
        )}
        {edges.map((edge) => {
          const linkedId = source ? edge.target : edge.source
          const linkedNode = nodes.find((node) => node.id === linkedId)
          const relationLabel = edge.data?.kind === 'reference' ? '引用' : edge.data?.kind === 'derived' ? '派生' : '序列'
          return (
            <button
              key={edge.id}
              onClick={() => linkedNode && onSelectNode(linkedNode.id)}
              className="flex w-full items-center justify-between rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-3 text-left transition hover:border-slate-600"
            >
              <div>
                <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">{relationLabel}</div>
                <div className="mt-1 text-sm text-slate-200">{linkedNode?.data.title ?? linkedId}</div>
              </div>
              <div className="text-xs text-slate-500">{linkedNode ? kindText(linkedNode.data.kind) : '缺失'}</div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function VersionJumpList({
  title,
  nodes,
  adoptedNodeId,
  onSelectNode,
  onAdoptNode,
}: {
  title: string
  nodes: CreativeNode[]
  adoptedNodeId?: string
  onSelectNode: (nodeId: string) => void
  onAdoptNode?: (nodeId: string) => void
}) {
  return (
    <div className="mb-3">
      <div className="mb-2 text-xs text-slate-400">{title}</div>
      <div className="space-y-2">
        {nodes.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-800 px-3 py-3 text-xs text-slate-500">当前还没有可用版本。</div>
        ) : (
          nodes.map((versionNode) => {
            const adopted = versionNode.id === adoptedNodeId
            return (
              <button
                key={versionNode.id}
                onClick={() => onSelectNode(versionNode.id)}
                aria-label={`打开${title}${versionNode.data.versionInfo?.label ?? versionNode.data.title}`}
                className="flex w-full items-center justify-between rounded-2xl border border-slate-800 bg-slate-900/60 px-3 py-3 text-left transition hover:border-slate-600"
              >
                <div>
                  <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
                    {versionNode.data.versionInfo?.label ?? '草稿'}
                  </div>
                  <div className="mt-1 text-sm text-slate-200">{versionNode.data.title}</div>
                </div>
                <div className="flex items-center gap-2">
                  {!adopted && onAdoptNode ? (
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation()
                        onAdoptNode(versionNode.id)
                      }}
                      aria-label={`采用${title}${versionNode.data.versionInfo?.label ?? versionNode.data.title}`}
                      className="rounded-full border border-slate-700 px-2 py-1 text-[11px] text-slate-200 transition hover:border-slate-500 hover:text-white"
                    >
                      采用
                    </button>
                  ) : null}
                  <div className={`rounded-full px-2 py-1 text-[11px] ${adopted ? 'bg-emerald-500/12 text-emerald-200' : 'bg-slate-800 text-slate-400'}`}>
                    {adopted ? '已采用' : nodeStatusLabel(versionNode.data)}
                  </div>
                </div>
              </button>
            )
          })
        )}
      </div>
    </div>
  )
}

function isReferenceLayerNode(node: CreativeNode) {
  return ['character', 'location', 'prop'].includes(node.data.kind) || node.data.imageRole === 'reference'
}

function collectShotVersions(document: CanvasDocument, shotId: string) {
  const sortVersions = (nodes: CreativeNode[]) =>
    [...nodes].sort(
      (left, right) =>
        (right.data.versionInfo?.version ?? 0) - (left.data.versionInfo?.version ?? 0) ||
        right.id.localeCompare(left.id, 'zh-Hans-CN'),
    )

  const allNodes = document.nodes.filter((node) => node.data.shotId === shotId)
  return {
    images: sortVersions(allNodes.filter((node) => node.data.kind === 'image' && node.data.imageRole !== 'reference')),
    videos: sortVersions(allNodes.filter((node) => node.data.kind === 'video')),
    audios: sortVersions(allNodes.filter((node) => node.data.kind === 'audio')),
  }
}

function buildSequenceEntries(document: CanvasDocument, shotNodes: CreativeNode[]): SequenceEntry[] {
  return [...shotNodes]
    .sort((left, right) => compareShotIdText(left.data.shotId ?? left.data.title, right.data.shotId ?? right.data.title))
    .map((shotNode) => {
      const shotId = shotNode.data.shotId ?? shotNode.id
      const adoptedNodeId = document.adoptedVersions.video?.[shotId]
      const adoptedNode = adoptedNodeId
        ? document.nodes.find((item) => item.id === adoptedNodeId) ?? null
        : null
      return {
        shotId,
        shotNode,
        adoptedNode,
        status: adoptedNode ? 'adopted' : 'missing',
      }
    })
}

export function buildEpisodeInspectionReport(
  document: CanvasDocument,
  shotNodes: CreativeNode[],
): EpisodeInspectionReport {
  const sortedShots = [...shotNodes].sort((left, right) =>
    compareShotIdText(left.data.shotId ?? left.data.title, right.data.shotId ?? right.data.title),
  )
  const failedTasks = document.nodes.filter((node) => node.data.status === 'error').length
  const issueLists = sortedShots.reduce<{
    missingImageShots: EpisodeInspectionIssue[]
    missingVideoShots: EpisodeInspectionIssue[]
    unadoptedVideoShots: EpisodeInspectionIssue[]
    missingSequenceShots: EpisodeInspectionIssue[]
    riskShots: EpisodeInspectionIssue[]
    referencedShots: number
    imageReadyShots: number
    videoReadyShots: number
    adoptedVideoShots: number
    sequenceShots: number
  }>((accumulator, shotNode) => {
    const shotId = shotNode.data.shotId ?? shotNode.id
    const production = getShotProductionState(document, shotNode)
    const versions = collectShotVersions(document, shotId)
    const hasReferences = production.referenceCount > 0
    const hasImage = versions.images.some((node) => node.data.status === 'done' || node.data.status === 'stale')
    const hasVideo = versions.videos.some((node) => node.data.status === 'done' || node.data.status === 'stale')
    const adoptedVideoId = document.adoptedVersions.video?.[shotId]
    const hasSequenceEdge = Boolean(
      adoptedVideoId &&
      document.edges.some(
        (edge) =>
          edge.source === adoptedVideoId &&
          edge.data?.kind === 'sequence' &&
          document.nodes.find((node) => node.id === edge.target)?.data.kind === 'sequence',
      ),
    )

    const createIssue = (detail: string): EpisodeInspectionIssue => ({
      shotId,
      shotNode,
      title: shotNode.data.title,
      detail,
    })

    if (hasReferences) accumulator.referencedShots += 1
    if (hasImage) accumulator.imageReadyShots += 1
    if (hasVideo) accumulator.videoReadyShots += 1
    if (adoptedVideoId) accumulator.adoptedVideoShots += 1
    if (hasSequenceEdge) accumulator.sequenceShots += 1

    if (!hasImage) {
      accumulator.missingImageShots.push(
        createIssue(
          production.referenceCount < 3
            ? `当前参考图完整度为 ${production.referenceCount}/3，建议先补齐参考资产，再生成分镜图。`
            : '当前镜头还没有分镜图版本，可直接进入分镜图生成队列。',
        ),
      )
    }
    if (!hasVideo) {
      accumulator.missingVideoShots.push(
        createIssue(
          hasImage
            ? '已有分镜图但还没有视频版本，可直接进入视频生成队列。'
            : '当前还没有可用视频，需先生成分镜图再继续生成视频。',
        ),
      )
    }
    if (hasVideo && !adoptedVideoId) {
      accumulator.unadoptedVideoShots.push(
        createIssue('当前镜头已有视频版本，但还没有采用版本，暂时不会进入成片序列。'),
      )
    }
    if (!hasSequenceEdge) {
      accumulator.missingSequenceShots.push(
        createIssue(
          adoptedVideoId
            ? '已有采用视频，但还没有正确接入成片序列，请检查序列连线。'
            : '当前镜头还没有进入成片序列，请先采用视频版本。',
        ),
      )
    }
    if ((production.referenceCount < 3 && (hasImage || hasVideo)) || production.imageState === '生成失败' || production.videoState === '生成失败') {
      accumulator.riskShots.push(
        createIssue(
          production.imageState === '生成失败' || production.videoState === '生成失败'
            ? '当前镜头存在失败任务，建议优先重试并确认输出质量。'
            : `参考图完整度仅 ${production.referenceCount}/3，但已继续生成下游内容，存在一致性风险。`,
        ),
      )
    }

    return accumulator
  }, {
    missingImageShots: [],
    missingVideoShots: [],
    unadoptedVideoShots: [],
    missingSequenceShots: [],
    riskShots: [],
    referencedShots: 0,
    imageReadyShots: 0,
    videoReadyShots: 0,
    adoptedVideoShots: 0,
    sequenceShots: 0,
  })

  return {
    totalShots: sortedShots.length,
    referencedShots: issueLists.referencedShots,
    imageReadyShots: issueLists.imageReadyShots,
    videoReadyShots: issueLists.videoReadyShots,
    adoptedVideoShots: issueLists.adoptedVideoShots,
    sequenceShots: issueLists.sequenceShots,
    failedTasks,
    missingImageShots: issueLists.missingImageShots,
    missingVideoShots: issueLists.missingVideoShots,
    unadoptedVideoShots: issueLists.unadoptedVideoShots,
    missingSequenceShots: issueLists.missingSequenceShots,
    riskShots: issueLists.riskShots,
    exportReady:
      sortedShots.length > 0 &&
      issueLists.missingVideoShots.length === 0 &&
      issueLists.unadoptedVideoShots.length === 0 &&
      issueLists.missingSequenceShots.length === 0 &&
      failedTasks === 0,
  }
}

export function buildFailureTaskEntries(document: CanvasDocument): FailureTaskEntry[] {
  return document.nodes
    .filter((node) => node.data.status === 'error')
    .map((node) => {
      const shotId = node.data.shotId ?? resolveReferenceShotId(document, node)
      const shotNode = shotId
        ? document.nodes.find((item) => item.data.kind === 'shot' && item.data.shotId === shotId) ?? null
        : null
      return {
        nodeId: node.id,
        kind: node.data.kind,
        title: node.data.title,
        shotId,
        shotNodeId: shotNode?.id,
        sourceLabel:
          node.data.metadata?.source === 'real'
            ? '真实任务'
            : node.data.metadata?.source === 'mock'
              ? 'Mock 分支'
              : '本地节点',
        modelLabel: describeNodeModel(node),
        errorMessage: node.data.errorMessage ?? '任务失败，等待重试。',
        handled: typeof node.data.metadata?.failureHandledAt === 'string',
        handledAt: typeof node.data.metadata?.failureHandledAt === 'string' ? node.data.metadata.failureHandledAt : undefined,
      }
    })
    .sort((left, right) => {
      if (left.handled !== right.handled) {
        return Number(left.handled) - Number(right.handled)
      }
      if (left.shotId && right.shotId && left.shotId !== right.shotId) {
        return compareShotIdText(left.shotId, right.shotId)
      }
      return left.title.localeCompare(right.title, 'zh-Hans-CN')
    })
}

export function buildExportReadinessReport({
  document,
  shotNodes,
  inspectionReport,
  failureTaskEntries,
  sequenceEntries,
  saveState,
}: {
  document: CanvasDocument
  shotNodes: CreativeNode[]
  inspectionReport: EpisodeInspectionReport
  failureTaskEntries: FailureTaskEntry[]
  sequenceEntries: SequenceEntry[]
  saveState: SaveState
}): ExportReadinessReport {
  const issues: ExportReadinessIssue[] = []

  inspectionReport.missingVideoShots.forEach((issue) => {
    issues.push({
      key: `missing-video-${issue.shotNode.id}`,
      title: `镜头 ${issue.shotId} 缺少采用视频`,
      detail: issue.detail,
      shotNodeId: issue.shotNode.id,
    })
  })

  inspectionReport.unadoptedVideoShots.forEach((issue) => {
    issues.push({
      key: `unadopted-video-${issue.shotNode.id}`,
      title: `镜头 ${issue.shotId} 还没有采用视频版本`,
      detail: issue.detail,
      shotNodeId: issue.shotNode.id,
    })
  })

  inspectionReport.missingSequenceShots.forEach((issue) => {
    issues.push({
      key: `missing-sequence-${issue.shotNode.id}`,
      title: `镜头 ${issue.shotId} 还未进入成片序列`,
      detail: issue.detail,
      shotNodeId: issue.shotNode.id,
    })
  })

  inspectionReport.riskShots.forEach((issue) => {
    issues.push({
      key: `risk-${issue.shotNode.id}`,
      title: `镜头 ${issue.shotId} 存在生产风险`,
      detail: issue.detail,
      shotNodeId: issue.shotNode.id,
    })
  })

  shotNodes.forEach((shotNode) => {
    const review = getShotReviewState(document, shotNode)
    if (review.status === 'pending' || review.status === 'changes_requested') {
      issues.push({
        key: `review-${shotNode.id}`,
        title: `镜头 ${shotNode.data.shotId ?? shotNode.data.title} 审片未完成`,
        detail:
          review.status === 'changes_requested'
            ? `该镜头当前被标记为需修改${review.note ? `：${review.note}` : '，需处理后再交付。'}`
            : '该镜头仍处于未审片状态，请先确认通过或暂时接受。',
        shotNodeId: shotNode.id,
      })
    }
  })

  failureTaskEntries.forEach((entry) => {
    issues.push({
      key: `failure-${entry.nodeId}`,
      title: `${kindText(entry.kind)}失败任务待处理`,
      detail: `${entry.title}：${entry.errorMessage}`,
      shotNodeId: entry.shotNodeId ?? entry.nodeId,
    })
  })

  if (saveState === 'saving') {
    issues.push({
      key: 'save-saving',
      title: '当前仍有保存中的本地变更',
      detail: '建议等待保存完成后再导出，避免导出检查与本地画布状态不一致。',
    })
  }

  if (saveState === 'error') {
    issues.push({
      key: 'save-error',
      title: '本地保存失败',
      detail: '请先处理保存失败问题，否则刷新后可能丢失当前采用状态或本地分支。',
    })
  }

  const adoptedCount = sequenceEntries.filter((entry) => entry.status === 'adopted').length
  const missingCount = sequenceEntries.filter((entry) => entry.status === 'missing').length
  const sequenceCoverage = missingCount === 0
    ? `当前成片序列已覆盖 ${adoptedCount}/${sequenceEntries.length} 个镜头。`
    : `当前成片序列仅覆盖 ${adoptedCount}/${sequenceEntries.length} 个镜头，仍缺 ${missingCount} 个镜头。`

  const canExport =
    inspectionReport.totalShots > 0 &&
    inspectionReport.exportReady &&
    failureTaskEntries.length === 0 &&
    shotNodes.every((shotNode) => {
      const status = getShotReviewState(document, shotNode).status
      return status === 'approved' || status === 'accepted'
    }) &&
    saveState === 'saved'

  return {
    canExport,
    summary: canExport
      ? '整集主链路已经闭环，可以进入交付或发布前的最终审阅。'
      : '当前仍有阻塞项，系统不会把这集标记为可导出。',
    sequenceCoverage,
    issues,
  }
}

export function buildProblemQueueEntries(
  document: CanvasDocument,
  shotNodes: CreativeNode[],
  inspectionReport: EpisodeInspectionReport,
  failureTaskEntries: FailureTaskEntry[],
): ProblemQueueEntry[] {
  const entries: ProblemQueueEntry[] = []

  shotNodes.forEach((shotNode) => {
    const review = getShotReviewState(document, shotNode)
    if (review.status === 'changes_requested') {
      entries.push({
        key: `review-${shotNode.id}`,
        shotId: shotNode.data.shotId,
        shotNodeId: shotNode.id,
        title: `${shotNode.data.title} 需要修改`,
        detail: review.note || '导演已将这个镜头标记为需修改，请回到镜头或视频节点继续调整。',
        type: 'review',
        severity: 'high',
        statusLabel: '需修改',
      })
    }
  })

  failureTaskEntries.forEach((entry) => {
    entries.push({
      key: `failure-${entry.nodeId}`,
      shotId: entry.shotId,
      shotNodeId: entry.shotNodeId ?? entry.nodeId,
      title: `${entry.title} 生成失败`,
      detail: entry.errorMessage,
      type: 'failure',
      severity: 'high',
      statusLabel: '待处理失败',
    })
  })

  inspectionReport.missingVideoShots.forEach((issue) => {
    entries.push({
      key: `missing-video-${issue.shotNode.id}`,
      shotId: issue.shotId,
      shotNodeId: issue.shotNode.id,
      title: `${issue.title} 缺少视频`,
      detail: issue.detail,
      type: 'missing_video',
      severity: 'high',
      statusLabel: '缺视频',
    })
  })

  inspectionReport.unadoptedVideoShots.forEach((issue) => {
    entries.push({
      key: `unadopted-video-${issue.shotNode.id}`,
      shotId: issue.shotId,
      shotNodeId: issue.shotNode.id,
      title: `${issue.title} 尚未采用视频`,
      detail: issue.detail,
      type: 'unadopted_video',
      severity: 'medium',
      statusLabel: '未采用',
    })
  })

  inspectionReport.missingSequenceShots.forEach((issue) => {
    entries.push({
      key: `missing-sequence-${issue.shotNode.id}`,
      shotId: issue.shotId,
      shotNodeId: issue.shotNode.id,
      title: `${issue.title} 尚未进入成片`,
      detail: issue.detail,
      type: 'missing_sequence',
      severity: 'medium',
      statusLabel: '未入成片',
    })
  })

  inspectionReport.riskShots.forEach((issue) => {
    entries.push({
      key: `risk-${issue.shotNode.id}`,
      shotId: issue.shotId,
      shotNodeId: issue.shotNode.id,
      title: `${issue.title} 存在风险`,
      detail: issue.detail,
      type: 'risk',
      severity: 'low',
      statusLabel: '风险提示',
    })
  })

  return entries.sort((left, right) => {
    const severityOrder = { high: 0, medium: 1, low: 2 }
    if (severityOrder[left.severity] !== severityOrder[right.severity]) {
      return severityOrder[left.severity] - severityOrder[right.severity]
    }
    if (left.shotId && right.shotId && left.shotId !== right.shotId) {
      return compareShotIdText(left.shotId, right.shotId)
    }
    return left.title.localeCompare(right.title, 'zh-Hans-CN')
  })
}

export function buildDeliveryChecklistReport({
  document,
  shotNodes,
  sequenceEntries,
  failureTaskEntries,
  inspectionReport,
  exportReadinessReport,
  failedNodes,
}: {
  document: CanvasDocument
  shotNodes: CreativeNode[]
  sequenceEntries: SequenceEntry[]
  failureTaskEntries: FailureTaskEntry[]
  inspectionReport: EpisodeInspectionReport
  exportReadinessReport: ExportReadinessReport
  failedNodes: CreativeNode[]
}): DeliveryChecklistReport {
  const latestDeliveryRecord = getLatestDeliveryRecord(document)
  const shots = shotNodes
    .slice()
    .sort((left, right) => compareShotIdText(left.data.shotId ?? left.id, right.data.shotId ?? right.id))
    .map((shotNode) => {
      const shotId = shotNode.data.shotId ?? shotNode.id
      const sequenceEntry = sequenceEntries.find((entry) => entry.shotId === shotId)
      const adoptedVideo = sequenceEntry?.adoptedNode
      const review = getShotReviewState(document, shotNode)
      const production = getShotProductionState(document, shotNode)
      return {
        shotId,
        shotTitle: shotNode.data.title,
        adoptedVideoTitle: adoptedVideo?.data.title ?? '缺视频',
        reviewStatus: review.status,
        reviewNote: review.note,
        durationSeconds:
          typeof adoptedVideo?.data.metadata?.durationSeconds === 'number'
            ? adoptedVideo.data.metadata.durationSeconds
            : adoptedVideo?.data.generation?.durationSeconds,
        referenceCount: production.referenceCount,
        hasFailureHistory: failedNodes.some((node) => node.data.shotId === shotId),
        riskHint: production.riskHint,
      }
    })

  return {
    projectTitle: document.projectTitle,
    episodeTitle: document.episodeTitle,
    shotCount: shotNodes.length,
    adoptedVideoCount: sequenceEntries.filter((entry) => entry.status === 'adopted').length,
    totalDurationSeconds: shots.reduce((sum, shot) => sum + (shot.durationSeconds ?? 0), 0),
    canDeliver: exportReadinessReport.canExport,
    blockedReasons: exportReadinessReport.issues.map((issue) => issue.title),
    riskSummary: inspectionReport.riskShots.map((issue) => `镜头 ${issue.shotId}：${issue.detail}`),
    failureSummary: failureTaskEntries.map((entry) => `${entry.title}：${entry.errorMessage}`),
    latestDeliveryLabel: latestDeliveryRecord?.versionLabel,
    latestDeliveryStatus: latestDeliveryRecord?.status,
    shots,
  }
}

function getNextStepGuide(document: CanvasDocument, node: CreativeNode): NextStepGuide {
  if (node.data.kind === 'sequence') {
    const entries = buildSequenceEntries(document, document.nodes.filter((item) => item.data.kind === 'shot'))
    const missingCount = entries.filter((entry) => entry.status === 'missing').length
    if (missingCount === 0) {
      return {
        title: '当前所有镜头都已进入成片序列。',
        detail: '可以直接播放整集预览，检查顺序、版本和节奏是否符合交付预期。',
        tone: 'success',
      }
    }
    return {
      title: `还有 ${missingCount} 个镜头未进入成片序列。`,
      detail: '请回到缺失镜头，先生成并采用视频版本；未采用的视频不会进入整集预览。',
      tone: 'warn',
    }
  }

  if (node.data.kind === 'shot') {
    const production = getShotProductionState(document, node)
    if (production.sequenceState === '已进入') {
      return {
        title: '这个镜头已经进入成片序列。',
        detail: '如果你还想迭代质量，可以再生成新版本视频，并重新采用更满意的版本。',
        tone: 'success',
      }
    }
    if (production.sequenceState === '待采用' || production.videoState === '已生成视频') {
      return {
        title: '下一步采用一个视频版本。',
        detail: '当前镜头已有可用视频，但还没有进入成片。请选择一个视频版本作为当前采用版本。',
      }
    }
    if (production.videoState === '生成中') {
      return {
        title: '视频任务正在处理中。',
        detail: '当前镜头的视频已经开始生成。你现在可以继续检查其他镜头，结果回填后再回来采用。',
      }
    }
    if (production.videoState === '生成失败') {
      return {
        title: '这个镜头的视频生成失败了。',
        detail: '请先查看失败原因并重试。失败记录会保留，不会污染当前成片序列。',
        tone: 'warn',
      }
    }
    if (production.imageState === '已生成图片') {
      return {
        title: '下一步生成视频。',
        detail: '分镜图已经就绪，可以从分镜图节点发起视频生成，再采用进入成片。',
      }
    }
    if (production.imageState === '生成中') {
      return {
        title: '分镜图任务正在处理中。',
        detail: '当前镜头的分镜图已经开始生成。等待回填后即可继续生成视频。',
      }
    }
    if (production.imageState === '生成失败') {
      return {
        title: '这个镜头的分镜图生成失败了。',
        detail: '先查看失败原因并重试分镜图生成，必要时调整提示词或参考资产。',
        tone: 'warn',
      }
    }
    if (production.referenceCount < 3) {
      return {
        title: '建议先补齐参考资产，再生成分镜图。',
        detail: `当前参考图完整度为 ${production.referenceCount}/3。也可以直接生成第一版分镜图，但角色、场景和道具的一致性风险会更高。`,
        tone: 'warn',
      }
    }
    return {
      title: '下一步生成分镜图。',
      detail: '当前镜头的参考资产已齐，可以直接生成首版分镜图，并继续推进到视频。',
    }
  }

  if (node.data.kind === 'image' && node.data.imageRole !== 'reference') {
    return {
      title: node.data.status === 'error' ? '这个分镜图生成失败，可直接重试。' : '下一步生成视频。',
      detail: node.data.status === 'error'
        ? (node.data.errorMessage ?? '保留失败记录，修正提示词后可重新发起视频生成。')
        : '从当前分镜图继续生成视频，生成多个版本后可选择一个采用并编入成片。',
      tone: node.data.status === 'error' ? 'warn' : 'info',
    }
  }

  if (node.data.kind === 'video') {
    const adoptedVideoId = node.data.shotId ? document.adoptedVersions.video?.[node.data.shotId] : undefined
    if (adoptedVideoId === node.id) {
      return {
        title: '当前视频已经是该镜头的采用版本。',
        detail: '你可以直接去成片序列检查顺序，也可以继续生成新的视频分支做版本比较。',
        tone: 'success',
      }
    }
    return {
      title: '下一步采用这个视频版本。',
      detail: '采用后它会替换该镜头当前进入成片序列的版本；旧版本不会被删除。',
    }
  }

  if (node.data.kind === 'character' || node.data.kind === 'location' || node.data.kind === 'prop') {
    return {
      title: '先为这个参考资产准备参考图。',
      detail: '生成出的参考图会回填到相关镜头，用于后续分镜图和视频生成，提高一致性。',
    }
  }

  return {
    title: '检查上下游关系后继续主链路。',
    detail: '优先补齐这个节点的输入，再继续生成下游结果，避免版本和依赖错位。',
  }
}

function nodeStatusLabel(data: CreativeNode['data']) {
  if (data.status === 'running' && data.metadata?.taskStage === 'queued') {
    return '排队中'
  }
  return statusLabel(data.status)
}

function getActionAvailability(document: CanvasDocument, node: CreativeNode, targetKind: VersionKind): ActionAvailability {
  if (node.data.status === 'running') {
    return { enabled: false, reason: '当前节点任务仍在进行中，请等待本次任务完成。' }
  }

  if (targetKind === 'audio') {
    if (node.data.kind === 'shot' && findRunningGenerationNode(document, node.id, 'audio')) {
      return { enabled: false, reason: '当前镜头已有音频任务在生成中，请等待完成后再继续。' }
    }
    return node.data.kind === 'shot'
      ? { enabled: true }
      : { enabled: false, reason: '只有镜头节点可以直接生成音频。' }
  }

  if (targetKind === 'image') {
    if (node.data.kind === 'shot') {
      if (findRunningGenerationNode(document, node.id, 'image')) {
        return { enabled: false, reason: '当前镜头已有分镜图任务在生成中，请先等待当前任务完成。' }
      }
      return { enabled: true }
    }
    if (node.data.kind === 'character' || node.data.kind === 'location' || node.data.kind === 'prop') {
      if (findRunningGenerationNode(document, node.id, 'image')) {
        return { enabled: false, reason: '当前参考资产已有参考图任务在生成中，请先等待当前任务完成。' }
      }
      return { enabled: true }
    }
    return { enabled: false, reason: '当前节点不能直接生成图片，请从镜头或参考资产节点发起。' }
  }

  if (targetKind === 'video') {
    if (node.data.kind === 'image' && node.data.imageRole !== 'reference') {
      if (findRunningGenerationNode(document, node.id, 'video')) {
        return { enabled: false, reason: '当前分镜图已有视频任务在生成中，请先等待当前任务完成。' }
      }
      return { enabled: true }
    }
    if (node.data.kind === 'video') {
      const sourceNodeId = node.data.versionInfo?.sourceNodeId
      if (sourceNodeId && findRunningGenerationNode(document, sourceNodeId, 'video')) {
        return { enabled: false, reason: '这条视频主线上已有新版本任务在生成中，请等待完成后再继续。' }
      }
      return sourceNodeId
        ? { enabled: true }
        : { enabled: false, reason: '这个视频缺少上游分镜图来源，暂时不能继续派生新视频分支。' }
    }
    return { enabled: false, reason: '只有分镜图或已有视频版本可以继续生成视频。' }
  }

  return { enabled: true }
}

function mergeActionAvailability(base: ActionAvailability, overrideReason?: string | null): ActionAvailability {
  if (overrideReason) {
    return { enabled: false, reason: overrideReason }
  }
  return base
}

function getShotProductionState(document: CanvasDocument, shotNode: CreativeNode) {
  const incomingReferenceNodes = document.edges
    .filter((edge) => edge.target === shotNode.id && edge.data?.kind === 'reference')
    .map((edge) => document.nodes.find((node) => node.id === edge.source))
    .filter(Boolean) as CreativeNode[]

  const hasCharacter = incomingReferenceNodes.some((node) => node.data.kind === 'character')
  const hasLocation = incomingReferenceNodes.some((node) => node.data.kind === 'location')
  const hasProp = incomingReferenceNodes.some((node) => node.data.kind === 'prop')
  const shotMediaNodes = document.nodes.filter((node) => node.data.shotId === shotNode.data.shotId)
  const storyboardImages = shotMediaNodes.filter((node) => node.data.kind === 'image' && node.data.imageRole !== 'reference')
  const shotVideos = shotMediaNodes.filter((node) => node.data.kind === 'video')
  const hasImage = storyboardImages.some((node) => node.data.status === 'done' || node.data.status === 'stale')
  const hasVideo = shotVideos.some((node) => node.data.status === 'done' || node.data.status === 'stale')
  const imageRunning = storyboardImages.some((node) => node.data.status === 'running')
  const imageError = storyboardImages.some((node) => node.data.status === 'error')
  const videoRunning = shotVideos.some((node) => node.data.status === 'running')
  const videoError = shotVideos.some((node) => node.data.status === 'error')
  const adoptedVideoId = shotNode.data.shotId ? document.adoptedVersions.video?.[shotNode.data.shotId] : undefined
  const hasSequence = Boolean(adoptedVideoId)

  const referenceCount = [hasCharacter, hasLocation, hasProp].filter(Boolean).length
  const referenceState = referenceCount === 3 ? '完整' : referenceCount > 0 ? `部分齐全 ${referenceCount}/3` : '不完整'
  const imageState = imageRunning
    ? '生成中'
    : imageError
      ? '生成失败'
      : hasImage
        ? '已生成图片'
        : shotNode.data.prompt
          ? '可生成'
          : '待补充'
  const videoState = videoRunning
    ? '生成中'
    : videoError
      ? '生成失败'
      : hasVideo
        ? '已生成视频'
        : hasImage || shotNode.data.notes
          ? '可生成'
          : '待补充'
  const sequenceState = hasSequence
    ? '已进入'
    : hasVideo
      ? '待采用'
      : '未进入'
  const riskHint = imageRunning || videoRunning
    ? '当前镜头有任务进行中，建议等待结果返回后再决定是否继续派生。'
    : imageError || videoError
      ? '当前镜头存在失败任务，建议先查看错误原因并重试。'
      : referenceCount === 3
        ? '参考资产已齐，可按推荐顺序继续生产。'
        : '参考图不完整，仍可继续生成，但会有一致性风险。'

  return {
    referenceCount,
    referenceState,
    imageState,
    videoState,
    sequenceState,
    riskHint,
  }
}

function getShotQuickAction({
  node,
  document,
  adoptedVersions,
  onSelectNode,
  onOpenPreview,
  onOpenFailureCenter,
}: {
  node: CreativeNode
  document: CanvasDocument
  adoptedVersions: CanvasDocument['adoptedVersions']
  onSelectNode: (nodeId: string) => void
  onOpenPreview: () => void
  onOpenFailureCenter: () => void
}) {
  const shotId = node.data.shotId ?? ''
  const review = getShotReviewState(document, node)
  const production = getShotProductionState(document, node)
  const imageVersions = document.nodes.filter((item) => item.data.kind === 'image' && item.data.shotId === shotId && item.data.imageRole !== 'reference')
  const videoVersions = document.nodes.filter((item) => item.data.kind === 'video' && item.data.shotId === shotId)
  const latestImage = imageVersions[imageVersions.length - 1]
  const latestVideo = videoVersions[videoVersions.length - 1]
  const adoptedVideoId = adoptedVersions.video?.[shotId]

  if (production.videoState === '生成失败' || production.imageState === '生成失败') {
    return {
      label: '查看失败任务',
      secondaryLabel: '打开镜头',
      onClick: onOpenFailureCenter,
    }
  }

  if (production.sequenceState === '已进入' && review.status === 'pending') {
    return {
      label: '进入审片台',
      secondaryLabel: '打开镜头',
      onClick: onOpenPreview,
    }
  }

  if ((production.sequenceState === '待采用' || production.videoState === '已生成视频') && (adoptedVideoId || latestVideo)) {
    return {
      label: '去采用视频',
      secondaryLabel: '打开镜头',
      onClick: () => onSelectNode(adoptedVideoId ?? latestVideo!.id),
    }
  }

  if (production.imageState === '已生成图片' && latestImage) {
    return {
      label: '去生成视频',
      secondaryLabel: '打开镜头',
      onClick: () => onSelectNode(latestImage.id),
    }
  }

  return {
    label: '去生成分镜图',
    secondaryLabel: '打开镜头',
    onClick: () => onSelectNode(node.id),
  }
}

function getShotReviewState(document: CanvasDocument, shotNode: CreativeNode): ShotReviewState {
  const statusValue = shotNode.data.metadata?.reviewStatus
  const status = statusValue === 'approved' || statusValue === 'changes_requested' || statusValue === 'accepted'
    ? statusValue
    : 'pending'
  const note = typeof shotNode.data.metadata?.reviewNote === 'string' ? shotNode.data.metadata.reviewNote : ''
  const reviewedAt = typeof shotNode.data.metadata?.reviewedAt === 'string' ? shotNode.data.metadata.reviewedAt : undefined
  return { status, note, reviewedAt }
}

function reviewStatusText(status: ReviewStatus) {
  switch (status) {
    case 'approved':
      return '通过'
    case 'changes_requested':
      return '需修改'
    case 'accepted':
      return '暂时接受'
    case 'pending':
    default:
      return '未审片'
  }
}

function reviewStatusClass(status: ReviewStatus) {
  switch (status) {
    case 'approved':
      return 'text-emerald-300'
    case 'changes_requested':
      return 'text-amber-300'
    case 'accepted':
      return 'text-sky-300'
    case 'pending':
    default:
      return 'text-slate-400'
  }
}

function problemTypeText(type: ProblemQueueEntry['type']) {
  switch (type) {
    case 'review':
      return '人工审片'
    case 'failure':
      return '失败任务'
    case 'risk':
      return '风险提示'
    case 'missing_video':
      return '缺视频'
    case 'unadopted_video':
      return '未采用'
    case 'missing_sequence':
      return '未入成片'
  }
}

function problemSeverityText(severity: ProblemQueueEntry['severity']) {
  switch (severity) {
    case 'high':
      return '高优先级'
    case 'medium':
      return '中优先级'
    case 'low':
      return '低优先级'
  }
}

function problemSeverityClass(severity: ProblemQueueEntry['severity']) {
  switch (severity) {
    case 'high':
      return 'bg-red-500/12 text-red-200'
    case 'medium':
      return 'bg-amber-500/12 text-amber-200'
    case 'low':
      return 'bg-slate-800 text-slate-400'
  }
}

function getLatestDeliveryRecord(document: CanvasDocument) {
  const records = document.deliveryRecords ?? []
  return records.length > 0 ? records[records.length - 1] : undefined
}

function markDeliveryRecordsStale(document: CanvasDocument): CanvasDocument {
  if (!document.deliveryRecords || document.deliveryRecords.length === 0) {
    return document
  }
  const hasDelivered = document.deliveryRecords.some((record) => record.status === 'delivered')
  if (!hasDelivered) {
    return document
  }
  return {
    ...document,
    deliveryRecords: document.deliveryRecords.map((record) => ({
      ...record,
      status: 'stale' as const,
    })),
  }
}

function formatDeliveryChecklistMarkdown(report: DeliveryChecklistReport) {
  const lines = [
    `# ${report.projectTitle} / ${report.episodeTitle} 交付清单`,
    '',
    `- 镜头总数：${report.shotCount}`,
    `- 已采用视频：${report.adoptedVideoCount}`,
    `- 总时长：${report.totalDurationSeconds} 秒`,
    `- 当前状态：${report.canDeliver ? '可交付' : '不可交付'}`,
    report.latestDeliveryLabel ? `- 当前交付版本：${report.latestDeliveryLabel}${report.latestDeliveryStatus === 'stale' ? '（有变更）' : ''}` : '- 当前交付版本：未创建',
    '',
    '## 镜头清单',
    ...report.shots.map((shot) => `- 镜头 ${shot.shotId}｜${shot.adoptedVideoTitle}｜审片 ${reviewStatusText(shot.reviewStatus)}${shot.reviewNote ? `｜备注：${shot.reviewNote}` : ''}`),
  ]

  if (report.blockedReasons.length > 0) {
    lines.push('', '## 阻塞原因', ...report.blockedReasons.map((item) => `- ${item}`))
  }
  if (report.riskSummary.length > 0) {
    lines.push('', '## 风险提示', ...report.riskSummary.map((item) => `- ${item}`))
  }
  if (report.failureSummary.length > 0) {
    lines.push('', '## 失败任务', ...report.failureSummary.map((item) => `- ${item}`))
  }

  return lines.join('\n')
}

function resolveReferenceShotId(document: CanvasDocument, node: CreativeNode) {
  const linkedShotEdge = document.edges.find((edge) => edge.source === node.id && edge.data?.kind === 'reference')
  if (!linkedShotEdge) {
    return undefined
  }
  const shotNode = document.nodes.find((item) => item.id === linkedShotEdge.target)
  return shotNode?.data.shotId
}

function collectReferenceAssetIds(document: CanvasDocument, node: CreativeNode) {
  const shotId = node.data.shotId ?? resolveReferenceShotId(document, node)
  if (!shotId) {
    return []
  }

  return Array.from(
    new Set(
      collectReferenceNodesForShot(document, shotId)
        .filter((item) => typeof item.data.metadata?.assetId === 'string')
        .map((item) => String(item.data.metadata?.assetId)),
    ),
  )
}

function findRunningGenerationNode(document: CanvasDocument, sourceNodeId: string, targetKind: VersionKind) {
  return document.nodes.find(
    (node) =>
      node.data.kind === targetKind &&
      node.data.status === 'running' &&
      node.data.versionInfo?.sourceNodeId === sourceNodeId,
  ) ?? null
}

function describeNodeModel(node: CreativeNode) {
  return String(node.data.metadata?.modelName || node.data.metadata?.model || node.data.generation?.model || '未记录')
}

function describeNodeProvider(node: CreativeNode) {
  return String(node.data.metadata?.provider || '未记录')
}

function formatNodeTimestamp(node: CreativeNode) {
  const raw =
    typeof node.data.metadata?.completedAt === 'string'
      ? node.data.metadata.completedAt
      : typeof node.data.metadata?.createdAt === 'string'
        ? node.data.metadata.createdAt
        : node.data.versionInfo?.createdAt
  return raw ? new Date(raw).toLocaleString() : '未知'
}

function summarizePrompt(primary: unknown, fallback?: string) {
  const text = typeof primary === 'string' && primary.trim()
    ? primary.trim()
    : fallback?.trim() || ''
  if (!text) {
    return '未记录'
  }
  return text.length > 80 ? `${text.slice(0, 80)}…` : text
}

function describeNodeUsage(node: CreativeNode) {
  if (node.data.imageRole === 'reference') {
    const scopeText =
      node.data.assetScope === 'character'
        ? '角色'
        : node.data.assetScope === 'location'
          ? '场景'
          : node.data.assetScope === 'prop'
            ? '道具'
            : '参考资产'
    return `${scopeText} / ${node.data.assetSubject ?? node.data.title}`
  }
  if (node.data.kind === 'image') {
    return `镜头分镜图 / ${node.data.shotId ?? node.data.title}`
  }
  if (node.data.kind === 'video') {
    return `镜头视频 / ${node.data.shotId ?? node.data.title}`
  }
  return node.data.assetSubject ?? node.data.title
}

function resolveGenerationPrompt(
  document: CanvasDocument,
  sourceNode: CreativeNode,
  targetKind: Extract<VersionKind, 'image' | 'video'>,
) {
  if (targetKind === 'video') {
    const shotNode = sourceNode.data.shotId
      ? document.nodes.find((item) => item.data.kind === 'shot' && item.data.shotId === sourceNode.data.shotId)
      : null
    return sourceNode.data.notes || shotNode?.data.notes || sourceNode.data.prompt || shotNode?.data.prompt || sourceNode.data.summary
  }

  return sourceNode.data.prompt || sourceNode.data.summary
}

function resolveGenerationDurationSeconds(
  document: CanvasDocument,
  sourceNode: CreativeNode,
  targetKind: Extract<VersionKind, 'image' | 'video'>,
) {
  if (targetKind !== 'video') {
    return sourceNode.data.generation?.durationSeconds
  }

  if (sourceNode.data.generation?.durationSeconds) {
    return sourceNode.data.generation.durationSeconds
  }

  const shotNode = sourceNode.data.shotId
    ? document.nodes.find((item) => item.data.kind === 'shot' && item.data.shotId === sourceNode.data.shotId)
    : null

  if (shotNode?.data.generation?.durationSeconds) {
    return shotNode.data.generation.durationSeconds
  }

  return typeof shotNode?.data.metadata?.duration === 'number'
    ? shotNode.data.metadata.duration
    : undefined
}

function resolveVideoGenerationSourceNode(document: CanvasDocument, node: CreativeNode) {
  if (node.data.kind !== 'video') {
    return node
  }

  const sourceNodeId = node.data.versionInfo?.sourceNodeId
  if (!sourceNodeId) {
    return null
  }

  const sourceNode = document.nodes.find((item) => item.id === sourceNodeId) ?? null
  return sourceNode?.data.kind === 'image' ? sourceNode : sourceNode
}

function resolvePreferredVideoSourceNode(document: CanvasDocument, shotNode: CreativeNode) {
  if (shotNode.data.kind !== 'shot' || !shotNode.data.shotId) {
    return null
  }

  const adoptedImageId = document.adoptedVersions.image?.[shotNode.data.shotId]
  const adoptedImageNode = adoptedImageId
    ? document.nodes.find(
        (node) =>
          node.id === adoptedImageId &&
          node.data.kind === 'image' &&
          node.data.imageRole !== 'reference' &&
          (node.data.status === 'done' || node.data.status === 'stale'),
      ) ?? null
    : null

  if (adoptedImageNode) {
    return adoptedImageNode
  }

  return collectShotVersions(document, shotNode.data.shotId).images.find(
    (node) => node.data.status === 'done' || node.data.status === 'stale',
  ) ?? null
}

function collectReferenceNodesForShot(document: CanvasDocument, shotId: string) {
  const shotNodeId = `shot-${shotId}`
  return document.nodes.filter(
    (item) =>
      item.data.imageRole === 'reference' &&
      document.edges.some((edge) => edge.source === item.id && edge.target === shotNodeId && edge.data?.kind === 'reference'),
  )
}

const UI_STATE_STORAGE_KEY = 'scene-composer-ui-v1'

function getSceneComposerStorageKey(scope: string) {
  return `scene-composer-document-v2:${scope}`
}

function loadInitialDocument(
  data: OutputsData,
  storageKey: string,
  options?: { episode?: number; projectTitle?: string },
): CanvasDocument {
  const fallback = () =>
    createRealEpisodeDocument(data, {
      episode: options?.episode,
      projectTitle: options?.projectTitle,
      episodeTitle: `第 ${options?.episode ?? 1} 集创作沙盒`,
    })
  const saved = localStorage.getItem(storageKey)
  if (!saved) {
    return fallback()
  }
  try {
    const document = deserializeDocument(saved)
    if (!isDocumentCompatible(document, options)) {
      return fallback()
    }
    return document
  } catch {
    return fallback()
  }
}

function isDocumentCompatible(
  document: CanvasDocument,
  options?: { episode?: number; projectTitle?: string },
) {
  if (options?.projectTitle && document.projectTitle !== options.projectTitle) {
    return false
  }

  if (options?.episode === undefined) {
    return true
  }

  const scriptNode = document.nodes.find((node) => node.data.kind === 'script')
  const scriptEpisode = scriptNode?.data.metadata?.episode
  if (typeof scriptEpisode === 'number' && scriptEpisode !== options.episode) {
    return false
  }

  if (typeof scriptEpisode === 'string' && Number(scriptEpisode) !== options.episode) {
    return false
  }

  return document.episodeTitle.includes(`第 ${options.episode} 集`)
}

function kindText(kind: CreativeNodeKind) {
  switch (kind) {
    case 'script':
      return '剧本'
    case 'shot':
      return '镜头'
    case 'character':
      return '角色'
    case 'location':
      return '场景'
    case 'prop':
      return '道具'
    case 'image':
      return '图片'
    case 'video':
      return '视频'
    case 'audio':
      return '音频'
    case 'sequence':
      return '成片序列'
  }
}

function sanitizeDocument(document: CanvasDocument): CanvasDocument {
  return {
    ...document,
    projectTitle: normalizeLegacyText(document.projectTitle) ?? document.projectTitle,
    episodeTitle: normalizeLegacyText(document.episodeTitle) ?? document.episodeTitle,
    nodes: document.nodes.map((node) => ({
      ...node,
      data: {
        ...node.data,
        title: normalizeLegacyText(node.data.title) ?? node.data.title,
        summary: normalizeLegacyText(node.data.summary) ?? node.data.summary,
        prompt: normalizeLegacyText(node.data.prompt) ?? node.data.prompt,
        notes: normalizeLegacyText(node.data.notes),
        content: normalizeLegacyText(node.data.content),
        errorMessage: normalizeLegacyText(node.data.errorMessage),
        versionInfo: node.data.versionInfo
          ? {
              ...node.data.versionInfo,
              label: normalizeLegacyText(node.data.versionInfo.label) ?? node.data.versionInfo.label,
            }
          : node.data.versionInfo,
      },
    })),
    edges: document.edges.map((edge) => ({
      ...edge,
      label: typeof edge.label === 'string' ? normalizeLegacyText(edge.label) : edge.label,
    })),
  }
}

function normalizeLegacyText(value?: string | number | boolean | null) {
  if (value === undefined || value === null) return undefined
  if (typeof value !== 'string') {
    return String(value)
  }
  if (!value) return value
  const replacements: Array<[string, string]> = [
    ['椤圭洰鍒楄〃', '项目列表'],
    ['瀵兼紨妯″紡', '内容准备'],
    ['鍘熷瀷', '分镜生产'],
    ['楂樼骇', '高级编排'],
    ['楂樼骇缂栬緫', '高级编排'],
    ['鍔犺浇椤圭洰鏁版嵁...', '加载项目数据...'],
    ['鍔犺浇澶辫触', '加载失败'],
    ['鏂板缓椤圭洰', '新建项目'],
    ['瑙嗛鐢熶骇绠＄嚎', '视频生产管线'],
    ['娴佺▼', '流程'],
    ['褰撳墠闆嗘暟', '当前集数'],
    ['绗?', '第 '],
    ['闆?', '集'],
    ['鍏ㄩ€?', '全选'],
    ['鍓ф湰鍑嗗', '内容准备'],
    ['鍒嗛暅鐢熶骇', '分镜生产'],
    ['瑙嗚璧勪骇', '视觉资产'],
    ['瀵煎嚭', '导出'],
    ['涓栫晫瑙?', '世界观'],
    ['鍓ф湰', '剧本'],
    ['鍒嗛暅鍥?', '分镜图'],
    ['瑙嗛', '视频'],
    ['瀵圭櫧 / 鐜闊?', '对白 / 环境音'],
    ['鎴愮墖搴忓垪', '成片序列'],
    ['鎴愮墖', '成片'],
    ['闀滃ご', '镜头'],
    ['鍦烘櫙', '场景'],
    ['鏈轰綅', '机位'],
    ['鏃堕暱', '时长'],
    ['绉?', '秒'],
    ['寰呰ˉ鍏?', '待补充'],
    ['寰呰ˉ鍏呭満鏅弿杩?', '待补充场景描述'],
    ['寰呰ˉ鍏呰鑹叉弿杩?', '待补充角色描述'],
    ['寰呰ˉ鍏呴亾鍏锋弿杩?', '待补充道具描述'],
    ['鍗曢泦鐭墽鍓ф湰涓庢湰闆嗗垱浣滅洰鏍囥€?', '单集短剧剧本与本集创作目标。'],
    ['褰撳墠闀滃ご鐨勯鐗堝垎闀滃浘鍊欓€夈€?', '当前镜头的首版分镜图候选。'],
    ['褰撳墠閲囩敤鐨勮繍鍔ㄧ増鏈€?', '当前采用的运动版本。'],
    ['鎸夊綋鍓嶉噰鐢ㄧ増鏈眹鎬荤殑闀滃ご瑙嗛涓庨煶棰戝簭鍒椼€?', '按当前采用版本汇总的镜头视频与音频序列。'],
    ['鐢ㄤ簬婕旂ず浜や粯椤哄簭鐨勬垚鐗囬瑙堢粍鍚堛€?', '用于演示交付顺序的成片预览组合。'],
    ['浠呮湰鍦?', '仅本地'],
  ]

  return replacements.reduce((current, [from, to]) => current.split(from).join(to), value)
}

function startFieldEdit(
  document: CanvasDocument,
  nodeId: string,
  field: 'title' | 'summary' | 'prompt' | 'content' | 'notes',
  value: string,
): CanvasDocument {
  return {
    ...document,
    nodes: document.nodes.map((node) => {
      if (node.id !== nodeId) {
        return node
      }
      return {
        ...node,
        data: {
          ...node.data,
          [field]: value,
          status: node.data.status === 'error' ? 'idle' : node.data.status,
        },
      }
    }),
  }
}

function collectRelatedNodeIds(document: CanvasDocument, nodeId: string): Set<string> {
  const related = new Set<string>([nodeId])
  const queue = [nodeId]

  while (queue.length > 0) {
    const current = queue.shift()!
    for (const edge of document.edges) {
      const next = edge.source === current ? edge.target : edge.target === current ? edge.source : null
      if (next && !related.has(next)) {
        related.add(next)
        queue.push(next)
      }
    }
  }

  return related
}

function collectRelatedEdgeIds(document: CanvasDocument, nodeId: string): Set<string> {
  const relatedNodes = collectRelatedNodeIds(document, nodeId)
  return new Set(
    document.edges
      .filter((edge) => relatedNodes.has(edge.source) && relatedNodes.has(edge.target))
      .map((edge) => edge.id),
  )
}

function compareShotIdText(left: string, right: string) {
  const tokenize = (value: string) =>
    value
      .split(/[^0-9A-Za-z\u4e00-\u9fa5]+/)
      .filter(Boolean)
      .map((part) => (/^\d+$/.test(part) ? Number(part) : part))

  const leftParts = tokenize(left)
  const rightParts = tokenize(right)
  const max = Math.max(leftParts.length, rightParts.length)

  for (let index = 0; index < max; index += 1) {
    const leftPart = leftParts[index]
    const rightPart = rightParts[index]
    if (leftPart === undefined) return -1
    if (rightPart === undefined) return 1
    if (typeof leftPart === 'number' && typeof rightPart === 'number') {
      if (leftPart !== rightPart) return leftPart - rightPart
      continue
    }
    const leftText = String(leftPart)
    const rightText = String(rightPart)
    if (leftText !== rightText) return leftText.localeCompare(rightText, 'zh-Hans-CN')
  }

  return left.localeCompare(right, 'zh-Hans-CN')
}
