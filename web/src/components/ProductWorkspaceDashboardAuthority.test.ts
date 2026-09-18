import { describe, expect, it } from 'vitest'
import { resolveProductionDashboardAction } from './ProductWorkspaceDashboardSection'

const legacy = { title: '旧的生成分镜建议', description: 'legacy', targetSection: 'storyboard', priority: 'high' } as any
const base = {
  schema_version: 'production_workspace_projection_v1',
  book_id: 1,
  workflow_profile: 'production',
  read_only: true,
  authority_source: 'current_authority_pointers_only',
  provider_calls: 0,
  project: { title: 'fixture', overall_state: 'blocked', overall_progress: 10, current_blockers: [], next_actions: [] },
  stages: {}, episodes: [], shots: [], assets: [],
} as any

describe('production dashboard authority closure', () => {
  it('does not fall back to legacy next action when authority has no action', () => {
    const result = resolveProductionDashboardAction({ state: 'ready', snapshot: base, legacy })
    expect(result.action).toBeNull()
    expect(result.title).toBe('当前没有待处理的生产阻塞')
    expect(result.title).not.toContain('旧的生成分镜建议')
  })

  it('fails closed when projection is unavailable', () => {
    const result = resolveProductionDashboardAction({ state: 'unavailable', snapshot: null, legacy })
    expect(result.action).toBeNull()
    expect(result.title).toBe('生产状态暂不可用')
  })
})
