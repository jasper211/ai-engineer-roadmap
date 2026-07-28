import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { loadAllData } from '@/lib/data'
import { ChevronDown, ChevronUp, Info } from 'lucide-react'

const TIER_COLORS: Record<string, string> = {
  Auto: '#34D399',
  Aug: '#38BDF8',
  Hybrid: '#FBBF24',
}
const TIER_LABELS: Record<string, string> = {
  Auto: 'Auto·可全自动',
  Aug: 'Aug·AI辅助人',
  Hybrid: 'Hybrid·人机协同',
}

export default function BriefAutomation() {
  const [data, setData] = useState<any>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => { loadAllData().then(setData) }, [])

  if (!data) return <div className="flex min-h-[60vh] items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" /></div>

  const l4s = data.l4_tier || []
  const tierTotals = ['Auto', 'Aug', 'Hybrid'].map(t => ({
    tier: t,
    count: l4s.filter((x: any) => x.agentifiability === t).length,
  }))
  const total = l4s.length

  const byL3: Record<string, any[]> = {}
  l4s.forEach((l: any) => {
    byL3[l.l3_code] = byL3[l.l3_code] || []
    byL3[l.l3_code].push(l)
  })
  const l3Groups = Object.entries(byL3).sort((a, b) => b[1].length - a[1].length)

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <h1 className="font-heading text-2xl font-bold text-text-primary">自动化评估全景(L4级)</h1>
        <p className="mt-1 text-sm text-text-secondary">
          全域{total}条L4业务活动的自动化程度判断(数据仓库权威源),按所属L3流程分组展示。
        </p>
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-accent-warning/30 bg-accent-warning/5 px-3 py-2 text-xs text-accent-warning">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>这是L4活动颗粒度的评估,目前还无法可靠地关联回具体价值节点——两套编码体系(节点用EQ/PAY等8个域,L4活动按L3流程组织)对不上号,不在节点详情页里编造关联。看某个节点该往哪个方向自动化,先看节点自己的熔断/四标签风险结论,这里只作全域参考。</span>
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
        {l3Groups.map(([l3Code, rows], i) => {
          const isOpen = expanded === l3Code
          const l3Name = rows[0]?.l3_name || ''
          const tierCounts: Record<string, number> = {}
          rows.forEach(r => { tierCounts[r.agentifiability] = (tierCounts[r.agentifiability] || 0) + 1 })
          return (
            <motion.div key={l3Code} className="rounded-xl border border-border-default bg-bg-elevated p-4"
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.03, 0.4) }}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold text-text-primary">{l3Code} · {l3Name}</h3>
                  <p className="mt-0.5 text-xs text-text-muted">共{rows.length}条L4活动</p>
                </div>
              </div>
              <div className="mt-3 flex h-2 overflow-hidden rounded-full">
                {(['Auto', 'Aug', 'Hybrid'] as const).map((tier) => {
                  const c = tierCounts[tier] || 0
                  return c > 0 ? <div key={tier} style={{ width: `${(c / rows.length) * 100}%`, backgroundColor: TIER_COLORS[tier] }} /> : null
                })}
              </div>
              <button onClick={() => setExpanded(isOpen ? null : l3Code)}
                className="mt-3 flex items-center gap-1 text-xs text-accent-primary hover:underline">
                {isOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                {isOpen ? '收起' : `展开${rows.length}条L4明细`}
              </button>
              {isOpen && (
                <div className="mt-3 max-h-60 space-y-1.5 overflow-y-auto rounded-lg border border-border-default bg-bg-surface p-2">
                  {rows.map((l: any) => (
                    <div key={l.l4_code} className="flex items-center justify-between gap-2 text-xs">
                      <span className="truncate text-text-secondary">{l.l4_name}</span>
                      <span className="shrink-0 rounded px-1.5 py-0.5" style={{ backgroundColor: `${TIER_COLORS[l.agentifiability]}22`, color: TIER_COLORS[l.agentifiability] }}>{l.agentifiability}</span>
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
