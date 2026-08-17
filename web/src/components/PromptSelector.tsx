import React, { useEffect, useState } from 'react'

interface PromptFile {
  name: string
  path: string
  size: number
}

interface Props {
  nodeType: string | null
  selectedPrompt: string | null
  onSelectPrompt: (name: string | null) => void
}

export default function PromptSelector({ nodeType, selectedPrompt, onSelectPrompt }: Props) {
  const [prompts, setPrompts] = useState<PromptFile[]>([])
  const [content, setContent] = useState<string>('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetch('/api/prompts').then(r => r.json()).then(setPrompts).catch(() => {})
  }, [])

  const loadContent = async (name: string) => {
    setLoading(true)
    try {
      const r = await fetch(`/api/prompts/${name}`)
      const data = await r.json()
      setContent(data.content || '')
    } catch { setContent('') }
    setLoading(false)
  }

  const handleSelect = (name: string) => {
    onSelectPrompt(name)
    loadContent(name)
  }

  // Filter prompts relevant to this node type
  const relevant = nodeType
    ? prompts.filter(p => p.name.startsWith(nodeType) || p.name.startsWith('genres/'))
    : prompts

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1">
        {relevant.slice(0, 15).map((p) => (
          <button
            key={p.name}
            onClick={() => handleSelect(p.name)}
            className={`text-xs px-1.5 py-0.5 rounded border transition-colors ${
              selectedPrompt === p.name
                ? 'bg-blue-900/50 border-blue-700 text-blue-300'
                : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500'
            }`}
          >
            {p.path}
          </button>
        ))}
      </div>

      {loading && <div className="text-xs text-slate-500">Loading...</div>}

      {content && (
        <textarea
          readOnly
          value={content}
          className="w-full h-32 bg-slate-950 border border-slate-700 rounded text-xs font-mono text-slate-300 p-2 resize-none"
        />
      )}
    </div>
  )
}
