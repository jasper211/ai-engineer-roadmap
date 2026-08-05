import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router'
import { AlertTriangle, ArrowRight, CheckCircle2, ChevronDown, ChevronUp, Database, GitBranch, LoaderCircle, Search, Star } from 'lucide-react'
import { loadDeliverableAudit, loadModelIndex, loadPendingSourceUpdate, type DeliverableAudit, type ModelIndex, type ModelIndexItem, type SourceUpdateReport } from '../lib/l3Models'

const scopeLabels: Record<string, string> = {
  blueprint: '流程蓝图', l4_delivery: 'L4与交付物', value_nodes: '价值节点',
  vn_l4_mapping: '价值节点-L4映射', l2_capability: 'L2能力', kpi: 'KPI',
  value_stream: '价值流', readiness: '建模准入', evidence: '证据注册表',
  l3_removed: 'L3已从源头移除',
}

function changeMeaning(change: SourceUpdateReport['changes'][number]) {
  if (change.status === 'ADDED') return {
    status: '源头新增',
    impact: '当前已发布前端尚无该L3；应用更新后会新增流程卡片，并按最新硬输入重新判定是否允许建模。',
    next: change.action === 'BLOCKED_INPUT' ? '先人工核实新增L3及编码，再应用事实更新；应用后进入待补清单，不运行模型。' : '核实新增L3及编码后应用事实更新，再进入统一分析队列。',
  }
  if (change.status === 'REMOVED') return {
    status: '源头移除',
    impact: '当前已发布前端仍暂时保留该L3；应用后将从当前模型清单移除，既有分析包只保留审计记录。',
    next: '先确认是正式删除、改名还是编码迁移；确认后再应用，避免误删现有模型入口。',
  }
  if (change.action === 'REANALYSIS_REQUIRED') return {
    status: '既有L3输入变化',
    impact: `应用后事实面板 ${change.affected_panels.join('/')} 将更新，既有模型分析会标记过期，Demo结论不能继续作为当前结论。`,
    next: '先核实变化来源，再应用事实更新；随后按影响范围重跑统一模型并完成抽检。',
  }
  if (change.action === 'BLOCKED_INPUT') return {
    status: '输入变化后不满足准入',
    impact: `应用后面板 ${change.affected_panels.join('/')} 更新，该L3转入待补清单，不生成流程模型。`,
    next: '核实缺少的蓝图、L4或D1-D6，并定位源头负责人补充；补齐后等待下一轮扫描。',
  }
  return {
    status: '事实变化',
    impact: `应用后面板 ${change.affected_panels.join('/')} 将更新；当前尚未发布的扫描结果不会直接改动Demo。`,
    next: '人工核实来源和变化范围后应用事实更新；若分析输入哈希变化，再安排模型重跑。',
  }
}

function Gate({ name, status }: { name: string; status: string }) {
  const pass = status === 'PASS'
  const conditional = status === 'CONDITIONAL'
  return (
    <span className={`rounded-md border px-2 py-1 font-mono text-[11px] ${pass ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-700' : conditional ? 'border-sky-400/25 bg-sky-400/10 text-sky-700' : 'border-amber-400/25 bg-amber-400/10 text-amber-700'}`}>
      {name} · {status}
    </span>
  )
}

function ModelCard({ model, quality }: { model: ModelIndexItem; quality?: { mixed: number; repeated: number } }) {
  const full = model.classification === 'FULL_MODEL'
  const limited = model.classification === 'LIMITED_MODEL'
  const productionLabels: Record<ModelIndexItem['production_status'], { label: string; tone: string }> = {
    READY_TO_RUN: { label: '待运行统一分析', tone: 'bg-blue-50 text-blue-700' },
    RUN_PREPARED: { label: '运行包已准备', tone: 'bg-cyan-50 text-cyan-700' },
    ANALYSIS_CURRENT: { label: '分析与当前输入一致', tone: 'bg-emerald-50 text-emerald-700' },
    ANALYSIS_INPUT_CHANGED: { label: '输入已变化·待重跑', tone: 'bg-rose-50 text-rose-700' },
    REVIEWED_BASELINE: { label: '历史评审基线', tone: 'bg-violet-50 text-violet-700' },
    BLOCKED_INPUT: { label: '输入未达准入', tone: 'bg-slate-100 text-slate-600' },
  }
  const production = productionLabels[model.production_status]
  const content = (
    <>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs text-accent-primary-light">{model.l3_code}</p>
          <h2 className="mt-1 text-base font-semibold text-text-primary">{model.l3_name}</h2>
          {model.l2_capabilities.length > 0 && (
            <p className="mt-1 text-[11px] text-text-muted">{model.l2_capabilities.join('、')}</p>
          )}
        </div>
        <div className="flex flex-col items-end gap-1.5">
          {model.has_demo && (
            <span className="flex items-center gap-1 rounded-full bg-violet-400/10 px-2.5 py-1 text-[11px] font-medium text-violet-700">
              <Star className="h-3 w-3" /> 完整 Demo
            </span>
          )}
          <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${full ? 'bg-emerald-400/10 text-emerald-700' : limited ? 'bg-sky-400/10 text-sky-700' : 'bg-amber-400/10 text-amber-700'}`}>
            {full ? '可生成完整模型' : limited ? '可生成带缺口模型' : '待补后生成'}
          </span>
          <span className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${production.tone}`}>{production.label}</span>
          {Boolean(quality && quality.mixed > 0) && <span className="rounded-full bg-rose-50 px-2.5 py-1 text-[11px] font-medium text-rose-700">交付物待治理 {quality?.mixed}</span>}
          {Boolean(quality && quality.repeated > 0) && <span className="rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-medium text-amber-700">重复值待核实 {quality?.repeated}</span>}
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Gate name="M" status={model.gates.M} />
        <Gate name="E" status={model.gates.E} />
        <Gate name="A" status={model.gates.A} />
      </div>
      <div className="mt-4 flex items-center justify-between border-t border-border-default pt-3 text-xs text-text-muted">
        <span>{model.l4_count} 个 L4 · {model.value_node_count} 个价值节点 · 蓝图 {model.blueprint_version || '缺失'}</span>
        {model.model_generation_allowed ? <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" /> : <span>模型入口已关闭</span>}
      </div>
      <p className="mt-2 text-[11px] text-text-muted">
        SOP {model.readiness_coverage.sop_count}份 · 规则 {model.readiness_coverage.rule_count}条 ·
        任务覆盖 {model.readiness_coverage.task.covered}/{model.readiness_coverage.task.total}
      </p>
      {model.value_streams.length > 0 && (
        <p className="mt-2 flex flex-wrap gap-1.5">
          {model.value_streams.map(vs => (
            <span key={`${vs.vs_code}-${vs.stage_code}`} className="rounded-full bg-teal-400/10 px-2 py-0.5 text-[11px] font-medium text-teal-700">
              {vs.vs_name} · {vs.stage_name}
            </span>
          ))}
        </p>
      )}
      {model.kpis.length > 0 && (
        <p className="mt-2 flex flex-wrap gap-1.5">
          {model.kpis.map((kpi, index) => (
            <span
              key={`${kpi.kpi_name}-${index}`}
              className={
                kpi.source_type === 'definition'
                  ? 'rounded-full bg-amber-400/10 px-2 py-0.5 text-[11px] font-medium text-amber-800'
                  : 'rounded-full border border-dashed border-rose-300 bg-rose-50 px-2 py-0.5 text-[11px] font-medium text-rose-700'
              }
            >
              {kpi.kpi_name}
            </span>
          ))}
        </p>
      )}
      {!full && model.gap_reasons.length > 0 && (
        <p className="mt-2 line-clamp-2 text-xs text-amber-800/80">首要缺口：{model.gap_reasons[0]}</p>
      )}
      <p className="mt-2 text-right text-[10px] text-text-muted">
        {model.analysis_run_at
          ? `最新demo跑通于 ${new Date(model.analysis_run_at).toLocaleString('zh-CN')}`
          : '未启动分析'}
      </p>
    </>
  )
  return model.model_generation_allowed
    ? <Link to={`/models/${model.l3_code}`} className="group panel block p-5 transition hover:border-border-hover hover:-translate-y-0.5">{content}</Link>
    : <div className="panel p-5 opacity-90">{content}</div>
}

export default function L3Models() {
  const [data, setData] = useState<ModelIndex | null>(null)
  const [audit, setAudit] = useState<DeliverableAudit | null>(null)
  const [pendingUpdate, setPendingUpdate] = useState<SourceUpdateReport | null>(null)
  const [error, setError] = useState('')
  const [showUpdateDetails, setShowUpdateDetails] = useState(false)
  const [view, setView] = useState<'all' | 'ready' | 'evaluable' | 'missing' | 'demo' | 'quality'>('all')
  const [query, setQuery] = useState('')
  const [vsFilter, setVsFilter] = useState('all')

  useEffect(() => {
    Promise.all([loadModelIndex(), loadDeliverableAudit(), loadPendingSourceUpdate()])
      .then(([modelData, auditData, sourceUpdate]) => { setData(modelData); setAudit(auditData); setPendingUpdate(sourceUpdate) })
      .catch(error => setError(error.message))
  }, [])

  const qualityByL3 = useMemo(() => {
    const result: Record<string, { mixed: number; repeated: number }> = {}
    for (const finding of audit?.findings ?? []) {
      const row = result[finding.l3_code] ?? { mixed: 0, repeated: 0 }
      if (finding.issue_type === 'MIXED_CONTENT') row.mixed += 1
      if (finding.issue_type === 'REPEATED_VALUE') row.repeated += 1
      result[finding.l3_code] = row
    }
    return result
  }, [audit])

  const groups = useMemo(() => ({
    all: data?.models ?? [],
    ready: data?.models.filter(item => item.classification === 'FULL_MODEL') ?? [],
    evaluable: data?.models.filter(item => item.classification === 'LIMITED_MODEL') ?? [],
    missing: data?.models.filter(item => item.classification === 'WAITING_INPUT') ?? [],
    demo: data?.models.filter(item => item.has_demo) ?? [],
    quality: data?.models.filter(item => Boolean(qualityByL3[item.l3_code])) ?? [],
  }), [data, qualityByL3])

  const valueStreams = useMemo(() => {
    const byCode = new Map<string, { vs_code: string; vs_name: string; count: number }>()
    let unmapped = 0
    for (const model of data?.models ?? []) {
      if (model.value_streams.length === 0) unmapped += 1
      for (const vs of model.value_streams) {
        const existing = byCode.get(vs.vs_code)
        if (existing) existing.count += 1
        else byCode.set(vs.vs_code, { vs_code: vs.vs_code, vs_name: vs.vs_name, count: 1 })
      }
    }
    return { list: [...byCode.values()].sort((a, b) => a.vs_code.localeCompare(b.vs_code)), unmapped }
  }, [data])

  if (error) return <div className="panel p-5 text-sm text-accent-danger">{error}</div>
  if (!data) return <div className="flex min-h-64 items-center justify-center text-text-muted"><LoaderCircle className="mr-2 h-5 w-5 animate-spin" />正在读取真实模型快照</div>

  const current = groups[view]
    .filter(model => `${model.l3_code}${model.l3_name}`.toLowerCase().includes(query.toLowerCase()))
    .filter(model => vsFilter === 'all' || (vsFilter === 'unmapped' ? model.value_streams.length === 0 : model.value_streams.some(vs => vs.vs_code === vsFilter)))
  const parsedCount = data.models.filter(model => model.blueprint_structure_status === 'PARSED').length
  const featuredDemo = groups.demo[0]
  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-xs text-accent-primary-light"><GitBranch className="h-4 w-4" /> L3 流程模型系统 · V1</div>
        <h1 className="mt-2 font-heading text-3xl font-bold">哪些流程可以进入 AI 化设计？</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">
          先看权威数据是否足以支撑模型。满足标准的进入模型评审；不满足的进入待补清单，不用推测填空。
        </p>
      </div>

      {(data.source_update_summary || pendingUpdate) && (
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
          <div className="border-b border-slate-100 px-5 py-4">
            <p className="text-sm font-semibold text-text-primary">源头变更处理台</p>
            <p className="mt-1 text-xs text-text-secondary">区分“当前正式版本”与“只读扫描候选变化”。扫描只发现问题，不会自动修改前端、模型或源头。</p>
          </div>

          {data.source_update_summary && (
            <div className="flex flex-wrap items-start justify-between gap-3 bg-emerald-50/70 px-5 py-3">
              <div className="flex items-start gap-3">
                <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-600" />
                <div>
                  <p className="text-xs font-semibold text-emerald-900">当前正式基线 · 前端正在展示的版本</p>
                  <p className="mt-1 text-xs text-emerald-800/80">已发布快照包含 {data.models.length} 个 L3。绿色只表示上次应用成功，不代表源头此刻没有新变化。</p>
                </div>
              </div>
              <span className="font-mono text-[10px] text-emerald-800/60">最近应用：{new Date(data.source_update_summary.generated_at).toLocaleString('zh-CN')}</span>
            </div>
          )}

          {pendingUpdate && !pendingUpdate.applied && (
            <div className={`border-t px-5 py-4 ${pendingUpdate.changed_l3_count > 0 ? 'border-amber-200 bg-amber-50/80' : 'border-sky-100 bg-sky-50/70'}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  {pendingUpdate.changed_l3_count > 0 ? <AlertTriangle className="mt-0.5 h-5 w-5 text-amber-600" /> : <CheckCircle2 className="mt-0.5 h-5 w-5 text-sky-600" />}
                  <div>
                    <p className="text-sm font-semibold text-text-primary">只读扫描候选 · {pendingUpdate.changed_l3_count > 0 ? `${pendingUpdate.changed_l3_count} 个 L3 等待人工处理` : '没有候选变化'}</p>
                    <p className="mt-1 text-xs text-text-secondary">
                      {pendingUpdate.changed_l3_count > 0
                        ? `源头候选为 ${pendingUpdate.after_l3_count} 个 L3，当前正式基线为 ${pendingUpdate.before_l3_count} 个；${pendingUpdate.blocked_l3_count} 个应用后将进入待补，${pendingUpdate.reanalyze_l3_count} 个需要重跑模型。当前前端和Demo尚未改变。`
                        : '本次扫描与当前正式基线一致，无需人工操作。'}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-[10px] text-text-muted">扫描：{new Date(pendingUpdate.generated_at).toLocaleString('zh-CN')}</span>
                  {pendingUpdate.changed_l3_count > 0 && (
                    <button onClick={() => setShowUpdateDetails(value => !value)} className="flex items-center gap-1 rounded-lg border border-amber-300 bg-white px-3 py-2 text-xs font-medium text-amber-800 hover:bg-amber-50">
                      {showUpdateDetails ? '收起详情' : '查看影响与下一步'}
                      {showUpdateDetails ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    </button>
                  )}
                </div>
              </div>

              {showUpdateDetails && pendingUpdate.changes.length > 0 && (
                <div className="mt-4 space-y-3 border-t border-amber-200 pt-4">
                  <div className="grid gap-2 text-[11px] md:grid-cols-3">
                    <div className="rounded-lg bg-white/80 p-3"><strong>① 人工核实</strong><p className="mt-1 text-text-muted">确认新增、删除或改名是否符合业务事实。</p></div>
                    <div className="rounded-lg bg-white/80 p-3"><strong>② 应用事实更新</strong><p className="mt-1 text-text-muted">运行受控更新后，前端事实面板才会变化。</p></div>
                    <div className="rounded-lg bg-white/80 p-3"><strong>③ 按影响重跑</strong><p className="mt-1 text-text-muted">仅对输入过期且满足准入的 L3 重跑模型。</p></div>
                  </div>
                  {pendingUpdate.changes.map(change => {
                    const meaning = changeMeaning(change)
                    return (
                      <article key={change.l3_code} className="rounded-xl border border-amber-200 bg-white p-4">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2"><span className="font-mono text-xs font-semibold text-blue-700">{change.l3_code}</span><span className="rounded-full bg-amber-100 px-2 py-1 text-[10px] font-medium text-amber-800">{meaning.status}</span></div>
                          <span className="text-[10px] text-text-muted">影响面板：{change.affected_panels.join(' / ')}</span>
                        </div>
                        <div className="mt-3 grid gap-3 text-xs lg:grid-cols-3">
                          <div><p className="font-semibold text-text-primary">变化内容</p><p className="mt-1 leading-5 text-text-secondary">{change.changed_scopes.map(scope => scopeLabels[scope] ?? scope).join('、')}</p></div>
                          <div><p className="font-semibold text-text-primary">对前端 / Demo 的影响</p><p className="mt-1 leading-5 text-text-secondary">{meaning.impact}</p></div>
                          <div><p className="font-semibold text-text-primary">建议人工动作</p><p className="mt-1 leading-5 text-text-secondary">{meaning.next}</p></div>
                        </div>
                        {(change.added_source_objects.length > 0 || change.removed_source_objects.length > 0) && (
                          <div className="mt-3 border-t border-slate-100 pt-3 text-[10px] leading-5 text-text-muted">
                            {change.added_source_objects.length > 0 && <p>新增来源：{change.added_source_objects.join('、')}</p>}
                            {change.removed_source_objects.length > 0 && <p>移除来源：{change.removed_source_objects.join('、')}</p>}
                          </div>
                        )}
                      </article>
                    )
                  })}
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {featuredDemo && (
        <Link to={`/models/${featuredDemo.l3_code}`} className="block rounded-2xl border border-violet-400/25 bg-violet-400/5 p-5 transition hover:bg-violet-400/10">
          <p className="eyebrow text-violet-700">已有评审通过的完整 Demo</p>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
            <div><p className="text-lg font-semibold text-text-primary">{featuredDemo.l3_code} · {featuredDemo.l3_name}</p><p className="mt-1 text-xs text-text-secondary">已按标准模板做出叙事、任务卡工作坊、优先级矩阵、交付物地图的完整版本，可直接作为其他 L3 出 demo 的参照样本。</p></div>
            <span className="flex items-center gap-1 text-xs text-violet-700">查看模型 <ArrowRight className="h-4 w-4" /></span>
          </div>
        </Link>
      )}

      {(data.prepared_batch.length > 0 || data.recommended_batch.length > 0) && (
        <section className="panel p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div><p className="eyebrow">统一分析生产队列</p><h2 className="mt-1 text-base font-semibold">{data.prepared_batch.length > 0 ? '首批运行包已准备' : '下一批统一分析建议'}</h2></div>
            <span className="text-xs text-text-muted">只生成运行包，不自动发布模型结论</span>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            {(data.prepared_batch.length > 0 ? data.prepared_batch : data.recommended_batch).map((item, index) => (
              <div key={item.l3_code} className="rounded-xl border border-blue-200 bg-blue-50/60 p-4">
                <p className="font-mono text-xs text-blue-700">{data.prepared_batch.length > 0 ? '已准备' : `优先级 ${index + 1}`} · {item.l3_code}</p>
                <p className="mt-1 font-semibold">{item.l3_name}</p>
                <p className="mt-2 text-xs text-text-muted">{item.l4_count}个L4 · {item.classification === 'FULL_MODEL' ? '完整输入' : '带明确缺口'}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="panel flex flex-wrap items-center gap-3 p-3">
        <button onClick={() => setView('all')} className={`flex items-center gap-2 rounded-xl px-4 py-3 text-sm ${view === 'all' ? 'bg-accent-primary/10 text-accent-primary-light' : 'text-text-secondary hover:bg-bg-surface'}`}>
          全部 L3 <strong>{groups.all.length}</strong>
        </button>
        <button onClick={() => setView('ready')} className={`flex items-center gap-2 rounded-xl px-4 py-3 text-sm ${view === 'ready' ? 'bg-emerald-400/10 text-emerald-700' : 'text-text-secondary hover:bg-bg-surface'}`}>
          <CheckCircle2 className="h-4 w-4" /> 可生成完整模型 <strong>{groups.ready.length}</strong>
        </button>
        <button onClick={() => setView('evaluable')} className={`flex items-center gap-2 rounded-xl px-4 py-3 text-sm ${view === 'evaluable' ? 'bg-sky-400/10 text-sky-700' : 'text-text-secondary hover:bg-bg-surface'}`}>
          可生成带缺口模型 <strong>{groups.evaluable.length}</strong>
        </button>
        <button onClick={() => setView('missing')} className={`flex items-center gap-2 rounded-xl px-4 py-3 text-sm ${view === 'missing' ? 'bg-amber-400/10 text-amber-700' : 'text-text-secondary hover:bg-bg-surface'}`}>
          <AlertTriangle className="h-4 w-4" /> 待补后生成 <strong>{groups.missing.length}</strong>
        </button>
        <button onClick={() => setView('demo')} className={`flex items-center gap-2 rounded-xl px-4 py-3 text-sm ${view === 'demo' ? 'bg-violet-400/10 text-violet-700' : 'text-text-secondary hover:bg-bg-surface'}`}>
          <Star className="h-4 w-4" /> 已有完整 Demo <strong>{groups.demo.length}</strong>
        </button>
        <button onClick={() => setView('quality')} className={`flex items-center gap-2 rounded-xl px-4 py-3 text-sm ${view === 'quality' ? 'bg-rose-50 text-rose-700' : 'text-text-secondary hover:bg-bg-surface'}`}>
          <AlertTriangle className="h-4 w-4" /> 交付物待治理/核实 <strong>{groups.quality.length}</strong>
        </button>
        <div className="ml-auto flex items-center gap-2 px-3 text-[11px] text-text-muted"><Database className="h-3.5 w-3.5" /> {data.source_policy}</div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {[
          ['数据库 L3', data.models.length, '权威库当前有效集合'],
          ['可解析蓝图', parsedCount, '已有步骤或判断结构'],
          ['允许生成模型', groups.evaluable.length + groups.ready.length, '通过模型准入门'],
          ['完整模型', groups.ready.length, '证据达到完整门槛'],
          ['交付物疑点', audit?.finding_count ?? 0, `涉及 ${audit?.affected_l3_count ?? 0} 个 L3`],
        ].map(([label, value, note]) => (
          <div key={String(label)} className="panel p-4"><p className="eyebrow">{label}</p><p className="mt-2 metric-value">{value}</p><p className="mt-1 text-[11px] text-text-muted">{note}</p></div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative max-w-md flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
          <input value={query} onChange={event => setQuery(event.target.value)} placeholder="按 L3 编码或名称搜索" className="w-full rounded-xl border border-border-default bg-bg-elevated py-2 pl-9 pr-3 text-sm text-text-primary placeholder:text-text-muted" />
        </div>
        <div className="flex items-center gap-2">
          <select
            value={vsFilter}
            onChange={event => setVsFilter(event.target.value)}
            className="rounded-xl border border-border-default bg-bg-elevated py-2 px-3 text-sm text-text-primary"
          >
            <option value="all">全部价值流</option>
            {valueStreams.list.map(vs => (
              <option key={vs.vs_code} value={vs.vs_code}>{vs.vs_code} · {vs.vs_name}（{vs.count}）</option>
            ))}
            <option value="unmapped">未归属价值流（{valueStreams.unmapped}）</option>
          </select>
          <span className="text-[10px] text-text-muted">SSOT：process_analytics.bridge_l3_vs_stage + dim_vs</span>
        </div>
      </div>

      <details className="panel p-4">
        <summary className="cursor-pointer text-xs font-semibold text-text-primary">图例说明 · 卡片标签颜色定义</summary>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <p className="eyebrow">建模分类（右上角第二枚）</p>
            <div className="mt-2 space-y-1.5">
              <p className="flex items-center gap-2 text-xs"><span className="rounded-full bg-emerald-400/10 px-2.5 py-1 text-[11px] font-medium text-emerald-700">可生成完整模型</span><span className="text-text-muted">证据达到完整门槛</span></p>
              <p className="flex items-center gap-2 text-xs"><span className="rounded-full bg-sky-400/10 px-2.5 py-1 text-[11px] font-medium text-sky-700">可生成带缺口模型</span><span className="text-text-muted">可建模但有明确缺口</span></p>
              <p className="flex items-center gap-2 text-xs"><span className="rounded-full bg-amber-400/10 px-2.5 py-1 text-[11px] font-medium text-amber-700">待补后生成</span><span className="text-text-muted">未达最低准入门槛</span></p>
            </div>
          </div>
          <div>
            <p className="eyebrow">生产状态（右上角第三枚）</p>
            <div className="mt-2 space-y-1.5">
              <p className="flex items-center gap-2 text-xs"><span className="rounded-full bg-blue-50 px-2.5 py-1 text-[11px] font-medium text-blue-700">待运行统一分析</span><span className="text-text-muted">尚未跑过统一模型</span></p>
              <p className="flex items-center gap-2 text-xs"><span className="rounded-full bg-cyan-50 px-2.5 py-1 text-[11px] font-medium text-cyan-700">运行包已准备</span><span className="text-text-muted">已进入生产队列</span></p>
              <p className="flex items-center gap-2 text-xs"><span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700">分析与当前输入一致</span><span className="text-text-muted">结论仍是最新</span></p>
              <p className="flex items-center gap-2 text-xs"><span className="rounded-full bg-rose-50 px-2.5 py-1 text-[11px] font-medium text-rose-700">输入已变化·待重跑</span><span className="text-text-muted">源头更新，旧结论过期</span></p>
              <p className="flex items-center gap-2 text-xs"><span className="rounded-full bg-violet-50 px-2.5 py-1 text-[11px] font-medium text-violet-700">历史评审基线</span><span className="text-text-muted">人工复核过的既有结论</span></p>
              <p className="flex items-center gap-2 text-xs"><span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600">输入未达准入</span><span className="text-text-muted">模型入口关闭</span></p>
            </div>
          </div>
          <div>
            <p className="eyebrow">数据质量提示</p>
            <div className="mt-2 space-y-1.5">
              <p className="flex items-center gap-2 text-xs"><span className="flex items-center gap-1 rounded-full bg-violet-400/10 px-2.5 py-1 text-[11px] font-medium text-violet-700"><Star className="h-3 w-3" />完整 Demo</span><span className="text-text-muted">已有评审通过的完整demo</span></p>
              <p className="flex items-center gap-2 text-xs"><span className="rounded-full bg-rose-50 px-2.5 py-1 text-[11px] font-medium text-rose-700">交付物待治理 N</span><span className="text-text-muted">交付物字段存在质量问题</span></p>
              <p className="flex items-center gap-2 text-xs"><span className="rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-medium text-amber-700">重复值待核实 N</span><span className="text-text-muted">交付物疑似重复值</span></p>
            </div>
          </div>
          <div>
            <p className="eyebrow">Gate（M / E / A）</p>
            <div className="mt-2 space-y-1.5">
              <p className="flex items-center gap-2 text-xs"><span className="rounded-md border border-emerald-400/25 bg-emerald-400/10 px-2 py-1 font-mono text-[11px] text-emerald-700">PASS</span><span className="text-text-muted">通过</span></p>
              <p className="flex items-center gap-2 text-xs"><span className="rounded-md border border-sky-400/25 bg-sky-400/10 px-2 py-1 font-mono text-[11px] text-sky-700">CONDITIONAL</span><span className="text-text-muted">条件通过，有缺口但不阻断</span></p>
              <p className="flex items-center gap-2 text-xs"><span className="rounded-md border border-amber-400/25 bg-amber-400/10 px-2 py-1 font-mono text-[11px] text-amber-700">BLOCKED</span><span className="text-text-muted">未通过</span></p>
            </div>
          </div>
          <div>
            <p className="eyebrow">价值流 / KPI</p>
            <div className="mt-2 space-y-1.5">
              <p className="flex items-center gap-2 text-xs"><span className="rounded-full bg-teal-400/10 px-2 py-0.5 text-[11px] font-medium text-teal-700">价值流名称 · 阶段</span><span className="text-text-muted">该L3在客户旅程中的位置</span></p>
              <p className="flex items-center gap-2 text-xs"><span className="rounded-full bg-amber-400/10 px-2 py-0.5 text-[11px] font-medium text-amber-800">KPI名称</span><span className="text-text-muted">已有公式/单位的业务指标定义</span></p>
              <p className="flex items-center gap-2 text-xs"><span className="rounded-full border border-dashed border-rose-300 bg-rose-50 px-2 py-0.5 text-[11px] font-medium text-rose-700">KPI名称</span><span className="text-text-muted">Mark战略权重，未确认草稿</span></p>
            </div>
          </div>
        </div>
      </details>

      <div className="grid gap-4 md:grid-cols-2">
        {current.map(model => <ModelCard key={model.l3_code} model={model} quality={qualityByL3[model.l3_code]} />)}
      </div>
    </div>
  )
}
