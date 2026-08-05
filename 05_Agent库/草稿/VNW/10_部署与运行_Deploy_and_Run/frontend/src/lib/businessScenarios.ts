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
