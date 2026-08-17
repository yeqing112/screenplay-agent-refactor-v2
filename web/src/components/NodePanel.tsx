import React from 'react'
import { NodeSpec } from '../types/nodes'

const CATEGORY_LABELS: Record<string, string> = {
  input: '📥 输入',
  analysis: '🔍 分析',
  adapt: '🎯 改编',
  script: '📝 剧本',
  vision: '🎨 视觉',
}

interface Props {
  specs: NodeSpec[]
  onDragStart: (spec: NodeSpec) => void
}

export default function NodePanel({ specs, onDragStart }: Props) {
  const grouped = specs.reduce((acc, spec) => {
    if (!acc[spec.category]) acc[spec.category] = []
    acc[spec.category].push(spec)
    return acc
  }, {} as Record<string, NodeSpec[]>)

  const handleDragStart = (e: React.DragEvent, spec: NodeSpec) => {
    e.dataTransfer.setData('application/json', JSON.stringify(spec))
    e.dataTransfer.effectAllowed = 'move'
  }

  return (
    <div className="w-56 bg-slate-900 border-r border-slate-800 overflow-y-auto flex-shrink-0">
      <div className="px-3 py-3 border-b border-slate-800">
        <h2 className="text-sm font-bold text-slate-300">节点库</h2>
      </div>
      {Object.entries(grouped).map(([category, items]) => (
        <div key={category} className="px-2 py-2">
          <div className="text-xs font-medium text-slate-500 mb-1 px-1 uppercase tracking-wider">
            {CATEGORY_LABELS[category] || category}
          </div>
          {items.map((spec) => (
            <div
              key={spec.name}
              draggable
              onDragStart={(e) => handleDragStart(e, spec)}
              className="px-2 py-1.5 mb-0.5 rounded text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-800 cursor-grab active:cursor-grabbing transition-colors"
            >
              <div className="font-medium">{spec.label}</div>
              <div className="text-slate-600 mt-0.5 truncate">{spec.description}</div>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
