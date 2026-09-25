import { describe, expect, it } from 'vitest'
import { productionWorkspaceV2Fixture } from '../fixtures/productionWorkspaceV2'
import {
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
})
