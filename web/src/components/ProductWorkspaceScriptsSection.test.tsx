import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import ProductWorkspaceScriptsSection from './ProductWorkspaceScriptsSection'

describe('ProductWorkspaceScriptsSection', () => {
  it('shows adaptation inheritance guidance when the project direction is not locked', () => {
    const html = renderToStaticMarkup(
      <ProductWorkspaceScriptsSection
        bookId={14}
        scripts={[{ episode: 1, content: '第一集剧本内容', status: 'done' } as any]}
        shotsByEpisode={{}}
        episodeProgress={[
          {
            episode: 1,
            statusLabel: '待放行',
            progressLabel: '脚本已锁稿，待放行到分镜',
            blockerCount: 1,
            nextAction: '回剧本工作台放行到分镜',
          },
        ]}
        scriptDecisionState={{}}
        onScriptDecisionStateChange={vi.fn()}
        hasLockedAdaptation={false}
        hasExplicitLockedAdaptation={false}
        adaptationStateLabel="待补锁"
        adaptationStateDetail="当前主方向还没有锁定。"
        selectedAdaptationName={undefined}
        onNavigate={() => {}}
        onGenerateScripts={() => {}}
        isGeneratingScripts={false}
      />,
    )

    expect(html).toContain('上游约束')
    expect(html).toContain('项目级改编方向')
    expect(html).toContain('待补锁')
    expect(html).toContain('建议先回改编方向完成锁定')
  })

  it('shows the selected direction as an inherited constraint once locked', () => {
    const html = renderToStaticMarkup(
      <ProductWorkspaceScriptsSection
        bookId={14}
        scripts={[{ episode: 1, content: '第一集剧本内容', status: 'done' } as any]}
        shotsByEpisode={{}}
        episodeProgress={[
          {
            episode: 1,
            statusLabel: '待放行',
            progressLabel: '脚本已锁稿，待放行到分镜',
            blockerCount: 1,
            nextAction: '回剧本工作台放行到分镜',
          },
        ]}
        scriptDecisionState={{}}
        onScriptDecisionStateChange={vi.fn()}
        hasLockedAdaptation
        hasExplicitLockedAdaptation
        adaptationStateLabel="已锁定"
        adaptationStateDetail="当前主方向已经锁定。"
        selectedAdaptationName="强情绪悬疑向"
        onNavigate={() => {}}
        onGenerateScripts={() => {}}
        isGeneratingScripts={false}
      />,
    )

    expect(html).toContain('强情绪悬疑向')
    expect(html).toContain('后续版本、锁稿备注与分镜放行')
  })

  it('marks historical release as historical when project direction is no longer locked', () => {
    const html = renderToStaticMarkup(
      <ProductWorkspaceScriptsSection
        bookId={14}
        scripts={[{ episode: 1, content: '第一集剧本内容', status: 'done' } as any]}
        shotsByEpisode={{ 1: [{ episode: 1, shot_id: '01', scene_name: '井边' }] as any }}
        episodeProgress={[
          {
            episode: 1,
            statusLabel: '脚本 QA 未清',
            progressLabel: '项目主方向还没有锁定，暂不应继续下游生产',
            blockerCount: 1,
            nextAction: '优先处理脚本 QA',
          },
        ]}
        scriptDecisionState={{
          '1': {
            lockedAt: '2026-07-17T10:00:00.000Z',
            releasedAt: '2026-07-17T10:30:00.000Z',
            note: 'history',
          },
        }}
        onScriptDecisionStateChange={vi.fn()}
        hasLockedAdaptation={false}
        hasExplicitLockedAdaptation={false}
        adaptationStateLabel="待补锁"
        adaptationStateDetail="当前主方向还没有锁定。"
        selectedAdaptationName={undefined}
        onNavigate={() => {}}
        onGenerateScripts={() => {}}
        isGeneratingScripts={false}
      />,
    )

    expect(html).toContain('历史已放行')
    expect(html).toContain('历史曾放行，但当前不应继续下游')
    expect(html).toContain('当前项目主方向还没有锁定')
    expect(html).toContain('disabled')
  })

  it('keeps script QA and version history out of the initial editing view', () => {
    const html = renderToStaticMarkup(
      <ProductWorkspaceScriptsSection
        bookId={14}
        scripts={[{ episode: 1, content: '第一集剧本内容', status: 'done' } as any]}
        shotsByEpisode={{}}
        episodeProgress={[
          {
            episode: 1,
            statusLabel: '待放行',
            progressLabel: '脚本已锁稿，待放行到分镜',
            blockerCount: 1,
            nextAction: '回剧本工作台放行到分镜',
          },
        ]}
        scriptDecisionState={{}}
        onScriptDecisionStateChange={vi.fn()}
        hasLockedAdaptation
        hasExplicitLockedAdaptation
        adaptationStateLabel="已锁定"
        adaptationStateDetail="当前主方向已经锁定。"
        selectedAdaptationName="强情绪悬疑向"
        onNavigate={() => {}}
        onGenerateScripts={() => {}}
        isGeneratingScripts={false}
      />,
    )

    expect(html).toContain('高级：查看脚本 QA 与版本历史')
    expect(html).not.toContain('<details open=""')
    expect(html).toContain('锁稿 / 放行')
  })
})
