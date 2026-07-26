import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { loadAllData } from '@/lib/data'
import { StatusBadge } from '@/components/StatusBadge'
import { MessageSquare, ClipboardList, Users, Mic, FileText, BarChart3 } from 'lucide-react'

export default function InterviewSOP() {
  const [data, setData] = useState<any>(null)
  const [tab, setTab] = useState('batches')

  useEffect(() => { loadAllData().then(setData) }, [])

  if (!data) return <div className="flex min-h-[60vh] items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" /></div>

  const tabs = [
    { key: 'batches', label: '访谈批次', icon: Users, count: (data.interview_batches || []).length },
    { key: 'recordings', label: '访谈记录', icon: Mic, count: (data.interview_recordings || []).length },
    { key: 'leads', label: '访谈线索', icon: MessageSquare, count: (data.interview_leads || []).length },
    { key: 'roles', label: '岗位映射', icon: ClipboardList, count: (data.role_mapping || []).length },
    { key: 'tracking', label: '报告跟踪', icon: FileText, count: (data.report_tracking || []).length },
  ]

  return (
    <div className="space-y-4">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <h1 className="font-heading text-2xl font-bold text-text-primary">访谈与SOP中心</h1>
        <p className="text-sm text-text-secondary">访谈管理 · 岗位映射 · SOP梳理 · 报告跟踪</p>
        <p className="mt-2 rounded-lg border border-accent-warning/30 bg-accent-warning/5 px-3 py-2 text-xs text-accent-warning">
          批次/记录/线索/报告跟踪均为人工维护表,本次数据底座大修未覆盖同步,内容可能滞后于当前节点集(报告跟踪自建表起一直是0行)。
        </p>
      </motion.div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 rounded-lg bg-bg-elevated p-1">
        {tabs.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`flex items-center gap-1 rounded-md px-3 py-2 text-sm transition-colors ${
              tab === t.key ? 'bg-accent-primary text-white' : 'text-text-secondary hover:text-text-primary hover:bg-bg-surface'
            }`}>
            <t.icon className="h-3.5 w-3.5" />{t.label} ({t.count})
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="min-h-[300px]">
        {tab === 'batches' && <BatchTable data={data.interview_batches || []} />}
        {tab === 'recordings' && <RecordingTable data={data.interview_recordings || []} />}
        {tab === 'leads' && <LeadTable data={data.interview_leads || []} />}
        {tab === 'roles' && <RoleTable data={data.role_mapping || []} />}
        {tab === 'tracking' && <ReportTable data={data.report_tracking || []} />}
      </div>
    </div>
  )
}

function BatchTable({ data }: { data: any[] }) {
  if (data.length === 0) return <p className="text-text-muted">暂无访谈批次</p>
  return (
    <div className="overflow-x-auto rounded-lg border border-border-default">
      <table className="w-full">
        <thead><tr className="border-b border-border-default bg-bg-surface">
          <th className="px-3 py-2 text-left text-xs font-semibold">批次ID</th>
          <th className="px-3 py-2 text-left text-xs font-semibold">部门角色</th>
          <th className="px-3 py-2 text-left text-xs font-semibold">节点</th>
          <th className="px-3 py-2 text-left text-xs font-semibold">访谈对象</th>
          <th className="px-3 py-2 text-left text-xs font-semibold">Gap数</th>
          <th className="px-3 py-2 text-left text-xs font-semibold">状态</th>
          <th className="px-3 py-2 text-left text-xs font-semibold">来源</th>
        </tr></thead>
        <tbody>
          {data.map((b: any, i: number) => (
            <tr key={i} className="border-b border-border-default hover:bg-bg-surface">
              <td className="px-3 py-2 font-mono text-xs text-accent-primary-light">{b.batch_id}</td>
              <td className="px-3 py-2 text-xs text-text-secondary">{b.dept_role}</td>
              <td className="px-3 py-2 text-xs text-text-secondary max-w-[200px] truncate">{b.node_ids}</td>
              <td className="px-3 py-2 text-xs text-text-secondary">{b.interviewee_name || '-'}</td>
              <td className="px-3 py-2 text-xs text-text-primary">{b.gap_count}</td>
              <td className="px-3 py-2"><StatusBadge status={b.status} /></td>
              <td className="px-3 py-2 text-xs text-text-muted max-w-[200px] truncate">{b.source_doc}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RecordingTable({ data }: { data: any[] }) {
  if (data.length === 0) return <p className="text-text-muted">暂无访谈记录</p>
  return (
    <div className="overflow-x-auto rounded-lg border border-border-default">
      <table className="w-full">
        <thead><tr className="border-b border-border-default bg-bg-surface">
          <th className="px-3 py-2 text-left text-xs font-semibold">记录ID</th>
          <th className="px-3 py-2 text-left text-xs font-semibold">批次</th>
          <th className="px-3 py-2 text-left text-xs font-semibold">访谈角色</th>
          <th className="px-3 py-2 text-left text-xs font-semibold">日期</th>
          <th className="px-3 py-2 text-left text-xs font-semibold">模板</th>
          <th className="px-3 py-2 text-left text-xs font-semibold">新发现</th>
          <th className="px-3 py-2 text-left text-xs font-semibold">状态</th>
        </tr></thead>
        <tbody>
          {data.map((r: any, i: number) => (
            <tr key={i} className="border-b border-border-default hover:bg-bg-surface">
              <td className="px-3 py-2 font-mono text-xs text-accent-primary-light">{r.recording_id}</td>
              <td className="px-3 py-2 text-xs text-text-secondary">{r.batch_id}</td>
              <td className="px-3 py-2 text-xs text-text-secondary max-w-[200px] truncate">{r.interviewee_dept_role}</td>
              <td className="px-3 py-2 text-xs text-text-secondary max-w-[200px] truncate">{r.interview_date}</td>
              <td className="px-3 py-2 text-xs text-text-secondary">{r.template_type}</td>
              <td className="px-3 py-2 text-xs text-text-secondary">{r.new_fused_found}</td>
              <td className="px-3 py-2"><StatusBadge status={r.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function LeadTable({ data }: { data: any[] }) {
  if (data.length === 0) return <p className="text-text-muted">暂无访谈线索</p>
  return (
    <div className="space-y-3">
      {data.slice(0, 50).map((l: any, i: number) => (
        <motion.div key={i} className="rounded-lg border border-border-default bg-bg-elevated p-4" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.02, 0.5) }}>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-accent-primary-light">{l.lead_id}</span>
            <StatusBadge status={l.status} />
            <span className="text-xs text-text-muted">{l.target_rule_type}</span>
            <span className="text-xs text-text-muted">{l.interview_priority}</span>
          </div>
          <p className="mt-2 text-sm text-text-primary">{l.content}</p>
          {l.interview_question && (
            <div className="mt-2 rounded bg-bg-surface p-2">
              <p className="text-xs text-text-muted">访谈问题</p>
              <p className="mt-1 whitespace-pre-line text-xs text-text-secondary">{l.interview_question}</p>
            </div>
          )}
          {l.gap_description && (
            <div className="mt-2 rounded bg-accent-danger/5 p-2">
              <p className="text-xs text-accent-danger">Gap: {l.gap_description}</p>
            </div>
          )}
          <div className="mt-2 flex gap-4 text-xs text-text-muted">
            {l.target_interviewee && <span>对象: {l.target_interviewee}</span>}
            {l.interview_result && <span>结果: {l.interview_result}</span>}
          </div>
        </motion.div>
      ))}
    </div>
  )
}

function RoleTable({ data }: { data: any[] }) {
  if (data.length === 0) return <p className="text-text-muted">暂无岗位映射</p>
  return (
    <div className="overflow-x-auto rounded-lg border border-border-default">
      <table className="w-full">
        <thead><tr className="border-b border-border-default bg-bg-surface">
          <th className="px-3 py-2 text-left text-xs font-semibold">映射ID</th>
          <th className="px-3 py-2 text-left text-xs font-semibold">节点</th>
          <th className="px-3 py-2 text-left text-xs font-semibold">角色</th>
          <th className="px-3 py-2 text-left text-xs font-semibold">类型</th>
          <th className="px-3 py-2 text-left text-xs font-semibold">职责模式</th>
          <th className="px-3 py-2 text-left text-xs font-semibold">单点风险</th>
          <th className="px-3 py-2 text-left text-xs font-semibold">来源</th>
        </tr></thead>
        <tbody>
          {data.map((r: any, i: number) => (
            <tr key={i} className="border-b border-border-default hover:bg-bg-surface">
              <td className="px-3 py-2 font-mono text-xs text-accent-primary-light">{r.mapping_id}</td>
              <td className="px-3 py-2 font-mono text-xs text-accent-primary-light">{r.node_id}</td>
              <td className="px-3 py-2 text-xs text-text-primary">{r.role_name}</td>
              <td className="px-3 py-2 text-xs text-text-secondary">{r.role_type}</td>
              <td className="px-3 py-2 text-xs text-text-secondary">{r.responsibility_mode || '-'}</td>
              <td className="px-3 py-2 text-xs text-accent-danger">{r.single_point_risk || '-'}</td>
              <td className="px-3 py-2 text-xs text-text-muted">{r.source_field || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ReportTable({ data }: { data: any[] }) {
  if (data.length === 0) return (
    <div className="flex min-h-[200px] flex-col items-center justify-center text-center">
      <FileText className="mb-3 h-12 w-12 text-text-muted" />
      <p className="text-text-secondary">报告跟踪表暂无数据</p>
      <p className="text-xs text-text-muted">T17_报告跟踪表已创建，等待报告生成后回填</p>
    </div>
  )
  return <div className="overflow-x-auto rounded-lg border border-border-default"><table className="w-full">...</table></div>
}
