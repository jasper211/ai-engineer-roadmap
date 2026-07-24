import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ArrowUpRight, FileText, Sparkles } from 'lucide-react'
import { fetchTasks, type Task, type TaskBuckets } from '../lib/api'
import { PriorityBadge } from '../components/StatusBadge'
import { TaskDecisionDrawer } from '../components/TaskDecisionDrawer'

function TaskAdvice({ task, onOpen }: { task: Task; onOpen: () => void }) {
  const advice = task.needs_mark_alignment
    ? '先内部对齐事实和备选方案，再线下找 Mark 裁定。'
    : task.signal_to?.length
      ? `建议由 ${task.signal_to.join('、')} 核对来源文件，确认是否进入执行。`
      : '建议先核对来源文件和影响范围，再决定是否处理。'
  return <button onClick={onOpen} className="group w-full rounded-xl border border-border-default bg-bg-elevated p-4 text-left hover:border-border-hover">
    <div className="flex items-start gap-3"><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><PriorityBadge priority={task.priority}/><span className="font-mono text-[10px] text-text-muted">{task.task_id}</span><span className="project-chip">{task.project_name}</span></div><h3 className="mt-2 text-sm font-medium leading-6">{task.name}</h3></div><ArrowUpRight size={15} className="text-text-muted group-hover:text-accent-primary-light"/></div>
    <p className="mt-3 text-xs leading-5 text-accent-secondary">{advice}</p>
    {task.related_files.length > 0 ? <div className="mt-3 flex items-start gap-2 text-[10px] text-text-muted"><FileText size={12}/><span>{task.related_files.join('、')}</span></div> : <div className="mt-3 flex items-center gap-2 text-[10px] text-accent-warning"><AlertTriangle size={12}/>当前缺少明确关联文件，执行前需补充证据</div>}
  </button>
}

export function ActivityFeed() {
  const [buckets, setBuckets] = useState<TaskBuckets | null>(null)
  const [selected, setSelected] = useState<Task | null>(null)
  const load = useCallback(async () => setBuckets(await fetchTasks('all')), [])
  useEffect(() => { load() }, [load])
  const tasks = useMemo(() => buckets ? [...buckets.new, ...buckets.aging] : [], [buckets])
  const groups = useMemo(() => ({
    EA: tasks.filter(t => t.project_name.includes('EA')),
    Jasper: tasks.filter(t => t.project_name.includes('Jasper')),
    Rw: tasks.filter(t => t.project_name.includes('Rw')),
  }), [tasks])
  if (!buckets) return <div className="p-8 text-text-muted">正在读取从文件变化中识别出的任务…</div>
  return <main className="mx-auto max-w-6xl space-y-7 px-5 py-7 lg:px-8">
    <header><div className="eyebrow"><Sparkles size={12}/>DOWNSTREAM FROM FILE FACTS</div><h1 className="mt-2 font-heading text-2xl font-semibold">与我相关的任务建议</h1><p className="mt-2 text-sm text-text-secondary">这里只展示从三个项目文件变化中推导出的下游建议；事实原文仍以指挥中心为准。</p></header>
    {Object.entries(groups).map(([name, items]) => <section key={name}><div className="mb-3 flex items-center gap-2"><h2 className="text-sm font-medium">{name}</h2><span className="rounded-full bg-bg-surface px-2 py-1 font-mono text-[10px] text-text-muted">{items.length}</span></div>{items.length ? <div className="grid gap-3 md:grid-cols-2">{items.map(t => <TaskAdvice key={t.task_id} task={t} onOpen={() => setSelected(t)}/>)}</div> : <div className="rounded-xl border border-border-default bg-bg-elevated px-5 py-8 text-xs text-text-muted">当前没有从该项目变化中识别出与你相关的开放任务</div>}</section>)}
    <TaskDecisionDrawer task={selected} onClose={() => setSelected(null)} onSaved={load}/>
  </main>
}
