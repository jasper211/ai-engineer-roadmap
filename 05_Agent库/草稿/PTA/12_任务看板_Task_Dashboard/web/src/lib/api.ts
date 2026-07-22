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
