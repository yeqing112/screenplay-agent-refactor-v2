import React from 'react'

// ── Result renderer: auto-detect best format ───────────────

export function renderResult(result: any, nodeName: string) {
  if (result === null || result === undefined) return null

  // 1. Pure string — text viewer
  if (typeof result === 'string') {
    return <TextViewer text={result} />
  }

  // 2. Dict with special keys
  if (typeof result === 'object' && !Array.isArray(result)) {
    // Check / QA
    if (result.overall_score !== undefined || result.score !== undefined) {
      return <QACard result={result} />
    }
    // Outline
    if (result.episodes || result.outline) {
      return <OutlineViewer result={result} />
    }
  }

  // 3. Storyboard: array with shots
  if (Array.isArray(result) && result.length > 0 && result[0].shot_id !== undefined) {
    return <StoryboardTable shots={result} />
  }

  // 4. Props / Locations: array of named items
  if (Array.isArray(result) && result.length > 0 && (result[0].prop_name || result[0].name)) {
    return <ItemList items={result} />
  }

  // 5. Any array — generic table
  if (Array.isArray(result) && result.length > 0 && typeof result[0] === 'object') {
    return <GenericTable data={result} />
  }

  // 6. Fallback: key-value view
  return <KVView data={result} />
}

// ── Text Viewer ────────────────────────────────────────────

function TextViewer({ text }: { text: string }) {
  // Detect if it's a script (starts with # or ## scene markers)
  const isScript = /^#/.test(text.trim())

  if (isScript) {
    return (
      <div className="text-xs">
        {text.split('\n').map((line, i) => {
          // Highlight scene headers
          if (line.startsWith('##') || line.startsWith('#')) {
            return (
              <div key={i} className="text-emerald-400 font-bold py-1 mt-1 text-sm">
                {line.replace(/^#+\s*/, '')}
              </div>
            )
          }
          // Highlight action lines (inside brackets)
          if (line.trim().startsWith('[') && line.trim().endsWith(']')) {
            return (
              <div key={i} className="text-yellow-400/70 italic py-0.5 text-[11px]">
                {line}
              </div>
            )
          }
          // Character dialogues (bold)
          if (line.trim().includes('**：**') || /^[^\s：]*[：:]/.test(line)) {
            const parts = line.split(/[：:]/)
            return (
              <div key={i} className="text-slate-200 py-0.5">
                <span className="font-bold text-blue-300">{parts[0]}</span>
                ：{parts.slice(1).join('：')}
              </div>
            )
          }
          return (
            <div key={i} className="text-slate-400 py-0.5 text-[11px]">
              {line || '\u00A0'}
            </div>
          )
        })}
      </div>
    )
  }

  // Plain text
  const lines = text.split('\n').length
  return (
    <pre className="text-[11px] text-slate-300 whitespace-pre-wrap font-sans bg-slate-800/30 rounded-lg p-2.5 max-h-96 overflow-y-auto leading-relaxed">
      {text}
    </pre>
  )
}

// ── QA / Check card ────────────────────────────────────────

function QACard({ result }: { result: any }) {
  const score = result.overall_score ?? result.score ?? '—'
  const errors = result.high_errors ?? result.errors ?? result.issues ?? []
  const details = result.details ?? result.items ?? []

  const color = Number(score) >= 8 ? 'emerald' : Number(score) >= 6 ? 'yellow' : 'red'

  return (
    <div className="space-y-3">
      {/* Score */}
      <div className="flex items-center gap-3 bg-slate-800/50 rounded-lg p-3">
        <div className={`text-2xl font-bold text-${color}-400`}>{score}</div>
        <div className="text-xs text-slate-400">
          <div className="text-slate-300 font-medium">综合评分</div>
          <div className="text-[10px]">满分 10 分</div>
        </div>
      </div>

      {/* Errors list */}
      {Array.isArray(errors) && errors.length > 0 && (
        <div>
          <div className="text-[10px] text-red-400 mb-1.5">
            共 {errors.length} 个问题
          </div>
          <div className="space-y-1">
            {errors.map((err: any, i: number) => (
              <div key={i} className="text-[11px] bg-red-950/20 border border-red-900/30 rounded px-2 py-1.5">
                <div className="text-slate-300">{err.description || err.message || String(err)}</div>
                {err.line !== undefined && (
                  <div className="text-[10px] text-slate-600 mt-0.5">第 {err.line} 行</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Details */}
      {Array.isArray(details) && details.length > 0 && (
        <div>
          <div className="text-[10px] text-slate-500 mb-1">详细检查项</div>
          <div className="space-y-1">
            {details.map((d: any, i: number) => (
              <div key={i} className="flex justify-between text-[11px] bg-slate-800/30 rounded px-2 py-1">
                <span className="text-slate-400">{d.name || d.item || `项 ${i + 1}`}</span>
                <span className={`font-medium ${d.passed ? 'text-emerald-400' : 'text-red-400'}`}>
                  {d.passed ? '✓' : '✗'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {!Array.isArray(errors) && <RawFallback data={result} />}
    </div>
  )
}

// ── Storyboard table ───────────────────────────────────────

function StoryboardTable({ shots }: { shots: any[] }) {
  const uniqueScenes = new Set(shots.map(s => s.scene_name)).size

  return (
    <div>
      <div className="text-[10px] text-slate-500 mb-2">
        共 {shots.length} 个镜头 · {uniqueScenes} 个场景
      </div>
      <div className="space-y-2 max-h-96 overflow-y-auto">
        {shots.map((shot, i) => (
          <div key={i} className="bg-slate-800/40 rounded-lg px-2.5 py-2 text-[11px]">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-emerald-400 font-bold">#{shot.shot_id}</span>
              <span className="text-slate-500">{shot.scene_name}</span>
              <span className="text-slate-600 ml-auto">
                {shot.camera_angle} / {shot.duration}s
              </span>
            </div>
            {shot.dialogue && (
              <div className="text-slate-300 mb-0.5 truncate">{shot.dialogue}</div>
            )}
            <div className="text-[10px] text-slate-600 flex gap-2">
              <span>{shot.camera_movement || 'static'}</span>
              {shot.transition && <span>→ {shot.transition}</span>}
              {shot.bgm_mood && <span>🎵 {shot.bgm_mood}</span>}
            </div>
          </div>
        ))}
      </div>
      <RawCollapse data={shots} />
    </div>
  )
}

// ── Item list (props / locations / makeups) ────────────────

function ItemList({ items }: { items: any[] }) {
  return (
    <div className="space-y-1.5 max-h-96 overflow-y-auto">
      {items.map((item, i) => {
        const name = item.prop_name || (item.name || '')
        const desc = item.description || item.visual_prompt_zh || item.core_prompt_zh || ''
        const extras = Object.entries(item)
          .filter(([k]) => !['name', 'prop_name', 'description', 'visual_prompt_zh', 'core_prompt_zh'].includes(k))
          .filter(([, v]) => v !== null && v !== undefined && v !== '')

        return (
          <div key={i} className="bg-slate-800/40 rounded-lg px-2.5 py-2">
            <div className="text-xs text-slate-200 font-medium mb-0.5">{name}</div>
            {desc && <div className="text-[10px] text-slate-500 mb-0.5 truncate">{desc}</div>}
            {extras.length > 0 && (
              <div className="text-[9px] text-slate-600 flex flex-wrap gap-1.5 mt-0.5">
                {extras.slice(0, 3).map(([k, v]) => (
                  <span key={k} className="bg-slate-800/60 px-1 rounded">
                    {k}: {String(v).slice(0, 40)}
                  </span>
                ))}
              </div>
            )}
          </div>
        )
      })}
      <RawCollapse data={items} />
    </div>
  )
}

// ── Outline viewer ─────────────────────────────────────────

function OutlineViewer({ result }: { result: any }) {
  const episodes = result.episodes || result.outline || []
  return (
    <div className="space-y-1.5 max-h-96 overflow-y-auto">
      {Array.isArray(episodes) && episodes.map((ep: any, i: number) => (
        <div key={i} className="bg-slate-800/40 rounded-lg px-2.5 py-2">
          <div className="text-[11px] text-slate-200 font-medium">
            #{ep.episode || ep.id || i + 1}: {ep.title || ep.name || '(无标题)'}
          </div>
          {ep.summary && <div className="text-[10px] text-slate-500 mt-0.5">{ep.summary.slice(0, 120)}</div>}
        </div>
      ))}
      {!Array.isArray(episodes) && <RawFallback data={result} />}
    </div>
  )
}

// ── Generic table ──────────────────────────────────────────

function GenericTable({ data }: { data: any[] }) {
  const keys = data.length > 0 ? Object.keys(data[0]) : []
  return (
    <div className="max-h-64 overflow-y-auto">
      <table className="w-full text-[10px]">
        <thead>
          <tr className="text-slate-500 border-b border-slate-800">
            {keys.slice(0, 5).map(k => (
              <th key={k} className="text-left px-1.5 py-1 font-medium">{k}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/30">
              {keys.slice(0, 5).map(k => (
                <td key={k} className="px-1.5 py-1 text-slate-400 truncate max-w-[100px]">
                  {String(row[k] ?? '').slice(0, 60)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {keys.length > 5 && (
        <div className="text-[9px] text-slate-600 mt-1">... 还有 {keys.length - 5} 列未显示</div>
      )}
    </div>
  )
}

// ── Key-Value JSON view (fallback) ─────────────────────────

function KVView({ data }: { data: any }) {
  const entries = typeof data === 'object' ? Object.entries(data) : [['value', data]]
  return (
    <div className="space-y-1 max-h-64 overflow-y-auto">
      {entries.map(([key, val]) => (
        <div key={key} className="flex gap-2 text-[11px] bg-slate-800/30 rounded px-2 py-1">
          <span className="text-slate-500 w-24 flex-shrink-0 truncate font-medium">{key}</span>
          <span className="text-slate-300 break-all">
            {typeof val === 'object' ? JSON.stringify(val).slice(0, 200) : String(val)}
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Raw data collapse (backup for every type) ──────────────

function RawCollapse({ data }: { data: any }) {
  return (
    <details className="group mt-2">
      <summary className="text-[9px] text-slate-600 cursor-pointer hover:text-slate-400 select-none">
        查看原始 JSON ▾
      </summary>
      <pre className="mt-1 text-[9px] text-green-300/60 whitespace-pre-wrap bg-black/40 rounded p-2 max-h-32 overflow-y-auto font-mono">
        {JSON.stringify(data, null, 2).slice(0, 3000)}
      </pre>
    </details>
  )
}

function RawFallback({ data }: { data: any }) {
  return (
    <pre className="text-[10px] text-slate-400 whitespace-pre-wrap bg-black/40 rounded p-2 max-h-48 overflow-y-auto font-mono">
      {JSON.stringify(data, null, 2).slice(0, 2000)}
    </pre>
  )
}
