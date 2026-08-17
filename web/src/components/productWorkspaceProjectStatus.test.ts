import { describe, expect, it } from 'vitest'
import { getProjectStatusLabel, isKnownProjectStatus } from './productWorkspaceProjectStatus'

describe('productWorkspaceProjectStatus', () => {
  it('maps legacy and refactor statuses to readable labels', () => {
    expect(getProjectStatusLabel('imported')).toBe('已导入原文')
    expect(getProjectStatusLabel('portraited')).toBe('已完成人物设定')
    expect(getProjectStatusLabel('prepared')).toBe('内容已就绪')
    expect(getProjectStatusLabel('content_ready')).toBe('内容已就绪')
  })

  it('falls back for unknown statuses and detects known ones', () => {
    expect(getProjectStatusLabel('mystery-status')).toBe('状态待确认')
    expect(isKnownProjectStatus('storyboarded')).toBe(true)
    expect(isKnownProjectStatus('')).toBe(false)
  })
})
