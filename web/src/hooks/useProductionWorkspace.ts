import { useCallback, useEffect, useState } from 'react'
import { fetchProductionWorkspace } from '../services/productionWorkspace'
import type { ProductionWorkspaceLoadState, ProductionWorkspaceSnapshot } from '../domain/productionWorkspace'
import { populatedProductionWorkspaceFixture } from '../fixtures/productionWorkspacePopulated'

export function useProductionWorkspace(bookId?: number) {
  const [data, setData] = useState<ProductionWorkspaceSnapshot | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [state, setState] = useState<ProductionWorkspaceLoadState>('loading')
  const refresh = useCallback(async () => {
    if (!bookId || bookId <= 0) {
      setData(null)
      setState('unavailable')
      return
    }
    setLoading(true)
    setState('loading')
    setError(null)
    try {
      const fixtureEnabled = import.meta.env.DEV && typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('workspace_fixture') === 'populated'
      if (fixtureEnabled) {
        setData({ ...populatedProductionWorkspaceFixture, book_id: bookId })
        setState('ready')
        return
      }
      const snapshot = await fetchProductionWorkspace(bookId)
      setData(snapshot)
      setState('ready')
    } catch (reason) {
      setData(null)
      setState('unavailable')
      setError(reason instanceof Error ? reason.message : '生产状态读取失败')
    } finally {
      setLoading(false)
    }
  }, [bookId])

  useEffect(() => { void refresh() }, [refresh])
  return { data, loading, error, state, refresh }
}
