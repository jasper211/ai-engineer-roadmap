import { useEffect, useMemo, useState } from 'react'
import { Workflow, Search, Info } from 'lucide-react'
import { loadDataLineage, type DataLineage, type FieldTransform, type LineageEdge, type LineageEdgeType, type LineageNode } from '../lib/dataLineage'
import { loadTableAnalysis, type TableAnalysis } from '../lib/tableAnalysis'

const TRANSFORM_LABEL: Record<FieldTransform, string> = {
  direct: '直接透传',
  derived: '由源字段计算',
  computed_literal: '常量/无法追溯到源字段',
}

const FIELD_CONFIDENCE_TONE: Record<string, string> = {
  origin: 'bg-emerald-400/10 text-emerald-700',
  foreign_key_confirmed: 'bg-sky-400/10 text-sky-700',
  same_name_business_confirmed: 'bg-amber-400/10 text-amber-700',
}
const FIELD_CONFIDENCE_LABEL: Record<string, string> = {
  origin: '源头(主键)',
  foreign_key_confirmed: '外键确认',
  same_name_business_confirmed: '同名(业务方确认一致)',
}

const EDGE_TONE: Record<LineageEdgeType, { stroke: string; dash?: string }> = {
  view_dependency: { stroke: '#6366f1' },
  foreign_key: { stroke: '#0ea5e9' },
  pipeline_sibling: { stroke: '#94a3b8', dash: '4 3' },
}

const RELATION_TONE = {
  confirmed: { fill: '#10b981', label: '已确认关联L4' },
  candidate: { fill: '#f59e0b', label: '血缘候选(待核实)' },
  zombie: { fill: '#e11d48', label: '疑似僵尸表(有数据但无人认领)' },
  none: { fill: '#94a3b8', label: '暂无信号' },
} as const

function nodeKey(schema: string, table: string) {
  return `${schema}.${table}`
}

interface LaidOutNode extends LineageNode {
  key: string
  x: number
  y: number
  degree: number
}

function computeForceLayout(nodes: LineageNode[], edges: LineageEdge[], width: number, height: number): Map<string, { x: number; y: number }> {
  const keys = nodes.map(n => nodeKey(n.schema, n.table))
  const index = new Map(keys.map((k, i) => [k, i]))
  const n = keys.length
  const positions = keys.map((_, i) => {
    const angle = (i / n) * Math.PI * 2
    const r = Math.min(width, height) * 0.35
    return { x: width / 2 + r * Math.cos(angle), y: height / 2 + r * Math.sin(angle) }
  })
  const velocities = keys.map(() => ({ x: 0, y: 0 }))
  const edgePairs = edges
    .map(e => [index.get(nodeKey(e.from_schema, e.from_table)), index.get(nodeKey(e.to_schema, e.to_table))])
    .filter((pair): pair is [number, number] => pair[0] !== undefined && pair[1] !== undefined)

  const area = width * height
  const k = Math.sqrt(area / Math.max(n, 1)) * 0.9
  let temperature = width / 10

  for (let iter = 0; iter < 250; iter++) {
    const disp = keys.map(() => ({ x: 0, y: 0 }))
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const dx = positions[i].x - positions[j].x
        const dy = positions[i].y - positions[j].y
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01)
        const force = (k * k) / dist
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        disp[i].x += fx
        disp[i].y += fy
        disp[j].x -= fx
        disp[j].y -= fy
      }
    }
    for (const [a, b] of edgePairs) {
      const dx = positions[a].x - positions[b].x
      const dy = positions[a].y - positions[b].y
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01)
      const force = (dist * dist) / k
      const fx = (dx / dist) * force
      const fy = (dy / dist) * force
      disp[a].x -= fx
      disp[a].y -= fy
      disp[b].x += fx
      disp[b].y += fy
    }
    for (let i = 0; i < n; i++) {
      const dx = disp[i].x
      const dy = disp[i].y
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01)
      const capped = Math.min(dist, temperature)
      positions[i].x += (dx / dist) * capped
      positions[i].y += (dy / dist) * capped
      positions[i].x = Math.min(width - 30, Math.max(30, positions[i].x))
      positions[i].y = Math.min(height - 30, Math.max(30, positions[i].y))
      velocities[i] = { x: 0, y: 0 }
    }
    temperature *= 0.97
  }

  const result = new Map<string, { x: number; y: number }>()
  keys.forEach((key, i) => result.set(key, positions[i]))
  return result
}

export default function DataLineage() {
  const [lineage, setLineage] = useState<DataLineage | null>(null)
  const [tableAnalysis, setTableAnalysis] = useState<TableAnalysis | null>(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [showPipelineSibling, setShowPipelineSibling] = useState(false)
  const [schemaFilter, setSchemaFilter] = useState<'all' | string>('all')
  const [l3Slice, setL3Slice] = useState<'all' | string>('all')
  const [fieldQuery, setFieldQuery] = useState('')

  useEffect(() => {
    loadDataLineage().then(setLineage).catch(err => setError(err.message))
    loadTableAnalysis().then(setTableAnalysis).catch(() => setTableAnalysis(null))
  }, [])

  const confirmedRelationKeys = useMemo(() => {
    const set = new Set<string>()
    tableAnalysis?.tables.forEach(t => {
      if (t.layer2.related_l3_l4.length > 0) set.add(nodeKey(t.schema, t.table))
    })
    return set
  }, [tableAnalysis])

  const l3ToTableKeys = useMemo(() => {
    const map = new Map<string, { name: string; keys: Set<string> }>()
    tableAnalysis?.tables.forEach(t => {
      t.layer2.related_l3_l4.forEach(rel => {
        const entry = map.get(rel.l3_code) ?? { name: rel.l3_name, keys: new Set<string>() }
        entry.keys.add(nodeKey(t.schema, t.table))
        map.set(rel.l3_code, entry)
      })
    })
    return map
  }, [tableAnalysis])

  const l3Options = useMemo(() => Array.from(l3ToTableKeys.entries()).sort(([a], [b]) => a.localeCompare(b)), [l3ToTableKeys])

  const sliceCoreKeys = useMemo(() => (l3Slice === 'all' ? null : l3ToTableKeys.get(l3Slice)?.keys ?? new Set<string>()), [l3Slice, l3ToTableKeys])

  const visibleEdges = useMemo(() => {
    if (!lineage) return []
    const base = lineage.edges.filter(e => showPipelineSibling || e.edge_type !== 'pipeline_sibling')
    if (!sliceCoreKeys) return base
    return base.filter(e => sliceCoreKeys.has(nodeKey(e.from_schema, e.from_table)) || sliceCoreKeys.has(nodeKey(e.to_schema, e.to_table)))
  }, [lineage, showPipelineSibling, sliceCoreKeys])

  const sliceNeighborKeys = useMemo(() => {
    if (!sliceCoreKeys) return new Set<string>()
    const set = new Set<string>()
    visibleEdges.forEach(e => {
      const a = nodeKey(e.from_schema, e.from_table)
      const b = nodeKey(e.to_schema, e.to_table)
      if (sliceCoreKeys.has(a) && !sliceCoreKeys.has(b)) set.add(b)
      if (sliceCoreKeys.has(b) && !sliceCoreKeys.has(a)) set.add(a)
    })
    return set
  }, [sliceCoreKeys, visibleEdges])

  const graphNodes = useMemo(() => {
    if (!lineage) return []
    if (!sliceCoreKeys) return lineage.nodes.filter(n => n.has_lineage)
    return lineage.nodes.filter(n => sliceCoreKeys.has(nodeKey(n.schema, n.table)) || sliceNeighborKeys.has(nodeKey(n.schema, n.table)))
  }, [lineage, sliceCoreKeys, sliceNeighborKeys])

  const isolatedNodes = useMemo(() => lineage?.nodes.filter(n => !n.has_lineage) ?? [], [lineage])

  const layout = useMemo(() => {
    if (!lineage) return new Map<string, { x: number; y: number }>()
    return computeForceLayout(graphNodes, visibleEdges, 1100, 820)
  }, [lineage, graphNodes, visibleEdges])

  const laidOutNodes: LaidOutNode[] = useMemo(() => {
    return graphNodes.map(n => {
      const key = nodeKey(n.schema, n.table)
      const pos = layout.get(key) ?? { x: 0, y: 0 }
      const degree = visibleEdges.filter(e => nodeKey(e.from_schema, e.from_table) === key || nodeKey(e.to_schema, e.to_table) === key).length
      return { ...n, key, x: pos.x, y: pos.y, degree }
    })
  }, [graphNodes, layout, visibleEdges])

  const filteredKeys = useMemo(() => {
    const q = query.toLowerCase()
    const set = new Set<string>()
    lineage?.nodes.forEach(n => {
      const key = nodeKey(n.schema, n.table)
      if (schemaFilter !== 'all' && n.schema !== schemaFilter) return
      if (q && !`${key} ${n.business_label}`.toLowerCase().includes(q)) return
      set.add(key)
    })
    return set
  }, [lineage, query, schemaFilter])

  const selectedNode = useMemo(() => lineage?.nodes.find(n => nodeKey(n.schema, n.table) === selected) ?? null, [lineage, selected])
  const selectedNeighbors = useMemo(() => {
    if (!selected || !lineage) return []
    return lineage.edges
      .filter(e => nodeKey(e.from_schema, e.from_table) === selected || nodeKey(e.to_schema, e.to_table) === selected)
      .map(e => ({
        direction: nodeKey(e.from_schema, e.from_table) === selected ? ('downstream' as const) : ('upstream' as const),
        neighbor: nodeKey(e.from_schema, e.from_table) === selected ? nodeKey(e.to_schema, e.to_table) : nodeKey(e.from_schema, e.from_table),
        edge_type: e.edge_type,
        evidence: e.evidence,
      }))
  }, [selected, lineage])

  const selectedFieldView = useMemo(() => lineage?.field_lineage.resolved_views.find(v => nodeKey(v.schema, v.table) === selected) ?? null, [lineage, selected])
  const selectedFieldUnparsed = useMemo(() => lineage?.field_lineage.unparsed_views.find(v => nodeKey(v.schema, v.table) === selected) ?? null, [lineage, selected])

  const fieldEntries = useMemo(() => {
    if (!lineage) return []
    const q = fieldQuery.trim().toLowerCase()
    return Object.values(lineage.field_index.fields)
      .filter(f => !q || f.field_name.toLowerCase().includes(q))
      .sort((a, b) => b.usages.length - a.usages.length)
      .slice(0, 40)
  }, [lineage, fieldQuery])

  const relationStatus = (node: LineageNode): keyof typeof RELATION_TONE => {
    const key = nodeKey(node.schema, node.table)
    if (confirmedRelationKeys.has(key)) return 'confirmed'
    if (lineage?.suggested_l4_candidates[key]?.length) return 'candidate'
    if (node.zombie_flag === 'suspected_zombie') return 'zombie'
    return 'none'
  }

  if (error) return <div className="panel p-5 text-sm text-accent-danger">{error}</div>
  if (!lineage) return <div className="flex min-h-64 items-center justify-center text-text-muted">正在读取数据血缘图…</div>

  const candidateCount = Object.keys(lineage.suggested_l4_candidates).length
  const zombieNodes = lineage.nodes.filter(n => n.zombie_flag === 'suspected_zombie')
  const neverActivatedCount = lineage.nodes.filter(n => n.zombie_flag === 'never_activated').length

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-xs text-accent-primary-light"><Workflow className="h-4 w-4" /> 业务数据分析 · 血缘视角</div>
        <h1 className="mt-2 font-heading text-3xl font-bold">104张表谁产出谁、谁消费谁</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">
          边只来自三类真实证据，不做同名字段/表名相似度的推测连接：
          <b className="text-indigo-600">视图SQL依赖</b>(pg_get_viewdef读出的真实FROM/JOIN，最高置信度)、
          <b className="text-sky-600">数据库外键约束</b>(information_schema里声明的真实FK，高置信度)、
          <b className="text-slate-500">同ETL流水线批次产出</b>(sync_history记录的真实airflow流水线同批装载，中置信度——
          只说明"同源"，不代表互为上下游，默认折叠)。没有任何证据的表如实标为"无可查血缘"——
          已核实仓库内外都没有对应ETL脚本，真实生产者在仓库之外，不是分析没做到位。
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-5">
        <div className="panel p-4"><p className="eyebrow">有血缘证据的表</p><p className="mt-2 metric-value">{lineage.nodes.filter(n => n.has_lineage).length}/{lineage.nodes.length}</p></div>
        <div className="panel p-4"><p className="eyebrow">真实血缘边</p><p className="mt-2 metric-value">{lineage.edge_type_counts.view_dependency + lineage.edge_type_counts.foreign_key}</p><p className="mt-1 text-[11px] text-text-muted">视图依赖{lineage.edge_type_counts.view_dependency} + 外键{lineage.edge_type_counts.foreign_key}</p></div>
        <div className="panel p-4"><p className="eyebrow">同流水线批次边</p><p className="mt-2 metric-value">{lineage.edge_type_counts.pipeline_sibling}</p><p className="mt-1 text-[11px] text-text-muted">默认折叠，仅供参考</p></div>
        <div className="panel p-4"><p className="eyebrow">经血缘产生候选L4的表</p><p className="mt-2 metric-value text-amber-600">{candidateCount}</p><p className="mt-1 text-[11px] text-text-muted">此前均标"未定位关联"，未经人工核实</p></div>
        <div className="panel p-4"><p className="eyebrow">疑似僵尸表</p><p className="mt-2 metric-value text-rose-600">{zombieNodes.length}</p><p className="mt-1 text-[11px] text-text-muted">有数据但血缘/L4关联都查不到，另有{neverActivatedCount}张0行未启用</p></div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-1 rounded-lg bg-bg-elevated p-1">
          {(['all', 'public', 'comm_sandbox', 'fin_sandbox'] as const).map(schema => (
            <button key={schema} onClick={() => setSchemaFilter(schema)} className={`rounded-md px-2.5 py-1 text-[11px] transition-colors ${schemaFilter === schema ? 'bg-accent-primary text-white' : 'text-text-secondary hover:text-text-primary hover:bg-bg-surface'}`}>{schema === 'all' ? '全部Schema' : schema}</button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-[11px] text-text-muted">
          按L3切片
          <select value={l3Slice} onChange={e => { setL3Slice(e.target.value); setSelected(null) }} className="rounded-md border border-border-default bg-bg-elevated px-2 py-1 text-[11px] text-text-primary">
            <option value="all">全部104张表(完整图)</option>
            {l3Options.map(([code, entry]) => <option key={code} value={code}>{code} · {entry.name}（{entry.keys.size}张核心表）</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1.5 text-[11px] text-text-muted">
          <input type="checkbox" checked={showPipelineSibling} onChange={e => setShowPipelineSibling(e.target.checked)} />
          显示"同流水线批次"弱关联线({lineage.edge_type_counts.pipeline_sibling}条，默认隐藏)
        </label>
        <div className="relative ml-auto max-w-xs">
          <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-text-muted" />
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索表名/中文含义高亮" className="w-full rounded-lg border border-border-default bg-bg-elevated py-1.5 pl-8 pr-3 text-xs text-text-primary placeholder:text-text-muted" />
        </div>
      </div>
      {l3Slice !== 'all' && (
        <p className="text-[11px] text-text-muted">
          切片视图：绿色实心为{l3Slice}确认关联的核心表({sliceCoreKeys?.size ?? 0}张)，虚线边框的是它们的真实血缘邻居——不代表这些邻居也属于{l3Slice}，只是"和核心表有真实数据关系，值得去核实"。
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        <div className="panel overflow-auto p-2" style={{ maxHeight: 720 }}>
          <svg viewBox="0 0 1100 820" width={1100} height={820} className="block">
            <defs>
              <marker id="arrow-view" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L6,3 z" fill={EDGE_TONE.view_dependency.stroke} /></marker>
              <marker id="arrow-fk" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L6,3 z" fill={EDGE_TONE.foreign_key.stroke} /></marker>
            </defs>
            {visibleEdges.map((e, i) => {
              const a = layout.get(nodeKey(e.from_schema, e.from_table))
              const b = layout.get(nodeKey(e.to_schema, e.to_table))
              if (!a || !b) return null
              const tone = EDGE_TONE[e.edge_type]
              const dim = query && !filteredKeys.has(nodeKey(e.from_schema, e.from_table)) && !filteredKeys.has(nodeKey(e.to_schema, e.to_table))
              const highlighted = selected && (nodeKey(e.from_schema, e.from_table) === selected || nodeKey(e.to_schema, e.to_table) === selected)
              return (
                <line
                  key={i}
                  x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                  stroke={tone.stroke}
                  strokeWidth={highlighted ? 2.5 : 1}
                  strokeDasharray={tone.dash}
                  opacity={dim ? 0.08 : highlighted ? 0.95 : e.edge_type === 'pipeline_sibling' ? 0.25 : 0.45}
                  markerEnd={e.edge_type === 'view_dependency' ? 'url(#arrow-view)' : e.edge_type === 'foreign_key' ? 'url(#arrow-fk)' : undefined}
                />
              )
            })}
            {laidOutNodes.map(n => {
              const status = relationStatus(n)
              const dim = query && !filteredKeys.has(n.key)
              const isSelected = selected === n.key
              const isNeighborOnly = sliceCoreKeys !== null && !sliceCoreKeys.has(n.key)
              const radius = 6 + Math.min(n.degree, 10) * 1.1
              return (
                <g key={n.key} transform={`translate(${n.x},${n.y})`} className="cursor-pointer" onClick={() => setSelected(isSelected ? null : n.key)} opacity={dim ? 0.15 : isNeighborOnly ? 0.6 : 1}>
                  <circle r={radius} fill={RELATION_TONE[status].fill} stroke={isSelected ? '#1e293b' : 'white'} strokeWidth={isSelected ? 2.5 : 1.5} strokeDasharray={isNeighborOnly ? '2 2' : undefined} />
                  {(isSelected || n.degree >= 4 || sliceCoreKeys !== null || (query && filteredKeys.has(n.key))) && (
                    <text x={radius + 4} y={4} fontSize={10} fill="currentColor" className="select-none fill-text-primary">
                      {n.table}{isNeighborOnly ? '（邻居）' : ''}
                    </text>
                  )}
                </g>
              )
            })}
          </svg>
        </div>

        <div className="space-y-3">
          <div className="panel p-3">
            <p className="text-xs font-semibold text-text-primary">图例</p>
            <div className="mt-2 space-y-1.5 text-[11px] text-text-secondary">
              {(Object.entries(RELATION_TONE) as [keyof typeof RELATION_TONE, typeof RELATION_TONE[keyof typeof RELATION_TONE]][]).map(([key, tone]) => (
                <div key={key} className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full" style={{ background: tone.fill }} />{tone.label}</div>
              ))}
              {(Object.entries(lineage.edge_type_labels) as [LineageEdgeType, string][]).map(([key, label]) => (
                <div key={key} className="flex items-center gap-2"><span className="h-0.5 w-4" style={{ background: EDGE_TONE[key].stroke, opacity: key === 'pipeline_sibling' ? 0.5 : 1 }} />{label}</div>
              ))}
            </div>
          </div>

          {selectedNode ? (
            <div className="panel p-3">
              <p className="font-mono text-sm font-bold text-text-primary">{selected}</p>
              <p className="mt-0.5 text-xs text-text-secondary">{selectedNode.business_label}</p>
              <p className="mt-1 text-[10px] text-text-muted">{selectedNode.table_type} · {selectedNode.row_count.toLocaleString()}行</p>

              {lineage.suggested_l4_candidates[selected ?? '']?.length ? (
                <div className="mt-3 rounded-md border border-dashed border-amber-300 bg-amber-400/10 p-2">
                  <p className="text-[11px] font-semibold text-amber-800">血缘候选L4(待核实，非确认关联)</p>
                  {lineage.suggested_l4_candidates[selected ?? ''].map((c, i) => (
                    <div key={i} className="mt-1.5 text-[10px] leading-4 text-amber-800">
                      <span className="font-mono">{c.l3_code}</span> {c.l4_name} · 经由 <span className="font-mono">{c.via_table}</span>（{lineage.edge_type_labels[c.edge_type]}）
                      <p className="text-amber-700/80">{c.evidence}</p>
                    </div>
                  ))}
                </div>
              ) : null}

              <div className="mt-3">
                <p className="text-[11px] font-semibold text-text-primary">上下游({selectedNeighbors.length})</p>
                <div className="mt-1.5 max-h-80 space-y-1.5 overflow-auto">
                  {selectedNeighbors.length === 0 && <p className="text-[10px] text-text-muted">无</p>}
                  {selectedNeighbors.map((nb, i) => (
                    <div key={i} className="rounded-md bg-bg-surface p-1.5 text-[10px] leading-4">
                      <span className={`mr-1 rounded px-1 ${nb.direction === 'upstream' ? 'bg-sky-100 text-sky-700' : 'bg-emerald-100 text-emerald-700'}`}>{nb.direction === 'upstream' ? '上游→本表' : '本表→下游'}</span>
                      <span className="font-mono text-text-secondary">{nb.neighbor}</span>
                      <p className="text-text-muted">{nb.evidence}</p>
                    </div>
                  ))}
                </div>
              </div>

              {selectedFieldView && (
                <div className="mt-3">
                  <p className="text-[11px] font-semibold text-text-primary">字段级血缘({selectedFieldView.columns.length}列，来自真实SQL解析)</p>
                  <div className="mt-1.5 max-h-80 space-y-1 overflow-auto">
                    {selectedFieldView.columns.map((col, i) => (
                      <div key={i} className="rounded-md bg-bg-surface p-1.5 text-[10px] leading-4">
                        <span className="font-mono text-text-primary">{col.output_column}</span>
                        <span className="ml-1.5 rounded bg-indigo-100 px-1 text-indigo-700">{TRANSFORM_LABEL[col.transform]}</span>
                        {col.sources.length > 0 && (
                          <p className="mt-0.5 text-text-muted">
                            {col.sources.map(s => `${s.schema}.${s.table}.${s.column}`).join('、')}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {selectedFieldUnparsed && (
                <p className="mt-3 text-[10px] text-text-muted">字段级血缘：{selectedFieldUnparsed.reason}，如实跳过，不猜测。</p>
              )}
            </div>
          ) : (
            <div className="panel flex items-start gap-2 p-3 text-[11px] text-text-muted">
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              点击图上任意一个点，查看该表的真实上下游、证据原文，以及经血缘推导出的候选L4关联。
            </div>
          )}
        </div>
      </div>

      <div className="panel p-4">
        <p className="text-sm font-semibold text-rose-700">疑似僵尸表（{zombieNodes.length}）</p>
        <p className="mt-1 text-[11px] text-text-muted">
          有真实数据(非0行)，但血缘查不到谁产出它、谁消费它，L4分析也没人认领——值得去核实是不是真的没人用了。
          这不是自动下线建议，核实结果可能是"确实废弃"，也可能只是"业务方在用、只是还没接入我们的分析"。
        </p>
        <div className="mt-3 space-y-1">
          {zombieNodes.sort((a, b) => b.row_count - a.row_count).map(n => (
            <div key={nodeKey(n.schema, n.table)} className="flex items-center gap-2 rounded-md bg-rose-50 px-2 py-1 text-[11px]">
              <span className="font-mono text-rose-800">{n.schema}.{n.table}</span>
              <span className="text-rose-700/80">{n.business_label}</span>
              <span className="ml-auto text-rose-600">{n.row_count.toLocaleString()}行</span>
            </div>
          ))}
        </div>
      </div>

      <div className="panel p-4">
        <p className="text-sm font-semibold text-text-primary">无可查血缘的表（{isolatedNodes.length}，含上面的疑似僵尸表）</p>
        <p className="mt-1 text-[11px] text-text-muted">已核实：既不是视图、没有声明外键，也没有命名ETL流水线的同批装载记录——真实生产者在本仓库之外，不是分析遗漏。</p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {isolatedNodes.map(n => (
            <span key={nodeKey(n.schema, n.table)} className="rounded-full bg-bg-surface px-2 py-1 font-mono text-[10px] text-text-muted" title={n.business_label}>{n.schema}.{n.table}</span>
          ))}
        </div>
      </div>

      <div className="panel p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-semibold text-text-primary">同名字段跨表索引（{Object.keys(lineage.field_index.fields).length}个共享字段名，按使用表数排序显示前40个）</p>
          <div className="relative max-w-xs">
            <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-text-muted" />
            <input value={fieldQuery} onChange={e => setFieldQuery(e.target.value)} placeholder="搜索字段名" className="w-full rounded-lg border border-border-default bg-bg-elevated py-1.5 pl-8 pr-3 text-xs text-text-primary placeholder:text-text-muted" />
          </div>
        </div>
        <p className="mt-1 text-[11px] text-text-muted">{lineage.field_index.source_policy}</p>
        <div className="mt-3 space-y-2">
          {fieldEntries.map(field => (
            <details key={field.field_name} className="rounded-lg border border-border-default bg-bg-elevated">
              <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-3 py-2">
                <span className="font-mono text-xs font-bold text-text-primary">{field.field_name}</span>
                <span className="text-[10px] text-text-muted">源头：{field.origin_tables.length > 0 ? field.origin_tables.map(o => `${o.schema}.${o.table}`).join('、') : '无声明主键的源头'}</span>
                <span className="ml-auto rounded-full bg-bg-surface px-2 py-0.5 text-[10px] text-text-secondary">出现在{field.usages.length}张表</span>
              </summary>
              <div className="border-t border-border-default p-2">
                <div className="flex flex-wrap gap-1.5">
                  {field.usages.map(u => (
                    <span key={`${u.schema}.${u.table}`} className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${FIELD_CONFIDENCE_TONE[u.confidence]}`} title={u.fk_target ? `外键指向${u.fk_target.schema}.${u.fk_target.table}.${u.fk_target.column}` : undefined}>
                      {u.schema}.{u.table} · {FIELD_CONFIDENCE_LABEL[u.confidence]}
                    </span>
                  ))}
                </div>
              </div>
            </details>
          ))}
        </div>
      </div>
    </div>
  )
}
