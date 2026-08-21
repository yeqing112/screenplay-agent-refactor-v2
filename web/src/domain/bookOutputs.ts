export type VersionKind = 'image' | 'video' | 'audio'
export type MetadataValue = string | number | boolean | string[] | undefined

export type GeneratedImageOutput = {
  id: string
  shotId: string
  prompt: string
  imageUrl: string
  createdAt: string
}

export interface MediaAssetOutput {
  id: string
  kind: VersionKind
  title: string
  label: string
  uri?: string
  previewUrl?: string
  prompt?: string
  model?: string
  status?: string
  adopted?: boolean
  sourceAssetId?: string
  metadata?: Record<string, MetadataValue>
}

export interface VisualReferenceAssetOutput {
  id: number
  book_id?: number
  episode?: number
  asset_type: string
  asset_id: string
  asset_name?: string
  image_url?: string
  local_path?: string
  reference_token?: string
  status?: string
  prompt?: string
  model?: string
  notes?: string
  meta_info?: Record<string, MetadataValue>
  created_at?: string | null
  updated_at?: string | null
}

export interface ReferenceAssetCollections {
  characters: Record<string, MediaAssetOutput[]>
  scene: MediaAssetOutput[]
  props: Record<string, MediaAssetOutput[]>
}

export interface ScriptOutput {
  id?: number
  episode: number
  content: string
  status?: string
}

export interface StoryboardShotOutput {
  episode?: number
  shot_id: string
  scene_name: string
  dialogue?: string
  duration?: number
  camera_angle?: string
  camera_movement?: string
  transition?: string
  lighting?: string
  sound_effects?: string[]
  bgm_mood?: string
  start_state?: string
  action_process?: string
  end_state?: string
  visual_prompt_static?: string
  visual_prompt_motion?: string
  visual_prompt_final?: string
  negative_prompt?: string
  prompt_version?: number | null
  prompt_locked?: boolean
  compiler_warnings?: string[]
  compiler_diagnostics?: {
    status?: string
    warnings?: string[]
    blocking_issues?: string[]
    checks?: Array<{ key?: string; label?: string; passed?: boolean; message?: string; details?: string[] }>
    metrics?: Record<string, unknown>
  }
  prompt_version_audit?: {
    recoverable_version_count?: number
    missing_critical_count?: number
    missing_critical_assets?: string[]
    missing_used_asset_names?: string[]
    is_scene_only_candidate?: boolean
    is_recoverable_version?: boolean
    is_degraded_version?: boolean
  }
  recommended_restore_version?: {
    id?: string | number
    version?: string | number
    reason?: string
  }
  repair_attempted?: boolean
  used_assets?: Array<{
    asset_id?: string
    asset_name?: string
    asset_type?: string
    reference_mode?: string
  }>
  locked_reference_summary?: {
    all?: Array<{
      id?: string | number
      scope?: string
      subject?: string
      title?: string
      token?: string
      status?: string
    }>
  }
  reference_images?: Array<{
    reference_asset_id?: string
    asset_type?: string
    asset_id?: string
    asset_name?: string
    reference_token?: string
    reference_status?: string
    image_url?: string
    local_path?: string
  }>
  prompt_compile_context?: {
    reference_asset_ids?: string[]
    compiled_reference_asset_ids?: string[]
    compile_prompt_contract?: {
      summary_lines?: string[]
      visual_fact_targets?: Array<{
        asset_type?: string
        asset_id?: string
        asset_name?: string
        reference_token?: string
        required_facts?: string[]
        min_facts_to_include?: number
        requires_used_asset?: boolean
      }>
      required_used_assets?: Array<{
        asset_type?: string
        asset_id?: string
        asset_name?: string
        reference_token?: string
        reference_status?: string
      }>
    }
    visual_fact_targets?: Array<{
      asset_type?: string
      asset_id?: string
      asset_name?: string
      reference_token?: string
      required_facts?: string[]
      min_facts_to_include?: number
      requires_used_asset?: boolean
    }>
    required_used_assets?: Array<{
      asset_type?: string
      asset_id?: string
      asset_name?: string
      reference_token?: string
      reference_status?: string
    }>
    compiled_reference_images?: Array<{
      reference_asset_id?: string
      asset_type?: string
      asset_id?: string
      asset_name?: string
      reference_token?: string
      reference_status?: string
      image_url?: string
      local_path?: string
    }>
    character_variants?: VisualMakeupOutput[]
    asset_bindings?: {
      scene?: {
        asset_id?: string
        asset_name?: string
        reference_asset_id?: string
        reference_token?: string
        image_url?: string
        reference_status?: string
        reference_source?: string
        has_reference?: boolean
        locked_reference?: boolean
        variant_scope?: string
        scope_label?: string
        stage_name?: string
        authority_prompt_raw?: string
        authority_prompt_source?: string
        authority_prompt_parts?: Array<{ key?: string; text?: string }>
      }
      characters?: Array<{
        asset_id?: string
        asset_name?: string
        reference_asset_id?: string
        reference_token?: string
        image_url?: string
        reference_status?: string
        has_reference?: boolean
        locked_reference?: boolean
        stage_name?: string
        variant_scope?: string
        variant_name?: string
        scope_label?: string
        reference_source?: string
        authority_prompt_raw?: string
        authority_prompt_source?: string
        authority_prompt_parts?: Array<{ key?: string; text?: string }>
      }>
      props?: Array<{
        asset_id?: string
        asset_name?: string
        reference_asset_id?: string
        reference_token?: string
        image_url?: string
        reference_status?: string
        reference_source?: string
        has_reference?: boolean
        locked_reference?: boolean
        variant_scope?: string
        scope_label?: string
        stage_name?: string
        authority_prompt_raw?: string
        authority_prompt_source?: string
        authority_prompt_parts?: Array<{ key?: string; text?: string }>
      }>
    }
    acceptance_feedback?: {
      failure_tags?: string[]
      notes?: string[]
      constraints?: string[]
    }
    warnings?: string[]
  }
  acceptance?: {
    status?: string
    asset_kind?: string
    asset_id?: string
    failure_tags?: string[]
    notes?: string
    updated_at?: string
  }
  asset_status?: string
  asset_links?: unknown
  meta_info?: unknown
  structured_shot?: {
    scene_asset_id?: string
    character_asset_ids?: string[]
    prop_asset_ids?: string[]
    style_key?: string
    character_blocking?: Array<Record<string, unknown>>
    action_beats?: Array<Record<string, unknown>>
  }
  scene_prompt?: string
  makeup_prompts?: Array<{
    id?: number
    character_name: string
    stage_name?: string
    makeup_scope?: string
    scope_label?: string
    refined_outfit?: string
    refined_accessories?: string
    makeup_spec?: string
    hair_style?: string
    visual_prompt_zh?: string
    core_prompt_zh?: string
    scene_prompt_zh?: string
    consistency_notes?: string
    shot_ids?: string[]
    resolution_reason?: string
  }>
  assets?: {
    images: MediaAssetOutput[]
    videos: MediaAssetOutput[]
    audios: MediaAssetOutput[]
    references?: ReferenceAssetCollections
  }
}

export interface VisualLocationOutput {
  id?: number
  name: string
  category?: string
  style?: string
  description?: string
  color_palette?: string
  lighting_mood?: string
  visual_prompt_zh?: string
  core_prompt_zh?: string
  zh_prompt?: string
  era?: string
  jimeng_ref_name?: string
  negative_prompt?: string
  asset_status?: string
  derived_asset_status?: string
  stage_name?: string
  variant_scope?: string
  scope_label?: string
  reference_assets?: VisualReferenceAssetOutput[]
  shot_ids?: string[]
}

export interface VisualPropOutput {
  id?: number
  name: string
  category?: string
  importance?: string
  era?: string
  description?: string
  associated_characters?: string
  visual_prompt_zh?: string
  core_prompt_zh?: string
  zh_prompt?: string
  jimeng_ref_name?: string
  negative_prompt?: string
  asset_status?: string
  derived_asset_status?: string
  stage_name?: string
  variant_scope?: string
  scope_label?: string
  reference_assets?: VisualReferenceAssetOutput[]
  shot_ids?: string[]
}

export interface VisualMakeupOutput {
  id?: number
  episode: number
  character_name: string
  stage_name?: string
  makeup_scope?: string
  scope_label?: string
  record_source?: string
  is_readonly?: boolean
  gender?: string
  identity?: string
  temperament?: string
  appearance?: string
  refined_outfit?: string
  refined_accessories?: string
  makeup_spec?: string
  hair_style?: string
  expression_mood?: string
  visual_prompt_zh?: string
  core_prompt_zh?: string
  outfit_prompt_zh?: string
  scene_prompt_zh?: string
  consistency_notes?: string
  meta_info?: Record<string, MetadataValue>
  jimeng_ref_name?: string
  negative_prompt?: string
  asset_status?: string
  derived_asset_status?: string
  reference_assets?: VisualReferenceAssetOutput[]
  shot_ids?: string[]
}

export interface OutputsData {
  bible: string
  scripts: ScriptOutput[]
  storyboard: {
    episodeShots: Record<number, StoryboardShotOutput[]>
  }
  visual: {
    era?: Record<string, string> | null
    locations: VisualLocationOutput[]
    props: VisualPropOutput[]
    makeups: VisualMakeupOutput[]
  }
  qa: Array<{
    id?: number
    episode: number
    result: unknown
    error_count?: number
  }>
  generatedImages: GeneratedImageOutput[]
}

export interface BookOutputsResponse {
  bible?: string
  portrait?: string
  scripts?: Array<{
    id?: number
    episode: number
    content?: string
    status?: string
  }>
  storyboard?:
    | Array<Omit<StoryboardShotOutput, 'shot_id' | 'assets'> & { shot_id: string | number }>
    | Record<string, Omit<StoryboardShotOutput, 'shot_id' | 'assets'> & { shot_id: string | number }>
  visual?: {
    era?: Record<string, string> | null
    locations?: Array<Omit<VisualLocationOutput, 'shot_ids'> & { shot_ids?: Array<string | number> }>
    props?: Array<Omit<VisualPropOutput, 'shot_ids'> & { shot_ids?: Array<string | number> }>
    makeups?: Array<Omit<VisualMakeupOutput, 'shot_ids'> & { shot_ids?: Array<string | number> }>
  }
  qa?: Array<{
    id?: number
    episode: number
    result: unknown
    error_count?: number
  }>
}

export const MOCK_OUTPUTS_DATA: OutputsData = createEmptyOutputsData()

export function createEmptyOutputsData(): OutputsData {
  return {
    bible: '',
    scripts: [],
    storyboard: {
      episodeShots: {},
    },
    visual: {
      era: null,
      locations: [],
      props: [],
      makeups: [],
    },
    qa: [],
    generatedImages: [],
  }
}

export function toDisplayText(value: unknown, fallback = ''): string {
  if (typeof value !== 'string') {
    return fallback
  }

  const text = value.trim()
  if (!text) {
    return fallback
  }

  return looksCorruptedText(text) ? fallback || text : text
}

export function normalizeBookOutputs(response: BookOutputsResponse): OutputsData {
  const storyboardItems = normalizeStoryboardItems(response.storyboard)
  const groupedShots = storyboardItems.reduce<Record<number, StoryboardShotOutput[]>>((acc, shot) => {
    const episode = shot.episode ?? 1
    if (!acc[episode]) {
      acc[episode] = []
    }
    acc[episode].push({
      ...shot,
      shot_id: String(shot.shot_id),
      sound_effects: shot.sound_effects ?? [],
      makeup_prompts: shot.makeup_prompts ?? [],
      assets: normalizeShotAssets(String(shot.shot_id), shot.asset_links),
    })
    return acc
  }, {})

  for (const episode of Object.keys(groupedShots)) {
    groupedShots[Number(episode)] = groupedShots[Number(episode)].sort((left, right) =>
      compareShotIds(left.shot_id, right.shot_id),
    )
  }

  const scripts = (response.scripts ?? [])
    .map((script) => ({
      id: script.id,
      episode: script.episode,
      content: script.content ?? '',
      status: script.status,
    }))
    .sort((left, right) => left.episode - right.episode)

  const locations = (response.visual?.locations ?? []).map((location) => ({
    ...location,
    description: location.description ?? '',
    zh_prompt: location.zh_prompt ?? location.visual_prompt_zh ?? location.core_prompt_zh ?? '',
    jimeng_ref_name: location.jimeng_ref_name ?? '',
    negative_prompt: location.negative_prompt ?? '',
    asset_status: location.asset_status ?? 'draft',
    reference_assets: location.reference_assets ?? [],
    shot_ids: dedupeStrings(location.shot_ids ?? []),
  }))

  const props = (response.visual?.props ?? []).map((prop) => ({
    ...prop,
    description: prop.description ?? '',
    importance: prop.importance ?? 'medium',
    zh_prompt: prop.zh_prompt ?? prop.visual_prompt_zh ?? prop.core_prompt_zh ?? '',
    jimeng_ref_name: prop.jimeng_ref_name ?? '',
    negative_prompt: prop.negative_prompt ?? '',
    asset_status: prop.asset_status ?? 'draft',
    reference_assets: prop.reference_assets ?? [],
    shot_ids: dedupeStrings(prop.shot_ids ?? []),
  }))

  const makeups = (response.visual?.makeups ?? []).map((makeup) => ({
    ...makeup,
    identity: makeup.identity ?? '',
    temperament: makeup.temperament ?? makeup.expression_mood ?? '',
    appearance: makeup.appearance ?? '',
    jimeng_ref_name: makeup.jimeng_ref_name ?? '',
    negative_prompt: makeup.negative_prompt ?? '',
    asset_status: makeup.asset_status ?? 'draft',
    reference_assets: makeup.reference_assets ?? [],
    shot_ids: dedupeStrings(makeup.shot_ids ?? []),
  }))

  return {
    ...createEmptyOutputsData(),
    bible: response.bible ?? '',
    scripts,
    storyboard: {
      episodeShots: groupedShots,
    },
    visual: {
      era: response.visual?.era ?? null,
      locations,
      props,
      makeups,
    },
    qa: response.qa ?? [],
  }
}

function normalizeStoryboardItems(
  storyboard: BookOutputsResponse['storyboard'],
): Array<Omit<StoryboardShotOutput, 'shot_id' | 'assets'> & { shot_id: string | number }> {
  if (!storyboard) return []
  if (Array.isArray(storyboard)) return storyboard
  return Object.values(storyboard).filter((item) => Boolean(item && typeof item === 'object'))
}

function dedupeStrings(values: Array<string | number>) {
  return Array.from(new Set(values.filter((value) => value !== undefined && value !== null && value !== '').map(String)))
}

function compareShotIds(left: string | number, right: string | number) {
  const leftParts = tokenizeShotId(left)
  const rightParts = tokenizeShotId(right)
  const maxLength = Math.max(leftParts.length, rightParts.length)

  for (let index = 0; index < maxLength; index += 1) {
    const leftPart = leftParts[index]
    const rightPart = rightParts[index]

    if (leftPart === undefined) return -1
    if (rightPart === undefined) return 1

    if (typeof leftPart === 'number' && typeof rightPart === 'number') {
      if (leftPart !== rightPart) {
        return leftPart - rightPart
      }
      continue
    }

    const leftText = String(leftPart)
    const rightText = String(rightPart)
    if (leftText !== rightText) {
      return leftText.localeCompare(rightText, 'zh-Hans-CN')
    }
  }

  return String(left).localeCompare(String(right), 'zh-Hans-CN')
}

function tokenizeShotId(value: string | number): Array<number | string> {
  return String(value)
    .split(/[^0-9A-Za-z\u4e00-\u9fa5]+/)
    .filter(Boolean)
    .map((part) => (/^\d+$/.test(part) ? Number(part) : part))
}

function normalizeShotAssets(shotId: string, assetLinks: unknown) {
  const root = parseJsonLike(assetLinks)
  return {
    images: normalizeAssetGroup('image', shotId, root, ['image', 'images', 'storyboard', 'storyboards', 'frames']),
    videos: normalizeAssetGroup('video', shotId, root, ['video', 'videos', 'clips', 'motions']),
    audios: normalizeAssetGroup('audio', shotId, root, ['audio', 'audios', 'voices', 'voice', 'music', 'bgm', 'sound']),
    references: normalizeReferenceAssets(shotId, root),
  }
}

function normalizeReferenceAssets(shotId: string, root: unknown): ReferenceAssetCollections {
  const referencesRoot = root && typeof root === 'object' ? parseJsonLike((root as Record<string, unknown>).references) : null
  const charactersRoot = referencesRoot && typeof referencesRoot === 'object'
    ? parseJsonLike((referencesRoot as Record<string, unknown>).characters)
    : null
  const sceneRoot = referencesRoot && typeof referencesRoot === 'object'
    ? parseJsonLike((referencesRoot as Record<string, unknown>).scene)
    : null
  const propsRoot = referencesRoot && typeof referencesRoot === 'object'
    ? parseJsonLike((referencesRoot as Record<string, unknown>).props)
    : null

  const characters = charactersRoot && typeof charactersRoot === 'object'
    ? Object.fromEntries(
        Object.entries(charactersRoot as Record<string, unknown>).map(([subject, value]) => [
          subject,
          normalizeReferenceAssetEntries(shotId, 'character', subject, value),
        ]),
      )
    : {}

  const scene = normalizeReferenceAssetEntries(shotId, 'location', 'scene', sceneRoot)

  const props = propsRoot && typeof propsRoot === 'object'
    ? Object.fromEntries(
        Object.entries(propsRoot as Record<string, unknown>).map(([subject, value]) => [
          subject,
          normalizeReferenceAssetEntries(shotId, 'prop', subject, value),
        ]),
      )
    : {}

  return { characters, scene, props }
}

function normalizeReferenceAssetEntries(
  shotId: string,
  scope: 'character' | 'location' | 'prop',
  subject: string,
  value: unknown,
) {
  return expandAssetEntries(value)
    .map((entry, index) => normalizeReferenceAssetEntry(shotId, scope, subject, entry, index))
    .filter((entry): entry is MediaAssetOutput => entry !== null)
}

function normalizeReferenceAssetEntry(
  shotId: string,
  scope: 'character' | 'location' | 'prop',
  subject: string,
  entry: unknown,
  index: number,
): MediaAssetOutput | null {
  const asset = normalizeAssetEntry('image', shotId, entry, index)
  if (!asset) {
    return null
  }

  return {
    ...asset,
    metadata: compactMetadata({
      ...(asset.metadata ?? {}),
      source: 'real',
      imageRole: 'reference',
      assetScope: scope,
      assetSubject: subject,
    }),
  }
}

function normalizeAssetGroup(
  kind: VersionKind,
  shotId: string,
  root: unknown,
  candidateKeys: string[],
): MediaAssetOutput[] {
  const rawEntries = pickAssetEntries(root, candidateKeys)
  return rawEntries
    .map((entry, index) => normalizeAssetEntry(kind, shotId, entry, index))
    .filter((entry): entry is MediaAssetOutput => entry !== null)
}

function pickAssetEntries(root: unknown, candidateKeys: string[]): unknown[] {
  if (!root || typeof root !== 'object') {
    return []
  }

  const normalizedEntries: unknown[] = []
  for (const [key, value] of Object.entries(root as Record<string, unknown>)) {
    const normalizedKey = key.toLowerCase()
    if (candidateKeys.some((candidate) => normalizedKey.includes(candidate))) {
      normalizedEntries.push(...expandAssetEntries(value))
    }
  }
  return normalizedEntries
}

function expandAssetEntries(value: unknown): unknown[] {
  if (value === undefined || value === null || value === '') {
    return []
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => expandAssetEntries(item))
  }
  if (typeof value === 'string') {
    return [value]
  }
  if (typeof value !== 'object') {
    return []
  }

  const record = value as Record<string, unknown>
  if (hasAssetLocator(record)) {
    return [record]
  }

  for (const nestedKey of ['items', 'assets', 'results', 'versions', 'outputs', 'list']) {
    if (nestedKey in record) {
      return expandAssetEntries(record[nestedKey])
    }
  }

  return []
}

function hasAssetLocator(record: Record<string, unknown>) {
  return ['url', 'uri', 'path', 'src', 'file', 'filepath', 'preview_url', 'previewUrl', 'thumbnail_url', 'thumbnailUrl'].some(
    (key) => key in record,
  )
}

function normalizeAssetEntry(
  kind: VersionKind,
  shotId: string,
  entry: unknown,
  index: number,
): MediaAssetOutput | null {
  if (typeof entry === 'string') {
    const label = `v${index + 1}`
    return {
      id: `${kind}-${shotId}-${index + 1}`,
      kind,
      title: `${assetKindLabel(kind)} ${shotId} ${label}`,
      label,
      uri: entry,
      previewUrl: kind === 'image' ? entry : undefined,
      status: 'done',
      adopted: index === 0,
      metadata: { source: 'real' },
    }
  }

  if (!entry || typeof entry !== 'object') {
    return null
  }

  const record = parseJsonLike(entry) as Record<string, unknown>
  const version = String(record.label ?? record.version ?? `v${index + 1}`)
  const uri = firstString(record.url, record.uri, record.path, record.src, record.file, record.filepath)
  const previewUrl = firstString(
    record.preview_url,
    record.previewUrl,
    record.thumbnail_url,
    record.thumbnailUrl,
    record.poster_url,
    record.posterUrl,
    kind === 'image' ? uri : undefined,
  )
  const adopted = Boolean(
    record.adopted ?? record.selected ?? record.is_adopted ?? record.current ?? record.use_in_sequence ?? index === 0,
  )

  if (!uri && !previewUrl) {
    return null
  }

  return {
    id: String(record.id ?? `${kind}-${shotId}-${index + 1}`),
    kind,
    title: toDisplayText(
      firstString(record.title, record.name),
      `${assetKindLabel(kind)} ${shotId} ${version}`,
    ),
    label: version,
    uri,
    previewUrl,
    prompt: toDisplayText(firstString(record.prompt, record.visual_prompt, record.visualPrompt), ''),
    model: firstString(record.model, record.provider),
    status: firstString(record.status) ?? 'done',
    adopted,
    sourceAssetId: firstString(record.source_asset_id, record.sourceAssetId, record.source_image_id, record.image_id),
    metadata: compactMetadata({
      ...normalizeMetadataRecord(record.metadata),
      source: 'real',
      provider: firstString(record.provider),
      format: firstString(record.format),
      duration: numberMetadata(record.duration),
    }),
  }
}

function looksCorruptedText(text: string) {
  const compact = text.replace(/\s+/g, '')
  if (!compact) {
    return false
  }

  if (compact.includes('�')) {
    return true
  }

  const questionMarks = compact.match(/\?/g)?.length ?? 0
  if (questionMarks >= 2 && questionMarks / compact.length >= 0.2) {
    return true
  }

  if (!/[\u4e00-\u9fff]/.test(compact) && /(?:Ã|Â|Å|Æ|Ð|Ø|Þ|ã|å|æ|ç){2,}/i.test(compact)) {
    return true
  }

  return false
}

function normalizeMetadataRecord(value: unknown): Record<string, MetadataValue> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {}
  }

  return Object.entries(value as Record<string, unknown>).reduce<Record<string, MetadataValue>>((acc, [key, rawValue]) => {
      if (typeof rawValue === 'string' || typeof rawValue === 'number' || typeof rawValue === 'boolean') {
        acc[key] = rawValue
        return acc
      }
      if (Array.isArray(rawValue) && rawValue.every((item) => typeof item === 'string')) {
        acc[key] = rawValue
        return acc
      }
      return acc
    }, {})
}

function parseJsonLike(value: unknown): unknown {
  if (typeof value !== 'string') {
    return value
  }
  const trimmed = value.trim()
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) {
    return value
  }
  try {
    return JSON.parse(trimmed)
  } catch {
    return value
  }
}

function firstString(...values: unknown[]) {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value
    }
  }
  return undefined
}

function numberMetadata(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function compactMetadata(
  values: Record<string, MetadataValue>,
): Record<string, Exclude<MetadataValue, undefined>> {
  return Object.fromEntries(
    Object.entries(values).filter(([, value]) => value !== undefined),
  ) as Record<string, Exclude<MetadataValue, undefined>>
}

function assetKindLabel(kind: VersionKind) {
  switch (kind) {
    case 'image':
      return '分镜图'
    case 'video':
      return '视频'
    case 'audio':
      return '音频'
  }
}
