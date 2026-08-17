import { describe, expect, it } from 'vitest'
import {
  buildDeliveryEpisodeReadiness,
  buildDeliveryExportPackage,
  buildDeliveryExportSummaryText,
  buildDeliveryFileStem,
  buildDeliveryFinalDraftDocument,
  buildDeliveryWordDocument,
  deriveDeliveryRecordRepairActions,
  isLikelyCorruptedDeliveryText,
  normalizeDeliveryRecordFormatLabel,
  summarizeDeliveryPackage,
  summarizeDeliveryRecordHistory,
} from './productWorkspaceDelivery'

describe('productWorkspaceDelivery', () => {
  it('marks an episode exportable only when script decisions, prompts, and adopted media are ready', () => {
    const readiness = buildDeliveryEpisodeReadiness({
      hasExplicitLockedAdaptation: true,
      scripts: [{ episode: 1, content: 'script ready' }],
      scriptDecisionState: {
        '1': {
          lockedAt: '2026-07-06T10:00:00.000Z',
          releasedAt: '2026-07-06T10:10:00.000Z',
          note: '',
        },
      },
      shotsByEpisode: {
        1: [
          {
            episode: 1,
            shot_id: '01',
            scene_name: 'scene',
            visual_prompt_static: 'static',
            visual_prompt_motion: 'motion',
            assets: {
              images: [{ id: 'img-1', adopted: true }],
              videos: [{ id: 'vid-1', adopted: true }],
              audios: [],
              references: {
                characters: { sister: [{ id: 'ref-1' }] },
                scene: [{ id: 'scene-ref' }],
                props: {},
              },
            },
          },
        ] as any,
      },
      qaEntries: [{ episode: 1, error_count: 0 }],
      makeups: [],
      locations: [],
      props: [],
    })

    expect(readiness[0]).toMatchObject({
      episode: 1,
      hasScript: true,
      canExport: true,
      statusLabel: '可交付',
      totalShots: 1,
      readyShots: 1,
      imageReadyShots: 1,
      videoReadyShots: 1,
      recommendedRepairSection: null,
    })
    expect(summarizeDeliveryPackage(readiness[0]!)).toContain('QA')
  })

  it('builds structured repair path for blocked export readiness', () => {
    const readiness = buildDeliveryEpisodeReadiness({
      hasExplicitLockedAdaptation: false,
      scripts: [{ episode: 2, content: 'script ready' }],
      scriptDecisionState: {
        '2': {
          lockedAt: '2026-07-06T10:00:00.000Z',
          releasedAt: null,
          note: '',
        },
      },
      shotsByEpisode: {
        2: [
          {
            episode: 2,
            shot_id: '01',
            scene_name: 'scene',
            visual_prompt_static: '',
            visual_prompt_motion: 'motion',
            assets: {
              images: [],
              videos: [],
              audios: [],
              references: {
                characters: {},
                scene: [],
                props: {},
              },
            },
          },
        ] as any,
      },
      qaEntries: [{ episode: 2, error_count: 3 }],
      makeups: [],
      locations: [],
      props: [],
    })

    expect(readiness[0]?.canExport).toBe(false)
    expect(readiness[0]?.blockedItems.map((item) => item.targetSection)).toEqual(
      expect.arrayContaining(['adaptation', 'scripts', 'storyboard', 'assets', 'qa']),
    )
    expect(readiness[0]?.blockedItems).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: 'missing_prompts',
          episode: 2,
          shotId: '01',
        }),
        expect.objectContaining({
          code: 'missing_images',
          episode: 2,
          shotId: '01',
        }),
        expect.objectContaining({
          code: 'missing_videos',
          episode: 2,
          shotId: '01',
        }),
        expect.objectContaining({
          code: 'missing_asset_references',
          episode: 2,
          shotId: '01',
        }),
      ]),
    )
    expect(readiness[0]?.recommendedRepairSection).toBe('adaptation')
    expect(readiness[0]?.blockedReasons).toContain('项目改编方向未锁定')
  })

  it('blocks delivery even when media is ready if adaptation is not locked', () => {
    const readiness = buildDeliveryEpisodeReadiness({
      hasExplicitLockedAdaptation: false,
      scripts: [{ episode: 1, content: 'script ready' }],
      scriptDecisionState: {
        '1': {
          lockedAt: '2026-07-06T10:00:00.000Z',
          releasedAt: '2026-07-06T10:10:00.000Z',
          note: '',
        },
      },
      shotsByEpisode: {
        1: [
          {
            episode: 1,
            shot_id: '01',
            scene_name: 'scene',
            visual_prompt_static: 'static',
            visual_prompt_motion: 'motion',
            assets: {
              images: [{ id: 'img-1', adopted: true }],
              videos: [{ id: 'vid-1', adopted: true }],
              audios: [],
              references: {
                characters: { sister: [{ id: 'ref-1' }] },
                scene: [{ id: 'scene-ref' }],
                props: {},
              },
            },
          },
        ] as any,
      },
      qaEntries: [{ episode: 1, error_count: 0 }],
      makeups: [],
      locations: [],
      props: [],
    })

    expect(readiness[0]?.canExport).toBe(false)
    expect(readiness[0]?.blockedItems[0]).toMatchObject({
      code: 'adaptation_not_locked',
      targetSection: 'adaptation',
    })
  })

  it('normalizes export format labels and detects corrupted delivery copy', () => {
    expect(normalizeDeliveryRecordFormatLabel('json')).toBe('JSON')
    expect(normalizeDeliveryRecordFormatLabel('delivery')).toBe('交付快照')
    expect(isLikelyCorruptedDeliveryText('manual verification snapshot')).toBe(true)
    expect(isLikelyCorruptedDeliveryText('???????')).toBe(true)
    expect(isLikelyCorruptedDeliveryText('第 1 集 | 剧本 待锁稿')).toBe(false)
  })

  it('rebuilds readable history summary for legacy export records', () => {
    const summary = summarizeDeliveryRecordHistory({
      episode: 1,
      scriptStatusLabel: '待锁稿',
      deliverableShots: 0,
      totalShots: 24,
      pendingReviewShots: 24,
      blockedReasons: ['剧本未锁稿', '剧本未放行', 'QA 39 项'],
      exportFormat: 'json',
      status: 'blocked',
    })

    expect(summary).toContain('第 1 集')
    expect(summary).toContain('24')
  })

  it('derives repair actions for blocked delivery history from blocked codes and reasons', () => {
    expect(
      deriveDeliveryRecordRepairActions({
        status: 'blocked',
        blockedCodes: ['adaptation_not_locked', 'missing_images', 'qa_blocked'],
        blockedReasons: [],
      }),
    ).toEqual([
      {
        code: 'adaptation_not_locked',
        label: '返回改编方向锁定',
        targetSection: 'adaptation',
      },
      {
        code: 'missing_images',
        label: '返回分镜工作台补参考图',
        targetSection: 'storyboard',
      },
      {
        code: 'qa_blocked',
        label: '返回 QA 工作台修复',
        targetSection: 'qa',
      },
    ])

    expect(
      deriveDeliveryRecordRepairActions({
        status: 'blocked',
        blockedReasons: ['项目改编方向未锁定', '缺已采纳视频', 'QA 5 项待处理'],
      }).map((item) => item.code),
    ).toEqual(['adaptation_not_locked', 'missing_videos', 'qa_blocked'])

    expect(
      deriveDeliveryRecordRepairActions({
        status: 'blocked',
        blockedReasons: ['仍有 24 个镜头缺首帧', '仍有 24 个镜头未通过验收'],
      }).map((item) => item.code),
    ).toEqual(['missing_images', 'qa_blocked'])

    expect(
      deriveDeliveryRecordRepairActions({
        status: 'completed',
        blockedCodes: ['missing_images'],
        blockedReasons: ['缺已采纳分镜图'],
      }),
    ).toEqual([])
  })

  it('builds a traceable delivery export package with adopted media and selected references', () => {
    const readiness = buildDeliveryEpisodeReadiness({
      scripts: [{ episode: 1, content: 'script ready' }],
      scriptDecisionState: {
        '1': {
          lockedAt: '2026-07-06T10:00:00.000Z',
          releasedAt: '2026-07-06T10:10:00.000Z',
          note: 'locked',
        },
      },
      shotsByEpisode: {
        1: [
          {
            episode: 1,
            shot_id: '01',
            scene_name: '井边',
            visual_prompt_static: 'static prompt',
            visual_prompt_motion: 'motion prompt',
            visual_prompt_final: 'final prompt',
            prompt_version: 4,
            assets: {
              images: [{ id: 'img-1', title: 'frame 1', label: 'v1', adopted: true, previewUrl: 'https://img.example/1.png' }],
              videos: [{ id: 'vid-1', title: 'video 1', label: 'v1', adopted: true, uri: 'https://video.example/1.mp4' }],
              audios: [],
              references: { characters: {}, scene: [], props: {} },
            },
          },
        ] as any,
      },
      qaEntries: [{ episode: 1, error_count: 0 }],
      makeups: [
        {
          id: 101,
          episode: 1,
          character_name: '和尚甲',
          scope_label: '第 1 集默认造型',
          visual_prompt_zh: 'character prompt',
          reference_assets: [
            { id: 1, asset_type: 'character', asset_id: '101', status: 'selected', image_url: 'https://img.example/char.png' },
          ],
        },
      ] as any,
      locations: [],
      props: [],
    })[0]!

    const exportPackage = buildDeliveryExportPackage({
      bookId: 14,
      bookTitle: '三个和尚',
      chapterCount: 1,
      wordCount: 1200,
      contentStatusLabel: '已完成',
      contentStatusDetail: '已导入原文',
      adaptationStateLabel: '已锁定',
      adaptationStateDetail: '主方向已确认',
      selectedAdaptationName: '悬疑反转向',
      adaptationCustomNote: '保留反转',
      adaptationLockedAt: '2026-07-17T09:00:00.000Z',
      readiness,
      scripts: [{ episode: 1, content: 'script ready' }],
      scriptDecisionState: {
        '1': {
          lockedAt: '2026-07-06T10:00:00.000Z',
          releasedAt: '2026-07-06T10:10:00.000Z',
          note: 'locked',
        },
      },
      shotsByEpisode: {
        1: [
          {
            episode: 1,
            shot_id: '01',
            scene_name: '井边',
            visual_prompt_static: 'static prompt',
            visual_prompt_motion: 'motion prompt',
            visual_prompt_final: 'final prompt',
            prompt_version: 4,
            assets: {
              images: [{ id: 'img-1', title: 'frame 1', label: 'v1', adopted: true, previewUrl: 'https://img.example/1.png' }],
              videos: [{ id: 'vid-1', title: 'video 1', label: 'v1', adopted: true, uri: 'https://video.example/1.mp4' }],
              audios: [],
              references: { characters: {}, scene: [], props: {} },
            },
          },
        ] as any,
      },
      makeups: [
        {
          id: 101,
          episode: 1,
          character_name: '和尚甲',
          scope_label: '第 1 集默认造型',
          visual_prompt_zh: 'character prompt',
          reference_assets: [
            { id: 1, asset_type: 'character', asset_id: '101', status: 'selected', image_url: 'https://img.example/char.png' },
          ],
        },
      ] as any,
      locations: [],
      props: [],
      versionLabel: 'v3',
      generatedAt: '2026-07-17T11:40:00.000Z',
    })

    expect(exportPackage.versionLabel).toBe('v3')
    expect(exportPackage.adoptedStoryboard[0]?.adoptedImage?.id).toBe('img-1')
    expect(exportPackage.adoptedStoryboard[0]?.adoptedVideo?.id).toBe('vid-1')
    expect(exportPackage.selectedReferenceAssets.characters[0]?.assetName).toBe('和尚甲')
    expect(exportPackage.selectedReferenceAssets.characters[0]?.selectedReferences).toHaveLength(1)
    expect(exportPackage.script.lockedAt).toBe('2026-07-06T10:00:00.000Z')
  })

  it('builds delivery export documents for Word and Final Draft', () => {
    const readiness = buildDeliveryEpisodeReadiness({
      scripts: [{ episode: 1, content: 'script ready' }],
      scriptDecisionState: {
        '1': {
          lockedAt: '2026-07-06T10:00:00.000Z',
          releasedAt: '2026-07-06T10:10:00.000Z',
          note: 'locked',
        },
      },
      shotsByEpisode: {
        1: [
          {
            episode: 1,
            shot_id: '01',
            scene_name: '井边',
            visual_prompt_static: 'static prompt',
            visual_prompt_motion: 'motion prompt',
            assets: {
              images: [{ id: 'img-1', title: 'frame 1', label: 'v1', adopted: true }],
              videos: [{ id: 'vid-1', title: 'video 1', label: 'v1', adopted: true }],
              audios: [],
              references: { characters: {}, scene: [], props: {} },
            },
          },
        ] as any,
      },
      qaEntries: [{ episode: 1, error_count: 0 }],
      makeups: [],
      locations: [],
      props: [],
    })[0]!

    const exportPackage = buildDeliveryExportPackage({
      bookId: 14,
      bookTitle: '三个和尚',
      chapterCount: 1,
      wordCount: 1200,
      contentStatusLabel: '已完成',
      contentStatusDetail: '已导入原文',
      adaptationStateLabel: '已锁定',
      adaptationStateDetail: '主方向已确认',
      selectedAdaptationName: '悬疑反转向',
      adaptationCustomNote: '保留反转',
      adaptationLockedAt: '2026-07-17T09:00:00.000Z',
      readiness,
      scripts: [{ episode: 1, content: 'script ready' }],
      scriptDecisionState: {
        '1': {
          lockedAt: '2026-07-06T10:00:00.000Z',
          releasedAt: '2026-07-06T10:10:00.000Z',
          note: 'locked',
        },
      },
      shotsByEpisode: {
        1: [
          {
            episode: 1,
            shot_id: '01',
            scene_name: '井边',
            visual_prompt_static: 'static prompt',
            visual_prompt_motion: 'motion prompt',
            assets: {
              images: [{ id: 'img-1', title: 'frame 1', label: 'v1', adopted: true }],
              videos: [{ id: 'vid-1', title: 'video 1', label: 'v1', adopted: true }],
              audios: [],
              references: { characters: {}, scene: [], props: {} },
            },
          },
        ] as any,
      },
      makeups: [],
      locations: [],
      props: [],
      versionLabel: 'v2',
      generatedAt: '2026-07-17T11:40:00.000Z',
    })

    const summary = buildDeliveryExportSummaryText(readiness)
    const fileStem = buildDeliveryFileStem(exportPackage.bookTitle, exportPackage.episode, exportPackage.versionLabel)
    const wordDocument = buildDeliveryWordDocument(exportPackage)
    const finalDraftDocument = buildDeliveryFinalDraftDocument(exportPackage)

    expect(summary).toContain('导出状态')
    expect(fileStem).toContain('episode-1-v2')
    expect(wordDocument).toContain('三个和尚')
    expect(wordDocument).toContain('分镜交付表')
    expect(finalDraftDocument).toContain('<FinalDraft')
    expect(finalDraftDocument).toContain('static prompt')
  })
})
