import type { ReactNode } from 'react'
import type { StoryboardShotOutput } from '../domain/bookOutputs'
import { hasDegradedPromptVersion, type StoryboardGateSummary } from './productWorkspaceStoryboard'

export function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mt-1 text-sm font-medium text-slate-100">{value}</div>
    </div>
  )
}

export function StatusPill({
  children,
  tone = 'slate',
}: {
  children: ReactNode
  tone?: 'slate' | 'sky' | 'cyan' | 'emerald' | 'amber' | 'rose'
}) {
  const toneClass = {
    slate: 'border-slate-700 bg-slate-950/60 text-slate-300',
    sky: 'border-sky-500/30 bg-sky-500/10 text-sky-200',
    cyan: 'border-cyan-500/30 bg-cyan-500/10 text-cyan-100',
    emerald: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
    amber: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
    rose: 'border-rose-500/30 bg-rose-500/10 text-rose-200',
  }[tone]

  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] ${toneClass}`}>
      {children}
    </span>
  )
}

export function CollapsiblePanel({
  title,
  description,
  children,
  defaultOpen = false,
  className = '',
}: {
  title: ReactNode
  description?: ReactNode
  children: ReactNode
  defaultOpen?: boolean
  className?: string
}) {
  return (
    <details open={defaultOpen} className={`rounded-xl border border-slate-800 bg-slate-950/40 p-4 ${className}`}>
      <summary className="cursor-pointer list-none">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-medium text-white">{title}</div>
            {description ? <div className="mt-1 text-xs leading-5 text-slate-500">{description}</div> : null}
          </div>
          <span className="rounded-full border border-slate-700 px-2 py-1 text-[10px] text-slate-400">展开</span>
        </div>
      </summary>
      <div className="mt-4">{children}</div>
    </details>
  )
}

export function getShotReadinessShortLabel(
  readiness: { statusLabel: string; blockerCount: number; nextAction: string },
  shot: StoryboardShotOutput,
) {
  if (hasDegradedPromptVersion(shot)) return '待恢复'
  const nextAction = readiness.nextAction
  if (nextAction.includes('参考资产')) return '缺参考'
  if (nextAction.includes('静态提示词') || nextAction.includes('运动提示词')) return '待重编'
  if (nextAction.includes('分镜图')) return '缺分镜图'
  if (nextAction.includes('视频')) return '待视频'
  if (readiness.blockerCount > 0) return readiness.statusLabel === '阻塞' ? '有阻塞' : '待补齐'
  if ((shot.assets?.videos?.length ?? 0) > 0) return '待验收'
  return readiness.statusLabel || '待处理'
}

export function StoryboardGateStrip({
  gate,
  selectedEpisode,
  lockedAt,
  releasedAt,
  onNavigateSection,
}: {
  gate: StoryboardGateSummary
  selectedEpisode: number | null | undefined
  lockedAt?: string | null
  releasedAt?: string | null
  onNavigateSection?: (section: 'scripts') => void
}) {
  return (
    <details
      open={gate.status !== 'ready'}
      className={`rounded-xl border p-4 ${
        gate.status === 'ready'
          ? 'border-emerald-500/15 bg-emerald-500/5'
          : 'border-rose-500/25 bg-rose-500/10'
      }`}
    >
      <summary className="cursor-pointer list-none">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <div className="text-sm font-medium text-white">上游放行</div>
            <StatusPill tone={gate.status === 'ready' ? 'emerald' : 'rose'}>
              {gate.status === 'ready' ? '已放行' : '未放行'}
            </StatusPill>
            <span className="text-xs text-slate-500">
              第 {selectedEpisode || '-'} 集 · 锁稿 {lockedAt ? '已完成' : '未完成'} · 分镜放行 {releasedAt ? '已完成' : '未完成'}
            </span>
          </div>
          <span className="rounded-full border border-slate-700 px-2 py-1 text-[10px] text-slate-400">
            {gate.status === 'ready' ? '详情' : '需处理'}
          </span>
        </div>
      </summary>

      <div className="mt-3 rounded-xl border border-slate-800 bg-slate-950/50 p-4 text-sm leading-6 text-slate-300">
        {gate.message}
      </div>

      {onNavigateSection ? (
        <button
          type="button"
          onClick={() => onNavigateSection('scripts')}
          className="mt-3 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 transition hover:border-sky-500 hover:text-white"
        >
          {gate.status === 'ready' ? '回剧本工作台复核' : '返回剧本工作台补放行'}
        </button>
      ) : null}
    </details>
  )
}

export function CurrentShotActionHeader({
  shotId,
  sceneName,
  diagnosticLabel,
  diagnosticToneClass,
  primaryActionLabel,
  primaryActionDetail,
  primaryActionIsExecutable,
  onPrimaryAction,
}: {
  shotId: string
  sceneName?: string | null
  diagnosticLabel: string
  diagnosticToneClass: string
  primaryActionLabel: string
  primaryActionDetail: string
  primaryActionIsExecutable: boolean
  onPrimaryAction: () => void
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="text-xs font-medium tracking-wide text-slate-500">当前镜头</div>
        <div className="text-lg font-semibold text-white">{shotId} {sceneName || '未命名场景'}</div>
        <div className="mt-1 text-sm text-slate-400">{primaryActionDetail}</div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full border px-2.5 py-1 text-xs ${diagnosticToneClass}`}>
          {diagnosticLabel}
        </span>
        {primaryActionIsExecutable ? (
          <button
            type="button"
            onClick={onPrimaryAction}
            className="rounded-lg bg-sky-600 px-3 py-2 text-xs font-medium text-white transition hover:bg-sky-500"
          >
            {primaryActionLabel}
          </button>
        ) : (
          <span className="rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-xs font-medium text-slate-200">
            {primaryActionLabel}
          </span>
        )}
      </div>
    </div>
  )
}

export function DirectorShotLanguageEditor({
  draft,
  sourceLabel,
  sourceTone,
  saveState,
  saveMessage,
  canSave,
  onDraftChange,
  onSaveAndRecompile,
  onRestoreSystemVersion,
}: {
  draft: string
  sourceLabel: string
  sourceTone: 'slate' | 'cyan' | 'amber'
  saveState: 'idle' | 'saving' | 'saved' | 'error'
  saveMessage: string
  canSave: boolean
  onDraftChange: (value: string) => void
  onSaveAndRecompile: () => void | Promise<void>
  onRestoreSystemVersion: () => void | Promise<void>
}) {
  return (
    <div className="mt-5 rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-white">创作内容 · 导演分镜语言编辑</div>
          <div className="mt-1 text-xs leading-5 text-cyan-100/75">
            用户看到和修改的是导演语言；提交生产前，系统再编译成面向不同模型的标准机器语言。
          </div>
        </div>
        <StatusPill tone={sourceTone}>{sourceLabel}</StatusPill>
      </div>
      <textarea
        value={draft}
        onChange={(event) => onDraftChange(event.target.value)}
        placeholder="请先加载导出预览，系统会生成可编辑的导演分镜语言。"
        className="mt-3 min-h-32 w-full rounded-lg border border-cyan-500/20 bg-slate-950 px-3 py-2 text-xs leading-6 text-slate-200 outline-none transition placeholder:text-slate-600 focus:border-cyan-500"
      />
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <div className={`text-xs ${saveState === 'error' ? 'text-rose-200' : 'text-slate-500'}`}>
          {saveMessage || '提示：这里保存的是导演语言覆盖层，最终生产仍会先编译为机器语言。'}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => { void onSaveAndRecompile() }}
            disabled={saveState === 'saving' || !canSave}
            className="rounded border border-cyan-400/30 bg-cyan-400/10 px-3 py-1.5 text-[11px] text-cyan-100 transition hover:border-cyan-300 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saveState === 'saving' ? '保存中...' : '保存并重编译导出'}
          </button>
          <details className="relative rounded border border-slate-800 bg-slate-950/60 px-2 py-1">
            <summary className="cursor-pointer list-none text-[11px] text-slate-400">高级</summary>
            <button
              type="button"
              onClick={() => { void onRestoreSystemVersion() }}
              disabled={saveState === 'saving' || !canSave}
              className="mt-2 rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition hover:border-cyan-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              恢复系统版
            </button>
          </details>
        </div>
      </div>
    </div>
  )
}
