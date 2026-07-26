import { useState, useMemo, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router'
import { motion } from 'framer-motion'
import { loadAllData, getDomainInfo } from '@/lib/data'
import { StatusBadge, PriorityBadge } from '@/components/StatusBadge'
import { ArrowLeft, FileText, Clock, AlertCircle, Package, Shield, MessageSquare, ClipboardList, Layers, Flame, BookOpen, ArrowRightLeft, ShieldQuestion } from 'lucide-react'

export default function NodeDetail() {
  const { nodeId } = useParams<{ nodeId: string }>()
  const navigate = useNavigate()
  const [data, setData] = useState<any>(null)
  const [tab, setTab] = useState('overview')

  useEffect(() => { loadAllData().then(setData) }, [])

  if (!data || !nodeId) return <div className="flex min-h-[60vh] items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" /></div>

  const node = (data.node_index || []).find((n: any) => n.node_id === nodeId)
  if (!node) {
    return <div className="flex min-h-[60vh] flex-col items-center justify-center"><AlertCircle className="mb-3 h-12 w-12 text-accent-danger" />
      <h2 className="text-xl font-semibold text-text-primary">节点不存在</h2>
      <button onClick={() => navigate('/nodes')} className="mt-4 flex items-center gap-2 text-accent-primary"><ArrowLeft className="h-4 w-4" />返回</button></div>
  }

  const domain = getDomainInfo(nodeId)
  const rules = (data.rules || []).filter((r: any) => r.node_id === nodeId)
  const signals = (data.signals || []).filter((s: any) => s.node_id === nodeId)
  const actions = (data.actions || []).filter((a: any) => a.node_id === nodeId)
  const gaps = (data.gaps || []).filter((g: any) => g.node_id === nodeId)
  const deliverables = (data.deliverables || []).filter((d: any) => d.node_id === nodeId)
  const gate = (data.gate_ratings || []).find((g: any) => g.node_id === nodeId)
  const roles = (data.role_mapping || []).filter((r: any) => r.node_id === nodeId)
  const leads = (data.interview_leads || []).filter((l: any) => l.node_id === nodeId)
  const recordings = (data.interview_recordings || []).filter((r: any) => r.node_ids?.includes(nodeId))
  const batches = (data.interview_batches || []).filter((b: any) => b.node_ids?.includes(nodeId))
  const review = (data.node_review || []).find((r: any) => r.node_id === nodeId)
  // 2026-07-25新增:T25(熔断状态权威判定)+T18(该节点熔断补建任务)+T19(SOP进度,仅VN价值节点类)
  // +T23(VNW→AIT移交)+T24(交付物四标签风险分析)
  const fusedStatus = (data.fused_status || []).find((f: any) => f.node_id === nodeId)
  const fusedTasks = (data.fused_tasks || []).filter((t: any) => t.node_id === nodeId)
  const sopStatus = (data.sop_progress || []).find((s: any) => s.coding_scheme === 'VN价值节点' && s.sop_ref === nodeId)
  const aitHandoff = (data.ait_handoff || []).find((a: any) => a.node_id === nodeId)
  const deliverableRisk = (data.deliverable_risk || []).filter((d: any) => d.node_id === nodeId)

  const tabs = [
    { key: 'overview', label: '概览', icon: Layers },
    { key: 'rules', label: `规则(${rules.length})`, icon: FileText },
    { key: 'actions', label: `行动(${actions.length})`, icon: Clock },
    { key: 'gaps', label: `Gap(${gaps.length})`, icon: AlertCircle },
    { key: 'deliverables', label: `交付物(${deliverables.length})`, icon: Package },
    { key: 'quality', label: '质量门', icon: Shield },
    { key: 'interviews', label: `访谈(${leads.length})`, icon: MessageSquare },
    { key: 'sop', label: `SOP(${roles.length})`, icon: ClipboardList },
    { key: 'fused', label: `熔断(${fusedTasks.length})`, icon: Flame },
    { key: 'sopProgress', label: 'SOP追踪', icon: BookOpen },
    { key: 'aitHandoff', label: 'AIT移交', icon: ArrowRightLeft },
    { key: 'riskAnalysis', label: `四标签风险(${deliverableRisk.length})`, icon: ShieldQuestion },
  ]

  return (
    <div className="space-y-4">
      {/* Header */}
      <motion.div className="rounded-lg border border-border-default bg-bg-elevated p-5" style={{ borderTopWidth: 4, borderTopColor: domain.color }}
        initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <button onClick={() => navigate('/nodes')} className="mb-3 flex items-center gap-1 text-sm text-text-secondary hover:text-text-primary"><ArrowLeft className="h-4 w-4" />返回</button>
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-mono text-lg text-accent-primary-light">{nodeId}</span>
          <span className="flex items-center gap-1 rounded-full bg-bg-surface px-2.5 py-0.5 text-xs"><span className="h-2 w-2 rounded-full" style={{ backgroundColor: domain.color }} />{node.domain}</span>
          {node.priority && <PriorityBadge priority={String(node.priority)} />}
          {fusedStatus && <StatusBadge status={fusedStatus.fused_status} />}
        </div>
        <h1 className="mt-2 font-heading text-2xl font-bold text-text-primary">{node.node_name}</h1>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 border-t border-border-default pt-3 text-sm">
          <span className="text-text-secondary">L3: <span className="text-text-primary">{node.l3_flow}</span></span>
          <span className="text-text-secondary">熔断状态: <span className="text-text-primary">{fusedStatus?.fused_status || '未判定'}</span></span>
          <span className="text-text-secondary">频率: <span className="text-text-primary">{node.frequency}</span></span>
          {node.value_property && <span className="text-text-secondary">价值属性: <span className="text-text-primary">{node.value_property}</span></span>}
        </div>
      </motion.div>

      {/* KPI mini */}
      <div className="grid grid-cols-3 gap-2 md:grid-cols-6">
        {[
          { label: '规则', count: rules.length, icon: FileText, color: 'text-accent-primary-light' },
          { label: '信号', count: signals.length, icon: MessageSquare, color: 'text-accent-secondary' },
          { label: '行动', count: actions.length, icon: Clock, color: 'text-accent-warning' },
          { label: 'Gap', count: gaps.length, icon: AlertCircle, color: 'text-accent-danger' },
          { label: '交付物', count: deliverables.length, icon: Package, color: 'text-accent-info' },
          { label: '角色', count: roles.length, icon: ClipboardList, color: 'text-accent-success' },
        ].map((item, i) => (
          <motion.div key={item.label} className="rounded-lg border border-border-default bg-bg-elevated p-2.5 text-center"
            initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.05 }}>
            <item.icon className={`mx-auto mb-1 h-4 w-4 ${item.color}`} />
            <p className="font-mono text-lg text-text-primary">{item.count}</p>
            <p className="text-xs text-text-muted">{item.label}</p>
          </motion.div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 rounded-lg bg-bg-elevated p-1">
        {tabs.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`flex items-center gap-1 rounded-md px-3 py-2 text-sm transition-colors ${
              tab === t.key ? 'bg-accent-primary text-white' : 'text-text-secondary hover:text-text-primary hover:bg-bg-surface'
            }`}>
            <t.icon className="h-3.5 w-3.5" />{t.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="min-h-[300px]">
        {tab === 'overview' && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="rounded-lg border border-border-default bg-bg-elevated p-4">
                <h3 className="mb-3 text-sm font-semibold text-text-primary">节点元数据</h3>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    ['L3流程', node.l3_flow], ['L3现状', node.l3_status], ['优先级', node.priority],
                    ['价值属性', node.value_property], ['生产方', node.producer], ['消费方', node.consumer],
                    ['单点风险', node.single_point_risk], ['频率', node.frequency], ['起始点', node.start_point],
                    ['终止点', node.end_point], ['交付物组成', node.composition], ['数据来源', node.source_file],
                  ].map(([k, v]) => (
                    <div key={String(k)} className="rounded bg-bg-surface p-2">
                      <p className="text-xs text-text-muted">{k}</p>
                      <p className="mt-0.5 truncate text-sm text-text-primary">{v || '-'}</p>
                    </div>
                  ))}
                </div>
              </div>
              {fusedStatus && (
                <div className="rounded-lg border border-border-default bg-bg-elevated p-4">
                  <h3 className="mb-3 text-sm font-semibold text-text-primary">熔断状态(T25权威判定)</h3>
                  <div className="flex items-center gap-3">
                    <StatusBadge status={fusedStatus.fused_status} />
                    {fusedStatus.fused_type && <span className="text-sm text-text-secondary">{fusedStatus.fused_type}</span>}
                  </div>
                  <p className="mt-2 text-xs text-text-muted">判定依据: {fusedStatus.source}</p>
                </div>
              )}
              {gate && (
                <div className="rounded-lg border border-border-default bg-bg-elevated p-4">
                  <h3 className="mb-3 text-sm font-semibold text-text-primary">质量门评级</h3>
                  <div className="flex gap-4">
                    {['gate1_status', 'gate2_status', 'gate3_status'].map(g => (
                      <div key={g} className="text-center">
                        <p className="text-xs text-text-muted">{g.replace('_', ' ')}</p>
                        <StatusBadge status={gate[g]} />
                      </div>
                    ))}
                  </div>
                  {gate.decision_priority && <p className="mt-3 text-xs text-text-muted">决策优先级: <span className="text-accent-primary-light">{gate.decision_priority}</span></p>}
                </div>
              )}
              {review && (
                <div className="rounded-lg border border-border-default bg-bg-elevated p-4 md:col-span-2">
                  <h3 className="mb-3 text-sm font-semibold text-text-primary">复评追踪 <span className="ml-1 text-xs font-normal text-text-muted">(T13人工维护,未纳入本次同步范围)</span></h3>
                  <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                    {[
                      ['阶段', review.phase], ['结果', review.review_result], ['负责人', review.owner],
                      ['阻塞项', review.blocker], ['里程碑', review.next_milestone], ['期望产出', review.expected_output],
                    ].map(([k, v]) => (
                      <div key={String(k)} className="rounded bg-bg-surface p-2">
                        <p className="text-xs text-text-muted">{k}</p>
                        <p className="mt-0.5 truncate text-sm text-text-primary">{v || '-'}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {tab === 'rules' && <DataTable data={rules} columns={[
          { key: 'rule_id', label: '规则ID', mono: true },
          { key: 'rule_name', label: '规则名称' },
          { key: 'rule_class', label: '类别' },
          { key: 'rule_trigger', label: '触发条件' },
          { key: 'rule_owner', label: '负责人' },
          { key: 'externalized', label: '外部化', badge: true },
          { key: 'priority', label: '优先级' },
        ]} />}

        {tab === 'actions' && <DataTable data={actions} columns={[
          { key: 'action_id', label: '行动ID', mono: true },
          { key: 'action_description', label: '描述' },
          { key: 'action_subtype', label: '子类型' },
          { key: 'status', label: '状态', badge: true },
          { key: 'action_owner', label: '负责人' },
          { key: 'blocker', label: '阻塞' },
        ]} />}

        {tab === 'gaps' && <DataTable data={gaps.sort((a: any, b: any) => (a.priority==='P0'?-1:a.priority==='P1'?0:1))} columns={[
          { key: 'priority', label: '优先级', priority: true },
          { key: 'gap_id', label: 'Gap ID', mono: true },
          { key: 'description', label: '描述' },
          { key: 'gap_type', label: '类型' },
          { key: 'gap_subtype', label: '子类型' },
          { key: 'status', label: '状态', badge: true },
          { key: 'sop_status', label: 'SOP状态' },
        ]} />}

        {tab === 'deliverables' && <DataTable data={deliverables} columns={[
          { key: 'deliverable_id', label: 'ID', mono: true },
          { key: 'deliverable_name', label: '名称' },
          { key: 'producer_role', label: '生产角色' },
          { key: 'consumer', label: '消费者' },
          { key: 'gate_status', label: '门状态', badge: true },
        ]} />}

        {tab === 'quality' && (
          gate ? <div className="rounded-lg border border-border-default bg-bg-elevated p-4">
            <h3 className="mb-3 text-sm font-semibold text-text-primary">Gate评级明细</h3>
            <div className="grid grid-cols-3 gap-4 text-center">
              {['gate1_status', 'gate2_status', 'gate3_status'].map(g => (
                <div key={g} className="rounded-lg bg-bg-surface p-4">
                  <p className="text-xs text-text-muted">{g.replace('_', ' ').toUpperCase()}</p>
                  <p className="mt-2 text-lg font-semibold">{gate[g]}</p>
                </div>
              ))}
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
              <span className="text-text-secondary">融合状态: <span className="text-text-primary">{gate.is_fused ? '已融合' : '未融合'}</span></span>
              <span className="text-text-secondary">Sheet5分类: <span className="text-text-primary">{gate.sheet5_category}</span></span>
              <span className="text-text-secondary">决策优先级: <span className="text-text-primary">{gate.decision_priority}</span></span>
            </div>
          </div> : <p className="text-text-muted">暂无质量门数据</p>
        )}

        {tab === 'interviews' && (
          <div className="space-y-4">
            <p className="rounded-lg border border-accent-warning/30 bg-accent-warning/5 px-3 py-2 text-xs text-accent-warning">
              T3/T10/T16为人工维护表,本次数据底座大修未覆盖同步,可能与当前节点集有出入(已发现真实错配案例,如REC-018引用的部分节点编码不在当前T1中)。
            </p>
            {batches.length > 0 && <div className="rounded-lg border border-border-default bg-bg-elevated p-4">
              <h3 className="mb-3 text-sm font-semibold text-text-primary">访谈批次 ({batches.length})</h3>
              <DataTable data={batches} columns={[
                { key: 'batch_id', label: '批次ID', mono: true },
                { key: 'dept_role', label: '部门角色' },
                { key: 'interviewee_name', label: '访谈对象' },
                { key: 'gap_count', label: 'Gap数' },
                { key: 'status', label: '状态', badge: true },
              ]} />
            </div>}
            {recordings.length > 0 && <div className="rounded-lg border border-border-default bg-bg-elevated p-4">
              <h3 className="mb-3 text-sm font-semibold text-text-primary">访谈记录 ({recordings.length})</h3>
              <DataTable data={recordings} columns={[
                { key: 'recording_id', label: '记录ID', mono: true },
                { key: 'interviewee_dept_role', label: '访谈角色' },
                { key: 'interview_date', label: '日期' },
                { key: 'template_type', label: '模板' },
                { key: 'status', label: '状态', badge: true },
              ]} />
            </div>}
            {leads.length > 0 && <div className="rounded-lg border border-border-default bg-bg-elevated p-4">
              <h3 className="mb-3 text-sm font-semibold text-text-primary">访谈线索 ({leads.length})</h3>
              <DataTable data={leads} columns={[
                { key: 'lead_id', label: '线索ID', mono: true },
                { key: 'content', label: '内容' },
                { key: 'target_rule_type', label: '规则类型' },
                { key: 'status', label: '状态', badge: true },
                { key: 'interview_result', label: '结果' },
              ]} />
            </div>}
          </div>
        )}

        {tab === 'sop' && <DataTable data={roles} columns={[
          { key: 'mapping_id', label: '映射ID', mono: true },
          { key: 'role_name', label: '角色' },
          { key: 'role_type', label: '类型' },
          { key: 'responsibility_mode', label: '职责模式' },
          { key: 'single_point_risk', label: '单点风险' },
          { key: 'source_field', label: '来源' },
        ]} />}

        {tab === 'fused' && (
          <div className="space-y-4">
            {fusedStatus && (
              <div className="rounded-lg border border-border-default bg-bg-elevated p-4">
                <div className="flex items-center gap-3">
                  <StatusBadge status={fusedStatus.fused_status} />
                  <span className="text-sm text-text-primary">{fusedStatus.fused_type || '无补充说明'}</span>
                </div>
                <p className="mt-2 text-xs text-text-muted">来源: {fusedStatus.source} · 更新于 {fusedStatus.last_updated}</p>
              </div>
            )}
            <DataTable data={fusedTasks} columns={[
              { key: 'task_id', label: '任务ID', mono: true },
              { key: 'task_name', label: '行动' },
              { key: 'action_tier', label: '类型' },
              { key: 'executor_role', label: '执行主体' },
              { key: 'deliverable_name', label: '期望产出' },
              { key: 'deadline', label: '预估周期' },
              { key: 'task_status', label: '状态', badge: true },
            ]} />
          </div>
        )}

        {tab === 'sopProgress' && (
          sopStatus ? <div className="rounded-lg border border-border-default bg-bg-elevated p-4">
            <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
              {[
                ['SOP文件', sopStatus.sop_file], ['版本', sopStatus.sop_version], ['状态', sopStatus.sop_status],
                ['Gap总数', sopStatus.gap_total], ['未解决', sopStatus.gap_open], ['已解决', sopStatus.gap_resolved],
              ].map(([k, v]) => (
                <div key={String(k)} className="rounded bg-bg-surface p-2">
                  <p className="text-xs text-text-muted">{k}</p>
                  <p className="mt-0.5 truncate text-sm text-text-primary">{v || '-'}</p>
                </div>
              ))}
            </div>
            <p className="mt-3 text-xs text-text-muted">最后同步: {sopStatus.last_synced}</p>
          </div> : <p className="text-text-muted">该节点尚无SOP产出</p>
        )}

        {tab === 'aitHandoff' && (
          aitHandoff ? <div className="rounded-lg border border-border-default bg-bg-elevated p-4">
            <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
              {[
                ['移交状态', aitHandoff.handoff_status], ['AIT拆解状态', aitHandoff.ait_breakdown_status || '未开始'],
                ['是否试点', aitHandoff.pilot_flag === 'TRUE' ? '是(L3-COM)' : '否'], ['决策依据', aitHandoff.decision_ref],
                ['下一步', aitHandoff.next_action],
              ].map(([k, v]) => (
                <div key={String(k)} className="rounded bg-bg-surface p-2">
                  <p className="text-xs text-text-muted">{k}</p>
                  <p className="mt-0.5 text-sm text-text-primary">{v || '-'}</p>
                </div>
              ))}
            </div>
          </div> : <p className="text-text-muted">暂无移交追踪数据</p>
        )}

        {tab === 'riskAnalysis' && <DataTable data={deliverableRisk} columns={[
          { key: 'deliverable_name', label: '交付物' },
          { key: 'a_type', label: 'A·类型' },
          { key: 'b_owner', label: 'B·Owner' },
          { key: 'b_single_point_risk', label: 'B·单点风险' },
          { key: 'c_breakpoint_type', label: 'C·断点类型' },
          { key: 'd_auth_level', label: 'D·授权级别' },
        ]} />}
      </div>
    </div>
  )
}

// Shared table component for tab content
function DataTable({ data, columns }: { data: any[], columns: { key: string; label: string; mono?: boolean; badge?: boolean; priority?: boolean }[] }) {
  if (data.length === 0) return <p className="text-text-muted">暂无数据</p>
  return (
    <div className="overflow-x-auto rounded-lg border border-border-default">
      <table className="w-full">
        <thead><tr className="border-b border-border-default bg-bg-surface">
          {columns.map(c => <th key={c.key} className="px-3 py-2 text-left text-xs font-semibold text-text-primary">{c.label}</th>)}
        </tr></thead>
        <tbody>
          {data.map((row: any, i: number) => (
            <tr key={i} className="border-b border-border-default hover:bg-bg-surface">
              {columns.map(c => (
                <td key={c.key} className={`px-3 py-2 ${c.mono ? 'font-mono text-xs text-accent-primary-light' : 'text-sm text-text-secondary'} ${c.key==='description'||c.key==='content'||c.key==='action_description' ? 'max-w-xs truncate' : ''}`}>
                  {c.badge ? <StatusBadge status={row[c.key]} /> : c.priority ? <PriorityBadge priority={row[c.key]} /> : (row[c.key] || '-')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
