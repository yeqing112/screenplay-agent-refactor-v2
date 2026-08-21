import type { ComponentProps } from 'react'
import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import ProductWorkspaceContentSection from './ProductWorkspaceContentSection'

function renderSection(overrides: Partial<ComponentProps<typeof ProductWorkspaceContentSection>> = {}) {
  return renderToStaticMarkup(
    <ProductWorkspaceContentSection
      bookId={1}
      contentReady={false}
      contentStatusLabel="待补内容"
      contentStatusDetail="当前还没有正式内容基础。"
      chapterCount={0}
      wordCount={0}
      projectStatus="draft"
      uploadFile={null}
      episodeCount={12}
      shortTitle=""
      shortText=""
      contentTask={{ mode: 'upload', status: 'idle', message: '尚未开始导入。' }}
      onOpenModelSettings={() => {}}
      onUploadFileChange={() => {}}
      onEpisodeCountChange={() => {}}
      onShortTitleChange={() => {}}
      onShortTextChange={() => {}}
      onSubmitNovelUpload={() => {}}
      onSubmitShortCreate={() => {}}
      {...overrides}
    />,
  )
}

describe('ProductWorkspaceContentSection', () => {
  it('shows the content workbench summary for draft-stage projects', () => {
    const html = renderSection({
      shortTitle: '雨夜来信',
      shortText: '第一章：雨夜叩门。',
      contentTask: { mode: 'short', status: 'idle', message: '尚未开始导入。' },
    })

    expect(html).toContain('内容整理台')
    expect(html).toContain('短篇录入链路')
    expect(html).toContain('短篇草稿：雨夜来信')
    expect(html).toContain('目标 12 集')
    expect(html).toContain('将以目标 12 集导入短篇《雨夜来信》。')
  })

  it('shows formal content context once the project already has structured source material', () => {
    const html = renderSection({
      contentReady: true,
      chapterCount: 24,
      wordCount: 86000,
      projectStatus: 'script_locked',
    })

    expect(html).toContain('已接入正式内容')
    expect(html).toContain('24 章 / 约 8.6 万字')
    expect(html).toContain('可以继续进入改编方向')
  })

  it('disables submit actions and surfaces preflight hints when draft inputs are incomplete', () => {
    const html = renderSection()

    expect(html).toContain('请先选择原文文件，再发起长篇导入。')
    expect(html).toContain('请先填写短篇标题和正文，再发起短篇导入。')
    expect(html).toContain('disabled')
  })
})
