import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { getProjectStatusLabel } from './productWorkspaceProjectStatus'
import type { WorkspaceSection } from './productWorkspaceAssetViewController'

interface WorkspaceShellSection {
  id: WorkspaceSection
  label: string
  icon: LucideIcon
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
  children,
}: Props) {
  const currentSectionLabel = sections.find((item) => item.id === section)?.label ?? '项目控制台'
  const projectStatusLabel = getProjectStatusLabel(projectStatus)

  return (
    <div className="flex h-full bg-slate-950 text-slate-200">
      <aside className="w-72 border-r border-slate-800 bg-slate-950 p-4">
        <div className="rounded-xl border border-violet-500/20 bg-violet-500/10 p-4">
          <div className="text-xs uppercase tracking-[0.2em] text-violet-300/80">Refactor Workspace</div>
          <div className="mt-2 text-lg font-semibold text-white">正式产品工作台</div>
          <div className="mt-2 text-sm leading-6 text-slate-300">
            这里是按重构蓝图整理后的正式工作区，内容准备、改编方向、剧本、分镜、资产、QA 与交付都收敛在同一条创作链路中。
          </div>
        </div>

        <nav className="mt-6 space-y-1">
          {sections.map((item) => {
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
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition ${
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
        </nav>

        <div className="mt-6 rounded-xl border border-slate-800 bg-slate-900 p-4">
          <div className="text-sm font-medium text-white">{bookTitle}</div>
          <div className="mt-2 text-xs leading-6 text-slate-400">
            当前项目状态：{projectStatusLabel}。你可以在这里连续推进内容准备、剧本生产、分镜生成、资产补齐、QA 修复与导出交付。
          </div>
        </div>

        <div className="mt-4">
          <button
            type="button"
            onClick={onRefreshAll}
            className="w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-left text-sm text-slate-300 hover:border-slate-700 hover:text-white"
          >
            刷新项目数据
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <header className="sticky top-0 z-10 border-b border-slate-800 bg-slate-950/95 px-6 py-4 backdrop-blur">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500">正式产品工作区</div>
              <h1 className="mt-1 text-2xl font-semibold text-white">{currentSectionLabel}</h1>
            </div>
            <div className="flex items-center gap-2">
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
        </header>

        <div className="px-6 py-6">
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
