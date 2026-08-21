import { useCallback, useEffect, useState } from 'react'
import { BookOpen, ChevronLeft, ChevronRight, FileText } from 'lucide-react'

interface Chapter {
  id: number
  seq: number
  title: string
  content?: string
  word_count: number
  status: string
  summary: string
}

interface Props {
  bookId: number
}

export default function ChapterViewer({ bookId }: Props) {
  const [chapters, setChapters] = useState<Chapter[]>([])
  const [selectedIdx, setSelectedIdx] = useState(0)
  const [loading, setLoading] = useState(true)
  const [chapterLoading, setChapterLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    fetch(`/api/books/${bookId}/chapters`)
      .then(r => r.json())
      .then(data => {
        setChapters(data)
        setSelectedIdx(0)
      })
      .catch(() => setChapters([]))
      .finally(() => setLoading(false))
  }, [bookId])

  const chapter = chapters[selectedIdx]
  const totalWords = chapters.reduce((sum, c) => sum + c.word_count, 0)

  useEffect(() => {
    if (!chapter || chapter.content !== undefined) return
    let cancelled = false
    setChapterLoading(true)
    fetch(`/api/books/${bookId}/chapters/${chapter.id}`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error('chapter detail failed'))))
      .then(data => {
        if (cancelled) return
        setChapters(prev => prev.map(item => (item.id === chapter.id ? { ...item, content: data.content || '' } : item)))
      })
      .catch(() => {
        if (cancelled) return
        setChapters(prev => prev.map(item => (item.id === chapter.id ? { ...item, content: '（章节正文加载失败）' } : item)))
      })
      .finally(() => {
        if (!cancelled) setChapterLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [bookId, chapter])

  const goPrev = useCallback(() => setSelectedIdx(i => Math.max(0, i - 1)), [])
  const goNext = useCallback(() => setSelectedIdx(i => Math.min(chapters.length - 1, i + 1)), [chapters.length])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-400">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-400 border-t-transparent" />
        <span className="ml-2 text-sm">加载中...</span>
      </div>
    )
  }

  if (chapters.length === 0) {
    return (
      <div className="py-16 text-center text-slate-500">
        <BookOpen className="mx-auto mb-3 h-10 w-10 opacity-30" />
        <p className="text-sm">暂无章节数据</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BookOpen className="h-5 w-5 text-blue-400" />
          <div>
            <h3 className="text-sm font-medium text-white">原始小说</h3>
            <p className="text-xs text-slate-400">{chapters.length} 章 · 约 {(totalWords / 10000).toFixed(1)} 万字</p>
          </div>
        </div>
      </div>

      {/* Chapter tabs */}
      <div className="flex flex-wrap gap-1.5">
        {chapters.map((ch, i) => (
          <button
            key={ch.id}
            onClick={() => setSelectedIdx(i)}
            className={`rounded-lg px-3 py-1.5 text-xs transition ${
              i === selectedIdx
                ? 'bg-blue-600 text-white'
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-200'
            }`}
          >
            {ch.title || `第${ch.seq}章`}
          </button>
        ))}
      </div>

      {/* Chapter content */}
      {chapter && (
        <div className="rounded-xl border border-slate-700 bg-slate-900/50">
          {/* Chapter header */}
          <div className="flex items-center justify-between border-b border-slate-700 px-5 py-3">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-slate-500" />
              <span className="text-sm font-medium text-white">
                {chapter.title || `第${chapter.seq}章`}
              </span>
              <span className="rounded bg-slate-700 px-1.5 py-0.5 text-xs text-slate-400">
                {chapter.word_count} 字
              </span>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={goPrev}
                disabled={selectedIdx === 0}
                className="rounded p-1 text-slate-400 transition hover:bg-slate-700 hover:text-white disabled:opacity-30"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <span className="min-w-[3rem] text-center text-xs text-slate-500">
                {selectedIdx + 1} / {chapters.length}
              </span>
              <button
                onClick={goNext}
                disabled={selectedIdx === chapters.length - 1}
                className="rounded p-1 text-slate-400 transition hover:bg-slate-700 hover:text-white disabled:opacity-30"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Summary */}
          {chapter.summary && (
            <div className="border-b border-slate-700/50 bg-slate-800/30 px-5 py-3">
              <div className="text-xs font-medium text-slate-400">章节摘要</div>
              <div className="mt-1 text-sm text-slate-300">{chapter.summary}</div>
            </div>
          )}

          {/* Raw text */}
          <div className="max-h-[60vh] overflow-y-auto px-5 py-4">
            <div className="whitespace-pre-wrap font-serif text-sm leading-7 text-slate-200">
              {chapterLoading && chapter.content === undefined ? '正文加载中...' : chapter.content || '（无内容）'}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
