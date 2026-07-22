import { useEffect, useState } from 'react'
import { Plus, Trash2, Loader2 } from 'lucide-react'
import { fetchWatchedProjects, addWatchedProject, removeWatchedProject, type WatchedProjectConfig } from '../lib/api'

// 新增项目/移除项目——之前只能手改daily_scan_projects.json再手动跑
// --seed-baseline，这里把两步合成一次表单提交：后端add_watched_project()
// 写完配置后立刻建种子基线，不需要用户自己记得再跑一次命令。
export function WatchedProjectManager({ onChanged }: { onChanged?: () => void }) {
  const [projects, setProjects] = useState<WatchedProjectConfig[]>([])
  const [name, setName] = useState('')
  const [root, setRoot] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [removingName, setRemovingName] = useState<string | null>(null)

  const reload = () => fetchWatchedProjects().then(setProjects)

  useEffect(() => {
    reload()
  }, [])

  async function handleAdd() {
    if (!name.trim() || !root.trim() || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const result = await addWatchedProject(name.trim(), root.trim())
      if (!result.success) {
        setError(result.error ?? '新增失败')
        return
      }
      setName('')
      setRoot('')
      await reload()
      onChanged?.()
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRemove(projectName: string) {
    setRemovingName(projectName)
    try {
      await removeWatchedProject(projectName)
      await reload()
      onChanged?.()
    } finally {
      setRemovingName(null)
    }
  }

  return (
    <section>
      <h2 className="text-sm font-medium text-text-secondary mb-3">巡检项目管理</h2>

      <div className="space-y-2 mb-3">
        {projects.map((p) => (
          <div key={p.name} className="rounded-radius-md border border-border-default bg-bg-elevated p-3 flex items-center gap-3">
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium">{p.name}</div>
              <div className="text-xs text-text-muted truncate">{p.project_root}</div>
              {p.exclude_dirs && p.exclude_dirs.length > 0 && (
                <div className="text-xs text-text-muted mt-0.5">排除: {p.exclude_dirs.join('、')}</div>
              )}
            </div>
            <button
              onClick={() => handleRemove(p.name)}
              disabled={removingName === p.name}
              aria-label={`移除 ${p.name}`}
              className="text-text-muted hover:text-accent-danger disabled:opacity-50"
            >
              {removingName === p.name ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
            </button>
          </div>
        ))}
        {projects.length === 0 && <p className="text-sm text-text-muted">还没有配置任何巡检项目</p>}
      </div>

      <div className="flex gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="项目名称"
          className="w-40 rounded-radius-sm border border-border-default bg-bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-border-hover"
        />
        <input
          value={root}
          onChange={(e) => setRoot(e.target.value)}
          placeholder="项目根目录绝对路径"
          className="flex-1 rounded-radius-sm border border-border-default bg-bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-border-hover"
        />
        <button
          onClick={handleAdd}
          disabled={submitting || !name.trim() || !root.trim()}
          className="flex items-center gap-1.5 rounded-radius-sm bg-accent-primary px-3 py-2 text-sm text-white disabled:opacity-50"
        >
          <Plus size={14} /> {submitting ? '新增中…' : '新增'}
        </button>
      </div>
      {error && <p className="text-xs text-accent-danger mt-2">{error}</p>}
      <p className="text-xs text-text-muted mt-2">
        新增后会立即为该项目建立种子基线（不调用LLM），下一次真实巡检起才会真正对比增量变化。
      </p>
    </section>
  )
}
