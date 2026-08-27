import { CollapsiblePanel, StatusPill } from './ProductWorkspaceStoryboardUi'

type MachineTimelineSegmentLike = {
  phase?: string
  time_range_seconds?: string
  visual_action?: string
  camera_instruction?: string
}

type MachinePromptExportPreviewLike = {
  api_submission?: boolean
  director_shot_text?: string
  bound_asset_count?: number
  reference_image_count?: number
  source_layers?: {
    machine_prompt_is_compiled?: boolean
    is_temporary_webui_draft?: boolean
    history_export_record_id?: string | number
  }
  machine_prompt?: {
    soundscape?: {
      overall_soundscape?: string
    }
  }
}

type ProductionExportRecordListItemLike = {
  id?: string | number
  summary?: string
  created_at?: string | null
  meta_info?: {
    record_type?: string
    api_submission?: boolean
    target_model?: string
    export_channel?: string
    episode?: number
    shot_id?: number | string
    scene_name?: string
    director_shot_text?: string
    reference_image_count?: number
    bound_asset_count?: number
    machine_prompt?: any
    model_exports?: Record<string, any>
  }
}

type MachinePromptExportState = 'idle' | 'loading' | 'loaded' | 'error'
type MachinePromptRecordState = 'idle' | 'saving' | 'saved' | 'error'
type MachinePromptRecordHistoryState = 'idle' | 'loading' | 'loaded' | 'error'
type MachinePromptExportFormat = 'markdown' | 'csv' | 'api-json'

interface MachinePromptExportPanelProps {
  machinePromptExport: MachinePromptExportPreviewLike | null
  machinePromptExportState: MachinePromptExportState
  machinePromptExportMessage: string
  machinePromptCopyMessage: string
  machinePromptRecordMessage: string
  machinePromptRecordState: MachinePromptRecordState
  machinePromptExportRecords: ProductionExportRecordListItemLike[]
  machinePromptRecordHistoryState: MachinePromptRecordHistoryState
  minimaxH3CopyText: string
  minimaxH3Fields: {
    integrated_multimodal_description?: string
    overall_soundscape?: string
    non_diegetic_music?: string
  }
  machineTimeline: MachineTimelineSegmentLike[]
  genericZhVideoExport?: {
    prompt?: string
  } | null
  canRecordExport: boolean
  onLoadPreview: () => void | Promise<void>
  onCopyText: (label: string, text: string | undefined) => void | Promise<void>
  onDownloadFile: (format: MachinePromptExportFormat) => void
  onSaveRecord: () => void | Promise<void>
  onLoadHistory: () => void | Promise<void>
  onRestoreRecordDraft: (record: ProductionExportRecordListItemLike) => void
}

export function ProductWorkspaceMachinePromptExportPanel({
  machinePromptExport,
  machinePromptExportState,
  machinePromptExportMessage,
  machinePromptCopyMessage,
  machinePromptRecordMessage,
  machinePromptRecordState,
  machinePromptExportRecords,
  machinePromptRecordHistoryState,
  minimaxH3CopyText,
  minimaxH3Fields,
  machineTimeline,
  genericZhVideoExport,
  canRecordExport,
  onLoadPreview,
  onCopyText,
  onDownloadFile,
  onSaveRecord,
  onLoadHistory,
  onRestoreRecordDraft,
}: MachinePromptExportPanelProps) {
  const isHistoryDraft = Boolean(machinePromptExport?.source_layers?.is_temporary_webui_draft)

  return (
    <div className="mt-4 rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-white">机器提示词导出预览</div>
          <div className="mt-1 text-xs leading-5 text-cyan-100/75">
            按“导演分镜语言 → 标准机器语言 → 多模型导出”生成，只读预览，不提交 API。
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => { void onLoadPreview() }}
            disabled={machinePromptExportState === 'loading'}
            className="rounded-lg border border-cyan-400/40 bg-cyan-400/10 px-3 py-2 text-xs font-medium text-cyan-100 transition hover:border-cyan-300 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {machinePromptExportState === 'loading' ? '生成预览中...' : machinePromptExport ? '重新生成预览' : '加载导出预览'}
          </button>
          <button
            type="button"
            onClick={() => { void onCopyText('H3 全字段', minimaxH3CopyText) }}
            disabled={!machinePromptExport}
            className="rounded-lg bg-cyan-600 px-3 py-2 text-xs font-medium text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
          >
            复制 H3 全字段
          </button>
          <details className="rounded-lg border border-cyan-400/20 bg-slate-950/50 px-3 py-2">
            <summary className="cursor-pointer list-none text-xs font-medium text-cyan-100">更多导出</summary>
            <div className="mt-3 flex max-w-xl flex-wrap gap-2">
              <button
                type="button"
                onClick={() => onDownloadFile('markdown')}
                disabled={!machinePromptExport}
                className="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition hover:border-cyan-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                导出 Markdown
              </button>
              <button
                type="button"
                onClick={() => onDownloadFile('csv')}
                disabled={!machinePromptExport}
                className="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition hover:border-cyan-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                导出 CSV
              </button>
              <button
                type="button"
                onClick={() => onDownloadFile('api-json')}
                disabled={!machinePromptExport}
                className="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition hover:border-cyan-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                导出 API JSON
              </button>
              <button
                type="button"
                onClick={() => { void onSaveRecord() }}
                disabled={machinePromptRecordState === 'saving' || !canRecordExport}
                className="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition hover:border-cyan-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                {machinePromptRecordState === 'saving' ? '登记中...' : '保存导出记录'}
              </button>
              <button
                type="button"
                onClick={() => { void onLoadHistory() }}
                disabled={machinePromptRecordHistoryState === 'loading' || !canRecordExport}
                className="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition hover:border-cyan-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                {machinePromptRecordHistoryState === 'loading' ? '读取中...' : '刷新导出历史'}
              </button>
            </div>
          </details>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <StatusPill tone={machinePromptExport?.source_layers?.machine_prompt_is_compiled ? 'emerald' : 'amber'}>
          {machinePromptExport?.source_layers?.machine_prompt_is_compiled ? '已编译' : '待加载'}
        </StatusPill>
        <StatusPill tone="cyan">仅导出</StatusPill>
        <StatusPill tone={machinePromptExport?.api_submission === false ? 'slate' : 'amber'}>
          {machinePromptExport?.api_submission === false ? 'API 未提交' : 'API 提交待加载'}
        </StatusPill>
        {isHistoryDraft ? (
          <StatusPill tone="amber">
            历史草稿 #{machinePromptExport?.source_layers?.history_export_record_id ?? '-'}
          </StatusPill>
        ) : null}
      </div>

      {machinePromptExportMessage ? (
        <div
          className={`mt-3 rounded-lg border px-3 py-2 text-xs ${
            machinePromptExportState === 'error'
              ? 'border-rose-500/20 bg-rose-500/5 text-rose-200'
              : 'border-cyan-500/20 bg-cyan-950/30 text-cyan-100/80'
          }`}
        >
          {machinePromptExportMessage}
        </div>
      ) : null}
      {machinePromptCopyMessage ? (
        <div className="mt-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-xs text-emerald-100/80">
          {machinePromptCopyMessage}
        </div>
      ) : null}
      {machinePromptRecordMessage ? (
        <div
          className={`mt-3 rounded-lg border px-3 py-2 text-xs ${
            machinePromptRecordState === 'error'
              ? 'border-rose-500/20 bg-rose-500/5 text-rose-200'
              : 'border-cyan-500/20 bg-cyan-950/30 text-cyan-100/80'
          }`}
        >
          {machinePromptRecordMessage}
        </div>
      ) : null}

      <CollapsiblePanel
        title="当前镜头导出历史"
        description="只记录 WebUI / 文件导出快照；生成 API 仍必须走独立任务。"
        className="mt-4 border-cyan-500/10"
      >
        <div className="mb-3 flex justify-end">
          <StatusPill tone="slate">
            {machinePromptRecordHistoryState === 'idle' ? '待读取' : `${machinePromptExportRecords.length} 条`}
          </StatusPill>
        </div>
        {machinePromptExportRecords.length > 0 ? (
          <div className="mt-3 space-y-2">
            {machinePromptExportRecords.slice(0, 5).map((record) => {
              const meta = record.meta_info ?? {}
              return (
                <div key={String(record.id ?? record.created_at ?? record.summary)} className="rounded border border-slate-800 bg-slate-950 px-2 py-2 text-xs">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="font-medium text-slate-200">#{record.id ?? '-'} · {meta.target_model || '模型未记录'} / {meta.export_channel || 'webui'}</div>
                    <div className="text-[11px] text-slate-500">{record.created_at || '-'}</div>
                  </div>
                  <div className="mt-1 text-[11px] leading-5 text-slate-400">{record.summary || '机器提示词导出快照'}</div>
                  <div className="mt-1 text-[11px] text-slate-500">
                    API 提交：{meta.api_submission === false ? '否' : '未知'} · 参考图 {meta.reference_image_count ?? 0} · 绑定资产 {meta.bound_asset_count ?? 0}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => onRestoreRecordDraft(record)}
                      disabled={!meta.machine_prompt && !meta.model_exports}
                      className="rounded border border-amber-400/30 px-2 py-1 text-[11px] text-amber-100 transition hover:border-amber-300 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      恢复为 WebUI 草稿
                    </button>
                    <span className="text-[11px] leading-6 text-slate-500">只恢复到导出预览，不改当前分镜。</span>
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="mt-3 text-xs text-slate-500">
            {machinePromptRecordHistoryState === 'loaded' ? '当前镜头还没有导出快照。' : '点击“刷新导出历史”读取当前镜头的导出快照。'}
          </div>
        )}
      </CollapsiblePanel>

      {machinePromptExport ? (
        <CollapsiblePanel
          title="更多机器语言与单字段复制"
          description="展开后查看导演语言快照、标准机器语言、H3 单字段和通用 WebUI 导出。"
          className="mt-4 border-cyan-500/10"
        >
          <div className="grid gap-4 xl:grid-cols-3">
            <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
              <div className="text-xs font-medium text-cyan-100">导演分镜语言</div>
              <div className="mt-2 whitespace-pre-wrap text-xs leading-6 text-slate-300">
                {machinePromptExport.director_shot_text || '暂无导演分镜语言。'}
              </div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-xs font-medium text-cyan-100">标准机器语言</div>
                <span className="text-[10px] text-slate-500">
                  参考图 {machinePromptExport.reference_image_count ?? 0} · 绑定资产 {machinePromptExport.bound_asset_count ?? 0}
                </span>
              </div>
              {machineTimeline.length > 0 ? (
                <div className="mt-2 space-y-2">
                  {machineTimeline.map((segment, index) => (
                    <div key={`${segment.phase || 'phase'}-${index}`} className="rounded border border-slate-800 bg-slate-950 px-2 py-2">
                      <div className="text-[11px] text-slate-500">
                        {segment.time_range_seconds || '-'} · {segment.phase || '阶段'} · {segment.camera_instruction || '默认运镜'}
                      </div>
                      <div className="mt-1 text-xs leading-5 text-slate-300">{segment.visual_action || '暂无动作描述'}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-2 text-xs text-slate-500">暂无机器时间线。</div>
              )}
              <div className="mt-3 text-[11px] leading-5 text-slate-500">
                环境声：{machinePromptExport.machine_prompt?.soundscape?.overall_soundscape || '待补齐'}
              </div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-xs font-medium text-cyan-100">MiniMax H3 / WebUI 导出</div>
                <button
                  type="button"
                  onClick={() => { void onCopyText('H3 全字段', minimaxH3CopyText) }}
                  className="rounded border border-cyan-400/30 px-2 py-1 text-[11px] text-cyan-100 transition hover:border-cyan-300 hover:text-white"
                >
                  复制明细全字段
                </button>
              </div>
              <div className="mt-2 space-y-2">
                <details open className="rounded border border-slate-800 bg-slate-950 px-2 py-2">
                  <summary className="cursor-pointer text-[11px] text-slate-400">integrated_multimodal_description</summary>
                  <button
                    type="button"
                    onClick={() => { void onCopyText('H3 integrated 描述', minimaxH3Fields.integrated_multimodal_description) }}
                    className="mt-2 rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition hover:border-cyan-400 hover:text-white"
                  >
                    复制 integrated
                  </button>
                  <div className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap text-xs leading-5 text-slate-300">
                    {minimaxH3Fields.integrated_multimodal_description || '暂无 H3 画面描述。'}
                  </div>
                </details>
                <div className="rounded border border-slate-800 bg-slate-950 px-2 py-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-[11px] text-slate-500">overall_soundscape</div>
                    <button
                      type="button"
                      onClick={() => { void onCopyText('H3 音景', minimaxH3Fields.overall_soundscape) }}
                      className="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition hover:border-cyan-400 hover:text-white"
                    >
                      复制音景
                    </button>
                  </div>
                  <div className="mt-1 text-xs leading-5 text-slate-300">{minimaxH3Fields.overall_soundscape || '待补齐'}</div>
                </div>
                <div className="rounded border border-slate-800 bg-slate-950 px-2 py-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-[11px] text-slate-500">non_diegetic_music</div>
                    <button
                      type="button"
                      onClick={() => { void onCopyText('H3 配乐', minimaxH3Fields.non_diegetic_music) }}
                      className="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition hover:border-cyan-400 hover:text-white"
                    >
                      复制配乐
                    </button>
                  </div>
                  <div className="mt-1 text-xs leading-5 text-slate-300">{minimaxH3Fields.non_diegetic_music || '待补齐'}</div>
                </div>
              </div>
              <details className="mt-3 rounded border border-slate-800 bg-slate-950 px-2 py-2">
                <summary className="cursor-pointer text-[11px] text-slate-400">通用中文视频 WebUI 导出</summary>
                <button
                  type="button"
                  onClick={() => { void onCopyText('通用 WebUI', genericZhVideoExport?.prompt) }}
                  className="mt-2 rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition hover:border-cyan-400 hover:text-white"
                >
                  复制通用 WebUI
                </button>
                <div className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap text-xs leading-5 text-slate-300">
                  {genericZhVideoExport?.prompt || '暂无通用 WebUI 导出。'}
                </div>
              </details>
            </div>
          </div>
        </CollapsiblePanel>
      ) : null}
    </div>
  )
}
