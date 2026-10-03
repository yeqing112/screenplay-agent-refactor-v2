import type {
  GenerationExecutionProjection,
  MediaCandidateProjection,
  OfficialMediaProjection,
  ProductionMediaLane,
  ProductionShotV2,
} from './productionWorkspace'

export type ProductionUiState =
  | 'ready'
  | 'running'
  | 'review'
  | 'waiting'
  | 'blocked'
  | 'stale'
  | 'failed'
  | 'official'

export type ProductionLaneTarget = 'IMAGE' | 'VIDEO'

export type ProductionPrimaryActionKind =
  | 'resolve_blocker'
  | 'refresh_stale_source'
  | 'retry_generation'
  | 'wait'
  | 'review_candidate'
  | 'generate_image'
  | 'generate_video'
  | 'view_official'
  | 'inspect'

export type ProductionSecondaryActionKind = 'regenerate_media'

export type ProductionUiReasonCode =
  | 'V3_CANONICAL_OFFICIAL_POINTER_MISSING'
  | 'V3_CANONICAL_OFFICIAL_POINTER_MISMATCH'
  | 'V3_CANONICAL_SOURCE_OFFICIAL_IMAGE_INVALID'
  | 'V3_UNKNOWN_EXECUTION_STATE'
  | 'V3_EXECUTION_CANDIDATE_MISSING'
  | 'V3_EXECUTION_CANDIDATE_NOT_VISIBLE'
  | 'V3_CANDIDATE_NOT_REVIEWABLE'
  | 'V3_READINESS_CONTRACT_MISSING'
  | 'V3_READINESS_CONTRACT_INCONSISTENT'
  | 'V3_STATE_UNRESOLVED'
  | string

export interface ProductionPrimaryAction {
  kind: ProductionPrimaryActionKind
  label: string
  lane?: ProductionLaneTarget
  enabled: boolean
  reason?: string
  reasonCodes: string[]
  requiresProviderCall: boolean
}

export interface ProductionSecondaryAction {
  kind: ProductionSecondaryActionKind
  label: string
  lane: ProductionLaneTarget
  enabled: boolean
  reason?: string
  reasonCodes: string[]
  requiresProviderCall: boolean
}

export interface CanonicalOfficialMediaViewModel {
  isCanonicalOfficial: boolean
  current: boolean
  currentness: string
  version: OfficialMediaProjection['version']
  authority: OfficialMediaProjection['authority']
  pointer: OfficialMediaProjection['pointer']
  preview: string | null
  reasonCodes: string[]
}

export type ExecutionUiState = 'waiting' | 'running' | 'succeeded' | 'failed' | 'stale' | 'unknown' | 'none'

export interface GenerationExecutionViewModel {
  id: string | null
  rawState: string | null
  state: ExecutionUiState
  isActive: boolean
  isTerminal: boolean
  retryAllowed: boolean
  failureCode: string | null
  provider: string | null
  model: string | null
  providerTaskId: string | null
  providerRequestId: string | null
  requestFingerprint: string | null
  raw: GenerationExecutionProjection | null
}

export interface CandidateReviewSummary {
  candidate: MediaCandidateProjection | null
  candidateCount: number
  reviewableCount: number
  reviewEligibility: boolean
  reviewReason: string | null
  validationStatus: string | null
  reasonCodes: string[]
}

export interface ProductionMediaLaneViewModel {
  target: ProductionLaneTarget
  state: ProductionUiState
  stateLabel: string
  detail: string
  reasonCodes: string[]
  prompt: {
    current: boolean
    stale: boolean
    state: string
    version: number | string | null
    reasonCodes: string[]
  }
  generationMode: ProductionMediaLane['generation_mode']
  generationReady: boolean
  generationAllowed: boolean
  readinessReasons: string[]
  readinessBlockers: Array<{ code: string; message: string; [key: string]: unknown }>
  official: CanonicalOfficialMediaViewModel
  sourceOfficialImage: CanonicalOfficialMediaViewModel | null
  execution: GenerationExecutionViewModel
  candidate: CandidateReviewSummary
  primaryAction: ProductionPrimaryAction
  regenerateAction: ProductionSecondaryAction
  professional: {
    model: ProductionMediaLane['model']
    generationModeSource: string | null
    generationReadiness: ProductionMediaLane['generation_readiness'] | null
    officialRaw: OfficialMediaProjection
    candidateItems: MediaCandidateProjection[]
  }
}

export interface ShotStudioViewModel {
  shotId: string
  episode: number
  scene: { id: string; name: string }
  storyboardShotId: number
  planShotId: string
  duration: number
  camera: ProductionShotV2['camera']
  action: string
  state: ProductionUiState
  stateLabel: string
  detail: string
  image: ProductionMediaLaneViewModel
  video: ProductionMediaLaneViewModel
  officialMedia: {
    IMAGE: CanonicalOfficialMediaViewModel
    VIDEO: CanonicalOfficialMediaViewModel
  }
  blockers: Array<{ code: string; message: string; lane?: ProductionLaneTarget; [key: string]: unknown }>
  stale: {
    isStale: boolean
    reasonCodes: string[]
  }
  readiness: {
    image: boolean
    video: boolean
    reasonCodes: string[]
  }
  primaryAction: ProductionPrimaryAction
  professional: {
    authoritySource: 'current_authority_pointers_only'
    backendNextAction: ProductionShotV2['next_action']
    rawBlockers: ProductionShotV2['blockers']
    assetReadiness: ProductionShotV2['asset_readiness']
    legacy: ProductionShotV2['legacy']
  }
}

const ACTIVE_EXECUTION_STATES = new Set(['CREATED', 'QUEUED', 'RUNNING', 'PROVIDER_PENDING', 'PROVIDER_CALLED', 'RETRYING'])
const RUNNING_EXECUTION_STATES = new Set(['RUNNING', 'PROVIDER_PENDING', 'PROVIDER_CALLED'])
const WAITING_EXECUTION_STATES = new Set(['CREATED', 'QUEUED', 'RETRYING'])
const REVIEWABLE_VALIDATIONS = new Set(['TECHNICALLY_VALID', 'REVIEW_REQUIRED', 'PASS'])
const WAITING_VALIDATIONS = new Set(['VALIDATION_PENDING', 'PENDING', 'NOT_RUN', ''])
const FAILED_EXECUTION_STATES = new Set(['FAILED', 'CANCELLED', 'ERROR'])

export const PRODUCTION_UI_REASON_CODES = {
  CANONICAL_OFFICIAL_POINTER_MISSING: 'V3_CANONICAL_OFFICIAL_POINTER_MISSING',
  CANONICAL_OFFICIAL_POINTER_MISMATCH: 'V3_CANONICAL_OFFICIAL_POINTER_MISMATCH',
  CANONICAL_SOURCE_OFFICIAL_IMAGE_INVALID: 'V3_CANONICAL_SOURCE_OFFICIAL_IMAGE_INVALID',
  UNKNOWN_EXECUTION_STATE: 'V3_UNKNOWN_EXECUTION_STATE',
  EXECUTION_CANDIDATE_MISSING: 'V3_EXECUTION_CANDIDATE_MISSING',
  EXECUTION_CANDIDATE_NOT_VISIBLE: 'V3_EXECUTION_CANDIDATE_NOT_VISIBLE',
  CANDIDATE_NOT_REVIEWABLE: 'V3_CANDIDATE_NOT_REVIEWABLE',
  READINESS_CONTRACT_MISSING: 'V3_READINESS_CONTRACT_MISSING',
  READINESS_CONTRACT_INCONSISTENT: 'V3_READINESS_CONTRACT_INCONSISTENT',
  STATE_UNRESOLVED: 'V3_STATE_UNRESOLVED',
} as const

const STATE_LABELS: Record<ProductionUiState, string> = {
  ready: '可以继续',
  running: '生成中',
  review: '待审核',
  waiting: '等待上游',
  blocked: '真正阻塞',
  stale: '上游已更新',
  failed: '执行失败',
  official: '正式版本',
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values.map((value) => String(value || '').trim()).filter(Boolean)))
}

function upper(value: unknown): string {
  return String(value ?? '').trim().toUpperCase()
}

function text(value: unknown): string {
  return String(value ?? '').trim()
}

function stateLabel(state: ProductionUiState): string {
  return STATE_LABELS[state]
}

function hasStaleReason(values: string[]): boolean {
  return values.some((value) => upper(value).includes('STALE'))
}

export function isCanonicalOfficialMedia(media: OfficialMediaProjection | null | undefined): CanonicalOfficialMediaViewModel {
  const input = media ?? {
    current: false,
    currentness: 'missing',
    version: null,
    authority: null,
    pointer: null,
    preview: null,
  }
  const reasonCodes: string[] = []
  const version = input.version
  const authority = input.authority
  const pointer = input.pointer
  const pointerPresent = Boolean(pointer && pointer.id != null && text(pointer.authority_id))
  const versionPresent = Boolean(version && text(version.id))
  const authorityPresent = Boolean(authority && text(authority.id))
  const pointerMatchesAuthority = Boolean(pointerPresent && authorityPresent && pointer?.authority_id === authority?.id)
  const currentness = upper(input.currentness)
  const currentnessValid = currentness === 'CURRENT'
  const authorityCurrent = !authority?.status || upper(authority.status) === 'CURRENT'

  if (input.current && !pointerPresent) reasonCodes.push(PRODUCTION_UI_REASON_CODES.CANONICAL_OFFICIAL_POINTER_MISSING)
  if (input.current && !versionPresent) reasonCodes.push(PRODUCTION_UI_REASON_CODES.CANONICAL_OFFICIAL_POINTER_MISSING)
  if (input.current && !authorityPresent) reasonCodes.push(PRODUCTION_UI_REASON_CODES.CANONICAL_OFFICIAL_POINTER_MISSING)
  if (input.current && !pointerMatchesAuthority) reasonCodes.push(PRODUCTION_UI_REASON_CODES.CANONICAL_OFFICIAL_POINTER_MISMATCH)
  if (input.current && !currentnessValid) reasonCodes.push(PRODUCTION_UI_REASON_CODES.CANONICAL_OFFICIAL_POINTER_MISMATCH)
  if (input.current && !authorityCurrent) reasonCodes.push(PRODUCTION_UI_REASON_CODES.CANONICAL_OFFICIAL_POINTER_MISMATCH)
  if (!input.current && currentness === 'INVALID' && pointerPresent) reasonCodes.push(PRODUCTION_UI_REASON_CODES.CANONICAL_OFFICIAL_POINTER_MISMATCH)

  return {
    isCanonicalOfficial: input.current === true && reasonCodes.length === 0 && currentnessValid && versionPresent && authorityPresent && pointerPresent && pointerMatchesAuthority && authorityCurrent,
    current: input.current === true,
    currentness: text(input.currentness) || 'missing',
    version: input.version ?? null,
    authority: input.authority ?? null,
    pointer: input.pointer ?? null,
    preview: input.preview_url ?? input.preview ?? null,
    reasonCodes: unique(reasonCodes),
  }
}

function normalizeExecution(execution: GenerationExecutionProjection | null | undefined, generationReady: boolean): GenerationExecutionViewModel {
  if (!execution) {
    return {
      id: null,
      rawState: null,
      state: 'none',
      isActive: false,
      isTerminal: false,
      retryAllowed: false,
      failureCode: null,
      provider: null,
      model: null,
      providerTaskId: null,
      providerRequestId: null,
      requestFingerprint: null,
      raw: null,
    }
  }
  const rawState = upper(execution.state)
  const isActive = ACTIVE_EXECUTION_STATES.has(rawState)
  const state: ExecutionUiState =
    RUNNING_EXECUTION_STATES.has(rawState) ? 'running'
      : WAITING_EXECUTION_STATES.has(rawState) ? 'waiting'
        : rawState === 'SUCCESS' || rawState === 'SUCCEEDED' ? 'succeeded'
          : rawState === 'STALE' ? 'stale'
            : FAILED_EXECUTION_STATES.has(rawState) ? 'failed'
              : 'unknown'
  const retryAllowed = (state === 'failed' || state === 'stale') && generationReady
  return {
    id: text(execution.id) || null,
    rawState: text(execution.state) || null,
    state,
    isActive,
    isTerminal: !isActive && state !== 'unknown',
    retryAllowed,
    failureCode: text(execution.failure_code) || null,
    provider: text(execution.provider) || null,
    model: text(execution.model) || null,
    providerTaskId: text(execution.provider_task_id) || null,
    providerRequestId: text(execution.provider_request_id) || null,
    requestFingerprint: text(execution.request_fingerprint) || null,
    raw: execution,
  }
}

function laneCandidateSummary(lane: ProductionMediaLane, official: CanonicalOfficialMediaViewModel): CandidateReviewSummary {
  const projectedItems = Array.isArray(lane.candidates?.items) ? lane.candidates.items : []
  const latest = lane.candidates?.latest ?? null
  const items = latest && !projectedItems.some((candidate) => text(candidate.id) === text(latest.id))
    ? [...projectedItems, latest]
    : projectedItems
  const currentOfficialCandidateId = official.isCanonicalOfficial ? text(official.version?.candidate_id) : ''
  const reviewItems = items.filter((candidate) => text(candidate.id) !== currentOfficialCandidateId)
  const reviewable = reviewItems.filter((candidate) => {
    const status = upper(candidate.technical_validation?.status)
    return upper(candidate.state) === 'MEDIA_CANDIDATE' && REVIEWABLE_VALIDATIONS.has(status)
  })
  const waiting = reviewItems.filter((candidate) => WAITING_VALIDATIONS.has(upper(candidate.technical_validation?.status)))
  const stale = reviewItems.filter((candidate) => upper(candidate.technical_validation?.status) === 'STALE')
  const unsupported = reviewItems.filter((candidate) => !REVIEWABLE_VALIDATIONS.has(upper(candidate.technical_validation?.status)) && !WAITING_VALIDATIONS.has(upper(candidate.technical_validation?.status)) && upper(candidate.technical_validation?.status) !== 'STALE')
  const candidate = reviewable[0] ?? items[0] ?? lane.candidates?.latest ?? null
  const reasonCodes: string[] = []
  if (reviewable.length > 0) reasonCodes.push('CANDIDATE_REVIEW_REQUIRED')
  if (waiting.length > 0 && reviewable.length === 0) reasonCodes.push('CANDIDATE_VALIDATION_PENDING')
  if (stale.length > 0) reasonCodes.push('CANDIDATE_STALE')
  if (unsupported.length > 0) reasonCodes.push(PRODUCTION_UI_REASON_CODES.CANDIDATE_NOT_REVIEWABLE)
  return {
    candidate,
    candidateCount: Number(lane.candidates?.count ?? items.length),
    reviewableCount: reviewable.length,
    reviewEligibility: reviewable.length > 0,
    reviewReason: reviewable.length > 0 ? '候选结果已完成技术验证，等待人工审核。' : null,
    validationStatus: candidate ? text(candidate.technical_validation?.status) || null : null,
    reasonCodes: unique(reasonCodes),
  }
}

function isPromptStale(lane: ProductionMediaLane): boolean {
  return lane.prompt_ir.stale === true
    || upper(lane.prompt_ir.state) === 'STALE'
    || hasStaleReason(lane.prompt_ir.reason_codes ?? [])
}

function readinessContract(lane: ProductionMediaLane): {
  present: boolean
  ready: boolean
  reasonCodes: string[]
  blockers: Array<{ code: string; message: string; [key: string]: unknown }>
} {
  const readiness = lane.generation_readiness
  if (!readiness) {
    return {
      present: false,
      ready: false,
      reasonCodes: [PRODUCTION_UI_REASON_CODES.READINESS_CONTRACT_MISSING],
      blockers: [],
    }
  }
  const reasonCodes = Array.isArray(readiness.reason_codes) ? readiness.reason_codes.map(String) : []
  const blockers = Array.isArray(readiness.blockers)
    ? readiness.blockers
    : readiness.primary_blocker
      ? [readiness.primary_blocker]
      : []
  const inconsistent = readiness.ready === true && reasonCodes.length > 0
  if (inconsistent) reasonCodes.push(PRODUCTION_UI_REASON_CODES.READINESS_CONTRACT_INCONSISTENT)
  return {
    present: true,
    ready: readiness.ready === true && !inconsistent,
    reasonCodes: unique(reasonCodes),
    blockers,
  }
}

function isDependencyWaiting(target: ProductionLaneTarget, lane: ProductionMediaLane, readinessReasons: string[]): boolean {
  return target === 'VIDEO'
    && upper(lane.generation_mode) === 'IMAGE_TO_VIDEO'
    && readinessReasons.some((code) => upper(code) === 'OFFICIAL_IMAGE_REQUIRED')
    && !lane.source_official_image?.current
}

function isSourceOfficialStale(lane: ProductionMediaLane): boolean {
  const currentness = upper(lane.source_official_image?.currentness)
  return Boolean(lane.source_official_image)
    && (currentness === 'STALE' || currentness === 'OBSOLETE' || currentness === 'HISTORICAL')
}

function isDownstreamDependencyView(view: ProductionMediaLaneViewModel): boolean {
  return view.target === 'VIDEO'
    && upper(view.generationMode) === 'IMAGE_TO_VIDEO'
    && (view.state === 'waiting' || view.state === 'blocked')
    && view.readinessReasons.some((code) => upper(code) === 'OFFICIAL_IMAGE_REQUIRED')
    && !view.reasonCodes.some((code) => code.startsWith('V3_CANONICAL_'))
}

function isVideoDownstreamDependency(lane: ProductionMediaLane, view: ProductionMediaLaneViewModel): boolean {
  return isDownstreamDependencyView(view) && upper(lane.generation_mode) === 'IMAGE_TO_VIDEO'
}

function hasVisibleExecutionCandidate(lane: ProductionMediaLane, execution: GenerationExecutionViewModel): boolean {
  const candidateId = text(execution.raw?.candidate_id)
  if (!candidateId) return false
  const items = Array.isArray(lane.candidates?.items) ? lane.candidates.items : []
  return items.some((candidate) => text(candidate.id) === candidateId)
    || text(lane.candidates?.latest?.id) === candidateId
}

function laneState(
  target: ProductionLaneTarget,
  lane: ProductionMediaLane,
  official: CanonicalOfficialMediaViewModel,
  sourceOfficialImage: CanonicalOfficialMediaViewModel | null,
  execution: GenerationExecutionViewModel,
  candidate: CandidateReviewSummary,
  readiness: ReturnType<typeof readinessContract>,
): { state: ProductionUiState; detail: string; reasonCodes: string[] } {
  const reasonCodes = unique([
    ...official.reasonCodes,
    ...(sourceOfficialImage?.reasonCodes ?? []),
    ...readiness.reasonCodes,
    ...candidate.reasonCodes,
  ])
  if (official.reasonCodes.length > 0 || sourceOfficialImage?.reasonCodes.length) {
    return { state: 'blocked', detail: '正式媒体 authority/current pointer 证据不一致，已停止状态升级。', reasonCodes }
  }
  if (isPromptStale(lane) || upper(official.currentness) === 'OBSOLETE' || upper(official.currentness) === 'HISTORICAL' || isSourceOfficialStale(lane) || candidate.reasonCodes.includes('CANDIDATE_STALE')) {
    return { state: 'stale', detail: '上游内容已更新，需要重新确认当前结果。', reasonCodes: unique([...reasonCodes, 'PROMPT_IR_STALE', ...(isSourceOfficialStale(lane) ? ['SOURCE_OFFICIAL_IMAGE_STALE'] : [])]) }
  }
  if (execution.state === 'unknown') {
    return { state: 'blocked', detail: '发现未知的 GenerationExecution 状态，无法安全继续。', reasonCodes: unique([...reasonCodes, PRODUCTION_UI_REASON_CODES.UNKNOWN_EXECUTION_STATE]) }
  }
  if (execution.state === 'failed') {
    const failedReason = execution.failureCode || 'GENERATION_EXECUTION_FAILED'
    return { state: 'failed', detail: '最近一次生成执行失败，需要查看原因或重试。', reasonCodes: unique([...reasonCodes, failedReason]) }
  }
  if (execution.state === 'stale') {
    return { state: 'stale', detail: '生成执行使用的上游来源已过期，需要重新生成。', reasonCodes: unique([...reasonCodes, 'STALE_SOURCE']) }
  }
  if (execution.isActive) {
    return {
      state: execution.state === 'running' ? 'running' : 'waiting',
      detail: execution.state === 'running' ? '模型处理中，请等待结果。' : '生成任务已提交，等待执行。',
      reasonCodes: unique([...reasonCodes, execution.state === 'running' ? 'EXECUTION_RUNNING' : 'EXECUTION_QUEUED']),
    }
  }
  if (execution.state === 'succeeded' && !execution.raw?.candidate_id && !official.isCanonicalOfficial) {
    return { state: 'failed', detail: '执行已结束但没有可审核的候选结果。', reasonCodes: unique([...reasonCodes, PRODUCTION_UI_REASON_CODES.EXECUTION_CANDIDATE_MISSING]) }
  }
  if (execution.state === 'succeeded' && execution.raw?.candidate_id && !official.isCanonicalOfficial && !hasVisibleExecutionCandidate(lane, execution)) {
    return { state: 'waiting', detail: '生成已完成，正在同步候选结果。', reasonCodes: unique([...reasonCodes, PRODUCTION_UI_REASON_CODES.EXECUTION_CANDIDATE_NOT_VISIBLE]) }
  }
  if (candidate.reviewEligibility) {
    return { state: 'review', detail: candidate.reviewReason || '候选结果等待人工审核。', reasonCodes }
  }
  if (candidate.candidateCount > 0 && candidate.reasonCodes.includes(PRODUCTION_UI_REASON_CODES.CANDIDATE_NOT_REVIEWABLE)) {
    return { state: 'blocked', detail: '当前候选没有可用的技术验证结果，不能直接审核或晋升。', reasonCodes }
  }
  if (candidate.candidateCount > 0 && candidate.reasonCodes.includes('CANDIDATE_VALIDATION_PENDING')) {
    return { state: 'waiting', detail: '候选正在等待技术验证。', reasonCodes }
  }
  if (isDependencyWaiting(target, lane, readiness.reasonCodes)) {
    return { state: 'waiting', detail: '视频生成等待当前正式图片。', reasonCodes: unique([...reasonCodes, 'OFFICIAL_IMAGE_REQUIRED']) }
  }
  if (official.isCanonicalOfficial) {
    return { state: 'official', detail: '当前 lane 已建立正式版本。', reasonCodes: unique([...reasonCodes, 'OFFICIAL_MEDIA_CURRENT']) }
  }
  if (!readiness.present || readiness.reasonCodes.includes(PRODUCTION_UI_REASON_CODES.READINESS_CONTRACT_INCONSISTENT)) {
    return { state: 'blocked', detail: '生成就绪契约缺失或自相矛盾，不能安全提交生成。', reasonCodes }
  }
  if (readiness.present && readiness.ready) {
    return { state: 'ready', detail: '上游条件已满足，可以提交生成。', reasonCodes }
  }
  if (readiness.reasonCodes.includes('ASSET_MEDIA_NOT_READY') || readiness.reasonCodes.includes('PROMPT_IR_NOT_CURRENT') || readiness.reasonCodes.includes('MODEL_PROFILE_REQUIRED') || readiness.reasonCodes.includes('VIDEO_GENERATION_MODE_INVALID')) {
    return { state: 'blocked', detail: readiness.blockers[0]?.message || '当前生成条件未满足，需要先处理阻塞。', reasonCodes }
  }
  if (readiness.reasonCodes.length > 0) {
    return { state: 'waiting', detail: readiness.blockers[0]?.message || '等待上游条件完成。', reasonCodes }
  }
  return { state: 'waiting', detail: '当前生产状态还没有足够的可执行证据。', reasonCodes: unique([...reasonCodes, PRODUCTION_UI_REASON_CODES.STATE_UNRESOLVED]) }
}

function action(
  kind: ProductionPrimaryActionKind,
  label: string,
  enabled: boolean,
  options: Partial<Pick<ProductionPrimaryAction, 'lane' | 'reason' | 'reasonCodes' | 'requiresProviderCall'>> = {},
): ProductionPrimaryAction {
  return {
    kind,
    label,
    enabled,
    reasonCodes: options.reasonCodes ?? [],
    requiresProviderCall: options.requiresProviderCall ?? false,
    ...options,
  }
}

function lanePrimaryAction(
  target: ProductionLaneTarget,
  state: ProductionUiState,
  execution: GenerationExecutionViewModel,
  candidate: CandidateReviewSummary,
  readiness: ReturnType<typeof readinessContract>,
): ProductionPrimaryAction {
  if (state === 'blocked') return action('resolve_blocker', '处理阻塞', false, { lane: target, reason: '当前状态需要先完成修复。', reasonCodes: readiness.reasonCodes })
  if (state === 'stale') return action('refresh_stale_source', '查看上游变化', true, { lane: target, reason: '上游内容已更新，需要重新确认。', reasonCodes: ['STALE_SOURCE'] })
  if (state === 'failed') {
    const retryable = execution.rawState === 'FAILED' && Boolean(execution.id) && readiness.ready
    return action('retry_generation', '重试本次生成', retryable, {
      lane: target,
      reason: retryable ? '保留失败记录并重新执行当前失败任务。' : '只有当前 FAILED execution 才允许重试。',
      reasonCodes: execution.failureCode ? [execution.failureCode] : ['RETRY_SOURCE_NOT_EXECUTABLE'],
      requiresProviderCall: retryable,
    })
  }
  if (state === 'running') return action('wait', '查看生成进度', true, { lane: target, reason: '模型正在处理中。', reasonCodes: ['EXECUTION_RUNNING'] })
  if (state === 'waiting') return action('wait', '等待上游', false, { lane: target, reason: '当前结果依赖上游生产完成。', reasonCodes: ['WAITING_UPSTREAM'] })
  if (state === 'review') return action('review_candidate', '打开审核', candidate.reviewEligibility, { lane: target, reason: candidate.reviewReason ?? '候选尚未满足审核条件。', reasonCodes: candidate.reasonCodes })
  if (state === 'ready') return action(target === 'IMAGE' ? 'generate_image' : 'generate_video', target === 'IMAGE' ? '生成图片' : '生成视频', readiness.ready, { lane: target, reason: readiness.ready ? undefined : 'generation_readiness 未允许生成。', reasonCodes: readiness.reasonCodes, requiresProviderCall: true })
  return action('view_official', '查看正式版本', true, { lane: target, reason: '当前 lane 已有正式版本。', reasonCodes: ['OFFICIAL_MEDIA_CURRENT'] })
}

function laneRegenerateAction(target: ProductionLaneTarget, state: ProductionUiState, official: CanonicalOfficialMediaViewModel, candidate: CandidateReviewSummary, stale: boolean): ProductionSecondaryAction {
  const enabled = state === 'official' && official.isCanonicalOfficial && !stale && !candidate.reviewEligibility && candidate.reasonCodes.length === 0
  return {
    kind: 'regenerate_media',
    label: '生成新版本',
    lane: target,
    enabled,
    reason: enabled ? '当前正式版本会继续保留，新候选审核通过后才会替换。' : '当前状态已有候选、任务进行中或正式版本证据不完整。',
    reasonCodes: enabled ? ['OFFICIAL_MEDIA_CURRENT'] : ['REGENERATE_NOT_AVAILABLE'],
    requiresProviderCall: enabled,
  }
}

export function toMediaLaneViewModel(target: ProductionLaneTarget, lane: ProductionMediaLane): ProductionMediaLaneViewModel {
  const official = isCanonicalOfficialMedia(lane.official)
  const sourceOfficialImageBase = lane.source_official_image ? isCanonicalOfficialMedia(lane.source_official_image) : null
  const sourceOfficialImage = sourceOfficialImageBase && lane.source_official_image?.current === true && !sourceOfficialImageBase.isCanonicalOfficial
    ? { ...sourceOfficialImageBase, reasonCodes: unique([...sourceOfficialImageBase.reasonCodes, PRODUCTION_UI_REASON_CODES.CANONICAL_SOURCE_OFFICIAL_IMAGE_INVALID]) }
    : sourceOfficialImageBase
  const readiness = readinessContract(lane)
  const candidate = laneCandidateSummary(lane, official)
  const execution = normalizeExecution(lane.latest_execution, readiness.ready)
  const resolved = laneState(target, lane, official, sourceOfficialImage, execution, candidate, readiness)
  const state = resolved.state
  return {
    target,
    state,
    stateLabel: stateLabel(state),
    detail: resolved.detail,
    reasonCodes: unique(resolved.reasonCodes),
    prompt: {
      current: lane.prompt_ir.current === true,
      stale: isPromptStale(lane),
      state: text(lane.prompt_ir.state) || 'not_started',
      version: lane.prompt_ir.version ?? null,
      reasonCodes: unique(lane.prompt_ir.reason_codes ?? []),
    },
    generationMode: lane.generation_mode,
    generationReady: readiness.ready,
    generationAllowed: readiness.ready && state === 'ready',
    readinessReasons: readiness.reasonCodes,
    readinessBlockers: readiness.blockers,
    official,
    sourceOfficialImage,
    execution,
    candidate,
    primaryAction: lanePrimaryAction(target, state, execution, candidate, readiness),
    regenerateAction: laneRegenerateAction(target, state, official, candidate, state === 'stale' || sourceOfficialImage?.currentness === 'STALE'),
    professional: {
      model: lane.model,
      generationModeSource: lane.generation_mode_source ?? null,
      generationReadiness: lane.generation_readiness ?? null,
      officialRaw: lane.official,
      candidateItems: Array.isArray(lane.candidates?.items) ? lane.candidates.items : [],
    },
  }
}

function shotBlockerState(shot: ProductionShotV2): { state: ProductionUiState | null; reasonCodes: string[] } {
  const readiness = shot.asset_readiness
  const reasonCodes: string[] = []
  if (readiness.current !== true && (readiness.stale.length > 0 || upper(readiness.state) === 'STALE')) {
    reasonCodes.push('ASSET_BINDING_STALE')
    return { state: 'stale', reasonCodes }
  }
  if (readiness.current !== true && (readiness.missing.length > 0 || upper(readiness.state) === 'BLOCKED')) {
    reasonCodes.push('ASSET_MEDIA_NOT_READY')
    return { state: 'blocked', reasonCodes }
  }
  const blockerCodes = (shot.blockers ?? []).map((item) => text(item.code)).filter(Boolean)
  if (blockerCodes.some((code) => upper(code).includes('STALE'))) return { state: 'stale', reasonCodes: blockerCodes }
  if (blockerCodes.length > 0) return { state: 'blocked', reasonCodes: blockerCodes }
  return { state: null, reasonCodes }
}

function combineShotState(
  shot: ProductionShotV2,
  image: ProductionMediaLaneViewModel,
  video: ProductionMediaLaneViewModel,
): { state: ProductionUiState; detail: string; reasonCodes: string[] } {
  const blocker = shotBlockerState(shot)
  const reasons = unique([...blocker.reasonCodes, ...image.reasonCodes, ...video.reasonCodes])
  if (image.reasonCodes.some((code) => code.startsWith('V3_CANONICAL_')) || video.reasonCodes.some((code) => code.startsWith('V3_CANONICAL_'))) {
    return { state: 'blocked', detail: '正式媒体 authority/current pointer 证据不一致，已停止状态升级。', reasonCodes: reasons }
  }
  if (blocker.state === 'blocked') return { state: 'blocked', detail: '当前镜头存在需要人工或数据修复的真实阻塞。', reasonCodes: reasons }
  if (blocker.state === 'stale') return { state: 'stale', detail: '镜头绑定或上游内容已更新，需要重新确认。', reasonCodes: reasons }
  if (isVideoDownstreamDependency(shot.VIDEO, video) && image.state !== 'official') {
    return {
      state: image.state,
      detail: image.detail,
      reasonCodes: unique([...reasons, 'DOWNSTREAM_DEPENDENCY_WAIT']),
    }
  }
  const states = [image.state, video.state]
  if (states.includes('blocked')) return { state: 'blocked', detail: '当前镜头存在需要先处理的生成条件阻塞。', reasonCodes: reasons }
  if (states.includes('stale')) return { state: 'stale', detail: '当前镜头有上游内容已更新，需要重新确认。', reasonCodes: reasons }
  if (states.includes('failed')) return { state: 'failed', detail: '当前镜头最近一次生成执行失败。', reasonCodes: reasons }
  if (states.includes('running')) return { state: 'running', detail: '当前镜头有生成任务正在处理中。', reasonCodes: reasons }
  if (states.includes('waiting')) return { state: 'waiting', detail: '当前镜头正在等待上游生产结果。', reasonCodes: reasons }
  if (states.includes('review')) return { state: 'review', detail: '当前镜头有候选结果等待人工审核。', reasonCodes: reasons }
  if (states.includes('ready')) return { state: 'ready', detail: '当前镜头已有可执行的下一步。', reasonCodes: reasons }
  if (states.every((state) => state === 'official')) return { state: 'official', detail: '当前镜头的媒体均为正式版本。', reasonCodes: reasons }
  return { state: 'waiting', detail: '当前镜头正在等待生产链路继续。', reasonCodes: unique([...reasons, PRODUCTION_UI_REASON_CODES.STATE_UNRESOLVED]) }
}

function shotPrimaryAction(
  state: ProductionUiState,
  image: ProductionMediaLaneViewModel,
  video: ProductionMediaLaneViewModel,
): ProductionPrimaryAction {
  const imageIsDependencySource = isDownstreamDependencyView(video) && image.state !== 'official'
  if (state === 'blocked') return action('resolve_blocker', '处理阻塞', false, { lane: imageIsDependencySource ? 'IMAGE' : undefined, reason: '请先处理当前镜头的真实阻塞。', reasonCodes: ['SHOT_BLOCKED'] })
  if (state === 'stale') return action('refresh_stale_source', '查看上游变化', true, { lane: imageIsDependencySource ? 'IMAGE' : undefined, reason: '上游内容已更新，需要重新确认。', reasonCodes: ['STALE_SOURCE'] })
  if (state === 'failed') {
    const failed = image.state === 'failed' ? image : video
    return action('retry_generation', '重新生成', failed.primaryAction.enabled, { lane: failed.target, reason: failed.primaryAction.reason, reasonCodes: failed.reasonCodes })
  }
  if (state === 'running') {
    const running = image.state === 'running' ? image : video
    return action('wait', '查看生成进度', true, { lane: running.target, reason: running.detail, reasonCodes: running.reasonCodes })
  }
  if (state === 'waiting') {
    const waiting = image.state === 'waiting' ? image : video
    return action('wait', '等待上游', false, { lane: waiting.target, reason: waiting.detail, reasonCodes: waiting.reasonCodes })
  }
  if (state === 'review') {
    const review = image.state === 'review' ? image : video
    return action('review_candidate', '打开审核', review.primaryAction.enabled, { lane: review.target, reason: review.primaryAction.reason, reasonCodes: review.reasonCodes })
  }
  if (state === 'ready') {
    const ready = image.state === 'ready' ? image : video
    return ready.primaryAction
  }
  return action('view_official', '查看正式版本', true, { reason: '当前镜头已建立正式媒体。', reasonCodes: ['OFFICIAL_MEDIA_CURRENT'] })
}

export function toShotStudioViewModel(shot: ProductionShotV2): ShotStudioViewModel {
  const image = toMediaLaneViewModel('IMAGE', shot.IMAGE)
  const video = toMediaLaneViewModel('VIDEO', shot.VIDEO)
  const combined = combineShotState(shot, image, video)
  const primaryAction = shotPrimaryAction(combined.state, image, video)
  const staleReasonCodes = unique([
    ...(shot.asset_readiness.stale ?? []).map(() => 'ASSET_BINDING_STALE'),
    ...(combined.state === 'stale' ? combined.reasonCodes : []),
    ...image.reasonCodes.filter((code) => upper(code).includes('STALE')),
    ...video.reasonCodes.filter((code) => upper(code).includes('STALE')),
  ])
  const blockers = [
    ...(shot.blockers ?? []).map((item) => ({ ...item })),
    ...image.readinessBlockers.map((item) => ({ ...item, lane: 'IMAGE' as const })),
    ...video.readinessBlockers.map((item) => ({ ...item, lane: 'VIDEO' as const })),
  ]
  return {
    shotId: text(shot.identity.shot_id),
    episode: Number(shot.identity.episode),
    scene: { id: text(shot.scene.id), name: text(shot.scene.name) || text(shot.scene.id) },
    storyboardShotId: Number(shot.identity.storyboard_shot_id),
    planShotId: text(shot.identity.plan_shot_id),
    duration: Number(shot.duration || 0),
    camera: shot.camera,
    action: text(shot.action),
    state: combined.state,
    stateLabel: stateLabel(combined.state),
    detail: combined.detail,
    image,
    video,
    officialMedia: { IMAGE: image.official, VIDEO: video.official },
    blockers,
    stale: { isStale: staleReasonCodes.length > 0, reasonCodes: staleReasonCodes },
    readiness: { image: image.generationAllowed, video: video.generationAllowed, reasonCodes: unique([...image.readinessReasons, ...video.readinessReasons]) },
    primaryAction,
    professional: {
      authoritySource: 'current_authority_pointers_only',
      backendNextAction: shot.next_action,
      rawBlockers: shot.blockers,
      assetReadiness: shot.asset_readiness,
      legacy: shot.legacy,
    },
  }
}

export function toShotStudioViewModels(shots: ProductionShotV2[]): ShotStudioViewModel[] {
  return (Array.isArray(shots) ? shots : []).map(toShotStudioViewModel)
}
