import { describe, expect, it, vi } from 'vitest'
import { productionWorkspaceV2Fixture } from '../fixtures/productionWorkspaceV2'
import {
  executeBatchTaskAction,
  isProductionBatchImageEligible,
  isProductionBatchVideoEligible,
} from './productWorkspaceBatchActions'

describe('V2 batch eligibility', () => {
  it('blocks IMAGE and VIDEO batch work while the authoritative asset gate is blocked', () => {
    expect(isProductionBatchImageEligible(productionWorkspaceV2Fixture, 1, '1')).toBe(false)
    expect(isProductionBatchVideoEligible(productionWorkspaceV2Fixture, 1, '1')).toBe(false)
  })

  it('requires the current Official IMAGE source before IMAGE_TO_VIDEO batch work', () => {
    const shot = productionWorkspaceV2Fixture.shots[0]
    const ready = {
      ...productionWorkspaceV2Fixture,
      shots: [{
        ...shot,
        asset_readiness: { ...shot.asset_readiness, state: 'ready', current: true, missing: [], stale: [] },
        IMAGE: { ...shot.IMAGE, prompt_ir: { ...shot.IMAGE.prompt_ir, current: true, state: 'complete' }, official: { ...shot.IMAGE.official, current: true }, candidates: { count: 0, latest: null, items: [] } },
        VIDEO: { ...shot.VIDEO, prompt_ir: { ...shot.VIDEO.prompt_ir, current: true, state: 'complete' }, generation_mode: 'IMAGE_TO_VIDEO' as const, source_official_image: { ...shot.IMAGE.official, current: true }, candidates: { count: 0, latest: null, items: [] } },
      }],
    }
    expect(isProductionBatchImageEligible(ready, 1, '1')).toBe(false)
    expect(isProductionBatchVideoEligible(ready, 1, '1')).toBe(true)
  })

  it('fails closed without a V2 snapshot before issuing IMAGE generation requests', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    await expect(executeBatchTaskAction({
      action: 'batch-generate-frames',
      bookId: 990401,
      shotsByEpisode: { 1: [{ episode: 1, shot_id: '1' } as any] },
      pendingTasks: [],
      qaWorkbenchEpisodes: [],
      fetchTaskStatus: async () => ({ status: 'done' } as any),
      waitForCreativeTask: async () => ({ status: 'done' } as any),
      imageModelProfileId: 'image-profile',
      productionWorkspaceV2: null,
      productionWorkspaceV2State: 'unavailable',
    })).rejects.toThrow('生产状态暂时不可用')
    expect(fetchSpy).not.toHaveBeenCalled()
    fetchSpy.mockRestore()
  })

  it('fails closed without a V2 snapshot before issuing VIDEO generation requests', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    await expect(executeBatchTaskAction({
      action: 'batch-generate-videos',
      bookId: 990401,
      shotsByEpisode: { 1: [{ episode: 1, shot_id: '1' } as any] },
      pendingTasks: [],
      qaWorkbenchEpisodes: [],
      fetchTaskStatus: async () => ({ status: 'done' } as any),
      waitForCreativeTask: async () => ({ status: 'done' } as any),
      videoModelProfileId: 'video-profile',
      productionWorkspaceV2: null,
      productionWorkspaceV2State: 'unavailable',
    })).rejects.toThrow('生产状态暂时不可用')
    expect(fetchSpy).not.toHaveBeenCalled()
    fetchSpy.mockRestore()
  })

  it('fails closed during a V2 refresh even when an old snapshot is still present', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    await expect(executeBatchTaskAction({
      action: 'batch-generate-frames',
      bookId: 990401,
      shotsByEpisode: { 1: [{ episode: 1, shot_id: '1' } as any] },
      pendingTasks: [],
      qaWorkbenchEpisodes: [],
      fetchTaskStatus: async () => ({ status: 'done' } as any),
      waitForCreativeTask: async () => ({ status: 'done' } as any),
      imageModelProfileId: 'image-profile',
      productionWorkspaceV2: productionWorkspaceV2Fixture,
      productionWorkspaceV2State: 'loading',
    })).rejects.toThrow('生产状态暂时不可用')
    expect(fetchSpy).not.toHaveBeenCalled()
    fetchSpy.mockRestore()
  })
})
