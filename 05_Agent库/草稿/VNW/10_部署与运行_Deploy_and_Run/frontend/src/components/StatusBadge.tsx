
export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    '已完成': 'bg-green-500/15 text-green-400',
    '进行中': 'bg-indigo-500/15 text-indigo-400',
    '待执行': 'bg-amber-500/15 text-amber-400',
    '待访谈': 'bg-amber-500/15 text-amber-400',
    '待排期': 'bg-amber-500/15 text-amber-400',
    'open': 'bg-red-500/15 text-red-400',
    'closed': 'bg-green-500/15 text-green-400',
    '待确认': 'bg-blue-500/15 text-blue-400',
    '待裁定': 'bg-amber-500/15 text-amber-400',
    '待复评': 'bg-amber-500/15 text-amber-400',
    '通过': 'bg-green-500/15 text-green-400',
    'PASS': 'bg-green-500/15 text-green-400',
    'PARTIAL': 'bg-amber-500/15 text-amber-400',
    'FAIL': 'bg-red-500/15 text-red-400',
    'False': 'bg-bg-surface text-text-muted',
    'True': 'bg-green-500/15 text-green-400',
    // 2026-07-25新增:T18/T19/T20/T25等新表用到的状态词汇
    '熔断': 'bg-red-500/15 text-red-400',
    '非熔断': 'bg-green-500/15 text-green-400',
    '未分发': 'bg-bg-surface text-text-muted',
    '已分发': 'bg-indigo-500/15 text-indigo-400',
    'Auto': 'bg-green-500/15 text-green-400',
    'Aug': 'bg-blue-500/15 text-blue-400',
    'Hybrid': 'bg-amber-500/15 text-amber-400',
    'Human': 'bg-bg-surface text-text-muted',
    '草稿中': 'bg-amber-500/15 text-amber-400',
  }
  const cls = map[status] || 'bg-bg-surface text-text-muted'
  return <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${cls}`}>{status || '-'}</span>
}

export function PriorityBadge({ priority }: { priority: string }) {
  const map: Record<string, string> = {
    'P0': 'bg-red-500 text-white',
    'P1': 'bg-amber-500 text-black',
    'P2': 'bg-blue-500 text-white',
    '4': 'bg-red-500 text-white',
    '5': 'bg-amber-500 text-black',
  }
  const label = priority?.startsWith('P') ? priority : `P${priority}`
  return <span className={`inline-block rounded px-2 py-0.5 text-xs font-bold ${map[priority] || 'bg-bg-surface text-text-muted'}`}>{label || '-'}</span>
}
