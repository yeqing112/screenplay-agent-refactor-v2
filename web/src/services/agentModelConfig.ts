import type { ModelProfileRecord } from './modelRegistry'

export interface AgentModelConfig {
  profile_id: string
  configured: boolean
  profile: ModelProfileRecord | null
  uses_production_default: false
  runtime_policy: {
    thinking: 'enabled' | 'disabled'
    vision_enabled: boolean
  }
}

const API = '/api/agent/model-config'

async function readError(response: Response): Promise<string> {
  const text = (await response.text()).trim()
  if (!text) return `HTTP ${response.status}`
  try {
    const parsed = JSON.parse(text)
    if (typeof parsed.detail === 'string') return parsed.detail
  } catch {
    // Keep the text response when it is not JSON.
  }
  return text
}

export async function fetchAgentModelConfig(): Promise<AgentModelConfig> {
  const response = await fetch(API)
  if (!response.ok) throw new Error(await readError(response))
  return response.json() as Promise<AgentModelConfig>
}

export async function saveAgentModelConfig(profileId: string, thinking?: 'enabled' | 'disabled', visionEnabled?: boolean): Promise<AgentModelConfig> {
  const response = await fetch(API, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_id: profileId, thinking, vision_enabled: visionEnabled }),
  })
  if (!response.ok) throw new Error(await readError(response))
  return response.json() as Promise<AgentModelConfig>
}
