import { useEffect, useMemo, useState } from 'react'
import { useBookOutputs } from './useBookOutputs'
import SceneComposer from './SceneComposer'

export function getEpisodeStorageKey(bookId?: number) {
  return `director-mode-selected-episode:${bookId ?? 'unknown'}`
}

export function readStoredEpisode(bookId?: number) {
  if (!bookId) {
    return null
  }
  const raw = localStorage.getItem(getEpisodeStorageKey(bookId))
  const parsed = raw ? Number(raw) : NaN
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

export function resolveEpisodeSelection(bookId: number | undefined, availableEpisodes: number[], fallbackEpisode: number) {
  const storedEpisode = readStoredEpisode(bookId)

  if (storedEpisode && (availableEpisodes.length === 0 || availableEpisodes.includes(storedEpisode))) {
    return storedEpisode
  }

  if (availableEpisodes.includes(fallbackEpisode)) {
    return fallbackEpisode
  }

  return availableEpisodes[0] ?? 1
}

function EmptyJourneyCard({
  title,
  detail,
  secondaryDetail,
  actions,
}: {
  title: string
  detail: string
  secondaryDetail?: string
  actions: Array<{ label: string; onClick: () => void; primary?: boolean }>
}) {
  return (
    <div className="max-w-2xl rounded-[28px] border border-slate-800 bg-slate-900/80 p-7 shadow-[0_24px_80px_rgba(2,6,23,0.35)]">
      <div className="text-[11px] uppercase tracking-[0.28em] text-sky-300">下一步引导</div>
      <div className="mt-3 text-xl font-semibold text-slate-100">{title}</div>
      <div className="mt-3 text-sm leading-7 text-slate-300">{detail}</div>
      {secondaryDetail ? (
        <div className="mt-3 text-sm leading-7 text-slate-500">{secondaryDetail}</div>
      ) : null}
      <div className="mt-6 flex flex-wrap gap-3">
        {actions.map((action) => (
          <button
            key={action.label}
            onClick={action.onClick}
            className={`rounded-full px-4 py-2 text-sm font-medium transition ${
              action.primary
                ? 'bg-sky-400 text-slate-950 hover:brightness-110'
                : 'border border-slate-700 text-slate-200 hover:border-slate-500 hover:text-white'
            }`}
          >
            {action.label}
          </button>
        ))}
      </div>
    </div>
  )
}

export default function DirectorMode({
  book,
  onBack,
  onOpenPreparation,
  onOpenAdvanced,
}: {
  book?: { id: number; title: string }
  onBack?: () => void
  onOpenPreparation?: () => void
  onOpenAdvanced?: () => void
}) {
  const { data, loading, error, refresh } = useBookOutputs(book?.id)
  const [selectedEpisode, setSelectedEpisode] = useState(() => {
    return resolveEpisodeSelection(book?.id, [], 1)
  })

  const availableEpisodes = useMemo(
    () => Array.from(new Set((data?.scripts ?? []).map((script) => script.episode))).sort((a, b) => a - b),
    [data?.scripts],
  )

  useEffect(() => {
    const nextEpisode = resolveEpisodeSelection(book?.id, availableEpisodes, selectedEpisode)
    setSelectedEpisode((current) => (current === nextEpisode ? current : nextEpisode))
  }, [availableEpisodes, book?.id, selectedEpisode])

  useEffect(() => {
    if (!book?.id) {
      return
    }
    localStorage.setItem(getEpisodeStorageKey(book.id), String(selectedEpisode))
  }, [book?.id, selectedEpisode])

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center bg-slate-950">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
          <div className="text-[14px] text-slate-400">加载项目数据中...</div>
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex flex-1 items-center justify-center bg-slate-950 px-6">
        <div className="max-w-md rounded-2xl border border-red-800/50 bg-red-950/20 p-5 text-center">
          <div className="text-sm font-medium text-red-300">加载失败</div>
          <div className="mt-2 text-sm leading-6 text-slate-300">
            {error ?? '未获取到项目数据，请稍后重试。'}
          </div>
          <button
            onClick={refresh}
            className="mt-4 rounded-full border border-red-700/60 px-4 py-2 text-xs text-red-200 transition hover:border-red-500 hover:text-white"
          >
            重试加载
          </button>
        </div>
      </div>
    )
  }

  if (!book?.id || book.id <= 0) {
    return (
      <div className="flex flex-1 items-center justify-center bg-slate-950 px-6">
        <EmptyJourneyCard
          title="先把内容准备完整，再进入分镜生产画布"
          detail="当前这个新建项目还只是一个空入口。普通用户路径建议先到内容准备导入小说文本、生成剧本和分镜表，再回到分镜生产继续做参考图、分镜图、视频、审片和交付。"
          secondaryDetail="如果你只是想试节点编排，也可以去高级编排手动编辑；但真实用户主路径建议先走内容准备。"
          actions={[
            { label: '去内容准备补齐内容', onClick: () => onOpenPreparation?.(), primary: true },
            { label: '去高级编排手动编辑', onClick: () => onOpenAdvanced?.() },
            { label: '返回项目列表', onClick: () => onBack?.() },
          ]}
        />
      </div>
    )
  }

  if (availableEpisodes.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center bg-slate-950 px-6">
        <EmptyJourneyCard
          title="当前项目还没有可用集数"
          detail={`项目“${book.title}”已经连接到后端，但还没有脚本或分镜集数可映射到画布。`}
          secondaryDetail="下一步建议先去内容准备补齐剧本和分镜，再回来进入镜头生产、审片和交付。"
          actions={[
            { label: '去内容准备补齐剧本/分镜', onClick: () => onOpenPreparation?.(), primary: true },
            { label: '重新检查数据', onClick: refresh },
            { label: '返回项目列表', onClick: () => onBack?.() },
          ]}
        />
      </div>
    )
  }

  if (!availableEpisodes.includes(selectedEpisode)) {
    return (
      <div className="flex flex-1 items-center justify-center bg-slate-950 px-6">
        <EmptyJourneyCard
          title="当前集数不存在"
          detail={`项目“${book.title}”没有第 ${selectedEpisode} 集的数据，请切换到已有集数后继续。`}
          actions={[
            { label: '切到第一可用集', onClick: () => setSelectedEpisode(availableEpisodes[0]), primary: true },
            { label: '返回项目列表', onClick: () => onBack?.() },
          ]}
        />
      </div>
    )
  }

  return (
    <SceneComposer
      key={`scene-composer:${book.id}:${selectedEpisode}`}
      data={data}
      projectId={book.id}
      projectTitle={book.title}
      episode={selectedEpisode}
      availableEpisodes={availableEpisodes}
      onEpisodeChange={setSelectedEpisode}
      storageScope={`book-${book.id}-episode-${selectedEpisode}`}
      onBack={onBack}
      onOpenPreparation={onOpenPreparation}
    />
  )
}
