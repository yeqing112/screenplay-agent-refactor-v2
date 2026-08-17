import React, { useState, useEffect, useRef, useMemo } from 'react'
import { NodeSpec } from '../types/nodes'
import { renderResult } from './ResultRenderer'

interface Props {
  nodeType: string | null
  spec: NodeSpec | null
  inputs: Record<string, any>
  onInputChange: (name: string, value: any) => void
  onRun: () => void
  runStatus: string
  logs?: string[]
  runResult?: any
}

// ── Business label maps ────────────────────────────────────

const GENRE_LABELS: Record<string, string> = {
  short_drama: '短剧',
  manhua: '漫画',
  movie: '电影',
  tv_series: '电视剧',
}

const STATUS_LABELS: Record<string, string> = {
  idle: '就绪',
  running: '运行中',
  done: '已完成',
  error: '执行出错',
}

const STATUS_ORDER = ['imported','ingested','read','bibeled','resolved','portraited','adapted','outlined','scripted','storyboarded']

interface BookInfo {
  id: number
  title: string
  chapters: number
  words: number
  scripts: number
  storyboard_shots: number
  status: string
}

// ── Main Component ─────────────────────────────────────────

export default function NodeConfigPanel({
  nodeType, spec, inputs, onInputChange, onRun, runStatus, logs = [], runResult,
}: Props) {
  const [collapsed, setCollapsed] = useState(false)

  if (!nodeType || !spec) {
    return (
      <div className="w-80 bg-slate-900 border-l border-slate-800 flex flex-col items-center justify-center text-slate-600 text-xs flex-shrink-0">
        <div className="text-2xl mb-2 opacity-50">👆</div>
        <div>选中画布上的节点</div>
        <div className="text-[10px] text-slate-700 mt-1">查看配置和运行结果</div>
      </div>
    )
  }

  // Determine if this node has a business-relevant result
  const hasResult = runResult !== null && runResult !== undefined
  const hasError = runStatus === 'error'

  return (
    <div className={`bg-slate-900 border-l border-slate-800 overflow-hidden flex-shrink-0 flex flex-col shadow-2xl shadow-black/50 ${
      collapsed ? 'w-8' : 'w-80'
    } transition-all duration-200`}>
      {collapsed ? (
        <button
          onClick={() => setCollapsed(false)}
          className="w-8 h-full flex items-center justify-center text-slate-600 hover:text-slate-400 hover:bg-slate-800"
          title="展开面板"
        >
          ◀
        </button>
      ) : (
        <>
          {/* === Header === */}
          <div className="px-3 py-2.5 border-b border-slate-800 flex items-center justify-between flex-shrink-0">
            <div className="min-w-0 flex-1">
              <h2 className="text-sm font-bold text-slate-300 truncate">{spec.label}</h2>
              <p className="text-[10px] text-slate-600 mt-0.5 truncate">{spec.description}</p>
            </div>
            <div className="flex items-center gap-1.5 ml-2 flex-shrink-0">
              <StatusBadge status={runStatus} />
              <button
                onClick={() => setCollapsed(true)}
                className="text-xs text-slate-600 hover:text-slate-400 px-1"
                title="收起"
              >▶</button>
            </div>
          </div>

          {/* === Scrollable content === */}
          <div className="flex-1 overflow-y-auto">
            {/* Parameters */}
            <div className="px-3 pt-3 pb-2">
              <div className="text-[10px] font-medium text-slate-500 uppercase tracking-wider mb-3">
                参数配置
              </div>
              <div className="bg-slate-950/40 rounded-lg p-3">
                <ParamForm spec={spec} inputs={inputs} onInputChange={onInputChange} />
              </div>
            </div>

            {/* Divider */}
            <div className="border-t border-slate-800 mx-3" />

            {/* Status + Run button area — always visible */}
            <div className="px-3 py-3 sticky bottom-0 bg-slate-900">
              <RunButton onRun={onRun} runStatus={runStatus} />
            </div>

            {/* Result section — only shows after run */}
            {(runStatus === 'done' || runStatus === 'error') && (
              <div className="px-3 pb-3">
                <div className="border-t border-slate-800 mx-0 mb-3" />

                {/* Error: auto-expand logs */}
                {hasError && (
                  <div className="mb-3">
                    <div className="text-[10px] font-medium text-red-500 flex items-center gap-1 mb-2">
                      <span>✗</span> 执行出错
                    </div>
                    <ErrorLogBlock logs={logs} />
                  </div>
                )}

                {/* Normal result */}
                {hasResult && !hasError && (
                  <ResultSummary spec={spec} result={runResult} />
                )}
              </div>
            )}

            {/* Running: show live logs */}
            {runStatus === 'running' && (
              <div className="px-3 pb-3">
                <div className="border-t border-slate-800 mx-0 mb-3" />
                <LiveLogBlock logs={logs} />
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    idle: 'bg-slate-800 text-slate-500',
    running: 'bg-yellow-900/50 text-yellow-400',
    done: 'bg-green-900/50 text-green-400',
    error: 'bg-red-900/50 text-red-400',
  }
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${colors[status] || colors.idle}`}>
      {STATUS_LABELS[status] || '就绪'}
    </span>
  )
}

// ── Parameter Form ─────────────────────────────────────────

function ParamForm({
  spec, inputs, onInputChange,
}: {
  spec: NodeSpec
  inputs: Record<string, any>
  onInputChange: (name: string, value: any) => void
}) {
  const [books, setBooks] = useState<BookInfo[]>([])
  const [booksLoaded, setBooksLoaded] = useState(false)

  // Load books for book_id parameter
  useEffect(() => {
    const controller = new AbortController()

    fetch('/api/books', { signal: controller.signal })
      .then(r => r.json())
      .then(data => setBooks(data))
      .catch((error) => {
        if ((error as Error).name !== 'AbortError') {
          setBooks([])
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setBooksLoaded(true)
        }
      })
    return () => controller.abort()
  }, [])

  // Deduplicate books by title, keep highest status
  const uniqueBooks = React.useMemo(() => {
    const best: Record<string, BookInfo> = {}
    for (const b of books) {
      if (!best[b.title] || STATUS_ORDER.indexOf(b.status) > STATUS_ORDER.indexOf(best[b.title].status)) {
        best[b.title] = b
      }
    }
    return Object.values(best)
  }, [books])

  // Find the currently selected book
  const currentBookId = inputs['book_id']
  const currentBook = currentBookId
    ? uniqueBooks.find(b => b.id === currentBookId)
    : undefined

  return (
    <div className="space-y-3">
      {spec.inputs.map((inp) => {
        const fieldValue = inputs[inp.name] ?? inp.default ?? ''
        const isIngestFile = inp.name === 'filepath' && (spec as any).support_upload

        return (
          <div key={inp.name}>
            <label className="text-[11px] text-slate-400 block mb-1.5 flex items-center gap-1">
              {inp.name === 'book_id' ? '选择小说' :
               inp.name === 'genre' ? '赛道类型' :
               inp.name === 'filepath' ? '上传小说文件' :
               inp.label}
              {inp.required && <span className="text-red-400">*</span>}
            </label>

            {/* filepath for ingest → file upload */}
            {isIngestFile && (
              <div>
                <label
                  className="flex items-center justify-center gap-2 w-full rounded-lg bg-slate-800 border border-slate-700 border-dashed px-2.5 py-4 text-xs text-slate-400 hover:border-blue-500 hover:text-blue-400 cursor-pointer transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  {fieldValue ? '已选择文件，点击更换' : '点击上传 TXT/MD 文件'}
                  <input
                    type="file"
                    accept=".txt,.md"
                    className="hidden"
                    onChange={async (e) => {
                      const file = e.target.files?.[0]
                      if (!file) return
                      const formData = new FormData()
                      formData.append('file', file)
                      try {
                        const res = await fetch('/api/upload', { method: 'POST', body: formData })
                        const data = await res.json()
                        onInputChange(inp.name, data.filepath)
                      } catch (err) {
                        console.error('Upload failed:', err)
                      }
                    }}
                  />
                </label>
                {fieldValue && (
                  <div className="text-[10px] text-emerald-500 mt-1.5 pl-1">
                    ✓ 文件已上传
                  </div>
                )}
              </div>
            )}

            {/* book_id → book selector */}
            {inp.name === 'book_id' && !isIngestFile && (
              <select
                value={fieldValue}
                onChange={(e) => onInputChange(inp.name, Number(e.target.value))}
                className="w-full rounded-lg bg-slate-800 border border-slate-700 px-2.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30"
              >
                <option value="">选择小说...</option>
                {uniqueBooks.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.title}
                    {b.scripts > 0 ? ` (${b.scripts}集)` : ''}
                  </option>
                ))}
              </select>
            )}

            {/* genre → select with Chinese labels */}
            {inp.name === 'genre' && (
              <select
                value={fieldValue || 'short_drama'}
                onChange={(e) => onInputChange(inp.name, e.target.value)}
                className="w-full rounded-lg bg-slate-800 border border-slate-700 px-2.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30"
              >
                {Object.entries(GENRE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            )}

            {/* episode → +/- stepper */}
            {inp.name === 'episode' && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => onInputChange(inp.name, Math.max(1, (Number(fieldValue) || 1) - 1))}
                  className="w-7 h-7 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-400 hover:bg-slate-700 hover:text-slate-200 transition-colors"
                >
                  −
                </button>
                <input
                  type="number"
                  value={fieldValue}
                  onChange={(e) => onInputChange(inp.name, Math.max(1, Number(e.target.value)))}
                  min={1}
                  className="w-16 rounded-lg bg-slate-800 border border-slate-700 px-2.5 py-1.5 text-xs text-slate-200 text-center focus:outline-none focus:border-blue-500"
                />
                <button
                  onClick={() => onInputChange(inp.name, (Number(fieldValue) || 1) + 1)}
                  className="w-7 h-7 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-400 hover:bg-slate-700 hover:text-slate-200 transition-colors"
                >
                  +
                </button>
                {/* Show max episodes if book selected */}
                {currentBook && currentBook.chapters > 0 && (
                  <span className="text-[10px] text-slate-600">
                    / {currentBook.chapters} 章
                  </span>
                )}
              </div>
            )}

            {/* Other string/int params */}
            {!['book_id', 'genre', 'episode'].includes(inp.name) && !isIngestFile && (
              <input
                type={inp.type === 'int' || inp.type === 'number' ? 'number' : 'text'}
                value={fieldValue}
                onChange={(e) => onInputChange(
                  inp.name,
                  inp.type === 'int' || inp.type === 'number' ? Number(e.target.value) : e.target.value,
                )}
                placeholder={inp.label}
                className="w-full rounded-lg bg-slate-800 border border-slate-700 px-2.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/30"
              />
            )}
          </div>
        )
      })}

      {/* Book info hint */}
      {currentBook && (
        <div className="text-[10px] text-slate-600 bg-slate-800/50 rounded-lg px-2.5 py-1.5 mt-1">
          {currentBook.chapters}章 · {(currentBook.words / 10000).toFixed(1)}万字
          {currentBook.scripts > 0 && ` · 已生成 ${currentBook.scripts} 集`}
        </div>
      )}
    </div>
  )
}

// ── Run Button ─────────────────────────────────────────────

function RunButton({ onRun, runStatus }: { onRun: () => void; runStatus: string }) {
  if (runStatus === 'running') {
    return (
      <button
        disabled
        className="w-full py-2.5 rounded-lg bg-yellow-600/20 text-yellow-400 text-xs font-medium cursor-wait flex items-center justify-center gap-2 border border-yellow-600/30"
      >
        <span className="w-3.5 h-3.5 rounded-full border-2 border-yellow-400 border-t-transparent animate-spin" />
        运行中...
      </button>
    )
  }

  return (
    <button
      onClick={onRun}
      className="w-full py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-all active:scale-[0.98] flex items-center justify-center gap-1.5 shadow-lg shadow-blue-900/30"
    >
      运行
    </button>
  )
}

// ── Result Summary ─────────────────────────────────────────

function ResultSummary({ spec, result }: { spec: NodeSpec; result: any }) {
  return (
    <div>
      <div className="text-[10px] font-medium text-emerald-500 flex items-center gap-1 mb-2">
        <span>✓</span> 执行结果
      </div>
      {renderResult(result, spec.name)}
    </div>
  )
}

// ── Live Log Block ─────────────────────────────────────────

function LiveLogBlock({ logs }: { logs: string[] }) {
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs.length])

  return (
    <div>
      <div className="text-[10px] font-medium text-yellow-500 flex items-center gap-1.5 mb-2">
        <span className="w-1.5 h-1.5 rounded-full bg-yellow-500 animate-pulse" />
        实时日志
      </div>
      <div className="bg-black/40 rounded-lg p-2 max-h-40 overflow-y-auto font-mono text-[10px]">
        {logs.length === 0 && <span className="text-slate-700">等待输出...</span>}
        {logs.map((line, i) => (
          <div key={i} className={`py-0.5 ${
            line.startsWith('ERROR') || line.startsWith('Error') ? 'text-red-400' :
            line.startsWith('WARN') ? 'text-yellow-400' :
            'text-slate-500'
          }`}>
            {line}
          </div>
        ))}
        <div ref={endRef} />
      </div>
    </div>
  )
}

// ── Error Log Block ────────────────────────────────────────

function ErrorLogBlock({ logs }: { logs: string[] }) {
  return (
    <div className="bg-red-950/30 border border-red-900/50 rounded-lg p-2 max-h-40 overflow-y-auto font-mono text-[10px]">
      {logs.map((line, i) => (
        <div key={i} className={`py-0.5 ${
          line.startsWith('ERROR') || line.startsWith('Error') || line.startsWith('Traceback')
            ? 'text-red-400' : 'text-slate-500'
        }`}>
          {line}
        </div>
      ))}
      {logs.length === 0 && (
        <div className="text-slate-600">（无详细日志）</div>
      )}
    </div>
  )
}

// ── Helpers ────────────────────────────────────────────────


