export type ContentPreparationStatus =
  | 'not_started'
  | 'uploading'
  | 'processing'
  | 'needs_cleanup'
  | 'ready'

export interface ContentPreparationSummary {
  status: ContentPreparationStatus
  label: string
  detail: string
  canProceedToAdaptation: boolean
}

export type AdaptationSetupStatus =
  | 'waiting_content'
  | 'ready_to_generate'
  | 'ready_to_lock'
  | 'backfill_needed'
  | 'locked'

export interface AdaptationSetupSummary {
  status: AdaptationSetupStatus
  label: string
  detail: string
  canGenerateCandidates: boolean
  canLock: boolean
  isLocked: boolean
  isReadyForDownstream: boolean
}

interface ContentInput {
  chapterCount: number
  wordCount: number
  projectStatus?: string | null
  contentTaskStatus: 'idle' | 'uploading' | 'running' | 'done' | 'error'
  hasDownstreamOutput: boolean
}

interface AdaptationInput {
  content: ContentPreparationSummary
  hasLockedAdaptation: boolean
  selectedAdaptationName?: string | null
  hasSelectedAdaptation: boolean
  hasDownstreamOutput: boolean
}

export function buildContentPreparationSummary(input: ContentInput): ContentPreparationSummary {
  const chapterCount = Math.max(0, input.chapterCount || 0)
  const wordCount = Math.max(0, input.wordCount || 0)
  const hasStructuredContent = chapterCount > 0 || wordCount > 0
  const normalizedProjectStatus = String(input.projectStatus || '').trim().toLowerCase()
  const hasProjectRecord = Boolean(normalizedProjectStatus && normalizedProjectStatus !== 'draft')

  if (input.contentTaskStatus === 'uploading') {
    return {
      status: 'uploading',
      label: '上传中',
      detail: '原文文件正在上传，完成后会进入正式解析链路。',
      canProceedToAdaptation: false,
    }
  }

  if (input.contentTaskStatus === 'running') {
    return {
      status: 'processing',
      label: '处理中',
      detail: '内容已进入整理与解析流程，暂时不建议提前锁定改编方向。',
      canProceedToAdaptation: false,
    }
  }

  if (hasStructuredContent) {
    return {
      status: 'ready',
      label: '已完成',
      detail: `当前已整理出 ${chapterCount} 章、约 ${formatWordCount(wordCount)} 万字内容，可进入改编方向。`,
      canProceedToAdaptation: true,
    }
  }

  if (input.hasDownstreamOutput || hasProjectRecord || input.contentTaskStatus === 'done') {
    return {
      status: 'needs_cleanup',
      label: '待补整理',
      detail:
        '项目已有下游产出或导入记录，但内容准备侧仍缺少稳定的结构化原文，建议补齐以便后续统一追踪。',
      canProceedToAdaptation: true,
    }
  }

  return {
    status: 'not_started',
    label: '未导入',
    detail: '先上传长篇小说或录入短篇内容，建立正式内容准备链路。',
    canProceedToAdaptation: false,
  }
}

export function buildAdaptationSetupSummary(input: AdaptationInput): AdaptationSetupSummary {
  if (input.hasLockedAdaptation) {
    return {
      status: 'locked',
      label: '已锁定',
      detail: input.selectedAdaptationName
        ? `当前主方向：${input.selectedAdaptationName}`
        : '当前主方向已锁定。',
      canGenerateCandidates: false,
      canLock: false,
      isLocked: true,
      isReadyForDownstream: true,
    }
  }

  if (!input.content.canProceedToAdaptation) {
    return {
      status: 'waiting_content',
      label: '等待内容准备',
      detail: '需要先完成内容准备，才能生成候选改编方向并进入锁定。',
      canGenerateCandidates: false,
      canLock: false,
      isLocked: false,
      isReadyForDownstream: false,
    }
  }

  if (input.hasDownstreamOutput) {
    return {
      status: 'backfill_needed',
      label: '待补锁定',
      detail: '当前项目已有下游产出，建议尽快补锁一个项目级主方向，避免后续风格漂移。',
      canGenerateCandidates: true,
      canLock: input.hasSelectedAdaptation,
      isLocked: false,
      isReadyForDownstream: true,
    }
  }

  if (input.hasSelectedAdaptation) {
    return {
      status: 'ready_to_lock',
      label: '待锁定',
      detail: '候选改编方向已经选中，确认后会成为后续剧本、分镜和资产策略的统一约束。',
      canGenerateCandidates: true,
      canLock: true,
      isLocked: false,
      isReadyForDownstream: false,
    }
  }

  return {
    status: 'ready_to_generate',
    label: '待生成候选',
    detail: '内容准备已具备，可以先生成 2-3 个候选改编方向再做项目级决策。',
    canGenerateCandidates: true,
    canLock: false,
    isLocked: false,
    isReadyForDownstream: false,
  }
}

function formatWordCount(wordCount: number) {
  return (wordCount / 10000).toFixed(1)
}
