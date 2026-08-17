import { describe, expect, it } from 'vitest'
import {
  buildAdaptationSetupSummary,
  buildContentPreparationSummary,
} from './productWorkspaceUpstream'

describe('productWorkspaceUpstream', () => {
  it('marks structured content as ready', () => {
    const summary = buildContentPreparationSummary({
      chapterCount: 12,
      wordCount: 86000,
      projectStatus: 'prepared',
      contentTaskStatus: 'done',
      hasDownstreamOutput: false,
    })

    expect(summary).toMatchObject({
      status: 'ready',
      label: '已完成',
      canProceedToAdaptation: true,
    })
  })

  it('marks legacy projects without structured content as backfill-needed but passable', () => {
    const summary = buildContentPreparationSummary({
      chapterCount: 0,
      wordCount: 0,
      projectStatus: 'scripted',
      contentTaskStatus: 'idle',
      hasDownstreamOutput: true,
    })

    expect(summary).toMatchObject({
      status: 'needs_cleanup',
      label: '待补整理',
      canProceedToAdaptation: true,
    })
  })

  it('blocks adaptation before content is ready', () => {
    const adaptation = buildAdaptationSetupSummary({
      content: buildContentPreparationSummary({
        chapterCount: 0,
        wordCount: 0,
        projectStatus: 'draft',
        contentTaskStatus: 'idle',
        hasDownstreamOutput: false,
      }),
      hasLockedAdaptation: false,
      selectedAdaptationName: null,
      hasSelectedAdaptation: false,
      hasDownstreamOutput: false,
    })

    expect(adaptation).toMatchObject({
      status: 'waiting_content',
      label: '等待内容准备',
      isReadyForDownstream: false,
    })
  })

  it('marks downstream legacy projects as backfill-needed adaptation', () => {
    const adaptation = buildAdaptationSetupSummary({
      content: buildContentPreparationSummary({
        chapterCount: 0,
        wordCount: 0,
        projectStatus: 'scripted',
        contentTaskStatus: 'idle',
        hasDownstreamOutput: true,
      }),
      hasLockedAdaptation: false,
      selectedAdaptationName: null,
      hasSelectedAdaptation: false,
      hasDownstreamOutput: true,
    })

    expect(adaptation).toMatchObject({
      status: 'backfill_needed',
      label: '待补锁定',
      isReadyForDownstream: true,
    })
  })
})
