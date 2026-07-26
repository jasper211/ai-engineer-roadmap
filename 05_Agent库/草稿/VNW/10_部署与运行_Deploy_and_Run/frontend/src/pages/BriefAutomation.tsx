import { useState } from 'react'
import { motion } from 'framer-motion'
import { loadAllData } from '@/lib/data'
import { ChevronDown, ChevronUp, Info } from 'lucide-react'

const TIER_COLORS: Record<string, string> = {
  Auto: '#34D399',
  Aug: '#38BDF8',
  Hybrid: '#FBBF24',
  Human: '#64748B',
}
const TIER_LABELS: Record<string, string> = {
  Auto: 'Auto·可全自动',
  Aug: 'Aug·AI辅助人',
  Hybrid: 'Hybrid·人机协同',
  Human: 'Human·仍需人工',
}

export default function BriefAutomation() {
  const [data, setData] = useState<any>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  useState(() => {
    if (!data) loadAllData().then(setData)
  })

  if (!data) return <div className="flex min-h-[60vh] items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" /></div>

  const agents = data.candidate_agents || []
  const l4s = data.l4_tier || []
  const tierTotals = ['Auto', 'Aug', 'Hybrid', 'Human'].map(t => ({
    tier: t,
    count: l4s.filter((x: any) => x.automation_tier === t).length,
  }))
  const total = l4s.length

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <h1 className="font-heading text-2xl font-bold text-text-primary">自动化评估全景(L4级)</h1>
        <p className="mt-1 text-sm text-text-secondary">
          全域368条L4业务活动的自动化程度理论判断,按候选Agent归属分组展示。
        </p>
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-accent-warning/30 bg-accent-warning/5 px-3 py-2 text-xs text-accent-warning">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>这是L4活动颗粒度的评估,目前还无法可靠地关联回具体价值节点——两套编码体系(节点用EQ/PAY等8个域,L4活动用13个业务板块标签)对不上号,不在节点详情页里编造关联。看某个节点该往哪个方向自动化,先看节点自己的熔断/四标签风险结论,这里只作全域参考。</span>
        </div>
      </motion.div>

      <div className="rounded-xl border border-border-default bg-bg-elevated p-5">
        <p className="text-sm font-medium text-text-primary">全域Tier分布</p>
        <div className="mt-3 flex h-3 overflow-hidden rounded-full">
          {tierTotals.map(t => (
            <div key={t.tier} style={{ width: `${(t.count / total) * 100}%`, backgroundColor: TIER_COLORS[t.tier] }} />
          ))}
        </div>
        <div className="mt-3 flex flex-wrap gap-4">
          {tierTotals.map(t => (
            <div key={t.tier} className="flex items-center gap-1.5 text-xs text-text-secondary">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: TIER_COLORS[t.tier] }} />
              {TIER_LABELS[t.tier]} · {t.count}
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {agents.map((agent: any, i: number) => {
          const agentL4s = l4s.filter((x: any) => x.candidate_agent === agent.candidate_agent)
          const isOpen = expanded === agent.candidate_agent
          return (
            <motion.div key={agent.candidate_agent} className="rounded-xl border border-border-default bg-bg-elevated p-4"
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.03, 0.4) }}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold text-text-primary">{agent.candidate_agent}</h3>
                  <p className="mt-0.5 text-xs text-text-muted">{agent.positioning_type} · 覆盖{agent.l4_coverage_count}条L4活动</p>
                </div>
                <span className="shrink-0 rounded-full bg-accent-primary/10 px-2 py-0.5 text-xs text-accent-primary-light">Hybrid+Human占比{agent.hybrid_human_ratio}</span>
              </div>
              <div className="mt-3 flex h-2 overflow-hidden rounded-full">
                {(['auto_count', 'aug_count', 'hybrid_count', 'human_count'] as const).map((k, idx) => {
                  const tier = ['Auto', 'Aug', 'Hybrid', 'Human'][idx]
                  const c = agent[k] || 0
                  return c > 0 ? <div key={k} style={{ width: `${(c / agent.l4_coverage_count) * 100}%`, backgroundColor: TIER_COLORS[tier] }} /> : null
                })}
              </div>
              <button onClick={() => setExpanded(isOpen ? null : agent.candidate_agent)}
                className="mt-3 flex items-center gap-1 text-xs text-accent-primary hover:underline">
                {isOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                {isOpen ? '收起' : `展开${agentL4s.length}条L4明细`}
              </button>
              {isOpen && (
                <div className="mt-3 max-h-60 space-y-1.5 overflow-y-auto rounded-lg border border-border-default bg-bg-surface p-2">
                  {agentL4s.map((l: any) => (
                    <div key={l.l4_code} className="flex items-center justify-between gap-2 text-xs">
                      <span className="truncate text-text-secondary">{l.l4_activity}</span>
                      <span className="shrink-0 rounded px-1.5 py-0.5" style={{ backgroundColor: `${TIER_COLORS[l.automation_tier]}22`, color: TIER_COLORS[l.automation_tier] }}>{l.automation_tier}</span>
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}
