import type { StoryboardShotOutput } from '../domain/bookOutputs'
import { CollapsiblePanel, MiniMetric } from './ProductWorkspaceStoryboardUi'
import {
  buildPromptVersionAuditSummary,
  getPromptRestoreReasonLabel,
} from './ProductWorkspacePromptHistoryPanel'

type CompilerCheckLike = {
  key?: string
  label?: string
  passed?: boolean
  message?: string
  details?: string[]
}

type CompilerFocusCardLike = {
  key: string
  title: string
  detail: string
  items: string[]
  tone: string
}

type MetricItemLike = {
  key: string
  label: string
  value: string
}

type RecommendedRestoreVersionLike = {
  version?: string | number
  reason?: string
} | null

type ActionState = 'idle' | 'saving' | 'success' | 'error'

export function ProductWorkspaceCompileDiagnosticsPanel({
  promptVersionAudit,
  promptVersionAuditSummary,
  recommendedRestoreVersion,
  restoreOutcomeMeta,
  historyActionState,
  compilerChecks,
  compilerFocusCards,
  compilerWarnings,
  blockingIssues,
  compileContextWarnings,
  compilerMetricItems,
  onRollbackRecommendedPromptVersion,
}: {
  promptVersionAudit: StoryboardShotOutput['prompt_version_audit'] | null | undefined
  promptVersionAuditSummary: ReturnType<typeof buildPromptVersionAuditSummary>
  recommendedRestoreVersion: RecommendedRestoreVersionLike
  restoreOutcomeMeta: { tone: string; label: string }
  historyActionState: ActionState
  compilerChecks: CompilerCheckLike[]
  compilerFocusCards: CompilerFocusCardLike[]
  compilerWarnings: string[]
  blockingIssues: string[]
  compileContextWarnings: string[]
  compilerMetricItems: MetricItemLike[]
  onRollbackRecommendedPromptVersion: () => void | Promise<void>
}) {
  return (
    <CollapsiblePanel
      title="编译诊断"
      description="当前镜头的诊断状态、检查项和量化指标。默认折叠，避免首屏被检查项淹没。"
    >
      {promptVersionAudit?.is_degraded_version ? (
        <div className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-amber-200">当前提示词版本疑似跑偏</div>
              <div className="mt-1 text-xs leading-5 text-amber-100/90">
                {promptVersionAuditSummary?.summary || '当前版本存在关键资产缺失或退化风险，建议优先检查提示词历史版本。'}
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                <MiniMetric label="缺失关键资产" value={`${promptVersionAudit.missing_critical_count ?? 0} 个`} />
                <MiniMetric label="可恢复版本" value={`${promptVersionAudit.recoverable_version_count ?? 0} 个`} />
                <MiniMetric label="场景孤岛风险" value={promptVersionAudit.is_scene_only_candidate ? '是' : '否'} />
              </div>
            </div>
            {recommendedRestoreVersion?.version ? (
              <button
                type="button"
                onClick={() => { void onRollbackRecommendedPromptVersion() }}
                disabled={historyActionState === 'saving'}
                className="rounded-lg border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-100 transition hover:border-amber-300 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
              >
                {historyActionState === 'saving'
                  ? '恢复中...'
                  : `恢复推荐版本 v${String(recommendedRestoreVersion.version)}`}
              </button>
            ) : null}
          </div>
          {recommendedRestoreVersion?.version ? (
            <div className="mt-3 text-[11px] text-amber-100/80">
              推荐原因：{getPromptRestoreReasonLabel(recommendedRestoreVersion.reason)}
            </div>
          ) : null}
          {recommendedRestoreVersion?.version ? (
            <div className={`mt-1 text-[11px] ${restoreOutcomeMeta.tone}`}>
              {restoreOutcomeMeta.label}
            </div>
          ) : null}
        </div>
      ) : null}

      {compilerChecks.length > 0 ? (
        <div className="mt-4 space-y-2">
          {compilerChecks.map((check, index) => {
            const passed = check.passed !== false
            return (
              <div key={`${check.key || 'check'}-${index}`} className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded-full border px-2 py-0.5 text-[11px] ${passed ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200' : 'border-amber-500/30 bg-amber-500/10 text-amber-200'}`}>
                    {passed ? '通过' : '待处理'}
                  </span>
                  <span className="text-sm text-slate-200">{check.label || check.key || `检查项 ${index + 1}`}</span>
                </div>
                {check.message ? <div className="mt-2 text-xs leading-5 text-slate-400">{check.message}</div> : null}
                {Array.isArray(check.details) && check.details.length > 0 ? (
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-500">
                    {check.details.map((detail, detailIndex) => <li key={`${index}-${detailIndex}`}>{detail}</li>)}
                  </ul>
                ) : null}
              </div>
            )
          })}
        </div>
      ) : null}

      {compilerFocusCards.length > 0 ? (
        <div className="mt-4 grid gap-3 xl:grid-cols-2">
          {compilerFocusCards.map((card) => (
            <div key={card.key} className={`rounded-lg border p-4 ${card.tone}`}>
              <div className="text-sm font-medium">{card.title}</div>
              <div className="mt-1 text-xs leading-5 opacity-90">{card.detail}</div>
              {card.items.length > 0 ? (
                <ul className="mt-3 list-disc space-y-1 pl-5 text-xs opacity-90">
                  {card.items.map((item, index) => <li key={`${card.key}-${index}`}>{item}</li>)}
                </ul>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {compilerWarnings.length > 0 ? (
        <div className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
          <div className="text-xs font-medium text-amber-200">编译告警</div>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-amber-100/90">
            {compilerWarnings.map((item, index) => <li key={`warning-${index}`}>{item}</li>)}
          </ul>
        </div>
      ) : null}

      {blockingIssues.length > 0 ? (
        <div className="mt-4 rounded-lg border border-rose-500/20 bg-rose-500/5 p-3">
          <div className="text-xs font-medium text-rose-200">阻塞问题</div>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-rose-100/90">
            {blockingIssues.map((item, index) => <li key={`blocking-${index}`}>{item}</li>)}
          </ul>
        </div>
      ) : null}

      {compileContextWarnings.length > 0 ? (
        <div className="mt-4 rounded-lg border border-slate-700 bg-slate-950/60 p-3">
          <div className="text-xs font-medium text-slate-200">编译上下文补充提示</div>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-400">
            {compileContextWarnings.map((item, index) => <li key={`context-warning-${index}`}>{item}</li>)}
          </ul>
        </div>
      ) : null}

      {compilerMetricItems.length > 0 ? (
        <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {compilerMetricItems.map((item) => <MiniMetric key={item.key} label={item.label} value={item.value} />)}
        </div>
      ) : null}
    </CollapsiblePanel>
  )
}
