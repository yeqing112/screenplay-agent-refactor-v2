import { batchActionLabel, type BatchTaskAction } from './productWorkspaceBatchActions'
import type { BatchRunRecord } from './productWorkspaceBatchRuns'
import type { TaskCenterEntry } from './productWorkspaceTasks'

type TaskActionState = {
  mode: 'idle' | 'loading' | 'success' | 'error'
  action:
    | 'qa-autofix'
    | 'qa-recheck'
    | 'recovery-refresh'
    | 'recovery-reconcile'
    | 'recovery-restart'
    | 'recovery-regenerate-latest'
    | BatchTaskAction
    | null
  message: string
}

interface Props {
  selectedTask: TaskCenterEntry
  selectedTaskActionState: TaskActionState
  latestSelectedBatchRunRecord: BatchRunRecord | null
  selectedBatchRunRecords: BatchRunRecord[]
  batchPromptCompileCount: number
  batchMissingFrameCount: number
  batchMissingVideoCount: number
  batchOpenQaEpisodeCount: number
  onRunBatchTaskAction: (action: BatchTaskAction) => void
  onRunRecoveryTaskAction: (action: 'recovery-refresh' | 'recovery-reconcile' | 'recovery-restart' | 'recovery-regenerate-latest') => void
  onRunQaTaskAction: (action: 'qa-autofix' | 'qa-recheck') => void
}

function buildRestartInputSummary(selectedTask: TaskCenterEntry) {
  if (!selectedTask.taskId || !selectedTask.creativeTaskMeta) return null
  const meta = selectedTask.creativeTaskMeta
  const taskPromptVersion = meta.taskPromptVersion
  const currentShotPromptVersion = meta.currentShotPromptVersion
  const firstFrameAssetId = String(meta.firstFrameAssetId || '').trim()
  const referenceCount = meta.referenceAssetIds?.length ?? 0

  const parts: string[] = []
  if (taskPromptVersion !== null && taskPromptVersion !== undefined) {
    parts.push(`重发会沿用任务提交时的提示词版本 v${taskPromptVersion}`)
  } else {
    parts.push('重发会沿用当前任务记录下来的原始提示词输入')
  }

  if (
    currentShotPromptVersion !== null &&
    currentShotPromptVersion !== undefined &&
    taskPromptVersion !== null &&
    taskPromptVersion !== undefined
  ) {
    if (currentShotPromptVersion !== taskPromptVersion) {
      parts.push(`不会自动切换到镜头当前版本 v${currentShotPromptVersion}`)
    } else {
      parts.push('当前与镜头版本一致')
    }
  }

  if (firstFrameAssetId) parts.push(`继续使用首帧 ${firstFrameAssetId}`)
  if (referenceCount > 0) parts.push(`继续挂载 ${referenceCount} 张静态参考图`)
  return parts.join('；') + '。'
}

export default function TaskCenterDetailPanels({
  selectedTask,
  selectedTaskActionState,
  latestSelectedBatchRunRecord,
  selectedBatchRunRecords,
  batchPromptCompileCount,
  batchMissingFrameCount,
  batchMissingVideoCount,
  batchOpenQaEpisodeCount,
  onRunBatchTaskAction,
  onRunRecoveryTaskAction,
  onRunQaTaskAction,
}: Props) {
  const restartInputSummary = buildRestartInputSummary(selectedTask)
  const canRegenerateLatest =
    selectedTask.recoveryKind === 'frame' ||
    selectedTask.recoveryKind === 'video'

  return (
    <>
      {latestSelectedBatchRunRecord ? (
        <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
          <div className="text-sm font-medium text-white">最近一次批量执行记录</div>
          <div className="mt-3 grid gap-3 md:grid-cols-4">
            <PanelMetricCard
              title="执行动作"
              value={batchActionLabel(latestSelectedBatchRunRecord.action)}
              detail="记录任务中心最近一次真实批量动作"
            />
            <PanelMetricCard
              title="成功 / 失败"
              value={`${latestSelectedBatchRunRecord.successCount} / ${latestSelectedBatchRunRecord.failedCount}`}
              detail={
                latestSelectedBatchRunRecord.pendingRecoveryCount
                  ? `待回收 ${latestSelectedBatchRunRecord.pendingRecoveryCount}`
                  : '已完成后即时回写'
              }
            />
            <PanelMetricCard
              title="执行时间"
              value={new Date(latestSelectedBatchRunRecord.finishedAt).toLocaleString('zh-CN', { hour12: false })}
              detail="用于回看最近一次批量调度"
            />
            <PanelMetricCard
              title="结果状态"
              value={latestSelectedBatchRunRecord.status === 'success' ? '成功' : '有失败'}
              detail="任务中心会保留最近一次执行摘要"
            />
          </div>
          <div className="mt-4 rounded-lg border border-slate-800 bg-slate-900/70 p-3 text-sm leading-6 text-slate-300">
            {latestSelectedBatchRunRecord.summary}
            {latestSelectedBatchRunRecord.failedTargets?.length ? (
              <div className="mt-2 text-xs text-slate-400">
                失败对象：{latestSelectedBatchRunRecord.failedTargets.slice(0, 5).join('、')}
                {latestSelectedBatchRunRecord.failedTargets.length > 5 ? ' 等' : ''}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {selectedBatchRunRecords.length > 1 ? (
        <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
          <div className="text-sm font-medium text-white">最近批量执行历史</div>
          <div className="mt-3 space-y-3">
            {selectedBatchRunRecords.slice(1).map((record, index) => (
              <div key={`${record.taskId}-${record.finishedAt}-${index}`} className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="text-sm text-slate-200">{batchActionLabel(record.action)}</div>
                  <div className="text-xs text-slate-500">
                    {new Date(record.finishedAt).toLocaleString('zh-CN', { hour12: false })}
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-400">
                  <span>成功 {record.successCount}</span>
                  <span>失败 {record.failedCount}</span>
                  {record.pendingRecoveryCount ? <span>待回收 {record.pendingRecoveryCount}</span> : null}
                  <span>{record.status === 'success' ? '执行成功' : '执行有失败'}</span>
                </div>
                <div className="mt-2 text-sm leading-6 text-slate-300">{record.summary}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {selectedTask.id === 'task-batch-prompts' ? (
        <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-white">批量提示词调度</div>
              <div className="mt-1 text-xs text-slate-400">直接对全项目未锁定且未完成的镜头批量发起提示词编译。</div>
            </div>
            <button
              type="button"
              onClick={() => onRunBatchTaskAction('batch-compile-prompts')}
              disabled={selectedTaskActionState.mode === 'loading' || batchPromptCompileCount === 0}
              className="rounded-lg border border-sky-500/50 px-3 py-1.5 text-xs font-medium text-sky-200 transition hover:border-sky-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              批量编译提示词
            </button>
          </div>
          <div className="mt-3 text-xs leading-6 text-slate-400">
            当前仍有 {batchPromptCompileCount} 个镜头需要补齐静态 / 运动提示词；已锁定镜头会自动跳过。
          </div>
          {selectedTaskActionState.message ? (
            <PanelActionFeedback state={selectedTaskActionState.mode} message={selectedTaskActionState.message} />
          ) : null}
        </div>
      ) : null}

      {selectedTask.id === 'task-batch-assets' ? (
        <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-white">批量首帧补齐</div>
              <div className="mt-1 text-xs text-slate-400">先补首帧，再对已采纳首帧的镜头批量发起视频生成，并把长任务接回任务中心恢复链路。</div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => onRunBatchTaskAction('batch-generate-frames')}
                disabled={selectedTaskActionState.mode === 'loading' || batchMissingFrameCount === 0}
                className="rounded-lg border border-amber-500/50 px-3 py-1.5 text-xs font-medium text-amber-200 transition hover:border-amber-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                批量补首帧
              </button>
              <button
                type="button"
                onClick={() => onRunBatchTaskAction('batch-generate-videos')}
                disabled={selectedTaskActionState.mode === 'loading' || batchMissingVideoCount === 0}
                className="rounded-lg border border-emerald-500/50 px-3 py-1.5 text-xs font-medium text-emerald-200 transition hover:border-emerald-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                批量补视频
              </button>
            </div>
          </div>
          <div className="mt-3 text-xs leading-6 text-slate-400">
            当前仍有 {batchMissingFrameCount} 个镜头没有分镜图，{batchMissingVideoCount} 个镜头已经具备已采纳首帧但还没有视频；已在执行中的同类任务会自动跳过，避免重复提交。
          </div>
          {selectedTaskActionState.message ? (
            <PanelActionFeedback state={selectedTaskActionState.mode} message={selectedTaskActionState.message} />
          ) : null}
        </div>
      ) : null}

      {selectedTask.id === 'task-batch-qa' ? (
        <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-white">批量 QA 调度</div>
              <div className="mt-1 text-xs text-slate-400">对仍有开放问题的集数统一触发自动修复或整集复检。</div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => onRunBatchTaskAction('batch-qa-autofix')}
                disabled={selectedTaskActionState.mode === 'loading' || batchOpenQaEpisodeCount === 0}
                className="rounded-lg border border-emerald-500/50 px-3 py-1.5 text-xs font-medium text-emerald-200 transition hover:border-emerald-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                批量自动修复
              </button>
              <button
                type="button"
                onClick={() => onRunBatchTaskAction('batch-qa-recheck')}
                disabled={selectedTaskActionState.mode === 'loading' || batchOpenQaEpisodeCount === 0}
                className="rounded-lg border border-sky-500/50 px-3 py-1.5 text-xs font-medium text-sky-200 transition hover:border-sky-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                批量触发复检
              </button>
            </div>
          </div>
          <div className="mt-3 text-xs leading-6 text-slate-400">
            当前仍有 {batchOpenQaEpisodeCount} 集处于开放问题或复检中的状态，适合在 QA 工作台继续闭环。
          </div>
          {selectedTaskActionState.message ? (
            <PanelActionFeedback state={selectedTaskActionState.mode} message={selectedTaskActionState.message} />
          ) : null}
        </div>
      ) : null}

      {selectedTask.taskId ? (
        <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-white">创意任务恢复</div>
              <div className="mt-1 text-xs text-slate-400">直接从任务中心查询状态、继续回收，或基于原始输入重新发起任务。</div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => onRunRecoveryTaskAction('recovery-refresh')}
                disabled={selectedTaskActionState.mode === 'loading' || selectedTask.status === 'done'}
                className="rounded-lg border border-slate-600 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-slate-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                刷新状态
              </button>
              <button
                type="button"
                onClick={() => onRunRecoveryTaskAction('recovery-reconcile')}
                disabled={
                  selectedTaskActionState.mode === 'loading' ||
                  selectedTask.status === 'done' ||
                  selectedTask.status === 'error'
                }
                className="rounded-lg border border-sky-500/50 px-3 py-1.5 text-xs font-medium text-sky-200 transition hover:border-sky-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                继续回收结果
              </button>
              <button
                type="button"
                onClick={() => onRunRecoveryTaskAction('recovery-restart')}
                disabled={selectedTaskActionState.mode === 'loading' || selectedTask.status === 'queued'}
                className="rounded-lg border border-amber-500/50 px-3 py-1.5 text-xs font-medium text-amber-200 transition hover:border-amber-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                按原始输入重发
              </button>
              <button
                type="button"
                onClick={() => onRunRecoveryTaskAction('recovery-regenerate-latest')}
                disabled={selectedTaskActionState.mode === 'loading' || !canRegenerateLatest}
                className="rounded-lg border border-emerald-500/50 px-3 py-1.5 text-xs font-medium text-emerald-200 transition hover:border-emerald-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                按最新状态重生成
              </button>
            </div>
          </div>

          {restartInputSummary ? (
            <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs leading-6 text-amber-100/90">
              重新发起说明：{restartInputSummary}
            </div>
          ) : null}

          <div className="mt-3 text-xs leading-6 text-slate-400">
            {selectedTask.status === 'error'
              ? '当前建议优先重新发起任务；如果只是外部状态未同步，也可以先刷新状态。'
              : selectedTask.status === 'done'
                ? '当前结果已经回写完成，下一步更适合回到对应工作台确认采纳状态。'
                : selectedTask.status === 'queued'
                  ? '任务已重新排队，建议先观察 provider 是否开始执行。'
                  : '任务仍在执行或等待回收，可先刷新状态，再决定是否继续回收结果。'}
          </div>

          {selectedTaskActionState.message ? (
            <PanelActionFeedback state={selectedTaskActionState.mode} message={selectedTaskActionState.message} />
          ) : null}
        </div>
      ) : null}

      {selectedTask.actionTarget === 'qa' && selectedTask.episode ? (
        <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-white">QA 调度动作</div>
              <div className="mt-1 text-xs text-slate-400">直接从任务中心触发整集自动修复或后台复检。</div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => onRunQaTaskAction('qa-autofix')}
                disabled={selectedTaskActionState.mode === 'loading'}
                className="rounded-lg border border-emerald-500/50 px-3 py-1.5 text-xs font-medium text-emerald-200 transition hover:border-emerald-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                整集自动修复
              </button>
              <button
                type="button"
                onClick={() => onRunQaTaskAction('qa-recheck')}
                disabled={selectedTaskActionState.mode === 'loading'}
                className="rounded-lg border border-sky-500/50 px-3 py-1.5 text-xs font-medium text-sky-200 transition hover:border-sky-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                触发复检
              </button>
            </div>
          </div>

          {selectedTaskActionState.message ? (
            <PanelActionFeedback state={selectedTaskActionState.mode} message={selectedTaskActionState.message} />
          ) : null}
        </div>
      ) : null}
    </>
  )
}

function PanelMetricCard({ title, value, detail }: { title: string; value: string; detail: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
      <div className="text-xs text-slate-500">{title}</div>
      <div className="mt-2 text-lg font-semibold text-white">{value}</div>
      <div className="mt-1 text-xs text-slate-400">{detail}</div>
    </div>
  )
}

function PanelActionFeedback({
  state,
  message,
}: {
  state: 'idle' | 'loading' | 'success' | 'error'
  message: string
}) {
  const tone =
    state === 'error'
      ? 'border-rose-500/30 bg-rose-500/10 text-rose-200'
      : state === 'loading'
        ? 'border-amber-500/30 bg-amber-500/10 text-amber-200'
        : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'

  return <div className={`mt-3 rounded-lg border px-3 py-2 text-xs ${tone}`}>{message}</div>
}
