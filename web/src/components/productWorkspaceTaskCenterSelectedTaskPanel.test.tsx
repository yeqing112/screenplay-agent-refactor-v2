import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import TaskCenterSelectedTaskPanel, {
  buildTaskCenterPrimaryActionPlan,
} from './productWorkspaceTaskCenterSelectedTaskPanel'
import type { TaskCenterEntry } from './productWorkspaceTasks'

function makeTask(overrides: Partial<TaskCenterEntry> = {}): TaskCenterEntry {
  return {
    id: 'task-recovery-video',
    type: '视频结果回收',
    target: '第 1 集 / 镜头 8',
    status: 'error',
    progress: '待修复',
    detail: '任务失败，需要继续恢复。',
    retryable: true,
    actionLabel: '前往分镜工作台',
    actionTarget: 'storyboard',
    episode: 1,
    taskId: 'task-123',
    shotId: '8',
    assetId: 'character-8',
    recoveryKind: 'video',
    creativeTaskMeta: {
      assetSubject: '和尚',
      generationChain: 'canvas_recovery_continue_after_frame',
    },
    ...overrides,
  }
}

describe('productWorkspaceTaskCenterSelectedTaskPanel', () => {
  it('builds regenerate-latest as the primary action for failed frame or video recovery tasks', () => {
    const plan = buildTaskCenterPrimaryActionPlan({
      selectedTask: makeTask({ status: 'error', recoveryKind: 'video' }),
      actionState: { mode: 'idle', action: null, message: '' },
      canNavigateToCanvas: true,
      canRegenerateLatest: true,
    })

    expect(plan).toMatchObject({
      action: 'recovery_regenerate_latest',
    })
  })

  it('builds reconcile as the primary action for running recovery tasks', () => {
    const plan = buildTaskCenterPrimaryActionPlan({
      selectedTask: makeTask({ status: 'running', recoveryKind: 'video' }),
      actionState: { mode: 'idle', action: null, message: '' },
      canNavigateToCanvas: true,
      canRegenerateLatest: true,
    })

    expect(plan).toMatchObject({
      action: 'recovery_reconcile',
    })
  })

  it('builds canvas navigation as the primary action after a successful recovery action', () => {
    const plan = buildTaskCenterPrimaryActionPlan({
      selectedTask: makeTask({ status: 'done', progress: '100%' }),
      actionState: { mode: 'success', action: 'recovery-reconcile', message: 'done' },
      canNavigateToCanvas: true,
      canRegenerateLatest: true,
    })

    expect(plan).toMatchObject({
      action: 'navigate_canvas',
    })
  })

  it('renders a primary handoff action card for selected recovery tasks', () => {
    const markup = renderToStaticMarkup(
      <TaskCenterSelectedTaskPanel
        bookId={14}
        selectedTask={makeTask()}
        selectedTaskActionState={{ mode: 'idle', action: null, message: '' }}
        selectedTaskEpisode={1}
        selectedTaskShotId="8"
        selectedTaskAssetId="character-8"
        latestSelectedBatchRunRecord={null}
        selectedBatchRunRecords={[]}
        batchPromptCompileCount={0}
        batchMissingFrameCount={0}
        batchMissingVideoCount={0}
        batchOpenQaEpisodeCount={0}
        onNavigate={() => {}}
        onOpenPreview={() => {}}
        onRunBatchTaskAction={() => {}}
        onRunRecoveryTaskAction={() => {}}
        onRunQaTaskAction={() => {}}
      />,
    )

    expect(markup).toContain('承接后的首个动作')
    expect(markup).toContain('立即继续')
  })
})
