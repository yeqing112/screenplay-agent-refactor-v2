import { useCallback, useEffect, useRef, useState } from 'react'
import { createProductionWorkspaceV2GenerationFixture, createProductionWorkspaceV2OfficialCandidateCoexistenceFixture, createProductionWorkspaceV2ReviewFixture, productionWorkspaceV2Fixture, type ProductionWorkspaceV2GenerationFixtureKind } from '../fixtures/productionWorkspaceV2'
import { fetchProductionWorkspaceV2, reconcileCanonicalGeneration } from '../services/productionWorkspace'
import type { ProductionWorkspaceLoadState, ProductionWorkspaceV2Snapshot } from '../domain/productionWorkspace'
import { readExplicitGenerationProfileSelection } from '../components/productWorkspaceGeneration'

export function useProductionWorkspaceV2(bookId?: number) {
  const [data, setData] = useState<ProductionWorkspaceV2Snapshot | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [state, setState] = useState<ProductionWorkspaceLoadState>('loading')
  const [reviewFixtureRefreshCount, setReviewFixtureRefreshCount] = useState(0)
  const reconcileTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

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
      const generationFixture = params?.get('workspace_v2_generation_fixture') as ProductionWorkspaceV2GenerationFixtureKind | null
      const reviewFixtureEnabled = import.meta.env.DEV && fixtureName === 'review'
      const coexistenceFixtureEnabled = import.meta.env.DEV && fixtureName === 'official-candidate'
      const fixtureEnabled = import.meta.env.DEV && params && (fixtureName === 'blocked' || params.get('workspace_fixture') === 'populated')
      const generationFixtureEnabled = import.meta.env.DEV && Boolean(generationFixture) && ['ready-image', 'failed-image', 'failed-video', 'official-image', 'running-image', 'review-image', 'official-image-ready-video', 'running-video', 'review-video', 'official-shot'].includes(generationFixture || '')
      if (generationFixtureEnabled && generationFixture) {
        const fixture = createProductionWorkspaceV2GenerationFixture(generationFixture)
        const requestedShotId = params?.get('shot')
        const selection = readExplicitGenerationProfileSelection()
        const fixtureShots = fixture.shots.map((shot, index) => {
          if (index !== 0) return shot
          return {
            ...shot,
            ...(requestedShotId ? { identity: { ...shot.identity, shot_id: requestedShotId } } : {}),
            IMAGE: selection.imageModelProfileId
              ? { ...shot.IMAGE, model: { ...shot.IMAGE.model, selected_profile_id: selection.imageModelProfileId } }
              : shot.IMAGE,
            VIDEO: selection.videoModelProfileId
              ? { ...shot.VIDEO, model: { ...shot.VIDEO.model, selected_profile_id: selection.videoModelProfileId } }
              : shot.VIDEO,
          }
        })
        setData({
          ...fixture,
          book_id: bookId,
          // Disposable generation fixtures must follow the storyboard shot
          // selected in the URL; real API projections remain untouched.
          shots: fixtureShots,
        })
        setState('ready')
        return
      }
      if (reviewFixtureEnabled) {
        const lane = params?.get('review_lane') === 'VIDEO' ? 'VIDEO' : 'IMAGE'
        const promoted = params?.get('review_mutation_fixture') === 'success' && reviewFixtureRefreshCount > 0
        setData({ ...createProductionWorkspaceV2ReviewFixture({ lane, promoted }), book_id: bookId })
        setState('ready')
        return
      }
      if (coexistenceFixtureEnabled) {
        setData({ ...createProductionWorkspaceV2OfficialCandidateCoexistenceFixture(), book_id: bookId })
        setState('ready')
        return
      }
      if (fixtureEnabled) {
        setData({ ...productionWorkspaceV2Fixture, book_id: bookId })
        setState('ready')
        return
      }
      const selection = readExplicitGenerationProfileSelection()
      const snapshot = await fetchProductionWorkspaceV2(bookId, selection)
      // Async canonical VIDEO executions are durable. Reconcile them from
      // the read model on load so a browser reload resumes the same task.
      const running = snapshot.shots.flatMap((shot) => {
        const execution = shot.VIDEO?.latest_execution
        const state = String(execution?.state || '').toUpperCase()
        if (!execution?.id || !execution?.provider_task_id || !execution?.confirmation_token || !['RUNNING', 'PROVIDER_PENDING', 'PROVIDER_CALLED'].includes(state)) return []
        return [{ episode: Number(shot.identity.episode), shotId: shot.identity.shot_id, executionId: String(execution.id), confirmationToken: String(execution.confirmation_token) }]
      })
      setData(snapshot)
      setState('ready')
      // Publish RUNNING before the first provider status GET completes. The
      // bounded timer keeps polling through this same backend reconcile path,
      // including after a full browser reload.
      if (running.length > 0 && !reconcileTimer.current) {
        reconcileTimer.current = setTimeout(() => {
          reconcileTimer.current = null
          void (async () => {
            let changed = false
            for (const item of running) {
              try { await reconcileCanonicalGeneration({ bookId, ...item }); changed = true } catch { /* retry on next refresh */ }
            }
            if (changed) await refresh()
          })()
        }, 250)
      }
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
