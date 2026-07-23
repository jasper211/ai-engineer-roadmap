import { useEffect, useState } from 'react'
import { ArrowRight, Check, Merge, Send, X } from 'lucide-react'
import { decideTask, type Task, type TaskDecisionInput } from '../lib/api'
import { PriorityBadge } from './StatusBadge'
import { ExecutionPlanPanel } from './ExecutionPlanPanel'

interface Props {
  task: Task | null
  onClose: () => void
  onSaved: () => Promise<void>
}

export function TaskDecisionDrawer({ task, onClose, onSaved }: Props) {
  const [title, setTitle] = useState('')
  const [priority, setPriority] = useState('P2')
  const [owner, setOwner] = useState('')
  const [dueDate, setDueDate] = useState('')
  const [criteria, setCriteria] = useState('')
  const [note, setNote] = useState('')
  const [mergedInto, setMergedInto] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!task) return
    setTitle(task.name)
    setPriority(task.priority || 'P2')
    setOwner(task.owner || '')
    setDueDate(task.due_date || '')
    setCriteria(task.acceptance_criteria || '')
    setNote(task.decision_note || '')
    setMergedInto(task.merged_into || '')
    setError('')
  }, [task])

  if (!task) return null
  const currentTask = task

  async function submit(decision_status: TaskDecisionInput['decision_status']) {
    if (decision_status === 'accepted' && (!owner.trim() || !criteria.trim())) {
      setError('接受任务前，请补齐负责人和验收标准。')
      return
    }
    if (decision_status === 'merged' && !mergedInto.trim()) {
      setError('合并任务前，请填写目标任务 ID。')
      return
    }
    setSaving(true)
    setError('')
    try {
      await decideTask(currentTask.project_name, currentTask.task_id, {
        decision_status, title: title.trim(), priority, owner: owner.trim(), due_date: dueDate,
        acceptance_criteria: criteria.trim(), decision_note: note.trim(), merged_into: mergedInto.trim(),
      })
      await onSaved()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="任务决策">
      <button className="absolute inset-0 bg-black/55 backdrop-blur-sm" onClick={onClose} aria-label="关闭任务详情" />
      <aside className="relative h-full w-full max-w-2xl overflow-y-auto border-l border-border-default bg-bg-elevated shadow-2xl">
        <header className="sticky top-0 z-10 flex items-center border-b border-border-default bg-bg-elevated/95 px-6 py-4 backdrop-blur">
          <div>
            <div className="font-mono text-xs text-accent-secondary">{task.task_id} · {task.project_name}</div>
            <h2 className="mt-1 font-heading text-lg font-semibold">候选任务决策</h2>
          </div>
          <button className="ml-auto rounded-lg p-2 text-text-muted hover:bg-bg-surface hover:text-text-primary" onClick={onClose}><X size={18} /></button>
        </header>

        <div className="space-y-6 p-6">
          <section className="rounded-xl border border-border-default bg-bg-base/50 p-4">
            <div className="flex items-center gap-2"><PriorityBadge priority={task.priority} /><span className="text-xs text-text-muted">PTA 建议</span></div>
            <p className="mt-3 text-base font-medium leading-7">{task.name}</p>
            <p className="mt-2 text-sm leading-6 text-text-secondary">{task.rationale || '历史任务尚未保存模型生成理由，请结合项目来源和相关文件人工判断。'}</p>
            {task.relevance_reason && <p className="mt-2 text-xs text-text-muted">关联依据：{task.relevance_reason}</p>}
            {task.related_files.length > 0 ? (
              <div className="mt-3 space-y-1">{task.related_files.map(f => <div key={f} className="rounded bg-bg-surface px-3 py-2 font-mono text-xs text-text-secondary">{f}</div>)}</div>
            ) : <p className="mt-3 rounded-lg border border-accent-warning/20 bg-accent-warning/5 px-3 py-2 text-xs text-accent-warning">当前没有关联文件，接受前建议在验收标准中补充明确证据。</p>}
          </section>

          <section className="grid gap-4 sm:grid-cols-2">
            <label className="sm:col-span-2 text-xs text-text-secondary">任务标题<input value={title} onChange={e => setTitle(e.target.value)} className="field mt-1" /></label>
            <label className="text-xs text-text-secondary">优先级<select value={priority} onChange={e => setPriority(e.target.value)} className="field mt-1"><option>P0</option><option>P1</option><option>P2</option><option>P3</option></select></label>
            <label className="text-xs text-text-secondary">负责人 *<input value={owner} onChange={e => setOwner(e.target.value)} placeholder="例如 Jasper" className="field mt-1" /></label>
            <label className="text-xs text-text-secondary">截止日期<input type="date" value={dueDate} onChange={e => setDueDate(e.target.value)} className="field mt-1" /></label>
            <label className="text-xs text-text-secondary">合并到任务<input value={mergedInto} onChange={e => setMergedInto(e.target.value)} placeholder="RPT-YYYYMMDD-NN" className="field mt-1" /></label>
            <label className="sm:col-span-2 text-xs text-text-secondary">验收标准 *<textarea value={criteria} onChange={e => setCriteria(e.target.value)} rows={3} placeholder="完成后用什么文件、字段、测试或人工确认作为证据？" className="field mt-1 resize-none" /></label>
            <label className="sm:col-span-2 text-xs text-text-secondary">决策备注<textarea value={note} onChange={e => setNote(e.target.value)} rows={2} placeholder="记录转交原因、限制条件或待确认事项" className="field mt-1 resize-none" /></label>
          </section>

          {task.decision_status === 'accepted' && <ExecutionPlanPanel task={task} onChanged={onSaved} />}

          {error && <p className="rounded-lg bg-accent-danger/10 px-3 py-2 text-sm text-accent-danger">{error}</p>}

          <section className="grid gap-2 sm:grid-cols-2">
            <button disabled={saving} onClick={() => submit('accepted')} className="action-primary"><Check size={15}/>接受并进入待执行<ArrowRight size={15}/></button>
            <button disabled={saving} onClick={() => submit('transferred')} className="action-secondary"><Send size={15}/>转交责任方</button>
            <button disabled={saving} onClick={() => submit('merged')} className="action-secondary"><Merge size={15}/>合并到已有任务</button>
            <button disabled={saving} onClick={() => submit('dismissed')} className="action-danger"><X size={15}/>忽略并关闭</button>
          </section>
          <p className="text-xs leading-5 text-text-muted">本页面只保存人工决策，不会执行 Shell、推送 Git 或发送外部通知。执行授权将在第二阶段单独接入。</p>
        </div>
      </aside>
    </div>
  )
}
