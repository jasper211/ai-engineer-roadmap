import {
  BookOpen, CheckCircle2, ClipboardCheck, Compass, FileText, Footprints,
  Lightbulb, Link2, X,
} from 'lucide-react'
import { type Task } from '../lib/api'

interface Props {
  task: Task | null
  onClose: () => void
  onSaved?: () => Promise<void>
}

function suggestionFor(task: Task) {
  if (task.personal_bucket === 'pending_evaluation') {
    return '先验证这项能力能否映射到 EA 的具体流程、任务或人机协同节点；映射成立后，再转为行动事项。'
  }
  if (task.needs_mark_alignment) {
    return '先基于文件事实形成内部方案和备选路径，完成内部对齐后，再带方案线下找 Mark 裁定。'
  }
  if (task.personal_bucket === 'ea_application') {
    return '将 Jasper 侧能力映射到 EA 的具体流程与任务，先做小范围验证，再决定是否纳入 SOP 或人机规则。'
  }
  return '围绕受影响的 EA 流程定位人机分工、信号、响应规则和可 Agent 化任务，优先补齐规则缺口。'
}

function executionReferenceFor(task: Task) {
  if (task.personal_bucket === 'pending_evaluation') return [
    '找到一个明确的 EA 流程、L3 或端到端任务作为映射对象。',
    '说明 Jasper 变化能解决什么问题，以及现行流程为什么无法满足。',
    '形成“可应用 / 暂不可应用”的判断，并保留证据与限制条件。',
  ]
  if (task.personal_bucket === 'ea_application') return [
    '定位对应的 EA 流程、SOP、任务节点及当前人机分工。',
    '设计最小验证场景，明确输入信号、Agent 动作、人工介入点和输出。',
    '验证通过后，更新人机协同流程、SOP 或规则，并记录适用边界。',
  ]
  return [
    '从来源文件确认变化事实，并定位受影响的端到端流程与具体任务。',
    '识别当前人工动作、可用信号、规则缺口及 Agent 化前置条件。',
    '产出调整方案，明确人工与 Agent 分工、异常升级路径和验证方式。',
  ]
}

function idealDeliverableFor(task: Task) {
  if (task.acceptance_criteria) return task.acceptance_criteria
  if (task.personal_bucket === 'pending_evaluation') {
    return '一份 EA 应用评估结论：对应流程与任务、可解决的问题、应用前提、风险限制，以及是否进入行动区。'
  }
  if (task.personal_bucket === 'ea_application') {
    return '一份可落地的 EA 应用方案：流程映射、人机分工、信号与响应规则、验证记录，以及需要更新的 SOP。'
  }
  return '一套可执行的人机协同设计：目标流程、任务清单、人机分工、信号与规则、Agent 化候选、异常升级与验收依据。'
}

function Module({ icon: Icon, index, title, children }: {
  icon: typeof BookOpen
  index: string
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="rounded-2xl border border-border-default bg-bg-base/45 p-5">
      <div className="flex items-center gap-3">
        <span className="font-mono text-[10px] text-text-muted">{index}</span>
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-bg-surface text-accent-secondary"><Icon size={15}/></span>
        <h3 className="font-heading text-sm font-semibold">{title}</h3>
      </div>
      <div className="mt-4 text-sm leading-7 text-text-secondary">{children}</div>
    </section>
  )
}

export function TaskDecisionDrawer({ task, onClose }: Props) {
  if (!task) return null
  const steps = executionReferenceFor(task)

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="工作事项详情">
      <button className="absolute inset-0 bg-black/55 backdrop-blur-sm" onClick={onClose} aria-label="关闭工作事项详情"/>
      <aside className="relative h-full w-full max-w-2xl overflow-y-auto border-l border-border-default bg-bg-elevated shadow-2xl">
        <header className="sticky top-0 z-10 flex items-center border-b border-border-default bg-bg-elevated/95 px-6 py-4 backdrop-blur">
          <div>
            <div className="font-mono text-[10px] tracking-wide text-accent-secondary">{task.project_name} · {task.task_id}</div>
            <h2 className="mt-1 font-heading text-lg font-semibold">工作事项分析</h2>
          </div>
          <button className="ml-auto rounded-lg p-2 text-text-muted hover:bg-bg-surface hover:text-text-primary" onClick={onClose} aria-label="关闭"><X size={18}/></button>
        </header>

        <div className="space-y-4 p-6">
          <Module icon={BookOpen} index="01" title="背景信息">
            <p className="font-medium text-text-primary">{task.name}</p>
            <p className="mt-2">{task.rationale || task.evidence || '该事项由项目文件变化识别产生，当前历史数据未保存更完整的背景说明。'}</p>
            {task.personal_reason && <div className="mt-3 rounded-lg border border-accent-secondary/15 bg-accent-secondary/5 p-3"><div className="flex items-center gap-2 text-xs font-medium text-accent-secondary"><Link2 size={13}/>与你的关系</div><p className="mt-1 text-xs leading-5">{task.personal_reason}</p></div>}
            {task.related_files.length > 0
              ? <div className="mt-3 space-y-1.5">{task.related_files.map(file => <div key={file} className="flex items-start gap-2 rounded-lg bg-bg-surface px-3 py-2 font-mono text-[11px] leading-5 text-text-muted"><FileText size={12} className="mt-1 shrink-0"/><span className="break-all">{file}</span></div>)}</div>
              : <p className="mt-3 text-xs text-accent-warning">当前缺少明确来源文件，执行前需要补充事实证据。</p>}
          </Module>

          <Module icon={Lightbulb} index="02" title="建议">
            <p>{suggestionFor(task)}</p>
            {task.signal_to?.length > 0 && <p className="mt-2 text-xs text-text-muted">建议协同核对：{task.signal_to.join('、')}</p>}
          </Module>

          <Module icon={Footprints} index="03" title="执行参考">
            <ol className="space-y-3">
              {steps.map((step, index) => (
                <li key={step} className="flex items-start gap-3">
                  <span className="mt-1 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-bg-surface font-mono text-[10px] text-accent-secondary">{index + 1}</span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
            <div className="mt-4 flex items-start gap-2 rounded-lg border border-border-default p-3 text-xs leading-5 text-text-muted"><Compass size={14} className="mt-0.5 shrink-0"/>这是决策参考，不会从页面自动执行命令、修改文件或发送通知。</div>
          </Module>

          <Module icon={ClipboardCheck} index="04" title="理想化交付">
            <div className="flex items-start gap-3"><CheckCircle2 size={17} className="mt-1 shrink-0 text-accent-success"/><p className="text-text-primary">{idealDeliverableFor(task)}</p></div>
          </Module>
        </div>
      </aside>
    </div>
  )
}
