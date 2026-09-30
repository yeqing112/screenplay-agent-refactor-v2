import { describe, expect, it } from 'vitest'
import {
  persistProductionModelSelection,
  profilesForTarget,
  readProductionModelSelection,
  type SharedProductionModelSelection,
} from './productionModelSelection'
import type { ModelProfileRecord } from './modelRegistry'

const profiles = [
  { id: 'image-1', name: 'Image', capability: 'image', provider: 'fixture', base_url: '', model_name: '', default_params: {}, enabled: true, is_default: false, key_configured: true, builtin: true, source: 'test', uses_mock: true },
  { id: 'video-1', name: 'Video', capability: 'video', provider: 'fixture', base_url: '', model_name: '', default_params: {}, enabled: true, is_default: false, key_configured: true, builtin: true, source: 'test', uses_mock: true },
  { id: 'image-disabled', name: 'Disabled', capability: 'image', provider: 'fixture', base_url: '', model_name: '', default_params: {}, enabled: false, is_default: false, key_configured: true, builtin: true, source: 'test', uses_mock: true },
] as ModelProfileRecord[]

describe('production model selection', () => {
  it('persists explicit shared selections and filters by capability', () => {
    const selection: SharedProductionModelSelection = { imageModelProfileId: 'image-1', videoModelProfileId: 'video-1' }
    persistProductionModelSelection(selection)
    expect(readProductionModelSelection()).toEqual({ imageModelProfileId: null, videoModelProfileId: null })
    expect(profilesForTarget(profiles, 'IMAGE').map((item) => item.id)).toEqual(['image-1'])
    expect(profilesForTarget(profiles, 'VIDEO').map((item) => item.id)).toEqual(['video-1'])
  })
})
