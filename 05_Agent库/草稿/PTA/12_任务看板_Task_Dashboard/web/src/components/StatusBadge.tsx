// 从app_v2(VNW自己的前端)搬运的写法(lookup-table + fallback样式)，扩展了
// PTA任务生命周期需要的几个新状态(新增/搁置中/已完成/已关闭)。

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    '新增': 'bg-indigo-500/15 text-indigo-400',
    '搁置中': 'bg-amber-500/15 text-amber-400',
    'done': 'bg-green-500/15 text-green-400',
    'dismissed': 'bg-bg-surface text-text-muted',
  }
  const cls = map[status] || 'bg-bg-surface text-text-muted'
  return <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${cls}`}>{status || '-'}</span>
}

export function PriorityBadge({ priority }: { priority: string }) {
  const map: Record<string, string> = {
    'P0': 'bg-red-500 text-white',
    'P1': 'bg-amber-500 text-black',
    'P2': 'bg-blue-500 text-white',
    'P3': 'bg-bg-surface text-text-muted',
  }
  return <span className={`inline-block rounded px-2 py-0.5 text-xs font-bold ${map[priority] || 'bg-bg-surface text-text-muted'}`}>{priority || '-'}</span>
}
