import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import ProductWorkspaceStoryboardSection, {
  buildMachinePromptApiJsonExportText,
  buildMachinePromptCsvExportText,
  buildMachinePromptMarkdownExportText,
  buildMachinePromptWebuiCopyText,
} from './ProductWorkspaceStoryboardSection'

describe('ProductWorkspaceStoryboardSection repair action chaining', () => {
  it('surfaces explicit prompt repair when legacy shots have short prompts and no scene asset binding', () => {
    const html = renderToStaticMarkup(
      <ProductWorkspaceStoryboardSection
        bookId={75}
        shotsByEpisode={{
          1: [
            {
              episode: 1,
              shot_id: '1-01',
              scene_name: '深夜便利店',
              visual_prompt_static: '便利店一角。',
              visual_prompt_motion: '镜头推进。',
              structured_shot: {
                scene_asset_id: '',
                character_asset_ids: [],
                prop_asset_ids: [],
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
        selectedShotId="1-01"
        onSelectShot={() => {}}
        onRefresh={() => {}}
        onNavigateSection={() => {}}
        onNavigateTaskSection={() => {}}
      />,
    )

    expect(html).toContain('重编提示词并补齐场景资产绑定')
    expect(html).toContain('静态提示词过短')
    expect(html).toContain('运动提示词过短')
    expect(html).toContain('缺场景资产绑定')
  })

  it('surfaces readonly machine prompt export preview entry in formal storyboard detail', () => {
    const html = renderToStaticMarkup(
      <ProductWorkspaceStoryboardSection
        bookId={75}
        shotsByEpisode={{
          1: [
            {
              episode: 1,
              shot_id: '1-01',
              scene_name: '便利店收银台',
              start_state: '林小夏倚在收银台后。',
              action_process: '风铃声响起，她身体一僵。',
              end_state: '她看向门口。',
              visual_prompt_static: '便利店收银台，中景，林小夏站在收银台后。',
              visual_prompt_motion: '固定机位，林小夏从慵懒转为警觉，保持场景和服装连续。',
              structured_shot: {
                scene_asset_id: 'scene-1',
                character_asset_ids: [],
                prop_asset_ids: [],
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
        selectedShotId="1-01"
        onSelectShot={() => {}}
        onRefresh={() => {}}
        onNavigateSection={() => {}}
        onNavigateTaskSection={() => {}}
      />,
    )

    expect(html).toContain('机器提示词导出预览')
    expect(html).toContain('导演分镜语言 → 标准机器语言 → 多模型导出')
    expect(html).toContain('加载导出预览')
    expect(html).toContain('保存导出记录')
    expect(html).toContain('刷新导出历史')
    expect(html).toContain('当前镜头导出历史')
    expect(html).toContain('导演分镜语言编辑')
    expect(html).toContain('保存并重编译导出')
    expect(html).toContain('恢复系统版')
    expect(html).toContain('导出 Markdown')
    expect(html).toContain('导出 CSV')
    expect(html).toContain('导出 API JSON')
    expect(html).toContain('API 提交')
    expect(html).toContain('待加载')
  })

  it('builds a copy-ready H3 WebUI machine prompt export block', () => {
    const preview = {
      book_id: 75,
      episode: 1,
      shot_id: 1,
      scene_name: '便利店收银台',
      api_submission: false,
      director_shot_text: '起始：林小夏倚在收银台后。',
      reference_image_count: 2,
      bound_asset_count: 3,
      machine_prompt: {
        api_submission: false,
        visual_timeline: [
          {
            phase: '起始',
            time_range_seconds: '0-1s',
            camera_instruction: '固定中景',
            visual_action: '林小夏抬头看向门口。',
          },
        ],
        soundscape: {
          overall_soundscape: '便利店冷柜低鸣。',
          non_diegetic_music: '低频悬疑铺底。',
        },
      },
      model_exports: {
        'minimax-h3': {
          target_model: 'minimax-h3',
          export_mode: 'webui_fields',
          api_submission: false,
          fields: {
            integrated_multimodal_description: '林小夏在便利店收银台后警觉抬头。',
            overall_soundscape: '风铃与冷柜低鸣。',
            non_diegetic_music: '轻微悬疑氛围。',
          },
          model_params: { duration: 4 },
        },
      },
    }
    const text = buildMachinePromptWebuiCopyText(preview)

    expect(text).toContain('# minimax-h3 WebUI 机器提示词导出')
    expect(text).toContain('API 提交：否，仅复制/导出')
    expect(text).toContain('## integrated_multimodal_description')
    expect(text).toContain('林小夏在便利店收银台后警觉抬头。')
    expect(text).toContain('"duration": 4')

    const markdown = buildMachinePromptMarkdownExportText(preview)
    expect(markdown).toContain('导出模式：Markdown / 人工审阅')
    expect(markdown).toContain('API 提交：否，仅导出')
    expect(markdown).toContain('| # | 时间 | 阶段 | 运镜 | 可观察动作 |')

    const csv = buildMachinePromptCsvExportText(preview)
    expect(csv).toContain('"field","value"')
    expect(csv).toContain('"api_submission","false"')
    expect(csv).toContain('"integrated_multimodal_description","林小夏在便利店收银台后警觉抬头。"')

    const apiJson = JSON.parse(buildMachinePromptApiJsonExportText(preview))
    expect(apiJson.export_contract.api_submission).toBe(false)
    expect(apiJson.export_contract.submission_policy).toBe('export_only_submit_via_generation_adapter')
    expect(apiJson.model_export.api_submission).toBe(false)
  })

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
