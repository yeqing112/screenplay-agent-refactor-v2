import type { ProductionMediaLane, ProductionWorkspaceV2Snapshot } from '../domain/productionWorkspace'

const emptyLane: ProductionMediaLane = {
  prompt_ir: { current: false, version: null, stale: false, state: 'not_started' },
  generation_mode: null,
  source_official_image: null,
  model: { selected_profile_id: null, provider: null, model_name: null },
  latest_execution: null,
  candidates: { count: 0, latest: null, items: [] },
  official: { current: false, currentness: 'missing', version: null, authority: null, pointer: null, preview: null },
}

const requiredEntities = [
  ['LIN_WAN', 'CHARACTER'], ['GU_CHEN', 'CHARACTER'], ['LU_SHU', 'CHARACTER'], ['TICKET_CLERK', 'CHARACTER'],
  ['E01_SC001', 'SCENE'], ['E01_SC002', 'SCENE'],
  ['APPLE', 'PROP'], ['BROKEN_UMBRELLA_RIB', 'PROP'], ['DOOR_LOCK', 'PROP'], ['HANDBAG', 'PROP'],
  ['POCKET_HARD_OBJECT', 'PROP'], ['RED_FIBER', 'PROP'], ['RED_UMBRELLA', 'PROP'], ['TABLE_SCRATCH', 'PROP'], ['TICKET', 'PROP'],
] as const

export const productionWorkspaceV2Fixture: ProductionWorkspaceV2Snapshot = {
  schema_version: 'production_workspace_projection_v2',
  book_id: 990401,
  workflow_profile: 'production',
  read_only: true,
  authority_source: 'current_authority_pointers_only',
  project: {
    title: 'Episode 01 · Production Workspace Fixture',
    overall_state: 'blocked',
    overall_progress: 0,
    current_blockers: [{
      code: 'UI_V2_BLOCKED_BY_PRODUCTION_ASSET_INGESTION_API',
      title: '缺少真实视觉资产',
      description: '当前项目需要 15 个真实视觉资产，尚未完成显式媒体绑定。',
      severity: 'blocked',
      stage: 'VISUAL_ASSET',
      scope: 'project',
      book_id: 990401,
      episode: 1,
      recommended_action: '前往资产中心补齐真实视觉资产',
      target_section: 'assets',
      target_params: { section: 'assets', episode: 1 },
    }],
    next_actions: [],
  },
  stages: {},
  episodes: [],
  shots: Array.from({ length: 2 }, (_, index) => ({
    identity: { episode: 1, shot_id: String(index + 1), storyboard_shot_id: index + 1, plan_shot_id: `fixture-shot-${index + 1}` },
    scene: { id: index === 0 ? 'E01_SC001' : 'E01_SC002', name: index === 0 ? '场景一' : '场景二' },
    duration: 4,
    camera: { angle: 'MS', movement: 'static', speed: 'slow' },
    action: '等待真实资产绑定',
    asset_readiness: { state: 'blocked', required: {}, missing: requiredEntities.map(([entity, type]) => `${type}:${entity}`), stale: [], current: false },
    IMAGE: emptyLane,
    VIDEO: emptyLane,
    next_action: { key: 'BLOCKED_BY_PRODUCTION_ASSET_INGESTION_API', label: '等待正式资产摄取 API' },
    blockers: [{ code: 'UI_V2_BLOCKED_BY_PRODUCTION_ASSET_INGESTION_API', message: '当前未提供正式的实体 Production Asset 摄取 API，暂不能在生产链路中上传或建立绑定。' }],
    legacy: { adopted_is_display_only: true },
  })),
  assets: requiredEntities.map(([entity_id, asset_type]) => ({
    entity_id,
    asset_key: `book:990401:${asset_type.toLowerCase()}:${entity_id}`,
    asset_type,
    current_version_id: null,
    revision: null,
    authority_status: 'MISSING_MEDIA',
    stale_status: 'FRESH',
    reference_state: 'needs_action',
    reference_count: 0,
    locked_reference: false,
    media: { present: false, storage_identity: null, checksum: null, mime: null, width: null, height: null },
    current_version: null,
    bindings: [],
    history: [],
  })),
  asset_ingestion_api_available: false,
  view_contract: {
    standard: 'state,next_action,blockers,official_media',
    professional: 'authority,pointer,prompt_ir,model,adapter,transport,execution,candidate,validation,official,history',
  },
  legacy_adopted_is_display_only: true,
  provider_calls: 0,
}

function cloneFixture<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

const reviewCandidate = {
  id: 'fixture-media-candidate-image',
  state: 'MEDIA_CANDIDATE',
  preview: null,
  preview_url: null,
  created_at: '2026-09-30T00:00:00Z',
  model_profile_id: 'fixture-image-profile',
  technical_validation: { status: 'TECHNICALLY_VALID', validation_id: 'fixture-validation-image', mime: 'image/png', width: 1024, height: 576, duration_ms: null, details: { fixture: true } },
  checksum: 'fixture-candidate-checksum',
  storage_identity: null,
}

const reviewVideoCandidate = {
  ...reviewCandidate,
  id: 'fixture-media-candidate-video',
  model_profile_id: 'fixture-video-profile',
  technical_validation: { ...reviewCandidate.technical_validation, validation_id: 'fixture-validation-video', mime: 'video/mp4', duration_ms: 4000 },
}

const fixtureOfficialImage = {
  current: true,
  currentness: 'current',
  version: { id: 'fixture-official-image', revision: 1, media_type: 'IMAGE', storage_identity: null, checksum: 'fixture-official-image-checksum', mime: 'image/png', width: 1024, height: 576, duration_ms: null, candidate_id: 'fixture-media-candidate-image', validation_id: 'fixture-validation-image' },
  authority: { id: 'fixture-authority-image', status: 'CURRENT', payload_hash: 'fixture-authority-payload', lineage_hash: 'fixture-authority-lineage' },
  pointer: { id: 1, authority_id: 'fixture-authority-image', fingerprint: 'fixture-pointer-image' },
  preview: null,
  preview_url: null,
} as const

/**
 * DEV-only disposable review fixture. It contains evidence placeholders and
 * never creates or promotes a real candidate. The production hook gates this
 * fixture behind import.meta.env.DEV and an explicit query parameter.
 */
export function createProductionWorkspaceV2ReviewFixture(options: { lane?: 'IMAGE' | 'VIDEO'; promoted?: boolean } = {}): ProductionWorkspaceV2Snapshot {
  const lane = options.lane ?? 'IMAGE'
  const promoted = options.promoted === true
  const base = cloneFixture(productionWorkspaceV2Fixture)
  const baseShot = base.shots[0]
  const imageCandidate = lane === 'IMAGE' && !promoted ? reviewCandidate : null
  const videoCandidate = lane === 'VIDEO' && !promoted ? reviewVideoCandidate : null
  const imageOfficial = lane === 'VIDEO' || promoted ? fixtureOfficialImage : baseShot.IMAGE.official
  const image = {
    ...baseShot.IMAGE,
    prompt_ir: { current: true, version: 1, stale: false, state: 'complete', reason_codes: [] },
    model: { selected_profile_id: 'fixture-image-profile', provider: 'fixture', model_name: 'Fixture Image Review' },
    generation_readiness: { ready: !promoted, reason_codes: promoted ? ['OFFICIAL_MEDIA_ALREADY_CURRENT'] : [], primary_blocker: null, blockers: [] },
    candidates: { count: imageCandidate ? 1 : 1, latest: imageCandidate ?? { ...reviewCandidate, technical_validation: { ...reviewCandidate.technical_validation, validation_id: 'fixture-validation-image' } }, items: [imageCandidate ?? { ...reviewCandidate, technical_validation: { ...reviewCandidate.technical_validation, validation_id: 'fixture-validation-image' } }] },
    official: imageOfficial,
  }
  const video = {
    ...baseShot.VIDEO,
    generation_mode: 'IMAGE_TO_VIDEO' as const,
    prompt_ir: { current: true, version: 1, stale: false, state: 'complete', reason_codes: [] },
    model: { selected_profile_id: 'fixture-video-profile', provider: 'fixture', model_name: 'Fixture Video Review' },
    source_official_image: lane === 'IMAGE' && !promoted ? null : fixtureOfficialImage,
    generation_readiness: ((lane === 'VIDEO' && !promoted) || (lane === 'IMAGE' && promoted))
      ? { ready: true, reason_codes: [], primary_blocker: null, blockers: [] }
      : { ready: false, reason_codes: ['OFFICIAL_IMAGE_REQUIRED'], primary_blocker: { code: 'OFFICIAL_IMAGE_REQUIRED', message: 'IMAGE_TO_VIDEO 需要先建立当前正式图片。' }, blockers: [{ code: 'OFFICIAL_IMAGE_REQUIRED', message: 'IMAGE_TO_VIDEO 需要先建立当前正式图片。' }] },
    candidates: { count: videoCandidate ? 1 : 0, latest: videoCandidate, items: videoCandidate ? [videoCandidate] : [] },
    official: promoted && lane === 'VIDEO'
      ? { ...fixtureOfficialImage, version: { ...fixtureOfficialImage.version, id: 'fixture-official-video', media_type: 'VIDEO', candidate_id: 'fixture-media-candidate-video', validation_id: 'fixture-validation-video' }, authority: { ...fixtureOfficialImage.authority, id: 'fixture-authority-video' }, pointer: { ...fixtureOfficialImage.pointer, authority_id: 'fixture-authority-video' } }
      : baseShot.VIDEO.official,
  }
  const shot = {
    ...baseShot,
    scene: { id: 'E01_SC001', name: '审核场景' },
    action: lane === 'IMAGE' ? '审核图片候选' : '审核视频候选',
    asset_readiness: { state: 'ready' as const, required: {}, missing: [], stale: [], current: true },
    IMAGE: image,
    VIDEO: video,
    blockers: [],
    next_action: promoted ? { key: 'GENERATE_VIDEO', label: '生成视频' } : { key: 'REVIEW_MEDIA_CANDIDATE', label: '审核候选媒体' },
  }
  return {
    ...base,
    project: { ...base.project, overall_state: 'ready', current_blockers: [], next_actions: [] },
    shots: [shot],
    assets: [],
    asset_ingestion_api_available: true,
    provider_calls: 0,
  }
}

export type ProductionWorkspaceV2GenerationFixtureKind =
  | 'ready-image'
  | 'running-image'
  | 'review-image'
  | 'official-image-ready-video'
  | 'running-video'
  | 'review-video'
  | 'official-shot'

/** Disposable DEV-only states used by Shot Studio generation QA. */
export function createProductionWorkspaceV2GenerationFixture(kind: ProductionWorkspaceV2GenerationFixtureKind): ProductionWorkspaceV2Snapshot {
  const base = createProductionWorkspaceV2ReviewFixture({ lane: kind.includes('video') ? 'VIDEO' : 'IMAGE', promoted: false })
  const shot = base.shots[0]
  const cleanImage: any = {
    ...shot.IMAGE,
    candidates: { count: 0, latest: null, items: [] },
    generation_readiness: { ready: true, reason_codes: [], primary_blocker: null, blockers: [] },
    official: { current: false, currentness: 'missing', version: null, authority: null, pointer: null, preview: null },
    model: { selected_profile_id: 'fixture-image-profile', provider: 'fixture', model_name: 'Fixture Image Generation' },
  }
  const cleanVideo: any = {
    ...shot.VIDEO,
    candidates: { count: 0, latest: null, items: [] },
    generation_readiness: { ready: false, reason_codes: ['OFFICIAL_IMAGE_REQUIRED'], primary_blocker: { code: 'OFFICIAL_IMAGE_REQUIRED', message: 'IMAGE_TO_VIDEO 需要先建立当前正式图片。' }, blockers: [{ code: 'OFFICIAL_IMAGE_REQUIRED', message: 'IMAGE_TO_VIDEO 需要先建立当前正式图片。' }] },
    official: { current: false, currentness: 'missing', version: null, authority: null, pointer: null, preview: null },
    model: { selected_profile_id: 'fixture-video-profile', provider: 'fixture', model_name: 'Fixture Video Generation' },
  }
  // Match the canonical V2 projection shape consumed by productionUiV3.
  const runningExecution: any = { id: `fixture-${kind}`, state: 'RUNNING', provider: 'fixture', model: 'Fixture' }
  let nextShot: any = { ...shot, IMAGE: cleanImage, VIDEO: cleanVideo, blockers: [], asset_readiness: { state: 'ready' as const, required: {}, missing: [], stale: [], current: true }, next_action: { key: 'GENERATE_IMAGE', label: '生成图片' } }
  if (kind === 'running-image') nextShot = { ...nextShot, IMAGE: { ...cleanImage, latest_execution: runningExecution, generation_readiness: { ...cleanImage.generation_readiness, ready: false, reason_codes: ['EXECUTION_RUNNING'] } } }
  if (kind === 'review-image') nextShot = { ...createProductionWorkspaceV2ReviewFixture({ lane: 'IMAGE' }).shots[0], blockers: [] }
  if (kind === 'official-image-ready-video') nextShot = { ...nextShot, IMAGE: { ...cleanImage, official: fixtureOfficialImage }, VIDEO: { ...cleanVideo, source_official_image: fixtureOfficialImage, generation_readiness: { ready: true, reason_codes: [], primary_blocker: null, blockers: [] } }, next_action: { key: 'GENERATE_VIDEO', label: '生成视频' } }
  if (kind === 'running-video') nextShot = { ...nextShot, IMAGE: { ...cleanImage, official: fixtureOfficialImage }, VIDEO: { ...cleanVideo, source_official_image: fixtureOfficialImage, latest_execution: runningExecution, generation_readiness: { ready: false, reason_codes: ['EXECUTION_RUNNING'], primary_blocker: null, blockers: [] } }, next_action: { key: 'WAIT_FOR_VIDEO', label: '等待视频' } }
  if (kind === 'review-video') nextShot = { ...createProductionWorkspaceV2ReviewFixture({ lane: 'VIDEO' }).shots[0], blockers: [] }
  if (kind === 'official-shot') nextShot = { ...createProductionWorkspaceV2ReviewFixture({ lane: 'VIDEO', promoted: true }).shots[0], blockers: [] }
  return { ...base, project: { ...base.project, overall_state: 'ready', current_blockers: [] }, shots: [nextShot], assets: [], asset_ingestion_api_available: true, provider_calls: 0 }
}

export const productionWorkspaceV2GenerationFixtures: Record<ProductionWorkspaceV2GenerationFixtureKind, ProductionWorkspaceV2Snapshot> = {
  'ready-image': createProductionWorkspaceV2GenerationFixture('ready-image'),
  'running-image': createProductionWorkspaceV2GenerationFixture('running-image'),
  'review-image': createProductionWorkspaceV2GenerationFixture('review-image'),
  'official-image-ready-video': createProductionWorkspaceV2GenerationFixture('official-image-ready-video'),
  'running-video': createProductionWorkspaceV2GenerationFixture('running-video'),
  'review-video': createProductionWorkspaceV2GenerationFixture('review-video'),
  'official-shot': createProductionWorkspaceV2GenerationFixture('official-shot'),
}
