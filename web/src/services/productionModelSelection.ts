import { fetchModelRegistry, type ModelCapability, type ModelProfileRecord } from './modelRegistry'

export type ProductionGenerationTarget = 'IMAGE' | 'VIDEO'

export type SharedProductionModelSelection = {
  imageModelProfileId: string | null
  videoModelProfileId: string | null
}

export const PRODUCTION_MODEL_SELECTION_KEY = 'production-generation-profile-selection-v1'

export function emptyProductionModelSelection(): SharedProductionModelSelection {
  return { imageModelProfileId: null, videoModelProfileId: null }
}

export function readProductionModelSelection(): SharedProductionModelSelection {
  if (typeof window === 'undefined') return emptyProductionModelSelection()
  try {
    const raw = window.localStorage.getItem(PRODUCTION_MODEL_SELECTION_KEY)
    const parsed = raw ? JSON.parse(raw) : null
    return {
      imageModelProfileId: typeof parsed?.imageModelProfileId === 'string' && parsed.imageModelProfileId.trim() ? parsed.imageModelProfileId.trim() : null,
      videoModelProfileId: typeof parsed?.videoModelProfileId === 'string' && parsed.videoModelProfileId.trim() ? parsed.videoModelProfileId.trim() : null,
    }
  } catch {
    return emptyProductionModelSelection()
  }
}

export function persistProductionModelSelection(selection: SharedProductionModelSelection) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(PRODUCTION_MODEL_SELECTION_KEY, JSON.stringify({
      imageModelProfileId: selection.imageModelProfileId || null,
      videoModelProfileId: selection.videoModelProfileId || null,
    }))
  } catch {
    // localStorage is only an operator convenience; V2 remains authoritative.
  }
}

export function profilesForTarget(profiles: ModelProfileRecord[], target: ProductionGenerationTarget) {
  const capability: ModelCapability = target === 'IMAGE' ? 'image' : 'video'
  return profiles.filter((profile) => profile.enabled && profile.capability === capability)
}

export function selectedProfileIdForTarget(selection: SharedProductionModelSelection, target: ProductionGenerationTarget) {
  return target === 'IMAGE' ? selection.imageModelProfileId : selection.videoModelProfileId
}

export async function fetchProductionGenerationProfiles() {
  const payload = await fetchModelRegistry()
  return payload.profiles.filter((profile) => profile.enabled && (profile.capability === 'image' || profile.capability === 'video'))
}

