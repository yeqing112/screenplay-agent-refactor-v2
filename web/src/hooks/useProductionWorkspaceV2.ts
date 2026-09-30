import { useCallback, useEffect, useState } from 'react'
import { createProductionWorkspaceV2ReviewFixture, productionWorkspaceV2Fixture } from '../fixtures/productionWorkspaceV2'
import { fetchProductionWorkspaceV2 } from '../services/productionWorkspace'
import type { ProductionWorkspaceLoadState, ProductionWorkspaceV2Snapshot } from '../domain/productionWorkspace'
import { readExplicitGenerationProfileSelection } from '../components/productWorkspaceGeneration'

export function useProductionWorkspaceV2(bookId?: number) {
  const [data, setData] = useState<ProductionWorkspaceV2Snapshot | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [state, setState] = useState<ProductionWorkspaceLoadState>('loading')
  const [reviewFixtureRefreshCount, setReviewFixtureRefreshCount] = useState(0)

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
      const fixtureName = params?.get('workspace_v2_fixture')
      const reviewFixtureEnabled = import.meta.env.DEV && fixtureName === 'review'
      const fixtureEnabled = import.meta.env.DEV && params && (fixtureName === 'blocked' || params.get('workspace_fixture') === 'populated')
      if (reviewFixtureEnabled) {
        const lane = params?.get('review_lane') === 'VIDEO' ? 'VIDEO' : 'IMAGE'
        const promoted = params?.get('review_mutation_fixture') === 'success' && reviewFixtureRefreshCount > 0
        setData({ ...createProductionWorkspaceV2ReviewFixture({ lane, promoted }), book_id: bookId })
        setState('ready')
        return
      }
      if (fixtureEnabled) {
        setData({ ...productionWorkspaceV2Fixture, book_id: bookId })
        setState('ready')
        return
      }
      const selection = readExplicitGenerationProfileSelection()
      setData(await fetchProductionWorkspaceV2(bookId, selection))
      setState('ready')
    } catch (reason) {
      setData(null)
      setState('unavailable')
      setError(reason instanceof Error ? reason.message : 'Production Workspace V2 读取失败')
    } finally {
      setLoading(false)
    }
  }, [bookId, reviewFixtureRefreshCount])

  useEffect(() => { void refresh() }, [refresh])
  const refreshWithFixtureMutation = useCallback(async () => {
    if (import.meta.env.DEV && typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('workspace_v2_fixture') === 'review') {
      setReviewFixtureRefreshCount((current) => current + 1)
      return
    }
    await refresh()
  }, [refresh])

  return { data, loading, error, state, refresh: refreshWithFixtureMutation }
}
