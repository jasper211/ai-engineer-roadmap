import { useEffect, useState } from 'react'
import { CheckCircle2, XCircle, ChevronDown, ChevronRight } from 'lucide-react'
import {
  fetchProjects, fetchPipelineStatus, fetchPipelineDriftDetail, fetchExecutionHistory,
  type ProjectInfo, type PipelineStatus, type DriftDetail, type ExecutionHistoryEntry,
} from '../lib/api'

function timeAgo(iso: string | null): string {
  if (!iso) return '从未运行'
  const diffMs = Date.now() - new Date(iso).getTime()
  const hours = Math.floor(diffMs / 3600_000)
  if (hours < 1) return '不到1小时前'
  if (hours < 24) return `${hours}小时前`
  return `${Math.floor(hours / 24)}天前`
}

export function PtaStatus() {
  const [projects, setProjects] = useState<ProjectInfo[]>([])
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null)
  const [driftDetail, setDriftDetail] = useState<DriftDetail | null>(null)
  const [driftExpanded, setDriftExpanded] = useState(false)
  const [history, setHistory] = useState<ExecutionHistoryEntry[]>([])

  useEffect(() => {
    fetchProjects().then(setProjects)
    fetchPipelineStatus().then(setPipeline)
    fetchExecutionHistory('all', 20).then(setHistory)
  }, [])

  function toggleDriftDetail() {
    if (!driftExpanded && driftDetail === null) {
      fetchPipelineDriftDetail().then(setDriftDetail)
    }
    setDriftExpanded((v) => !v)
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-8">
      <h1 className="text-lg font-heading font-medium">PTA 运行状态</h1>

      <section>
        <h2 className="text-sm font-medium text-text-secondary mb-3">每日巡检（daily-scan，工作日 11:00）</h2>
        <div className="space-y-2">
          {projects.map((p) => (
            <div key={p.name} className="rounded-radius-md border border-border-default bg-bg-elevated p-4 flex items-center gap-3">
              {p.exists ? <CheckCircle2 size={16} className="text-accent-success" /> : <XCircle size={16} className="text-accent-danger" />}
              <span className="font-medium text-sm">{p.name}</span>
              <span className="ml-auto text-xs text-text-muted">
                最近一次: {timeAgo(p.last_daily_scan?.timestamp ?? null)}
              </span>
            </div>
          ))}
          {projects.length === 0 && <p className="text-sm text-text-muted">daily_scan_projects.json 里没有配置项目</p>}
        </div>
      </section>

      <section>
        <h2 className="text-sm font-medium text-text-secondary mb-3">Pipeline 矩阵漂移检测（pipeline-check，周五 11:00）</h2>
        {pipeline ? (
          <div className="rounded-radius-md border border-border-default bg-bg-elevated p-4">
            {pipeline.report_date ? (
              <>
                <div className="text-sm">最新报告: {pipeline.report_date}</div>
                <button
                  onClick={toggleDriftDetail}
                  className={`flex items-center gap-1 text-sm mt-1 ${pipeline.drift_count > 0 ? 'text-accent-warning' : 'text-accent-success'}`}
                >
                  {pipeline.drift_count > 0 ? <ChevronDown size={14} className={driftExpanded ? '' : '-rotate-90'} /> : null}
                  {pipeline.drift_count > 0 ? `发现 ${pipeline.drift_count} 处与矩阵声明不一致（点击查看详情）` : '本周无drift'}
                </button>
                {driftExpanded && driftDetail && (
                  <div className="mt-3 space-y-2 border-t border-border-default pt-3">
                    {driftDetail.drift_rows.map((row, i) => (
                      <div key={i} className="text-xs">
                        <div className="font-medium text-text-secondary">{row.stage} / {row.dimension}</div>
                        <div className="text-text-muted">声明: {row.claim}</div>
                        <div className="text-text-muted">实测: {row.actual}</div>
                        <div className="text-text-muted">{row.note}</div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <div className="text-sm text-text-muted">还没有检测记录，跑一次 --pipeline-check 生成</div>
            )}
          </div>
        ) : (
          <p className="text-sm text-text-muted">加载中…</p>
        )}
      </section>

      <section>
        <h2 className="text-sm font-medium text-text-secondary mb-3">执行记录（最近20条）</h2>
        {history.length === 0 ? (
          <p className="text-sm text-text-muted">还没有跨项目的执行记录</p>
        ) : (
          <div className="rounded-radius-md border border-border-default bg-bg-elevated divide-y divide-border-default">
            {history.map((h, i) => (
              <div key={i} className="flex items-center justify-between px-4 py-2 text-sm">
                <div className="flex items-center gap-2">
                  {h.status === 'completed'
                    ? <ChevronRight size={14} className="text-accent-success" />
                    : <ChevronRight size={14} className="text-text-muted" />}
                  <span>{h.task_id} · {h.summary}</span>
                </div>
                <span className="text-xs text-text-muted">
                  {h.project_name} · {h.success_rate} · {new Date(h.timestamp).toLocaleString('zh-CN')}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
