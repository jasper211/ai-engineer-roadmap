import { useEffect, useState } from 'react'
import { CheckCircle2, XCircle } from 'lucide-react'
import { fetchProjects, fetchPipelineStatus, type ProjectInfo, type PipelineStatus } from '../lib/api'

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

  useEffect(() => {
    fetchProjects().then(setProjects)
    fetchPipelineStatus().then(setPipeline)
  }, [])

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
                <div className={`text-sm mt-1 ${pipeline.drift_count > 0 ? 'text-accent-warning' : 'text-accent-success'}`}>
                  {pipeline.drift_count > 0 ? `发现 ${pipeline.drift_count} 处与矩阵声明不一致` : '本周无drift'}
                </div>
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
        <h2 className="text-sm font-medium text-text-secondary mb-3">其他Agent</h2>
        <p className="text-sm text-text-muted">
          VNW / AIT / 方法论转正Agent / OB — 暂不接入本阶段，见优先级排序（各自仍在早期/另项目管理中）。
        </p>
      </section>
    </div>
  )
}
