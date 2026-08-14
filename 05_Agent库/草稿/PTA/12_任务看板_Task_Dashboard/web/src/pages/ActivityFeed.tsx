import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle, ArrowRight, ArrowUpRight, Bot, CircleDot,
  FileText, FlaskConical, Route, ShieldCheck, Sparkles,
} from 'lucide-react'
import { fetchFileContent, fetchPersonalWork, type FileContentResponse, type PersonalWorkResponse, type PinnedFile, type Task } from '../lib/api'
import { PriorityBadge } from '../components/StatusBadge'
import { TaskDecisionDrawer } from '../components/TaskDecisionDrawer'

function TaskAdvice({ task, onOpen, tone }: {
  task: Task
  onOpen: () => void
  tone: 'action' | 'application' | 'evaluation'
}) {
  const toneClass = tone === 'action'
    ? 'border-accent-primary/30 hover:border-accent-primary'
    : tone === 'application'
      ? 'border-accent-success/25 hover:border-accent-success/60'
      : 'border-accent-warning/20 hover:border-accent-warning/50'
  return (
    <button onClick={onOpen} className={`group w-full rounded-xl border bg-bg-elevated p-4 text-left transition ${toneClass}`}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <PriorityBadge priority={task.priority}/>
            <span className="font-mono text-[10px] text-text-muted">{task.task_id}</span>
            <span className="project-chip">{task.project_name}</span>
          </div>
          <h3 className="mt-2 text-sm font-medium leading-6">{task.name}</h3>
        </div>
        <ArrowUpRight size={15} className="text-text-muted transition group-hover:text-text-primary"/>
      </div>
      <div className="mt-3 rounded-lg bg-bg-base/70 p-3">
        <div className="mb-1 text-[10px] font-semibold text-accent-secondary">为什么与你相关</div>
        <p className="text-xs leading-5 text-text-secondary">{task.personal_reason}</p>
      </div>
      {task.related_files.length > 0
        ? <div className="mt-3 flex items-start gap-2 text-[10px] text-text-muted"><FileText size={12} className="mt-0.5 shrink-0"/><span className="break-all">{task.related_files.join('、')}</span></div>
        : <div className="mt-3 flex items-center gap-2 text-[10px] text-accent-warning"><AlertTriangle size={12}/>缺少明确关联文件，进入执行前必须补证据</div>}
    </button>
  )
}

function WorkSection({ icon: Icon, eyebrow, title, description, items, empty, tone, onOpen }: {
  icon: typeof Bot
  eyebrow: string
  title: string
  description: string
  items: Task[]
  empty: string
  tone: 'action' | 'application' | 'evaluation'
  onOpen: (task: Task) => void
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-border-default bg-bg-elevated">
      <header className="flex flex-col gap-3 border-b border-border-default px-5 py-4 sm:flex-row sm:items-center">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-bg-surface text-accent-secondary"><Icon size={18}/></div>
        <div className="min-w-0 flex-1">
          <div className="text-[10px] font-semibold tracking-[.14em] text-text-muted">{eyebrow}</div>
          <h2 className="mt-1 font-heading text-base font-semibold">{title}</h2>
          <p className="mt-1 text-xs leading-5 text-text-secondary">{description}</p>
        </div>
        <span className="w-fit rounded-full bg-bg-surface px-2.5 py-1 font-mono text-xs text-text-secondary">{items.length}</span>
      </header>
      {items.length
        ? <div className="grid gap-3 p-4 lg:grid-cols-2">{items.map(task => <TaskAdvice key={task.task_id} task={task} tone={tone} onOpen={() => onOpen(task)}/>)}</div>
        : <div className="px-5 py-9 text-center text-xs text-text-muted">{empty}</div>}
    </section>
  )
}

function TaskbookSection({ items = [] }: { items?: PinnedFile[] }) {
  const [selected, setSelected] = useState<PinnedFile | null>(null)
  const [content, setContent] = useState<FileContentResponse | null>(null)
  async function open(item: PinnedFile) {
    setSelected(item); setContent(null)
    try { setContent(await fetchFileContent(item.project_name, item.file)) } catch { setContent(null) }
  }
  return <section className="overflow-hidden rounded-2xl border-2 border-amber-400 bg-amber-50"><header className="border-b border-amber-300 px-5 py-4"><div className="text-[10px] font-semibold tracking-[.14em] text-amber-700">P&L · AUTHORITATIVE TASK SOURCE</div><h2 className="mt-1 font-heading text-base font-semibold text-amber-950">我的 P&L 任务书</h2><p className="mt-1 text-xs leading-5 text-amber-900">任务已经在文件中明确，本区域直接展示任务书，不再根据变化生成另一套建议任务。</p></header><div className="p-4">{items.length ? items.map(item => <button key={item.file} onClick={() => open(item)} className="w-full rounded-xl border border-amber-300 bg-white p-4 text-left"><div className="flex items-center gap-2 text-xs font-semibold text-amber-950"><FileText size={14}/>{item.name}</div><p className="mt-2 break-all font-mono text-[10px] text-amber-700">{item.file}</p></button>) : <p className="text-xs text-amber-800">尚未识别到文件名包含 Jasper 的有效个人任务书。</p>}{selected && <div className="mt-3 rounded-xl border border-amber-300 bg-white p-4"><div className="mb-3 text-xs font-semibold">{selected.name} · 正文</div>{content ? <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap font-mono text-xs leading-6 text-text-secondary">{content.content}</pre> : <p className="text-xs text-text-muted">正在读取 Word 正文…</p>}</div>}</div></section>
}

export function ActivityFeed() {
  const [data, setData] = useState<PersonalWorkResponse | null>(null)
  const [selected, setSelected] = useState<Task | null>(null)
  const [error, setError] = useState('')
  const load = useCallback(async () => {
    try {
      setData(await fetchPersonalWork())
      setError('')
    } catch (e) {
      setError(String(e))
    }
  }, [])
  useEffect(() => { load() }, [load])
  if (error) return <div className="p-8 text-accent-danger">个人工作视图加载失败：{error}</div>
  if (!data) return <div className="p-8 text-text-muted">正在依据你的工作边界筛选文件变化…</div>

  const actionCount = data.direct_actions.length + data.ea_applications.length
  const informedCount = data.excluded_counts.EA + data.excluded_counts['P&L'] + data.excluded_counts.Jasper + data.excluded_counts.Rw
  return (
    <main className="mx-auto max-w-[1280px] space-y-6 px-5 py-7 lg:px-8">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-end">
        <div>
          <div className="eyebrow"><Sparkles size={12}/>PERSONAL WORK SCOPE</div>
          <h1 className="mt-2 font-heading text-2xl font-semibold tracking-tight lg:text-3xl">与我相关</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">EA、RW 与 Jasper 按职责判断；P&L 直接以你的个人任务书为任务来源，不做二次任务分析。</p>
        </div>
        <div className="ml-auto flex gap-3">
          <div className="rounded-xl border border-accent-primary/25 bg-accent-primary/5 px-4 py-3"><div className="text-2xl font-semibold">{actionCount}</div><div className="text-[10px] text-text-muted">当前行动事项</div></div>
          <div className="rounded-xl border border-border-default bg-bg-elevated px-4 py-3"><div className="text-2xl font-semibold">{informedCount}</div><div className="text-[10px] text-text-muted">留在知悉层</div></div>
        </div>
      </header>

      <section className="rounded-2xl border border-accent-secondary/20 bg-accent-secondary/5 p-5">
        <div className="flex items-center gap-2 text-xs font-semibold text-accent-secondary"><ShieldCheck size={15}/>当前生效的个人判断边界</div>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="scope-card"><Route size={16}/><div><b>EA · 核心行动域</b><p>{data.scope.ea}</p></div></div>
          <div className="scope-card border-accent-primary/25"><Route size={16}/><div><b>P&L · EA小组经营分析</b><p>{data.scope.pnl}</p></div></div>
          <div className="scope-card"><FlaskConical size={16}/><div><b>Jasper · 应用来源</b><p>{data.scope.jasper}</p></div></div>
          <div className="scope-card"><Route size={16}/><div><b>RW · 核心行动域</b><p>{data.scope.rw}</p></div></div>
        </div>
      </section>

      <div className="grid gap-3 rounded-xl border border-border-default bg-bg-elevated p-4 text-xs text-text-secondary md:grid-cols-[auto_1fr_auto_1fr_1.2fr]">
        <span className="font-semibold text-text-primary">判断链路</span>
        <span>文件变化</span><ArrowRight size={13} className="hidden text-text-muted md:block"/>
        <span>EA/RW/Jasper 做职责判断；P&L 读取任务书</span>
        <span className="text-accent-secondary">行动 / 评估 / 仅知悉</span>
      </div>

      <WorkSection icon={Route} eyebrow="EA / RW · DIRECT ACTION" title="核心业务直接行动"
        description="只保留明确影响人机协同流程与 SOP、信号与规则、端到端任务 Agent 化的事项，EA 与 RW 使用同一套判断标准。"
        items={data.direct_actions} empty="当前没有命中个人职责边界的 EA/RW 开放事项" tone="action" onOpen={setSelected}/>
      <TaskbookSection items={data.pnl_taskbooks}/>
      <WorkSection icon={Bot} eyebrow="JASPER → EA" title="可应用到 EA"
        description="Jasper 的技术或方法变化已经出现明确 EA 应用映射，可以进入行动区。"
        items={data.ea_applications} empty="当前没有已明确映射到 EA 的 Jasper 变化" tone="application" onOpen={setSelected}/>
      <WorkSection icon={CircleDot} eyebrow="EVALUATE, NOT ACTION" title="待评估"
        description="存在人机协同或 Agent 应用潜力，但尚未证明能用于 EA；不计入行动事项。"
        items={data.pending_evaluation} empty="当前没有需要判断 EA 应用价值的候选事项" tone="evaluation" onOpen={setSelected}/>

      <div className="rounded-xl border border-border-default bg-bg-base/50 px-4 py-3 text-[11px] leading-5 text-text-muted">
        已留在知悉层：EA {data.excluded_counts.EA} 项、P&L {data.excluded_counts['P&L']} 项、Jasper {data.excluded_counts.Jasper} 项、RW {data.excluded_counts.Rw} 项。请到“指挥中心”查看完整文件变化。
      </div>
      <TaskDecisionDrawer task={selected} onClose={() => setSelected(null)} onSaved={load}/>
    </main>
  )
}
