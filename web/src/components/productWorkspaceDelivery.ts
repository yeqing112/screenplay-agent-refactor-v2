import type {
  ScriptOutput,
  StoryboardShotOutput,
  VisualLocationOutput,
  VisualMakeupOutput,
  VisualPropOutput,
  VisualReferenceAssetOutput,
} from '../prototyping/sceneComposerData'
import { getScriptDecision, type ScriptDecisionMap } from './productWorkspaceScriptDecisions'
import { buildScriptReleaseSummary } from './productWorkspaceScriptRelease'

export type DeliveryRepairSection = 'adaptation' | 'scripts' | 'storyboard' | 'assets' | 'qa'

export interface DeliveryBlockedItem {
  code:
    | 'adaptation_not_locked'
    | 'missing_script'
    | 'script_not_locked'
    | 'script_not_released'
    | 'missing_storyboard'
    | 'missing_prompts'
    | 'missing_images'
    | 'missing_videos'
    | 'missing_asset_references'
    | 'qa_blocked'
  label: string
  detail: string
  targetSection: DeliveryRepairSection
  priority: 'high' | 'medium'
  episode?: number
  shotId?: string | null
  assetId?: string | null
}

export interface DeliveryEpisodeReadiness {
  episode: number
  hasScript: boolean
  canExport: boolean
  statusLabel: string
  scriptLocked: boolean
  scriptReleased: boolean
  scriptStatusLabel: string
  blockedReasons: string[]
  blockedItems: DeliveryBlockedItem[]
  recommendedRepairSection: DeliveryRepairSection | null
  recommendedRepairLabel: string
  totalShots: number
  readyShots: number
  promptReadyShots: number
  imageReadyShots: number
  videoReadyShots: number
  referencedAssetCount: number
  qaCount: number
}

export interface DeliveryRecord {
  id: string
  episode: number
  createdAt: string
  status: 'completed' | 'blocked'
  versionLabel: string
  formatLabel?: string
  summary: string
  exportFormat: string
  totalShots: number
  deliverableShots: number
  pendingReviewShots: number
  blockedShots: number
  blockedShotIds: string[]
  blockedShotIdsByCode?: Partial<Record<DeliveryBlockedItem['code'], string>>
  blockedCodes: DeliveryBlockedItem['code'][]
  blockedReasons: string[]
}

export interface DeliveryRecordRepairAction {
  code: DeliveryBlockedItem['code']
  label: string
  targetSection: DeliveryRepairSection
}

export interface DeliveryReferenceAssetSnapshot {
  assetRecordId: number | null
  assetName: string
  variantLabel: string
  prompt: string
  selectedReferences: Array<{
    id: number
    status: string
    model: string | undefined
    imageUrl: string | undefined
    localPath: string | undefined
    createdAt: string | null
  }>
}

export interface DeliveryExportPackage {
  bookId: number
  bookTitle: string
  episode: number
  generatedAt: string
  versionLabel: string
  contentPreparation: {
    chapterCount: number
    wordCount: number
    statusLabel: string
    statusDetail: string
  }
  adaptationDirection: {
    statusLabel: string
    statusDetail: string
    selectedName: string | null
    customNote: string | null
    lockedAt: string | null
  }
  script: {
    episode: number
    statusLabel: string
    lockedAt: string | null
    releasedAt: string | null
    note: string
    content: string
  }
  qa: {
    totalIssueCount: number
    blocked: boolean
    summary: string
  }
  readiness: DeliveryEpisodeReadiness
  adoptedStoryboard: Array<{
    shotId: string
    sceneName: string
    promptVersion: number | null
    staticPrompt: string
    motionPrompt: string
    finalPrompt: string
    adoptedImage: {
      id: string
      title: string
      label: string
      uri?: string
      previewUrl?: string
      model?: string
    } | null
    adoptedVideo: {
      id: string
      title: string
      label: string
      uri?: string
      previewUrl?: string
      model?: string
    } | null
  }>
  selectedReferenceAssets: {
    characters: DeliveryReferenceAssetSnapshot[]
    locations: DeliveryReferenceAssetSnapshot[]
    props: DeliveryReferenceAssetSnapshot[]
  }
}

interface Params {
  hasExplicitLockedAdaptation?: boolean
  scripts: ScriptOutput[]
  scriptDecisionState: ScriptDecisionMap
  shotsByEpisode: Record<number, StoryboardShotOutput[]>
  qaEntries: Array<{ episode: number; error_count?: number }>
  makeups: VisualMakeupOutput[]
  locations: VisualLocationOutput[]
  props: VisualPropOutput[]
}

const DELIVERY_BLOCKED_CODE_MAP: Record<
  DeliveryBlockedItem['code'],
  { label: string; targetSection: DeliveryRepairSection; keywords: string[] }
> = {
  adaptation_not_locked: {
    label: '返回改编方向锁定',
    targetSection: 'adaptation',
    keywords: ['改编方向', '未锁定', '方向未锁定'],
  },
  missing_script: {
    label: '返回剧本工作台补剧本',
    targetSection: 'scripts',
    keywords: ['缺剧本', '无剧本', '没有剧本'],
  },
  script_not_locked: {
    label: '返回剧本工作台锁稿',
    targetSection: 'scripts',
    keywords: ['剧本未锁', '未锁稿', '待锁稿'],
  },
  script_not_released: {
    label: '返回剧本工作台放行',
    targetSection: 'scripts',
    keywords: ['剧本未放行', '待放行', '未放行'],
  },
  missing_storyboard: {
    label: '返回分镜工作台补分镜',
    targetSection: 'storyboard',
    keywords: ['缺分镜', '无分镜', '没有分镜'],
  },
  missing_prompts: {
    label: '返回分镜工作台补提示词',
    targetSection: 'storyboard',
    keywords: ['缺提示词', '静态提示词', '运动提示词', '提示词未完成'],
  },
  missing_images: {
    label: '返回分镜工作台补参考图',
    targetSection: 'storyboard',
    keywords: ['缺已采纳分镜图', '缺分镜图', '没有图片', '参考图', '缺首帧', '没有首帧', '首帧'],
  },
  missing_videos: {
    label: '返回分镜工作台补视频',
    targetSection: 'storyboard',
    keywords: ['缺已采纳视频', '缺视频', '没有视频'],
  },
  missing_asset_references: {
    label: '返回资产中心补引用',
    targetSection: 'assets',
    keywords: ['缺资产引用', '没有资产引用', '资产引用不足', '缺少资产'],
  },
  qa_blocked: {
    label: '返回 QA 工作台修复',
    targetSection: 'qa',
    keywords: ['QA', '质检', '待处理问题', '问题待处理', '未通过验收', '验收未通过'],
  },
}

export function buildDeliveryEpisodeReadiness(params: Params): DeliveryEpisodeReadiness[] {
  const episodeIds = new Set<number>([
    ...params.scripts.map((item) => item.episode),
    ...Object.keys(params.shotsByEpisode).map((value) => Number(value)),
    ...params.qaEntries.map((item) => item.episode),
  ])

  return Array.from(episodeIds)
    .filter((episode) => episode > 0)
    .sort((left, right) => left - right)
    .map((episode) => {
      const script = params.scripts.find((item) => item.episode === episode && item.content.trim()) ?? null
      const hasScript = Boolean(script)
      const scriptDecision = getScriptDecision(params.scriptDecisionState, episode)
      const scriptLocked = Boolean(scriptDecision.lockedAt)
      const scriptReleased = Boolean(scriptDecision.releasedAt)
      const shots = params.shotsByEpisode[episode] ?? []
      const qaCount = params.qaEntries
        .filter((item) => item.episode === episode)
        .reduce((sum, item) => sum + (item.error_count ?? 0), 0)

      const promptReadyShots = shots.filter((shot) =>
        Boolean(shot.visual_prompt_static?.trim() && shot.visual_prompt_motion?.trim()),
      ).length
      const imageReadyShots = shots.filter((shot) => hasAdoptedAsset(shot.assets?.images)).length
      const videoReadyShots = shots.filter((shot) => hasAdoptedAsset(shot.assets?.videos)).length
      const referencedAssetCount = countEpisodeReferencedAssets(
        episode,
        shots,
        params.makeups,
        params.locations,
        params.props,
      )
      const readyShots = shots.filter((shot) => isShotReadyForDelivery(shot)).length
      const release = buildScriptReleaseSummary({
        hasScript,
        scriptLocked,
        scriptReleased,
        shotCount: shots.length,
      })

      const blockedItems = buildBlockedItems({
        episode,
        adaptationLocked: Boolean(params.hasExplicitLockedAdaptation),
        hasScript,
        scriptLocked,
        scriptReleased,
        shots,
        shotsLength: shots.length,
        promptReadyShots,
        imageReadyShots,
        videoReadyShots,
        totalShots: shots.length,
        referencedAssetCount,
        qaCount,
      })

      const blockedReasons = blockedItems.map((item) => item.label)
      const recommendedRepairSection = blockedItems[0]?.targetSection ?? null
      const recommendedRepairLabel = buildRepairLabel(recommendedRepairSection, blockedItems[0]?.detail ?? '')

      return {
        episode,
        hasScript,
        canExport: blockedItems.length === 0,
        statusLabel: blockedItems.length === 0 ? '可交付' : blockedItems.length >= 3 ? '阻塞中' : '待补齐',
        scriptLocked,
        scriptReleased,
        scriptStatusLabel: release.scriptStatusLabel,
        blockedReasons,
        blockedItems,
        recommendedRepairSection,
        recommendedRepairLabel,
        totalShots: shots.length,
        readyShots,
        promptReadyShots,
        imageReadyShots,
        videoReadyShots,
        referencedAssetCount,
        qaCount,
      }
    })
}

export function summarizeDeliveryPackage(readiness: DeliveryEpisodeReadiness) {
  return [
    `第 ${readiness.episode} 集`,
    `剧本 ${readiness.scriptStatusLabel}`,
    `镜头 ${readiness.readyShots}/${readiness.totalShots}`,
    `提示词 ${readiness.promptReadyShots}/${readiness.totalShots}`,
    `分镜图 ${readiness.imageReadyShots}/${readiness.totalShots}`,
    `视频 ${readiness.videoReadyShots}/${readiness.totalShots}`,
    `资产引用 ${readiness.referencedAssetCount}`,
    readiness.qaCount > 0 ? `QA ${readiness.qaCount}` : 'QA 通过',
  ].join(' | ')
}

export function normalizeDeliveryRecordFormatLabel(exportFormat: string) {
  const normalized = String(exportFormat || '').trim().toLowerCase()
  if (!normalized) return 'JSON'
  if (normalized === 'pdf') return 'PDF'
  if (normalized === 'word' || normalized === 'doc') return 'Word'
  if (normalized === 'fdx' || normalized === 'final-draft') return 'Final Draft'
  if (normalized === 'json') return 'JSON'
  if (normalized === 'delivery') return '交付快照'
  return normalized.toUpperCase()
}

export function deriveDeliveryRecordRepairActions(input: {
  status: DeliveryRecord['status']
  blockedCodes?: DeliveryBlockedItem['code'][]
  blockedReasons?: string[]
}) {
  if (input.status !== 'blocked') return []

  const actions: DeliveryRecordRepairAction[] = []
  const seen = new Set<DeliveryBlockedItem['code']>()

  const addCode = (code: DeliveryBlockedItem['code']) => {
    if (seen.has(code)) return
    seen.add(code)
    const config = DELIVERY_BLOCKED_CODE_MAP[code]
    actions.push({
      code,
      label: config.label,
      targetSection: config.targetSection,
    })
  }

  for (const code of input.blockedCodes ?? []) {
    if (code in DELIVERY_BLOCKED_CODE_MAP) addCode(code)
  }

  if (actions.length > 0) return actions

  for (const reason of input.blockedReasons ?? []) {
    const normalized = String(reason || '').trim()
    if (!normalized) continue
    for (const [code, config] of Object.entries(DELIVERY_BLOCKED_CODE_MAP) as Array<
      [DeliveryBlockedItem['code'], (typeof DELIVERY_BLOCKED_CODE_MAP)[DeliveryBlockedItem['code']]]
    >) {
      if (config.keywords.some((keyword) => normalized.includes(keyword))) {
        addCode(code)
      }
    }
  }

  return actions
}

export function isLikelyCorruptedDeliveryText(value: unknown) {
  if (typeof value !== 'string') return false
  const trimmed = value.trim()
  if (!trimmed) return false
  if (trimmed === '[object Object]') return true
  if (trimmed.includes('????')) return true
  if (trimmed.toLowerCase().includes('manual verification snapshot')) return true
  if (/[闂備浇娉曢崳锕傚箯缁屽嫰姊绘担鑺ョ《闁革綇绠撻獮蹇曠矚閸掓摷]/.test(trimmed)) return true
  if (trimmed.includes('娴溿倓绮') || trimmed.includes('濞存嚎鍊') || trimmed.includes('闁告挆鍕') || trimmed.includes('闊浂鍋')) return true
  return false
}

export function summarizeDeliveryRecordHistory(input: {
  episode: number
  scriptStatusLabel?: string | null
  deliverableShots: number
  totalShots: number
  pendingReviewShots: number
  blockedReasons: string[]
  exportFormat: string
  status: 'completed' | 'blocked'
}) {
  const parts = [`第 ${input.episode} 集`]

  if (input.scriptStatusLabel) {
    parts.push(`剧本 ${input.scriptStatusLabel}`)
  }

  parts.push(`可交付镜头 ${input.deliverableShots}/${input.totalShots}`)

  if (input.pendingReviewShots > 0) {
    parts.push(`待复核 ${input.pendingReviewShots}`)
  }

  if (input.blockedReasons.length > 0) {
    parts.push(input.blockedReasons.slice(0, 3).join(' / '))
  } else {
    parts.push(
      input.status === 'completed'
        ? '已登记交付版本'
        : `${normalizeDeliveryRecordFormatLabel(input.exportFormat)} 快照`,
    )
  }

  return parts.join(' | ')
}

export function buildDeliveryExportPackage(input: {
  bookId: number
  bookTitle: string
  chapterCount: number
  wordCount: number
  contentStatusLabel: string
  contentStatusDetail: string
  adaptationStateLabel: string
  adaptationStateDetail: string
  selectedAdaptationName?: string
  adaptationCustomNote?: string
  adaptationLockedAt?: string | null
  readiness: DeliveryEpisodeReadiness
  scripts: ScriptOutput[]
  scriptDecisionState: ScriptDecisionMap
  shotsByEpisode: Record<number, StoryboardShotOutput[]>
  makeups: VisualMakeupOutput[]
  locations: VisualLocationOutput[]
  props: VisualPropOutput[]
  versionLabel: string
  generatedAt: string
}): DeliveryExportPackage {
  const script = input.scripts.find((item) => item.episode === input.readiness.episode) ?? null
  const scriptDecision = getScriptDecision(input.scriptDecisionState, input.readiness.episode)
  const shots = input.shotsByEpisode[input.readiness.episode] ?? []

  return {
    bookId: input.bookId,
    bookTitle: input.bookTitle,
    episode: input.readiness.episode,
    generatedAt: input.generatedAt,
    versionLabel: input.versionLabel,
    contentPreparation: {
      chapterCount: input.chapterCount,
      wordCount: input.wordCount,
      statusLabel: input.contentStatusLabel,
      statusDetail: input.contentStatusDetail,
    },
    adaptationDirection: {
      statusLabel: input.adaptationStateLabel,
      statusDetail: input.adaptationStateDetail,
      selectedName: input.selectedAdaptationName ?? null,
      customNote: input.adaptationCustomNote?.trim() ? input.adaptationCustomNote.trim() : null,
      lockedAt: input.adaptationLockedAt ?? null,
    },
    script: {
      episode: input.readiness.episode,
      statusLabel: input.readiness.scriptStatusLabel,
      lockedAt: scriptDecision.lockedAt,
      releasedAt: scriptDecision.releasedAt,
      note: scriptDecision.note,
      content: script?.content ?? '',
    },
    qa: {
      totalIssueCount: input.readiness.qaCount,
      blocked: input.readiness.qaCount > 0,
      summary:
        input.readiness.qaCount > 0
          ? `当前仍有 ${input.readiness.qaCount} 条 QA 问题。`
          : '当前未发现交付阻塞 QA。',
    },
    readiness: input.readiness,
    adoptedStoryboard: shots.map((shot) => ({
      shotId: String(shot.shot_id),
      sceneName: shot.scene_name,
      promptVersion: shot.prompt_version ?? null,
      staticPrompt: shot.visual_prompt_static ?? '',
      motionPrompt: shot.visual_prompt_motion ?? '',
      finalPrompt: shot.visual_prompt_final ?? '',
      adoptedImage: toDeliveryMediaSnapshot(shot.assets?.images),
      adoptedVideo: toDeliveryMediaSnapshot(shot.assets?.videos),
    })),
    selectedReferenceAssets: {
      characters: collectEpisodeReferenceSnapshots(
        input.makeups,
        input.readiness.episode,
        (item) => item.episode === input.readiness.episode,
      ),
      locations: collectEpisodeReferenceSnapshots(
        input.locations,
        input.readiness.episode,
        (item) => hasEpisodeShotIds(item.shot_ids, input.readiness.episode),
      ),
      props: collectEpisodeReferenceSnapshots(
        input.props,
        input.readiness.episode,
        (item) => hasEpisodeShotIds(item.shot_ids, input.readiness.episode),
      ),
    },
  }
}

function buildBlockedItems(input: {
  episode: number
  adaptationLocked: boolean
  hasScript: boolean
  scriptLocked: boolean
  scriptReleased: boolean
  shots: StoryboardShotOutput[]
  shotsLength: number
  promptReadyShots: number
  imageReadyShots: number
  videoReadyShots: number
  totalShots: number
  referencedAssetCount: number
  qaCount: number
}): DeliveryBlockedItem[] {
  const items: DeliveryBlockedItem[] = []
  const firstMissingPromptShot = input.shots.find(
    (shot) => !shot.visual_prompt_static?.trim() || !shot.visual_prompt_motion?.trim(),
  )
  const firstMissingImageShot = input.shots.find((shot) => !hasAdoptedAsset(shot.assets?.images))
  const firstMissingVideoShot = input.shots.find((shot) => !hasAdoptedAsset(shot.assets?.videos))
  const firstMissingReferenceShot = input.shots.find((shot) => countShotReferenceAssets(shot) === 0)

  if (!input.adaptationLocked) {
    items.push({
      code: 'adaptation_not_locked',
      label: '项目改编方向未锁定',
      detail: '正式交付前需要先锁定项目级改编方向，确保剧本、分镜、资产和 QA 继承同一主约束。',
      targetSection: 'adaptation',
      priority: 'high',
      episode: input.episode,
    })
  }
  if (!input.hasScript) {
    items.push({
      code: 'missing_script',
      label: '缺剧本',
      detail: '当前分集还没有正式剧本内容，无法进入交付。',
      targetSection: 'scripts',
      priority: 'high',
      episode: input.episode,
    })
  }
  if (input.hasScript && !input.scriptLocked) {
    items.push({
      code: 'script_not_locked',
      label: '剧本未锁稿',
      detail: '导出前需要先完成剧本锁稿决策。',
      targetSection: 'scripts',
      priority: 'high',
      episode: input.episode,
    })
  }
  if (input.hasScript && !input.scriptReleased) {
    items.push({
      code: 'script_not_released',
      label: '剧本未放行',
      detail: '剧本还没有明确放行到分镜与交付链路。',
      targetSection: 'scripts',
      priority: 'high',
      episode: input.episode,
    })
  }
  if (input.shotsLength === 0) {
    items.push({
      code: 'missing_storyboard',
      label: '缺镜头',
      detail: '当前分集还没有正式镜头内容。',
      targetSection: 'storyboard',
      priority: 'high',
      episode: input.episode,
    })
  }
  if (input.shotsLength > 0 && input.promptReadyShots < input.totalShots) {
    const firstShotId = String(firstMissingPromptShot?.shot_id ?? '').trim()
    items.push({
      code: 'missing_prompts',
      label: '提示词未齐',
      detail: buildBlockedDetailWithShot(
        `仍有 ${input.totalShots - input.promptReadyShots} 个镜头缺少静态或运动提示词。`,
        firstShotId,
      ),
      targetSection: 'storyboard',
      priority: 'high',
      episode: input.episode,
      shotId: firstShotId || null,
    })
  }
  if (input.shotsLength > 0 && input.imageReadyShots < input.totalShots) {
    const firstShotId = String(firstMissingImageShot?.shot_id ?? '').trim()
    items.push({
      code: 'missing_images',
      label: '缺已采纳分镜图',
      detail: buildBlockedDetailWithShot(
        `仍有 ${input.totalShots - input.imageReadyShots} 个镜头没有已采纳分镜图。`,
        firstShotId,
      ),
      targetSection: 'storyboard',
      priority: 'high',
      episode: input.episode,
      shotId: firstShotId || null,
    })
  }
  if (input.shotsLength > 0 && input.videoReadyShots < input.totalShots) {
    const firstShotId = String(firstMissingVideoShot?.shot_id ?? '').trim()
    items.push({
      code: 'missing_videos',
      label: '缺已采纳视频',
      detail: buildBlockedDetailWithShot(
        `仍有 ${input.totalShots - input.videoReadyShots} 个镜头没有已采纳视频版本。`,
        firstShotId,
      ),
      targetSection: 'storyboard',
      priority: 'medium',
      episode: input.episode,
      shotId: firstShotId || null,
    })
  }
  if (input.referencedAssetCount === 0 && input.shotsLength > 0) {
    const firstShotId = String(firstMissingReferenceShot?.shot_id ?? input.shots[0]?.shot_id ?? '').trim()
    items.push({
      code: 'missing_asset_references',
      label: '缺可追溯资产引用',
      detail: buildBlockedDetailWithShot(
        '当前镜头里还没有可追溯的人物、场景或道具参考引用。',
        firstShotId,
      ),
      targetSection: 'assets',
      priority: 'medium',
      episode: input.episode,
      shotId: firstShotId || null,
    })
  }
  if (input.qaCount > 0) {
    items.push({
      code: 'qa_blocked',
      label: `QA ${input.qaCount} 项`,
      detail: '当前仍有 QA 问题未清零或未明确放行。',
      targetSection: 'qa',
      priority: 'high',
      episode: input.episode,
    })
  }

  return items
}

function toDeliveryMediaSnapshot(
  items:
    | Array<{
        adopted?: boolean
        id?: string
        title?: string
        label?: string
        uri?: string
        previewUrl?: string
        model?: string
      }>
    | undefined,
) {
  const adopted = items?.find((item) => Boolean(item?.adopted)) ?? null
  if (!adopted) return null

  return {
    id: String(adopted.id ?? ''),
    title: String(adopted.title ?? ''),
    label: String(adopted.label ?? ''),
    uri: adopted.uri,
    previewUrl: adopted.previewUrl,
    model: adopted.model,
  }
}

function hasEpisodeShotIds(shotIds: string[] | undefined, episode: number) {
  return Array.isArray(shotIds) && shotIds.some((shotId) => String(shotId).startsWith(`${episode}-`))
}

function collectEpisodeReferenceSnapshots<T extends {
  id?: number
  name?: string
  character_name?: string
  subtitle?: string
  scope_label?: string
  stage_name?: string
  category?: string
  visual_prompt_zh?: string
  core_prompt_zh?: string
  zh_prompt?: string
  reference_assets?: VisualReferenceAssetOutput[]
}>(
  items: T[],
  episode: number,
  predicate: (item: T) => boolean,
): DeliveryReferenceAssetSnapshot[] {
  const snapshots: Array<DeliveryReferenceAssetSnapshot | null> = items
    .filter(predicate)
    .map((item) => {
      const selectedReferences = (item.reference_assets ?? [])
        .filter((reference) => reference.status === 'selected' || reference.status === 'locked')
        .map((reference) => ({
          id: Number(reference.id),
          status: String(reference.status ?? ''),
          model: reference.model,
          imageUrl: reference.image_url,
          localPath: reference.local_path,
          createdAt: reference.created_at ?? null,
        }))

      if (selectedReferences.length === 0) return null

      return {
        assetRecordId: typeof item.id === 'number' ? item.id : null,
        assetName: String(item.character_name ?? item.name ?? '未命名资产'),
        variantLabel: String(item.scope_label ?? item.stage_name ?? item.category ?? '当前版本'),
        prompt: String(item.visual_prompt_zh ?? item.zh_prompt ?? item.core_prompt_zh ?? ''),
        selectedReferences,
      }
    })

  return snapshots.filter((item): item is DeliveryReferenceAssetSnapshot => item !== null)
}

function buildRepairLabel(section: DeliveryRepairSection | null, detail: string) {
  if (!section) return '当前已具备交付条件。'
  const prefix =
    section === 'adaptation'
      ? '先回改编方向'
      : section === 'scripts'
        ? '先回剧本工作台'
        : section === 'storyboard'
          ? '先回镜头工作台'
          : section === 'assets'
            ? '先回资产中心'
            : '先回 QA 修复'
  return `${prefix}：${detail}`
}

function isShotReadyForDelivery(shot: StoryboardShotOutput) {
  const hasPrompt = Boolean(shot.visual_prompt_static?.trim() && shot.visual_prompt_motion?.trim())
  const hasImage = hasAdoptedAsset(shot.assets?.images)
  const hasVideo = hasAdoptedAsset(shot.assets?.videos)
  return hasPrompt && hasImage && hasVideo
}

function hasAdoptedAsset(items: Array<{ adopted?: boolean }> | undefined) {
  return Array.isArray(items) && items.some((item) => Boolean(item?.adopted))
}

function buildBlockedDetailWithShot(detail: string, shotId: string) {
  if (!shotId) return detail
  return `${detail} 首个阻塞镜头：${shotId}。`
}

function countShotReferenceAssets(shot: StoryboardShotOutput) {
  const characters = shot.assets?.references?.characters ?? {}
  const scenes = Array.isArray(shot.assets?.references?.scene) ? shot.assets.references.scene : []
  const propGroups = shot.assets?.references?.props ?? {}

  const characterCount = Object.values(characters).reduce((subTotal, items) => {
    return subTotal + (Array.isArray(items) ? items.length : 0)
  }, 0)
  const sceneCount = scenes.length
  const propCount = Object.values(propGroups).reduce((subTotal, items) => {
    return subTotal + (Array.isArray(items) ? items.length : 0)
  }, 0)

  return characterCount + sceneCount + propCount
}

function countEpisodeReferencedAssets(
  episode: number,
  shots: StoryboardShotOutput[],
  makeups: VisualMakeupOutput[],
  locations: VisualLocationOutput[],
  props: VisualPropOutput[],
) {
  const shotReferenceCount = shots.reduce((sum, shot) => sum + countShotReferenceAssets(shot), 0)

  if (shotReferenceCount > 0) {
    return shotReferenceCount
  }

  return [
    ...makeups.filter((item) => item.episode === episode),
    ...locations.filter((item) => item.shot_ids?.some((shotId) => String(shotId).startsWith(`${episode}-`))),
    ...props.filter((item) => item.shot_ids?.some((shotId) => String(shotId).startsWith(`${episode}-`))),
  ].reduce((sum, item) => sum + (item.reference_assets?.length ?? 0), 0)
}

export function buildDeliveryExportSummaryText(readiness: DeliveryEpisodeReadiness) {
  return [
    `导出状态：${readiness.canExport ? '可导出' : '未完成'}`,
    `集数：第 ${readiness.episode} 集`,
    `剧本状态：${readiness.scriptStatusLabel}`,
    `总镜头：${readiness.totalShots}`,
    `可交付镜头：${readiness.readyShots}`,
    `提示词完成：${readiness.promptReadyShots}/${readiness.totalShots}`,
    `静帧完成：${readiness.imageReadyShots}/${readiness.totalShots}`,
    `视频完成：${readiness.videoReadyShots}/${readiness.totalShots}`,
    `参考资产引用：${readiness.referencedAssetCount}`,
    `QA 问题：${readiness.qaCount}`,
    ...(readiness.blockedReasons.length > 0 ? readiness.blockedReasons.map((item) => `- ${item}`) : []),
  ].join('\n')
}

export function buildDeliveryFileStem(bookTitle: string, episode: number, versionLabel: string) {
  const safeTitle = String(bookTitle || 'project').replace(/[^\w\u4e00-\u9fa5-]+/g, '_') || 'project'
  return `${safeTitle}-episode-${episode}-${versionLabel}`
}

export function buildDeliveryWordDocument(exportPackage: DeliveryExportPackage) {
  const shotRows = exportPackage.adoptedStoryboard
    .map(
      (shot) => `
      <tr>
        <td>${escapeHtml(shot.shotId)}</td>
        <td>${escapeHtml(shot.sceneName)}</td>
        <td>${escapeHtml(shot.staticPrompt)}</td>
        <td>${escapeHtml(shot.motionPrompt)}</td>
        <td>${escapeHtml(shot.adoptedImage?.title || '-')}</td>
        <td>${escapeHtml(shot.adoptedVideo?.title || '-')}</td>
      </tr>`,
    )
    .join('')

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>${escapeHtml(exportPackage.bookTitle)} 第${exportPackage.episode}集交付文档</title>
  <style>
    body { font-family: "Microsoft YaHei", sans-serif; padding: 32px; color: #111827; }
    h1, h2 { margin: 0 0 12px; }
    .meta { margin-bottom: 24px; color: #4b5563; white-space: pre-wrap; }
    .section { margin-top: 24px; }
    table { width: 100%; border-collapse: collapse; margin-top: 16px; }
    th, td { border: 1px solid #cbd5e1; padding: 8px; font-size: 12px; vertical-align: top; }
    th { background: #e2e8f0; }
    pre { white-space: pre-wrap; background: #f8fafc; border: 1px solid #e2e8f0; padding: 16px; }
  </style>
</head>
<body>
  <h1>${escapeHtml(exportPackage.bookTitle)} 第${exportPackage.episode}集交付文档</h1>
  <div class="meta">${escapeHtml(buildDeliveryExportSummaryText(exportPackage.readiness))}</div>
  <div class="section">
    <h2>改编方向</h2>
    <pre>${escapeHtml(exportPackage.adaptationDirection.selectedName || exportPackage.adaptationDirection.statusLabel)}
${escapeHtml(exportPackage.adaptationDirection.customNote || exportPackage.adaptationDirection.statusDetail || '')}</pre>
  </div>
  <div class="section">
    <h2>剧本</h2>
    <pre>${escapeHtml(exportPackage.script.content || '暂无剧本内容')}</pre>
  </div>
  <div class="section">
    <h2>分镜交付表</h2>
    <table>
      <thead>
        <tr><th>镜号</th><th>场景</th><th>静态提示词</th><th>运动提示词</th><th>采用静帧</th><th>采用视频</th></tr>
      </thead>
      <tbody>
        ${shotRows || '<tr><td colspan="6">暂无已采纳分镜</td></tr>'}
      </tbody>
    </table>
  </div>
</body>
</html>`
}

export function buildDeliveryFinalDraftDocument(exportPackage: DeliveryExportPackage) {
  const promptParagraphs = exportPackage.adoptedStoryboard
    .flatMap((shot) => [
      `<Paragraph Type="Scene Heading"><Text>${escapeXml(`第${exportPackage.episode}集 / ${shot.shotId} / ${shot.sceneName}`)}</Text></Paragraph>`,
      `<Paragraph Type="Action"><Text>${escapeXml(shot.staticPrompt || '')}</Text></Paragraph>`,
      `<Paragraph Type="Action"><Text>${escapeXml(shot.motionPrompt || '')}</Text></Paragraph>`,
    ])
    .join('')

  return `<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<FinalDraft DocumentType="Script" Template="No" Version="1">
  <Content>
    <Paragraph Type="Title"><Text>${escapeXml(`${exportPackage.bookTitle} 第${exportPackage.episode}集交付导出`)}</Text></Paragraph>
    <Paragraph Type="Action"><Text>${escapeXml(buildDeliveryExportSummaryText(exportPackage.readiness))}</Text></Paragraph>
    <Paragraph Type="Scene Heading"><Text>${escapeXml(`第${exportPackage.episode}集 / 剧本`)}</Text></Paragraph>
    <Paragraph Type="Action"><Text>${escapeXml(exportPackage.script.content || '暂无剧本内容')}</Text></Paragraph>
    ${promptParagraphs || '<Paragraph Type="Action"><Text>暂无已采纳分镜</Text></Paragraph>'}
  </Content>
</FinalDraft>`
}

function escapeHtml(value: unknown) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function escapeXml(value: unknown) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}
