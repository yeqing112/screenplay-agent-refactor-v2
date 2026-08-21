import { useEffect, useMemo, useState } from 'react'
import { FileText, Settings2, Upload } from 'lucide-react'
import type { ModelRegistryPayload } from '../prototyping/sceneComposerModelRegistry'
import { fetchModelRegistryDefaults } from '../prototyping/sceneComposerModelRegistry'
import { buildContentModelContextSummary } from './productWorkspaceContentModels'
import { getProjectStatusLabel } from './productWorkspaceProjectStatus'
import type { ContentTaskState, ProductionSkillSectionState } from './productWorkspaceSectionContracts'
import ChapterViewer from './ChapterViewer'

interface Props {
  bookId: number
  contentReady: boolean
  contentStatusLabel: string
  contentStatusDetail: string
  chapterCount: number
  wordCount: number
  projectStatus: string
  uploadFile: File | null
  episodeCount: number
  shortTitle: string
  shortText: string
  productionSkill?: ProductionSkillSectionState
  contentTask: ContentTaskState
  onOpenModelSettings: () => void
  onUploadFileChange: (file: File | null) => void
  onEpisodeCountChange: (value: number) => void
  onShortTitleChange: (value: string) => void
  onShortTextChange: (value: string) => void
  onSubmitNovelUpload: () => void
  onSubmitShortCreate: () => void
}

export default function ProductWorkspaceContentSection({
  bookId,
  contentReady,
  contentStatusLabel,
  contentStatusDetail,
  chapterCount,
  wordCount,
  projectStatus,
  uploadFile,
  episodeCount,
  shortTitle,
  shortText,
  productionSkill,
  contentTask,
  onOpenModelSettings,
  onUploadFileChange,
  onEpisodeCountChange,
  onShortTitleChange,
  onShortTextChange,
  onSubmitNovelUpload,
  onSubmitShortCreate,
}: Props) {
  const resolvedProductionSkill: ProductionSkillSectionState =
    productionSkill ?? {
      skillOptions: [],
      selectedSkillId: null,
      platform: '',
      track: '',
      emotionGoal: '',
      rhythmStrength: '',
      visualStyle: '',
      priorities: [],
      enforcement: '',
      customNote: '',
      lockedAt: null,
      runtimeSummary: null,
    }
  const [modelDefaults, setModelDefaults] = useState<ModelRegistryPayload['default_profiles'] | null>(null)
  const [modelContextState, setModelContextState] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    let active = true
    setModelContextState('loading')

    fetchModelRegistryDefaults()
      .then((payload) => {
        if (!active) return
        setModelDefaults(payload.default_profiles ?? {})
        setModelContextState('ready')
      })
      .catch(() => {
        if (!active) return
        setModelDefaults(null)
        setModelContextState('error')
      })

    return () => {
      active = false
    }
  }, [])

  const modelSummary = useMemo(() => buildContentModelContextSummary(modelDefaults), [modelDefaults])
  const wordCountLabel = ((wordCount || 0) / 10000).toFixed(1)
  const projectStatusLabel = getProjectStatusLabel(projectStatus)
  const taskDisplay = useMemo(
    () => buildContentTaskDisplay({ contentTask, chapterCount, wordCount, projectStatus }),
    [chapterCount, contentTask, projectStatus, wordCount],
  )
  const contentWorkbench = useMemo(
    () =>
      buildContentWorkbenchSummary({
        contentReady,
        chapterCount,
        wordCount,
        episodeCount,
        uploadFile,
        shortTitle,
        shortText,
        contentTask,
      }),
    [chapterCount, contentReady, contentTask, episodeCount, shortText, shortTitle, uploadFile, wordCount],
  )

  const shortTitleText = shortTitle.trim()
  const shortTextValue = shortText.trim()
  const canSubmitNovelUpload = Boolean(uploadFile)
  const canSubmitShortCreate = Boolean(shortTitleText && shortTextValue)
  const safeEpisodeCount = Math.max(1, episodeCount || 1)

  const uploadHint = uploadFile
    ? `将以目标 ${safeEpisodeCount} 集导入 ${uploadFile.name}。`
    : '请先选择原文文件，再发起长篇导入。'
  const shortDraftHint = canSubmitShortCreate
    ? `将以目标 ${safeEpisodeCount} 集导入短篇《${shortTitleText}》。`
    : !shortTitleText && !shortTextValue
      ? '请先填写短篇标题和正文，再发起短篇导入。'
      : !shortTitleText
        ? '还缺短篇标题。'
        : '还缺短篇正文。'

  return (
    <div className="space-y-6">
    <div className="grid gap-6 xl:grid-cols-[1.1fr_1fr_0.9fr]">
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="flex items-center gap-2 text-white">
          <Upload className="h-4 w-4 text-sky-300" />
          上传长篇小说
        </div>
        <div className="mt-3 text-sm leading-6 text-slate-400">
          支持 `txt`、`md`、`markdown`、`doc`、`docx` 原文导入。导入后继续复用现有解析与剧本流程，
          作为内容准备的正式起点。
        </div>
        <div className="mt-4 space-y-3">
          <input
            type="file"
            accept=".txt,.md,.markdown,.doc,.docx"
            onChange={(event) => onUploadFileChange(event.target.files?.[0] ?? null)}
            className="block w-full text-sm text-slate-300 file:mr-4 file:rounded-md file:border-0 file:bg-slate-800 file:px-3 file:py-2 file:text-sm file:text-slate-200"
          />
          <label className="block text-xs text-slate-500">
            目标集数
            <input
              type="number"
              min={1}
              max={120}
              value={episodeCount}
              onChange={(event) => onEpisodeCountChange(Math.max(1, Number(event.target.value) || 1))}
              className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white"
            />
          </label>
          <div className="text-xs text-slate-500">
            {uploadFile ? `已选择：${uploadFile.name}` : '尚未选择原文文件'}
          </div>
          <InlineHint tone={canSubmitNovelUpload ? 'ready' : 'warning'}>{uploadHint}</InlineHint>
          <button
            type="button"
            onClick={onSubmitNovelUpload}
            disabled={!canSubmitNovelUpload}
            className="w-full rounded-lg border border-sky-600/50 bg-sky-500/10 px-3 py-2 text-sm text-sky-200 transition hover:border-sky-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            开始导入长篇
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="flex items-center gap-2 text-white">
          <FileText className="h-4 w-4 text-violet-300" />
          添加短篇小说
        </div>
        <div className="mt-3 text-sm leading-6 text-slate-400">
          直接粘贴短篇正文即可，不需要先准备文件。系统会自动转成临时文本文件，并走同一条正式导入链路。
        </div>
        <div className="mt-4 space-y-3">
          <input
            type="text"
            placeholder="短篇标题"
            value={shortTitle}
            onChange={(event) => onShortTitleChange(event.target.value)}
            className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white placeholder:text-slate-600"
          />
          <textarea
            placeholder="粘贴短篇正文"
            value={shortText}
            onChange={(event) => onShortTextChange(event.target.value)}
            className="h-48 w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white placeholder:text-slate-600"
          />
          <InlineHint tone={canSubmitShortCreate ? 'ready' : 'warning'}>{shortDraftHint}</InlineHint>
          <button
            type="button"
            onClick={onSubmitShortCreate}
            disabled={!canSubmitShortCreate}
            className="w-full rounded-lg border border-violet-600/50 bg-violet-500/10 px-3 py-2 text-sm text-violet-200 transition hover:border-violet-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            创建短篇并导入
          </button>
        </div>
      </div>

      <div className="space-y-6">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="text-sm font-medium text-white">Production Skill</div>
          <div className="mt-2 text-sm leading-6 text-slate-400">
            当前项目使用统一的剧本、分镜、资产生产规范。建议先锁定 skill，再进入改编方向和下游生产。
          </div>
          <div className="mt-4 space-y-2 text-sm">
            <InfoRow
              label="技能包"
              value={
                resolvedProductionSkill.runtimeSummary?.skill_name ||
                resolvedProductionSkill.skillOptions.find((item) => item.id === resolvedProductionSkill.selectedSkillId)?.name ||
                '未选择'
              }
            />
            <InfoRow label="赛道 / 平台" value={`${resolvedProductionSkill.track || '-'} / ${resolvedProductionSkill.platform || '-'}`} />
            <InfoRow label="节奏 / 风格" value={`${resolvedProductionSkill.rhythmStrength || '-'} / ${resolvedProductionSkill.visualStyle || '-'}`} subdued />
            <InfoRow label="优先目标" value={(resolvedProductionSkill.priorities ?? []).join('、') || '-'} />
            <InfoRow label="锁定状态" value={resolvedProductionSkill.lockedAt ? '已锁定' : '待锁定'} subdued={!resolvedProductionSkill.lockedAt} />
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-white">当前模型上下文</div>
              <div className="mt-2 text-sm leading-6 text-slate-400">
                内容准备会优先使用默认 LLM 和默认向量模型来完成文本整理、结构抽取和检索准备。
              </div>
            </div>
            <button
              type="button"
              onClick={onOpenModelSettings}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-200 transition hover:border-sky-500 hover:text-white"
            >
              <Settings2 className="h-3.5 w-3.5" />
              模型设置
            </button>
          </div>
          <div className="mt-4 space-y-2 text-sm">
            <InfoRow label="状态" value={modelContextState === 'error' ? '读取失败' : modelSummary.statusLabel} />
            <InfoRow label="LLM" value={modelContextState === 'loading' ? '正在读取默认 LLM...' : modelSummary.llmTitle} />
            <InfoRow label="LLM Provider" value={modelContextState === 'loading' ? '正在读取...' : modelSummary.llmProvider} subdued />
            <InfoRow
              label="向量模型"
              value={modelContextState === 'loading' ? '正在读取默认向量模型...' : modelSummary.embeddingTitle}
            />
            <InfoRow
              label="向量 Provider"
              value={modelContextState === 'loading' ? '正在读取...' : modelSummary.embeddingProvider}
              subdued
            />
            {modelContextState === 'error' ? (
              <div className="rounded-lg border border-amber-700/40 bg-amber-500/10 px-3 py-2 text-xs leading-5 text-amber-200">
                当前无法读取默认模型配置，但内容准备入口已经接入模型管理跳转，可直接去“模型管理”检查默认 LLM
                和向量模型。
              </div>
            ) : null}
          </div>
        </div>

        <InfoPanel
          title="当前项目内容状态"
          action={contentStatusLabel}
          description={`${contentStatusDetail} 当前项目基础信息来自真实项目数据：${chapterCount} 章，约 ${wordCountLabel} 万字，项目状态 ${projectStatusLabel}。`}
        />

        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="text-sm font-medium text-white">导入状态</div>
          <div className="mt-4 space-y-2 text-sm">
            <InfoRow label="当前模式" value={taskDisplay.modeLabel} />
            <InfoRow label="状态" value={taskDisplay.statusLabel} />
            <InfoRow label="是否可进改编方向" value={contentReady ? '可以继续' : '仍需补齐'} />
            <div className="rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2 text-slate-400">
              {taskDisplay.message}
            </div>
            {contentTask.taskId ? <InfoRow label="任务 ID" value={contentTask.taskId} subdued /> : null}
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="text-sm font-medium text-white">内容整理台</div>
          <div className="mt-2 text-sm leading-6 text-slate-400">
            这里汇总当前项目原文链路、导入草稿和目标集数，方便在进入改编方向前确认内容基础是否已经稳定。
          </div>
          <div className="mt-4 space-y-2 text-sm">
            <InfoRow label="内容来源" value={contentWorkbench.sourceLabel} />
            <InfoRow label="当前规模" value={contentWorkbench.scaleLabel} />
            <InfoRow label="目标集数" value={contentWorkbench.episodeLabel} />
            <InfoRow label="当前草稿" value={contentWorkbench.draftLabel} subdued={!contentWorkbench.hasDraft} />
            <div className="rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2 text-slate-400">
              {contentWorkbench.note}
            </div>
          </div>
        </div>
      </div>
    </div>
    <ChapterViewer bookId={bookId} />
    </div>
  )
}

function buildContentTaskDisplay({
  contentTask,
  chapterCount,
  wordCount,
  projectStatus,
}: {
  contentTask: ContentTaskState
  chapterCount: number
  wordCount: number
  projectStatus: string
}) {
  const hasStructuredContent = chapterCount > 0 || wordCount > 0
  const hasRealTask =
    contentTask.status !== 'idle' || Boolean(contentTask.taskId) || Boolean(contentTask.message?.trim())

  if (!hasRealTask && hasStructuredContent) {
    return {
      modeLabel: '历史内容接入',
      statusLabel: '已接入',
      message: `当前项目已存在 ${chapterCount} 章、约 ${((wordCount || 0) / 10000).toFixed(1)} 万字的真实内容基础，当前无需重新发起导入任务。`,
    }
  }

  if (contentTask.status === 'idle' && hasStructuredContent) {
    return {
      modeLabel: '历史内容接入',
      statusLabel: '已接入',
      message: `当前项目内容来自既有项目数据，项目状态 ${getProjectStatusLabel(projectStatus)}。如果需要覆盖原内容，可重新上传长篇或录入短篇。`,
    }
  }

  return {
    modeLabel: contentTask.mode === 'short' ? '短篇录入' : '长篇上传',
    statusLabel: buildContentTaskStatusLabel(contentTask.status),
    message: contentTask.message || '尚未开始导入。',
  }
}

function buildContentTaskStatusLabel(status: ContentTaskState['status']) {
  if (status === 'uploading') return '上传中'
  if (status === 'running') return '处理中'
  if (status === 'done') return '已完成'
  if (status === 'error') return '失败'
  return '未开始'
}

function buildContentWorkbenchSummary({
  contentReady,
  chapterCount,
  wordCount,
  episodeCount,
  uploadFile,
  shortTitle,
  shortText,
  contentTask,
}: {
  contentReady: boolean
  chapterCount: number
  wordCount: number
  episodeCount: number
  uploadFile: File | null
  shortTitle: string
  shortText: string
  contentTask: ContentTaskState
}) {
  const hasStructuredContent = chapterCount > 0 || wordCount > 0
  const shortTitleText = shortTitle.trim()
  const shortTextValue = shortText.trim()
  const hasShortDraft = Boolean(shortTitleText || shortTextValue)
  const hasUploadDraft = Boolean(uploadFile)

  const sourceLabel = hasStructuredContent
    ? '已接入正式内容'
    : contentTask.mode === 'short'
      ? '短篇录入链路'
      : '长篇上传链路'

  const scaleLabel = hasStructuredContent
    ? `${chapterCount} 章 / 约 ${((wordCount || 0) / 10000).toFixed(1)} 万字`
    : hasShortDraft
      ? `短篇草稿 / ${shortTextValue.length} 字`
      : hasUploadDraft
        ? '待导入原文文件'
        : '尚未建立正式内容规模'

  const draftLabel = hasUploadDraft
    ? `上传文件：${uploadFile?.name ?? ''}`
    : hasShortDraft
      ? `短篇草稿：${shortTitleText || '未命名短篇'}`
      : '当前没有待处理草稿'

  const note = hasStructuredContent
    ? contentReady
      ? '当前项目已经具备稳定内容基础，可以继续进入改编方向，锁定项目主创作路径。'
      : '项目已有内容基础，但仍建议先完成本模块校对，再进入改编方向和剧本工作台。'
    : hasShortDraft
      ? '短篇草稿已在本地编辑区，可直接发起导入并沿正式内容链路继续处理。'
      : hasUploadDraft
        ? '已选择原文文件，确认目标集数后即可发起正式导入。'
        : '先上传长篇小说，或填写短篇标题和正文，再建立正式内容准备链路。'

  return {
    sourceLabel,
    scaleLabel,
    episodeLabel: `目标 ${Math.max(1, episodeCount || 1)} 集`,
    draftLabel,
    note,
    hasDraft: hasShortDraft || hasUploadDraft,
  }
}

function InlineHint({
  tone,
  children,
}: {
  tone: 'ready' | 'warning'
  children: string
}) {
  return (
    <div
      className={`rounded-lg border px-3 py-2 text-xs leading-5 ${
        tone === 'ready'
          ? 'border-sky-500/20 bg-sky-500/10 text-sky-200'
          : 'border-amber-500/20 bg-amber-500/10 text-amber-200'
      }`}
    >
      {children}
    </div>
  )
}

function InfoPanel({
  title,
  action,
  description,
}: {
  title: string
  action?: string
  description: string
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-medium text-white">{title}</div>
        {action ? (
          <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">{action}</span>
        ) : null}
      </div>
      <div className="mt-3 text-sm leading-6 text-slate-400">{description}</div>
    </div>
  )
}

function InfoRow({ label, value, subdued }: { label: string; value: string; subdued?: boolean }) {
  return (
    <div
      className={`rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2 ${
        subdued ? 'text-slate-500' : 'text-slate-300'
      }`}
    >
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 text-sm leading-6">{value}</div>
    </div>
  )
}
