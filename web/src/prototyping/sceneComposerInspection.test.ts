import { describe, expect, it } from 'vitest'
import {
  MOCK_BIBLE,
  MOCK_GENERATED_IMAGES,
  MOCK_QA,
  MOCK_SCRIPTS,
  MOCK_STORYBOARD,
  MOCK_VISUAL,
} from './mockData'
import { buildDeliveryChecklistReport, buildEpisodeInspectionReport, buildExportReadinessReport, buildFailureTaskEntries, buildProblemQueueEntries } from './SceneComposer'
import { createTemplateDocument, type CanvasDocument } from './sceneComposerModel'
import {
  completeGenerationTask,
  createPendingGenerationBranch,
  failGenerationTask,
} from './sceneComposerTaskService'

const outputs = {
  bible: MOCK_BIBLE,
  scripts: MOCK_SCRIPTS,
  storyboard: MOCK_STORYBOARD,
  visual: MOCK_VISUAL,
  qa: MOCK_QA,
  generatedImages: MOCK_GENERATED_IMAGES,
}

function getShotNodes(document: CanvasDocument) {
  return document.nodes.filter((node) => node.data.kind === 'shot')
}

describe('sceneComposerInspection', () => {
  it('summarizes missing storyboard, video, adoption, and sequence gaps', () => {
    const document = createTemplateDocument(outputs)
    const pending = createPendingGenerationBranch(document, 'image-seed-1-2', 'video', { source: 'real' })
    const withExtraVideo = completeGenerationTask(pending.document, pending.nodeId, {
      id: 'video-real-1-2',
      kind: 'video',
      title: '视频 1-2 v1',
      label: 'v1',
      adopted: false,
    })
    const { ['1-2']: _removedVideo, ...remainingVideoAdoptions } = withExtraVideo.adoptedVersions.video ?? {}
    const withoutAdoptedVideo = {
      ...withExtraVideo,
      adoptedVersions: {
        ...withExtraVideo.adoptedVersions,
        video: remainingVideoAdoptions,
      },
      edges: withExtraVideo.edges.filter(
        (edge) => !(edge.source === pending.nodeId && edge.data?.kind === 'sequence'),
      ),
    }

    const report = buildEpisodeInspectionReport(withoutAdoptedVideo, getShotNodes(withoutAdoptedVideo))

    expect(report.totalShots).toBe(5)
    expect(report.imageReadyShots).toBeGreaterThanOrEqual(2)
    expect(report.videoReadyShots).toBeGreaterThanOrEqual(2)
    expect(report.missingImageShots.map((item) => item.shotId)).toEqual(expect.arrayContaining(['1-3', '1-4', '1-5']))
    expect(report.missingVideoShots.map((item) => item.shotId)).toEqual(expect.arrayContaining(['1-3', '1-4', '1-5']))
    expect(report.unadoptedVideoShots.map((item) => item.shotId)).toContain('1-2')
    expect(report.missingSequenceShots.map((item) => item.shotId)).toContain('1-2')
    expect(report.exportReady).toBe(false)
  })

  it('flags risky shots when references are incomplete but downstream media already exists', () => {
    const document = createTemplateDocument(outputs)
    const degraded = {
      ...document,
      edges: document.edges.filter(
        (edge) =>
          !(
            edge.target === 'shot-1-1' &&
            ['character-1', 'location-1', 'prop-1'].includes(edge.source)
          ),
      ),
    }

    const report = buildEpisodeInspectionReport(degraded, getShotNodes(degraded))

    expect(report.riskShots.map((item) => item.shotId)).toContain('1-1')
    expect(report.riskShots.find((item) => item.shotId === '1-1')?.detail).toContain('参考图完整度仅 0/3')
  })

  it('marks a fully sequenced episode as export ready', () => {
    const document = createTemplateDocument(outputs)
    const nodeIds = new Set(['script-1', 'shot-1-1', 'character-1', 'location-1', 'prop-1', 'image-seed-1-1', 'video-seed-1-1', 'sequence-1'])
    const focused = {
      ...document,
      nodes: document.nodes.filter((node) => nodeIds.has(node.id)),
      edges: document.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)),
      adoptedVersions: {
        image: { '1-1': 'image-seed-1-1' },
        video: { '1-1': 'video-seed-1-1' },
        audio: {},
      },
    }

    const report = buildEpisodeInspectionReport(focused, getShotNodes(focused))

    expect(report.totalShots).toBe(1)
    expect(report.sequenceShots).toBe(1)
    expect(report.missingImageShots).toHaveLength(0)
    expect(report.missingVideoShots).toHaveLength(0)
    expect(report.unadoptedVideoShots).toHaveLength(0)
    expect(report.missingSequenceShots).toHaveLength(0)
    expect(report.riskShots).toHaveLength(0)
    expect(report.exportReady).toBe(true)
  })

  it('does not let reference-risk warnings alone block export readiness', () => {
    const document = createTemplateDocument(outputs)
    const nodeIds = new Set(['script-1', 'shot-1-1', 'character-1', 'location-1', 'prop-1', 'image-seed-1-1', 'video-seed-1-1', 'sequence-1'])
    const focused = {
      ...document,
      nodes: document.nodes.filter((node) => nodeIds.has(node.id)),
      edges: document.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)).filter(
        (edge) =>
          !(
            edge.target === 'shot-1-1' &&
            ['character-1', 'location-1', 'prop-1'].includes(edge.source)
          ),
      ),
      adoptedVersions: {
        image: { '1-1': 'image-seed-1-1' },
        video: { '1-1': 'video-seed-1-1' },
        audio: {},
      },
    }

    const report = buildEpisodeInspectionReport(focused, getShotNodes(focused))

    expect(report.riskShots.map((item) => item.shotId)).toContain('1-1')
    expect(report.exportReady).toBe(true)
  })

  it('builds failure task entries with handled state and shot ownership', () => {
    const document = createTemplateDocument(outputs)
    const failedImagePending = createPendingGenerationBranch(document, 'shot-1-3', 'image', { source: 'real', nodeId: 'image-failed-1-3' })
    const failedImage = failGenerationTask(failedImagePending.document, 'image-failed-1-3', 'image', '图片生成失败')
    const failedVideoPending = createPendingGenerationBranch(failedImage, 'image-seed-1-1', 'video', { source: 'mock', nodeId: 'video-failed-1-1' })
    const failedVideo = failGenerationTask(failedVideoPending.document, 'video-failed-1-1', 'video', '视频生成失败')
    const markedHandled = {
      ...failedVideo,
      nodes: failedVideo.nodes.map((node) =>
        node.id === 'video-failed-1-1'
          ? {
              ...node,
              data: {
                ...node.data,
                metadata: {
                  ...(node.data.metadata ?? {}),
                  failureHandledAt: '2026-06-25T07:00:00.000Z',
                },
              },
            }
          : node,
      ),
    }

    const entries = buildFailureTaskEntries(markedHandled)

    expect(entries).toHaveLength(2)
    expect(entries[0]).toMatchObject({
      nodeId: 'image-failed-1-3',
      kind: 'image',
      shotId: '1-3',
      handled: false,
      sourceLabel: '真实任务',
    })
    expect(entries[1]).toMatchObject({
      nodeId: 'video-failed-1-1',
      kind: 'video',
      shotId: '1-1',
      handled: true,
      sourceLabel: 'Mock 分支',
    })
  })

  it('blocks export when shots, failures, or save state are incomplete', () => {
    const document = createTemplateDocument(outputs)
    const inspectionReport = buildEpisodeInspectionReport(document, getShotNodes(document))
    const failedImagePending = createPendingGenerationBranch(document, 'shot-1-3', 'image', { source: 'real', nodeId: 'image-failed-1-3' })
    const failedImage = failGenerationTask(failedImagePending.document, 'image-failed-1-3', 'image', '图片生成失败')
    const failureEntries = buildFailureTaskEntries(failedImage)

    const report = buildExportReadinessReport({
      document,
      shotNodes: getShotNodes(document),
      inspectionReport,
      failureTaskEntries: failureEntries.filter((entry) => !entry.handled),
      sequenceEntries: [],
      saveState: 'error',
    })

    expect(report.canExport).toBe(false)
    expect(report.issues.some((issue) => issue.title.includes('缺少采用视频'))).toBe(true)
    expect(report.issues.some((issue) => issue.title.includes('失败任务待处理'))).toBe(true)
    expect(report.issues.some((issue) => issue.title.includes('本地保存失败'))).toBe(true)
  })

  it('marks export ready when sequence, failures, and save state are all healthy', () => {
    const document = createTemplateDocument(outputs)
    const nodeIds = new Set(['script-1', 'shot-1-1', 'character-1', 'location-1', 'prop-1', 'image-seed-1-1', 'video-seed-1-1', 'sequence-1'])
    const focused = {
      ...document,
      nodes: document.nodes.filter((node) => nodeIds.has(node.id)),
      edges: document.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)),
      adoptedVersions: {
        image: { '1-1': 'image-seed-1-1' },
        video: { '1-1': 'video-seed-1-1' },
        audio: {},
      },
    }
    const shotNodes = getShotNodes(focused)
    const reviewed = {
      ...focused,
      nodes: focused.nodes.map((node) =>
        node.id === 'shot-1-1'
          ? {
              ...node,
              data: {
                ...node.data,
                metadata: {
                  ...(node.data.metadata ?? {}),
                  reviewStatus: 'approved',
                },
              },
            }
          : node,
      ),
    }
    const reviewedShotNodes = getShotNodes(reviewed)
    const inspectionReport = buildEpisodeInspectionReport(reviewed, reviewedShotNodes)
    const report = buildExportReadinessReport({
      document: reviewed,
      shotNodes: reviewedShotNodes,
      inspectionReport,
      failureTaskEntries: [],
      sequenceEntries: [{
        shotId: '1-1',
        shotNode: reviewedShotNodes[0] ?? null,
        adoptedNode: reviewed.nodes.find((node) => node.id === 'video-seed-1-1') ?? null,
        status: 'adopted',
      }],
      saveState: 'saved',
    })

    expect(report.canExport).toBe(true)
    expect(report.issues).toHaveLength(0)
    expect(report.sequenceCoverage).toContain('1/1')
  })

  it('adds changes-requested review items into the problem queue', () => {
    const document = createTemplateDocument(outputs)
    const reviewed = {
      ...document,
      nodes: document.nodes.map((node) =>
        node.id === 'shot-1-2'
          ? {
              ...node,
              data: {
                ...node.data,
                metadata: {
                  ...(node.data.metadata ?? {}),
                  reviewStatus: 'changes_requested',
                  reviewNote: '表演情绪不够稳定',
                },
              },
            }
          : node,
      ),
    }

    const entries = buildProblemQueueEntries(
      reviewed,
      getShotNodes(reviewed),
      buildEpisodeInspectionReport(reviewed, getShotNodes(reviewed)),
      [],
    )

    expect(entries.some((entry) => entry.type === 'review' && entry.shotId === '1-2')).toBe(true)
    expect(entries.find((entry) => entry.type === 'review' && entry.shotId === '1-2')?.detail).toContain('表演情绪不够稳定')
  })
  it('builds a delivery checklist with review and delivery metadata', () => {
    const document = createTemplateDocument(outputs)
    const nodeIds = new Set(['script-1', 'shot-1-1', 'character-1', 'location-1', 'prop-1', 'image-seed-1-1', 'video-seed-1-1', 'sequence-1'])
    const focused = {
      ...document,
      nodes: document.nodes
        .filter((node) => nodeIds.has(node.id))
        .map((node) =>
          node.id === 'shot-1-1'
            ? {
                ...node,
                data: {
                  ...node.data,
                  metadata: {
                    ...(node.data.metadata ?? {}),
                    reviewStatus: 'approved',
                  },
                },
              }
            : node,
        ),
      edges: document.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)),
      adoptedVersions: {
        image: { '1-1': 'image-seed-1-1' },
        video: { '1-1': 'video-seed-1-1' },
        audio: {},
      },
      deliveryRecords: [{
        id: 'delivery-1',
        createdAt: '2026-06-25T10:00:00.000Z',
        versionLabel: 'delivery-v1',
        status: 'delivered' as const,
        summary: 'test',
        shotCount: 1,
      }],
    }
    const shotNodes = getShotNodes(focused)
    const inspectionReport = buildEpisodeInspectionReport(focused, shotNodes)
    const sequenceEntries = [{
      shotId: '1-1',
      shotNode: shotNodes[0] ?? null,
      adoptedNode: focused.nodes.find((node) => node.id === 'video-seed-1-1') ?? null,
      status: 'adopted' as const,
    }]
    const exportReport = buildExportReadinessReport({
      document: focused,
      shotNodes,
      inspectionReport,
      failureTaskEntries: [],
      sequenceEntries,
      saveState: 'saved',
    })

    const checklist = buildDeliveryChecklistReport({
      document: focused,
      shotNodes,
      sequenceEntries,
      failureTaskEntries: [],
      inspectionReport,
      exportReadinessReport: exportReport,
      failedNodes: [],
    })

    expect(checklist.canDeliver).toBe(true)
    expect(checklist.latestDeliveryLabel).toBe('delivery-v1')
    expect(checklist.shots[0]?.reviewStatus).toBe('approved')
    expect(checklist.adoptedVideoCount).toBe(1)
  })
})
