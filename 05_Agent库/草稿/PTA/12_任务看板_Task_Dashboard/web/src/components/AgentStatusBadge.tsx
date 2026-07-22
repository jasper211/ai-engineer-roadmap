import type { AgentStatusValue } from '../lib/api'

// 四态跟StatusBadge同样的lookup-table写法——"死的"用danger色重点提示（唯一
// 需要人工介入排查的状态），"自动"用success色，"人工"用info色（中性、不是
// 问题），"未搭建"用muted灰色（还没到需要关注的阶段）。
const MAP: Record<AgentStatusValue, string> = {
  '自动': 'bg-accent-success/15 text-accent-success',
  '人工': 'bg-accent-info/15 text-accent-info',
  '未搭建': 'bg-bg-surface text-text-muted',
  '死的': 'bg-accent-danger/15 text-accent-danger',
}

export function AgentStatusBadge({ status }: { status: AgentStatusValue }) {
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${MAP[status] ?? 'bg-bg-surface text-text-muted'}`}>
      {status}
    </span>
  )
}
