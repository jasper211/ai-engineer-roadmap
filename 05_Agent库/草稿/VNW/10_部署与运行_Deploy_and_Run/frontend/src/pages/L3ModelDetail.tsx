import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ArrowLeft, ArrowRight, Bot, GitBranch, GripVertical, Info, Layers3, LoaderCircle, RotateCcw, Save, ShieldCheck } from 'lucide-react'
import { loadL3Model, type L3Model } from '../lib/l3Models'

const COLUMNS = [
  { id: 'Human', label: '暂不替代', color: 'border-rose-400/30 bg-rose-400/5' },
  { id: 'Hybrid', label: '人机协同', color: 'border-amber-400/30 bg-amber-400/5' },
  { id: 'Auto', label: '可完全替代', color: 'border-emerald-400/30 bg-emerald-400/5' },
  { id: 'Aug', label: 'AI 增强', color: 'border-sky-400/30 bg-sky-400/5' },
] as const

type WorkshopState = { placements: Record<string, string>; note: string; updatedAt: string; baseSnapshotHash: string }

function gateTone(status: string) {
  return status === 'PASS' ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-700' : 'border-amber-400/25 bg-amber-400/10 text-amber-700'
}

function tierTone(tier: string) {
  if (tier === 'Auto') return 'border-emerald-200 bg-emerald-100 text-emerald-800'
  if (tier === 'Aug') return 'border-blue-200 bg-blue-100 text-blue-800'
  if (tier === 'Hybrid') return 'border-amber-200 bg-amber-100 text-amber-800'
  if (tier === 'Human') return 'border-rose-200 bg-rose-100 text-rose-800'
  return 'border-slate-200 bg-slate-100 text-slate-600'
}

function roleTone(role: string) {
  if (role.startsWith('价值')) return 'border-blue-200 bg-blue-50/70'
  if (role.startsWith('控制')) return 'border-rose-200 bg-rose-50/70'
  if (role.startsWith('支撑')) return 'border-amber-200 bg-amber-50/70'
  return 'border-border-default bg-bg-surface'
}

export default function L3ModelDetail({ modelCode }: { modelCode?: string } = {}) {
  const params = useParams()
  const l3Code = modelCode || params.l3Code || ''
  const [model, setModel] = useState<L3Model | null>(null)
  const [error, setError] = useState('')
  const storageKey = `vnw-workshop-v1:${l3Code}`
  const [session, setSession] = useState<WorkshopState>({ placements: {}, note: '', updatedAt: '', baseSnapshotHash: '' })
  const [taskL4Filter, setTaskL4Filter] = useState('ALL')

  useEffect(() => {
    loadL3Model(l3Code).then(setModel).catch(error => setError(error.message))
    const saved = localStorage.getItem(storageKey)
    if (saved) {
      try { setSession(JSON.parse(saved)) } catch { localStorage.removeItem(storageKey) }
    }
  }, [l3Code, storageKey])

  const cards = useMemo(() => {
    if (!model) return []
    const analyzedTasks = model.analysis.tasks.filter(task => COLUMNS.some(column => column.id === task.suggested_tier))
    const base = analyzedTasks.length > 0
      ? analyzedTasks.map(task => ({
          card_id: task.task_id,
          l4_code: task.l4_code,
          deliverable: task.task_name,
          l4_name: task.tier_rationale,
          tier: task.suggested_tier,
          source_type: task.source_type,
        }))
      : model.l4s.map(l4 => ({ ...l4, card_id: l4.l4_code, source_type: 'DATABASE_L4' }))
    return base.map(card => ({
      ...card,
      placement: session.placements[card.card_id] || card.tier,
      changed: Boolean(session.placements[card.card_id] && session.placements[card.card_id] !== card.tier),
    }))
  }, [model, session.placements])
  const mappedL4s = useMemo(() => new Set(
    model?.vn_l4_mappings.map(row => String(row.l4_code || '')) ?? []
  ), [model])
  const taskL4Options = useMemo(() => [...new Set(cards.map(card => card.l4_code))].sort(), [cards])
  const visibleCards = useMemo(
    () => taskL4Filter === 'ALL' ? cards : cards.filter(card => card.l4_code === taskL4Filter),
    [cards, taskL4Filter],
  )
  function moveCard(cardId: string, placement: string) {
    setSession(current => ({ ...current, placements: { ...current.placements, [cardId]: placement } }))
  }

  function persist() {
    const next = { ...session, updatedAt: new Date().toISOString(), baseSnapshotHash: model?.snapshot_hash || '' }
    localStorage.setItem(storageKey, JSON.stringify(next))
    setSession(next)
  }

  function reset() {
    localStorage.removeItem(storageKey)
    setSession({ placements: {}, note: '', updatedAt: '', baseSnapshotHash: '' })
  }

  if (error) return <div className="panel p-5 text-sm text-accent-danger">{error}</div>
  if (!model) return <div className="flex min-h-64 items-center justify-center text-text-muted"><LoaderCircle className="mr-2 h-5 w-5 animate-spin" />正在读取模型证据</div>

  return (
    <div className="space-y-6">
      <Link to="/models" className="inline-flex items-center gap-2 text-xs text-text-muted hover:text-text-primary"><ArrowLeft className="h-4 w-4" />返回模型清单</Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs text-accent-primary-light">{model.l3_code}</p>
          <h1 className="mt-1 font-heading text-3xl font-bold">{model.l3_name}</h1>
          <p className="mt-2 text-sm text-text-secondary">{model.l4s.length} 个 L4 交付活动 · {model.value_nodes.length} 个价值节点 · 蓝图 {model.blueprint.version || '未覆盖'}</p>
        </div>
        <div className="flex gap-2">
          {(['M', 'E', 'A'] as const).map(gate => <span key={gate} className={`rounded-lg border px-3 py-2 font-mono text-xs ${gateTone(model.gates[gate].status)}`}>Gate {gate} · {model.gates[gate].status}</span>)}
        </div>
      </div>

      <section className="rounded-2xl border border-indigo-200 bg-indigo-50/60 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold text-indigo-700">统一分析标准 · {model.analysis.analysis_standard_id}</p>
            <p className="mt-1 text-xs leading-5 text-text-secondary">
              当前事实包已从同一数据库与知识输入链生成，提取出 {model.analysis.tasks.length} 条可追溯蓝图任务。
              {model.analysis.analysis_status === 'PENDING_MODEL'
                ? '模型分析尚未执行，以下页面只展示事实层，不会自动补造COM式结论。'
                : '模型分析草稿已生成，页面中的推导内容必须保留证据引用。'}
            </p>
          </div>
          <span className={`rounded-full px-3 py-1.5 text-xs font-medium ${model.analysis.analysis_status === 'PENDING_MODEL' ? 'bg-amber-100 text-amber-800' : 'bg-violet-100 text-violet-800'}`}>
            {model.analysis.analysis_status === 'PENDING_MODEL' ? '待运行统一模型' : '模型分析草稿'}
          </span>
        </div>
        {model.analysis.missing_analysis.length > 0 && (
          <p className="mt-2 text-[11px] text-text-muted">尚待生成：{model.analysis.missing_analysis.join('、')}</p>
        )}
      </section>

      <section className="panel p-5">
        <div className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-accent-primary-light" /><h2 className="text-sm font-semibold">为什么处于这个 Gate</h2></div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {(['M', 'E', 'A'] as const).map(gate => (
            <div key={gate} className="rounded-xl border border-border-default bg-bg-surface p-4">
              <p className="font-mono text-xs text-text-muted">Gate {gate}</p>
              <div className="mt-2 space-y-2">
                {model.gates[gate].checks.map(check => (
                  <div key={check.rule_id} className="flex gap-2 text-xs">
                    <span className={check.passed ? 'text-emerald-700' : 'text-amber-700'}>{check.passed ? '✓' : '!'}</span>
                    <span className="text-text-secondary">{check.detail}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-default pb-3">
          <div className="flex items-center gap-2"><GitBranch className="h-4 w-4 text-accent-primary-light" /><h2 className="text-sm font-semibold">面板 A · L3流程叙事（理想态执行路径）</h2></div>
          <span className="text-[10px] text-text-muted">{model.blueprint.filename} · {model.blueprint.steps.length}步 / {model.blueprint.decisions.length}判断点</span>
        </div>
        {model.blueprint.structure_status === 'PARSED' ? (
          <>
            <div className="mt-4 overflow-x-auto pb-3">
              <div className="flex min-w-max items-stretch gap-2">
                {model.blueprint.steps.map((step, index) => {
                const highlighted = step.l4_codes.some(code => mappedL4s.has(code))
                return (
                  <div key={step.step_id} className="flex items-center gap-2">
                    <div className={`w-48 shrink-0 rounded-xl border p-3 ${highlighted ? 'border-violet-300 bg-violet-50' : 'border-slate-200 bg-white'}`}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-[10px] text-accent-primary">{step.l4_codes.join(' / ') || `步骤${step.sequence}`}</span>
                        <span className="text-[9px] text-text-muted">#{step.sequence}</span>
                      </div>
                      <p className="mt-2 text-sm font-semibold leading-5 text-text-primary">{step.step_name}</p>
                      {step.activities[0] && <p className="mt-2 line-clamp-3 text-[11px] leading-4 text-text-secondary">{step.activities[0]}</p>}
                      <p className="mt-2 text-[9px] text-text-muted">蓝图第 {step.source_line} 行</p>
                    </div>
                    {index < model.blueprint.steps.length - 1 && <ArrowRight className="h-5 w-5 shrink-0 text-slate-500" />}
                  </div>
                )
              })}
              </div>
            </div>
            {model.blueprint.decisions.length === 0 ? (
              <div className="mt-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-800">蓝图没有显式判断菱形，因此不增加决策点或回退线；支链和控制点不能擅自改画成主链判断。</div>
            ) : (
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {model.blueprint.decisions.map(decision => (
                  <div key={decision.decision_id} className="rounded-xl border border-amber-300 bg-amber-50 p-4">
                    <p className="text-center text-sm font-semibold text-amber-900">◇ {decision.question}？</p>
                    <div className="mt-3 space-y-2">{decision.branches.map((branch, index) => <p key={index} className={`rounded-lg border bg-white px-3 py-2 text-xs ${branch.is_return ? 'border-rose-200 text-rose-800' : 'border-amber-100 text-text-secondary'}`}><b>{branch.label}</b> → {branch.target_text}</p>)}</div>
                  </div>
                ))}
              </div>
            )}
            {Boolean(model.analysis.control_chain?.length) && (
              <div className="mt-4">
                <div className="flex flex-wrap items-center justify-center gap-2">
                  {model.analysis.control_chain?.map((item, index) => <div key={item.l4_code} className="flex items-center gap-2">
                    <div className={`rounded-xl border px-4 py-3 ${item.tone === 'critical' ? 'border-rose-300 bg-rose-50' : 'border-slate-200 bg-white'}`}>
                      <p className="text-xs font-bold text-text-primary">{item.level} · {item.l4_code.replace('L4-', '')}</p>
                      <p className="mt-1 text-xs text-text-secondary">{item.label}</p>
                    </div>
                    {index < (model.analysis.control_chain?.length || 0) - 1 && <ArrowRight className="h-4 w-4 text-slate-500" />}
                  </div>)}
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="mt-4 rounded-xl border border-amber-400/25 bg-amber-400/5 p-4">
            <p className="text-sm font-medium text-amber-800">当前不生成流程图：{model.blueprint.structure_status}</p>
            <p className="mt-1 text-xs leading-5 text-text-secondary">{model.blueprint.note}</p>
            {Boolean(model.blueprint.diagnostics?.missing_in_blueprint?.length) && (
              <p className="mt-2 text-xs text-text-muted">数据库存在但蓝图未覆盖：{model.blueprint.diagnostics.missing_in_blueprint?.join('、')}</p>
            )}
          </div>
        )}
      </section>

      <section className="panel p-5">
        <div className="flex items-center gap-2"><Layers3 className="h-4 w-4 text-accent-primary-light" /><h2 className="text-sm font-semibold">面板 E · L4交付物地图</h2></div>
        <p className="mt-2 text-xs text-text-muted">围绕 L3 目标查看交付物、数据库 Tier 和人工介入点。当前蓝图为 {model.blueprint.structure_status}，因此不展示未经正文解析的流程箭头。</p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {model.l4s.map(l4 => {
            const analysis = model.analysis.l4_analysis.find(item => String(item.l4_code) === l4.l4_code) as Record<string, unknown> | undefined
            const displayTier = String(analysis?.recommended_tier || l4.tier || '')
            return (
            <div key={l4.l4_code} className={`rounded-xl border p-4 ${roleTone(String(analysis?.deliverable_role || ''))}`}>
              <div className="flex items-center justify-between gap-3"><span className="font-mono text-[11px] text-accent-primary-light">{l4.l4_code}</span><span className={`rounded-md border px-2 py-1 text-[10px] font-semibold ${tierTone(displayTier)}`}>{displayTier || '未评估'}</span></div>
              <p className="mt-2 text-sm font-medium">{l4.deliverable || l4.l4_name}</p>
              <p className="mt-1 text-xs text-text-muted">{l4.l4_name}</p>
              {Boolean(analysis?.deliverable_role) && <span className="mt-3 inline-block rounded-full bg-indigo-50 px-2.5 py-1 text-[10px] font-medium text-indigo-700">{String(analysis?.deliverable_role)}</span>}
              {Array.isArray(analysis?.specific_capabilities) && analysis.specific_capabilities.length > 0 && <p className="mt-3 text-xs leading-5 text-text-secondary"><b>具体能力：</b>{analysis.specific_capabilities.join('、')}</p>}
              {Boolean(analysis?.ai_reshape) && <p className="mt-2 text-xs leading-5 text-indigo-700"><b>AI重塑：</b>{String(analysis?.ai_reshape)}</p>}
              {Boolean(analysis?.quality_anchor) && <p className="mt-2 text-xs leading-5 text-emerald-700"><b>质量锚点：</b>{String(analysis?.quality_anchor)}</p>}
              {Boolean(analysis?.database_tier && analysis?.recommended_tier && analysis.database_tier !== analysis.recommended_tier) && <p className="mt-2 text-[10px] text-amber-700">数据库Tier：{String(analysis?.database_tier)} · 正式复核建议：{String(analysis?.recommended_tier)}</p>}
              {!analysis?.ai_reshape && l4.human_touchpoint && <p className="mt-2 text-xs text-text-secondary">人工介入：{l4.human_touchpoint}</p>}
            </div>
          )})}
        </div>
        {model.blueprint.blueprint_value_nodes.length > 0 && (
          <>
            <h3 className="mt-6 text-sm font-semibold text-text-primary">服务的价值节点</h3>
            <p className="mt-1 text-xs text-text-muted">数据库正式映射与蓝图补充关系分层展示；蓝图内容不冒充数据库桥接。</p>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {model.blueprint.blueprint_value_nodes.map(node => (
                <div key={node.vn_id} className="rounded-xl border border-amber-200 bg-amber-50/70 p-4">
                  <div className="flex justify-between gap-3"><span className="font-mono text-xs text-amber-800">{node.vn_id}</span><span className="text-[10px] text-text-muted">蓝图第 {node.source_line} 行</span></div>
                  <p className="mt-2 text-sm font-medium text-text-primary">{node.vn_name}</p>
                  <p className="mt-1 text-xs text-text-secondary">{node.deliverable}</p>
                  <p className="mt-2 text-[11px] text-text-muted">{node.l4_codes.join('、')} · {node.status_text}</p>
                </div>
              ))}
            </div>
          </>
        )}
      </section>

      <section className="panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2"><Bot className="h-4 w-4 text-accent-primary-light" /><h2 className="text-sm font-semibold">面板 C · AI任务卡片工作坊</h2></div>
            <p className="mt-2 text-xs text-text-muted">初始位置来自数据库；拖动后的差异仅是本机工作坊共识，不会写回权威库。</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 rounded-lg border border-border-default bg-white px-3 py-2 text-xs text-text-secondary">
              <span>L4筛选</span>
              <select value={taskL4Filter} onChange={event => setTaskL4Filter(event.target.value)} className="bg-transparent font-mono text-[11px] text-text-primary outline-none">
                <option value="ALL">全部任务（{cards.length}）</option>
                {taskL4Options.map(code => {
                  const l4Name = model.l4s.find(item => item.l4_code === code)?.l4_name || '名称待补'
                  return <option key={code} value={code}>{code} · {l4Name}（{cards.filter(card => card.l4_code === code).length}）</option>
                })}
              </select>
            </label>
            <button onClick={reset} className="flex items-center gap-1.5 rounded-lg border border-border-default px-3 py-2 text-xs text-text-muted hover:text-text-primary"><RotateCcw className="h-3.5 w-3.5" />恢复数据库位置</button>
            <button onClick={persist} className="flex items-center gap-1.5 rounded-lg bg-accent-primary px-3 py-2 text-xs text-white"><Save className="h-3.5 w-3.5" />保存到本机</button>
          </div>
        </div>
        {session.baseSnapshotHash && session.baseSnapshotHash !== model.snapshot_hash && (
          <div className="mt-4 rounded-xl border border-rose-400/30 bg-rose-400/5 p-3 text-xs text-rose-800">
            这份本机工作坊草稿基于旧模型快照。系统不会自动合并；请先对照新数据，再保存为当前版本或恢复数据库位置。
          </div>
        )}

        <div className="mt-4 grid gap-3 lg:grid-cols-4">
          {COLUMNS.map(column => (
            <div key={column.id} onDragOver={event => event.preventDefault()} onDrop={event => moveCard(event.dataTransfer.getData('text/card'), column.id)} className={`min-h-48 rounded-xl border p-3 ${column.color}`}>
              <div className="mb-3 flex items-center justify-between"><h3 className="text-sm font-semibold">{column.label}</h3><span className="text-xs text-text-muted">{visibleCards.filter(card => card.placement === column.id).length}</span></div>
              <div className="space-y-2">
                {visibleCards.filter(card => card.placement === column.id).map(card => (
                  <article key={card.card_id} draggable onDragStart={event => event.dataTransfer.setData('text/card', card.card_id)} className="cursor-grab rounded-lg border border-border-default bg-bg-elevated p-3 active:cursor-grabbing">
                    <div className="flex gap-2"><GripVertical className="mt-0.5 h-4 w-4 shrink-0 text-text-muted" /><div><p className="text-xs font-medium text-text-primary">{card.deliverable || card.l4_name}</p><p className="mt-1 font-mono text-[10px] text-text-muted">{card.l4_code}</p></div></div>
                    <p className="mt-1 text-[10px] text-text-muted">{card.source_type}</p>
                    {card.changed && <p className="mt-2 rounded bg-violet-400/10 px-2 py-1 text-[10px] text-violet-700">工作坊共识假设 · 数据库原位置：{card.tier}</p>}
                    <select aria-label={`调整 ${card.card_id} 的工作坊位置`} value={card.placement} onChange={event => moveCard(card.card_id, event.target.value)} className="mt-2 w-full rounded border border-border-default bg-bg-surface px-2 py-1 text-[10px] text-text-secondary lg:hidden">
                      {COLUMNS.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
                    </select>
                  </article>
                ))}
              </div>
            </div>
          ))}
        </div>

        <label className="mt-4 block text-xs text-text-secondary">本次讨论结论
          <textarea value={session.note} onChange={event => setSession(current => ({ ...current, note: event.target.value }))} placeholder="只记录负责人确认的结论、待验证事项和责任人；保存后仅留在当前浏览器。" className="mt-2 min-h-24 w-full rounded-xl border border-border-default bg-bg-surface p-3 text-sm text-text-primary placeholder:text-text-muted" />
        </label>
        {session.updatedAt && <p className="mt-2 text-[11px] text-text-muted">本机最后保存：{new Date(session.updatedAt).toLocaleString()}</p>}
      </section>

      <section className="panel p-5">
        <div className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-accent-primary-light" /><h2 className="text-sm font-semibold">面板 B · 人机协作与控制地图</h2></div>
        <p className="mt-2 text-xs text-text-muted">固定展示AI负责、人负责、转人工条件和不可绕过控制门。模型未完成分析时保留缺失态，不从Tier名称反推业务控制。</p>
        {model.analysis.analysis_status === 'PENDING_MODEL' ? (
          <div className="mt-4 rounded-xl border border-dashed border-amber-300 bg-amber-50 p-5">
            <p className="text-sm font-medium text-amber-800">待运行统一模型</p>
            <p className="mt-1 text-xs leading-5 text-text-secondary">当前只有数据库Tier和人工触点，尚不足以生成逐L4的人机责任、异常升级条件和控制门。</p>
          </div>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-[980px] w-full text-xs">
              <thead><tr className="border-b border-border-default text-left text-text-muted"><th className="py-2">L4</th><th>AI负责</th><th>人负责</th><th>何时转人工</th><th>不可绕过控制门</th></tr></thead>
              <tbody>{model.analysis.l4_analysis.map((item, index) => {
                const row = item as Record<string, unknown>
                return <tr key={String(row.l4_code || index)} className="border-b border-border-default/70 align-top"><td className="py-3 font-mono text-accent-primary">{String(row.l4_code || '')}</td><td>{String(row.ai_responsibility || '待补')}</td><td>{String(row.human_responsibility || '待补')}</td><td>{Array.isArray(row.handoff_triggers) ? row.handoff_triggers.join('；') : '待补'}</td><td>{Array.isArray(row.control_gates) ? row.control_gates.join('；') : '待补'}</td></tr>
              })}</tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel p-5">
        <div className="flex items-center gap-2"><Layers3 className="h-4 w-4 text-accent-primary-light" /><h2 className="text-sm font-semibold">面板 D · AI机会优先级</h2></div>
        <p className="mt-2 text-xs text-text-muted">每个位置必须有数据依据、流程背景、风险限制和当前建议；无分析依据时不自动安排象限位置。</p>
        {model.analysis.priority_drafts.length === 0 ? (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {['优先验证', '治理后推进', '补数据后推进', '暂缓自动化'].map(label => (
              <div key={label} className="min-h-28 rounded-xl border border-dashed border-border-default bg-bg-surface p-4">
                <p className="text-sm font-medium text-text-primary">{label}</p>
                <p className="mt-2 text-xs text-text-muted">尚无经过证据校验的逐L4分析，不生成假位置。</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-4 space-y-3">
            {model.analysis.priority_drafts.some(item => !['q1', 'q2', 'q3', 'q4'].includes(String(item.quadrant))) && (
              <div className="rounded-xl border border-violet-200 bg-violet-50/70 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-violet-900">待负责人归类 · 不编造象限位置</p>
                  <span className="rounded-full bg-white px-2 py-1 text-[10px] text-violet-700">缺少逐 L4 价值依据</span>
                </div>
                <div className="mt-3 grid gap-2 lg:grid-cols-2">
                  {model.analysis.priority_drafts.filter(item => !['q1', 'q2', 'q3', 'q4'].includes(String(item.quadrant))).map((item, index) => (
                    <div key={String(item.l4_code || index)} className="rounded-lg border border-violet-100 bg-white p-3 shadow-sm">
                      <p className="font-mono text-[10px] text-accent-primary">{String(item.l4_code || '')}</p>
                      <p className="mt-1 text-xs font-medium text-text-primary">{String(item.current_recommendation || '')}</p>
                      <p className="mt-1 text-[11px] leading-4 text-text-secondary"><b>流程背景：</b>{String(item.process_context || '')}</p>
                      <p className="mt-1 text-[10px] leading-4 text-text-muted"><b>风险/限制：</b>{Array.isArray(item.risks_limits) ? item.risks_limits.join('；') : ''}</p>
                      <p className="mt-1 text-[10px] leading-4 text-text-muted"><b>数据依据：</b>{Array.isArray(item.data_basis) ? item.data_basis.join('；') : ''}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="grid gap-3 sm:grid-cols-2">
              {[
                ['q1', '优先验证', 'border-emerald-200 bg-emerald-50/60'],
                ['q2', '治理后推进', 'border-blue-200 bg-blue-50/60'],
                ['q3', '补数据后推进', 'border-amber-200 bg-amber-50/60'],
                ['q4', '暂缓自动化', 'border-rose-200 bg-rose-50/60'],
              ].map(([quadrant, label, tone]) => (
                <div key={quadrant} className={`min-h-36 rounded-xl border p-4 ${tone}`}>
                  <p className="text-sm font-semibold text-text-primary">{label}</p>
                  <div className="mt-3 space-y-2">
                    {model.analysis.priority_drafts.filter(item => String(item.quadrant) === quadrant).map((item, index) => (
                      <div key={String(item.l4_code || index)} className="rounded-lg border border-white/80 bg-white p-3 shadow-sm">
                        <p className="font-mono text-[10px] text-accent-primary">{String(item.l4_code || '')}</p>
                        <p className="mt-1 text-xs font-medium text-text-primary">{String(item.current_recommendation || '')}</p>
                        <p className="mt-1 text-[11px] leading-4 text-text-secondary">{String(item.process_context || '')}</p>
                        <p className="mt-1 text-[10px] leading-4 text-text-muted">限制：{Array.isArray(item.risks_limits) ? item.risks_limits.join('；') : ''}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-indigo-200 bg-gradient-to-br from-indigo-50 to-white p-5 shadow-panel">
        <div className="flex items-center gap-2"><Bot className="h-4 w-4 text-accent-primary" /><h2 className="text-sm font-semibold">负责人决策 · 先试哪些AI任务</h2></div>
        <p className="mt-2 text-xs text-text-muted">只输出任务级优先顺序、最小试点、人工边界和需要拍板的事项。</p>
        {model.analysis.decision_drafts.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-indigo-200 bg-white/80 p-5 text-sm text-text-secondary">
            当前尚无通过证据校验的负责人决策草稿。完成统一模型分析后再生成，不使用通用建议占位。
          </div>
        ) : (
          <div className="mt-4 space-y-3">{model.analysis.decision_drafts.map((draft, index) => (
            <div key={String(draft.priority || index)} className="grid gap-3 rounded-xl border border-indigo-100 bg-white p-4 md:grid-cols-[90px_1.2fr_1fr_1fr]">
              <div><span className="rounded-full bg-indigo-100 px-2.5 py-1 text-xs font-bold text-indigo-800">{String(draft.priority || '')}</span></div>
              <div><p className="text-sm font-semibold text-text-primary">{String(draft.title || '')}</p><p className="mt-1 font-mono text-[10px] text-text-muted">{Array.isArray(draft.task_ids) ? draft.task_ids.join('、') : ''}</p></div>
              <div><p className="eyebrow">最小试点</p><p className="mt-1 text-xs leading-5 text-text-secondary">{String(draft.pilot_scope || '')}</p></div>
              <div><p className="eyebrow">人工边界</p><p className="mt-1 text-xs leading-5 text-text-secondary">{String(draft.human_boundary || '')}</p></div>
            </div>
          ))}</div>
        )}
      </section>

      <section className="panel p-5">
        <details>
          <summary className="cursor-pointer text-sm font-semibold text-text-primary">面板 F · SSOT与证据</summary>
          <p className="mt-2 text-xs text-text-muted">当前模型共登记 {model.evidence_registry.length} 条字段证据；分析标准为 {model.analysis.analysis_standard_id}。</p>
          <div className="mt-4 max-h-96 overflow-auto rounded-xl border border-border-default">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-bg-surface text-text-muted"><tr><th className="px-3 py-2">证据ID</th><th>证据层</th><th>字段</th><th>状态</th></tr></thead>
              <tbody>{model.evidence_registry.map((item, index) => {
                const row = item as Record<string, unknown>
                return <tr key={String(row.evidence_id || index)} className="border-t border-border-default"><td className="px-3 py-2 font-mono text-[10px] text-accent-primary">{String(row.evidence_id || '')}</td><td>{String(row.evidence_class || '')}</td><td>{String(row.field_name || '')}</td><td>{String(row.status || '')}</td></tr>
              })}</tbody>
            </table>
          </div>
        </details>
      </section>

      <div className="flex items-start gap-2 rounded-xl border border-sky-400/20 bg-sky-400/5 p-4 text-xs text-sky-800">
        <Info className="mt-0.5 h-4 w-4 shrink-0" />
        <span>本页业务事实来自 process_analytics 快照，共 {model.evidence_registry.length} 条字段证据。浏览器保存内容属于 CONSENSUS 层，不参与 Gate 自动判断。</span>
      </div>
    </div>
  )
}
