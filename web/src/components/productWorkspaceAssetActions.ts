import {
  removePendingStoryboardTask,
  upsertPendingStoryboardTask,
} from './productWorkspaceRecovery'

type AssetCategory = 'character' | 'location' | 'prop'

type AssetReferenceItem = {
  id: number
  asset_type?: string
  asset_id?: string
  asset_name?: string
  image_url?: string
  reference_token?: string
  status?: string
}

type AssetSummaryLike = {
  id: string
  title: string
  category: AssetCategory
  prompt?: string | null
  assetRecordId?: string | number | null
  episodeIds: number[]
  shotIds: string[]
  references: AssetReferenceItem[]
}

interface AssetActionDispatchers {
  setAssetActionTone: (tone: 'info' | 'error') => void
  setAssetActionMessage: (message: string) => void
  setAssetGenerationState: (state: 'idle' | 'saving') => void
  setShotBindingState: (state: 'idle' | 'saving' | 'saved' | 'error') => void
  closeAssetPreview: () => void
  refreshAll: () => void
}

interface GenerateReferenceParams extends AssetActionDispatchers {
  bookId: number
  assetEpisodeFilter: 'all' | number
  selectedAsset: AssetSummaryLike | null
  buildAssetReferenceToken: (title: string) => string
  toVisualAssetType: (category: AssetCategory) => string
  inferredShotIds?: string[]
}

interface DeleteReferenceParams extends AssetActionDispatchers {
  bookId: number
  referenceId: number
  selectedAsset: AssetSummaryLike | null
  assetPreviewUrl: string | null
}

interface UpdateReferenceStatusParams extends AssetActionDispatchers {
  bookId: number
  referenceId: number
  nextStatus: 'candidate' | 'selected' | 'locked'
}

interface SaveShotBindingsParams extends AssetActionDispatchers {
  bookId: number
  selectedAsset: AssetSummaryLike | null
  linkedShotDraft: string[]
  toVisualAssetType: (category: AssetCategory) => string
}

export type GenerateReferenceOutcome =
  | { status: 'invalid' | 'error'; taskId?: undefined; episode?: undefined; shotId?: undefined; assetId?: undefined }
  | { status: 'pending' | 'done'; taskId: string; episode: number; shotId: string; assetId: string }

function referenceStatusLabel(status?: string) {
  if (status === 'locked') return '\u5df2\u9501\u5b9a'
  if (status === 'selected') return '\u9ed8\u8ba4\u53c2\u8003'
  if (status === 'rejected') return '\u5df2\u6dd8\u6c70'
  if (status === 'candidate') return '\u5019\u9009\u53c2\u8003'
  return '\u8349\u7a3f'
}

function normalizeShotCandidate(value: string | null | undefined) {
  return String(value || '').trim()
}

function toEpisodeShotCandidate(episode: number, shotId: string) {
  const normalizedShotId = normalizeShotCandidate(shotId)
  if (!episode || !normalizedShotId) return ''
  if (normalizedShotId.startsWith(`${episode}-`)) return normalizedShotId
  return `${episode}-${normalizedShotId}`
}

export function resolveAssetReferenceShotTarget(input: {
  assetEpisodeFilter: 'all' | number
  selectedAsset: Pick<AssetSummaryLike, 'episodeIds' | 'shotIds'>
  inferredShotIds?: string[]
}) {
  const explicitShotIds = (input.selectedAsset.shotIds ?? []).map(normalizeShotCandidate).filter(Boolean)
  const inferredShotIds = (input.inferredShotIds ?? []).map(normalizeShotCandidate).filter(Boolean)
  const combinedShotIds = Array.from(new Set([...explicitShotIds, ...inferredShotIds]))

  const candidateEpisodes = [
    input.assetEpisodeFilter !== 'all' ? input.assetEpisodeFilter : null,
    ...(input.selectedAsset.episodeIds ?? []),
    ...combinedShotIds
      .map((item) => Number(String(item).split('-')[0]))
      .filter((item) => Number.isFinite(item) && item > 0),
    1,
  ].filter((item): item is number => typeof item === 'number' && Number.isFinite(item) && item > 0)

  const preferredEpisode = candidateEpisodes[0] ?? 1
  const shotId =
    combinedShotIds.find((value) => value.startsWith(`${preferredEpisode}-`)) ??
    combinedShotIds[0] ??
    toEpisodeShotCandidate(preferredEpisode, '1')

  return {
    preferredEpisode,
    shotId,
    relatedShotIds: combinedShotIds,
    usedInferredShot: !explicitShotIds.includes(shotId) && inferredShotIds.includes(shotId),
  }
}

export function buildAssetGenerationReferenceImages(
  selectedAsset: Pick<AssetSummaryLike, 'category' | 'title' | 'references'>,
) {
  const statusOrder: Record<string, number> = { locked: 0, selected: 1 }
  return (selectedAsset.references ?? [])
    .filter((reference) => {
      const status = String(reference.status || '').trim().toLowerCase()
      return status === 'locked' || status === 'selected'
    })
    .filter((reference) => Boolean(String(reference.image_url || '').trim()))
    .slice()
    .sort((left, right) => {
      const leftRank = statusOrder[String(left.status || '').trim().toLowerCase()] ?? 99
      const rightRank = statusOrder[String(right.status || '').trim().toLowerCase()] ?? 99
      return leftRank - rightRank || left.id - right.id
    })
    .map((reference) => ({
      reference_asset_id: `ref-${reference.id}`,
      reference_token: String(reference.reference_token || `@${selectedAsset.title}`).trim(),
      reference_name: String(reference.asset_name || selectedAsset.title).trim(),
      image_url: String(reference.image_url || '').trim(),
      reference_status: String(reference.status || '').trim().toLowerCase(),
      asset_type: String(reference.asset_type || selectedAsset.category).trim(),
      asset_id: String(reference.asset_id || '').trim(),
      role: selectedAsset.category === 'location' ? 'scene' : selectedAsset.category,
      reference_purpose:
        selectedAsset.category === 'character'
          ? 'identity_costume_face_hair'
          : selectedAsset.category === 'location'
            ? 'background_layout_lighting'
            : 'prop_shape_material_state',
    }))
}

export async function runGenerateSelectedAssetReference({
  bookId,
  assetEpisodeFilter,
  selectedAsset,
  buildAssetReferenceToken,
  toVisualAssetType,
  inferredShotIds,
  setAssetActionTone,
  setAssetActionMessage,
  setAssetGenerationState,
  refreshAll,
}: GenerateReferenceParams): Promise<GenerateReferenceOutcome> {
  if (bookId <= 0 || !selectedAsset?.assetRecordId) return { status: 'invalid' }

  const prompt = String(selectedAsset.prompt || '').trim()
  if (!prompt) {
    setAssetActionTone('error')
    setAssetActionMessage('\u5f53\u524d\u8d44\u4ea7\u8fd8\u6ca1\u6709\u53ef\u7528\u7684\u53c2\u8003\u56fe\u63d0\u793a\u8bcd\u3002')
    return { status: 'invalid' }
  }

  const { preferredEpisode, shotId, relatedShotIds, usedInferredShot } = resolveAssetReferenceShotTarget({
    assetEpisodeFilter,
    selectedAsset,
    inferredShotIds,
  })
  const referenceImages = buildAssetGenerationReferenceImages(selectedAsset)

  try {
    setAssetGenerationState('saving')
    setAssetActionTone('info')
    setAssetActionMessage(
      usedInferredShot
        ? `\u6b63\u5728\u63d0\u4ea4\u53c2\u8003\u56fe\u751f\u6210\u4efb\u52a1\uff08\u643a\u5e26 ${referenceImages.length} \u5f20\u5df2\u9501\u5b9a/\u9ed8\u8ba4\u8d44\u4ea7\u56fe\uff09\uff0c\u5e76\u4f18\u5148\u4f7f\u7528\u7cfb\u7edf\u8bc6\u522b\u51fa\u7684\u5f71\u54cd\u955c\u5934\u4f5c\u4e3a\u56de\u5199\u76ee\u6807...`
        : `\u6b63\u5728\u63d0\u4ea4\u53c2\u8003\u56fe\u751f\u6210\u4efb\u52a1\uff08\u643a\u5e26 ${referenceImages.length} \u5f20\u5df2\u9501\u5b9a/\u9ed8\u8ba4\u8d44\u4ea7\u56fe\uff09...`,
    )

    const startResponse = await fetch('/api/prototyping/generate-reference-image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bookId,
        episode: preferredEpisode,
        shotId,
        sourceNodeId: `product-workspace-${selectedAsset.id}`,
        sourceAssetId: String(selectedAsset.assetRecordId),
        assetScope: selectedAsset.category,
        assetSubject: selectedAsset.title,
        targetKind: 'image',
        prompt,
        aspectRatio: '1:1',
        referenceImages,
      }),
    })
    if (!startResponse.ok) {
      throw new Error(`\u542f\u52a8\u53c2\u8003\u56fe\u751f\u6210\u5931\u8d25: HTTP ${startResponse.status}`)
    }

    const task = await startResponse.json()
    const taskId = String(task.task_id || '').trim()
    if (!taskId) {
      throw new Error('\u53c2\u8003\u56fe\u4efb\u52a1\u5df2\u521b\u5efa\uff0c\u4f46\u6ca1\u6709\u8fd4\u56de\u4efb\u52a1\u7f16\u53f7\u3002')
    }

    upsertPendingStoryboardTask(bookId, {
      taskId,
      episode: preferredEpisode,
      shotId,
      kind: 'reference',
      updatedAt: new Date().toISOString(),
      assetLabel: selectedAsset.title,
      assetId: selectedAsset.id,
    })

    let finalPayload: any = null
    for (let attempt = 0; attempt < 40; attempt += 1) {
      const statusResponse = await fetch(`/api/prototyping/tasks/${taskId}`)
      if (!statusResponse.ok) {
        throw new Error(`\u67e5\u8be2\u53c2\u8003\u56fe\u4efb\u52a1\u5931\u8d25: HTTP ${statusResponse.status}`)
      }

      const payload = await statusResponse.json()
      finalPayload = payload
      const status = String(payload.status || '').trim()

      if (status === 'done' || status === 'error' || status === 'not_found') break

      const progress = typeof payload.progress === 'number' ? ` ${payload.progress}%` : ''
      setAssetActionMessage(`\u6b63\u5728\u751f\u6210\u53c2\u8003\u56fe\uff0c\u4efb\u52a1 ${taskId}${progress}`.trim())
      await new Promise((resolve) => window.setTimeout(resolve, 1500))
    }

    const finalStatus = String(finalPayload?.status || '').trim()
    if (!finalPayload || (finalStatus !== 'done' && finalStatus !== 'error' && finalStatus !== 'not_found')) {
      setAssetActionTone('info')
      setAssetActionMessage(`\u53c2\u8003\u56fe\u4efb\u52a1 ${taskId} \u4ecd\u5728\u6267\u884c\uff0c\u8bf7\u53bb\u4efb\u52a1\u4e2d\u5fc3\u7ee7\u7eed\u56de\u6536\u7ed3\u679c\u3002`)
      return { status: 'pending', taskId, episode: preferredEpisode, shotId, assetId: selectedAsset.id }
    }

    if (finalStatus === 'error' || finalStatus === 'not_found') {
      removePendingStoryboardTask(bookId, taskId)
      throw new Error(String(finalPayload?.error || `\u53c2\u8003\u56fe\u4efb\u52a1 ${taskId} \u6267\u884c\u5931\u8d25`))
    }

    if (!finalPayload.reference_asset) {
      const generatedAsset = finalPayload.asset
      const imageUrl = String(generatedAsset?.uri || generatedAsset?.previewUrl || '').trim()
      if (!imageUrl) {
        throw new Error('\u53c2\u8003\u56fe\u4efb\u52a1\u5df2\u5b8c\u6210\uff0c\u4f46\u6ca1\u6709\u53ef\u56de\u5199\u7684\u56fe\u7247\u5730\u5740\u3002')
      }

      const persistResponse = await fetch(`/api/books/${bookId}/visual-reference-assets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          assetType: toVisualAssetType(selectedAsset.category),
          assetId: String(selectedAsset.assetRecordId),
          assetName: selectedAsset.title,
          episode: preferredEpisode,
          imageUrl,
          referenceToken: buildAssetReferenceToken(selectedAsset.title),
          status: 'selected',
          prompt: String(generatedAsset?.prompt || prompt),
          model: String(generatedAsset?.model || generatedAsset?.metadata?.modelName || ''),
          notes: '\u6b63\u5f0f\u5de5\u4f5c\u533a\u8d44\u4ea7\u4e2d\u5fc3\u751f\u6210',
          metaInfo: {
            source: 'product-workspace-assets-generate',
            taskId,
            shotId,
            shotIds: relatedShotIds,
            generatedAt: new Date().toISOString(),
            assetScope: selectedAsset.category,
            assetSubject: selectedAsset.title,
            usesMock: Boolean(finalPayload?.uses_mock),
            usedInferredShot,
          },
        }),
      })

      if (!persistResponse.ok) {
        throw new Error(`\u53c2\u8003\u56fe\u5df2\u751f\u6210\uff0c\u4f46\u56de\u5199\u8d44\u4ea7\u4e2d\u5fc3\u5931\u8d25: HTTP ${persistResponse.status}`)
      }
    }

    removePendingStoryboardTask(bookId, taskId)
    setAssetActionTone('info')
    setAssetActionMessage(
      usedInferredShot
        ? `\u5df2\u4e3a\u300c${selectedAsset.title}\u300d\u751f\u6210\u53c2\u8003\u56fe\uff0c\u5e76\u6309\u7cfb\u7edf\u8bc6\u522b\u7684\u5f71\u54cd\u955c\u5934\u540c\u6b65\u56de\u8d44\u4ea7\u4e2d\u5fc3\u3002`
        : `\u5df2\u4e3a\u300c${selectedAsset.title}\u300d\u751f\u6210\u53c2\u8003\u56fe\uff0c\u5e76\u540c\u6b65\u56de\u8d44\u4ea7\u4e2d\u5fc3\u3002`,
    )
    refreshAll()
    return { status: 'done', taskId, episode: preferredEpisode, shotId, assetId: selectedAsset.id }
  } catch (error) {
    setAssetActionTone('error')
    setAssetActionMessage(error instanceof Error ? error.message : '\u751f\u6210\u53c2\u8003\u56fe\u5931\u8d25')
    return { status: 'error' }
  } finally {
    setAssetGenerationState('idle')
  }
}

export async function runDeleteReferenceAsset({
  bookId,
  referenceId,
  selectedAsset,
  assetPreviewUrl,
  setAssetActionTone,
  setAssetActionMessage,
  closeAssetPreview,
  refreshAll,
}: DeleteReferenceParams) {
  if (bookId <= 0 || referenceId <= 0) return

  try {
    setAssetActionMessage('')
    const response = await fetch(`/api/books/${bookId}/visual-reference-assets/${referenceId}`, {
      method: 'DELETE',
    })
    if (!response.ok) {
      throw new Error(`\u5220\u9664\u5931\u8d25: HTTP ${response.status}`)
    }

    const payload = await response.json()
    const removedStoryboardReferences =
      typeof payload.removed_storyboard_references === 'number'
        ? `\uff0c\u5e76\u540c\u6b65\u79fb\u9664 ${payload.removed_storyboard_references} \u4e2a\u955c\u5934\u5f15\u7528`
        : ''

    setAssetActionTone('info')
    setAssetActionMessage(`\u53c2\u8003\u56fe\u5df2\u5220\u9664${removedStoryboardReferences}\u3002`)
    if (assetPreviewUrl && selectedAsset?.references.some((item) => item.id === referenceId)) {
      closeAssetPreview()
    }
    refreshAll()
  } catch (deleteError) {
    setAssetActionTone('error')
    setAssetActionMessage(deleteError instanceof Error ? deleteError.message : '\u5220\u9664\u53c2\u8003\u56fe\u5931\u8d25')
  }
}

export async function runUpdateReferenceAssetStatus({
  bookId,
  referenceId,
  nextStatus,
  setAssetActionTone,
  setAssetActionMessage,
  refreshAll,
}: UpdateReferenceStatusParams) {
  if (bookId <= 0 || referenceId <= 0) return

  try {
    setAssetActionMessage('')
    const response = await fetch(`/api/books/${bookId}/visual-reference-assets/${referenceId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: nextStatus }),
    })
    if (!response.ok) {
      throw new Error(`\u66f4\u65b0\u53c2\u8003\u56fe\u72b6\u6001\u5931\u8d25: HTTP ${response.status}`)
    }

    const payload = await response.json()
    const statusLabel = referenceStatusLabel(payload.status || nextStatus)
    setAssetActionTone('info')
    setAssetActionMessage(
      payload.sync_warning
        ? `\u53c2\u8003\u56fe\u5df2\u66f4\u65b0\u4e3a\u300c${statusLabel}\u300d\uff0c\u4f46\u955c\u5934\u540c\u6b65\u5b58\u5728\u63d0\u9192\uff1a${payload.sync_warning}`
        : `\u53c2\u8003\u56fe\u5df2\u66f4\u65b0\u4e3a\u300c${statusLabel}\u300d\uff0c\u8d44\u4ea7\u4e2d\u5fc3\u4e0e\u955c\u5934\u5f15\u7528\u5df2\u540c\u6b65\u5237\u65b0\u3002`,
    )
    refreshAll()
  } catch (updateError) {
    setAssetActionTone('error')
    setAssetActionMessage(updateError instanceof Error ? updateError.message : '\u66f4\u65b0\u53c2\u8003\u56fe\u72b6\u6001\u5931\u8d25')
  }
}

export async function runSaveAssetShotBindings({
  bookId,
  selectedAsset,
  linkedShotDraft,
  toVisualAssetType,
  setShotBindingState,
  setAssetActionTone,
  setAssetActionMessage,
  refreshAll,
}: SaveShotBindingsParams) {
  if (bookId <= 0 || !selectedAsset?.assetRecordId) return

  try {
    setShotBindingState('saving')
    setAssetActionMessage('')
    const response = await fetch(
      `/api/books/${bookId}/visual-assets/${toVisualAssetType(selectedAsset.category)}/${selectedAsset.assetRecordId}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ shot_ids: linkedShotDraft }),
      },
    )
    if (!response.ok) {
      throw new Error(`\u4fdd\u5b58\u955c\u5934\u7ed1\u5b9a\u5931\u8d25: HTTP ${response.status}`)
    }

    const payload = await response.json()
    setShotBindingState('saved')
    setAssetActionTone('info')
    setAssetActionMessage(
      payload.sync_warning
        ? `\u5df2\u4fdd\u5b58 ${linkedShotDraft.length} \u4e2a\u5173\u8054\u955c\u5934\uff0c\u4f46\u540c\u6b65\u5b58\u5728\u63d0\u9192\uff1a${payload.sync_warning}`
        : `\u5df2\u4fdd\u5b58 ${linkedShotDraft.length} \u4e2a\u5173\u8054\u955c\u5934\uff0c\u8d44\u4ea7\u4e0e\u53c2\u8003\u56fe\u540c\u6b65\u5df2\u5237\u65b0\u3002`,
    )
    refreshAll()
  } catch (saveError) {
    setShotBindingState('error')
    setAssetActionTone('error')
    setAssetActionMessage(saveError instanceof Error ? saveError.message : '\u4fdd\u5b58\u955c\u5934\u7ed1\u5b9a\u5931\u8d25')
  }
}
