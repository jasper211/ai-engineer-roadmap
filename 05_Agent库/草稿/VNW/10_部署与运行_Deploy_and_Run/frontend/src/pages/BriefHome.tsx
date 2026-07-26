import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { motion } from 'framer-motion'
import { loadAllData, DOMAINS, getDomainInfo } from '@/lib/data'
import { StatusBadge } from '@/components/StatusBadge'
import { Search, ChevronRight, FlaskConical, CircleHelp, ShieldCheck } from 'lucide-react'

export default function BriefHome() {
  const navigate = useNavigate()
  const [data, setData] = useState<any>(null)
  const [search, setSearch] = useState('')
  const [domainFilter, setDomainFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'fused' | 'ready' | 'ait'>('all')

  useEffect(() => { loadAllData().then(setData) }, [])

  const nodes = data?.node_index || []
  const fusedMap: Record<string, any> = {}
  ;(data?.fused_status || []).forEach((f: any) => { fusedMap[f.node_id] = f })
  const handoffMap: Record<string, any> = {}
  ;(data?.ait_handoff || []).forEach((h: any) => { handoffMap[h.node_id] = h })

  const filtered = nodes.filter((n: any) => {
    const matchSearch = !search || n.node_id?.toLowerCase().includes(search.toLowerCase()) || n.node_name?.includes(search)
    const matchDomain = !domainFilter || n.domain === domainFilter
    const fused = fusedMap[n.node_id]?.fused_status === '熔断'
    const ait = handoffMap[n.node_id]?.pilot_flag === 'TRUE' || handoffMap[n.node_id]?.handoff_status === '已移交'
    const matchStatus = statusFilter === 'all'
      || (statusFilter === 'fused' && fused)
      || (statusFilter === 'ready' && !fused && !ait)
      || (statusFilter === 'ait' && ait)
    return matchSearch && matchDomain && matchStatus
  })

  if (!data) return <div className="flex min-h-[60vh] items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" /></div>

  const fusedCount = (data.fused_status || []).filter((f: any) => f.fused_status === '熔断').length
  const pilotCount = (data.ait_handoff || []).filter((h: any) => h.pilot_flag === 'TRUE').length
  const readyCount = nodes.filter((node: any) =>
    fusedMap[node.node_id]?.fused_status !== '熔断'
    && handoffMap[node.node_id]?.pilot_flag !== 'TRUE'
    && handoffMap[node.node_id]?.handoff_status !== '已移交'
  ).length

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent-primary-light">先看结论，再决定是否验证</p>
        <h1 className="mt-2 font-heading text-2xl font-bold text-text-primary">哪些业务交付物值得做成 AI 工具？</h1>
        <p className="mt-1 text-sm text-text-secondary">
          选择一个价值节点，查看自动化或 Skill 机会、流程现状和证据，再决定是否交给 AIT 继续设计。
        </p>
      </motion.div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatFilter active={statusFilter === 'all'} onClick={() => setStatusFilter('all')} value={nodes.length} label="全部机会" />
        <StatFilter active={statusFilter === 'fused'} onClick={() => setStatusFilter('fused')} value={fusedCount} label="熔断 · 先补建" tone="danger" />
        <StatFilter active={statusFilter === 'ready'} onClick={() => setStatusFilter('ready')} value={readyCount} label="可进入验证" tone="success" />
        <StatFilter active={statusFilter === 'ait'} onClick={() => setStatusFilter('ait')} value={pilotCount} label="AIT · 已承接" tone="primary" />
        {/* 数字卡同时也是筛选标签，避免再增加一层导航。 */}
        <div className="hidden rounded-lg border border-border-default bg-bg-elevated p-4">
          <p className="font-mono text-2xl font-medium text-text-primary">{nodes.length}</p>
          <p className="mt-1 text-xs text-text-muted">全部节点</p>
        </div>
        <div className="hidden rounded-lg border border-border-default bg-bg-elevated p-4">
          <p className="font-mono text-2xl font-medium text-accent-danger">{fusedCount}</p>
          <p className="mt-1 text-xs text-text-muted">需先补齐规则</p>
        </div>
        <div className="hidden rounded-lg border border-border-default bg-bg-elevated p-4">
          <p className="font-mono text-2xl font-medium text-accent-primary-light">{pilotCount}</p>
          <p className="mt-1 text-xs text-text-muted">已进入 AIT</p>
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
          const ready = fused?.fused_status === '非熔断'
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
                {ready ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-accent-success/10 px-2 py-0.5 text-xs text-accent-success">
                    <ShieldCheck className="h-3 w-3" /> 可进入业务验证
                  </span>
                ) : fused ? (
                  <StatusBadge status={fused.fused_status} />
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full bg-bg-surface px-2 py-0.5 text-xs text-text-muted">
                    <CircleHelp className="h-3 w-3" /> 待评估
                  </span>
                )}
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

function StatFilter({ active, onClick, value, label, tone = 'default' }: { active: boolean; onClick: () => void; value: number; label: string; tone?: 'default' | 'danger' | 'success' | 'primary' }) {
  const toneClass = {
    default: 'text-text-primary',
    danger: 'text-accent-danger',
    success: 'text-accent-success',
    primary: 'text-accent-primary-light',
  }[tone]
  return (
    <button onClick={onClick} className={`rounded-lg border bg-bg-elevated p-4 text-left transition-colors ${active ? 'border-accent-primary ring-1 ring-accent-primary/30' : 'border-border-default hover:border-text-muted'}`}>
      <p className={`font-mono text-2xl font-medium ${toneClass}`}>{value}</p>
      <p className="mt-1 text-xs text-text-muted">{label}</p>
    </button>
  )
}
