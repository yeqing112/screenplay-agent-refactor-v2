import { describe, expect, it } from 'vitest'
import { buildAgentTaskCenterEntries } from './productWorkspaceAgentTasks'

describe('buildAgentTaskCenterEntries', () => {
  it('shows awaiting confirmation as an attention item without inventing a production task', () => {
    const [entry] = buildAgentTaskCenterEntries([
      { kind: 'session', id: 9, session_id: 9, status: 'awaiting_confirmation', at: '2026-09-06T10:00:00Z', summary: '审阅镜头连续性', evidence_fingerprint: 'evidence-1' },
      { kind: 'plan', id: 10, session_id: 9, status: 'draft', at: '2026-09-06T10:00:00Z', summary: '审阅镜头连续性', plan_fingerprint: 'plan-1' },
    ])
    expect(entry).toMatchObject({
      id: 'agent-session-9', type: '智能导演台', status: 'queued', actionLabel: '打开智能导演台',
      agentMeta: { sessionId: 9, evidenceFingerprint: 'evidence-1', planFingerprint: 'plan-1' },
    })
    expect(entry.detail).toContain('尚未执行任何生产操作')
  })

  it('surfaces a failed external call as an error that requires re-preview', () => {
    const [entry] = buildAgentTaskCenterEntries([
      { kind: 'session', id: 3, session_id: 3, status: 'blocked', at: '2026-09-06T10:00:00Z', summary: '诊断项目' },
      { kind: 'audit', id: 4, session_id: 3, status: 'failed', at: '2026-09-06T10:00:01Z', summary: 'provider failed', operation: 'generate_llm_draft', tier: 'D' },
    ])
    expect(entry.status).toBe('error')
    expect(entry.progress).toBe('需要重新预览')
    expect(entry.detail).toContain('未自动重试')
  })

  it('surfaces an unread proactive project update without turning it into a production task', () => {
    const [entry] = buildAgentTaskCenterEntries([
      { kind: 'project_update', id: 22, session_id: 0, status: 'unread', at: '2026-09-07T10:00:00Z', summary: '最近一次视频任务失败', operation: 'failure', tier: 'A', evidence_fingerprint: 'evidence-22' },
    ])
    expect(entry).toMatchObject({ id: 'agent-update-22', type: '项目动态', status: 'error', actionLabel: '打开智能导演台' })
  })

  it('keeps a confirmed handoff visible until the formal workbench finishes it', () => {
    const [entry] = buildAgentTaskCenterEntries([
      { kind: 'session', id: 12, session_id: 12, status: 'accepted', at: '2026-09-08T10:00:00Z', summary: '提交镜头视频' },
      { kind: 'audit', id: 13, session_id: 12, status: 'handoff_confirmed', at: '2026-09-08T10:00:01Z', summary: '已确认承接', operation: 'chat_turn', tier: 'D' },
    ])
    expect(entry).toMatchObject({ status: 'queued', progress: '已确认，待工作台处理' })
    expect(entry.detail).toContain('完成最终证据校验')
  })
})
