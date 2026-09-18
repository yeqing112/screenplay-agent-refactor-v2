import { humanizeProductionState, type ProductionWorkspaceSnapshot } from '../domain/productionWorkspace'

export default function ProductionWorkspaceAuthorityBanner({
  snapshot,
  episode,
  title,
}: {
  snapshot: ProductionWorkspaceSnapshot | null
  episode?: number | null
  title: string
}) {
  if (!snapshot) return null
  const episodeSummary = episode ? snapshot.episodes.find((item) => item.episode === episode) : null
  const blockers = (episodeSummary?.blockers ?? snapshot.project.current_blockers).slice(0, 4)
  const state = episodeSummary?.overall_state ?? snapshot.project.overall_state
  return (
    <section className="mb-5 rounded-xl border border-slate-800 bg-slate-900/80 p-4" aria-label={title}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-white">{title}</div>
          <div className="mt-1 text-xs text-slate-400">生产真相来自当前权威指针，不根据旧数量推断</div>
        </div>
        <span className="rounded-full border border-slate-700 px-2 py-1 text-[11px] text-slate-200">{humanizeProductionState(state)}</span>
      </div>
      {blockers.length > 0 ? (
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          {blockers.map((blocker) => (
            <div key={`${blocker.code}-${blocker.scene_id ?? ''}-${blocker.shot_id ?? ''}-${blocker.asset_key ?? ''}`} className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
              <div className="text-xs font-medium text-amber-100">{blocker.title}</div>
              <div className="mt-1 text-[11px] leading-5 text-slate-400">{blocker.description}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-3 text-xs text-emerald-200">当前没有来自权威投影的阻塞。</div>
      )}
    </section>
  )
}
