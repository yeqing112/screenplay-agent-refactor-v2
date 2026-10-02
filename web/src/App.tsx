import { useCallback, useEffect, useMemo, useState } from 'react'
import ProjectsPage from './pages/ProjectsPage'
import CanvasPage from './pages/CanvasPage'
import { resolveProjectDisplayTitle } from './pages/projectDisplayText'
import SmartDirectorDrawer from './components/SmartDirectorDrawer'
import type { DirectorContext } from './services/agent'

type View =
  | { page: 'projects' }
  | { page: 'canvas'; book: { id: number; title: string } }

const APP_VIEW_STORAGE_KEY = 'screenplay-app-view-v1'

function readBookIdFromUrl(): number | null {
  if (typeof window === 'undefined') return null
  const raw = new URLSearchParams(window.location.search).get('book_id')
  const id = Number(raw)
  return Number.isInteger(id) && id > 0 ? id : null
}

function updateBookUrl(bookId: number | null) {
  if (typeof window === 'undefined') return
  const next = new URL(window.location.href)
  if (bookId) next.searchParams.set('book_id', String(bookId))
  else next.searchParams.delete('book_id')
  window.history.replaceState({}, '', `${next.pathname}${next.search}${next.hash}`)
}

export default function App() {
  const [view, setView] = useState<View>(() => {
    const urlBookId = readBookIdFromUrl()
    const raw = localStorage.getItem(APP_VIEW_STORAGE_KEY)
    if (urlBookId) {
      return { page: 'canvas', book: { id: urlBookId, title: `项目 ${urlBookId}` } }
    }
    if (!raw) {
      return { page: 'projects' }
    }

    try {
      const parsed = JSON.parse(raw) as View
      if (parsed?.page === 'canvas' && parsed.book) {
        return {
          ...parsed,
          book: {
            ...parsed.book,
            title: resolveProjectDisplayTitle(parsed.book.title, parsed.book.id),
          },
        }
      }
    } catch {
      // Ignore invalid persisted view.
    }

    return { page: 'projects' }
  })

  useEffect(() => {
    localStorage.setItem(APP_VIEW_STORAGE_KEY, JSON.stringify(view))
    updateBookUrl(view.page === 'canvas' ? view.book.id : null)
  }, [view])

  useEffect(() => {
    if (view.page !== 'canvas' || !readBookIdFromUrl()) return
    const controller = new AbortController()
    fetch('/api/books', { signal: controller.signal })
      .then((response) => response.json())
      .then((books) => {
        const found = Array.isArray(books) ? books.find((item: any) => Number(item.id) === view.book.id) : null
        if (found) {
          setView((current) => current.page === 'canvas' && current.book.id === view.book.id
            ? { page: 'canvas', book: { ...current.book, ...found, title: resolveProjectDisplayTitle(found.title, view.book.id) } }
            : current)
        } else {
          setView({ page: 'projects' })
        }
      })
      .catch((error) => {
        if ((error as Error).name !== 'AbortError') return
      })
    return () => controller.abort()
  }, [])

  const handleSelectBook = useCallback((book: { id: number; title: string }) => {
    updateBookUrl(book.id)
    setView({
      page: 'canvas',
      book: {
        ...book,
        title: resolveProjectDisplayTitle(book.title, book.id),
      },
    })
  }, [])

  const handleBack = useCallback(() => {
    updateBookUrl(null)
    setView({ page: 'projects' })
  }, [])

  const directorContext = useMemo<DirectorContext | null>(() => {
    if (view.page !== 'canvas') return null
    return {
      book_id: view.book.id || null,
      book_title: view.book.title,
      section: '创作画布',
    }
  }, [view])

  return (
    <>
      {view.page === 'projects' ? (
        <ProjectsPage
          onSelectBook={handleSelectBook}
        />
      ) : (
        <CanvasPage
          book={view.book}
          onBack={handleBack}
          onSelectBook={handleSelectBook}
        />
      )}
      <SmartDirectorDrawer context={directorContext} />
    </>
  )
}
