import type { AdaptationOption } from './productWorkspaceAdaptation'
import type { ProductionSkillSectionState } from './productWorkspaceSectionContracts'

interface Props {
  contentReady: boolean
  productionSkill?: ProductionSkillSectionState
  adaptationOptions: AdaptationOption[]
  selectedAdaptationId: string | null
  selectedAdaptationName?: string | null
  adaptationCustomNote: string
  hasLockedAdaptation: boolean
  adaptationStateLabel: string
  adaptationStateDetail: string
  canGenerateCandidates: boolean
  canLockAdaptation: boolean
  canLockProductionSkill?: boolean
  onSelectProductionSkill?: (id: string | null) => void
  onProductionSkillFieldChange?: (
    field: 'platform' | 'track' | 'emotionGoal' | 'rhythmStrength' | 'visualStyle' | 'enforcement' | 'customNote',
    value: string,
  ) => void
  onToggleProductionSkillPriority?: (value: string) => void
  onLockProductionSkill?: () => void
  onUnlockProductionSkill?: () => void
  onRegenerate: () => void
  onSelect: (id: string) => void
  onCustomNoteChange: (value: string) => void
  onLock: () => void
  onUnlock: () => void
  onNavigateSection?: (section: 'content' | 'scripts') => void
}

export default function ProductWorkspaceAdaptationSection({
  contentReady,
  productionSkill,
  adaptationOptions,
  selectedAdaptationId,
  selectedAdaptationName,
  adaptationCustomNote,
  hasLockedAdaptation,
  adaptationStateLabel,
  adaptationStateDetail,
  canGenerateCandidates,
  canLockAdaptation,
  canLockProductionSkill,
  onSelectProductionSkill,
  onProductionSkillFieldChange,
  onToggleProductionSkillPriority,
  onLockProductionSkill,
  onUnlockProductionSkill,
  onRegenerate,
  onSelect,
  onCustomNoteChange,
  onLock,
  onUnlock,
  onNavigateSection,
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
  const safeCanLockProductionSkill = Boolean(canLockProductionSkill)
  const safeOnSelectProductionSkill = onSelectProductionSkill ?? (() => {})
  const safeOnProductionSkillFieldChange = onProductionSkillFieldChange ?? (() => {})
  const safeOnToggleProductionSkillPriority = onToggleProductionSkillPriority ?? (() => {})
  const safeOnLockProductionSkill = onLockProductionSkill ?? (() => {})
  const safeOnUnlockProductionSkill = onUnlockProductionSkill ?? (() => {})
  const isActuallyLocked = hasLockedAdaptation
  const selectedOption =
    adaptationOptions.find((option) => option.id === selectedAdaptationId) ?? null
  const handoffItems = buildAdaptationHandoffItems({
    contentReady,
    hasLockedAdaptation: isActuallyLocked,
    selectedAdaptationId,
    canLockAdaptation,
  })
  const handoffSummary = buildAdaptationHandoffSummary({
    contentReady,
    hasLockedAdaptation: isActuallyLocked,
    selectedAdaptationName,
    selectedAdaptationId,
    canLockAdaptation,
  })
  const nextSectionAction = buildAdaptationNextSectionAction({
    contentReady,
    hasLockedAdaptation: isActuallyLocked,
  })
  const selectionHint = buildSelectionHint({
    contentReady,
    selectedAdaptationName: selectedOption?.name ?? selectedAdaptationName ?? null,
    hasLockedAdaptation: isActuallyLocked,
  })
  const lockHint = buildLockHint({
    contentReady,
    selectedAdaptationId,
    hasLockedAdaptation: isActuallyLocked,
    canLockAdaptation,
  })

  return (
    <div className="grid gap-6 xl:grid-cols-[1.2fr_0.9fr]">
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-lg font-semibold text-white">{'改编方向候选'}</div>
            <div className="mt-2 text-sm leading-6 text-slate-400">
              {
                '先生成 2-3 个项目级候选方向，再锁定一个主方向。后续剧本、分镜和资产策略都要继承这套约束。'
              }
            </div>
          </div>
          <button
            type="button"
            onClick={onRegenerate}
            disabled={!canGenerateCandidates || isActuallyLocked}
            className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-300 transition disabled:cursor-not-allowed disabled:text-slate-600"
          >
            {'重新生成候选'}
          </button>
        </div>

        <div className="mt-5 grid gap-4">
          {adaptationOptions.map((option) => {
            const selected = selectedAdaptationId === option.id
            return (
              <button
                key={option.id}
                type="button"
                aria-pressed={selected}
                onClick={() => {
                  if (!isActuallyLocked) onSelect(option.id)
                }}
                disabled={!contentReady}
                className={`rounded-xl border p-4 text-left transition ${
                  selected
                    ? 'border-sky-500/40 bg-sky-500/10 shadow-[0_0_0_1px_rgba(56,189,248,0.15)]'
                    : 'border-slate-800 bg-slate-950/50 hover:border-slate-700'
                } ${!contentReady ? 'cursor-not-allowed opacity-60' : ''}`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-white">{option.name}</div>
                    {selected && !isActuallyLocked ? (
                      <div className="mt-2 inline-flex rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-[11px] text-sky-200">
                        {'当前已选中，下一步可锁定'}
                      </div>
                    ) : null}
                    {selected && isActuallyLocked ? (
                      <div className="mt-2 inline-flex rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-200">
                        {'当前主方向'}
                      </div>
                    ) : null}
                  </div>
                  <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">
                    {option.strength}
                  </span>
                </div>

                <div className="mt-3 grid gap-2 text-sm text-slate-300 md:grid-cols-2">
                  <InfoCell label="目标受众" value={option.audience} />
                  <InfoCell label="节奏策略" value={option.rhythm} />
                  <InfoCell label="一句话卖点" value={option.hook} spanFull />
                  <InfoCell label="保留内容" value={option.keep} />
                  <InfoCell label="强化内容" value={option.enhance} />
                  <InfoCell label="风险提示" value={option.risk} spanFull />
                </div>
              </button>
            )
          })}
        </div>

        <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/50 p-4 text-sm leading-6 text-slate-300">
          {selectionHint}
        </div>
      </div>

      <div className="space-y-6">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="text-lg font-semibold text-white">Production Skill</div>
          <div className="mt-3 text-sm leading-6 text-slate-400">
            先锁定赛道化生产 skill，再去确定改编方向。后续剧本、分镜、资产、QA 都会继承这套规范。
          </div>

          <div className="mt-4 space-y-4">
            <label className="block text-xs text-slate-500">
              技能包
              <select
                value={resolvedProductionSkill.selectedSkillId ?? ''}
                onChange={(event) => safeOnSelectProductionSkill(event.target.value || null)}
                disabled={Boolean(resolvedProductionSkill.lockedAt)}
                className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white"
              >
                {resolvedProductionSkill.skillOptions.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.name}
                  </option>
                ))}
              </select>
            </label>

            <div className="grid gap-3 md:grid-cols-2">
              <label className="block text-xs text-slate-500">
                平台
                <input
                  type="text"
                  value={resolvedProductionSkill.platform}
                  disabled={Boolean(resolvedProductionSkill.lockedAt)}
                  onChange={(event) => safeOnProductionSkillFieldChange('platform', event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white"
                />
              </label>
              <label className="block text-xs text-slate-500">
                赛道
                <input
                  type="text"
                  value={resolvedProductionSkill.track}
                  disabled={Boolean(resolvedProductionSkill.lockedAt)}
                  onChange={(event) => safeOnProductionSkillFieldChange('track', event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white"
                />
              </label>
              <label className="block text-xs text-slate-500">
                情绪目标
                <input
                  type="text"
                  value={resolvedProductionSkill.emotionGoal}
                  disabled={Boolean(resolvedProductionSkill.lockedAt)}
                  onChange={(event) => safeOnProductionSkillFieldChange('emotionGoal', event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white"
                />
              </label>
              <label className="block text-xs text-slate-500">
                节奏强度
                <input
                  type="text"
                  value={resolvedProductionSkill.rhythmStrength}
                  disabled={Boolean(resolvedProductionSkill.lockedAt)}
                  onChange={(event) => safeOnProductionSkillFieldChange('rhythmStrength', event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white"
                />
              </label>
              <label className="block text-xs text-slate-500">
                视觉风格
                <input
                  type="text"
                  value={resolvedProductionSkill.visualStyle}
                  disabled={Boolean(resolvedProductionSkill.lockedAt)}
                  onChange={(event) => safeOnProductionSkillFieldChange('visualStyle', event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white"
                />
              </label>
              <label className="block text-xs text-slate-500">
                执行强度
                <input
                  type="text"
                  value={resolvedProductionSkill.enforcement}
                  disabled={Boolean(resolvedProductionSkill.lockedAt)}
                  onChange={(event) => safeOnProductionSkillFieldChange('enforcement', event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white"
                />
              </label>
            </div>

            <div>
              <div className="text-xs text-slate-500">优先目标</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {['storyboard', 'assets', 'mystery', 'emotion', 'payoff'].map((item) => {
                  const active = resolvedProductionSkill.priorities.includes(item)
                  return (
                    <button
                      key={item}
                      type="button"
                      disabled={Boolean(resolvedProductionSkill.lockedAt)}
                      onClick={() => safeOnToggleProductionSkillPriority(item)}
                      className={`rounded-full border px-3 py-1 text-xs transition ${
                        active
                          ? 'border-sky-500/40 bg-sky-500/10 text-sky-200'
                          : 'border-slate-700 text-slate-300'
                      }`}
                    >
                      {item}
                    </button>
                  )
                })}
              </div>
            </div>

            <label className="block text-xs text-slate-500">
              项目补充约束
              <textarea
                value={resolvedProductionSkill.customNote}
                disabled={Boolean(resolvedProductionSkill.lockedAt)}
                onChange={(event) => safeOnProductionSkillFieldChange('customNote', event.target.value)}
                className="mt-1 h-24 w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white"
              />
            </label>

            <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4 text-sm leading-6 text-slate-300">
              {resolvedProductionSkill.runtimeSummary?.skill_name
                ? `${resolvedProductionSkill.runtimeSummary.skill_name} / ${resolvedProductionSkill.runtimeSummary.track} / ${resolvedProductionSkill.runtimeSummary.platform}`
                : '当前还没有加载到生产 skill 摘要。'}
            </div>

            <div className="flex flex-wrap gap-2">
              {!resolvedProductionSkill.lockedAt ? (
                <button
                  type="button"
                  onClick={safeOnLockProductionSkill}
                  disabled={!safeCanLockProductionSkill}
                  className="rounded-lg border border-fuchsia-600/50 bg-fuchsia-500/10 px-3 py-2 text-sm text-fuchsia-200 transition disabled:cursor-not-allowed disabled:text-slate-600"
                >
                  锁定 Production Skill
                </button>
              ) : (
                <button
                  type="button"
                  onClick={safeOnUnlockProductionSkill}
                  className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-300 transition hover:border-slate-700 hover:text-white"
                >
                  解除 Skill 锁定
                </button>
              )}
            </div>
          </div>
        </div>

        <InfoPanel
          title="项目级方向状态"
          action={adaptationStateLabel}
          description={
            isActuallyLocked
              ? `当前主方向：${selectedAdaptationName ?? '已锁定主方向'}`
              : adaptationStateDetail
          }
        />

        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="text-sm font-medium text-white">{'上游交接状态'}</div>
          <div className="mt-3 text-sm leading-6 text-slate-400">
            {
              '把内容准备、候选选择和项目级锁定拆开看，避免误以为“已经选了方案”就等于可以直接继续下游生产。'
            }
          </div>
          <div className="mt-4 space-y-3">
            {handoffItems.map((item) => (
              <div
                key={item.label}
                className="flex items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950/50 px-4 py-3"
              >
                <div className="min-w-0">
                  <div className="text-sm text-slate-200">{item.label}</div>
                  <div className="mt-1 text-xs text-slate-500">{item.detail}</div>
                </div>
                <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] ${tone(item.status)}`}>
                  {item.statusLabel}
                </span>
              </div>
            ))}
          </div>
          <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/50 p-4 text-sm leading-6 text-slate-300">
            {handoffSummary}
          </div>
          {nextSectionAction && onNavigateSection ? (
            <button
              type="button"
              onClick={() => onNavigateSection(nextSectionAction.section)}
              className="mt-4 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 transition hover:border-sky-500 hover:text-white"
            >
              {nextSectionAction.label}
            </button>
          ) : null}
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="text-sm font-medium text-white">{'补充约束'}</div>
          <textarea
            value={adaptationCustomNote}
            onChange={(event) => onCustomNoteChange(event.target.value)}
            placeholder="例如：保留危险关系与误判感，首集尽量前置悬念钩子，不走甜宠改编。"
            className="mt-4 h-32 w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white placeholder:text-slate-600"
          />
          <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/50 p-3 text-sm leading-6 text-slate-300">
            {lockHint}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {!isActuallyLocked ? (
              <button
                type="button"
                onClick={onLock}
                disabled={!canLockAdaptation}
                className="rounded-lg border border-sky-600/50 bg-sky-500/10 px-3 py-2 text-sm text-sky-200 transition disabled:cursor-not-allowed disabled:text-slate-600"
              >
                {'锁定为主方向'}
              </button>
            ) : null}
            {isActuallyLocked ? (
              <button
                type="button"
                onClick={onUnlock}
                className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-300 transition hover:border-slate-700 hover:text-white"
              >
                {'解除锁定'}
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}

function tone(status: 'done' | 'pending' | 'blocked') {
  if (status === 'done') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
  if (status === 'blocked') return 'border-rose-500/30 bg-rose-500/10 text-rose-200'
  return 'border-amber-500/30 bg-amber-500/10 text-amber-200'
}

function statusLabel(status: 'done' | 'pending' | 'blocked') {
  if (status === 'done') return '已就绪'
  if (status === 'blocked') return '未满足'
  return '待确认'
}

function buildAdaptationHandoffItems({
  contentReady,
  hasLockedAdaptation,
  selectedAdaptationId,
  canLockAdaptation,
}: {
  contentReady: boolean
  hasLockedAdaptation: boolean
  selectedAdaptationId: string | null
  canLockAdaptation: boolean
}) {
  const candidateStatus: 'done' | 'pending' | 'blocked' = selectedAdaptationId
    ? hasLockedAdaptation
      ? 'done'
      : 'pending'
    : 'blocked'
  const downstreamStatus: 'done' | 'pending' | 'blocked' = hasLockedAdaptation
    ? 'done'
    : canLockAdaptation
      ? 'pending'
      : 'blocked'

  return [
    {
      label: '内容准备已具备',
      detail: contentReady ? '内容基础已建立，可以正式进入项目级主方向决策。' : '需要先回内容准备补齐原文链路，再生成或锁定主方向。',
      status: contentReady ? 'done' : 'blocked',
      statusLabel: statusLabel(contentReady ? 'done' : 'blocked'),
    },
    {
      label: '候选方向已选定',
      detail: selectedAdaptationId
        ? '当前已有候选主方向，可继续补充约束并执行项目级锁定。'
        : '先从候选方案中选定一个主方向，再进入正式锁定。',
      status: candidateStatus,
      statusLabel: statusLabel(candidateStatus),
    },
    {
      label: '允许进入剧本工作台',
      detail: hasLockedAdaptation
        ? '主方向已锁定，后续剧本、分镜和资产提示词都应继承这套方向约束。'
        : canLockAdaptation
          ? '当前已经接近放行条件，完成锁定后即可继续剧本工作台。'
          : '尚未达到放行条件，暂不建议继续下游剧本生产。',
      status: downstreamStatus,
      statusLabel: statusLabel(downstreamStatus),
    },
  ] as const
}

function buildAdaptationHandoffSummary({
  contentReady,
  hasLockedAdaptation,
  selectedAdaptationName,
  selectedAdaptationId,
  canLockAdaptation,
}: {
  contentReady: boolean
  hasLockedAdaptation: boolean
  selectedAdaptationName?: string | null
  selectedAdaptationId: string | null
  canLockAdaptation: boolean
}) {
  if (!contentReady) {
    return '当前主链路应先回到内容准备，补齐原文导入与内容基础，再来做项目级改编方向锁定。'
  }

  if (hasLockedAdaptation) {
    return `当前项目已锁定主方向：${selectedAdaptationName ?? '已锁定主方向'}。下一步应进入剧本工作台，让分集剧本、分镜和资产统一继承这套约束。`
  }

  if (selectedAdaptationId && canLockAdaptation) {
    return '当前候选方向已经选中，建议现在就补充约束并锁定，避免剧本工作台继续沿未确认方向生产。'
  }

  if (selectedAdaptationId) {
    return '当前虽然已经选中候选方向，但仍未达到正式锁定状态，暂时不建议继续下游剧本生产。'
  }

  return '当前还没有项目级主方向。请先选择候选方案，再决定是否锁定为后续剧本与分镜的统一约束。'
}

function buildAdaptationNextSectionAction({
  contentReady,
  hasLockedAdaptation,
}: {
  contentReady: boolean
  hasLockedAdaptation: boolean
}) {
  if (!contentReady) {
    return { section: 'content' as const, label: '返回内容准备' }
  }

  if (hasLockedAdaptation) {
    return { section: 'scripts' as const, label: '进入剧本工作台' }
  }

  return null
}

function buildSelectionHint({
  contentReady,
  selectedAdaptationName,
  hasLockedAdaptation,
}: {
  contentReady: boolean
  selectedAdaptationName: string | null
  hasLockedAdaptation: boolean
}) {
  if (!contentReady) {
    return '内容准备尚未完成，当前候选只用于预览，暂时不能进入正式锁定。'
  }

  if (hasLockedAdaptation) {
    return `当前项目已经锁定主方向：${selectedAdaptationName ?? '已锁定主方向'}。后续剧本与分镜都应沿这套约束继续生产。`
  }

  if (selectedAdaptationName) {
    return `已选中候选方向：${selectedAdaptationName}。可以继续补充约束，然后执行项目级锁定。`
  }

  return '请先从上方候选卡中选择一个主方向，锁定按钮才会启用。'
}

function buildLockHint({
  contentReady,
  selectedAdaptationId,
  hasLockedAdaptation,
  canLockAdaptation,
}: {
  contentReady: boolean
  selectedAdaptationId: string | null
  hasLockedAdaptation: boolean
  canLockAdaptation: boolean
}) {
  if (hasLockedAdaptation) {
    return '当前项目主方向已经锁定；如需重走路线，先解除锁定，再重新选择候选方案。'
  }

  if (!contentReady) {
    return '请先完成内容准备，上游内容基础补齐后才能锁定项目级主方向。'
  }

  if (!selectedAdaptationId) {
    return '请先选择一个候选方向，锁定按钮才会启用。'
  }

  if (canLockAdaptation) {
    return '当前已满足锁定条件。锁定后，剧本、分镜、提示词和资产策略都应统一继承该方向。'
  }

  return '当前已选中候选方向，但仍未满足正式锁定条件，请先补齐上游限制项。'
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
          <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">
            {action}
          </span>
        ) : null}
      </div>
      <div className="mt-3 text-sm leading-6 text-slate-400">{description}</div>
    </div>
  )
}

function InfoCell({ label, value, spanFull }: { label: string; value: string; spanFull?: boolean }) {
  return (
    <div className={`rounded-lg border border-slate-800 bg-slate-900/40 p-3 ${spanFull ? 'md:col-span-2' : ''}`}>
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-2 text-sm leading-6 text-slate-300">{value}</div>
    </div>
  )
}
