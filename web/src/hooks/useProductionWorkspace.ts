import { useCallback, useEffect, useState } from 'react'
import { fetchProductionWorkspace } from '../services/productionWorkspace'
import type { ProductionWorkspaceSnapshot } from '../domain/productionWorkspace'

export function useProductionWorkspace(bookId?: number) {
  const [data, setData] = useState<ProductionWorkspaceSnapshot | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const refresh = useCallback(async () => {
    if (!bookId || bookId <= 0) {
      setData(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      setData(await fetchProductionWorkspace(bookId))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '生产状态读取失败')
    } finally {
      setLoading(false)
    }
  }, [bookId])

  useEffect(() => { void refresh() }, [refresh])
  return { data, loading, error, refresh }
}
