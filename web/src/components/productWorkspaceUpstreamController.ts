import { useEffect, useMemo, useState } from 'react'
import {
  buildAdaptationOptions,
  getSelectedAdaptation,
  type AdaptationOption,
} from './productWorkspaceAdaptation'
import type {
  ContentTaskState,
  ProductionSkillOption,
  ProductionSkillRuntimeSummary,
  ProductionSkillSectionState,
} from './productWorkspaceSectionContracts'

export type { ContentTaskState } from './productWorkspaceSectionContracts'

interface StoredAdaptationState {
  customNote: string
  lockedAt: string | null
  selectedId: string | null
  selectedName: string | null
}

interface ProductionSkillApiPayload {
  skills?: Array<{
    skill_meta?: {
      id?: string
      name?: string
      summary?: string
      tracks?: string[]
      platforms?: string[]
    }
  }>
}

interface StoredProductionSkillState {
  selectedSkillId: string | null
  platform: string
  track: string
  emotionGoal: string
  rhythmStrength: string
  visualStyle: string
  priorities: string[]
  enforcement: string
  customNote: string
  lockedAt: string | null
  runtimeSummary: ProductionSkillRuntimeSummary | null
}

interface Params {
  bookId: number
  bookTitle: string
  chapterCount: number
  wordCount: number
  scriptExcerpt?: string
  episodeCountDefault?: number
  onBookChange: (bookId: number) => void
  onRefreshAll: () => void
}

const MESSAGE_REPLACEMENTS: Array<[string, string]> = [
  ['瀵煎叆鏂囦欢', '导入文件'],
  ['瀵煎叆瀹屾垚', '导入完成'],
  ['瀵煎叆澶辫触', '导入失败'],
  ['閫愮珷鍒嗘瀽', '逐章分析'],
  ['姝ｅ湪涓婁紶鍐呭鏂囦欢', '正在上传内容文件'],
  ['宸蹭笂浼狅紝姝ｅ湪鍚姩瀵煎叆娴佺▼', '已上传，正在启动导入流程'],
  ['瀵煎叆浠诲姟宸插惎鍔', '导入任务已启动'],
  ['姝ｅ湪澶勭悊绔犺妭涓庤剼鏈祦绋', '正在处理章节与脚本流程'],
  ['涓婁紶澶辫触', '上传失败'],
  ['涓婁紶瀵煎叆澶辫触', '上传导入失败'],
  ['鐭瘒褰曞叆澶辫触', '短篇录入失败'],
  ['鐭瘒鏍囬鍜屾鏂囬兘涓嶈兘涓虹┖', '短篇标题和正文都不能为空'],
  ['璇峰厛閫夋嫨瑕佷笂浼犵殑灏忚鏂囦欢', '请先选择要上传的小说文件'],
  ['瀵煎叆浠诲姟杞瓒呮椂', '导入任务轮询超时'],
  ['澶勭悊涓', '处理中'],
  ['灏氭湭寮€濮嬪鍏', '尚未开始导入'],
  ['reader complete', '逐章分析完成'],
  ['bible complete', '小说圣经完成'],
  ['portrait complete', '人物画像完成'],
  ['content preparation complete', '内容准备完成'],
  ['生成人物画像', '生成人物画像'],
  ['人物画像跳过，继续主链路', '人物画像跳过，继续主链路'],
  [
    "No character signals found. Make sure 'read' was run with the updated prompt.",
    '未识别到可用人物信号，请先确认逐章分析结果是否完整。',
  ],
]

function adaptationStorageKey(bookId: number) {
  return `product-workspace:adaptation:${bookId}`
}

function productionSkillStorageKey(bookId: number) {
  return `product-workspace:production-skill:${bookId}`
}

function sanitizeContentTaskMessage(message: unknown, fallback: string) {
  const raw = typeof message === 'string' ? message.trim() : ''
  let normalized = raw || fallback
  for (const [from, to] of MESSAGE_REPLACEMENTS) {
    normalized = normalized.split(from).join(to)
  }
  normalized = normalized
    .replace(/[?？]+$/g, '')
    .replace(/\s+\/\s+\/+/g, ' / ')
    .replace(/\.\.+$/g, '...')
    .trim()
  return normalized || fallback
}

function readStoredAdaptationState(bookId: number): StoredAdaptationState | null {
  if (bookId <= 0 || typeof window === 'undefined') return null

  try {
    const raw = window.localStorage.getItem(adaptationStorageKey(bookId))
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<StoredAdaptationState>
    return {
      customNote: typeof parsed.customNote === 'string' ? parsed.customNote : '',
      lockedAt: typeof parsed.lockedAt === 'string' ? parsed.lockedAt : null,
      selectedId: typeof parsed.selectedId === 'string' ? parsed.selectedId : null,
      selectedName: typeof parsed.selectedName === 'string' ? parsed.selectedName : null,
    }
  } catch {
    return null
  }
}

function defaultProductionSkillState(): StoredProductionSkillState {
  return {
    selectedSkillId: 'rebirth_suspense',
    platform: 'douyin',
    track: '重生悬疑',
    emotionGoal: '高压悬念',
    rhythmStrength: 'strong_hooks',
    visualStyle: 'cinematic_realism',
    priorities: ['storyboard', 'assets', 'mystery'],
    enforcement: 'strict',
    customNote: '',
    lockedAt: null,
    runtimeSummary: null,
  }
}

function readStoredProductionSkillState(bookId: number): StoredProductionSkillState | null {
  if (bookId <= 0 || typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(productionSkillStorageKey(bookId))
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<StoredProductionSkillState>
    return {
      ...defaultProductionSkillState(),
      selectedSkillId: typeof parsed.selectedSkillId === 'string' ? parsed.selectedSkillId : 'rebirth_suspense',
      platform: typeof parsed.platform === 'string' ? parsed.platform : 'douyin',
      track: typeof parsed.track === 'string' ? parsed.track : '重生悬疑',
      emotionGoal: typeof parsed.emotionGoal === 'string' ? parsed.emotionGoal : '高压悬念',
      rhythmStrength: typeof parsed.rhythmStrength === 'string' ? parsed.rhythmStrength : 'strong_hooks',
      visualStyle: typeof parsed.visualStyle === 'string' ? parsed.visualStyle : 'cinematic_realism',
      priorities: Array.isArray(parsed.priorities) ? parsed.priorities.filter((item): item is string => typeof item === 'string') : ['storyboard', 'assets', 'mystery'],
      enforcement: typeof parsed.enforcement === 'string' ? parsed.enforcement : 'strict',
      customNote: typeof parsed.customNote === 'string' ? parsed.customNote : '',
      lockedAt: typeof parsed.lockedAt === 'string' ? parsed.lockedAt : null,
      runtimeSummary: (parsed.runtimeSummary as ProductionSkillRuntimeSummary | null | undefined) ?? null,
    }
  } catch {
    return null
  }
}

function persistProductionSkillState(bookId: number, state: StoredProductionSkillState) {
  if (bookId <= 0 || typeof window === 'undefined') return
  window.localStorage.setItem(productionSkillStorageKey(bookId), JSON.stringify(state))
}

function persistAdaptationState(bookId: number, state: StoredAdaptationState) {
  if (bookId <= 0 || typeof window === 'undefined') return
  window.localStorage.setItem(adaptationStorageKey(bookId), JSON.stringify(state))
}

async function fetchPersistedAdaptationState(bookId: number): Promise<StoredAdaptationState | null> {
  if (bookId <= 0) return null
  try {
    const response = await fetch(`/api/books/${bookId}/adaptation-state`, { cache: 'no-store' })
    if (!response.ok) return null
    const payload = await response.json()
    return {
      customNote: typeof payload?.custom_note === 'string' ? payload.custom_note : '',
      lockedAt: typeof payload?.locked_at === 'string' ? payload.locked_at : null,
      selectedId: typeof payload?.selected_id === 'string' ? payload.selected_id : null,
      selectedName: typeof payload?.selected_name === 'string' ? payload.selected_name : null,
    }
  } catch {
    return null
  }
}

async function persistAdaptationStateToServer(bookId: number, state: StoredAdaptationState) {
  if (bookId <= 0) return
  try {
    await fetch(`/api/books/${bookId}/adaptation-state`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        selectedId: state.selectedId,
        selectedName: state.selectedName,
        customNote: state.customNote,
        lockedAt: state.lockedAt,
      }),
    })
  } catch {
    // Keep local cache usable when the server persistence endpoint is unavailable.
  }
}

async function fetchProductionSkillOptions(): Promise<ProductionSkillOption[]> {
  const response = await fetch('/api/production-skills', { cache: 'no-store' })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const payload = (await response.json()) as ProductionSkillApiPayload
  return (payload.skills ?? []).map((item) => ({
    id: String(item.skill_meta?.id || '').trim(),
    name: String(item.skill_meta?.name || '').trim(),
    summary: String(item.skill_meta?.summary || '').trim(),
    tracks: Array.isArray(item.skill_meta?.tracks) ? item.skill_meta?.tracks : [],
    platforms: Array.isArray(item.skill_meta?.platforms) ? item.skill_meta?.platforms : [],
  })).filter((item) => item.id && item.name)
}

async function fetchPersistedProductionSkillState(bookId: number): Promise<StoredProductionSkillState | null> {
  if (bookId <= 0) return null
  try {
    const response = await fetch(`/api/books/${bookId}/production-skill-state`, { cache: 'no-store' })
    if (!response.ok) return null
    const payload = await response.json()
    return {
      selectedSkillId: typeof payload?.skill_id === 'string' ? payload.skill_id : 'rebirth_suspense',
      platform: typeof payload?.platform === 'string' ? payload.platform : 'douyin',
      track: typeof payload?.track === 'string' ? payload.track : '重生悬疑',
      emotionGoal: typeof payload?.emotion_goal === 'string' ? payload.emotion_goal : '高压悬念',
      rhythmStrength: typeof payload?.rhythm_strength === 'string' ? payload.rhythm_strength : 'strong_hooks',
      visualStyle: typeof payload?.visual_style === 'string' ? payload.visual_style : 'cinematic_realism',
      priorities: Array.isArray(payload?.priorities) ? payload.priorities.filter((item: unknown): item is string => typeof item === 'string') : ['storyboard', 'assets', 'mystery'],
      enforcement: typeof payload?.enforcement === 'string' ? payload.enforcement : 'strict',
      customNote: typeof payload?.custom_note === 'string' ? payload.custom_note : '',
      lockedAt: typeof payload?.locked_at === 'string' ? payload.locked_at : null,
      runtimeSummary: (payload?.runtime_summary as ProductionSkillRuntimeSummary | null | undefined) ?? null,
    }
  } catch {
    return null
  }
}

async function persistProductionSkillStateToServer(bookId: number, state: StoredProductionSkillState) {
  if (bookId <= 0) return
  try {
    await fetch(`/api/books/${bookId}/production-skill-state`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        skillId: state.selectedSkillId,
        platform: state.platform,
        track: state.track,
        emotionGoal: state.emotionGoal,
        rhythmStrength: state.rhythmStrength,
        visualStyle: state.visualStyle,
        priorities: state.priorities,
        enforcement: state.enforcement,
        customNote: state.customNote,
        lockedAt: state.lockedAt,
      }),
    })
  } catch {
    // Keep local state usable if the server is temporarily unavailable.
  }
}

function resolveStoredAdaptationSelection(
  options: AdaptationOption[],
  selectedId: string | null | undefined,
  selectedName: string | null | undefined,
) {
  const normalizedId = typeof selectedId === 'string' ? selectedId.trim() : ''
  if (normalizedId && options.some((option) => option.id === normalizedId)) return normalizedId

  const normalizedName = typeof selectedName === 'string' ? selectedName.trim() : ''
  if (normalizedName) {
    return options.find((option) => option.name === normalizedName)?.id ?? null
  }

  return null
}

function estimateEpisodeCountFromText(text: string) {
  const normalized = text.trim()
  if (!normalized) return 1

  const chineseMatches =
    normalized.match(/^\s*第\s*[0-9一二三四五六七八九十百千万两零]+[章节回幕集]\s*/gm) ?? []
  if (chineseMatches.length > 0) return chineseMatches.length

  const englishMatches =
    normalized.match(/^\s*(chapter|scene|ep|episode)\s*[\d一二三四五六七八九十]+\b/gim) ?? []
  if (englishMatches.length > 0) return englishMatches.length

  return 1
}

function formatTaskMessage(step: unknown, progress: unknown, warnings: unknown, fallback: string) {
  const currentStep = sanitizeContentTaskMessage(step, fallback)
  const progressText = typeof progress === 'number' ? `${progress}%` : ''
  const warningText =
    Array.isArray(warnings) && warnings.length > 0
      ? `（${warnings
          .map((item) => sanitizeContentTaskMessage(String(item), '存在待关注项'))
          .join('；')}）`
      : ''

  return `${currentStep}${progressText ? ` / ${progressText}` : ''}${warningText}`.trim()
}

export function useProductWorkspaceUpstream({
  bookId,
  bookTitle,
  chapterCount,
  wordCount,
  scriptExcerpt,
  episodeCountDefault = 1,
  onBookChange,
  onRefreshAll,
}: Params) {
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [shortTitle, setShortTitle] = useState('')
  const [shortText, setShortText] = useState('')
  const [episodeCount, setEpisodeCount] = useState(Math.max(1, episodeCountDefault))
  const [contentTask, setContentTask] = useState<ContentTaskState>({
    mode: 'upload',
    status: 'idle',
    message: '尚未开始导入。',
  })
  const [adaptationOptions, setAdaptationOptions] = useState<AdaptationOption[]>([])
  const [selectedAdaptationId, setSelectedAdaptationId] = useState<string | null>(null)
  const [adaptationCustomNote, setAdaptationCustomNote] = useState('')
  const [adaptationLockedAt, setAdaptationLockedAt] = useState<string | null>(null)
  const [adaptationStorageLoadedForBook, setAdaptationStorageLoadedForBook] = useState<number | null>(
    null,
  )
  const [productionSkillOptions, setProductionSkillOptions] = useState<ProductionSkillOption[]>([])
  const [productionSkillState, setProductionSkillState] = useState<StoredProductionSkillState>(defaultProductionSkillState())
  const [productionSkillStorageLoadedForBook, setProductionSkillStorageLoadedForBook] = useState<number | null>(null)

  const selectedAdaptation = useMemo(
    () => getSelectedAdaptation(adaptationOptions, selectedAdaptationId),
    [adaptationOptions, selectedAdaptationId],
  )

  useEffect(() => {
    setAdaptationStorageLoadedForBook(null)
    const options = buildAdaptationOptions({
      title: bookTitle,
      chapterCount,
      wordCount,
      scriptExcerpt,
    })

    setAdaptationOptions(options)
    setEpisodeCount(Math.max(1, episodeCountDefault))
    setSelectedAdaptationId(null)
    setAdaptationCustomNote('')
    setAdaptationLockedAt(null)

    let cancelled = false
    const localState = readStoredAdaptationState(bookId)

    fetchPersistedAdaptationState(bookId)
      .then((serverState) => {
        if (cancelled) return
        const resolvedState = serverState ?? localState
        const resolvedSelectedId = resolveStoredAdaptationSelection(
          options,
          resolvedState?.selectedId ?? null,
          resolvedState?.selectedName ?? null,
        )

        setSelectedAdaptationId(resolvedSelectedId)
        setAdaptationCustomNote(resolvedState?.customNote ?? '')
        setAdaptationLockedAt(resolvedState?.lockedAt ?? null)
        setAdaptationStorageLoadedForBook(bookId)

      })
      .catch(() => {
        if (cancelled) return
        const resolvedSelectedId = resolveStoredAdaptationSelection(
          options,
          localState?.selectedId ?? null,
          localState?.selectedName ?? null,
        )
        setSelectedAdaptationId(resolvedSelectedId)
        setAdaptationCustomNote(localState?.customNote ?? '')
        setAdaptationLockedAt(localState?.lockedAt ?? null)
        setAdaptationStorageLoadedForBook(bookId)
      })

    return () => {
      cancelled = true
    }
  }, [bookId, bookTitle, chapterCount, wordCount, scriptExcerpt, episodeCountDefault])

  useEffect(() => {
    if (adaptationStorageLoadedForBook !== bookId) return
    const nextState = {
      customNote: adaptationCustomNote,
      lockedAt: adaptationLockedAt,
      selectedId: selectedAdaptationId,
      selectedName: selectedAdaptation?.name ?? null,
    }
    persistAdaptationState(bookId, nextState)
  }, [
    bookId,
    adaptationCustomNote,
    adaptationLockedAt,
    selectedAdaptationId,
    selectedAdaptation?.name,
    adaptationStorageLoadedForBook,
  ])

  useEffect(() => {
    setProductionSkillStorageLoadedForBook(null)
    const localState = readStoredProductionSkillState(bookId) ?? defaultProductionSkillState()
    let cancelled = false

    Promise.allSettled([fetchProductionSkillOptions(), fetchPersistedProductionSkillState(bookId)]).then((results) => {
      if (cancelled) return
      const optionResult = results[0]
      const stateResult = results[1]
      const options =
        optionResult.status === 'fulfilled' && optionResult.value.length > 0
          ? optionResult.value
          : [
              { id: 'rebirth_suspense', name: '重生悬疑 Production Skill', summary: '旧疑点推进 + 新疑点生成 + 证据驱动。', tracks: ['重生悬疑'], platforms: ['douyin', 'kuaishou'] },
              { id: 'romance_abuse', name: '情感虐恋 Production Skill', summary: '关系压强 + 误会反转 + 情绪爆点。', tracks: ['情感虐恋'], platforms: ['douyin', 'kuaishou'] },
              { id: 'rise_revenge', name: '逆袭爽剧 Production Skill', summary: '压制反击 + 翻盘兑现 + 爽点镜头。', tracks: ['逆袭爽剧'], platforms: ['douyin', 'kuaishou'] },
            ]
      setProductionSkillOptions(options)
      const resolvedState =
        stateResult.status === 'fulfilled' && stateResult.value ? stateResult.value : localState
      setProductionSkillState({
        ...defaultProductionSkillState(),
        ...resolvedState,
      })
      setProductionSkillStorageLoadedForBook(bookId)
    })

    return () => {
      cancelled = true
    }
  }, [bookId])

  useEffect(() => {
    if (productionSkillStorageLoadedForBook !== bookId) return
    persistProductionSkillState(bookId, productionSkillState)
  }, [bookId, productionSkillState, productionSkillStorageLoadedForBook])

  const pollPipelineTask = async (taskId: string) => {
    for (let index = 0; index < 180; index += 1) {
      const response = await fetch(`/api/pipeline/task/${taskId}`)
      const payload = await response.json()
      const status = String(payload.status || '')

      if (status === 'done') {
        setContentTask((prev) => ({
          ...prev,
          status: 'done',
          message: formatTaskMessage(
            payload.current_step || '导入完成',
            payload.progress,
            payload.warnings,
            '导入完成',
          ),
        }))
        if (payload.new_book_id && Number(payload.new_book_id) > 0 && Number(payload.new_book_id) !== bookId) {
          onBookChange(Number(payload.new_book_id))
          return
        }
        onRefreshAll()
        return
      }

      if (status === 'error') {
        setContentTask((prev) => ({
          ...prev,
          status: 'error',
          message: sanitizeContentTaskMessage(
            payload.error || payload.current_step,
            '导入失败',
          ),
        }))
        return
      }

      setContentTask((prev) => ({
        ...prev,
        status: 'running',
        message: formatTaskMessage(
          payload.current_step,
          payload.progress,
          payload.warnings,
          '处理中',
        ),
      }))
      await new Promise((resolve) => window.setTimeout(resolve, 1500))
    }

    setContentTask((prev) => ({
      ...prev,
      status: 'error',
      message: '导入任务轮询超时，请去任务中心继续查看。',
    }))
  }

  const startImportFromFile = async (
    file: File,
    mode: 'upload' | 'short',
    episodeCountOverride?: number,
    preferredTitle?: string,
  ) => {
    setContentTask({ mode, status: 'uploading', message: '正在上传内容文件...' })
    const formData = new FormData()
    formData.append('file', file)

    const uploadResponse = await fetch('/api/upload', { method: 'POST', body: formData })
    if (!uploadResponse.ok) throw new Error(`上传失败: HTTP ${uploadResponse.status}`)

    const uploadPayload = await uploadResponse.json()
    setContentTask({ mode, status: 'running', message: '已上传，正在启动导入流程...' })

    const pipelineResponse = await fetch('/api/pipeline/script', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        book_id: bookId > 0 ? bookId : 0,
        filepath: uploadPayload.filepath,
        genre: 'short_drama',
        episode_count: episodeCountOverride ?? episodeCount,
        stop_after: 'content',
        preferred_title: preferredTitle?.trim() || undefined,
      }),
    })

    if (!pipelineResponse.ok) throw new Error(`上传导入失败: HTTP ${pipelineResponse.status}`)

    const pipelinePayload = await pipelineResponse.json()
    const taskId = pipelinePayload.task_id
    if (!taskId) throw new Error('导入流程没有返回 task_id')

    setContentTask({
      mode,
      status: 'running',
      message: '导入任务已启动，正在处理章节与脚本流程...',
      taskId,
    })
    await pollPipelineTask(taskId)
  }

  const handleNovelUpload = async () => {
    if (!uploadFile) {
      setContentTask({ mode: 'upload', status: 'error', message: '请先选择要上传的小说文件。' })
      return
    }

    try {
      await startImportFromFile(uploadFile, 'upload')
    } catch (importError) {
      setContentTask({
        mode: 'upload',
        status: 'error',
        message: sanitizeContentTaskMessage(
          importError instanceof Error ? importError.message : '',
          '上传导入失败',
        ),
      })
    }
  }

  const handleShortCreate = async () => {
    const title = shortTitle.trim()
    const text = shortText.trim()

    if (!title || !text) {
      setContentTask({ mode: 'short', status: 'error', message: '短篇标题和正文都不能为空。' })
      return
    }

    try {
      const estimatedEpisodeCount = estimateEpisodeCountFromText(text)
      const resolvedEpisodeCount = Math.max(1, Math.min(episodeCount, estimatedEpisodeCount))
      const file = new File([text], `${title}.txt`, { type: 'text/plain;charset=utf-8' })

      if (resolvedEpisodeCount !== episodeCount) {
        setContentTask({
          mode: 'short',
          status: 'uploading',
          message: `短篇正文当前最多可按 ${resolvedEpisodeCount} 集导入，系统已自动收敛后继续处理。`,
        })
      }

      await startImportFromFile(file, 'short', resolvedEpisodeCount, title)
    } catch (importError) {
      setContentTask({
        mode: 'short',
        status: 'error',
        message: sanitizeContentTaskMessage(
          importError instanceof Error ? importError.message : '',
          '短篇录入失败',
        ),
      })
    }
  }

  const regenerateAdaptationOptions = () => {
    setAdaptationOptions(
      buildAdaptationOptions({
        title: bookTitle,
        chapterCount,
        wordCount,
        scriptExcerpt,
      }),
    )
    setSelectedAdaptationId(null)
    setAdaptationLockedAt(null)
  }

  const lockSelectedAdaptation = () => {
    if (!selectedAdaptationId || !productionSkillState.lockedAt) return
    const nextState = {
      customNote: adaptationCustomNote,
      lockedAt: new Date().toISOString(),
      selectedId: selectedAdaptationId,
      selectedName: selectedAdaptation?.name ?? null,
    }
    setAdaptationLockedAt(nextState.lockedAt)
    persistAdaptationState(bookId, nextState)
    void persistAdaptationStateToServer(bookId, nextState)
  }

  const unlockAdaptation = () => {
    const nextState = {
      customNote: adaptationCustomNote,
      lockedAt: null,
      selectedId: selectedAdaptationId,
      selectedName: selectedAdaptation?.name ?? null,
    }
    setAdaptationLockedAt(null)
    persistAdaptationState(bookId, nextState)
    void persistAdaptationStateToServer(bookId, nextState)
  }

  const updateProductionSkillField = (
    field: 'platform' | 'track' | 'emotionGoal' | 'rhythmStrength' | 'visualStyle' | 'enforcement' | 'customNote',
    value: string,
  ) => {
    setProductionSkillState((current) => ({
      ...current,
      [field]: value,
    }))
  }

  const toggleProductionSkillPriority = (value: string) => {
    setProductionSkillState((current) => {
      const exists = current.priorities.includes(value)
      return {
        ...current,
        priorities: exists
          ? current.priorities.filter((item) => item !== value)
          : [...current.priorities, value],
      }
    })
  }

  const lockProductionSkill = () => {
    if (!productionSkillState.selectedSkillId) return
    const nextState = {
      ...productionSkillState,
      lockedAt: new Date().toISOString(),
    }
    setProductionSkillState(nextState)
    persistProductionSkillState(bookId, nextState)
    void persistProductionSkillStateToServer(bookId, nextState)
  }

  const unlockProductionSkill = () => {
    const nextState = {
      ...productionSkillState,
      lockedAt: null,
    }
    setProductionSkillState(nextState)
    persistProductionSkillState(bookId, nextState)
    void persistProductionSkillStateToServer(bookId, nextState)
  }

  const productionSkillSectionState: ProductionSkillSectionState = {
    skillOptions: productionSkillOptions,
    selectedSkillId: productionSkillState.selectedSkillId,
    platform: productionSkillState.platform,
    track: productionSkillState.track,
    emotionGoal: productionSkillState.emotionGoal,
    rhythmStrength: productionSkillState.rhythmStrength,
    visualStyle: productionSkillState.visualStyle,
    priorities: productionSkillState.priorities,
    enforcement: productionSkillState.enforcement,
    customNote: productionSkillState.customNote,
    lockedAt: productionSkillState.lockedAt,
    runtimeSummary: productionSkillState.runtimeSummary,
  }

  return {
    uploadFile,
    setUploadFile,
    shortTitle,
    setShortTitle,
    shortText,
    setShortText,
    episodeCount,
    setEpisodeCount,
    contentTask,
    adaptationOptions,
    selectedAdaptationId,
    setSelectedAdaptationId,
    adaptationCustomNote,
    setAdaptationCustomNote,
    adaptationLockedAt,
    selectedAdaptation,
    productionSkillSectionState,
    handleNovelUpload,
    handleShortCreate,
    setSelectedProductionSkillId: (value: string | null) => {
      setProductionSkillState((current) => ({
        ...current,
        selectedSkillId: value,
      }))
    },
    updateProductionSkillField,
    toggleProductionSkillPriority,
    lockProductionSkill,
    unlockProductionSkill,
    regenerateAdaptationOptions,
    lockSelectedAdaptation,
    unlockAdaptation,
  }
}
