import type { TaskCenterEntry, TaskCenterStatus } from './productWorkspaceTasks'

type StatusOption = {
  value: 'all' | TaskCenterStatus
  label: string
}

type ScopeOption = {
  value: 'all' | 'global' | 'episode'
  label: string
}

interface Props {
  statusFilter: 'all' | TaskCenterStatus
  scopeFilter: 'all' | 'global' | 'episode'
  episodeFilter: 'all' | number
  episodeOptions: number[]
  filteredEntries: TaskCenterEntry[]
  taskRuntimeById: Record<string, { latestExecutionLabel?: string | null; pendingKindLabels: string[] }>
  selectedTaskId: string | null
  statusOptions: readonly StatusOption[]
  scopeOptions: readonly ScopeOption[]
  onStatusFilterChange: (value: 'all' | TaskCenterStatus) => void
  onScopeFilterChange: (value: 'all' | 'global' | 'episode') => void
  onEpisodeFilterChange: (value: 'all' | number) => void
  onSelectTask: (taskId: string) => void
  onRunTaskAction: (entry: TaskCenterEntry) => void
}

export default function TaskCenterListPanel({
  statusFilter,
  scopeFilter,
  episodeFilter,
  episodeOptions,
  filteredEntries,
  taskRuntimeById,
  selectedTaskId,
  statusOptions,
  scopeOptions,
  onStatusFilterChange,
  onScopeFilterChange,
  onEpisodeFilterChange,
  onSelectTask,
  onRunTaskAction,
}: Props) {
  return (
    <div className="min-w-0 rounded-xl border border-slate-800 bg-slate-900 p-4">
      <div className="text-sm font-medium text-white">任务列表</div>

      <div className="mt-4 grid gap-2">
        <select
          value={statusFilter}
          onChange={(event) => onStatusFilterChange(event.target.value as 'all' | TaskCenterStatus)}
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
        >
          {statusOptions.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>

        <select
          value={scopeFilter}
          onChange={(event) => onScopeFilterChange(event.target.value as 'all' | 'global' | 'episode')}
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
        >
          {scopeOptions.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>

        <select
          value={episodeFilter === 'all' ? 'all' : String(episodeFilter)}
          onChange={(event) => onEpisodeFilterChange(event.target.value === 'all' ? 'all' : Number(event.target.value))}
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
        >
          <option value="all">全部集数</option>
          {episodeOptions.map((episode) => (
            <option key={episode} value={episode}>
              第 {episode} 集
            </option>
          ))}
        </select>
      </div>

      <div className="mt-4 space-y-3">
        {filteredEntries.map((entry) => {
          const active = selectedTaskId === entry.id
          const runtimeSummary = taskRuntimeById[entry.id]
          return (
            <div
              key={entry.id}
              role="button"
              tabIndex={0}
              onClick={() => onSelectTask(entry.id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  onSelectTask(entry.id)
                }
              }}
              className={`w-full rounded-xl border p-3 text-left transition focus:outline-none focus:ring-2 focus:ring-sky-500/40 ${
                active ? 'border-sky-500/40 bg-sky-500/10' : 'border-slate-800 bg-slate-950/50 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-white">{entry.type}</div>
                  <div className="mt-1 text-[11px] text-slate-500">
                    {entry.scope === 'global' ? '\u6279\u91cf / \u5168\u5c40\u4efb\u52a1' : '\u5355\u96c6\u4efb\u52a1'}
                    {entry.isBatch ? ' | \u8c03\u5ea6\u5165\u53e3' : ''}
                  </div>
                </div>
                <span className={`rounded-full border px-2 py-0.5 text-[11px] ${statusTone(entry.status)}`}>
                  {statusLabel(entry.status)}
                </span>
              </div>
              <div className="mt-2 text-xs text-slate-400">{entry.target}</div>
              {runtimeSummary ? (
                <div className="mt-2 flex flex-wrap gap-2 text-[10px]">
                  {runtimeSummary.latestExecutionLabel ? (
                    <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-sky-200">
                      最近执行 · {runtimeSummary.latestExecutionLabel}
                    </span>
                  ) : null}
                  {runtimeSummary.pendingKindLabels.length > 0 ? (
                    <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-200">
                      待回收 · {runtimeSummary.pendingKindLabels.join(' / ')}
                    </span>
                  ) : null}
                </div>
              ) : null}
              {entry.promptHealth?.degradedShotCount ? (
                <div className="mt-2 flex flex-wrap gap-2 text-[10px]">
                  <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-200">
                    {'\u8dd1\u504f\u955c\u5934 '}{entry.promptHealth.degradedShotCount}
                  </span>
                  {entry.promptHealth.recommendedRestoreCount ? (
                    <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-emerald-200">
                      {'\u53ef\u6062\u590d '}{entry.promptHealth.recommendedRestoreCount}
                    </span>
                  ) : null}
                  {entry.promptHealth.partialRestoreCount ? (
                    <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-sky-200">
                      {'\u90e8\u5206\u6062\u590d '}{entry.promptHealth.partialRestoreCount}
                    </span>
                  ) : null}
                  {entry.promptHealth.manualRepairCount ? (
                    <span className="rounded-full border border-rose-500/30 bg-rose-500/10 px-2 py-0.5 text-rose-200">
                      {'\u5f85\u4eba\u5de5\u4fee\u590d '}{entry.promptHealth.manualRepairCount}
                    </span>
                  ) : null}
                </div>
              ) : null}
              <div className="mt-3 flex items-center justify-between gap-2 text-[11px] text-slate-500">
                <span className="truncate">{entry.progress}</span>
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation()
                    onRunTaskAction(entry)
                  }}
                  className="rounded-md border border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition hover:border-sky-500 hover:text-white"
                >
                  {entry.actionLabel}
                </button>
              </div>
            </div>
          )
        })}

        {filteredEntries.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
            当前筛选条件下没有任务。
          </div>
        ) : null}
      </div>
    </div>
  )
}

function statusTone(status: TaskCenterStatus) {
  switch (status) {
    case 'done':
      return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
    case 'running':
      return 'border-sky-500/30 bg-sky-500/10 text-sky-200'
    case 'error':
      return 'border-rose-500/30 bg-rose-500/10 text-rose-200'
    case 'blocked':
      return 'border-slate-600 bg-slate-800 text-slate-300'
    case 'skipped':
      return 'border-violet-500/30 bg-violet-500/10 text-violet-200'
    default:
      return 'border-amber-500/30 bg-amber-500/10 text-amber-200'
  }
}

function statusLabel(status: TaskCenterStatus) {
  switch (status) {
    case 'done':
      return '已完成'
    case 'running':
      return '进行中'
    case 'error':
      return '待修复'
    case 'blocked':
      return '等待上游'
    case 'skipped':
      return '已跳过'
    default:
      return '待执行'
  }
}
