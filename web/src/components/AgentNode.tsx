import React, { memo, useState } from 'react'
import { Handle, Position, NodeProps } from 'reactflow'
import { CanvasNodeData } from '../types/nodes'

const CATEGORY_COLORS: Record<string, string> = {
  input: '#3b82f6',
  analysis: '#8b5cf6',
  adapt: '#f59e0b',
  script: '#10b981',
  vision: '#ec4899',
}

const STATUS_COLORS: Record<string, string> = {
  idle: '#475569',
  running: '#f59e0b',
  done: '#10b981',
  error: '#ef4444',
}

function AgentNode({ data, selected }: NodeProps<CanvasNodeData>) {
  const { spec, inputs = {}, runStatus = 'idle', runId } = data
  const [expanded, setExpanded] = useState(false)
  const [outputData, setOutputData] = useState<string | null>(null)
  const [loadingOutput, setLoadingOutput] = useState(false)

  const color = CATEGORY_COLORS[spec.category] || '#64748b'
  const statusColor = STATUS_COLORS[runStatus]

  const toggleExpand = () => {
    if (!expanded && runId && !outputData && !loadingOutput) {
      setLoadingOutput(true)
      fetch(`/api/nodes/run/${runId}`)
        .then(r => r.json())
        .then(data => {
          const result = data.result
          if (result) {
            setOutputData(
              typeof result === 'string'
                ? result.slice(0, 2000)
                : JSON.stringify(result, null, 2).slice(0, 2000)
            )
          } else {
            setOutputData('(执行结果为空)')
          }
        })
        .catch(() => setOutputData('(加载失败)'))
        .finally(() => setLoadingOutput(false))
    }
    setExpanded(!expanded)
  }

  return (
    <div
      className={`rounded-lg border-2 shadow-lg min-w-[200px] ${
        selected ? 'ring-2 ring-blue-500' : ''
      }`}
      style={{
        background: '#1e293b',
        borderColor: selected ? '#3b82f6' : color,
      }}
    >
      {/* Top bar */}
      <div
        className="px-3 py-2 rounded-t-md flex items-center justify-between cursor-pointer"
        style={{ background: `${color}22`, borderBottom: `1px solid ${color}44` }}
        onClick={toggleExpand}
      >
        <div className="flex items-center gap-2">
          <div
            className="w-2 h-2 rounded-full"
            style={{ background: statusColor }}
          />
          <span className="text-sm font-medium text-slate-200">
            {spec.label}
            {expanded ? ' ▼' : ' ▶'}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <span
            className="text-[10px] px-1.5 py-0.5 rounded"
            style={{ background: `${color}33`, color }}
          >
            {spec.name}
          </span>
        </div>
      </div>

      {/* Body - collapsed: input summary */}
      {!expanded && (
        <div className="px-3 py-2 text-xs text-slate-400 space-y-0.5">
          {spec.inputs.map((inp) => (
            <div key={inp.name} className="flex justify-between">
              <span>{inp.label}:</span>
              <span className="text-slate-300 truncate max-w-[100px]">
                {typeof inputs[inp.name] === 'object'
                  ? JSON.stringify(inputs[inp.name]).slice(0, 30)
                  : inputs[inp.name] ?? inp.default ?? '-'}
              </span>
            </div>
          ))}
          {spec.inputs.length === 0 && (
            <span className="text-slate-500 italic">no inputs</span>
          )}
          {runId && (
            <div className="text-[10px] text-slate-600 mt-1 flex justify-between">
              <span>run: {runId.slice(0, 8)}</span>
              <span className={
                runStatus === 'done' ? 'text-green-500' :
                runStatus === 'error' ? 'text-red-500' : ''
              }>
                {runStatus === 'done' ? '✓' : runStatus === 'error' ? '✗' : ''}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Expanded: data preview */}
      {expanded && (
        <div className="px-3 py-2 text-xs max-h-[300px] overflow-y-auto">
          {/* Inputs */}
          <div className="mb-2">
            <div className="text-slate-500 font-medium mb-1">📥 Inputs</div>
            {spec.inputs.map((inp) => (
              <div key={inp.name} className="flex gap-2 mb-0.5">
                <span className="text-slate-500 w-20 flex-shrink-0">{inp.label}:</span>
                <span className="text-slate-300 break-all">
                  {typeof inputs[inp.name] === 'object'
                    ? JSON.stringify(inputs[inp.name], null, 2)
                    : String(inputs[inp.name] ?? inp.default ?? '-')}
                </span>
              </div>
            ))}
          </div>

          {/* Outputs */}
          <div>
            <div className="text-slate-500 font-medium mb-1">📤 Outputs</div>
            {runId && !loadingOutput && outputData !== null && (
              <pre className="text-slate-300 whitespace-pre-wrap bg-slate-800/50 rounded p-2 text-[10px] leading-relaxed max-h-[180px] overflow-y-auto">
                {outputData}
              </pre>
            )}
            {runId && loadingOutput && (
              <div className="text-slate-600 italic">加载中...</div>
            )}
            {runId && !loadingOutput && outputData === null && (
              <div className="text-slate-600 italic">点击查看</div>
            )}
            {!runId && (
              <div className="text-slate-600 italic">尚未执行</div>
            )}
          </div>

          {/* History link */}
          {runId && (
            <div className="mt-2 pt-2 border-t border-slate-800 text-[10px] text-slate-600">
              Run: {runId}
            </div>
          )}
        </div>
      )}

      {/* Handles */}
      <Handle
        type="target"
        position={Position.Left}
        className="!w-3 !h-3 !border-2"
        style={{ background: '#1e293b', borderColor: color }}
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!w-3 !h-3 !border-2"
        style={{ background: '#1e293b', borderColor: color }}
      />
    </div>
  )
}

export default memo(AgentNode)
