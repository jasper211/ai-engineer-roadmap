import { useEffect, useMemo, useState } from 'react'
import {
  Activity, ArrowDownToLine, ArrowRight, ArrowUpRight, ChevronDown, Clock3,
  FileDiff, FileMinus2, FilePlus2, FolderKanban, GitCompareArrows, Link2, Sparkles,
} from 'lucide-react'
import {
  fetchCommandCenter, type ChangeItem, type CommandCenterResponse,
  type CommandProject, type CrossProjectRelation, type Task,
} from '../lib/api'
import { PriorityBadge } from '../components/StatusBadge'

const CHANGE_META = {
  added: { label: '新增', icon: FilePlus2, cls: 'text-accent-success bg-accent-success/10 border-accent-success/20' },
  changed: { label: '修改', icon: FileDiff, cls: 'text-accent-info bg-accent-info/10 border-accent-info/20' },
  removed: { label: '删除', icon: FileMinus2, cls: 'text-accent-danger bg-accent-danger/10 border-accent-danger/20' },
}

function formatTime(value: string) {
  if (!value) return '尚未成功巡检'
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function ChangeRow({ change, initiallyOpen = false }: { change: ChangeItem; initiallyOpen?: boolean }) {
  const [open, setOpen] = useState(initiallyOpen)
  const meta = CHANGE_META[change.change_type] || CHANGE_META.changed
  const Icon = meta.icon
  const hasDetail = !!(change.diff_text || change.before_excerpt || change.after_excerpt)
  return (
    <div className="border-b border-border-default/70 last:border-0">
      <button onClick={() => hasDetail && setOpen(v => !v)} className="group flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-bg-surface/50">
        <span className={`mt-0.5 flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] font-medium ${meta.cls}`}><Icon size={11}/>{meta.label}</span>
        <div className="min-w-0 flex-1">
          <div className="break-all font-mono text-[11px] text-text-primary">{change.file}</div>
          <div className="mt-1 text-xs leading-5 text-text-secondary">{change.summary || '已记录文件事实变化'}</div>
          <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-text-muted"><span>{change.domain || '其他'}</span><span>·</span><span>{change.who || '未知来源'}</span>{!hasDetail && <><span>·</span><span>旧报告未保存内容级 diff</span></>}</div>
        </div>
        {hasDetail && <ChevronDown size={15} className={`mt-1 shrink-0 text-text-muted transition ${open ? 'rotate-180' : ''}`}/>}
      </button>
      {open && hasDetail && (
        <div className="mx-4 mb-4 overflow-hidden rounded-xl border border-border-default bg-bg-base">
          {change.change_type === 'changed' && (change.before_excerpt || change.after_excerpt) && (
            <div className="grid md:grid-cols-2">
              <div className="border-b border-border-default p-3 md:border-b-0 md:border-r"><div className="mb-2 text-[10px] font-semibold text-accent-danger">修改前</div><pre className="max-h-44 overflow-auto whitespace-pre-wrap text-[10px] leading-5 text-text-muted">{change.before_excerpt || '无可读内容'}</pre></div>
              <div className="p-3"><div className="mb-2 text-[10px] font-semibold text-accent-success">修改后</div><pre className="max-h-44 overflow-auto whitespace-pre-wrap text-[10px] leading-5 text-text-secondary">{change.after_excerpt || '无可读内容'}</pre></div>
            </div>
          )}
          {change.change_type !== 'changed' && <div className="p-3"><div className="mb-2 text-[10px] font-semibold text-text-secondary">{change.change_type === 'added' ? '新增内容' : '删除前最后内容'}</div><pre className="max-h-52 overflow-auto whitespace-pre-wrap text-[10px] leading-5 text-text-muted">{change.after_excerpt || change.before_excerpt || change.diff_text}</pre></div>}
          {change.diff_text && change.change_type === 'changed' && <details className="border-t border-border-default"><summary className="cursor-pointer px-3 py-2 text-[10px] text-text-muted">查看原始 diff</summary><pre className="max-h-56 overflow-auto whitespace-pre-wrap px-3 pb-3 text-[10px] leading-5 text-text-secondary">{change.diff_text}</pre></details>}
        </div>
      )}
    </div>
  )
}

function TaskSignal({ task }: { task: Task }) {
  const advice = task.needs_mark_alignment
    ? '建议：先形成内部方案，再线下找 Mark 裁定'
    : task.signal_to?.length ? `建议：由 ${task.signal_to.join('、')} 核对并决定是否推进` : '建议：结合文件事实人工核对'
  return <div className="rounded-lg border border-border-default bg-bg-base/60 p-3"><div className="flex items-center gap-2"><PriorityBadge priority={task.priority}/><span className="font-mono text-[10px] text-text-muted">{task.task_id}</span></div><div className="mt-2 text-xs font-medium leading-5">{task.name}</div><div className="mt-2 text-[10px] leading-4 text-accent-secondary">{advice}</div></div>
}

function ProjectPanel({ project, primary = false }: { project: CommandProject; primary?: boolean }) {
  const [showAll, setShowAll] = useState(primary)
  const counts = { added: project.files_added, changed: project.files_changed, removed: project.files_removed }
  const visible = showAll ? project.changes : project.changes.slice(0, 4)
  return (
    <section className={`overflow-hidden rounded-2xl border bg-bg-elevated ${primary ? 'border-accent-primary/35 shadow-[0_18px_60px_rgba(0,0,0,.2)]' : 'border-border-default'}`}>
      <header className={`border-b border-border-default px-5 py-4 ${primary ? 'bg-gradient-to-r from-accent-primary/10 to-transparent' : ''}`}>
        <div className="flex items-start gap-3"><div className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${primary ? 'bg-accent-primary text-white' : 'bg-bg-surface text-text-secondary'}`}><FolderKanban size={18}/></div><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h2 className="font-heading text-base font-semibold">{project.project_name}</h2><span className="rounded bg-bg-surface px-2 py-0.5 text-[10px] text-text-muted">{project.label}</span></div><p className="mt-1 text-[11px] leading-5 text-text-muted">{project.question}</p></div></div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="change-counter text-accent-success"><ArrowDownToLine size={12}/>新增 {counts.added}</span>
          <span className="change-counter text-accent-info"><FileDiff size={12}/>修改 {counts.changed}</span>
          <span className="change-counter text-accent-danger"><FileMinus2 size={12}/>删除 {counts.removed}</span>
          <span className="ml-auto flex items-center gap-1 text-[10px] text-text-muted"><Clock3 size={11}/>{formatTime(project.generated_at)}</span>
        </div>
      </header>
      {project.total_changes === 0 ? <div className="px-5 py-10 text-center"><Activity className="mx-auto text-accent-success" size={20}/><p className="mt-2 text-xs text-text-secondary">本周期无文件变化</p><p className="mt-1 text-[10px] text-text-muted">巡检成功，不是数据缺失</p></div> : (
        <>
          <div>{visible.map((c, i) => <ChangeRow key={`${c.file}-${i}`} change={c} initiallyOpen={primary && i < 2}/>)}</div>
          {!showAll && project.changes.length > visible.length && <button onClick={() => setShowAll(true)} className="w-full border-t border-border-default px-4 py-3 text-xs text-accent-primary-light hover:bg-bg-surface">查看全部 {project.changes.length} 个文件变化</button>}
        </>
      )}
      {project.relationships.length > 0 && <div className="border-t border-border-default bg-bg-base/40 px-4 py-3"><div className="mb-2 flex items-center gap-1 text-[10px] font-semibold text-text-secondary"><Link2 size={11}/>项目内变化关系</div>{project.relationships.slice(0, primary ? 4 : 2).map((r, i) => <p key={i} className="mb-1 text-[10px] leading-5 text-text-muted">{r.description}</p>)}</div>}
      {project.related_tasks.length > 0 && <div className="border-t border-border-default px-4 py-4"><div className="mb-3 flex items-center gap-1 text-[10px] font-semibold text-text-secondary"><Sparkles size={11}/>从文件变化识别出的相关任务</div><div className="space-y-2">{project.related_tasks.slice(0, primary ? 5 : 2).map(t => <TaskSignal key={t.task_id} task={t}/>)}</div></div>}
    </section>
  )
}

function RelationCard({ relation }: { relation: CrossProjectRelation }) {
  return <div className="rounded-xl border border-border-default bg-bg-elevated p-4"><div className="flex items-center gap-2 text-xs font-medium"><span>{relation.from_project}</span><ArrowRight size={13} className="text-accent-secondary"/><span>{relation.to_project}</span></div><p className="mt-2 text-xs leading-5 text-text-secondary">{relation.analysis}</p><div className="mt-3 flex flex-wrap gap-1">{relation.shared_domains.map(d => <span key={d} className="rounded bg-bg-surface px-2 py-1 text-[10px] text-text-muted">{d}</span>)}</div><p className="mt-3 text-[10px] text-accent-warning">关系线索，需结合文件内容核对，不视为已确认因果</p></div>
}

export function TaskBoard() {
  const [data, setData] = useState<CommandCenterResponse | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { fetchCommandCenter().then(setData).catch(e => setError(String(e))) }, [])
  const core = useMemo(() => data?.projects.find(p => p.role === 'core'), [data])
  const secondary = useMemo(() => data?.projects.filter(p => p.role !== 'core') || [], [data])
  const total = data?.projects.reduce((sum, p) => sum + p.total_changes, 0) || 0
  if (error) return <div className="p-8 text-accent-danger">指挥中心加载失败：{error}</div>
  if (!data) return <div className="p-8 text-text-muted">正在汇总三个项目的最新文件事实…</div>
  return (
    <main className="mx-auto max-w-[1440px] space-y-7 px-5 py-7 lg:px-8">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-end"><div><div className="eyebrow"><GitCompareArrows size={12}/>PERSONAL PROJECT INTELLIGENCE</div><h1 className="mt-2 font-heading text-2xl font-semibold tracking-tight lg:text-3xl">三项目指挥中心</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">文件事实是唯一源头：先看三个项目发生了什么，再判断与你相关的任务和跨项目影响。</p></div><div className="ml-auto rounded-xl border border-border-default bg-bg-elevated px-4 py-3"><div className="text-2xl font-semibold">{total}</div><div className="text-[10px] text-text-muted">本周期文件变化</div></div></header>
      <div className="rounded-xl border border-accent-secondary/15 bg-accent-secondary/5 px-4 py-3 text-xs text-text-secondary"><b className="text-accent-secondary">SSOT 时间口径：</b>{data.period_basis}</div>
      <section className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.65fr)_minmax(360px,.85fr)]">{core ? <ProjectPanel project={core} primary/> : <div className="rounded-2xl border border-accent-danger/20 p-8 text-sm text-accent-danger">EA 核心项目尚无成功巡检报告</div>}<div className="space-y-6">{secondary.map(p => <ProjectPanel key={p.project_name} project={p}/>)}</div></section>
      <section><div className="mb-3 flex items-center gap-2"><GitCompareArrows size={16} className="text-accent-secondary"/><h2 className="font-heading text-base font-semibold">跨项目关系线索</h2><span className="text-[10px] text-text-muted">EA ↔ Jasper ↔ Rw</span></div>{data.cross_project_relations.length ? <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{data.cross_project_relations.map((r, i) => <RelationCard key={`${r.from_project}-${r.to_project}-${i}`} relation={r}/>)}</div> : <div className="rounded-xl border border-border-default bg-bg-elevated px-5 py-8 text-center text-xs text-text-muted">本轮三个项目暂未出现共同业务域的变化线索</div>}</section>
    </main>
  )
}
