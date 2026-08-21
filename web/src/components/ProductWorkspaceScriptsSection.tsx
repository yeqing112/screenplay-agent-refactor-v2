import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from 'react'
import type { ScriptOutput, StoryboardShotOutput } from '../domain/bookOutputs'
import type { EpisodeProgress } from './productWorkspaceProgress'
import {
  buildScriptEpisodeSummaries,
  parseScriptScenes,
  type ScriptWorkbenchResponse,
} from './productWorkspaceScripts'
import { getScriptDecision, type ScriptDecisionMap } from './productWorkspaceScriptDecisions'

type WorkspaceSection = 'qa' | 'storyboard'

interface Props {
  bookId: number
  scripts: ScriptOutput[]
  shotsByEpisode: Record<number, StoryboardShotOutput[]>
  episodeProgress: EpisodeProgress[]
  scriptDecisionState: ScriptDecisionMap
  onScriptDecisionStateChange: Dispatch<SetStateAction<ScriptDecisionMap>>
  hasLockedAdaptation: boolean
  hasExplicitLockedAdaptation: boolean
  adaptationStateLabel: string
  adaptationStateDetail: string
  selectedAdaptationName?: string
  onNavigate: (section: WorkspaceSection, options?: { episode?: number | null }) => void
  onGenerateScripts: () => void
  isGeneratingScripts: boolean
}

function tone(status: 'done' | 'pending' | 'blocked') {
  if (status === 'done') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
  if (status === 'blocked') return 'border-rose-500/30 bg-rose-500/10 text-rose-200'
  return 'border-amber-500/30 bg-amber-500/10 text-amber-200'
}

function versionTone(status?: string) {
  const normalized = String(status ?? '').trim().toLowerCase()
  if (normalized === 'recheck_passed' || normalized === 'resolved') {
    return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
  }
  if (normalized === 'rechecking' || normalized === 'fixing' || normalized === 'fixed') {
    return 'border-violet-500/30 bg-violet-500/10 text-violet-200'
  }
  return 'border-amber-500/30 bg-amber-500/10 text-amber-200'
}

function formatLocalTime(value: string | null) {
  if (!value) return '未记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function buildScriptStatusLabel(status?: string) {
  const normalized = String(status ?? '').trim().toLowerCase()
  if (!normalized) return '未知'
  if (normalized === 'done' || normalized === 'completed') return '已完成'
  if (normalized === 'running' || normalized === 'processing') return '处理中'
  if (normalized === 'pending' || normalized === 'draft') return '待完善'
  return normalized
}

function buildDecisionSummary(lockedAt: string | null, releasedAt: string | null) {
  if (releasedAt) return '已放行到分镜'
  if (lockedAt) return '已锁稿待放行'
  return '尚未锁稿'
}

function buildDecisionHistoryBadge(
  releasedAt: string | null,
  lockedAt: string | null,
  hasExplicitLockedAdaptation: boolean,
) {
  if (releasedAt) {
    return hasExplicitLockedAdaptation ? '已放行' : '历史已放行'
  }
  if (lockedAt) return '已锁稿'
  return null
}

function buildDecisionSummaryWithContext(params: {
  lockedAt: string | null
  releasedAt: string | null
  hasExplicitLockedAdaptation: boolean
}) {
  const { lockedAt, releasedAt, hasExplicitLockedAdaptation } = params
  if (releasedAt) {
    return hasExplicitLockedAdaptation ? '已放行到分镜' : '历史曾放行，但当前不应继续下游'
  }
  if (lockedAt) return '已锁稿待放行'
  return '尚未锁稿'
}

export default function ProductWorkspaceScriptsSection({
  bookId,
  scripts,
  shotsByEpisode,
  episodeProgress,
  scriptDecisionState,
  onScriptDecisionStateChange,
  hasLockedAdaptation,
  hasExplicitLockedAdaptation,
  adaptationStateLabel,
  adaptationStateDetail,
  selectedAdaptationName,
  onNavigate,
  onGenerateScripts,
  isGeneratingScripts,
}: Props) {
  const [qaWorkbench, setQaWorkbench] = useState<ScriptWorkbenchResponse | null>(null)
  const [workbenchState, setWorkbenchState] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle')
  const [selectedEpisode, setSelectedEpisode] = useState<number | null>(scripts[0]?.episode ?? null)
  const [decisionNote, setDecisionNote] = useState('')

  useEffect(() => {
    if (bookId <= 0) return

    let cancelled = false
    setWorkbenchState('loading')

    fetch(`/api/books/${bookId}/qa/workbench`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        return response.json()
      })
      .then((payload: ScriptWorkbenchResponse) => {
        if (cancelled) return
        setQaWorkbench(payload)
        setWorkbenchState('loaded')
      })
      .catch(() => {
        if (cancelled) return
        setWorkbenchState('error')
      })

    return () => {
      cancelled = true
    }
  }, [bookId])

  const episodeSummaries = useMemo(
    () =>
      buildScriptEpisodeSummaries({
        scripts,
        episodeProgress,
        qaWorkbench,
        shotsByEpisode,
        scriptDecisionState,
        hasLockedAdaptation,
      }),
    [episodeProgress, hasLockedAdaptation, qaWorkbench, scriptDecisionState, scripts, shotsByEpisode],
  )

  const sceneCountByEpisode = useMemo(
    () =>
      new Map(
        scripts.map((script) => [script.episode, parseScriptScenes(script.content ?? '').length]),
      ),
    [scripts],
  )

  useEffect(() => {
    if (episodeSummaries.length === 0) {
      setSelectedEpisode(null)
      return
    }

    if (selectedEpisode && episodeSummaries.some((item) => item.episode === selectedEpisode)) {
      return
    }

    setSelectedEpisode(episodeSummaries[0]?.episode ?? null)
  }, [episodeSummaries, selectedEpisode])

  const selectedSummary =
    episodeSummaries.find((item) => item.episode === selectedEpisode) ?? episodeSummaries[0] ?? null
  const selectedScript = scripts.find((item) => item.episode === selectedSummary?.episode) ?? null
  const selectedWorkbench =
    (qaWorkbench?.episodes ?? []).find((item) => Number(item.episode ?? 0) === selectedSummary?.episode) ?? null
  const selectedScenes = useMemo(() => parseScriptScenes(selectedScript?.content ?? ''), [selectedScript?.content])
  const selectedDecision = selectedSummary ? getScriptDecision(scriptDecisionState, selectedSummary.episode) : null
  const adaptationInheritanceSummary = buildAdaptationInheritanceSummary({
    hasLockedAdaptation: hasExplicitLockedAdaptation,
    adaptationStateLabel,
    adaptationStateDetail,
    selectedAdaptationName,
    selectedEpisode: selectedSummary?.episode ?? null,
  })

  useEffect(() => {
    setDecisionNote(selectedDecision?.note ?? '')
  }, [selectedDecision?.note, selectedSummary?.episode])

  const releaseChecklist = selectedSummary
    ? [
        {
          label: '项目改编方向已锁定',
          status: hasLockedAdaptation ? 'done' : 'blocked',
        },
        {
          label: '本集已有正式剧本',
          status: selectedSummary.scriptLength > 0 ? 'done' : 'blocked',
        },
        {
          label: '脚本 QA 已清空',
          status: selectedSummary.openScriptIssueCount === 0 ? 'done' : 'blocked',
        },
        {
          label: '允许进入镜头工作台',
          status: selectedSummary.releaseStatus,
        },
      ]
    : []

  const updateDecision = async (
    episode: number,
    updater: (current: { lockedAt: string | null; releasedAt: string | null; note: string }) => {
      lockedAt: string | null
      releasedAt: string | null
      note: string
    },
  ) => {
    const current = getScriptDecision(scriptDecisionState, episode)
    const next = updater(current)

    onScriptDecisionStateChange((state) => ({
      ...state,
      [String(episode)]: next,
    }))

    try {
      const response = await fetch(`/api/books/${bookId}/script-decisions/${episode}`, {
        method: 'PUT',
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lockedAt: next.lockedAt,
          releasedAt: next.releasedAt,
          note: next.note,
        }),
      })
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const payload = await response.json()
      const decision = payload?.decision ?? {}
      onScriptDecisionStateChange((state) => ({
        ...state,
        [String(episode)]: {
          lockedAt: typeof decision.locked_at === 'string' ? decision.locked_at : null,
          releasedAt: typeof decision.released_at === 'string' ? decision.released_at : null,
          note: typeof decision.note === 'string' ? decision.note : next.note,
        },
      }))
    } catch {
      onScriptDecisionStateChange((state) => ({
        ...state,
        [String(episode)]: current,
      }))
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[0.95fr_1.2fr_0.95fr]">
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="text-sm font-medium text-white">分集剧本列表</div>
          <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">
            {episodeSummaries.length} 集
          </span>
        </div>
        <div className="mt-3 text-xs leading-6 text-slate-400">
          这里按集聚合剧本状态、脚本 QA、版本数量、场次数量和进入分镜前的放行判断。
        </div>
        <div className="mt-4 space-y-3">
          {episodeSummaries.length > 0 ? (
            episodeSummaries.map((item) => {
              const decision = scriptDecisionState[String(item.episode)]
              const decisionBadge = buildDecisionHistoryBadge(
                decision?.releasedAt ?? null,
                decision?.lockedAt ?? null,
                hasExplicitLockedAdaptation,
              )
              return (
                <button
                  key={item.episode}
                  type="button"
                  onClick={() => setSelectedEpisode(item.episode)}
                  className={`w-full rounded-xl border p-4 text-left transition ${
                    selectedSummary?.episode === item.episode
                      ? 'border-sky-500/50 bg-sky-500/10'
                      : 'border-slate-800 bg-slate-950/50 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-medium text-white">第 {item.episode} 集</div>
                    <span className={`rounded-full border px-2 py-0.5 text-[11px] ${tone(item.releaseStatus)}`}>
                      {item.releaseLabel}
                    </span>
                  </div>
                  <div className="mt-2 text-xs text-slate-500">{item.progressLabel}</div>
                  <div className="mt-2 text-xs text-slate-400">{item.nextAction}</div>
                  <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-slate-300">
                    <span className="rounded-full border border-slate-700 px-2 py-0.5">
                      脚本 QA Open {item.openScriptIssueCount}
                    </span>
                    <span className="rounded-full border border-slate-700 px-2 py-0.5">版本 {item.versionCount}</span>
                    <span className="rounded-full border border-slate-700 px-2 py-0.5">镜头 {item.shotCount}</span>
                    <span className="rounded-full border border-slate-700 px-2 py-0.5">
                      场次 {sceneCountByEpisode.get(item.episode) ?? item.sceneCount}
                    </span>
                    {decisionBadge ? (
                      <span
                        className={`rounded-full border px-2 py-0.5 ${
                          decision?.releasedAt
                            ? hasExplicitLockedAdaptation
                              ? 'border-sky-500/30 bg-sky-500/10 text-sky-200'
                              : 'border-amber-500/30 bg-amber-500/10 text-amber-200'
                            : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
                        }`}
                      >
                        {decisionBadge}
                      </span>
                    ) : null}
                  </div>
                </button>
              )
            })
          ) : (
            <div className="rounded-xl border border-dashed border-slate-700 bg-slate-950/40 p-6 text-center">
              <div className="text-sm text-slate-400">当前项目还没有正式剧本输出。</div>
              <div className="mt-3 text-xs text-slate-500">需要先完成改编方向锁定，再生成分集大纲和剧本。</div>
              <button
                type="button"
                onClick={onGenerateScripts}
                disabled={isGeneratingScripts}
                className="mt-4 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-500 disabled:bg-blue-900/50 disabled:text-slate-500"
              >
                {isGeneratingScripts ? (
                  <>
                    <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
                    生成中...
                  </>
                ) : (
                  '一键生成剧本'
                )}
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="space-y-6">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-lg font-semibold text-white">
                {selectedSummary ? `第 ${selectedSummary.episode} 集剧本详情` : '剧本详情'}
              </div>
              <div className="mt-1 text-sm text-slate-400">
                剧本状态、长度、评分、脚本 QA、场次拆解与版本变更在这里统一汇总。
              </div>
            </div>
            {selectedSummary ? (
              <span className={`rounded-full border px-2 py-0.5 text-[11px] ${tone(selectedSummary.releaseStatus)}`}>
                {selectedSummary.releaseLabel}
              </span>
            ) : null}
          </div>

          {selectedSummary ? (
            <>
              <div className="mt-5 grid gap-3 md:grid-cols-4">
                <MetricCard label="脚本状态" value={buildScriptStatusLabel(selectedSummary.scriptStatus)} />
                <MetricCard label="脚本长度" value={`${selectedSummary.scriptLength} 字`} />
                <MetricCard label="QA 分数" value={selectedSummary.overallScore === null ? '暂无' : `${selectedSummary.overallScore}`} />
                <MetricCard label="脚本 QA Open" value={`${selectedSummary.openScriptIssueCount}`} />
              </div>

              <div className="mt-5 grid gap-3 md:grid-cols-4">
                <MetricCard label="场次数量" value={`${selectedSummary.sceneCount}`} />
                <MetricCard label="镜头数量" value={`${selectedSummary.shotCount}`} />
                <MetricCard label="版本数量" value={`${selectedSummary.versionCount}`} />
                <MetricCard
                  label="锁稿状态"
                  value={buildDecisionSummaryWithContext({
                    lockedAt: selectedDecision?.lockedAt ?? null,
                    releasedAt: selectedDecision?.releasedAt ?? null,
                    hasExplicitLockedAdaptation,
                  })}
                />
              </div>

              <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                <div className="text-sm font-medium text-white">脚本正文摘录</div>
                <div className="mt-3 max-h-[340px] overflow-auto whitespace-pre-wrap text-sm leading-6 text-slate-300">
                  {selectedScript?.content?.trim() || '当前还没有可展示的正式剧本内容。'}
                </div>
              </div>

              <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-medium text-white">场次管理视图</div>
                  <div className="text-xs text-slate-500">{selectedScenes.length} 个场次</div>
                </div>
                <div className="mt-4 space-y-3">
                  {selectedScenes.length > 0 ? (
                    selectedScenes.map((scene) => (
                      <div key={`${scene.index}-${scene.title}`} className="rounded-xl border border-slate-800 bg-slate-900/70 p-3">
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-sm font-medium text-white">{scene.heading}</div>
                          <div className="text-xs text-slate-500">{scene.title}</div>
                        </div>
                        <div className="mt-2 grid gap-2 text-xs text-slate-400 md:grid-cols-3">
                          <div>时间：{scene.timeLabel || '暂无'}</div>
                          <div>地点：{scene.locationLabel || '暂无'}</div>
                          <div>人物：{scene.characterLabel || '暂无'}</div>
                        </div>
                        <div className="mt-2 text-sm text-slate-300">
                          {scene.beatPreview || '当前场次还没有提取到关键片段。'}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900/50 p-3 text-sm text-slate-400">
                      当前还没有提取出结构化场次，后续可以继续接入 LLM 做更精细的场次拆解。
                    </div>
                  )}
                </div>
              </div>

              <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-medium text-white">脚本 QA 与版本</div>
                  <div className="text-xs text-slate-500">
                    {workbenchState === 'loading'
                      ? '正在加载 QA 工作台'
                      : workbenchState === 'error'
                        ? 'QA 工作台加载失败'
                        : '已接入真实 QA 工作台'}
                  </div>
                </div>
                <div className="mt-4 grid gap-3 md:grid-cols-3">
                  <MetricCard label="开放问题总数" value={`${selectedSummary.openIssueCount}`} />
                  <MetricCard label="脚本层问题" value={`${selectedSummary.openScriptIssueCount}`} />
                  <MetricCard label="非脚本层问题" value={`${selectedSummary.openNonScriptIssueCount}`} />
                </div>
                <div className="mt-4 space-y-3">
                  {(selectedWorkbench?.versions ?? []).length > 0 ? (
                    (selectedWorkbench?.versions ?? []).slice(0, 6).map((version) => (
                      <div
                        key={version.id ?? `${version.version_no ?? 'v'}-${version.created_at ?? ''}`}
                        className="rounded-xl border border-slate-800 bg-slate-900/70 p-3"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-sm font-medium text-white">
                            {version.label || `v${version.version_no ?? '?'}`}
                          </div>
                          <span className={`rounded-full border px-2 py-0.5 text-[11px] ${versionTone(version.recheck_status)}`}>
                            {version.recheck_status || 'pending'}
                          </span>
                        </div>
                        <div className="mt-2 text-xs text-slate-500">
                          {version.change_type || 'manual'} / {version.operator_name || 'system'}
                        </div>
                        {version.change_reason ? (
                          <div className="mt-2 text-sm text-slate-300">{version.change_reason}</div>
                        ) : null}
                        {version.recheck_summary ? (
                          <div className="mt-2 text-xs text-slate-500">{version.recheck_summary}</div>
                        ) : null}
                      </div>
                    ))
                  ) : (
                    <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900/50 p-3 text-sm text-slate-400">
                      当前还没有脚本版本记录。
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : null}
        </div>
      </div>

      <div className="space-y-6">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="text-lg font-semibold text-white">上游约束</div>
          <div className="mt-3 text-sm leading-6 text-slate-400">
            剧本工作台不是孤立编辑页。这里需要明确继承项目级改编方向，再决定当前这一集是否允许继续锁稿和放行。
          </div>
          <div className="mt-4 space-y-3">
            <div className="rounded-xl border border-slate-800 bg-slate-950/50 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm text-slate-200">项目级改编方向</span>
                <span className={`rounded-full border px-2 py-0.5 text-[11px] ${tone(hasExplicitLockedAdaptation ? 'done' : 'blocked')}`}>
                  {adaptationStateLabel}
                </span>
              </div>
              <div className="mt-2 text-xs leading-6 text-slate-500">{adaptationInheritanceSummary}</div>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4 text-sm leading-6 text-slate-300">
              {hasExplicitLockedAdaptation
                ? `当前集${selectedSummary ? `第 ${selectedSummary.episode} 集` : ''}的锁稿、场次拆解和分镜放行，都应沿“${selectedAdaptationName ?? '当前主方向'}”执行。`
                : adaptationStateDetail}
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="text-lg font-semibold text-white">进入分镜前检查</div>
          <div className="mt-3 text-sm leading-6 text-slate-400">
            把“脚本准备好了吗”显式拆成放行动作，而不是默认用户自行判断。
          </div>
          {selectedSummary ? (
            <>
              <div className="mt-5 space-y-3">
                {releaseChecklist.map((item) => (
                  <div
                    key={item.label}
                    className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/50 px-4 py-3"
                  >
                    <span className="text-sm text-slate-300">{item.label}</span>
                    <span className={`rounded-full border px-2 py-0.5 text-[11px] ${tone(item.status as 'done' | 'pending' | 'blocked')}`}>
                      {item.status}
                    </span>
                  </div>
                ))}
              </div>

              <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4 text-sm leading-6 text-slate-300">
                {selectedSummary.releaseReason}
              </div>

              <div className="mt-5 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                <div className="text-sm font-medium text-white">锁稿 / 放行</div>
                <div className="mt-3 text-xs text-slate-500">
                  记录本集剧本已经锁稿、是否允许进入分镜，以及相关说明。
                </div>
                <textarea
                  value={decisionNote}
                  onChange={(event) => setDecisionNote(event.target.value)}
                  placeholder="记录锁稿理由、退回原因或放行说明"
                  className="mt-4 h-24 w-full rounded-xl border border-slate-800 bg-slate-900/70 px-3 py-2 text-sm text-slate-200 outline-none transition focus:border-sky-500"
                />
                <div className="mt-4 grid gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      if (!selectedSummary) return
                      updateDecision(selectedSummary.episode, (current) => ({
                        ...current,
                        lockedAt: new Date().toISOString(),
                        note: decisionNote.trim(),
                      }))
                    }}
                    disabled={!selectedSummary || selectedSummary.scriptLength === 0 || !hasExplicitLockedAdaptation}
                    className="rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-4 py-3 text-sm font-medium text-emerald-100 transition hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {selectedDecision?.lockedAt ? '重新锁稿' : '确认锁稿'}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (!selectedSummary) return
                      updateDecision(selectedSummary.episode, (current) => ({
                        ...current,
                        lockedAt: current.lockedAt ?? new Date().toISOString(),
                        releasedAt: new Date().toISOString(),
                        note: decisionNote.trim(),
                      }))
                    }}
                    disabled={
                      !selectedSummary ||
                      !selectedDecision?.lockedAt ||
                      selectedSummary.openScriptIssueCount > 0 ||
                      !hasExplicitLockedAdaptation
                    }
                    className="rounded-xl border border-sky-500/40 bg-sky-500/10 px-4 py-3 text-sm font-medium text-sky-100 transition hover:bg-sky-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    放行到分镜
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (!selectedSummary) return
                      updateDecision(selectedSummary.episode, () => ({
                        lockedAt: null,
                        releasedAt: null,
                        note: decisionNote.trim(),
                      }))
                    }}
                    className="rounded-xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-sm text-slate-200 transition hover:border-slate-600"
                  >
                    清空决策
                  </button>
                </div>
                {!hasExplicitLockedAdaptation ? (
                  <div className="mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm leading-6 text-amber-100">
                    当前项目主方向还没有锁定。这里会保留历史锁稿 / 放行记录，但不会继续放行新的剧本决策，也不建议直接进入镜头工作台。
                  </div>
                ) : null}
                <div className="mt-4 space-y-2 text-xs text-slate-400">
                  <div>锁稿时间：{formatLocalTime(selectedDecision?.lockedAt ?? null)}</div>
                  <div>放行时间：{formatLocalTime(selectedDecision?.releasedAt ?? null)}</div>
                </div>
              </div>

              <div className="mt-5 grid gap-3">
                <button
                  type="button"
                  onClick={() => onNavigate('storyboard', { episode: selectedSummary.episode })}
                  disabled={selectedSummary.releaseStatus !== 'done' || !hasExplicitLockedAdaptation}
                  className="rounded-xl border border-sky-500/40 bg-sky-500/10 px-4 py-3 text-sm font-medium text-sky-100 transition hover:bg-sky-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  前往镜头工作台
                </button>
                <button
                  type="button"
                  onClick={() => onNavigate('qa', { episode: selectedSummary.episode })}
                  className="rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-200 transition hover:border-slate-600"
                >
                  查看 QA 修复
                </button>
              </div>
            </>
          ) : null}
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="text-sm font-medium text-white">当前阶段结论</div>
          <div className="mt-3 text-sm leading-6 text-slate-400">
            剧本工作台现在已经能承接真实剧本、真实 QA 工作台、场次拆解、脚本版本历史，以及锁稿 / 放行决策。后续继续把这些状态同步回项目控制台和镜头工作台，就能更稳定地串起主链路。
          </div>
        </div>
      </div>
    </div>
  )
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-2 text-sm font-medium text-white">{value}</div>
    </div>
  )
}

function buildAdaptationInheritanceSummary({
  hasLockedAdaptation,
  adaptationStateLabel,
  adaptationStateDetail,
  selectedAdaptationName,
  selectedEpisode,
}: {
  hasLockedAdaptation: boolean
  adaptationStateLabel: string
  adaptationStateDetail: string
  selectedAdaptationName?: string
  selectedEpisode: number | null
}) {
  if (hasLockedAdaptation) {
    return `当前项目主方向状态：${adaptationStateLabel}。${selectedEpisode ? `第 ${selectedEpisode} 集` : '当前剧本'}后续版本、锁稿备注与分镜放行，都应继承“${selectedAdaptationName ?? '当前主方向'}”的叙事约束。`
  }

  return `当前项目主方向状态：${adaptationStateLabel}。${adaptationStateDetail} 建议先回改编方向完成锁定，再继续剧本决策。`
}
