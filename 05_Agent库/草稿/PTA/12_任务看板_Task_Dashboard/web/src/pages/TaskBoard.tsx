import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ArrowUpRight, CheckCircle2, Clock3, Filter, Inbox, ShieldAlert, Sparkles, UserRound } from 'lucide-react'
import { fetchProjects, fetchTasks, type ProjectInfo, type Task, type TaskBuckets } from '../lib/api'
import { PriorityBadge } from '../components/StatusBadge'
import { TaskDecisionDrawer } from '../components/TaskDecisionDrawer'

function Metric({ label, value, tone, icon: Icon }: { label: string; value: number; tone: string; icon: typeof Inbox }) {
  return <div className="metric-card"><div className={`metric-icon ${tone}`}><Icon size={17}/></div><div><div className="text-2xl font-semibold tracking-tight">{value}</div><div className="text-xs text-text-muted">{label}</div></div></div>
}

function TaskRow({ task, onOpen }: { task: Task; onOpen: (task: Task) => void }) {
  const state = task.decision_status || 'pending_review'
  return (
    <button onClick={() => onOpen(task)} className="group grid w-full grid-cols-[auto_1fr_auto] items-start gap-3 border-b border-border-default/70 px-4 py-4 text-left last:border-0 hover:bg-bg-surface/60">
      <div className={`mt-1 h-2 w-2 rounded-full ${task.priority === 'P0' ? 'bg-accent-danger shadow-[0_0_12px_#f87171]' : task.priority === 'P1' ? 'bg-accent-warning' : 'bg-accent-info'}`} />
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2"><PriorityBadge priority={task.priority}/><span className="font-mono text-[11px] text-text-muted">{task.task_id}</span><span className="project-chip">{task.project_name}</span></div>
        <div className="mt-2 text-sm font-medium leading-6 text-text-primary group-hover:text-white">{task.name}</div>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-muted">
          {task.owner ? <span className="flex items-center gap-1"><UserRound size={12}/>{task.owner}</span> : <span className="text-accent-warning">未指定负责人</span>}
          {task.days_pending !== undefined && task.days_pending > 0 && <span className="flex items-center gap-1"><Clock3 size={12}/>搁置 {task.days_pending} 天</span>}
          {task.needs_mark_alignment && <span className="flex items-center gap-1 text-accent-danger"><AlertTriangle size={12}/>需 Mark 裁定</span>}
          {state === 'accepted' && <span className="text-accent-success">已接受 · 待执行</span>}
          {state === 'transferred' && <span className="text-accent-info">已转交</span>}
          {task.execution?.state === 'approved' && <span className="text-accent-warning">计划已批准</span>}
        </div>
      </div>
      <ArrowUpRight size={16} className="mt-1 text-text-muted transition group-hover:text-accent-primary-light" />
    </button>
  )
}

export function TaskBoard() {
  const [projects, setProjects] = useState<ProjectInfo[]>([])
  const [projectFilter, setProjectFilter] = useState('all')
  const [buckets, setBuckets] = useState<TaskBuckets | null>(null)
  const [selected, setSelected] = useState<Task | null>(null)
  const [view, setView] = useState<'decision' | 'accepted' | 'aging'>('decision')
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setError(null)
      const [projs, tasks] = await Promise.all([fetchProjects(), fetchTasks(projectFilter)])
      setProjects(projs); setBuckets(tasks)
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }, [projectFilter])
  useEffect(() => { load() }, [load])

  const allOpen = useMemo(() => buckets ? [...buckets.new, ...buckets.aging] : [], [buckets])
  const decision = allOpen.filter(t => !t.decision_status || t.decision_status === 'pending_review')
  const accepted = allOpen.filter(t => t.decision_status === 'accepted' || t.decision_status === 'transferred')
  const aging = allOpen.filter(t => (t.days_pending || 0) > 0)
  const visible = view === 'decision' ? decision : view === 'accepted' ? accepted : aging
  const urgent = allOpen.filter(t => t.priority === 'P0').length
  const mark = allOpen.filter(t => t.needs_mark_alignment).length

  if (error) return <div className="p-8 text-accent-danger">驾驶舱加载失败：{error}</div>
  if (!buckets) return <div className="p-8 text-text-muted">正在汇总今日任务态势…</div>

  return (
    <main className="mx-auto max-w-[1280px] space-y-6 px-5 py-7 lg:px-8">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-end">
        <div>
          <div className="eyebrow"><Sparkles size={12}/>PTA COMMAND CENTER</div>
          <h1 className="mt-2 font-heading text-2xl font-semibold tracking-tight lg:text-3xl">今天需要你做的决策</h1>
          <p className="mt-2 text-sm text-text-secondary">先处理高风险与待裁定事项，再把接受的任务送入执行准备区。</p>
        </div>
        <label className="ml-auto flex items-center gap-2 rounded-lg border border-border-default bg-bg-elevated px-3 py-2 text-xs text-text-secondary"><Filter size={14}/><select value={projectFilter} onChange={e => setProjectFilter(e.target.value)} className="bg-transparent text-text-primary outline-none"><option value="all">全部项目</option>{projects.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}</select></label>
      </header>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label="待我决策" value={decision.length} tone="bg-accent-primary/15 text-accent-primary-light" icon={Inbox}/>
        <Metric label="P0 紧急事项" value={urgent} tone="bg-accent-danger/15 text-accent-danger" icon={ShieldAlert}/>
        <Metric label="需 Mark 裁定" value={mark} tone="bg-accent-warning/15 text-accent-warning" icon={AlertTriangle}/>
        <Metric label="已接受 / 转交" value={accepted.length} tone="bg-accent-success/15 text-accent-success" icon={CheckCircle2}/>
      </section>

      <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="overflow-hidden rounded-2xl border border-border-default bg-bg-elevated">
          <div className="flex flex-wrap items-center gap-1 border-b border-border-default px-3 pt-3">
            {([['decision','待决策',decision.length],['accepted','执行准备',accepted.length],['aging','搁置事项',aging.length]] as const).map(([key,label,count]) => <button key={key} onClick={() => setView(key)} className={`tab-button ${view === key ? 'tab-button-active' : ''}`}>{label}<span>{count}</span></button>)}
          </div>
          {visible.length ? visible.map(t => <TaskRow key={`${t.project_name}-${t.task_id}`} task={t} onOpen={setSelected}/>) : <div className="px-6 py-16 text-center"><CheckCircle2 className="mx-auto text-accent-success"/><p className="mt-3 text-sm text-text-secondary">这个队列已经清空</p></div>}
        </div>

        <aside className="space-y-4">
          <div className="rounded-2xl border border-accent-warning/20 bg-gradient-to-br from-accent-warning/10 to-transparent p-5">
            <div className="flex items-center gap-2 text-sm font-medium"><ShieldAlert size={16} className="text-accent-warning"/>决策原则</div>
            <ol className="mt-4 space-y-3 text-xs leading-5 text-text-secondary"><li><b className="text-text-primary">1. 先去重：</b>确认是不是旧事项的新证据。</li><li><b className="text-text-primary">2. 再定责：</b>没有 Owner 的任务不会自然推进。</li><li><b className="text-text-primary">3. 后验收：</b>接受前写清文件、字段、测试或人工回执。</li></ol>
          </div>
          <div className="rounded-2xl border border-border-default bg-bg-elevated p-5">
            <div className="text-sm font-medium">当前能力边界</div><p className="mt-2 text-xs leading-5 text-text-muted">驾驶舱本阶段只保存人工决策。接受任务不会自动运行命令、推送代码或通知外部人员。</p>
          </div>
        </aside>
      </section>
      <TaskDecisionDrawer task={selected} onClose={() => setSelected(null)} onSaved={load}/>
    </main>
  )
}
