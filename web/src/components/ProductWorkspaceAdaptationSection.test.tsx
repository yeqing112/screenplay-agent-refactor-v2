import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ProductWorkspaceAdaptationSection from './ProductWorkspaceAdaptationSection'

const baseOption = {
  id: 'plan-a',
  name: '强情绪悬疑向',
  strength: '轻改',
  audience: '女性短剧',
  rhythm: '前快后稳',
  hook: '错认与反转',
  keep: '核心人物关系',
  enhance: '冲突密度',
  risk: '注意控制狗血感',
}

describe('ProductWorkspaceAdaptationSection', () => {
  it('shows the backfill detail instead of fake locked copy when downstream exists but adaptation is not locked', () => {
    const html = renderToStaticMarkup(
      <ProductWorkspaceAdaptationSection
        contentReady
        adaptationOptions={[baseOption]}
        selectedAdaptationId={null}
        selectedAdaptationName={null}
        adaptationCustomNote=""
        hasLockedAdaptation={false}
        adaptationStateLabel="待补锁"
        adaptationStateDetail="当前项目已有下游产出，建议尽快补锁一个项目级主方向，避免后续风格漂移。"
        canGenerateCandidates
        canLockAdaptation={false}
        onRegenerate={() => {}}
        onSelect={() => {}}
        onCustomNoteChange={() => {}}
        onLock={() => {}}
        onUnlock={() => {}}
      />,
    )

    expect(html).toContain('待补锁')
    expect(html).toContain('建议尽快补锁一个项目级主方向')
    expect(html).not.toContain('当前主方向：已锁定主方向')
  })

  it('hides the lock action once the adaptation has been locked', () => {
    const html = renderToStaticMarkup(
      <ProductWorkspaceAdaptationSection
        contentReady
        adaptationOptions={[baseOption]}
        selectedAdaptationId="plan-a"
        selectedAdaptationName="强情绪悬疑向"
        adaptationCustomNote=""
        hasLockedAdaptation
        adaptationStateLabel="已锁定"
        adaptationStateDetail="当前主方向已经锁定。"
        canGenerateCandidates={false}
        canLockAdaptation={false}
        onRegenerate={() => {}}
        onSelect={() => {}}
        onCustomNoteChange={() => {}}
        onLock={() => {}}
        onUnlock={() => {}}
      />,
    )

    expect(html).toContain('解除锁定')
    expect(html).not.toContain('锁定为主方向')
  })

  it('collapses an already locked Production Skill but keeps its adjustment route', () => {
    const html = renderToStaticMarkup(
      <ProductWorkspaceAdaptationSection
        contentReady
        productionSkill={{
          skillOptions: [{
            id: 'mystery',
            name: '悬疑 Production Skill',
            summary: '高压悬疑短剧生产规范',
            tracks: ['悬疑'],
            platforms: ['douyin'],
          }],
          selectedSkillId: 'mystery',
          platform: 'douyin',
          track: '悬疑',
          emotionGoal: '高压',
          rhythmStrength: 'strong_hooks',
          visualStyle: 'cinematic_realism',
          priorities: ['storyboard'],
          enforcement: 'strict',
          customNote: '',
          lockedAt: '2026-09-06T00:00:00Z',
          runtimeSummary: {
            skill_name: '悬疑 Production Skill',
            platform: 'douyin',
            track: '悬疑',
            emotion_goal: '高压',
            rhythm_strength: 'strong_hooks',
            visual_style: 'cinematic_realism',
            priorities: ['storyboard'],
            enforcement: 'strict',
            locked: true,
            custom_note: '',
          },
        }}
        adaptationOptions={[baseOption]}
        selectedAdaptationId="plan-a"
        selectedAdaptationName="强情绪悬疑向"
        adaptationCustomNote=""
        hasLockedAdaptation
        adaptationStateLabel="已锁定"
        adaptationStateDetail="当前主方向已经锁定。"
        canGenerateCandidates={false}
        canLockAdaptation={false}
        onRegenerate={() => {}}
        onSelect={() => {}}
        onCustomNoteChange={() => {}}
        onLock={() => {}}
        onUnlock={() => {}}
      />,
    )

    expect(html).toContain('高级：查看或调整已锁定的 Production Skill')
    expect(html).toContain('解除 Skill 锁定')
    expect(html).not.toContain('<details open=""')
  })

  it('shows upstream handoff guidance before and after project-level lock', () => {
    const pendingHtml = renderToStaticMarkup(
      <ProductWorkspaceAdaptationSection
        contentReady
        adaptationOptions={[baseOption]}
        selectedAdaptationId="plan-a"
        selectedAdaptationName="强情绪悬疑向"
        adaptationCustomNote=""
        hasLockedAdaptation={false}
        adaptationStateLabel="待锁定"
        adaptationStateDetail="当前主方向还未锁定。"
        canGenerateCandidates
        canLockAdaptation
        onRegenerate={() => {}}
        onSelect={() => {}}
        onCustomNoteChange={() => {}}
        onLock={() => {}}
        onUnlock={() => {}}
      />,
    )

    expect(pendingHtml).toContain('上游交接状态')
    expect(pendingHtml).toContain('候选方向已选定')
    expect(pendingHtml).toContain('待确认')
    expect(pendingHtml).toContain('完成锁定后即可继续剧本工作台')
    expect(pendingHtml).toContain('已选中候选方向：强情绪悬疑向')
    expect(pendingHtml).toContain('当前已满足锁定条件。锁定后')

    const lockedHtml = renderToStaticMarkup(
      <ProductWorkspaceAdaptationSection
        contentReady
        adaptationOptions={[baseOption]}
        selectedAdaptationId="plan-a"
        selectedAdaptationName="强情绪悬疑向"
        adaptationCustomNote=""
        hasLockedAdaptation
        adaptationStateLabel="已锁定"
        adaptationStateDetail="当前主方向已经锁定。"
        canGenerateCandidates={false}
        canLockAdaptation={false}
        onRegenerate={() => {}}
        onSelect={() => {}}
        onCustomNoteChange={() => {}}
        onLock={() => {}}
        onUnlock={() => {}}
      />,
    )

    expect(lockedHtml).toContain('允许进入剧本工作台')
    expect(lockedHtml).toContain('已就绪')
    expect(lockedHtml).toContain('下一步应进入剧本工作台')
  })

  it('shows next-step CTA for upstream backtrack and downstream handoff', () => {
    const contentHtml = renderToStaticMarkup(
      <ProductWorkspaceAdaptationSection
        contentReady={false}
        adaptationOptions={[]}
        selectedAdaptationId={null}
        selectedAdaptationName={null}
        adaptationCustomNote=""
        hasLockedAdaptation={false}
        adaptationStateLabel="待内容准备"
        adaptationStateDetail="需要先完成内容准备。"
        canGenerateCandidates={false}
        canLockAdaptation={false}
        onRegenerate={() => {}}
        onSelect={() => {}}
        onCustomNoteChange={() => {}}
        onLock={() => {}}
        onUnlock={() => {}}
        onNavigateSection={() => {}}
      />,
    )

    expect(contentHtml).toContain('返回内容准备')

    const scriptsHtml = renderToStaticMarkup(
      <ProductWorkspaceAdaptationSection
        contentReady
        adaptationOptions={[]}
        selectedAdaptationId="plan-a"
        selectedAdaptationName="强情绪悬疑向"
        adaptationCustomNote=""
        hasLockedAdaptation
        adaptationStateLabel="已锁定"
        adaptationStateDetail="当前主方向已经锁定。"
        canGenerateCandidates={false}
        canLockAdaptation={false}
        onRegenerate={() => {}}
        onSelect={() => {}}
        onCustomNoteChange={() => {}}
        onLock={() => {}}
        onUnlock={() => {}}
        onNavigateSection={() => {}}
      />,
    )

    expect(scriptsHtml).toContain('进入剧本工作台')
  })
})
