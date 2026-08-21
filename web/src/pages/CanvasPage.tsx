import { Suspense, lazy, useCallback, useEffect, useState } from 'react'

const ProductWorkspace = lazy(() => import('../components/ProductWorkspace'))

interface Props {
  book: { id: number; title: string }
  onBack: () => void
  onSelectBook: (book: { id: number; title: string }) => void
}

function WorkspaceLoadingFallback() {
  return (
    <div className="flex h-full items-center justify-center bg-slate-950 text-sm text-slate-500">
      正在加载正式工作台...
    </div>
  )
}

export default function CanvasPage({ book, onBack, onSelectBook }: Props) {
  const [bookData, setBookData] = useState<any>(null)

  const refreshBookData = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await fetch('/api/books', { signal })
      const list = await response.json()
      const found = list.find((item: any) => item.id === book.id)
      setBookData(found ?? null)
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        setBookData(null)
      }
    }
  }, [book.id])

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
      // Fall through to a readable fallback title.
    }

    onSelectBook({ id: bookId, title: `项目 ${bookId}` })
  }, [onSelectBook])

  useEffect(() => {
    setBookData(null)
    const controller = new AbortController()
    void refreshBookData(controller.signal)
    return () => controller.abort()
  }, [refreshBookData])

  return (
    <div className="flex h-full flex-col bg-slate-950">
      <div className="flex h-10 flex-shrink-0 items-center gap-4 border-b border-slate-800 bg-slate-900 px-4">
        <button onClick={onBack} className="flex items-center gap-1 text-xs text-slate-500 transition-colors hover:text-slate-300">
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          项目列表
        </button>
        <span className="text-sm font-bold text-slate-300">{book.title}</span>
        <span className="ml-auto rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] text-emerald-200">
          正式工作台
        </span>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <Suspense fallback={<WorkspaceLoadingFallback />}>
          <ProductWorkspace
            book={book}
            bookData={bookData}
            onRefresh={() => {
              void refreshBookData()
            }}
            onBookChange={handleBookChange}
          />
        </Suspense>
      </div>
    </div>
  )
}
