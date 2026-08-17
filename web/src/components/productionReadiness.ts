import type { StoryboardShotOutput } from '../prototyping/sceneComposerData'

export interface ShotChecklist {
  missing: string[]
  promptReady: boolean
  frameReady: boolean
  videoReady: boolean
  lockedReferenceReady: boolean
  selectedReferenceReady: boolean
  structureReady: boolean
  diagnosticBlocked: boolean
  diagnosticWarning: boolean
  diagnosticStatus: string
}

export interface StoryboardReadinessSummary {
  total: number
  missingPrompt: number
  missingFrame: number
  missingVideo: number
  missingReference: number
  missingLockedReference: number
  missingStructure: number
  warningShots: number
  blockedDiagnostics: number
  blockedShots: Array<{ shotId: string | number; episode: number; missing: string[] }>
}

export interface ExportReadinessSummary {
  canExport: boolean
  issues: string[]
  totalShots: number
  deliverableShots: number
  pendingReviewShots: number
  blockedShots: Array<{ episode: number; shotId: string | number; reasons: string[] }>
}

export interface VisualAssetSummary {
  ready: boolean
  sceneCount: number
  propCount: number
  characterCount: number
  selectedReferenceCount: number
  lockedReferenceCount: number
  totalAssetCount: number
  draftAssetCount: number
  refReadyAssetCount: number
  lockedAssetCount: number
  rejectedAssetCount: number
}

export interface ReferencedVisualAssetSummary {
  totalReferencedAssets: number
  draftAssetCount: number
  refReadyAssetCount: number
  lockedAssetCount: number
  rejectedAssetCount: number
}

function countReferences(items: any[], statuses: Set<string>): number {
  return items.reduce((total, item) => {
    const refs = Array.isArray(item?.reference_assets) ? item.reference_assets : []
    return total + refs.filter((ref: any) => statuses.has(String(ref?.status || ''))).length
  }, 0)
}

export function buildVisualAssetSummary(visualData: any): VisualAssetSummary {
  const locations = Array.isArray(visualData?.locations) ? visualData.locations : []
  const props = Array.isArray(visualData?.props) ? visualData.props : []
  const makeups = Array.isArray(visualData?.makeups) ? visualData.makeups : []
  const allAssets = [...locations, ...props, ...makeups]
  const countByStatus = (status: string) => allAssets.filter((asset) => String(asset?.derived_asset_status || asset?.asset_status || 'draft') === status).length

  return {
    ready: Boolean(visualData?.era),
    sceneCount: locations.length,
    propCount: props.length,
    characterCount: makeups.length,
    selectedReferenceCount: countReferences(allAssets, new Set(['selected'])),
    lockedReferenceCount: countReferences(allAssets, new Set(['locked'])),
    totalAssetCount: allAssets.length,
    draftAssetCount: countByStatus('draft'),
    refReadyAssetCount: countByStatus('ref_ready'),
    lockedAssetCount: countByStatus('locked'),
    rejectedAssetCount: countByStatus('rejected'),
  }
}

export function buildReferencedVisualAssetSummary(
  shots: StoryboardShotOutput[],
  visualData: any,
): ReferencedVisualAssetSummary {
  const sceneIds = new Set<string>()
  const propIds = new Set<string>()
  const characterIds = new Set<string>()

  for (const shot of shots) {
    const structured = shot?.structured_shot ?? {}
    const sceneAssetId = String(structured?.scene_asset_id ?? '').trim()
    if (sceneAssetId) sceneIds.add(sceneAssetId)

    const propAssetIds = Array.isArray(structured?.prop_asset_ids) ? structured.prop_asset_ids : []
    for (const assetId of propAssetIds) {
      const normalized = String(assetId ?? '').trim()
      if (normalized) propIds.add(normalized)
    }

    const characterAssetIds = Array.isArray(structured?.character_asset_ids) ? structured.character_asset_ids : []
    for (const assetId of characterAssetIds) {
      const normalized = String(assetId ?? '').trim()
      if (normalized) characterIds.add(normalized)
    }
  }

  const referencedAssets = [
    ...(Array.isArray(visualData?.locations) ? visualData.locations : []).filter((asset: any) => sceneIds.has(String(asset?.id ?? ''))),
    ...(Array.isArray(visualData?.props) ? visualData.props : []).filter((asset: any) => propIds.has(String(asset?.id ?? ''))),
    ...(Array.isArray(visualData?.makeups) ? visualData.makeups : []).filter((asset: any) => characterIds.has(String(asset?.id ?? ''))),
  ]

  const countByStatus = (status: string) =>
    referencedAssets.filter((asset) => String(asset?.derived_asset_status || asset?.asset_status || 'draft') === status).length

  return {
    totalReferencedAssets: referencedAssets.length,
    draftAssetCount: countByStatus('draft'),
    refReadyAssetCount: countByStatus('ref_ready'),
    lockedAssetCount: countByStatus('locked'),
    rejectedAssetCount: countByStatus('rejected'),
  }
}

export function buildShotChecklist(
  shot: StoryboardShotOutput & {
    assets?: { images?: Array<{ adopted?: boolean }>; videos?: Array<{ adopted?: boolean }> }
    compiler_diagnostics?: { status?: string }
  },
  hasSelectedReferenceAsset: (assetType: 'scene' | 'prop' | 'character', assetId: string) => boolean,
  hasLockedReferenceAsset?: (assetType: 'scene' | 'prop' | 'character', assetId: string) => boolean,
): ShotChecklist {
  const structured = shot.structured_shot ?? {}
  const characterBindings = Array.isArray(structured.character_asset_ids) ? structured.character_asset_ids : []
  const propBindings = Array.isArray(structured.prop_asset_ids) ? structured.prop_asset_ids : []
  const blocking = Array.isArray(structured.character_blocking) ? structured.character_blocking : []
  const beats = Array.isArray(structured.action_beats) ? structured.action_beats : []
  const images = Array.isArray(shot.assets?.images) ? shot.assets.images : []
  const videos = Array.isArray(shot.assets?.videos) ? shot.assets.videos : []
  const adoptedImage = images.some((asset) => asset?.adopted)
  const adoptedVideo = videos.some((asset) => asset?.adopted)
  const missing: string[] = []
  const diagnosticStatus = String(shot?.compiler_diagnostics?.status || '').trim().toLowerCase()
  const diagnosticBlocked = diagnosticStatus === 'blocked'
  const diagnosticWarning = diagnosticStatus === 'warning'
  const missingSelectedReference =
    (structured.scene_asset_id && !hasSelectedReferenceAsset('scene', String(structured.scene_asset_id))) ||
    characterBindings.some((id) => !hasSelectedReferenceAsset('character', String(id))) ||
    propBindings.some((id) => !hasSelectedReferenceAsset('prop', String(id)))
  const missingLockedReference = hasLockedReferenceAsset
    ? (
        (structured.scene_asset_id && !hasLockedReferenceAsset('scene', String(structured.scene_asset_id))) ||
        characterBindings.some((id) => !hasLockedReferenceAsset('character', String(id))) ||
        propBindings.some((id) => !hasLockedReferenceAsset('prop', String(id)))
      )
    : false
  const structureReadyBase = Boolean(structured.scene_asset_id)
    && !(characterBindings.length === 0 && Array.isArray(shot.makeup_prompts) && shot.makeup_prompts.length > 0)
    && !(characterBindings.length > 0 && blocking.length === 0)
    && beats.length > 0

  if (!structured.scene_asset_id) missing.push('缺场景绑定')
  if (!shot.prompt_version) missing.push('缺提示词版本')
  if (diagnosticBlocked) missing.push('提示词诊断阻塞')
  if (characterBindings.length === 0 && Array.isArray(shot.makeup_prompts) && shot.makeup_prompts.length > 0) missing.push('缺角色绑定')
  if (characterBindings.length > 0 && blocking.length === 0) missing.push('缺角色站位')
  if (beats.length === 0) missing.push('缺动作节拍')
  if (!adoptedImage) missing.push('缺已采用首帧')
  if (!adoptedVideo) missing.push('缺已采用视频')
  if (structured.scene_asset_id && !hasSelectedReferenceAsset('scene', String(structured.scene_asset_id))) missing.push('缺场景主参考图')
  if (characterBindings.some((id) => !hasSelectedReferenceAsset('character', String(id)))) missing.push('缺角色主参考图')
  if (propBindings.some((id) => !hasSelectedReferenceAsset('prop', String(id)))) missing.push('缺道具主参考图')
  if (hasLockedReferenceAsset) {
    if (structured.scene_asset_id && !hasLockedReferenceAsset('scene', String(structured.scene_asset_id))) missing.push('场景参考图未锁定')
    if (characterBindings.some((id) => !hasLockedReferenceAsset('character', String(id)))) missing.push('角色参考图未锁定')
    if (propBindings.some((id) => !hasLockedReferenceAsset('prop', String(id)))) missing.push('道具参考图未锁定')
  }

  return {
    missing,
    promptReady: Boolean(shot.prompt_version),
    frameReady: adoptedImage,
    videoReady: adoptedVideo,
    lockedReferenceReady: !missingLockedReference,
    selectedReferenceReady: !missingSelectedReference,
    structureReady: structureReadyBase,
    diagnosticBlocked,
    diagnosticWarning,
    diagnosticStatus,
  }
}

export function buildStoryboardReadiness(
  shots: StoryboardShotOutput[],
  selectedEpisodes: Set<number>,
  getShotChecklist: (shot: StoryboardShotOutput) => ShotChecklist,
): StoryboardReadinessSummary {
  const selectedShots = shots.filter((shot) => selectedEpisodes.size === 0 || selectedEpisodes.has(shot.episode ?? 1))
  const summary: StoryboardReadinessSummary = {
    total: selectedShots.length,
    missingPrompt: 0,
    missingFrame: 0,
    missingVideo: 0,
    missingReference: 0,
    missingLockedReference: 0,
    missingStructure: 0,
    warningShots: 0,
    blockedDiagnostics: 0,
    blockedShots: [],
  }

  for (const shot of selectedShots) {
    const checklist = getShotChecklist(shot)
    if (!checklist.promptReady) summary.missingPrompt += 1
    if (!checklist.frameReady) summary.missingFrame += 1
    if (!checklist.videoReady) summary.missingVideo += 1
    if (checklist.missing.some((item) => item.includes('参考图'))) summary.missingReference += 1
    if (checklist.missing.some((item) => item.includes('参考图未锁定'))) summary.missingLockedReference += 1
    if (checklist.missing.some((item) => item.includes('绑定') || item.includes('站位') || item.includes('动作节拍'))) summary.missingStructure += 1
    if (checklist.diagnosticWarning) summary.warningShots += 1
    if (checklist.diagnosticBlocked) summary.blockedDiagnostics += 1
    if (checklist.missing.length > 0) {
      summary.blockedShots.push({
        shotId: shot.shot_id,
        episode: shot.episode ?? 1,
        missing: checklist.missing,
      })
    }
  }

  return summary
}

export function buildExportReadiness(
  shots: StoryboardShotOutput[],
  scriptsCount: number,
  visualReady: boolean,
  storyboardReadiness: StoryboardReadinessSummary,
  getShotChecklist: (shot: StoryboardShotOutput) => ShotChecklist,
  referencedVisualAssets?: ReferencedVisualAssetSummary,
): ExportReadinessSummary {
  const issues: string[] = []
  const pendingReviewShots = shots.filter((shot) => {
    const status = String(shot.acceptance?.status || '')
    return !status || status === 'retrying' || status === 'failed'
  })
  const deliverableShots = shots.filter((shot) => {
    const checklist = getShotChecklist(shot)
    const acceptanceStatus = String(shot.acceptance?.status || '')
    return checklist.videoReady && (acceptanceStatus === 'approved' || acceptanceStatus === 'accepted')
  })

  if (scriptsCount === 0) issues.push('缺剧本内容')
  if (shots.length === 0) issues.push('缺分镜镜头')
  if (!visualReady) issues.push('缺视觉设定')
  if ((referencedVisualAssets?.draftAssetCount || 0) > 0) issues.push(`仍有 ${referencedVisualAssets?.draftAssetCount} 个已引用视觉资产缺参考图`)
  if ((referencedVisualAssets?.refReadyAssetCount || 0) > 0) issues.push(`仍有 ${referencedVisualAssets?.refReadyAssetCount} 个已引用视觉资产尚未锁定终图`)
  if ((referencedVisualAssets?.rejectedAssetCount || 0) > 0) issues.push(`仍有 ${referencedVisualAssets?.rejectedAssetCount} 个已引用视觉资产处于退回状态`)
  if (storyboardReadiness.missingPrompt > 0) issues.push(`仍有 ${storyboardReadiness.missingPrompt} 个镜头缺提示词`)
  if (storyboardReadiness.missingFrame > 0) issues.push(`仍有 ${storyboardReadiness.missingFrame} 个镜头缺首帧`)
  if (storyboardReadiness.missingVideo > 0) issues.push(`仍有 ${storyboardReadiness.missingVideo} 个镜头缺视频`)
  if (pendingReviewShots.length > 0) issues.push(`仍有 ${pendingReviewShots.length} 个镜头未通过验收`)

  return {
    canExport: issues.length === 0 && shots.length > 0,
    issues,
    totalShots: shots.length,
    deliverableShots: deliverableShots.length,
    pendingReviewShots: pendingReviewShots.length,
    blockedShots: shots
      .map((shot) => {
        const checklist = getShotChecklist(shot)
        const acceptanceStatus = String(shot.acceptance?.status || 'pending')
        const reasons = [...checklist.missing]
        if (!['approved', 'accepted'].includes(acceptanceStatus)) {
          reasons.push(acceptanceStatus === 'failed' ? '验收未通过' : '待验收')
        }
        return {
          episode: shot.episode ?? 1,
          shotId: shot.shot_id,
          reasons,
        }
      })
      .filter((item) => item.reasons.length > 0),
  }
}
