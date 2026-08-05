import { useEffect, useRef } from 'react'
import cytoscape from 'cytoscape'
import dagre from 'cytoscape-dagre'
import type { LineageEdge, LineageEdgeType, LineageNode } from '../lib/dataLineage'

cytoscape.use(dagre)

export interface LineageGraphProps {
  nodes: LineageNode[]
  edges: LineageEdge[]
  /** 血缘上/下游跳数 */
  hops: 1 | 2
  /** 焦点表 key（schema.table）；空则显示全部 */
  focusKey?: string | null
  /** schema 过滤（总览着色） */
  focusSchema?: string | null
  onSelect?: (schema: string, table: string) => void
}

const EDGE_COLOR: Record<LineageEdgeType, string> = {
  view_dependency: '#6366f1',
  foreign_key: '#0ea5e9',
  pipeline_sibling: '#94a3b8',
}

/** 节点类型 → 颜色 */
function nodeColor(n: LineageNode): string {
  if (n.row_count === 0) return '#e2e8f0'
  if (n.zombie_flag === 'suspected_zombie') return '#e11d48'
  const t = n.table_type
  if (t === '视图' || t === '桥接表' || t === '映射表') return '#0ea5e9'
  if (t === '配置表' || t === '维度表' || t === '规则表') return '#8ca3e8'
  return '#6366f1'
}

/** 收集焦点表的 k 跳子图（上游+下游） */
function collectSubgraph(
  allNodes: LineageNode[],
  allEdges: LineageEdge[],
  focusKey: string | null,
  hops: 1 | 2,
): { nodes: LineageNode[]; edges: LineageEdge[] } {
  if (!focusKey) return { nodes: allNodes, edges: allEdges }
  const keySet = new Set([focusKey])
  let frontier = new Set([focusKey])
  for (let h = 0; h < hops; h++) {
    const next = new Set<string>()
    for (const e of allEdges) {
      const a = `${e.from_schema}.${e.from_table}`
      const b = `${e.to_schema}.${e.to_table}`
      if (frontier.has(a) && !keySet.has(b)) { keySet.add(b); next.add(b) }
      if (frontier.has(b) && !keySet.has(a)) { keySet.add(a); next.add(a) }
    }
    frontier = next
  }
  const edges = allEdges.filter(e => {
    const a = `${e.from_schema}.${e.from_table}`
    const b = `${e.to_schema}.${e.to_table}`
    return keySet.has(a) && keySet.has(b)
  })
  const nodes = allNodes.filter(n => keySet.has(`${n.schema}.${n.table}`))
  return { nodes, edges }
}

export default function LineageGraph({ nodes, edges, hops, focusKey, focusSchema, onSelect }: LineageGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const { nodes: subNodes, edges: subEdges } = collectSubgraph(nodes, edges, focusKey ?? null, hops)
    const isOverview = !focusKey
    const elements: cytoscape.ElementDefinition[] = []
    subNodes.forEach(n => {
      const k = `${n.schema}.${n.table}`
      elements.push({
        data: {
          id: k,
          label: n.table,
          schema: n.schema,
          business_label: n.business_label,
          table_type: n.table_type,
          row_count: n.row_count,
          isFocus: k === focusKey,
          color: !focusSchema || n.schema === focusSchema ? nodeColor(n) : '#cbd5e1',
        },
      })
    })
    subEdges.forEach(e => {
      elements.push({
        data: {
          id: `${e.from_schema}.${e.from_table}__${e.to_schema}.${e.to_table}__${e.edge_type}`,
          source: `${e.from_schema}.${e.from_table}`,
          target: `${e.to_schema}.${e.to_table}`,
          edge_type: e.edge_type,
          color: EDGE_COLOR[e.edge_type] ?? '#94a3b8',
          dash: e.edge_type === 'pipeline_sibling' ? 'dashed' : 'solid',
          label: e.edge_type === 'view_dependency' ? '视图依赖' : e.edge_type === 'foreign_key' ? '外键' : '流水线同批',
        },
      })
    })
    const style = [
      {
        selector: 'node',
        style: {
          'background-color': 'data(color)',
          'border-width': 'data(isFocus)',
          'border-color': '#1e293b',
          width: 36,
          height: 36,
          shape: 'roundrectangle' as const,
        },
      },
      {
        selector: 'node[label]',
        style: {
          label: 'data(label)',
          color: '#0f172a',
          'font-size': 9,
          'text-valign': 'bottom' as const,
          'text-margin-y': 6,
          'text-background-color': '#ffffff',
          'text-background-opacity': 0.7,
          'text-background-padding': '2px',
        },
      },
      {
        selector: 'node:parent',
        style: {
          'border-width': 1,
          'border-color': '#cbd5e1',
          'background-color': '#f8fafc',
          'background-opacity': 0.6,
          label: 'data(label)',
          'font-size': 11,
          'text-valign': 'top' as const,
          'text-margin-y': 2,
          color: '#334155',
          'font-weight': 'bold' as const,
        },
      },
      {
        selector: 'node:selected',
        style: { 'border-width': 4, 'border-color': '#f59e0b' },
      },
      {
        selector: 'edge',
        style: {
          width: 1.5,
          'line-color': 'data(color)',
          'target-arrow-color': 'data(color)',
          'target-arrow-shape': 'triangle' as const,
          'curve-style': 'bezier',
          'arrow-scale': 1,
          'line-style': 'data(dash)' as const,
          label: 'data(label)',
          'font-size': 8,
          'text-background-color': '#ffffff',
          'text-background-opacity': 0.8,
          'text-background-padding': '2px',
          color: '#64748b',
        },
      },
    ]
    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style,
      wheelSensitivity: 0.4,
      minZoom: 0.15,
      maxZoom: 4,
      boxSelectionEnabled: false,
    })

    // dagre 布局：LR 分层（上游左 → 下游右），ranksep/nodesep 拉开避免粘连
    // 说明：dagre 插件选项为自有类型，cytoscape 核心类型覆盖不到，故 layout config 用 Record<string, unknown>
    const layoutOptions: Record<string, unknown> = {
      name: 'dagre',
      rankDir: 'LR',
      directed: true,
      rankSep: isOverview ? 70 : 90,
      nodeSep: isOverview ? 45 : 110,
      edgeSep: 30,
      spacingFactor: isOverview ? 1.3 : 1.6,
      padding: 30,
      animate: true,
      animationDuration: 250,
      fit: true,
      nodeDimensionsIncludeLabels: true,
    }
    // dagre 为图形布局插件，其选项不在 cytoscape 核心静态类型中，断言绕过（运行时由插件解析）
    const layout = cy.layout(layoutOptions as unknown as cytoscape.LayoutOptions)
    layout.run()

    cy.one('layoutstop', () => {
      if (containerRef.current) {
        const w = containerRef.current.clientWidth || 900
        const h = containerRef.current.clientHeight || 480
        const bb = cy.elements().boundingBox({ includeLabels: true })
        if (bb.w > 0 && bb.h > 0) {
          // 自适应缩放和平移，让图占满可视区又不被截断
          const scale = Math.min(w / bb.w, h / bb.h) * 0.92
          cy.zoom(Math.max(0.2, Math.min(1.2, scale)))
          cy.center()
        }
      }
      if (focusKey) {
        // 聚焦：把焦点表移动到可视区中央稍偏左，便于右侧看下游
        const focusNode = cy.getElementById(focusKey)
        if (focusNode.length) cy.center(focusNode)
      }
    })

    cy.on('tap', 'node', (evt) => {
      const d = (evt.target as cytoscape.NodeSingular).data()
      if (onSelect) onSelect(d.schema as string, d.label as string)
    })
    cy.on('tap', (evt) => {
      // 点击空白取消聚焦高亮（可选）
      if (evt.target === cy) cy.elements().unselect()
    })
    cyRef.current = cy
    return () => { cy.destroy(); cyRef.current = null }
  }, [nodes, edges, hops, focusKey, focusSchema, onSelect])

  return (
    <div className="relative">
      <div ref={containerRef} style={{ width: '100%', height: 480 }} />
      <div className="pointer-events-none absolute bottom-2 left-2 z-10 text-[10px] text-text-muted">滚轮缩放 · 拖拽平移 · 点节点切换焦点 · 因dagre按血缘方向左右分层，清晰可读</div>
    </div>
  )
}
