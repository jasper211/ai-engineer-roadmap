#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'

const agentRoot = path.resolve(import.meta.dirname, '../..')
const snapshotDir = path.join(agentRoot, '10_部署与运行_Deploy_and_Run/frontend/public/data/model_snapshots')
const outputDir = path.join(agentRoot, '07_接入记忆_Integrate_Memory/analysis_packages')
const demoDir = path.join(agentRoot, '03_规划项目结构_Plan_Project_Structure')

function readArray(html, name) {
  const startToken = `const ${name}`
  const start = html.indexOf(startToken)
  const equals = html.indexOf('=', start)
  const arrayStart = html.indexOf('[', equals)
  if (start < 0 || equals < 0 || arrayStart < 0) throw new Error(`找不到 ${name}`)
  let depth = 0
  let quote = ''
  let escaped = false
  for (let index = arrayStart; index < html.length; index += 1) {
    const char = html[index]
    if (quote) {
      if (escaped) escaped = false
      else if (char === '\\') escaped = true
      else if (char === quote) quote = ''
      continue
    }
    if (char === '"' || char === "'" || char === '`') {
      quote = char
      continue
    }
    if (char === '[') depth += 1
    if (char === ']') {
      depth -= 1
      if (depth === 0) return vm.runInNewContext(`(${html.slice(arrayStart, index + 1)})`)
    }
  }
  throw new Error(`数组 ${name} 未闭合`)
}

function refsFor(snapshot, code) {
  const l4 = snapshot.l4s.find(item => item.l4_code === code)
  return [...new Set(Object.values(l4?.evidence_refs || {}).filter(Boolean))].sort()
}

function split(value) {
  return String(value || '').split(/[、；]/).map(item => item.trim()).filter(Boolean)
}

function basePackage(snapshot, demoFile, modelName) {
  return {
    schema_version: 'vnw.l3-analysis.v1',
    analysis_standard_id: 'VNW-L3-COM-GOLD-v1.0',
    generation_mode: 'REVIEWED_DEMO_MIGRATION',
    analysis_status: 'REVIEWED',
    model_run: {
      model_name: modelName,
      model_version: 'reviewed-demo-20260729',
      prompt_version: 'VNW-L3-COM-GOLD-v1.0',
      generated_at: new Date().toISOString(),
      input_snapshot_hash: '',
    },
    source_scope: {
      database: 'process_analytics',
      knowledge: 'ACTIVE supplemental evidence only',
      evidence_count: snapshot.evidence_registry.length,
      migration_source: demoFile,
    },
    rejected_task_sources: [],
    missing_analysis: [],
  }
}

const iriDelivery = {
  '01': ['支撑交付物', '条款理解、差异识别、权限裁决', '生成谈判底稿、识别权限差异与冲突；由负责人保留最终权限裁决。', '边界完整、冲突已裁定、签批可追溯'],
  '02': ['支撑交付物', '多源汇集、分类去重、缺项检查', '自动汇集多源资源、去重归类、检查缺项并生成标准清单。', '资源全量、状态准确、责任清晰'],
  '03': ['支撑交付物', '联调跟踪、证据归集、异常闭环', '聚合联调日志、异常、测试结果与关闭证据，自动形成报告。', '测试有证据、异常有闭环'],
  '04': ['支撑交付物', '权限配置、状态验证、定向通知', '监听配置与验证结果，满足条件后自动生成并定向分发通知。', '生效对象、时间和权限范围一致'],
  '05': ['核心价值交付物', '证据核验、质量门判断、正式签批', '自动核验全部前置交付物与检查清单，证据齐备后生成确认书。', '签字版、前置证据齐全、可触发L3-IBE'],
  '06': ['支撑交付物', '接口理解、约束转译、规范维护', '依据系统能力、接口约束和安全要求生成规范，并随联调结果更新。', '接口可执行、安全约束完整'],
  '07': ['支撑交付物', '内容生成、知识验证、责任交接', '生成培训材料、知识检查与换手清单；人完成宣讲和最终确认。', '关键人员掌握、换手责任明确'],
}

const iriPriority = {
  '01': ['确定系统和业务可以使用哪些权限，是全部对接工作的前置边界。', '蓝图明确负责人必须参与最终权限裁决，存在单点判断依赖。', 'AI准备条款差异与冲突清单，人保留裁决和签批。', 'q4'],
  '02': ['汇集保司可用系统、数据、人员及其他资源，为后续联调提供输入。', '主要风险是来源分散、重复和缺项，属于可规则检查的问题。', '适合作为第一批AIT验证，关注完整率和缺项识别。', 'q2'],
  '03': ['汇总系统、数据和人员三线对接结果，是判断技术验证是否通过的证据。', '日志可自动归集，但异常是否真正关闭仍需责任团队确认。', '先自动生成报告和异常列表，保留异常关闭确认。', 'q2'],
  '04': ['权限配置和测试通过后，向相关使用方确认何时、对谁、哪些权限已经生效。', '错误通知会导致未授权使用或业务无法启动，需要测试结果作为质量门。', '规则明确，适合形成“配置—测试—通知”自动闭环。', 'q2'],
  '05': ['汇集所有前置交付物，形成触发L3-IBE的核心确认凭证。', '数据库标为Auto，但当前仍是口头确认，正式签字和异常升级规则没有落地。', '保留真实Tier；治理补齐前暂不自动出具确认书。', 'q2'],
  '06': ['把接口、安全、数据和系统约束固化为后续对接与维护的共同规范。', '规范可能随联调变化，需要保证版本与实际配置一致。', '适合自动生成初稿并根据联调结果持续更新。', 'q2'],
  '07': ['将系统、权限和操作方式交接给保司人员，证明人员侧具备运营条件。', '现场宣讲、答疑和责任确认依赖真实互动，不能仅凭材料判断完成。', 'AI生成材料和知识检查，人负责培训与最终换手确认。', 'q4'],
}

function migrateIri() {
  const code = 'L3-IRI'
  const demoFile = 'L3流程模型_demo_L3-IRI_V2评估版_20260728.html'
  const html = fs.readFileSync(path.join(demoDir, demoFile), 'utf8')
  const snapshot = JSON.parse(fs.readFileSync(path.join(snapshotDir, `${code}.json`), 'utf8'))
  const tasks = readArray(html, 'tasks')
  const l4Analysis = snapshot.l4s.map(l4 => {
    const id = l4.l4_code.slice(-2)
    const delivery = iriDelivery[id]
    const priority = iriPriority[id]
    return {
      l4_code: l4.l4_code,
      analysis_status: 'MODEL_DRAFT',
      evidence_refs: refsFor(snapshot, l4.l4_code),
      confidence: 'REVIEWED_SAMPLE',
      database_tier: l4.tier,
      recommended_tier: l4.tier,
      deliverable_role: delivery[0],
      specific_capabilities: split(delivery[1]),
      ai_reshape: delivery[2],
      quality_anchor: delivery[3],
      ai_responsibility: delivery[2].split('；')[0],
      human_responsibility: delivery[2].split('；')[1] || '异常与最终结果由责任人确认',
      handoff_triggers: id === '05' ? ['前置证据不齐', '检查清单不通过', '缺少正式签字'] : ['异常或低置信结果', '需要业务裁决'],
      control_gates: id === '05' ? ['正式签字与就绪确认'] : ['交付物质量锚点通过'],
      owner_scope: '以蓝图RACI与岗位族为准',
      data_basis: [`数据库Tier=${l4.tier}`, `D1-D6=${Object.values(l4.d1_d6).join('/')}`, '分析迁自经评审IRI Demo'],
      process_context: priority[0],
      risks_limits: [priority[1]],
      current_recommendation: priority[2],
      quadrant: priority[3],
    }
  })
  const taskItems = tasks.map(task => ({
    task_id: task.id,
    l4_code: task.l4,
    task_name: task.name,
    source_type: 'REVIEWED_DEMO_TASK',
    evidence_refs: refsFor(snapshot, task.l4),
    analysis_status: 'MODEL_DRAFT',
    suggested_tier: task.tier,
    tier_rationale: task.why,
  }))
  const result = {
    ...basePackage(snapshot, demoFile, 'IRI既有评审Demo迁移'),
    l4_analysis: l4Analysis,
    tasks: taskItems,
    priority_drafts: l4Analysis.map(item => ({
      l4_code: item.l4_code, quadrant: item.quadrant, data_basis: item.data_basis,
      process_context: item.process_context, risks_limits: item.risks_limits,
      current_recommendation: item.current_recommendation, evidence_refs: item.evidence_refs,
      analysis_status: 'MODEL_DRAFT',
    })),
    decision_drafts: [
      { priority: 'P0-1', task_ids: ['T05', 'T06', 'T07'], title: '先验证资源清单自动汇集与缺项检查', pilot_scope: '选取一个真实对接项目，旁路生成资源清单并与人工结果比对', human_boundary: '资源责任人与最终状态由项目负责人确认', evidence_refs: refsFor(snapshot, 'L4-IRI-02'), analysis_status: 'MODEL_DRAFT' },
      { priority: 'P0-2', task_ids: ['T15', 'T16', 'T17'], title: '验证权限配置—测试—通知闭环', pilot_scope: '使用测试环境验证配置状态、测试结果和通知对象的一致性', human_boundary: '失败例外和正式生效由权限责任人批准', evidence_refs: refsFor(snapshot, 'L4-IRI-04'), analysis_status: 'MODEL_DRAFT' },
      { priority: 'P1-1', task_ids: ['T22', 'T23', 'T24', 'T25', 'T26'], title: '先补齐整合就绪质量门，再设计自动确认', pilot_scope: '先建立正式检查清单、签字规则和异常升级路径', human_boundary: '正式签字与触发后续L3保留人工授权', evidence_refs: refsFor(snapshot, 'L4-IRI-05'), analysis_status: 'MODEL_DRAFT' },
    ],
    control_chain: [],
  }
  fs.writeFileSync(path.join(outputDir, `${code}.reviewed.json`), `${JSON.stringify(result, null, 2)}\n`)
  return { code, l4: l4Analysis.length, tasks: taskItems.length }
}

const ibrdDelivery = {
  '01': ['支撑交付物', '资格条件核验、资料缺项识别', '自动预审并生成启动清单', '资格条件有依据、缺项可定位', '《合作资格预审与流程启动计划》'],
  '02': ['支撑交付物', '责任识别、协作规则设计', 'AI建议沟通机制；人确认责任关系', '责任人、频率和升级路径明确', '《项目沟通机制建立》'],
  '03': ['支撑交付物（测试拆分）', '多源调查、证据归集、异常提示', '执行标准查验并生成证据包', '证据完整、异常可追溯', '《合作伙伴尽职调查记录》'],
  '04': ['控制交付物', '牌照核验、权威确认', 'AI检索比对；人完成保司确认', '牌照状态与权威确认一致', '《牌照核查与保司确认记录》'],
  '05': ['支撑交付物（测试拆分）', '股权穿透、关联方识别', '执行查册、穿透和风险标记', '穿透路径完整、异常有证据', '《DD Form与股东穿透查册结果》'],
  '06': ['控制交付物（测试拆分）', '规则评分、合规判断、升级处置', 'AI建议评级；人批准高风险结论', '评级规则明确、升级留痕', '《AML风险评级记录》'],
  '07': ['核心价值交付物（测试拆分）', '路径选择、商业与合规权衡', 'AI形成建议；负责人作出决议', '准入依据完整、决议可追溯', '《渠道准入与合作路径决策记录》'],
  '08': ['支撑交付物（测试拆分）', '到期监控、事件触发、差异复核', '持续监控并发起更新', '触发及时、变化有记录', '《DD Form年度更新记录》'],
}

function migrateIbrd() {
  const code = 'L3-IBRD'
  const demoFile = 'L3流程模型_demo_L3-IBRD_标准测试版_20260728.html'
  const html = fs.readFileSync(path.join(demoDir, demoFile), 'utf8')
  const snapshot = JSON.parse(fs.readFileSync(path.join(snapshotDir, `${code}.json`), 'utf8'))
  const tasks = readArray(html, 'tasks')
  const matrixItems = readArray(html, 'matrixItems')
  const matrixById = Object.fromEntries(matrixItems.map(item => [item.id, item]))
  const l4Analysis = snapshot.l4s.map(l4 => {
    const id = l4.l4_code.slice(-2)
    const delivery = ibrdDelivery[id]
    const priority = matrixById[id]
    return {
      l4_code: l4.l4_code,
      analysis_status: 'MODEL_DRAFT',
      evidence_refs: refsFor(snapshot, l4.l4_code),
      confidence: 'REVIEWED_TEST_SAMPLE',
      database_tier: l4.tier,
      recommended_tier: priority.tier,
      deliverable_role: delivery[0],
      proposed_deliverable: delivery[4],
      specific_capabilities: split(delivery[1]),
      ai_reshape: delivery[2],
      quality_anchor: delivery[3],
      ai_responsibility: delivery[2].split('；')[0],
      human_responsibility: delivery[2].split('；')[1] || '异常与最终结果由责任人确认',
      handoff_triggers: ['异常或资料不足', '涉及准入、合规或外部权威确认'],
      control_gates: id === '01' ? ['资格预审门'] : id === '06' ? ['AML风险门'] : id === '07' ? ['准入决策门'] : ['交付物质量锚点通过'],
      owner_scope: '以蓝图RACI与岗位族为准',
      data_basis: [`数据库Tier=${l4.tier}`, `Demo建议Tier=${priority.tier}`, `D1-D6=${Object.values(l4.d1_d6).join('/')}`, '缺少per-L4价值数据'],
      process_context: priority.background,
      risks_limits: [priority.risk],
      current_recommendation: priority.suggestion,
      quadrant: 'unclassified',
    }
  })
  const taskItems = tasks.map(task => {
    const l4Code = `L4-IBRD-${task.l4}`
    return {
      task_id: task.id, l4_code: l4Code, task_name: task.name,
      source_type: 'REVIEWED_DEMO_TASK',
      evidence_refs: refsFor(snapshot, l4Code),
      analysis_status: 'MODEL_DRAFT', suggested_tier: task.tier, tier_rationale: task.why,
    }
  })
  const result = {
    ...basePackage(snapshot, demoFile, 'IBRD标准测试Demo迁移'),
    l4_analysis: l4Analysis,
    tasks: taskItems,
    priority_drafts: l4Analysis.map(item => ({
      l4_code: item.l4_code, quadrant: 'unclassified', data_basis: item.data_basis,
      process_context: item.process_context, risks_limits: item.risks_limits,
      current_recommendation: item.current_recommendation, evidence_refs: item.evidence_refs,
      analysis_status: 'MODEL_DRAFT',
    })),
    decision_drafts: [
      { priority: 'P0-1', task_ids: ['T01', 'T02'], title: '验证预审与资料缺项识别', pilot_scope: '选择一批历史合作申请，旁路比较预审结果与缺项召回率', human_boundary: '资格条件和终止决定由业务负责人确认', evidence_refs: refsFor(snapshot, 'L4-IBRD-01'), analysis_status: 'MODEL_DRAFT' },
      { priority: 'P0-2', task_ids: ['T07'], title: '验证DD查册与股东穿透', pilot_scope: '在历史样本中验证关系穿透、异常标记和证据包完整性', human_boundary: '风险解释与处置决定由合规人员确认', evidence_refs: refsFor(snapshot, 'L4-IBRD-05'), analysis_status: 'MODEL_DRAFT' },
      { priority: 'P1-1', task_ids: ['T12'], title: '验证到期与重大事件触发', pilot_scope: '先建立触发事件和更新周期清单，再运行提醒试点', human_boundary: '重大变化定义和是否重新尽调由负责人确认', evidence_refs: refsFor(snapshot, 'L4-IBRD-08'), analysis_status: 'MODEL_DRAFT' },
    ],
    control_chain: [
      { level: '资格门', l4_code: 'L4-IBRD-01', label: '不通过则终止或补件', tone: 'critical' },
      { level: '合规门', l4_code: 'L4-IBRD-06', label: '高风险升级合规', tone: 'critical' },
      { level: '准入门', l4_code: 'L4-IBRD-07', label: '负责人保留最终决议', tone: 'critical' },
    ],
    missing_analysis: ['per-L4业务价值数据', 'L4-03/05/06/07/08权威交付物拆分确认'],
  }
  fs.writeFileSync(path.join(outputDir, `${code}.reviewed.json`), `${JSON.stringify(result, null, 2)}\n`)
  return { code, l4: l4Analysis.length, tasks: taskItems.length }
}

fs.mkdirSync(outputDir, { recursive: true })
console.log(JSON.stringify([migrateIri(), migrateIbrd()]))
