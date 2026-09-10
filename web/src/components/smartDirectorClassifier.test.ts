import { describe, expect, it } from 'vitest'
import {
  TIER_LABEL,
  TIER_OPERATIONS,
  TIER_TONE,
  classifyOperation,
} from './smartDirectorClassifier'
import {
  summariseContextForAgent,
  type DirectorContext,
} from '../services/agent'

describe('smartDirectorClassifier', () => {
  it('classifies read-only operations as tier A', () => {
    expect(classifyOperation('diagnose')).toBe('A')
    expect(classifyOperation('continuity_check')).toBe('A')
  })

  it('classifies draft operations as tier B', () => {
    expect(classifyOperation('draft_prompt')).toBe('B')
    expect(classifyOperation('draft_repair')).toBe('B')
  })

  it('classifies versioned writes as tier C', () => {
    expect(classifyOperation('write_prompt_version')).toBe('C')
  })

  it('defaults unknown operations to tier D (external cost)', () => {
    expect(classifyOperation('image_generation')).toBe('D')
    expect(classifyOperation('video_generation')).toBe('D')
    expect(classifyOperation('totally_unknown_op')).toBe('D')
    expect(classifyOperation('')).toBe('D')
  })

  it('keeps a label, a tone and a fixed set of exposed operations', () => {
    expect(Object.keys(TIER_LABEL).sort()).toEqual(['A', 'B', 'C', 'D'])
    expect(Object.keys(TIER_TONE).sort()).toEqual(['A', 'B', 'C', 'D'])
    expect(TIER_OPERATIONS).toContain('diagnose')
    expect(TIER_OPERATIONS).toContain('video_generation')
  })
})

describe('summariseContextForAgent', () => {
  it('falls back to a placeholder when nothing is selected', () => {
    expect(summariseContextForAgent(null)).toContain('未选择')
  })

  it('composes book, section, shot and asset into a short label', () => {
    const ctx: DirectorContext = {
      book_id: 75,
      book_title: '便利店收银台',
      section: '镜头工作台',
      shot_id: 3,
    }
    const label = summariseContextForAgent(ctx)
    expect(label).toContain('便利店收银台')
    expect(label).toContain('镜头工作台')
    expect(label).toContain('镜头 3')
  })

  it('omits sections it does not have', () => {
    const ctx: DirectorContext = { book_id: 1 }
    const label = summariseContextForAgent(ctx)
    expect(label).toContain('项目 #1')
    expect(label).not.toContain('镜头')
  })
})