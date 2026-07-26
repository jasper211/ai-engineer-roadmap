import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { loadAllData } from '@/lib/data'
import { Bot, ChevronDown, ChevronUp } from 'lucide-react'

const TIER_COLORS: Record<string, string> = {
  Auto: 'bg-green-500', Aug: 'bg-blue-500', Hybrid: 'bg-amber-500', Human: 'bg-bg-surface',
}

export default function AgentReadiness() {
  const [data, setData] = useState<any>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  useEffect(() => { loadAllData().then(setData) }, [])

  if (!data) return <div className="flex min-h-[60vh] items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" /></div>

  const agents = data.candidate_agents || []
  const l4Rows = data.l4_tier || []
  const totalL4 = l4Rows.length

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <div className="flex items-center gap-3">
          <Bot className="h-7 w-7 text-accent-primary" />
          <h1 className="font-heading text-2xl font-bold text-text-primary">候选Agent与自动化就绪度</h1>
        </div>
        <p className="mt-1 text-sm text-text-muted">T26候选Agent汇总 + T20 L4自动化Tier评估(来自Agent与Skill体系方法论,是全域L4流程的理论打分,不是VNW已验证的真实产出)</p>
      </motion.div>

      {/* Summary */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="rounded-lg border border-border-default bg-bg-elevated p-3 text-center">
          <p className="font-mono text-2xl text-text-primary">{agents.length}</p>
          <p className="text-xs text-text-muted">候选Agent</p>
        </div>
        <div className="rounded-lg border border-border-default bg-bg-elevated p-3 text-center">
          <p className="font-mono text-2xl text-text-primary">{totalL4}</p>
          <p className="text-xs text-text-muted">L4流程总数</p>
        </div>
        <div className="rounded-lg border border-border-default bg-bg-elevated p-3 text-center">
          <p className="font-mono text-2xl text-accent-success">{agents.filter((a: any) => a.positioning_type === '自动化执行型').length}</p>
          <p className="text-xs text-text-muted">自动化执行型</p>
        </div>
        <div className="rounded-lg border border-border-default bg-bg-elevated p-3 text-center">
          <p className="font-mono text-2xl text-accent-warning">{agents.filter((a: any) => a.positioning_type === '决策支持/协同型').length}</p>
          <p className="text-xs text-text-muted">决策支持/协同型</p>
        </div>
      </div>

      {/* Agent Cards */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {agents.map((a: any, i: number) => {
          const isOpen = expanded === a.candidate_agent
          const agentL4s = l4Rows.filter((l: any) => l.candidate_agent === a.candidate_agent)
          const isAuto = a.positioning_type === '自动化执行型'
          return (
            <motion.div key={a.candidate_agent} className="rounded-lg border border-border-default bg-bg-elevated p-4"
              style={{ borderTopWidth: 3, borderTopColor: isAuto ? '#34D399' : '#FBBF24' }}
              initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-heading text-sm font-semibold text-text-primary">{a.candidate_agent}</h3>
                  <p className="text-xs text-text-muted">{a.positioning_type} · Hybrid+Human占比 {a.hybrid_human_ratio}</p>
                </div>
                <span className="rounded-full bg-accent-primary/10 px-2 py-0.5 text-xs text-accent-primary-light">{a.l4_coverage_count}条L4</span>
              </div>

              {/* Tier distribution bar */}
              <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-bg-surface">
                {['auto_count', 'aug_count', 'hybrid_count', 'human_count'].map((key) => {
                  const tier = key.replace('_count', '').replace(/^./, c => c.toUpperCase())
                  const count = Number(a[key] || 0)
                  const pct = a.l4_coverage_count > 0 ? (count / a.l4_coverage_count) * 100 : 0
                  return pct > 0 ? <div key={key} className={TIER_COLORS[tier]} style={{ width: `${pct}%` }} title={`${tier}: ${count}`} /> : null
                })}
              </div>
              <div className="mt-2 flex flex-wrap gap-3 text-xs text-text-secondary">
                <span><span className="inline-block h-2 w-2 rounded-full bg-green-500 mr-1" />Auto {a.auto_count}</span>
                <span><span className="inline-block h-2 w-2 rounded-full bg-blue-500 mr-1" />Aug {a.aug_count}</span>
                <span><span className="inline-block h-2 w-2 rounded-full bg-amber-500 mr-1" />Hybrid {a.hybrid_count}</span>
                <span><span className="inline-block h-2 w-2 rounded-full bg-bg-surface border border-border-default mr-1" />Human {a.human_count}</span>
              </div>
              {(Number(a.funds_safety_gate_count) > 0 || Number(a.physical_execution_count) > 0) && (
                <div className="mt-2 flex gap-3 text-xs text-accent-danger">
                  {Number(a.funds_safety_gate_count) > 0 && <span>资金安全关卡×{a.funds_safety_gate_count}</span>}
                  {Number(a.physical_execution_count) > 0 && <span>物理执行×{a.physical_execution_count}</span>}
                </div>
              )}

              <button onClick={() => setExpanded(isOpen ? null : a.candidate_agent)}
                className="mt-3 flex items-center gap-1 text-xs text-accent-primary hover:text-accent-primary-light">
                {isOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                {isOpen ? '收起L4明细' : `展开${agentL4s.length}条L4明细`}
              </button>

              {isOpen && (
                <div className="mt-3 overflow-x-auto rounded-lg border border-border-default">
                  <table className="w-full">
                    <thead><tr className="border-b border-border-default bg-bg-surface">
                      <th className="px-2 py-1.5 text-left text-xs font-semibold text-text-primary">L4编码</th>
                      <th className="px-2 py-1.5 text-left text-xs font-semibold text-text-primary">L4活动</th>
                      <th className="px-2 py-1.5 text-left text-xs font-semibold text-text-primary">Tier</th>
                    </tr></thead>
                    <tbody>
                      {agentL4s.map((l: any, j: number) => (
                        <tr key={j} className="border-b border-border-default hover:bg-bg-surface">
                          <td className="px-2 py-1.5 font-mono text-xs text-accent-primary-light">{l.l4_code}</td>
                          <td className="px-2 py-1.5 text-xs text-text-secondary">{l.l4_activity}</td>
                          <td className="px-2 py-1.5 text-xs text-text-secondary">{l.automation_tier}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}
