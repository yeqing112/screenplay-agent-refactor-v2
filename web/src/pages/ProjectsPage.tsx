import { useCallback, useEffect, useState } from 'react'
import ModelRegistryModal from '../components/ModelRegistryModal'
import { fetchModelRegistry, type ModelRegistryPayload } from '../services/modelRegistry'
import { resolveProjectDisplayTitle } from './projectDisplayText'

interface Book {
  id: number
  title: string
  chapters: number
  words: number
  status: string
  scripts: number
  storyboard_shots: number
  created_at: string
}

type ProjectCardBook = Book & {
  displayTitle: string
  duplicateTitleCount: number
}

const STATUS_LABELS: Record<string, string> = {
  imported: '\u5df2\u5bfc\u5165',
  ingested: '\u5df2\u5207\u7ae0',
  read: '\u5df2\u5206\u6790',
  bibled: '\u5c0f\u8bf4\u5723\u7ecf\u5b8c\u6210',
  bibeled: '\u5c0f\u8bf4\u5723\u7ecf\u5b8c\u6210',
  resolved: '\u522b\u540d\u5f52\u5e76\u5b8c\u6210',
  portraited: '\u4eba\u7269\u8bbe\u5b9a\u5b8c\u6210',
  adapted: '\u6539\u7f16\u65b9\u6848\u5b8c\u6210',
  outlined: '\u5927\u7eb2\u5b8c\u6210',
  scripted: '\u5267\u672c\u5b8c\u6210',
  storyboarded: '\u5206\u955c\u5b8c\u6210',
}

const STATUS_ORDER = [
  'imported',
  'ingested',
  'read',
  'bibled',
  'bibeled',
  'resolved',
  'portraited',
  'adapted',
  'outlined',
  'scripted',
  'storyboarded',
]

function statusProgress(status: string): number {
  const idx = STATUS_ORDER.indexOf(status)
  return idx === -1 ? 0 : Math.round((idx / (STATUS_ORDER.length - 1)) * 100)
}

function statusColor(status: string): string {
  const idx = STATUS_ORDER.indexOf(status)
  if (idx === -1) return 'bg-slate-700'
  if (idx < 3) return 'bg-slate-600'
  if (idx < 6) return 'bg-blue-600'
  if (idx < 9) return 'bg-emerald-600'
  return 'bg-violet-600'
}

export function resolveProjectStatusLabel(status: string): string {
  const normalized = String(status || '').trim()
  if (STATUS_LABELS[normalized]) {
    return STATUS_LABELS[normalized]
  }
  if (!normalized) {
    return '\u672a\u6807\u8bb0\u72b6\u6001'
  }
  return normalized.replace(/[_-]+/g, ' ')
}

function formatDate(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function normalizeBookTitle(book: Book): Book {
  return {
    ...book,
    title: resolveProjectDisplayTitle(book.title, book.id),
  }
}

export function buildProjectCardBooks(items: Book[]): ProjectCardBook[] {
  const normalizedBooks = items.map(normalizeBookTitle)
  const duplicateCounts = normalizedBooks.reduce<Record<string, number>>((acc, book) => {
    acc[book.title] = (acc[book.title] ?? 0) + 1
    return acc
  }, {})

  return normalizedBooks.map((book) => ({
    ...book,
    displayTitle: duplicateCounts[book.title] > 1 ? `${book.title} · #${book.id}` : book.title,
    duplicateTitleCount: duplicateCounts[book.title] ?? 1,
  }))
}

interface Props {
  onSelectBook: (book: Book) => void
  onNewProject: () => void
}

const API_PROXY_TARGET = import.meta.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:18765'

export default function ProjectsPage({ onSelectBook, onNewProject }: Props) {
  const [books, setBooks] = useState<ProjectCardBook[]>([])
  const [loading, setLoading] = useState(true)
  const [modelRegistryOpen, setModelRegistryOpen] = useState(false)
  const [modelRegistryData, setModelRegistryData] = useState<ModelRegistryPayload | null>(null)
  const [modelRegistryError, setModelRegistryError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    fetch('/api/books', { signal: controller.signal })
      .then((r) => r.json())
      .then((data) => {
        setBooks(buildProjectCardBooks(data as Book[]))
      })
      .catch((error) => {
        if ((error as Error).name !== 'AbortError') {
          setBooks([])
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      })

    return () => controller.abort()
  }, [])

  const deleteBook = useCallback(async (book: Book, event: React.MouseEvent) => {
    event.stopPropagation()
    if (!confirm(`\u786e\u5b9a\u5220\u9664\u9879\u76ee\u300a${book.title}\u300b\u5417\uff1f\u6240\u6709\u6570\u636e\u5c06\u6c38\u4e45\u4e22\u5931\u3002`)) {
      return
    }
    try {
      const res = await fetch(`/api/books/${book.id}`, { method: 'DELETE' })
      if (!res.ok) throw new Error('Delete failed')
      setBooks((prev) => prev.filter((item) => item.id !== book.id))
    } catch (error) {
      alert(`\u5220\u9664\u5931\u8d25\uff1a${String(error)}`)
    }
  }, [])

  const openModelRegistry = useCallback(() => {
    setModelRegistryOpen(true)
    setModelRegistryError(null)
    fetchModelRegistry()
      .then((payload) => setModelRegistryData(payload))
      .catch((error) => setModelRegistryError(error instanceof Error ? error.message : '\u52a0\u8f7d\u6a21\u578b\u914d\u7f6e\u5931\u8d25'))
  }, [])

  return (
    <div className="flex h-full flex-col bg-slate-950 text-slate-300">
      <header className="flex h-14 flex-shrink-0 items-center gap-4 border-b border-slate-800 bg-slate-900 px-6">
        <div className="flex items-center gap-2">
          <span className="text-lg">{'\u7247'}</span>
          <span className="text-base font-bold">Screenplay Studio</span>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <div className="hidden rounded-full border border-slate-700 px-3 py-1 text-[11px] text-slate-400 md:block">
            API Proxy: {API_PROXY_TARGET}
          </div>
          <button
            onClick={openModelRegistry}
            className="rounded-full border border-violet-600/60 px-3 py-1.5 text-xs text-violet-200 transition hover:border-violet-400 hover:text-white"
          >
            {'\u6a21\u578b\u7ba1\u7406'}
          </button>
          <span className="text-xs text-slate-600">{'\u5168\u90e8\u9879\u76ee'}</span>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div
          onClick={onNewProject}
          className="group inline-flex h-72 w-64 cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-slate-700 transition-all hover:border-blue-500 hover:bg-slate-900/50"
        >
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-800 transition-colors group-hover:bg-blue-900/50">
            <svg className="h-6 w-6 text-slate-500 group-hover:text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
          </div>
          <span className="text-sm text-slate-500 transition-colors group-hover:text-blue-400">{'\u65b0\u5efa\u9879\u76ee'}</span>
        </div>

        <div className="inline-block align-top" />

        <div className="ml-5 inline-flex flex-wrap gap-5">
          {books.map((book) => {
            const progress = statusProgress(book.status)
            const label = resolveProjectStatusLabel(book.status)

            return (
              <div
                key={book.id}
                onClick={() => onSelectBook(book)}
                data-book-id={book.id}
                aria-label={`打开项目 ${book.displayTitle}`}
                className="group relative flex h-72 w-64 cursor-pointer flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-900 transition-all hover:border-slate-700 hover:bg-slate-900/80"
              >
                <button
                  onClick={(event) => deleteBook(book, event)}
                  className="absolute left-2 top-2 z-10 flex h-5 w-5 items-center justify-center rounded-full bg-red-900/60 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100 hover:bg-red-600"
                  title={'\u5220\u9664\u9879\u76ee'}
                >
                  {'\u00d7'}
                </button>

                <div className="relative flex flex-1 items-center justify-center bg-gradient-to-br from-slate-800 to-slate-900">
                  <div className="text-5xl opacity-30 transition-opacity group-hover:opacity-50">{'\u5267'}</div>
                  <div className="absolute right-3 top-3">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] text-white ${statusColor(book.status)}`}>
                      {label}
                    </span>
                  </div>
                  <div className="absolute bottom-0 left-0 right-0 h-1 bg-slate-800">
                    <div
                      className={`h-full transition-all duration-500 ${statusColor(book.status)}`}
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>

                <div className="px-4 py-3">
                  <h3 className="truncate text-sm font-bold text-slate-300 transition-colors group-hover:text-white">
                    {book.displayTitle}
                  </h3>
                  <div className="mt-1 flex items-center gap-3 text-[11px] text-slate-600">
                    <span>{book.chapters} {'\u7ae0'}</span>
                    <span>{(book.words / 10000).toFixed(1)} {'\u4e07\u5b57'}</span>
                    {book.scripts > 0 ? <span>{book.scripts} {'\u573a'}</span> : null}
                    {book.storyboard_shots > 0 ? <span>{book.storyboard_shots} {'\u955c'}</span> : null}
                  </div>
                  <div className="mt-1 flex items-center gap-2 text-[10px] text-slate-700">
                    <span>ID {book.id}</span>
                    <span>{formatDate(book.created_at)}</span>
                    {book.duplicateTitleCount > 1 ? <span>同名 {book.duplicateTitleCount}</span> : null}
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {!loading && books.length === 0 ? (
          <div className="mt-12 text-center text-sm text-slate-700">
            {'\u8fd8\u6ca1\u6709\u9879\u76ee\uff0c\u70b9\u51fb\u201c\u65b0\u5efa\u9879\u76ee\u201d\u5f00\u59cb\u3002'}
          </div>
        ) : null}

        {loading ? <div className="mt-12 text-center text-sm text-slate-700">{'\u52a0\u8f7d\u4e2d...'}</div> : null}
      </div>

      {modelRegistryOpen ? (
        <ModelRegistryModal
          data={modelRegistryData}
          error={modelRegistryError}
          onClose={() => setModelRegistryOpen(false)}
          onSaved={(payload) => setModelRegistryData(payload)}
        />
      ) : null}
    </div>
  )
}
