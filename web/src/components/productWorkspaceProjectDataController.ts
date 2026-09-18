import { useMemo } from 'react'
import type {
  ScriptOutput,
  StoryboardShotOutput,
  VisualLocationOutput,
  VisualMakeupOutput,
  VisualPropOutput,
} from '../domain/bookOutputs'

export interface WorkspaceQaEntry {
  id?: number
  episode: number
  result: unknown
  error_count?: number
}

interface WorkspaceProjectOutputs {
  scripts?: ScriptOutput[]
  qa?: Array<{ id?: number; episode: number; result?: unknown; error_count?: number }>
  storyboard?: { episodeShots?: Record<number, StoryboardShotOutput[]> }
  visual?: {
    makeups?: VisualMakeupOutput[]
    locations?: VisualLocationOutput[]
    props?: VisualPropOutput[]
  }
}

export function useProductWorkspaceProjectData(data: WorkspaceProjectOutputs | null | undefined) {
  return useMemo(() => {
    const fixtureEnabled = import.meta.env.DEV && typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('workspace_fixture') === 'populated'
    if (fixtureEnabled) {
      const shot = {
        episode: 1, shot_id: 'A', scene_name: '旧公寓门厅', duration: 4, camera_angle: '中景', camera_movement: '固定', camera_speed: '慢', action_process: '林晚停在门口', start_state: '铁门关闭', end_state: '铁门关闭', asset_status: 'reference_pending', visual_prompt_static: '冷青灰雨夜门厅，人物停在铁门前。', visual_prompt_motion: '人物停留，雨声延续。', prompt_version: 1, prompt_locked: true, makeup_prompts: [{ id: 1, character_name: '林晚' }], assets: { images: [], videos: [], audios: [], references: { characters: { 林晚: [] }, scene: [], props: {} } }, structured_shot: { character_asset_ids: [1], scene_asset_id: 2, prop_asset_ids: [3] }, reference_images: [],
      } as any
      const followUpShot = {
        episode: 1, shot_id: 'B', scene_name: '旧公寓门厅', duration: 6, camera_angle: '近景', camera_movement: '推进', camera_speed: '慢', action_process: '林晚抬头', start_state: '铁门关闭', end_state: '人物抬头', asset_status: 'prompt_stale', visual_prompt_static: '冷青灰雨夜门厅，林晚抬头确认门外动静。', visual_prompt_motion: '镜头缓慢推进，林晚抬头。', prompt_version: 1, prompt_locked: false, makeup_prompts: [{ id: 1, character_name: '林晚' }], assets: { images: [], videos: [], audios: [], references: { characters: { 林晚: [] }, scene: [], props: {} } }, structured_shot: { character_asset_ids: [1], scene_asset_id: 2, prop_asset_ids: [3] }, reference_images: [],
      } as any
      return {
        firstScript: { episode: 1, content: 'fixture script' } as ScriptOutput,
        scripts: [{ episode: 1, content: 'fixture script' } as ScriptOutput],
        shotsByEpisode: { 1: [shot, followUpShot] },
        qaEntries: [],
        makeups: [{ id: 1, episode: 1, character_name: '林晚', gender: '女', identity: '便利店店员', appearance: '短发', refined_outfit: '深色外套', visual_prompt_zh: '六宫格人物设定板', shot_ids: ['A'], reference_assets: [] }] as any,
        locations: [{ id: 2, name: '旧公寓门厅', category: 'scene', style: '写实电影感', description: '雨夜铁门门厅', shot_ids: ['A'], references: [] }] as any,
        props: [{ id: 3, name: '铁门钥匙', category: 'prop', importance: 'high', description: '旧钥匙', shot_ids: ['A'], references: [] }] as any,
      }
    }
    const scripts = data?.scripts ?? []
    const shotsByEpisode = data?.storyboard?.episodeShots ?? {}
    const qaEntries: WorkspaceQaEntry[] = (data?.qa ?? []).map((item) => ({
      id: item.id,
      episode: item.episode,
      result: item.result ?? null,
      error_count: item.error_count,
    }))
    const makeups = data?.visual?.makeups ?? []
    const locations = data?.visual?.locations ?? []
    const props = data?.visual?.props ?? []

    return {
      firstScript: scripts[0] ?? null,
      scripts,
      shotsByEpisode,
      qaEntries,
      makeups,
      locations,
      props,
    }
  }, [data])
}
