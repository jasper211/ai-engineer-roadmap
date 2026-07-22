import { useEffect, useState } from 'react'
import { fetchAgentMonitor, type AgentMonitorResponse, type LaunchdJob } from '../lib/api'
import { AgentStatusBadge } from '../components/AgentStatusBadge'

function JobRow({ job }: { job: LaunchdJob }) {
  return (
    <div className="flex items-center justify-between text-xs py-1">
      <span className="font-mono text-text-secondary">{job.label}</span>
      <span className={job.healthy ? 'text-accent-success' : 'text-accent-danger'}>
        {job.pid ? `运行中 (pid ${job.pid})` : `退出码 ${job.last_exit_code}`}
      </span>
    </div>
  )
}

// 五个Agent同时承担两个作用：既是"哪些在自动跑/人工跑/没搭/挂了"的监控器，
// 也是VNW/AIT/方法论转正Agent这三块此前规划里单独占面板的"静态但真实"状态
// 卡片——两者本质是同一份数据(agent_registry.json + launchctl真实状态)，
// 拆成两个视图只会让同一个事实展示两次，所以合而为一。
export function AgentMonitor() {
  const [data, setData] = useState<AgentMonitorResponse | null>(null)

  useEffect(() => {
    fetchAgentMonitor().then(setData)
  }, [])

  if (!data) return <div className="p-6 text-sm text-text-muted">加载中…</div>

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-lg font-heading font-medium">Agent 执行监控器</h1>
        <p className="text-sm text-text-muted mt-1">
          五个主Agent各自的真实自动化状态——基于launchctl真实退出码+代码路径真实存在性检测，不做主观修正。
        </p>
      </div>

      <section className="space-y-3">
        {data.agents.map((a) => (
          <div key={a.agent_id} className="rounded-radius-md border border-border-default bg-bg-elevated p-4">
            <div className="flex items-center gap-3">
              <span className="font-medium text-sm">{a.display_name}</span>
              <AgentStatusBadge status={a.status} />
            </div>
            <p className="text-xs text-text-muted mt-1">{a.description}</p>
            {a.launchd_jobs.length > 0 && (
              <div className="mt-2 border-t border-border-default pt-2 space-y-0.5">
                {a.launchd_jobs.map((j) => <JobRow key={j.label} job={j} />)}
              </div>
            )}
          </div>
        ))}
      </section>

      <section>
        <h2 className="text-sm font-medium text-text-secondary mb-1">Skill 调用频率（PTA自身）</h2>
        <p className="text-xs text-text-muted mb-3">
          从这份日志上线那天开始累计，此前的历史调用量无法补——不代表PTA诞生以来的完整数据。范围只覆盖PTA自己，不含VNW/AIT/OB。
        </p>
        {data.skill_usage.length === 0 ? (
          <p className="text-sm text-text-muted">还没有累计到调用记录</p>
        ) : (
          <div className="rounded-radius-md border border-border-default bg-bg-elevated divide-y divide-border-default">
            {data.skill_usage.map((s) => (
              <div key={s.skill} className="flex items-center justify-between px-4 py-2 text-sm">
                <span className="font-mono">{s.skill}</span>
                <span className="text-text-muted text-xs">
                  {s.count} 次 · 最近 {new Date(s.last_called).toLocaleString('zh-CN')}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
