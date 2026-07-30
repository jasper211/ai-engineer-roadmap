#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '../..')
const snapshotPath = path.join(root, '10_部署与运行_Deploy_and_Run/frontend/public/data/model_snapshots/L3-BAM.json')
const outputPath = path.join(root, '07_接入记忆_Integrate_Memory/analysis_packages/L3-BAM.reviewed.json')
const snapshot = JSON.parse(fs.readFileSync(snapshotPath, 'utf8'))

const specs = {
  '01': {
    role: '价值交付物', capabilities: ['开户需求识别', '资料缺项检查', '银行准入评估'],
    reshape: 'AI整理开户需求、检查资料缺项并形成银行准入评估草稿；业务负责人确认银行选择与正式申请。',
    quality: '开户目的、主体、授权和资料清单完整，准入评估口径经负责人确认。',
    ai: '整理需求、核对资料清单、生成准入评估草稿', human: '确认开户需求、选择银行并批准正式申请',
    handoff: ['准入标准未确认', '资料或授权不完整', '银行选择存在争议'], controls: ['正式开户申请前人工批准'],
    context: '账户全生命周期起点，同时服务银行准入记录；数据库交付物注明四维评估当前尚无标准。',
    risks: ['银行准入四维度由访谈提出，尚未形成正式标准', '蓝图将资料准备标为Human'],
    recommendation: '先固化银行准入标准与资料清单，再验证AI资料预审。', tier: 'Aug', quadrant: 'q2',
    tasks: [['01-a', '汇集开户需求与主体资料', 'Aug', '输入可整理，但需求真实性由业务确认'], ['01-b', '执行资料缺项与授权检查', 'Aug', '可按清单检查，标准尚待固化'], ['01-c', '生成银行准入评估草稿', 'Aug', '可生成四维评估草稿，银行选择不可自动决定']],
  },
  '02': {
    role: '支撑交付物', capabilities: ['柜台材料交接', '外勤办理', '回执核验'],
    reshape: 'AI准备柜台办理清单、跟踪状态并核对回执；线下柜台办理仍由人员完成。',
    quality: '办理材料与申请一致，回执主体、账号、日期和银行印章可核验。',
    ai: '准备办理清单、跟踪进度、核对回执字段', human: '执行银行柜台外勤并接收正式回执',
    handoff: ['银行要求补件', '柜台规则变化', '回执信息异常'], controls: ['银行柜台正式受理与回执确认'],
    context: '开户申请后的线下外勤步骤，数据库Tier为Human且接口可达性、回退能力均为0。',
    risks: ['依赖银行线下柜台', '输入结构化和API条件不足'],
    recommendation: '不替代外勤，只验证材料准备和回执核验辅助。', tier: 'Human', quadrant: 'q4',
    tasks: [['02-a', '生成柜台办理材料清单', 'Aug', 'AI可辅助准备，需人员确认银行要求'], ['02-b', '银行柜台办理', 'Human', '必须由人员完成线下受理'], ['02-c', '核对并归档开户回执', 'Aug', '可抽取字段并提示异常，原件由人确认']],
  },
  '03': {
    role: '控制交付物', capabilities: ['U盾登记', '双签控制', '领用追踪', '异常审计'],
    reshape: 'AI维护U盾与支票领用台账、检查双签和交接异常；实物保管、授权和双签不得自动放行。',
    quality: '实物、人员、权限和领用记录一一对应，双签有效且变更可追溯。',
    ai: '维护台账、检查双签完整性、识别领用与交接异常', human: '保管实物、执行授权和双签、处理控制例外',
    handoff: ['双签缺失或失效', '实物与台账不一致', '人员权限异常'], controls: ['U盾/支票双签与实物交接'],
    context: '蓝图标为P0控制步骤；数据库备注现有支票双签存在“签完一本交财务”的控制失效风险。',
    risks: ['现有双签可能形同虚设', 'AI不能替代实物保管和授权责任'],
    recommendation: '优先补强双签控制与台账一致性，再做异常监测。', tier: 'Hybrid', quadrant: 'q2',
    tasks: [['03-a', '登记U盾/Token与持有人信息', 'Auto', '字段明确，可自动维护台账'], ['03-b', '检查双签与领用记录完整性', 'Auto', '规则清晰，可自动检查'], ['03-c', '执行实物交接和授权确认', 'Human', '涉及实物与授权责任'], ['03-d', '识别并升级控制异常', 'Hybrid', 'AI识别异常，人决定冻结或纠正']],
  },
  '04': {
    role: '价值交付物', capabilities: ['对账单接收监控', '文件识别', '完整性检查', '定向分发'],
    reshape: 'AI监控月度对账单到达、识别账户与期间、更新接收清单并按规则分发；缺失转L4-BAM-05。',
    quality: '账户、期间、文件版本和接收状态完整，分发对象正确且可追溯。',
    ai: '监控接收、识别文件、更新清单并分发', human: '处理低置信文件和异常接收渠道',
    handoff: ['文件无法识别', '账户或期间不匹配', '到期仍未收到'], controls: ['完整性检查通过后进入L3-CFM'],
    context: '蓝图P0主链及唯一判断点“对账单是否完整收到”；D1=3、D4=2，自动处理条件相对最好。',
    risks: ['部分银行渠道可能无法稳定接入', '错误分发会影响后续月度对账'],
    recommendation: '作为首批AIT影子验证，先做接收识别、完整性检查和分发。', tier: 'Auto', quadrant: 'q1',
    tasks: [['04-a', '监控并接收月度对账单', 'Auto', '周期和目标账户明确'], ['04-b', '识别账户、期间与文件版本', 'Auto', '结构化识别可自动执行'], ['04-c', '更新接收清单并检查完整性', 'Auto', '蓝图存在明确完整性判断'], ['04-d', '向下游定向分发对账单', 'Auto', '完整性通过后可按规则分发']],
  },
  '05': {
    role: '控制交付物', capabilities: ['缺失识别', '银行跟进', '状态追踪', '升级闭环'],
    reshape: 'AI生成缺失清单、跟踪催办和更新记录；对银行的正式沟通、升级和关闭确认由人员负责。',
    quality: '缺失账户、期间、责任人、跟进记录和关闭证据完整。',
    ai: '生成缺失清单、提醒催办、维护跟进状态', human: '联系银行、处理争议并确认关闭',
    handoff: ['超过时限仍缺失', '银行反馈存在争议', '影响下游关账'], controls: ['缺失关闭证据确认'],
    context: '由“对账单部分缺失”判断分支显式触发，是P0异常支路。',
    risks: ['外部银行响应不可控', '数据库Tier为Auto但蓝图明确人工主动跟进'],
    recommendation: '先做缺失识别和催办助手，保留银行沟通与关闭确认。', tier: 'Aug', quadrant: 'q2',
    tasks: [['05-a', '生成对账单缺失清单', 'Auto', '由接收状态自动识别'], ['05-b', '生成催办计划与提醒', 'Auto', '可按时限规则触发'], ['05-c', '联系银行处理缺失或争议', 'Human', '依赖外部沟通和判断'], ['05-d', '更新记录并确认关闭', 'Hybrid', 'AI维护状态，人确认证据闭环']],
  },
  '06': {
    role: '支撑交付物', capabilities: ['变更资料准备', '变更状态跟踪', '回执核验', '内部同步'],
    reshape: 'AI准备账户变更资料、跟踪回执并同步内部记录；正式变更申请与异常批准保留人工。',
    quality: '变更前后信息、授权、银行回执和内部系统记录一致。',
    ai: '准备资料、比对变更前后字段、核验回执并生成更新草稿', human: '批准变更申请并处理银行异常',
    handoff: ['授权不完整', '关键信息冲突', '银行回执与申请不一致'], controls: ['账户关键信息变更批准'],
    context: '账户生命周期P1维护步骤；规则清晰度仅1，蓝图标为Human。',
    risks: ['变更规则未充分结构化', '关键账户信息变更需要授权'],
    recommendation: '先补变更类型与授权规则，再验证资料生成和回执核验。', tier: 'Aug', quadrant: 'unclassified',
    tasks: [['06-a', '准备账户变更资料', 'Aug', '可按变更类型生成清单'], ['06-b', '提交并跟踪正式变更', 'Human', '需要授权并依赖银行'], ['06-c', '核验回执并同步内部记录', 'Hybrid', 'AI比对，人确认正式生效']],
  },
  '07': {
    role: '支撑交付物', capabilities: ['账户状态监控', '差异识别', '盘点汇总', '异常升级'],
    reshape: 'AI汇集账户状态、识别长期未动或信息异常并生成盘点表；负责人确认处置。',
    quality: '账户范围完整、状态与银行记录一致、异常有责任人与处置状态。',
    ai: '汇集状态、生成盘点表、提示异常账户', human: '确认异常性质并决定保留、整改或注销',
    handoff: ['状态来源冲突', '发现异常账户', '需要注销或权限调整'], controls: ['异常账户处置批准'],
    context: 'P1周期性盘点步骤；D1-D4较完整，适合自动汇集但处置判断仍需人。',
    risks: ['数据源一致性需验证', '账户处置涉及责任与授权'],
    recommendation: '可做自动盘点和异常提示，处置决策保持人工。', tier: 'Hybrid', quadrant: 'unclassified',
    tasks: [['07-a', '汇集账户状态数据', 'Auto', '数据汇集适合自动执行'], ['07-b', '识别异常并生成盘点表', 'Auto', '规则化比对可自动完成'], ['07-c', '确认异常与处置方案', 'Human', '涉及业务责任和授权']],
  },
  '08': {
    role: '控制交付物', capabilities: ['交接清单', '权限核验', '实物确认', '记录归档'],
    reshape: 'AI生成交接清单、核对人员权限与历史记录；U盾实物交接和授权确认由双方人员完成。',
    quality: '交出人、接收人、实物编号、权限和时间完整，双方确认可追溯。',
    ai: '生成交接清单、核对权限和台账差异', human: '执行实物交接并完成双方确认',
    handoff: ['实物缺失', '权限不一致', '交接双方未确认'], controls: ['U盾实物双人交接'],
    context: 'P1实物与人员交接步骤；D4=0，无法依靠系统接口完成闭环。',
    risks: ['实物交接不可数字化替代', '接口可达性为0'],
    recommendation: '只做交接清单和差异检查辅助，不自动确认交接完成。', tier: 'Hybrid', quadrant: 'q4',
    tasks: [['08-a', '生成U盾交接清单', 'Aug', '可从台账生成清单'], ['08-b', '执行实物交接与双方确认', 'Human', '实物责任不可替代'], ['08-c', '核对并归档交接记录', 'Aug', '可比对字段并提示缺项']],
  },
  '09': {
    role: '支撑交付物', capabilities: ['费用汇总', '年检日历', '资料检查', '完成跟踪'],
    reshape: 'AI汇总银行费用、监控年检期限并生成资料清单；正式年检提交和异常处理由人员完成。',
    quality: '费用范围完整、期限准确、年检资料和完成回执可追溯。',
    ai: '汇总费用、监控期限、生成资料清单和提醒', human: '确认费用异常并执行正式年检',
    handoff: ['费用异常', '年检资料缺失', '银行规则变化'], controls: ['年检完成回执确认'],
    context: '账户生命周期P1周期维护步骤；数据库Tier为Auto但规则清晰度仅1。',
    risks: ['不同银行费用和年检要求可能变化', '正式年检依赖银行'],
    recommendation: '先验证费用汇总、期限监控和资料预审。', tier: 'Aug', quadrant: 'unclassified',
    tasks: [['09-a', '汇总银行费用并识别异常', 'Auto', '数据汇总和阈值提示可自动'], ['09-b', '监控年检期限并准备资料', 'Auto', '周期和清单可规则化'], ['09-c', '执行年检并确认完成', 'Human', '正式办理依赖银行与授权']],
  },
  '10': {
    role: '控制交付物', capabilities: ['注销条件检查', '余额核验', '资金归集', '注销回执确认'],
    reshape: 'AI检查注销条件、核对余额和准备资金归集清单；资金转出、正式注销和回执确认保留人工控制。',
    quality: '余额清零、未结事项关闭、资金去向和注销回执完整。',
    ai: '检查注销前置条件、生成资金归集清单、核对回执', human: '批准资金转出并执行正式注销',
    handoff: ['余额或未结事项不为零', '资金去向异常', '注销回执缺失'], controls: ['资金转出批准与正式注销确认'],
    context: '账户生命周期P1终止步骤，涉及资金转出和不可逆注销。',
    risks: ['资金操作和注销不可逆', '输入结构化与规则清晰度均仅1'],
    recommendation: '先补注销检查清单；AI只做前置核验和回执比对。', tier: 'Hybrid', quadrant: 'q4',
    tasks: [['10-a', '检查余额与未结事项', 'Auto', '前置条件可按清单检查'], ['10-b', '生成资金归集与注销材料', 'Aug', '可生成草稿，需人工复核'], ['10-c', '批准资金转出并办理注销', 'Human', '涉及资金与不可逆操作'], ['10-d', '核验注销回执并关闭账户', 'Hybrid', 'AI比对，人确认正式关闭']],
  },
  '11': {
    role: '价值交付物', capabilities: ['全生命周期归集', '完整性检查', '索引生成', '审计追溯'],
    reshape: 'AI持续归集开户、变更、U盾、对账、年检和注销证据，生成账户档案袋并检查缺项。',
    quality: '每个账户全生命周期材料齐全、版本唯一、索引清楚且可审计。',
    ai: '持续归集证据、生成索引和档案袋、检查生命周期缺项', human: '确认例外材料和最终归档状态',
    handoff: ['关键凭证缺失', '版本冲突', '账户状态与档案不一致'], controls: ['最终归档完整性确认'],
    context: '全流程终点，形成VN-BAM-01银行账户全生命周期管理资产包。',
    risks: ['依赖前序环节持续提供有效证据', 'D4仅1且回退、合规维度均为1'],
    recommendation: '先做旁路档案归集和缺项检查，不替代正式归档确认。', tier: 'Hybrid', quadrant: 'unclassified',
    tasks: [['11-a', '归集账户全生命周期材料', 'Auto', '可按账户主键持续归集'], ['11-b', '生成档案索引并检查缺项', 'Auto', '交付物清单明确'], ['11-c', '处理版本冲突和例外材料', 'Hybrid', 'AI提示，人确认有效版本'], ['11-d', '确认并发布正式档案袋', 'Human', '正式归档状态由责任人确认']],
  },
}

const l4ByCode = Object.fromEntries(snapshot.l4s.map(item => [item.l4_code, item]))
const stepRefs = {}
for (const step of snapshot.blueprint.steps) {
  for (const code of step.l4_codes) stepRefs[code] = step.evidence_ref
}
const valueEvidence = Object.values(snapshot.value_nodes[0]?.evidence_refs || {}).filter(Boolean)
function refsFor(code) {
  return [...new Set([...Object.values(l4ByCode[code].evidence_refs).filter(Boolean), stepRefs[code], ...valueEvidence].filter(Boolean))].sort()
}
function dbBasis(l4, spec) {
  return [
    `数据库Tier=${l4.tier}`,
    `统一模型建议Tier=${spec.tier}`,
    `D1-D6=${Object.values(l4.d1_d6).join('/')}`,
    `蓝图人工触点=${l4.human_touchpoint || '未登记'}`,
    'VN-BAM-01=P0/FAIL',
  ]
}

const l4Analysis = snapshot.l4s.map(l4 => {
  const spec = specs[l4.l4_code.slice(-2)]
  return {
    l4_code: l4.l4_code,
    analysis_status: 'MODEL_DRAFT',
    evidence_refs: refsFor(l4.l4_code),
    confidence: 'EVIDENCE_GROUNDED_DRAFT',
    database_tier: l4.tier,
    recommended_tier: spec.tier,
    deliverable_role: spec.role,
    specific_capabilities: spec.capabilities,
    ai_reshape: spec.reshape,
    quality_anchor: spec.quality,
    ai_responsibility: spec.ai,
    human_responsibility: spec.human,
    handoff_triggers: spec.handoff,
    control_gates: spec.controls,
    owner_scope: '岗位族/部门待蓝图RACI补充',
    data_basis: dbBasis(l4, spec),
    process_context: spec.context,
    risks_limits: spec.risks,
    current_recommendation: spec.recommendation,
    quadrant: spec.quadrant,
  }
})

const tasks = snapshot.l4s.flatMap(l4 => specs[l4.l4_code.slice(-2)].tasks.map(([id, name, tier, why]) => ({
  task_id: id,
  l4_code: l4.l4_code,
  task_name: name,
  source_type: 'MODEL_DECOMPOSITION_FROM_BLUEPRINT_AND_L4',
  evidence_refs: refsFor(l4.l4_code),
  analysis_status: 'MODEL_DRAFT',
  suggested_tier: tier,
  tier_rationale: why,
})))

const priorities = l4Analysis.map(item => ({
  l4_code: item.l4_code,
  quadrant: item.quadrant,
  data_basis: item.data_basis,
  process_context: item.process_context,
  risks_limits: item.risks_limits,
  current_recommendation: item.current_recommendation,
  evidence_refs: item.evidence_refs,
  analysis_status: 'MODEL_DRAFT',
}))

const decisions = [
  {
    priority: 'P0-1', task_ids: ['04-a', '04-b', '04-c', '04-d'],
    title: '先验证月度对账单接收、完整性检查与分发',
    pilot_scope: '选择一个月度周期和少量银行账户，旁路生成接收清单并与人工清单比较',
    human_boundary: '文件识别异常、缺失关闭和进入L3-CFM的最终确认由财务人员负责',
    evidence_refs: refsFor('L4-BAM-04'), analysis_status: 'MODEL_DRAFT',
  },
  {
    priority: 'P0-2', task_ids: ['05-a', '05-b', '05-c', '05-d'],
    title: '同步验证缺失识别与催办跟踪',
    pilot_scope: '只生成缺失清单、催办建议和状态记录，不自动向银行发送正式结论',
    human_boundary: '银行沟通、争议处理和缺失关闭确认由责任人完成',
    evidence_refs: refsFor('L4-BAM-05'), analysis_status: 'MODEL_DRAFT',
  },
  {
    priority: 'P1-1', task_ids: ['03-a', '03-b', '03-c', '03-d'],
    title: '先整改U盾/支票双签，再建设异常监测',
    pilot_scope: '建立实物—人员—权限—台账一致性清单，检查历史样本中的双签与交接缺口',
    human_boundary: '实物保管、授权、冻结和双签不得由AI自动完成',
    evidence_refs: refsFor('L4-BAM-03'), analysis_status: 'MODEL_DRAFT',
  },
  {
    priority: 'P1-2', task_ids: ['11-a', '11-b'],
    title: '旁路生成账户全生命周期档案袋',
    pilot_scope: '选取已完成生命周期的历史账户，自动归集材料、生成索引并标记缺项',
    human_boundary: '版本冲突、例外材料和正式归档状态由档案责任人确认',
    evidence_refs: refsFor('L4-BAM-11'), analysis_status: 'MODEL_DRAFT',
  },
]

const result = {
  schema_version: 'vnw.l3-analysis.v1',
  analysis_standard_id: 'VNW-L3-COM-GOLD-v1.0',
  generation_mode: 'UNIFIED_MODEL_EVIDENCE_GROUNDED',
  analysis_status: 'REVIEWED',
  model_run: {
    model_name: 'VNW统一L3分析模型',
    model_version: 'v1.0-bam-pilot',
    prompt_version: 'VNW-L3-COM-GOLD-v1.0',
    generated_at: new Date().toISOString(),
    input_snapshot_hash: '',
  },
  source_scope: {
    database: 'process_analytics',
    knowledge: 'ACTIVE supplemental evidence only',
    evidence_count: snapshot.evidence_registry.length,
    blueprint: snapshot.blueprint.filename,
  },
  l4_analysis: l4Analysis,
  tasks,
  priority_drafts: priorities,
  decision_drafts: decisions,
  control_chain: [
    { level: '一级', l4_code: 'L4-BAM-03', label: 'U盾/支票双签与实物控制', tone: 'critical' },
    { level: '二级', l4_code: 'L4-BAM-04', label: '对账单完整性判断', tone: 'standard' },
    { level: '三级', l4_code: 'L4-BAM-05', label: '缺失跟进与关闭确认', tone: 'critical' },
  ],
  rejected_task_sources: [],
  missing_analysis: ['蓝图RACI岗位族与部门信息', '逐L4业务价值量化数据', '银行准入四维正式标准'],
}

fs.mkdirSync(path.dirname(outputPath), { recursive: true })
fs.writeFileSync(outputPath, `${JSON.stringify(result, null, 2)}\n`)
console.log(JSON.stringify({ output: outputPath, l4: l4Analysis.length, tasks: tasks.length, priorities: priorities.length, decisions: decisions.length }))
