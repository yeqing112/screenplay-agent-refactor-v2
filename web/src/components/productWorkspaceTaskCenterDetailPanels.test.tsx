import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import TaskCenterDetailPanels from './productWorkspaceTaskCenterDetailPanels'
import type { TaskCenterEntry } from './productWorkspaceTasks'

function makeTask(overrides: Partial<TaskCenterEntry> = {}): TaskCenterEntry {
  return {
    id: 'task-recovery-video',
    type: '视频结果回收',
    target: '第 1 集 · 1 · 寺庙后院水房',
    status: 'error',
    progress: '70%',
    detail: '任务失败',
    retryable: true,
    actionLabel: '前往镜头工作台',
    actionTarget: 'storyboard',
    episode: 1,
    taskId: 'task-123',
    shotId: '1',
    creativeTaskMeta: {
      taskPromptVersion: 12,
      currentShotPromptVersion: 15,
      firstFrameAssetId: 'image-001',
      referenceAssetIds: ['ref-a', 'ref-b'],
    },
    ...overrides,
  }
}

describe('productWorkspaceTaskCenterDetailPanels', () => {
  it('shows restart input summary for recovery tasks', () => {
    const markup = renderToStaticMarkup(
      <TaskCenterDetailPanels
        selectedTask={makeTask()}
        selectedTaskActionState={{ mode: 'idle', action: null, message: '' }}
        latestSelectedBatchRunRecord={null}
        selectedBatchRunRecords={[]}
        batchPromptCompileCount={0}
        batchMissingFrameCount={0}
        batchMissingVideoCount={0}
        batchOpenQaEpisodeCount={0}
        onRunBatchTaskAction={() => {}}
        onRunRecoveryTaskAction={() => {}}
        onRunQaTaskAction={() => {}}
      />,
    )

    expect(markup).toContain('重新发起说明')
    expect(markup).toContain('重发会沿用任务提交时的提示词版本 v12')
    expect(markup).toContain('不会自动切换到镜头当前版本 v15')
    expect(markup).toContain('继续使用首帧 image-001')
    expect(markup).toContain('继续挂载 2 张静态参考图')
  })
})
