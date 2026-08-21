import type { ModelProfileRecord, ModelRegistryPayload } from '../services/modelRegistry'

export interface ContentModelContextSummary {
  llmTitle: string
  llmProvider: string
  embeddingTitle: string
  embeddingProvider: string
  ready: boolean
  statusLabel: string
}

function buildProfileTitle(profile: ModelProfileRecord | null | undefined, fallback: string) {
  if (!profile) return fallback
  const modelName = String(profile.model_name || '').trim()
  return modelName ? `${profile.name} (${modelName})` : profile.name
}

function buildProviderLabel(profile: ModelProfileRecord | null | undefined, fallback: string) {
  const provider = String(profile?.provider || '').trim()
  return provider || fallback
}

export function buildContentModelContextSummary(
  defaultProfiles: ModelRegistryPayload['default_profiles'] | null | undefined,
): ContentModelContextSummary {
  const llmProfile = defaultProfiles?.llm ?? null
  const embeddingProfile = defaultProfiles?.embedding ?? null
  const ready = Boolean(llmProfile && embeddingProfile)

  return {
    llmTitle: buildProfileTitle(llmProfile, '未配置默认 LLM'),
    llmProvider: buildProviderLabel(llmProfile, '未配置 provider'),
    embeddingTitle: buildProfileTitle(embeddingProfile, '未配置默认向量模型'),
    embeddingProvider: buildProviderLabel(embeddingProfile, '未配置 provider'),
    ready,
    statusLabel: ready ? '已接入模型上下文' : '待补模型配置',
  }
}
