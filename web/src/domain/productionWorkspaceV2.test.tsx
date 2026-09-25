import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { productionWorkspaceV2Fixture } from '../fixtures/productionWorkspaceV2'
import ProductionWorkspaceV2Panel from '../components/ProductionWorkspaceV2Panel'
import {
  normalizeProductionWorkspaceV2Snapshot,
  validateProductionWorkspaceV2Snapshot,
} from './productionWorkspace'
import { fetchProductionWorkspaceV2 } from '../services/productionWorkspace'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('production workspace V2 contract', () => {
  it('does not require provider_calls to render a V2 projection', () => {
    const payload = { ...productionWorkspaceV2Fixture, provider_calls: 4 }
    expect(validateProductionWorkspaceV2Snapshot(payload)).toEqual([])
    expect(normalizeProductionWorkspaceV2Snapshot(payload, 990401).book_id).toBe(990401)
  })

  it('restores the authoritative V2 snapshot after browser recovery caches are cleared', async () => {
    const clear = vi.fn()
    vi.stubGlobal('localStorage', { clear })
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ...productionWorkspaceV2Fixture, provider_calls: 9 }),
    })
    vi.stubGlobal('fetch', fetchMock)

    globalThis.localStorage.clear()
    const snapshot = await fetchProductionWorkspaceV2(990401)

    expect(clear).toHaveBeenCalledOnce()
    expect(fetchMock).toHaveBeenCalledWith('/api/books/990401/production-workspace-v2')
    expect(snapshot.book_id).toBe(990401)
    expect(snapshot.legacy_adopted_is_display_only).toBe(true)
    expect(snapshot.shots[0].asset_readiness.state).toBe('blocked')
  })

  it('keeps the standard view focused on state and hides raw lineage ids', () => {
    const html = renderToStaticMarkup(<ProductionWorkspaceV2Panel snapshot={productionWorkspaceV2Fixture} state="ready" mode="standard" />)
    expect(html).toContain('缺少真实视觉资产')
    expect(html).toContain('候选结果')
    expect(html).not.toContain('storyboard_shot_id=')
    expect(html).not.toContain('PromptIR:')
  })

  it('exposes lineage only in professional view and labels legacy adopted data as display-only', () => {
    const html = renderToStaticMarkup(<ProductionWorkspaceV2Panel snapshot={productionWorkspaceV2Fixture} state="ready" mode="professional" />)
    expect(html).toContain('storyboard_shot_id=')
    expect(html).toContain('PromptIR:')
    expect(html).toContain('候选结果')
    expect(html).toContain('不等于当前正式版本')
  })

  it('blocks image and video generation without explicit model profiles', () => {
    const html = renderToStaticMarkup(<ProductionWorkspaceV2Panel snapshot={productionWorkspaceV2Fixture} state="ready" mode="standard" />)
    expect(html).toContain('请选择已配置的生成模型')
    expect(html).toContain('disabled=""')
    expect(html).toContain('生成图片')
    expect(html).toContain('生成视频')
  })

  it('distinguishes a candidate from the current official media and shows the official image as video source', () => {
    const shot = productionWorkspaceV2Fixture.shots[0]
    const official = {
      current: true,
      currentness: 'current',
      version: { id: 'omv-image-1', revision: 1, media_type: 'IMAGE', storage_identity: 'storage://official-image', checksum: 'sha', mime: 'image/png', width: 1024, height: 576, duration_ms: null, candidate_id: 'candidate-image-1', validation_id: 'validation-1' },
      authority: { id: 'oma-1', status: 'CURRENT', payload_hash: 'payload', lineage_hash: 'lineage' },
      pointer: { id: 1, authority_id: 'oma-1', fingerprint: 'pointer-fp' },
      preview: 'storage://official-image',
    } as const
    const candidate = {
      id: 'candidate-image-2', state: 'MEDIA_CANDIDATE', preview: 'storage://candidate-image', created_at: '2026-09-25T00:00:00Z', model_profile_id: 'image-profile',
      technical_validation: { status: 'PASS', validation_id: 'validation-2', mime: 'image/png', width: 1024, height: 576, duration_ms: null, details: {} }, checksum: 'candidate-sha', storage_identity: 'storage://candidate-image',
    }
    const snapshot = {
      ...productionWorkspaceV2Fixture,
      shots: [{
        ...shot,
        IMAGE: { ...shot.IMAGE, model: { selected_profile_id: 'image-profile', provider: 'fixture', model_name: 'Fixture Image' }, candidates: { count: 1, latest: candidate, items: [candidate] }, official },
        VIDEO: { ...shot.VIDEO, generation_mode: 'IMAGE_TO_VIDEO', source_official_image: official },
      }],
    }
    const html = renderToStaticMarkup(<ProductionWorkspaceV2Panel snapshot={snapshot} state="ready" mode="standard" />)
    expect(html).toContain('候选待审核')
    expect(html).toContain('当前正式版本')
    expect(html).toContain('视频来源：当前正式图片')
    expect(html).toContain('这只是候选结果，不是当前正式版本。')
  })

  it('exposes only the canonical validation or promotion action for a candidate', () => {
    const shot = productionWorkspaceV2Fixture.shots[0]
    const candidate = {
      id: 'candidate-image-review', state: 'MEDIA_CANDIDATE', preview: null, created_at: null, model_profile_id: 'image-profile',
      technical_validation: { status: 'PASS', validation_id: 'validation-review', mime: 'image/png', width: 1024, height: 576, duration_ms: null, details: {} }, checksum: 'sha', storage_identity: null,
    }
    const html = renderToStaticMarkup(
      <ProductionWorkspaceV2Panel
        snapshot={{ ...productionWorkspaceV2Fixture, shots: [{ ...shot, IMAGE: { ...shot.IMAGE, candidates: { count: 1, latest: candidate, items: [candidate] } } }] }}
        state="ready"
        mode="standard"
        onRefresh={() => undefined}
      />,
    )
    expect(html).toContain('设为正式版本')
    expect(html).not.toContain('accepted=true')
    expect(html).not.toContain('favorite=true')
  })

  it('labels stale prompt state as needing an update', () => {
    const snapshot = {
      ...productionWorkspaceV2Fixture,
      shots: [{ ...productionWorkspaceV2Fixture.shots[0], IMAGE: { ...productionWorkspaceV2Fixture.shots[0].IMAGE, prompt_ir: { current: false, version: 2, stale: true, state: 'stale', payload_hash: 'old' } } }],
    }
    const html = renderToStaticMarkup(<ProductionWorkspaceV2Panel snapshot={snapshot} state="ready" mode="standard" />)
    expect(html).toContain('需要更新')
  })
})
