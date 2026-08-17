import React, { useState } from 'react'

interface Props {
  runResult: any
  logs: string[]
  runStatus?: string
}

export default function ResultsPanel({ runResult, logs, runStatus }: Props) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div
      className={`flex-shrink-0 bg-slate-900 border-t border-slate-800 ${
        expanded ? 'h-48' : 'h-10'
      } transition-all duration-200 overflow-hidden`}
    >
      <div
        className="px-3 py-1.5 border-b border-slate-800 flex items-center justify-between cursor-pointer hover:bg-slate-800/50"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-slate-400">
            {expanded ? '▼' : '▲'} 执行日志
          </span>
          {runStatus && (
            <span className={`text-xs px-1.5 py-0.5 rounded ${
              runStatus === 'running' ? 'bg-yellow-900/50 text-yellow-400' :
              runStatus === 'done' ? 'bg-green-900/50 text-green-400' :
              runStatus === 'error' ? 'bg-red-900/50 text-red-400' :
              'bg-slate-800 text-slate-500'
            }`}>
              {runStatus === 'running' ? '运行中' :
               runStatus === 'done' ? '完成' :
               runStatus === 'error' ? '失败' : '就绪'}
            </span>
          )}
        </div>
        {logs.length > 0 && (
          <span className="text-xs text-slate-600">{logs.length} 行</span>
        )}
      </div>
      {expanded && (
        <div className="px-3 py-2 text-xs font-mono space-y-0.5 overflow-y-auto h-[calc(100%-2rem)]">
          {logs.length === 0 && !runResult && (
            <span className="text-slate-600 italic">运行节点后在此查看日志和输出</span>
          )}
          {logs.map((line, i) => (
            <div key={i} className="text-slate-400 truncate hover:whitespace-normal">
              {line}
            </div>
          ))}
          {runResult && (
            <div className="mt-2">
              <div className="text-xs text-slate-500 mb-1">输出结果：</div>
              <pre className="text-green-300 whitespace-pre-wrap text-xs bg-slate-800/50 p-2 rounded max-h-32 overflow-y-auto">
                {JSON.stringify(runResult, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
