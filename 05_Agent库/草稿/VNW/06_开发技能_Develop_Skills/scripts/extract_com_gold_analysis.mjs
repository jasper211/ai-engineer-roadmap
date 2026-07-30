#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'

const agentRoot = path.resolve(import.meta.dirname, '../..')
const htmlPath = path.join(agentRoot, '03_规划项目结构_Plan_Project_Structure/L3流程模型_demo_L3-COM_标准测试版_20260728.html')
const snapshotPath = path.join(agentRoot, '10_部署与运行_Deploy_and_Run/frontend/public/data/model_snapshots/L3-COM.json')
const outputPath = path.join(agentRoot, '07_接入记忆_Integrate_Memory/analysis_packages/L3-COM.reviewed.json')
const html = fs.readFileSync(htmlPath, 'utf8')
const snapshot = JSON.parse(fs.readFileSync(snapshotPath, 'utf8'))

function expressionBetween(name, nextName) {
  const start = html.indexOf(`const ${name}=`)
  const end = html.indexOf(`\nconst ${nextName}=`, start)
  if (start < 0 || end < 0) throw new Error(`找不到 ${name}`)
  const expression = html.slice(start + `const ${name}=`.length, end).trim().replace(/;$/, '')
  return vm.runInNewContext(`(${expression})`)
}

const l4s = expressionBetween('l4s', 'chain')
const deliveryMeta = expressionBetween('deliveryMeta', 'analysisMeta')
const analysisMeta = expressionBetween('analysisMeta', 'collabMeta')
const collabMeta = expressionBetween('collabMeta', 'tasks')
const tasks = expressionBetween('tasks', 'byCode')
const l4ByCode = Object.fromEntries(snapshot.l4s.map(item => [item.l4_code, item]))

function refsFor(code) {
  return [...new Set(Object.values(l4ByCode[code]?.evidence_refs || {}).filter(Boolean))].sort()
}

function splitList(value) {
  return String(value || '').split(/[、；]/).map(item => item.trim()).filter(Boolean)
}

const l4Analysis = l4s.map(row => {
  const code = row[0]
  const suffix = code.slice(-2)
  const delivery = deliveryMeta[suffix]
  const priority = analysisMeta[suffix]
  const collab = collabMeta[suffix]
  return {
    l4_code: code,
    analysis_status: 'MODEL_DRAFT',
    evidence_refs: refsFor(code),
    confidence: 'REVIEWED_SAMPLE',
    database_tier: row[3],
    recommended_tier: row[4],
    deliverable_role: delivery[0],
    specific_capabilities: splitList(delivery[1]),
    ai_reshape: delivery[2],
    quality_anchor: delivery[3],
    ai_responsibility: collab[0],
    human_responsibility: collab[1],
    handoff_triggers: splitList(collab[2]),
    control_gates: splitList(collab[3]),
    owner_scope: collab[4],
    data_basis: [`数据库Tier=${row[3]}`, `复核Tier=${row[4]}`, `D1-D6=${row[5].join('/')}`, `总分=${row[6]}/18`],
    process_context: priority[0],
    risks_limits: splitList(priority[1]),
    current_recommendation: priority[2],
    quadrant: priority[3],
  }
})

const taskItems = tasks.map(task => ({
  task_id: task.id,
  l4_code: task.l4,
  task_name: task.name,
  source_type: task.source,
  evidence_refs: refsFor(task.l4),
  analysis_status: 'MODEL_DRAFT',
  suggested_tier: task.tier,
  tier_rationale: task.why,
}))

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
  ['P0-1', ['16-b', '16-c'], '保司文件字段抽取、标准格式转换与解析质量检查', '先选1家格式稳定的保司和1个季度样本，影子模式比对', '异常字段和低置信结果必须转人工'],
  ['P0-2', ['11-a', '11-b'], '银行回单OCR、应收实收匹配与对账评估', '选择1个结算周期，只生成匹配建议和差异对照', '差异分类和已对平确认由财务完成'],
  ['P0-3', ['01-a', '01-c'], '政策原件版本登记与生效期冲突检测', '对新到政策做旁路登记和冲突提示', '冲突裁定和正式入库由佣金管理与合规岗确认'],
  ['P1-1', ['15-a', '15-b'], '付款回执识别归档与派发台账更新草稿', '在已完成付款的历史批次做影子归档', '正式台账发布由财务确认'],
  ['P1-2', ['07-a'], '争议登记、分类与状态结构化', '只登记新发生争议并建立标准字段', '责任裁定和关闭批准保留人工'],
].map(([priority, taskIds, title, pilotScope, humanBoundary]) => ({
  priority,
  task_ids: taskIds,
  title,
  pilot_scope: pilotScope,
  human_boundary: humanBoundary,
  evidence_refs: [...new Set(taskIds.flatMap(id => taskItems.find(task => task.task_id === id)?.evidence_refs || []))],
  analysis_status: 'MODEL_DRAFT',
}))

const result = {
  schema_version: 'vnw.l3-analysis.v1',
  analysis_standard_id: 'VNW-L3-COM-GOLD-v1.0',
  generation_mode: 'REVIEWED_GOLD_MIGRATION',
  analysis_status: 'REVIEWED',
  model_run: {
    model_name: 'COM多轮人机协作分析',
    model_version: 'reviewed-20260729',
    prompt_version: 'VNW-L3-COM-GOLD-v1.0',
    generated_at: new Date().toISOString(),
    input_snapshot_hash: '',
  },
  source_scope: {
    database: 'process_analytics',
    knowledge: 'ACTIVE supplemental evidence only',
    evidence_count: snapshot.evidence_registry.length,
    migration_source: path.basename(htmlPath),
  },
  l4_analysis: l4Analysis,
  tasks: taskItems,
  priority_drafts: priorities,
  decision_drafts: decisions,
  control_chain: [
    { level: '一级', l4_code: 'L4-COM-11', label: '自动对账 / 差异对照', tone: 'standard' },
    { level: '二级', l4_code: 'L4-COM-13', label: '人工强制签字 · 不得自动放行', tone: 'critical' },
    { level: '三级', l4_code: 'L4-COM-17', label: '合规独立评估', tone: 'standard' },
  ],
  rejected_task_sources: [],
  missing_analysis: [],
}

fs.mkdirSync(path.dirname(outputPath), { recursive: true })
fs.writeFileSync(outputPath, `${JSON.stringify(result, null, 2)}\n`)
console.log(JSON.stringify({ output: outputPath, l4: l4Analysis.length, tasks: taskItems.length, priorities: priorities.length, decisions: decisions.length }))
