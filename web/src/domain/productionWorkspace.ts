export type ProductionStageState =
  | 'not_started'
  | 'in_progress'
  | 'ready'
  | 'blocked'
  | 'needs_action'
  | 'stale'
  | 'complete'
  | 'warning'

export type ProductionWorkspaceLoadState = 'loading' | 'ready' | 'unavailable'

export type ProductionWorkspaceViewMode = 'standard' | 'professional'

export type ProductionLaneState = 'not_started' | 'ready' | 'blocked' | 'stale' | 'in_progress' | 'complete' | string

export interface ProductionPromptLane {
  current: boolean
  version: number | string | null
  stale: boolean
  state: ProductionLaneState
  payload_hash?: string | null
}

export interface ProductionModelProjection {
  selected_profile_id: string | null
  provider: string | null
  model_name: string | null
}

export interface GenerationExecutionProjection {
  id: string
  state: string
  target_media: 'IMAGE' | 'VIDEO' | string
  model_profile_id: string
  provider: string
  model: string
  adapter: string
  adapter_version: string
  transport_retry_count: number
  provider_task_id: string
  provider_request_id: string
  request_fingerprint: string
  candidate_id: string | null
  failure_code: string | null
  created_at: string | null
  completed_at: string | null
}

export interface MediaTechnicalValidation {
  status: string
  validation_id: string | null
  mime: string | null
  width: number | null
  height: number | null
  duration_ms: number | null
  details: Record<string, unknown>
}

export interface MediaCandidateProjection {
  id: string
  state: string
  preview: string | null
  created_at: string | null
  model_profile_id: string
  technical_validation: MediaTechnicalValidation
  checksum: string | null
  storage_identity: string | null
}

export interface OfficialMediaProjection {
  current: boolean
  currentness: 'current' | 'historical' | 'missing' | string
  version: {
    id: string
    revision: number | null
    media_type: string
    storage_identity: string | null
    checksum: string | null
    mime: string | null
    width: number | null
    height: number | null
    duration_ms: number | null
    candidate_id: string | null
    validation_id: string | null
  } | null
  authority: {
    id: string | null
    status: string | null
    payload_hash: string | null
    lineage_hash: string | null
  } | null
  pointer: {
    id: number | null
    authority_id: string | null
    fingerprint: string | null
  } | null
  preview: string | null
}

export interface ProductionMediaLane {
  prompt_ir: ProductionPromptLane
  generation_mode: 'TEXT_TO_IMAGE' | 'TEXT_TO_VIDEO' | 'IMAGE_TO_VIDEO' | string | null
  source_official_image: OfficialMediaProjection | null
  model: ProductionModelProjection
  latest_execution: GenerationExecutionProjection | null
  candidates: {
    count: number
    latest: MediaCandidateProjection | null
    items: MediaCandidateProjection[]
  }
  official: OfficialMediaProjection
}

export interface ProductionAssetV2 {
  entity_id: string
  asset_key: string
  asset_type: string
  current_version_id: number | string | null
  revision: number | null
  authority_status: string
  stale_status: string
  reference_state: ProductionLaneState | string
  reference_count: number
  locked_reference: boolean
  media: {
    present: boolean
    storage_identity: string | null
    checksum: string | null
    mime: string | null
    width: number | null
    height: number | null
  }
  bindings: Array<Record<string, unknown>>
  history: Array<Record<string, unknown>>
}

export interface ProductionShotV2 {
  identity: {
    episode: number
    shot_id: string
    storyboard_shot_id: number
    plan_shot_id: string
  }
  scene: { id: string; name: string }
  duration: number
  camera: { angle: string; movement: string; speed: string }
  action: string
  asset_readiness: {
    state: ProductionLaneState
    required: Record<string, Array<Record<string, unknown>>>
    missing: string[]
    stale: string[]
    current: boolean
  }
  IMAGE: ProductionMediaLane
  VIDEO: ProductionMediaLane
  next_action: { key: string; label: string }
  blockers: Array<{ code: string; message: string; [key: string]: unknown }>
  legacy?: Record<string, unknown>
}

export interface ProductionWorkspaceV2Snapshot {
  schema_version: 'production_workspace_projection_v2' | string
  book_id: number
  workflow_profile: 'production' | string
  read_only: true
  authority_source: 'current_authority_pointers_only' | string
  project: ProductionWorkspaceSnapshot['project']
  stages: Record<string, ProductionStageSummary>
  episodes: EpisodeProductionSummary[]
  shots: ProductionShotV2[]
  assets: ProductionAssetV2[]
  view_contract: { standard: string; professional: string }
  legacy_adopted_is_display_only: true
  provider_calls?: number
}

export function findProductionShotV2(
  snapshot: ProductionWorkspaceV2Snapshot | null | undefined,
  episode: number | null | undefined,
  shotId: string | number | null | undefined,
): ProductionShotV2 | null {
  if (!snapshot || episode == null || shotId == null) return null
  return snapshot.shots.find((shot) => Number(shot.identity.episode) === Number(episode) && String(shot.identity.shot_id) === String(shotId)) ?? null
}

export function isProductionImageGenerationReady(shot: ProductionShotV2 | null | undefined): boolean {
  if (!shot) return false
  return shot.asset_readiness.current && shot.IMAGE.prompt_ir.current && !shot.IMAGE.official.current && shot.IMAGE.candidates.count === 0
}

export function isProductionVideoGenerationReady(shot: ProductionShotV2 | null | undefined): boolean {
  if (!shot) return false
  const sourceReady = shot.VIDEO.generation_mode === 'IMAGE_TO_VIDEO'
    ? Boolean(shot.VIDEO.source_official_image?.current)
    : shot.VIDEO.prompt_ir.current
  return shot.asset_readiness.current && sourceReady && shot.VIDEO.prompt_ir.current && !shot.VIDEO.official.current && shot.VIDEO.candidates.count === 0
}

export interface ProductionNavigationTarget {
  section: string
  episode?: number | null
  scene_id?: string | null
  shot_id?: string | null
  asset_key?: string | null
  blocker_code?: string | null
  task_id?: string | null
}

export interface ProductionBlocker {
  code: string
  title: string
  description: string
  severity: 'blocked' | 'warning' | string
  stage: string
  scope: string
  book_id: number
  episode?: number | null
  scene_id?: string | null
  shot_id?: string | null
  asset_key?: string | null
  recommended_action: string
  target_section: string
  target_params: ProductionNavigationTarget
}

export interface ProductionStageSummary {
  key: string
  label: string
  state: ProductionStageState
  detail: string
  completed: boolean
  blocked: boolean
  stale: boolean
  warning: boolean
  counts: Record<string, number>
  reason_codes: string[]
  target_route: ProductionNavigationTarget
  blockers: ProductionBlocker[]
}

export interface EpisodeProductionSummary {
  episode: number
  overall_state: ProductionStageState
  overall_progress: number
  blockers: ProductionBlocker[]
  next_action: ProductionBlocker | null
  stages: Record<string, ProductionStageSummary>
}

export interface ShotProductionSummary {
  episode: number
  shot_id: string
  storyboard_shot_id: number
  scene_id: string
  plan_shot_id: string
  duration: number
  camera: { angle: string; movement: string; speed: string }
  action: string
  entry_state: string
  exit_state: string
  prompt_ir_state: ProductionStageState | string
  reference_state: ProductionStageState | string
  media_state: ProductionStageState | string
}

export interface AssetAuthoritySummary {
  asset_key: string
  asset_type: string
  current_version_id: number | null
  revision: number | null
  authority_status: string
  stale_status: string
  reference_state: ProductionStageState | string
  reference_count: number
  locked_reference: boolean
}

export interface ProductionWorkspaceSnapshot {
  schema_version: string
  book_id: number
  workflow_profile: 'production' | string
  read_only: boolean
  authority_source: string
  provider_calls: number
  project: {
    title: string
    overall_state: ProductionStageState
    overall_progress: number
    current_blockers: ProductionBlocker[]
    next_actions: ProductionBlocker[]
  }
  stages: Record<string, ProductionStageSummary>
  episodes: EpisodeProductionSummary[]
  shots: ShotProductionSummary[]
  assets: AssetAuthoritySummary[]
}

export function validateProductionWorkspaceSnapshot(value: unknown): string[] {
  const errors: string[] = []
  if (!value || typeof value !== 'object') return ['投影响应不是对象']
  const input = value as Record<string, any>
  if (String(input.schema_version ?? '').trim() !== 'production_workspace_projection_v1') errors.push('schema_version 不受支持')
  if (String(input.workflow_profile ?? '').trim() !== 'production') errors.push('workflow_profile 不是 production')
  if (input.read_only !== true) errors.push('read_only 必须为 true')
  if (String(input.authority_source ?? '').trim() !== 'current_authority_pointers_only') errors.push('authority_source 不受支持')
  if (Number(input.provider_calls ?? -1) !== 0) errors.push('provider_calls 必须为 0')
  if (!input.project || typeof input.project !== 'object') errors.push('缺少 project')
  if (!input.stages || typeof input.stages !== 'object') errors.push('缺少 stages')
  if (!Array.isArray(input.episodes)) errors.push('episodes 必须是数组')
  if (!Array.isArray(input.shots)) errors.push('shots 必须是数组')
  if (!Array.isArray(input.assets)) errors.push('assets 必须是数组')
  return errors
}

export function isKnownProductionState(value: unknown): boolean {
  return new Set(['not_started', 'in_progress', 'ready', 'blocked', 'needs_action', 'stale', 'complete', 'warning']).has(String(value ?? '').trim())
}

export function isProductionSnapshotGenerationReady(snapshot: ProductionWorkspaceSnapshot | null | undefined): boolean {
  if (!snapshot || validateProductionWorkspaceSnapshot(snapshot).length > 0) return false
  if (snapshot.project.overall_state === 'blocked' || snapshot.project.overall_state === 'stale') return false
  return true
}

export function humanizeProductionState(state: string): string {
  const labels: Record<string, string> = {
    not_started: '未开始',
    in_progress: '进行中',
    ready: '可以继续',
    blocked: '暂不能继续',
    needs_action: '待处理',
    stale: '需要更新',
    complete: '已确认',
    warning: '需要注意',
    PRODUCTION_QUALIFIED: '已确认',
    FRESH: '当前有效',
    STALE: '需要更新',
    AUTHORING_PENDING: '待完成视觉设计',
    ASSET_AUTHORING_PENDING: '待完成视觉设计',
    ASSET_REFERENCE_PENDING: '待补参考图',
    REFERENCE_PENDING: '待补参考图',
    REFERENCE_LOCKED: '参考图已锁定',
    BLOCKED: '暂不能继续',
    READY: '可以继续',
    COMPLETE: '已确认',
  }
  const normalized = String(state ?? '').trim()
  return labels[normalized] ?? labels[normalized.toLowerCase()] ?? '待确认'
}

export function normalizeProductionWorkspaceSnapshot(value: unknown, bookId: number): ProductionWorkspaceSnapshot {
  const input = value && typeof value === 'object' ? value as Record<string, any> : {}
  return {
    schema_version: String(input.schema_version ?? 'production_workspace_projection_v1'),
    book_id: Number(input.book_id ?? bookId),
    workflow_profile: String(input.workflow_profile ?? 'production'),
    read_only: input.read_only !== false,
    authority_source: String(input.authority_source ?? 'current_authority_pointers_only'),
    provider_calls: Number(input.provider_calls ?? 0),
    project: {
      title: String(input.project?.title ?? ''),
      overall_state: String(input.project?.overall_state ?? 'not_started') as ProductionStageState,
      overall_progress: Number(input.project?.overall_progress ?? 0),
      current_blockers: Array.isArray(input.project?.current_blockers) ? input.project.current_blockers as ProductionBlocker[] : [],
      next_actions: Array.isArray(input.project?.next_actions) ? input.project.next_actions as ProductionBlocker[] : [],
    },
    stages: (input.stages && typeof input.stages === 'object' ? input.stages : {}) as Record<string, ProductionStageSummary>,
    episodes: Array.isArray(input.episodes) ? input.episodes as EpisodeProductionSummary[] : [],
    shots: Array.isArray(input.shots) ? input.shots as ShotProductionSummary[] : [],
    assets: Array.isArray(input.assets) ? input.assets as AssetAuthoritySummary[] : [],
  }
}

function asRecord(value: unknown): Record<string, any> {
  return value && typeof value === 'object' ? value as Record<string, any> : {}
}

function normalizeOfficial(value: unknown): OfficialMediaProjection {
  const input = asRecord(value)
  const version = asRecord(input.version)
  const authority = asRecord(input.authority)
  const pointer = asRecord(input.pointer)
  return {
    current: input.current === true,
    currentness: String(input.currentness ?? 'missing'),
    version: input.version && typeof input.version === 'object' ? {
      id: String(version.id ?? ''),
      revision: version.revision == null ? null : Number(version.revision),
      media_type: String(version.media_type ?? ''),
      storage_identity: version.storage_identity == null ? null : String(version.storage_identity),
      checksum: version.checksum == null ? null : String(version.checksum),
      mime: version.mime == null ? null : String(version.mime),
      width: version.width == null ? null : Number(version.width),
      height: version.height == null ? null : Number(version.height),
      duration_ms: version.duration_ms == null ? null : Number(version.duration_ms),
      candidate_id: version.candidate_id == null ? null : String(version.candidate_id),
      validation_id: version.validation_id == null ? null : String(version.validation_id),
    } : null,
    authority: input.authority && typeof input.authority === 'object' ? {
      id: authority.id == null ? null : String(authority.id),
      status: authority.status == null ? null : String(authority.status),
      payload_hash: authority.payload_hash == null ? null : String(authority.payload_hash),
      lineage_hash: authority.lineage_hash == null ? null : String(authority.lineage_hash),
    } : null,
    pointer: input.pointer && typeof input.pointer === 'object' ? {
      id: pointer.id == null ? null : Number(pointer.id),
      authority_id: pointer.authority_id == null ? null : String(pointer.authority_id),
      fingerprint: pointer.fingerprint == null ? null : String(pointer.fingerprint),
    } : null,
    preview: input.preview == null ? null : String(input.preview),
  }
}

function normalizeLane(value: unknown): ProductionMediaLane {
  const input = asRecord(value)
  const prompt = asRecord(input.prompt_ir)
  const model = asRecord(input.model)
  const candidates = asRecord(input.candidates)
  const normalizeCandidate = (candidate: unknown): MediaCandidateProjection | null => {
    if (!candidate || typeof candidate !== 'object') return null
    const item = asRecord(candidate)
    const validation = asRecord(item.technical_validation)
    return {
      id: String(item.id ?? ''),
      state: String(item.state ?? 'MEDIA_CANDIDATE'),
      preview: item.preview == null ? null : String(item.preview),
      created_at: item.created_at == null ? null : String(item.created_at),
      model_profile_id: String(item.model_profile_id ?? ''),
      technical_validation: {
        status: String(validation.status ?? 'NOT_RUN'),
        validation_id: validation.validation_id == null ? null : String(validation.validation_id),
        mime: validation.mime == null ? null : String(validation.mime),
        width: validation.width == null ? null : Number(validation.width),
        height: validation.height == null ? null : Number(validation.height),
        duration_ms: validation.duration_ms == null ? null : Number(validation.duration_ms),
        details: validation.details && typeof validation.details === 'object' ? validation.details : {},
      },
      checksum: item.checksum == null ? null : String(item.checksum),
      storage_identity: item.storage_identity == null ? null : String(item.storage_identity),
    }
  }
  const executionInput = input.latest_execution
  const executionRecord = executionInput && typeof executionInput === 'object' ? asRecord(executionInput) : null
  return {
    prompt_ir: {
      current: prompt.current === true,
      version: prompt.version == null ? null : (typeof prompt.version === 'number' ? prompt.version : String(prompt.version)),
      stale: prompt.stale === true,
      state: String(prompt.state ?? 'not_started'),
      payload_hash: prompt.payload_hash == null ? null : String(prompt.payload_hash),
    },
    generation_mode: input.generation_mode == null ? null : String(input.generation_mode) as ProductionMediaLane['generation_mode'],
    source_official_image: input.source_official_image ? normalizeOfficial(input.source_official_image) : null,
    model: {
      selected_profile_id: model.selected_profile_id == null ? null : String(model.selected_profile_id),
      provider: model.provider == null ? null : String(model.provider),
      model_name: model.model_name == null ? null : String(model.model_name),
    },
    latest_execution: executionRecord ? {
      id: String(executionRecord.id ?? ''),
      state: String(executionRecord.state ?? 'unknown'),
      target_media: String(executionRecord.target_media ?? ''),
      model_profile_id: String(executionRecord.model_profile_id ?? ''),
      provider: String(executionRecord.provider ?? ''),
      model: String(executionRecord.model ?? ''),
      adapter: String(executionRecord.adapter ?? ''),
      adapter_version: String(executionRecord.adapter_version ?? ''),
      transport_retry_count: Number(executionRecord.transport_retry_count ?? 0),
      provider_task_id: String(executionRecord.provider_task_id ?? ''),
      provider_request_id: String(executionRecord.provider_request_id ?? ''),
      request_fingerprint: String(executionRecord.request_fingerprint ?? ''),
      candidate_id: executionRecord.candidate_id == null ? null : String(executionRecord.candidate_id),
      failure_code: executionRecord.failure_code == null ? null : String(executionRecord.failure_code),
      created_at: executionRecord.created_at == null ? null : String(executionRecord.created_at),
      completed_at: executionRecord.completed_at == null ? null : String(executionRecord.completed_at),
    } : null,
    candidates: {
      count: Number(candidates.count ?? 0),
      latest: normalizeCandidate(candidates.latest),
      items: Array.isArray(candidates.items) ? candidates.items.map(normalizeCandidate).filter((item): item is MediaCandidateProjection => Boolean(item)) : [],
    },
    official: normalizeOfficial(input.official),
  }
}

export function validateProductionWorkspaceV2Snapshot(value: unknown): string[] {
  const errors: string[] = []
  const input = asRecord(value)
  if (String(input.schema_version ?? '').trim() !== 'production_workspace_projection_v2') errors.push('schema_version 不受支持')
  if (String(input.workflow_profile ?? '').trim() !== 'production') errors.push('workflow_profile 不是 production')
  if (input.read_only !== true) errors.push('read_only 必须为 true')
  if (String(input.authority_source ?? '').trim() !== 'current_authority_pointers_only') errors.push('authority_source 不受支持')
  if (!input.project || typeof input.project !== 'object') errors.push('缺少 project')
  if (!input.view_contract || typeof input.view_contract !== 'object') errors.push('缺少 view_contract')
  if (!Array.isArray(input.shots)) errors.push('shots 必须是数组')
  if (!Array.isArray(input.assets)) errors.push('assets 必须是数组')
  return errors
}

export function normalizeProductionWorkspaceV2Snapshot(value: unknown, bookId: number): ProductionWorkspaceV2Snapshot {
  const input = asRecord(value)
  const project = normalizeProductionWorkspaceSnapshot({
    schema_version: 'production_workspace_projection_v1',
    book_id: input.book_id ?? bookId,
    workflow_profile: input.workflow_profile ?? 'production',
    read_only: true,
    authority_source: input.authority_source ?? 'current_authority_pointers_only',
    provider_calls: input.provider_calls ?? 0,
    project: input.project,
    stages: input.stages,
    episodes: input.episodes,
    shots: [],
    assets: [],
  }, bookId)
  const shots: ProductionShotV2[] = Array.isArray(input.shots) ? input.shots.map((value: unknown) => {
    const item = asRecord(value)
    const identity = asRecord(item.identity)
    const scene = asRecord(item.scene)
    const readiness = asRecord(item.asset_readiness)
    return {
      identity: {
        episode: Number(identity.episode ?? 0),
        shot_id: String(identity.shot_id ?? ''),
        storyboard_shot_id: Number(identity.storyboard_shot_id ?? 0),
        plan_shot_id: String(identity.plan_shot_id ?? ''),
      },
      scene: { id: String(scene.id ?? ''), name: String(scene.name ?? '') },
      duration: Number(item.duration ?? 0),
      camera: { angle: String(item.camera?.angle ?? ''), movement: String(item.camera?.movement ?? ''), speed: String(item.camera?.speed ?? '') },
      action: String(item.action ?? ''),
      asset_readiness: {
        state: String(readiness.state ?? 'blocked'),
        required: readiness.required && typeof readiness.required === 'object' ? readiness.required : {},
        missing: Array.isArray(readiness.missing) ? readiness.missing.map(String) : [],
        stale: Array.isArray(readiness.stale) ? readiness.stale.map(String) : [],
        current: readiness.current === true,
      },
      IMAGE: normalizeLane(item.IMAGE),
      VIDEO: normalizeLane(item.VIDEO),
      next_action: { key: String(item.next_action?.key ?? ''), label: String(item.next_action?.label ?? '') },
      blockers: Array.isArray(item.blockers) ? item.blockers as ProductionShotV2['blockers'] : [],
      legacy: item.legacy && typeof item.legacy === 'object' ? item.legacy : undefined,
    }
  }) : []
  const assets: ProductionAssetV2[] = Array.isArray(input.assets) ? input.assets.map((value: unknown) => {
    const item = asRecord(value)
    const media = asRecord(item.media)
    return {
      entity_id: String(item.entity_id ?? item.asset_key ?? ''),
      asset_key: String(item.asset_key ?? ''),
      asset_type: String(item.asset_type ?? ''),
      current_version_id: item.current_version_id == null ? null : item.current_version_id,
      revision: item.revision == null ? null : Number(item.revision),
      authority_status: String(item.authority_status ?? ''),
      stale_status: String(item.stale_status ?? ''),
      reference_state: String(item.reference_state ?? 'needs_action'),
      reference_count: Number(item.reference_count ?? 0),
      locked_reference: item.locked_reference === true,
      media: {
        present: media.present === true,
        storage_identity: media.storage_identity == null ? null : String(media.storage_identity),
        checksum: media.checksum == null ? null : String(media.checksum),
        mime: media.mime == null ? null : String(media.mime),
        width: media.width == null ? null : Number(media.width),
        height: media.height == null ? null : Number(media.height),
      },
      bindings: Array.isArray(item.bindings) ? item.bindings as Array<Record<string, unknown>> : [],
      history: Array.isArray(item.history) ? item.history as Array<Record<string, unknown>> : [],
    }
  }) : []
  return {
    schema_version: String(input.schema_version ?? 'production_workspace_projection_v2'),
    book_id: Number(input.book_id ?? bookId),
    workflow_profile: String(input.workflow_profile ?? 'production'),
    read_only: true,
    authority_source: String(input.authority_source ?? 'current_authority_pointers_only'),
    project: project.project,
    stages: project.stages,
    episodes: project.episodes,
    shots,
    assets,
    view_contract: {
      standard: String(input.view_contract?.standard ?? 'state,next_action,blockers,official_media'),
      professional: String(input.view_contract?.professional ?? 'authority,pointer,prompt_ir,model,adapter,transport,execution,candidate,validation,official,history'),
    },
    legacy_adopted_is_display_only: true,
    provider_calls: Number(input.provider_calls ?? 0),
  }
}
