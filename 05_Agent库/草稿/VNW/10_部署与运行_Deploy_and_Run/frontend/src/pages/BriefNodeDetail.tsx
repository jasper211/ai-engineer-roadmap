import { useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router'
import { motion } from 'framer-motion'
import { loadAllData, getDomainInfo } from '@/lib/data'
import { StatusBadge, PriorityBadge } from '@/components/StatusBadge'
import { ArrowLeft, Flame, CheckCircle2, AlertTriangle, ArrowRightCircle, Info } from 'lucide-react'

export default function BriefNodeDetail() {
  const { nodeId } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState<any>(null)

  useState(() => {
    if (!data) loadAllData().then(setData)
  })

  if (!data) return <div className="flex min-h-[60vh] items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" /></div>

  const node = (data.node_index || []).find((n: any) => n.node_id === nodeId)
  if (!node) {
    return (
      <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 text-center">
        <p className="text-text-secondary">未找到节点 {nodeId}</p>
        <button onClick={() => navigate('/brief')} className="text-sm text-accent-primary hover:underline">返回列表</button>
      </div>
    )
  }

  const dInfo = getDomainInfo(node.node_id)
  const fused = (data.fused_status || []).find((f: any) => f.node_id === nodeId)
  const fusedTasks = (data.fused_tasks || []).filter((t: any) => t.node_id === nodeId)
  const risks = (data.deliverable_risk || []).filter((r: any) => r.node_id === nodeId)
  const handoff = (data.ait_handoff || []).find((h: any) => h.node_id === nodeId)

  const taskDone = fusedTasks.filter((t: any) => t.task_status === '已完成').length

  return (
    <div className="space-y-5">
      <button onClick={() => navigate('/brief')} className="flex items-center gap-1.5 text-sm text-text-muted hover:text-text-secondary">
        <ArrowLeft className="h-4 w-4" /> 返回节点列表
      </button>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-wrap items-center gap-3">
        <span className="h-3 w-3 rounded-full" style={{ backgroundColor: dInfo.color }} />
        <h1 className="font-heading text-2xl font-bold text-text-primary">{node.node_name}</h1>
        <span className="rounded bg-bg-surface px-2 py-0.5 font-mono text-xs text-text-muted">{node.node_id}</span>
        <PriorityBadge priority={node.priority} />
      </motion.div>

      {/* 核心结论:自动化/Skill就绪度 */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
        className={`rounded-xl border p-5 ${fused?.fused_status === '熔断' ? 'border-accent-danger/30 bg-accent-danger/5' : 'border-accent-success/30 bg-accent-success/5'}`}>
        <div className="flex items-center gap-2">
          {fused?.fused_status === '熔断' ? <Flame className="h-5 w-5 text-accent-danger" /> : <CheckCircle2 className="h-5 w-5 text-accent-success" />}
          <h2 className="font-heading text-base font-semibold text-text-primary">自动化 / Skill 就绪度评估</h2>
        </div>

        {fused ? (
          <div className="mt-3 space-y-2">
            <div className="flex items-center gap-2"><StatusBadge status={fused.fused_status} /><span className="text-sm text-text-secondary">{fused.fused_type || (fused.fused_status === '非熔断' ? '规则基础已具备,未发现阻断性缺口' : '')}</span></div>
            {fused.fused_status === '熔断' && (
              <p className="text-xs text-text-muted">来源:{fused.source}</p>
            )}
          </div>
        ) : (
          <p className="mt-3 text-sm text-text-muted">该节点尚无熔断状态判定记录。</p>
        )}

        {fused?.fused_status === '熔断' && fusedTasks.length > 0 && (
          <div className="mt-4 rounded-lg border border-border-default bg-bg-elevated p-3">
            <p className="text-xs font-medium text-text-secondary">补建任务进度 {taskDone}/{fusedTasks.length} 已完成</p>
            <div className="mt-2 space-y-1.5">
              {fusedTasks.map((t: any) => (
                <div key={t.task_id} className="flex items-center justify-between gap-2 text-xs">
                  <span className="text-text-secondary">{t.task_name}</span>
                  <StatusBadge status={t.task_status} />
                </div>
              ))}
            </div>
          </div>
        )}

        {risks.length > 0 && (
          <div className="mt-4 space-y-3">
            <p className="text-xs font-medium text-text-secondary">交付物四标签风险分析</p>
            {risks.map((r: any) => (
              <div key={r.analysis_id} className="rounded-lg border border-border-default bg-bg-elevated p-3 text-xs">
                <p className="font-medium text-text-primary">{r.deliverable_name}</p>
                <p className="mt-1.5 text-text-secondary"><span className="text-text-muted">A·类型与风险:</span> {r.a_type}{r.a_risk ? ` — ${r.a_risk}` : ''}</p>
                {r.c_blind_spot && <p className="mt-1 text-text-secondary"><span className="text-text-muted">C·验证盲点:</span> {r.c_blind_spot}</p>}
                {r.d_auth_level && <p className="mt-1 text-text-secondary"><span className="text-text-muted">D·授权级别:</span> {r.d_auth_level}</p>}
              </div>
            ))}
          </div>
        )}

        <div className="mt-4 flex items-start gap-2 rounded-lg bg-bg-surface p-3 text-xs text-text-muted">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>L4级自动化Tier(Auto/Aug/Hybrid/Human)与候选Agent归属目前只做到L4活动颗粒度,还无法可靠地关联回具体价值节点——这是已知数据缺口,不在此处编造。<Link to="/brief/automation" className="text-accent-primary hover:underline">查看全域L4自动化评估参考 →</Link></span>
        </div>
      </motion.div>

      {/* 流程背景 */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
        className="rounded-xl border border-border-default bg-bg-elevated p-5">
        <h2 className="font-heading text-base font-semibold text-text-primary">流程背景与现状</h2>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="所属L3流程" value={node.l3_flow} />
          <Field label="流程现状" value={node.l3_status} />
          <Field label="生产方" value={node.producer} />
          <Field label="消费方" value={node.consumer} />
          <Field label="交付物组成" value={node.composition} />
          <Field label="KPI锚点" value={node.kpi_anchors} />
        </div>
        {node.single_point_risk && (
          <div className="mt-3 flex items-start gap-2 rounded-lg border border-accent-warning/30 bg-accent-warning/5 p-3 text-xs text-accent-warning">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>单点风险:{node.single_point_risk}</span>
          </div>
        )}
      </motion.div>

      {/* 验证与下一步 */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
        className="rounded-xl border border-border-default bg-bg-elevated p-5">
        <div className="flex items-center gap-2">
          <ArrowRightCircle className="h-5 w-5 text-accent-primary" />
          <h2 className="font-heading text-base font-semibold text-text-primary">验证与下一步</h2>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <StatusBadge status={handoff?.handoff_status || '未移交'} />
          {handoff?.pilot_flag === 'TRUE' && <span className="rounded-full bg-accent-primary/10 px-2 py-0.5 text-xs text-accent-primary-light">AIT试点中</span>}
        </div>
        {handoff?.next_action ? (
          <p className="mt-2 text-sm text-text-secondary">下一步:{handoff.next_action}{handoff.decision_ref ? `(依据 ${handoff.decision_ref})` : ''}</p>
        ) : (
          <p className="mt-2 text-sm text-text-muted">尚未安排下线验证。若确认该节点具备自动化/Skill搭建条件,下一步是移交AIT进入方案设计。</p>
        )}
      </motion.div>
    </div>
  )
}

function Field({ label, value }: { label: string; value?: string }) {
  if (!value) return null
  return (
    <div>
      <p className="text-xs text-text-muted">{label}</p>
      <p className="mt-0.5 text-sm text-text-secondary">{value}</p>
    </div>
  )
}
