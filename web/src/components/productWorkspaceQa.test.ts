import { describe, expect, it } from 'vitest'
import {
  buildQaIssueFromWorkbenchIssue,
  buildQaIssueRecords,
  buildQaSummaryStats,
  matchesQaLifecycleFilter,
  pickQaNavigationIssue,
  qaLifecycleLabel,
  sortQaIssues,
} from './productWorkspaceQa'

describe('productWorkspaceQa', () => {
  it('flattens structured QA issues into actionable repair records', () => {
    const issues = buildQaIssueRecords(
      [
        {
          episode: 1,
          result: {
            high_errors: [
              {
                shot_id: '1-03',
                description: '镜头里的服装与已确认定妆不一致',
              },
            ],
            medium_errors: [
              {
                shot_id: '1-04',
                description: '运动提示词没有明确镜头推进节奏',
              },
            ],
            suggestions: ['第一句独白可以再自然一点。'],
          },
        },
      ],
      {
        1: [
          { shot_id: '1-03', scene_name: '天台', prompt_version: 3 },
          { shot_id: '1-04', scene_name: '客厅', prompt_version: 2 },
        ] as any,
      },
    )

    expect(issues).toHaveLength(3)
    expect(issues[0]).toMatchObject({
      layer: 'asset',
      shotId: '1-03',
      promptVersion: 3,
      severity: 'high',
    })
    expect(issues[0]?.recommendedActions.some((item) => item.target === 'assets')).toBe(true)
    expect(issues[1]).toMatchObject({
      layer: 'video',
      shotId: '1-04',
      promptVersion: 2,
    })
    expect(issues[2]).toMatchObject({
      layer: 'script',
      source: 'suggestion',
      severity: 'low',
    })
  })

  it('builds summary counts by layer and unresolved status', () => {
    const stats = buildQaSummaryStats(
      [
        {
          id: 'a',
          episode: 1,
          layer: 'script',
          severity: 'low',
          title: 't1',
          detail: 'd1',
          shotId: null,
          promptVersion: null,
          assetLabel: null,
          source: 'suggestion',
          recommendedActions: [],
        },
        {
          id: 'b',
          episode: 1,
          layer: 'storyboard',
          severity: 'high',
          title: 't2',
          detail: 'd2',
          shotId: '1-01',
          promptVersion: 1,
          assetLabel: null,
          source: 'error',
          recommendedActions: [],
        },
      ],
      {
        a: 'resolved',
        b: 'open',
      },
    )

    expect(stats.total).toBe(2)
    expect(stats.open).toBe(1)
    expect(stats.inProgress).toBe(0)
    expect(stats.resolved).toBe(1)
    expect(stats.wontFix).toBe(0)
    expect(stats.byLayer.script).toBe(1)
    expect(stats.byLayer.storyboard).toBe(1)
    expect(stats.bySeverity.high).toBe(1)
    expect(stats.bySeverity.low).toBe(1)
  })

  it('prefers persisted workflow and repair fields from the QA workbench payload', () => {
    const issue = buildQaIssueFromWorkbenchIssue(
      {
        issue_id: 'qa-1',
        episode: 1,
        severity: 'medium',
        type: 'logic_gap',
        title: 'issue-title',
        description: 'issue-description',
        rule_family: 'character_state_transition',
        repair_goal: '补足状态切换的触发器与递进动作',
        workflow_status: 'wont_fix',
        repair_version: 'script v3',
        note: 'kept for historical comparison',
        fix_status: 'recheck_failed',
        location: {},
        meta_info: {},
      },
      { 1: [] as any },
    )

    expect(issue.workflowStatus).toBe('wont_fix')
    expect(issue.rawFixStatus).toBe('recheck_failed')
    expect(issue.repairVersion).toBe('script v3')
    expect(issue.note).toBe('kept for historical comparison')
    expect(issue.ruleFamily).toBe('character_state_transition')
    expect(issue.repairGoal).toBe('补足状态切换的触发器与递进动作')
  })

  it('exposes lifecycle labels and lifecycle filtering for workbench issues', () => {
    const issue = buildQaIssueFromWorkbenchIssue(
      {
        issue_id: 'qa-2',
        episode: 1,
        severity: 'high',
        type: 'logic_gap',
        title: 'issue-title',
        description: 'issue-description',
        fix_status: 'rechecking',
        location: {},
        meta_info: {},
      },
      { 1: [] as any },
    )

    expect(qaLifecycleLabel('rechecking')).toBe('复检中')
    expect(matchesQaLifecycleFilter(issue, 'rechecking')).toBe(true)
    expect(matchesQaLifecycleFilter(issue, 'recheck_failed')).toBe(false)
  })

  it('sorts QA issues by unresolved priority before severity and freshness', () => {
    const issues = [
      {
        id: 'resolved-high',
        episode: 1,
        layer: 'script',
        severity: 'high',
        title: 'resolved',
        detail: 'resolved detail',
        shotId: null,
        promptVersion: null,
        assetLabel: null,
        source: 'error',
        workflowStatus: 'resolved',
        rawFixStatus: 'recheck_passed',
        updatedAt: '2026-07-17T09:00:00.000Z',
        recommendedActions: [],
      },
      {
        id: 'open-medium',
        episode: 1,
        layer: 'storyboard',
        severity: 'medium',
        title: 'open',
        detail: 'open detail',
        shotId: '1-01',
        promptVersion: 2,
        assetLabel: null,
        source: 'error',
        workflowStatus: 'open',
        rawFixStatus: 'pending',
        updatedAt: '2026-07-17T08:00:00.000Z',
        recommendedActions: [],
      },
      {
        id: 'in-progress-high',
        episode: 1,
        layer: 'asset',
        severity: 'high',
        title: 'progress',
        detail: 'progress detail',
        shotId: '1-02',
        promptVersion: 3,
        assetLabel: '和尚甲',
        source: 'error',
        workflowStatus: 'in_progress',
        rawFixStatus: 'rechecking',
        updatedAt: '2026-07-17T10:00:00.000Z',
        recommendedActions: [],
      },
    ] as any

    const sorted = sortQaIssues(issues, {}, 'status_priority')
    expect(sorted.map((item) => item.id)).toEqual(['open-medium', 'in-progress-high', 'resolved-high'])
  })

  it('prefers actionable workbench issues when navigating from another workspace section', () => {
    const issues = [
      {
        id: 'resolved-script',
        episode: 1,
        layer: 'script',
        severity: 'high',
        title: 'resolved',
        detail: 'resolved detail',
        shotId: null,
        promptVersion: null,
        assetLabel: null,
        source: 'error',
        sourceKind: 'workbench',
        workflowStatus: 'resolved',
        rawFixStatus: 'recheck_passed',
        updatedAt: '2026-07-17T09:00:00.000Z',
        recommendedActions: [],
      },
      {
        id: 'open-storyboard',
        episode: 1,
        layer: 'storyboard',
        severity: 'medium',
        title: 'open',
        detail: 'open detail',
        shotId: '3',
        promptVersion: 2,
        assetLabel: null,
        source: 'error',
        sourceKind: 'workbench',
        workflowStatus: 'open',
        rawFixStatus: 'pending',
        updatedAt: '2026-07-17T08:00:00.000Z',
        recommendedActions: [],
      },
      {
        id: 'derived-shot',
        episode: 1,
        layer: 'asset',
        severity: 'high',
        title: 'derived',
        detail: 'derived detail',
        shotId: '3',
        promptVersion: 3,
        assetLabel: null,
        source: 'error',
        sourceKind: 'derived',
        workflowStatus: 'open',
        rawFixStatus: null,
        updatedAt: '2026-07-17T10:00:00.000Z',
        recommendedActions: [],
      },
    ] as any

    const picked = pickQaNavigationIssue(issues, {}, { episode: 1, shotId: '3' })
    expect(picked?.id).toBe('open-storyboard')
  })

  it('prefers downstream delivery-recovery issues over generic script workbench issues', () => {
    const issues = [
      {
        id: 'open-script-workbench',
        episode: 1,
        layer: 'script',
        severity: 'high',
        title: 'script open',
        detail: 'script detail',
        shotId: null,
        promptVersion: null,
        assetLabel: null,
        source: 'error',
        sourceKind: 'workbench',
        workflowStatus: 'open',
        rawFixStatus: 'pending',
        updatedAt: '2026-07-17T09:00:00.000Z',
        recommendedActions: [],
      },
      {
        id: 'derived-storyboard-shot',
        episode: 1,
        layer: 'storyboard',
        severity: 'medium',
        title: 'storyboard open',
        detail: 'storyboard detail',
        shotId: '3',
        promptVersion: 2,
        assetLabel: null,
        source: 'error',
        sourceKind: 'derived',
        workflowStatus: 'open',
        rawFixStatus: null,
        updatedAt: '2026-07-17T08:00:00.000Z',
        recommendedActions: [],
      },
    ] as any

    const picked = pickQaNavigationIssue(issues, {}, { episode: 1, shotId: null, qaFocus: 'delivery_recovery' })
    expect(picked?.id).toBe('derived-storyboard-shot')
  })
})
