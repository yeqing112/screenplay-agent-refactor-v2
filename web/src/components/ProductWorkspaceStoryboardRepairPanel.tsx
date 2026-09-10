import { getPromptReferenceScopeLabel } from './productWorkspacePrompt'
import { normalizeReferenceAssetType } from './productWorkspaceStoryboardBindings'

type UsedAssetLike = {
  asset_id?: string | number
  asset_name?: string
  asset_type?: string
}

type StoryboardRepairActionLike = {
  key: string
  title: string
  detail: string
  cta: string
  onClick?: () => void
  disabled?: boolean
}

type CompileActionState = 'idle' | 'saving' | 'success' | 'error'

export function splitStoryboardRepairActions<T>(actions: T[]) {
  return { primary: actions[0] ?? null, remaining: actions.slice(1) }
}

function getDisplayAssetTypeLabel(assetType: string | undefined) {
  return getPromptReferenceScopeLabel(normalizeReferenceAssetType(assetType) || 'reference')
}

export function ProductWorkspaceStoryboardRepairPanel({
  usedAssets,
  repairActions,
  compileActionState,
  compileActionMessage,
}: {
  usedAssets: UsedAssetLike[]
  repairActions: StoryboardRepairActionLike[]
  compileActionState: CompileActionState
  compileActionMessage: string
}) {
  const { primary: primaryRepairAction, remaining: remainingRepairActions } = splitStoryboardRepairActions(repairActions)

  return (
    <>
      {usedAssets.length > 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="text-sm font-medium text-white">本次实际引用资产</div>
          <div className="mt-3 flex flex-wrap gap-2">
            {usedAssets.map((asset, index) => (
              <span
                key={`${asset.asset_id || asset.asset_name || 'asset'}-${index}`}
                className="rounded-full border border-slate-700 px-2 py-1 text-[11px] text-slate-300"
              >
                {getDisplayAssetTypeLabel(asset.asset_type)} · {asset.asset_name || asset.asset_id || '未命名资产'}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {repairActions.length > 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-medium text-white">当前修复入口</div>
            <div className="text-xs text-slate-500">把当前镜头最该先做的动作直接串到对应工作台</div>
          </div>
          {primaryRepairAction ? <div className="mt-4 grid gap-3">
            {[primaryRepairAction].map((action) => (
              <div key={action.key} className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="text-sm text-slate-100">{action.title}</div>
                    <div className="mt-1 text-xs leading-5 text-slate-400">{action.detail}</div>
                  </div>
                  <button
                    type="button"
                    onClick={action.onClick}
                    disabled={action.disabled}
                    className={`rounded-lg border px-3 py-2 text-xs transition ${
                      action.disabled
                        ? 'cursor-not-allowed border-slate-800 text-slate-600'
                        : 'border-slate-700 text-slate-300 hover:border-sky-500 hover:text-white'
                    }`}
                  >
                    {action.cta}
                  </button>
                </div>
              </div>
            ))}
          </div> : null}
          {remainingRepairActions.length > 0 ? (
            <details className="mt-3 rounded-xl border border-slate-800 bg-slate-950/40 p-3">
              <summary className="cursor-pointer text-xs font-medium text-slate-300">
                还有 {remainingRepairActions.length} 项准备工作
              </summary>
              <div className="mt-3 grid gap-3">
                {remainingRepairActions.map((action) => (
                  <div key={action.key} className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="text-sm text-slate-200">{action.title}</div>
                        <div className="mt-1 text-xs leading-5 text-slate-400">{action.detail}</div>
                      </div>
                      <button
                        type="button"
                        onClick={action.onClick}
                        disabled={action.disabled}
                        className={`rounded-lg border px-3 py-2 text-xs transition ${
                          action.disabled
                            ? 'cursor-not-allowed border-slate-800 text-slate-600'
                            : 'border-slate-700 text-slate-300 hover:border-sky-500 hover:text-white'
                        }`}
                      >
                        {action.cta}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </details>
          ) : null}
          {compileActionMessage ? (
            <div
              role="status"
              aria-live="polite"
              className={`mt-4 rounded-xl border p-3 text-sm ${
                compileActionState === 'error'
                  ? 'border-rose-500/20 bg-rose-500/5 text-rose-200'
                  : compileActionState === 'success'
                    ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-200'
                    : 'border-slate-700 bg-slate-950/60 text-slate-300'
              }`}
            >
              {compileActionMessage}
            </div>
          ) : null}
        </div>
      ) : null}
    </>
  )
}
