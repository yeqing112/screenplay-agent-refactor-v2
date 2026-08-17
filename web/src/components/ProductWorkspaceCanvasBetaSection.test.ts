import { describe, expect, it } from 'vitest'

import {
  buildCanvasShotRuntimeSummaryCard,
  buildCanvasNodePrimaryActionPlan,
  buildCanvasShotPrimaryActionPlan,
  buildNavigationContinueChainMeta,
  getCanvasExecutionSummaryLabel,
} from './ProductWorkspaceCanvasBetaSection'

describe('ProductWorkspaceCanvasBetaSection helpers', () => {
  it('builds recovery-specific continue chain metadata for frame and prompt follow-up actions', () => {
    expect(
      buildNavigationContinueChainMeta({
        action: 'generate_video',
        recoveryKind: 'frame',
      }),
    ).toEqual({
      generationChain: 'canvas_recovery_continue_after_frame',
    })

    expect(
      buildNavigationContinueChainMeta({
        action: 'generate_video',
        recoveryKind: 'prompt',
      }),
    ).toEqual({
      generationChain: 'canvas_recovery_continue_after_prompt',
    })

    expect(
      buildNavigationContinueChainMeta({
        action: 'generate_frame',
        recoveryKind: 'prompt',
      }),
    ).toEqual({
      generationChain: 'canvas_recovery_continue_after_prompt',
    })
  })

  it('builds recovery-specific recompile chain metadata for reference follow-up actions', () => {
    expect(
      buildNavigationContinueChainMeta({
        action: 'recompile_then_video',
        recoveryKind: 'reference',
      }),
    ).toEqual({
      generationChain: 'canvas_recovery_recompile_then_video',
      compileReason: 'canvas-recovery-reference-before-video',
    })

    expect(
      buildNavigationContinueChainMeta({
        action: 'recompile_then_frame',
        recoveryKind: 'reference',
      }),
    ).toEqual({
      generationChain: 'canvas_recovery_recompile_then_frame',
      compileReason: 'canvas-recovery-reference-before-frame',
    })
  })

  it('maps recovery-specific generation chains to readable execution summary labels', () => {
    expect(getCanvasExecutionSummaryLabel('video', 'canvas_recovery_continue_after_frame')).toBe('恢复后继续生成视频')
    expect(getCanvasExecutionSummaryLabel('video', 'canvas_recovery_continue_after_prompt')).toBe('恢复后继续生成视频')
    expect(getCanvasExecutionSummaryLabel('video', 'canvas_recovery_recompile_then_video')).toBe('重编后继续生成视频')
    expect(getCanvasExecutionSummaryLabel('frame', 'canvas_recovery_continue_after_prompt')).toBe('恢复后继续生成首帧')
    expect(getCanvasExecutionSummaryLabel('frame', 'canvas_recovery_recompile_then_frame')).toBe('重编后生成首帧')
  })
  it('builds a primary creation action for ordinary shot states before and after recovery', () => {
    expect(
      buildCanvasShotPrimaryActionPlan({
        hasCompiledPrompt: false,
        hasAdoptedFrame: false,
        hasAdoptedVideo: false,
      }),
    ).toMatchObject({
      action: 'compile_prompts',
    })

    expect(
      buildCanvasShotPrimaryActionPlan({
        hasCompiledPrompt: true,
        hasAdoptedFrame: false,
        hasAdoptedVideo: false,
      }),
    ).toMatchObject({
      action: 'generate_frame',
    })

    expect(
      buildCanvasShotPrimaryActionPlan({
        hasCompiledPrompt: true,
        hasAdoptedFrame: true,
        hasAdoptedVideo: false,
      }),
    ).toMatchObject({
      action: 'generate_video',
    })

    expect(
      buildCanvasShotPrimaryActionPlan({
        hasCompiledPrompt: true,
        hasAdoptedFrame: true,
        hasAdoptedVideo: true,
      }),
    ).toMatchObject({
      action: 'open_storyboard',
    })
  })

  it('prioritizes task recovery over new generation when pending tasks still exist', () => {
    expect(
      buildCanvasShotPrimaryActionPlan({
        promptRecoveryTaskId: 'task-prompt-1',
        hasCompiledPrompt: true,
        hasAdoptedFrame: false,
        hasAdoptedVideo: false,
      }),
    ).toMatchObject({
      action: 'tasks_prompt',
    })

    expect(
      buildCanvasShotPrimaryActionPlan({
        frameRecoveryTaskId: 'task-frame-1',
        hasCompiledPrompt: true,
        hasAdoptedFrame: false,
        hasAdoptedVideo: false,
      }),
    ).toMatchObject({
      action: 'tasks_frame',
    })

    expect(
      buildCanvasShotPrimaryActionPlan({
        videoRecoveryTaskId: 'task-video-1',
        hasCompiledPrompt: true,
        hasAdoptedFrame: true,
        hasAdoptedVideo: false,
      }),
    ).toMatchObject({
      action: 'tasks_video',
    })
  })

  it('builds a readable runtime summary card for canvas shot execution state', () => {
    expect(
      buildCanvasShotRuntimeSummaryCard({
        latestExecutionLabel: '已提交视频生成 v3',
        pendingTaskSummary: {
          count: 2,
          joinedKindLabels: '视频 / 提示词编译',
          latestTaskId: 'canvas-video-001',
          latestSourceLabel: '视频',
        },
      }),
    ).toEqual({
      latestExecutionLabel: '已提交视频生成 v3',
      pendingTaskLabel: '视频 / 提示词编译',
      suggestedActionLabel: '先回收任务',
      latestSourceLine: '最近待回收来源：视频 · 任务 ID：canvas-video-001',
    })

    expect(
      buildCanvasShotRuntimeSummaryCard({
        latestExecutionLabel: null,
        pendingTaskSummary: {
          count: 0,
          joinedKindLabels: '无',
          latestTaskId: null,
          latestSourceLabel: null,
        },
      }),
    ).toEqual({
      latestExecutionLabel: '未记录',
      pendingTaskLabel: '无',
      suggestedActionLabel: '可继续执行',
      latestSourceLine: null,
    })
  })

  it('builds node-level primary actions for asset, qa, and delivery nodes', () => {
    expect(
      buildCanvasNodePrimaryActionPlan({
        id: 'asset-1',
        kind: 'character',
        title: '和尚甲',
        subtitle: '人物资产',
        meta: [],
        x: 0,
        y: 0,
        missingReference: true,
        hasBlocker: true,
        hasOutput: false,
        route: { section: 'assets' },
      } as any),
    ).toMatchObject({
      label: '前往资产中心补齐参考图',
    })

    expect(
      buildCanvasNodePrimaryActionPlan({
        id: 'asset-2',
        kind: 'character',
        title: '和尚乙',
        subtitle: '人物资产',
        meta: [],
        x: 0,
        y: 0,
        missingReference: true,
        hasBlocker: true,
        hasOutput: false,
        route: { section: 'assets', options: { shotId: '8' } },
      } as any),
    ).toMatchObject({
      label: '前往资产中心补齐该镜头参考图',
    })

    expect(
      buildCanvasNodePrimaryActionPlan({
        id: 'qa-1',
        kind: 'qa',
        title: '第 1 集 QA',
        subtitle: '质检',
        meta: [],
        x: 0,
        y: 0,
        missingReference: false,
        hasBlocker: true,
        hasOutput: false,
        route: { section: 'qa' },
      } as any),
    ).toMatchObject({
      label: '前往 QA 修复处理问题',
    })

    expect(
      buildCanvasNodePrimaryActionPlan({
        id: 'delivery-1',
        kind: 'delivery',
        title: '交付',
        subtitle: '导出',
        meta: [],
        x: 0,
        y: 0,
        missingReference: false,
        hasBlocker: false,
        hasOutput: true,
        route: { section: 'delivery' },
      } as any),
    ).toMatchObject({
      label: '前往导出中心确认可交付状态',
    })
  })
})
