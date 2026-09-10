import type { DashboardAction, ProjectStageProjection } from './productWorkspaceProgress'

type WorkspaceTarget = DashboardAction['targetSection']

export function ProductWorkspaceProjectStageStrip({
  projection,
  activeSection,
  onNavigate,
}: {
  projection: ProjectStageProjection
  activeSection: string
  onNavigate: (section: WorkspaceTarget) => void
}) {
  const isCurrentWorkspace = activeSection === projection.primaryAction.targetSection

  return (
    <section className="mb-5 rounded-xl border border-slate-800 bg-slate-900/80 p-4" aria-label="项目当前进度">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs font-medium tracking-wide text-slate-400">项目当前进度</div>
          <div className="mt-1 text-sm font-medium text-white">正在：{projection.currentStageLabel}</div>
        </div>
        <span className="rounded-full border border-sky-400/30 bg-sky-500/10 px-2 py-1 text-[11px] text-sky-100">
          当前步骤
        </span>
      </div>
      <ol className="mt-3 flex flex-wrap gap-x-3 gap-y-2 text-[11px]" aria-label="生产阶段">
        {projection.stages.map((stage) => (
          <li key={stage.key} className={stage.state === 'done' ? 'text-emerald-200' : stage.state === 'current' ? 'font-medium text-sky-100' : 'text-slate-500'}>
            {stage.state === 'done' ? '已完成 · ' : stage.state === 'current' ? '当前 · ' : ''}{stage.label}
          </li>
        ))}
      </ol>
      {!isCurrentWorkspace ? (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-400/20 bg-amber-400/5 p-3">
          <div>
            <div className="text-sm font-medium text-white">先完成：{projection.primaryAction.title}</div>
            <div className="mt-1 text-xs leading-5 text-slate-400">{projection.primaryAction.description}</div>
          </div>
          <button type="button" onClick={() => onNavigate(projection.primaryAction.targetSection)} className="rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-sky-500">
            去完成这一步
          </button>
        </div>
      ) : (
        <div className="mt-3 text-xs text-sky-100">你正在处理项目的首要步骤。完成后系统会自动提示下一阶段。</div>
      )}
    </section>
  )
}
