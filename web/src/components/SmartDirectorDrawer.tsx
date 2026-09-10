import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  fetchAgentAudit,
  fetchAgentUsageSummary,
  fetchAgentHandoffPreview,
  confirmAgentHandoff,
  fetchAgentTimeline,
  fetchAgentTools,
  fetchDirectorSkills,
  setAgentSessionPaused,
  invokeAgentDraft,
  uploadAgentAttachment,
  agentAttachmentContentUrl,
  sendAgentChatMessage,
  fetchAgentSessions,
  fetchAgentSessionState,
  previewAgentDraft,
  reconcileAgentProjectUpdates,
  fetchAgentProjectUpdates,
  openAgentProjectUpdateStream,
  updateAgentProjectUpdateState,
  summariseContextForAgent,
  type AgentDraftPreview,
  type AgentDraftResult,
  type AgentAuditEntry,
  type AgentUsageSummary,
  type AgentHandoffAction,
  type AgentTimelineEvent,
  type AgentToolDefinition,
  type AgentAttachment,
  type AgentMessage,
  type AgentSessionSummary,
  type DirectorSkill,
  type DirectorContext,
  type DirectorPlan,
  type DirectorPlanStep,
  type AgentProjectUpdate,
} from '../services/agent'
import {
  TIER_LABEL,
  TIER_OPERATIONS,
  TIER_TONE,
  classifyOperation,
} from './smartDirectorClassifier'

interface Props {
  context: DirectorContext | null
}

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function auditUsageLabel(entry: AgentAuditEntry): string {
  const usage = entry.llm_usage
  if (!usage) return ''
  const input = usage.prompt_tokens ?? null
  const cached = usage.cached_tokens ?? null
  const output = usage.completion_tokens ?? null
  const latency = usage.last_latency_ms ?? null
  if (input === null && output === null && latency === null) return ''
  const cache = cached === null ? '缓存不可观测' : `缓存 ${cached}/${input ?? '—'}${usage.cache_hit_rate == null ? '' : ` · ${(usage.cache_hit_rate * 100).toFixed(1)}%`}`
  return `用量：输入 ${input ?? '—'} · ${cache} · 输出 ${output ?? '—'}${latency == null ? '' : ` · ${Math.round(latency)}ms`}`
}

const QUICK_STARTS: Array<{
  label: string
  objective: string
  operations: DirectorPlanStep['operation'][]
}> = [
  {
    label: '看看下一步做什么',
    objective: '请检查当前项目进度，告诉我现在最该做什么，并说明原因。',
    operations: ['diagnose'],
  },
  {
    label: '检查镜头是否连贯',
    objective: '请检查当前镜头与相邻镜头是否连贯，告诉我哪里需要调整。',
    operations: ['diagnose', 'continuity_check'],
  },
  {
    label: '帮我优化提示词',
    objective: '请检查当前镜头提示词是否适合生产，并给出可审核的优化建议。',
    operations: ['diagnose', 'draft_prompt'],
  },
  {
    label: '准备生成视频',
    objective: '请检查生成当前镜头视频前还缺哪些内容，并列出下一步。',
    operations: ['diagnose', 'continuity_check', 'video_generation'],
  },
]

const OPERATION_LABELS: Record<string, string> = {
  diagnose: '检查当前状态',
  continuity_check: '检查镜头衔接',
  draft_prompt: '准备提示词优化建议',
  draft_repair: '准备修复建议',
  write_prompt_version: '写入新的提示词版本',
  image_generation: '生成图片',
  video_generation: '生成视频',
}

const TIER_USER_LABEL: Record<DirectorPlanStep['tier'], string> = {
  A: '只检查',
  B: '给出建议',
  C: '修改前确认',
  D: '生成前确认',
}

export default function SmartDirectorDrawer({ context }: Props) {
  const [open, setOpen] = useState<boolean>(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const hadOpenRef = useRef(false)
  const [objective, setObjective] = useState<string>('')
  const [selected, setSelected] = useState<Set<DirectorPlanStep['operation']>>(
    () => new Set(['diagnose', 'continuity_check', 'draft_prompt']),
  )
  const [plan, setPlan] = useState<DirectorPlan | null>(null)
  const [pending, setPending] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [announce, setAnnounce] = useState<string>('')
  const [draftPreview, setDraftPreview] = useState<AgentDraftPreview | null>(null)
  const [draftResult, setDraftResult] = useState<AgentDraftResult | null>(null)
  const [draftPending, setDraftPending] = useState<boolean>(false)
  const [auditEntries, setAuditEntries] = useState<AgentAuditEntry[] | null>(null)
  const [usageSummary, setUsageSummary] = useState<AgentUsageSummary | null>(null)
  const [handoffActions, setHandoffActions] = useState<AgentHandoffAction[] | null>(null)
  const [timeline, setTimeline] = useState<AgentTimelineEvent[] | null>(null)
  const [toolDefinitions, setToolDefinitions] = useState<AgentToolDefinition[] | null>(null)
  const [skills, setSkills] = useState<DirectorSkill[]>([])
  const [selectedSkillId, setSelectedSkillId] = useState<string>('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [attachments, setAttachments] = useState<AgentAttachment[]>([])
  const [uploading, setUploading] = useState(false)
  const [lastSubmittedObjective, setLastSubmittedObjective] = useState<string>('')
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [recentSessions, setRecentSessions] = useState<AgentSessionSummary[]>([])
  const [showSessionHistory, setShowSessionHistory] = useState(false)
  const [actionProposal, setActionProposal] = useState<Record<string, unknown> | null>(null)
  const [projectUpdates, setProjectUpdates] = useState<AgentProjectUpdate[]>([])
  const [updatesLoading, setUpdatesLoading] = useState(false)
  const updateCursorRef = useRef(0)

  const contextLabel = useMemo(() => summariseContextForAgent(context), [context])

  const refreshProjectUpdates = useCallback(async () => {
    if (!context?.book_id) return
    setUpdatesLoading(true)
    try {
      await reconcileAgentProjectUpdates(context.book_id, {
        section: context.section ?? null,
        shot_id: context.shot_id ?? null,
        asset_id: context.asset_id ?? null,
      })
      setProjectUpdates(await fetchAgentProjectUpdates(context.book_id))
    } catch {
      // Project updates are an assistance layer; the conversation remains
      // usable when reconciliation is temporarily unavailable.
    } finally {
      setUpdatesLoading(false)
    }
  }, [context?.asset_id, context?.book_id, context?.section, context?.shot_id])

  useEffect(() => {
    if (!context) return
    setObjective((prev) => (prev.trim() ? prev : `请帮我分析当前 ${contextLabel} 的状态，并给出下一步建议。`))
  }, [context, contextLabel])

  useEffect(() => {
    void fetchAgentTools().then(setToolDefinitions).catch(() => undefined)
    void fetchDirectorSkills().then(setSkills).catch(() => undefined)
  }, [])

  useEffect(() => {
    const openDrawer = (event: Event) => {
      setOpen(true)
      if (!context?.book_id) return
      const requestedSessionId = Number((event as CustomEvent<{ sessionId?: number }>).detail?.sessionId ?? 0) || null
      void Promise.all([fetchAgentAudit(context.book_id), fetchAgentTimeline(context.book_id), fetchAgentSessions(context.book_id), fetchAgentUsageSummary(context.book_id)])
        .then(async ([audits, events, sessions, usage]) => {
          setAuditEntries(audits)
          setTimeline(events)
          setRecentSessions(sessions)
          setUsageSummary(usage)
          const selectedSession = (requestedSessionId ? sessions.find((item) => item.id === requestedSessionId) : null) ?? sessions[0]
          if (selectedSession) {
            const state = await fetchAgentSessionState(selectedSession.id)
            setSessionId(state.session.id)
            setMessages(state.messages)
            setPlan(state.plan)
          }
        })
        .catch(() => {
          // The drawer still opens even when an optional replay read is down.
        })
    }
    window.addEventListener('smart-director:open', openDrawer)
    return () => window.removeEventListener('smart-director:open', openDrawer)
  }, [context?.book_id])

  useEffect(() => {
    if (!context?.book_id) return
    void refreshProjectUpdates()
    const timer = window.setInterval(() => { void refreshProjectUpdates() }, open ? 30000 : 120000)
    return () => window.clearInterval(timer)
  }, [open, context?.book_id, refreshProjectUpdates])

  useEffect(() => {
    if (!open || !context?.book_id) return
    let disposed = false
    let closeStream: () => void = () => undefined
    let reconnectTimer: number | undefined
    const connect = () => {
      if (disposed) return
      closeStream = openAgentProjectUpdateStream(
        context.book_id as number,
        updateCursorRef.current,
        (update) => {
          updateCursorRef.current = Math.max(updateCursorRef.current, update.id)
          setProjectUpdates((current) => [update, ...current.filter((item) => item.id !== update.id)].slice(0, 50))
        },
        () => {
          if (!disposed) reconnectTimer = window.setTimeout(connect, 1500)
        },
      )
    }
    connect()
    return () => {
      disposed = true
      closeStream()
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
    }
  }, [context?.book_id, open])

  const updateProjectUpdateStatus = useCallback(async (update: AgentProjectUpdate, status: 'acknowledged' | 'resolved' | 'snoozed') => {
    try {
      const next = await updateAgentProjectUpdateState(update.id, status)
      setProjectUpdates((current) => current.map((item) => item.id === next.id ? next : item))
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新项目动态状态失败')
    }
  }, [])

  useEffect(() => {
    if (open) {
      hadOpenRef.current = true
      const timer = window.setTimeout(() => composerRef.current?.focus(), 0)
      return () => window.clearTimeout(timer)
    }
    if (hadOpenRef.current) triggerRef.current?.focus()
    return undefined
  }, [open])

  useEffect(() => {
    if (!open || !context?.book_id) return
    void fetchAgentSessions(context.book_id)
      .then(async (sessions) => {
        setRecentSessions(sessions)
        if (!sessionId && sessions[0]) {
          const state = await fetchAgentSessionState(sessions[0].id)
          setSessionId(state.session.id); setMessages(state.messages); setPlan(state.plan)
        }
      })
      .catch(() => {
        // History is optional; the composer remains usable if it is unavailable.
      })
  }, [open, context?.book_id, sessionId])

  const toggleOperation = useCallback((op: DirectorPlanStep['operation']) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(op)) {
        next.delete(op)
      } else {
        next.add(op)
      }
      return next
    })
  }, [])

  const applyQuickStart = useCallback((quickStart: typeof QUICK_STARTS[number]) => {
    setObjective(quickStart.objective)
    setSelected(new Set(quickStart.operations))
    setSelectedSkillId(quickStart.operations.includes('continuity_check') ? 'continuity' : '')
    setPlan(null)
    setDraftPreview(null)
    setDraftResult(null)
    setAnnounce(`已选择：${quickStart.label}。`)
  }, [])

  const onSelectAttachments = useCallback(async (files: FileList | null) => {
    if (!files?.length) return
    if (!context?.book_id) {
      setError('请先打开一个项目，再向 AI 导演助手附加资料。')
      return
    }
    const incoming = Array.from(files)
    if (attachments.length + incoming.length > 6) {
      setError('一次对话最多附加 6 个资料。')
      return
    }
    setUploading(true); setError(null)
    try {
      const uploaded = await Promise.all(incoming.map((file) => uploadAgentAttachment(context.book_id as number, file)))
      setAttachments((current) => [...current, ...uploaded])
      setAnnounce(`已附加 ${uploaded.length} 个资料；尚未发送给 AI。`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '附件上传失败')
    } finally { setUploading(false) }
  }, [attachments.length, context?.book_id])

  const onSubmit = useCallback(async () => {
    const submittedObjective = objective.trim()
    if (!submittedObjective) {
      setError('请先输入你想让我处理的事情。')
      return
    }
    if (!context?.book_id) {
      setError('请先打开一个项目，再开始对话。')
      return
    }
    setPending(true)
    setError(null)
    setAnnounce('正在理解你的请求')
    try {
      const result = await sendAgentChatMessage(context.book_id, submittedObjective, {
        section: context.section ?? null,
        shot_id: context.shot_id ?? null,
        asset_id: context.asset_id ?? null,
      }, attachments.map((item) => item.id), sessionId)
      const userMessage: AgentMessage = { id: Date.now(), role: 'user', content: submittedObjective, attachment_ids: attachments.map((item) => item.id), created_at: new Date().toISOString() }
      const assistantMessage: AgentMessage = { id: Date.now() + 1, role: 'assistant', content: result.message.content, attachment_ids: [], created_at: new Date().toISOString() }
      setSessionId(result.session_id)
      setMessages((current) => [...current, userMessage, assistantMessage])
      setProjectUpdates((result.updates ?? []).map((item, index) => ({
        id: Number(item.id ?? -(index + 1)), book_id: context.book_id as number,
        type: String(item.type ?? 'progress') as AgentProjectUpdate['type'], severity: String(item.severity ?? 'info') as AgentProjectUpdate['severity'],
        title: String(item.title ?? ''), message: String(item.message ?? ''), source_refs: Array.isArray(item.source_refs) ? item.source_refs as Array<Record<string, unknown>> : [],
        evidence_fingerprint: String(item.evidence_fingerprint ?? ''), action_proposal: (item.action_proposal && typeof item.action_proposal === 'object' ? item.action_proposal : {}) as Record<string, unknown>,
        requires_confirmation: Boolean(item.requires_confirmation), status: 'unread', dedupe_key: String(item.dedupe_key ?? ''), created_at: null, updated_at: null,
      })))
      setLastSubmittedObjective(submittedObjective)
      setObjective('')
      setDraftPreview(null)
      setDraftResult(null)
      setPlan(null)
      setActionProposal(result.requires_confirmation ? { ...result.action_proposal, __audit_id: result.audit_id } : null)
      setAnnounce(result.requires_confirmation ? 'AI 已给出需要你确认的操作提案。' : 'AI 已直接回复你的请求。')
    } catch (err) {
      const message = err instanceof Error ? err.message : '未知错误'
      setError(message)
      setAnnounce('对话失败：' + message)
    } finally {
      setPending(false)
    }
  }, [attachments, context, objective, sessionId])

  const onPreviewDraft = useCallback(async () => {
    if (!plan) return
    setDraftPending(true)
    setError(null)
    try {
      const preview = await previewAgentDraft(objective.trim() || plan.objective, plan, attachments.map((attachment) => attachment.id), sessionId)
      setDraftPreview(preview)
      setDraftResult(null)
      setAnnounce('已生成真实模型调用预览；尚未调用模型。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '生成调用预览失败')
    } finally { setDraftPending(false) }
  }, [attachments, objective, plan, sessionId])

  const onInvokeDraft = useCallback(async () => {
    if (!plan || !draftPreview) return
    setDraftPending(true)
    setError(null)
    try {
      const result = await invokeAgentDraft(objective.trim() || plan.objective, plan, draftPreview.draft_fingerprint, attachments.map((attachment) => attachment.id), sessionId)
      setDraftResult(result)
      setAuditEntries(null)
      setAnnounce(result.deduplicated ? '已复用同一证据包的候选草案，未重复调用模型。' : '真实 Agent 模型已生成候选草案；未执行生产操作。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '调用智能导演台模型失败')
      if (context?.book_id) {
        try {
          setTimeline(await fetchAgentTimeline(context.book_id))
        } catch {
          // Keep the original provider error visible even if the read-only
          // timeline refresh is temporarily unavailable.
        }
      }
    } finally { setDraftPending(false) }
  }, [attachments, context?.book_id, draftPreview, objective, plan, sessionId])

  const onLoadAudit = useCallback(async () => {
    if (!context?.book_id) return
    setDraftPending(true)
    setError(null)
    try {
      const [entries, usage] = await Promise.all([fetchAgentAudit(context.book_id), fetchAgentUsageSummary(context.book_id)])
      setAuditEntries(entries)
      setUsageSummary(usage)
    }
    catch (err) { setError(err instanceof Error ? err.message : '加载 Agent 审计记录失败') }
    finally { setDraftPending(false) }
  }, [context?.book_id])

  const onLoadHandoffs = useCallback(async (auditId: number) => {
    setDraftPending(true); setError(null)
    try { setHandoffActions(await fetchAgentHandoffPreview(auditId)) }
    catch (err) { setError(err instanceof Error ? err.message : '加载候选草案承接入口失败') }
    finally { setDraftPending(false) }
  }, [])

  const onConfirmActionProposal = useCallback(async () => {
    const auditId = Number(actionProposal?.__audit_id ?? 0)
    if (!auditId) {
      setError('这条提案缺少可追溯审计编号，请重新发送请求。')
      return
    }
    setDraftPending(true)
    setError(null)
    try {
      const result = await confirmAgentHandoff(auditId)
      setActionProposal(null)
      setAnnounce('已记录你的确认，正在打开对应工作台；正式工作台还会继续进行最终校验。')
      window.dispatchEvent(new CustomEvent('smart-director:navigate', { detail: result.handoff }))
      setOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : '确认动作提案失败')
    } finally {
      setDraftPending(false)
    }
  }, [actionProposal])

  const onLoadTimeline = useCallback(async () => {
    if (!context?.book_id) return
    setDraftPending(true); setError(null)
    try { setTimeline(await fetchAgentTimeline(context.book_id)) }
    catch (err) { setError(err instanceof Error ? err.message : '加载 Agent 时间线失败') }
    finally { setDraftPending(false) }
  }, [context?.book_id])

  const onSetSessionPaused = useCallback(async (sessionId: number, paused: boolean) => {
    setDraftPending(true); setError(null)
    try {
      await setAgentSessionPaused(sessionId, paused)
      if (context?.book_id) setTimeline(await fetchAgentTimeline(context.book_id))
    } catch (err) { setError(err instanceof Error ? err.message : '更新会话状态失败') }
    finally { setDraftPending(false) }
  }, [context?.book_id])

  return (
    <>
      <button
        type="button"
        aria-label="打开智能导演台"
        ref={triggerRef}
        onClick={() => setOpen((v) => !v)}
        className="fixed bottom-6 right-6 z-40 flex items-center gap-2 rounded-full border border-violet-400/40 bg-violet-500/20 px-4 py-2 text-sm font-medium text-violet-50 shadow-lg shadow-violet-500/20 backdrop-blur transition hover:bg-violet-500/30"
      >
        <span aria-hidden>🎬</span>
        智能导演台
        {projectUpdates.some((update) => update.status === 'unread') ? <span className="ml-1 rounded-full bg-rose-500 px-1.5 py-0.5 text-[10px] text-white">{projectUpdates.filter((update) => update.status === 'unread').length}</span> : null}
      </button>

      {open ? (
        <aside
          role="dialog"
          aria-modal="true"
          aria-label="智能导演台对话"
          className="fixed right-0 top-0 z-50 flex h-full w-[420px] max-w-[calc(100vw-0.5rem)] flex-col border-l border-slate-800 bg-slate-950/95 text-slate-100 shadow-2xl"
        >
          <header className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
            <div>
              <div className="text-xs uppercase tracking-[0.2em] text-violet-300/80">Smart Director</div>
              <h2 id="smart-director-title" className="text-sm font-semibold text-white">AI 导演助手</h2>
            </div>
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => setShowSessionHistory((value) => !value)} className="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800">历史</button>
              <button type="button" onClick={() => { setSessionId(null); setMessages([]); setPlan(null); setDraftPreview(null); setDraftResult(null); setActionProposal(null); setObjective(''); setAttachments([]); setLastSubmittedObjective(''); setShowSessionHistory(false) }} className="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800">新对话</button>
              <button type="button" onClick={() => setOpen(false)} className="rounded-md border border-slate-700 px-2 py-1 text-xs text-slate-200 transition hover:bg-slate-800" aria-label="关闭智能导演台">关闭</button>
            </div>
          </header>

          {showSessionHistory ? <div className="border-b border-slate-800 bg-slate-900/80 px-4 py-2" aria-label="最近对话列表">
            <div className="mb-1 text-[11px] text-slate-400">最近对话</div>
            {recentSessions.length ? recentSessions.slice(0, 5).map((item) => <button key={item.id} type="button" onClick={async () => { const state = await fetchAgentSessionState(item.id); setSessionId(state.session.id); setMessages(state.messages); setPlan(state.plan); setShowSessionHistory(false) }} className="block w-full truncate rounded px-2 py-1.5 text-left text-xs text-slate-200 hover:bg-slate-800">{item.user_prompt || '未命名对话'}</button>) : <div className="text-xs text-slate-500">还没有已保存的对话</div>}
          </div> : null}

          <div className="border-b border-slate-800 bg-slate-900/60 px-4 py-3 text-xs text-slate-300">
            <div className="font-medium text-slate-200">我正在协助你处理</div>
            <div className="mt-1 text-slate-400">{contextLabel}</div>
          </div>

          <section className="border-b border-slate-800 bg-slate-950/70 px-4 py-3" aria-label="项目动态">
            <div className="flex items-center justify-between">
              <div className="text-xs font-medium text-slate-200">项目动态</div>
              <button type="button" onClick={() => void refreshProjectUpdates()} className="text-[10px] text-slate-500 hover:text-slate-200" disabled={updatesLoading}>
                {updatesLoading ? '检查中…' : '刷新'}
              </button>
            </div>
            {projectUpdates.length ? (
              <div className="mt-2 space-y-2">
                {projectUpdates.slice(0, 4).map((update) => {
                  const tone = update.severity === 'critical' ? 'border-rose-400/50 bg-rose-500/10' : update.severity === 'blocking' ? 'border-amber-400/40 bg-amber-500/10' : update.severity === 'warning' ? 'border-yellow-400/30 bg-yellow-500/5' : 'border-slate-800 bg-slate-900/60'
                  return (
                    <div key={update.id} className={`rounded-md border p-2 ${tone}`}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="text-[11px] font-medium text-slate-100">{update.title}</div>
                        <div className="flex shrink-0 items-center gap-2 text-[10px]">
                          {update.status === 'unread' ? <button type="button" onClick={() => void updateProjectUpdateStatus(update, 'acknowledged')} className="text-slate-400 underline hover:text-white" aria-label={`已知悉：${update.title}`}>已知悉</button> : null}
                          {update.status !== 'resolved' && update.status !== 'snoozed' ? <button type="button" onClick={() => void updateProjectUpdateStatus(update, 'snoozed')} className="text-slate-400 underline hover:text-white" aria-label={`稍后提醒：${update.title}`}>稍后提醒</button> : null}
                          {update.status !== 'resolved' ? <button type="button" onClick={() => void updateProjectUpdateStatus(update, 'resolved')} className="text-emerald-300 underline hover:text-emerald-100" aria-label={`标记已解决：${update.title}`}>已解决</button> : <span className="text-emerald-300">已解决</span>}
                        </div>
                      </div>
                      <div className="mt-1 text-[11px] leading-5 text-slate-400">{update.message}</div>
                    </div>
                  )
                })}
              </div>
            ) : <div className="mt-2 text-[11px] text-slate-500">暂时没有新的项目动态。</div>}
          </section>

          <div className="flex-1 overflow-y-auto px-4 py-4">
            {messages.length > 0 ? <div className="mb-4 space-y-2" aria-label="最近对话">
              {messages.map((message) => <div key={message.id} className={message.role === 'user' ? 'ml-8 rounded-2xl rounded-tr-sm bg-violet-600 px-3 py-2 text-sm text-white' : 'mr-5 rounded-2xl rounded-tl-sm border border-slate-800 bg-slate-900/70 px-3 py-2 text-sm text-slate-200'}>{message.content}{message.attachment_ids.length ? <div className="mt-1 text-[10px] opacity-70">附带 {message.attachment_ids.length} 个资料</div> : null}</div>)}
            </div> : null}
            {actionProposal ? <section className="mb-4 mr-5 rounded-xl border border-amber-400/40 bg-amber-500/10 p-3" aria-label="待确认操作">
              <div className="text-xs font-medium text-amber-100">这一步需要你的确认</div>
              <div className="mt-1 text-[11px] leading-5 text-amber-50/80">{String(actionProposal.summary || actionProposal.operation || 'AI 建议执行一项会改变项目的操作。')}</div>
              {actionProposal.impact ? <div className="mt-1 text-[10px] text-amber-100/70">影响：{String(actionProposal.impact)}</div> : null}
               <div className="mt-2 text-[10px] text-amber-100/60">确认只表示同意承接这一步；随后会打开对应工作台，最终安全门禁仍由工作台执行。</div>
               <div className="mt-3 flex items-center gap-2">
                 <button type="button" onClick={() => void onConfirmActionProposal()} disabled={draftPending} className="rounded-md bg-amber-500 px-3 py-1.5 text-[11px] font-medium text-slate-950 hover:bg-amber-400 disabled:opacity-60">{draftPending ? '正在处理…' : '确认并打开工作台'}</button>
                 <button type="button" onClick={() => setActionProposal(null)} disabled={draftPending} className="rounded-md border border-amber-300/30 px-3 py-1.5 text-[11px] text-amber-100 hover:bg-amber-500/10 disabled:opacity-60">稍后处理</button>
               </div>
            </section> : null}
            {!plan ? <>
            <div className="text-sm font-medium text-slate-100">今天想让我帮你做什么？</div>
            <div className="mt-1 text-xs leading-5 text-slate-400">直接用日常语言告诉我。先给你建议，不会自动改内容或提交生成。</div>
            <label className="sr-only" htmlFor="agent-objective">
              你想让 AI 导演助手做什么
            </label>
            <textarea
              id="agent-objective"
              ref={composerRef}
              value={objective}
              onChange={(event) => setObjective(event.target.value)}
              className="mt-1 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 focus:border-violet-400 focus:outline-none"
              rows={3}
              placeholder="例如：帮我看看这个镜头能不能直接生成视频。"
            />

            {attachments.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-2" aria-label="本轮已附加资料">
                {attachments.map((attachment) => (
                  <div key={attachment.id} className="flex max-w-full items-center gap-2 rounded-md border border-slate-700 bg-slate-900/80 px-2 py-1.5 text-[11px] text-slate-200">
                    {attachment.kind === 'image' && context?.book_id ? (
                      <img src={agentAttachmentContentUrl(context.book_id, attachment.id)} alt="" className="h-8 w-8 rounded object-cover" />
                    ) : <span aria-hidden>📄</span>}
                    <span className="max-w-[180px] truncate">{attachment.filename}</span>
                    <button type="button" aria-label={`移除 ${attachment.filename}`} onClick={() => {
                      setAttachments((current) => current.filter((item) => item.id !== attachment.id))
                      setDraftPreview(null); setDraftResult(null)
                    }} className="text-slate-400 hover:text-white">×</button>
                  </div>
                ))}
              </div>
            ) : null}

            <div className="mt-2 flex items-center justify-between gap-3 text-[11px] text-slate-400">
              <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-violet-400/30 bg-violet-500/10 px-2.5 py-1.5 text-[11px] font-medium text-violet-100 transition hover:bg-violet-500/20">
                <span aria-hidden>📎</span> 添加附件
                <input aria-label="添加图片或文档" className="sr-only" type="file" multiple accept=".png,.jpg,.jpeg,.webp,.txt,.md,.pdf,.docx" disabled={uploading || !context?.book_id} onChange={(event) => {
                void onSelectAttachments(event.target.files)
                event.currentTarget.value = ''
                }} />
              </label>
              <span>{uploading ? '正在保存资料…' : '资料仅用于本次对话理解，不会自动公开或用于生成。'}</span>
            </div>

            <div className="mt-3 flex flex-wrap gap-2" aria-label="常用请求">
              {QUICK_STARTS.map((quickStart) => <button key={quickStart.label} type="button" onClick={() => applyQuickStart(quickStart)} className="rounded-full border border-violet-400/30 bg-violet-500/10 px-3 py-1.5 text-[11px] text-violet-100 transition hover:bg-violet-500/20">{quickStart.label}</button>)}
            </div>

            <button type="button" className="mt-4 text-xs text-slate-400 underline decoration-slate-600 underline-offset-4 hover:text-slate-200" onClick={() => setShowAdvanced((value) => !value)} aria-expanded={showAdvanced}>
              {showAdvanced ? '收起高级设置' : '高级设置（通常不需要）'}
            </button>

            {showAdvanced ? <div className="mt-3 rounded-md border border-slate-800 bg-slate-900/35 p-3">
              <label className="block text-xs font-medium text-slate-300" htmlFor="agent-skill">创作模式</label>
              <select id="agent-skill" value={selectedSkillId} onChange={(event) => setSelectedSkillId(event.target.value)} className="mt-1 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100">
                <option value="">自动判断适合的方式</option>
                {skills.map((skill) => <option key={skill.id} value={skill.id}>{skill.label}</option>)}
              </select>
              {selectedSkillId ? <div className="mt-1 text-[11px] leading-5 text-slate-400">{skills.find((skill) => skill.id === selectedSkillId)?.description}</div> : null}

              <fieldset className="mt-4">
              <legend className="text-xs font-medium text-slate-300">让助手重点检查</legend>
              <div className="mt-2 grid grid-cols-2 gap-2">
                {TIER_OPERATIONS.map((op) => {
                  const tier = classifyOperation(op)
                  const serverTool = toolDefinitions?.find((item) => item.operation === op)
                  return (
                    <label
                      key={op}
                      className={`flex cursor-pointer items-start gap-2 rounded-md border px-2 py-1.5 text-[11px] ${
                        selected.has(op) ? TIER_TONE[tier] : 'border-slate-700 bg-slate-900 text-slate-300'
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="mt-0.5"
                        checked={selected.has(op)}
                        onChange={() => toggleOperation(op)}
                      />
                      <span>
                        <span className="block font-medium">{op}</span>
                        <span className="block text-[10px] opacity-80">{serverTool ? `${serverTool.label} · ${serverTool.requires_confirmation ? '需确认' : '可审阅'}` : TIER_LABEL[tier]}</span>
                      </span>
                    </label>
                  )
                })}
              </div>
            </fieldset>
            </div> : null}

            <div className="mt-4 flex items-center gap-2">
              <button
                type="button"
                onClick={onSubmit}
                disabled={pending}
                className="rounded-md bg-violet-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:bg-slate-700"
              >
                {pending ? '正在帮你分析…' : '发送'}
              </button>
              <span className="text-[11px] text-slate-400">
                先给你可执行建议；涉及修改、付费调用或生成内容时，会单独征求你的确认。
              </span>
            </div>
            </> : messages.length === 0 ? (
              <div className="ml-8 rounded-2xl rounded-tr-sm bg-violet-600 px-3 py-2 text-sm text-white shadow-sm">
                <div>{lastSubmittedObjective || plan.objective}</div>
                {attachments.length ? <div className="mt-1 text-[11px] text-violet-100">附带 {attachments.length} 个资料</div> : null}
              </div>
            ) : null}

            <div role="status" aria-live="polite" className="sr-only">
              {announce}
            </div>

            {error ? (
              <div className="mt-4 rounded-md border border-rose-400/40 bg-rose-500/10 p-3 text-xs text-rose-100">
                {error}
              </div>
            ) : null}

            {plan ? (
              <section className="mt-4 space-y-3" aria-label="智能导演台计划">
                <div className="mr-5 rounded-2xl rounded-tl-sm border border-slate-800 bg-slate-900/70 p-3 text-xs">
                  <div className="font-medium text-slate-100">AI 导演助手</div>
                  <div className="mt-2 font-medium text-slate-200">我建议这样做</div>
                  <div className="mt-1 text-[11px] leading-5 text-slate-400">{plan.tier_counts.C + plan.tier_counts.D === 0 ? '这一步只会检查和整理建议，不会修改内容或发起生成。' : `其中 ${plan.tier_counts.C + plan.tier_counts.D} 项涉及修改或生成，执行前会单独请你确认。`}</div>
                  <div className="mt-2 grid grid-cols-4 gap-2 text-center">
                    {(Object.keys(plan.tier_counts) as Array<DirectorPlanStep['tier']>).map((tier) => (
                      <div key={tier} className={`rounded-md border px-2 py-1 ${TIER_TONE[tier]}`}>
                        <div className="text-[10px]">{TIER_USER_LABEL[tier]}</div>
                        <div className="text-base font-semibold">{plan.tier_counts[tier]}</div>
                      </div>
                    ))}
                  </div>
                  {plan.blocking_issues.length > 0 ? (
                    <ul className="mt-2 list-disc pl-4 text-[11px] text-rose-200">
                      {plan.blocking_issues.map((issue) => (
                        <li key={issue}>{issue}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>

                <ol className="space-y-2">
                  {plan.steps.map((step) => (
                    <li
                      key={`${step.index}-${step.operation}`}
                      className={`rounded-md border px-3 py-2 text-xs ${TIER_TONE[step.tier]}`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="font-medium">{OPERATION_LABELS[step.operation] || step.operation}</div>
                        <div className="text-[10px] opacity-80">{TIER_USER_LABEL[step.tier]}</div>
                      </div>
                      {step.description && step.description !== TIER_LABEL[step.tier] ? (
                        <div className="mt-1 text-[11px] text-slate-200/80">{step.description}</div>
                      ) : null}
                      {step.requires_confirmation ? (
                        <div className="mt-1 text-[10px]">执行前会请你确认</div>
                      ) : null}
                    </li>
                  ))}
                </ol>

                <details className="rounded-md border border-slate-800 bg-slate-900/40 p-3 text-[11px] text-slate-300">
                  <summary className="cursor-pointer text-slate-200">高级：证据包与作用域</summary>
                  <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap text-[10px] text-slate-400">
{safeStringify({
  scope: plan.scope,
  evidence_snapshot: plan.evidence_snapshot,
  preconditions: plan.preconditions,
  approval_policy: plan.approval_policy,
  cost_envelope: plan.cost_envelope,
  rollback_anchor: plan.rollback_anchor,
})}
                  </pre>
                </details>

                <section className="rounded-md border border-violet-500/30 bg-violet-500/5 p-3 text-xs">
                  <div className="font-medium text-violet-100">需要更深入的 AI 建议吗？</div>
                  <div className="mt-1 text-[11px] leading-5 text-slate-400">
                    可以先查看 AI 会依据哪些项目资料分析。预览不调用模型；确认后只保存建议，不会自动改内容或提交生成。
                  </div>
                  {!draftPreview ? (
                    <button type="button" onClick={() => void onPreviewDraft()} disabled={draftPending} className="mt-3 rounded-md border border-violet-400/50 px-3 py-1.5 text-[11px] font-medium text-violet-100 hover:bg-violet-500/15 disabled:opacity-60">
                      {draftPending ? '正在准备…' : '查看 AI 分析预览'}
                    </button>
                  ) : (
                    <>
                      <div className="mt-3 rounded-md border border-slate-700 bg-slate-950/70 p-2 text-[11px] text-slate-300">
                        将使用：{draftPreview.model.name} · {draftPreview.model.model_name || draftPreview.model.provider}<br />
                        预计用量：{draftPreview.estimated_tokens}；{draftPreview.cost_notice}
                        {attachments.length > 0 ? <div className="mt-1 text-slate-400">
                          已附加 {attachments.length} 个资料。文档会作为参考摘录发送；{draftPreview.attachment_capabilities?.images_sent_to_model ? '图片会作为视觉参考发送给当前模型。' : attachments.some((item) => item.kind === 'image') ? (draftPreview.attachment_capabilities?.model_supports_vision ? 'Agent 当前未允许读取图片，图片只提供文件信息。' : '当前模型未标记视觉理解能力，图片只提供文件信息。') : '没有图片资料。'}
                        </div> : null}
                      </div>
                      <details className="mt-2 rounded-md border border-slate-700 bg-slate-950/40 p-2">
                        <summary className="cursor-pointer text-[11px] text-slate-200">高级：查看 AI 分析依据</summary>
                        <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap text-[10px] text-slate-400">{safeStringify({ system_prompt: draftPreview.system_prompt, user_prompt: draftPreview.user_prompt, evidence: draftPreview.evidence })}</pre>
                      </details>
                      {!draftResult ? (
                        <button type="button" onClick={() => void onInvokeDraft()} disabled={draftPending} className="mt-3 rounded-md border border-amber-400/60 bg-amber-500/10 px-3 py-1.5 text-[11px] font-medium text-amber-100 hover:bg-amber-500/20 disabled:opacity-60">
                          {draftPending ? '正在生成建议…' : '确认生成 AI 建议'}
                        </button>
                      ) : (
                        <div className="mt-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-2 text-[11px] text-emerald-100">
                          <div className="font-medium">AI 建议已保存（尚未执行）</div>
                          <div className="mt-1">{draftResult.draft.summary}</div>
                          <div className="mt-1 whitespace-pre-wrap text-emerald-100/80">{draftResult.draft.analysis}</div>
                          {draftResult.draft.recommended_steps.length > 0 ? <div className="mt-2">建议：{safeStringify(draftResult.draft.recommended_steps)}</div> : null}
                          {draftResult.draft.risks.length > 0 ? <div className="mt-1 text-amber-100">风险：{safeStringify(draftResult.draft.risks)}</div> : null}
                        </div>
                      )}
                      {context?.book_id ? <button type="button" onClick={() => void onLoadAudit()} disabled={draftPending} className="mt-3 rounded-md border border-slate-600 px-3 py-1.5 text-[11px] text-slate-200 hover:bg-slate-800 disabled:opacity-60">查看本项目 Agent 审计</button> : null}
                      {context?.book_id ? <button type="button" onClick={() => void onLoadTimeline()} disabled={draftPending} className="ml-2 mt-3 rounded-md border border-slate-600 px-3 py-1.5 text-[11px] text-slate-200 hover:bg-slate-800 disabled:opacity-60">查看会话时间线</button> : null}
                      {auditEntries ? <details className="mt-2 rounded-md border border-slate-700 bg-slate-950/50 p-2" open><summary className="cursor-pointer text-[11px] text-slate-200">最近 {auditEntries.length} 条审计记录</summary><div className="mt-2 space-y-2">{auditEntries.map((entry) => <div key={entry.id} className="rounded border border-slate-800 p-2 text-[10px]"><div>{entry.model.name || 'Agent 模型'} · {entry.result_status}</div><div className="mt-1">{entry.draft.summary || entry.result_message}</div>{auditUsageLabel(entry) ? <div className="mt-1 text-slate-500">{auditUsageLabel(entry)}</div> : null}<button type="button" onClick={() => void onLoadHandoffs(entry.id)} className="mt-2 text-violet-200 underline">查看可承接动作</button></div>)}</div></details> : null}
                      {handoffActions ? <div className="mt-2 rounded-md border border-sky-500/30 bg-sky-500/5 p-2 text-[11px]"><div className="font-medium text-sky-100">候选草案可承接动作</div>{handoffActions.length ? handoffActions.map((action) => <div key={`${action.kind}-${action.route}`} className="mt-2 rounded border border-slate-700 p-2"><div className="text-slate-100">{action.label} · {action.tier} 档{action.requires_confirmation ? ' · 需确认' : ''}</div><div className="mt-1 text-slate-400">{action.guard}</div></div>) : <div className="mt-1 text-slate-400">当前候选没有可安全承接的动作。</div>}</div> : null}
                      {timeline ? <details className="mt-2 rounded-md border border-slate-700 bg-slate-950/50 p-2"><summary className="cursor-pointer text-[11px] text-slate-200">会话时间线（{timeline.length}）</summary><ol className="mt-2 space-y-1 text-[10px] text-slate-400">{timeline.map((event) => <li key={`${event.kind}-${event.id}`} className="rounded border border-slate-800 p-1.5"><span className="text-slate-200">{event.kind} · {event.status}</span>{event.tier ? <span> · {event.tier} 档</span> : null}<div>{event.summary}</div>{event.kind === 'session' && (event.status === 'paused' || event.status === 'awaiting_confirmation' || event.status === 'draft' || event.status === 'running') ? <button type="button" disabled={draftPending} onClick={() => void onSetSessionPaused(event.session_id, event.status !== 'paused')} className="mt-1 text-violet-200 underline">{event.status === 'paused' ? '恢复至等待确认' : '暂停会话'}</button> : null}</li>)}</ol></details> : null}
                    </>
                  )}
                </section>
              </section>
            ) : null}

            {(auditEntries || timeline) ? (
              <section className="mt-4 rounded-md border border-slate-800 bg-slate-900/40 p-3 text-xs" aria-label="智能导演台会话回放">
                <div className="font-medium text-slate-200">会话回放</div>
                <div className="mt-1 text-[11px] leading-5 text-slate-400">以下是当前项目的已保存候选建议与状态；打开它们不会执行任何生产操作。</div>
                {usageSummary ? <div className="mt-2 rounded border border-slate-800 bg-slate-950/40 p-2 text-[10px] text-slate-400" aria-label="Agent累计用量">
                  <span className="text-slate-200">本项目累计用量：</span>输入 {usageSummary.prompt_tokens} · 输出 {usageSummary.completion_tokens} · 总计 {usageSummary.total_tokens}
                  {usageSummary.cache_observable ? ` · 缓存命中 ${(Number(usageSummary.cache_hit_rate ?? 0) * 100).toFixed(1)}%` : ' · 缓存命中率不可观测'}
                  {usageSummary.average_latency_ms == null ? '' : ` · 平均 ${Math.round(usageSummary.average_latency_ms)}ms`}
                </div> : null}
                {auditEntries?.length ? (
                  <div className="mt-3 space-y-2">
                    {auditEntries.slice(0, 5).map((entry) => (
                      <div key={entry.id} className="rounded border border-slate-800 bg-slate-950/50 p-2 text-[11px]">
                        <div className="text-slate-200">{entry.model.name || 'Agent 模型'} · {entry.result_status}</div>
                        {auditUsageLabel(entry) ? <div className="mt-1 text-[10px] text-slate-500">{auditUsageLabel(entry)}</div> : null}
                        <div className="mt-1 text-slate-400">{entry.draft.summary || entry.result_message}</div>
                        {entry.result_status === 'succeeded' ? <button type="button" onClick={() => void onLoadHandoffs(entry.id)} className="mt-2 text-violet-200 underline">查看可承接动作</button> : null}
                      </div>
                    ))}
                  </div>
                ) : <div className="mt-2 text-[11px] text-slate-500">当前项目尚无可回放的 Agent 候选建议。</div>}
                {timeline?.length ? <div className="mt-3 text-[11px] text-slate-500">已加载 {timeline.length} 条会话事件。</div> : null}
                {handoffActions ? <div className="mt-3 rounded border border-sky-500/30 bg-sky-500/5 p-2 text-[11px]"><div className="font-medium text-sky-100">可承接动作</div>{handoffActions.length ? handoffActions.map((action) => <div key={`${action.kind}-${action.route}`} className="mt-2 text-slate-300">{action.label} · {action.tier} 档{action.requires_confirmation ? ' · 仍需确认' : ''}<div className="mt-1 text-slate-500">{action.guard}</div></div>) : <div className="mt-1 text-slate-400">当前候选没有可安全承接的动作。</div>}</div> : null}
              </section>
            ) : null}
          </div>
          {plan ? <footer className="border-t border-slate-800 bg-slate-950 px-4 py-3">
            <label className="sr-only" htmlFor="agent-follow-up">继续告诉 AI 导演助手</label>
            <div className="rounded-xl border border-slate-700 bg-slate-900 p-2 focus-within:border-violet-400">
              {attachments.length > 0 ? <div className="mb-2 flex flex-wrap gap-1.5" aria-label="本轮已附加资料">
                {attachments.map((attachment) => <div key={attachment.id} className="flex max-w-full items-center gap-1.5 rounded border border-slate-700 bg-slate-950/70 px-2 py-1 text-[10px] text-slate-300">
                  <span aria-hidden>{attachment.kind === 'image' ? '🖼️' : '📄'}</span><span className="max-w-[150px] truncate">{attachment.filename}</span>
                  <button type="button" aria-label={`移除 ${attachment.filename}`} onClick={() => { setAttachments((current) => current.filter((item) => item.id !== attachment.id)); setDraftPreview(null); setDraftResult(null) }} className="text-slate-500 hover:text-white">×</button>
                </div>)}
              </div> : null}
              <textarea id="agent-follow-up" value={objective} onChange={(event) => setObjective(event.target.value)} rows={2} placeholder="继续追问，或告诉我下一件想做的事…" className="min-h-[38px] w-full resize-none bg-transparent px-1 py-1 text-sm text-slate-100 outline-none placeholder:text-slate-500" />
              <div className="mt-2 flex items-center justify-between gap-2 border-t border-slate-800 pt-2">
                <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-slate-700 px-2.5 py-1.5 text-[11px] text-slate-300 transition hover:border-violet-400/50 hover:text-violet-100">
                  <span aria-hidden>📎</span> 添加附件
                  <input aria-label="添加图片或文档" className="sr-only" type="file" multiple accept=".png,.jpg,.jpeg,.webp,.txt,.md,.pdf,.docx" disabled={uploading || !context?.book_id} onChange={(event) => { void onSelectAttachments(event.target.files); event.currentTarget.value = '' }} />
                </label>
                <button type="button" onClick={onSubmit} disabled={pending} className="rounded-lg bg-violet-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-violet-500 disabled:bg-slate-700">{pending ? '分析中…' : '发送'}</button>
              </div>
            </div>
            <div className="mt-1 text-[10px] text-slate-500">继续对话只会生成建议；修改内容、调用模型或提交生成仍会单独确认。</div>
          </footer> : null}
        </aside>
      ) : null}
    </>
  )
}
