import { useState, useEffect, useMemo } from 'react'
import { motion } from 'framer-motion'
import { loadAllData } from '@/lib/data'
import { StatusBadge, PriorityBadge } from '@/components/StatusBadge'
import { AlertCircle, Clock, Filter, Search, X, Kanban, List } from 'lucide-react'

export default function GapsActions() {
  const [data, setData] = useState<any>(null)
  const [view, setView] = useState<'kanban' | 'list'>('kanban')
  const [filterType, setFilterType] = useState<'gap' | 'action'>('gap')
  const [search, setSearch] = useState('')
  const [domainFilter, setDomainFilter] = useState('')

  useEffect(() => { loadAllData().then(setData) }, [])

  if (!data) return <div className="flex min-h-[60vh] items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" /></div>

  const gaps = data.gaps || []
  const actions = data.actions || []

  const filteredGaps = useMemo(() => {
    return gaps.filter((g: any) => {
      const matchSearch = !search || Object.values(g).some(v => String(v).toLowerCase().includes(search.toLowerCase()))
      const matchDomain = !domainFilter || g.domain === domainFilter || g.node_id?.includes(domainFilter)
      return matchSearch && matchDomain
    })
  }, [gaps, search, domainFilter])

  const filteredActions = useMemo(() => {
    return actions.filter((a: any) => {
      const matchSearch = !search || Object.values(a).some(v => String(v).toLowerCase().includes(search.toLowerCase()))
      const matchDomain = !domainFilter || a.node_id?.includes(domainFilter)
      return matchSearch && matchDomain
    })
  }, [actions, search, domainFilter])

  const p0Gaps = gaps.filter((g: any) => g.priority === 'P0' && g.status === 'open').length
  const p1Gaps = gaps.filter((g: any) => g.priority === 'P1' && g.status === 'open').length
  const p2Gaps = gaps.filter((g: any) => g.priority === 'P2' && g.status === 'open').length
  const pendingActions = actions.filter((a: any) => a.status === '待执行').length

  // Kanban columns by priority for gaps, by status for actions
  const gapColumns = [
    { key: 'P0', label: 'P0 紧急', color: 'border-red-500', items: filteredGaps.filter((g: any) => g.priority === 'P0') },
    { key: 'P1', label: 'P1 重要', color: 'border-amber-500', items: filteredGaps.filter((g: any) => g.priority === 'P1') },
    { key: 'P2', label: 'P2 一般', color: 'border-blue-500', items: filteredGaps.filter((g: any) => g.priority === 'P2') },
  ]

  const actionColumns = [
    { key: 'pending', label: '待执行', color: 'border-amber-500', items: filteredActions.filter((a: any) => a.status === '待执行') },
    { key: 'done', label: '已完成', color: 'border-green-500', items: filteredActions.filter((a: any) => a.status === '已完成' || a.status === '已关闭') },
    { key: 'other', label: '其他', color: 'border-text-muted', items: filteredActions.filter((a: any) => a.status !== '待执行' && a.status !== '已完成' && a.status !== '已关闭') },
  ]

  const columns = filterType === 'gap' ? gapColumns : actionColumns

  return (
    <div className="space-y-4">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <AlertCircle className="h-7 w-7 text-accent-primary" />
          <h1 className="font-heading text-2xl font-bold text-text-primary">Gap与行动追踪</h1>
        </div>
        <div className="flex rounded-md border border-border-default bg-bg-surface">
          <button onClick={() => setFilterType('gap')} className={`px-4 py-2 text-sm ${filterType==='gap'?'bg-accent-primary text-white':'text-text-secondary'}`}>Gap ({filteredGaps.length})</button>
          <button onClick={() => setFilterType('action')} className={`px-4 py-2 text-sm ${filterType==='action'?'bg-accent-primary text-white':'text-text-secondary'}`}>行动 ({filteredActions.length})</button>
        </div>
      </motion.div>

      {/* Alert Banner */}
      {p0Gaps > 0 && (
        <div className="flex items-center gap-3 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3">
          <AlertCircle className="h-5 w-5 shrink-0 text-red-400" />
          <span className="text-sm text-red-400">{p0Gaps} 个 P0 紧急 Gap 待处理</span>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="rounded-lg border border-border-default bg-bg-elevated p-3 text-center">
          <p className="font-mono text-xl text-red-400">{p0Gaps}</p><p className="text-xs text-text-muted">P0 Gap</p>
        </div>
        <div className="rounded-lg border border-border-default bg-bg-elevated p-3 text-center">
          <p className="font-mono text-xl text-amber-400">{p1Gaps}</p><p className="text-xs text-text-muted">P1 Gap</p>
        </div>
        <div className="rounded-lg border border-border-default bg-bg-elevated p-3 text-center">
          <p className="font-mono text-xl text-blue-400">{p2Gaps}</p><p className="text-xs text-text-muted">P2 Gap</p>
        </div>
        <div className="rounded-lg border border-border-default bg-bg-elevated p-3 text-center">
          <p className="font-mono text-xl text-accent-warning">{pendingActions}</p><p className="text-xs text-text-muted">待执行行动</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
          <input type="text" value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索..."
            className="h-9 w-56 rounded-md border border-border-default bg-bg-surface pl-9 pr-3 text-sm outline-none focus:border-accent-primary" />
        </div>
        <select value={domainFilter} onChange={e => setDomainFilter(e.target.value)}
          className="h-9 rounded-md border border-border-default bg-bg-surface px-3 text-sm outline-none focus:border-accent-primary">
          <option value="">全部域</option>
          <option value="PAY">PAY</option><option value="EQ">EQ</option><option value="HR">HR</option>
          <option value="INS">INS</option><option value="BAM">BAM</option><option value="MGA">MGA</option>
          <option value="AGT">AGT</option><option value="KA">KA</option>
        </select>
        <div className="ml-auto flex rounded-md border border-border-default bg-bg-surface">
          <button onClick={() => setView('kanban')} className={`px-3 py-1.5 text-sm ${view==='kanban'?'bg-accent-primary text-white':'text-text-secondary'}`}><Kanban className="h-4 w-4" /></button>
          <button onClick={() => setView('list')} className={`px-3 py-1.5 text-sm ${view==='list'?'bg-accent-primary text-white':'text-text-secondary'}`}><List className="h-4 w-4" /></button>
        </div>
      </div>

      {/* Kanban View */}
      {view === 'kanban' ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {columns.map(col => (
            <div key={col.key} className={`rounded-lg border-t-2 ${col.color} border-x border-b border-border-default bg-bg-elevated`}>
              <div className="flex items-center justify-between border-b border-border-default px-3 py-2">
                <span className="text-sm font-semibold text-text-primary">{col.label}</span>
                <span className="rounded-full bg-bg-surface px-2 py-0.5 text-xs text-text-muted">{col.items.length}</span>
              </div>
              <div className="space-y-2 p-2">
                {col.items.map((item: any, i: number) => (
                  <motion.div key={i} className="rounded-md bg-bg-surface p-3" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                    {filterType === 'gap' ? (
                      <>
                        <div className="flex items-center gap-2">
                          <PriorityBadge priority={item.priority} />
                          <span className="font-mono text-xs text-accent-primary-light">{item.gap_id}</span>
                        </div>
                        <p className="mt-1 text-xs text-text-secondary line-clamp-3">{item.description}</p>
                        <div className="mt-2 flex gap-2 text-xs text-text-muted">
                          <span>{item.gap_type}</span><span>{item.gap_subtype}</span>
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="flex items-center gap-2">
                          <StatusBadge status={item.status} />
                          <span className="font-mono text-xs text-accent-primary-light">{item.action_id}</span>
                        </div>
                        <p className="mt-1 text-xs text-text-secondary line-clamp-3">{item.action_description || item.content}</p>
                        <div className="mt-2 text-xs text-text-muted">{item.action_owner}</div>
                      </>
                    )}
                  </motion.div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* List View */
        <div className="overflow-x-auto rounded-lg border border-border-default">
          {filterType === 'gap' ? (
            <table className="w-full">
              <thead><tr className="border-b border-border-default bg-bg-surface">
                <th className="px-3 py-2 text-left text-xs font-semibold">优先级</th>
                <th className="px-3 py-2 text-left text-xs font-semibold">Gap ID</th>
                <th className="px-3 py-2 text-left text-xs font-semibold">描述</th>
                <th className="px-3 py-2 text-left text-xs font-semibold">类型</th>
                <th className="px-3 py-2 text-left text-xs font-semibold">状态</th>
                <th className="px-3 py-2 text-left text-xs font-semibold">SOP</th>
              </tr></thead>
              <tbody>
                {filteredGaps.sort((a: any, b: any) => (a.priority==='P0'?-1:a.priority==='P1'?0:1)).map((g: any, i: number) => (
                  <tr key={i} className="border-b border-border-default hover:bg-bg-surface">
                    <td className="px-3 py-2"><PriorityBadge priority={g.priority} /></td>
                    <td className="px-3 py-2 font-mono text-xs text-accent-primary-light">{g.gap_id}</td>
                    <td className="max-w-sm px-3 py-2 text-xs text-text-secondary">{g.description}</td>
                    <td className="px-3 py-2 text-xs text-text-secondary">{g.gap_type}</td>
                    <td className="px-3 py-2"><StatusBadge status={g.status} /></td>
                    <td className="px-3 py-2 text-xs text-text-secondary">{g.sop_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table className="w-full">
              <thead><tr className="border-b border-border-default bg-bg-surface">
                <th className="px-3 py-2 text-left text-xs font-semibold">状态</th>
                <th className="px-3 py-2 text-left text-xs font-semibold">行动ID</th>
                <th className="px-3 py-2 text-left text-xs font-semibold">描述</th>
                <th className="px-3 py-2 text-left text-xs font-semibold">子类型</th>
                <th className="px-3 py-2 text-left text-xs font-semibold">负责人</th>
              </tr></thead>
              <tbody>
                {filteredActions.map((a: any, i: number) => (
                  <tr key={i} className="border-b border-border-default hover:bg-bg-surface">
                    <td className="px-3 py-2"><StatusBadge status={a.status} /></td>
                    <td className="px-3 py-2 font-mono text-xs text-accent-primary-light">{a.action_id}</td>
                    <td className="max-w-sm px-3 py-2 text-xs text-text-secondary">{a.action_description || a.content}</td>
                    <td className="px-3 py-2 text-xs text-text-secondary">{a.action_subtype}</td>
                    <td className="px-3 py-2 text-xs text-text-secondary">{a.action_owner}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
