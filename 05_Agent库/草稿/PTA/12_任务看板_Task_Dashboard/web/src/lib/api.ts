// 只用相对路径 /api/...——开发模式下 vite.config.ts 的 proxy 把它转发到本地
// 8787 端口的 Python 后端；生产模式下同一个 Python 进程既服务这些接口也服务
// 这份前端的静态文件，相对路径天然同源，不需要区分环境配置 base URL。

export interface Task {
  task_id: string
  name: string
  priority: string
  signal_to: string[]
  needs_mark_alignment: boolean
  related_files: string[]
  project_name: string
  days_pending?: number
  status?: string
  status_updated_at?: string
  evidence?: string
  rationale?: string
  relevance_reason?: string
  decision_status?: 'pending_review' | 'accepted' | 'transferred' | 'dismissed' | 'merged'
  decision_updated_at?: string
  owner?: string
  due_date?: string
  acceptance_criteria?: string
  decision_note?: string
  merged_into?: string
  first_suggested?: string
  last_suggested?: string
  execution?: TaskExecution | null
}

export interface StepRisk { level: 'low' | 'high' | 'critical'; label: string; requires_reconfirm: boolean }
export interface ExecutionStepInfo {
  seq: number; action: string; tool: string; command?: string; script?: string; description: string;
  status: string; output?: string; error?: string; risk: StepRisk
}
export interface TaskExecution {
  state: 'plan_ready' | 'dry_run_passed' | 'dry_run_failed' | 'approved'
  prepared_at: string
  plan: { plan_id: string; task_id: string; task_name: string; status: string; steps: ExecutionStepInfo[] }
  risk_level: 'low' | 'high' | 'critical'
  dry_run: null | { status: string; completed: number; failed: number; total: number; run_at: string; steps: ExecutionStepInfo[] }
  approved_at: string | null
  approval_note: string
  requires_explicit_execute?: boolean
}

export interface TaskBuckets {
  new: Task[]
  aging: Task[]
  resolved_recent: Task[]
}

export interface ProjectInfo {
  name: string
  project_root: string
  exists: boolean
  last_daily_scan: { timestamp: string; report_path: string } | null
}

export interface PipelineStatus {
  report_date: string | null
  drift_count: number
  report_path: string | null
}

export interface DriftRow {
  stage: string
  dimension: string
  claim: string
  actual: string
  note: string
}

export interface DriftDetail {
  report_date: string | null
  report_path: string | null
  drift_rows: DriftRow[]
}

export interface ExecutionHistoryEntry {
  task_id: string
  summary: string
  status: string
  success_rate: string
  mode: string
  timestamp: string
  run_dir?: string
  project_name: string
}

export interface ChangeItem {
  file: string
  summary: string
  who: string
  domain: string
}

export interface RelationshipItem {
  description: string
  related_files: string[]
}

export interface ResolvedTaskItem {
  task_id: string
  name: string
  status: string
  evidence: string
}

export interface ActivityFeedEntry {
  project_name: string
  generated_at: string
  files_added: number
  files_changed: number
  files_removed: number
  changes: ChangeItem[]
  relationships: RelationshipItem[]
  resolved_tasks: ResolvedTaskItem[]
  skipped_llm_call: boolean
}

export interface LaunchdJob {
  label: string
  pid: string | null
  last_exit_code: number | null
  healthy: boolean
}

export type AgentStatusValue = '自动' | '人工' | '未搭建' | '死的'

export interface AgentStatusInfo {
  agent_id: string
  display_name: string
  description: string
  status: AgentStatusValue
  has_code: boolean
  launchd_jobs: LaunchdJob[]
}

export interface SkillUsageEntry {
  skill: string
  count: number
  last_called: string
}

export interface AgentMonitorResponse {
  agents: AgentStatusInfo[]
  skill_usage: SkillUsageEntry[]
}

export interface ObSearchResult {
  query: string
  found: boolean
  background: string | null
}

export interface WatchedProjectConfig {
  name: string
  project_root: string
  exclude_dirs?: string[]
  exclude_note?: string
}

async function getJSON<T>(url: string): Promise<T> {
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`${url} 请求失败: HTTP ${resp.status}`)
  return resp.json()
}

export function fetchProjects(): Promise<ProjectInfo[]> {
  return getJSON('/api/projects')
}

export function fetchTasks(project: string = 'all'): Promise<TaskBuckets> {
  return getJSON(`/api/tasks?project=${encodeURIComponent(project)}`)
}

export function fetchPipelineStatus(): Promise<PipelineStatus> {
  return getJSON('/api/pipeline-status')
}

export function fetchPipelineDriftDetail(): Promise<DriftDetail> {
  return getJSON('/api/pipeline-drift-detail')
}

export function fetchExecutionHistory(project: string = 'all', limit: number = 30): Promise<ExecutionHistoryEntry[]> {
  return getJSON(`/api/execution-history?project=${encodeURIComponent(project)}&limit=${limit}`)
}

export function fetchActivityFeed(project: string = 'all'): Promise<ActivityFeedEntry[]> {
  return getJSON(`/api/activity-feed?project=${encodeURIComponent(project)}`)
}

export function fetchAgentMonitor(): Promise<AgentMonitorResponse> {
  return getJSON('/api/agent-monitor')
}

export function fetchObSearch(query: string): Promise<ObSearchResult> {
  return getJSON(`/api/ob-search?query=${encodeURIComponent(query)}`)
}

export function fetchWatchedProjects(): Promise<WatchedProjectConfig[]> {
  return getJSON('/api/watched-projects')
}

export async function addWatchedProject(
  name: string,
  projectRoot: string,
  excludeDirs?: string[],
): Promise<{ success: boolean; error?: string; seeded_files?: number }> {
  const resp = await fetch('/api/watched-projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, project_root: projectRoot, exclude_dirs: excludeDirs }),
  })
  return resp.json()
}

export async function removeWatchedProject(name: string): Promise<{ success: boolean; error?: string }> {
  const resp = await fetch(`/api/watched-projects/${encodeURIComponent(name)}`, { method: 'DELETE' })
  return resp.json()
}

export async function setTaskStatus(
  project: string,
  taskId: string,
  status: 'dismissed' | 'pending',
): Promise<{ found: boolean }> {
  const resp = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project, status }),
  })
  if (!resp.ok) throw new Error(`关闭/重开任务失败: HTTP ${resp.status}`)
  return resp.json()
}

export interface TaskDecisionInput {
  decision_status: 'pending_review' | 'accepted' | 'transferred' | 'dismissed' | 'merged'
  title?: string
  priority?: string
  owner?: string
  due_date?: string
  acceptance_criteria?: string
  decision_note?: string
  merged_into?: string
}

export async function decideTask(project: string, taskId: string, input: TaskDecisionInput) {
  const resp = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project, ...input }),
  })
  if (!resp.ok) throw new Error(`保存任务决策失败: HTTP ${resp.status}`)
  return resp.json() as Promise<{ found: boolean }>
}

async function executionAction(project: string, taskId: string, action: 'prepare' | 'dry-run' | 'approve', approval_note = '') {
  const resp = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/execution/${action}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project, approval_note }),
  })
  const payload = await resp.json()
  if (!resp.ok) throw new Error(payload.error || `${action} 失败`)
  return payload as { success: boolean; execution: TaskExecution }
}
export const prepareTaskExecution = (project: string, taskId: string) => executionAction(project, taskId, 'prepare')
export const dryRunTaskExecution = (project: string, taskId: string) => executionAction(project, taskId, 'dry-run')
export const approveTaskExecution = (project: string, taskId: string, note = '') => executionAction(project, taskId, 'approve', note)
