import { afterEach, describe, expect, it, vi } from 'vitest'
import { bindCurrentProductionAssets, fetchProductionAssetBridgeState } from './productionAssets'

describe('production asset bridge service', () => {
  afterEach(() => vi.restoreAllMocks())

  it('reads the server backed bridge state with no durable client identity', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ requirements: [], binding_current: false, can_bind: false }), { status: 200 }))
    await fetchProductionAssetBridgeState(12, 34)
    expect(fetchMock).toHaveBeenCalledWith('/api/books/12/production-assets/shots/34/bridge-state', { cache: 'no-store' })
  })

  it('uses the backend resolved bind-current contract', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ current: true }), { status: 200 }))
    await bindCurrentProductionAssets(12, 34)
    expect(fetchMock).toHaveBeenCalledWith('/api/books/12/production-assets/shots/34/bind-current', { method: 'POST' })
  })
})
