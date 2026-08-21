import type { StoryboardShotOutput } from '../domain/bookOutputs'

export interface CompilerDiagnosticMeta {
  label: string
  tone: string
  textTone: string
}

export interface PromptReferenceItem {
  key: string
  scope: string
  subject: string
  token: string
  status: string
}

export interface PromptAuthorityItem {
  key: string
  scope: 'scene' | 'character' | 'prop'
  name: string
  assetId: string
  token: string
  variantLabel: string
  referenceSourceLabel: string
  referenceStatusLabel: string
  authorityPromptExcerpt: string
  authorityPromptSource: string
}

export interface PromptAuthoritySummary {
  items: PromptAuthorityItem[]
  warningCount: number
  constraintCount: number
  noteCount: number
  failureTagCount: number
}

function normalizeText(value: unknown) {
  return String(value ?? '').trim()
}

function normalizeScopeValue(scope: string | undefined) {
  const normalized = normalizeText(scope).toLowerCase()
  if (normalized === 'location') return 'scene'
  return normalized
}

function formatEpisodeDefaultLabel(value: string) {
  const match = value.match(/^episode_(\d+)_default$/i)
  if (!match) return ''
  return `第${match[1]}集默认造型`
}

function formatShotVariantLabel(value: string) {
  const match = value.match(/^shot_(\d+)_(.+)$/i)
  if (!match) return ''
  return `镜头 ${match[1]} · ${match[2].replace(/_/g, ' ')}`
}

function isInternalStageToken(value: string) {
  const normalized = value.trim().toLowerCase()
  return Boolean(
    normalized &&
      (normalized === 'base_identity' ||
        normalized === 'episode_default' ||
        normalized === 'shot_variant' ||
        /^episode_\d+_default$/.test(normalized) ||
        /^shot_\d+_.+$/.test(normalized)),
  )
}

function sanitizeDisplayText(value: string | undefined) {
  const text = normalizeText(value)
  if (!text) return ''

  return text
    .replace(/人物集默认定妆设定板/g, '人物分集默认定妆设定板')
    .replace(/人物集默认定妆/g, '人物分集默认定妆')
    .replace(/当前集默认定妆/g, '当前分集默认定妆')
    .replace(/(^|[^分])集默认定妆/g, (_match, prefix) => `${prefix}分集默认定妆`)
    .replace(/episode_(\d+)_default/g, (_match, episode) => `第${episode}集默认造型`)
    .replace(/shot_(\d+)_([A-Za-z0-9_\u4e00-\u9fa5-]+)/g, (_match, shot, label) => {
      return `镜头 ${shot} · ${String(label).replace(/_/g, ' ')}`
    })
    .replace(/\s+/g, ' ')
    .trim()
}

function getVariantScopeLabel(variantScope: string | undefined) {
  const normalized = normalizeText(variantScope).toLowerCase()
  if (normalized === 'base_identity') return '基础定妆'
  if (normalized === 'episode_default') return '分集默认'
  if (normalized === 'shot_variant') return '分镜精调'
  if (normalized === 'scene_variant') return '场景变体'
  if (normalized === 'prop_variant') return '道具变体'
  return ''
}

function normalizeScopeLabelText(scopeLabel: string | undefined, variantScope: string | undefined) {
  const text = sanitizeDisplayText(scopeLabel)
  if (!text) return ''

  const normalizedScope = normalizeText(variantScope).toLowerCase()
  if (normalizedScope === 'base_identity') return '基础定妆'
  if (normalizedScope === 'episode_default') return '分集默认'
  if (normalizedScope === 'shot_variant') return '分镜精调'
  if (normalizedScope === 'scene_variant') return '场景变体'
  if (normalizedScope === 'prop_variant') return '道具变体'

  if (text.includes('基础定妆')) return '基础定妆'
  if (text.includes('分镜精调')) return '分镜精调'
  if (text.includes('场景变体')) return '场景变体'
  if (text.includes('道具变体')) return '道具变体'
  if (text.includes('分集默认')) return '分集默认'
  return text
}

function normalizeStageName(stageName: string | undefined, variantScope: string | undefined) {
  const stage = sanitizeDisplayText(stageName)
  if (!stage) {
    const scopeLabel = getVariantScopeLabel(variantScope)
    return scopeLabel === '基础定妆' ? '基础身份阶段' : ''
  }

  const lowered = stage.toLowerCase()
  if (lowered === 'base_identity') return '基础身份阶段'

  const episodeLabel = formatEpisodeDefaultLabel(lowered)
  if (episodeLabel) return episodeLabel

  const shotLabel = formatShotVariantLabel(stage)
  if (shotLabel) return shotLabel

  return stage
}

function getPromptVariantLabel(
  scopeLabel: string | undefined,
  variantScope: string | undefined,
  stageName: string | undefined,
) {
  const normalizedScopeLabel = normalizeScopeLabelText(scopeLabel, variantScope)
  const normalizedScope = normalizeText(variantScope).toLowerCase()
  const normalizedStage = normalizeStageName(stageName, variantScope)

  if (normalizedScopeLabel && !isInternalStageToken(normalizedScopeLabel)) {
    return normalizedStage ? `${normalizedScopeLabel} / ${normalizedStage}` : normalizedScopeLabel
  }

  if (normalizedScope === 'base_identity') return '基础定妆'
  if (normalizedScope === 'episode_default') {
    return normalizedStage ? `分集默认 / ${normalizedStage}` : '分集默认'
  }
  if (normalizedScope === 'shot_variant') {
    return normalizedStage ? `分镜精调 / ${normalizedStage}` : '分镜精调'
  }
  if (normalizedScope === 'scene_variant') {
    return normalizedStage ? `场景变体 / ${normalizedStage}` : '场景变体'
  }
  if (normalizedScope === 'prop_variant') {
    return normalizedStage ? `道具变体 / ${normalizedStage}` : '道具变体'
  }

  return normalizedStage || '未标记版本'
}

function finalizeVariantLabel(primary: string, fallback: string) {
  return primary && primary !== '未标记版本' ? primary : fallback
}

export function getPromptReferenceScopeLabel(scope: string | undefined) {
  const normalized = normalizeScopeValue(scope)
  if (normalized === 'character') return '人物'
  if (normalized === 'scene') return '场景'
  if (normalized === 'prop') return '道具'
  return '引用'
}

export function getPromptReferenceStatusLabel(status: string | undefined) {
  const normalized = normalizeText(status).toLowerCase()
  if (normalized === 'locked') return '已锁定'
  if (normalized === 'selected') return '默认参考'
  if (normalized === 'candidate') return '候选参考'
  if (normalized === 'rejected') return '已淘汰'
  if (normalized === 'missing') return '缺参考图'
  return normalized ? status || '' : '未标记'
}

function getPromptReferenceSourceLabel(source: string | undefined, variantScope?: string) {
  const normalized = normalizeText(source).toLowerCase()
  const normalizedScope = normalizeText(variantScope).toLowerCase()
  if (normalized === 'active_variant') {
    if (normalizedScope === 'base_identity') return '基础定妆'
    if (normalizedScope === 'episode_default') return '当前分集默认定妆'
    if (normalizedScope === 'shot_variant') return '当前精调定妆'
    return '当前精调版本'
  }
  if (normalized === 'resolved_makeup') {
    if (normalizedScope === 'base_identity') return '基础定妆'
    if (normalizedScope === 'episode_default') return '当前分集默认定妆'
    if (normalizedScope === 'shot_variant') return '镜头精调定妆'
    return '已解析定妆'
  }
  if (normalized === 'base_identity') return '基础定妆回退'
  if (normalized === 'selected') return '默认参考'
  if (normalized === 'locked') return '锁定参考'
  if (normalized === 'missing') return '未绑定参考图'
  return normalized ? source || '' : '未标记来源'
}

function getPromptAuthoritySourceLabel(source: string | undefined) {
  const normalized = normalizeText(source).toLowerCase()
  if (normalized === 'character_makeup') return '人物定妆权威源'
  if (normalized === 'scene_asset') return '场景资产权威源'
  if (normalized === 'prop_asset') return '道具资产权威源'
  return normalized ? source || '' : '未标记权威源'
}

function stripAuthorityExcerptKeys(text: string) {
  return text
    .split(/\n+/)
    .map((line) => line.replace(/^[a-z_]+:\s*/i, '').trim())
    .filter(Boolean)
    .join(' ')
}

function summarizeAuthorityExcerpt(text: string) {
  const segments = text
    .split(/[，,。；;：:\n\r\t（）()\[\]{}|]+/)
    .map((item) => item.trim())
    .filter(Boolean)
  if (segments.length === 0) return text
  const preview = segments.slice(0, 4).join(' / ')
  return preview.length > 88 ? `${preview.slice(0, 88)}...` : preview
}

function toAuthorityExcerpt(raw: string | undefined) {
  const text = stripAuthorityExcerptKeys(sanitizeDisplayText(raw))
  if (!text) return ''
  return summarizeAuthorityExcerpt(text)
}

export function getCompilerDiagnosticMeta(status: string | undefined): CompilerDiagnosticMeta {
  const normalized = normalizeText(status).toLowerCase()
  if (normalized === 'blocked') {
    return {
      label: '阻塞',
      tone: 'border-rose-800/80 bg-rose-950/40 text-rose-200',
      textTone: 'text-rose-300',
    }
  }
  if (normalized === 'warning') {
    return {
      label: '警告',
      tone: 'border-amber-800/80 bg-amber-950/40 text-amber-200',
      textTone: 'text-amber-300',
    }
  }
  return {
    label: normalized ? '通过' : '未诊断',
    tone: normalized
      ? 'border-emerald-800/80 bg-emerald-950/40 text-emerald-200'
      : 'border-slate-800 bg-slate-950/60 text-slate-300',
    textTone: normalized ? 'text-emerald-300' : 'text-slate-400',
  }
}

export function getPromptReferenceItems(shot: StoryboardShotOutput): PromptReferenceItem[] {
  const lockedSummary = shot.locked_reference_summary?.all
  if (Array.isArray(lockedSummary) && lockedSummary.length > 0) {
    return lockedSummary.map((item, index) => ({
      key: `${item.id ?? item.scope ?? 'ref'}-${index}`,
      scope: String(item.scope || 'reference'),
      subject: sanitizeDisplayText(String(item.subject || item.title || '未命名参考')),
      token: sanitizeDisplayText(String(item.token || '')),
      status: String(item.status || 'locked'),
    }))
  }

  const items: PromptReferenceItem[] = []

  const sceneRefs = shot.assets?.references?.scene ?? []
  const adoptedScene = sceneRefs.find((item) => item.metadata?.imageRole === 'reference') ?? sceneRefs[0]
  if (adoptedScene) {
    items.push({
      key: `scene-${adoptedScene.id}`,
      scope: 'scene',
      subject: sanitizeDisplayText(shot.scene_name || '场景'),
      token: sanitizeDisplayText(String(adoptedScene.sourceAssetId || adoptedScene.label || '')),
      status: String(adoptedScene.status || 'selected'),
    })
  }

  for (const [subject, refs] of Object.entries(shot.assets?.references?.characters ?? {})) {
    const active = refs[0]
    if (!active) continue
    items.push({
      key: `character-${subject}-${active.id}`,
      scope: 'character',
      subject: sanitizeDisplayText(subject),
      token: sanitizeDisplayText(String(active.sourceAssetId || active.label || '')),
      status: String(active.status || 'selected'),
    })
  }

  for (const [subject, refs] of Object.entries(shot.assets?.references?.props ?? {})) {
    const active = refs[0]
    if (!active) continue
    items.push({
      key: `prop-${subject}-${active.id}`,
      scope: 'prop',
      subject: sanitizeDisplayText(subject),
      token: sanitizeDisplayText(String(active.sourceAssetId || active.label || '')),
      status: String(active.status || 'selected'),
    })
  }

  return items
}

export function buildPromptAuthoritySummary(shot: StoryboardShotOutput): PromptAuthoritySummary {
  const assetBindings = shot.prompt_compile_context?.asset_bindings
  const items: PromptAuthorityItem[] = []

  const scene = assetBindings?.scene
  if (scene && (scene.asset_name || scene.asset_id || shot.scene_name)) {
    const sceneVariantLabel = finalizeVariantLabel(
      getPromptVariantLabel(scene.scope_label, scene.variant_scope, scene.stage_name),
      sanitizeDisplayText(String(scene.stage_name || scene.scope_label || '')) || '当前场景绑定',
    )

    items.push({
      key: `scene-${String(scene.asset_id || shot.scene_name || 'scene')}`,
      scope: 'scene',
      name: sanitizeDisplayText(String(scene.asset_name || shot.scene_name || '未命名场景')),
      assetId: String(scene.asset_id || ''),
      token: sanitizeDisplayText(String(scene.reference_token || '')),
      variantLabel: sceneVariantLabel,
      referenceSourceLabel: getPromptReferenceSourceLabel(scene.reference_source || scene.reference_status),
      referenceStatusLabel: getPromptReferenceStatusLabel(scene.reference_status),
      authorityPromptExcerpt: toAuthorityExcerpt(scene.authority_prompt_raw),
      authorityPromptSource: getPromptAuthoritySourceLabel(scene.authority_prompt_source),
    })
  }

  for (const character of assetBindings?.characters ?? []) {
    items.push({
      key: `character-${String(character.asset_id || character.asset_name || items.length)}`,
      scope: 'character',
      name: sanitizeDisplayText(String(character.asset_name || '未命名人物')),
      assetId: String(character.asset_id || ''),
      token: sanitizeDisplayText(String(character.reference_token || '')),
      variantLabel: getPromptVariantLabel(character.scope_label, character.variant_scope, character.stage_name),
      referenceSourceLabel: getPromptReferenceSourceLabel(character.reference_source, character.variant_scope),
      referenceStatusLabel: getPromptReferenceStatusLabel(character.reference_status),
      authorityPromptExcerpt: toAuthorityExcerpt(character.authority_prompt_raw),
      authorityPromptSource: getPromptAuthoritySourceLabel(character.authority_prompt_source),
    })
  }

  for (const prop of assetBindings?.props ?? []) {
    const propRecord = prop as Record<string, unknown>
    const propVariantLabel = finalizeVariantLabel(
      getPromptVariantLabel(
        String(propRecord.scope_label || ''),
        String(propRecord.variant_scope || ''),
        String(propRecord.stage_name || '当前道具绑定'),
      ),
      '当前道具绑定',
    )

    items.push({
      key: `prop-${String(prop.asset_id || prop.asset_name || items.length)}`,
      scope: 'prop',
      name: sanitizeDisplayText(String(prop.asset_name || '未命名道具')),
      assetId: String(prop.asset_id || ''),
      token: sanitizeDisplayText(String(prop.reference_token || '')),
      variantLabel: propVariantLabel,
      referenceSourceLabel: getPromptReferenceSourceLabel(prop.reference_source || prop.reference_status),
      referenceStatusLabel: getPromptReferenceStatusLabel(prop.reference_status),
      authorityPromptExcerpt: toAuthorityExcerpt(prop.authority_prompt_raw),
      authorityPromptSource: getPromptAuthoritySourceLabel(prop.authority_prompt_source),
    })
  }

  const acceptance = shot.prompt_compile_context?.acceptance_feedback
  return {
    items,
    warningCount: shot.prompt_compile_context?.warnings?.length ?? 0,
    constraintCount: acceptance?.constraints?.length ?? 0,
    noteCount: acceptance?.notes?.length ?? 0,
    failureTagCount: acceptance?.failure_tags?.length ?? 0,
  }
}

export function getReferencePreviewUrl(reference: {
  image_url?: string
  local_path?: string
}): string {
  return String(reference.image_url || reference.local_path || '').trim()
}
