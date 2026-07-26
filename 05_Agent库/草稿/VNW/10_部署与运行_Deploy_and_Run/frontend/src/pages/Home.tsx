import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router'
import { loadAllData } from '@/lib/data'
import {
  AlertTriangle, ArrowUpRight, Bot, CheckCircle2, ChevronRight, CircleDot,
  Database, FileCheck2, GitPullRequestArrow, Layers3, RefreshCw, ShieldAlert,
} from 'lucide-react'

const fade = {
  initial: { opacity: 0, y: 14 },
  animate: { opacity: 1, y: 0 },
}

function Metric({
  label, value, hint, icon: Icon, tone = 'primary', onClick,
}: {
  label: string; value: number | string; hint: string; icon: any; tone?: string; onClick?: () => void
}) {
  const tones: Record<string, string> = {
    primary: 'bg-accent-primary/10 text-accent-primary-light',
    danger: 'bg-accent-danger/10 text-accent-danger',
    warning: 'bg-accent-warning/10 text-accent-warning',
    success: 'bg-accent-success/10 text-accent-success',
  }
  return (
    <button onClick={onClick} className="panel group w-full p-4 text-left transition hover:-translate-y-0.5 hover:border-border-hover">
      <div className="flex items-start justify-between gap-3">
        <span className={`grid h-9 w-9 place-items-center rounded-xl ${tones[tone]}`}>
          <Icon className="h-4 w-4" />
        </span>
        <ArrowUpRight className="h-4 w-4 text-text-muted opacity-0 transition group-hover:opacity-100" />
      </div>
      <p className="mt-5 metric-value">{value}</p>
      <p className="mt-1 text-sm font-medium text-text-primary">{label}</p>
      <p className="mt-1 text-[11px] leading-relaxed text-text-muted">{hint}</p>
    </button>
  )
}

export default function Home() {
  const navigate = useNavigate()
  const [data, setData] = useState<Record<string, any[]> | null>(null)
  useEffect(() => { loadAllData().then(setData) }, [])

  const summary = useMemo(() => {
    if (!data) return null
    const nodes = data.node_index || []
    const fused = data.fused_status || []
    const gaps = data.gaps || []
    const actions = data.actions || []
    const audits = data.data_audit || []
    const handoffs = data.ait_handoff || []
    const sops = data.sop_progress || []
    return {
      nodes: nodes.length,
      fused: fused.filter((x: any) => x.fused_status === '熔断').length,
      p0Gaps: gaps.filter((x: any) => x.status === 'open' && x.priority === 'P0').length,
      openGaps: gaps.filter((x: any) => x.status === 'open').length,
      pendingActions: actions.filter((x: any) => !['已完成', 'closed'].includes(x.status)).length,
      auditHigh: audits.filter((x: any) => x.status === 'open' && x.severity === '高').length,
      auditOpen: audits.filter((x: any) => x.status === 'open').length,
      handoffReady: handoffs.filter((x: any) => ['已移交', '可移交'].includes(x.handoff_status)).length,
      handoffTotal: handoffs.length,
      sopTotal: sops.length,
    }
  }, [data])

  if (!data || !summary) {
    return (
      <div className="flex min-h-[70vh] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-9 w-9 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" />
          <p className="mt-3 text-xs text-text-muted">正在载入治理数据</p>
        </div>
      </div>
    )
  }

  const domains = data.domain_progress || []
  const audits = (data.data_audit || []).filter((x: any) => x.status === 'open')
  const criticalAudits = audits.sort((a: any, b: any) => ({ 高: 0, 中: 1, 低: 2 }[a.severity as '高'] - { 高: 0, 中: 1, 低: 2 }[b.severity as '高'])).slice(0, 4)
  const syncDate = domains[0]?.last_updated || '—'

  return (
    <div className="space-y-7">
      <motion.header {...fade} className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <div className="mb-3 flex items-center gap-2">
            <span className="rounded-full border border-accent-primary/30 bg-accent-primary/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-primary-light">
              Governance cockpit
            </span>
            <span className="flex items-center gap-1.5 text-xs text-text-muted">
              <span className="h-1.5 w-1.5 rounded-full bg-accent-success" /> 数据同步 {syncDate}
            </span>
          </div>
          <h1 className="max-w-3xl font-heading text-3xl font-bold tracking-tight text-text-primary sm:text-4xl">
            先看风险，再推动闭环
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-text-secondary">
            从价值节点、规则 Gap 到 SOP 与 AIT 移交，把治理事实收敛成今天可以推进的动作。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => navigate('/gaps-actions')} className="rounded-lg bg-accent-primary px-4 py-2.5 text-sm font-medium text-white shadow-glow transition hover:bg-accent-primary-light">
            处理 Gap 与行动
          </button>
          <button onClick={() => navigate('/data-health')} className="rounded-lg border border-border-default bg-bg-elevated px-4 py-2.5 text-sm font-medium text-text-secondary transition hover:border-border-hover hover:text-text-primary">
            检查数据健康
          </button>
        </div>
      </motion.header>

      {(summary.p0Gaps > 0 || summary.auditHigh > 0) && (
        <motion.div {...fade} transition={{ delay: .04 }} className="flex flex-col gap-3 rounded-2xl border border-accent-danger/25 bg-gradient-to-r from-accent-danger/10 to-transparent p-4 sm:flex-row sm:items-center">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent-danger/15 text-accent-danger">
            <ShieldAlert className="h-5 w-5" />
          </span>
          <div>
            <p className="text-sm font-semibold text-text-primary">需要优先处理的治理风险</p>
            <p className="mt-1 text-xs text-text-secondary">
              {summary.p0Gaps} 个 P0 Gap · {summary.auditHigh} 个高严重度数据问题
            </p>
          </div>
          <button onClick={() => navigate('/gaps-actions')} className="sm:ml-auto flex items-center gap-1 text-xs font-medium text-accent-danger">
            进入处理队列 <ChevronRight className="h-4 w-4" />
          </button>
        </motion.div>
      )}

      <motion.section {...fade} transition={{ delay: .08 }} className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
        <Metric label="价值节点" value={summary.nodes} hint="当前治理对象总量" icon={Layers3} onClick={() => navigate('/nodes')} />
        <Metric label="熔断节点" value={summary.fused} hint="需补建或解除阻塞" icon={AlertTriangle} tone="danger" onClick={() => navigate('/nodes')} />
        <Metric label="开放 Gap" value={summary.openGaps} hint={`${summary.p0Gaps} 个为 P0`} icon={CircleDot} tone="warning" onClick={() => navigate('/gaps-actions')} />
        <Metric label="待推进动作" value={summary.pendingActions} hint="未完成行动项" icon={RefreshCw} tone="warning" onClick={() => navigate('/gaps-actions')} />
        <Metric label="SOP 资产" value={summary.sopTotal} hint="当前已识别 SOP 文件" icon={FileCheck2} tone="success" onClick={() => navigate('/interview-sop')} />
        <Metric label="AIT 可移交" value={summary.handoffReady} hint={`覆盖 ${summary.handoffTotal} 个节点`} icon={GitPullRequestArrow} tone="primary" onClick={() => navigate('/agent-readiness')} />
      </motion.section>

      <div className="grid gap-5 xl:grid-cols-[1.35fr_.85fr]">
        <motion.section {...fade} transition={{ delay: .12 }} className="panel p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="eyebrow">Domain execution</p>
              <h2 className="mt-1 font-heading text-lg font-semibold text-text-primary">业务域推进矩阵</h2>
              <p className="mt-1 text-xs text-text-muted">用规则产出密度判断哪些域已经进入可执行阶段</p>
            </div>
            <button onClick={() => navigate('/domains')} className="text-xs font-medium text-accent-primary-light">查看明细</button>
          </div>
          <div className="mt-5 space-y-3">
            {domains.map((domain: any) => {
              const rules = Number(domain.t5_count || 0)
              const signals = Number(domain.t2_count || 0)
              const ratio = Math.min(100, signals ? Math.round((rules / signals) * 100) : 0)
              return (
                <button key={domain.domain} onClick={() => navigate('/domains')} className="group grid w-full grid-cols-[5.5rem_1fr_auto] items-center gap-3 rounded-xl px-2 py-2 text-left transition hover:bg-bg-surface/70">
                  <div>
                    <p className="font-mono text-xs font-semibold text-text-primary">{domain.domain}</p>
                    <p className="mt-0.5 text-[10px] text-text-muted">{domain.node_count} 节点</p>
                  </div>
                  <div>
                    <div className="h-2 overflow-hidden rounded-full bg-bg-surface">
                      <div className="h-full rounded-full bg-gradient-to-r from-accent-primary to-accent-secondary transition-all" style={{ width: `${ratio}%` }} />
                    </div>
                    <p className="mt-1.5 truncate text-[10px] text-text-muted">{domain.current_phase || '待识别阶段'} · 规则 {rules}</p>
                  </div>
                  <span className="font-mono text-xs text-text-secondary">{ratio}%</span>
                </button>
              )
            })}
          </div>
        </motion.section>

        <motion.section {...fade} transition={{ delay: .16 }} className="panel flex flex-col p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="eyebrow">Data quality</p>
              <h2 className="mt-1 font-heading text-lg font-semibold text-text-primary">待解决的数据问题</h2>
              <p className="mt-1 text-xs text-text-muted">{summary.auditOpen} 个开放问题，按严重度排序</p>
            </div>
            <Database className="h-5 w-5 text-text-muted" />
          </div>
          <div className="mt-5 flex-1 space-y-2">
            {criticalAudits.length ? criticalAudits.map((item: any) => (
              <button key={item.audit_id} onClick={() => navigate('/data-health')} className="flex w-full items-start gap-3 rounded-xl border border-transparent p-3 text-left transition hover:border-border-default hover:bg-bg-surface/60">
                <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${item.severity === '高' ? 'bg-accent-danger' : item.severity === '中' ? 'bg-accent-warning' : 'bg-accent-info'}`} />
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-xs font-medium text-text-primary">{item.audit_type}</p>
                    <span className="rounded bg-bg-surface px-1.5 py-0.5 text-[9px] text-text-muted">{item.scope}</span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-text-muted">{item.issue_desc}</p>
                </div>
              </button>
            )) : (
              <div className="grid h-40 place-items-center text-center">
                <div>
                  <CheckCircle2 className="mx-auto h-7 w-7 text-accent-success" />
                  <p className="mt-2 text-sm text-text-secondary">当前没有开放问题</p>
                </div>
              </div>
            )}
          </div>
          <button onClick={() => navigate('/data-health')} className="mt-4 flex items-center justify-center gap-1 rounded-lg border border-border-default py-2 text-xs text-text-secondary hover:text-text-primary">
            查看完整审计 <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </motion.section>
      </div>

      <motion.section {...fade} transition={{ delay: .2 }} className="grid gap-3 md:grid-cols-3">
        {[
          { title: '规则治理', desc: '从开放 Gap 进入责任人与交付物处理队列', icon: AlertTriangle, route: '/gaps-actions' },
          { title: 'SOP 生产', desc: '查看访谈证据、SOP 生成和缺口回填进度', icon: FileCheck2, route: '/interview-sop' },
          { title: 'Agent 移交', desc: '判断节点是否具备进入 AIT 三轨拆解的条件', icon: Bot, route: '/agent-readiness' },
        ].map(item => (
          <button key={item.title} onClick={() => navigate(item.route)} className="panel group flex items-center gap-4 p-4 text-left transition hover:border-border-hover">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-bg-surface text-accent-primary-light">
              <item.icon className="h-5 w-5" />
            </span>
            <div>
              <p className="text-sm font-semibold text-text-primary">{item.title}</p>
              <p className="mt-1 text-xs leading-relaxed text-text-muted">{item.desc}</p>
            </div>
            <ChevronRight className="ml-auto h-4 w-4 text-text-muted transition group-hover:translate-x-0.5 group-hover:text-text-secondary" />
          </button>
        ))}
      </motion.section>
    </div>
  )
}
