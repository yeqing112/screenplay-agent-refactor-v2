/**
 * Build a pipeline layout for the given book.
 * Returns [nodes, edges] for ReactFlow.
 */
import { Node, Edge, MarkerType } from 'reactflow'

interface BookInfo {
  id: number
  title: string
  chapters: number
  status: string
  scripts: number
  storyboard_shots: number
}

const PIPELINE_NODES = [
  { name: 'ingest',       label: '📥 导入',     category: 'input',   inputs: [{ name: 'filepath', default: '' }], support_upload: true },
  { name: 'read',         label: '🔍 逐章分析', category: 'analysis', inputs: [{ name: 'book_id', default: 0 }] },
  { name: 'bible',        label: '📖 小说圣经', category: 'analysis', inputs: [{ name: 'book_id', default: 0 }] },
  { name: 'resolve',      label: '🔄 别名归并', category: 'analysis', inputs: [{ name: 'book_id', default: 0 }] },
  { name: 'portrait',     label: '👤 人物画像', category: 'analysis', inputs: [{ name: 'book_id', default: 0 }] },
  { name: 'adapt',        label: '🎯 改编方案', category: 'adapt',    inputs: [{ name: 'book_id', default: 0 }, { name: 'genre', default: 'short_drama' }] },
  { name: 'outline',      label: '📋 分集大纲', category: 'adapt',    inputs: [{ name: 'book_id', default: 0 }] },
  { name: 'script',       label: '📝 剧本写作', category: 'script',   inputs: [{ name: 'book_id', default: 0 }, { name: 'episode', default: 1 }, { name: 'genre', default: 'short_drama' }] },
  { name: 'era_scan',     label: '⏳ 时代规范', category: 'vision',   inputs: [{ name: 'book_id', default: 0 }] },
  { name: 'props',        label: '🪑 道具清单', category: 'vision',   inputs: [{ name: 'book_id', default: 0 }, { name: 'episode', default: 1 }] },
  { name: 'locations',    label: '🏠 场景规划', category: 'vision',   inputs: [{ name: 'book_id', default: 0 }, { name: 'episode', default: 1 }] },
  { name: 'makeup',       label: '💄 定妆照',   category: 'vision',   inputs: [{ name: 'book_id', default: 0 }, { name: 'episode', default: 1 }] },
  { name: 'storyboard',   label: '🎬 分镜表',   category: 'vision',   inputs: [{ name: 'book_id', default: 0 }, { name: 'episode', default: 1 }, { name: 'genre', default: 'short_drama' }] },
  { name: 'check',        label: '✅ 质检',     category: 'script',   inputs: [{ name: 'book_id', default: 0 }, { name: 'episode', default: 1 }] },
]

const EDGES: [string, string][] = [
  ['ingest', 'read'],
  ['read', 'bible'],
  ['bible', 'resolve'],
  ['resolve', 'portrait'],
  ['portrait', 'adapt'],
  ['adapt', 'outline'],
  ['outline', 'script'],
  ['outline', 'era_scan'],
  ['era_scan', 'props'],
  ['era_scan', 'locations'],
  ['era_scan', 'makeup'],
  ['props', 'storyboard'],
  ['locations', 'storyboard'],
  ['makeup', 'storyboard'],
  ['script', 'check'],
]

// Run status lookup: based on Book.status, determine which nodes have run
const NODE_STATUS_FROM_BOOK: Record<string, string[]> = {
  imported:     ['ingest'],
  ingested:     ['ingest'],
  read:         ['ingest', 'read'],
  bibeled:      ['ingest', 'read', 'bible'],
  resolved:     ['ingest', 'read', 'bible', 'resolve'],
  portraited:   ['ingest', 'read', 'bible', 'resolve', 'portrait'],
  adapted:      ['ingest', 'read', 'bible', 'resolve', 'portrait', 'adapt'],
  outlined:     ['ingest', 'read', 'bible', 'resolve', 'portrait', 'adapt', 'outline'],
  scripted:     ['ingest', 'read', 'bible', 'resolve', 'portrait', 'adapt', 'outline', 'script'],
  storyboarded: ['ingest', 'read', 'bible', 'resolve', 'portrait', 'adapt', 'outline', 'script', 'era_scan', 'props', 'locations', 'makeup', 'storyboard'],
}

const COLUMN_WIDTH = 180
const ROW_HEIGHT = 90
const START_X = 60
const START_Y = 60

const CATEGORY_ORDER = ['input', 'analysis', 'adapt', 'script', 'vision']

export function buildPipelineLayout(book: BookInfo): { nodes: Node[]; edges: Edge[] } {
  // Group nodes by category
  const byCategory: Record<string, typeof PIPELINE_NODES> = {}
  for (const n of PIPELINE_NODES) {
    if (!byCategory[n.category]) byCategory[n.category] = []
    byCategory[n.category].push(n)
  }

  // Compute which nodes have run
  const doneSet = new Set(NODE_STATUS_FROM_BOOK[book.status] || [])

  // Layout: left to right by category
  const nodes: Node[] = []
  const edges: Edge[] = []

  CATEGORY_ORDER.forEach((cat, colIdx) => {
    const items = byCategory[cat] || []
    items.forEach((spec, rowIdx) => {
      const id = spec.name
      const eid = `edge_${id}`

      const done = doneSet.has(id)
      nodes.push({
        id,
        type: 'agentNode',
        position: { x: START_X + colIdx * COLUMN_WIDTH, y: START_Y + rowIdx * ROW_HEIGHT },
        data: {
          spec: {
            name: spec.name,
            label: spec.label,
            category: spec.category,
            inputs: spec.inputs,
            outputs: [],
            support_upload: spec.name === 'ingest',
          },
          inputs: {
            book_id: book.id,
            ...(spec.name === 'ingest' ? {} : { book_id: book.id }),
          },
          config: {},
          runStatus: done ? 'done' : 'idle',
          // Disable drag for pipeline layout
          draggable: false,
        },
        selected: false,
      })
    })
  })

  EDGES.forEach(([src, tgt], idx) => {
    edges.push({
      id: `e_${src}_${tgt}`,
      source: src,
      target: tgt,
      animated: true,
      style: { stroke: '#475569', strokeWidth: 1.5 },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#475569' },
    })
  })

  return { nodes, edges }
}
