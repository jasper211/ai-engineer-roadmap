import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { Database, LoaderCircle, Search, Target } from 'lucide-react'
import { loadModelIndex, loadL3Model, type ModelIndex, type L3Model } from '../lib/l3Models'
import { loadScenarioIndex, loadScenario, type ScenarioIndex, type BusinessScenario } from '../lib/businessScenarios'

const EVIDENCE_TYPE_INFO: Record<string, { label: string; tone: string }> = {
  output: { label: '产出证据', tone: 'text-emerald-700' },
  rule: { label: '规则证据', tone: 'text-indigo-700' },
  workflow: { label: '流程状态证据', tone: 'text-amber-700' },
  audit: { label: '追溯证据', tone: 'text-slate-600' },
}

const STATE_INFO: Record<string, { label: string; tone: string }> = {
  A: { label: 'A·有表有数据(任务真实在跑)', tone: 'bg-emerald-400/10 text-emerald-700' },
  B: { label: 'B·有表没数据(未标准化)', tone: 'bg-amber-400/10 text-amber-700' },
  C: { label: 'C·应有而无表(数据空白)', tone: 'bg-rose-50 text-rose-700 border border-dashed border-rose-300' },
}

function ScenarioCard({ file }: { file: string }) {
  const [scenario, setScenario] = useState<BusinessScenario | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    loadScenario(file).then(setScenario).catch(err => setError(err.message))
  }, [file])

  if (error) return <p className="p-3 text-xs text-accent-danger">{error}</p>
  if (!scenario) return <p className="p-3 text-xs text-text-muted">加载中…</p>

  return (
    <div className="space-y-4 p-4">
      <div>
        <p className="text-xs font-semibold text-text-primary">场景定义</p>
        <p className="mt-1 text-sm leading-6 text-text-secondary">{scenario.definition}</p>
        {scenario.definition_note && <p className="mt-1 text-[11px] text-amber-700">{scenario.definition_note}</p>}
        <p className="mt-1 text-[10px] text-text-muted">提出人：{scenario.raised_by} · {scenario.raised_at}</p>
      </div>

      <div className="space-y-3">
        {scenario.components.map(component => (
          <div key={component.component_name} className="rounded-lg border border-border-default bg-bg-surface p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-semibold text-text-primary">{component.component_name}</p>
              <span className={`rounded-full px-2.5 py-1 text-[10px] font-medium ${STATE_INFO[component.state]?.tone}`}>{STATE_INFO[component.state]?.label ?? component.state}</span>
            </div>
            {component.kpi_refs.length > 0 && (
              <p className="mt-2 text-[11px] text-indigo-700">关联KPI：{component.kpi_refs.join('、')}{component.kpi_note ? ` · ${component.kpi_note}` : ''}</p>
            )}
            {component.l3_trace.length > 0 && (
              <div className="mt-2 space-y-1">
                {component.l3_trace.map(trace => (
                  <p key={trace.l3_code} className="text-[10px] leading-4 text-text-secondary">
                    <span className="font-mono text-accent-primary-light">{trace.l3_code}</span>
                    {' '}（{trace.in_current_db ? `在库${trace.gate_a ? `·Gate A=${trace.gate_a}` : ''}` : '不在当前DB'}）· {trace.note}
                  </p>
                ))}
              </div>
            )}
            {component.business_evidence.length > 0 && (
              <div className="mt-2 space-y-1">
                {component.business_evidence.map(evidence => (
                  <p key={`${evidence.schema}.${evidence.table}`} className="text-[10px] leading-4 text-text-secondary">
                    <span className="font-mono">{evidence.schema}.{evidence.table}</span>（{evidence.row_count}行）· {evidence.note}
                  </p>
                ))}
              </div>
            )}
            <p className="mt-2 text-[11px] leading-5 text-text-secondary"><b>结论：</b>{component.conclusion}</p>
          </div>
        ))}
      </div>

      <div className="rounded-lg border border-indigo-200 bg-indigo-50/70 p-3">
        <p className="text-xs font-semibold text-indigo-800">综合结论</p>
        <p className="mt-1 text-[11px] leading-5 text-text-secondary">{scenario.overall_conclusion}</p>
        {scenario.next_steps.length > 0 && (
          <>
            <p className="mt-2 text-xs font-semibold text-indigo-800">下一步</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11px] leading-5 text-text-secondary">
              {scenario.next_steps.map((step, index) => <li key={index}>{step}</li>)}
            </ul>
          </>
        )}
      </div>
    </div>
  )
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
  const [scenarioIndex, setScenarioIndex] = useState<ScenarioIndex | null>(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [expanded, setExpanded] = useState<string | null>(searchParams.get('l3'))
  const [expandedScenario, setExpandedScenario] = useState<string | null>(null)

  useEffect(() => {
    loadModelIndex().then(setData).catch(err => setError(err.message))
    loadScenarioIndex().then(setScenarioIndex).catch(() => setScenarioIndex({ schema_version: '', scenarios: [] }))
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
        <h1 className="mt-2 font-heading text-3xl font-bold">真实工作场景，今天能不能被数据支撑？</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">
          两个并行入口：<b>①场景分析</b>——从真实业务问题（如"P&L定期核算"）往下拆解成数据组成项，
          追溯到L3/L4/KPI/表，判断今天能不能端到端产出，卡在哪段；场景随真实问题产生，不预先穷举。
          <b>②系统性覆盖扫描</b>——从L4/价值节点结构往上扫，逐个L3核实122张业务数据仓库表（public/comm_sandbox/fin_sandbox）
          有没有对应支撑，作为兜底层，防止没人恰好问到的角落被漏掉。两者共用同一套三态判断
          （A有表有数据·任务真实在跑 / B有表没数据·未标准化 / C应有而无表·数据空白）。
        </p>
      </div>

      <section>
        <div className="flex items-center gap-2 text-sm font-semibold text-text-primary"><Target className="h-4 w-4 text-accent-primary-light" /> 入口① 场景分析</div>
        <div className="mt-3 space-y-2">
          {(scenarioIndex?.scenarios.length ?? 0) === 0 ? (
            <p className="panel p-4 text-xs text-text-muted">暂无场景记录——场景随真实业务问题产生，不预先穷举。</p>
          ) : (
            scenarioIndex!.scenarios.map(scenario => (
              <details
                key={scenario.scenario_id}
                open={expandedScenario === scenario.scenario_id}
                onToggle={event => setExpandedScenario(event.currentTarget.open ? scenario.scenario_id : null)}
                className="rounded-lg border border-border-default bg-bg-elevated"
              >
                <summary className="flex cursor-pointer flex-wrap items-center gap-3 px-4 py-3">
                  <span className="text-sm font-medium text-text-primary">{scenario.scenario_name}</span>
                  <span className="text-[10px] text-text-muted">提出人：{scenario.raised_by}</span>
                  <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${scenario.status === 'CONFIRMED' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}`}>
                    {scenario.status === 'CONFIRMED' ? '已确认' : '草稿'}
                  </span>
                  <span className="ml-auto flex gap-1.5 text-[10px]">
                    {Object.entries(scenario.state_counts).map(([state, count]) => (
                      <span key={state} className={`rounded-full px-2 py-0.5 font-medium ${STATE_INFO[state]?.tone ?? 'bg-slate-100 text-slate-600'}`}>{state}×{count}</span>
                    ))}
                  </span>
                </summary>
                {expandedScenario === scenario.scenario_id && (
                  <div className="border-t border-border-default">
                    <ScenarioCard file={scenario.file} />
                  </div>
                )}
              </details>
            ))
          )}
        </div>
      </section>

      <section>
        <div className="flex items-center gap-2 text-sm font-semibold text-text-primary"><Database className="h-4 w-4 text-accent-primary-light" /> 入口② 系统性覆盖扫描</div>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <div className="panel p-4"><p className="eyebrow">已评估L3</p><p className="mt-2 metric-value">{evaluated.length}/{data.models.length}</p></div>
          <div className="panel p-4"><p className="eyebrow">已定位业务表的L4</p><p className="mt-2 metric-value">{totalL4Covered}</p></div>
          <div className="panel p-4"><p className="eyebrow">业务数据仓库表总数</p><p className="mt-2 metric-value">122</p><p className="mt-1 text-[11px] text-text-muted">public 75 · comm_sandbox 24 · fin_sandbox 5 · process_analytics 18（见"数据库现状"）</p></div>
        </div>

        <div className="relative mt-3 max-w-md">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
          <input value={query} onChange={event => setQuery(event.target.value)} placeholder="按 L3 编码或名称搜索" className="w-full rounded-xl border border-border-default bg-bg-elevated py-2 pl-9 pr-3 text-sm text-text-primary placeholder:text-text-muted" />
        </div>

        <div className="mt-3 space-y-2">
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
      </section>
    </div>
  )
}
