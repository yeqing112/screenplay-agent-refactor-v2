import type { AgentTimelineEvent } from '../services/agent'
import type { TaskCenterEntry } from './productWorkspaceTasks'

/** Keep Agent events distinct from CreativeTask records, while presenting items
 * needing a human decision in the task-center vocabulary. */
export function buildAgentTaskCenterEntries(events: AgentTimelineEvent[]): TaskCenterEntry[] {
  const sessions = events.filter((event) => event.kind === 'session')
  const projectUpdates = events.filter((event) => event.kind === 'project_update' && (event.status === 'unread' || event.status === 'acknowledged'))
  const related = new Map<number, AgentTimelineEvent[]>()
  for (const event of events) related.set(event.session_id, [...(related.get(event.session_id) ?? []), event])
  const sessionEntries: TaskCenterEntry[] = sessions.map((session) => {
    const activity = related.get(session.session_id) ?? []
    const latestAudit = activity.find((event) => event.kind === 'audit')
    const state = String(session.status || '').trim()
    const handoffConfirmed = latestAudit?.status === 'handoff_confirmed'
    const failed = latestAudit?.status === 'failed' || state === 'blocked'
    return {
      id: `agent-session-${session.session_id}`,
      type: '智能导演台',
      target: session.summary || `Agent 会话 #${session.session_id}`,
      status: (failed ? 'error' : handoffConfirmed ? 'queued' : state === 'awaiting_confirmation' || state === 'draft' ? 'queued' : state === 'paused' ? 'skipped' : state === 'running' ? 'running' : 'done') as TaskCenterEntry['status'],
      progress: failed ? '需要重新预览' : handoffConfirmed ? '已确认，待工作台处理' : state === 'awaiting_confirmation' ? '等待你审核候选草案' : state === 'paused' ? '已暂停' : state === 'running' ? '分析中' : state === 'draft' ? '候选草案待审核' : '已归档',
      detail: failed ? '模型调用失败，系统未自动重试。请在智能导演台重新预览后再次确认。' : handoffConfirmed ? '你已确认承接这一步；请在正式工作台完成最终证据校验和实际操作，Agent 不会代替工作台执行。' : state === 'awaiting_confirmation' ? '候选建议已保存，尚未执行任何生产操作。请在智能导演台审阅后，按原工作台门禁承接。' : state === 'paused' ? '此会话已暂停；暂停不会取消、重试或改动任何图片、视频和生产任务。' : session.summary || '智能导演台历史会话。',
      statusReason: state === 'paused' ? '会话被人工暂停，未改动生产内容' : failed ? '真实模型调用失败，需人工重新确认' : undefined,
      retryable: false, actionLabel: '打开智能导演台', actionTarget: 'storyboard', episode: null, scope: 'global',
      agentMeta: {
        sessionId: session.session_id, sessionStatus: state, evidenceFingerprint: session.evidence_fingerprint,
        planFingerprint: latestAudit?.plan_fingerprint ?? activity.find((event) => event.kind === 'plan')?.plan_fingerprint,
        operation: latestAudit?.operation,
      },
    }
  })
  const updateEntries = projectUpdates
    .filter((event) => event.operation === 'failure' || event.tier === 'D' || event.status === 'unread')
    .map((event) => ({
      id: `agent-update-${event.id}`,
      type: '项目动态',
      target: '智能导演台',
      status: event.operation === 'failure' ? 'error' as const : 'blocked' as const,
      progress: event.operation === 'failure' ? '任务失败' : '需要关注',
      detail: event.summary || '智能导演台发现一条需要关注的项目动态。',
      statusReason: '项目状态发生变化，建议查看智能导演台详情',
      retryable: false,
      actionLabel: '打开智能导演台',
      actionTarget: 'storyboard' as const,
      episode: null,
      scope: 'global' as const,
      agentMeta: { sessionId: event.session_id, sessionStatus: event.status, evidenceFingerprint: event.evidence_fingerprint, operation: event.operation },
    }))
  return [...sessionEntries, ...updateEntries]
}
