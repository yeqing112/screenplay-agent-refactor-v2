import { describe, expect, it } from 'vitest'
import type { StoryboardShotOutput } from '../domain/bookOutputs'
import type { AssetSummary } from './productWorkspaceAssets'
import {
  buildCanvasRecoveryActionLabel,
  buildCanvasRecoveryContinueActionPlan,
  buildCanvasRecoveryActionPlan,
  buildCanvasRecoveryClosureStatus,
  buildCanvasNavigationSummary,
  buildCanvasNavigationTargetStatus,
  buildProductWorkspaceCanvasBetaGraph,
  resolveCanvasEpisodeSelection,
  resolveCanvasNavigationNodeId,
  shouldShowCanvasNavigationRefocusAction,
  shouldShowCanvasSyncingState,
} from './productWorkspaceCanvasBeta'
import { collapseCanvasGraphByKind } from './ProductWorkspaceCanvasBetaSection'

describe('buildProductWorkspaceCanvasBetaGraph', () => {
  it('builds graph nodes and edges from real workspace data', () => {
    const shotsByEpisode: Record<number, StoryboardShotOutput[]> = {
      1: [
        {
          episode: 1,
          shot_id: '1',
          scene_name: '寺庙厨房',
          dialogue: '师兄在偷懒',
          visual_prompt_static: '静态提示词',
          visual_prompt_motion: '运动提示词',
          assets: {
            images: [
              {
                id: 'image-1',
                kind: 'image',
                title: '镜头1图片',
                label: 'v1',
                uri: '/assets/shot-1.png',
                adopted: true,
              },
            ],
            videos: [
              {
                id: 'video-1',
                kind: 'video',
                title: '镜头1视频',
                label: 'v1',
                previewUrl: '/assets/shot-1-video.jpg',
                adopted: true,
              },
            ],
            audios: [],
          },
        },
      ],
    }

    const allAssets: AssetSummary[] = [
      {
        id: 'character-1',
        category: 'character',
        assetRecordId: 1,
        title: '阿宁',
        subtitle: '分镜精调',
        detailPrimary: '青年和尚',
        status: 'ready',
        prompt: '人物提示词',
        shotIds: ['1-1'],
        episodeIds: [1],
        referenceCount: 1,
        previewCount: 1,
        selectedReferenceCount: 1,
        lockedReferenceCount: 1,
        staleReferenceCount: 0,
        hasStaleReferencePrompt: false,
        references: [{ id: 1, asset_type: 'character', asset_id: '1', image_url: '/assets/aning-ref.png' }],
        variantLabel: '分镜精调',
        variantScope: 'shot_variant',
        variantStageName: '镜头 1',
      },
    ]

    const graph = buildProductWorkspaceCanvasBetaGraph({
      bookTitle: '三个和尚',
      scripts: [{ episode: 1, content: '第1集剧本' }],
      shotsByEpisode,
      allAssets,
      qaEntries: [{ episode: 1, result: null, error_count: 2 }],
    })

    expect(graph.summary.episodeCount).toBe(1)
    expect(graph.summary.shotCount).toBe(1)
    expect(graph.nodes.some((node) => node.kind === 'script')).toBe(true)
    expect(graph.nodes.some((node) => node.kind === 'character')).toBe(true)
    expect(graph.nodes.some((node) => node.kind === 'image')).toBe(true)
    expect(graph.nodes.some((node) => node.kind === 'video')).toBe(true)
    expect(graph.nodes.some((node) => node.kind === 'qa')).toBe(true)
    expect(graph.nodes.find((node) => node.kind === 'character')?.hasOutput).toBe(true)
    expect(graph.nodes.find((node) => node.kind === 'shot')?.hasOutput).toBe(true)
    expect(graph.nodes.find((node) => node.kind === 'qa')?.hasBlocker).toBe(true)
    expect(graph.edges.some((edge) => edge.source === 'canvas-script-episode-1' && edge.target === 'canvas-shot-1-1')).toBe(true)
    expect(graph.edges.some((edge) => edge.source === 'canvas-asset-character-1' && edge.target === 'canvas-shot-1-1')).toBe(true)
    expect(graph.nodes.find((node) => node.id === 'canvas-asset-character-1')?.route).toMatchObject({
      section: 'assets',
      options: {
        episode: 1,
        shotId: '1',
        assetId: 'character-1',
      },
    })
  })

  it('marks missing references and blockers for incomplete nodes', () => {
    const graph = buildProductWorkspaceCanvasBetaGraph({
      bookTitle: '三个和尚',
      scripts: [{ episode: 2, content: '' }],
      shotsByEpisode: {
        2: [
          {
            episode: 2,
            shot_id: '3',
            scene_name: '后院',
            used_assets: [{ asset_id: '88', asset_name: '木桶', asset_type: 'prop' }],
            visual_prompt_static: '',
            visual_prompt_motion: '',
            assets: { images: [], videos: [], audios: [] },
          },
        ],
      },
      allAssets: [
        {
          id: 'prop-88',
          category: 'prop',
          assetRecordId: 88,
          title: '木桶',
          subtitle: '分镜精调',
          detailPrimary: '旧木桶',
          status: 'draft',
          prompt: '木桶提示词',
          shotIds: ['2-3'],
          episodeIds: [2],
          referenceCount: 0,
          previewCount: 0,
          selectedReferenceCount: 0,
          lockedReferenceCount: 0,
          staleReferenceCount: 0,
          hasStaleReferencePrompt: false,
          references: [],
          variantLabel: '分镜精调',
          variantScope: 'shot_variant',
          variantStageName: '镜头 3',
        },
      ],
      qaEntries: [],
    })

    expect(graph.nodes.find((node) => node.kind === 'script')?.hasBlocker).toBe(true)
    expect(graph.nodes.find((node) => node.kind === 'prop')?.missingReference).toBe(true)
    expect(graph.nodes.find((node) => node.kind === 'shot')?.missingReference).toBe(true)
    expect(graph.nodes.find((node) => node.kind === 'shot')?.hasBlocker).toBe(true)
    expect(graph.nodes.find((node) => node.kind === 'delivery')?.hasBlocker).toBe(true)
  })

  it('infers asset shot context from linked shots even when the asset record itself has no saved shotIds', () => {
    const graph = buildProductWorkspaceCanvasBetaGraph({
      bookTitle: '三个和尚',
      scripts: [{ episode: 1, content: '第一集剧本' }],
      shotsByEpisode: {
        1: [
          {
            episode: 1,
            shot_id: '5',
            scene_name: '寺庙后院水房',
            visual_prompt_static: '',
            visual_prompt_motion: '',
            assets: { images: [], videos: [], audios: [] },
          },
        ],
      },
      allAssets: [
        {
          id: 'location-5',
          category: 'location',
          assetRecordId: 5,
          title: '寺庙后院水房',
          subtitle: '场景资产',
          detailPrimary: '水房',
          status: 'draft',
          prompt: '场景提示词',
          shotIds: [],
          episodeIds: [1],
          referenceCount: 0,
          previewCount: 0,
          selectedReferenceCount: 0,
          lockedReferenceCount: 0,
          staleReferenceCount: 0,
          hasStaleReferencePrompt: false,
          references: [],
          variantLabel: '场景版本',
          variantScope: 'location_variant',
          variantStageName: '默认',
        },
      ],
      qaEntries: [],
    })

    expect(graph.nodes.find((node) => node.id === 'canvas-asset-location-5')?.route).toMatchObject({
      section: 'assets',
      options: {
        episode: 1,
        shotId: '5',
        assetId: 'location-5',
      },
    })
  })

  it('resolves a canvas navigation target back to the correct node', () => {
    const graph = buildProductWorkspaceCanvasBetaGraph({
      bookTitle: '三个和尚',
      scripts: [{ episode: 1, content: '第一集剧本' }],
      shotsByEpisode: {
        1: [
          {
            episode: 1,
            shot_id: '8',
            scene_name: '寺庙后院',
            visual_prompt_static: '静态',
            visual_prompt_motion: '运动',
            assets: { images: [], videos: [], audios: [] },
          },
        ],
      },
      allAssets: [
        {
          id: 'character-8',
          category: 'character',
          assetRecordId: 8,
          title: '和尚丙',
          subtitle: '分镜精调',
          detailPrimary: '青年和尚',
          status: 'ready',
          prompt: '人物提示词',
          shotIds: ['1-8'],
          episodeIds: [1],
          referenceCount: 1,
          previewCount: 1,
          selectedReferenceCount: 1,
          lockedReferenceCount: 0,
          staleReferenceCount: 0,
          hasStaleReferencePrompt: false,
          references: [{ id: 11, asset_type: 'character', asset_id: '8', image_url: '/assets/heshangbing.png' }],
          variantLabel: '分镜精调',
          variantScope: 'shot_variant',
          variantStageName: '镜头 8',
        },
      ],
      qaEntries: [],
    })

    expect(
      resolveCanvasNavigationNodeId(graph, {
        episode: 1,
        shotId: '8',
      }),
    ).toBe('canvas-shot-1-8')

    expect(
      resolveCanvasNavigationNodeId(graph, {
        episode: 1,
        assetId: 'character-8',
      }),
    ).toBe('canvas-asset-character-8')
  })

  it('builds a readable canvas recovery summary from navigation context', () => {
    const summary = buildCanvasNavigationSummary({
      episode: 1,
      shotId: '8',
      assetLabel: '阿宁',
      taskId: 'runtime-verify-pending-001',
      recoveryKind: 'video',
      recoveryIntent: 'shot_variant_refinement',
    })

    expect(summary).toBeTruthy()
    expect(summary?.title).toContain('第 1 集')
    expect(summary?.title).toContain('镜头 8')
    expect(summary?.title).toContain('阿宁')
    expect(summary?.title).toContain('视频回收')
    expect(summary?.detail).toContain('runtime-verify-pending-001')
    expect(summary?.detail).toContain('镜头精调')
  })

  it('distinguishes project syncing from true empty canvas state', () => {
    expect(
      shouldShowCanvasSyncingState({
        graphNodeCount: 0,
        isProjectDataLoading: true,
      }),
    ).toBe(true)

    expect(
      shouldShowCanvasSyncingState({
        graphNodeCount: 0,
        isProjectDataLoading: false,
      }),
    ).toBe(false)

    expect(
      shouldShowCanvasSyncingState({
        graphNodeCount: 12,
        isProjectDataLoading: true,
      }),
    ).toBe(false)
  })

  it('normalizes invalid episode selection back to a valid episode or all', () => {
    expect(
      resolveCanvasEpisodeSelection({
        selectedEpisode: 2,
        availableEpisodes: [1],
        navigationTargetEpisode: 1,
      }),
    ).toBe(1)

    expect(
      resolveCanvasEpisodeSelection({
        selectedEpisode: 2,
        availableEpisodes: [1, 3],
        navigationTargetEpisode: null,
      }),
    ).toBe(1)

    expect(
      resolveCanvasEpisodeSelection({
        selectedEpisode: 2,
        availableEpisodes: [],
        navigationTargetEpisode: null,
      }),
    ).toBe('all')
  })

  it('shows refocus action only when navigation target and concrete target node both exist', () => {
    expect(
      shouldShowCanvasNavigationRefocusAction({
        target: { episode: 1, shotId: '3' },
        targetNodeId: 'canvas-shot-1-3',
      }),
    ).toBe(true)

    expect(
      shouldShowCanvasNavigationRefocusAction({
        target: { episode: 1, shotId: '3' },
        targetNodeId: null,
      }),
    ).toBe(false)

    expect(
      shouldShowCanvasNavigationRefocusAction({
        target: null,
        targetNodeId: 'canvas-shot-1-3',
      }),
    ).toBe(false)
  })

  it('describes resolved, syncing, and missing recovery target states', () => {
    expect(
      buildCanvasNavigationTargetStatus({
        target: { episode: 1, shotId: '3' },
        targetNodeId: 'canvas-shot-1-3',
        isProjectDataLoading: false,
      }),
    ).toMatchObject({
      tone: 'resolved',
      label: '已定位到恢复目标',
    })

    expect(
      buildCanvasNavigationTargetStatus({
        target: { episode: 1, shotId: '3' },
        targetNodeId: null,
        isProjectDataLoading: true,
      }),
    ).toMatchObject({
      tone: 'syncing',
      label: '正在等待目标节点',
    })

    expect(
      buildCanvasNavigationTargetStatus({
        target: { episode: 1, shotId: '3' },
        targetNodeId: null,
        isProjectDataLoading: false,
      }),
    ).toMatchObject({
      tone: 'missing',
      label: '暂未定位到恢复目标',
    })
  })

  it('describes pending, closed, and changed recovery closure states', () => {
    expect(
      buildCanvasRecoveryClosureStatus({
        target: { episode: 1, shotId: '3', taskId: 'task-1', recoveryKind: 'frame' },
        targetNodeId: 'canvas-shot-1-3',
        isProjectDataLoading: false,
        pendingFrameTaskId: 'task-1',
        hasAdoptedFrame: false,
      }),
    ).toMatchObject({
      tone: 'pending',
      label: '恢复结果仍待回收',
    })

    expect(
      buildCanvasRecoveryClosureStatus({
        target: { episode: 1, shotId: '3', taskId: 'task-1', recoveryKind: 'frame' },
        targetNodeId: 'canvas-shot-1-3',
        isProjectDataLoading: false,
        pendingFrameTaskId: null,
        latestExecutionTaskId: 'task-1',
        hasAdoptedFrame: true,
      }),
    ).toMatchObject({
      tone: 'closed',
      label: '恢复链路已收口',
    })

    expect(
      buildCanvasRecoveryClosureStatus({
        target: { episode: 1, shotId: '3', taskId: 'task-1', recoveryKind: 'video' },
        targetNodeId: 'canvas-shot-1-3',
        isProjectDataLoading: false,
        pendingVideoTaskId: null,
        latestExecutionTaskId: 'task-2',
        hasAdoptedVideo: false,
      }),
    ).toMatchObject({
      tone: 'changed',
      label: '恢复目标已变化',
    })
  })

  it('treats a mismatched latest execution task as changed even when a same-kind output already exists', () => {
    expect(
      buildCanvasRecoveryClosureStatus({
        target: { episode: 1, shotId: '3', taskId: 'task-1', recoveryKind: 'frame' },
        targetNodeId: 'canvas-shot-1-3',
        isProjectDataLoading: false,
        pendingFrameTaskId: null,
        latestExecutionTaskId: 'task-2',
        hasAdoptedFrame: true,
      }),
    ).toMatchObject({
      tone: 'changed',
    })
  })

  it('builds state-specific recovery action plans for pending, closed, and missing targets', () => {
    expect(
      buildCanvasRecoveryActionPlan({
        target: { episode: 1, shotId: '3', taskId: 'task-1', recoveryKind: 'frame' },
        targetStatusTone: 'resolved',
        closureStatusTone: 'pending',
        canRefocus: true,
      }),
    ).toMatchObject({
      primaryAction: 'tasks',
      allowRefocus: true,
    })

    expect(
      buildCanvasRecoveryActionPlan({
        target: { episode: 1, shotId: '3', taskId: 'task-1', recoveryKind: 'frame' },
        targetStatusTone: 'resolved',
        closureStatusTone: 'closed',
        canRefocus: true,
      }),
    ).toMatchObject({
      primaryAction: 'storyboard',
      allowRefocus: true,
    })

    expect(
      buildCanvasRecoveryActionPlan({
        target: { episode: 1, shotId: '3', taskId: 'task-1', recoveryKind: 'frame' },
        targetStatusTone: 'missing',
        closureStatusTone: 'missing',
        canRefocus: true,
      }),
    ).toMatchObject({
      primaryAction: 'tasks',
      allowRefocus: false,
    })
  })

  it('collapses asset nodes into grouped canvas nodes without losing state aggregation', () => {
    const graph = buildProductWorkspaceCanvasBetaGraph({
      bookTitle: '三个和尚',
      scripts: [{ episode: 1, content: '第一集剧本' }],
      shotsByEpisode: {
        1: [
          {
            episode: 1,
            shot_id: '8',
            scene_name: '寺庙后院',
            visual_prompt_static: '静态提示词',
            visual_prompt_motion: '运动提示词',
            assets: { images: [], videos: [], audios: [] },
          },
        ],
      },
      allAssets: [
        {
          id: 'character-8',
          category: 'character',
          assetRecordId: 8,
          title: '阿宁',
          subtitle: '分镜精调',
          detailPrimary: '青年和尚',
          status: 'ready',
          prompt: '人物提示词',
          shotIds: ['1-8'],
          episodeIds: [1],
          referenceCount: 1,
          previewCount: 1,
          selectedReferenceCount: 1,
          lockedReferenceCount: 1,
          staleReferenceCount: 0,
          hasStaleReferencePrompt: false,
          references: [{ id: 11, asset_type: 'character', asset_id: '8', image_url: '/assets/aning.png' }],
          variantLabel: '分镜精调',
          variantScope: 'shot_variant',
          variantStageName: '镜头 8',
        },
        {
          id: 'character-9',
          category: 'character',
          assetRecordId: 9,
          title: '师兄',
          subtitle: '分镜精调',
          detailPrimary: '青年和尚',
          status: 'draft',
          prompt: '人物提示词',
          shotIds: ['1-8'],
          episodeIds: [1],
          referenceCount: 0,
          previewCount: 0,
          selectedReferenceCount: 0,
          lockedReferenceCount: 0,
          staleReferenceCount: 0,
          hasStaleReferencePrompt: false,
          references: [],
          variantLabel: '分镜精调',
          variantScope: 'shot_variant',
          variantStageName: '镜头 8',
        },
      ] satisfies AssetSummary[],
      qaEntries: [],
    })

    const collapsed = collapseCanvasGraphByKind(graph.nodes, graph.edges, ['character'])

    const groupNode = collapsed.nodes.find((node) => node.id === 'canvas-group-character-1')
    expect(groupNode).toBeTruthy()
    expect(groupNode?.isGroup).toBe(true)
    expect(groupNode?.groupedNodeIds).toEqual(
      expect.arrayContaining(['canvas-asset-character-8', 'canvas-asset-character-9']),
    )
    expect(groupNode?.hasOutput).toBe(true)
    expect(groupNode?.hasBlocker).toBe(true)
    expect(groupNode?.missingReference).toBe(true)
    expect(groupNode?.meta.length).toBeGreaterThan(0)
    expect(groupNode?.meta.some((item) => item.includes('2'))).toBe(true)
    expect(collapsed.nodes.some((node) => node.id === 'canvas-asset-character-8')).toBe(false)
    expect(collapsed.nodes.some((node) => node.id === 'canvas-asset-character-9')).toBe(false)
    expect(collapsed.edges.some((edge) => edge.source === 'canvas-group-character-1' && edge.target === 'canvas-shot-1-8')).toBe(
      true,
    )
    expect(collapsed.edges.some((edge) => edge.source === 'canvas-group-character-1' && edge.target === 'canvas-group-character-1')).toBe(
      false,
    )
  })

  it('builds creation-oriented recovery action labels for different recovery states', () => {
    expect(
      buildCanvasRecoveryActionLabel({
        action: 'tasks',
        targetStatusTone: 'resolved',
        closureStatusTone: 'pending',
      }),
    ).toBe('继续回收任务')

    expect(
      buildCanvasRecoveryActionLabel({
        action: 'tasks',
        targetStatusTone: 'missing',
        closureStatusTone: 'missing',
      }),
    ).toBe('回任务中心确认')

    expect(
      buildCanvasRecoveryActionLabel({
        action: 'storyboard',
        targetStatusTone: 'resolved',
        closureStatusTone: 'closed',
      }),
    ).toBe('继续当前镜头创作')

    expect(
      buildCanvasRecoveryActionLabel({
        action: 'storyboard',
        targetStatusTone: 'missing',
        closureStatusTone: 'missing',
      }),
    ).toBe('检查当前集镜头')

    expect(
      buildCanvasRecoveryActionLabel({
        action: 'assets',
        targetStatusTone: 'resolved',
        closureStatusTone: 'closed',
      }),
    ).toBe('继续当前资产创作')

    expect(
      buildCanvasRecoveryActionLabel({
        action: 'refocus',
        targetStatusTone: 'resolved',
        closureStatusTone: 'closed',
      }),
    ).toBe('回到恢复节点')
  })
  it('builds direct continue-creation actions only for closed recovery states with a selected shot', () => {
    expect(
      buildCanvasRecoveryContinueActionPlan({
        recoveryKind: 'frame',
        closureStatusTone: 'closed',
        hasSelectedShot: true,
        hasAdoptedFrame: true,
        hasAdoptedVideo: false,
      }),
    ).toMatchObject({
      action: 'generate_video',
    })

    expect(
      buildCanvasRecoveryContinueActionPlan({
        recoveryKind: 'prompt',
        closureStatusTone: 'closed',
        hasSelectedShot: true,
        hasCompiledPrompt: true,
        hasAdoptedFrame: false,
        hasAdoptedVideo: false,
      }),
    ).toMatchObject({
      action: 'generate_frame',
    })

    expect(
      buildCanvasRecoveryContinueActionPlan({
        recoveryKind: 'reference',
        closureStatusTone: 'closed',
        hasSelectedShot: true,
        hasAdoptedFrame: true,
        hasAdoptedVideo: false,
      }),
    ).toMatchObject({
      action: 'recompile_then_video',
    })

    expect(
      buildCanvasRecoveryContinueActionPlan({
        recoveryKind: 'video',
        closureStatusTone: 'closed',
        hasSelectedShot: true,
        hasAdoptedFrame: true,
        hasAdoptedVideo: false,
      }),
    ).toBeNull()

    expect(
      buildCanvasRecoveryContinueActionPlan({
        recoveryKind: 'frame',
        closureStatusTone: 'pending',
        hasSelectedShot: true,
        hasAdoptedFrame: true,
        hasAdoptedVideo: false,
      }),
    ).toBeNull()
  })
})
