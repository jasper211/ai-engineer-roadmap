import { useState } from 'react'
import { AlertTriangle, FileText, Loader2 } from 'lucide-react'
import type { Task } from '../lib/api'
import { PriorityBadge } from './StatusBadge'

interface Props {
  task: Task
  // undefined = 只读展示(比如"最近完成"区块，不需要勾选)；有值时渲染勾选框
  onToggle?: (task: Task, dismissed: boolean) => Promise<void>
  checked?: boolean
}

export function TaskCard({ task, onToggle, checked }: Props) {
  const [pending, setPending] = useState(false)

  const handleToggle = async () => {
    if (!onToggle || pending) return
    setPending(true)
    try {
      await onToggle(task, !checked)
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="rounded-radius-md border border-border-default bg-bg-elevated p-4 flex gap-3">
      {onToggle && (
        <button
          onClick={handleToggle}
          disabled={pending}
          aria-label={checked ? '重新开始跟踪这条任务' : '关闭这条任务（不需要执行）'}
          className="mt-0.5 h-5 w-5 shrink-0 rounded border border-border-hover flex items-center justify-center
                     hover:border-accent-primary disabled:opacity-50"
        >
          {pending ? <Loader2 size={12} className="animate-spin text-text-muted" /> : (checked ? '✓' : '')}
        </button>
      )}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-xs text-text-muted">{task.task_id}</span>
          <PriorityBadge priority={task.priority} />
          <span className="text-xs text-text-secondary rounded bg-bg-surface px-2 py-0.5">{task.project_name}</span>
          {task.days_pending !== undefined && task.days_pending > 0 && (
            <span className="text-xs text-accent-warning">已搁置 {task.days_pending} 天</span>
          )}
        </div>
        <div className="mt-1 text-sm text-text-primary font-medium">{task.name}</div>
        {task.signal_to.length > 0 && (
          <div className="mt-1 text-xs text-text-secondary">通知: {task.signal_to.join('、')}</div>
        )}
        {task.needs_mark_alignment && (
          <div className="mt-1 flex items-center gap-1 text-xs text-accent-danger">
            <AlertTriangle size={12} /> 需内部对齐后线下找 Mark
          </div>
        )}
        {task.related_files.length > 0 && (
          <div className="mt-1 flex items-center gap-1 text-xs text-text-muted">
            <FileText size={12} /> {task.related_files.join('、')}
          </div>
        )}
      </div>
    </div>
  )
}
