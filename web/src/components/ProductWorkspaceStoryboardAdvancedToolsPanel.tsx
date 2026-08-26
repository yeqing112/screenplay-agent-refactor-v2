import {
  getStoryboardRecoveryKindLabel,
  type PendingStoryboardTaskSummary,
  type ShotRuntimeState,
  type StoryboardRecoveryKind,
} from './productWorkspaceRecovery'
import { CollapsiblePanel, MiniMetric } from './ProductWorkspaceStoryboardUi'

type GenerationUiState = 'idle' | 'frame' | 'video' | 'success' | 'error'

interface StoryboardAdvancedToolsPanelProps {
  episode?: number | null
  shotId: string
  assetStatus?: string | null
  canGenerateFromGate: boolean
  hasAdoptedFrame: boolean
  isGenerationBusy: boolean
  generationState: GenerationUiState
  generationMessage: string
  adoptedFrameLabel: string
  adoptedFrameAssetId: string
  referenceAssetIds: string[]
  compiledReferenceAssetIds: string[]
  effectiveReferenceAssetIds: string[]
  effectiveReferencePayloadSource: string
  hasReferencePayloadDrift: boolean
  predictedVideoTaskMode: string
  frameRecoveryTaskId: string | null
  videoRecoveryTaskId: string | null
  promptRecoveryTaskId: string | null
  hasRecoveryTask: boolean
  selectedShotRuntime: ShotRuntimeState
  selectedShotPendingSummary: PendingStoryboardTaskSummary
  onNavigateCanvas?: (target: { episode?: number | null; shotId: string }) => void
  onNavigateTasks?: (target: {
    episode?: number | null
    shotId: string
    taskId?: string
    recoveryKind?: StoryboardRecoveryKind
  }) => void
  onGenerateFrame: () => void | Promise<void>
  onGenerateVideo: () => void | Promise<void>
}

export function ProductWorkspaceStoryboardAdvancedToolsPanel({
  episode,
  shotId,
  assetStatus,
  canGenerateFromGate,
  hasAdoptedFrame,
  isGenerationBusy,
  generationState,
  generationMessage,
  adoptedFrameLabel,
  adoptedFrameAssetId,
  referenceAssetIds,
  compiledReferenceAssetIds,
  effectiveReferenceAssetIds,
  effectiveReferencePayloadSource,
  hasReferencePayloadDrift,
  predictedVideoTaskMode,
  frameRecoveryTaskId,
  videoRecoveryTaskId,
  promptRecoveryTaskId,
  hasRecoveryTask,
  selectedShotRuntime,
  selectedShotPendingSummary,
  onNavigateCanvas,
  onNavigateTasks,
  onGenerateFrame,
  onGenerateVideo,
}: StoryboardAdvancedToolsPanelProps) {
  return (
    <CollapsiblePanel
      title="高级生产工具"
      description="手动生成首帧/视频、查看任务回收、核对视频输入摘要。常规情况下直接使用当前镜头顶部主动作。"
      className="mt-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-white">{'单镜头生成动作'}</div>
          <div className="mt-1 text-xs text-slate-500">{'在新版镜头工作台直接发起首帧和视频任务；长任务会自动接回任务中心恢复链路。'}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          {onNavigateCanvas ? (
            <button
              type="button"
              onClick={() => onNavigateCanvas({ episode, shotId })}
              className="rounded-lg border border-slate-700 px-3 py-2 text-xs transition border-slate-700 text-slate-300 hover:border-sky-500 hover:text-white"
            >
              在创作画布查看
            </button>
          ) : null}
          <button
            type="button"
            disabled={!canGenerateFromGate || isGenerationBusy}
            onClick={() => { void onGenerateFrame() }}
            className={`rounded-lg px-3 py-2 text-xs font-medium transition ${
              !canGenerateFromGate || isGenerationBusy
                ? 'cursor-not-allowed border border-slate-800 bg-slate-900 text-slate-500'
                : 'bg-emerald-600 text-white hover:bg-emerald-500'
            }`}
          >
            {generationState === 'frame' ? '生成首帧中...' : '生成首帧'}
          </button>
          <button
            type="button"
            disabled={!canGenerateFromGate || !hasAdoptedFrame || isGenerationBusy}
            onClick={() => { void onGenerateVideo() }}
            className={`rounded-lg px-3 py-2 text-xs font-medium transition ${
              !canGenerateFromGate || !hasAdoptedFrame || isGenerationBusy
                ? 'cursor-not-allowed border border-slate-800 bg-slate-900 text-slate-500'
                : 'bg-fuchsia-600 text-white hover:bg-fuchsia-500'
            }`}
          >
            {generationState === 'video' ? '生成视频中...' : '生成视频'}
          </button>
          {onNavigateTasks ? (
            <button
              type="button"
              disabled={!hasRecoveryTask}
              onClick={() =>
                onNavigateTasks({
                  episode,
                  shotId,
                  taskId: videoRecoveryTaskId || frameRecoveryTaskId || undefined,
                  recoveryKind: videoRecoveryTaskId ? 'video' : frameRecoveryTaskId ? 'frame' : undefined,
                })
              }
              className={`rounded-lg border px-3 py-2 text-xs transition ${
                hasRecoveryTask
                  ? 'border-slate-700 text-slate-300 hover:border-sky-500 hover:text-white'
                  : 'cursor-not-allowed border-slate-800 text-slate-600'
              }`}
            >
              {'去任务中心继续回收'}
            </button>
          ) : null}
        </div>
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <MiniMetric label={'首帧状态'} value={hasAdoptedFrame ? '已有采纳首帧' : '缺采纳首帧'} />
        <MiniMetric label={'待恢复任务'} value={`${Number(Boolean(frameRecoveryTaskId)) + Number(Boolean(videoRecoveryTaskId))} 个`} />
        <MiniMetric label={'当前资产状态'} value={assetStatus || 'pending'} />
      </div>

      {selectedShotRuntime.latestExecutionSummary || selectedShotRuntime.pendingTasks.length > 0 ? (
        <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-xs text-slate-500">当前镜头运行态</div>
            <div className="flex flex-wrap gap-2 text-[10px] text-slate-500">
              {selectedShotRuntime.latestExecutionSummary?.updatedAt ? (
                <span className="rounded-full border border-slate-800 px-2 py-0.5">
                  更新于 {new Date(selectedShotRuntime.latestExecutionSummary.updatedAt).toLocaleString('zh-CN', { hour12: false })}
                </span>
              ) : null}
              {selectedShotPendingSummary.latestUpdatedAt ? (
                <span className="rounded-full border border-slate-800 px-2 py-0.5">
                  待回收更新于 {new Date(selectedShotPendingSummary.latestUpdatedAt).toLocaleString('zh-CN', { hour12: false })}
                </span>
              ) : null}
              {promptRecoveryTaskId ? (
                <span className="rounded-full border border-slate-800 px-2 py-0.5">
                  提示词待回收
                </span>
              ) : null}
            </div>
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            <MiniMetric
              label="最近执行"
              value={selectedShotRuntime.latestExecutionSummary?.label || '未记录'}
            />
            <MiniMetric
              label="待回收任务"
              value={
                selectedShotPendingSummary.count > 0
                  ? selectedShotPendingSummary.joinedKindLabels
                  : '无'
              }
            />
            <MiniMetric
              label="建议动作"
              value={
                selectedShotRuntime.pendingTasks.length > 0
                  ? '先回收任务'
                  : selectedShotRuntime.latestExecutionSummary
                    ? '继续复核结果'
                    : '可发起执行'
              }
            />
          </div>
          {promptRecoveryTaskId ? (
            <div className="mt-3 text-[11px] text-slate-400">
              当前镜头还有提示词重编译任务在后台执行，建议先等任务回收完成，再决定是否继续出图或出视频。
            </div>
          ) : null}
          {selectedShotPendingSummary.latestTaskId && selectedShotPendingSummary.latestSourceLabel ? (
            <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-[11px] text-slate-300">
              最近待回收来源：{selectedShotPendingSummary.latestSourceLabel} · 任务 ID：{selectedShotPendingSummary.latestTaskId}
            </div>
          ) : null}
          {selectedShotRuntime.pendingTasks.length > 0 ? (
            <div className="mt-4 space-y-2">
              {selectedShotRuntime.pendingTasks.slice(0, 4).map((task) => (
                <div key={`${task.taskId}-${task.updatedAt}`} className="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 text-xs text-slate-300">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span>{getStoryboardRecoveryKindLabel(task.kind)} · 任务 ID：{task.taskId}</span>
                    <span className="text-slate-500">
                      {new Date(task.updatedAt).toLocaleString('zh-CN', { hour12: false })}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
        <div className="text-xs text-slate-500">本次视频输入摘要</div>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
            <div className="text-[11px] text-slate-500">{'首帧来源'}</div>
            <div className="mt-1 text-sm font-medium text-slate-100 break-all">
              {hasAdoptedFrame ? adoptedFrameLabel : '未采纳首帧'}
            </div>
            <div className="mt-2 break-all text-[11px] text-slate-500">
              {hasAdoptedFrame ? `资产 ID：${adoptedFrameAssetId || '未记录'}` : '没有首帧时视频生成保持禁用'}
            </div>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
            <div className="text-[11px] text-slate-500">{'参考图输入'}</div>
            <div className="mt-1 text-sm font-medium text-slate-100">{`${referenceAssetIds.length} 张`}</div>
            <div className="mt-2 break-all text-[11px] text-slate-500">
              {referenceAssetIds.length > 0 ? referenceAssetIds.join(' / ') : '当前未记录结构化参考图 ID'}
            </div>
            <div className="mt-2 break-all text-[11px] text-slate-500">
              {compiledReferenceAssetIds.length > 0
                ? `当前编译实际使用：${compiledReferenceAssetIds.length} 张 · ${compiledReferenceAssetIds.join(' / ')}`
                : '当前编译尚未沉淀可用参考图载荷'}
            </div>
            <div className="mt-2 break-all text-[11px] text-sky-200">
              {effectiveReferenceAssetIds.length > 0
                ? `本次视频实际提交：${effectiveReferenceAssetIds.length} 张 · ${effectiveReferenceAssetIds.join(' / ')}`
                : '本次视频不提交静态参考图 ID'}
            </div>
            <div className="mt-2 break-all text-[11px] text-slate-500">
              {effectiveReferencePayloadSource === 'compiled'
                ? '当前会优先沿用已编译版本实际使用的参考图，保证提示词、参考图与任务记录保持一致。'
                : '当前会直接使用结构化绑定里的参考图。'}
            </div>
            {hasReferencePayloadDrift ? (
              <div className="mt-2 text-[11px] text-amber-300">
                {'结构化绑定数量与当前编译载荷不一致。本次会优先沿用已编译载荷；如果要切换到最新绑定，建议先重编提示词。'}
              </div>
            ) : null}
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
            <div className="text-[11px] text-slate-500">{'任务模式'}</div>
            <div className="mt-1 text-sm font-medium text-slate-100">{predictedVideoTaskMode}</div>
            <div className="mt-2 break-all text-[11px] text-slate-500">
              {'优先使用 image_to_video，其次 reference_to_video，最后 text_to_video'}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-3 text-sm text-slate-300">
        {!canGenerateFromGate
          ? '当前镜头仍受上游锁稿/放行约束，暂不建议直接出图或出视频。'
          : hasAdoptedFrame
            ? '当前镜头已具备采纳首帧，视频会显式使用这张首帧与当前结构化参考图继续生成。'
            : '当前镜头还没有采纳首帧，视频生成按钮会保持禁用。'}
      </div>

      {generationMessage ? (
        <div className={`mt-3 rounded-lg border px-3 py-2 text-sm ${
          generationState === 'success'
            ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-200'
            : generationState === 'error'
              ? 'border-amber-500/20 bg-amber-500/5 text-amber-100'
              : 'border-slate-700 bg-slate-950/60 text-slate-300'
        }`}>
          {generationMessage}
        </div>
      ) : null}

      {hasRecoveryTask ? (
        <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-slate-400">
          {frameRecoveryTaskId ? <span className="rounded-full border border-slate-700 px-2 py-1">{'首帧任务：'}{frameRecoveryTaskId}</span> : null}
          {videoRecoveryTaskId ? <span className="rounded-full border border-slate-700 px-2 py-1">{'视频任务：'}{videoRecoveryTaskId}</span> : null}
        </div>
      ) : null}
    </CollapsiblePanel>
  )
}
