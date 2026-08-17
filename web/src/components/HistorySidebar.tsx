import React, { useEffect, useState } from 'react'

interface RunEntry {
  run_id: string
  node_type: string
  started_at: string
  finished_at?: string
  output_summary?: Record<string, any>
}

interface Props {
  nodeType: string | null
  nodeId: string | null
  onReplay: (runId: string) => void
  open: boolean
  onClose: () => void
}

export default function HistorySidebar({ nodeType, nodeId, onReplay, open, onClose }: Props) {
  const [runs, setRuns] = useState<RunEntry[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open || !nodeType) return
    setLoading(true)
    fetch(`/api/runs?node_type=${nodeType}`)
      .then(r => r.json())
      .then(setRuns)
      .catch(() => setRuns([]))
      .finally(() => setLoading(false))
  }, [open, nodeType])

  if (!open) return null

  return (
    <div className="absolute top-10 right-0 w-80 bg-slate-900 border border-slate-800 rounded-lg shadow-2xl z-20 max-h-96 overflow-y-auto">
      <div className="px-3 py-2 border-b border-slate-800 flex items-center justify-between">
        <span className="text-xs font-medium text-slate-300">
          执行历史 · {nodeType}
        </span>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-sm">&times;</button>
      </div>

      {loading && <div className="p-4 text-xs text-slate-500 text-center">加载中...</div>}

      {!loading && runs.length === 0 && (
        <div className="p-4 text-xs text-slate-500 text-center">暂无执行记录</div>
      )}

      {runs.map((run) => (
        <div
          key={run.run_id}
          className="px-3 py-2 border-b border-slate-800/50 hover:bg-slate-800/50 cursor-pointer transition-colors"
          onClick={() => onReplay(run.run_id)}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400">
              {run.run_id.slice(0, 8)}
            </span>
            <span className="text-[10px] text-slate-600">
              {run.finished_at ? new Date(run.finished_at).toLocaleTimeString() : '运行中'}
            </span>
          </div>
          {run.output_summary && Object.keys(run.output_summary).length > 0 && (
            <div className="text-xs text-slate-600 mt-0.5 truncate">
              {JSON.stringify(run.output_summary)}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
