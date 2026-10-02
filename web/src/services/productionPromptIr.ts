export type PromptIrMediaTarget = 'IMAGE' | 'VIDEO'

export async function compileProductionPromptIR(bookId: number, episode: number, targetMedia: PromptIrMediaTarget) {
  const policy = targetMedia === 'IMAGE'
    ? { mode: 'TEXT_TO_IMAGE', target_media: 'IMAGE', source: 'shot-studio-ui' }
    : { mode: 'IMAGE_TO_VIDEO', target_media: 'VIDEO', duration_seconds: 5, source: 'shot-studio-ui' }
  const response = await fetch(`/api/books/${bookId}/episodes/${episode}/prompt-ir/compile`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ generation_policy: policy }),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(String(payload?.detail?.message || payload?.detail || `HTTP ${response.status}`))
  return payload
}
