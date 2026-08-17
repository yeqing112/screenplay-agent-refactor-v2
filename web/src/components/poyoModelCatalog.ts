export const POYO_IMAGE_MODEL_SUGGESTIONS = [
  'gpt-image-2',
  'nano-banana-2',
  'seedream-5-0-lite-api',
] as const

export const POYO_VIDEO_MODEL_SUGGESTIONS = [
  'seedance-2',
  'kling-3-api',
  'kling-3.0/standard',
  'kling-3.0/pro',
  'kling-3.0/4K',
  'happy-horse-1-1',
] as const

export function normalizePoyoModelName(value: string) {
  const normalized = value.trim().toLowerCase()
  if (!normalized) return ''
  if (normalized === 'nano-banana-2-new') return 'nano-banana-2'
  if (normalized === 'seedream-5.0-lite') return 'seedream-5-0-lite-api'
  if (normalized === 'happy-horse-1.1') return 'happy-horse-1-1'
  if (normalized === 'kling-3.0/4k') return 'kling-3.0/4k'
  return normalized
}

export function isPoyoHappyHorseModel(modelName: string) {
  return normalizePoyoModelName(modelName) === 'happy-horse-1-1'
}

export function isPoyoKlingFamilyModel(modelName: string) {
  const normalized = normalizePoyoModelName(modelName)
  return (
    normalized === 'kling-3-api' ||
    normalized === 'kling-3.0/standard' ||
    normalized === 'kling-3.0/pro' ||
    normalized === 'kling-3.0/4k'
  )
}

export function isPoyoSeedreamLiteModel(modelName: string) {
  return normalizePoyoModelName(modelName) === 'seedream-5-0-lite-api'
}

export function isPoyoNanoBananaModel(modelName: string) {
  return normalizePoyoModelName(modelName) === 'nano-banana-2'
}
