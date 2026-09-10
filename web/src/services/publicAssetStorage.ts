export interface PublicAssetStorageConfig {
  provider: string
  enabled: boolean
  local_base_url: string
  qiniu_bucket: string
  qiniu_region: string
  qiniu_public_base_url: string
  qiniu_bucket_private: boolean
  qiniu_key_prefix: string
  qiniu_upload_token_expires_seconds: number
  qiniu_public_url_ttl_seconds: number
  qiniu_access_key_configured: boolean
  qiniu_secret_key_configured: boolean
}

export interface PublicAssetStorageMigrationPlan {
  storage: PublicAssetStorageConfig
  summary: {
    total_scanned: number
    already_target_storage: number
    needs_publish: number
    external_unchecked: number
    external_accessible: number
    external_unreachable: number
    unknown_source: number
    requires_migration: number
  }
  items: Array<{
    source: string
    owner: Record<string, unknown>
    url: string
    status: string
    requires_migration: boolean
    reason: string
  }>
  migration_apply_supported: boolean
  migration_apply_note: string
  confirmation_token: string
  plan_fingerprint: string
}

export interface PublicAssetStorageMigrationRecord {
  id: number
  task_id: string
  plan_fingerprint: string
  status: string
  result: { total?: number; migrated?: number; failed?: number }
  error_report: Array<{ error?: string; retryable?: boolean }>
  old_objects_deleted: boolean
}

const API = '/api/public-asset-storage'

async function readErrorMessage(response: Response, fallback: string) {
  const text = (await response.text()).trim()
  if (!text) return fallback
  try {
    const parsed = JSON.parse(text)
    if (typeof parsed?.detail === 'string' && parsed.detail.trim()) return parsed.detail.trim()
  } catch {
    // noop
  }
  return text
}

export async function fetchPublicAssetStorageConfig(): Promise<PublicAssetStorageConfig> {
  const response = await fetch(`${API}/config`)
  if (!response.ok) {
    const detail = await readErrorMessage(response, `HTTP ${response.status}`)
    throw new Error(`加载对象存储配置失败：${detail}`)
  }
  return response.json()
}

export async function savePublicAssetStorageConfig(payload: Partial<PublicAssetStorageConfig> & {
  qiniu_access_key?: string
  qiniu_secret_key?: string
}): Promise<PublicAssetStorageConfig> {
  const response = await fetch(`${API}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const detail = await readErrorMessage(response, `HTTP ${response.status}`)
    throw new Error(`保存对象存储配置失败：${detail}`)
  }
  return response.json()
}

export async function fetchPublicAssetStorageMigrationPlan(limit = 200): Promise<PublicAssetStorageMigrationPlan> {
  const response = await fetch(`${API}/migration-plan?limit=${encodeURIComponent(String(limit))}`)
  if (!response.ok) {
    const detail = await readErrorMessage(response, `HTTP ${response.status}`)
    throw new Error(`生成对象存储迁移计划失败：${detail}`)
  }
  return response.json()
}

export async function executePublicAssetStorageMigration(plan: PublicAssetStorageMigrationPlan): Promise<{ record_id: number; task_id: string; status?: string }> {
  const response = await fetch(`${API}/migration-plan/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      confirmationToken: plan.confirmation_token,
      limit: Math.max(1, Math.min(plan.summary.total_scanned || 200, 2000)),
      executeWrite: true,
      confirmed: true,
      allowWrite: true,
      executionConfirmationToken: 'CONFIRM_PUBLIC_ASSET_STORAGE_MIGRATION',
    }),
  })
  if (!response.ok) {
    const detail = await readErrorMessage(response, `HTTP ${response.status}`)
    throw new Error(`对象存储迁移提交失败：${detail}`)
  }
  return response.json()
}

export async function fetchPublicAssetStorageMigrationRecord(recordId: number): Promise<PublicAssetStorageMigrationRecord> {
  const response = await fetch(`${API}/migration-records/${encodeURIComponent(String(recordId))}`)
  if (!response.ok) {
    const detail = await readErrorMessage(response, `HTTP ${response.status}`)
    throw new Error(`加载对象存储迁移记录失败：${detail}`)
  }
  return response.json()
}
