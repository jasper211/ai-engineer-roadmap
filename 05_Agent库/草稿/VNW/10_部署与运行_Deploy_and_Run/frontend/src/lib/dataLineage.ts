export interface LineageNode {
  schema: string
  table: string
  table_type: string
  business_label: string
  row_count: number
  has_lineage: boolean
}

export type LineageEdgeType = 'view_dependency' | 'foreign_key' | 'pipeline_sibling'

export interface LineageEdge {
  from_schema: string
  from_table: string
  to_schema: string
  to_table: string
  edge_type: LineageEdgeType
  evidence: string
}

export interface LineageL4Candidate {
  l3_code: string
  l3_name: string
  l4_code: string
  l4_name: string
  via_table: string
  edge_type: LineageEdgeType
  evidence: string
}

export interface DataLineage {
  schema_version: string
  source_policy: string
  edge_type_labels: Record<LineageEdgeType, string>
  edge_type_counts: Record<LineageEdgeType, number>
  nodes: LineageNode[]
  edges: LineageEdge[]
  suggested_l4_candidates: Record<string, LineageL4Candidate[]>
}

export async function loadDataLineage(): Promise<DataLineage> {
  const response = await fetch('/data/data_lineage.json')
  if (!response.ok) throw new Error('数据血缘图读取失败')
  return response.json()
}
