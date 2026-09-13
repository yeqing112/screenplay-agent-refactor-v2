export type ModelCapability = 'llm' | 'embedding' | 'image' | 'video'

export interface ModelProfileRecord {
  id: string
  name: string
  capability: ModelCapability
  provider: string
  base_url: string
  model_name: string
  default_params: Record<string, unknown>
  enabled: boolean
  is_default: boolean
  key_configured: boolean
  builtin: boolean
  source: string
  uses_mock: boolean
  api_key?: string
}

export interface ModelRegistryPayload {
  profiles: ModelProfileRecord[]
  defaults: Partial<Record<ModelCapability, string | null>>
  default_profiles: Partial<Record<ModelCapability, ModelProfileRecord | null>>
}

export interface ModelRegistryTestPayload {
  ok: boolean
  message: string
  profile: ModelProfileRecord
  model_available?: boolean
  catalog_status?: 'verified' | 'unavailable'
  available_models?: string[]
  suggested_models?: string[]
}

const API = '/api/model-registry'

async function readErrorMessage(response: Response, fallback: string) {
  const text = (await response.text()).trim()
  if (!text) return fallback
  try {
    const parsed = JSON.parse(text)
    if (typeof parsed?.detail === 'string' && parsed.detail.trim()) return parsed.detail.trim()
    if (typeof parsed?.message === 'string' && parsed.message.trim()) return parsed.message.trim()
  } catch {
    // noop
  }
  return text
}

export async function fetchModelRegistry(): Promise<ModelRegistryPayload> {
  const response = await fetch(API)
  if (!response.ok) {
    const detail = await readErrorMessage(response, `HTTP ${response.status}`)
    throw new Error(`加载模型注册表失败：${detail}`)
  }
  return response.json()
}

export async function fetchModelRegistryDefaults(): Promise<
  Pick<ModelRegistryPayload, 'defaults' | 'default_profiles'>
> {
  const response = await fetch(`${API}/defaults`)
  if (!response.ok) {
    const detail = await readErrorMessage(response, `HTTP ${response.status}`)
    throw new Error(`加载默认模型失败：${detail}`)
  }
  return response.json()
}

export async function saveModelRegistry(payload: {
  profiles: Array<Partial<ModelProfileRecord> & Pick<ModelProfileRecord, 'name' | 'capability' | 'provider'>>
  defaults: Partial<Record<ModelCapability, string>>
}): Promise<ModelRegistryPayload> {
  const response = await fetch(API, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const detail = await readErrorMessage(response, `HTTP ${response.status}`)
    throw new Error(`保存模型注册表失败：${detail}`)
  }
  return response.json()
}

export async function testModelProfile(payload: {
  profile_id?: string
  profile?: Partial<ModelProfileRecord> & Pick<ModelProfileRecord, 'name' | 'capability' | 'provider'>
}): Promise<ModelRegistryTestPayload> {
  const response = await fetch(`${API}/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const detail = await readErrorMessage(response, `HTTP ${response.status}`)
    throw new Error(`测试模型连接失败：${detail}`)
  }
  return response.json()
}
