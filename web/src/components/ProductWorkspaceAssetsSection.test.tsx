import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import ProductWorkspaceAssetsSection, { buildAssetCanvasPrimaryActionPlan } from './ProductWorkspaceAssetsSection'
import type { AssetEpisodeInsight, AssetSummary } from './productWorkspaceAssets'

function buildAsset(overrides: Partial<AssetSummary> = {}): AssetSummary {
  return {
    id: 'asset-character-1',
    category: 'character',
    assetRecordId: 101,
    title: '和尚甲',
    subtitle: '第 1 集默认造型',
    status: 'ref_ready',
    prompt: '人物分镜精调定妆设定板提示词',
    shotIds: ['1-01'],
    episodeIds: [1],
    referenceCount: 1,
    previewCount: 1,
    selectedReferenceCount: 1,
    lockedReferenceCount: 0,
    staleReferenceCount: 0,
    hasStaleReferencePrompt: false,
    variantScope: 'episode_default',
    variantLabel: '分集默认',
    variantStageName: '第 1 集默认造型',
    siblingVariantCount: 0,
    siblingVariants: [],
    references: [
      {
        id: 9001,
        asset_type: 'character',
        asset_id: 'asset-character-1',
        asset_name: '和尚甲 / 默认参考',
        image_url: 'https://example.com/ref.png',
        status: 'selected',
        prompt: '来源提示词正文',
        model: 'seedream-5.0-lite',
      },
    ],
    ...overrides,
  }
}

function renderSection(selectedAsset: AssetSummary | null, assetEpisodeInsights = new Map<string, AssetEpisodeInsight>()) {
  const prioritizedAssets = selectedAsset ? [selectedAsset] : []
  return renderToStaticMarkup(
    <ProductWorkspaceAssetsSection
      bookId={14}
      allAssetsCount={prioritizedAssets.length}
      shotEpisodes={[]}
      assetEpisodeFilter="all"
      assetCategoryFilter="all"
      assetStatusFilter="all"
      assetVersionFilter="all"
      assetSearchQuery=""
      assetCategoryCounts={{ all: prioritizedAssets.length, character: prioritizedAssets.length, location: 0, prop: 0 }}
      assetStatusCounts={{
        all: prioritizedAssets.length,
        missing_reference: 0,
        pending_selection: 0,
        stale_prompt: 0,
        locked_reference: 0,
      }}
      assetVersionCounts={{
        all: prioritizedAssets.length,
        base_identity: 0,
        episode_default: prioritizedAssets.length,
        shot_variant: 0,
        location_variant: 0,
        prop_variant: 0,
      }}
      prioritizedAssets={prioritizedAssets}
      selectedAsset={selectedAsset}
      assetEpisodeInsights={assetEpisodeInsights}
      assetActionMessage=""
      assetActionTone="info"
      assetActionFollowUp={null}
      linkedShotDraft={[]}
      shotBindingState="idle"
      isGeneratingReference={false}
      canvasHandoff={null}
      onAssetEpisodeFilterChange={() => {}}
      onAssetCategoryFilterChange={() => {}}
      onAssetStatusFilterChange={() => {}}
      onAssetVersionFilterChange={() => {}}
      onAssetSearchQueryChange={() => {}}
      onSelectAsset={() => {}}
      onOpenPreview={() => {}}
      onGenerateReference={() => {}}
      onGenerateAssetReference={() => {}}
      onDeleteReferenceAsset={() => {}}
      onUpdateReferenceAssetStatus={() => {}}
      onNavigateSection={() => {}}
      onNavigateTaskSection={() => {}}
      onNavigateShot={() => {}}
      onToggleShotBinding={() => {}}
      onApplyInferredShotBindings={() => {}}
      onSaveShotBindings={() => {}}
    />,
  )
}

describe('ProductWorkspaceAssetsSection', () => {
  it('shows category filter labels and summary for character assets', () => {
    const html = renderSection(buildAsset())

    expect(html).toContain('全部')
    expect(html).toContain('人物')
    expect(html).toContain('场景')
    expect(html).toContain('道具')
    expect(html).toContain('类型“全部”')
  })

  it('shows source prompt action for references that retain their generation prompt', () => {
    const html = renderSection(buildAsset())

    expect(html).toContain('查看来源')
  })

  it('hides source prompt action when the reference has no stored prompt', () => {
    const html = renderSection(
      buildAsset({
        references: [
          {
            id: 9002,
            asset_type: 'character',
            asset_id: 'asset-character-1',
            asset_name: '和尚甲 / 默认参考',
            image_url: 'https://example.com/ref.png',
            status: 'selected',
          },
        ],
      }),
    )

    expect(html).not.toContain('查看来源')
  })

  it('shows storyboard handoff CTA when the asset is still missing a reference image', () => {
    const selectedAsset = buildAsset({ previewCount: 0, referenceCount: 0, references: [] })
    const html = renderSection(
      selectedAsset,
      new Map([
        [
          selectedAsset.id,
          {
            shotIds: ['1-01'],
            blockerCount: 1,
            missingReference: true,
            impactShots: [
              {
                shotId: '1-01',
                episode: 1,
                sceneName: '井边',
                blockerCount: 1,
                statusLabel: '待补齐',
                nextAction: '补角色参考图',
                missingItems: ['角色参考图'],
              },
            ],
          },
        ],
      ]),
    )

    expect(html).toContain('上下游交接状态')
    expect(html).toContain('当前资产仍未具备参考图')
    expect(html).toContain('回镜头工作台复核')
  })

  it('prioritizes stale prompt repair when the asset references old prompt images', () => {
    const selectedAsset = buildAsset({
      hasStaleReferencePrompt: true,
      staleReferenceCount: 2,
    })
    const html = renderSection(
      selectedAsset,
      new Map([
        [
          selectedAsset.id,
          {
            shotIds: ['1-01'],
            blockerCount: 0,
            missingReference: false,
            impactShots: [
              {
                shotId: '1-01',
                episode: 1,
                sceneName: '井边',
                blockerCount: 0,
                statusLabel: '已就绪',
                nextAction: '进入 QA 修复',
                missingItems: [],
              },
            ],
          },
        ],
      ]),
    )

    expect(html).toContain('当前参考图仍基于旧提示词')
    expect(html).toContain('重生新版参考图')
  })

  it('shows QA handoff CTA when the asset is ready for downstream review', () => {
    const selectedAsset = buildAsset()
    const html = renderSection(
      selectedAsset,
      new Map([
        [
          selectedAsset.id,
          {
            shotIds: ['1-01'],
            blockerCount: 0,
            missingReference: false,
            impactShots: [
              {
                shotId: '1-01',
                episode: 1,
                sceneName: '井边',
                blockerCount: 0,
                statusLabel: '已就绪',
                nextAction: '进入 QA 修复',
                missingItems: [],
              },
            ],
          },
        ],
      ]),
    )

    expect(html).toContain('资产已具备下游接力条件')
    expect(html).toContain('进入 QA 修复')
  })

  it('shows inferred pending binding counts instead of zero when impact shots exist but bindings are not saved yet', () => {
    const selectedAsset = buildAsset({ shotIds: [] })
    const html = renderSection(
      selectedAsset,
      new Map([
        [
          selectedAsset.id,
          {
            shotIds: ['1-01', '1-02', '1-03'],
            blockerCount: 2,
            missingReference: true,
            impactShots: [
              {
                shotId: '1-01',
                episode: 1,
                sceneName: '井边',
                blockerCount: 1,
                statusLabel: '待补齐',
                nextAction: '补参考图',
                missingItems: ['参考资产'],
              },
            ],
          },
        ],
      ]),
    )

    expect(html).toContain('待同步绑定 3')
    expect(html).not.toContain('待同步绑定 0')
  })

  it('shows one-click inferred binding handoff when impact shots have not been written back yet', () => {
    const selectedAsset = buildAsset({ shotIds: [] })
    const html = renderSection(
      selectedAsset,
      new Map([
        [
          selectedAsset.id,
          {
            shotIds: ['01', '02'],
            blockerCount: 2,
            missingReference: false,
            impactShots: [
              {
                shotId: '01',
                episode: 1,
                sceneName: '水房',
                blockerCount: 1,
                statusLabel: '待恢复',
                nextAction: '继续修复提示词',
                missingItems: [],
              },
              {
                shotId: '02',
                episode: 1,
                sceneName: '院落',
                blockerCount: 1,
                statusLabel: '待补齐',
                nextAction: '补参考图',
                missingItems: [],
              },
            ],
          },
        ],
      ]),
    )

    expect(html).toContain('系统已识别 2 个待同步镜头，尚未写回资产绑定')
    expect(html).toContain('加入待同步镜头')
  })

  it('shows shot-variant recovery guidance when arriving from a storyboard state-change warning', () => {
    const selectedAsset = buildAsset()
    const html = renderToStaticMarkup(
      <ProductWorkspaceAssetsSection
        bookId={14}
        allAssetsCount={1}
        shotEpisodes={[]}
        assetEpisodeFilter={1}
        assetCategoryFilter="character"
        assetStatusFilter="all"
        assetVersionFilter="shot_variant"
        assetSearchQuery=""
        assetCategoryCounts={{ all: 1, character: 1, location: 0, prop: 0 }}
        assetStatusCounts={{ all: 1, missing_reference: 0, pending_selection: 0, stale_prompt: 0, locked_reference: 0 }}
        assetVersionCounts={{ all: 1, base_identity: 0, episode_default: 1, shot_variant: 0, location_variant: 0, prop_variant: 0 }}
        prioritizedAssets={[selectedAsset]}
        selectedAsset={selectedAsset}
        assetEpisodeInsights={new Map()}
        assetActionMessage=""
        assetActionTone="info"
        assetActionFollowUp={null}
        linkedShotDraft={[]}
        shotBindingState="idle"
        isGeneratingReference={false}
        recoveryFocus={{
          recoveryIntent: 'shot_variant_refinement',
          episode: 1,
          shotId: '13',
          assetId: selectedAsset.id,
          assetLabel: selectedAsset.title,
        }}
        onDismissRecoveryFocus={() => {}}
        onAssetEpisodeFilterChange={() => {}}
        onAssetCategoryFilterChange={() => {}}
        onAssetStatusFilterChange={() => {}}
        onAssetVersionFilterChange={() => {}}
        onAssetSearchQueryChange={() => {}}
        onSelectAsset={() => {}}
        onOpenPreview={() => {}}
        onGenerateReference={() => {}}
        onGenerateAssetReference={() => {}}
        onDeleteReferenceAsset={() => {}}
        onUpdateReferenceAssetStatus={() => {}}
        onNavigateSection={() => {}}
        onNavigateTaskSection={() => {}}
        onNavigateShot={() => {}}
        onToggleShotBinding={() => {}}
        onApplyInferredShotBindings={() => {}}
        onSaveShotBindings={() => {}}
      />,
    )

    expect(html).toContain('补分镜精调定妆')
    expect(html).toContain('镜头 13')
    expect(html).toContain('分镜精调')
  })

  it('offers switching to a sibling shot-variant asset during storyboard recovery', () => {
    const selectedAsset = buildAsset({
      variantScope: 'episode_default',
      siblingVariantCount: 2,
      siblingVariants: [
        {
          id: 'asset-character-1',
          label: '分集默认',
          stageName: '第 1 集默认造型',
          episode: 1,
          status: 'ref_ready',
          scope: 'episode_default',
        },
        {
          id: 'character-shot-13',
          label: '分镜精调',
          stageName: 'shot_13_episode_1',
          episode: 1,
          status: 'ref_ready',
          scope: 'shot_variant',
        },
      ],
    })

    const html = renderToStaticMarkup(
      <ProductWorkspaceAssetsSection
        bookId={14}
        allAssetsCount={1}
        shotEpisodes={[]}
        assetEpisodeFilter={1}
        assetCategoryFilter="character"
        assetStatusFilter="all"
        assetVersionFilter="shot_variant"
        assetSearchQuery=""
        assetCategoryCounts={{ all: 1, character: 1, location: 0, prop: 0 }}
        assetStatusCounts={{ all: 1, missing_reference: 0, pending_selection: 0, stale_prompt: 0, locked_reference: 0 }}
        assetVersionCounts={{ all: 1, base_identity: 0, episode_default: 1, shot_variant: 1, location_variant: 0, prop_variant: 0 }}
        prioritizedAssets={[selectedAsset]}
        selectedAsset={selectedAsset}
        assetEpisodeInsights={new Map()}
        assetActionMessage=""
        assetActionTone="info"
        assetActionFollowUp={null}
        linkedShotDraft={[]}
        shotBindingState="idle"
        isGeneratingReference={false}
        recoveryFocus={{
          recoveryIntent: 'shot_variant_refinement',
          episode: 1,
          shotId: '13',
          assetId: selectedAsset.id,
          assetLabel: selectedAsset.title,
        }}
        onDismissRecoveryFocus={() => {}}
        onAssetEpisodeFilterChange={() => {}}
        onAssetCategoryFilterChange={() => {}}
        onAssetStatusFilterChange={() => {}}
        onAssetVersionFilterChange={() => {}}
        onAssetSearchQueryChange={() => {}}
        onSelectAsset={() => {}}
        onOpenPreview={() => {}}
        onGenerateReference={() => {}}
        onGenerateAssetReference={() => {}}
        onDeleteReferenceAsset={() => {}}
        onUpdateReferenceAssetStatus={() => {}}
        onNavigateSection={() => {}}
        onNavigateTaskSection={() => {}}
        onNavigateShot={() => {}}
        onToggleShotBinding={() => {}}
        onApplyInferredShotBindings={() => {}}
        onSaveShotBindings={() => {}}
      />,
    )

    expect(html).toContain('切到分镜精调版本')
  })

  it('shows recovery detail for an already selected shot-variant asset', () => {
    const selectedAsset = buildAsset({
      variantScope: 'shot_variant',
      variantLabel: '分镜精调',
      variantStageName: 'shot_13_episode_1',
      subtitle: '镜头 13 版本',
      siblingVariantCount: 2,
      siblingVariants: [
        {
          id: 'asset-character-1',
          label: '分集默认',
          stageName: '第 1 集默认造型',
          episode: 1,
          status: 'ref_ready',
          scope: 'episode_default',
        },
        {
          id: 'asset-character-13',
          label: '分镜精调',
          stageName: 'shot_13_episode_1',
          episode: 1,
          status: 'ref_ready',
          scope: 'shot_variant',
        },
      ],
    })

    const html = renderToStaticMarkup(
      <ProductWorkspaceAssetsSection
        bookId={14}
        allAssetsCount={1}
        shotEpisodes={[]}
        assetEpisodeFilter={1}
        assetCategoryFilter="character"
        assetStatusFilter="all"
        assetVersionFilter="shot_variant"
        assetSearchQuery=""
        assetCategoryCounts={{ all: 1, character: 1, location: 0, prop: 0 }}
        assetStatusCounts={{ all: 1, missing_reference: 0, pending_selection: 0, stale_prompt: 0, locked_reference: 0 }}
        assetVersionCounts={{ all: 1, base_identity: 0, episode_default: 0, shot_variant: 1, location_variant: 0, prop_variant: 0 }}
        prioritizedAssets={[selectedAsset]}
        selectedAsset={selectedAsset}
        assetEpisodeInsights={new Map()}
        assetActionMessage=""
        assetActionTone="info"
        assetActionFollowUp={null}
        linkedShotDraft={[]}
        shotBindingState="idle"
        isGeneratingReference={false}
        recoveryFocus={{
          recoveryIntent: 'shot_variant_refinement',
          episode: 1,
          shotId: '13',
          assetId: selectedAsset.id,
          assetLabel: selectedAsset.title,
        }}
        onDismissRecoveryFocus={() => {}}
        onAssetEpisodeFilterChange={() => {}}
        onAssetCategoryFilterChange={() => {}}
        onAssetStatusFilterChange={() => {}}
        onAssetVersionFilterChange={() => {}}
        onAssetSearchQueryChange={() => {}}
        onSelectAsset={() => {}}
        onOpenPreview={() => {}}
        onGenerateReference={() => {}}
        onGenerateAssetReference={() => {}}
        onDeleteReferenceAsset={() => {}}
        onUpdateReferenceAssetStatus={() => {}}
        onNavigateSection={() => {}}
        onNavigateTaskSection={() => {}}
        onNavigateShot={() => {}}
        onToggleShotBinding={() => {}}
        onApplyInferredShotBindings={() => {}}
        onSaveShotBindings={() => {}}
      />,
    )

    expect(html).toContain('已经切到当前镜头对应的“分镜精调”版本')
    expect(html).not.toContain('切到分镜精调版本')
  })

  it('prioritizes generating current-shot references when the selected shot-variant has no preview image', () => {
    const selectedAsset = buildAsset({
      variantScope: 'shot_variant',
      variantLabel: '分镜精调',
      variantStageName: 'shot_13_episode_1',
      subtitle: '镜头 13 版本',
      previewCount: 0,
      referenceCount: 0,
      references: [],
    })

    const html = renderToStaticMarkup(
      <ProductWorkspaceAssetsSection
        bookId={14}
        allAssetsCount={1}
        shotEpisodes={[]}
        assetEpisodeFilter={1}
        assetCategoryFilter="character"
        assetStatusFilter="all"
        assetVersionFilter="shot_variant"
        assetSearchQuery=""
        assetCategoryCounts={{ all: 1, character: 1, location: 0, prop: 0 }}
        assetStatusCounts={{ all: 1, missing_reference: 1, pending_selection: 0, stale_prompt: 0, locked_reference: 0 }}
        assetVersionCounts={{ all: 1, base_identity: 0, episode_default: 0, shot_variant: 1, location_variant: 0, prop_variant: 0 }}
        prioritizedAssets={[selectedAsset]}
        selectedAsset={selectedAsset}
        assetEpisodeInsights={new Map()}
        assetActionMessage=""
        assetActionTone="info"
        assetActionFollowUp={null}
        linkedShotDraft={[]}
        shotBindingState="idle"
        isGeneratingReference={false}
        recoveryFocus={{
          recoveryIntent: 'shot_variant_refinement',
          episode: 1,
          shotId: '13',
          assetId: selectedAsset.id,
          assetLabel: selectedAsset.title,
        }}
        onDismissRecoveryFocus={() => {}}
        onAssetEpisodeFilterChange={() => {}}
        onAssetCategoryFilterChange={() => {}}
        onAssetStatusFilterChange={() => {}}
        onAssetVersionFilterChange={() => {}}
        onAssetSearchQueryChange={() => {}}
        onSelectAsset={() => {}}
        onOpenPreview={() => {}}
        onGenerateReference={() => {}}
        onGenerateAssetReference={() => {}}
        onDeleteReferenceAsset={() => {}}
        onUpdateReferenceAssetStatus={() => {}}
        onNavigateSection={() => {}}
        onNavigateTaskSection={() => {}}
        onNavigateShot={() => {}}
        onToggleShotBinding={() => {}}
        onApplyInferredShotBindings={() => {}}
        onSaveShotBindings={() => {}}
      />,
    )

    expect(html).toContain('当前镜头精调版本还没有参考图')
    expect(html).toContain('生成当前镜头参考图')
  })

  it('shows a task-center follow-up CTA after reference generation enters recovery flow', () => {
    const selectedAsset = buildAsset()
    const html = renderToStaticMarkup(
      <ProductWorkspaceAssetsSection
        bookId={14}
        allAssetsCount={1}
        shotEpisodes={[]}
        assetEpisodeFilter={1}
        assetCategoryFilter="character"
        assetStatusFilter="all"
        assetVersionFilter="all"
        assetSearchQuery=""
        assetCategoryCounts={{ all: 1, character: 1, location: 0, prop: 0 }}
        assetStatusCounts={{ all: 1, missing_reference: 0, pending_selection: 0, stale_prompt: 0, locked_reference: 0 }}
        assetVersionCounts={{ all: 1, base_identity: 0, episode_default: 1, shot_variant: 0, location_variant: 0, prop_variant: 0 }}
        prioritizedAssets={[selectedAsset]}
        selectedAsset={selectedAsset}
        assetEpisodeInsights={new Map()}
        assetActionMessage="参考图任务 task-ref-13 仍在执行，请去任务中心继续回收结果。"
        assetActionTone="info"
        assetActionFollowUp={{
          mode: 'tasks',
          label: '去任务中心继续回收',
          taskId: 'task-ref-13',
          episode: 1,
          shotId: '13',
          assetId: selectedAsset.id,
        }}
        linkedShotDraft={[]}
        shotBindingState="idle"
        isGeneratingReference={false}
        onDismissRecoveryFocus={() => {}}
        onAssetEpisodeFilterChange={() => {}}
        onAssetCategoryFilterChange={() => {}}
        onAssetStatusFilterChange={() => {}}
        onAssetVersionFilterChange={() => {}}
        onAssetSearchQueryChange={() => {}}
        onSelectAsset={() => {}}
        onOpenPreview={() => {}}
        onGenerateReference={() => {}}
        onGenerateAssetReference={() => {}}
        onDeleteReferenceAsset={() => {}}
        onUpdateReferenceAssetStatus={() => {}}
        onNavigateSection={() => {}}
        onNavigateTaskSection={() => {}}
        onNavigateShot={() => {}}
        onToggleShotBinding={() => {}}
        onApplyInferredShotBindings={() => {}}
        onSaveShotBindings={() => {}}
      />,
    )

    expect(html).toContain('去任务中心继续回收')
  })

  it('offers actionable recovery CTAs when the selected asset has pending shot runtime tasks', () => {
    const selectedAsset = buildAsset({ shotIds: [] })
    const storage = new Map<string, string>()
    storage.set(
      'product-workspace.shot-execution-summary.14',
      JSON.stringify([
        {
          episode: 1,
          shotId: '3',
          action: 'frame',
          label: '生成首帧',
          updatedAt: '2026-07-29T18:35:00.000Z',
        },
      ]),
    )
    storage.set(
      'product-workspace.pending-storyboard-tasks.14',
      JSON.stringify([
        {
          taskId: 'runtime-verify-pending-001',
          episode: 1,
          shotId: '3',
          kind: 'video',
          updatedAt: '2026-07-29T18:35:05.000Z',
        },
      ]),
    )

    const previousWindow = (globalThis as any).window
    ;(globalThis as any).window = {
      localStorage: {
        getItem(key: string) {
          return storage.get(key) ?? null
        },
        setItem(key: string, value: string) {
          storage.set(key, value)
        },
        removeItem(key: string) {
          storage.delete(key)
        },
      },
    }

    try {
      const html = renderSection(
        selectedAsset,
        new Map([
          [
            selectedAsset.id,
            {
              shotIds: ['1-3'],
              blockerCount: 0,
              missingReference: false,
              impactShots: [
                {
                  shotId: '3',
                  episode: 1,
                  sceneName: '井边',
                  blockerCount: 0,
                  statusLabel: '已就绪',
                  nextAction: '继续回收',
                  missingItems: [],
                },
              ],
            },
          ],
        ]),
      )

      expect(html).toContain('关联镜头运行态')
      expect(html).toContain('去任务中心继续回收')
      expect(html).toContain('去镜头工作台定位镜头')
      expect(html).toContain('继续回收')
      expect(html).toContain('runtime-verify-pending-001')
    } finally {
      ;(globalThis as any).window = previousWindow
    }
  })

  it('builds a generate-reference primary action for missing asset previews', () => {
    const selectedAsset = buildAsset({ previewCount: 0, referenceCount: 0, references: [] })

    expect(
      buildAssetCanvasPrimaryActionPlan({
        selectedAsset,
        selectedAssetRuntimePrimaryTask: null,
        shouldOfferShotVariantSwitch: false,
        hasMissingReference: true,
        hasStaleReferencePrompt: false,
        hasUnsyncedBindings: false,
        draftAlreadyCoversUnsyncedBindings: false,
      }),
    ).toEqual({
      action: 'generate_reference',
      label: '生成当前版本参考图',
      detail: '当前资产还没有可预览参考图，建议先补图，再继续镜头编译和出图链路。',
    })
  })

  it('builds a task-recovery primary action when runtime tasks exist', () => {
    const selectedAsset = buildAsset()

    expect(
      buildAssetCanvasPrimaryActionPlan({
        selectedAsset,
        selectedAssetRuntimePrimaryTask: {
          taskId: 'task-video-1',
          shotLabel: '第 1 集 / 镜头 3',
          kindLabel: '视频任务',
          episode: 1,
          shotId: '3',
          kind: 'video',
        },
        shouldOfferShotVariantSwitch: false,
        hasMissingReference: false,
        hasStaleReferencePrompt: false,
        hasUnsyncedBindings: false,
        draftAlreadyCoversUnsyncedBindings: false,
      }),
    ).toEqual({
      action: 'tasks',
      label: '去任务中心继续回收',
      detail: '当前资产仍有关联待回收任务，建议先把 第 1 集 / 镜头 3 的 视频任务 结果收回来。',
    })
  })

  it('renders canvas handoff primary action inside asset detail', () => {
    const selectedAsset = buildAsset({ previewCount: 0, referenceCount: 0, references: [] })
    const html = renderToStaticMarkup(
      <ProductWorkspaceAssetsSection
        bookId={14}
        allAssetsCount={1}
        shotEpisodes={[]}
        assetEpisodeFilter={1}
        assetCategoryFilter="character"
        assetStatusFilter="all"
        assetVersionFilter="all"
        assetSearchQuery=""
        assetCategoryCounts={{ all: 1, character: 1, location: 0, prop: 0 }}
        assetStatusCounts={{ all: 1, missing_reference: 1, pending_selection: 0, stale_prompt: 0, locked_reference: 0 }}
        assetVersionCounts={{ all: 1, base_identity: 0, episode_default: 1, shot_variant: 0, location_variant: 0, prop_variant: 0 }}
        prioritizedAssets={[selectedAsset]}
        selectedAsset={selectedAsset}
        assetEpisodeInsights={new Map()}
        assetActionMessage=""
        assetActionTone="info"
        assetActionFollowUp={null}
        linkedShotDraft={[]}
        shotBindingState="idle"
        isGeneratingReference={false}
        canvasHandoff={{
          target: 'assets',
          episode: 1,
          shotId: '13',
          assetId: selectedAsset.id,
          assetLabel: selectedAsset.title,
        }}
        onAssetEpisodeFilterChange={() => {}}
        onAssetCategoryFilterChange={() => {}}
        onAssetStatusFilterChange={() => {}}
        onAssetVersionFilterChange={() => {}}
        onAssetSearchQueryChange={() => {}}
        onSelectAsset={() => {}}
        onOpenPreview={() => {}}
        onGenerateReference={() => {}}
        onGenerateAssetReference={() => {}}
        onDeleteReferenceAsset={() => {}}
        onUpdateReferenceAssetStatus={() => {}}
        onNavigateSection={() => {}}
        onNavigateTaskSection={() => {}}
        onNavigateShot={() => {}}
        onToggleShotBinding={() => {}}
        onApplyInferredShotBindings={() => {}}
        onSaveShotBindings={() => {}}
      />,
    )

    expect(html).toContain('创作画布承接中')
    expect(html).toContain('承接后的首个动作')
    expect(html).toContain('生成当前版本参考图')
  })

  it('shows pending recovery timestamp and latest source summary in asset runtime state', () => {
    const selectedAsset = buildAsset()
    const storage = new Map<string, string>()
    storage.set(
      'product-workspace.pending-storyboard-tasks.14',
      JSON.stringify([
        {
          taskId: 'runtime-verify-video-002',
          episode: 1,
          shotId: '3',
          kind: 'video',
          updatedAt: '2026-07-29T18:36:00.000Z',
          assetLabel: '姐姐 / 夜戏造型',
        },
        {
          taskId: 'runtime-verify-prompt-003',
          episode: 1,
          shotId: '3',
          kind: 'prompt',
          updatedAt: '2026-07-29T18:35:30.000Z',
        },
      ]),
    )

    const previousWindow = (globalThis as any).window
    ;(globalThis as any).window = {
      localStorage: {
        getItem(key: string) {
          return storage.get(key) ?? null
        },
        setItem(key: string, value: string) {
          storage.set(key, value)
        },
        removeItem(key: string) {
          storage.delete(key)
        },
      },
    }

    try {
      const html = renderSection(
        selectedAsset,
        new Map([
          [
            selectedAsset.id,
            {
              shotIds: ['1-3'],
              blockerCount: 0,
              missingReference: false,
              impactShots: [
                {
                  shotId: '3',
                  episode: 1,
                  sceneName: '井边',
                  blockerCount: 0,
                  statusLabel: '已就绪',
                  nextAction: '继续回收',
                  missingItems: [],
                },
              ],
            },
          ],
        ]),
      )

      expect(html).toContain('待回收更新于')
      expect(html).toContain('最近待回收来源：视频 / 第 1 集 / 镜头 3')
      expect(html).toContain('视频 / 提示词编译')
      expect(html).toContain('runtime-verify-video-002')
    } finally {
      ;(globalThis as any).window = previousWindow
    }
  })
})
