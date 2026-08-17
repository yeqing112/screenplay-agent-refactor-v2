import { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import { useNodeExecution } from '../hooks/useNodeExecution'
import { CANVAS_MODE_LABELS, resolveDefaultMode, type CanvasMode } from './canvasMode'

const Canvas = lazy(() => import('../components/Canvas'))
const NodeConfigPanel = lazy(() => import('../components/NodeConfigPanel'))
const NodePanel = lazy(() => import('../components/NodePanel'))
const LegacyProductionMode = lazy(() => import('../components/ProductionMode'))
const ProductWorkspace = lazy(() => import('../components/ProductWorkspace'))
const DirectorMode = lazy(() => import('../prototyping/DirectorMode'))

interface Props {
  book: { id: number; title: string }
  onBack: () => void
  onSelectBook: (book: { id: number; title: string }) => void
}

function ModeLoadingFallback() {
  return (
    <div className="h-full flex items-center justify-center bg-slate-950 text-slate-500 text-sm">
      正在加载工作台...
    </div>
  )
}

export default function CanvasPage({ book, onBack, onSelectBook }: Props) {
  const exec = useNodeExecution()
  const { fetchRegistry, runNode, pollRun } = exec
  const [loaded, setLoaded] = useState(false)
  const [mode, setMode] = useState<CanvasMode>('production')
  const [modeTouched, setModeTouched] = useState(false)
  const [bookData, setBookData] = useState<any>(null)

  const [selectedNode, setSelectedNode] = useState<any>(null)
  const [selectedSpec, setSelectedSpec] = useState<any>(null)
  const [selectedInputs, setSelectedInputs] = useState<Record<string, any>>({})
  const [runStatus, setRunStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle')
  const [logs, setLogs] = useState<string[]>([])
  const [runResult, setRunResult] = useState<any>(null)

  const refreshBookData = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await fetch('/api/books', { signal })
      const list = await res.json()
      const found = list.find((item: any) => item.id === book.id)
      setBookData(found ?? null)
    } catch (error) {
      if ((error as Error).name === 'AbortError') {
        return
      }
    }
  }, [book.id])

  const handleModeChange = useCallback((nextMode: CanvasMode) => {
    setModeTouched(true)
    setMode(nextMode)
  }, [])

  const handleBookChange = useCallback(async (bookId: number) => {
    try {
      const response = await fetch('/api/books')
      const list = await response.json()
      const nextBook = list.find((item: any) => item.id === bookId)
      if (nextBook) {
        onSelectBook({ id: nextBook.id, title: nextBook.title })
        return
      }
    } catch {
      // Fall through.
    }

    onSelectBook({ id: bookId, title: `项目 ${bookId}` })
  }, [onSelectBook])

  useEffect(() => {
    setBookData(null)
    setModeTouched(false)
    setMode('production')
  }, [book.id])

  useEffect(() => {
    if (modeTouched) return
    setMode(resolveDefaultMode())
  }, [bookData, modeTouched])

  useEffect(() => {
    const controller = new AbortController()

    fetchRegistry(controller.signal)
      .then(() => {
        if (!controller.signal.aborted) {
          setLoaded(true)
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setLoaded(true)
        }
      })

    refreshBookData(controller.signal)

    return () => controller.abort()
  }, [fetchRegistry, refreshBookData])

  const handleNodeSelect = useCallback((node: any) => {
    if (!node) {
      setSelectedNode(null)
      setSelectedSpec(null)
      setSelectedInputs({})
      return
    }

    setSelectedNode(node)
    setSelectedSpec(node.data?.spec || null)
    setSelectedInputs(node.data?.inputs || {})

    if (node.data?.runId) {
      fetch(`/api/nodes/run/${node.data.runId}`)
        .then((response) => response.json())
        .then((data) => {
          if (data.logs) {
            setLogs(data.logs)
            setRunResult(data.result)
          }
        })
        .catch(() => {})
    } else {
      setLogs([])
      setRunResult(null)
    }

    setRunStatus(node.data?.runStatus || 'idle')
  }, [])

  const handleInputChange = useCallback((name: string, value: any) => {
    setSelectedInputs((prev) => ({ ...prev, [name]: value }))
    if (selectedNode) {
      window.dispatchEvent(
        new CustomEvent('node-inputs-update', {
          detail: { nodeId: selectedNode.id, inputs: { [name]: value } },
        }),
      )
    }
  }, [selectedNode])

  const handleRun = useCallback(async () => {
    if (!selectedNode || !selectedSpec) return

    setLogs([])
    setRunResult(null)
    setRunStatus('running')

    const filledInputs = { ...selectedInputs }
    for (const input of selectedSpec.inputs) {
      if (filledInputs[input.name] === undefined || filledInputs[input.name] === null || filledInputs[input.name] === '') {
        filledInputs[input.name] = input.default ?? ''
      }
    }

    window.dispatchEvent(
      new CustomEvent('node-inputs-update', {
        detail: { nodeId: selectedNode.id, inputs: filledInputs },
      }),
    )

    try {
      const runId = await runNode(selectedNode.id, selectedSpec.name, filledInputs)
      const result = await pollRun(
        runId,
        (data: any) => {
          if (data.logs) setLogs(data.logs)
        },
        2000,
      )

      setRunResult(result.result)
      setRunStatus(result.status === 'done' ? 'done' : 'error')
      window.dispatchEvent(
        new CustomEvent('node-run-complete', {
          detail: { nodeId: selectedNode.id, runId, status: result.status },
        }),
      )
    } catch (error: any) {
      setLogs((prev) => [...prev, `ERROR: ${error.message}`])
      setRunStatus('error')
    }
  }, [selectedNode, selectedSpec, selectedInputs, runNode, pollRun])

  if (!loaded) {
    return (
      <div className="h-full flex items-center justify-center bg-slate-950 text-slate-500 text-sm">
        加载中...
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-slate-950">
      <div className="h-10 bg-slate-900 border-b border-slate-800 flex items-center px-4 gap-4 flex-shrink-0">
        <button onClick={onBack} className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors">
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          项目列表
        </button>

        <span className="text-sm font-bold text-slate-300">{book.title}</span>

        <div className="ml-auto flex items-center gap-3">
          <div className="flex items-center gap-1 bg-slate-800 rounded-lg p-0.5">
            {(['production', 'legacy', 'prototype', 'dev'] as const).map((item) => (
              <button
                key={item}
                onClick={() => handleModeChange(item)}
                className={`text-[11px] px-2.5 py-1 rounded-md transition-colors ${
                  mode === item ? 'bg-slate-700 text-slate-200' : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {CANVAS_MODE_LABELS[item]}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <Suspense fallback={<ModeLoadingFallback />}>
          {mode === 'production' ? (
            <ProductWorkspace
              book={book}
              bookData={bookData}
              onRefresh={() => {
                void refreshBookData()
              }}
              onBookChange={handleBookChange}
              onOpenLegacy={() => handleModeChange('legacy')}
              onOpenPrototype={() => handleModeChange('prototype')}
              onSwitchToDev={() => handleModeChange('dev')}
            />
          ) : mode === 'legacy' ? (
            <LegacyProductionMode
              book={book}
              bookData={bookData}
              onRefresh={refreshBookData}
              onBookChange={handleBookChange}
              onSwitchToDev={() => handleModeChange('dev')}
              onOpenPrototype={() => handleModeChange('prototype')}
            />
          ) : mode === 'prototype' ? (
            <DirectorMode
              book={book}
              onBack={onBack}
              onOpenPreparation={() => handleModeChange('production')}
              onOpenAdvanced={() => handleModeChange('dev')}
            />
          ) : (
            <>
              <NodePanel specs={exec.specs} onDragStart={() => {}} />
              <div className="flex flex-1">
                <Canvas specs={exec.specs} exec={exec} onNodeSelect={handleNodeSelect} activeBookId={book.id} />
                <NodeConfigPanel
                  nodeType={selectedNode?.id || null}
                  spec={selectedSpec}
                  inputs={selectedInputs}
                  onInputChange={handleInputChange}
                  onRun={handleRun}
                  runStatus={runStatus}
                  logs={logs}
                  runResult={runResult}
                />
              </div>
            </>
          )}
        </Suspense>
      </div>
    </div>
  )
}
