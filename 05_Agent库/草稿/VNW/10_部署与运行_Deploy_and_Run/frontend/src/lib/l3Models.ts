export type GateStatus = 'PASS' | 'PARTIAL' | 'FAIL' | 'BLOCKED'

export interface ModelIndexItem {
  l3_code: string
  l3_name: string
  l2_capabilities: string[]
  l4_count: number
  value_node_count: number
  blueprint_coverage: 'INDEXED' | 'MISSING'
  blueprint_version: string
  gates: { M: GateStatus; E: GateStatus; A: GateStatus }
  classification: 'MODEL_READY' | 'NEEDS_DATA'
  highest_gate: 'A' | 'E' | 'M' | 'NONE'
  gap_reasons: string[]
  blueprint_structure_status: 'PARSED' | 'INDEX_ONLY' | 'CONFLICT' | 'UNAVAILABLE'
  snapshot_file: string
  has_demo: boolean
  demo_file: string
}

export interface ModelIndex {
  schema_version: string
  source_policy: string
  models: ModelIndexItem[]
}

export interface GateCheck {
  rule_id: string
  passed: boolean
  detail: string
}

export interface L4Item {
  l4_code: string
  l4_name: string
  deliverable: string
  deliverable_type: string
  tier: string
  human_touchpoint: string
  d1_d6: Record<string, unknown>
  evidence_refs: Record<string, string>
}

export interface L3Model {
  snapshot_hash: string
  schema_version: string
  l3_code: string
  l3_name: string
  has_demo: boolean
  demo_file: string
  source_policy: Record<string, unknown>
  blueprint: {
    coverage: string
    version: string
    filename: string
    structure_status: string
    steps: {
      step_id: string
      sequence: number
      step_name: string
      l4_codes: string[]
      activities: string[]
      source_line: number
    }[]
    decisions: {
      decision_id: string
      question: string
      after_step: string
      source_line: number
      branches: {
        label: string
        target_text: string
        target_step: string
        target_l4: string
        is_return: boolean
        source_line: number
      }[]
    }[]
    edges: Record<string, unknown>[]
    blueprint_value_nodes: {
      vn_id: string
      vn_name: string
      priority: string
      deliverable: string
      l4_codes: string[]
      status_text: string
      source_line: number
    }[]
    raci: {
      l4_code: string
      l4_name: string
      accountable: string
      responsible: string
      consulted: string
      informed: string
      source_line: number
    }[]
    diagnostics: {
      db_l4_count?: number
      blueprint_l4_count?: number
      parsed_step_l4_count?: number
      missing_in_blueprint?: string[]
      extra_in_blueprint?: string[]
    }
    note: string
  }
  l2_capabilities: Record<string, unknown>[]
  l4s: L4Item[]
  value_nodes: Record<string, unknown>[]
  vn_l4_mappings: Record<string, unknown>[]
  kpi_mappings: Record<string, unknown>[]
  value_stream_mappings: Record<string, unknown>[]
  gates: Record<'M' | 'E' | 'A', { status: GateStatus; checks: GateCheck[] }>
  evidence_registry: Record<string, unknown>[]
  analysis: {
    schema_version: string
    analysis_standard_id: string
    generation_mode: string
    analysis_status: 'PENDING_MODEL' | 'MODEL_DRAFT' | 'REVIEWED'
    model_run: null | {
      model_name: string
      model_version: string
      prompt_version: string
      generated_at: string
      input_snapshot_hash: string
    }
    source_scope: Record<string, unknown>
    l4_analysis: Record<string, unknown>[]
    tasks: {
      task_id: string
      l4_code: string
      task_name: string
      source_type: string
      evidence_refs: string[]
      analysis_status: string
      suggested_tier: string
      tier_rationale: string
    }[]
    priority_drafts: Record<string, unknown>[]
    decision_drafts: Record<string, unknown>[]
    missing_analysis: string[]
  }
}

export async function loadModelIndex(): Promise<ModelIndex> {
  const response = await fetch('/data/model_snapshots/index.json')
  if (!response.ok) throw new Error('L3模型索引读取失败')
  return response.json()
}

export async function loadL3Model(l3Code: string): Promise<L3Model> {
  const base = `/data/model_snapshots/${encodeURIComponent(l3Code)}`
  const [snapshotResponse, manifestResponse] = await Promise.all([
    fetch(`${base}.json`),
    fetch(`${base}.manifest.json`),
  ])
  if (!snapshotResponse.ok || !manifestResponse.ok) throw new Error(`${l3Code}模型快照读取失败`)
  const [snapshot, manifest] = await Promise.all([snapshotResponse.json(), manifestResponse.json()])
  return { ...snapshot, snapshot_hash: manifest.snapshot_hash }
}
