import { useState } from 'react'
import { motion } from 'framer-motion'
import {
  Users, Layers, Package, GitBranch, Bot, AlertTriangle,
  ArrowDown, ArrowRight, CheckCircle2, ShieldAlert,
} from 'lucide-react'

// ---------------------------------------------------------------------------
// 单L3手工demo,数据全部来自真实源文件手动摘录(不接sync_data_foundation.py管道):
// 流程蓝图_L3-IRI_V1.1.md / L2业务能力详情卡_v1.0.csv(CAP-L2-1-S3) /
// D2_价值节点_L3映射表(VN-INS-03) / T1节点索引 / T20 L4自动化Tier评估
// 目的:验证"L3流程模型五维(人/能力/节点/物/AI协同标准)"这个概念在真实数据上
// 站不站得住,不代表已确定的架构,不接入主导航,仅供review。
// ---------------------------------------------------------------------------

const CAPABILITY = {
  id: 'CAP-L2-1-S3',
  name: '保司资源整合能力',
  definition: '整合保险公司的产品、数据、系统等核心资源，完成技术与业务深度对接，确保资源有效接入平台运营体系的能力。',
  maturity: 'PARTIAL',
  gap: '该能力部分满足要求，存在局部缺口。',
  l3Coverage: ['L3-IRI'],
  source: 'L2业务能力详情卡_v1.0.csv · 企业能力视角评估，非VNW自己的Gate判断',
}

const NODE = {
  id: 'VN-INS-03',
  name: '整合就绪确认书',
  domain: 'INS',
  l3Flow: '保司资源整合与深度对接E2E',
  priority: 'P1',
  endStandard: '签字版',
  gap: 'INS域暂无访谈覆盖，producer/consumer字段目前是空的——现状证据只到04层规则/Gap，没有05_SOP层的沉淀',
}

const ROLES = [
  { role: 'A族-保司交付', type: '主责', raci: 'Responsible' },
  { role: 'B族-保司关系经理', type: '协作', raci: 'Consulted' },
  { role: 'Mark', type: '权限清单谈判(L4-IRI-01)必须介入', raci: 'Accountable(该步)' },
  { role: 'Terresa', type: '跟进《整合就绪确认书》升级为签字流程的推进节点', raci: 'Informed/跟进' },
]

const DELIVERABLES = [
  { name: '《权限清单》', l4: 'L4-IRI-01', dest: '内部存档(Mark签批)' },
  { name: '《资源对接清单》', l4: 'L4-IRI-02', dest: '移交执行团队' },
  { name: '《对接技术规范》', l4: 'L4-IRI-06', dest: 'IT团队执行' },
  { name: '对接完成报告', l4: 'L4-IRI-03', dest: '内部存档' },
  { name: '权限生效通知', l4: 'L4-IRI-04', dest: '全员同步' },
  { name: '《培训换手记录》', l4: 'L4-IRI-07', dest: '内部存档' },
  { name: '《整合就绪确认书》', l4: 'L4-IRI-05', dest: '确认→触发L3-IBE', flag: '⚠️当前口头确认，蓝图自己标注建议升级为正式签字流程(P1)' },
]

const STEPS = [
  { n: 1, name: '权限清单谈判与确认', l4: 'L4-IRI-01', detail: 'A族+Mark确认权限边界→输出《权限清单》(Mark必须介入)' },
  { n: 2, name: '资源盘点与对接规范制定', l4: 'L4-IRI-02/06', detail: '盘点保司可用资源→《资源对接清单》；制定《对接技术规范》' },
  { n: 3, name: '系统与数据团队对接', l4: 'L4-IRI-03', detail: '系统+数据+人员三线对接→对接完成报告', gate: '判断节点1：系统对接是否通过技术验证？未通过→返回步骤2修订技术规范' },
  { n: 4, name: '权限生效与配置', l4: 'L4-IRI-04', detail: '系统自动化配置权限→权限生效通知', gate: '判断节点2：权限生效测试是否通过？未通过→返回步骤3技术团队修复' },
  { n: 5, name: '保司内部培训与人员换手', l4: 'L4-IRI-07', detail: '对保司人员开展培训→《培训换手记录》' },
  { n: 6, name: '整合就绪确认', l4: 'L4-IRI-05', detail: '各项checklist核验→《整合就绪确认书》', flag: '⚠️当前口头确认，无正式签字文件' },
]

const L4_COLLAB = [
  { code: 'L4-IRI-01', name: '权限清单谈判', tier: 'Human', bpHuman: 'Mark必须介入', agent: '清单模板+谈判支持' },
  { code: 'L4-IRI-02', name: '保司资源盘点', tier: 'Aug', bpHuman: '无需人介入', agent: '清单生成+盘点' },
  { code: 'L4-IRI-03', name: '系统数据团队对接', tier: 'Aug', bpHuman: '技术协调', agent: 'API+数据迁移' },
  { code: 'L4-IRI-04', name: '权限生效与配置', tier: 'Auto', bpHuman: '测试验证', agent: '系统配置自动化' },
  { code: 'L4-IRI-05', name: '整合就绪确认', tier: 'Aug', bpHuman: '确认(建议签字)', agent: 'checklist+验证' },
  { code: 'L4-IRI-06', name: '保司IT系统深度对接', tier: 'Aug', bpHuman: '技术判断', agent: 'API+SSO+联调' },
  { code: 'L4-IRI-07', name: '保司内部培训与换手', tier: 'Hybrid', bpHuman: '现场宣讲', agent: '培训材料+LMS' },
]

const TIER_COLORS: Record<string, string> = { Auto: '#34D399', Aug: '#38BDF8', Hybrid: '#FBBF24', Human: '#64748B' }

function Section({ icon: Icon, title, sourceNote, children }: any) {
  return (
    <div className="rounded-xl border border-border-default bg-bg-elevated p-5">
      <div className="mb-3 flex items-center gap-2">
        <Icon className="h-4 w-4 text-accent-primary-light" />
        <h2 className="text-sm font-semibold text-text-primary">{title}</h2>
      </div>
      {children}
      {sourceNote && <p className="mt-3 text-[11px] text-text-muted">来源：{sourceNote}</p>}
    </div>
  )
}

export default function L3Demo() {
  const [tab, setTab] = useState<'flow' | 'collab'>('flow')

  return (
    <div className="space-y-5">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="rounded-lg border border-accent-warning/30 bg-accent-warning/5 p-3 text-xs text-accent-warning">
        这是围绕单个L3(L3-IRI)手工搭建的demo原型——数据来自真实源文件摘录，不接自动化管道，不代表已确定的架构，仅供你判断"五维流程模型"这个概念能不能站住。
      </motion.div>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex flex-wrap items-center gap-2 text-xs text-text-muted">
          <span className="font-mono">L3-IRI</span>
          <span className="rounded-full bg-bg-surface px-2 py-0.5">保司域</span>
          <span className="rounded-full bg-bg-surface px-2 py-0.5">VS-1 保司投放 · S3</span>
        </div>
        <h1 className="mt-1 font-heading text-2xl font-bold text-text-primary">保司资源整合与深度对接</h1>
        <p className="mt-1 text-sm text-text-secondary">
          前置：L3-IAC-Auth(合同生效) → <span className="text-text-primary">本流程</span> → 后续：L3-IBE(保司业务运营赋能)
        </p>
      </motion.div>

      {/* 能力定位 */}
      <Section icon={Layers} title="① 能力定位——这个L3服务于哪项业务能力" sourceNote={CAPABILITY.source}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-text-primary">{CAPABILITY.id} · {CAPABILITY.name}</p>
            <p className="mt-1 max-w-xl text-xs text-text-secondary">{CAPABILITY.definition}</p>
          </div>
          <span className="shrink-0 rounded-full bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-400">能力成熟度: {CAPABILITY.maturity}</span>
        </div>
        <p className="mt-2 text-xs text-accent-warning">缺口：{CAPABILITY.gap}</p>
      </Section>

      {/* 人 */}
      <Section icon={Users} title="② 人——谁按理想态流程执行" sourceNote="流程蓝图_L3-IRI_V1.1.md 主责/协作/待确认事项字段">
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {ROLES.map(r => (
            <div key={r.role} className="rounded-lg border border-border-default bg-bg-surface p-2.5">
              <div className="flex items-center justify-between">
                <span className="text-sm text-text-primary">{r.role}</span>
                <span className="rounded bg-accent-primary/10 px-1.5 py-0.5 text-[10px] text-accent-primary-light">{r.raci}</span>
              </div>
              <p className="mt-1 text-xs text-text-muted">{r.type}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* 节点与物 */}
      <Section icon={Package} title="③ 节点与物——锚点节点 + 应交付的物理产出" sourceNote="T1节点索引 + 流程蓝图_L3-IRI 输出物表">
        <div className="mb-3 rounded-lg border border-border-default bg-bg-surface p-3">
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs text-accent-primary-light">{NODE.id}</span>
            <span className="text-xs font-bold text-amber-400">{NODE.priority}</span>
          </div>
          <p className="mt-1 text-sm font-semibold text-text-primary">{NODE.name}</p>
          <p className="mt-1 text-xs text-accent-warning">{NODE.gap}</p>
        </div>
        <div className="space-y-1.5">
          {DELIVERABLES.map(d => (
            <div key={d.l4} className="flex items-center justify-between gap-2 rounded-md bg-bg-surface px-2.5 py-1.5 text-xs">
              <span className="text-text-primary">{d.name}</span>
              <span className="font-mono text-text-muted">{d.l4}</span>
              <span className="text-text-secondary">{d.dest}</span>
            </div>
          ))}
        </div>
        {DELIVERABLES.filter(d => d.flag).map(d => (
          <p key={d.l4} className="mt-2 flex items-start gap-1.5 text-xs text-accent-warning"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{d.flag}</p>
        ))}
      </Section>

      {/* Tab: 流程现状 / AI协同标准 */}
      <div className="flex gap-1 rounded-lg bg-bg-elevated p-1">
        <button onClick={() => setTab('flow')} className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs ${tab === 'flow' ? 'bg-accent-primary text-white' : 'text-text-secondary'}`}>
          <GitBranch className="h-3.5 w-3.5" /> ④ 流程现状(理想态执行路径)
        </button>
        <button onClick={() => setTab('collab')} className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs ${tab === 'collab' ? 'bg-accent-primary text-white' : 'text-text-secondary'}`}>
          <Bot className="h-3.5 w-3.5" /> ⑤ AI人机协同标准
        </button>
      </div>

      {tab === 'flow' && (
        <Section icon={GitBranch} title="6步流程 · 含2个判断节点" sourceNote="流程蓝图_L3-IRI_V1.1.md 第三节·关键步骤">
          <div className="space-y-2">
            {STEPS.map((s, i) => (
              <div key={s.n}>
                <div className="rounded-lg border border-border-default bg-bg-surface p-3">
                  <div className="flex items-center gap-2">
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent-primary/15 text-xs font-bold text-accent-primary-light">{s.n}</span>
                    <span className="text-sm font-medium text-text-primary">{s.name}</span>
                    <span className="ml-auto font-mono text-[11px] text-text-muted">{s.l4}</span>
                  </div>
                  <p className="mt-1.5 pl-8 text-xs text-text-secondary">{s.detail}</p>
                  {s.gate && (
                    <p className="mt-1.5 flex items-start gap-1.5 pl-8 text-xs text-accent-primary-light">
                      <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />{s.gate}
                    </p>
                  )}
                  {s.flag && (
                    <p className="mt-1.5 flex items-start gap-1.5 pl-8 text-xs text-accent-warning">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{s.flag}
                    </p>
                  )}
                </div>
                {i < STEPS.length - 1 && <div className="flex justify-center py-0.5"><ArrowDown className="h-3.5 w-3.5 text-text-muted" /></div>}
              </div>
            ))}
          </div>
        </Section>
      )}

      {tab === 'collab' && (
        <Section icon={Bot} title="每条L4活动的人机协同判断" sourceNote="T20(automation_tier) 与 流程蓝图自带的'人介入点'列——两条独立产出的数据在这个例子上互相印证">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="border-b border-border-default text-left text-text-muted">
                <th className="py-1.5 pr-3">L4</th><th className="py-1.5 pr-3">活动</th><th className="py-1.5 pr-3">T20判断Tier</th><th className="py-1.5 pr-3">蓝图·人介入点</th><th className="py-1.5">Agent能力</th>
              </tr></thead>
              <tbody>
                {L4_COLLAB.map(l => (
                  <tr key={l.code} className="border-b border-border-default/50">
                    <td className="py-2 pr-3 font-mono text-accent-primary-light">{l.code}</td>
                    <td className="py-2 pr-3 text-text-primary">{l.name}</td>
                    <td className="py-2 pr-3">
                      <span className="rounded px-1.5 py-0.5" style={{ backgroundColor: `${TIER_COLORS[l.tier]}22`, color: TIER_COLORS[l.tier] }}>{l.tier}</span>
                    </td>
                    <td className="py-2 pr-3 text-text-secondary">{l.bpHuman}</td>
                    <td className="py-2 text-text-muted">{l.agent}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex items-center gap-2 rounded-lg border border-border-default bg-bg-surface p-2.5 text-xs text-text-secondary">
            <ShieldAlert className="h-3.5 w-3.5 shrink-0 text-text-muted" />
            这个例子里资金安全硬门(funds_safety_hard_gate)没有触发，7条L4里1条Human(需Mark判断权限边界)、4条Aug、1条Auto、1条Hybrid——汇总到能力层"可否被AI替代"这个结论，用什么聚合规则(多数决/一票否决/风险优先)还没定，这里先如实列出分布，不擅自下结论。
          </div>
        </Section>
      )}

      <div className="rounded-lg border border-border-default bg-bg-elevated p-4 text-xs text-text-secondary">
        <p className="font-semibold text-text-primary">这个demo想验证的事：</p>
        <p className="mt-1">五维（能力/人/节点与物/流程现状/AI协同标准）用真实数据摆出来是否讲得通；流程蓝图自己标注的"待升级"缺口（如《整合就绪确认书》口头确认）能不能直接当"现状缺口"用，不用再另写比对算法；蓝图的"人介入点"和T20的Tier判断在这个例子上是否一致（结果：一致）。</p>
      </div>
    </div>
  )
}
