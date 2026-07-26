import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { loadAllData, DOMAINS } from '@/lib/data'
import { StatusBadge } from '@/components/StatusBadge'
import { Globe, BarChart3 } from 'lucide-react'

export default function Domains() {
  const [data, setData] = useState<any>(null)
  useEffect(() => { loadAllData().then(setData) }, [])

  if (!data) return <div className="flex min-h-[60vh] items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" /></div>

  const domainProgress = data.domain_progress || []
  const nodes = data.node_index || []

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <div className="flex items-center gap-3">
          <Globe className="h-7 w-7 text-accent-primary" />
          <h1 className="font-heading text-2xl font-bold text-text-primary">域扩展进度</h1>
        </div>
      </motion.div>

      {/* Summary */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="rounded-lg border border-border-default bg-bg-elevated p-3 text-center">
          <p className="font-mono text-2xl text-text-primary">{domainProgress.length}</p>
          <p className="text-xs text-text-muted">业务域</p>
        </div>
        <div className="rounded-lg border border-border-default bg-bg-elevated p-3 text-center">
          <p className="font-mono text-2xl text-text-primary">{nodes.length}</p>
          <p className="text-xs text-text-muted">价值节点</p>
        </div>
        <div className="rounded-lg border border-border-default bg-bg-elevated p-3 text-center">
          <p className="font-mono text-2xl text-accent-primary-light">{(data.fused_status || []).filter((f: any) => f.fused_status === '非熔断').length}</p>
          <p className="text-xs text-text-muted">非熔断节点</p>
        </div>
        <div className="rounded-lg border border-border-default bg-bg-elevated p-3 text-center">
          <p className="font-mono text-2xl text-accent-danger">{(data.gaps || []).filter((g: any) => g.status === 'open').length}</p>
          <p className="text-xs text-text-muted">开放Gap</p>
        </div>
      </div>

      {/* Domain Cards */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {domainProgress.map((d: any, i: number) => {
          const domainNodes = nodes.filter((n: any) => n.domain === d.domain)
          const fusedIds = new Set((data.fused_status || []).filter((f: any) => f.fused_status === '非熔断').map((f: any) => f.node_id))
          const passCount = domainNodes.filter((n: any) => fusedIds.has(n.node_id)).length
          return (
            <motion.div key={d.domain} className="rounded-lg border border-border-default bg-bg-elevated p-4"
              initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-heading text-sm font-semibold text-text-primary">{d.domain_name}</h3>
                  <p className="text-xs text-text-muted">当前阶段: {d.current_phase}</p>
                </div>
                <span className="rounded-full bg-accent-primary/10 px-2 py-0.5 text-xs text-accent-primary-light">{d.node_count}节点</span>
              </div>
              <div className="mt-3 flex items-center gap-2">
                <div className="h-2 flex-1 rounded-full bg-bg-surface">
                  <div className="h-2 rounded-full bg-accent-primary" style={{ width: `${d.node_count > 0 ? (passCount / d.node_count * 100) : 0}%` }} />
                </div>
                <span className="text-xs text-text-muted">{passCount}/{d.node_count}</span>
              </div>
              <div className="mt-3 flex gap-4 text-xs text-text-secondary">
                <span>信号基线: {d.signal_baseline}</span>
                <span>规则: v{d.rule_map_version}</span>
                <span>访谈: v{d.interview_toolkit}</span>
              </div>
              {d.notes && <p className="mt-2 text-xs text-text-muted line-clamp-2">{d.notes}</p>}
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}
