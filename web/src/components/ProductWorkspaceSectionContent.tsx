import { lazy, Suspense } from 'react'
import type { RecoveryFocusContext } from './productWorkspaceAssetViewController'
import type { CanvasHandoffTarget, ProductWorkspaceSectionContentProps } from './productWorkspaceSectionContracts'
import WorkspaceSectionErrorBoundary from './WorkspaceSectionErrorBoundary'

const ProductWorkspaceAdaptationSection = lazy(() => import('./ProductWorkspaceAdaptationSection'))
const ProductWorkspaceAssetsSection = lazy(() => import('./ProductWorkspaceAssetsSection'))
const ProductWorkspaceCanvasBetaSection = lazy(() => import('./ProductWorkspaceCanvasBetaSection'))
const ProductWorkspaceContentSection = lazy(() => import('./ProductWorkspaceContentSection'))
const CharacterQAPanel = lazy(() => import('./CharacterQAPanel'))
const ProductWorkspaceDashboardSection = lazy(() => import('./ProductWorkspaceDashboardSection'))
const ProductWorkspaceDeliverySection = lazy(() => import('./ProductWorkspaceDeliverySection'))
const ProductWorkspaceModelsSection = lazy(() => import('./ProductWorkspaceModelsSection'))
const ProductWorkspaceQaSection = lazy(() => import('./ProductWorkspaceQaSection'))
const ProductWorkspaceScriptsSection = lazy(() => import('./ProductWorkspaceScriptsSection'))
const ProductWorkspaceStoryboardSection = lazy(() => import('./ProductWorkspaceStoryboardSection'))
const ProductWorkspaceTasksSection = lazy(() => import('./ProductWorkspaceTasksSection'))

function toStoryboardRecoveryFocus(recoveryFocus: RecoveryFocusContext | null) {
  if (recoveryFocus?.target !== 'storyboard') return null
  return {
    taskId: recoveryFocus.taskId ?? null,
    recoveryKind: recoveryFocus.recoveryKind ?? null,
    episode: recoveryFocus.episode ?? null,
    shotId: recoveryFocus.shotId ?? null,
  }
}

function toAssetsRecoveryFocus(recoveryFocus: RecoveryFocusContext | null) {
  if (recoveryFocus?.target !== 'assets') return null
  return {
    taskId: recoveryFocus.taskId ?? null,
    recoveryKind: recoveryFocus.recoveryKind ?? null,
    recoveryIntent: recoveryFocus.recoveryIntent ?? null,
    episode: recoveryFocus.episode ?? null,
    shotId: recoveryFocus.shotId ?? null,
    assetId: recoveryFocus.assetId ?? null,
    assetLabel: recoveryFocus.assetLabel ?? null,
  }
}

function formatHandoffEpisodeLabel(episode?: number | null) {
  return typeof episode === 'number' && Number.isFinite(episode) ? `第 ${episode} 集` : '跨集'
}

export function buildCanvasHandoffSummary(handoff: CanvasHandoffTarget | null) {
  if (!handoff) return null

  const contextParts = [formatHandoffEpisodeLabel(handoff.episode)]
  if (handoff.shotId) contextParts.push(`镜头 ${handoff.shotId}`)
  if (handoff.assetLabel) contextParts.push(handoff.assetLabel)

  const defaultLabelMap: Record<CanvasHandoffTarget['target'], string> = {
    storyboard: '前往镜头工作台继续这个镜头的创作',
    assets: handoff.shotId ? '前往资产中心补齐该镜头参考图' : '前往资产中心确认资产引用状态',
    qa: '前往 QA 修复处理当前上下文问题',
    delivery: '前往导出中心确认当前集交付状态',
  }

  const defaultDetailMap: Record<CanvasHandoffTarget['target'], string> = {
    storyboard: '当前上下文已经从创作画布切到镜头工作台，适合直接继续提示词、首帧和视频链路。',
    assets: handoff.shotId
      ? '当前上下文已经带着具体镜头与资产进入资产中心，可以直接补图、校验版本并确认下游引用。'
      : '当前上下文已经从创作画布落到资产中心，可以继续整理参考图、版本和命中关系。',
    qa: '当前上下文已经从创作画布落到 QA 修复，可直接围绕这一集或镜头继续核查问题。',
    delivery: '当前上下文已经从创作画布落到导出中心，可直接确认当前集的阻塞项与交付放行状态。',
  }

  return {
    title: `当前承接：${contextParts.join(' / ')}`,
    label: handoff.handoffLabel || defaultLabelMap[handoff.target],
    detail: handoff.handoffDetail || defaultDetailMap[handoff.target],
  }
}

function CanvasHandoffBanner({ handoff }: { handoff: CanvasHandoffTarget | null }) {
  const summary = buildCanvasHandoffSummary(handoff)
  if (!summary) return null

  return (
    <div className="mb-5 rounded-xl border border-fuchsia-500/30 bg-fuchsia-500/10 p-4">
      <div className="text-xs font-medium tracking-wide text-fuchsia-200">来自创作画布的下一步</div>
      <div className="mt-2 text-sm font-medium text-white">{summary.title}</div>
      <div className="mt-2 text-sm text-fuchsia-100">{summary.label}</div>
      <div className="mt-2 text-xs leading-6 text-fuchsia-100/80">{summary.detail}</div>
    </div>
  )
}

function SectionLoadingFallback() {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 text-sm text-slate-400">
      正在加载工作区...
    </div>
  )
}

export default function ProductWorkspaceSectionContent({
  section,
  dashboard,
  content,
  adaptation,
  scripts,
  storyboard,
  canvas,
  assets,
  qa,
  tasks,
  delivery,
  preview,
}: ProductWorkspaceSectionContentProps) {
  return (
    <Suspense fallback={<SectionLoadingFallback />}>
      {section === 'dashboard' ? (
        <ProductWorkspaceDashboardSection
          summary={{
            contentReady: dashboard.summary.contentReady,
            chapterCount: dashboard.summary.chapterCount,
            wordCount: dashboard.summary.wordCount,
            episodesWithScripts: dashboard.summary.episodesWithScripts,
            totalShots: dashboard.summary.totalShots,
            visualCount: dashboard.summary.visualCount,
            qaCount: dashboard.summary.qaCount,
          }}
          adaptationStateLabel={dashboard.adaptationStateLabel}
          adaptationStateDetail={dashboard.adaptationStateDetail}
          episodeProgress={dashboard.episodeProgress}
          dashboardActions={dashboard.dashboardActions}
          onNavigate={dashboard.onNavigateSection}
        />
      ) : null}

      {section === 'content' ? (
        <ProductWorkspaceContentSection
          bookId={content.bookId}
          contentReady={content.summary.contentReady}
          contentStatusLabel={content.summary.contentSummary.label}
          contentStatusDetail={content.summary.contentSummary.detail}
          chapterCount={content.summary.chapterCount}
          wordCount={content.summary.wordCount}
          projectStatus={content.summary.projectStatus}
          uploadFile={content.uploadFile}
          episodeCount={content.episodeCount}
          shortTitle={content.shortTitle}
          shortText={content.shortText}
          productionSkill={content.productionSkill}
          contentTask={content.contentTask}
          onOpenModelSettings={content.onOpenModelSettings}
          onUploadFileChange={content.onUploadFileChange}
          onEpisodeCountChange={content.onEpisodeCountChange}
          onShortTitleChange={content.onShortTitleChange}
          onShortTextChange={content.onShortTextChange}
          onSubmitNovelUpload={content.onSubmitNovelUpload}
          onSubmitShortCreate={content.onSubmitShortCreate}
        />
      ) : null}

      {section === 'adaptation' ? (
        <ProductWorkspaceAdaptationSection
          contentReady={adaptation.contentReady}
          productionSkill={adaptation.productionSkill}
          adaptationOptions={adaptation.adaptationOptions}
          selectedAdaptationId={adaptation.selectedAdaptationId}
          selectedAdaptationName={adaptation.selectedAdaptationName}
          adaptationCustomNote={adaptation.adaptationCustomNote}
          hasLockedAdaptation={adaptation.hasLockedAdaptation}
          adaptationStateLabel={adaptation.adaptationStateLabel}
          adaptationStateDetail={adaptation.adaptationStateDetail}
          canGenerateCandidates={adaptation.canGenerateCandidates}
          canLockAdaptation={adaptation.canLockAdaptation}
          canLockProductionSkill={adaptation.canLockProductionSkill}
          onSelectProductionSkill={adaptation.onSelectProductionSkill}
          onProductionSkillFieldChange={adaptation.onProductionSkillFieldChange}
          onToggleProductionSkillPriority={adaptation.onToggleProductionSkillPriority}
          onLockProductionSkill={adaptation.onLockProductionSkill}
          onUnlockProductionSkill={adaptation.onUnlockProductionSkill}
          onRegenerate={adaptation.onRegenerateAdaptation}
          onSelect={adaptation.onSelectAdaptation}
          onCustomNoteChange={adaptation.onAdaptationCustomNoteChange}
          onLock={adaptation.onLockAdaptation}
          onUnlock={adaptation.onUnlockAdaptation}
          onNavigateSection={adaptation.onNavigateSection}
        />
      ) : null}

      {section === 'characters' ? (
        <CharacterQAPanel bookId={scripts.bookId} />
      ) : null}

      {section === 'scripts' ? (
        <ProductWorkspaceScriptsSection
          bookId={scripts.bookId}
          scripts={scripts.scripts}
          shotsByEpisode={scripts.shotsByEpisode}
          episodeProgress={scripts.episodeProgress}
          scriptDecisionState={scripts.scriptDecisionState}
          onScriptDecisionStateChange={scripts.onScriptDecisionStateChange}
          hasLockedAdaptation={scripts.hasLockedAdaptation}
          hasExplicitLockedAdaptation={scripts.hasExplicitLockedAdaptation}
          adaptationStateLabel={scripts.adaptationStateLabel}
          adaptationStateDetail={scripts.adaptationStateDetail}
          selectedAdaptationName={scripts.selectedAdaptationName}
          onNavigate={scripts.onNavigateTaskSection}
          onGenerateScripts={scripts.onGenerateScripts}
          isGeneratingScripts={scripts.isGeneratingScripts}
        />
      ) : null}

      {section === 'storyboard' ? (
        <>
          <CanvasHandoffBanner handoff={storyboard.canvasHandoff} />
          <ProductWorkspaceStoryboardSection
            bookId={storyboard.bookId}
            shotsByEpisode={storyboard.shotsByEpisode}
            scriptDecisionState={storyboard.scriptDecisionState}
            hasExplicitLockedAdaptation={storyboard.hasExplicitLockedAdaptation}
            selectedShotId={storyboard.selectedStoryboardShotId}
            onSelectShot={storyboard.onSelectShot}
            onRefresh={storyboard.onRefreshAll}
            canvasHandoff={storyboard.canvasHandoff}
            recoveryFocus={toStoryboardRecoveryFocus(storyboard.recoveryFocus)}
            onDismissRecoveryFocus={storyboard.onDismissStoryboardRecoveryFocus}
            onNavigateSection={storyboard.onNavigateSection}
            onNavigateTaskSection={storyboard.onNavigateTaskSection}
            onGenerateStoryboard={storyboard.onGenerateStoryboard}
            isGeneratingStoryboard={storyboard.isGeneratingStoryboard}
          />
        </>
      ) : null}

      {section === 'canvas' ? (
        <ProductWorkspaceCanvasBetaSection
          bookId={canvas.bookId}
          bookTitle={canvas.bookTitle}
          isProjectDataLoading={canvas.isProjectDataLoading}
          scripts={canvas.scripts}
          shotsByEpisode={canvas.shotsByEpisode}
          allAssets={canvas.allAssets}
          qaEntries={canvas.qaEntries}
          navigationTarget={canvas.navigationTarget}
          onRefreshAll={canvas.onRefreshAll}
          onNavigateTaskSection={canvas.onNavigateTaskSection}
        />
      ) : null}

      {section === 'assets' ? (
        <>
          <CanvasHandoffBanner handoff={assets.canvasHandoff} />
          <ProductWorkspaceAssetsSection
            bookId={assets.bookId}
            allAssetsCount={assets.allAssetsCount}
            shotEpisodes={assets.shotEpisodes}
            assetEpisodeFilter={assets.assetEpisodeFilter}
            assetCategoryFilter={assets.assetCategoryFilter}
            assetStatusFilter={assets.assetStatusFilter}
            assetVersionFilter={assets.assetVersionFilter}
            assetSearchQuery={assets.assetSearchQuery}
            assetCategoryCounts={assets.assetCategoryCounts}
            assetStatusCounts={assets.assetStatusCounts}
            assetVersionCounts={assets.assetVersionCounts}
            prioritizedAssets={assets.prioritizedAssets}
            selectedAsset={assets.selectedAsset}
            assetEpisodeInsights={assets.assetEpisodeInsights}
            assetActionMessage={assets.assetActionMessage}
            assetActionTone={assets.assetActionTone}
            assetActionFollowUp={assets.assetActionFollowUp}
            linkedShotDraft={assets.linkedShotDraft}
            shotBindingState={assets.shotBindingState}
            isGeneratingReference={assets.isGeneratingReference}
            canvasHandoff={assets.canvasHandoff}
            onAssetEpisodeFilterChange={assets.onAssetEpisodeFilterChange}
            onAssetCategoryFilterChange={assets.onAssetCategoryFilterChange}
            onAssetStatusFilterChange={assets.onAssetStatusFilterChange}
            onAssetVersionFilterChange={assets.onAssetVersionFilterChange}
            onAssetSearchQueryChange={assets.onAssetSearchQueryChange}
            onSelectAsset={assets.onSelectAsset}
            onOpenPreview={assets.onOpenAssetPreview}
            recoveryFocus={toAssetsRecoveryFocus(assets.recoveryFocus)}
            onDismissRecoveryFocus={assets.onDismissAssetsRecoveryFocus}
            onGenerateReference={assets.onGenerateReference}
            onGenerateAssetReference={assets.onGenerateAssetReference}
            onDeleteReferenceAsset={assets.onDeleteReferenceAsset}
            onUpdateReferenceAssetStatus={assets.onUpdateReferenceAssetStatus}
            onNavigateSection={assets.onNavigateSection}
            onNavigateTaskSection={assets.onNavigateTaskSection}
            onNavigateShot={assets.onNavigateAssetShot}
            onToggleShotBinding={assets.onToggleShotBinding}
            onApplyInferredShotBindings={assets.onApplyInferredShotBindings}
            onSaveShotBindings={assets.onSaveShotBindings}
          />
        </>
      ) : null}

      {section === 'qa' ? (
        <>
          <CanvasHandoffBanner handoff={qa.canvasHandoff} />
          <ProductWorkspaceQaSection
            bookId={qa.bookId}
            scripts={qa.scripts}
            scriptDecisionState={qa.scriptDecisionState}
            hasExplicitLockedAdaptation={qa.hasExplicitLockedAdaptation}
            qaEntries={qa.qaEntries}
            shotsByEpisode={qa.shotsByEpisode}
            qaNavigationTarget={qa.qaNavigationTarget}
            canvasHandoff={qa.canvasHandoff}
            onNavigate={qa.onNavigateSection}
            onSelectShot={qa.onSelectShot}
          />
        </>
      ) : null}

      {section === 'tasks' ? (
        <ProductWorkspaceTasksSection
          bookId={tasks.bookId}
          contentReady={tasks.contentReady}
          adaptationLocked={tasks.adaptationLocked}
          adaptationReadyForDownstream={tasks.adaptationReadyForDownstream}
          contentTask={tasks.contentTask}
          scripts={tasks.scripts}
          scriptDecisionState={tasks.scriptDecisionState}
          shotsByEpisode={tasks.shotsByEpisode}
          qaEntries={tasks.qaEntries}
          navigationTarget={tasks.taskNavigationTarget}
          onRefresh={tasks.onRefreshAll}
          onNavigate={tasks.onNavigateTaskSection}
        />
      ) : null}

      {section === 'delivery' ? (
        <WorkspaceSectionErrorBoundary sectionLabel="导出中心">
          <>
            <CanvasHandoffBanner handoff={delivery.canvasHandoff} />
            <ProductWorkspaceDeliverySection
              bookId={delivery.bookId}
              isProjectDataLoading={delivery.isProjectDataLoading}
              bookTitle={delivery.bookTitle}
              chapterCount={delivery.chapterCount}
              wordCount={delivery.wordCount}
              contentStatusLabel={delivery.contentStatusLabel}
              contentStatusDetail={delivery.contentStatusDetail}
              adaptationStateLabel={delivery.adaptationStateLabel}
              adaptationStateDetail={delivery.adaptationStateDetail}
              selectedAdaptationName={delivery.selectedAdaptationName}
              adaptationCustomNote={delivery.adaptationCustomNote}
              adaptationLockedAt={delivery.adaptationLockedAt}
              scripts={delivery.scripts}
              scriptDecisionState={delivery.scriptDecisionState}
              shotsByEpisode={delivery.shotsByEpisode}
              qaEntries={delivery.qaEntries}
              makeups={delivery.makeups}
              locations={delivery.locations}
              props={delivery.props}
              canvasHandoff={delivery.canvasHandoff}
              onNavigate={delivery.onNavigateTaskSection}
            />
          </>
        </WorkspaceSectionErrorBoundary>
      ) : null}

      {section === 'models' ? <ProductWorkspaceModelsSection /> : null}

      {preview.assetPreviewUrl ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 px-6 py-10"
          onClick={preview.onCloseAssetPreview}
        >
          <div
            className="max-h-full w-full max-w-5xl overflow-hidden rounded-xl border border-slate-700 bg-slate-950 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-white">
                  {preview.assetPreviewLabel || '参考图预览'}
                </div>
                <div className="mt-1 text-xs text-slate-500">资产中心参考图预览</div>
              </div>
              <button
                type="button"
                onClick={preview.onCloseAssetPreview}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
              >
                关闭
              </button>
            </div>
            <div className="flex max-h-[80vh] items-center justify-center bg-slate-900 p-4">
              <img
                src={preview.assetPreviewUrl}
                alt={preview.assetPreviewLabel || '参考图预览'}
                className="max-h-[72vh] w-auto max-w-full rounded-lg object-contain"
              />
            </div>
          </div>
        </div>
      ) : null}
    </Suspense>
  )
}
