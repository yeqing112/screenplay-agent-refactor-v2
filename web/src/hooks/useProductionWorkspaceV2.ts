import { useCallback, useEffect, useState } from 'react'
import { productionWorkspaceV2Fixture } from '../fixtures/productionWorkspaceV2'
import { fetchProductionWorkspaceV2 } from '../services/productionWorkspace'
import type { ProductionWorkspaceLoadState, ProductionWorkspaceV2Snapshot } from '../domain/productionWorkspace'

export function useProductionWorkspaceV2(bookId?: number) {
  const [data, setData] = useState<ProductionWorkspaceV2Snapshot | null>(null)
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
      const params = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null
      const fixtureEnabled = import.meta.env.DEV && params && (params.get('workspace_v2_fixture') === 'blocked' || params.get('workspace_fixture') === 'populated')
      if (fixtureEnabled) {
        setData({ ...productionWorkspaceV2Fixture, book_id: bookId })
        setState('ready')
        return
      }
      setData(await fetchProductionWorkspaceV2(bookId))
      setState('ready')
    } catch (reason) {
      setData(null)
      setState('unavailable')
      setError(reason instanceof Error ? reason.message : 'Production Workspace V2 读取失败')
    } finally {
      setLoading(false)
    }
  }, [bookId])

  useEffect(() => { void refresh() }, [refresh])
  return { data, loading, error, state, refresh }
}
