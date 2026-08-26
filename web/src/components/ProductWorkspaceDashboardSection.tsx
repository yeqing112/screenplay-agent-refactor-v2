import type { DashboardAction, EpisodeProgress } from './productWorkspaceProgress'

type DashboardTargetSection = 'content' | 'adaptation' | 'scripts' | 'storyboard' | 'assets' | 'qa' | 'delivery'

interface SummaryStats {
  contentReady: boolean
  chapterCount: number
  wordCount: number
  episodesWithScripts: number
  totalShots: number
  visualCount: number
  qaCount: number
}

interface Props {
  summary: SummaryStats
  adaptationStateLabel: string
  adaptationStateDetail: string
  episodeProgress: EpisodeProgress[]
  dashboardActions: DashboardAction[]
  onNavigate: (target: DashboardTargetSection) => void
}

function StatusSummaryItem({ title, value, detail }: { title: string; value: string; detail: string }) {
  return (
    <div className="min-w-[140px] flex-1 rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2">
      <div className="text-xs text-slate-400">{title}</div>
      <div className="mt-1 text-lg font-semibold text-white">{value}</div>
      <div className="mt-1 line-clamp-2 text-[11px] leading-5 text-slate-500">{detail}</div>
    </div>
  )
}

export default function ProductWorkspaceDashboardSection({
  summary,
  adaptationStateLabel,
  adaptationStateDetail,
  episodeProgress,
  dashboardActions,
  onNavigate,
}: Props) {
  const primaryAction = dashboardActions[0] ?? null
  const secondaryActions = dashboardActions.slice(1)

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-800 bg-slate-900/90 p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="text-sm font-medium text-white">项目状态摘要</div>
          <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">
            生产链路
          </span>
        </div>
        <div className="flex flex-wrap gap-3">
        <StatusSummaryItem
          title={'\u5185\u5bb9\u51c6\u5907'}
          value={summary.contentReady ? '\u5df2\u5efa\u7acb' : '\u672a\u5b8c\u6210'}
          detail={`${summary.chapterCount} \u7ae0 / ${((summary.wordCount || 0) / 10000).toFixed(1)} \u4e07\u5b57`}
        />
        <StatusSummaryItem title={'\u6539\u7f16\u65b9\u5411'} value={adaptationStateLabel} detail={adaptationStateDetail} />
        <StatusSummaryItem
          title={'\u5267\u672c\u9636\u6bb5'}
          value={`${summary.episodesWithScripts} \u96c6`}
          detail={'\u5f53\u524d\u5df2\u6709\u6b63\u5f0f\u5267\u672c\u8f93\u51fa\u7684\u96c6\u6570'}
        />
        <StatusSummaryItem
          title={'\u5206\u955c\u9636\u6bb5'}
          value={`${summary.totalShots} \u955c`}
          detail={'\u5f53\u524d\u9879\u76ee\u5df2\u5b58\u5728\u7684\u955c\u5934\u603b\u91cf'}
        />
        <StatusSummaryItem
          title={'\u8d44\u4ea7\u4e2d\u5fc3'}
          value={`${summary.visualCount}`}
          detail={'\u4eba\u7269\u3001\u573a\u666f\u3001\u9053\u5177\u8d44\u4ea7\u603b\u6570'}
        />
        <StatusSummaryItem
          title={'QA \u963b\u585e'}
          value={`${summary.qaCount}`}
          detail={'\u5f53\u524d\u7d2f\u8ba1\u53ef\u89c1\u95ee\u9898\u6570'}
        />
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.2fr,1fr]">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="text-sm font-medium text-white">{'\u5355\u96c6 readiness \u603b\u89c8'}</div>
          <div className="mt-4 space-y-3">
            {episodeProgress.length > 0 ? (
              episodeProgress.map((item) => (
                <div key={item.episode} className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-white">
                        {'\u7b2c '}{item.episode}{' \u96c6'}
                      </div>
                      <div className="mt-1 text-xs text-slate-500">{item.progressLabel}</div>
                    </div>
                    <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">
                      {item.statusLabel}
                    </span>
                  </div>
                  <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
                    <span>{'\u963b\u585e\u9879 '}{item.blockerCount}</span>
                    <span>{item.nextAction}</span>
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
                {'\u5f53\u524d\u8fd8\u6ca1\u6709\u53ef\u6c47\u603b\u7684\u5355\u96c6\u751f\u4ea7\u6570\u636e\uff0c\u5148\u4ece\u5185\u5bb9\u51c6\u5907\u5f00\u59cb\u5efa\u7acb\u6b63\u5f0f\u94fe\u8def\u3002'}
              </div>
            )}
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-xl border border-sky-500/20 bg-sky-500/10 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm font-medium text-white">下一步行动</div>
                <div className="mt-2 text-base font-semibold text-sky-50">
                  {primaryAction?.title || '当前没有新的阻塞'}
                </div>
                <div className="mt-2 text-sm leading-6 text-sky-100/80">
                  {primaryAction?.description || '可以继续按当前模块检查生产链路，或进入单集 readiness 总览复核。'}
                </div>
              </div>
              {primaryAction ? (
                <button
                  type="button"
                  onClick={() => onNavigate(primaryAction.targetSection)}
                  className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-sky-500"
                >
                  立即前往
                </button>
              ) : null}
            </div>
            {secondaryActions.length > 0 ? (
              <details className="mt-4 rounded-lg border border-sky-400/20 bg-slate-950/30 p-3">
                <summary className="cursor-pointer text-xs font-medium text-sky-100">更多建议动作</summary>
                <div className="mt-3 space-y-2">
                  {secondaryActions.map((action) => (
                    <button
                      key={`${action.targetSection}-${action.title}`}
                      type="button"
                      onClick={() => onNavigate(action.targetSection)}
                      className="w-full rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-left transition hover:border-slate-700"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm font-medium text-white">{action.title}</div>
                        <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">
                          {action.priority}
                        </span>
                      </div>
                      <div className="mt-1 text-xs leading-5 text-slate-400">{action.description}</div>
                    </button>
                  ))}
                </div>
              </details>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
