import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import ProductWorkspaceStoryboardSection from './ProductWorkspaceStoryboardSection'

describe('ProductWorkspaceStoryboardSection repair action chaining', () => {
  it('upgrades prompt repair CTA to recompile-and-generate-frame when no adopted frame exists', () => {
    const html = renderToStaticMarkup(
      <ProductWorkspaceStoryboardSection
        bookId={14}
        shotsByEpisode={{
          1: [
            {
              episode: 1,
              shot_id: '1-02',
              scene_name: '寺庙后院水房',
              visual_prompt_static: '一个和尚站在院子里。',
              visual_prompt_motion: '镜头缓慢推进，保持人物和场景一致。',
              compiler_diagnostics: {
                status: 'warning',
                checks: [
                  {
                    key: 'visual_fact_target_coverage',
                    passed: false,
                    message: '这些资产没有满足首轮编译要求的视觉事实覆盖：和尚甲、木桶',
                    details: [
                      '和尚甲：至少补入 1 条视觉事实 / 湿透的灰色僧袍 / 右肩裸露',
                      '木桶：至少补入 1 条视觉事实 / 旧木桶 / 边缘磨损',
                    ],
                  },
                ],
              },
              assets: {
                images: [],
                videos: [],
                audios: [],
                references: { characters: {}, scene: [], props: {} },
              },
              reference_images: [],
            } as any,
          ],
        }}
        scriptDecisionState={{
          '1': {
            lockedAt: '2026-07-17T09:00:00.000Z',
            releasedAt: '2026-07-17T09:10:00.000Z',
            note: '',
          },
        }}
        hasExplicitLockedAdaptation
        selectedShotId="1-02"
        onSelectShot={() => {}}
        onRefresh={() => {}}
        onNavigateSection={() => {}}
        onNavigateTaskSection={() => {}}
      />,
    )

    expect(html).toContain('重编后生成首帧')
  })

  it('upgrades prompt repair CTA to recompile-and-generate-video when an adopted frame exists', () => {
    const html = renderToStaticMarkup(
      <ProductWorkspaceStoryboardSection
        bookId={14}
        shotsByEpisode={{
          1: [
            {
              episode: 1,
              shot_id: '1-03',
              scene_name: '寺庙后院',
              visual_prompt_static: '一个和尚站在院里。',
              visual_prompt_motion: '镜头缓慢推近，保持角色与场景一致。',
              compiler_diagnostics: {
                status: 'warning',
                checks: [
                  {
                    key: 'visual_fact_target_coverage',
                    passed: false,
                    message: '这些资产没有满足首轮编译要求的视觉事实覆盖：和尚甲',
                    details: ['和尚甲：至少补入 1 条视觉事实 / 右肩裸露 / 灰色僧袍'],
                  },
                ],
              },
              assets: {
                images: [
                  {
                    id: 'img-1',
                    title: '首帧 v1',
                    previewUrl: 'https://example.com/frame.png',
                    adopted: true,
                  },
                ],
                videos: [],
                audios: [],
                references: { characters: {}, scene: [], props: {} },
              },
            } as any,
          ],
        }}
        scriptDecisionState={{
          '1': {
            lockedAt: '2026-07-17T09:00:00.000Z',
            releasedAt: '2026-07-17T09:10:00.000Z',
            note: '',
          },
        }}
        hasExplicitLockedAdaptation
        selectedShotId="1-03"
        onSelectShot={() => {}}
        onRefresh={() => {}}
        onNavigateSection={() => {}}
        onNavigateTaskSection={() => {}}
      />,
    )

    expect(html).toContain('重编后继续生成视频')
  })
})
