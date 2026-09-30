import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { ProductionWorkspaceV2Snapshot } from '../domain/productionWorkspace'
import { toShotStudioViewModels } from '../domain/productionUiV3'
import { createProductionWorkspaceV2ReviewFixture, productionWorkspaceV2Fixture, productionWorkspaceV2GenerationFixtures } from '../fixtures/productionWorkspaceV2'
import ProductWorkspaceShotStudioV3, { GenerationControls } from './ProductWorkspaceShotStudioV3'

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

const official = {
  current: true,
  currentness: 'current',
  version: { id: 'official-image-1', revision: 1, media_type: 'IMAGE', storage_identity: 'https://cdn.example/official.png', checksum: 'sha', mime: 'image/png', width: 1024, height: 576, duration_ms: null, candidate_id: 'candidate-promoted', validation_id: 'validation-1' },
  authority: { id: 'authority-1', status: 'CURRENT', payload_hash: 'payload', lineage_hash: 'lineage' },
  pointer: { id: 1, authority_id: 'authority-1', fingerprint: 'pointer' },
  preview: 'https://cdn.example/official.png',
} as const

const candidate = {
  id: 'candidate-review',
  state: 'MEDIA_CANDIDATE',
  preview: 'https://cdn.example/candidate.png',
  created_at: null,
  model_profile_id: 'image-profile',
  technical_validation: { status: 'TECHNICALLY_VALID', validation_id: 'validation-review', mime: 'image/png', width: 1024, height: 576, duration_ms: null, details: {} },
  checksum: 'candidate-sha',
  storage_identity: 'https://cdn.example/candidate.png',
}

function readySnapshot(overrides: Partial<ProductionWorkspaceV2Snapshot['shots'][number]> = {}): ProductionWorkspaceV2Snapshot {
  const base = clone(productionWorkspaceV2Fixture.shots[0])
  const shot = {
    ...base,
    asset_readiness: { state: 'ready', required: {}, missing: [], stale: [], current: true },
    IMAGE: { ...base.IMAGE, prompt_ir: { current: true, version: 1, stale: false, state: 'complete', reason_codes: [] }, model: { selected_profile_id: 'image-profile', provider: 'fixture', model_name: 'Fixture Image' }, generation_readiness: { ready: true, reason_codes: [], primary_blocker: null, blockers: [] }, candidates: { count: 0, latest: null, items: [] }, official: { current: false, currentness: 'missing', version: null, authority: null, pointer: null, preview: null } },
    VIDEO: { ...base.VIDEO, generation_mode: 'TEXT_TO_VIDEO', prompt_ir: { current: true, version: 1, stale: false, state: 'complete', reason_codes: [] }, model: { selected_profile_id: 'video-profile', provider: 'fixture', model_name: 'Fixture Video' }, generation_readiness: { ready: true, reason_codes: [], primary_blocker: null, blockers: [] }, candidates: { count: 0, latest: null, items: [] }, official: { current: false, currentness: 'missing', version: null, authority: null, pointer: null, preview: null } },
    blockers: [],
    ...overrides,
  }
  return { ...clone(productionWorkspaceV2Fixture), shots: [shot] }
}

function renderSurface(snapshot: ProductionWorkspaceV2Snapshot | null, props: Partial<React.ComponentProps<typeof ProductWorkspaceShotStudioV3>> = {}) {
  return renderToStaticMarkup(<ProductWorkspaceShotStudioV3 snapshot={snapshot} state={snapshot ? 'ready' : 'loading'} onSelectShot={() => undefined} {...props} />)
}

describe('ProductWorkspaceShotStudioV3', () => {
  it('renders the V2 snapshot as a canonical Shot Studio surface', () => {
    const html = renderSurface(productionWorkspaceV2Fixture)
    expect(html).toContain('Shot Navigator')
    expect(html).toContain('Shot Studio · V3')
    expect(html).not.toContain('V3 Canary')
    expect(html).toContain('兼容工作台')
    expect(html).toContain('Media Canvas')
    expect(html).toContain('Shot Pipeline')
    expect(html).toContain('Shot Context')
    expect(html).toContain('下一步')
    expect(html).toContain('真正阻塞')
    expect(html).not.toContain('设为正式版本')
    expect(html).not.toContain('生成图片</button>')
  })

  it('follows the existing selected shot id and groups shots by scene', () => {
    const snapshot = clone(productionWorkspaceV2Fixture)
    snapshot.shots = [snapshot.shots[0], { ...snapshot.shots[1], identity: { ...snapshot.shots[1].identity, shot_id: '2', storyboard_shot_id: 2 }, scene: { id: 'E01_SC001', name: '场景一' } }]
    const html = renderSurface(snapshot, { focusShotId: '2' })
    expect(html).toContain('E01 · 场景一')
    expect(html).toMatch(/data-testid="shot-studio-shot-2"[^>]*aria-current="true"/)
  })

  it('renders candidate evidence without promoting it to official', () => {
    const snapshot = readySnapshot({ IMAGE: { ...readySnapshot().shots[0].IMAGE, candidates: { count: 1, latest: candidate, items: [candidate] } } })
    const html = renderSurface(snapshot)
    expect(html).toContain('候选 · 不是正式版本')
    expect(html).not.toContain('authority-1')
    expect(html).not.toContain('当前正式版本')
  })

  it('renders canonical official evidence and professional details only in professional mode', () => {
    const snapshot = readySnapshot({ IMAGE: { ...readySnapshot().shots[0].IMAGE, official } })
    const standard = renderSurface(snapshot, { mode: 'standard' })
    expect(standard).toContain('正式版本')
    expect(standard).not.toContain('authority-1')
    const professional = renderSurface(snapshot, { mode: 'professional' })
    expect(professional).toContain('Production Details')
    expect(professional).toContain('authority-1')
    expect(professional).toContain('pointer')
  })

  it('renders loading, empty, unavailable, and a 100-shot stress surface', () => {
    const loading = renderToStaticMarkup(<ProductWorkspaceShotStudioV3 snapshot={null} state="loading" onSelectShot={() => undefined} />)
    expect(loading).toContain('shot-studio-loading')
    const emptySnapshot = { ...clone(productionWorkspaceV2Fixture), shots: [] }
    expect(renderSurface(emptySnapshot)).toContain('当前还没有可查看的镜头')
    const unavailable = renderToStaticMarkup(<ProductWorkspaceShotStudioV3 snapshot={null} state="unavailable" error="读取失败" onRefresh={() => undefined} onSelectShot={() => undefined} />)
    expect(unavailable).toContain('生产状态暂不可用')
    const stress = clone(productionWorkspaceV2Fixture)
    stress.shots = Array.from({ length: 100 }, (_, index) => ({ ...stress.shots[index % 2], identity: { ...stress.shots[index % 2].identity, episode: Math.floor(index / 20) + 1, shot_id: String(index + 1), storyboard_shot_id: index + 1 }, scene: { id: `SCENE_${Math.floor(index / 10)}`, name: `场景 ${Math.floor(index / 10)}` } }))
    expect(renderSurface(stress)).toContain('100 shots')
  })

  it('opens an IMAGE Review Desk with a real candidate evidence placeholder and locked unsupported decisions', () => {
    const html = renderSurface(createProductionWorkspaceV2ReviewFixture({ lane: 'IMAGE' }))
    expect(html).toContain('Review Desk')
    expect(html).toContain('Candidate · 非正式版本')
    expect(html).toContain('批准并继续')
    expect(html).toContain('统一修改意见契约尚未接入')
    expect(html).toContain('候选没有可预览 URL')
    expect(html).not.toContain('已建立正式版本')
    expect(html).not.toContain('撤销')
    expect(html).not.toContain('驳回')
    expect(html).not.toContain('生成图片</button>')
  })

  it('opens a VIDEO Review Desk only for the current VIDEO candidate', () => {
    const html = renderSurface(createProductionWorkspaceV2ReviewFixture({ lane: 'VIDEO' }), { mode: 'professional' })
    expect(html).toContain('· VIDEO')
    expect(html).toContain('fixture-media-candidate-video')
    expect(html).toContain('批准并继续')
    expect(html).not.toContain('生成视频</button>')
  })

  it('uses video controls for VIDEO review evidence instead of an image element', () => {
    const snapshot = createProductionWorkspaceV2ReviewFixture({ lane: 'VIDEO' })
    const videoCandidate = snapshot.shots[0].VIDEO.candidates.items[0]
    snapshot.shots[0].VIDEO.candidates.items = [{ ...videoCandidate, preview: 'https://cdn.example/candidate.mp4', preview_url: 'https://cdn.example/candidate.mp4' }]
    snapshot.shots[0].VIDEO.candidates.latest = snapshot.shots[0].VIDEO.candidates.items[0]
    const html = renderSurface(snapshot)
    expect(html).toContain('<video controls')
    expect(html).toContain('candidate.mp4')
  })

  it('does not render a misleading cancel action while foreground observation is running', () => {
    const shot = toShotStudioViewModels(readySnapshot().shots)[0]
    const html = renderToStaticMarkup(<GenerationControls shot={shot} lane="IMAGE" mutation={{ state: 'running', shotId: shot.shotId, target: 'IMAGE', message: '生成任务仍在后台进行；重新进入时会恢复。', errorCode: null, status: null, response: null }} onGenerate={() => undefined} />)
    expect(html).toContain('生成任务仍在后台进行')
    expect(html).not.toContain('取消生成')
    expect(html).not.toMatch(/>取消<\/button>/)
  })

  it('maps the DEV long-running fixture to canonical running state', () => {
    const html = renderSurface(productionWorkspaceV2GenerationFixtures['running-image'])
    expect(html).toContain('生成中')
    expect(html).not.toContain('真正阻塞')
    expect(html).not.toMatch(/>取消<\/button>/)
  })

  it('keeps candidate identity professional-only while Standard stays focused on review evidence', () => {
    const snapshot = createProductionWorkspaceV2ReviewFixture({ lane: 'IMAGE' })
    const standard = renderSurface(snapshot, { mode: 'standard' })
    const professional = renderSurface(snapshot, { mode: 'professional' })
    expect(standard).not.toContain('fixture-media-candidate-image')
    expect(professional).toContain('fixture-media-candidate-image')
    expect(professional).toContain('Candidate ID')
  })
})
