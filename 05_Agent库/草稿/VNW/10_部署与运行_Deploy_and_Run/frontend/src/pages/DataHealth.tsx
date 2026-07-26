import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { loadAllData } from '@/lib/data'
import { StatusBadge } from '@/components/StatusBadge'
import { HeartPulse } from 'lucide-react'

const SEVERITY_ORDER = ['高', '中', '低']
const SEVERITY_COLOR: Record<string, string> = { 高: '#F87171', 中: '#FBBF24', 低: '#60A5FA' }

export default function DataHealth() {
  const [data, setData] = useState<any>(null)
  useEffect(() => { loadAllData().then(setData) }, [])

  if (!data) return <div className="flex min-h-[60vh] items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" /></div>

  const audits = data.data_audit || []
  const grouped = SEVERITY_ORDER.map(sev => ({ sev, items: audits.filter((a: any) => a.severity === sev) }))

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <div className="flex items-center gap-3">
          <HeartPulse className="h-7 w-7 text-accent-primary" />
          <h1 className="font-heading text-2xl font-bold text-text-primary">数据健康 / 对齐审计</h1>
        </div>
        <p className="mt-1 text-sm text-text-muted">T21每次同步脚本运行时全量重新生成,是当前数据底座已知问题的即时快照,不做历史累积</p>
      </motion.div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-3">
        {grouped.map(g => (
          <div key={g.sev} className="rounded-lg border border-border-default bg-bg-elevated p-3 text-center" style={{ borderTopWidth: 3, borderTopColor: SEVERITY_COLOR[g.sev] }}>
            <p className="font-mono text-2xl text-text-primary">{g.items.length}</p>
            <p className="text-xs text-text-muted">{g.sev}优先级</p>
          </div>
        ))}
      </div>

      {audits.length === 0 && (
        <div className="rounded-lg border border-border-default bg-bg-elevated p-8 text-center text-text-muted">
          当前没有已知问题记录
        </div>
      )}

      {grouped.map(g => g.items.length > 0 && (
        <div key={g.sev} className="space-y-2">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-text-primary">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: SEVERITY_COLOR[g.sev] }} />
            {g.sev}优先级 ({g.items.length})
          </h3>
          <div className="overflow-x-auto rounded-lg border border-border-default">
            <table className="w-full">
              <thead><tr className="border-b border-border-default bg-bg-surface">
                <th className="px-3 py-2 text-left text-xs font-semibold text-text-primary">审计ID</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-text-primary">类型</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-text-primary">范围</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-text-primary">问题描述</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-text-primary">状态</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-text-primary">发现日期</th>
              </tr></thead>
              <tbody>
                {g.items.map((a: any, i: number) => (
                  <tr key={i} className="border-b border-border-default hover:bg-bg-surface">
                    <td className="px-3 py-2 font-mono text-xs text-accent-primary-light">{a.audit_id}</td>
                    <td className="px-3 py-2 text-sm text-text-secondary">{a.audit_type}</td>
                    <td className="px-3 py-2 text-sm text-text-secondary">{a.scope}</td>
                    <td className="px-3 py-2 max-w-md text-sm text-text-secondary">{a.issue_desc}</td>
                    <td className="px-3 py-2"><StatusBadge status={a.status} /></td>
                    <td className="px-3 py-2 text-xs text-text-muted">{a.detected_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  )
}
