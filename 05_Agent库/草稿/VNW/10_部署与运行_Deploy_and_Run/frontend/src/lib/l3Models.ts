export type GateStatus = 'PASS' | 'CONDITIONAL' | 'PARTIAL' | 'FAIL' | 'BLOCKED'

export interface ModelIndexItem {
  l3_code: string
  l3_name: string
  l2_capabilities: string[]
  l4_count: number
  value_node_count: number
  blueprint_coverage: 'INDEXED' | 'MISSING'
  blueprint_version: string
  gates: { M: GateStatus; E: GateStatus; A: GateStatus }
  classification: 'FULL_MODEL' | 'LIMITED_MODEL' | 'WAITING_INPUT'
  model_generation_allowed: boolean
  readiness_coverage: {
    sop_count: number
    rule_count: number
    deliverable: { covered: number; total: number }
    task: { covered: number; total: number }
    rule_l4: { covered: number; total: number }
    critical_task: { covered: number; total: number }
    skill_feasibility: { verified: number; provisional: number; total: number }
  }
  analysis_status: 'PENDING_MODEL' | 'MODEL_DRAFT' | 'REVIEWED'
  analysis_input_hash: string
  analysis_run_input_hash: string
  production_status: 'READY_TO_RUN' | 'RUN_PREPARED' | 'ANALYSIS_CURRENT' | 'ANALYSIS_INPUT_CHANGED' | 'REVIEWED_BASELINE' | 'BLOCKED_INPUT'
  highest_gate: 'A' | 'E' | 'M' | 'NONE'
  gap_reasons: string[]
  blueprint_structure_status: 'PARSED' | 'INDEX_ONLY' | 'CONFLICT' | 'UNAVAILABLE'
  snapshot_file: string
  has_demo: boolean
  demo_file: string
  value_streams: {
    vs_code: string
    vs_name: string
    stage_code: string
    stage_name: string
    stage_sequence: number | null
  }[]
  kpis: { kpi_name: string; source_type: 'definition' | 'mark_priority_draft' }[]
}

export interface ModelIndex {
  schema_version: string
  source_policy: string
  models: ModelIndexItem[]
  production_summary: Record<ModelIndexItem['production_status'], number>
  recommended_batch: {
    l3_code: string
    l3_name: string
    classification: ModelIndexItem['classification']
    l4_count: number
  }[]
  prepared_batch: ModelIndex['recommended_batch']
  source_update_summary?: {
    generated_at: string
    changed_l3_count: number
    reanalyze_l3_count: number
    blocked_l3_count: number
    applied: boolean
  }
}

export interface SourceUpdateReport {
  schema_version: string
  generated_at: string
  before_l3_count: number
  after_l3_count: number
  changed_l3_count: number
  reanalyze_l3_count: number
  blocked_l3_count: number
  applied: boolean
  changes: {
    l3_code: string
    status: 'ADDED' | 'CHANGED' | 'REMOVED'
    action: 'BLOCKED_INPUT' | 'REANALYSIS_REQUIRED' | 'FACTS_REFRESHED' | 'REMOVE_FROM_CURRENT_SET'
    changed_scopes: string[]
    affected_panels: string[]
    previous_analysis_input_hash: string
    current_analysis_input_hash: string
    added_source_objects: string[]
    removed_source_objects: string[]
  }[]
}

export interface DeliverableAuditFinding {
  l3_code: string
  l4_code: string
  l4_name: string
  issue_type: 'MIXED_CONTENT' | 'REPEATED_VALUE'
  reasons: string[]
  evidence_id: string
  source_value: string
}

export interface DeliverableAudit {
  schema_version: string
  generated_at: string
  scanned_l3_count: number
  affected_l3_count: number
  finding_count: number
  findings: DeliverableAuditFinding[]
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
  skill_feasibility: null | {
    action_nature: string
    action_singularity: string
    grade: string
    judgment_basis: string
    funds_safety_hard_gate: boolean
    physical_execution: boolean
    verification_status: 'VERIFIED' | 'PROVISIONAL'
    recommended_path: string
  }
  position_family: null | {
    family_code: string
    family_name: string
    category_name: string
    category_type: string
  }
  business_evidence: {
    schema: string
    table: string
    row_count: number | null
    matched_columns: string[]
    rationale: string
    confidence: 'strong' | 'weak'
    evidence_type: 'output' | 'rule' | 'workflow' | 'audit'
  }[]
  evidence_refs: Record<string, string>
}

export interface L3Model {
  snapshot_hash: string
  schema_version: string
  l3_code: string
  l3_name: string
  analysis_freshness?: 'CURRENT' | 'INPUT_CHANGED' | 'PENDING_MODEL' | 'UNVERSIONED_REVIEWED_BASELINE'
  has_demo: boolean
  demo_file: string
  source_policy: Record<string, unknown>
  source_locations?: Record<string, {
    rows?: number[]
    lines?: number[]
    record_keys?: string[]
  }>
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
      evidence_ref?: string
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
  kpi_mappings: {
    kpi_code: string
    kpi_name: string
    source_type: 'definition' | 'mark_priority_draft'
    kpi_formula?: string | null
    kpi_unit?: string | null
    kpi_target?: number | null
    measurement_cycle?: string | null
    contribution_weight?: number | null
    weight_confirmed?: string | null
  }[]
  value_stream_mappings: Record<string, unknown>[]
  gates: Record<'M' | 'E' | 'A', { status: GateStatus; checks: GateCheck[] }>
  model_readiness: {
    status: 'FULL_MODEL' | 'LIMITED_MODEL' | 'WAITING_INPUT'
    model_generation_allowed: boolean
    coverage: ModelIndexItem['readiness_coverage']
    linked_sources: {
      sops: { ref: string; file: string; evidence_ref: string }[]
      rules: { rule_id: string; node_id: string; name: string; evidence_ref: string }[]
    }
  }
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
      sequence_no?: number | null
      sequence_status?: 'SOURCE_CONFIRMED' | 'SOURCE_STEP_ONLY' | 'UNCONFIRMED'
      source_step_id?: string
      source_line?: number | null
      previous_task_ids?: string[]
      next_task_ids?: string[]
      relation_type?: 'SEQUENTIAL' | 'PARALLEL' | 'BRANCH' | 'RETURN' | 'UNCONFIRMED'
      evidence_refs: string[]
      analysis_status: string
      suggested_tier: string
      tier_rationale: string
    }[]
    priority_drafts: Record<string, unknown>[]
    decision_drafts: Record<string, unknown>[]
    control_chain?: {
      level: string
      l4_code: string
      label: string
      tone: string
    }[]
    missing_analysis: string[]
  }
  unified_analysis: {
    schema_version: string
    status: 'DRAFT' | 'CONFIRMED'
    confirmed_by: string | null
    confirmed_at: string | null
    confirmation_notes: string | null
    axis_conflicts: string[]
    coverage: {
      l4_total: number
      business_evidence_covered: number
      position_covered: number
      kpi_count: number
      value_stream_count: number
    }
    gate_a_status: string
    dod_checklist: { item: string; satisfied: boolean; detail?: Record<string, boolean> }[]
    root_cause_ladders: Record<string, {
      layer: string
      grade: string
      statement: string
      axis_conflict?: boolean
    }[]>
  }
}

export async function loadModelIndex(): Promise<ModelIndex> {
  const response = await fetch('/data/model_snapshots/index.json')
  if (!response.ok) throw new Error('L3模型索引读取失败')
  return response.json()
}

export async function loadDeliverableAudit(): Promise<DeliverableAudit> {
  const response = await fetch('/data/l4_deliverable_quality_audit.json')
  if (!response.ok) throw new Error('L4交付物质量审计读取失败')
  return response.json()
}

export async function loadPendingSourceUpdate(): Promise<SourceUpdateReport | null> {
  const response = await fetch('/data/source_updates/pending.json', { cache: 'no-store' })
  if (response.status === 404) return null
  if (!response.ok) throw new Error('源头更新检测结果读取失败')
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
