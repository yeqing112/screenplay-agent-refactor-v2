import { useCallback, useEffect, useState } from 'react'
import ProjectsPage from './pages/ProjectsPage'
import CanvasPage from './pages/CanvasPage'
import { resolveProjectDisplayTitle } from './pages/projectDisplayText'

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

  if (view.page === 'projects') {
    return (
      <ProjectsPage
        onSelectBook={handleSelectBook}
        onNewProject={handleNewProject}
      />
    )
  }

  return <CanvasPage book={view.book} onBack={handleBack} onSelectBook={handleSelectBook} />
}
