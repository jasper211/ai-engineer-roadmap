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
  }
  layer3: {
    status: 'BLOCKED' | 'ACTIVE'
    goal: string
    required_inputs: string[]
    reason: string
  }
  layer4: {
    status: 'BLOCKED' | 'ACTIVE'
    goal: string
    required_inputs: string[]
    reason: string
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
  }
}

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
