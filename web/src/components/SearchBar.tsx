import React, { useState, useRef, useEffect } from 'react'
import { useNodeExecution } from '../hooks/useNodeExecution'

interface SearchResult {
  type: string
  id: string
  label: string
  sub: string
}

interface Props {
  exec: ReturnType<typeof useNodeExecution>
  onSelect: (type: string, id: string) => void
}

export default function SearchBar({ exec, onSelect }: Props) {
  const { search } = exec
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [focused, setFocused] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout>>()
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!query.trim()) { setResults([]); return }
    clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      const data = await search(query)
      setResults(data)
    }, 300)
    return () => clearTimeout(timer.current)
  }, [query, search])

  useEffect(() => {
    const handle = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setFocused(false)
      }
    }
    document.addEventListener('mousedown', handle)
    return () => document.removeEventListener('mousedown', handle)
  }, [])

  return (
    <div ref={ref} className="relative">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => setFocused(true)}
        placeholder="搜索节点、工作流..."
        className="w-48 px-2 py-1 rounded bg-slate-800 border border-slate-700 text-xs text-slate-300 placeholder-slate-600 focus:outline-none focus:border-blue-500 transition-colors"
      />
      {focused && results.length > 0 && (
        <div className="absolute top-full left-0 mt-1 w-64 bg-slate-900 border border-slate-800 rounded-lg shadow-xl z-30 max-h-48 overflow-y-auto">
          {results.map((r) => (
            <div
              key={`${r.type}-${r.id}`}
              className="px-3 py-2 hover:bg-slate-800 cursor-pointer"
              onClick={() => { onSelect(r.type, r.id); setFocused(false); setQuery('') }}
            >
              <div className="flex items-center gap-2">
                <span className="text-[10px] px-1 py-0.5 rounded bg-slate-800 text-slate-500 uppercase">
                  {r.type}
                </span>
                <span className="text-xs text-slate-300">{r.label}</span>
              </div>
              <div className="text-[10px] text-slate-600 ml-1">{r.sub}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
