import React, { useCallback, useRef, useEffect, useState } from 'react'
import ReactFlow, {
  Node,
  Edge,
  addEdge,
  Connection,
  useNodesState,
  useEdgesState,
  MiniMap,
  Controls,
  Background,
  BackgroundVariant,
  ReactFlowInstance,
  SelectionMode,
} from 'reactflow'
import 'reactflow/dist/style.css'

import AgentNode from './AgentNode'
import HistorySidebar from './HistorySidebar'
import { NodeSpec } from '../types/nodes'
import { useNodeExecution } from '../hooks/useNodeExecution'
import { buildPipelineLayout } from './pipelineLayout'

const nodeTypes = { agentNode: AgentNode }

interface Props {
  specs: NodeSpec[]
  exec: ReturnType<typeof useNodeExecution>
  onNodeSelect: (node: any) => void
  activeBookId?: number  // when set, auto-load pipeline for this book
}

export default function Canvas({ specs, exec, onNodeSelect, activeBookId }: Props) {
  const { saveWorkflow, loadWorkflows, loadWorkflow } = exec
  const reactFlowWrapper = useRef<HTMLDivElement>(null)
  const [reactFlowInstance, setReactFlowInstance] = useState<ReactFlowInstance | null>(null)
  const [workflowId, setWorkflowId] = useState<string | null>(null)
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  // History sidebar
  const [historyNode, setHistoryNode] = useState<{ id: string; type: string } | null>(null)

  const specMap = specs.reduce((acc, s) => { acc[s.name] = s; return acc }, {} as Record<string, NodeSpec>)

  // Context menu
  const [contextMenu, setContextMenu] = useState<{
    visible: boolean
    x: number
    y: number
    nodeId: string | null  // null = pane
  }>({ visible: false, x: 0, y: 0, nodeId: null })

  const [copiedNode, setCopiedNode] = useState<Node | null>(null)

  // Load pipeline when activeBookId changes
  useEffect(() => {
    if (!activeBookId) return
    const controller = new AbortController()

    fetch('/api/books', { signal: controller.signal })
      .then(r => r.json())
      .then((books: any[]) => {
        const found = books.find((b: any) => b.id === activeBookId)
        if (!found) return
        const { nodes: newNodes, edges: newEdges } = buildPipelineLayout(found)
        setNodes(newNodes)
        setEdges(newEdges)
        setWorkflowId(null)
        onNodeSelect(null)
      })
      .catch((error) => {
        if ((error as Error).name !== 'AbortError') {
          // Ignore load errors in local canvas mode.
        }
      })
    return () => controller.abort()
  }, [activeBookId])

  // Listen for run-complete events from App
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail
      if (!detail) return
      setNodes((nds) =>
        nds.map((n) =>
          n.id === detail.nodeId
            ? { ...n, data: { ...n.data, runStatus: detail.status, runId: detail.runId } }
            : n
        )
      )
    }
    window.addEventListener('node-run-complete', handler)
    return () => window.removeEventListener('node-run-complete', handler)
  }, [setNodes])

  // Listen for node inputs update (e.g. file upload from right panel)
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail
      if (!detail) return
      setNodes((nds) =>
        nds.map((n) =>
          n.id === detail.nodeId
            ? { ...n, data: { ...n.data, inputs: { ...n.data.inputs, ...detail.inputs } } }
            : n
        )
      )
    }
    window.addEventListener('node-inputs-update', handler)
    return () => window.removeEventListener('node-inputs-update', handler)
  }, [setNodes])

  // --- Drop handler ---
  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const raw = e.dataTransfer.getData('application/json')
    if (!raw || !reactFlowInstance) return

    const spec: NodeSpec = JSON.parse(raw)
    const position = reactFlowInstance.screenToFlowPosition({
      x: e.clientX,
      y: e.clientY,
    })

    const defaults: Record<string, any> = {}
    for (const inp of spec.inputs) {
      if (inp.default !== undefined) defaults[inp.name] = inp.default
    }

    const newNode: Node = {
      id: `${spec.name}_${Date.now()}`,
      type: 'agentNode',
      position,
      data: { spec, inputs: defaults, config: {}, runStatus: 'idle' },
    }
    setNodes((nds) => [...nds, newNode])
  }, [reactFlowInstance, setNodes])

  // --- Connect ---
  const onConnect = useCallback((params: Edge | Connection) => {
    setEdges((eds) => addEdge(params, eds))
  }, [setEdges])

  // --- Selection ---
  const onNodeClick = useCallback((_: any, node: Node) => {
    onNodeSelect(node)
  }, [onNodeSelect])

  const onPaneClick = useCallback(() => {
    setContextMenu((prev) => ({ ...prev, visible: false }))
    onNodeSelect(null)
  }, [onNodeSelect])

  // Right-click handlers
  const onNodeContextMenu = useCallback((e: React.MouseEvent, node: Node) => {
    e.preventDefault()
    setContextMenu({ visible: true, x: e.clientX, y: e.clientY, nodeId: node.id })
  }, [])

  const onPaneContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setContextMenu((prev) => ({ ...prev, visible: false }))
    // Don't block default browser context menu on pane — but we override it
  }, [])

  const closeContextMenu = useCallback(() => {
    setContextMenu((prev) => ({ ...prev, visible: false }))
  }, [])

  // Context menu actions
  const deleteNode = useCallback(() => {
    const id = contextMenu.nodeId
    if (!id) return
    setNodes((nds) => nds.filter((n) => n.id !== id))
    setEdges((eds) => eds.filter((e) => e.source !== id && e.target !== id))
    closeContextMenu()
  }, [contextMenu.nodeId, setNodes, setEdges, closeContextMenu])

  const copyNode = useCallback(() => {
    const id = contextMenu.nodeId
    if (!id) return
    const node = nodes.find((n) => n.id === id)
    if (node) setCopiedNode({ ...node })
    closeContextMenu()
  }, [contextMenu.nodeId, nodes, closeContextMenu])

  const pasteNode = useCallback(() => {
    if (!copiedNode || !reactFlowInstance) return
    const newId = `${copiedNode.id}_copy_${Date.now()}`
    const newNode: Node = {
      ...copiedNode,
      id: newId,
      position: {
        x: copiedNode.position.x + 40,
        y: copiedNode.position.y + 40,
      },
      data: { ...copiedNode.data, runStatus: 'idle', runId: undefined },
      selected: false,
    }
    setNodes((nds) => [...nds, newNode])
    closeContextMenu()
  }, [copiedNode, reactFlowInstance, setNodes, closeContextMenu])

  // --- History ---
  const toggleHistory = useCallback((e: React.MouseEvent, node: Node) => {
    e.stopPropagation()
    const nodeType = node.data?.spec?.name
    if (!nodeType) return
    setHistoryNode((prev) =>
      prev?.id === node.id ? null : { id: node.id, type: nodeType }
    )
  }, [])

  const onReplay = useCallback(async (runId: string) => {
    setHistoryNode(null)
    // Relay to App via custom event (App will handle in onNodeSelect)
    window.dispatchEvent(new CustomEvent('replay-run', { detail: { runId } }))
  }, [])

  // --- Multi-select execution ---
  const runSelected = useCallback(() => {
    const selected = nodes.filter(n => n.selected)
    if (selected.length === 0) return

    // Run first selected node via App
    const first = selected[0]
    onNodeSelect(first)
    window.dispatchEvent(new CustomEvent('run-selected', { detail: { nodeId: first.id } }))
  }, [nodes, onNodeSelect])

  // --- Topological run (follow edges) ---
  const runSubgraph = useCallback(() => {
    const selected = nodes.filter(n => n.selected)
    if (selected.length === 0) return

    // Sort by position.y for rough top-to-bottom order
    const sorted = [...selected].sort((a, b) => a.position.y - b.position.y)
    const first = sorted[0]
    onNodeSelect(first)
    window.dispatchEvent(new CustomEvent('run-selected', { detail: { nodeId: first.id } }))
  }, [nodes, onNodeSelect])

  // --- Toolbar ---
  const onSave = useCallback(async () => {
    if (!reactFlowInstance) return
    const viewport = reactFlowInstance.getViewport()
    const id = await saveWorkflow(nodes, edges, viewport, workflowId ?? undefined)
    setWorkflowId(id)
  }, [reactFlowInstance, nodes, edges, saveWorkflow, workflowId])

  const onLoad = useCallback(async () => {
    const list = await loadWorkflows()
    if (!list.length) return
    const data = await loadWorkflow(list[0].id)
    setWorkflowId(data.id)
    if (data.nodes) {
      const restored = data.nodes.map((n: any) => ({
        ...n,
        data: { ...n.data, spec: specMap[n.data?.spec?.name] || n.data.spec, runStatus: 'idle' },
      }))
      setNodes(restored)
    }
    if (data.edges) setEdges(data.edges)
    if (data.viewport && reactFlowInstance) {
      reactFlowInstance.setViewport(data.viewport)
    }
  }, [loadWorkflows, loadWorkflow, specMap, setNodes, setEdges, reactFlowInstance])

  const onClear = useCallback(() => {
    setNodes([])
    setEdges([])
    setWorkflowId(null)
  }, [setNodes, setEdges])

  return (
    <div ref={reactFlowWrapper} className="flex-1 relative">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onInit={setReactFlowInstance}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        onNodeContextMenu={onNodeContextMenu}
        onPaneContextMenu={onPaneContextMenu}
        nodeTypes={nodeTypes}
        fitView
        deleteKeyCode="Delete"
        multiSelectionKeyCode="Shift"
        snapToGrid
        snapGrid={[16, 16]}
        selectionMode={SelectionMode.Partial}
        panOnDrag={[1]}        // 中键拖拽平移
        selectionOnDrag       // 左键拖拽框选
      >
        <MiniMap
          nodeColor={() => '#1e293b'}
          maskColor="rgba(0,0,0,0.6)"
          style={{ background: '#0f172a' }}
        />
        <Controls showInteractive={false} />
        <Background variant={BackgroundVariant.Dots} gap={24} color="#1e293b" />
      </ReactFlow>

      {/* Context menu */}
      {contextMenu.visible && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={closeContextMenu}
            onContextMenu={(e) => { e.preventDefault(); closeContextMenu() }}
          />
          <div
            className="fixed z-50 bg-slate-900 border border-slate-700 rounded-lg shadow-2xl py-1 min-w-[140px]"
            style={{ left: contextMenu.x, top: contextMenu.y }}
          >
            {contextMenu.nodeId && (
              <>
                <button
                  onClick={deleteNode}
                  className="w-full px-3 py-2 text-left text-xs text-red-400 hover:bg-slate-800 flex items-center gap-2"
                >
                  <span>🗑</span> 删除节点
                </button>
                <button
                  onClick={copyNode}
                  className="w-full px-3 py-2 text-left text-xs text-slate-300 hover:bg-slate-800 flex items-center gap-2"
                >
                  <span>📋</span> 复制节点
                </button>
              </>
            )}
            <button
              onClick={pasteNode}
              className={`w-full px-3 py-2 text-left text-xs flex items-center gap-2 ${
                copiedNode ? 'text-slate-300 hover:bg-slate-800' : 'text-slate-600 cursor-not-allowed'
              }`}
              disabled={!copiedNode}
            >
              <span>📄</span> 粘贴{copiedNode ? '' : '（无复制内容）'}
            </button>
          </div>
        </>
      )}

      {/* History sidebar */}
      {historyNode && (
        <HistorySidebar
          nodeType={historyNode.type}
          nodeId={historyNode.id}
          onReplay={onReplay}
          open={true}
          onClose={() => setHistoryNode(null)}
        />
      )}

      {/* Toolbar overlay */}
      <div className="absolute top-3 left-3 z-10 flex gap-2">
        <button onClick={onSave} className="px-2.5 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 border border-slate-700 transition-colors">
          💾 保存
        </button>
        <button onClick={onLoad} className="px-2.5 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 border border-slate-700 transition-colors">
          📂 加载
        </button>
        <button onClick={onClear} className="px-2.5 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-xs text-slate-300 border border-slate-700 transition-colors">
          🗑 清空
        </button>
        <button onClick={runSelected} className="px-2.5 py-1.5 rounded bg-emerald-800 hover:bg-emerald-700 text-xs text-emerald-300 border border-emerald-700 transition-colors">
          ▶ 选中执行
        </button>
        {workflowId && (
          <span className="px-2.5 py-1.5 text-xs text-slate-600">
            ID: {workflowId}
          </span>
        )}
      </div>
    </div>
  )
}
