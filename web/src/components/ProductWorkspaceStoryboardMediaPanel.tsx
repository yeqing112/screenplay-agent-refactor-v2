import type { MediaAssetOutput, StoryboardShotOutput } from '../domain/bookOutputs'
import {
  getPromptReferenceScopeLabel,
  getReferencePreviewUrl,
} from './productWorkspacePrompt'
import { getReferenceStatusLabel, normalizeReferenceAssetType } from './productWorkspaceStoryboardBindings'

type StoryboardReferenceImage = NonNullable<StoryboardShotOutput['reference_images']>[number]

function getMediaAssetKindLabel(kind: string | undefined) {
  const normalized = String(kind || '').trim().toLowerCase()
  if (normalized === 'image') return '分镜图'
  if (normalized === 'video') return '视频'
  if (normalized === 'audio') return '音频'
  return normalized ? kind || '' : '资产'
}

function getMediaAssetStatusLabel(status: string | undefined) {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'done' || normalized === 'completed' || normalized === 'ready') return '已生成'
  if (normalized === 'running' || normalized === 'processing') return '生成中'
  if (normalized === 'error' || normalized === 'failed') return '生成失败'
  if (normalized === 'pending') return '待处理'
  return normalized ? status || '' : '未记录'
}

function getDisplayAssetTypeLabel(assetType: string | undefined) {
  return getPromptReferenceScopeLabel(normalizeReferenceAssetType(assetType) || 'reference')
}

function MediaAssetCard({ item }: { item: MediaAssetOutput }) {
  const href = String(item.previewUrl || item.uri || '').trim()

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/70 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] text-slate-300">
          {getMediaAssetKindLabel(String(item.kind || ''))}
        </span>
        {item.adopted ? (
          <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-200">
            当前采纳
          </span>
        ) : null}
      </div>
      <div className="mt-2 text-sm font-medium text-white">{item.title || item.label || item.id}</div>
      <div className="mt-2 space-y-1 text-[11px] text-slate-400">
        <div>版本标签：<span className="text-slate-300">{item.label || '-'}</span></div>
        <div>生成状态：<span className="text-slate-300">{getMediaAssetStatusLabel(item.status)}</span></div>
        <div>模型：<span className="text-slate-300">{item.model || '未记录'}</span></div>
      </div>
      {href ? (
        <a href={href} target="_blank" rel="noreferrer" className="mt-2 inline-flex text-[11px] text-sky-300 transition hover:text-sky-200">
          查看原始文件
        </a>
      ) : null}
    </div>
  )
}

export function ProductWorkspaceStoryboardMediaPanel({
  imageAssets,
  videoAssets,
  referenceImages,
}: {
  imageAssets: MediaAssetOutput[]
  videoAssets: MediaAssetOutput[]
  referenceImages: StoryboardReferenceImage[]
}) {
  return (
    <>
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="text-sm font-medium text-white">已生成分镜图</div>
        {imageAssets.length > 0 ? (
          <div className="mt-3 space-y-3">
            {imageAssets.map((item) => <MediaAssetCard key={item.id} item={item} />)}
          </div>
        ) : (
          <div className="mt-3 rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
            当前还没有生成的分镜图版本。
          </div>
        )}
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="text-sm font-medium text-white">已生成视频</div>
        {videoAssets.length > 0 ? (
          <div className="mt-3 space-y-3">
            {videoAssets.map((item) => <MediaAssetCard key={item.id} item={item} />)}
          </div>
        ) : (
          <div className="mt-3 rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
            当前还没有生成的视频版本。
          </div>
        )}
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="text-sm font-medium text-white">参考图预览</div>
        {referenceImages.length > 0 ? (
          <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
            {referenceImages.map((reference, index) => {
              const previewUrl = getReferencePreviewUrl(reference)
              return (
                <div key={`${reference.reference_asset_id || reference.asset_id || 'reference'}-${index}`} className="min-w-0 rounded-lg border border-slate-800 bg-slate-950/70 p-2">
                  <div className="aspect-[4/3] overflow-hidden rounded bg-slate-900">
                    {previewUrl ? (
                      <img src={previewUrl} alt={reference.asset_name || reference.reference_token || '参考图'} className="h-full w-full object-cover" />
                    ) : (
                      <div className="flex h-full items-center justify-center text-xs text-slate-500">无可预览图片</div>
                    )}
                  </div>
                  <div className="mt-2 break-all text-xs text-slate-300">{reference.asset_name || reference.reference_token || '未命名参考图'}</div>
                  <div className="mt-1 break-all text-[11px] text-slate-500">
                    {getDisplayAssetTypeLabel(reference.asset_type)}
                    {reference.reference_token ? ` · ${reference.reference_token}` : ''}
                    {reference.reference_status ? ` · ${getReferenceStatusLabel(reference.reference_status)}` : ''}
                  </div>
                  {previewUrl ? (
                    <a href={previewUrl} target="_blank" rel="noreferrer" className="mt-2 inline-flex text-[11px] text-sky-300 transition hover:text-sky-200">
                      查看大图
                    </a>
                  ) : null}
                </div>
              )
            })}
          </div>
        ) : (
          <div className="mt-3 rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-4 text-sm text-slate-400">
            当前镜头还没有参考图。
          </div>
        )}
      </div>
    </>
  )
}
