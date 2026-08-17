import { describe, expect, it } from 'vitest'
import { buildScriptEpisodeSummaries, parseScriptScenes } from './productWorkspaceScripts'
import type { EpisodeProgress } from './productWorkspaceProgress'

const episodeProgress: EpisodeProgress[] = [
  {
    episode: 1,
    statusLabel: '待出图',
    progressLabel: '已有 24 镜，待生成分镜图片',
    blockerCount: 2,
    nextAction: '编译提示词并出图',
  },
]

describe('buildScriptEpisodeSummaries', () => {
  it('blocks release when adaptation is not locked', () => {
    const summaries = buildScriptEpisodeSummaries({
      scripts: [{ episode: 1, content: '第一集剧本', status: 'done' }],
      episodeProgress,
      qaWorkbench: { episodes: [] },
      shotsByEpisode: {},
      scriptDecisionState: {},
      hasLockedAdaptation: false,
    })

    expect(summaries[0].releaseStatus).toBe('blocked')
    expect(summaries[0].releaseLabel).toBe('缺改编方向')
  })

  it('blocks release when script qa still has open issues', () => {
    const summaries = buildScriptEpisodeSummaries({
      scripts: [{ episode: 1, content: '姐姐看向阿宁，气氛骤冷。', status: 'done' }],
      episodeProgress,
      qaWorkbench: {
        episodes: [
          {
            episode: 1,
            issues: [
              {
                issue_id: 'issue-1',
                type: 'script_logic',
                title: '人物动机偏弱',
                description: '这一段人物情绪转折缺少铺垫。',
                fix_status: 'pending',
              },
              {
                issue_id: 'issue-2',
                type: 'storyboard_prompt',
                title: '镜头提示词过空',
                description: '镜头 1-2 的构图指令太弱。',
                fix_status: 'pending',
                meta_info: { shot_id: '1-2' },
              },
            ],
            versions: [{ version_no: 2 }],
          },
        ],
      },
      shotsByEpisode: { 1: [{ shot_id: '1-2', scene_name: '天台' } as any] },
      scriptDecisionState: {
        '1': {
          lockedAt: '2026-07-10T10:00:00.000Z',
          releasedAt: null,
          note: '',
        },
      },
      hasLockedAdaptation: true,
    })

    expect(summaries[0].openScriptIssueCount).toBe(1)
    expect(summaries[0].openNonScriptIssueCount).toBe(1)
    expect(summaries[0].releaseStatus).toBe('blocked')
    expect(summaries[0].releaseLabel).toBe('脚本 QA 未清')
  })

  it('marks release ready when script is locked, clean, and not yet storyboarded', () => {
    const summaries = buildScriptEpisodeSummaries({
      scripts: [{ episode: 2, content: '第二集剧本', status: 'done' }],
      episodeProgress: [
        {
          episode: 2,
          statusLabel: '待放行',
          progressLabel: '剧本已锁稿，待放行到分镜',
          blockerCount: 1,
          nextAction: '回剧本工作台放行到分镜',
        },
      ],
      qaWorkbench: {
        episodes: [
          {
            episode: 2,
            qa_summary: { overall_score: 92 },
            issues: [],
            versions: [{ version_no: 1 }, { version_no: 2 }],
          },
        ],
      },
      shotsByEpisode: {},
      scriptDecisionState: {
        '2': {
          lockedAt: '2026-07-10T10:00:00.000Z',
          releasedAt: '2026-07-10T10:05:00.000Z',
          note: '',
        },
      },
      hasLockedAdaptation: true,
    })

    expect(summaries[0].releaseStatus).toBe('done')
    expect(summaries[0].releaseLabel).toBe('可进分镜')
    expect(summaries[0].overallScore).toBe(92)
    expect(summaries[0].versionCount).toBe(2)
  })

  it('tracks structured scene count when script scenes are available', () => {
    const summaries = buildScriptEpisodeSummaries({
      scripts: [
        {
          episode: 3,
          status: 'done',
          content: `
**场景一：[水房·清晨]**
- 时间：清晨
- 地点：寺庙后院水房
- 人物：和尚甲、和尚乙

**[冷水泼下，和尚甲猛地睁眼]**

**场景二：[院落·日间]**
- 时间：日间
- 地点：寺庙院落
- 人物：和尚甲、和尚丙

**[和尚甲挑水走进院子]**
`,
        },
      ],
      episodeProgress: [],
      qaWorkbench: { episodes: [] },
      shotsByEpisode: {},
      scriptDecisionState: {
        '3': {
          lockedAt: '2026-07-10T10:00:00.000Z',
          releasedAt: null,
          note: '',
        },
      },
      hasLockedAdaptation: true,
    })

    expect(summaries[0].sceneCount).toBe(2)
  })
})

describe('parseScriptScenes', () => {
  it('extracts structured scene summaries from script markdown', () => {
    const scenes = parseScriptScenes(`
**场景一：[水房·清晨]**
- 时间：清晨
- 地点：寺庙后院水房
- 人物：和尚甲、和尚乙、和尚丙

**[画面开场：一桶冷水兜头泼下]**

**场景二：[寺庙院落·日间]**
- 时间：正午
- 地点：寺庙院落
- 人物：和尚甲、和尚丙

**[和尚甲挑着两桶水，从山门走进来]**
`)

    expect(scenes).toHaveLength(2)
    expect(scenes[0]).toMatchObject({
      title: '水房·清晨',
      timeLabel: '清晨',
      locationLabel: '寺庙后院水房',
      characterLabel: '和尚甲、和尚乙、和尚丙',
    })
    expect(scenes[0].beatPreview).toContain('画面开场')
    expect(scenes[1].title).toBe('寺庙院落·日间')
  })
})
