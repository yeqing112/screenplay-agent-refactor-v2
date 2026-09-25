import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { getProjectStatusLabel } from './productWorkspaceProjectStatus'
import type { WorkspaceSection } from './productWorkspaceAssetViewController'
import type { ProductionWorkspaceViewMode } from '../domain/productionWorkspace'

interface WorkspaceShellSection {
  id: WorkspaceSection
  label: string
  icon: LucideIcon
  group?: string
}

interface Props {
  bookTitle: string
  projectStatus: string
  section: WorkspaceSection
  sections: WorkspaceShellSection[]
  loading: boolean
  error?: string | null
  onSelectSection: (section: WorkspaceSection) => void
  getSectionBlockedReason: (section: WorkspaceSection) => string | null
  onRefreshAll: () => void
  viewMode?: ProductionWorkspaceViewMode
  onViewModeChange?: (mode: ProductionWorkspaceViewMode) => void
  children: ReactNode
}

export default function ProductWorkspaceShell({
  bookTitle,
  projectStatus,
  section,
  sections,
  loading,
  error,
  onSelectSection,
  getSectionBlockedReason,
  onRefreshAll,
  viewMode = 'standard',
  onViewModeChange = () => undefined,
  children,
}: Props) {
  const currentSectionLabel = sections.find((item) => item.id === section)?.label ?? '项目控制台'
  const projectStatusLabel = getProjectStatusLabel(projectStatus)
  const sectionGroups = sections.reduce<Array<{ label: string; items: WorkspaceShellSection[] }>>((groups, item) => {
    const label = item.group || '工作区'
    const existing = groups.find((group) => group.label === label)
    if (existing) {
      existing.items.push(item)
    } else {
      groups.push({ label, items: [item] })
    }
    return groups
  }, [])

  return (
    <div className="flex h-full min-w-0 bg-slate-950 text-slate-200">
      <aside className="hidden w-72 shrink-0 overflow-y-auto border-r border-slate-800 bg-slate-950 p-4 md:block">
        <div className="rounded-xl border border-violet-500/20 bg-violet-500/10 p-3">
          <div className="text-[11px] uppercase tracking-[0.2em] text-violet-300/80">Workspace</div>
          <div className="mt-1 text-base font-semibold text-white">正式产品工作台</div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-300">
            <span className="max-w-full truncate">{bookTitle}</span>
            <span className="rounded-full border border-violet-400/30 bg-violet-950/40 px-2 py-0.5 text-violet-100">
              {projectStatusLabel}
            </span>
          </div>
        </div>

        <nav className="mt-6 space-y-5" aria-label="正式工作台导航">
          {sectionGroups.map((group) => (
            <div key={group.label}>
              <div className="mb-1 px-3 text-[10px] font-medium uppercase tracking-[0.16em] text-slate-600">{group.label}</div>
              <div className="space-y-1">
                {group.items.map((item) => {
                  const Icon = item.icon
                  const active = section === item.id
                  const blockedReason = getSectionBlockedReason(item.id)
                  const effectiveBlockedReason = loading ? null : blockedReason

                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => {
                        if (!effectiveBlockedReason) onSelectSection(item.id)
                      }}
                      title={effectiveBlockedReason ?? item.label}
                      aria-disabled={effectiveBlockedReason ? 'true' : 'false'}
                      aria-current={active ? 'page' : undefined}
                      className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 ${
                        effectiveBlockedReason
                          ? 'cursor-not-allowed text-slate-600'
                          : active
                            ? 'bg-slate-800 text-white'
                            : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
                      }`}
                    >
                      <Icon className="h-4 w-4" />
                      <span className="flex-1">{item.label}</span>
                      {effectiveBlockedReason ? <span className="text-[10px] text-slate-600">锁定</span> : null}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </nav>

      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto">
        <header className="sticky top-0 z-10 border-b border-slate-800 bg-slate-950/95 px-4 py-3 backdrop-blur md:px-6 md:py-4">
          <div className="flex flex-col items-stretch gap-3 md:flex-row md:items-center md:justify-between md:gap-4">
            <div>
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500">正式产品工作区</div>
              <h1 className="mt-1 text-xl font-semibold text-white md:text-2xl">{currentSectionLabel}</h1>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center rounded-lg border border-slate-800 bg-slate-900 p-0.5" aria-label="工作区视图模式">
                {(['standard', 'professional'] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    aria-pressed={viewMode === mode}
                    onClick={() => onViewModeChange(mode)}
                    className={`rounded-md px-2.5 py-1.5 text-xs transition ${viewMode === mode ? 'bg-violet-600 text-white' : 'text-slate-400 hover:text-white'}`}
                  >
                    {mode === 'standard' ? '标准视图' : '专业视图'}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={onRefreshAll}
                className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-700 hover:text-white"
              >
                刷新项目数据
              </button>
              {loading ? (
                <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs text-amber-300">
                  正在同步项目数据
                </span>
              ) : (
                <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-300">
                  已接入真实项目数据
                </span>
              )}
            </div>
          </div>

          <label className="mt-3 block md:hidden">
            <span className="sr-only">选择工作台页面</span>
            <select
              aria-label="选择工作台页面"
              value={section}
              onChange={(event) => {
                const nextSection = event.target.value as WorkspaceSection
                if (!getSectionBlockedReason(nextSection)) onSelectSection(nextSection)
              }}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-violet-400 focus:outline-none"
            >
              {sections.map((item) => {
                const blockedReason = getSectionBlockedReason(item.id)
                return (
                  <option key={item.id} value={item.id} disabled={Boolean(blockedReason)}>
                    {item.label}{blockedReason ? '（锁定）' : ''}
                  </option>
                )
              })}
            </select>
          </label>
        </header>

        <div className="px-4 py-4 md:px-6 md:py-6">
          {error ? (
            <div className="mb-6 rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
              项目数据读取失败：{error}
            </div>
          ) : null}

          {children}
        </div>
      </main>
    </div>
  )
}
