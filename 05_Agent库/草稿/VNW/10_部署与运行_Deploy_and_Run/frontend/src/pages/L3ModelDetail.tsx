import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ArrowDown, ArrowLeft, Bot, GitBranch, GripVertical, Info, Layers3, LoaderCircle, RotateCcw, Save, ShieldCheck } from 'lucide-react'
import { loadL3Model, type L3Model } from '../lib/l3Models'

const COLUMNS = [
  { id: 'Human', label: '暂不替代', color: 'border-rose-400/30 bg-rose-400/5' },
  { id: 'Hybrid', label: '人机协同', color: 'border-amber-400/30 bg-amber-400/5' },
  { id: 'Auto', label: '可完全替代', color: 'border-emerald-400/30 bg-emerald-400/5' },
  { id: 'Aug', label: 'AI 增强', color: 'border-sky-400/30 bg-sky-400/5' },
] as const

type WorkshopState = { placements: Record<string, string>; note: string; updatedAt: string; baseSnapshotHash: string }

function gateTone(status: string) {
  return status === 'PASS' ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300' : 'border-amber-400/25 bg-amber-400/10 text-amber-300'
}

export default function L3ModelDetail() {
  const { l3Code = '' } = useParams()
  const [model, setModel] = useState<L3Model | null>(null)
  const [error, setError] = useState('')
  const storageKey = `vnw-workshop-v1:${l3Code}`
  const [session, setSession] = useState<WorkshopState>({ placements: {}, note: '', updatedAt: '', baseSnapshotHash: '' })

  useEffect(() => {
    loadL3Model(l3Code).then(setModel).catch(error => setError(error.message))
    const saved = localStorage.getItem(storageKey)
    if (saved) {
      try { setSession(JSON.parse(saved)) } catch { localStorage.removeItem(storageKey) }
    }
  }, [l3Code, storageKey])

  const cards = useMemo(() => model?.l4s.map(l4 => ({
    ...l4,
    placement: session.placements[l4.l4_code] || l4.tier,
    changed: Boolean(session.placements[l4.l4_code] && session.placements[l4.l4_code] !== l4.tier),
  })) ?? [], [model, session.placements])
  const mappedL4s = useMemo(() => new Set(
    model?.vn_l4_mappings.map(row => String(row.l4_code || '')) ?? []
  ), [model])

  function moveCard(code: string, placement: string) {
    setSession(current => ({ ...current, placements: { ...current.placements, [code]: placement } }))
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

      <section className="panel p-5">
        <div className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-accent-primary-light" /><h2 className="text-sm font-semibold">为什么处于这个 Gate</h2></div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {(['M', 'E', 'A'] as const).map(gate => (
            <div key={gate} className="rounded-xl border border-border-default bg-bg-surface p-4">
              <p className="font-mono text-xs text-text-muted">Gate {gate}</p>
              <div className="mt-2 space-y-2">
                {model.gates[gate].checks.map(check => (
                  <div key={check.rule_id} className="flex gap-2 text-xs">
                    <span className={check.passed ? 'text-emerald-300' : 'text-amber-300'}>{check.passed ? '✓' : '!'}</span>
                    <span className="text-text-secondary">{check.detail}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-5">
        <div className="flex items-center gap-2"><GitBranch className="h-4 w-4 text-accent-primary-light" /><h2 className="text-sm font-semibold">实际流程蓝图</h2></div>
        {model.blueprint.structure_status === 'PARSED' ? (
          <>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-text-muted">
              <span>正文解析：{model.blueprint.steps.length} 步 · {model.blueprint.decisions.length} 个判断点</span>
              <span>·</span>
              <span>{model.blueprint.filename}</span>
              {mappedL4s.size > 0 && <span className="rounded bg-violet-400/10 px-2 py-1 text-violet-300">紫色步骤 = 与当前价值节点映射的 L4</span>}
            </div>
            <div className="mx-auto mt-5 max-w-3xl">
              {model.blueprint.steps.map((step, index) => {
                const decisions = model.blueprint.decisions.filter(decision => decision.after_step === step.step_id)
                const highlighted = step.l4_codes.some(code => mappedL4s.has(code))
                return (
                  <div key={step.step_id}>
                    <div className={`rounded-xl border p-4 ${highlighted ? 'border-violet-400/50 bg-violet-400/10' : 'border-border-default bg-bg-surface'}`}>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="grid h-7 w-7 place-items-center rounded-full bg-accent-primary/15 text-xs font-bold text-accent-primary-light">{step.sequence}</span>
                        <span className="text-sm font-medium text-text-primary">{step.step_name}</span>
                        <div className="ml-auto flex flex-wrap gap-1">
                          {step.l4_codes.map(code => <span key={code} className="rounded bg-bg-overlay px-2 py-1 font-mono text-[10px] text-text-secondary">{code}</span>)}
                        </div>
                      </div>
                      {step.activities.length > 0 && <div className="mt-2 space-y-1 pl-9">{step.activities.map((activity, activityIndex) => <p key={activityIndex} className="text-xs text-text-muted">{activity}</p>)}</div>}
                      <p className="mt-2 text-right text-[10px] text-text-muted">蓝图第 {step.source_line} 行</p>
                    </div>
                    {decisions.map(decision => (
                      <div key={decision.decision_id} className="my-3 rounded-xl border border-amber-400/35 bg-amber-400/5 p-4">
                        <p className="text-center text-sm font-medium text-amber-200">◇ {decision.question}？</p>
                        <div className="mt-3 grid gap-2 sm:grid-cols-2">
                          {decision.branches.map((branch, branchIndex) => (
                            <div key={`${branch.label}-${branchIndex}`} className={`rounded-lg border px-3 py-2 text-xs ${branch.is_return ? 'border-rose-400/30 bg-rose-400/5' : 'border-border-default bg-bg-surface'}`}>
                              <span className="font-medium text-text-primary">{branch.label}</span>
                              <span className="mx-1 text-text-muted">→</span>
                              <span className="text-text-secondary">{branch.target_text}</span>
                              <p className="mt-1 text-[10px] text-text-muted">蓝图第 {branch.source_line} 行</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                    {index < model.blueprint.steps.length - 1 && <div className="flex justify-center py-1"><ArrowDown className="h-4 w-4 text-text-muted" /></div>}
                  </div>
                )
              })}
            </div>
          </>
        ) : (
          <div className="mt-4 rounded-xl border border-amber-400/25 bg-amber-400/5 p-4">
            <p className="text-sm font-medium text-amber-200">当前不生成流程图：{model.blueprint.structure_status}</p>
            <p className="mt-1 text-xs leading-5 text-text-secondary">{model.blueprint.note}</p>
            {Boolean(model.blueprint.diagnostics?.missing_in_blueprint?.length) && (
              <p className="mt-2 text-xs text-text-muted">数据库存在但蓝图未覆盖：{model.blueprint.diagnostics.missing_in_blueprint?.join('、')}</p>
            )}
          </div>
        )}
      </section>

      <section className="panel p-5">
        <div className="flex items-center gap-2"><Layers3 className="h-4 w-4 text-accent-primary-light" /><h2 className="text-sm font-semibold">L4 交付物地图</h2></div>
        <p className="mt-2 text-xs text-text-muted">围绕 L3 目标查看交付物、数据库 Tier 和人工介入点。当前蓝图为 {model.blueprint.structure_status}，因此不展示未经正文解析的流程箭头。</p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {model.l4s.map(l4 => (
            <div key={l4.l4_code} className="rounded-xl border border-border-default bg-bg-surface p-4">
              <div className="flex items-center justify-between gap-3"><span className="font-mono text-[11px] text-accent-primary-light">{l4.l4_code}</span><span className="rounded bg-bg-overlay px-2 py-1 text-[10px] text-text-secondary">{l4.tier || '未评估'}</span></div>
              <p className="mt-2 text-sm font-medium">{l4.deliverable || l4.l4_name}</p>
              <p className="mt-1 text-xs text-text-muted">{l4.l4_name}</p>
              {l4.human_touchpoint && <p className="mt-2 text-xs text-text-secondary">人工介入：{l4.human_touchpoint}</p>}
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2"><Bot className="h-4 w-4 text-accent-primary-light" /><h2 className="text-sm font-semibold">工作坊任务卡片墙</h2></div>
            <p className="mt-2 text-xs text-text-muted">初始位置来自数据库；拖动后的差异仅是本机工作坊共识，不会写回权威库。</p>
          </div>
          <div className="flex gap-2">
            <button onClick={reset} className="flex items-center gap-1.5 rounded-lg border border-border-default px-3 py-2 text-xs text-text-muted hover:text-text-primary"><RotateCcw className="h-3.5 w-3.5" />恢复数据库位置</button>
            <button onClick={persist} className="flex items-center gap-1.5 rounded-lg bg-accent-primary px-3 py-2 text-xs text-white"><Save className="h-3.5 w-3.5" />保存到本机</button>
          </div>
        </div>
        {session.baseSnapshotHash && session.baseSnapshotHash !== model.snapshot_hash && (
          <div className="mt-4 rounded-xl border border-rose-400/30 bg-rose-400/5 p-3 text-xs text-rose-200">
            这份本机工作坊草稿基于旧模型快照。系统不会自动合并；请先对照新数据，再保存为当前版本或恢复数据库位置。
          </div>
        )}

        <div className="mt-4 grid gap-3 lg:grid-cols-4">
          {COLUMNS.map(column => (
            <div key={column.id} onDragOver={event => event.preventDefault()} onDrop={event => moveCard(event.dataTransfer.getData('text/l4'), column.id)} className={`min-h-48 rounded-xl border p-3 ${column.color}`}>
              <div className="mb-3 flex items-center justify-between"><h3 className="text-sm font-semibold">{column.label}</h3><span className="text-xs text-text-muted">{cards.filter(card => card.placement === column.id).length}</span></div>
              <div className="space-y-2">
                {cards.filter(card => card.placement === column.id).map(card => (
                  <article key={card.l4_code} draggable onDragStart={event => event.dataTransfer.setData('text/l4', card.l4_code)} className="cursor-grab rounded-lg border border-border-default bg-bg-elevated p-3 active:cursor-grabbing">
                    <div className="flex gap-2"><GripVertical className="mt-0.5 h-4 w-4 shrink-0 text-text-muted" /><div><p className="text-xs font-medium text-text-primary">{card.deliverable || card.l4_name}</p><p className="mt-1 font-mono text-[10px] text-text-muted">{card.l4_code}</p></div></div>
                    {card.changed && <p className="mt-2 rounded bg-violet-400/10 px-2 py-1 text-[10px] text-violet-300">工作坊共识假设 · 数据库原位置：{card.tier}</p>}
                    <select aria-label={`调整 ${card.l4_code} 的工作坊位置`} value={card.placement} onChange={event => moveCard(card.l4_code, event.target.value)} className="mt-2 w-full rounded border border-border-default bg-bg-surface px-2 py-1 text-[10px] text-text-secondary lg:hidden">
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

      <div className="flex items-start gap-2 rounded-xl border border-sky-400/20 bg-sky-400/5 p-4 text-xs text-sky-200">
        <Info className="mt-0.5 h-4 w-4 shrink-0" />
        <span>本页业务事实来自 process_analytics 快照，共 {model.evidence_registry.length} 条字段证据。浏览器保存内容属于 CONSENSUS 层，不参与 Gate 自动判断。</span>
      </div>
    </div>
  )
}
