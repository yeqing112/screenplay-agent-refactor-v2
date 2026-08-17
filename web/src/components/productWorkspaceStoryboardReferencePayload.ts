import type { StoryboardShotOutput } from '../prototyping/sceneComposerData'

function normalizeReferenceAssetIds(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.map((item) => String(item || '').trim()).filter(Boolean)))
}

export function collectStructuredReferenceAssetIds(shot: StoryboardShotOutput | null | undefined) {
  return normalizeReferenceAssetIds((shot?.reference_images ?? []).map((item) => item.reference_asset_id))
}

export function collectCompiledReferenceAssetIds(shot: StoryboardShotOutput | null | undefined) {
  const compiledReferenceIds = shot?.prompt_compile_context?.compiled_reference_asset_ids
  if (Array.isArray(compiledReferenceIds)) {
    const normalizedCompiledIds = normalizeReferenceAssetIds(compiledReferenceIds)
    if (normalizedCompiledIds.length > 0) return normalizedCompiledIds
  }

  const assetBindings = shot?.prompt_compile_context?.asset_bindings
  if (!assetBindings || typeof assetBindings !== 'object') return []

  const collected: string[] = []
  const pushBinding = (binding: { reference_asset_id?: string; image_url?: string; has_reference?: boolean } | null | undefined) => {
    if (!binding || typeof binding !== 'object') return
    const referenceAssetId = String(binding.reference_asset_id || '').trim()
    const imageUrl = String(binding.image_url || '').trim()
    if (!referenceAssetId || !imageUrl || binding.has_reference === false) return
    collected.push(referenceAssetId)
  }

  pushBinding(assetBindings.scene)
  for (const binding of assetBindings.characters ?? []) pushBinding(binding)
  for (const binding of assetBindings.props ?? []) pushBinding(binding)

  return normalizeReferenceAssetIds(collected)
}

export function resolveEffectiveReferenceAssetIds(shot: StoryboardShotOutput | null | undefined) {
  const compiledReferenceIds = collectCompiledReferenceAssetIds(shot)
  if (compiledReferenceIds.length > 0) {
    return {
      assetIds: compiledReferenceIds,
      source: 'compiled' as const,
    }
  }

  return {
    assetIds: collectStructuredReferenceAssetIds(shot),
    source: 'structured' as const,
  }
}
