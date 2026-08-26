import type { StoryboardShotOutput } from '../domain/bookOutputs'
import {
  getCompilerDiagnosticMeta,
  getPromptReferenceStatusLabel,
} from './productWorkspacePrompt'
import { CollapsiblePanel } from './ProductWorkspaceStoryboardUi'

type PromptVersionRecordLike = Record<string, unknown> & {
  id?: string | number
  version?: string | number
  compile_reason?: string
  prompt_static?: string
  prompt_motion?: string
  negative_prompt?: string
  is_current?: boolean
  is_locked_version?: boolean
  compiler_diagnostics?: StoryboardShotOutput['compiler_diagnostics']
  version_audit?: StoryboardShotOutput['prompt_version_audit']
  locked_reference_summary?: {
    all?: Array<{
      id?: string | number
      scope?: string
      subject?: string
      title?: string
      token?: string
      status?: string
    }>
  }
  prompt_compile_context?: StoryboardShotOutput['prompt_compile_context']
  created_at?: string | null
}

type RecommendedRestoreVersionLike = {
  version?: string | number
  reason?: string
} | null

type HistoryState = 'idle' | 'loading' | 'loaded' | 'error'
type ActionState = 'idle' | 'saving' | 'success' | 'error'

export function getPromptCompileReasonMeta(reason: string | undefined) {
  const normalized = String(reason || '').trim()
  if (!normalized || normalized === 'manual') {
    return { label: '手动编译', detail: '由当前镜头手动触发编译。' }
  }
  if (normalized.startsWith('manual-')) {
    const manualReason = normalized.replace(/^manual-/, '').replace(/-/g, ' ').trim()
    return {
      label: '手动重编译',
      detail: manualReason ? `触发原因：${manualReason}` : '由当前镜头手动重新编译。',
    }
  }
  if (normalized === 'history-rollback') {
    return { label: '历史回滚', detail: '从历史提示词版本恢复当前镜头。' }
  }

  const rollbackMatch = normalized.match(/^rollback:v([^:]+):(.+)$/i)
  if (rollbackMatch) {
    const sourceVersion = String(rollbackMatch[1] || '').trim()
    const rollbackReason = String(rollbackMatch[2] || '').trim()
    const rollbackReasonLabel =
      rollbackReason === 'manual-rollback'
        ? '从历史版本恢复当前镜头'
        : rollbackReason.replace(/-/g, ' ').trim()
    return {
      label: `版本回滚 · 源自 v${sourceVersion || '-'}`,
      detail: rollbackReasonLabel ? `回滚说明：${rollbackReasonLabel}` : '从历史版本恢复当前镜头。',
    }
  }

  if (normalized.startsWith('batch-')) {
    const batchReason = normalized.replace(/^batch-/, '').replace(/-/g, ' ').trim()
    return {
      label: '批量编译',
      detail: batchReason ? `批量来源：${batchReason}` : '由批量操作触发编译。',
    }
  }

  return { label: normalized, detail: '保留原始编译原因。' }
}

export function getPromptRestoreReasonLabel(reason: string | undefined) {
  const normalized = String(reason || '').trim()
  if (normalized === 'latest_recoverable_version') return '最新可恢复版本'
  if (normalized === 'best_partial_recovery_version') return '最佳部分恢复版本'
  return normalized ? normalized.replace(/_/g, ' ') : '推荐恢复版本'
}

export function buildPromptVersionAuditSummary(audit: StoryboardShotOutput['prompt_version_audit'] | null | undefined) {
  if (!audit) return null
  const missingCriticalAssets = Array.isArray(audit.missing_critical_assets) ? audit.missing_critical_assets.filter(Boolean) : []
  const missingUsedAssetNames = Array.isArray(audit.missing_used_asset_names) ? audit.missing_used_asset_names.filter(Boolean) : []
  const lines: string[] = []

  if (audit.is_scene_only_candidate) {
    lines.push('当前版本接近“只有场景、缺角色/关键道具”的退化状态。')
  }
  if (missingCriticalAssets.length > 0) {
    lines.push(`缺失关键资产：${missingCriticalAssets.join(' / ')}`)
  }
  if (missingUsedAssetNames.length > 0) {
    lines.push(`used_assets 未覆盖：${missingUsedAssetNames.join(' / ')}`)
  }
  if (audit.is_recoverable_version) {
    lines.push('该版本仍可作为恢复候选。')
  }
  if (!lines.length && audit.is_degraded_version) {
    lines.push('当前版本存在结构化引用退化风险，建议复核并考虑恢复。')
  }

  return {
    missingCriticalAssets,
    missingUsedAssetNames,
    summary: lines.join(' '),
  }
}

function formatVersionTimestamp(value: string | undefined | null) {
  if (!value) return '未记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function getCompileContextReferenceSourceLabel(value: string) {
  const normalized = value.trim().toLowerCase()
  if (!normalized) return value
  if (normalized === 'selected') return '默认参考'
  if (normalized === 'locked') return '已锁定'
  if (normalized === 'candidate') return '候选参考'
  if (normalized === 'rejected') return '已淘汰'
  if (normalized === 'missing') return '未绑定参考图'
  if (normalized === 'current_makeup') return '当前精调定妆'
  if (normalized === 'current_variant') return '当前变体'
  return value
}

function sanitizeCompileContextString(key: string, value: string) {
  const trimmed = value.trim()
  if (!trimmed) return value
  if (/^episode_(\d+)_default$/i.test(trimmed)) {
    const match = trimmed.match(/^episode_(\d+)_default$/i)
    return `第${match?.[1] || '?'}集默认造型`
  }
  if (trimmed === 'episode_default') return '分集默认'
  if (trimmed === 'scene_variant') return '场景变体'
  if (trimmed === 'prop_variant') return '道具变体'
  if (trimmed === 'active_variant') return '当前变体'
  if (trimmed === 'scene_asset') return '场景资产权威源'
  if (trimmed === 'character_makeup') return '人物定妆权威源'
  if (trimmed === 'prop_asset') return '道具资产权威源'
  if (key === 'image_url' && trimmed.startsWith('data:image/')) {
    const mimeMatch = trimmed.match(/^data:(image\/[a-zA-Z0-9.+-]+);/i)
    const mimeType = mimeMatch?.[1] || 'image/*'
    return `[内嵌参考图已省略：${mimeType}]`
  }
  if (key === 'reference_status') return getPromptReferenceStatusLabel(trimmed)
  if (key === 'reference_source') return getCompileContextReferenceSourceLabel(trimmed)
  if (key === 'authority_prompt_raw' || key === 'canonical_prompt_raw') {
    return '[详细提示词已折叠，请以上方权威源摘要为准]'
  }
  if (trimmed.length > 600) {
    return `${trimmed.slice(0, 240)}... [内容过长，已截断，共 ${trimmed.length} 字符]`
  }
  return value
}

export function sanitizeCompileContextForDisplay(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeCompileContextForDisplay(item))
  }

  if (!value || typeof value !== 'object') return value

  const entries = Object.entries(value as Record<string, unknown>).map(([key, itemValue]) => {
    if (key === 'reference_summary') {
      return [key, '[已省略内部引用统计，请以上方 Prompt 引用摘要为准]']
    }
    if (key === 'reference_asset_ids') {
      return [key, '[已省略内部引用 ID 列表]']
    }
    if (key === 'reference_images') {
      return [key, '[已省略参考图载荷明细，请以上方参考图预览为准]']
    }
    if (key === 'authority_prompt_parts' || key === 'canonical_prompt_parts') {
      return [key, '[已省略详细拆解，请以上方权威源摘要为准]']
    }

    if (Array.isArray(itemValue) && key === 'reference_statuses') {
      return [key, itemValue.map((status) => (typeof status === 'string' ? getPromptReferenceStatusLabel(status) : status))]
    }

    if (typeof itemValue === 'string') {
      return [key, sanitizeCompileContextString(key, itemValue)]
    }
    return [key, sanitizeCompileContextForDisplay(itemValue)]
  })

  return Object.fromEntries(entries)
}

export function ProductWorkspacePromptHistoryPanel({
  promptVersions,
  historyState,
  historyActionState,
  historyActionMessage,
  promptLockState,
  promptLockMessage,
  hasCompiledPrompt,
  isPromptLocked,
  recommendedRestoreVersion,
  onTogglePromptLock,
  onRollbackPromptVersion,
}: {
  promptVersions: PromptVersionRecordLike[]
  historyState: HistoryState
  historyActionState: ActionState
  historyActionMessage: string
  promptLockState: ActionState
  promptLockMessage: string
  hasCompiledPrompt: boolean
  isPromptLocked?: boolean
  recommendedRestoreVersion: RecommendedRestoreVersionLike
  onTogglePromptLock: () => void | Promise<void>
  onRollbackPromptVersion: (versionId: string | number | undefined) => void | Promise<void>
}) {
  return (
    <CollapsiblePanel
      title="提示词历史版本"
      description={
        historyState === 'loading'
          ? '正在加载历史版本'
          : historyState === 'error'
            ? '历史版本加载失败'
            : historyState === 'loaded'
              ? `${promptVersions.length} 个版本`
              : '当前镜头会保留编译版本记录'
      }
    >
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => { void onTogglePromptLock() }}
          disabled={promptLockState === 'saving' || !hasCompiledPrompt}
          className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${
            isPromptLocked
              ? 'border-amber-500/40 bg-amber-500/10 text-amber-100 hover:border-amber-300 hover:text-white'
              : 'border-slate-700 text-slate-300 hover:border-sky-500 hover:text-white'
          }`}
        >
          {promptLockState === 'saving'
            ? '保存中...'
            : isPromptLocked
              ? '已锁定提示词'
              : '锁定当前版本'}
        </button>
      </div>

      {promptLockMessage ? (
        <div
          className={`mt-4 rounded-xl border p-3 text-sm ${
            promptLockState === 'error'
              ? 'border-rose-500/20 bg-rose-500/5 text-rose-200'
              : 'border-emerald-500/20 bg-emerald-500/5 text-emerald-200'
          }`}
        >
          {promptLockMessage}
        </div>
      ) : null}

      {promptVersions.length > 0 ? (
        <div className="mt-4 space-y-3">
          {promptVersions.map((version) => (
            <details key={String(version.id || version.version || Math.random())} className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
              <summary className="cursor-pointer text-sm text-slate-300">
                v{String(version.version ?? '-')} · {getPromptCompileReasonMeta(version.compile_reason).label}
              </summary>
              <div className="mt-3 space-y-3">
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                  <span className={`rounded-full border px-2 py-0.5 ${getCompilerDiagnosticMeta(version.compiler_diagnostics?.status).tone}`}>
                    {getCompilerDiagnosticMeta(version.compiler_diagnostics?.status).label}
                  </span>
                  {version.is_current ? (
                    <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-sky-200">
                      当前版本
                    </span>
                  ) : null}
                  {version.is_locked_version ? (
                    <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-200">
                      锁定版本
                    </span>
                  ) : null}
                  <span>创建时间：{formatVersionTimestamp(version.created_at)}</span>
                </div>
                <div className="text-xs leading-5 text-slate-500">
                  {getPromptCompileReasonMeta(version.compile_reason).detail}
                </div>

                {version.version_audit?.is_degraded_version ? (
                  <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                    <div className="text-[11px] font-medium text-amber-200">该历史版本也存在退化风险</div>
                    <div className="mt-1 text-[11px] leading-5 text-amber-100/90">
                      {buildPromptVersionAuditSummary(version.version_audit)?.summary || '该版本存在关键资产缺失，请谨慎恢复。'}
                    </div>
                  </div>
                ) : null}

                {recommendedRestoreVersion?.version !== undefined &&
                String(version.version ?? '') === String(recommendedRestoreVersion.version) ? (
                  <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3 text-[11px] text-emerald-100">
                    系统建议优先恢复到这个版本。原因：{getPromptRestoreReasonLabel(recommendedRestoreVersion.reason)}
                  </div>
                ) : null}

                {Array.isArray(version.locked_reference_summary?.all) && version.locked_reference_summary.all.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {version.locked_reference_summary.all.map((item, index) => (
                      <span
                        key={`${item.id || item.scope || 'ref'}-${index}`}
                        className="rounded-full border border-slate-700 px-2 py-1 text-[11px] text-slate-300"
                      >
                        {item.subject || item.title || '未命名参考'}
                        {item.token ? ` · ${item.token}` : ''}
                        {item.status ? ` · ${getPromptReferenceStatusLabel(item.status)}` : ''}
                      </span>
                    ))}
                  </div>
                ) : null}

                <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                  <div className="text-[11px] text-slate-500">静态提示词</div>
                  <div className="mt-2 whitespace-pre-wrap text-xs leading-5 text-slate-300">{String(version.prompt_static || '-')}</div>
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                  <div className="text-[11px] text-slate-500">运动提示词</div>
                  <div className="mt-2 whitespace-pre-wrap text-xs leading-5 text-slate-300">{String(version.prompt_motion || '-')}</div>
                </div>
                <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                  <div className="text-[11px] text-slate-500">负向提示词</div>
                  <div className="mt-2 whitespace-pre-wrap text-xs leading-5 text-slate-300">{String(version.negative_prompt || '-')}</div>
                </div>

                {version.prompt_compile_context ? (
                  <details className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                    <summary className="cursor-pointer text-[11px] text-slate-400">查看当时的编译上下文</summary>
                    <pre className="mt-3 max-w-full overflow-auto rounded bg-slate-950 p-2 text-xs text-slate-300">
                      {JSON.stringify(sanitizeCompileContextForDisplay(version.prompt_compile_context), null, 2)}
                    </pre>
                  </details>
                ) : null}

                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => { void onRollbackPromptVersion(version.id) }}
                    disabled={historyActionState === 'saving' || Boolean(version.is_current)}
                    className="rounded-lg border border-slate-700 px-3 py-1.5 text-[11px] text-slate-300 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {version.is_current
                      ? '当前使用中'
                      : historyActionState === 'saving'
                        ? '回滚中...'
                        : '回滚到此版本'}
                  </button>
                </div>
              </div>
            </details>
          ))}
        </div>
      ) : historyState === 'loaded' ? (
        <div className="mt-4 rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
          当前镜头还没有历史版本记录。
        </div>
      ) : historyState === 'error' ? (
        <div className="mt-4 rounded-xl border border-rose-500/20 bg-rose-500/5 p-4 text-sm text-rose-200">
          历史版本暂时加载失败，刷新镜头后可重试。
        </div>
      ) : null}

      {historyActionMessage ? (
        <div
          className={`mt-4 rounded-xl border p-3 text-sm ${
            historyActionState === 'error'
              ? 'border-rose-500/20 bg-rose-500/5 text-rose-200'
              : historyActionState === 'success'
                ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-200'
                : 'border-slate-700 bg-slate-950/60 text-slate-300'
          }`}
        >
          {historyActionMessage}
        </div>
      ) : null}
    </CollapsiblePanel>
  )
}
