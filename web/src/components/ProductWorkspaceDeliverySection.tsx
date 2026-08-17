import { useEffect, useMemo, useState } from 'react'
import type {
  ScriptOutput,
  StoryboardShotOutput,
  VisualLocationOutput,
  VisualMakeupOutput,
  VisualPropOutput,
} from '../prototyping/sceneComposerData'
import {
  buildDeliveryFileStem,
  buildDeliveryExportPackage,
  buildDeliveryExportSummaryText,
  buildDeliveryFinalDraftDocument,
  buildDeliveryEpisodeReadiness,
  buildDeliveryWordDocument,
  deriveDeliveryRecordRepairActions,
  isLikelyCorruptedDeliveryText,
  normalizeDeliveryRecordFormatLabel,
  summarizeDeliveryPackage,
  summarizeDeliveryRecordHistory,
  type DeliveryBlockedItem,
  type DeliveryEpisodeReadiness,
  type DeliveryRecord,
} from './productWorkspaceDelivery'
import type { ScriptDecisionMap } from './productWorkspaceScriptDecisions'
import type { CanvasHandoffTarget, TaskNavigateHandler } from './productWorkspaceSectionContracts'

type RecordState = 'idle' | 'loading' | 'saving' | 'saved' | 'error'
type ExportRecordApi = Record<string, any>

type DeliveryCanvasPrimaryActionPlan =
  | { action: 'repair_blocker'; label: string; detail: string }
  | { action: 'save_record'; label: string; detail: string }
  | { action: 'export_json'; label: string; detail: string }

interface Props {
  bookId: number
  isProjectDataLoading: boolean
  bookTitle: string
  chapterCount: number
  wordCount: number
  contentStatusLabel: string
  contentStatusDetail: string
  adaptationStateLabel: string
  adaptationStateDetail: string
  selectedAdaptationName?: string
  adaptationCustomNote?: string
  adaptationLockedAt?: string | null
  scripts: ScriptOutput[]
  scriptDecisionState: ScriptDecisionMap
  shotsByEpisode: Record<number, StoryboardShotOutput[]>
  qaEntries: Array<{ episode: number; error_count?: number }>
  makeups: VisualMakeupOutput[]
  locations: VisualLocationOutput[]
  props: VisualPropOutput[]
  canvasHandoff?: CanvasHandoffTarget | null
  onNavigate: TaskNavigateHandler
}

export function buildDeliveryCanvasHandoffSummary(input: {
  handoff?: CanvasHandoffTarget | null
  readiness?: DeliveryEpisodeReadiness | null
}) {
  const handoff = input.handoff
  if (!handoff) return null

  const readiness = input.readiness
  const episode =
    typeof readiness?.episode === 'number' && Number.isFinite(readiness.episode)
      ? readiness.episode
      : handoff.episode ?? null

  return {
    title:
      typeof episode === 'number' && Number.isFinite(episode)
        ? `已从创作画布定位到 第 ${episode} 集交付`
        : '已从创作画布定位到当前交付上下文',
    label: handoff.handoffLabel || '继续确认当前集交付状态',
    detail:
      handoff.handoffDetail ||
      '当前交付上下文已经根据创作画布自动定位，可以直接继续确认阻塞项、生成交付记录或导出交付快照。',
  }
}

export function buildDeliveryCanvasPrimaryActionPlan(input: {
  readiness: DeliveryEpisodeReadiness | null
  primaryBlockedItem: DeliveryBlockedItem | null
  episodeRecordCount: number
}) {
  const readiness = input.readiness
  if (!readiness) return null

  if (input.primaryBlockedItem) {
    return {
      action: 'repair_blocker',
      label: buildBlockedItemActionLabel(input.primaryBlockedItem),
      detail: `当前集仍存在首个交付阻塞项“${input.primaryBlockedItem.label}”，先回到对应模块处理，再继续交付链路。`,
    } satisfies DeliveryCanvasPrimaryActionPlan
  }

  if (input.episodeRecordCount <= 0) {
    return {
      action: 'save_record',
      label: '先生成交付记录',
      detail: '当前集已经具备交付条件，建议先沉淀一版交付记录，收口本次交付状态与版本快照。',
    } satisfies DeliveryCanvasPrimaryActionPlan
  }

  return {
    action: 'export_json',
    label: '导出 JSON 并登记',
    detail: '当前集已有交付记录，下一步更适合继续导出结构化交付快照，供下游协作与回溯使用。',
  } satisfies DeliveryCanvasPrimaryActionPlan
}

export default function ProductWorkspaceDeliverySection({
  bookId,
  isProjectDataLoading,
  bookTitle,
  chapterCount,
  wordCount,
  contentStatusLabel,
  contentStatusDetail,
  adaptationStateLabel,
  adaptationStateDetail,
  selectedAdaptationName,
  adaptationCustomNote,
  adaptationLockedAt,
  scripts,
  scriptDecisionState,
  shotsByEpisode,
  qaEntries,
  makeups,
  locations,
  props,
  canvasHandoff,
  onNavigate,
}: Props) {
  const [rawRecords, setRawRecords] = useState<ExportRecordApi[]>([])
  const [selectedEpisode, setSelectedEpisode] = useState<number | null>(null)
  const [recordState, setRecordState] = useState<RecordState>('idle')
  const [recordMessage, setRecordMessage] = useState('')

  const readinessList = useMemo(
    () =>
      buildDeliveryEpisodeReadiness({
        hasExplicitLockedAdaptation: Boolean(adaptationLockedAt),
        scripts,
        scriptDecisionState,
        shotsByEpisode,
        qaEntries,
        makeups,
        locations,
        props,
      }),
    [scripts, scriptDecisionState, shotsByEpisode, qaEntries, makeups, locations, props],
  )

  const selectedReadiness = useMemo(
    () => readinessList.find((item) => item.episode === selectedEpisode) ?? readinessList[0] ?? null,
    [readinessList, selectedEpisode],
  )
  const primaryBlockedItem = selectedReadiness?.blockedItems[0] ?? null
  const isReadinessSyncing = isProjectDataLoading && readinessList.length === 0

  const overall = useMemo(
    () => ({
      totalEpisodes: readinessList.length,
      exportableEpisodes: readinessList.filter((item) => item.canExport).length,
      blockedEpisodes: readinessList.filter((item) => !item.canExport).length,
      totalBlockedReasons: readinessList.reduce((sum, item) => sum + item.blockedReasons.length, 0),
    }),
    [readinessList],
  )
  const records = useMemo(
    () =>
      rawRecords
        .map((item) => normalizeDeliveryRecord(item, readinessList))
        .filter(Boolean) as DeliveryRecord[],
    [rawRecords, readinessList],
  )

  useEffect(() => {
    void loadRecords()
  }, [bookId])

  useEffect(() => {
    if (readinessList.length === 0) {
      setSelectedEpisode(null)
      return
    }

    setSelectedEpisode((current) => {
      if (current && readinessList.some((item) => item.episode === current)) {
        return current
      }
      return readinessList[0]?.episode ?? null
    })
  }, [readinessList])

  async function loadRecords() {
    if (bookId <= 0) {
      setRawRecords([])
      return
    }

    setRecordState('loading')
    setRecordMessage('')

    try {
      const response = await fetch(`/api/books/${bookId}/export-records`, { cache: 'no-store' })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const payload = await response.json()
      const nextRecords = Array.isArray(payload.records) ? (payload.records as ExportRecordApi[]) : []

      setRawRecords(nextRecords)
      setRecordState('idle')
    } catch (error) {
      setRawRecords([])
      setRecordState('error')
      setRecordMessage(error instanceof Error ? error.message : '加载交付记录失败')
    }
  }

  async function persistRecord(format: string) {
    if (!selectedReadiness) return null

    setRecordState('saving')
    setRecordMessage('')

    const payload = {
      exportFormat: format,
      formatLabel: normalizeDeliveryRecordFormatLabel(format),
      status: selectedReadiness.canExport ? 'completed' : 'blocked',
      totalShots: selectedReadiness.totalShots,
      deliverableShots: selectedReadiness.readyShots,
      pendingReviewShots: Math.max(selectedReadiness.totalShots - selectedReadiness.readyShots, 0),
      blockedShots: selectedReadiness.blockedItems.length,
      summary: summarizeDeliveryPackage(selectedReadiness),
      metaInfo: {
        episode: selectedReadiness.episode,
        script_status: selectedReadiness.scriptStatusLabel,
        blocked_reasons: selectedReadiness.blockedReasons,
        blocked_codes: selectedReadiness.blockedItems.map((item) => item.code),
        version_label: selectedReadiness.canExport ? '可交付快照' : '阻塞快照',
      },
    }

    try {
      const response = await fetch(`/api/books/${bookId}/export-records`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const record = await response.json()
      await loadRecords()
      setRecordState('saved')
      setRecordMessage(format === 'json' ? 'JSON 已导出，并登记交付记录。' : '交付记录已保存。')
      return record
    } catch (error) {
      setRecordState('error')
      setRecordMessage(error instanceof Error ? error.message : '保存交付记录失败')
      return null
    }
  }

  async function handleSaveRecord() {
    await persistRecord('delivery')
  }

  async function handleExportJson() {
    if (!selectedReadiness || !selectedExportPackage) return

    const record = await persistRecord('json')
    if (!record) return

    const snapshot = { ...selectedExportPackage, record }
    const fileStem = buildDeliveryFileStem(bookTitle, selectedReadiness.episode, nextVersionLabel)

    downloadTextFile(
      JSON.stringify(snapshot, null, 2),
      'application/json',
      `${fileStem}.json`,
    )
  }

  async function handleExportWord() {
    if (!selectedReadiness || !selectedExportPackage) return

    const record = await persistRecord('word')
    if (!record) return

    downloadTextFile(
      buildDeliveryWordDocument(selectedExportPackage),
      'application/msword',
      `${buildDeliveryFileStem(bookTitle, selectedReadiness.episode, nextVersionLabel)}.doc`,
    )
  }

  async function handleExportFinalDraft() {
    if (!selectedReadiness || !selectedExportPackage) return

    const record = await persistRecord('fdx')
    if (!record) return

    downloadTextFile(
      buildDeliveryFinalDraftDocument(selectedExportPackage),
      'application/vnd.finaldraft',
      `${buildDeliveryFileStem(bookTitle, selectedReadiness.episode, nextVersionLabel)}.fdx`,
    )
  }

  async function handleExportPdf() {
    if (!selectedReadiness) return

    const record = await persistRecord('pdf')
    if (!record) return

    try {
      const response = await fetch(`/api/books/${bookId}/export-pdf?episode=${selectedReadiness.episode}`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const blob = await response.blob()
      downloadBlob(blob, `${buildDeliveryFileStem(bookTitle, selectedReadiness.episode, nextVersionLabel)}.pdf`)
      setRecordState('saved')
      setRecordMessage('PDF 已导出，并登记交付记录。')
    } catch (error) {
      setRecordState('error')
      setRecordMessage(error instanceof Error ? error.message : '导出 PDF 失败')
    }
  }

  async function handleCopySummary() {
    if (!selectedReadiness) return

    try {
      await navigator.clipboard.writeText(buildDeliveryExportSummaryText(selectedReadiness))
      setRecordState('saved')
      setRecordMessage('交付摘要已复制。')
    } catch (error) {
      setRecordState('error')
      setRecordMessage(error instanceof Error ? error.message : '复制交付摘要失败')
    }
  }

  const selectedEpisodeRecords = useMemo(
    () =>
      selectedReadiness
        ? records.filter((item) => item.episode === selectedReadiness.episode)
        : records,
    [records, selectedReadiness],
  )

  const nextVersionLabel = useMemo(
    () => (selectedReadiness ? `v${selectedEpisodeRecords.length + 1}` : 'v1'),
    [selectedEpisodeRecords.length, selectedReadiness],
  )
  const deliveryCanvasHandoffSummary = buildDeliveryCanvasHandoffSummary({
    handoff: canvasHandoff,
    readiness: selectedReadiness,
  })
  const deliveryCanvasPrimaryAction = buildDeliveryCanvasPrimaryActionPlan({
    readiness: selectedReadiness,
    primaryBlockedItem,
    episodeRecordCount: selectedEpisodeRecords.length,
  })

  const selectedExportPackage = useMemo(
    () =>
      selectedReadiness
        ? buildDeliveryExportPackage({
            bookId,
            bookTitle,
            chapterCount,
            wordCount,
            contentStatusLabel,
            contentStatusDetail,
            adaptationStateLabel,
            adaptationStateDetail,
            selectedAdaptationName,
            adaptationCustomNote,
            adaptationLockedAt,
            readiness: selectedReadiness,
            scripts,
            scriptDecisionState,
            shotsByEpisode,
            makeups,
            locations,
            props,
            versionLabel: nextVersionLabel,
            generatedAt: new Date().toISOString(),
          })
        : null,
    [
      adaptationCustomNote,
      adaptationLockedAt,
      adaptationStateDetail,
      adaptationStateLabel,
      bookId,
      bookTitle,
      chapterCount,
      contentStatusDetail,
      contentStatusLabel,
      locations,
      makeups,
      nextVersionLabel,
      props,
      scriptDecisionState,
      scripts,
      selectedAdaptationName,
      selectedReadiness,
      shotsByEpisode,
      wordCount,
    ],
  )

  async function runDeliveryCanvasPrimaryAction() {
    if (!selectedReadiness || !deliveryCanvasPrimaryAction) return

    switch (deliveryCanvasPrimaryAction.action) {
      case 'repair_blocker':
        if (!primaryBlockedItem) return
        onNavigate(primaryBlockedItem.targetSection, {
          episode: primaryBlockedItem.episode ?? selectedReadiness.episode,
          shotId: primaryBlockedItem.shotId ?? null,
          assetId: primaryBlockedItem.assetId ?? null,
          qaFocus: primaryBlockedItem.targetSection === 'qa' ? 'delivery_recovery' : null,
        })
        return
      case 'save_record':
        await handleSaveRecord()
        return
      case 'export_json':
        await handleExportJson()
        return
    }
  }

  return (
    <div className="space-y-6">
      <section className="grid gap-3 md:grid-cols-4">
        <MetricCard title="交付集数" value={`${overall.totalEpisodes}`} detail="已进入正式交付评估的分集" />
        <MetricCard title="可交付" value={`${overall.exportableEpisodes}`} detail="剧本、分镜、资产和 QA 已通过" />
        <MetricCard title="待修复" value={`${overall.blockedEpisodes}`} detail="仍存在阻塞项，建议先处理再导出" />
        <MetricCard title="阻塞总数" value={`${overall.totalBlockedReasons}`} detail="累计可见的交付问题数量" />
      </section>

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.25fr]">
        <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-white">交付 readiness</div>
              <div className="mt-1 text-xs text-slate-500">按分集检查剧本放行、镜头版本、资产引用和 QA 状态。</div>
            </div>
          </div>

          <div className="mt-4 space-y-3">
            {isReadinessSyncing ? (
              <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-400">
                正在同步交付评估数据，请稍候查看当前分集的交付状态。
              </div>
            ) : readinessList.length > 0 ? (
              readinessList.map((item) => {
                const active = selectedReadiness?.episode === item.episode
                return (
                  <button
                    key={item.episode}
                    type="button"
                    onClick={() => setSelectedEpisode(item.episode)}
                    className={`w-full rounded-xl border p-4 text-left transition ${
                      active ? 'border-sky-500/40 bg-sky-500/10' : 'border-slate-800 bg-slate-950/50 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-sm font-medium text-white">第 {item.episode} 集</div>
                      <span className={`rounded-full border px-2 py-0.5 text-[11px] ${item.canExport ? 'border-emerald-500/30 text-emerald-200' : 'border-amber-500/30 text-amber-200'}`}>
                        {item.statusLabel}
                      </span>
                    </div>
                    <div className="mt-2 text-xs text-slate-400">{summarizeDeliveryPackage(item)}</div>
                    <div className="mt-3 grid grid-cols-3 gap-2 text-[11px] text-slate-500">
                      <span>镜头 {item.readyShots}/{item.totalShots}</span>
                      <span>图片 {item.imageReadyShots}/{item.totalShots}</span>
                      <span>视频 {item.videoReadyShots}/{item.totalShots}</span>
                    </div>
                  </button>
                )
              })
            ) : (
              <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
                当前还没有可评估交付的分集，请先完成剧本和镜头生产。
              </div>
            )}
          </div>
        </section>

        <section className="space-y-6">
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
            {selectedReadiness ? (
              <>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="text-lg font-semibold text-white">第 {selectedReadiness.episode} 集交付面板</div>
                    <div className="mt-2 text-sm leading-6 text-slate-400">{summarizeDeliveryPackage(selectedReadiness)}</div>
                  </div>
                  <span className={`rounded-full border px-2.5 py-1 text-xs ${selectedReadiness.canExport ? 'border-emerald-500/30 text-emerald-200' : 'border-amber-500/30 text-amber-200'}`}>
                    {selectedReadiness.statusLabel}
                  </span>
                </div>

                <div className="mt-5 grid gap-3 md:grid-cols-4">
                  <MetricCard title="剧本状态" value={selectedReadiness.scriptStatusLabel} detail="先锁稿，再放行到分镜与交付" />
                  <MetricCard title="可交付镜头" value={`${selectedReadiness.readyShots}/${selectedReadiness.totalShots}`} detail="静态提示词、运动提示词、图片和视频齐备" />
                  <MetricCard title="资产引用" value={`${selectedReadiness.referencedAssetCount}`} detail="人物、场景、道具的可追溯引用数量" />
                  <MetricCard title="QA 问题" value={`${selectedReadiness.qaCount}`} detail={selectedReadiness.qaCount > 0 ? '仍需清理后再进入稳定交付' : '当前未发现交付阻塞 QA'} />
                </div>

                {deliveryCanvasHandoffSummary ? (
                  <div className="mt-5 rounded-xl border border-fuchsia-500/30 bg-fuchsia-500/10 p-4">
                    <div className="text-xs font-medium tracking-wide text-fuchsia-200">创作画布承接中</div>
                    <div className="mt-2 text-sm font-medium text-white">{deliveryCanvasHandoffSummary.title}</div>
                    <div className="mt-2 text-sm text-fuchsia-100">{deliveryCanvasHandoffSummary.label}</div>
                    <div className="mt-2 text-xs leading-6 text-fuchsia-100/80">{deliveryCanvasHandoffSummary.detail}</div>
                    {deliveryCanvasPrimaryAction ? (
                      <div className="mt-4 rounded-lg border border-fuchsia-400/20 bg-slate-950/30 p-3">
                        <div className="text-[11px] tracking-wide text-fuchsia-200/90">承接后的首个动作</div>
                        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="text-sm font-medium text-white">{deliveryCanvasPrimaryAction.label}</div>
                            <div className="mt-1 text-xs leading-6 text-fuchsia-100/80">{deliveryCanvasPrimaryAction.detail}</div>
                          </div>
                          <button
                            type="button"
                            onClick={() => void runDeliveryCanvasPrimaryAction()}
                            disabled={recordState === 'saving'}
                            className="rounded-lg border border-fuchsia-400/40 px-3 py-1.5 text-xs font-medium text-fuchsia-100 transition hover:border-fuchsia-300 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            立即继续
                          </button>
                        </div>
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {primaryBlockedItem ? (
                  <div className="mt-5 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-amber-100">首个阻塞入口</div>
                        <div className="mt-1 text-sm text-white">{primaryBlockedItem.label}</div>
                        <div className="mt-2 text-xs leading-6 text-amber-100/80">{primaryBlockedItem.detail}</div>
                      </div>
                      <button
                        type="button"
                        onClick={() =>
                          onNavigate(primaryBlockedItem.targetSection, {
                            episode: primaryBlockedItem.episode ?? selectedReadiness.episode,
                            shotId: primaryBlockedItem.shotId ?? null,
                            assetId: primaryBlockedItem.assetId ?? null,
                          })
                        }
                        className="rounded-lg border border-amber-300/40 px-3 py-1.5 text-xs text-amber-100 transition hover:border-amber-200 hover:text-white"
                      >
                        {buildBlockedItemActionLabel(primaryBlockedItem)}
                      </button>
                    </div>
                  </div>
                ) : null}

                <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                  <div className="text-sm font-medium text-white">阻塞清单</div>
                  {selectedReadiness.blockedItems.length > 0 ? (
                    <div className="mt-3 space-y-3">
                      {selectedReadiness.blockedItems.map((item) => (
                        <BlockedItemCard key={`${selectedReadiness.episode}-${item.code}`} item={item} onNavigate={onNavigate} />
                      ))}
                    </div>
                  ) : (
                    <div className="mt-3 text-sm text-emerald-300">当前没有阻塞项，可以进入交付记录或导出 JSON。</div>
                  )}
                </div>

                {selectedExportPackage ? (
                  <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-white">交付包内容</div>
                        <div className="mt-1 text-xs text-slate-500">
                          当前导出会生成 {selectedExportPackage.versionLabel} 交付快照，并收录上游版本、采纳媒体、参考图与 QA 摘要。
                        </div>
                      </div>
                      <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">
                        {selectedExportPackage.versionLabel}
                      </span>
                    </div>

                    <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                      <MetricCard
                        title="内容准备"
                        value={selectedExportPackage.contentPreparation.statusLabel}
                        detail={`章节 ${selectedExportPackage.contentPreparation.chapterCount} / ${selectedExportPackage.contentPreparation.wordCount} 字`}
                      />
                      <MetricCard
                        title="改编方向"
                        value={selectedExportPackage.adaptationDirection.selectedName || selectedExportPackage.adaptationDirection.statusLabel}
                        detail={selectedExportPackage.adaptationDirection.lockedAt ? '已锁定主方向' : selectedExportPackage.adaptationDirection.statusDetail}
                      />
                      <MetricCard
                        title="采纳分镜图"
                        value={`${selectedExportPackage.adoptedStoryboard.filter((item) => item.adoptedImage).length}/${selectedExportPackage.adoptedStoryboard.length}`}
                        detail="逐镜头记录当前采纳图片版本"
                      />
                      <MetricCard
                        title="采纳视频"
                        value={`${selectedExportPackage.adoptedStoryboard.filter((item) => item.adoptedVideo).length}/${selectedExportPackage.adoptedStoryboard.length}`}
                        detail="逐镜头记录当前采纳视频版本"
                      />
                    </div>

                    <div className="mt-4 grid gap-3 md:grid-cols-3">
                      <MetricCard
                        title="人物参考图"
                        value={`${selectedExportPackage.selectedReferenceAssets.characters.reduce((sum, item) => sum + item.selectedReferences.length, 0)}`}
                        detail="仅导出 selected / locked 参考图"
                      />
                      <MetricCard
                        title="场景参考图"
                        value={`${selectedExportPackage.selectedReferenceAssets.locations.reduce((sum, item) => sum + item.selectedReferences.length, 0)}`}
                        detail="仅导出 selected / locked 参考图"
                      />
                      <MetricCard
                        title="道具参考图"
                        value={`${selectedExportPackage.selectedReferenceAssets.props.reduce((sum, item) => sum + item.selectedReferences.length, 0)}`}
                        detail="仅导出 selected / locked 参考图"
                      />
                    </div>
                  </div>
                ) : null}

                <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-white">交付动作</div>
                      <div className="mt-1 text-xs text-slate-500">先登记快照，再决定是否导出给外部团队或质检链路。</div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={handleSaveRecord}
                        disabled={!selectedReadiness || recordState === 'saving'}
                        className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {selectedReadiness?.canExport ? '生成交付记录' : '记录阻塞快照'}
                      </button>
                      <button
                        type="button"
                        onClick={handleExportJson}
                        disabled={!selectedReadiness || recordState === 'saving'}
                        className="rounded-lg border border-sky-500/50 px-3 py-1.5 text-xs text-sky-200 transition hover:border-sky-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        导出 JSON 并登记
                      </button>
                      <button
                        type="button"
                        onClick={handleExportWord}
                        disabled={!selectedReadiness?.canExport || recordState === 'saving'}
                        className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        导出 Word
                      </button>
                      <button
                        type="button"
                        onClick={handleExportFinalDraft}
                        disabled={!selectedReadiness?.canExport || recordState === 'saving'}
                        className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        导出 Final Draft
                      </button>
                      <button
                        type="button"
                        onClick={handleExportPdf}
                        disabled={!selectedReadiness?.canExport || recordState === 'saving'}
                        className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        导出 PDF
                      </button>
                      <button
                        type="button"
                        onClick={handleCopySummary}
                        disabled={!selectedReadiness}
                        className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        复制交付摘要
                      </button>
                      <button
                        type="button"
                        onClick={() => void loadRecords()}
                        disabled={recordState === 'loading'}
                        className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        刷新交付记录
                      </button>
                    </div>
                  </div>

                  {recordMessage ? (
                    <div className={`mt-3 rounded-lg border px-3 py-2 text-xs ${
                      recordState === 'error'
                        ? 'border-rose-500/30 bg-rose-500/10 text-rose-200'
                        : 'border-sky-500/30 bg-sky-500/10 text-sky-200'
                    }`}>
                      {recordMessage}
                    </div>
                  ) : null}

                  {selectedReadiness && !selectedReadiness.canExport ? (
                    <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs leading-6 text-amber-100">
                      当前集仍有交付阻塞项，`Word / Final Draft / PDF` 仅在可交付状态下开放。请先处理上面的阻塞清单，再导出正式交付文件。
                    </div>
                  ) : null}
                </div>
              </>
            ) : isReadinessSyncing ? (
              <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-400">
                正在同步项目数据，交付面板会在分集评估完成后自动显示。
              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
                当前没有可查看的交付分集。
              </div>
            )}
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
            <div className="text-sm font-medium text-white">交付记录</div>
            <div className="mt-1 text-xs text-slate-500">历史记录会优先显示清洗后的摘要，旧脏文案会自动回退到标准格式。</div>

            <div className="mt-4 space-y-3">
              {recordState === 'loading' ? <div className="text-sm text-slate-500">正在加载交付记录...</div> : null}
              {recordState !== 'loading' && selectedEpisodeRecords.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
                  {recordState === 'error' ? recordMessage || '加载交付记录失败。' : '当前还没有交付记录。'}
                </div>
              ) : null}

              {selectedEpisodeRecords.map((record) => (
                <div key={record.id} className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-white">{record.formatLabel || normalizeDeliveryRecordFormatLabel(record.exportFormat)}</span>
                    <span className={`rounded-full px-2 py-0.5 text-[11px] ${
                      record.status === 'completed'
                        ? 'bg-emerald-900/40 text-emerald-300'
                        : 'bg-amber-900/40 text-amber-300'
                    }`}>
                      {record.status === 'completed' ? '已完成' : '阻塞'}
                    </span>
                    <span className="text-xs text-slate-500">{record.createdAt}</span>
                  </div>
                  <div className="mt-2 text-sm text-slate-300">{record.summary}</div>
                  {record.blockedReasons.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {record.blockedReasons.map((reason, index) => (
                        <span
                          key={`${record.id}-reason-${index}`}
                          className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-200"
                        >
                          {reason}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  <div className="mt-3 grid gap-2 md:grid-cols-4 text-xs text-slate-500">
                    <div>总镜头：{record.totalShots}</div>
                    <div>可交付：{record.deliverableShots}</div>
                    <div>待验收：{record.pendingReviewShots}</div>
                    <div>阻塞：{record.blockedShots}</div>
                  </div>
                  <RecordRepairActions record={record} onNavigate={onNavigate} />
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

function MetricCard({ title, value, detail }: { title: string; value: string; detail: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
      <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{title}</div>
      <div className="mt-2 text-xl font-semibold text-white">{value}</div>
      <div className="mt-2 text-xs leading-5 text-slate-500">{detail}</div>
    </div>
  )
}

function BlockedItemCard({
  item,
  onNavigate,
}: {
  item: DeliveryBlockedItem
  onNavigate: TaskNavigateHandler
}) {
  const buttonLabel = buildBlockedItemActionLabel(item)
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-white">{item.label}</div>
          <div className="mt-1 text-xs leading-6 text-slate-400">{item.detail}</div>
        </div>
        <button
          type="button"
          onClick={() =>
            onNavigate(item.targetSection, {
              episode: item.episode ?? null,
              shotId: item.shotId ?? null,
              assetId: item.assetId ?? null,
              qaFocus: item.targetSection === 'qa' ? 'delivery_recovery' : null,
            })
          }
          className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
        >
          {buttonLabel}
        </button>
      </div>
    </div>
  )
}

function RecordRepairActions({
  record,
  onNavigate,
}: {
  record: DeliveryRecord
  onNavigate: TaskNavigateHandler
}) {
  const actions = deriveDeliveryRecordRepairActions(record)
  if (actions.length === 0) return null
  const firstBlockedShotId = getFirstBlockedShotId(record.blockedShotIds)

  return (
    <div className="mt-4 border-t border-slate-800 pt-3">
      <div className="mb-2 text-[11px] uppercase tracking-[0.16em] text-slate-500">阻塞回溯</div>
      <div className="flex flex-wrap gap-2">
        {actions.map((action) => (
          <button
            key={`${record.id}-${action.code}`}
            type="button"
            onClick={() =>
              onNavigate(action.targetSection, {
                episode: record.episode,
                shotId:
                  action.targetSection === 'storyboard' || action.targetSection === 'assets'
                    ? record.blockedShotIdsByCode?.[action.code] ?? firstBlockedShotId
                    : null,
                qaFocus: action.targetSection === 'qa' ? 'delivery_recovery' : null,
              })
            }
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
          >
            {buildRecordRepairActionLabel(action.label, record.blockedShotIdsByCode?.[action.code] ?? firstBlockedShotId, action.targetSection)}
          </button>
        ))}
      </div>
    </div>
  )
}

function buildBlockedItemActionLabel(item: DeliveryBlockedItem) {
  if (item.targetSection === 'storyboard') {
    return item.shotId ? `定位镜头 ${item.shotId}` : '去镜头工作台'
  }
  if (item.targetSection === 'assets') {
    return item.shotId ? `去资产中心定位镜头 ${item.shotId}` : '去资产中心'
  }
  if (item.targetSection === 'scripts') return '去剧本工作台'
  if (item.targetSection === 'qa') return '去 QA 修复'
  return '去改编方向'
}

function getFirstBlockedShotId(blockedShotIds: string[]) {
  for (const item of blockedShotIds) {
    const normalized = String(item || '').trim()
    if (!normalized) continue
    const match = normalized.match(/^(?:\d+-)?(.+)$/)
    if (match?.[1]) return match[1]
  }
  return null
}

function buildRecordRepairActionLabel(label: string, shotId: string | null | undefined, targetSection: string) {
  if (!shotId || (targetSection !== 'storyboard' && targetSection !== 'assets')) return label
  return `${label}（镜头 ${shotId}）`
}

function downloadTextFile(content: string, mimeType: string, filename: string) {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` })
  downloadBlob(blob, filename)
}

function downloadBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

function normalizeDeliveryRecord(
  record: ExportRecordApi,
  readinessList: DeliveryEpisodeReadiness[],
): DeliveryRecord | null {
  if (!record || typeof record !== 'object') return null

  const metaInfo = record.meta_info && typeof record.meta_info === 'object' ? record.meta_info : {}
  const blockedShotIds = Array.isArray(metaInfo.blockedShotIds)
    ? metaInfo.blockedShotIds.map((item: unknown) => String(item))
    : Array.isArray(metaInfo.blocked_shot_ids)
      ? metaInfo.blocked_shot_ids.map((item: unknown) => String(item))
      : []
  const blockedReasons = Array.isArray(metaInfo.blocked_reasons)
    ? metaInfo.blocked_reasons.map((item: unknown) => String(item))
    : Array.isArray(metaInfo.issues)
      ? metaInfo.issues.map((item: unknown) => String(item))
      : []
  const blockedCodes = Array.isArray(metaInfo.blocked_codes)
    ? metaInfo.blocked_codes
        .map((item: unknown) => String(item))
        .filter(Boolean)
    : []

  const sanitizedBlockedReasons = blockedReasons.filter(
    (item: string) => !isLikelyCorruptedDeliveryText(item) && !item.includes('?'),
  )

  const inferredEpisode = inferEpisodeFromBlockedShotIds(blockedShotIds)
  const episode = Number(metaInfo.episode ?? inferredEpisode ?? record.episode ?? 0)
  const fallbackReadiness = readinessList.find((item) => item.episode === episode)
  const exportFormat = toDisplayText(record.export_format, 'json').toLowerCase()
  const fallbackFormatLabel = normalizeDeliveryRecordFormatLabel(exportFormat)

  const rawFormatLabel = toDisplayText(record.format_label, fallbackFormatLabel)
  const formatLabel = isLikelyCorruptedDeliveryText(rawFormatLabel) ? fallbackFormatLabel : rawFormatLabel

  const rawVersionLabel = toDisplayText(metaInfo.version_label, formatLabel)
  const versionLabel = isLikelyCorruptedDeliveryText(rawVersionLabel) ? formatLabel : rawVersionLabel

  const pendingReviewShots = Number(
    record.pending_review_shots ?? Math.max((fallbackReadiness?.totalShots ?? 0) - (fallbackReadiness?.readyShots ?? 0), 0),
  )

  const fallbackSummary = summarizeDeliveryRecordHistory({
    episode: episode || fallbackReadiness?.episode || 0,
    scriptStatusLabel:
      typeof metaInfo.script_status === 'string' && metaInfo.script_status.trim()
        ? metaInfo.script_status.trim()
        : fallbackReadiness?.scriptStatusLabel,
    deliverableShots: Number(record.deliverable_shots ?? fallbackReadiness?.readyShots ?? 0),
    totalShots: Number(record.total_shots ?? fallbackReadiness?.totalShots ?? 0),
    pendingReviewShots,
    blockedReasons: sanitizedBlockedReasons,
    exportFormat,
    status: record.status === 'completed' ? 'completed' : 'blocked',
  })

  const summarySource = toDisplayText(record.summary, fallbackSummary)
  const hasBrokenSeparator = /\s[路璺]\s/.test(summarySource)
  const summary = isLikelyCorruptedDeliveryText(summarySource) || hasBrokenSeparator
    ? fallbackSummary
    : summarySource
  const effectiveBlockedShotIds =
    blockedShotIds.length > 0
      ? blockedShotIds
      : inferBlockedShotIdsFromReadiness(sanitizedBlockedReasons, blockedCodes, fallbackReadiness)
  const blockedShotIdsByCode =
    blockedShotIds.length > 0
      ? {}
      : inferBlockedShotIdsByCodeFromReadiness(sanitizedBlockedReasons, blockedCodes, fallbackReadiness)

  return {
    id: String(record.id ?? ''),
    episode: episode || fallbackReadiness?.episode || 0,
    createdAt: String(record.created_at ?? new Date().toISOString()),
    status: record.status === 'completed' ? 'completed' : 'blocked',
    versionLabel,
    formatLabel,
    summary,
    exportFormat,
    totalShots: Number(record.total_shots ?? fallbackReadiness?.totalShots ?? 0),
    deliverableShots: Number(record.deliverable_shots ?? fallbackReadiness?.readyShots ?? 0),
    pendingReviewShots,
    blockedShots: Number(record.blocked_shots ?? sanitizedBlockedReasons.length ?? 0),
    blockedShotIds: effectiveBlockedShotIds,
    blockedShotIdsByCode,
    blockedCodes: blockedCodes as DeliveryRecord['blockedCodes'],
    blockedReasons: sanitizedBlockedReasons,
  }
}

function inferEpisodeFromBlockedShotIds(blockedShotIds: string[]) {
  for (const item of blockedShotIds) {
    const match = String(item).match(/^(\d+)-/)
    if (match) return Number(match[1])
  }
  return null
}

function toDisplayText(value: unknown, fallback: string) {
  const text = typeof value === 'string' ? value.trim() : ''
  return text || fallback
}

function inferBlockedShotIdsFromReadiness(
  blockedReasons: string[],
  blockedCodes: string[],
  readiness: DeliveryEpisodeReadiness | undefined,
) {
  if (!readiness) return []

  const codeSet = new Set(blockedCodes.map((item) => String(item || '').trim()).filter(Boolean))
  for (const reason of blockedReasons) {
    const normalized = String(reason || '').trim()
    if (!normalized) continue
    if (normalized.includes('分镜图') || normalized.includes('首帧')) codeSet.add('missing_images')
    if (normalized.includes('视频')) codeSet.add('missing_videos')
    if (normalized.includes('提示词')) codeSet.add('missing_prompts')
    if (normalized.includes('资产')) codeSet.add('missing_asset_references')
  }

  return Array.from(
    new Set(
      readiness.blockedItems
        .filter((item) => item.shotId && codeSet.has(item.code))
        .map((item) => `${readiness.episode}-${item.shotId}`),
    ),
  )
}

function inferBlockedShotIdsByCodeFromReadiness(
  blockedReasons: string[],
  blockedCodes: string[],
  readiness: DeliveryEpisodeReadiness | undefined,
) {
  if (!readiness) return {}

  const codeSet = new Set(blockedCodes.map((item) => String(item || '').trim()).filter(Boolean))
  for (const reason of blockedReasons) {
    const normalized = String(reason || '').trim()
    if (!normalized) continue
    if (normalized.includes('分镜图') || normalized.includes('首帧')) codeSet.add('missing_images')
    if (normalized.includes('视频')) codeSet.add('missing_videos')
    if (normalized.includes('提示词')) codeSet.add('missing_prompts')
    if (normalized.includes('资产')) codeSet.add('missing_asset_references')
  }

  const result: Partial<Record<DeliveryRecord['blockedCodes'][number], string>> = {}
  for (const item of readiness.blockedItems) {
    if (!item.shotId || !codeSet.has(item.code) || result[item.code]) continue
    result[item.code] = item.shotId
  }
  return result
}
