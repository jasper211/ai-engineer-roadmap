import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router'
import { AlertTriangle, ArrowRight, CheckCircle2, Database, GitBranch, LoaderCircle, Search, Star } from 'lucide-react'
import { loadDeliverableAudit, loadModelIndex, loadPendingSourceUpdate, type DeliverableAudit, type ModelIndex, type ModelIndexItem, type SourceUpdateReport } from '../lib/l3Models'

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
      {!full && model.gap_reasons.length > 0 && (
        <p className="mt-2 line-clamp-2 text-xs text-amber-800/80">首要缺口：{model.gap_reasons[0]}</p>
      )}
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
  const [view, setView] = useState<'all' | 'ready' | 'evaluable' | 'missing' | 'demo' | 'quality'>('all')
  const [query, setQuery] = useState('')

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

  if (error) return <div className="panel p-5 text-sm text-accent-danger">{error}</div>
  if (!data) return <div className="flex min-h-64 items-center justify-center text-text-muted"><LoaderCircle className="mr-2 h-5 w-5 animate-spin" />正在读取真实模型快照</div>

  const current = groups[view].filter(model => `${model.l3_code}${model.l3_name}`.toLowerCase().includes(query.toLowerCase()))
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

      {data.source_update_summary && (
        <section className={`rounded-2xl border p-4 ${data.source_update_summary.changed_l3_count > 0 ? 'border-rose-200 bg-rose-50' : 'border-emerald-200 bg-emerald-50'}`}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-start gap-3">
              {data.source_update_summary.changed_l3_count > 0
                ? <AlertTriangle className="mt-0.5 h-5 w-5 text-rose-600" />
                : <CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-600" />}
              <div>
                <p className="text-sm font-semibold text-text-primary">阶段2 · 源头更新状态</p>
                <p className="mt-1 text-xs text-text-secondary">
                  {data.source_update_summary.changed_l3_count > 0
                    ? `发现 ${data.source_update_summary.changed_l3_count} 个L3输入变化；${data.source_update_summary.reanalyze_l3_count}个需重跑分析，${data.source_update_summary.blocked_l3_count}个因硬输入不足阻断。`
                    : '数据库与知识输入已与当前事实快照对齐，没有待发布变化。'}
                </p>
              </div>
            </div>
            <span className="font-mono text-[10px] text-text-muted">最近应用：{new Date(data.source_update_summary.generated_at).toLocaleString('zh-CN')}
            </span>
          </div>
        </section>
      )}

      {pendingUpdate && !pendingUpdate.applied && (
        <section className={`rounded-2xl border p-4 ${pendingUpdate.changed_l3_count > 0 ? 'border-amber-300 bg-amber-50' : 'border-sky-200 bg-sky-50'}`}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-text-primary">自动只读扫描 · {pendingUpdate.changed_l3_count > 0 ? '发现待应用变化' : '未发现新变化'}</p>
              <p className="mt-1 text-xs text-text-secondary">
                {pendingUpdate.changed_l3_count > 0
                  ? `影响${pendingUpdate.changed_l3_count}个L3；${pendingUpdate.reanalyze_l3_count}个需重跑分析，${pendingUpdate.blocked_l3_count}个将进入阻断。当前页面尚未应用这些变化。`
                  : '本次扫描与已发布快照一致，无需操作。'}
              </p>
              {pendingUpdate.changes.length > 0 && (
                <p className="mt-2 text-[11px] text-amber-800">影响L3：{pendingUpdate.changes.slice(0, 8).map(item => item.l3_code).join('、')}{pendingUpdate.changes.length > 8 ? '等' : ''}</p>
              )}
            </div>
            <span className="font-mono text-[10px] text-text-muted">最近扫描：{new Date(pendingUpdate.generated_at).toLocaleString('zh-CN')}</span>
          </div>
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

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
        <input value={query} onChange={event => setQuery(event.target.value)} placeholder="按 L3 编码或名称搜索" className="w-full rounded-xl border border-border-default bg-bg-elevated py-2 pl-9 pr-3 text-sm text-text-primary placeholder:text-text-muted" />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {current.map(model => <ModelCard key={model.l3_code} model={model} quality={qualityByL3[model.l3_code]} />)}
      </div>
    </div>
  )
}
