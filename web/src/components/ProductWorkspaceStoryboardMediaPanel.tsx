import { useState } from 'react'
import type { MediaAssetOutput, StoryboardShotOutput } from '../domain/bookOutputs'
import {
  getPromptReferenceScopeLabel,
  getReferencePreviewUrl,
} from './productWorkspacePrompt'
import { getReferenceStatusLabel, normalizeReferenceAssetType } from './productWorkspaceStoryboardBindings'

type StoryboardReferenceImage = NonNullable<StoryboardShotOutput['reference_images']>[number]
type ManualUploadKind = 'image' | 'reference-image'

function collectManualReferenceTargets(shot: StoryboardShotOutput) {
  const items = [
    ...(shot.prompt_compile_context?.visual_fact_targets ?? []),
    ...(shot.prompt_compile_context?.required_used_assets ?? []),
    ...(shot.used_assets ?? []),
    ...(shot.reference_images ?? []),
  ]
  const seen = new Set<string>()
  return items
    .map((item) => {
      const normalizedType = normalizeReferenceAssetType(item.asset_type)
      const assetType = normalizedType === 'location' ? 'scene' : normalizedType
      const assetId = String(item.asset_id || '').trim()
      const assetName = String(item.asset_name || '').trim()
      const referenceToken = String('reference_token' in item ? item.reference_token || '' : '').trim()
      return { assetType, assetId, assetName, referenceToken }
    })
    .filter((item) => item.assetType && item.assetId)
    .filter((item) => {
      const key = `${item.assetType}:${item.assetId}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
}

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

function MediaAssetCard({ item, showPrompt = false }: { item: MediaAssetOutput; showPrompt?: boolean }) {
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
      {showPrompt && item.prompt ? (
        <details className="mt-3 rounded border border-slate-800 bg-slate-900/70 p-2">
          <summary className="cursor-pointer text-[11px] text-slate-400">查看当次提交提示词</summary>
          <div className="mt-2 whitespace-pre-wrap break-words text-[11px] leading-5 text-slate-300">{item.prompt}</div>
        </details>
      ) : null}
    </div>
  )
}

function ManualMediaUploadCard({
  bookId,
  shot,
  onUploaded,
}: {
  bookId: number
  shot: StoryboardShotOutput
  onUploaded?: () => void
}) {
  const [kind, setKind] = useState<ManualUploadKind>('image')
  const [file, setFile] = useState<File | null>(null)
  const [assetType, setAssetType] = useState('scene')
  const [assetId, setAssetId] = useState('')
  const [assetName, setAssetName] = useState('')
  const [referenceToken, setReferenceToken] = useState('')
  const [state, setState] = useState<'idle' | 'uploading' | 'done' | 'error'>('idle')
  const [message, setMessage] = useState('')
  const referenceTargets = collectManualReferenceTargets(shot)

  const upload = async () => {
    if (!file) {
      setState('error')
      setMessage('请先选择一张 PNG / JPG / WebP 图片。')
      return
    }
    if (kind === 'reference-image' && !assetId.trim()) {
      setState('error')
      setMessage('上传参考图需要填写已绑定视觉资产 ID，才能进入 H3 多参考链路。')
      return
    }
    setState('uploading')
    setMessage('正在上传手动资产...')
    try {
      const form = new FormData()
      form.append('file', file)
      form.append('targetKind', kind)
      form.append('assetType', assetType)
      form.append('assetId', assetId.trim())
      form.append('assetName', assetName.trim())
      form.append('referenceToken', referenceToken.trim())
      form.append('status', kind === 'reference-image' ? 'locked' : 'selected')
      form.append('adopted', 'true')
      form.append('notes', '正式工作台手动上传资产。')
      const response = await fetch(`/api/books/${bookId}/storyboard/${shot.episode}/${shot.shot_id}/manual-media-assets`, {
        method: 'POST',
        body: form,
      })
      if (!response.ok) {
        let detail = ''
        try {
          const payload = await response.json()
          detail = String(payload?.detail || payload?.error || '').trim()
        } catch {
          detail = await response.text()
        }
        throw new Error(detail || `HTTP ${response.status}`)
      }
      setState('done')
      setMessage(kind === 'image' ? '手动分镜图已上传并采纳。' : '手动参考图已上传、锁定，并进入多参考资产。')
      setFile(null)
      onUploaded?.()
    } catch (error) {
      setState('error')
      setMessage(error instanceof Error ? error.message : '手动资产上传失败。')
    }
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-white">手动上传资产</div>
          <div className="mt-1 text-xs text-slate-400">
            支持上传分镜图或参考图；参考图被选中后会参与 H3 多参考视频生成。
          </div>
        </div>
        <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-[10px] text-sky-200">
          PNG / JPG / WebP
        </span>
      </div>

      <div className="mt-4 space-y-3">
        <select
          value={kind}
          onChange={(event) => setKind(event.target.value as ManualUploadKind)}
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
        >
          <option value="image">上传为当前镜头分镜图</option>
          <option value="reference-image">上传为 H3 多参考图</option>
        </select>
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-300"
        />

        {kind === 'reference-image' ? (
          <>
            {referenceTargets.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {referenceTargets.slice(0, 8).map((target) => (
                  <button
                    key={`${target.assetType}-${target.assetId}`}
                    type="button"
                    onClick={() => {
                      setAssetType(target.assetType || 'scene')
                      setAssetId(target.assetId)
                      setAssetName(target.assetName)
                      setReferenceToken(target.referenceToken)
                    }}
                    className="rounded-full border border-slate-700 px-2 py-1 text-[11px] text-slate-300 transition hover:border-sky-500 hover:text-sky-200"
                  >
                    {getDisplayAssetTypeLabel(target.assetType)} · {target.assetName || target.assetId}
                  </button>
                ))}
              </div>
            ) : null}
            <div className="grid gap-2 sm:grid-cols-2">
              <select
                value={assetType}
                onChange={(event) => setAssetType(event.target.value)}
                className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
              >
                <option value="scene">场景参考</option>
                <option value="character">人物参考</option>
                <option value="prop">道具参考</option>
              </select>
              <input
                value={assetId}
                onChange={(event) => setAssetId(event.target.value)}
                placeholder="视觉资产 ID（必填）"
                className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600"
              />
              <input
                value={assetName}
                onChange={(event) => setAssetName(event.target.value)}
                placeholder="资产名（可选）"
                className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600"
              />
              <input
                value={referenceToken}
                onChange={(event) => setReferenceToken(event.target.value)}
                placeholder="引用标记，如 @姐姐（可选）"
                className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600"
              />
            </div>
          </>
        ) : null}

        <button
          type="button"
          onClick={upload}
          disabled={state === 'uploading'}
          className="rounded-lg bg-sky-500 px-3 py-2 text-sm font-medium text-white transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {state === 'uploading' ? '上传中...' : '上传并写入资产'}
        </button>
        {message ? (
          <div role="status" aria-live="polite" className={`text-xs ${state === 'error' ? 'text-rose-300' : state === 'done' ? 'text-emerald-300' : 'text-slate-400'}`}>
            {message}
          </div>
        ) : null}
      </div>
    </div>
  )
}

export function ProductWorkspaceStoryboardMediaPanel({
  bookId,
  shot,
  imageAssets,
  videoAssets,
  archivedAssets,
  referenceImages,
  onUploaded,
  allowManualUpload = true,
}: {
  bookId: number
  shot: StoryboardShotOutput
  imageAssets: MediaAssetOutput[]
  videoAssets: MediaAssetOutput[]
  archivedAssets?: Pick<NonNullable<StoryboardShotOutput['split_archived_assets']>, 'images' | 'videos' | 'audios'>
  referenceImages: StoryboardReferenceImage[]
  onUploaded?: () => void
  allowManualUpload?: boolean
}) {
  const archivedImages = archivedAssets?.images ?? []
  const archivedVideos = archivedAssets?.videos ?? []
  const archivedAudios = archivedAssets?.audios ?? []
  const hasArchivedMedia = archivedImages.length > 0 || archivedVideos.length > 0 || archivedAudios.length > 0

  return (
    <>
      {allowManualUpload ? (
        <ManualMediaUploadCard bookId={bookId} shot={shot} onUploaded={onUploaded} />
      ) : (
        <details className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <summary className="cursor-pointer text-sm font-medium text-slate-300">高级：查看上传说明</summary>
          <div className="mt-2 text-xs leading-5 text-slate-500">上游剧本尚未放行，当前不能上传或采纳新资产。完成放行后，此处会开放分镜图和 H3 多参考图上传。</div>
        </details>
      )}

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

      {hasArchivedMedia ? (
        <details className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-5">
          <summary className="cursor-pointer text-sm font-medium text-amber-100">
            拆镜前归档媒体
            <span className="ml-2 text-[11px] font-normal text-amber-200/70">仅追溯，不作为当前镜头成片</span>
          </summary>
          <div className="mt-3 rounded-lg border border-amber-500/15 bg-slate-950/50 p-3 text-xs leading-5 text-slate-300">
            这些资源属于拆镜前的原始镜头，保留用于审计、查看历史结果与提交提示词；它们不会计入当前镜头的分镜图/视频版本，也不能被采纳为当前成片。
          </div>
          <div className="mt-3 space-y-4">
            {archivedImages.length > 0 ? (
              <div>
                <div className="text-xs font-medium text-amber-100">原分镜图</div>
                <div className="mt-2 space-y-3">{archivedImages.map((item) => <MediaAssetCard key={`archived-image-${item.id}`} item={item} showPrompt />)}</div>
              </div>
            ) : null}
            {archivedVideos.length > 0 ? (
              <div>
                <div className="text-xs font-medium text-amber-100">原视频</div>
                <div className="mt-2 space-y-3">{archivedVideos.map((item) => <MediaAssetCard key={`archived-video-${item.id}`} item={item} showPrompt />)}</div>
              </div>
            ) : null}
            {archivedAudios.length > 0 ? (
              <div>
                <div className="text-xs font-medium text-amber-100">原音频</div>
                <div className="mt-2 space-y-3">{archivedAudios.map((item) => <MediaAssetCard key={`archived-audio-${item.id}`} item={item} showPrompt />)}</div>
              </div>
            ) : null}
          </div>
        </details>
      ) : null}

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
