import type { TaskCenterEntry } from './productWorkspaceTasks'

type TaskCenterStats = {
  total: number
  running: number
  queued: number
  error: number
  blocked: number
  skipped: number
  done: number
  globalCount: number
  actionableCount: number
  nextFocus: TaskCenterEntry | null
}

export default function TaskCenterOverviewPanel({ stats }: { stats: TaskCenterStats }) {
  return (
    <div className="min-w-0 rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="text-sm font-medium text-white">任务中心概览</div>

      <div className="mt-4 grid gap-3">
        <OverviewMetricCard title="总任务数" value={`${stats.total}`} detail="主链路任务与批量调度入口统一收口" />
        <OverviewMetricCard title="待推进" value={`${stats.actionableCount}`} detail="进行中、待执行、待修复任务总数" />
        <OverviewMetricCard title="批量调度" value={`${stats.globalCount}`} detail="全项目级批量 / 全局任务入口" />
        <OverviewMetricCard title="等待上游" value={`${stats.blocked}`} detail="明确暴露被上游卡住的节点" />
        <OverviewMetricCard title="已跳过" value={`${stats.skipped}`} detail="当前无执行条件的任务不会伪装成失败" />
        <OverviewMetricCard title="已完成" value={`${stats.done}`} detail="已经走通的任务会下沉为稳定背景状态" />
      </div>

      <div className="mt-5 space-y-3">
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <div className="text-xs text-slate-500">当前阶段建议</div>
          <div className="mt-2 text-sm leading-6 text-slate-300">
            {stats.nextFocus
              ? `当前最值得先处理的是「${stats.nextFocus.type}」：${stats.nextFocus.statusReason || stats.nextFocus.detail}`
              : '当前没有新的阻塞，任务中心处于相对平稳状态。'}
          </div>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <div className="text-xs text-slate-500">当前能力</div>
          <div className="mt-2 text-sm leading-6 text-slate-300">
            任务中心现在不仅展示任务状态，也能直接查询真实创意任务、继续回收结果，并基于原始输入重新发起失败任务。
          </div>
        </div>
      </div>
    </div>
  )
}

function OverviewMetricCard({ title, value, detail }: { title: string; value: string; detail: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
      <div className="text-xs text-slate-500">{title}</div>
      <div className="mt-2 text-lg font-semibold text-white">{value}</div>
      <div className="mt-1 text-xs text-slate-400">{detail}</div>
    </div>
  )
}
