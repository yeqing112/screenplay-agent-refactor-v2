import { describe, expect, it } from 'vitest'
import {
  buildDashboardActions,
  buildEpisodeProgress,
  buildProjectStageProjection,
  buildScriptWorkbenchChecklist,
} from './productWorkspaceProgress'

describe('productWorkspaceProgress', () => {
  it('guides users to content preparation first', () => {
    const actions = buildDashboardActions({
      contentReady: false,
      adaptationLocked: false,
      episodesWithScripts: 0,
      scriptReleasePendingCount: 0,
      totalShots: 0,
      visualCount: 0,
      qaCount: 0,
    })

    expect(actions[0]?.targetSection).toBe('content')
    expect(actions[0]?.priority).toBe('high')
  })

  it('routes users back to scripts when release decisions are missing', () => {
    const actions = buildDashboardActions({
      contentReady: true,
      adaptationLocked: true,
      episodesWithScripts: 2,
      scriptReleasePendingCount: 1,
      totalShots: 0,
      visualCount: 0,
      qaCount: 0,
    })

    expect(actions[0]?.targetSection).toBe('scripts')
    expect(actions[0]?.priority).toBe('high')
  })

  it('prioritizes adaptation backfill before other downstream actions when the project direction is still unlocked', () => {
    const actions = buildDashboardActions({
      contentReady: true,
      adaptationLocked: false,
      episodesWithScripts: 2,
      scriptReleasePendingCount: 1,
      totalShots: 24,
      visualCount: 10,
      qaCount: 3,
    })

    expect(actions[0]).toMatchObject({
      targetSection: 'adaptation',
      priority: 'high',
    })
  })

  it('projects one shared current stage from the highest-priority project action', () => {
    const projection = buildProjectStageProjection({
      contentReady: true,
      adaptationLocked: false,
      episodesWithScripts: 1,
      scriptReleasePendingCount: 1,
      totalShots: 25,
      visualCount: 6,
      qaCount: 5,
    })

    expect(projection.currentStage).toBe('adaptation')
    expect(projection.primaryAction.targetSection).toBe('adaptation')
    expect(projection.stages.map((item) => [item.key, item.state])).toEqual([
      ['content', 'done'],
      ['adaptation', 'current'],
      ['scripts', 'pending'],
      ['assets', 'pending'],
      ['storyboard', 'pending'],
      ['qa', 'pending'],
      ['delivery', 'pending'],
    ])
  })

  it('builds episode progress from production artifacts', () => {
    const progress = buildEpisodeProgress([
      {
        episode: 2,
        hasLockedAdaptation: true,
        hasScript: true,
        scriptLocked: true,
        scriptReleased: false,
        shotCount: 0,
        imageCount: 0,
        videoCount: 0,
        qaCount: 0,
      },
      {
        episode: 1,
        hasLockedAdaptation: true,
        hasScript: true,
        scriptLocked: true,
        scriptReleased: true,
        shotCount: 8,
        imageCount: 8,
        videoCount: 8,
        qaCount: 0,
      },
    ])

    expect(progress[0]).toMatchObject({
      episode: 1,
      statusLabel: '可交付',
    })
    expect(progress[1]).toMatchObject({
      episode: 2,
      statusLabel: '待放行',
      nextAction: '回剧本工作台放行到分镜',
    })
  })

  it('shows adaptation blocker before downstream work', () => {
    const progress = buildEpisodeProgress([
      {
        episode: 1,
        hasLockedAdaptation: false,
        hasScript: false,
        scriptLocked: false,
        scriptReleased: false,
        shotCount: 0,
        imageCount: 0,
        videoCount: 0,
        qaCount: 0,
      },
    ])

    expect(progress[0]).toMatchObject({
      statusLabel: '缺改编方向',
      nextAction: '先锁定项目改编方向',
    })
  })

  it('computes script workbench checklist', () => {
    const checklist = buildScriptWorkbenchChecklist({
      hasLockedAdaptation: true,
      hasScript: true,
      qaCount: 1,
    })

    expect(checklist[0]?.status).toBe('done')
    expect(checklist[2]?.status).toBe('blocked')
    expect(checklist[3]?.status).toBe('pending')
  })
})
