export type ZombieFlag = 'none' | 'never_activated' | 'field_anchored' | 'utility_support' | 'suspected_zombie'

export interface LineageNode {
  schema: string
  table: string
  table_type: string
  business_label: string
  row_count: number
  has_lineage: boolean
  zombie_flag: ZombieFlag
  utility_support_reason?: string
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

export type FieldTransform = 'direct' | 'derived' | 'computed_literal'

export interface FieldSource {
  schema: string
  table: string
  column: string
}

export interface FieldLineageColumn {
  output_column: string
  transform: FieldTransform
  sources: FieldSource[]
}

export interface ResolvedFieldView {
  schema: string
  table: string
  columns: FieldLineageColumn[]
}

export interface UnparsedFieldView {
  schema: string
  table: string
  reason: string
}

export interface FieldLineage {
  resolved_views: ResolvedFieldView[]
  unparsed_views: UnparsedFieldView[]
}

export type FieldUsageConfidence = 'origin' | 'foreign_key_confirmed' | 'same_name_business_confirmed'

export interface FieldUsage {
  schema: string
  table: string
  confidence: FieldUsageConfidence
  fk_target: { schema: string; table: string; column: string } | null
}

export interface FieldIndexEntry {
  field_name: string
  origin_tables: { schema: string; table: string }[]
  usages: FieldUsage[]
}

export interface FieldIndex {
  schema_version: string
  source_policy: string
  fields: Record<string, FieldIndexEntry>
}

export interface FieldAnchorLink {
  field: string
  linked_tables: string[]
  origin_tables: string[]
}

export interface DataLineage {
  schema_version: string
  source_policy: string
  edge_type_labels: Record<LineageEdgeType, string>
  edge_type_counts: Record<LineageEdgeType, number>
  nodes: LineageNode[]
  edges: LineageEdge[]
  suggested_l4_candidates: Record<string, LineageL4Candidate[]>
  field_lineage: FieldLineage
  field_index: FieldIndex
  field_anchor_links: Record<string, FieldAnchorLink[]>
}

export async function loadDataLineage(): Promise<DataLineage> {
  const response = await fetch('/data/data_lineage.json')
  if (!response.ok) throw new Error('数据血缘图读取失败')
  return response.json()
}
