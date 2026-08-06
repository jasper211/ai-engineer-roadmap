export interface TableAnalysisEntry {
  schema: string
  table: string
  row_count: number
  role: string
  table_type: string
  description: string | null
  business_label: string
  layer1: {
    fact_statement: string
    has_data: boolean
  }
  layer2: {
    related_l3_l4: { l3_code: string; l3_name: string; l4_code: string; l4_name: string }[]
    positions: string[]
    data_health: string
    status: string
    analyzed_l3_coverage: { analyzed: number; total: number }
    shared_master_data: { l3_span_count: number; l3_codes: string[]; reason: string } | null
    utility_support: { reason: string } | null
    field_anchored: { anchors: { field: string; linked_tables: string[]; origin_tables: string[] }[] } | null
    non_business: { reason: string } | null
  }
  layer3: {
    status: 'BLOCKED' | 'MODEL_DRAFT'
    upstream: { key: string; business_label: string; edge_type: string }[]
    downstream: { key: string; business_label: string; edge_type: string }[]
    task_cluster: { label: TaskClusterLabel; rationale: string } | null
    reason?: string
  }
  layer4: {
    status: 'BLOCKED' | 'MODEL_DRAFT'
    hidden_deliverables: {
      l4_code: string
      l4_name: string
      candidate_name: string
      rationale: string
    }[]
    reason?: string
  }
  layer5: {
    status: 'PRELIMINARY' | 'NO_BASIS' | 'CONFIRMED'
    note: string
    l4_quadrants: {
      l4_code: string
      l4_name: string
      quadrant: 'q1' | 'q2' | 'q3' | 'q4'
      quadrant_label: string
      axis_conflict: boolean
      confidence: 'confirmed_basis' | 'draft_basis'
      rationale: string
      classification_basis: 'DERIVED'
    }[]
    governance_track: { flagged: true; reason: string } | null
    process_lever_track: { flagged: true; reason: string } | null
  }
}

export type TaskClusterLabel =
  | '源头采集型'
  | '枢纽整合型'
  | '终端消费型'
  | '规则配置型'
  | '直通转换型'
  | '孤立支撑型'

export interface TableAnalysis {
  schema_version: string
  source_policy: string
  tables: TableAnalysisEntry[]
}

export async function loadTableAnalysis(): Promise<TableAnalysis> {
  const response = await fetch('/data/table_analysis.json')
  if (!response.ok) throw new Error('数据表五层分析读取失败')
  return response.json()
}
