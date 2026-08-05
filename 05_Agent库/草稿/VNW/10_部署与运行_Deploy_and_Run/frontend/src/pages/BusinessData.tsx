import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { Database, LoaderCircle, Lock, Search, Target } from 'lucide-react'
import { loadScenarioIndex, loadScenario, type ScenarioIndex, type BusinessScenario } from '../lib/businessScenarios'
import { loadTableAnalysis, type TableAnalysis, type TableAnalysisEntry } from '../lib/tableAnalysis'

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

const HEALTH_TONE: Record<string, string> = {
  '未开始录入': 'bg-slate-100 text-slate-500',
  '试点阶段(个位数记录)': 'bg-amber-400/10 text-amber-700',
  '小规模在跑': 'bg-sky-400/10 text-sky-700',
  '规模化在跑': 'bg-emerald-400/10 text-emerald-700',
}

function BlockedLayer({ title, layer }: { title: string; layer: { status: string; goal: string; required_inputs: string[]; reason: string } }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50/60 p-3">
      <div className="flex items-center gap-2">
        <Lock className="h-3.5 w-3.5 text-slate-400" />
        <p className="text-xs font-semibold text-slate-500">{title} · <span className="font-mono">BLOCKED</span></p>
      </div>
      <p className="mt-1.5 text-[11px] leading-5 text-text-secondary"><b>分析目标：</b>{layer.goal}</p>
      <p className="mt-1 text-[11px] leading-5 text-text-secondary"><b>卡在：</b>{layer.reason}</p>
      <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[10px] leading-4 text-slate-500">
        {layer.required_inputs.map((input, index) => <li key={index}>{input}</li>)}
      </ul>
    </div>
  )
}

function TableFiveLayerDetail({ entry }: { entry: TableAnalysisEntry }) {
  return (
    <div className="space-y-2 p-3">
      <div className="rounded-lg border border-border-default bg-bg-surface p-3">
        <p className="text-[11px] font-semibold text-text-primary">L1 描述层</p>
        <p className="mt-1 text-[11px] leading-5 text-text-secondary">{entry.layer1.fact_statement}</p>
      </div>

      <div className="rounded-lg border border-border-default bg-bg-surface p-3">
        <p className="text-[11px] font-semibold text-text-primary">L2 诊断层</p>
        {entry.layer2.related_l3_l4.length > 0 ? (
          <div className="mt-1.5 space-y-1">
            {entry.layer2.related_l3_l4.map(rel => (
              <p key={`${rel.l3_code}-${rel.l4_code}`} className="text-[10px] leading-4 text-text-secondary">
                <span className="font-mono text-accent-primary-light">{rel.l3_code}</span> {rel.l3_name} → <span className="font-mono">{rel.l4_code}</span> {rel.l4_name}
              </p>
            ))}
            {entry.layer2.positions.length > 0 && (
              <p className="text-[10px] text-text-muted">负责岗位：{entry.layer2.positions.join('、')}</p>
            )}
          </div>
        ) : (
          <p className="mt-1 text-[10px] text-text-muted">{entry.layer2.status}</p>
        )}
        <span className={`mt-2 inline-block rounded-full px-2 py-0.5 text-[10px] font-medium ${HEALTH_TONE[entry.layer2.data_health] ?? 'bg-slate-100 text-slate-500'}`}>{entry.layer2.data_health}</span>
      </div>

      <BlockedLayer title="L3 归因层" layer={entry.layer3} />
      <BlockedLayer title="L4 预测层" layer={entry.layer4} />

      <div className="rounded-lg border border-indigo-200 bg-indigo-50/70 p-3">
        <p className="text-[11px] font-semibold text-indigo-800">L5 决策层 · {entry.layer5.status === 'PRELIMINARY' ? '初步判断' : entry.layer5.status === 'CONFIRMED' ? '已确认' : '暂无依据'}</p>
        <p className="mt-1 text-[11px] leading-5 text-text-secondary">{entry.layer5.note}</p>
      </div>
    </div>
  )
}

export default function BusinessData() {
  const [searchParams] = useSearchParams()
  const [scenarioIndex, setScenarioIndex] = useState<ScenarioIndex | null>(null)
  const [tableAnalysis, setTableAnalysis] = useState<TableAnalysis | null>(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState(searchParams.get('l3') ?? '')
  const [expandedTable, setExpandedTable] = useState<string | null>(null)
  const [expandedScenario, setExpandedScenario] = useState<string | null>(null)

  useEffect(() => {
    loadScenarioIndex().then(setScenarioIndex).catch(() => setScenarioIndex({ schema_version: '', scenarios: [] }))
    loadTableAnalysis().then(setTableAnalysis).catch(err => setError(err.message))
  }, [])

  const relatedCount = useMemo(() => tableAnalysis?.tables.filter(t => t.layer2.related_l3_l4.length > 0).length ?? 0, [tableAnalysis])
  const hasDataCount = useMemo(() => tableAnalysis?.tables.filter(t => t.layer1.has_data).length ?? 0, [tableAnalysis])

  const filteredTables = useMemo(() => {
    if (!tableAnalysis) return []
    const q = query.toLowerCase()
    return tableAnalysis.tables
      .filter(t => !q || `${t.schema}.${t.table}`.toLowerCase().includes(q) || t.layer2.related_l3_l4.some(rel => rel.l3_code.toLowerCase().includes(q)))
      .sort((a, b) => b.layer2.related_l3_l4.length - a.layer2.related_l3_l4.length)
  }, [tableAnalysis, query])

  if (error) return <div className="panel p-5 text-sm text-accent-danger">{error}</div>
  if (!tableAnalysis) return <div className="flex min-h-64 items-center justify-center text-text-muted"><LoaderCircle className="mr-2 h-5 w-5 animate-spin" />正在读取业务数据分析</div>

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-xs text-accent-primary-light"><Database className="h-4 w-4" /> 业务数据分析 · 新接入输入源</div>
        <h1 className="mt-2 font-heading text-3xl font-bold">真实工作场景，今天能不能被数据支撑？</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">
          两个并行入口：<b>①场景分析</b>——从真实业务问题（如"P&L定期核算"）往下拆解成数据组成项，
          追溯到L3/L4/KPI/表，判断今天能不能端到端产出，卡在哪段；场景随真实问题产生，不预先穷举。
          <b>②系统性覆盖扫描</b>——以104张业务数据表（public/comm_sandbox/fin_sandbox，不含process_analytics）
          为锚点逐张五层展开：L1描述层→L2诊断层（关联哪些L3/L4、谁负责、数据录入健康度）→L3归因层→
          L4预测层→L5决策层，作为兜底层防止没人恰好问到的角落被漏掉。L3/L4两层今天全部标注BLOCKED——
          不是没做，是核查后发现底层输入（任务耗时/错误率、人力成本单价）真实不存在，如实呈现缺口，
          不做代理指标替代，等输入产生后再激活。
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
        <div className="flex items-center gap-2 text-sm font-semibold text-text-primary"><Database className="h-4 w-4 text-accent-primary-light" /> 入口② 系统性覆盖扫描 · 以104张业务数据表为锚点的五层分析</div>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <div className="panel p-4"><p className="eyebrow">已定位L3/L4关联的表</p><p className="mt-2 metric-value">{relatedCount}/{tableAnalysis.tables.length}</p></div>
          <div className="panel p-4"><p className="eyebrow">有真实数据的表</p><p className="mt-2 metric-value">{hasDataCount}/{tableAnalysis.tables.length}</p></div>
          <div className="panel p-4"><p className="eyebrow">L3归因层/L4预测层</p><p className="mt-2 text-sm font-semibold text-slate-500">全部 BLOCKED</p><p className="mt-1 text-[11px] text-text-muted">fact_card/fact_agent(唯一含耗时/错误率字段的表)当前0行，无薪酬成本字段——分析维度保留，不做降级替代</p></div>
        </div>

        <div className="relative mt-3 max-w-md">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
          <input value={query} onChange={event => setQuery(event.target.value)} placeholder="按表名(schema.table)或L3编码搜索" className="w-full rounded-xl border border-border-default bg-bg-elevated py-2 pl-9 pr-3 text-sm text-text-primary placeholder:text-text-muted" />
        </div>

        <div className="mt-3 space-y-2">
          {filteredTables.map(entry => {
            const key = `${entry.schema}.${entry.table}`
            return (
              <details key={key} open={expandedTable === key} onToggle={event => setExpandedTable(event.currentTarget.open ? key : null)} className="rounded-lg border border-border-default bg-bg-elevated">
                <summary className="flex cursor-pointer flex-wrap items-center gap-3 px-4 py-3">
                  <span className="font-mono text-xs text-accent-primary-light">{key}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${HEALTH_TONE[entry.layer2.data_health] ?? 'bg-slate-100 text-slate-500'}`}>{entry.layer2.data_health}</span>
                  <span className={`ml-auto rounded-full px-2.5 py-1 text-[11px] font-medium ${entry.layer2.related_l3_l4.length > 0 ? 'bg-emerald-400/10 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>
                    {entry.layer2.related_l3_l4.length > 0 ? `关联${entry.layer2.related_l3_l4.length}个L4` : '未定位关联'}
                  </span>
                </summary>
                {expandedTable === key && (
                  <div className="border-t border-border-default">
                    <TableFiveLayerDetail entry={entry} />
                  </div>
                )}
              </details>
            )
          })}
        </div>
      </section>
    </div>
  )
}
