import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import ProductWorkspaceAssetsSection from './ProductWorkspaceAssetsSection'
import type { AssetSummary } from './productWorkspaceAssets'

function buildAsset(overrides: Partial<AssetSummary> = {}): AssetSummary {
  return {
    id: 'asset-scene-1',
    category: 'location',
    assetRecordId: 201,
    title: '寺庙后院水房',
    subtitle: '场景资产',
    status: 'ref_ready',
    prompt: '',
    shotIds: ['1', '2', '3'],
    episodeIds: [1],
    referenceCount: 0,
    previewCount: 0,
    selectedReferenceCount: 0,
    lockedReferenceCount: 0,
    staleReferenceCount: 0,
    hasStaleReferencePrompt: false,
    references: [],
    ...overrides,
  }
}

describe('ProductWorkspaceAssetsSection canvas handoff priority', () => {
  it('prioritizes canvas handoff guidance over stale recovery focus banners', () => {
    const selectedAsset = buildAsset()
    const html = renderToStaticMarkup(
      <ProductWorkspaceAssetsSection
        bookId={14}
        allAssetsCount={1}
        shotEpisodes={[]}
        assetEpisodeFilter={1}
        assetCategoryFilter="location"
        assetStatusFilter="all"
        assetVersionFilter="all"
        assetSearchQuery=""
        assetCategoryCounts={{ all: 1, character: 0, location: 1, prop: 0 }}
        assetStatusCounts={{ all: 1, missing_reference: 1, pending_selection: 0, stale_prompt: 0, locked_reference: 0 }}
        assetVersionCounts={{ all: 1, base_identity: 0, episode_default: 0, shot_variant: 0, location_variant: 1, prop_variant: 0 }}
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
          shotId: '1',
          assetId: selectedAsset.id,
          assetLabel: selectedAsset.title,
        }}
        recoveryFocus={{
          taskId: 'task-legacy-1',
          recoveryKind: 'reference',
          recoveryIntent: 'reference',
          episode: 1,
          shotId: '1',
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

    expect(html).toContain('创作画布承接中')
    expect(html).not.toContain('已从任务中心恢复到当前资产')
  })
})
