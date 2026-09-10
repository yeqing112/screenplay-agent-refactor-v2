export type ToolTier = 'A' | 'B' | 'C' | 'D'

export interface DirectorPlanStep {
  index: number
  operation: string
  description: string
  tier: ToolTier
  requires_confirmation: boolean
  params: Record<string, unknown>
}

export interface DirectorPlan {
  objective: string
  scope: Record<string, unknown>
  scope_key: string
  evidence_snapshot: { items?: unknown[] } & Record<string, unknown>
  steps: DirectorPlanStep[]
  tier_counts: { A: number; B: number; C: number; D: number }
  preconditions: string[]
  blocking_issues: string[]
  approval_policy: Record<string, unknown>
  cost_envelope: Record<string, unknown>
  rollback_anchor: Record<string, unknown>
  status: string
  auto_executable: boolean
  plan_fingerprint: string
}

export interface DirectorPlanSummary {
  plan_fingerprint: string
  status: string
  tier_counts: { A: number; B: number; C: number; D: number }
  step_count: number
  blocking_issues: string[]
  auto_executable: boolean
}

export interface DirectorPlanResponse {
  plan: DirectorPlan
  summary: DirectorPlanSummary
  plan_id: number | null
  status: string
}

export interface AgentDraftPreview {
  protocol_version: string
  plan_fingerprint: string
  evidence_fingerprint: string
  draft_fingerprint: string
  model: { id: string; name: string; provider: string; model_name: string; supports_vision?: boolean }
  attachment_capabilities?: {
    documents_included_as_text: boolean
    images_sent_to_model: boolean
    image_understanding_available: boolean
    model_supports_vision?: boolean
    agent_vision_enabled?: boolean
    agent_thinking?: 'enabled' | 'disabled'
  }
  estimated_tokens: number
  cost_notice: string
  system_prompt: string
  user_prompt: string
  evidence: Record<string, unknown>
}

export interface AgentAttachment {
  id: number
  filename: string
  kind: 'image' | 'document'
  mime_type: string
  size_bytes: number
  sha256: string
  extraction_status: string
  status: string
}

export interface AgentDraftResult {
  draft: {
    summary: string
    analysis: string
    recommended_steps: unknown[]
    risks: unknown[]
    requires_confirmation: boolean
  }
  deduplicated: boolean
  llm_called: boolean
  mutated: boolean
  status?: string
}

export interface AgentAuditEntry {
  id: number
  session_id: number
  operation: string
  tier: ToolTier
  evidence_fingerprint: string
  plan_fingerprint: string
  request_fingerprint?: string
  llm_usage?: {
    prompt_tokens?: number | null
    cached_tokens?: number | null
    completion_tokens?: number | null
    total_tokens?: number | null
    cache_hit_rate?: number | null
    last_latency_ms?: number | null
  }
  model: { name?: string; model_name?: string }
  result_status: string
  result_message: string
  confirmed_at: string | null
  created_at: string | null
  draft: AgentDraftResult['draft']
}

export interface AgentUsageSummary {
  book_id: number
  audit_count: number
  observed_calls: number
  prompt_tokens: number
  cached_tokens: number | null
  completion_tokens: number
  total_tokens: number
  cache_observable: boolean
  cache_observable_calls: number
  cache_hit_rate: number | null
  average_latency_ms: number | null
}

export interface AgentHandoffAction {
  kind: string
  tier: ToolTier
  requires_confirmation: boolean
  label: string
  route: string
  guard: string
}

export interface AgentHandoffConfirmation {
  audit_id: number
  book_id: number
  operation: string
  tool: AgentToolDefinition
  handoff: {
    section: 'dashboard' | 'storyboard' | 'assets' | 'qa'
    episode: number | null
    shot_id: number | null
    asset_id: number | null
    label: string
    guard: string
  }
  mutated: boolean
}

export interface AgentTimelineEvent {
  kind: 'session' | 'plan' | 'audit' | 'project_update'
  id: number
  session_id: number
  status: string
  at: string | null
  summary: string
  operation?: string
  tier?: ToolTier
  evidence_fingerprint?: string
  plan_fingerprint?: string
}

export type AgentProjectUpdateType = 'progress' | 'issue' | 'recommendation' | 'action_proposal' | 'completion' | 'failure'
export type AgentProjectUpdateSeverity = 'info' | 'warning' | 'blocking' | 'critical'
export type AgentProjectUpdateStatus = 'unread' | 'acknowledged' | 'resolved' | 'dismissed' | 'snoozed' | 'expired'

export interface AgentProjectUpdate {
  id: number
  book_id: number
  type: AgentProjectUpdateType
  severity: AgentProjectUpdateSeverity
  title: string
  message: string
  source_refs: Array<Record<string, unknown>>
  evidence_fingerprint: string
  action_proposal: Record<string, unknown>
  requires_confirmation: boolean
  status: AgentProjectUpdateStatus
  dedupe_key: string
  created_at: string | null
  updated_at: string | null
}

export interface AgentToolDefinition {
  operation: string
  label: string
  tier: ToolTier
  execution: 'read_only' | 'handoff' | 'blocked'
  requires_confirmation: boolean
  external_cost: boolean
  state_before_confirmation: string
}

export interface DirectorSkill {
  id: string
  version: string
  label: string
  description: string
  input_schema: Record<string, unknown>
  allowed_operations: string[]
  required_evidence: string[]
}

export interface DirectorContext {
  book_id: number | null
  book_title?: string | null
  section?: string | null
  shot_id?: number | null
  asset_id?: number | null
  notes?: string
}

export interface BuildPlanRequest {
  objective: string
  scope: Record<string, unknown>
  evidence_snapshot: Record<string, unknown>
  candidate_operations: Array<{ operation: string; description?: string; params?: Record<string, unknown> }>
  preconditions?: string[]
  blocking_issues?: string[]
  persist?: boolean
  skill_id?: string | null
}

export async function buildDirectorPlan(req: BuildPlanRequest): Promise<DirectorPlanResponse> {
  const response = await fetch('/api/agent/plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`agent plan request failed: ${response.status} ${text}`)
  }
  return response.json() as Promise<DirectorPlanResponse>
}

async function agentDraftRequest(path: string, body: Record<string, unknown>): Promise<Response> {
  return fetch(`/api/agent/llm-drafts/${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
}

async function readAgentError(response: Response): Promise<string> {
  const text = await response.text()
  try {
    const parsed = JSON.parse(text) as { detail?: string }
    return parsed.detail || text
  } catch { return text }
}

export async function previewAgentDraft(objective: string, plan: DirectorPlan, attachmentIds: number[] = [], sessionId: number | null = null): Promise<AgentDraftPreview> {
  const response = await agentDraftRequest('preview', { objective, plan, attachmentIds, sessionId })
  if (!response.ok) throw new Error(await readAgentError(response))
  return (await response.json() as { preview: AgentDraftPreview }).preview
}

export async function invokeAgentDraft(objective: string, plan: DirectorPlan, draftFingerprint: string, attachmentIds: number[] = [], sessionId: number | null = null): Promise<AgentDraftResult> {
  const response = await agentDraftRequest('invoke', {
    objective, plan, draftFingerprint, attachmentIds, sessionId, confirmed: true, allowExternalCall: true,
  })
  if (!response.ok) throw new Error(await readAgentError(response))
  return response.json() as Promise<AgentDraftResult>
}

export async function uploadAgentAttachment(bookId: number, file: File): Promise<AgentAttachment> {
  const form = new FormData()
  form.append('file', file)
  const response = await fetch(`/api/agent/attachments?bookId=${encodeURIComponent(String(bookId))}`, { method: 'POST', body: form })
  if (!response.ok) throw new Error(await readAgentError(response))
  return (await response.json() as { attachment: AgentAttachment }).attachment
}

export function agentAttachmentContentUrl(bookId: number, attachmentId: number): string {
  return `/api/agent/attachments/${encodeURIComponent(String(attachmentId))}/content?bookId=${encodeURIComponent(String(bookId))}`
}

export interface AgentMessage {
  id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  attachment_ids: number[]
  created_at: string | null
}

export interface AgentChatResponse {
  session_id: number
  audit_id?: number
  message: { role: 'assistant'; content: string; attachment_ids: number[] }
  intent: string
  requires_confirmation: boolean
  action_proposal: Record<string, unknown>
  updates: Array<Record<string, unknown>>
  llm_called: boolean
  mutated: boolean
}

export async function sendAgentChatMessage(bookId: number, message: string, scope: Record<string, unknown> = {}, attachmentIds: number[] = [], sessionId: number | null = null): Promise<AgentChatResponse> {
  const response = await fetch('/api/agent/chat', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bookId, message, scope, attachmentIds, sessionId }),
  })
  if (!response.ok) throw new Error(await readAgentError(response))
  return response.json() as Promise<AgentChatResponse>
}

export async function createAgentSession(bookId: number, userPrompt: string): Promise<number> {
  const response = await fetch('/api/agent/sessions', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bookId, userPrompt }),
  })
  if (!response.ok) throw new Error(await readAgentError(response))
  return (await response.json() as { session_id: number }).session_id
}

export async function fetchAgentMessages(sessionId: number): Promise<AgentMessage[]> {
  const response = await fetch(`/api/agent/sessions/${encodeURIComponent(String(sessionId))}/messages`)
  if (!response.ok) throw new Error(await readAgentError(response))
  return (await response.json() as { messages: AgentMessage[] }).messages
}

export async function fetchAgentSessionState(sessionId: number): Promise<{ session: { id: number; status: string }; messages: AgentMessage[]; plan: DirectorPlan | null }> {
  const response = await fetch(`/api/agent/sessions/${encodeURIComponent(String(sessionId))}/state`)
  if (!response.ok) throw new Error(await readAgentError(response))
  return response.json() as Promise<{ session: { id: number; status: string }; messages: AgentMessage[]; plan: DirectorPlan | null }>
}

export interface AgentSessionSummary {
  id: number
  status: string
  user_prompt: string
  created_at: string | null
  updated_at: string | null
}

export async function fetchAgentSessions(bookId: number): Promise<AgentSessionSummary[]> {
  const response = await fetch(`/api/agent/sessions?bookId=${encodeURIComponent(String(bookId))}`)
  if (!response.ok) throw new Error(await readAgentError(response))
  return (await response.json() as { sessions: AgentSessionSummary[] }).sessions
}

export async function appendAgentMessage(sessionId: number, role: AgentMessage['role'], content: string, attachmentIds: number[] = []): Promise<void> {
  const response = await fetch(`/api/agent/sessions/${encodeURIComponent(String(sessionId))}/messages`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role, content, attachmentIds }),
  })
  if (!response.ok) throw new Error(await readAgentError(response))
}

export async function fetchAgentAudit(bookId: number): Promise<AgentAuditEntry[]> {
  const response = await fetch(`/api/agent/audit?bookId=${encodeURIComponent(String(bookId))}`)
  if (!response.ok) throw new Error(await readAgentError(response))
  return (await response.json() as { entries: AgentAuditEntry[] }).entries
}

export async function fetchAgentUsageSummary(bookId: number): Promise<AgentUsageSummary> {
  const response = await fetch(`/api/agent/usage-summary?bookId=${encodeURIComponent(String(bookId))}`)
  if (!response.ok) throw new Error(await response.text())
  const payload = await response.json() as { [key: string]: unknown }
  return payload as unknown as AgentUsageSummary
}

export async function fetchAgentHandoffPreview(auditId: number): Promise<AgentHandoffAction[]> {
  const response = await fetch(`/api/agent/audit/${encodeURIComponent(String(auditId))}/handoff-preview`)
  if (!response.ok) throw new Error(await readAgentError(response))
  return (await response.json() as { actions: AgentHandoffAction[] }).actions
}

export async function confirmAgentHandoff(auditId: number): Promise<AgentHandoffConfirmation> {
  const response = await fetch(`/api/agent/audit/${encodeURIComponent(String(auditId))}/handoff-confirm`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
  })
  if (!response.ok) throw new Error(await readAgentError(response))
  return response.json() as Promise<AgentHandoffConfirmation>
}

export async function fetchAgentTimeline(bookId: number): Promise<AgentTimelineEvent[]> {
  const response = await fetch(`/api/agent/timeline?bookId=${encodeURIComponent(String(bookId))}`)
  if (!response.ok) throw new Error(await readAgentError(response))
  return (await response.json() as { events: AgentTimelineEvent[] }).events
}

export async function reconcileAgentProjectUpdates(bookId: number, scope: Record<string, unknown> = {}): Promise<{ updates: AgentProjectUpdate[]; summary: Record<string, unknown>; created_count: number; reused_count: number }> {
  const response = await fetch('/api/agent/updates/reconcile', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bookId, scope }),
  })
  if (!response.ok) throw new Error(await readAgentError(response))
  return response.json() as Promise<{ updates: AgentProjectUpdate[]; summary: Record<string, unknown>; created_count: number; reused_count: number }>
}

export async function fetchAgentProjectUpdates(bookId: number, status?: AgentProjectUpdateStatus): Promise<AgentProjectUpdate[]> {
  const params = new URLSearchParams({ bookId: String(bookId) })
  if (status) params.set('status', status)
  const response = await fetch(`/api/agent/updates?${params.toString()}`)
  if (!response.ok) throw new Error(await readAgentError(response))
  return (await response.json() as { updates: AgentProjectUpdate[] }).updates
}

/**
 * Subscribe to newly persisted project updates. The server sends one batch
 * or a heartbeat and closes the stream; callers can reconnect with the last
 * received id. This is intentionally read-only and complements polling.
 */
export function openAgentProjectUpdateStream(
  bookId: number,
  sinceId: number,
  onUpdate: (update: AgentProjectUpdate) => void,
  onError?: () => void,
  waitMs = 25000,
): () => void {
  if (typeof EventSource === 'undefined') return () => undefined
  const params = new URLSearchParams({ bookId: String(bookId), sinceId: String(Math.max(0, sinceId)), waitMs: String(Math.max(0, waitMs)) })
  const source = new EventSource(`/api/agent/updates/stream?${params.toString()}`)
  source.addEventListener('project_update', (event) => {
    try { onUpdate(JSON.parse((event as MessageEvent).data) as AgentProjectUpdate) } catch { onError?.() }
  })
  source.onerror = () => { onError?.(); source.close() }
  return () => source.close()
}

export async function updateAgentProjectUpdateState(updateId: number, status: Exclude<AgentProjectUpdateStatus, 'unread' | 'expired'>): Promise<AgentProjectUpdate> {
  const response = await fetch(`/api/agent/updates/${encodeURIComponent(String(updateId))}/state`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }),
  })
  if (!response.ok) throw new Error(await readAgentError(response))
  return (await response.json() as { update: AgentProjectUpdate }).update
}

export async function fetchAgentTools(): Promise<AgentToolDefinition[]> {
  const response = await fetch('/api/agent/tools')
  if (!response.ok) throw new Error(await readAgentError(response))
  return (await response.json() as { tools: AgentToolDefinition[] }).tools
}

export async function fetchDirectorSkills(): Promise<DirectorSkill[]> {
  const response = await fetch('/api/agent/skills')
  if (!response.ok) throw new Error(await readAgentError(response))
  return (await response.json() as { skills: DirectorSkill[] }).skills
}

export async function setAgentSessionPaused(sessionId: number, paused: boolean): Promise<void> {
  const response = await fetch(`/api/agent/sessions/${encodeURIComponent(String(sessionId))}/${paused ? 'pause' : 'resume'}`, { method: 'POST' })
  if (!response.ok) throw new Error(await readAgentError(response))
}

export function summariseContextForAgent(context: DirectorContext | null): string {
  if (!context) return '当前未选择项目。'
  const book = context.book_title || (context.book_id ? `项目 #${context.book_id}` : '未命名项目')
  const section = context.section ? ` / ${context.section}` : ''
  const shot = context.shot_id ? ` / 镜头 ${context.shot_id}` : ''
  const asset = context.asset_id ? ` / 资产 ${context.asset_id}` : ''
  return `${book}${section}${shot}${asset}`
}
