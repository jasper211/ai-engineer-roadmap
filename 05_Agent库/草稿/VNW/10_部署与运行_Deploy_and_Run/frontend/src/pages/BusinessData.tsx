import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { Database, LoaderCircle, Search } from 'lucide-react'
import { loadModelIndex, loadL3Model, type ModelIndex, type L3Model } from '../lib/l3Models'

const EVIDENCE_TYPE_INFO: Record<string, { label: string; tone: string }> = {
  output: { label: '产出证据', tone: 'text-emerald-700' },
  rule: { label: '规则证据', tone: 'text-indigo-700' },
  workflow: { label: '流程状态证据', tone: 'text-amber-700' },
  audit: { label: '追溯证据', tone: 'text-slate-600' },
}

function L3EvidenceDetail({ l3Code }: { l3Code: string }) {
  const [model, setModel] = useState<L3Model | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    loadL3Model(l3Code).then(setModel).catch(err => setError(err.message))
  }, [l3Code])

  if (error) return <p className="p-3 text-xs text-accent-danger">{error}</p>
  if (!model) return <p className="p-3 text-xs text-text-muted">加载中…</p>

  const covered = model.l4s.filter(l4 => l4.business_evidence.length > 0)
  const uncovered = model.l4s.filter(l4 => l4.business_evidence.length === 0)

  return (
    <div className="space-y-2 p-3">
      {covered.length === 0 ? (
        <p className="text-xs text-text-muted">该L3的L4尚未评估业务数据仓库匹配（未进入试点范围）。</p>
      ) : (
        covered.map(l4 => (
          <div key={l4.l4_code} className="rounded-lg border border-border-default bg-bg-surface p-3">
            <p className="font-mono text-[11px] text-accent-primary-light">{l4.l4_code} · {l4.l4_name}</p>
            <div className="mt-2 space-y-1">
              {l4.business_evidence.map(evidence => (
                <p key={`${evidence.schema}.${evidence.table}`} className="text-[10px] leading-4 text-text-secondary">
                  <span className={`font-semibold ${EVIDENCE_TYPE_INFO[evidence.evidence_type]?.tone}`}>[{EVIDENCE_TYPE_INFO[evidence.evidence_type]?.label ?? evidence.evidence_type}]</span>{' '}
                  <span className="font-mono">{evidence.schema}.{evidence.table}</span>（{evidence.row_count ?? '?'}行，{evidence.confidence === 'strong' ? '强匹配' : '弱匹配'}）· {evidence.rationale}
                </p>
              ))}
            </div>
          </div>
        ))
      )}
      {uncovered.length > 0 && covered.length > 0 && (
        <p className="text-[10px] text-text-muted">其余 {uncovered.length} 个L4（{uncovered.map(l4 => l4.l4_code).join('、')}）未匹配到业务数据仓库表，业务数据仓库122张表逐一核实后确认不覆盖，非遗漏。</p>
      )}
    </div>
  )
}

export default function BusinessData() {
  const [searchParams] = useSearchParams()
  const [data, setData] = useState<ModelIndex | null>(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [expanded, setExpanded] = useState<string | null>(searchParams.get('l3'))

  useEffect(() => {
    loadModelIndex().then(setData).catch(err => setError(err.message))
  }, [])

  const evaluated = useMemo(() => data?.models.filter(m => m.business_evidence_l4_count > 0) ?? [], [data])
  const totalL4Covered = useMemo(() => evaluated.reduce((sum, m) => sum + m.business_evidence_l4_count, 0), [evaluated])

  const filtered = useMemo(() => {
    if (!data) return []
    const q = query.toLowerCase()
    return data.models
      .filter(m => !q || `${m.l3_code}${m.l3_name}`.toLowerCase().includes(q))
      .sort((a, b) => b.business_evidence_l4_count - a.business_evidence_l4_count)
  }, [data, query])

  if (error) return <div className="panel p-5 text-sm text-accent-danger">{error}</div>
  if (!data) return <div className="flex min-h-64 items-center justify-center text-text-muted"><LoaderCircle className="mr-2 h-5 w-5 animate-spin" />正在读取业务数据分析</div>

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-xs text-accent-primary-light"><Database className="h-4 w-4" /> 业务数据分析 · 新接入输入源</div>
        <h1 className="mt-2 font-heading text-3xl font-bold">L4任务背后有没有真实业务系统数据支撑？</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">
          与机会台的Gate/D1-D6/KPI等数据库原生字段不同，这里是人工逐张表核实public/comm_sandbox/fin_sandbox
          业务数据仓库（122张表）后，判断每个L4的交付物在业务系统里有没有真实数据落地——产出证据(交付物实际数据)、
          规则证据(判断逻辑已参数化)、流程状态证据(暴露人工关卡位置)、追溯证据(变更可追溯程度)。
          目前只完成了L3-COM试点，其余L3待评估，如实标注，不猜测编造。
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="panel p-4"><p className="eyebrow">已评估L3</p><p className="mt-2 metric-value">{evaluated.length}/{data.models.length}</p></div>
        <div className="panel p-4"><p className="eyebrow">已定位业务表的L4</p><p className="mt-2 metric-value">{totalL4Covered}</p></div>
        <div className="panel p-4"><p className="eyebrow">业务数据仓库表总数</p><p className="mt-2 metric-value">122</p><p className="mt-1 text-[11px] text-text-muted">public 75 · comm_sandbox 24 · fin_sandbox 5 · process_analytics 18（见"数据库现状"）</p></div>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
        <input value={query} onChange={event => setQuery(event.target.value)} placeholder="按 L3 编码或名称搜索" className="w-full rounded-xl border border-border-default bg-bg-elevated py-2 pl-9 pr-3 text-sm text-text-primary placeholder:text-text-muted" />
      </div>

      <div className="space-y-2">
        {filtered.map(model => (
          <details key={model.l3_code} open={expanded === model.l3_code} onToggle={event => setExpanded(event.currentTarget.open ? model.l3_code : null)} className="rounded-lg border border-border-default bg-bg-elevated">
            <summary className="flex cursor-pointer flex-wrap items-center gap-3 px-4 py-3">
              <span className="font-mono text-xs text-accent-primary-light">{model.l3_code}</span>
              <span className="text-sm font-medium text-text-primary">{model.l3_name}</span>
              <span className={`ml-auto rounded-full px-2.5 py-1 text-[11px] font-medium ${model.business_evidence_l4_count > 0 ? 'bg-emerald-400/10 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                {model.business_evidence_l4_count > 0 ? `${model.business_evidence_l4_count}/${model.l4_count} 个L4已定位业务表` : '未评估'}
              </span>
            </summary>
            {expanded === model.l3_code && (
              <div className="border-t border-border-default">
                <L3EvidenceDetail l3Code={model.l3_code} />
              </div>
            )}
          </details>
        ))}
      </div>
    </div>
  )
}
