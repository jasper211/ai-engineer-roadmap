// AIT 轨道判定结果读取。数据来自 AIT 自己的 track_router.py 输出，独立于
// VNW 的 model_snapshots，只读不改——详见 05_Agent库/草稿/AIT/流程设计.md。

export interface AitTaskRoute {
  task_id: string
  l4_code: string
  task_name: string
  suggested_tier: string
  track: '机器规则轨道' | '人的规则轨道' | '待定'
  gate_type: '固定关卡' | '条件关卡' | null
  gate_reason: string | null
  build_agent: boolean
  error?: string
}

export interface AitDecision {
  decision_id: string
  task_name: string
  pilot_scope: string
  human_boundary: string
  selected_by: string
  selected_at: string
  tasks: AitTaskRoute[]
}

export interface AitTrackAssignment {
  schema_version: string
  l3_code: string
  source_decisions: string
  source_snapshot_hash: string
  decisions: AitDecision[]
}

export async function loadAitTrackAssignment(l3Code: string): Promise<AitTrackAssignment | null> {
  const response = await fetch(`/data/ait_track_assignments/${encodeURIComponent(l3Code)}.json`)
  if (!response.ok) return null
  return response.json()
}
