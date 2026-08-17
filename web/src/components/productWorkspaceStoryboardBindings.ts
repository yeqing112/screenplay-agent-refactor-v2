import type { StoryboardShotOutput } from '../prototyping/sceneComposerData'

export type ShotBindingSummary = {
  key: string
  title: string
  detail: string
  token: string
  status: string
  actionableMissingReference?: boolean
  assetId?: string
  masterLabel?: string
  variantLabel?: string
  referenceSourceLabel?: string
  scopeLabel?: string
  bindingSourceLabel?: string
  bindingSourceDetail?: string
}

type CharacterBindingRecord = NonNullable<
  NonNullable<NonNullable<StoryboardShotOutput['prompt_compile_context']>['asset_bindings']>['characters']
>[number]
type CharacterVariantRecord = NonNullable<
  NonNullable<StoryboardShotOutput['prompt_compile_context']>['character_variants']
>[number]
type MakeupPromptRecord = NonNullable<StoryboardShotOutput['makeup_prompts']>[number]
type ReferenceImageRecord = NonNullable<StoryboardShotOutput['reference_images']>[number]

export function normalizeReferenceAssetType(assetType: string | undefined) {
  const normalized = String(assetType || '').trim().toLowerCase()
  if (normalized === 'location') return 'scene'
  return normalized
}

export function getReferenceStatusLabel(status: string | undefined) {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'locked') return '\u5df2\u9501\u5b9a'
  if (normalized === 'selected') return '\u9ed8\u8ba4\u53c2\u8003'
  if (normalized === 'candidate') return '\u5019\u9009\u53c2\u8003'
  if (normalized === 'rejected') return '\u5df2\u6dd8\u6c70'
  if (normalized === 'missing') return '\u7f3a\u53c2\u8003\u56fe'
  return normalized ? status || '' : '\u672a\u6807\u8bb0'
}

export function getCharacterReferenceSourceLabel(referenceSource: string | undefined, variantScope?: string) {
  const source = String(referenceSource || '').trim().toLowerCase()
  const scope = String(variantScope || '').trim().toLowerCase()

  if (source === 'active_variant') {
    if (scope === 'base_identity') return '\u57fa\u7840\u5b9a\u5986'
    if (scope === 'episode_default') return '\u5f53\u524d\u5206\u96c6\u9ed8\u8ba4\u5b9a\u5986'
    return '\u5f53\u524d\u7cbe\u8c03\u5b9a\u5986'
  }
  if (source === 'resolved_makeup') {
    if (scope === 'base_identity') return '\u57fa\u7840\u5b9a\u5986'
    if (scope === 'episode_default') return '\u5f53\u524d\u5206\u96c6\u9ed8\u8ba4\u5b9a\u5986'
    if (scope === 'shot_variant') return '\u955c\u5934\u7cbe\u8c03\u5b9a\u5986'
    return '\u5df2\u89e3\u6790\u5b9a\u5986'
  }
  if (source === 'base_identity') return '\u57fa\u7840\u5b9a\u5986\u56de\u9000'
  if (source === 'missing') return '\u672a\u7ed1\u5b9a\u53c2\u8003\u56fe'
  return source ? referenceSource || '' : '\u5f85\u8865\u5b9a\u5986\u94fe\u8def'
}

function normalizeStructuredIds(ids: string[] | undefined) {
  return new Set((ids ?? []).map((item) => String(item || '').trim()).filter(Boolean))
}

function buildCharacterBindingSourceSummary(input: {
  bindingAssetId: string
  structuredCharacterIds: string[]
  referenceSource: string
  resolvedVariantScope: string
  usedPromptFallback: boolean
  hasReference: boolean
}) {
  const structuredCharacterIds = normalizeStructuredIds(input.structuredCharacterIds)
  const referenceSource = input.referenceSource.trim().toLowerCase()
  const variantScope = input.resolvedVariantScope.trim().toLowerCase()

  if (input.bindingAssetId && structuredCharacterIds.has(input.bindingAssetId)) {
    return {
      label: '正式结构化绑定',
      detail:
        variantScope === 'shot_variant'
          ? '当前人物来自镜头结构化绑定，且命中了镜头级人物变体。'
          : '当前人物来自镜头结构化绑定，可作为提示词编译与回溯的正式资产关系。',
    }
  }

  if (referenceSource === 'active_variant' || referenceSource === 'resolved_makeup') {
    return {
      label: '编译期变体命中',
      detail: '当前人物没有命中正式结构化绑定，编译阶段按人物变体解析规则补入了该资产。',
    }
  }

  if (referenceSource === 'base_identity') {
    return {
      label: '基础定妆回退',
      detail: '当前镜头缺少更高优先级的人物变体，编译阶段回退到了基础定妆。',
    }
  }

  if (input.usedPromptFallback) {
    return {
      label: '旧链路回填',
      detail: input.hasReference
        ? '当前人物摘要来自旧定妆 prompt 链路回填，仍建议补成正式结构化绑定。'
        : '当前人物摘要仅来自旧定妆 prompt 链路，尚未形成正式结构化绑定。',
    }
  }

  return {
    label: '待确认绑定',
    detail: '当前人物资产来源尚未完全结构化，建议回资产中心或镜头结构化绑定继续收敛。',
  }
}

function isInternalVariantKey(value: string) {
  const normalized = value.trim().toLowerCase()
  if (!normalized) return false
  return normalized === 'base_identity' || /^episode_\d+_default$/.test(normalized) || normalized.startsWith('shot_')
}

function normalizeScopeLabel(scopeLabel: string, variantScope: string) {
  const trimmed = scopeLabel.trim()
  const normalizedScope = variantScope.trim().toLowerCase()
  if (normalizedScope === 'base_identity') return '\u57fa\u7840\u5b9a\u5986'
  if (normalizedScope === 'episode_default') return '\u5206\u96c6\u9ed8\u8ba4'
  if (normalizedScope === 'shot_variant') return '\u5206\u955c\u7cbe\u8c03'
  return trimmed
}

function deriveVariantLabel(stageName: string, variantName: string, scopeLabel: string, variantScope: string) {
  if (variantName && !isInternalVariantKey(variantName)) return variantName

  const normalizedStage = stageName.trim().toLowerCase()
  const normalizedScope = variantScope.trim().toLowerCase()

  if (normalizedStage === 'base_identity' || normalizedScope === 'base_identity') return '\u57fa\u7840\u5b9a\u5986'

  const episodeMatch = normalizedStage.match(/^episode_(\d+)_default$/)
  if (episodeMatch) return `\u7b2c${episodeMatch[1]}\u96c6\u9ed8\u8ba4\u9020\u578b`

  if (normalizedScope === 'shot_variant' || normalizedStage.startsWith('shot_')) return '\u955c\u5934\u7cbe\u8c03\u9020\u578b'

  if (scopeLabel) return normalizeScopeLabel(scopeLabel, variantScope)
  return stageName || '\u9ed8\u8ba4\u9020\u578b'
}

export function getBindingVariantTypeLabel(variantScope: string | undefined, fallbackScopeLabel?: string) {
  const normalizedScope = String(variantScope || '').trim().toLowerCase()
  if (normalizedScope === 'base_identity') return '\u57fa\u7840\u5b9a\u5986'
  if (normalizedScope === 'episode_default') return '\u5206\u96c6\u9ed8\u8ba4'
  if (normalizedScope === 'shot_variant') return '\u5206\u955c\u7cbe\u8c03'
  if (normalizedScope === 'scene_variant') return '\u573a\u666f\u53d8\u4f53'
  if (normalizedScope === 'prop_variant') return '\u9053\u5177\u53d8\u4f53'
  return String(fallbackScopeLabel || '').trim() || '\u5f53\u524d\u7248\u672c'
}

function buildCharacterLookupKey(characterName: string, stageName: string) {
  return `${characterName.trim().toLowerCase()}::${stageName.trim().toLowerCase()}`
}

function resolveCharacterReference(references: ReferenceImageRecord[], characterName: string, assetId: string) {
  const normalizedName = characterName.trim().toLowerCase()
  const normalizedAssetId = assetId.trim()

  return references.find((item) => {
    const referenceName = String(item.asset_name || '').trim().toLowerCase()
    const referenceAssetId = String(item.asset_id || '').trim()
    const referenceToken = String(item.reference_token || '').trim().toLowerCase()

    if (normalizedAssetId && referenceAssetId === normalizedAssetId) return true
    if (normalizedName && referenceName === normalizedName) return true
    if (normalizedName && referenceToken === `@${normalizedName}`) return true
    return false
  })
}

function toVariantRecord(variant: CharacterVariantRecord | undefined) {
  return (variant ?? null) as unknown as Record<string, unknown> | null
}

export function buildCharacterBindingSummaries(shot: StoryboardShotOutput | null): ShotBindingSummary[] {
  if (!shot) return []

  const characterBindings = shot.prompt_compile_context?.asset_bindings?.characters ?? []
  const characterReferences = (shot.reference_images ?? []).filter(
    (item) => normalizeReferenceAssetType(item.asset_type) === 'character',
  )
  const compiledVariants = shot.prompt_compile_context?.character_variants ?? []
  const makeupPrompts = shot.makeup_prompts ?? []

  const promptByKey = new Map<string, MakeupPromptRecord>()
  const variantByKey = new Map<string, CharacterVariantRecord>()

  for (const prompt of makeupPrompts) {
    const key = buildCharacterLookupKey(String(prompt.character_name || ''), String(prompt.stage_name || ''))
    promptByKey.set(key, prompt)
  }

  for (const variant of compiledVariants) {
    const record = toVariantRecord(variant)
    const characterName = String(record?.character_name || record?.asset_name || '')
    const stageName = String(record?.stage_name || '')
    const key = buildCharacterLookupKey(characterName, stageName)
    variantByKey.set(key, variant)
  }

  const sourceBindings: CharacterBindingRecord[] =
    characterBindings.length > 0
      ? characterBindings
      : makeupPrompts.map((prompt) => ({
          asset_id: String(prompt.id || ''),
          asset_name: prompt.character_name,
          stage_name: prompt.stage_name,
          variant_scope: prompt.makeup_scope,
          variant_name: '',
          scope_label: prompt.scope_label,
          reference_source: prompt.makeup_scope === 'base_identity' ? 'base_identity' : 'missing',
        }))

  const structuredCharacterIds = shot.structured_shot?.character_asset_ids ?? []
  const usingFallbackBindings = characterBindings.length === 0

  return sourceBindings.map((binding, index) => {
    const characterName = String(binding.asset_name || '').trim()
    const stageName = String(binding.stage_name || '').trim()
    const variantScope = String(binding.variant_scope || '').trim()
    const lookupKey = buildCharacterLookupKey(characterName, stageName)
    const matchedPrompt = promptByKey.get(lookupKey)
    const matchedVariant = toVariantRecord(variantByKey.get(lookupKey))
    const reference = resolveCharacterReference(
      characterReferences,
      characterName || String(matchedPrompt?.character_name || ''),
      String(binding.asset_id || ''),
    )

    const title =
      characterName ||
      String(matchedVariant?.character_name || matchedPrompt?.character_name || '') ||
      '\u672a\u547d\u540d\u4eba\u7269'
    const resolvedVariantScope = variantScope || String(matchedPrompt?.makeup_scope || matchedVariant?.makeup_scope || '')
    const variantLabel = deriveVariantLabel(
      stageName || String(matchedVariant?.stage_name || matchedPrompt?.stage_name || ''),
      String(binding.variant_name || ''),
      String(binding.scope_label || matchedPrompt?.scope_label || matchedVariant?.scope_label || ''),
      resolvedVariantScope,
    )
    const rawScopeLabel = String(binding.scope_label || matchedPrompt?.scope_label || matchedVariant?.scope_label || '').trim()
    const scopeLabel = normalizeScopeLabel(rawScopeLabel, resolvedVariantScope)
    const referenceSource = getCharacterReferenceSourceLabel(
      String(binding.reference_source || matchedVariant?.reference_source || ''),
      resolvedVariantScope,
    )
    const bindingAssetId = String(binding.asset_id || '').trim()
    const bindingSource = buildCharacterBindingSourceSummary({
      bindingAssetId,
      structuredCharacterIds,
      referenceSource: String(binding.reference_source || matchedVariant?.reference_source || ''),
      resolvedVariantScope,
      usedPromptFallback: usingFallbackBindings,
      hasReference: Boolean(reference),
    })

    const detailParts = [variantLabel]
    if (scopeLabel && scopeLabel !== variantLabel) detailParts.push(scopeLabel)
    if (referenceSource) detailParts.push(referenceSource)

    return {
      key: `character-${String(binding.asset_id || title || index)}`,
      title,
      detail: detailParts.join(' \u00b7 '),
      token: String(reference?.reference_token || ''),
      status: reference ? getReferenceStatusLabel(reference.reference_status) : '\u7f3a\u53c2\u8003\u56fe',
      actionableMissingReference: Boolean(reference) || !usingFallbackBindings,
      assetId: String(binding.asset_id || ''),
      masterLabel: title,
      variantLabel,
      referenceSourceLabel: referenceSource,
      scopeLabel: getBindingVariantTypeLabel(resolvedVariantScope, scopeLabel),
      bindingSourceLabel: bindingSource.label,
      bindingSourceDetail: bindingSource.detail,
    }
  })
}
