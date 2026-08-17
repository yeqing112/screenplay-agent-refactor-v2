import { useState, useCallback, useRef, useMemo } from 'react'
import { NodeSpec, RunResult } from '../types/nodes'

const API = '/api'

export function useNodeExecution() {
  const [specs, setSpecs] = useState<NodeSpec[]>([])
  const [loading, setLoading] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const fetchRegistry = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await fetch(`${API}/nodes/registry`, { signal })
      const data = await res.json()
      setSpecs(data)
      return data as NodeSpec[]
    } catch (error) {
      if ((error as Error).name === 'AbortError') {
        return [] as NodeSpec[]
      }
      throw error
    }
  }, [])

  const runNode = useCallback(async (
    nodeId: string,
    nodeType: string,
    inputs: Record<string, any>,
    config: Record<string, any> = {},
  ): Promise<string> => {
    const res = await fetch(`${API}/nodes/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_id: nodeId, node_type: nodeType, inputs, config }),
    })
    const data = await res.json()
    return data.run_id
  }, [])

  const pollRun = useCallback(async (
    runId: string,
    onUpdate: (result: RunResult) => void,
    intervalMs = 1000,
  ): Promise<RunResult> => {
    return new Promise((resolve) => {
      const poll = async () => {
        try {
          const res = await fetch(`${API}/nodes/run/${runId}`)
          const data: RunResult = await res.json()
          onUpdate(data)
          if (data.status !== 'running') {
            resolve(data)
            return
          }
        } catch (e) {
          // ignore
        }
        setTimeout(poll, intervalMs)
      }
      poll()
    })
  }, [])

  const streamLogs = useCallback(async (
    runId: string,
    onLog: (line: string) => void,
  ): Promise<void> => {
    abortRef.current = new AbortController()
    try {
      const res = await fetch(`${API}/nodes/run/${runId}/stream`, {
        signal: abortRef.current.signal,
      })
      const reader = res.body?.getReader()
      if (!reader) return
      const decoder = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const text = decoder.decode(value)
        text.split('\n').filter(l => l.startsWith('data: ')).forEach(line => {
          onLog(line.replace('data: ', ''))
        })
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') throw e
    }
  }, [])

  const abortStream = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  // --- Search ---
  const search = useCallback(async (query: string) => {
    if (!query) return []
    const res = await fetch(`${API}/search?query=${encodeURIComponent(query)}`)
    return res.json()
  }, [])

  // --- Diff ---
  const diffRuns = useCallback(async (runIdA: string, runIdB: string) => {
    const res = await fetch(`${API}/runs/${runIdA}/diff?run_id_b=${runIdB}`)
    return res.json()
  }, [])

  // --- Replay ---
  const replayRun = useCallback(async (runId: string): Promise<string> => {
    const res = await fetch(`${API}/runs/${runId}/replay`, { method: 'GET' })
    const data = await res.json()
    return data.run_id
  }, [])

  // --- History ---
  const getHistory = useCallback(async (nodeType: string) => {
    const res = await fetch(`${API}/runs?node_type=${encodeURIComponent(nodeType)}`)
    return res.json()
  }, [])

  // --- Workflows ---
  const loadWorkflows = useCallback(async () => {
    const res = await fetch(`${API}/workflows`)
    return res.json()
  }, [])

  const saveWorkflow = useCallback(async (
    nodes: any[],
    edges: any[],
    viewport: any = null,
    workflowId?: string,
  ): Promise<string> => {
    const body = JSON.stringify({ nodes, edges, viewport })
    if (workflowId) {
      await fetch(`${API}/workflows/${workflowId}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body,
      })
      return workflowId
    }
    const res = await fetch(`${API}/workflows`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body,
    })
    const data = await res.json()
    return data.id
  }, [])

  const loadWorkflow = useCallback(async (workflowId: string) => {
    const res = await fetch(`${API}/workflows/${workflowId}`)
    return res.json()
  }, [])

  return useMemo(() => ({
    specs, loading, fetchRegistry,
    runNode, pollRun, streamLogs, abortStream,
    search, diffRuns, replayRun, getHistory,
    loadWorkflows, saveWorkflow, loadWorkflow,
  }), [
    specs,
    loading,
    fetchRegistry,
    runNode,
    pollRun,
    streamLogs,
    abortStream,
    search,
    diffRuns,
    replayRun,
    getHistory,
    loadWorkflows,
    saveWorkflow,
    loadWorkflow,
  ])
}
