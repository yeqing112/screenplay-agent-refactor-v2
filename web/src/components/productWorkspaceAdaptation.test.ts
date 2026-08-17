import { describe, expect, it } from 'vitest'
import { buildAdaptationOptions, getSelectedAdaptation } from './productWorkspaceAdaptation'

describe('productWorkspaceAdaptation', () => {
  it('builds three structured adaptation options', () => {
    const options = buildAdaptationOptions({
      title: '天台之后',
      chapterCount: 18,
      wordCount: 86000,
      scriptExcerpt: '# 第1集：姐姐转身看向阿宁\n\n**场景一：[雨夜屋檐]** 风里有危险的停顿。',
    })

    expect(options).toHaveLength(3)
    expect(options[0]).toMatchObject({
      id: 'emotion-suspense',
      name: '竖屏情绪悬疑短剧',
    })
    expect(options[0].keep).toContain('18 章素材')
    expect(options[0].hook).toContain('天台之后')
    expect(options[0].keep).not.toContain('#')
    expect(options[0].keep).not.toContain('**')
  })

  it('resolves the currently selected option', () => {
    const options = buildAdaptationOptions({
      title: '测试项目',
      chapterCount: 0,
      wordCount: 12000,
    })

    expect(getSelectedAdaptation(options, 'urban-relationship')?.name).toBe('都市关系流连续短剧')
    expect(getSelectedAdaptation(options, 'missing')).toBeNull()
  })
})
