import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router'
import { AlertTriangle, ArrowRight, CheckCircle2, Database, GitBranch, LoaderCircle, Search } from 'lucide-react'
import { loadModelIndex, type ModelIndex, type ModelIndexItem } from '../lib/l3Models'

function Gate({ name, status }: { name: string; status: string }) {
  const pass = status === 'PASS'
  return (
    <span className={`rounded-md border px-2 py-1 font-mono text-[11px] ${pass ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300' : 'border-amber-400/25 bg-amber-400/10 text-amber-300'}`}>
      {name} · {status}
    </span>
  )
}

function ModelCard({ model }: { model: ModelIndexItem }) {
  const ready = model.classification === 'MODEL_READY'
  return (
    <Link to={`/models/${model.l3_code}`} className="group panel block p-5 transition hover:border-border-hover hover:-translate-y-0.5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs text-accent-primary-light">{model.l3_code}</p>
          <h2 className="mt-1 text-base font-semibold text-text-primary">{model.l3_name}</h2>
        </div>
        <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${ready ? 'bg-emerald-400/10 text-emerald-300' : 'bg-amber-400/10 text-amber-300'}`}>
          {ready ? '可进入模型' : '待补数据'}
        </span>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Gate name="M" status={model.gates.M} />
        <Gate name="E" status={model.gates.E} />
        <Gate name="A" status={model.gates.A} />
      </div>
      <div className="mt-4 flex items-center justify-between border-t border-border-default pt-3 text-xs text-text-muted">
        <span>{model.l4_count} 个 L4 · {model.value_node_count} 个价值节点 · 蓝图 {model.blueprint_version || '缺失'}</span>
        <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" />
      </div>
      {!ready && model.gap_reasons.length > 0 && (
        <p className="mt-2 line-clamp-2 text-xs text-amber-200/80">首要缺口：{model.gap_reasons[0]}</p>
      )}
    </Link>
  )
}

export default function L3Models() {
  const [data, setData] = useState<ModelIndex | null>(null)
  const [error, setError] = useState('')
  const [view, setView] = useState<'all' | 'ready' | 'evaluable' | 'missing'>('all')
  const [query, setQuery] = useState('')

  useEffect(() => {
    loadModelIndex().then(setData).catch(error => setError(error.message))
  }, [])

  const groups = useMemo(() => ({
    all: data?.models ?? [],
    ready: data?.models.filter(item => item.classification === 'MODEL_READY') ?? [],
    evaluable: data?.models.filter(item => item.highest_gate === 'E') ?? [],
    missing: data?.models.filter(item => item.classification === 'NEEDS_DATA') ?? [],
  }), [data])

  if (error) return <div className="panel p-5 text-sm text-accent-danger">{error}</div>
  if (!data) return <div className="flex min-h-64 items-center justify-center text-text-muted"><LoaderCircle className="mr-2 h-5 w-5 animate-spin" />正在读取真实模型快照</div>

  const current = groups[view].filter(model => `${model.l3_code}${model.l3_name}`.toLowerCase().includes(query.toLowerCase()))
  const parsedCount = data.models.filter(model => model.blueprint_structure_status === 'PARSED').length
  const recommended = groups.ready[0]
  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-xs text-accent-primary-light"><GitBranch className="h-4 w-4" /> L3 流程模型系统 · V1</div>
        <h1 className="mt-2 font-heading text-3xl font-bold">哪些流程可以进入 AI 化设计？</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">
          先看权威数据是否足以支撑模型。满足标准的进入模型评审；不满足的进入待补清单，不用推测填空。
        </p>
      </div>

      {recommended && (
        <Link to={`/models/${recommended.l3_code}`} className="block rounded-2xl border border-emerald-400/25 bg-emerald-400/5 p-5 transition hover:bg-emerald-400/10">
          <p className="eyebrow text-emerald-300">系统推荐 · 当前唯一通过 Gate A</p>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
            <div><p className="text-lg font-semibold text-text-primary">{recommended.l3_code} · {recommended.l3_name}</p><p className="mt-1 text-xs text-text-secondary">{recommended.l4_count} 个 L4 的 D1-D6 与价值节点映射满足当前移交门槛，建议作为首个 AIT 设计样本。</p></div>
            <span className="flex items-center gap-1 text-xs text-emerald-300">查看模型 <ArrowRight className="h-4 w-4" /></span>
          </div>
        </Link>
      )}

      <div className="panel flex flex-wrap items-center gap-3 p-3">
        <button onClick={() => setView('all')} className={`flex items-center gap-2 rounded-xl px-4 py-3 text-sm ${view === 'all' ? 'bg-accent-primary/10 text-accent-primary-light' : 'text-text-secondary hover:bg-bg-surface'}`}>
          全部 L3 <strong>{groups.all.length}</strong>
        </button>
        <button onClick={() => setView('ready')} className={`flex items-center gap-2 rounded-xl px-4 py-3 text-sm ${view === 'ready' ? 'bg-emerald-400/10 text-emerald-300' : 'text-text-secondary hover:bg-bg-surface'}`}>
          <CheckCircle2 className="h-4 w-4" /> 可移交 AIT <strong>{groups.ready.length}</strong>
        </button>
        <button onClick={() => setView('evaluable')} className={`flex items-center gap-2 rounded-xl px-4 py-3 text-sm ${view === 'evaluable' ? 'bg-sky-400/10 text-sky-300' : 'text-text-secondary hover:bg-bg-surface'}`}>
          可评估、待补后移交 <strong>{groups.evaluable.length}</strong>
        </button>
        <button onClick={() => setView('missing')} className={`flex items-center gap-2 rounded-xl px-4 py-3 text-sm ${view === 'missing' ? 'bg-amber-400/10 text-amber-300' : 'text-text-secondary hover:bg-bg-surface'}`}>
          <AlertTriangle className="h-4 w-4" /> 数据不足待补 <strong>{groups.missing.length}</strong>
        </button>
        <div className="ml-auto flex items-center gap-2 px-3 text-[11px] text-text-muted"><Database className="h-3.5 w-3.5" /> {data.source_policy}</div>
      </div>

      <div className="grid gap-3 sm:grid-cols-4">
        {[
          ['数据库 L3', data.models.length, '权威库当前有效集合'],
          ['可解析蓝图', parsedCount, '已有步骤或判断结构'],
          ['可评估', groups.evaluable.length + groups.ready.length, '至少通过 Gate E'],
          ['可移交 AIT', groups.ready.length, '通过 Gate A'],
        ].map(([label, value, note]) => (
          <div key={String(label)} className="panel p-4"><p className="eyebrow">{label}</p><p className="mt-2 metric-value">{value}</p><p className="mt-1 text-[11px] text-text-muted">{note}</p></div>
        ))}
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
        <input value={query} onChange={event => setQuery(event.target.value)} placeholder="按 L3 编码或名称搜索" className="w-full rounded-xl border border-border-default bg-bg-elevated py-2 pl-9 pr-3 text-sm text-text-primary placeholder:text-text-muted" />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {current.map(model => <ModelCard key={model.l3_code} model={model} />)}
      </div>
    </div>
  )
}
