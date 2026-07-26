import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router'
import { motion } from 'framer-motion'
import { loadAllData, getDomainInfo } from '@/lib/data'
import { StatusBadge, PriorityBadge } from '@/components/StatusBadge'
import { ArrowLeft, Flame, CheckCircle2, AlertTriangle, ArrowRightCircle, FlaskConical, PauseCircle, HelpCircle, GitBranch } from 'lucide-react'

export default function BriefNodeDetail() {
  const { nodeId } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState<any>(null)
  const [decision, setDecision] = useState('')

  useEffect(() => { loadAllData().then(setData) }, [])
  useEffect(() => {
    setDecision(localStorage.getItem(`vnw-decision-${nodeId}`) || '')
  }, [nodeId])

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
  const deliverables = (data.deliverables || []).filter((d: any) =>
    d.node_id === nodeId || d.vn_id === nodeId || d.value_node_id === nodeId
  )
  const flowContext = (data.flow_context || []).find((row: any) => row.node_id === nodeId)?.blueprint

  const taskDone = fusedTasks.filter((t: any) => t.task_status === '已完成').length
  const isFused = fused?.fused_status === '熔断'
  const mappedL4Codes: string[] = flowContext?.node_l4_map?.[nodeId || ''] || []
  const conclusion = isFused ? '暂不进入 AI 工具设计' : '可进入业务验证'
  const evidenceText = isFused
    ? `${fused.fused_type || '规则或交付物基础仍有缺口'}；补建任务完成 ${taskDone}/${fusedTasks.length}`
    : '当前权威清单未将该节点列为熔断节点'
  const conditionText = isFused
    ? '完成补建任务、核验交付物，并由负责人确认解除熔断'
    : '确认业务价值、使用场景、输入数据与人工授权边界'
  const actionText = isFused ? '继续补建并安排复核' : '发起小范围业务验证'

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

      {/* 1. 核心结论 */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
        className={`rounded-xl border p-5 ${fused?.fused_status === '熔断' ? 'border-accent-danger/30 bg-accent-danger/5' : 'border-accent-success/30 bg-accent-success/5'}`}>
        <div className="flex items-center gap-2">
          {fused?.fused_status === '熔断' ? <Flame className="h-5 w-5 text-accent-danger" /> : <CheckCircle2 className="h-5 w-5 text-accent-success" />}
          <h2 className="font-heading text-base font-semibold text-text-primary">1 · 核心判断</h2>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <JudgmentField label="结论" value={fused ? conclusion : '待形成判断'} emphasis />
          <JudgmentField label="判断依据" value={fused ? evidenceText : '尚无权威熔断状态记录'} />
          <JudgmentField label={isFused ? '解除条件' : '验证条件'} value={conditionText} />
          <JudgmentField label="建议动作" value={actionText} emphasis />
        </div>
        {fused && <p className="mt-3 text-[11px] text-text-muted">判断来源：{fused.source} · 更新日期 {fused.last_updated}</p>}

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

      </motion.div>

      {/* 2. 交付物与流程背景 */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
        className="rounded-xl border border-border-default bg-bg-elevated p-5">
        <h2 className="font-heading text-base font-semibold text-text-primary">2 · 交付物与流程现状</h2>
        {deliverables.length > 0 && (
          <div className="mt-3 rounded-lg border border-border-default bg-bg-surface p-3">
            <p className="text-xs text-text-muted">已有交付物记录</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {deliverables.map((item: any, index: number) => (
                <span key={item.deliverable_id || index} className="rounded-md bg-bg-elevated px-2 py-1 text-xs text-text-secondary">
                  {item.deliverable_name || item.name || item.deliverable || `交付物 ${index + 1}`}
                </span>
              ))}
            </div>
          </div>
        )}
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
        {flowContext && (
          <div className="mt-4 rounded-lg border border-border-default bg-bg-surface p-4">
            <div className="flex items-center gap-2">
              <GitBranch className="h-4 w-4 text-accent-primary-light" />
              <p className="text-sm font-semibold text-text-primary">{flowContext.l3_code} · {flowContext.l3_name}</p>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <Field label="流程状态" value={flowContext.status} />
              <Field label="主责与协作" value={[flowContext.owner, flowContext.collaborators].filter(Boolean).join('；')} />
              <Field label="触发条件" value={flowContext.trigger} />
              <Field label="退出条件" value={flowContext.exit} />
              <Field label="上游流程" value={flowContext.upstream} />
              <Field label="下游流程" value={flowContext.downstream} />
            </div>
            <p className="mt-3 text-[11px] text-text-muted">来源：{flowContext.source_file}</p>
          </div>
        )}

        {flowContext?.steps?.length > 0 && (
          <div className="mt-4">
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-text-primary">完整流程步骤</p>
                <p className="mt-1 text-xs text-text-muted">蓝色步骤表示流程蓝图已明确映射到当前价值节点。</p>
              </div>
              {mappedL4Codes.length === 0 && <span className="rounded-full bg-accent-warning/10 px-2 py-1 text-xs text-accent-warning">尚无步骤级映射</span>}
            </div>
            <div className="mt-3 space-y-2">
              {flowContext.steps.map((step: any, index: number) => {
                const highlighted = mappedL4Codes.includes(step.l4_code)
                return (
                  <div key={step.step_id} className="flex gap-3">
                    <div className="flex w-7 shrink-0 flex-col items-center">
                      <span className={`grid h-7 w-7 place-items-center rounded-full text-xs font-medium ${highlighted ? 'bg-accent-primary text-white' : 'border border-border-default bg-bg-surface text-text-muted'}`}>{index + 1}</span>
                      {index < flowContext.steps.length - 1 && <span className={`h-full w-px ${highlighted ? 'bg-accent-primary/50' : 'bg-border-default'}`} />}
                    </div>
                    <div className={`mb-2 flex-1 rounded-lg border p-3 ${highlighted ? 'border-accent-primary/50 bg-accent-primary/10' : 'border-border-default bg-bg-surface'}`}>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium text-text-primary">{step.step_name}</span>
                        {step.l4_code && <span className="font-mono text-xs text-text-muted">{step.l4_code}</span>}
                        {highlighted && <span className="rounded-full bg-accent-primary px-2 py-0.5 text-[11px] text-white">当前价值节点</span>}
                      </div>
                      {step.activities?.length > 0 && <p className="mt-1 text-xs text-text-secondary">{step.activities.join('；')}</p>}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {flowContext?.l4s?.length > 0 && (
          <div className="mt-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-text-primary">L4 自动化评估</p>
              <Link to="/brief/automation" className="text-xs text-accent-primary hover:underline">查看全域评估 →</Link>
            </div>
            <div className="mt-2 space-y-2">
              {flowContext.l4s.map((l4: any) => (
                <div key={l4.l4_code} className={`rounded-lg border p-3 ${mappedL4Codes.includes(l4.l4_code) ? 'border-accent-primary/50 bg-accent-primary/5' : 'border-border-default bg-bg-surface'}`}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-text-muted">{l4.l4_code}</span>
                    <span className="text-sm font-medium text-text-primary">{l4.l4_name}</span>
                    <StatusBadge status={l4.automation_tier || '待评估'} />
                  </div>
                  <p className="mt-2 text-xs text-text-secondary">{automationNarrative(l4)}</p>
                  {l4.judgment_basis && <p className="mt-1 text-xs text-text-muted">判断依据：{l4.judgment_basis}</p>}
                  {l4.candidate_agent && <p className="mt-1 text-xs text-text-muted">候选承载：{l4.candidate_agent}</p>}
                </div>
              ))}
            </div>
          </div>
        )}
      </motion.div>

      {/* 3-5. 决策、AIT移交与设计归档 */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
        className="rounded-xl border border-border-default bg-bg-elevated p-5">
        <div className="flex items-center gap-2">
          <ArrowRightCircle className="h-5 w-5 text-accent-primary" />
          <h2 className="font-heading text-base font-semibold text-text-primary">3 · 业务决定：是否进入验证？</h2>
        </div>
        <p className="mt-2 text-sm text-text-secondary">这一步只做业务决策，不要求业务负责人先理解 Agent 架构。</p>
        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          <DecisionButton active={decision === 'validate'} icon={<FlaskConical className="h-4 w-4" />} title="进入验证" desc="确认价值与使用场景" onClick={() => saveDecision('validate')} />
          <DecisionButton active={decision === 'clarify'} icon={<HelpCircle className="h-4 w-4" />} title="补充信息" desc="规则或交付物仍不清楚" onClick={() => saveDecision('clarify')} />
          <DecisionButton active={decision === 'pause'} icon={<PauseCircle className="h-4 w-4" />} title="暂不推进" desc="当前收益或优先级不足" onClick={() => saveDecision('pause')} />
        </div>
        {decision && <p className="mt-3 text-xs text-accent-success">本机已记录选择；后续接入正式工作流时再同步到 VNW 数据底座。</p>}

        <div className="my-5 border-t border-border-default" />
        <h3 className="text-sm font-semibold text-text-primary">4 · AIT 接入状态</h3>
        <div className="mt-3 flex items-center gap-2">
          <StatusBadge status={handoff?.handoff_status || '未移交'} />
          {handoff?.pilot_flag === 'TRUE' && <span className="rounded-full bg-accent-primary/10 px-2 py-0.5 text-xs text-accent-primary-light">AIT试点中</span>}
        </div>
        {handoff?.next_action ? (
          <p className="mt-2 text-sm text-text-secondary">下一步:{handoff.next_action}{handoff.decision_ref ? `(依据 ${handoff.decision_ref})` : ''}</p>
        ) : (
          <p className="mt-2 text-sm text-text-muted">尚未安排验证。选择“进入验证”并完成业务验证后，再移交 AIT。</p>
        )}
        <div className="mt-4 rounded-lg border border-border-default bg-bg-surface p-3">
          <p className="text-xs font-medium text-text-secondary">5 · 形成设计记录</p>
          <p className="mt-1 text-xs text-text-muted">AIT 接入后，将验证结论沉淀为工具、Skill 或 Agent 的边界、输入输出、规则、授权与验收标准。</p>
        </div>
      </motion.div>
    </div>
  )

  function saveDecision(value: string) {
    setDecision(value)
    localStorage.setItem(`vnw-decision-${nodeId}`, value)
  }
}

function automationNarrative(l4: any) {
  const target = l4.physical_deliverable_ideal || l4.blueprint_deliverable || '该活动交付物'
  const tierText: Record<string, string> = {
    Auto: `适合优先验证端到端自动化，目标是稳定生成“${target}”，重点核实输入数据完整性和异常处理。`,
    Aug: `适合先搭建辅助型 Skill，由 AI 处理信息整理与初稿，人负责判断和确认“${target}”。`,
    Hybrid: `适合设计人机协同方案：AI 承担标准步骤，人保留关键判断、授权和验收。目标交付物为“${target}”。`,
    Human: `当前仍应以人工执行为主，可先从资料检索、检查清单或留痕辅助切入，不宜直接追求全自动。`,
  }
  return tierText[l4.automation_tier] || `尚未完成自动化分级，建议围绕“${target}”补充输入、规则、授权和验收条件。`
}

function JudgmentField({ label, value, emphasis = false }: { label: string; value: string; emphasis?: boolean }) {
  return (
    <div className="rounded-lg border border-border-default bg-bg-elevated p-3">
      <p className="text-xs text-text-muted">{label}</p>
      <p className={`mt-1 text-sm ${emphasis ? 'font-semibold text-text-primary' : 'text-text-secondary'}`}>{value}</p>
    </div>
  )
}

function DecisionButton({ active, icon, title, desc, onClick }: { active: boolean; icon: React.ReactNode; title: string; desc: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className={`rounded-lg border p-3 text-left transition-colors ${active ? 'border-accent-primary bg-accent-primary/10' : 'border-border-default bg-bg-surface hover:border-text-muted'}`}>
      <span className={`flex items-center gap-2 text-sm font-medium ${active ? 'text-accent-primary-light' : 'text-text-primary'}`}>{icon}{title}</span>
      <span className="mt-1 block text-xs text-text-muted">{desc}</span>
    </button>
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
