const ACCEPTANCE_STATUS_OPTIONS = [
  { value: 'passed', label: '通过采纳' },
  { value: 'failed', label: '打回重做' },
  { value: 'pending', label: '继续观察' },
]

const ACCEPTANCE_TAG_OPTIONS = [
  { value: 'character_consistency', label: '角色一致性' },
  { value: 'character_blocking_error', label: '角色站位错误' },
  { value: 'prop_mismatch', label: '道具不一致' },
  { value: 'scene_mismatch', label: '场景不一致' },
  { value: 'style_drift', label: '风格跑偏' },
  { value: 'motion_error', label: '运动错误' },
  { value: 'camera_error', label: '镜头语言错误' },
]

type AcceptanceDraft = {
  assetKind: string
  assetId: string
  status: string
  failureTags: string[]
  notes: string
}

type AcceptanceRecordLike = {
  status?: string
  asset_kind?: string
  asset_id?: string
  failure_tags?: string[]
  notes?: string
  updated_at?: string | null
}

type AcceptanceState = 'idle' | 'saving' | 'success' | 'error'

function getAcceptanceStatusLabel(status: string | undefined) {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'passed' || normalized === 'approved') return '通过采纳'
  if (normalized === 'failed' || normalized === 'rejected') return '打回重做'
  if (normalized === 'pending') return '继续观察'
  return normalized ? status || '' : '未验收'
}

function getAcceptanceStatusTone(status: string | undefined) {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'passed' || normalized === 'approved') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
  if (normalized === 'failed' || normalized === 'rejected') return 'border-rose-500/30 bg-rose-500/10 text-rose-200'
  if (normalized === 'pending') return 'border-amber-500/30 bg-amber-500/10 text-amber-200'
  return 'border-slate-700 bg-slate-950/60 text-slate-300'
}

function getAcceptanceAssetKindLabel(kind: string | undefined) {
  const normalized = String(kind || '').trim().toLowerCase()
  if (normalized === 'image') return '分镜图'
  if (normalized === 'video') return '视频'
  if (normalized === 'audio') return '音频'
  return normalized ? kind || '' : '资产'
}

export function ProductWorkspaceStoryboardAcceptancePanel({
  acceptance,
  acceptanceAssetKind,
  acceptanceAssetId,
  acceptanceDraft,
  acceptanceState,
  acceptanceMessage,
  onDraftChange,
  onSave,
}: {
  acceptance: AcceptanceRecordLike | null | undefined
  acceptanceAssetKind: string
  acceptanceAssetId: string
  acceptanceDraft: AcceptanceDraft
  acceptanceState: AcceptanceState
  acceptanceMessage: string
  onDraftChange: (draft: AcceptanceDraft) => void
  onSave: () => void | Promise<void>
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-medium text-white">当前验收结论</div>
        <span className={`rounded-full border px-2.5 py-1 text-[11px] ${getAcceptanceStatusTone(acceptance?.status)}`}>
          {getAcceptanceStatusLabel(acceptance?.status)}
        </span>
      </div>
      <div className="mt-3 space-y-2 text-[11px] text-slate-400">
        <div>验收对象：<span className="text-slate-300">{getAcceptanceAssetKindLabel(acceptanceAssetKind)}</span></div>
        <div>当前资产：<span className="break-all text-slate-300">{acceptanceAssetId || '未记录'}</span></div>
        <div>最近更新时间：<span className="text-slate-300">{acceptance?.updated_at || '未记录'}</span></div>
      </div>
      {Array.isArray(acceptance?.failure_tags) && acceptance.failure_tags.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {acceptance.failure_tags.map((tag) => (
            <span key={tag} className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-200">
              {tag}
            </span>
          ))}
        </div>
      ) : null}
      <div className="mt-3 text-xs leading-5 text-slate-500">{acceptance?.notes || '当前还没有记录验收备注。'}</div>

      <details className="mt-4 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
        <summary className="cursor-pointer text-xs font-medium text-slate-300">提交验收记录</summary>
        <div className="mt-3 space-y-3">
          <div className="grid gap-2">
            <select
              value={acceptanceDraft.assetKind}
              onChange={(event) => onDraftChange({ ...acceptanceDraft, assetKind: event.target.value })}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 outline-none transition focus:border-sky-500"
            >
              <option value="image">分镜图</option>
              <option value="video">视频</option>
              <option value="audio">音频</option>
            </select>
            <input
              value={acceptanceDraft.assetId}
              onChange={(event) => onDraftChange({ ...acceptanceDraft, assetId: event.target.value })}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 outline-none transition focus:border-sky-500"
              placeholder="资产 ID"
            />
            <select
              value={acceptanceDraft.status}
              onChange={(event) => onDraftChange({ ...acceptanceDraft, status: event.target.value })}
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-200 outline-none transition focus:border-sky-500"
            >
              {ACCEPTANCE_STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </div>
          <div className="flex flex-wrap gap-2">
            {ACCEPTANCE_TAG_OPTIONS.map((option) => {
              const active = acceptanceDraft.failureTags.includes(option.value)
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() =>
                    onDraftChange({
                      ...acceptanceDraft,
                      failureTags: active
                        ? acceptanceDraft.failureTags.filter((item) => item !== option.value)
                        : [...acceptanceDraft.failureTags, option.value],
                    })
                  }
                  className={`rounded-full border px-2 py-0.5 text-[10px] transition ${
                    active
                      ? 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                      : 'border-slate-700 text-slate-400 hover:border-slate-500 hover:text-white'
                  }`}
                >
                  {option.label}
                </button>
              )
            })}
          </div>
          <textarea
            rows={4}
            value={acceptanceDraft.notes}
            onChange={(event) => onDraftChange({ ...acceptanceDraft, notes: event.target.value })}
            className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs leading-6 text-slate-200 outline-none transition focus:border-sky-500"
            placeholder="记录通过理由、打回原因或下一轮约束。"
          />
          <button
            type="button"
            onClick={() => { void onSave() }}
            disabled={acceptanceState === 'saving'}
            className="rounded-lg border border-sky-500/50 px-3 py-2 text-xs font-medium text-sky-200 transition hover:border-sky-400 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {acceptanceState === 'saving' ? '保存中...' : '保存验收'}
          </button>
          {acceptanceMessage ? (
            <div
              role="status"
              aria-live="polite"
              className={`rounded-lg border px-3 py-2 text-xs ${
                acceptanceState === 'error'
                  ? 'border-rose-500/20 bg-rose-500/5 text-rose-200'
                  : 'border-emerald-500/20 bg-emerald-500/5 text-emerald-200'
              }`}
            >
              {acceptanceMessage}
            </div>
          ) : null}
        </div>
      </details>
    </div>
  )
}
