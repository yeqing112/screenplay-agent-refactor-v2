import type {
  StoryboardShotOutput,
  VisualLocationOutput,
  VisualMakeupOutput,
  VisualPropOutput,
  VisualReferenceAssetOutput,
} from '../prototyping/sceneComposerData'
import { buildShotReadiness } from './productWorkspaceStoryboard'

export type AssetCategory = 'character' | 'location' | 'prop'

type AssetVariantEntry = {
  id: string
  label: string
  stageName?: string
  episode?: number | null
  status: string
  scope?: string
}

export interface AssetSummary {
  id: string
  category: AssetCategory
  assetRecordId: number | null
  recordSource?: string
  isReadonly?: boolean
  title: string
  subtitle: string
  detailPrimary?: string
  detailSecondary?: string
  detailTertiary?: string
  status: string
  prompt: string
  shotIds: string[]
  episodeIds: number[]
  referenceCount: number
  previewCount: number
  selectedReferenceCount: number
  lockedReferenceCount: number
  staleReferenceCount: number
  hasStaleReferencePrompt: boolean
  references: VisualReferenceAssetOutput[]
  variantGroupKey?: string
  variantLabel?: string
  variantScope?: string
  variantStageName?: string
  variantEpisode?: number | null
  siblingVariantCount?: number
  siblingVariants?: AssetVariantEntry[]
}

export interface AssetImpactShotSummary {
  shotId: string
  episode: number | null
  sceneName: string
  blockerCount: number
  statusLabel: string
  nextAction: string
  missingItems: string[]
}

export interface AssetEpisodeInsight {
  shotIds: string[]
  blockerCount: number
  missingReference: boolean
  impactShots: AssetImpactShotSummary[]
}

function compareNumericLikeStrings(left: string, right: string) {
  const leftValue = Number(left)
  const rightValue = Number(right)
  if (Number.isFinite(leftValue) && Number.isFinite(rightValue)) {
    return leftValue - rightValue
  }
  return left.localeCompare(right, 'zh-CN', { numeric: true })
}

function summarizeReferenceAssets(referenceAssets: VisualReferenceAssetOutput[] | undefined) {
  const items = referenceAssets ?? []
  const previewCount = items.filter((item) => item.image_url || item.local_path).length
  const selectedReferenceCount = items.filter((item) => item.status === 'selected').length
  const lockedReferenceCount = items.filter((item) => item.status === 'locked').length
  return {
    totalCount: items.length,
    previewCount,
    selectedReferenceCount,
    lockedReferenceCount,
  }
}

function normalizePromptText(value: string | null | undefined) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
}

function sanitizePromptDisplayText(value: string | null | undefined) {
  const text = String(value || '')
  if (!text.trim()) return ''

  return text
    .replace(/人物集默认定妆设定板/g, '人物分集默认定妆设定板')
    .replace(/人物集默认定妆/g, '人物分集默认定妆')
    .replace(/当前集默认定妆/g, '当前分集默认定妆')
    .replace(/(^|[^分])集默认定妆/g, (_match, prefix) => `${prefix}分集默认定妆`)
    .replace(/episode_(\d+)_default/g, (_match, episode) => `第 ${episode} 集默认造型`)
    .replace(/shot_(\d+)_([^/\n。]+)/g, (_match, shot, label) => `镜头 ${shot} / ${String(label).replace(/_/g, ' ')}`)
}

function countStaleReferencePrompts(assetPrompt: string, referenceAssets: VisualReferenceAssetOutput[] | undefined) {
  const normalizedAssetPrompt = normalizePromptText(assetPrompt)
  if (!normalizedAssetPrompt) return 0
  return (referenceAssets ?? []).filter((item) => {
    const normalizedReferencePrompt = normalizePromptText(item.prompt)
    return Boolean(normalizedReferencePrompt) && normalizedReferencePrompt !== normalizedAssetPrompt
  }).length
}

function toEpisodeIds(shotIds: string[]) {
  return Array.from(
    new Set(
      shotIds
        .map((shotId) => Number(String(shotId).split('-')[0]))
        .filter((episode) => Number.isFinite(episode) && episode > 0),
    ),
  ).sort((left, right) => left - right)
}

function normalizeDisplayText(value: unknown): string {
  if (Array.isArray(value)) {
    return value
      .map((item) => normalizeDisplayText(item))
      .filter(Boolean)
      .join('、')
  }

  if (value === null || value === undefined) return ''
  const text = String(value).trim()
  if (!text) return ''

  if ((text.startsWith('[') && text.endsWith(']')) || (text.startsWith('{') && text.endsWith('}'))) {
    try {
      return normalizeDisplayText(JSON.parse(text))
    } catch {
      return decodeEscapedUnicodeText(text)
    }
  }

  return decodeEscapedUnicodeText(text)
}

function decodeEscapedUnicodeText(text: string) {
  if (!/\\u[0-9a-fA-F]{4}/.test(text)) return text
  return text.replace(/\\u([0-9a-fA-F]{4})/g, (_match, hex: string) =>
    String.fromCharCode(Number.parseInt(hex, 16)),
  )
}

function pickFirstDisplayValue(...values: Array<unknown>) {
  for (const value of values) {
    const normalized = normalizeDisplayText(value)
    if (normalized) return normalized
  }
  return ''
}

function collectShotCandidateNames(shot: StoryboardShotOutput) {
  const candidateNames = new Set<string>()
  if (shot.scene_name) candidateNames.add(shot.scene_name)
  for (const asset of shot.used_assets ?? []) {
    if (asset.asset_name) candidateNames.add(asset.asset_name)
  }
  for (const binding of shot.prompt_compile_context?.asset_bindings?.characters ?? []) {
    if (binding.asset_name) candidateNames.add(binding.asset_name)
    if (binding.stage_name) candidateNames.add(binding.stage_name)
  }
  return candidateNames
}

function toShotKey(episode: number | null | undefined, shotId: string | number | null | undefined) {
  const normalizedShotId = String(shotId ?? '').trim()
  const normalizedEpisode = typeof episode === 'number' && Number.isFinite(episode) ? episode : null
  if (!normalizedShotId) return ''
  return normalizedEpisode ? `${normalizedEpisode}-${normalizedShotId}` : normalizedShotId
}

function shotStructuredAssetIds(shot: StoryboardShotOutput, category: AssetCategory) {
  if (category === 'character') return shot.structured_shot?.character_asset_ids ?? []
  if (category === 'location') return shot.structured_shot?.scene_asset_id ? [shot.structured_shot.scene_asset_id] : []
  return shot.structured_shot?.prop_asset_ids ?? []
}

function shotPromptCharacterIds(shot: StoryboardShotOutput) {
  return (shot.makeup_prompts ?? []).map((item) => String(item.id ?? '').trim()).filter(Boolean)
}

function shotPromptCharacterNames(shot: StoryboardShotOutput) {
  return new Set(
    (shot.makeup_prompts ?? [])
      .flatMap((item) => [item.character_name, item.stage_name])
      .map((item) => String(item ?? '').trim())
      .filter(Boolean),
  )
}

function doesShotUseAsset(asset: AssetSummary, shot: StoryboardShotOutput, candidateNames: Set<string>) {
  const rawShotId = String(shot.shot_id ?? '').trim()
  const compositeShotId = toShotKey(typeof shot.episode === 'number' ? shot.episode : null, shot.shot_id)
  if (asset.shotIds.includes(rawShotId) || (compositeShotId && asset.shotIds.includes(compositeShotId))) {
    return true
  }

  const structuredIds = shotStructuredAssetIds(shot, asset.category).map((item) => String(item ?? '').trim())
  if (asset.assetRecordId !== null && structuredIds.includes(String(asset.assetRecordId))) {
    return true
  }

  if (asset.category === 'character') {
    if (asset.assetRecordId !== null && shotPromptCharacterIds(shot).includes(String(asset.assetRecordId))) {
      return true
    }
    const promptNames = shotPromptCharacterNames(shot)
    if (promptNames.has(asset.title) || promptNames.has(asset.subtitle)) {
      return true
    }
  }

  return candidateNames.has(asset.title) || candidateNames.has(asset.subtitle)
}

function makeupScopeOrder(scope?: string) {
  const normalized = String(scope || '').trim()
  if (normalized === 'base_identity') return 0
  if (normalized === 'episode_default') return 1
  if (normalized === 'shot_variant') return 2
  return 9
}

function compareCharacterVariants(left: VisualMakeupOutput, right: VisualMakeupOutput) {
  const scopeDelta = makeupScopeOrder(left.makeup_scope) - makeupScopeOrder(right.makeup_scope)
  if (scopeDelta !== 0) return scopeDelta
  const episodeDelta = (left.episode ?? 0) - (right.episode ?? 0)
  if (episodeDelta !== 0) return episodeDelta
  return String(left.stage_name || '').localeCompare(String(right.stage_name || ''), 'zh-CN')
}

function compareAssetVariantEntries(left: AssetVariantEntry, right: AssetVariantEntry) {
  const episodeDelta = (left.episode ?? 0) - (right.episode ?? 0)
  if (episodeDelta !== 0) return episodeDelta
  return String(left.stageName || '').localeCompare(String(right.stageName || ''), 'zh-CN')
}

function normalizeCharacterVariantLabel(scopeLabel: unknown, stageName: unknown, variantScope: unknown) {
  const normalizedStage = String(stageName || '').trim().toLowerCase()
  const normalizedScope = String(variantScope || '').trim().toLowerCase()
  if (normalizedStage === 'base_identity' || normalizedScope === 'base_identity') return '基础定妆'
  if (normalizedScope === 'episode_default' || /^episode_\d+_default$/.test(normalizedStage)) return '分集默认'
  if (normalizedScope === 'shot_variant' || normalizedStage.startsWith('shot_')) return '分镜精调'

  const explicitLabel = normalizeDisplayText(scopeLabel)
  if (explicitLabel) return explicitLabel
  return '定妆版本'
}

function normalizeCharacterVariantStage(stageName: unknown, variantScope: unknown) {
  const normalizedStage = normalizeDisplayText(stageName)
  if (!normalizedStage) return ''

  const lowered = normalizedStage.toLowerCase()
  const normalizedScope = String(variantScope || '').trim().toLowerCase()
  if (lowered === 'base_identity' || normalizedScope === 'base_identity') return '基础身份阶段'

  const episodeMatch = lowered.match(/^episode_(\d+)_default$/)
  if (episodeMatch) return `第 ${episodeMatch[1]} 集默认造型`

  const shotMatch = normalizedStage.match(/^shot_(\d+)_(.+)$/i)
  if (shotMatch) return `镜头 ${shotMatch[1]} · ${shotMatch[2].replace(/_/g, ' ')}`

  if (normalizedScope === 'episode_default') return '分集默认阶段'
  return normalizedStage
}

function normalizePropVariantLabel(importance: unknown, category: unknown) {
  const normalizedImportance = String(importance || '').trim().toLowerCase()
  if (normalizedImportance === 'high') return '重点道具'
  if (normalizedImportance === 'medium') return '当前版本'
  if (normalizedImportance === 'low') return '补充版本'
  return pickFirstDisplayValue(category, '道具版本')
}

function inferLocationVariantScope(
  item: Pick<VisualLocationOutput, 'style' | 'lighting_mood' | 'color_palette' | 'variant_scope'>,
  siblingVariantCount: number,
) {
  if (String(item.variant_scope || '').trim()) return String(item.variant_scope || '').trim()
  return siblingVariantCount > 1 ? 'scene_variant' : ''
}

function inferLocationVariantStage(item: Pick<VisualLocationOutput, 'stage_name' | 'lighting_mood' | 'color_palette' | 'style'>) {
  return pickFirstDisplayValue(item.stage_name, item.lighting_mood, item.color_palette, item.style)
}

function inferPropVariantScope(
  item: Pick<VisualPropOutput, 'importance' | 'associated_characters' | 'era' | 'variant_scope'>,
  siblingVariantCount: number,
) {
  if (String(item.variant_scope || '').trim()) return String(item.variant_scope || '').trim()
  return siblingVariantCount > 1 ? 'prop_variant' : ''
}

function inferPropVariantStage(item: Pick<VisualPropOutput, 'stage_name' | 'associated_characters' | 'era' | 'description'>) {
  return pickFirstDisplayValue(item.stage_name, item.associated_characters, item.era, item.description)
}

export function buildAssetEpisodeInsights(
  assets: AssetSummary[],
  episodeShots: StoryboardShotOutput[],
): Map<string, AssetEpisodeInsight> {
  const result = new Map<string, AssetEpisodeInsight>()

  const addImpactShot = (assetId: string, shot: StoryboardShotOutput) => {
    const readiness = buildShotReadiness(shot)
    const current = result.get(assetId) ?? {
      shotIds: [],
      blockerCount: 0,
      missingReference: false,
      impactShots: [],
    }

    if (!current.shotIds.includes(String(shot.shot_id))) {
      current.shotIds.push(String(shot.shot_id))
    }

    current.blockerCount = Math.max(current.blockerCount, readiness.blockerCount)

    if (!current.impactShots.some((item) => item.shotId === String(shot.shot_id))) {
      current.impactShots.push({
        shotId: String(shot.shot_id),
        episode: typeof shot.episode === 'number' ? shot.episode : null,
        sceneName: shot.scene_name || '未命名镜头',
        blockerCount: readiness.blockerCount,
        statusLabel: readiness.statusLabel,
        nextAction: readiness.nextAction,
        missingItems: readiness.items.filter((item) => item.status === 'missing').map((item) => item.label),
      })
    }

    result.set(assetId, current)
  }

  for (const shot of episodeShots) {
    const candidateNames = collectShotCandidateNames(shot)
    for (const asset of assets) {
      if (doesShotUseAsset(asset, shot, candidateNames)) {
        addImpactShot(asset.id, shot)
      }
    }
  }

  for (const asset of assets) {
    const current = result.get(asset.id) ?? {
      shotIds: [],
      blockerCount: 0,
      missingReference: false,
      impactShots: [],
    }
    current.missingReference = asset.previewCount === 0
    current.impactShots.sort((left, right) => {
      if ((left.episode ?? 0) !== (right.episode ?? 0)) return (left.episode ?? 0) - (right.episode ?? 0)
      return compareNumericLikeStrings(left.shotId, right.shotId)
    })
    current.shotIds.sort((left, right) => compareNumericLikeStrings(left, right))
    result.set(asset.id, current)
  }

  return result
}

export function buildCharacterAssetSummaries(makeups: VisualMakeupOutput[]): AssetSummary[] {
  const groupedVariants = new Map<string, VisualMakeupOutput[]>()
  for (const item of makeups) {
    const key = normalizeDisplayText(item.character_name) || '未命名角色'
    const bucket = groupedVariants.get(key) ?? []
    bucket.push(item)
    groupedVariants.set(key, bucket)
  }

  return makeups.map((item, index) => {
    const refs = summarizeReferenceAssets(item.reference_assets)
    const shotIds = item.shot_ids ?? []
    const prompt = sanitizePromptDisplayText(
      item.visual_prompt_zh || item.core_prompt_zh || item.outfit_prompt_zh || item.scene_prompt_zh || '',
    )
    const staleReferenceCount = countStaleReferencePrompts(prompt, item.reference_assets)
    const variantGroupKey = normalizeDisplayText(item.character_name) || '未命名角色'
    const siblingVariants = (groupedVariants.get(variantGroupKey) ?? [])
      .slice()
      .sort(compareCharacterVariants)
      .map((variant, variantIndex) => ({
        id: `character-${variant.id ?? `${variant.character_name}-${makeups.indexOf(variant) >= 0 ? makeups.indexOf(variant) : variantIndex}`}`,
        label: normalizeCharacterVariantLabel(variant.scope_label, variant.stage_name, variant.makeup_scope),
        stageName: normalizeCharacterVariantStage(variant.stage_name, variant.makeup_scope),
        episode: typeof variant.episode === 'number' ? variant.episode : null,
        status: variant.derived_asset_status || variant.asset_status || 'draft',
        scope: String(variant.makeup_scope || '').trim(),
      }))

    return {
      id: `character-${item.id ?? `${item.character_name}-${index}`}`,
      category: 'character',
      assetRecordId: item.id ?? null,
      recordSource: item.record_source || 'visual_makeup',
      isReadonly: Boolean(item.is_readonly),
      title: normalizeDisplayText(item.character_name) || '未命名角色',
      subtitle: pickFirstDisplayValue(
        normalizeCharacterVariantLabel(item.scope_label, item.stage_name, item.makeup_scope),
        item.identity,
        '浜虹墿瀹氬',
      ),
      detailPrimary: pickFirstDisplayValue(item.identity, item.gender ? `${item.gender}瑙掕壊` : ''),
      detailSecondary: pickFirstDisplayValue(
        normalizeCharacterVariantStage(item.stage_name, item.makeup_scope),
        item.temperament,
        item.makeup_scope,
      ),
      detailTertiary: pickFirstDisplayValue(item.refined_outfit, item.hair_style, item.expression_mood),
      status: item.derived_asset_status || item.asset_status || 'draft',
      prompt,
      shotIds,
      episodeIds: toEpisodeIds(shotIds),
      referenceCount: refs.totalCount,
      previewCount: refs.previewCount,
      selectedReferenceCount: refs.selectedReferenceCount,
      lockedReferenceCount: refs.lockedReferenceCount,
      staleReferenceCount,
      hasStaleReferencePrompt: staleReferenceCount > 0,
      references: item.reference_assets ?? [],
      variantGroupKey,
      variantLabel: normalizeCharacterVariantLabel(item.scope_label, item.stage_name, item.makeup_scope),
      variantScope: item.makeup_scope || '',
      variantStageName: normalizeCharacterVariantStage(item.stage_name, item.makeup_scope),
      variantEpisode: typeof item.episode === 'number' ? item.episode : null,
      siblingVariantCount: siblingVariants.length,
      siblingVariants,
    }
  })
}

export function buildLocationAssetSummaries(locations: VisualLocationOutput[]): AssetSummary[] {
  const groupedVariants = new Map<string, VisualLocationOutput[]>()
  for (const item of locations) {
    const key = normalizeDisplayText(item.name) || '未命名场景'
    const bucket = groupedVariants.get(key) ?? []
    bucket.push(item)
    groupedVariants.set(key, bucket)
  }

  return locations.map((item, index) => {
    const refs = summarizeReferenceAssets(item.reference_assets)
    const shotIds = item.shot_ids ?? []
    const prompt = sanitizePromptDisplayText(item.zh_prompt || item.visual_prompt_zh || item.core_prompt_zh || item.description || '')
    const variantGroupKey = normalizeDisplayText(item.name) || '未命名场景'
    const siblingVariants: AssetVariantEntry[] = (groupedVariants.get(variantGroupKey) ?? [])
      .map((variant, variantIndex) => ({
        id: `location-${variant.id ?? `${variant.name}-${locations.indexOf(variant) >= 0 ? locations.indexOf(variant) : variantIndex}`}`,
        label: pickFirstDisplayValue(variant.scope_label, variant.style, variant.category, '场景版本'),
        stageName: pickFirstDisplayValue(variant.stage_name, variant.lighting_mood, variant.color_palette),
        episode: null,
        status: variant.derived_asset_status || variant.asset_status || 'draft',
        scope: String(variant.variant_scope || '').trim(),
      }))
      .sort(compareAssetVariantEntries)
    const siblingVariantCount = siblingVariants.length
    const variantScope = inferLocationVariantScope(item, siblingVariantCount)
    const variantStageName = inferLocationVariantStage(item)
    const variantLabel = pickFirstDisplayValue(
      item.scope_label,
      item.style,
      item.category,
      variantScope === 'scene_variant' ? '场景变体' : '场景版本',
    )

    return {
      id: `location-${item.id ?? `${item.name}-${index}`}`,
      category: 'location',
      assetRecordId: item.id ?? null,
      title: normalizeDisplayText(item.name) || '未命名场景',
      subtitle: pickFirstDisplayValue(item.category, item.style, '场景资产'),
      detailPrimary: pickFirstDisplayValue(item.category, item.era),
      detailSecondary: pickFirstDisplayValue(item.style, item.lighting_mood),
      detailTertiary: pickFirstDisplayValue(item.color_palette, item.description),
      status: item.derived_asset_status || item.asset_status || 'draft',
      prompt,
      shotIds,
      episodeIds: toEpisodeIds(shotIds),
      referenceCount: refs.totalCount,
      previewCount: refs.previewCount,
      selectedReferenceCount: refs.selectedReferenceCount,
      lockedReferenceCount: refs.lockedReferenceCount,
      staleReferenceCount: 0,
      hasStaleReferencePrompt: false,
      references: item.reference_assets ?? [],
      variantGroupKey,
      variantLabel,
      variantScope,
      variantStageName,
      variantEpisode: null,
      siblingVariantCount,
      siblingVariants,
    }
  })
}

export function buildPropAssetSummaries(props: VisualPropOutput[]): AssetSummary[] {
  const groupedVariants = new Map<string, VisualPropOutput[]>()
  for (const item of props) {
    const key = normalizeDisplayText(item.name) || '未命名道具'
    const bucket = groupedVariants.get(key) ?? []
    bucket.push(item)
    groupedVariants.set(key, bucket)
  }

  return props.map((item, index) => {
    const refs = summarizeReferenceAssets(item.reference_assets)
    const shotIds = item.shot_ids ?? []
    const prompt = sanitizePromptDisplayText(item.zh_prompt || item.visual_prompt_zh || item.core_prompt_zh || item.description || '')
    const variantGroupKey = normalizeDisplayText(item.name) || '未命名道具'
    const siblingVariants: AssetVariantEntry[] = (groupedVariants.get(variantGroupKey) ?? [])
      .map((variant, variantIndex) => ({
        id: `prop-${variant.id ?? `${variant.name}-${props.indexOf(variant) >= 0 ? props.indexOf(variant) : variantIndex}`}`,
        label: pickFirstDisplayValue(variant.scope_label, normalizePropVariantLabel(variant.importance, variant.category)),
        stageName: pickFirstDisplayValue(variant.stage_name, variant.associated_characters, variant.era),
        episode: null,
        status: variant.derived_asset_status || variant.asset_status || 'draft',
        scope: String(variant.variant_scope || '').trim(),
      }))
      .sort(compareAssetVariantEntries)
    const siblingVariantCount = siblingVariants.length
    const variantScope = inferPropVariantScope(item, siblingVariantCount)
    const variantStageName = inferPropVariantStage(item)
    const variantLabel = pickFirstDisplayValue(
      item.scope_label,
      normalizePropVariantLabel(item.importance, item.category),
    )

    return {
      id: `prop-${item.id ?? `${item.name}-${index}`}`,
      category: 'prop',
      assetRecordId: item.id ?? null,
      title: normalizeDisplayText(item.name) || '未命名道具',
      subtitle: pickFirstDisplayValue(item.category, normalizePropVariantLabel(item.importance, item.category), '道具资产'),
      detailPrimary: pickFirstDisplayValue(item.category, normalizePropVariantLabel(item.importance, item.category)),
      detailSecondary: pickFirstDisplayValue(item.associated_characters, item.era),
      detailTertiary: pickFirstDisplayValue(item.description),
      status: item.derived_asset_status || item.asset_status || 'draft',
      prompt,
      shotIds,
      episodeIds: toEpisodeIds(shotIds),
      referenceCount: refs.totalCount,
      previewCount: refs.previewCount,
      selectedReferenceCount: refs.selectedReferenceCount,
      lockedReferenceCount: refs.lockedReferenceCount,
      staleReferenceCount: 0,
      hasStaleReferencePrompt: false,
      references: item.reference_assets ?? [],
      variantGroupKey,
      variantLabel,
      variantScope,
      variantStageName,
      variantEpisode: null,
      siblingVariantCount,
      siblingVariants,
    }
  })
}
