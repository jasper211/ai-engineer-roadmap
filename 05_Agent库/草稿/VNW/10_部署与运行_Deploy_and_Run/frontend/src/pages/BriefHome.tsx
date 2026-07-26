import { useState } from 'react'
import { useNavigate } from 'react-router'
import { motion } from 'framer-motion'
import { loadAllData, DOMAINS, getDomainInfo } from '@/lib/data'
import { StatusBadge } from '@/components/StatusBadge'
import { Search, ChevronRight, FlaskConical } from 'lucide-react'

export default function BriefHome() {
  const navigate = useNavigate()
  const [data, setData] = useState<any>(null)
  const [search, setSearch] = useState('')
  const [domainFilter, setDomainFilter] = useState('')

  useState(() => {
    if (!data) loadAllData().then(setData)
  })

  const nodes = data?.node_index || []
  const fusedMap: Record<string, any> = {}
  ;(data?.fused_status || []).forEach((f: any) => { fusedMap[f.node_id] = f })
  const handoffMap: Record<string, any> = {}
  ;(data?.ait_handoff || []).forEach((h: any) => { handoffMap[h.node_id] = h })

  const filtered = nodes.filter((n: any) => {
    const matchSearch = !search || n.node_id?.toLowerCase().includes(search.toLowerCase()) || n.node_name?.includes(search)
    const matchDomain = !domainFilter || n.domain === domainFilter
    return matchSearch && matchDomain
  })

  if (!data) return <div className="flex min-h-[60vh] items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" /></div>

  const fusedCount = (data.fused_status || []).filter((f: any) => f.fused_status === '熔断').length
  const pilotCount = (data.ait_handoff || []).filter((h: any) => h.pilot_flag === 'TRUE').length

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <h1 className="font-heading text-2xl font-bold text-text-primary">价值节点浏览</h1>
        <p className="mt-1 text-sm text-text-secondary">
          每个节点是否已具备可自动化/搭建Skill的条件、当前流程背景、以及是否需要下线验证——一目了然。
        </p>
      </motion.div>

      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg border border-border-default bg-bg-elevated p-4">
          <p className="font-mono text-2xl font-medium text-text-primary">{nodes.length}</p>
          <p className="mt-1 text-xs text-text-muted">全部节点</p>
        </div>
        <div className="rounded-lg border border-border-default bg-bg-elevated p-4">
          <p className="font-mono text-2xl font-medium text-accent-danger">{fusedCount}</p>
          <p className="mt-1 text-xs text-text-muted">熔断中(规则未就绪)</p>
        </div>
        <div className="rounded-lg border border-border-default bg-bg-elevated p-4">
          <p className="font-mono text-2xl font-medium text-accent-primary-light">{pilotCount}</p>
          <p className="mt-1 text-xs text-text-muted">已进入AIT试点</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
          <input type="text" value={search} onChange={e => setSearch(e.target.value)}
            placeholder="搜索节点ID或名称..." className="h-9 w-56 rounded-md border border-border-default bg-bg-surface pl-9 pr-3 text-sm text-text-primary outline-none placeholder:text-text-muted focus:border-accent-primary" />
        </div>
        <select value={domainFilter} onChange={e => setDomainFilter(e.target.value)}
          className="h-9 rounded-md border border-border-default bg-bg-surface px-3 text-sm text-text-primary outline-none focus:border-accent-primary">
          <option value="">全部业务域</option>
          {DOMAINS.map(d => <option key={d.code} value={d.code}>{d.name}</option>)}
        </select>
        <span className="ml-auto text-xs text-text-muted">{filtered.length}/{nodes.length}</span>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map((node: any, i: number) => {
          const dInfo = getDomainInfo(node.node_id)
          const fused = fusedMap[node.node_id]
          const handoff = handoffMap[node.node_id]
          return (
            <motion.div key={node.node_id} className="group cursor-pointer rounded-lg border border-border-default bg-bg-elevated p-4"
              style={{ borderTopWidth: 3, borderTopColor: dInfo.color }}
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.02, 0.4) }}
              whileHover={{ y: -2, boxShadow: '0 8px 32px rgba(0,0,0,0.3)' }}
              onClick={() => navigate(`/brief/node/${node.node_id}`)}>
              <div className="flex items-center justify-between">
                <span className="rounded bg-bg-surface px-2 py-0.5 font-mono text-xs text-text-muted">{node.node_id}</span>
                <ChevronRight className="h-4 w-4 text-text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
              <h3 className="mt-2 truncate text-sm font-semibold text-text-primary">{node.node_name}</h3>
              <div className="mt-1 flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: dInfo.color }} />
                <span className="text-xs text-text-secondary">{node.domain} · {node.l3_flow}</span>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {fused && <StatusBadge status={fused.fused_status} />}
                {handoff?.pilot_flag === 'TRUE' && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-accent-primary/10 px-2 py-0.5 text-xs text-accent-primary-light">
                    <FlaskConical className="h-3 w-3" /> AIT试点
                  </span>
                )}
              </div>
            </motion.div>
          )
        })}
      </div>

      {filtered.length === 0 && (
        <div className="flex min-h-[30vh] flex-col items-center justify-center text-center">
          <Search className="mb-3 h-12 w-12 text-text-muted" />
          <p className="text-text-secondary">未找到匹配节点</p>
        </div>
      )}
    </div>
  )
}
