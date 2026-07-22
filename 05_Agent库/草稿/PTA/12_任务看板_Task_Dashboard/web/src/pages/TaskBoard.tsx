import { useEffect, useState, useCallback } from 'react'
import { fetchProjects, fetchTasks, setTaskStatus, type Task, type TaskBuckets, type ProjectInfo } from '../lib/api'
import { TaskCard } from '../components/TaskCard'

export function TaskBoard() {
  const [projects, setProjects] = useState<ProjectInfo[]>([])
  const [projectFilter, setProjectFilter] = useState('all')
  const [buckets, setBuckets] = useState<TaskBuckets | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setError(null)
      const [projs, tasks] = await Promise.all([fetchProjects(), fetchTasks(projectFilter)])
      setProjects(projs)
      setBuckets(tasks)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [projectFilter])

  useEffect(() => {
    load()
  }, [load])

  const handleToggle = async (task: Task, dismissed: boolean) => {
    // 乐观更新看板本身意义不大（关闭/重开会改变任务所在的桶，重新拉一次
    // 更简单可靠，不用手动维护三个桶之间"这条任务该搬到哪个桶"的逻辑）。
    await setTaskStatus(task.project_name, task.task_id, dismissed ? 'dismissed' : 'pending')
    await load()
  }

  if (error) {
    return (
      <div className="p-6 text-accent-danger">
        加载失败: {error}
        <div className="mt-2 text-sm text-text-muted">确认后端服务是否已启动（python3 api/server.py）</div>
      </div>
    )
  }

  if (!buckets) {
    return <div className="p-6 text-text-muted">加载中…</div>
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-8">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-heading font-medium">任务看板</h1>
        <select
          value={projectFilter}
          onChange={(e) => setProjectFilter(e.target.value)}
          className="ml-auto bg-bg-surface border border-border-default rounded px-3 py-1.5 text-sm"
        >
          <option value="all">全部项目</option>
          {projects.map((p) => (
            <option key={p.name} value={p.name}>{p.name}</option>
          ))}
        </select>
      </div>

      <section>
        <h2 className="text-sm font-medium text-text-secondary mb-3">🆕 新增（{buckets.new.length}）</h2>
        {buckets.new.length === 0 ? (
          <p className="text-sm text-text-muted">没有新任务</p>
        ) : (
          <div className="space-y-2">
            {buckets.new.map((t) => (
              <TaskCard key={t.task_id} task={t} checked={false} onToggle={handleToggle} />
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="text-sm font-medium text-text-secondary mb-3">⏳ 搁置中（{buckets.aging.length}）</h2>
        {buckets.aging.length === 0 ? (
          <p className="text-sm text-text-muted">没有搁置中的任务</p>
        ) : (
          <div className="space-y-2">
            {buckets.aging.map((t) => (
              <TaskCard key={t.task_id} task={t} checked={false} onToggle={handleToggle} />
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="text-sm font-medium text-text-secondary mb-3">✅ 最近完成/关闭（{buckets.resolved_recent.length}）</h2>
        {buckets.resolved_recent.length === 0 ? (
          <p className="text-sm text-text-muted">最近14天没有完成/关闭的任务</p>
        ) : (
          <div className="space-y-2">
            {buckets.resolved_recent.map((t) => (
              // checked=true：已经是done/dismissed状态，勾选框显示✓，
              // 点一下等于"重新开始跟踪"（写回pending）。
              <TaskCard key={t.task_id} task={t} checked={true} onToggle={handleToggle} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
