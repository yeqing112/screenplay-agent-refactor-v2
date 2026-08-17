import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import ProductWorkspaceQaSection, {
  buildFollowupOutcomeMessage,
  buildQaCanvasHandoffSummary,
  buildQaCanvasPrimaryActionPlan,
  countEpisodePendingIssues,
  findRawWorkbenchIssue,
} from './ProductWorkspaceQaSection'

describe('ProductWorkspaceQaSection', () => {
  it('counts pending workbench issues by episode and finds the target issue', () => {
    const payload = {
      episodes: [
        {
          episode: 1,
          issues: [
            { issue_id: 'issue-1', fix_status: 'rechecking' },
            { issue_id: 'issue-2', fix_status: 'recheck_passed' },
          ],
        },
        {
          episode: 2,
          issues: [{ issue_id: 'issue-3', fix_status: 'pending' }],
        },
      ],
    }

    expect(findRawWorkbenchIssue(payload as any, 'issue-3')?.issue_id).toBe('issue-3')
    expect(countEpisodePendingIssues(payload as any, 1)).toBe(1)
    expect(countEpisodePendingIssues(payload as any, 2)).toBe(1)
  })

  it('builds follow-up outcome messages for QA rechecks', () => {
    expect(
      buildFollowupOutcomeMessage('autofix', { issue_id: 'issue-1', fix_status: 'recheck_passed' } as any, 0),
    ).toEqual({
      mode: 'success',
      message: '自动修复已完成，QA 复检通过。',
    })

    expect(
      buildFollowupOutcomeMessage('autofix', { issue_id: 'issue-2', fix_status: 'recheck_failed' } as any, 1),
    ).toEqual({
      mode: 'error',
      message: '自动修复已完成，但 QA 复检未通过，请继续处理。',
    })

    expect(buildFollowupOutcomeMessage('recheck', null, 2)).toEqual({
      mode: 'error',
      message: '该集 QA 复检已完成，当前仍有 2 个问题待处理。',
    })
  })

  it('builds a readable canvas handoff summary for QA continuation', () => {
    expect(
      buildQaCanvasHandoffSummary({
        handoff: {
          target: 'qa',
          episode: 1,
          shotId: '4',
          assetLabel: '小和尚',
          handoffDetail: '继续处理这个镜头对应的 QA 问题。',
        },
        issue: {
          title: '人物表情与镜头动作不一致',
          episode: 1,
          shotId: '4',
          assetLabel: '小和尚',
        },
      }),
    ).toEqual({
      title: '已从创作画布定位到 第 1 集 / 镜头 4 / 小和尚',
      issueTitle: '人物表情与镜头动作不一致',
      detail: '继续处理这个镜头对应的 QA 问题。',
    })
  })

  it('builds a first executable action for canvas-driven QA repair', () => {
    expect(
      buildQaCanvasPrimaryActionPlan({
        hasReleaseGateBlock: true,
        issue: {
          sourceKind: 'derived',
          workflowStatus: 'open',
          rawFixStatus: null,
          recommendedActions: [
            {
              label: '进入镜头工作台',
              reason: '先检查镜头提示词。',
              target: 'storyboard',
            },
          ],
        },
      }),
    ).toEqual({
      action: 'scripts_gate',
      label: '返回剧本工作台补放行',
      detail: '当前 QA 仍被上游剧本放行状态拦住，先补齐锁稿与放行，再继续本条问题的修复闭环。',
    })

    expect(
      buildQaCanvasPrimaryActionPlan({
        hasReleaseGateBlock: false,
        issue: {
          sourceKind: 'workbench',
          workflowStatus: 'open',
          rawFixStatus: 'pending',
          recommendedActions: [],
        },
        actionState: {
          action: null,
          options: [],
          diffText: '',
        },
      }),
    ).toEqual({
      action: 'generate_fix',
      label: '生成修复方案',
      detail: '先为这条真实 QA 工单生成修复方案，收敛处理方向后再执行自动修复或人工回改。',
    })

    expect(
      buildQaCanvasPrimaryActionPlan({
        hasReleaseGateBlock: false,
        issue: {
          sourceKind: 'workbench',
          workflowStatus: 'in_progress',
          rawFixStatus: 'pending',
          recommendedActions: [],
        },
        actionState: {
          action: 'generate',
          options: [{ id: 'fix-1', summary: '修复建议' }],
          diffText: '',
        },
      }),
    ).toEqual({
      action: 'autofix',
      label: '自动修复',
      detail: '修复方案已经回流到当前问题，下一步可以直接执行自动修复并等待 QA 复检。',
    })
  })

  it('renders the canvas handoff card with a first action inside the selected issue panel', () => {
    const html = renderToStaticMarkup(
      <ProductWorkspaceQaSection
        bookId={14}
        scripts={[]}
        scriptDecisionState={{}}
        hasExplicitLockedAdaptation
        qaEntries={[
          {
            id: 1,
            episode: 1,
            error_count: 1,
            result: {
              issues: [
                {
                  issue_id: 'issue-1',
                  severity: 'high',
                  type: 'storyboard',
                  title: '人物表情与镜头动作不一致',
                  description: '当前镜头的情绪动作没有对齐。',
                  workflow_status: 'open',
                  location: { shot_id: '4' },
                  meta_info: { asset_label: '小和尚' },
                },
              ],
            },
          },
        ] as any}
        shotsByEpisode={{ 1: [{ shot_id: '4', episode: 1 }] as any }}
        qaNavigationTarget={{ episode: 1, shotId: '4' }}
        canvasHandoff={{
          target: 'qa',
          episode: 1,
          shotId: '4',
          assetLabel: '小和尚',
          handoffDetail: '继续处理这个镜头对应的 QA 问题。',
        }}
        onNavigate={() => {}}
        onSelectShot={() => {}}
      />,
    )

    expect(html).toContain('承接后的首个动作')
    expect(html).toContain('立即继续')
  })
})
