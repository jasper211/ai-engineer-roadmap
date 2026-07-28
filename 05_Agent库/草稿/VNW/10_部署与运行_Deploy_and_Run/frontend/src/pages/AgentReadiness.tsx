import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { loadAllData } from '@/lib/data'
import { Bot, ChevronDown, ChevronUp, Info } from 'lucide-react'

const TYPE_COLORS: Record<string, string> = {
  Auto: 'bg-green-500', Aug: 'bg-blue-500', Hybrid: 'bg-amber-500',
}
const STATUS_COLORS: Record<string, string> = {
  '已上线': 'text-accent-success', '开发中': 'text-accent-primary-light',
  '规划中': 'text-text-muted', '已停用': 'text-accent-danger',
}

export default function AgentReadiness() {
  const [data, setData] = useState<any>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  useEffect(() => { loadAllData().then(setData) }, [])

  if (!data) return <div className="flex min-h-[60vh] items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" /></div>

  const agents = data.candidate_agents || []
  const total = agents.length
  const byType: Record<string, number> = {}
  const byStatus: Record<string, number> = {}
  const byL3: Record<string, any[]> = {}
  agents.forEach((a: any) => {
    byType[a.agent_type] = (byType[a.agent_type] || 0) + 1
    byStatus[a.agent_status] = (byStatus[a.agent_status] || 0) + 1
    const l3 = a.l3_primary || '(未归属L3)'
    byL3[l3] = byL3[l3] || []
    byL3[l3].push(a)
  })
  const l3Groups = Object.entries(byL3).sort((a, b) => b[1].length - a[1].length)

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <div className="flex items-center gap-3">
          <Bot className="h-7 w-7 text-accent-primary" />
          <h1 className="font-heading text-2xl font-bold text-text-primary">Agent规划总览</h1>
        </div>
        <p className="mt-1 text-sm text-text-muted">T26源:数据仓库process_analytics.dim_agent——每行是"1条L4活动=1个规划中的原子级Agent",按所属L3流程分组展示。</p>
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-accent-warning/30 bg-accent-warning/5 px-3 py-2 text-xs text-accent-warning">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>2026-07-26起数据源从文件里的"30个聚合候选Agent"改为数据仓库的"361个原子级规划表"——这是两种不同的Agent组织方式,不是同一份数据的新旧版本。当前全部agent_status为"规划中",还没有已上线的。</span>
        </div>
      </motion.div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="rounded-lg border border-border-default bg-bg-elevated p-3 text-center">
          <p className="font-mono text-2xl text-text-primary">{total}</p>
          <p className="text-xs text-text-muted">规划中的Agent(L4级)</p>
        </div>
        {['Auto', 'Aug', 'Hybrid'].map(t => (
          <div key={t} className="rounded-lg border border-border-default bg-bg-elevated p-3 text-center">
            <p className={`font-mono text-2xl ${t === 'Auto' ? 'text-accent-success' : t === 'Aug' ? 'text-accent-primary-light' : 'text-accent-warning'}`}>{byType[t] || 0}</p>
            <p className="text-xs text-text-muted">{t}型</p>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap gap-2 text-xs text-text-secondary">
        {Object.entries(byStatus).map(([status, count]) => (
          <span key={status} className={`rounded-full bg-bg-surface px-2.5 py-1 ${STATUS_COLORS[status] || ''}`}>{status} · {count}</span>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {l3Groups.map(([l3Code, rows], i) => {
          const isOpen = expanded === l3Code
          const typeCounts = { Auto: 0, Aug: 0, Hybrid: 0 } as Record<string, number>
          rows.forEach(r => { typeCounts[r.agent_type] = (typeCounts[r.agent_type] || 0) + 1 })
          return (
            <motion.div key={l3Code} className="rounded-lg border border-border-default bg-bg-elevated p-4"
              initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.03, 0.4) }}>
              <div className="flex items-center justify-between">
                <h3 className="font-heading text-sm font-semibold text-text-primary">{l3Code}</h3>
                <span className="rounded-full bg-accent-primary/10 px-2 py-0.5 text-xs text-accent-primary-light">{rows.length}个Agent</span>
              </div>
              <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-bg-surface">
                {(['Auto', 'Aug', 'Hybrid'] as const).map(t => {
                  const pct = rows.length > 0 ? (typeCounts[t] / rows.length) * 100 : 0
                  return pct > 0 ? <div key={t} className={TYPE_COLORS[t]} style={{ width: `${pct}%` }} title={`${t}: ${typeCounts[t]}`} /> : null
                })}
              </div>
              <div className="mt-2 flex flex-wrap gap-3 text-xs text-text-secondary">
                <span><span className="inline-block h-2 w-2 rounded-full bg-green-500 mr-1" />Auto {typeCounts.Auto || 0}</span>
                <span><span className="inline-block h-2 w-2 rounded-full bg-blue-500 mr-1" />Aug {typeCounts.Aug || 0}</span>
                <span><span className="inline-block h-2 w-2 rounded-full bg-amber-500 mr-1" />Hybrid {typeCounts.Hybrid || 0}</span>
              </div>

              <button onClick={() => setExpanded(isOpen ? null : l3Code)}
                className="mt-3 flex items-center gap-1 text-xs text-accent-primary hover:text-accent-primary-light">
                {isOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                {isOpen ? '收起明细' : `展开${rows.length}个Agent明细`}
              </button>

              {isOpen && (
                <div className="mt-3 overflow-x-auto rounded-lg border border-border-default">
                  <table className="w-full">
                    <thead><tr className="border-b border-border-default bg-bg-surface">
                      <th className="px-2 py-1.5 text-left text-xs font-semibold text-text-primary">Agent编码</th>
                      <th className="px-2 py-1.5 text-left text-xs font-semibold text-text-primary">对应L4活动</th>
                      <th className="px-2 py-1.5 text-left text-xs font-semibold text-text-primary">类型</th>
                      <th className="px-2 py-1.5 text-left text-xs font-semibold text-text-primary">状态</th>
                    </tr></thead>
                    <tbody>
                      {rows.map((a: any, j: number) => (
                        <tr key={j} className="border-b border-border-default hover:bg-bg-surface">
                          <td className="px-2 py-1.5 font-mono text-xs text-accent-primary-light">{a.agent_code}</td>
                          <td className="px-2 py-1.5 text-xs text-text-secondary">{a.agent_name}</td>
                          <td className="px-2 py-1.5 text-xs text-text-secondary">{a.agent_type}</td>
                          <td className={`px-2 py-1.5 text-xs ${STATUS_COLORS[a.agent_status] || 'text-text-secondary'}`}>{a.agent_status}</td>
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
