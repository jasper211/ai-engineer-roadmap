export interface ScenarioIndexEntry {
  scenario_id: string
  scenario_name: string
  status: 'DRAFT' | 'CONFIRMED'
  raised_by: string
  raised_at: string
  component_count: number
  state_counts: Record<string, number>
  file: string
}

export interface ScenarioIndex {
  schema_version: string
  scenarios: ScenarioIndexEntry[]
}

export interface ScenarioComponent {
  component_name: string
  component_type: string
  kpi_refs: string[]
  kpi_note?: string
  l3_trace: {
    l3_code: string
    in_current_db: boolean
    gate_a?: string
    note: string
  }[]
  business_evidence: {
    schema: string
    table: string
    row_count: number
    note: string
  }[]
  state: 'A' | 'B' | 'C'
  conclusion: string
}

export interface BusinessScenario {
  schema_version: string
  scenario_id: string
  scenario_name: string
  raised_by: string
  raised_at: string
  status: 'DRAFT' | 'CONFIRMED'
  definition: string
  definition_note?: string
  components: ScenarioComponent[]
  overall_conclusion: string
  next_steps: string[]
}

export async function loadScenarioIndex(): Promise<ScenarioIndex> {
  const response = await fetch('/data/business_scenarios/index.json')
  if (!response.ok) throw new Error('业务场景索引读取失败')
  return response.json()
}

export async function loadScenario(file: string): Promise<BusinessScenario> {
  const response = await fetch(`/data/business_scenarios/${file}`)
  if (!response.ok) throw new Error('业务场景记录读取失败')
  return response.json()
}

export interface ScenarioGoal {
  definition: string
  industry_logic: string
  our_approach: string
}

export interface ScenarioProcessStatusItem {
  activity: string
  relevant_l3s: { l3_code: string; l3_name: string; relationship: '核心支撑' | '部分支撑' | '存在缺口' }[]
  assessment: string
}

export interface ScenarioGovernanceItem {
  need: string
  existing_tables: { schema: string; table: string; assessment: string }[]
  gap: string | null
  new_table_proposal: { suggested_name: string; purpose: string; key_fields: string[] } | null
}

export interface ScenarioTask {
  task_id: string
  description: string
  priority: 'P0' | 'P1' | 'P2'
  depends_on: string[]
  rationale: string
}

export interface ScenarioOptimization {
  target: string
  recommendation: string
  rationale: string
}

export interface ScenarioAnalysis {
  schema_version: string
  scenario_id: string
  generated_at: string
  model_run: { model_name: string; generated_at: string }
  status: 'MODEL_DRAFT' | 'CONFIRMED'
  goal: ScenarioGoal
  process_status: ScenarioProcessStatusItem[]
  data_governance: ScenarioGovernanceItem[]
  task_list: ScenarioTask[]
  process_optimization: ScenarioOptimization[]
}

export async function loadScenarioAnalysis(scenarioId: string): Promise<ScenarioAnalysis | null> {
  const response = await fetch(`/data/business_scenario_analysis/${scenarioId}.json`)
  if (!response.ok) return null
  return response.json()
}
