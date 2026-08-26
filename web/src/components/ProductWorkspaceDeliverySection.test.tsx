import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import ProductWorkspaceDeliverySection, {
  buildDeliveryHistorySummary,
  buildDeliveryCanvasHandoffSummary,
  buildDeliveryCanvasPrimaryActionPlan,
  filterDeliveryHistoryRecords,
  getDeliveryRecordAssetType,
} from './ProductWorkspaceDeliverySection'

describe('ProductWorkspaceDeliverySection', () => {
  it('builds a readable canvas handoff summary for delivery continuation', () => {
    expect(
      buildDeliveryCanvasHandoffSummary({
        handoff: {
          target: 'delivery',
          episode: 2,
          handoffDetail: '继续确认这一集的交付阻塞与放行状态。',
        },
        readiness: {
          episode: 2,
        } as any,
      }),
    ).toEqual({
      title: '已从创作画布定位到 第 2 集交付',
      label: '继续确认当前集交付状态',
      detail: '继续确认这一集的交付阻塞与放行状态。',
    })
  })

  it('builds a first executable action for delivery continuation', () => {
    expect(
      buildDeliveryCanvasPrimaryActionPlan({
        readiness: {
          episode: 1,
          canExport: false,
        } as any,
        primaryBlockedItem: {
          code: 'missing_prompts',
          label: '提示词未齐',
          detail: '仍有镜头缺少提示词。',
          targetSection: 'storyboard',
          priority: 'high',
          episode: 1,
          shotId: '4',
        },
        episodeRecordCount: 0,
      }),
    ).toEqual({
      action: 'repair_blocker',
      label: '定位镜头 4',
      detail: '当前集仍存在首个交付阻塞项“提示词未齐”，先回到对应模块处理，再继续交付链路。',
    })

    expect(
      buildDeliveryCanvasPrimaryActionPlan({
        readiness: {
          episode: 1,
          canExport: true,
        } as any,
        primaryBlockedItem: null,
        episodeRecordCount: 0,
      }),
    ).toEqual({
      action: 'save_record',
      label: '先生成交付记录',
      detail: '当前集已经具备交付条件，建议先沉淀一版交付记录，收口本次交付状态与版本快照。',
    })

    expect(
      buildDeliveryCanvasPrimaryActionPlan({
        readiness: {
          episode: 1,
          canExport: true,
        } as any,
        primaryBlockedItem: null,
        episodeRecordCount: 2,
      }),
    ).toEqual({
      action: 'export_json',
      label: '导出 JSON 并登记',
      detail: '当前集已有交付记录，下一步更适合继续导出结构化交付快照，供下游协作与回溯使用。',
    })
  })

  it('filters delivery history by episode status and format', () => {
    const records = [
      {
        id: 'record-1',
        episode: 1,
        status: 'completed',
        exportFormat: 'json',
        formatLabel: 'JSON',
        createdAt: '2026-08-26T10:00:00.000Z',
        summary: '第 1 集可交付',
        totalShots: 2,
        deliverableShots: 2,
        pendingReviewShots: 0,
        blockedShots: 0,
        blockedShotIds: [],
        blockedCodes: [],
        blockedReasons: [],
      },
      {
        id: 'record-2',
        episode: 2,
        status: 'blocked',
        exportFormat: 'delivery',
        formatLabel: '交付快照',
        createdAt: '2026-08-26T11:00:00.000Z',
        summary: '第 2 集 QA 阻塞',
        totalShots: 3,
        deliverableShots: 1,
        pendingReviewShots: 2,
        blockedShots: 1,
        blockedShotIds: [],
        blockedCodes: ['qa_blocked'],
        blockedReasons: ['QA 待处理 1 项'],
      },
      {
        id: 'record-3',
        episode: 1,
        status: 'completed',
        exportFormat: 'storyboard-machine-prompt-minimax-h3-webui',
        formatLabel: 'STORYBOARD-MACHINE-PROMPT-MINIMAX-H3-WEBUI',
        createdAt: '2026-08-26T12:00:00.000Z',
        summary: '第 1 集 · 镜头 8 · minimax-h3 WEBUI 机器提示词导出快照',
        totalShots: 1,
        deliverableShots: 1,
        pendingReviewShots: 0,
        blockedShots: 0,
        blockedShotIds: [],
        blockedCodes: [],
        blockedReasons: [],
        metaInfo: {
          record_type: 'storyboard_machine_prompt_export',
          target_model: 'minimax-h3',
          export_channel: 'webui',
          scene_name: '便利店',
          shot_id: 8,
          api_submission: false,
        },
      },
    ] as any

    expect(buildDeliveryHistorySummary(records)).toMatchObject({
      total: 3,
      completed: 2,
      blocked: 1,
      deliveryPackageCount: 2,
      machinePromptCount: 1,
      episodes: [1, 2],
    })
    expect(getDeliveryRecordAssetType(records[2])).toBe('machine_prompt')
    expect(
      filterDeliveryHistoryRecords(records, {
        selectedEpisode: 1,
        episodeFilter: 'current',
        statusFilter: 'all',
        formatFilter: 'all',
        assetTypeFilter: 'delivery_package',
      }).map((record) => record.id),
    ).toEqual(['record-1'])
    expect(
      filterDeliveryHistoryRecords(records, {
        selectedEpisode: 1,
        episodeFilter: 'all',
        statusFilter: 'blocked',
        formatFilter: 'delivery',
      }).map((record) => record.id),
    ).toEqual(['record-2'])
    expect(
      filterDeliveryHistoryRecords(records, {
        selectedEpisode: 1,
        episodeFilter: 'all',
        statusFilter: 'all',
        formatFilter: 'all',
        assetTypeFilter: 'machine_prompt',
        searchQuery: '便利店 minimax',
      }).map((record) => record.id),
    ).toEqual(['record-3'])
  })

  it('renders the canvas handoff card with a first action inside delivery detail', () => {
    const html = renderToStaticMarkup(
      <ProductWorkspaceDeliverySection
        bookId={14}
        isProjectDataLoading={false}
        bookTitle="三个和尚"
        chapterCount={3}
        wordCount={1200}
        contentStatusLabel="内容已就绪"
        contentStatusDetail="已完成内容准备。"
        adaptationStateLabel="改编已锁定"
        adaptationStateDetail="已完成改编锁定。"
        adaptationLockedAt="2026-07-29T10:00:00.000Z"
        scripts={[{ episode: 1, content: '第一集剧本', status: 'done' } as any]}
        scriptDecisionState={{
          '1': {
            lockedAt: '2026-07-29T10:00:00.000Z',
            releasedAt: '2026-07-29T10:10:00.000Z',
            note: '',
          },
        }}
        shotsByEpisode={{
          1: [
            {
              episode: 1,
              shot_id: '1',
              scene_name: '寺庙后院',
              visual_prompt_static: '静态提示词',
              visual_prompt_motion: '运动提示词',
              assets: {
                images: [{ adopted: true, id: 'img-1', title: '分镜图', label: '分镜图' }],
                videos: [{ adopted: true, id: 'video-1', title: '视频', label: '视频' }],
                references: {
                  characters: { monk: [{ id: 'ref-1' }] },
                  scene: [],
                  props: {},
                },
              },
            },
          ] as any,
        }}
        qaEntries={[]}
        makeups={[] as any}
        locations={[] as any}
        props={[] as any}
        canvasHandoff={{
          target: 'delivery',
          episode: 1,
          handoffDetail: '继续确认当前集交付状态。',
        }}
        onNavigate={() => {}}
      />,
    )

    expect(html).toContain('承接后的首个动作')
    expect(html).toContain('立即继续')
  })
})
