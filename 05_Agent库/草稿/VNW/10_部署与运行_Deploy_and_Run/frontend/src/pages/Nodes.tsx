import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router'
import { motion, AnimatePresence } from 'framer-motion'
import { loadAllData, getDomainInfo, DOMAINS } from '@/lib/data'
import { StatusBadge } from '@/components/StatusBadge'
import { Search, Grid3X3, List, Download, X, ChevronRight, Layers } from 'lucide-react'

export default function Nodes() {
  const navigate = useNavigate()
  const [data, setData] = useState<any>(null)
  const [search, setSearch] = useState('')
  const [domainFilter, setDomainFilter] = useState('')
  const [view, setView] = useState<'grid'|'list'>('grid')

  useState(() => {
    if (!data) loadAllData().then(setData)
  })

  // 2026-07-25修复:useMemo原来写在'if (!data) return'这个提前返回之后,违反Hooks规则
  // (首次渲染data为null会提前return跳过useMemo,数据到位后的渲染又会调用它,两次渲染
  // hooks数量不一致,React会直接崩溃整个页面变黑屏)。改成所有hooks都在提前返回之前调用。
  const nodes = data?.node_index || []
  const fusedMap: Record<string, string> = {}
  ;(data?.fused_status || []).forEach((f: any) => { fusedMap[f.node_id] = f.fused_status })

  const filtered = useMemo(() => {
    return nodes.filter((n: any) => {
      const matchSearch = !search || n.node_id?.toLowerCase().includes(search.toLowerCase()) || n.node_name?.includes(search)
      const matchDomain = !domainFilter || n.domain === domainFilter
      return matchSearch && matchDomain
    })
  }, [nodes, search, domainFilter])

  if (!data) return <div className="flex min-h-[60vh] items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" /></div>

  const nodeRelCounts = (nodeId: string) => {
    return {
      rules: (data.rules || []).filter((r: any) => r.node_id === nodeId).length,
      actions: (data.actions || []).filter((a: any) => a.node_id === nodeId).length,
      gaps: (data.gaps || []).filter((g: any) => g.node_id === nodeId).length,
      signals: (data.signals || []).filter((s: any) => s.node_id === nodeId).length,
    }
  }

  return (
    <div className="space-y-4">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Layers className="h-7 w-7 text-accent-primary" />
          <h1 className="font-heading text-2xl font-bold text-text-primary">价值节点浏览器</h1>
          <span className="rounded-full bg-accent-primary/15 px-3 py-1 text-xs text-accent-primary-light">{filtered.length}/{nodes.length}</span>
        </div>
      </motion.div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
          <input type="text" value={search} onChange={e => setSearch(e.target.value)}
            placeholder="搜索节点ID或名称..." className="h-9 w-56 rounded-md border border-border-default bg-bg-surface pl-9 pr-3 text-sm text-text-primary outline-none placeholder:text-text-muted focus:border-accent-primary" />
          {search && <button onClick={() => setSearch('')} className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted"><X className="h-3.5 w-3.5" /></button>}
        </div>
        <select value={domainFilter} onChange={e => setDomainFilter(e.target.value)}
          className="h-9 rounded-md border border-border-default bg-bg-surface px-3 text-sm text-text-primary outline-none focus:border-accent-primary">
          <option value="">全部域</option>
          {DOMAINS.map(d => <option key={d.code} value={d.code}>{d.name}</option>)}
        </select>
        <div className="ml-auto flex rounded-md border border-border-default bg-bg-surface">
          <button onClick={() => setView('grid')} className={`flex items-center gap-1 rounded-l-md px-3 py-1.5 text-sm ${view==='grid'?'bg-accent-primary text-white':'text-text-secondary'}`}><Grid3X3 className="h-4 w-4"/>网格</button>
          <button onClick={() => setView('list')} className={`flex items-center gap-1 rounded-r-md px-3 py-1.5 text-sm ${view==='list'?'bg-accent-primary text-white':'text-text-secondary'}`}><List className="h-4 w-4"/>列表</button>
        </div>
      </div>

      <AnimatePresence mode="wait">
        {view === 'grid' ? (
          <motion.div key="grid" className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            {filtered.map((node: any, i: number) => {
              const dInfo = getDomainInfo(node.node_id)
              const counts = nodeRelCounts(node.node_id)
              return (
                <motion.div key={node.node_id} className="group cursor-pointer rounded-lg border border-border-default bg-bg-elevated p-4"
                  style={{ borderTopWidth: 3, borderTopColor: dInfo.color }}
                  initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i*0.02, 0.5) }}
                  whileHover={{ y: -3, boxShadow: '0 8px 32px rgba(0,0,0,0.3)' }}
                  onClick={() => navigate(`/node/${node.node_id}`)}>
                  <div className="flex items-center justify-between">
                    <span className="rounded bg-bg-surface px-2 py-0.5 font-mono text-xs text-text-muted">{node.node_id}</span>
                    <ChevronRight className="h-4 w-4 text-text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                  <h3 className="mt-2 truncate text-sm font-semibold text-text-primary">{node.node_name}</h3>
                  <div className="mt-1 flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full" style={{ backgroundColor: dInfo.color }} />
                    <span className="text-xs text-text-secondary">{node.domain}</span>
                  </div>
                  <div className="mt-1 text-xs text-text-muted">{node.l3_flow} · {node.priority}</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {counts.rules > 0 && <span className="rounded-full bg-accent-primary/10 px-2 py-0.5 text-xs text-accent-primary-light">规则 {counts.rules}</span>}
                    {counts.signals > 0 && <span className="rounded-full bg-accent-secondary/10 px-2 py-0.5 text-xs text-accent-secondary">信号 {counts.signals}</span>}
                    {counts.actions > 0 && <span className="rounded-full bg-accent-warning/10 px-2 py-0.5 text-xs text-accent-warning">行动 {counts.actions}</span>}
                    {counts.gaps > 0 && <span className="rounded-full bg-accent-danger/10 px-2 py-0.5 text-xs text-accent-danger">Gap {counts.gaps}</span>}
                  </div>
                </motion.div>
              )
            })}
          </motion.div>
        ) : (
          <motion.div key="list" className="overflow-hidden rounded-lg border border-border-default" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <table className="w-full">
              <thead><tr className="border-b border-border-default bg-bg-surface">
                <th className="px-4 py-3 text-left text-xs font-semibold text-text-primary">节点ID</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-text-primary">名称</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-text-primary">域</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-text-primary">L3流程</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-text-primary">优先级</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-text-primary">状态</th>
              </tr></thead>
              <tbody>
                {filtered.map((node: any, i: number) => (
                  <motion.tr key={node.node_id} className="cursor-pointer border-b border-border-default hover:bg-bg-surface"
                    initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: Math.min(i*0.01, 0.3) }}
                    onClick={() => navigate(`/node/${node.node_id}`)}>
                    <td className="px-4 py-3 font-mono text-sm text-accent-primary-light">{node.node_id}</td>
                    <td className="px-4 py-3 text-sm text-text-primary">{node.node_name}</td>
                    <td className="px-4 py-3 text-sm text-text-secondary">{node.domain}</td>
                    <td className="px-4 py-3 text-sm text-text-secondary">{node.l3_flow}</td>
                    <td className="px-4 py-3"><span className={`text-xs font-bold ${node.priority==='P0'?'text-red-400':node.priority==='P1'?'text-amber-400':'text-blue-400'}`}>{node.priority}</span></td>
                    <td className="px-4 py-3"><StatusBadge status={fusedMap[node.node_id] || '未判定'} /></td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </motion.div>
        )}
      </AnimatePresence>

      {filtered.length === 0 && (
        <div className="flex min-h-[30vh] flex-col items-center justify-center text-center">
          <Search className="mb-3 h-12 w-12 text-text-muted" />
          <p className="text-text-secondary">未找到匹配节点</p>
        </div>
      )}
    </div>
  )
}
