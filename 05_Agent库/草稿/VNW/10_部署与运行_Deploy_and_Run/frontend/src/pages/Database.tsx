import { useEffect, useMemo, useState } from 'react'
import { Database as DatabaseIcon, Search } from 'lucide-react'
import { loadDbCatalog, type DbCatalog, type DbCatalogTable } from '@/lib/dbCatalog'

const SCHEMA_LABELS: Record<string, string> = {
  process_analytics: 'process_analytics（流程数据）',
  public: 'public（业务数据）',
  comm_sandbox: 'comm_sandbox（业务数据·佣金）',
  fin_sandbox: 'fin_sandbox（业务数据·财务）',
}

function TableCard({ table }: { table: DbCatalogTable }) {
  return (
    <details className="rounded-lg border border-border-default bg-bg-elevated">
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-4 py-3">
        <span className="font-mono text-xs text-accent-primary-light">{table.schema}.{table.table}</span>
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
          table.role === '流程数据' ? 'bg-blue-100 text-blue-700'
            : table.role === '业务数据' ? 'bg-amber-100 text-amber-700'
              : 'bg-slate-100 text-slate-500'
        }`}>
          {table.role}
        </span>
        <span className="text-xs text-text-muted">{table.row_count.toLocaleString()} 行</span>
        <span className="text-xs text-text-muted">· {table.columns.length} 列</span>
        {!table.description && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500">待分析</span>}
        <span className="ml-auto flex-1 truncate text-right text-xs text-text-secondary">{table.description ?? ''}</span>
      </summary>
      <div className="border-t border-border-default px-4 py-3">
        {table.description && <p className="mb-3 text-xs leading-5 text-text-secondary">{table.description}</p>}
        <div className="flex flex-wrap gap-1.5">
          {table.columns.map(col => (
            <span key={col.name} className="rounded-md bg-bg-surface px-2 py-1 font-mono text-[10px] text-text-secondary" title={col.type}>
              {col.name}
            </span>
          ))}
        </div>
      </div>
    </details>
  )
}

export default function Database() {
  const [data, setData] = useState<DbCatalog | null>(null)
  const [error, setError] = useState('')
  const [schemaFilter, setSchemaFilter] = useState<'all' | string>('all')
  const [query, setQuery] = useState('')

  useEffect(() => {
    loadDbCatalog().then(setData).catch(err => setError(err.message))
  }, [])

  const filtered = useMemo(() => {
    if (!data) return []
    const q = query.toLowerCase()
    return data.tables.filter(table => {
      if (schemaFilter !== 'all' && table.schema !== schemaFilter) return false
      if (!q) return true
      return (
        table.table.toLowerCase().includes(q) ||
        (table.description ?? '').toLowerCase().includes(q) ||
        table.columns.some(col => col.name.toLowerCase().includes(q))
      )
    })
  }, [data, schemaFilter, query])

  if (error) return <div className="panel p-5 text-sm text-accent-danger">{error}</div>
  if (!data) return <div className="flex min-h-[60vh] items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" /></div>

  const knownCount = data.tables.filter(t => t.description).length

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center gap-3">
          <DatabaseIcon className="h-7 w-7 text-accent-primary" />
          <h1 className="font-heading text-2xl font-bold text-text-primary">数据库现状</h1>
        </div>
        <p className="mt-1 text-sm text-text-secondary">
          直连PostgreSQL的实时表结构+行数快照，覆盖流程数据(process_analytics)和业务数据仓库(public/comm_sandbox/fin_sandbox)。
          与"数据表中心"不是一回事——那里是VNW过程产出物(T1-T30治理表)，这里是数据库本身的现状。
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {Object.entries(SCHEMA_LABELS).map(([schema, label]) => {
          const count = data.tables.filter(t => t.schema === schema).length
          return (
            <div key={schema} className="rounded-lg border border-border-default bg-bg-elevated p-3 text-center">
              <p className="font-mono text-2xl text-text-primary">{count}</p>
              <p className="text-xs text-text-muted">{label}</p>
            </div>
          )
        })}
        <div className="rounded-lg border border-border-default bg-bg-elevated p-3 text-center">
          <p className="font-mono text-2xl text-accent-primary-light">{knownCount}/{data.tables.length}</p>
          <p className="text-xs text-text-muted">已核实业务含义</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-1 rounded-lg bg-bg-elevated p-1">
          <button onClick={() => setSchemaFilter('all')} className={`rounded-md px-3 py-1.5 text-xs transition-colors ${schemaFilter === 'all' ? 'bg-accent-primary text-white' : 'text-text-secondary hover:text-text-primary hover:bg-bg-surface'}`}>
            全部 ({data.tables.length})
          </button>
          {data.schemas.map(schema => (
            <button key={schema} onClick={() => setSchemaFilter(schema)} className={`rounded-md px-3 py-1.5 text-xs transition-colors ${schemaFilter === schema ? 'bg-accent-primary text-white' : 'text-text-secondary hover:text-text-primary hover:bg-bg-surface'}`}>
              {schema} ({data.tables.filter(t => t.schema === schema).length})
            </button>
          ))}
        </div>
        <div className="relative ml-auto">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="按表名/列名/说明搜索"
            className="h-9 w-64 rounded-md border border-border-default bg-bg-surface pl-9 pr-3 text-sm outline-none focus:border-accent-primary"
          />
        </div>
      </div>

      <p className="text-[11px] text-text-muted">{data.source_policy}</p>

      <div className="space-y-2">
        {filtered.map(table => <TableCard key={`${table.schema}.${table.table}`} table={table} />)}
      </div>
    </div>
  )
}
