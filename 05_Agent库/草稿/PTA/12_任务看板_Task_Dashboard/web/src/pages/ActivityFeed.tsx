import { useEffect, useState } from 'react'
import { Search } from 'lucide-react'
import { fetchActivityFeed, fetchObSearch, type ActivityFeedEntry, type ChangeItem } from '../lib/api'

function groupByDomain(changes: ChangeItem[]): Record<string, ChangeItem[]> {
  const groups: Record<string, ChangeItem[]> = {}
  for (const c of changes) {
    (groups[c.domain] ??= []).push(c)
  }
  return groups
}

function ProjectFeedCard({ entry }: { entry: ActivityFeedEntry }) {
  const groups = groupByDomain(entry.changes)
  const total = entry.files_added + entry.files_changed + entry.files_removed

  return (
    <div className="rounded-radius-md border border-border-default bg-bg-elevated p-4">
      <div className="flex items-center justify-between">
        <span className="font-medium text-sm">{entry.project_name}</span>
        <span className="text-xs text-text-muted">
          {new Date(entry.generated_at).toLocaleString('zh-CN')}
        </span>
      </div>

      {total === 0 ? (
        <p className="text-sm text-text-muted mt-2">最近一次巡检无变化</p>
      ) : (
        <div className="mt-3 space-y-3">
          {Object.entries(groups).map(([domain, items]) => (
            <div key={domain}>
              <div className="text-xs font-medium text-text-secondary mb-1">{domain}（{items.length}处）</div>
              <ul className="space-y-0.5">
                {items.map((c, i) => (
                  <li key={i} className="text-xs text-text-muted">
                    <span className="text-text-secondary">[{c.who}]</span> {c.file}：{c.summary}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {entry.resolved_tasks.length > 0 && (
        <div className="mt-3 border-t border-border-default pt-2 space-y-1">
          {entry.resolved_tasks.map((t) => (
            <div key={t.task_id} className="text-xs text-accent-success">
              ✅ {t.task_id} · {t.name}
              {t.evidence && <span className="text-text-muted"> — {t.evidence}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ObSearchBox() {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [searched, setSearched] = useState(false)

  async function runSearch() {
    if (!query.trim()) return
    setLoading(true)
    setSearched(true)
    try {
      const res = await fetchObSearch(query)
      setResult(res.background)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section>
      <h2 className="text-sm font-medium text-text-secondary mb-3">OB 背景检索</h2>
      <div className="flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && runSearch()}
          placeholder="输入关键词查OB知识库背景，例如：价值节点"
          className="flex-1 rounded-radius-sm border border-border-default bg-bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-border-hover"
        />
        <button
          onClick={runSearch}
          disabled={loading || !query.trim()}
          className="flex items-center gap-1.5 rounded-radius-sm bg-accent-primary px-3 py-2 text-sm text-white disabled:opacity-50"
        >
          <Search size={14} /> {loading ? '检索中…' : '检索'}
        </button>
      </div>
      {searched && !loading && (
        <div className="mt-3 rounded-radius-md border border-border-default bg-bg-elevated p-4">
          {result ? (
            <pre className="text-xs text-text-secondary whitespace-pre-wrap font-mono">{result}</pre>
          ) : (
            <p className="text-sm text-text-muted">未检索到相关背景</p>
          )}
        </div>
      )}
    </section>
  )
}

export function ActivityFeed() {
  const [feed, setFeed] = useState<ActivityFeedEntry[] | null>(null)

  useEffect(() => {
    fetchActivityFeed().then(setFeed)
  }, [])

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-8">
      <h1 className="text-lg font-heading font-medium">今日动态</h1>

      <section className="space-y-3">
        {feed === null ? (
          <p className="text-sm text-text-muted">加载中…</p>
        ) : feed.length === 0 ? (
          <p className="text-sm text-text-muted">还没有任何项目跑过daily-scan</p>
        ) : (
          feed.map((entry) => <ProjectFeedCard key={entry.project_name} entry={entry} />)
        )}
      </section>

      <ObSearchBox />
    </div>
  )
}
