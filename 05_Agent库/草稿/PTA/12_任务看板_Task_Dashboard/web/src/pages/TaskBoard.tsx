import { useEffect, useMemo, useState } from 'react'
import {
  Activity, ArrowDownToLine, ArrowRight, BarChart3, CalendarDays, ChevronDown, Clock3,
  FileDiff, FileMinus2, FilePlus2, FolderKanban, GitCompareArrows, Link2,
  RotateCcw, Search, SlidersHorizontal, Sparkles, Users,
} from 'lucide-react'
import {
  fetchCommandCenter, fetchFileContent, type ChangeItem, type CommandCenterResponse,
  type FileContentResponse,
  type CommandProject, type CrossProjectRelation, type Task,
} from '../lib/api'
import { PriorityBadge } from '../components/StatusBadge'

type ChangeFilter = 'all' | ChangeItem['change_type']
type DateRange = 1 | 3 | 7 | 30

const CHANGE_META = {
  added: { label: '新增', icon: FilePlus2, cls: 'text-accent-success bg-accent-success/10 border-accent-success/20' },
  changed: { label: '修改', icon: FileDiff, cls: 'text-accent-info bg-accent-info/10 border-accent-info/20' },
  removed: { label: '删除', icon: FileMinus2, cls: 'text-accent-danger bg-accent-danger/10 border-accent-danger/20' },
}

const FILTER_OPTIONS: { value: ChangeFilter; label: string; icon: typeof FileDiff }[] = [
  { value: 'all', label: '全部变更', icon: SlidersHorizontal },
  { value: 'added', label: '新增', icon: FilePlus2 },
  { value: 'changed', label: '修改', icon: FileDiff },
  { value: 'removed', label: '删除', icon: FileMinus2 },
]

const DATE_OPTIONS: { value: DateRange; label: string }[] = [
  { value: 30, label: '过往30天' },
  { value: 7, label: '过往7天' },
  { value: 3, label: '过往3天' },
  { value: 1, label: '过往1天' },
]

function formatTime(value: string) {
  if (!value) return '尚未成功巡检'
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function peopleFromWho(who: string) {
  const value = (who || '未知来源').trim()
  if (!value) return ['未知来源']
  return value.split(/[、,，/;；]+/).map(item => item.trim()).filter(Boolean)
}

function matchesFileQuery(change: ChangeItem, rawQuery: string) {
  const query = rawQuery.trim().toLocaleLowerCase()
  if (!query) return true
  const content = `${change.file} ${change.summary || ''}`.toLocaleLowerCase()
  // 短英文缩写按词/路径片段匹配，避免 pta 误命中 acceptance 中间的字母。
  if (/^[a-z0-9]{1,4}$/.test(query)) {
    return content.split(/[^a-z0-9]+/).some(token => token === query || token.startsWith(query))
  }
  return content.includes(query)
}

function ChangeRow({ change, projectName }: { change: ChangeItem; projectName: string }) {
  const [open, setOpen] = useState(false)
  const [document, setDocument] = useState<FileContentResponse | null>(null)
  const [documentError, setDocumentError] = useState('')
  const [documentLoading, setDocumentLoading] = useState(false)
  const meta = CHANGE_META[change.change_type] || CHANGE_META.changed
  const Icon = meta.icon
  const hasDetail = !!(change.diff_text || change.before_excerpt || change.after_excerpt)
  async function togglePreview() {
    const willOpen = !open
    setOpen(willOpen)
    if (!willOpen || document || documentLoading || documentError) return
    setDocumentLoading(true)
    try {
      setDocument(await fetchFileContent(projectName, change.file))
    } catch (error) {
      setDocumentError(error instanceof Error ? error.message.replace(/^.*请求失败: /, '') : String(error))
    } finally {
      setDocumentLoading(false)
    }
  }
  return (
    <div className="border-b border-border-default/70 last:border-0">
      <button onClick={togglePreview} aria-expanded={open} className="group flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-bg-surface/50">
        <span className={`mt-0.5 flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] font-medium ${meta.cls}`}><Icon size={11}/>{meta.label}</span>
        <div className="min-w-0 flex-1">
          <div className="break-all font-mono text-[11px] text-text-primary">{change.file}</div>
          <div className="mt-1 text-xs leading-5 text-text-secondary">{change.summary || '已记录文件事实变化'}</div>
          <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-text-muted"><span>{change.domain || '其他'}</span><span>·</span><span>{change.who || '未知来源'}</span>{change.observed_at && <><span>·</span><span>发现于 {formatTime(change.observed_at)}</span></>}{!hasDetail && <><span>·</span><span>旧报告未保存内容级 diff</span></>}</div>
        </div>
        <span className="mt-0.5 flex shrink-0 items-center gap-1 rounded-md border border-border-default bg-bg-base px-2 py-1 text-[10px] text-text-secondary group-hover:border-border-hover"><span className="hidden sm:inline">{open ? '收起预览' : '预览详情'}</span><ChevronDown size={13} className={`transition ${open ? 'rotate-180' : ''}`}/></span>
      </button>
      {open && (
        <div className="mx-4 mb-4 space-y-3">
          <section className="overflow-hidden rounded-xl border border-accent-primary/20 bg-white">
            <header className="flex flex-wrap items-center gap-2 border-b border-border-default bg-accent-primary/5 px-3 py-2"><div className="text-xs font-semibold text-text-primary">当前文件全文</div>{document && <><span className="text-[10px] text-text-muted">{(document.size_bytes / 1024).toFixed(1)} KB</span><span className="text-[10px] text-text-muted">· 最近修改 {formatTime(document.modified_at)}</span></>}</header>
            {documentLoading && <div className="p-4 text-xs text-text-muted">正在读取文件正文…</div>}
            {documentError && <div className="p-4"><p className="text-xs text-accent-warning">{documentError}</p><p className="mt-2 text-[10px] text-text-muted">历史巡检摘录仍可在下方查看。</p></div>}
            {document && <><pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-xs leading-6 text-text-secondary">{document.content}</pre>{document.truncated && <div className="border-t border-accent-warning/20 bg-accent-warning/5 px-4 py-2 text-[10px] text-accent-warning">文件超过 2 MB，当前预览显示前 2 MB 内容。</div>}</>}
          </section>
          <section className="overflow-hidden rounded-xl border border-border-default bg-bg-base">
            <header className="border-b border-border-default px-3 py-2 text-xs font-semibold text-text-primary">巡检时变化记录</header>
          {!hasDetail && <div className="p-4"><div className="text-xs font-semibold text-text-primary">本次记录没有保存内容快照</div><p className="mt-2 text-xs leading-5 text-text-secondary">可确认的更新摘要：{change.summary || '仅检测到文件发生变化，暂无内容级摘要。'}</p><p className="mt-2 text-[10px] text-text-muted">这通常来自较早版本的巡检报告；系统不会用当前文件内容冒充当时的历史版本。</p></div>}
          {change.change_type === 'changed' && (change.before_excerpt || change.after_excerpt) && (
            <div className="grid md:grid-cols-2">
              <div className="border-b border-border-default p-3 md:border-b-0 md:border-r"><div className="mb-2 text-[10px] font-semibold text-accent-danger">修改前</div><pre className="max-h-44 overflow-auto whitespace-pre-wrap text-[10px] leading-5 text-text-muted">{change.before_excerpt || '无可读内容'}</pre></div>
              <div className="p-3"><div className="mb-2 text-[10px] font-semibold text-accent-success">修改后</div><pre className="max-h-44 overflow-auto whitespace-pre-wrap text-[10px] leading-5 text-text-secondary">{change.after_excerpt || '无可读内容'}</pre></div>
            </div>
          )}
          {change.change_type !== 'changed' && <div className="p-3"><div className="mb-2 text-[10px] font-semibold text-text-secondary">{change.change_type === 'added' ? '新增内容' : '删除前最后内容'}</div><pre className="max-h-52 overflow-auto whitespace-pre-wrap text-[10px] leading-5 text-text-muted">{change.after_excerpt || change.before_excerpt || change.diff_text}</pre></div>}
          {change.diff_text && change.change_type === 'changed' && <details className="border-t border-border-default"><summary className="cursor-pointer px-3 py-2 text-[10px] text-text-muted">查看原始 diff</summary><pre className="max-h-56 overflow-auto whitespace-pre-wrap px-3 pb-3 text-[10px] leading-5 text-text-secondary">{change.diff_text}</pre></details>}
          </section>
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

function ProjectPanel({ project, primary = false, filtering = false }: { project: CommandProject; primary?: boolean; filtering?: boolean }) {
  const [showAll, setShowAll] = useState(primary)
  const counts = {
    added: project.changes.filter(c => c.change_type === 'added').length,
    changed: project.changes.filter(c => c.change_type === 'changed').length,
    removed: project.changes.filter(c => c.change_type === 'removed').length,
  }
  const visible = showAll ? project.changes : project.changes.slice(0, 4)
  return (
    <section className={`overflow-hidden rounded-2xl border bg-bg-elevated ${primary ? 'border-accent-primary/30 shadow-[0_18px_60px_rgba(60,72,110,.12)]' : 'border-border-default'}`}>
      <header className={`border-b border-border-default px-5 py-4 ${primary ? 'bg-gradient-to-r from-accent-primary/10 to-transparent' : ''}`}>
        <div className="flex items-start gap-3"><div className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${primary ? 'bg-accent-primary text-white' : 'bg-bg-surface text-text-secondary'}`}><FolderKanban size={18}/></div><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h2 className="font-heading text-base font-semibold">{project.project_name}</h2><span className="rounded bg-bg-surface px-2 py-0.5 text-[10px] text-text-muted">{project.label}</span></div><p className="mt-1 text-[11px] leading-5 text-text-muted">{project.question}</p></div></div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="change-counter text-accent-success"><ArrowDownToLine size={12}/>新增 {counts.added}</span>
          <span className="change-counter text-accent-info"><FileDiff size={12}/>修改 {counts.changed}</span>
          <span className="change-counter text-accent-danger"><FileMinus2 size={12}/>删除 {counts.removed}</span>
          <span className="ml-auto flex items-center gap-1 text-[10px] text-text-muted"><Clock3 size={11}/>{formatTime(project.generated_at)}</span>
        </div>
      </header>
      {project.changes.length === 0 ? <div className="px-5 py-10 text-center"><Activity className={`mx-auto ${filtering ? 'text-text-muted' : 'text-accent-success'}`} size={20}/><p className="mt-2 text-xs text-text-secondary">{filtering ? '当前筛选条件下没有匹配文件' : '本周期无文件变化'}</p><p className="mt-1 text-[10px] text-text-muted">{filtering ? '可调整变更类型、成员或文件关键词' : '巡检成功，不是数据缺失'}</p></div> : (
        <><div>{visible.map((c, i) => <ChangeRow key={`${c.file}-${i}`} change={c} projectName={project.project_name}/>)}</div>{!showAll && project.changes.length > visible.length && <button onClick={() => setShowAll(true)} className="w-full border-t border-border-default px-4 py-3 text-xs text-accent-primary-light hover:bg-bg-surface">查看全部 {project.changes.length} 个匹配文件</button>}</>
      )}
      {project.relationships.length > 0 && <div className="border-t border-border-default bg-bg-base/40 px-4 py-3"><div className="mb-2 flex items-center gap-1 text-[10px] font-semibold text-text-secondary"><Link2 size={11}/>与筛选文件相关的变化关系</div>{project.relationships.slice(0, primary ? 4 : 2).map((r, i) => <p key={i} className="mb-1 text-[10px] leading-5 text-text-muted">{r.description}</p>)}</div>}
      {project.related_tasks.length > 0 && <div className="border-t border-border-default px-4 py-4"><div className="mb-3 flex items-center gap-1 text-[10px] font-semibold text-text-secondary"><Sparkles size={11}/>与筛选文件相关的任务</div><div className="space-y-2">{project.related_tasks.slice(0, primary ? 5 : 2).map(t => <TaskSignal key={t.task_id} task={t}/>)}</div></div>}
    </section>
  )
}

function FilterAnalysis({ projects, type, member, query }: { projects: CommandProject[]; type: ChangeFilter; member: string; query: string }) {
  const rows = projects.flatMap(project => project.changes.map(change => ({ project: project.project_name, change })))
  if (!rows.length) return <section className="rounded-2xl border border-border-default bg-bg-elevated p-5"><div className="flex items-center gap-2 text-sm font-semibold"><BarChart3 size={16} className="text-accent-secondary"/>更新分析</div><p className="mt-3 text-xs text-text-muted">当前筛选条件没有匹配内容，暂时无法形成更新分析。</p></section>
  const domains = new Map<string, number>()
  const people = new Map<string, number>()
  rows.forEach(({ change }) => {
    domains.set(change.domain || '其他', (domains.get(change.domain || '其他') || 0) + 1)
    peopleFromWho(change.who).forEach(person => people.set(person, (people.get(person) || 0) + 1))
  })
  const topDomains = [...domains.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3)
  const topPeople = [...people.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3)
  const removals = rows.filter(({ change }) => change.change_type === 'removed').length
  const typeText = type === 'all' ? '全部类型' : CHANGE_META[type].label
  return (
    <section className="rounded-2xl border border-accent-secondary/20 bg-gradient-to-br from-accent-secondary/8 to-bg-elevated p-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-start"><div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent-secondary/10 text-accent-secondary"><BarChart3 size={18}/></div><div className="min-w-0 flex-1"><h2 className="font-heading text-base font-semibold">筛选结果 · 更新分析</h2><p className="mt-1 text-xs leading-5 text-text-secondary">当前查看 {typeText}{member !== 'all' ? ` · ${member}` : ''}{query ? ` · 文件包含“${query}”` : ''}，共命中 {rows.length} 个文件，涉及 {new Set(rows.map(row => row.project)).size} 个项目。</p></div></div>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <div className="analysis-stat"><span>主要更新领域</span><b>{topDomains.map(([name, count]) => `${name} ${count}`).join(' · ')}</b></div>
        <div className="analysis-stat"><span>主要更新成员</span><b>{topPeople.map(([name, count]) => `${name} ${count}`).join(' · ')}</b></div>
        <div className="analysis-stat"><span>风险提示</span><b className={removals ? 'text-accent-warning' : ''}>{removals ? `${removals} 个删除项，建议核对依赖关系` : '未发现删除项'}</b></div>
      </div>
      <div className="mt-4 border-t border-border-default/70 pt-4"><div className="mb-2 text-[10px] font-semibold tracking-wide text-text-muted">重点更新速读</div><div className="grid gap-2 lg:grid-cols-2">{rows.slice(0, 6).map(({ project, change }, index) => <div key={`${project}-${change.file}-${index}`} className="rounded-lg bg-bg-base/60 p-3"><div className="flex items-center gap-2 text-[10px] text-text-muted"><span>{project}</span><span>·</span><span>{CHANGE_META[change.change_type].label}</span><span>·</span><span>{change.who || '未知来源'}</span></div><p className="mt-1 text-xs leading-5 text-text-secondary">{change.summary || change.file}</p></div>)}</div>{rows.length > 6 && <p className="mt-2 text-[10px] text-text-muted">其余 {rows.length - 6} 个匹配文件请在下方项目视图继续查阅。</p>}</div>
    </section>
  )
}

function RelationCard({ relation }: { relation: CrossProjectRelation }) {
  return <div className="rounded-xl border border-border-default bg-bg-elevated p-4"><div className="flex items-center gap-2 text-xs font-medium"><span>{relation.from_project}</span><ArrowRight size={13} className="text-accent-secondary"/><span>{relation.to_project}</span></div><p className="mt-2 text-xs leading-5 text-text-secondary">{relation.analysis}</p><div className="mt-3 flex flex-wrap gap-1">{relation.shared_domains.map(d => <span key={d} className="rounded bg-bg-surface px-2 py-1 text-[10px] text-text-muted">{d}</span>)}</div><p className="mt-3 text-[10px] text-accent-warning">关系线索，需结合文件内容核对，不视为已确认因果</p></div>
}

export function TaskBoard() {
  const [data, setData] = useState<CommandCenterResponse | null>(null)
  const [error, setError] = useState('')
  const [changeType, setChangeType] = useState<ChangeFilter>('all')
  const [rangeDays, setRangeDays] = useState<DateRange>(1)
  const [member, setMember] = useState('all')
  const [fileQuery, setFileQuery] = useState('')
  useEffect(() => {
    setData(null)
    fetchCommandCenter(rangeDays).then(setData).catch(e => setError(String(e)))
  }, [rangeDays])

  const members = useMemo(() => {
    if (!data) return []
    return [...new Set(data.projects.flatMap(project => project.changes.flatMap(change => peopleFromWho(change.who))))].sort((a, b) => a.localeCompare(b, 'zh-CN'))
  }, [data])
  const filtering = changeType !== 'all' || member !== 'all' || !!fileQuery.trim()
  const filteredProjects = useMemo(() => {
    if (!data) return []
    const query = fileQuery.trim().toLocaleLowerCase()
    return data.projects.map(project => {
      const changes = project.changes.filter(change => {
        const typeMatch = changeType === 'all' || change.change_type === changeType
        const memberMatch = member === 'all' || peopleFromWho(change.who).includes(member)
        const fileMatch = matchesFileQuery(change, query)
        return typeMatch && memberMatch && fileMatch
      })
      const files = new Set(changes.map(change => change.file))
      return {
        ...project,
        changes,
        total_changes: changes.length,
        relationships: filtering ? project.relationships.filter(item => item.related_files.some(file => files.has(file))) : project.relationships,
        related_tasks: filtering ? project.related_tasks.filter(task => task.related_files?.some(file => files.has(file))) : project.related_tasks,
      }
    })
  }, [data, changeType, member, fileQuery, filtering])
  const core = filteredProjects.find(project => project.role === 'core')
  const secondary = filteredProjects.filter(project => project.role !== 'core')
  const total = data?.projects.reduce((sum, project) => sum + project.total_changes, 0) || 0
  const filteredTotal = filteredProjects.reduce((sum, project) => sum + project.changes.length, 0)
  const filteredFiles = new Set(filteredProjects.flatMap(project => project.changes.map(change => change.file)))
  const filteredRelations = data?.cross_project_relations.filter(relation => !filtering || relation.evidence_files.some(file => filteredFiles.has(file))) || []
  const resetFilters = () => { setChangeType('all'); setMember('all'); setFileQuery('') }

  if (error) return <div className="p-8 text-accent-danger">指挥中心加载失败：{error}</div>
  if (!data) return <div className="p-8 text-text-muted">正在汇总三个项目的最新文件事实…</div>
  return (
    <main className="mx-auto max-w-[1440px] space-y-7 px-5 py-7 lg:px-8">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-end"><div><div className="eyebrow"><GitCompareArrows size={12}/>PERSONAL PROJECT INTELLIGENCE</div><h1 className="mt-2 font-heading text-2xl font-semibold tracking-tight lg:text-3xl">项目指挥中心</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">文件事实是唯一源头：选择时间范围，筛选谁更新了什么，快速定位文件，再查看筛选范围内的更新分析。</p></div><div className="ml-auto rounded-xl border border-border-default bg-bg-elevated px-4 py-3"><div className="text-2xl font-semibold">{filtering ? filteredTotal : total}</div><div className="text-[10px] text-text-muted">{filtering ? `筛选命中 / 全部 ${total}` : `过去 ${rangeDays} 天文件变化`}</div></div></header>
      <div className="rounded-xl border border-accent-secondary/15 bg-accent-secondary/5 px-4 py-3 text-xs text-text-secondary"><b className="text-accent-secondary">SSOT 时间口径：</b>{data.period_basis}</div>

      <section className="sticky top-[65px] z-30 rounded-2xl border border-border-default bg-bg-elevated/95 p-4 shadow-xl backdrop-blur-xl">
        <div className="mb-4 border-b border-border-default pb-4"><div className="mb-2 flex items-center gap-2 text-xs font-semibold"><CalendarDays size={14} className="text-accent-secondary"/>日期范围</div><div className="flex flex-wrap gap-2">{DATE_OPTIONS.map(option => <button key={option.value} onClick={() => setRangeDays(option.value)} aria-pressed={rangeDays === option.value} className={`filter-chip ${rangeDays === option.value ? 'filter-chip-active' : ''}`}>{option.label}</button>)}</div></div>
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end">
          <div className="min-w-0 flex-1"><div className="mb-2 flex items-center gap-2 text-xs font-semibold"><SlidersHorizontal size={14} className="text-accent-secondary"/>变更类型</div><div className="flex flex-wrap gap-2">{FILTER_OPTIONS.map(({ value, label, icon: Icon }) => <button key={value} onClick={() => setChangeType(value)} aria-pressed={changeType === value} className={`filter-chip ${changeType === value ? 'filter-chip-active' : ''}`}><Icon size={13}/>{label}</button>)}</div></div>
          <label className="block min-w-[190px] text-xs font-semibold"><span className="mb-2 flex items-center gap-2"><Users size={14} className="text-accent-secondary"/>项目组成员</span><select value={member} onChange={event => setMember(event.target.value)} className="field h-10 py-0"><option value="all">全部成员</option>{members.map(name => <option key={name} value={name}>{name}</option>)}</select></label>
          <label className="block min-w-0 flex-1 text-xs font-semibold xl:max-w-sm"><span className="mb-2 flex items-center gap-2"><Search size={14} className="text-accent-secondary"/>快速定位更新文件</span><div className="relative"><Search size={14} className="absolute left-3 top-3 text-text-muted"/><input value={fileQuery} onChange={event => setFileQuery(event.target.value)} className="field h-10 py-0 pl-9" placeholder="输入文件名、路径或更新摘要"/></div></label>
          <button onClick={resetFilters} disabled={!filtering} className="action-secondary h-10 px-3 py-0 text-xs"><RotateCcw size={13}/>清除筛选</button>
        </div>
      </section>

      <FilterAnalysis projects={filteredProjects} type={changeType} member={member} query={fileQuery.trim()}/>
      <section className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.65fr)_minmax(360px,.85fr)]">{core ? <ProjectPanel project={core} primary filtering={filtering}/> : <div className="rounded-2xl border border-accent-danger/20 p-8 text-sm text-accent-danger">EA 核心项目尚无成功巡检报告</div>}<div className="space-y-6">{secondary.map(project => <ProjectPanel key={project.project_name} project={project} filtering={filtering}/>)}</div></section>
      <section><div className="mb-3 flex items-center gap-2"><GitCompareArrows size={16} className="text-accent-secondary"/><h2 className="font-heading text-base font-semibold">{filtering ? '与筛选文件相关的跨项目关系' : '跨项目关系线索'}</h2><span className="text-[10px] text-text-muted">EA ↔ Jasper ↔ Rw</span></div>{filteredRelations.length ? <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{filteredRelations.map((relation, index) => <RelationCard key={`${relation.from_project}-${relation.to_project}-${index}`} relation={relation}/>)}</div> : <div className="rounded-xl border border-border-default bg-bg-elevated px-5 py-8 text-center text-xs text-text-muted">{filtering ? '当前筛选文件没有已记录的跨项目关系线索' : '本轮三个项目暂未出现共同业务域的变化线索'}</div>}</section>
    </main>
  )
}
