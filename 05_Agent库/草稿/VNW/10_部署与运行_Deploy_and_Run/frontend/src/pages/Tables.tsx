import { useState, useEffect, useMemo } from 'react'
import { motion } from 'framer-motion'
import { loadAllData, getTableData, TABLE_DISPLAY_NAMES } from '@/lib/data'
import { StatusBadge, PriorityBadge } from '@/components/StatusBadge'
import { Search, Download, Table2, ChevronLeft, ChevronRight } from 'lucide-react'

const PAGE_SIZE = 20

export default function Tables() {
  const [data, setData] = useState<any>(null)
  const [activeTab, setActiveTab] = useState('node_index')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [sortCol, setSortCol] = useState('')
  const [sortAsc, setSortAsc] = useState(true)

  useEffect(() => {
    if (!data) loadAllData().then(d => { setData(d); setActiveTab(Object.keys(TABLE_DISPLAY_NAMES)[0]) })
  }, [data])

  const tableData = useMemo(() => {
    if (!data) return []
    let rows = getTableData(activeTab)
    if (search) {
      const s = search.toLowerCase()
      rows = rows.filter((r: any) => Object.values(r).some(v => String(v).toLowerCase().includes(s)))
    }
    if (sortCol) {
      rows = [...rows].sort((a: any, b: any) => {
        const av = a[sortCol], bv = b[sortCol]
        if (av == null) return sortAsc ? 1 : -1
        if (bv == null) return sortAsc ? -1 : 1
        if (typeof av === 'number' && typeof bv === 'number') return sortAsc ? av - bv : bv - av
        return sortAsc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av))
      })
    }
    return rows
  }, [data, activeTab, search, sortCol, sortAsc])

  const columns = useMemo(() => {
    if (tableData.length === 0) return []
    return Object.keys(tableData[0]).filter(k => !k.startsWith('_'))
  }, [tableData])

  const totalPages = Math.ceil(tableData.length / PAGE_SIZE)
  const paged = tableData.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  function exportCSV() {
    const headers = columns.join(',')
    const rows = tableData.map((r: any) => columns.map(c => `"${String(r[c] ?? '').replace(/"/g, '""')}"`).join(','))
    const csv = `\ufeff${headers}\n${rows.join('\n')}`
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${activeTab}.csv`
    a.click()
  }

  if (!data) return <div className="flex min-h-[60vh] items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" /></div>

  // Hide keys that are too long for display
  const hiddenCols = ['strategic_note', 'ideal_state', 'current_state', 'fused_info_summary', 'gate_1_note', 'gate_2_note', 'gate_3_note']
  const displayCols = columns.filter(c => !hiddenCols.includes(c))

  const isStatusCol = (col: string) => ['status', 'gate_status', 'externalized', 'is_fused', 'sop_status'].includes(col)
  const isPriorityCol = (col: string) => col === 'priority'

  return (
    <div className="space-y-4">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <div className="flex items-center gap-3">
          <Table2 className="h-7 w-7 text-accent-primary" />
          <h1 className="font-heading text-2xl font-bold text-text-primary">数据表中心</h1>
        </div>
        <p className="mt-1 text-sm text-text-secondary">全面浏览 · 搜索筛选 · CSV导出</p>
      </motion.div>

      {/* Tab Bar */}
      <div className="flex flex-wrap gap-1 rounded-lg bg-bg-elevated p-1">
        {Object.entries(TABLE_DISPLAY_NAMES).map(([key, info]) => (
          <button key={key} onClick={() => { setActiveTab(key); setPage(1); setSearch(''); }}
            className={`rounded-md px-3 py-1.5 text-xs transition-colors ${
              activeTab === key ? 'bg-accent-primary text-white' : 'text-text-secondary hover:text-text-primary hover:bg-bg-surface'
            }`}>
            {info.name} <span className="opacity-70">({getTableData(key).length})</span>
          </button>
        ))}
      </div>

      {/* Info + Search + Export */}
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">{TABLE_DISPLAY_NAMES[activeTab]?.name}</h2>
          <p className="text-xs text-text-muted">{TABLE_DISPLAY_NAMES[activeTab]?.desc}</p>
        </div>
        <div className="relative ml-auto">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
          <input type="text" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }}
            placeholder="搜索..." className="h-9 w-56 rounded-md border border-border-default bg-bg-surface pl-9 pr-3 text-sm outline-none focus:border-accent-primary" />
        </div>
        <button onClick={exportCSV} className="flex items-center gap-1 rounded-md border border-border-default bg-bg-surface px-3 py-2 text-sm text-text-secondary hover:text-text-primary">
          <Download className="h-4 w-4" />导出
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-border-default">
        <table className="w-full">
          <thead><tr className="border-b border-border-default bg-bg-surface">
            {displayCols.map(c => (
              <th key={c} onClick={() => { setSortCol(c); setSortAsc(sortCol === c ? !sortAsc : true); }}
                className="cursor-pointer whitespace-nowrap px-3 py-2 text-left text-xs font-semibold text-text-primary hover:text-accent-primary-light">
                {c} {sortCol === c && (sortAsc ? '↑' : '↓')}
              </th>
            ))}
          </tr></thead>
          <tbody>
            {paged.map((row: any, i: number) => (
              <tr key={i} className="border-b border-border-default hover:bg-bg-surface">
                {displayCols.map(c => (
                  <td key={c} className={`whitespace-nowrap px-3 py-2 text-xs ${
                    c.includes('_id') ? 'font-mono text-accent-primary-light' :
                    isStatusCol(c) ? '' : 'text-text-secondary'
                  } ${c==='description'||c==='content' ? 'max-w-[300px] truncate' : ''}`}>
                    {isStatusCol(c) ? <StatusBadge status={row[c]} /> :
                     isPriorityCol(c) ? <PriorityBadge priority={row[c]} /> :
                     row[c] == null ? '-' : String(row[c]).length > 100 ? String(row[c]).slice(0, 100) + '...' : String(row[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-text-muted">{tableData.length} 条 · 第 {page}/{totalPages} 页</span>
          <div className="flex gap-1">
            <button onClick={() => setPage(p => Math.max(1, p-1))} disabled={page===1} className="rounded-md border border-border-default p-1 disabled:opacity-30"><ChevronLeft className="h-4 w-4" /></button>
            {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
              let p = i + 1
              if (totalPages > 5 && page > 3) p = page - 3 + i
              if (p > totalPages) return null
              return <button key={p} onClick={() => setPage(p)} className={`h-7 w-7 rounded-md text-xs ${page===p?'bg-accent-primary text-white':'border border-border-default text-text-secondary'}`}>{p}</button>
            })}
            <button onClick={() => setPage(p => Math.min(totalPages, p+1))} disabled={page===totalPages} className="rounded-md border border-border-default p-1 disabled:opacity-30"><ChevronRight className="h-4 w-4" /></button>
          </div>
        </div>
      )}
    </div>
  )
}
