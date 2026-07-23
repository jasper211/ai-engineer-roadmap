import { useState } from 'react'
import { Check, CircleDashed, Play, ShieldCheck, TerminalSquare, TriangleAlert } from 'lucide-react'
import { approveTaskExecution, dryRunTaskExecution, prepareTaskExecution, type Task, type TaskExecution } from '../lib/api'

const STATE_LABEL: Record<string, string> = {
  plan_ready: '计划待演练', dry_run_passed: '演练通过', dry_run_failed: '演练失败', approved: '已批准待执行',
}

export function ExecutionPlanPanel({ task, onChanged }: { task: Task; onChanged: () => Promise<void> }) {
  const [execution, setExecution] = useState<TaskExecution | null>(task.execution || null)
  const [note, setNote] = useState(task.execution?.approval_note || '')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  async function act(kind: 'prepare' | 'dry-run' | 'approve') {
    setBusy(kind); setError('')
    try {
      const result = kind === 'prepare'
        ? await prepareTaskExecution(task.project_name, task.task_id)
        : kind === 'dry-run'
          ? await dryRunTaskExecution(task.project_name, task.task_id)
          : await approveTaskExecution(task.project_name, task.task_id, note)
      setExecution(result.execution)
      await onChanged()
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    finally { setBusy('') }
  }

  if (!execution) return (
    <section className="rounded-xl border border-accent-primary/20 bg-accent-primary/5 p-4">
      <div className="flex items-center gap-2 text-sm font-medium"><TerminalSquare size={16} className="text-accent-primary-light"/>执行准备</div>
      <p className="mt-2 text-xs leading-5 text-text-secondary">调用 PTA 现有执行编排器生成步骤清单，并进行确定性风险标注。此操作不会运行任何步骤。</p>
      <button disabled={!!busy} onClick={() => act('prepare')} className="action-primary mt-4 w-full"><CircleDashed size={15}/>{busy ? '正在生成…' : '生成执行计划'}</button>
      {error && <p className="mt-2 text-xs text-accent-danger">{error}</p>}
    </section>
  )

  return (
    <section className="rounded-xl border border-border-default bg-bg-base/50 p-4">
      <div className="flex items-center gap-2">
        <TerminalSquare size={16} className="text-accent-primary-light"/><span className="text-sm font-medium">执行计划</span>
        <span className={`ml-auto rounded-full px-2 py-1 text-[10px] ${execution.state === 'approved' ? 'bg-accent-success/15 text-accent-success' : 'bg-bg-surface text-text-secondary'}`}>{STATE_LABEL[execution.state]}</span>
      </div>
      <div className="mt-4 space-y-2">
        {execution.plan.steps.map((step, i) => {
          const dry = execution.dry_run?.steps?.[i]
          return <div key={step.seq} className="rounded-lg border border-border-default bg-bg-elevated p-3">
            <div className="flex items-start gap-3"><div className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-bg-surface font-mono text-[10px]">{step.seq}</div><div className="min-w-0 flex-1"><div className="text-xs font-medium">{step.description || step.action}</div><div className="mt-1 flex flex-wrap gap-2 text-[10px] text-text-muted"><span className="font-mono">{step.tool}</span><span className={step.risk.level === 'low' ? 'text-accent-success' : 'text-accent-warning'}>{step.risk.label}</span>{dry && <span className={dry.status === 'completed' ? 'text-accent-success' : 'text-accent-danger'}>{dry.status === 'completed' ? '演练通过' : '演练失败'}</span>}</div>{step.command && <code className="mt-2 block overflow-x-auto rounded bg-bg-base px-2 py-1.5 text-[10px] text-text-secondary">{step.command}</code>}</div></div>
          </div>
        })}
      </div>

      {execution.state === 'plan_ready' || execution.state === 'dry_run_failed' ? <button disabled={!!busy} onClick={() => act('dry-run')} className="action-primary mt-4 w-full"><Play size={15}/>{busy ? '正在演练…' : execution.state === 'dry_run_failed' ? '重新 dry-run' : '运行 dry-run'}</button> : null}

      {execution.state === 'dry_run_passed' && <div className="mt-4 rounded-lg border border-accent-success/20 bg-accent-success/5 p-3"><div className="flex items-center gap-2 text-xs text-accent-success"><ShieldCheck size={15}/>全部 {execution.dry_run?.total} 个步骤演练通过</div><textarea value={note} onChange={e => setNote(e.target.value)} placeholder="批准说明或真实执行前必须核对的条件" rows={2} className="field mt-3 resize-none"/><button disabled={!!busy} onClick={() => act('approve')} className="action-primary mt-2 w-full"><Check size={15}/>{busy ? '正在保存…' : '批准计划，进入待执行'}</button></div>}

      {execution.state === 'approved' && <div className="mt-4 rounded-lg border border-accent-warning/25 bg-accent-warning/5 p-3"><div className="flex items-center gap-2 text-xs font-medium text-accent-warning"><TriangleAlert size={15}/>已批准，但尚未真实执行</div><p className="mt-2 text-xs leading-5 text-text-secondary">真实执行仍需再次明确授权；高风险步骤会再次确认，不会由本页面自动触发。</p>{execution.approval_note && <p className="mt-2 text-xs text-text-muted">批准备注：{execution.approval_note}</p>}</div>}
      {error && <p className="mt-3 text-xs text-accent-danger">{error}</p>}
    </section>
  )
}
