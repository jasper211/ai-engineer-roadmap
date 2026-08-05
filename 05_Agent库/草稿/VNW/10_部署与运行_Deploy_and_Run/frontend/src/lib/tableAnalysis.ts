export interface TableAnalysisEntry {
  schema: string
  table: string
  row_count: number
  role: string
  layer1: {
    fact_statement: string
    has_data: boolean
  }
  layer2: {
    related_l3_l4: { l3_code: string; l3_name: string; l4_code: string; l4_name: string }[]
    positions: string[]
    data_health: string
    status: string
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
