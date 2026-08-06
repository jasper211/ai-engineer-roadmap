import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router'
import { ArrowRight, Compass, Database, LoaderCircle, Lock, Search, Sparkles, Target } from 'lucide-react'
import { loadScenarioIndex, loadScenario, loadScenarioAnalysis, type ScenarioIndex, type BusinessScenario, type ScenarioAnalysis } from '../lib/businessScenarios'
import { loadTableAnalysis, type TableAnalysis, type TableAnalysisEntry, type TaskClusterLabel } from '../lib/tableAnalysis'

const STATE_INFO: Record<string, { label: string; tone: string }> = {
  A: { label: 'A·有表有数据(任务真实在跑)', tone: 'bg-emerald-400/10 text-emerald-700' },
  B: { label: 'B·有表没数据(未标准化)', tone: 'bg-amber-400/10 text-amber-700' },
  C: { label: 'C·应有而无表(数据空白)', tone: 'bg-rose-50 text-rose-700 border border-dashed border-rose-300' },
}

function gateBadgeTone(status: string) {
  return status === 'PASS' ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-700' : 'border-amber-400/25 bg-amber-400/10 text-amber-700'
}

const GOVERNANCE_TONE: Record<string, string> = {
  DATA_GAP: 'border-amber-200 bg-amber-50 text-amber-800',
  PROCESS_MISSING: 'border-rose-200 bg-rose-50 text-rose-800',
  GATE_A_BLOCKED: 'border-rose-200 bg-rose-50 text-rose-800',
}

function AnalysisNote({ children }: { children: ReactNode }) {
  return <p className="mb-2 text-[10px] italic leading-4 text-text-muted">{children}</p>
}

function ScenarioCard({ file }: { file: string }) {
  const [scenario, setScenario] = useState<BusinessScenario | null>(null)
  const [analysis, setAnalysis] = useState<ScenarioAnalysis | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    loadScenario(file).then(setScenario).catch(err => setError(err.message))
  }, [file])

  useEffect(() => {
    if (!scenario) return
    loadScenarioAnalysis(scenario.scenario_id).then(setAnalysis).catch(() => setAnalysis(null))
  }, [scenario])

  if (error) return <p className="p-3 text-xs text-accent-danger">{error}</p>
  if (!scenario) return <p className="p-3 text-xs text-text-muted">加载中…</p>

  return (
    <div className="space-y-4 p-4">
      <div className="rounded-lg border border-indigo-200 bg-indigo-50/60 p-3">
        <p className="text-xs font-semibold text-indigo-800">目标</p>
        <p className="mt-1 text-[11px] leading-5 text-text-secondary">
          这不是为了证明VNW这套系统本身建得怎么样——是为了把公司/部门真正关心的问题讲清楚：
          "{scenario.scenario_name}"这件事，今天到底能不能做出来、卡在哪、谁该做什么去解决。
          Gate、MODEL_DRAFT这些是我们内部工作用的标注，不是给业务负责人看的重点，
          业务负责人只需要看结论和行动项。
        </p>
        <p className="mt-2 text-xs font-semibold text-indigo-800">框架逻辑</p>
        <p className="mt-1 text-[11px] leading-5 text-text-secondary">
          先把这个业务问题拆解成可追溯的组成项，看今天有没有真实数据支撑（数据现状）；
          对牵涉到的流程，查它现在处于什么建模阶段（流程现状）；把两边暴露出的缺口整理成
          需要谁来处理的清单（数据治理→任务清单）；最后看这些缺口有没有已经在做的流程优化能覆盖，
          没有就反馈去补流程模型的输入材料、重新分析（流程优化）。
        </p>
      </div>

      <div>
        <AnalysisNote>场景需求：从真实业务问题出发拆解出的组成项定义，人工authoring，不是模板穷举出来的。</AnalysisNote>
        <p className="text-xs font-semibold text-text-primary">场景定义</p>
        <p className="mt-1 text-sm leading-6 text-text-secondary">{scenario.definition}</p>
        {scenario.definition_note && <p className="mt-1 text-[11px] text-amber-700">{scenario.definition_note}</p>}
        <p className="mt-1 text-[10px] text-text-muted">提出人：{scenario.raised_by} · {scenario.raised_at}</p>
      </div>

      <div className="space-y-3">
        <AnalysisNote>数据现状：逐组成项追溯到真实业务数据表和关联L3，用行数/表结构判断今天是否有真实数据支撑（A/B/C三态），不是猜测。</AnalysisNote>
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

      <div className="rounded-lg border border-border-default bg-bg-surface p-3">
        <p className="text-xs font-semibold text-text-primary">流程现状</p>
        <AnalysisNote>把场景涉及的每个L3，去查model_snapshots里的真实Gate M/E/A状态——人工判断(manual_gate_a)和实时查询(live_gates)并列展示，不用后者静默覆盖前者。</AnalysisNote>
        {!analysis || analysis.process_status.length === 0 ? (
          <p className="mt-1 text-[11px] text-text-muted">待生成</p>
        ) : (
          <div className="mt-2 space-y-1.5">
            {analysis.process_status.map(ps => (
              <div key={ps.l3_code} className="flex flex-wrap items-center gap-2 text-[11px]">
                {ps.in_current_db ? (
                  <Link to={`/models/${ps.l3_code}`} className="font-mono text-accent-primary-light hover:underline">{ps.l3_code}</Link>
                ) : (
                  <span className="font-mono text-text-muted">{ps.l3_code}</span>
                )}
                <span className="text-text-secondary">{ps.l3_name ?? '不在当前DB'}</span>
                {ps.live_gates ? (
                  (['M', 'E', 'A'] as const).map(gate => (
                    <span key={gate} className={`rounded border px-1.5 py-0.5 font-mono text-[9px] ${gateBadgeTone(ps.live_gates![gate])}`}>{gate}·{ps.live_gates![gate]}</span>
                  ))
                ) : (
                  <span className="rounded border border-border-default px-1.5 py-0.5 text-[9px] text-text-muted">不在当前DB</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-lg border border-border-default bg-bg-surface p-3">
        <p className="text-xs font-semibold text-text-primary">数据治理</p>
        <AnalysisNote>两条机械规则：组成项状态B/C(有表没数据/应有无表)标数据缺口；关联L3不在当前DB或Gate A未过标流程建模缺口——判定语言复用入口②L5层同一套说法，不是另外发明的标准。</AnalysisNote>
        {!analysis || analysis.data_governance.length === 0 ? (
          <p className="mt-1 text-[11px] text-text-muted">当前无治理缺口</p>
        ) : (
          <div className="mt-2 space-y-1.5">
            {analysis.data_governance.map((item, index) => (
              <div key={index} className={`rounded border px-2 py-1.5 text-[11px] leading-4 ${GOVERNANCE_TONE[item.flag]}`}>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-mono text-[9px]">{item.flag}</span>
                  {item.component_name && <b>{item.component_name}</b>}{item.l3_code && <b className="font-mono">{item.l3_code}</b>}
                </div>
                <p className="mt-1">{item.reason}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-lg border border-border-default bg-bg-surface p-3">
        <p className="text-xs font-semibold text-text-primary">任务清单</p>
        <AnalysisNote>人工写的下一步(next_steps)和机械算出的治理缺口统一转成结构化任务，各自标注来源；优先级/负责人没有依据的字段不臆造。</AnalysisNote>
        {!analysis || analysis.task_list.length === 0 ? (
          <p className="mt-1 text-[11px] text-text-muted">待生成</p>
        ) : (
          <table className="mt-2 w-full text-[11px]">
            <tbody>
              {analysis.task_list.map(task => (
                <tr key={task.task_id} className="border-t border-border-default/60 align-top">
                  <td className="py-1.5 pr-2 font-mono text-[9px] text-text-muted">{task.task_id}</td>
                  <td className="py-1.5 pr-2"><span className="rounded bg-bg-elevated px-1.5 py-0.5 text-[9px] text-text-secondary">{task.type}</span></td>
                  <td className="py-1.5 pr-2 leading-4 text-text-secondary">{task.description}</td>
                  <td className="py-1.5 text-[9px] text-text-muted">{task.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="rounded-lg border border-border-default bg-bg-surface p-3">
        <p className="text-xs font-semibold text-text-primary">流程优化</p>
        <AnalysisNote>
          只对场景本身发现的建模缺口(Gate A未过)生成条目。这类缺口是"价值节点映射/熔断判定未完成"，
          和该L3已有的AI任务试点建议(decision_drafts)是两件不同层次的事，机械规则判断不出语义上是否覆盖，
          因此如实并列展示两边证据，不假装匹配——如果下面的AI任务建议里确实没有能解决这个缺口的，
          说明是本场景新发现的优化点，需要把发现补充进该L3的分析输入材料后重跑统一分析。
        </AnalysisNote>
        {!analysis || analysis.process_optimization.length === 0 ? (
          <p className="mt-1 text-[11px] text-text-muted">当前场景未发现需要流程优化的建模缺口</p>
        ) : (
          <div className="mt-2 space-y-2">
            {analysis.process_optimization.map(opt => (
              <div key={opt.l3_code} className="rounded border border-border-default bg-bg-elevated p-2">
                <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                  <Link to={`/models/${opt.l3_code}`} className="font-mono text-accent-primary-light hover:underline">{opt.l3_code}</Link>
                  <span className="text-text-secondary">{opt.l3_name}</span>
                </div>
                <p className="mt-1.5 text-[10px] leading-4 text-rose-800"><b>本场景发现：</b>{opt.scenario_finding}</p>
                {opt.existing_decision_drafts.length > 0 && (
                  <>
                    <p className="mt-1.5 text-[10px] font-medium text-text-secondary">该L3已有的AI任务试点建议 <span className="text-amber-700">MODEL_DRAFT</span></p>
                    <ul className="mt-0.5 space-y-0.5 pl-3 text-[10px] leading-4 text-text-secondary">
                      {opt.existing_decision_drafts.map((draft, index) => (
                        <li key={index} className="list-disc"><b>{draft.priority}</b> {draft.title}</li>
                      ))}
                    </ul>
                  </>
                )}
                <p className="mt-1.5 text-[10px] leading-4 text-indigo-700">{opt.conclusion}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

const QUADRANT_TONE: Record<string, string> = {
  q1: 'bg-emerald-400/10 text-emerald-700',
  q2: 'bg-amber-400/10 text-amber-700',
  q3: 'bg-sky-400/10 text-sky-700',
  q4: 'bg-slate-100 text-slate-500',
}

const HEALTH_TONE: Record<string, string> = {
  '未开始录入': 'bg-slate-100 text-slate-500',
  '试点阶段(个位数记录)': 'bg-amber-400/10 text-amber-700',
  '小规模在跑': 'bg-sky-400/10 text-sky-700',
  '规模化在跑': 'bg-emerald-400/10 text-emerald-700',
}

const LAYER_NOTES: Record<'L1' | 'L2' | 'L3' | 'L4' | 'L5', string> = {
  L1: '层说明：这张表的事实是什么——有没有数据、数据量多少，建立分析基线',
  L2: '层说明：现状分析——这张表关联哪些L3/L4、谁负责、数据录入健康度如何',
  L3: '层说明：根因分析——这张表的上下游血缘是谁(表名+中文)，基于血缘位置+表类型做任务特征聚类，识别数据加工环节的瓶颈',
  L4: '层说明：反向补全——基于血缘位置+所处L4+L3识别出的隐形任务，反向推断这张表背后可能存在的隐藏产出(此前未记录的交付物或过程产物)',
  L5: '层说明：该做什么——复用流程模型面板D的四象限语义给优先级参考，并给出两条机械判定轨道：数据治理优先 / 流程补全杠杆',
}

const TASK_CLUSTER_TONE: Record<TaskClusterLabel, string> = {
  源头采集型: 'bg-emerald-400/10 text-emerald-700',
  枢纽整合型: 'bg-rose-400/10 text-rose-700',
  终端消费型: 'bg-sky-400/10 text-sky-700',
  规则配置型: 'bg-violet-400/10 text-violet-700',
  直通转换型: 'bg-amber-400/10 text-amber-700',
  孤立支撑型: 'bg-slate-100 text-slate-500',
}

function BlockedLayer({ title, noteKey, reason }: { title: string; noteKey: 'L3' | 'L4'; reason?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50/60 p-3">
      <div className="flex items-center gap-2">
        <Lock className="h-3.5 w-3.5 text-slate-400" />
        <p className="text-xs font-semibold text-slate-500">{title} · <span className="font-mono">BLOCKED</span></p>
      </div>
      <p className="mt-1 text-[10px] italic leading-4 text-slate-400">{LAYER_NOTES[noteKey]}</p>
      {reason && <p className="mt-1.5 text-[11px] leading-5 text-text-secondary"><b>卡在：</b>{reason}</p>}
    </div>
  )
}

function ModelDraftBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-400/10 px-2 py-0.5 text-[10px] font-medium text-amber-700">
      <Sparkles className="h-2.5 w-2.5" /> AI生成草稿·待人工复核
    </span>
  )
}

function L3RootCauseLayer({ layer }: { layer: TableAnalysisEntry['layer3'] }) {
  if (layer.status === 'BLOCKED') return <BlockedLayer title="L3 根因分析层" noteKey="L3" reason={layer.reason} />
  return (
    <div className="rounded-lg border border-border-default bg-bg-surface p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] font-semibold text-text-primary">L3 根因分析层</p>
        <ModelDraftBadge />
      </div>
      <p className="mt-1 text-[10px] italic leading-4 text-text-muted">{LAYER_NOTES.L3}</p>

      {layer.task_cluster && (
        <span className={`mt-2 inline-block rounded-full px-2.5 py-1 text-[11px] font-medium ${TASK_CLUSTER_TONE[layer.task_cluster.label]}`}>
          任务聚类·{layer.task_cluster.label}
        </span>
      )}
      {layer.task_cluster && <p className="mt-1 text-[10px] leading-4 text-text-muted">{layer.task_cluster.rationale}</p>}

      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <div>
          <p className="text-[10px] font-semibold text-text-muted">上游（{layer.upstream.length}）</p>
          {layer.upstream.length === 0 ? (
            <p className="mt-1 text-[10px] text-slate-400">无真实上游</p>
          ) : (
            <ul className="mt-1 space-y-0.5">
              {layer.upstream.map((u, i) => (
                <li key={`${u.key}-${u.edge_type}-${i}`} className="text-[10px] leading-4 text-text-secondary">
                  <span className="font-mono text-accent-primary-light">{u.key}</span> {u.business_label}
                  <span className="ml-1 text-slate-400">({u.edge_type})</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <p className="text-[10px] font-semibold text-text-muted">下游（{layer.downstream.length}）</p>
          {layer.downstream.length === 0 ? (
            <p className="mt-1 text-[10px] text-slate-400">无真实下游</p>
          ) : (
            <ul className="mt-1 space-y-0.5">
              {layer.downstream.map((d, i) => (
                <li key={`${d.key}-${d.edge_type}-${i}`} className="text-[10px] leading-4 text-text-secondary">
                  <span className="font-mono text-accent-primary-light">{d.key}</span> {d.business_label}
                  <span className="ml-1 text-slate-400">({d.edge_type})</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}

function L4ReverseCompletionLayer({ layer }: { layer: TableAnalysisEntry['layer4'] }) {
  if (layer.status === 'BLOCKED') return <BlockedLayer title="L4 反向补全层" noteKey="L4" reason={layer.reason} />
  return (
    <div className="rounded-lg border border-border-default bg-bg-surface p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] font-semibold text-text-primary">L4 反向补全层</p>
        <ModelDraftBadge />
      </div>
      <p className="mt-1 text-[10px] italic leading-4 text-text-muted">{LAYER_NOTES.L4}</p>
      {layer.hidden_deliverables.length === 0 ? (
        <p className="mt-1.5 text-[10px] text-slate-400">该表加工模式与已记录交付物一致，未发现缺口</p>
      ) : (
        <div className="mt-2 space-y-1.5">
          {layer.hidden_deliverables.map((hd, i) => (
            <div key={i} className="rounded-md border border-dashed border-amber-300 bg-amber-50/60 p-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-mono text-[10px] text-accent-primary-light">{hd.l4_code}</span>
                <span className="text-[10px] text-text-secondary">{hd.l4_name}</span>
                <span className="rounded-full bg-amber-400/20 px-2 py-0.5 text-[10px] font-semibold text-amber-800">候选：{hd.candidate_name}</span>
              </div>
              <p className="mt-1 text-[10px] leading-4 text-text-muted">{hd.rationale}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function TableFiveLayerDetail({ entry }: { entry: TableAnalysisEntry }) {
  return (
    <div className="space-y-2 p-3">
      <div className="rounded-lg border border-indigo-200 bg-indigo-50/50 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-mono text-base font-bold text-text-primary">{entry.schema}.{entry.table}</p>
          <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-medium text-text-secondary">{entry.table_type}</span>
        </div>
        <p className="mt-1 text-sm text-text-secondary">{entry.business_label}</p>
        {entry.description && <p className="mt-1 text-[11px] leading-5 text-text-secondary">{entry.description}</p>}
        {!entry.description && <p className="mt-1 text-[11px] text-amber-700">业务含义待核实（与"数据库现状"页一致，尚未逐字段核实过）</p>}
      </div>

      <div className="rounded-lg border border-border-default bg-bg-surface p-3">
        <p className="text-[11px] font-semibold text-text-primary">L1 描述层</p>
        <p className="mt-1 text-[10px] italic leading-4 text-text-muted">{LAYER_NOTES.L1}</p>
        <p className="mt-1.5 text-[11px] leading-5 text-text-secondary">{entry.layer1.fact_statement}</p>
      </div>

      <div className="rounded-lg border border-border-default bg-bg-surface p-3">
        <p className="text-[11px] font-semibold text-text-primary">L2 诊断层</p>
        <p className="mt-1 text-[10px] italic leading-4 text-text-muted">{LAYER_NOTES.L2}</p>
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
        {entry.layer2.non_business && (
          <div className="mt-1.5 rounded-md border border-dashed border-slate-300 bg-slate-100/60 p-1.5">
            <p className="text-[10px] font-semibold text-slate-600">{entry.layer2.non_business.reason}</p>
          </div>
        )}
        {entry.layer2.shared_master_data && (
          <div className="mt-1.5 rounded-md border border-dashed border-cyan-300 bg-cyan-50/60 p-1.5">
            <p className="text-[10px] font-semibold text-cyan-800">{entry.layer2.shared_master_data.reason}</p>
          </div>
        )}
        {entry.layer2.utility_support && (
          <div className="mt-1.5 rounded-md border border-dashed border-violet-300 bg-violet-50/60 p-1.5">
            <p className="text-[10px] font-semibold text-violet-800">{entry.layer2.utility_support.reason}</p>
          </div>
        )}
        {entry.layer2.field_anchored && (
          <div className="mt-1.5 space-y-1 rounded-md border border-dashed border-sky-300 bg-sky-50/60 p-1.5">
            {entry.layer2.field_anchored.anchors.slice(0, 3).map((anchor, i) => (
              <p key={i} className="text-[10px] font-semibold text-sky-800">无L4关联，但字段"{anchor.field}"是{anchor.origin_tables.join('、')}的真实主键，且被{anchor.linked_tables.length}张表共用——非孤立</p>
            ))}
            {entry.layer2.field_anchored.anchors.length > 3 && <p className="text-[10px] text-sky-700">+{entry.layer2.field_anchored.anchors.length - 3} 个锚定字段…</p>}
          </div>
        )}
        <span className={`mt-2 inline-block rounded-full px-2 py-0.5 text-[10px] font-medium ${HEALTH_TONE[entry.layer2.data_health] ?? 'bg-slate-100 text-slate-500'}`}>{entry.layer2.data_health}</span>
      </div>

      <L3RootCauseLayer layer={entry.layer3} />
      <L4ReverseCompletionLayer layer={entry.layer4} />

      <div className="rounded-lg border border-indigo-200 bg-indigo-50/70 p-3">
        <p className="text-[11px] font-semibold text-indigo-800">L5 决策层 · {entry.layer5.status === 'PRELIMINARY' ? '初步判断' : entry.layer5.status === 'CONFIRMED' ? '已确认' : '暂无依据'}</p>
        <p className="mt-1 text-[10px] italic leading-4 text-indigo-400">{LAYER_NOTES.L5}</p>
        <p className="mt-1.5 text-[11px] leading-5 text-text-secondary">{entry.layer5.note}</p>
        {(entry.layer5.governance_track || entry.layer5.process_lever_track) && (
          <div className="mt-2 space-y-1.5">
            {entry.layer5.governance_track && (
              <div className="flex items-start gap-1.5 rounded-md border border-amber-300 bg-amber-50/70 p-2">
                <Compass className="mt-0.5 h-3 w-3 shrink-0 text-amber-700" />
                <p className="text-[10px] leading-4 text-amber-800"><b>轨道A·先立数据标准：</b>{entry.layer5.governance_track.reason}</p>
              </div>
            )}
            {entry.layer5.process_lever_track && (
              <div className="flex items-start gap-1.5 rounded-md border border-indigo-300 bg-indigo-100/60 p-2">
                <ArrowRight className="mt-0.5 h-3 w-3 shrink-0 text-indigo-700" />
                <p className="text-[10px] leading-4 text-indigo-800"><b>轨道B·可撬动流程补全：</b>{entry.layer5.process_lever_track.reason}</p>
              </div>
            )}
          </div>
        )}
        {entry.layer5.l4_quadrants.length > 0 && (
          <div className="mt-2 space-y-1.5">
            {entry.layer5.l4_quadrants.map(q => (
              <div key={q.l4_code} className="rounded-md border border-indigo-200/70 bg-white/60 p-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-mono text-[10px] text-accent-primary-light">{q.l4_code}</span>
                  <span className="text-[10px] text-text-secondary">{q.l4_name}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${QUADRANT_TONE[q.quadrant]}`}>{q.quadrant_label}</span>
                  {q.axis_conflict && <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-medium text-rose-700">双轴冲突</span>}
                  <span className="text-[10px] text-text-muted">{q.confidence === 'confirmed_basis' ? '依据已核实' : '依据为草稿'}</span>
                </div>
                <p className="mt-1 text-[10px] leading-4 text-text-muted">{q.rationale}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default function BusinessData() {
  const [searchParams] = useSearchParams()
  const [scenarioIndex, setScenarioIndex] = useState<ScenarioIndex | null>(null)
  const [tableAnalysis, setTableAnalysis] = useState<TableAnalysis | null>(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [expandedTable, setExpandedTable] = useState<string | null>(null)
  const [expandedScenario, setExpandedScenario] = useState<string | null>(null)
  const [schemaFilter, setSchemaFilter] = useState<'all' | string>('all')
  const [tableTypeFilter, setTableTypeFilter] = useState<'all' | string>('all')
  const [healthFilter, setHealthFilter] = useState<'all' | string>('all')
  const [relationFilter, setRelationFilter] = useState<'all' | 'related' | 'unrelated'>('all')
  const [l3Filter, setL3Filter] = useState<'all' | string>(searchParams.get('l3') ?? 'all')

  useEffect(() => {
    loadScenarioIndex().then(setScenarioIndex).catch(() => setScenarioIndex({ schema_version: '', scenarios: [] }))
    loadTableAnalysis().then(setTableAnalysis).catch(err => setError(err.message))
  }, [])

  const relatedCount = useMemo(() => tableAnalysis?.tables.filter(t => t.layer2.related_l3_l4.length > 0).length ?? 0, [tableAnalysis])
  const hasDataCount = useMemo(() => tableAnalysis?.tables.filter(t => t.layer1.has_data).length ?? 0, [tableAnalysis])
  const sharedMasterDataCount = useMemo(() => tableAnalysis?.tables.filter(t => t.layer2.shared_master_data).length ?? 0, [tableAnalysis])
  const utilitySupportCount = useMemo(() => tableAnalysis?.tables.filter(t => t.layer2.utility_support).length ?? 0, [tableAnalysis])
  const fieldAnchoredCount = useMemo(() => tableAnalysis?.tables.filter(t => t.layer2.field_anchored).length ?? 0, [tableAnalysis])
  const nonBusinessCount = useMemo(() => tableAnalysis?.tables.filter(t => t.layer2.non_business).length ?? 0, [tableAnalysis])
  const l3Coverage = tableAnalysis?.tables[0]?.layer2.analyzed_l3_coverage ?? { analyzed: 0, total: 0 }
  const hiddenDeliverableCount = useMemo(() => tableAnalysis?.tables.filter(t => t.layer4.hidden_deliverables.length > 0).length ?? 0, [tableAnalysis])
  const governanceFlaggedCount = useMemo(() => tableAnalysis?.tables.filter(t => t.layer5.governance_track?.flagged).length ?? 0, [tableAnalysis])
  const processLeverFlaggedCount = useMemo(() => tableAnalysis?.tables.filter(t => t.layer5.process_lever_track?.flagged).length ?? 0, [tableAnalysis])

  const schemas = useMemo(() => Array.from(new Set(tableAnalysis?.tables.map(t => t.schema) ?? [])).sort(), [tableAnalysis])
  const tableTypes = useMemo(() => Array.from(new Set(tableAnalysis?.tables.map(t => t.table_type) ?? [])).sort(), [tableAnalysis])
  const healthBuckets = ['未开始录入', '试点阶段(个位数记录)', '小规模在跑', '规模化在跑']

  const l3Options = useMemo(() => {
    const map = new Map<string, string>()
    tableAnalysis?.tables.forEach(t => t.layer2.related_l3_l4.forEach(rel => map.set(rel.l3_code, rel.l3_name)))
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b))
  }, [tableAnalysis])

  const filteredTables = useMemo(() => {
    if (!tableAnalysis) return []
    const q = query.toLowerCase()
    return tableAnalysis.tables
      .filter(t => schemaFilter === 'all' || t.schema === schemaFilter)
      .filter(t => tableTypeFilter === 'all' || t.table_type === tableTypeFilter)
      .filter(t => healthFilter === 'all' || t.layer2.data_health === healthFilter)
      .filter(t => relationFilter === 'all' || (relationFilter === 'related' ? t.layer2.related_l3_l4.length > 0 : t.layer2.related_l3_l4.length === 0))
      .filter(t => l3Filter === 'all' || t.layer2.related_l3_l4.some(rel => rel.l3_code === l3Filter))
      .filter(t => !q
        || `${t.schema}.${t.table}`.toLowerCase().includes(q)
        || t.business_label.toLowerCase().includes(q)
        || t.layer2.related_l3_l4.some(rel => rel.l3_code.toLowerCase().includes(q)))
      .sort((a, b) => b.layer2.related_l3_l4.length - a.layer2.related_l3_l4.length)
  }, [tableAnalysis, query, schemaFilter, tableTypeFilter, healthFilter, relationFilter, l3Filter])

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
          <b>②系统性覆盖扫描</b>——以当前{tableAnalysis.tables.length}张业务数据表（public/comm_sandbox/fin_sandbox，
          不含process_analytics；表数量随数据库真实变化，见下方"表数量"指标）为锚点逐张五层展开：
          L1描述层→L2诊断层（关联哪些L3/L4、谁负责、数据录入健康度）→L3根因分析层（基于真实数据血缘做表级
          上下游归因+任务特征聚类）→L4反向补全层（反推隐藏产出候选）→L5决策层（四象限优先级+数据治理/流程
          补全两条判定轨道），作为兜底层防止没人恰好问到的角落被漏掉。L3/L4两层由AI辅助推理生成，统一标注
          <span className="font-mono">MODEL_DRAFT</span>，复核在页面上进行；尚未纳入本轮血缘分析范围的表如实标注BLOCKED，不做代理指标替代。
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
        <div className="flex items-center gap-2 text-sm font-semibold text-text-primary"><Database className="h-4 w-4 text-accent-primary-light" /> 入口② 系统性覆盖扫描 · 以{tableAnalysis.tables.length}张业务数据表为锚点的五层分析</div>
        <div className="mt-3 grid gap-3 sm:grid-cols-4">
          <div className="panel p-4"><p className="eyebrow">已纳入匹配分析的L3</p><p className="mt-2 metric-value">{l3Coverage.analyzed}/{l3Coverage.total}</p><p className="mt-1 text-[11px] text-text-muted">其余L3尚未逐张核实，其表暂不计入"已核实无关联"</p></div>
          <div className="panel p-4"><p className="eyebrow">已定位L3/L4关联的表</p><p className="mt-2 metric-value">{relatedCount}/{tableAnalysis.tables.length}</p></div>
          <div className="panel p-4"><p className="eyebrow">共用主数据/维度表</p><p className="mt-2 metric-value text-cyan-600">{sharedMasterDataCount}</p><p className="mt-1 text-[11px] text-text-muted">血缘候选跨≥3个L3，不建议归入单一L4</p></div>
          <div className="panel p-4"><p className="eyebrow">工具/服务支撑</p><p className="mt-2 metric-value text-violet-600">{utilitySupportCount}</p><p className="mt-1 text-[11px] text-text-muted">业务方核实非断点，方法论对其天然失效</p></div>
          <div className="panel p-4"><p className="eyebrow">字段锚定(非孤立)</p><p className="mt-2 metric-value text-sky-600">{fieldAnchoredCount}</p><p className="mt-1 text-[11px] text-text-muted">无L4/血缘边，但有真实主键字段连回主链</p></div>
          <div className="panel p-4"><p className="eyebrow">系统表/非业务表</p><p className="mt-2 metric-value text-slate-500">{nonBusinessCount}</p><p className="mt-1 text-[11px] text-text-muted">已核实与保险业务无关，非"未分析"</p></div>
          <div className="panel p-4"><p className="eyebrow">有真实数据的表</p><p className="mt-2 metric-value">{hasDataCount}/{tableAnalysis.tables.length}</p></div>
          <div className="panel p-4"><p className="eyebrow">L4隐藏产出候选</p><p className="mt-2 metric-value text-amber-600">{hiddenDeliverableCount}</p><p className="mt-1 text-[11px] text-text-muted">AI根因分析(MODEL_DRAFT)反推出的可能未记录交付物</p></div>
          <div className="panel p-4"><p className="eyebrow">轨道A·建议先立数据标准</p><p className="mt-2 metric-value text-amber-600">{governanceFlaggedCount}</p><p className="mt-1 text-[11px] text-text-muted">枢纽整合型但暂无明确负责岗位</p></div>
          <div className="panel p-4"><p className="eyebrow">轨道B·可撬动流程补全</p><p className="mt-2 metric-value text-indigo-600">{processLeverFlaggedCount}</p><p className="mt-1 text-[11px] text-text-muted">数据证据可用于反推流程蓝图缺口</p></div>
        </div>

        <div className="mt-3 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] text-text-muted">Schema</span>
            <div className="flex flex-wrap gap-1 rounded-lg bg-bg-elevated p-1">
              <button onClick={() => setSchemaFilter('all')} className={`rounded-md px-2.5 py-1 text-[11px] transition-colors ${schemaFilter === 'all' ? 'bg-accent-primary text-white' : 'text-text-secondary hover:text-text-primary hover:bg-bg-surface'}`}>全部</button>
              {schemas.map(schema => (
                <button key={schema} onClick={() => setSchemaFilter(schema)} className={`rounded-md px-2.5 py-1 text-[11px] transition-colors ${schemaFilter === schema ? 'bg-accent-primary text-white' : 'text-text-secondary hover:text-text-primary hover:bg-bg-surface'}`}>{schema}</button>
              ))}
            </div>
            <span className="ml-2 text-[11px] text-text-muted">关联状态</span>
            <div className="flex flex-wrap gap-1 rounded-lg bg-bg-elevated p-1">
              {([['all', '全部'], ['related', '已关联L4'], ['unrelated', '未定位关联']] as const).map(([value, label]) => (
                <button key={value} onClick={() => setRelationFilter(value)} className={`rounded-md px-2.5 py-1 text-[11px] transition-colors ${relationFilter === value ? 'bg-accent-primary text-white' : 'text-text-secondary hover:text-text-primary hover:bg-bg-surface'}`}>{label}</button>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-1.5 text-[11px] text-text-muted">
              按L3筛选
              <select value={l3Filter} onChange={event => setL3Filter(event.target.value)} className="rounded-md border border-border-default bg-bg-elevated px-2 py-1 text-[11px] text-text-primary">
                <option value="all">全部</option>
                {l3Options.map(([code, name]) => <option key={code} value={code}>{code} · {name}</option>)}
              </select>
            </label>
            <label className="flex items-center gap-1.5 text-[11px] text-text-muted">
              表类型
              <select value={tableTypeFilter} onChange={event => setTableTypeFilter(event.target.value)} className="rounded-md border border-border-default bg-bg-elevated px-2 py-1 text-[11px] text-text-primary">
                <option value="all">全部</option>
                {tableTypes.map(type => <option key={type} value={type}>{type}</option>)}
              </select>
            </label>
            <label className="flex items-center gap-1.5 text-[11px] text-text-muted">
              数据健康度
              <select value={healthFilter} onChange={event => setHealthFilter(event.target.value)} className="rounded-md border border-border-default bg-bg-elevated px-2 py-1 text-[11px] text-text-primary">
                <option value="all">全部</option>
                {healthBuckets.map(bucket => <option key={bucket} value={bucket}>{bucket}</option>)}
              </select>
            </label>
            <span className="text-[11px] text-text-muted">共{filteredTables.length}张（{tableAnalysis.tables.length}张中）</span>
          </div>
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
            <input value={query} onChange={event => setQuery(event.target.value)} placeholder="按表名/中文含义/L3编码搜索" className="w-full rounded-xl border border-border-default bg-bg-elevated py-2 pl-9 pr-3 text-sm text-text-primary placeholder:text-text-muted" />
          </div>
        </div>

        <div className="mt-3 space-y-2">
          {filteredTables.map(entry => {
            const key = `${entry.schema}.${entry.table}`
            return (
              <details key={key} open={expandedTable === key} onToggle={event => setExpandedTable(event.currentTarget.open ? key : null)} className="rounded-lg border border-border-default bg-bg-elevated">
                <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-4 py-3">
                  <span className="font-mono text-sm font-bold text-text-primary">{key}</span>
                  <span className="rounded-full bg-bg-surface px-2 py-0.5 text-[10px] font-medium text-text-secondary">{entry.table_type}</span>
                  <span className="text-xs text-text-secondary">{entry.business_label}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${HEALTH_TONE[entry.layer2.data_health] ?? 'bg-slate-100 text-slate-500'}`}>{entry.layer2.data_health}</span>
                  <span className={`ml-auto rounded-full px-2.5 py-1 text-[11px] font-medium ${
                    entry.layer2.related_l3_l4.length > 0 ? 'bg-emerald-400/10 text-emerald-700'
                      : entry.layer2.non_business ? 'bg-slate-200 text-slate-600'
                        : entry.layer2.shared_master_data ? 'bg-cyan-400/10 text-cyan-700'
                          : entry.layer2.utility_support ? 'bg-violet-400/10 text-violet-700'
                            : entry.layer2.field_anchored ? 'bg-sky-400/10 text-sky-700'
                              : entry.layer2.analyzed_l3_coverage.analyzed >= entry.layer2.analyzed_l3_coverage.total ? 'bg-slate-100 text-slate-500'
                                : 'border border-dashed border-amber-300 bg-amber-400/10 text-amber-700'
                  }`}>
                    {entry.layer2.related_l3_l4.length > 0
                      ? `关联${entry.layer2.related_l3_l4.length}个L4`
                      : entry.layer2.non_business
                        ? '系统表/非业务表'
                        : entry.layer2.shared_master_data
                          ? `共用主数据·跨${entry.layer2.shared_master_data.l3_span_count}个L3`
                          : entry.layer2.utility_support
                            ? '工具/服务支撑'
                            : entry.layer2.field_anchored
                              ? '字段锚定(非孤立)'
                              : entry.layer2.analyzed_l3_coverage.analyzed >= entry.layer2.analyzed_l3_coverage.total ? '已核实无关联' : '未纳入分析范围'}
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
