export type ProductionStageState =
  | 'not_started'
  | 'in_progress'
  | 'ready'
  | 'blocked'
  | 'needs_action'
  | 'stale'
  | 'complete'
  | 'warning'

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
