import type { DirectorPlanStep } from '../services/agent'

export const TIER_LABEL: Record<DirectorPlanStep['tier'], string> = {
  A: '只读诊断',
  B: '内部草案',
  C: '需你确认的写入',
  D: '需你确认的外部调用',
}

export const TIER_TONE: Record<DirectorPlanStep['tier'], string> = {
  A: 'border-emerald-400/30 bg-emerald-500/10 text-emerald-100',
  B: 'border-sky-400/30 bg-sky-500/10 text-sky-100',
  C: 'border-amber-400/30 bg-amber-500/10 text-amber-100',
  D: 'border-rose-400/30 bg-rose-500/10 text-rose-100',
}

export function classifyOperation(operation: string): DirectorPlanStep['tier'] {
  if (operation === 'diagnose' || operation === 'continuity_check') return 'A'
  if (operation === 'draft_prompt' || operation === 'draft_repair') return 'B'
  if (operation === 'write_prompt_version') return 'C'
  return 'D'
}

export const TIER_OPERATIONS: DirectorPlanStep['operation'][] = [
  'diagnose',
  'continuity_check',
  'draft_prompt',
  'draft_repair',
  'write_prompt_version',
  'image_generation',
  'video_generation',
]