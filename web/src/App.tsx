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

export default function App() {
  const [view, setView] = useState<View>(() => {
    const raw = localStorage.getItem(APP_VIEW_STORAGE_KEY)
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
  }, [view])

  const handleSelectBook = useCallback((book: { id: number; title: string }) => {
    setView({
      page: 'canvas',
      book: {
        ...book,
        title: resolveProjectDisplayTitle(book.title, book.id),
      },
    })
  }, [])

  const handleBack = useCallback(() => {
    setView({ page: 'projects' })
  }, [])

  const handleNewProject = useCallback(() => {
    setView({ page: 'canvas', book: { id: 0, title: '新建项目' } })
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
          onNewProject={handleNewProject}
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