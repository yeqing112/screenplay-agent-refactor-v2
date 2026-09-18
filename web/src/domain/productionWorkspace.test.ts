import { describe, expect, it } from 'vitest'
import {
  humanizeProductionState,
  isKnownProductionState,
  normalizeProductionWorkspaceSnapshot,
  validateProductionWorkspaceSnapshot,
} from './productionWorkspace'

describe('production workspace domain contract', () => {
  it('maps engineering states to creator-facing labels', () => {
    expect(humanizeProductionState('PRODUCTION_QUALIFIED')).toBe('已确认')
    expect(humanizeProductionState('FRESH')).toBe('当前有效')
    expect(humanizeProductionState('AUTHORING_PENDING')).toBe('待完成视觉设计')
    expect(humanizeProductionState('ASSET_REFERENCE_PENDING')).toBe('待补参考图')
    expect(humanizeProductionState('stale')).toBe('需要更新')
    expect(humanizeProductionState('blocked')).toBe('暂不能继续')
  })

  it('normalizes an empty or malformed transport response safely', () => {
    const snapshot = normalizeProductionWorkspaceSnapshot(null, 12)
    expect(snapshot.book_id).toBe(12)
    expect(snapshot.read_only).toBe(true)
    expect(snapshot.authority_source).toBe('current_authority_pointers_only')
    expect(snapshot.project.current_blockers).toEqual([])
  })

  it('preserves projection stages and blockers without translating raw status into readiness', () => {
    const snapshot = normalizeProductionWorkspaceSnapshot({
      book_id: 12,
      project: {
        overall_state: 'stale',
        overall_progress: 40,
        current_blockers: [{ code: 'PROMPT_IR_STALE', target_section: 'storyboard' }],
      },
      stages: { PROMPT_IR: { key: 'PROMPT_IR', state: 'stale', reason_codes: ['PROMPT_IR_STALE'] } },
    }, 12)
    expect(snapshot.project.overall_state).toBe('stale')
    expect(snapshot.project.current_blockers[0].code).toBe('PROMPT_IR_STALE')
    expect(snapshot.stages.PROMPT_IR.state).toBe('stale')
  })

  it('fails closed for malformed or non-production projections', () => {
    expect(validateProductionWorkspaceSnapshot(null)).toContain('投影响应不是对象')
    expect(validateProductionWorkspaceSnapshot({ workflow_profile: 'creative_draft' })).toContain('workflow_profile 不是 production')
    expect(validateProductionWorkspaceSnapshot({
      schema_version: 'production_workspace_projection_v1',
      workflow_profile: 'production',
      read_only: true,
      authority_source: 'current_authority_pointers_only',
      provider_calls: 1,
      project: {}, stages: {}, episodes: [], shots: [], assets: [],
    })).toContain('provider_calls 必须为 0')
  })

  it('does not treat unknown authority states as production-ready', () => {
    expect(isKnownProductionState('future_state')).toBe(false)
    expect(humanizeProductionState('future_state')).toBe('待确认')
  })
})
