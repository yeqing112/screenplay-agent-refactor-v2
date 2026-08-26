import type { PromptAuthoritySummary } from './productWorkspacePrompt'
import { getPromptReferenceScopeLabel } from './productWorkspacePrompt'

export function ProductWorkspacePromptAuthorityPanel({
  promptAuthoritySummary,
  compileContextDisplay,
}: {
  promptAuthoritySummary: PromptAuthoritySummary
  compileContextDisplay: unknown
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-medium text-white">编译权威源摘要</div>
        <div className="flex flex-wrap gap-2 text-[11px] text-slate-400">
          <span>绑定资产 {promptAuthoritySummary.items.length}</span>
          <span>约束 {promptAuthoritySummary.constraintCount}</span>
          <span>反馈 {promptAuthoritySummary.noteCount}</span>
          <span>告警 {promptAuthoritySummary.warningCount}</span>
        </div>
      </div>

      {promptAuthoritySummary.items.length > 0 ? (
        <div className="mt-3 space-y-2">
          {promptAuthoritySummary.items.map((item) => (
            <details key={item.key} className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
              <summary className="cursor-pointer list-none">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-300">
                        {getPromptReferenceScopeLabel(item.scope)}
                      </span>
                      <div className="font-medium text-white">{item.name}</div>
                      {item.variantLabel ? (
                        <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-400">
                          {item.variantLabel}
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-2 text-xs leading-5 text-slate-500">
                      {item.authorityPromptExcerpt || '当前还没有可展示的权威摘要。'}
                    </div>
                  </div>
                  <div className="text-[11px] text-slate-500">展开详情</div>
                </div>
              </summary>
              <div className="mt-3 space-y-1 border-t border-slate-800 pt-3 text-[11px] text-slate-400">
                <div>资产 ID：<span className="text-slate-300">{item.assetId || '-'}</span></div>
                <div>引用 token：<span className="text-slate-300">{item.token || '-'}</span></div>
                <div>生效版本：<span className="text-slate-300">{item.variantLabel || '-'}</span></div>
                <div>参考来源：<span className="text-slate-300">{item.referenceSourceLabel || '-'}</span></div>
                <div>参考状态：<span className="text-slate-300">{item.referenceStatusLabel || '-'}</span></div>
                <div>权威来源：<span className="text-slate-300">{item.authorityPromptSource || '-'}</span></div>
              </div>
            </details>
          ))}
        </div>
      ) : (
        <div className="mt-3 rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
          当前还没有可读的编译权威源摘要。
        </div>
      )}

      <details className="mt-3 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
        <summary className="cursor-pointer text-xs text-slate-400">查看原始编译上下文 JSON</summary>
        <pre className="mt-3 max-w-full overflow-auto rounded bg-slate-950 p-2 text-xs text-slate-300">{JSON.stringify(compileContextDisplay, null, 2)}</pre>
      </details>
    </div>
  )
}
