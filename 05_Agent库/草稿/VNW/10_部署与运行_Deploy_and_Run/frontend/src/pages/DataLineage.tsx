import { useEffect, useMemo, useState } from 'react'
import { Workflow, Search, Database, FolderTree, Briefcase, Boxes, Network } from 'lucide-react'
import { loadDataLineage, type DataLineage, type LineageEdge, type LineageNode } from '../lib/dataLineage'
import { loadTableAnalysis, type TableAnalysis } from '../lib/tableAnalysis'
import LineageGraph from '../components/LineageGraph'

/** 合并后的统一表记录 */
interface TableRecord {
  schema: string
  table: string
  key: string
  business_label: string
  table_type: string
  row_count: number
  has_lineage: boolean
  zombie_flag: string
  // 血缘
  inDegree: number
  outDegree: number
  // 语义（合并自 table_analysis）
  description: string | null
  related_l3_l4: { l3_code: string; l3_name: string; l4_code: string; l4_name: string }[]
  positions: string[]
  data_health: string
  status: string
}

const SCHEMA_ALL = ['public', 'comm_sandbox', 'fin_sandbox'] as const

/** 分类：用于树导航第一层 */
const TYPE_ORDER = ['事实表', '维度表', '汇总表', '配置表', '规则表', '映射表', '桥接表', '视图', '状态记录表', '事件记录表', '调整记录表', '历史记录表', '快照表', '核对匹配表', '系统表', '疑似记录表', '其他']

export default function DataLineage() {
  const [lineage, setLineage] = useState<DataLineage | null>(null)
  const [tableAnalysis, setTableAnalysis] = useState<TableAnalysis | null>(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  // 树导航：当前维度视图
  const [navView, setNavView] = useState<'schema' | 'l3l4' | 'position'>('schema')
  // 选中的树节点（按视图不同含义不同）
  const [navSelection, setNavSelection] = useState<string>('')
  // 选中表（焦点），schema.table
  const [focus, setFocus] = useState<string | null>(null)
  // 血缘子图跳数 1|2，'all' 总览
  const [hops, setHops] = useState<1 | 2>(1)
  const [showOverview, setShowOverview] = useState(false)

  useEffect(() => {
    loadDataLineage().then(setLineage).catch(err => setError(err.message))
    loadTableAnalysis().then(setTableAnalysis).catch(() => setTableAnalysis(null))
  }, [])

  /** 统一表记录 */
  const tables: TableRecord[] = useMemo(() => {
    if (!lineage) return []
    const nodeMap = new Map<string, LineageNode>()
    lineage.nodes.forEach(n => { nodeMap.set(`${n.schema}.${n.table}`, n) })
    const taMap = new Map<string, { description: string | null; related_l3_l4: TableRecord['related_l3_l4']; positions: string[]; data_health: string; status: string }>()
    tableAnalysis?.tables.forEach(t => {
      taMap.set(`${t.schema}.${t.table}`, {
        description: t.description,
        related_l3_l4: t.layer2.related_l3_l4,
        positions: t.layer2.positions,
        data_health: t.layer2.data_health,
        status: t.layer2.status,
      })
    })
    const inDeg = new Map<string, number>()
    const outDeg = new Map<string, number>()
    lineage.edges.forEach(e => {
      const a = `${e.from_schema}.${e.from_table}`
      const b = `${e.to_schema}.${e.to_table}`
      outDeg.set(a, (outDeg.get(a) ?? 0) + 1)
      inDeg.set(b, (inDeg.get(b) ?? 0) + 1)
    })
    return lineage.nodes.map(n => {
      const k = `${n.schema}.${n.table}`
      const ta = taMap.get(k)
      return {
        schema: n.schema,
        table: n.table,
        key: k,
        business_label: n.business_label,
        table_type: n.table_type,
        row_count: n.row_count,
        has_lineage: n.has_lineage,
        zombie_flag: n.zombie_flag,
        inDegree: inDeg.get(k) ?? 0,
        outDegree: outDeg.get(k) ?? 0,
        description: ta?.description ?? null,
        related_l3_l4: ta?.related_l3_l4 ?? [],
        positions: ta?.positions ?? [],
        data_health: ta?.data_health ?? '',
        status: ta?.status ?? '',
      }
    })
  }, [lineage, tableAnalysis])

  /** 树数据构建 */
  const schemaTree = useMemo(() => {
    const map = new Map<string, Map<string, TableRecord[]>>()
    tables.forEach(t => {
      const byType = map.get(t.schema) ?? new Map<string, TableRecord[]>()
      ;(byType.get(t.table_type) ?? byType.set(t.table_type, []).get(t.table_type)!).push(t)
      map.set(t.schema, byType)
    })
    return Array.from(map.entries()).map(([schema, types]) => ({
      schema,
      types: Array.from(types.entries()).map(([type, list]) => ({ type, list: list.sort((a,b)=>b.row_count-a.row_count) })),
    }))
  }, [tables])

  const l3L4Tree = useMemo(() => {
    const map = new Map<string, Map<string, Map<string, string[]>>>() // l3 -> l4 -> list of keys
    tables.forEach(t => {
      t.related_l3_l4.forEach(r => {
        const l4 = map.get(r.l3_code) ?? new Map<string, Map<string, string[]>>()
        const keyList = l4.get(r.l4_code) ?? new Map<string, string[]>()
        ;(keyList.get(r.l4_name) ?? keyList.set(r.l4_name, []).get(r.l4_name)!).push(t.key)
        l4.set(r.l4_code, keyList)
        map.set(r.l3_code, l4)
      })
    })
    return Array.from(map.entries()).map(([l3, l4map]) => ({
      l3,
      l4s: Array.from(l4map.entries()).map(([l4code, names]) => ({ l4code, names: Array.from(names.entries()).map(([name, keys]) => ({ name, keys })) })),
    }))
  }, [tables])

  const positionTree = useMemo(() => {
    const map = new Map<string, TableRecord[]>()
    tables.forEach(t => {
      t.positions.forEach(p => { (map.get(p) ?? map.set(p, []).get(p)!).push(t) })
    })
    return Array.from(map.entries()).map(([pos, list]) => ({ pos, list: list.sort((a,b)=>b.row_count-a.row_count) }))
  }, [tables])

  /** 当前树过滤出的表集合（全部 key） */
  const navFilteredKeys = useMemo(() => {
    const set = new Set<string>()
    if (navSelection === '' ) return set
    if (navView === 'schema') {
      const [schema, type] = navSelection.split('::')
      tables.forEach(t => {
        if (t.schema === schema && (!type || t.table_type === type)) set.add(t.key)
      })
    } else if (navView === 'l3l4') {
      const [l3, l4, l4name] = navSelection.split('::')
      tables.forEach(t => {
        t.related_l3_l4.forEach(r => {
          if (r.l3_code === (l3 ?? r.l3_code)) {
            if (!l4 || (r.l4_code === l4 && (!l4name || r.l4_name === l4name))) set.add(t.key)
          }
        })
      })
    } else if (navView === 'position') {
      tables.forEach(t => { if (t.positions.includes(navSelection)) set.add(t.key) })
    }
    return set
  }, [tables, navView, navSelection])

  /** 显示在卡片网格的表 */
  const visibleTables = useMemo(() => {
    const q = query.trim().toLowerCase()
    return tables.filter(t => {
      if (navSelection !== '' && navFilteredKeys.size > 0 && !navFilteredKeys.has(t.key)) return false
      if (q && !`${t.key} ${t.business_label} ${t.table_type}`.toLowerCase().includes(q)) return false
      return true
    })
  }, [tables, navView, navSelection, navFilteredKeys, query])

  // 用于血缘子图的原始数据（供 LineageGraph 全量或子图）
  const focusNodeInfo = useMemo(() => tables.find(t => t.key === focus) ?? null, [tables, focus])

  if (error) return <div className="panel p-5 text-sm text-accent-danger">{error}</div>
  if (!lineage) return <div className="flex min-h-64 items-center justify-center text-text-muted">正在读取数据血缘…</div>

  const candidateCount = Object.keys(lineage.suggested_l4_candidates).length
  const suspectedCount = tables.filter(t => t.zombie_flag === 'suspected_zombie').length
  const fieldAnchoredCount = tables.filter(t => t.zombie_flag === 'field_anchored').length
  const utilitySupportCount = tables.filter(t => t.zombie_flag === 'utility_support').length
  const withL4 = tables.filter(t => t.related_l3_l4.length > 0).length
  const noLineage = tables.filter(t => !t.has_lineage).length

  const nodeByIds = new Map<TableRecord['key'], TableRecord>()

  return (
    <div className="space-y-6">
      {/* 顶部统计带 */}
      <div>
        <div className="flex items-center gap-2 text-xs text-accent-primary-light"><Workflow className="h-4 w-4" /> 业务数据表 · 分类分层分级 · 血缘关系</div>
        <h1 className="mt-2 font-heading text-3xl font-bold">104张业务表：分类 · 分层 · 关系</h1>
        <p className="mt-2 max-w-4xl text-sm leading-6 text-text-secondary">
          从「分类(Schema/表型) / 分层(L3-L4) / 分级(岗位)」三个维度浏览全部业务表；
          点任意表卡片，在下方血缘图聚焦看它 1~2 跳的真实上下游（视图依赖/外键/流水线同批）。
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-7">
        <div className="panel p-4"><p className="eyebrow">全部业务表</p><p className="mt-2 metric-value">{tables.length}</p></div>
        <div className="panel p-4"><p className="eyebrow">已定位 L3/L4</p><p className="mt-2 metric-value text-indigo-500">{withL4}</p><p className="mt-1 text-[11px] text-text-muted">映射到业务模型的表</p></div>
        <div className="panel p-4"><p className="eyebrow">有血缘证据</p><p className="mt-2 metric-value">{lineage.nodes.filter(n=>n.has_lineage).length}</p><p className="mt-1 text-[11px] text-text-muted">真实边 {lineage.edge_type_counts.view_dependency+lineage.edge_type_counts.foreign_key}</p></div>
        <div className="panel p-4"><p className="eyebrow">血缘候选 L4</p><p className="mt-2 metric-value text-amber-600">{candidateCount}</p><p className="mt-1 text-[11px] text-text-muted">未经人工核实</p></div>
        <div className="panel p-4"><p className="eyebrow">字段锚定(非孤立)</p><p className="mt-2 metric-value text-sky-600">{fieldAnchoredCount}</p><p className="mt-1 text-[11px] text-text-muted">无血缘边/L4，但有真实主键字段连回主链</p></div>
        <div className="panel p-4"><p className="eyebrow">工具/服务支撑</p><p className="mt-2 metric-value text-violet-600">{utilitySupportCount}</p><p className="mt-1 text-[11px] text-text-muted">业务方核实非断点，方法论对其天然失效</p></div>
        <div className="panel p-4"><p className="eyebrow">真断点(待核实)</p><p className="mt-2 metric-value text-rose-600">{suspectedCount}</p><p className="mt-1 text-[11px] text-text-muted">血缘/语义/字段锚定/工具登记均查不到</p></div>
      </div>

      {/* 主体：左树 + 中卡片 */}
      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        {/* 左栏：树导航 */}
        <div className="panel flex flex-col p-3">
          <p className="text-xs font-semibold text-text-primary">浏览维度</p>
          <div className="mt-2 flex flex-col gap-1">
            <button onClick={() => { setNavView('schema'); setNavSelection(''); setFocus(null) }} className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-[11px] text-left ${navView==='schema' ? 'bg-accent-primary text-white' : 'text-text-secondary hover:bg-bg-surface'}`}><FolderTree className="h-3.5 w-3.5" />按Schema/表型 分类</button>
            <button onClick={() => { setNavView('l3l4'); setNavSelection(''); setFocus(null) }} className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-[11px] text-left ${navView==='l3l4' ? 'bg-accent-primary text-white' : 'text-text-secondary hover:bg-bg-surface'}`}><Database className="h-3.5 w-3.5" />按L3-L4 分层</button>
            <button onClick={() => { setNavView('position'); setNavSelection(''); setFocus(null) }} className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-[11px] text-left ${navView==='position' ? 'bg-accent-primary text-white' : 'text-text-secondary hover:bg-bg-surface'}`}><Briefcase className="h-3.5 w-3.5" />按岗位 分级</button>
          </div>

          <div className="mt-3 max-h-[520px] overflow-auto pr-1 text-[11px]">
            {navView === 'schema' && (
              <div className="space-y-1.5">
                {schemaTree.map(s => (
                  <details key={s.schema} className="group" open={true}>
                    <summary className="cursor-pointer rounded-md px-2 py-1 font-semibold text-text-primary hover:bg-bg-surface">{s.schema}</summary>
                    <button onClick={() => { setNavSelection(s.schema); setFocus(null) }} className={`ml-3 mt-1 flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] ${navSelection===s.schema?'bg-accent-primary text-white':'text-text-secondary hover:bg-bg-surface'}`}>全部({s.types.reduce((x,t)=>x+t.list.length,0)})</button>
                    <div className="ml-3 space-y-0.5">
                      {s.types.map(t => (
                        <button key={t.type} onClick={() => { setNavSelection(`${s.schema}::${t.type}`); setFocus(null) }} className={`flex w-full items-center justify-between rounded-md px-2 py-0.5 text-left ${navSelection===`${s.schema}::${t.type}`?'bg-accent-primary text-white':'text-text-secondary hover:bg-bg-surface'}`}>
                          <span>{t.type}</span><span className="opacity-60">{t.list.length}</span>
                        </button>
                      ))}
                    </div>
                  </details>
                ))}
              </div>
            )}
            {navView === 'l3l4' && (
              <div className="space-y-1.5">
                {l3L4Tree.map(grp => (
                  <details key={grp.l3} className="group">
                    <summary className="cursor-pointer rounded-md px-2 py-1 font-semibold text-text-primary hover:bg-bg-surface">{grp.l3}</summary>
                    {grp.l4s.map(l4 => (
                      <div key={l4.l4code} className="ml-2">
                        <button onClick={() => { setNavSelection(`${grp.l3}::${l4.l4code}`); setFocus(null) }} className={`mt-0.5 flex w-full items-center justify-between rounded-md px-2 py-0.5 text-left font-medium text-indigo-700 ${navSelection===`${grp.l3}::${l4.l4code}`?'bg-indigo-100 text-indigo-900':'hover:bg-bg-surface'}`}>
                          <span>{l4.l4code}</span>
                        </button>
                        {l4.names.map(nm => (
                          <button key={nm.name} onClick={() => { setNavSelection(`${grp.l3}::${l4.l4code}::${nm.name}`); setFocus(null) }} className={`mt-0.5 ml-3 flex w-full items-center justify-between rounded-md px-2 py-0.5 text-left text-text-secondary ${navSelection===`${grp.l3}::${l4.l4code}::${nm.name}`?'bg-accent-primary text-white':'hover:bg-bg-surface'}`}>
                            <span>{nm.name}</span><span className="opacity-60">{nm.keys.length}</span>
                          </button>
                        ))}
                      </div>
                    ))}
                  </details>
                ))}
              </div>
            )}
            {navView === 'position' && (
              <div className="space-y-1.5">
                {positionTree.map(p => (
                  <button key={p.pos} onClick={() => { setNavSelection(p.pos); setFocus(null) }} className={`flex w-full items-center justify-between rounded-md px-2 py-1 text-left ${navSelection===p.pos?'bg-accent-primary text-white':'text-text-secondary hover:bg-bg-surface'}`}>
                    <span className="flex items-center gap-1.5"><Briefcase className="h-3 w-3" />{p.pos}</span><span className="opacity-60">{p.list.length}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <p className="mt-3 border-t border-border-default pt-2 text-[10px] text-text-muted">{tables.length}张表 · {withL4}张已映射L4/岗位 · {utilitySupportCount}张工具/服务支撑 · 其余为字段锚定/独立表</p>
        </div>

        {/* 中栏：表卡片网格 */}
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative ml-auto w-full max-w-xs">
              <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-text-muted" />
              <input value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索表名/中文/类型" className="w-full rounded-lg border border-border-default bg-bg-elevated py-1.5 pl-8 pr-3 text-xs text-text-primary placeholder:text-text-muted" />
            </div>
          </div>
          <p className="text-[11px] text-text-muted">显示 {visibleTables.length} / {tables.length} 张表</p>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {visibleTables.map(t => {
              const hasL4 = t.related_l3_l4.length > 0
              const isZombie = t.zombie_flag === 'suspected_zombie'
              const isFieldAnchored = t.zombie_flag === 'field_anchored'
              const isUtilitySupport = t.zombie_flag === 'utility_support'
              const anchorLinks = lineage.field_anchor_links[t.key]
              const isFocus = focus === t.key
              return (
                <div key={t.key} onClick={() => setFocus(t.key)} className={`panel cursor-pointer p-3 transition ${isFocus ? 'ring-2 ring-accent-primary' : 'hover:border-accent-primary'} ${hasL4 ? '' : 'opacity-80'}`}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-mono text-xs font-bold text-text-primary">{t.schema}.{t.table}</p>
                      <p className="mt-0.5 truncate text-[11px] text-text-secondary">{t.business_label}</p>
                    </div>
                    <span className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-medium ${isZombie ? 'bg-rose-100 text-rose-700' : hasL4 ? 'bg-indigo-100 text-indigo-700' : isFieldAnchored ? 'bg-sky-100 text-sky-700' : isUtilitySupport ? 'bg-violet-100 text-violet-700' : 'bg-slate-100 text-slate-500'}`}>
                      {isZombie ? '断点' : hasL4 ? '已定位L4' : isFieldAnchored ? '字段锚定' : isUtilitySupport ? '工具/服务支撑' : '支撑/独立'}
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1 text-[9px]">
                    <span className="rounded bg-bg-surface px-1.5 py-0.5 text-text-muted">{t.table_type}</span>
                    <span className="rounded bg-bg-surface px-1.5 py-0.5 text-text-muted">{t.row_count.toLocaleString()}行</span>
                    <span className="rounded bg-bg-surface px-1.5 py-0.5 text-sky-600">↑{t.inDegree}</span>
                    <span className="rounded bg-bg-surface px-1.5 py-0.5 text-emerald-600">↓{t.outDegree}</span>
                  </div>
                  {hasL4 && (
                    <div className="mt-2 space-y-0.5">
                      {t.related_l3_l4.slice(0, 2).map((r, i) => (
                        <p key={i} title={r.l4_name} className="truncate text-[9px] text-indigo-700">{r.l3_code} · {r.l4_code} · {r.l4_name}</p>
                      ))}
                      {t.related_l3_l4.length > 2 && <p className="text-[9px] text-text-muted">+{t.related_l3_l4.length-2} 个L4…</p>}
                    </div>
                  )}
                  {isFieldAnchored && anchorLinks && anchorLinks.length > 0 && (
                    <div className="mt-2 rounded-md border border-dashed border-sky-300 bg-sky-50/60 p-1.5">
                      <p className="text-[9px] font-semibold text-sky-800">无血缘边/L4，但字段"{anchorLinks[0].field}"是{anchorLinks[0].origin_tables.join('、')}的真实主键，且被{anchorLinks[0].linked_tables.length}张表共用——非孤立</p>
                    </div>
                  )}
                  {isUtilitySupport && (
                    <div className="mt-2 rounded-md border border-dashed border-violet-300 bg-violet-50/60 p-1.5">
                      <p className="text-[9px] font-semibold text-violet-800">{lineage.nodes.find(n => `${n.schema}.${n.table}` === t.key)?.utility_support_reason}</p>
                    </div>
                  )}
                  {t.positions.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {t.positions.map(p => <span key={p} className="rounded-full bg-amber-50 px-1.5 py-0.5 text-[9px] font-medium text-amber-700">{p}</span>)}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* 底部：血缘关系子图 */}
      <div className="panel p-3">
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-sm font-semibold text-text-primary flex items-center gap-2"><Network className="h-4 w-4" />数据血缘关系图</p>
          {focusNodeInfo ? (
            <span className="rounded-md bg-accent-primary/10 px-2 py-0.5 font-mono text-[11px] text-accent-primary-light">焦点：{focus}</span>
          ) : (
            <span className="text-[11px] text-text-muted">点上方表卡片聚焦看它的血缘，或切换"全图总览"</span>
          )}
          <div className="ml-auto flex items-center gap-1 rounded-lg bg-bg-elevated p-1 text-[11px]">
            {([1, 2] as const).map(h => (
              <button key={h} disabled={showOverview} onClick={() => { setHops(h); setShowOverview(false) }} className={`rounded-md px-2 py-1 disabled:opacity-40 ${!showOverview && hops===h ? 'bg-accent-primary text-white' : 'text-text-secondary hover:bg-bg-surface'}`}>{h}跳到上游/下游</button>
            ))}
            <button onClick={() => setShowOverview(v => !v)} className={`rounded-md px-2 py-1 ${showOverview ? 'bg-accent-primary text-white' : 'text-text-secondary hover:bg-bg-surface'}`}>全图总览</button>
          </div>
        </div>
        <div className="mt-3">
          <LineageGraph
            nodes={lineage.nodes}
            edges={lineage.edges}
            hops={hops}
            focusKey={showOverview ? null : focus}
            focusSchema={!showOverview && focus ? focus.split('.')[0] : null}
            onSelect={(schema, table) => setFocus(`${schema}.${table}`)}
          />
        </div>
      </div>
    </div>
  )
}
