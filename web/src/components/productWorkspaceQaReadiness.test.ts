import { describe, expect, it } from 'vitest'
import { buildQaReleaseGateSummary } from './productWorkspaceQaReadiness'

describe('productWorkspaceQaReadiness', () => {
  it('reports unlocked and unreleased script episodes separately', () => {
    const summary = buildQaReleaseGateSummary(
      [
        { episode: 1, content: 'script-1' },
        { episode: 2, content: 'script-2' },
        { episode: 3, content: 'script-3' },
      ] as any,
      {
        '1': { lockedAt: null, releasedAt: null, note: '' },
        '2': { lockedAt: '2026-07-06T10:00:00.000Z', releasedAt: null, note: '' },
        '3': { lockedAt: '2026-07-06T10:00:00.000Z', releasedAt: '2026-07-06T10:05:00.000Z', note: '' },
      },
      true,
    )

    expect(summary).toMatchObject({
      totalScriptEpisodes: 3,
      unlockedEpisodes: [1],
      unreleasedEpisodes: [2],
      blockedEpisodes: [1, 2],
      isBlocked: true,
      summaryLabel: '上游未放行 2 集',
    })
    expect(summary.detail).toContain('待锁稿：第 1 集')
    expect(summary.detail).toContain('待放行：第 2 集')
  })

  it('marks the gate clean when all scripts are locked and released', () => {
    const summary = buildQaReleaseGateSummary(
      [{ episode: 8, content: 'script-8' }] as any,
      {
        '8': {
          lockedAt: '2026-07-06T10:00:00.000Z',
          releasedAt: '2026-07-06T10:05:00.000Z',
          note: '',
        },
      },
      true,
    )

    expect(summary.isBlocked).toBe(false)
    expect(summary.summaryLabel).toBe('剧本闸门已通过')
  })

  it('keeps QA blocked when adaptation is not explicitly locked', () => {
    const summary = buildQaReleaseGateSummary(
      [{ episode: 8, content: 'script-8' }] as any,
      {
        '8': {
          lockedAt: '2026-07-06T10:00:00.000Z',
          releasedAt: '2026-07-06T10:05:00.000Z',
          note: '',
        },
      },
      false,
    )

    expect(summary.isBlocked).toBe(true)
    expect(summary.summaryLabel).toBe('上游未放行 1 集')
    expect(summary.detail).toContain('项目改编方向尚未正式锁定')
  })
})
