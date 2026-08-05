import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router'
import { AlertTriangle, ArrowLeft, ArrowRight, Bot, Download, GitBranch, GripVertical, Info, Layers3, LoaderCircle, RotateCcw, Save, ShieldCheck } from 'lucide-react'
import { loadL3Model, type L3Model } from '../lib/l3Models'

const COLUMNS = [
  { id: 'Human', label: 'Human · 人工主导', explanation: '任务由人完成；AI最多提供资料检索或记录支持，不替代判断与执行。', color: 'border-rose-400/30 bg-rose-400/5' },
  { id: 'Hybrid', label: 'Hybrid · 人机协同', explanation: 'AI与人分段协作；AI处理可标准化部分，人承担判断、审批或异常处置。', color: 'border-amber-400/30 bg-amber-400/5' },
  { id: 'Auto', label: 'Auto · 自动执行', explanation: '规则、输入和校验均稳定时由系统自动完成，并保留监控、回退与审计。', color: 'border-emerald-400/30 bg-emerald-400/5' },
  { id: 'Aug', label: 'Aug · AI增强', explanation: '人仍是任务主体；AI生成草稿、提示风险或加速分析，由人确认结果。', color: 'border-sky-400/30 bg-sky-400/5' },
] as const

const PRIORITY_ZONES = [
  { id: 'q1', label: '优先验证', explanation: '价值明确、输入与规则较稳定、风险可控。适合先做小范围AI原型，用真实任务验证效率与质量。', guide: '先选任务 → 明确人工边界 → 设质量指标 → 小范围试跑', tone: 'border-emerald-200 bg-emerald-50/60' },
  { id: 'q2', label: '治理后推进', explanation: '机会成立，但流程、职责、规则或接口尚不稳定。先完成治理，再进入AI方案验证。', guide: '先定流程/责任/控制门 → 再开发AI', tone: 'border-blue-200 bg-blue-50/60' },
  { id: 'q3', label: '补数据后推进', explanation: '业务场景有价值，但缺少可用输入、历史样本或质量基准，当前无法可靠训练、提示或验收。', guide: '先补数据与质量口径 → 建立样本集 → 再验证AI', tone: 'border-amber-200 bg-amber-50/60' },
  { id: 'q4', label: '暂缓自动化', explanation: '高风险判断、强关系协商、物理执行或投入产出不合理。当前以人工为主，仅优化前后信息流。', guide: '保留人工主导 → 监测条件变化 → 定期复评', tone: 'border-rose-200 bg-rose-50/60' },
] as const

const GATE_INFO = {
  M: { name: 'Modelable · 可建模门', description: '确认是否具备建流程模型的最低事实基础：可解析蓝图、L4交付活动及D1–D6评估。缺少任一硬输入时不生成模型。' },
  E: { name: 'Evidence · 证据充分门', description: '检查交付物、任务、规则、SOP及补充证据的覆盖与可追溯性。规则或SOP不足可条件通过，但必须明确缺口。' },
  A: { name: 'Actionable · 可行动门', description: '确认输出能否支持AI任务拆分、优先级讨论和负责人决策；要求任务可执行、边界清晰且结论可回到证据。' },
} as const

type WorkshopState = {
  placements: Record<string, string>
  priorityPlacements: Record<string, string>
  note: string
  updatedAt: string
  baseSnapshotHash: string
}

function gateTone(status: string) {
  return status === 'PASS' ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-700' : 'border-amber-400/25 bg-amber-400/10 text-amber-700'
}

function tierTone(tier: string) {
  if (tier === 'Auto') return 'border-emerald-200 bg-emerald-100 text-emerald-800'
  if (tier === 'Aug') return 'border-blue-200 bg-blue-100 text-blue-800'
  if (tier === 'Hybrid') return 'border-amber-200 bg-amber-100 text-amber-800'
  if (tier === 'Human') return 'border-rose-200 bg-rose-100 text-rose-800'
  return 'border-slate-200 bg-slate-100 text-slate-600'
}

function tierLabel(tier: string) {
  return COLUMNS.find(column => column.id === tier)?.label || tier || '未评估'
}

function skillTone(grade: string) {
  if (grade.startsWith('A-')) return 'border-emerald-200 bg-emerald-100 text-emerald-800'
  if (grade.startsWith('B-')) return 'border-blue-200 bg-blue-100 text-blue-800'
  if (grade.startsWith('C-')) return 'border-amber-200 bg-amber-100 text-amber-800'
  if (grade.startsWith('F-')) return 'border-rose-200 bg-rose-100 text-rose-800'
  return 'border-slate-200 bg-slate-100 text-slate-600'
}

function shortSkillGrade(grade: string) {
  if (!grade) return '封装待评估'
  return grade.split('(')[0].trim()
}

function roleTone(role: string) {
  if (role.startsWith('价值')) return 'border-blue-200 bg-blue-50/70'
  if (role.startsWith('控制')) return 'border-rose-200 bg-rose-50/70'
  if (role.startsWith('支撑')) return 'border-amber-200 bg-amber-50/70'
  return 'border-border-default bg-bg-surface'
}

function readableList(value: unknown) {
  if (!Array.isArray(value) || value.length === 0) return '待补'
  const texts = value.map(item => {
    if (typeof item === 'string' || typeof item === 'number') return String(item)
    if (!item || typeof item !== 'object') return ''
    const record = item as Record<string, unknown>
    const label = record.description || record.label || record.name || record.title || record.condition
    const id = record.decision_id || record.gate_id || record.id
    if (label && id) return `${String(id)} · ${String(label)}`
    if (label) return String(label)
    return ''
  }).filter(Boolean)
  return texts.length ? texts.join('；') : '待补'
}

function PanelMeta({ ssot, logic }: { ssot: string; logic?: string }) {
  return (
    <details className="max-w-md text-right">
      <summary className="cursor-pointer text-[10px] font-medium text-indigo-700">SSOT来源与分析逻辑</summary>
      <div className="mt-2 rounded-lg border border-indigo-100 bg-indigo-50/90 p-3 text-left text-[10px] leading-4 text-text-secondary shadow-sm">
        <p><b>SSOT：</b>{ssot}</p>
        {logic && <p className="mt-1"><b>分析逻辑：</b>{logic}</p>}
      </div>
    </details>
  )
}

function sourceContribution(sourceObject: string, fields: string[]) {
  if (sourceObject === 'process_analytics.dim_process') {
    return {
      thinking: '以数据库正式L4定义为结构主轴，区分活动名称、交付物、交付物类型、既有AI协作Tier与人工触点。',
      input: '决定模型中的L4范围，并进入Gate M/E、面板B、C、D、E。',
    }
  }
  if (sourceObject === 'process_analytics.dim_vn') {
    return {
      thinking: '流程模型最终需要服务真实价值节点，并保留优先级、融合状态和可追溯性判断。',
      input: '进入Gate A、流程背景、价值节点映射和负责人决策语境。',
    }
  }
  if (sourceObject.includes('L4两阶段复核')) {
    return {
      thinking: '从“是否能自动化”进一步拆成输入结构、规则清晰、输出验证、接口可达、失败降级和合规约束六个判断维度。',
      input: '为Gate M/E、面板B的人机边界、面板D的风险与推进条件提供D1–D6事实输入。',
    }
  }
  if (sourceObject.includes('Skill封装可行性评估')) {
    return {
      thinking: 'AI机会不能只看Tier，还要判断动作是信息处理还是认知决策、单一还是复合，以及是否存在资金安全或物理执行硬门槛。',
      input: '为面板C的任务拆分、面板D的治理路径、面板E的A/B/C/F封装方式和Skill/Agent设计建议提供输入。',
    }
  }
  if (sourceObject.toLowerCase().includes('sop')) {
    return {
      thinking: '将流程目标下沉为可执行步骤、人工确认点、异常返回和质量检查。',
      input: '为面板A流程补充、面板B控制门和面板C任务卡提供执行层输入。',
    }
  }
  if (sourceObject.includes('流程蓝图_')) {
    return {
      thinking: '使用真实步骤、先后关系、判断点、返回路径、RACI与价值节点背景还原流程，不由模型补画。',
      input: '直接形成面板A，并为面板B控制点、面板C任务拆分、面板D流程背景提供输入。',
    }
  }
  if (sourceObject.includes('T5_规则清单')) {
    return {
      thinking: '把现行规则动作、判断标准和适用节点作为持续治理中的约束输入，而不是人机协作规则本身。',
      input: '用于Gate E证据覆盖、任务拆分、控制门和风险限制；缺规则不阻断建模，但明确标注缺口。',
    }
  }
  if (sourceObject.includes('T19_SOP生产进度')) {
    return {
      thinking: '确认哪些节点已经有可定位的执行材料，避免仅凭L4名称推测日常任务。',
      input: '用于Gate E及面板C任务证据；具体SOP正文只在已经定位到真实文件时使用。',
    }
  }
  return {
    thinking: `从该文件提取${fields.join('、') || '可追溯知识'}，作为数据库事实之外的补充视角。`,
    input: '仅进入其证据能够支持的分析字段；未覆盖部分保持待补。',
  }
}

function compactRanges(values: number[]) {
  const sorted = [...new Set(values)].sort((a, b) => a - b)
  const ranges: string[] = []
  let start = sorted[0]
  let previous = sorted[0]
  for (const value of sorted.slice(1)) {
    if (value === previous + 1) {
      previous = value
      continue
    }
    ranges.push(start === previous ? `${start}` : `${start}–${previous}`)
    start = value
    previous = value
  }
  if (start !== undefined) ranges.push(start === previous ? `${start}` : `${start}–${previous}`)
  return ranges.join('、')
}

function sourceLocation(sourceSystem: string, keys: string[], indexed?: { rows?: number[]; lines?: number[]; record_keys?: string[] }) {
  if (indexed?.rows?.length) return `使用行：${compactRanges(indexed.rows)}（命中${new Set(indexed.rows).size}行）`
  if (indexed?.lines?.length) return `使用正文行：${compactRanges(indexed.lines)}（命中${new Set(indexed.lines).size}处）`
  if (indexed?.record_keys?.length) return `数据库记录键：${indexed.record_keys.slice(0, 4).join('、')}${indexed.record_keys.length > 4 ? ` 等${indexed.record_keys.length}条` : ''}`
  const rows = keys.flatMap(key => {
    const match = key.match(/@row:(\d+)/)
    return match ? [Number(match[1])] : []
  })
  const lines = keys.flatMap(key => {
    const match = key.match(/line:(\d+)/)
    return match ? [Number(match[1])] : []
  })
  if (rows.length) return `使用行：${compactRanges(rows)}（命中${new Set(rows).size}行）`
  if (lines.length) return `使用正文行：${compactRanges(lines)}（命中${new Set(lines).size}处）`
  const cleanKeys = [...new Set(keys)].filter(Boolean)
  if (sourceSystem === 'PostgreSQL') return `数据库记录键：${cleanKeys.slice(0, 4).join('、')}${cleanKeys.length > 4 ? ` 等${cleanKeys.length}条` : ''}`
  return `源记录：${cleanKeys.slice(0, 4).join('、')}${cleanKeys.length > 4 ? ` 等${cleanKeys.length}条` : ''}`
}

function deliverableQuality(rawDeliverable: string, sameValueCount: number) {
  const governanceLanguage = /P[01]\s*[:：]|系统\s*bug|根因|未纳入流程库|当前无标准|待建设|纯手工|批次\d+|新增[:：]/
  if (rawDeliverable.length > 80 || governanceLanguage.test(rawDeliverable)) {
    return {
      level: 'MIXED_CONTENT',
      label: '源数据待治理 · 交付物混入问题或治理说明',
      reason: '该字段不只包含交付物，还包含现状、问题、人员或待补规则。',
    }
  }
  if (rawDeliverable && sameValueCount >= 3) {
    return {
      level: 'REPEATED_VALUE',
      label: `源数据待核实 · 同一交付物在 ${sameValueCount} 个 L4 中复用`,
      reason: '重复可能是标准化共用交付物，也可能是源表批量填充；系统不自动判错。',
    }
  }
  return null
}

function buildMarkdownReport(model: L3Model): string {
  const ua = model.unified_analysis
  const lines: string[] = []
  lines.push(`# ${model.l3_code} · ${model.l3_name} · VNW统一分析报告`)
  lines.push('')
  lines.push(`> 状态：**${ua.status === 'CONFIRMED' ? `已确认（${ua.confirmed_by ?? ''} · ${ua.confirmed_at ?? ''}）` : '草稿 · 尚未人工确认，不可作为最终投入决策依据'}**`)
  lines.push(`> 依据：VNW统一分析Spec v1.0 · 快照 ${model.snapshot_hash.slice(0, 12)} · Gate M/E/A = ${model.gates.M.status}/${model.gates.E.status}/${model.gates.A.status}`)
  lines.push('')
  lines.push('## 一、分析基线')
  lines.push(`- 数据快照：\`${model.snapshot_hash}\``)
  lines.push(`- 蓝图版本：${model.blueprint.version || '未覆盖'}`)
  lines.push(`- L4总数：${model.l4s.length} · 价值节点：${model.value_nodes.length}`)
  lines.push('')
  lines.push('## 二、受控维度')
  lines.push(`- L2业务能力：${model.l2_capabilities.length > 0 ? model.l2_capabilities.map(row => String((row as Record<string, unknown>).l2_name ?? '')).join('、') : '待补'}`)
  lines.push(`- 价值流位置：${model.value_stream_mappings.length > 0 ? model.value_stream_mappings.map(row => { const r = row as Record<string, unknown>; return `${r.vs_name}·${r.stage_name}` }).join('、') : '未定位到客户旅程/价值流阶段'}`)
  lines.push(`- 关联KPI：${model.kpi_mappings.length > 0 ? model.kpi_mappings.map(kpi => `${kpi.kpi_name}${kpi.source_type === 'mark_priority_draft' ? '(战略权重草稿)' : ''}`).join('、') : '待补'}`)
  lines.push(`- 岗位归属：${ua.coverage.position_covered}/${ua.coverage.l4_total} 个L4已归口`)
  lines.push(`- 业务数据证据：${ua.coverage.business_evidence_covered}/${ua.coverage.l4_total} 个L4定位到业务数据仓库表`)
  lines.push('')
  lines.push('## 三、双轴声明（D1-D6/Tier轴 与 候选Agent封装轴，禁止合并）')
  if (ua.axis_conflicts.length > 0) {
    lines.push(`⚠️ 两轴方向冲突：${ua.axis_conflicts.join('、')} —— 需业务方澄清，本报告不自动选边。`)
  } else {
    lines.push('本L3当前两轴方向一致，无冲突。')
  }
  lines.push('')
  lines.push('## 四、逐L4根因阶梯（事实→机制→结构→策略）')
  for (const l4 of model.l4s) {
    const ladder = ua.root_cause_ladders[l4.l4_code]
    lines.push(`### ${l4.l4_code} · ${l4.l4_name}`)
    if (ladder) {
      for (const layer of ladder) {
        lines.push(`- **[${layer.layer}·${layer.grade}级]** ${layer.statement}`)
      }
    } else {
      lines.push('- 待补')
    }
    lines.push('')
  }
  lines.push('## 五、Definition of Done')
  for (const item of ua.dod_checklist) {
    lines.push(`- [${item.satisfied ? 'x' : ' '}] ${item.item}`)
  }
  lines.push('')
  lines.push('## 六、综合判断')
  lines.push(ua.status === 'DRAFT'
    ? '本报告为VNW自动生成的草稿，仅供参考，须经Jasper/L3业务负责人复核并写入决策确认记录后才可作为最终投入依据。'
    : `本报告已由${ua.confirmed_by ?? '业务负责人'}于${ua.confirmed_at ?? ''}确认。${ua.confirmation_notes ?? ''}`)
  lines.push('')
  lines.push('---')
  lines.push(`来源：03_规划项目结构_Plan_Project_Structure/VNW统一分析Spec_v1.0.md`)
  return lines.join('\n')
}

function downloadMarkdown(model: L3Model) {
  const content = buildMarkdownReport(model)
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${model.l3_code}_统一分析报告.md`
  link.click()
  URL.revokeObjectURL(url)
}

export default function L3ModelDetail({ modelCode }: { modelCode?: string } = {}) {
  const params = useParams()
  const l3Code = modelCode || params.l3Code || ''
  const [model, setModel] = useState<L3Model | null>(null)
  const [error, setError] = useState('')
  const storageKey = `vnw-workshop-v1:${l3Code}`
  const [session, setSession] = useState<WorkshopState>({ placements: {}, priorityPlacements: {}, note: '', updatedAt: '', baseSnapshotHash: '' })
  const [taskL4Filter, setTaskL4Filter] = useState('ALL')

  useEffect(() => {
    loadL3Model(l3Code).then(setModel).catch(error => setError(error.message))
    const saved = localStorage.getItem(storageKey)
    if (saved) {
      try {
        const parsed = JSON.parse(saved)
        setSession({ placements: {}, priorityPlacements: {}, note: '', updatedAt: '', baseSnapshotHash: '', ...parsed })
      } catch { localStorage.removeItem(storageKey) }
    }
  }, [l3Code, storageKey])

  const cards = useMemo(() => {
    if (!model) return []
    const analyzedTasks = model.analysis.tasks.filter(task => COLUMNS.some(column => column.id === task.suggested_tier))
    const ordinalByL4: Record<string, number> = {}
    const base = analyzedTasks.length > 0
      ? analyzedTasks.map(task => {
          ordinalByL4[task.l4_code] = (ordinalByL4[task.l4_code] || 0) + 1
          const matchedStep = model.blueprint.steps.find(step =>
            step.l4_codes.includes(task.l4_code)
            && Boolean(step.evidence_ref)
            && task.evidence_refs.includes(step.evidence_ref || '')
          )
          const sequenceStatus = task.sequence_status
            || (matchedStep ? 'SOURCE_STEP_ONLY' : 'UNCONFIRMED')
          return {
            card_id: task.task_id,
            displayTaskCode: `${task.l4_code.replace(/^L4-/, 'L3-')}-${String(ordinalByL4[task.l4_code]).padStart(2, '0')}`,
            l4_code: task.l4_code,
            deliverable: task.task_name,
            l4_name: task.tier_rationale,
            tier: task.suggested_tier,
            source_type: task.source_type,
            sequenceNo: task.sequence_no ?? matchedStep?.sequence ?? null,
            sequenceStatus,
            sourceStepId: task.source_step_id || matchedStep?.step_id || '',
            sourceLine: task.source_line ?? matchedStep?.source_line ?? null,
            previousTaskIds: task.previous_task_ids || [],
            nextTaskIds: task.next_task_ids || [],
            relationType: task.relation_type || 'UNCONFIRMED',
          }
        })
      : model.analysis.analysis_status === 'PENDING_MODEL'
        ? model.l4s.map(l4 => ({
            ...l4,
            card_id: l4.l4_code,
            displayTaskCode: `${l4.l4_code.replace(/^L4-/, 'L3-')}-01`,
            source_type: 'DATABASE_L4',
            sequenceNo: null,
            sequenceStatus: 'UNCONFIRMED' as const,
            sourceStepId: '',
            sourceLine: null,
            previousTaskIds: [],
            nextTaskIds: [],
            relationType: 'UNCONFIRMED',
          }))
        : []
    return base.map(card => ({
      ...card,
      placement: session.placements[card.card_id] || card.tier,
      changed: Boolean(session.placements[card.card_id] && session.placements[card.card_id] !== card.tier),
    }))
  }, [model, session.placements])
  const mappedL4s = useMemo(() => new Set(
    model?.vn_l4_mappings.map(row => String(row.l4_code || '')) ?? []
  ), [model])
  const positionCategory = useMemo(() => {
    if (!model) return null
    return model.l4s.find(l4 => l4.position_family)?.position_family ?? null
  }, [model])
  const businessDataSummary = useMemo(() => {
    if (!model) return null
    const matched = model.l4s.filter(l4 => l4.business_evidence.length > 0)
    if (matched.length === 0) return null
    return { matched: matched.length, total: model.l4s.length }
  }, [model])
  const taskL4Options = useMemo(() => [...new Set(cards.map(card => card.l4_code))].sort(), [cards])
  const visibleCards = useMemo(
    () => taskL4Filter === 'ALL' ? cards : cards.filter(card => card.l4_code === taskL4Filter),
    [cards, taskL4Filter],
  )
  const priorityDrafts = useMemo(() => {
    if (!model) return []
    return model.analysis.priority_drafts.map((item, index) => {
      const l4Code = String(item.l4_code || `priority-${index}`)
      const initial = ['q1', 'q2', 'q3', 'q4'].includes(String(item.quadrant)) ? String(item.quadrant) : 'unclassified'
      const placement = session.priorityPlacements[l4Code] || initial
      return {
        l4Code,
        l4Name: model.l4s.find(l4 => l4.l4_code === l4Code)?.l4_name || '中文名称待补',
        initial,
        placement,
        changed: placement !== initial,
        current_recommendation: String(item.current_recommendation || ''),
        process_context: String(item.process_context || ''),
        risks_limits: Array.isArray(item.risks_limits) ? item.risks_limits : [],
        data_basis: Array.isArray(item.data_basis) ? item.data_basis : [],
      }
    })
  }, [model, session.priorityPlacements])
  const inputLineage = useMemo(() => {
    if (!model) return []
    const groups = new Map<string, { sourceObject: string; sourceSystem: string; sourceVersion: string; fields: Set<string>; keys: Set<string>; evidenceCount: number }>()
    model.evidence_registry.forEach(item => {
      const source = item.source as Record<string, unknown> | undefined
      const sourceSystem = String(source?.source_system || '')
      const sourceObject = String(source?.source_object || '')
      if (!sourceObject) return
      const groupKey = `${sourceSystem}::${sourceObject}`
      const current = groups.get(groupKey) || {
        sourceObject,
        sourceSystem,
        sourceVersion: String(source?.source_version || ''),
        fields: new Set<string>(),
        keys: new Set<string>(),
        evidenceCount: 0,
      }
      current.fields.add(String(item.field_name || ''))
      current.keys.add(String(source?.source_key || ''))
      current.evidenceCount += 1
      groups.set(groupKey, current)
    })
    return [...groups.values()].map(group => {
      const fields = [...group.fields].filter(Boolean)
      const keys = [...group.keys].filter(Boolean)
      return {
        ...group,
        fields,
        keys,
        location: sourceLocation(group.sourceSystem, keys, model.source_locations?.[group.sourceObject]),
        ...sourceContribution(group.sourceObject, fields),
      }
    })
  }, [model])
  function moveCard(cardId: string, placement: string) {
    setSession(current => ({ ...current, placements: { ...current.placements, [cardId]: placement } }))
  }

  function movePriority(l4Code: string, placement: string) {
    if (!l4Code) return
    setSession(current => ({ ...current, priorityPlacements: { ...current.priorityPlacements, [l4Code]: placement } }))
  }

  function persist() {
    const next = { ...session, updatedAt: new Date().toISOString(), baseSnapshotHash: model?.snapshot_hash || '' }
    localStorage.setItem(storageKey, JSON.stringify(next))
    setSession(next)
  }

  function reset() {
    localStorage.removeItem(storageKey)
    setSession({ placements: {}, priorityPlacements: {}, note: '', updatedAt: '', baseSnapshotHash: '' })
  }

  if (error) return <div className="panel p-5 text-sm text-accent-danger">{error}</div>
  if (!model) return <div className="flex min-h-64 items-center justify-center text-text-muted"><LoaderCircle className="mr-2 h-5 w-5 animate-spin" />正在读取模型证据</div>
  if (!model.model_readiness.model_generation_allowed) {
    const gaps = (['M', 'E'] as const).flatMap(gate =>
      model.gates[gate].checks.filter(check => !check.passed).map(check => check.detail)
    )
    return (
      <div className="space-y-6">
        <Link to="/models" className="inline-flex items-center gap-2 text-xs text-text-muted hover:text-text-primary"><ArrowLeft className="h-4 w-4" />返回模型清单</Link>
        <section className="rounded-2xl border border-amber-300 bg-amber-50 p-6">
          <p className="font-mono text-xs text-amber-700">{model.l3_code}</p>
          <h1 className="mt-1 font-heading text-2xl font-bold">{model.l3_name}</h1>
          <div className="mt-4 flex items-center gap-2 text-amber-800"><AlertTriangle className="h-5 w-5" /><strong>待补后生成 · 当前不产出流程模型和AI分析</strong></div>
          <p className="mt-2 text-sm leading-6 text-text-secondary">基础结构或任务证据尚未达到最低准入门槛。系统只展示补建事项，不使用模板或模型推测填充。</p>
        </section>
        <section className="panel p-5">
          <h2 className="text-sm font-semibold">需要补充的输入</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {gaps.map((gap, index) => <div key={`${gap}-${index}`} className="rounded-xl border border-amber-200 bg-amber-50/60 p-3 text-sm text-amber-900">{gap}</div>)}
          </div>
          <p className="mt-4 text-xs text-text-muted">
            当前已定位：SOP {model.model_readiness.coverage.sop_count}份 · 规则 {model.model_readiness.coverage.rule_count}条 ·
            交付物 {model.model_readiness.coverage.deliverable.covered}/{model.model_readiness.coverage.deliverable.total} ·
            可追溯任务 {model.model_readiness.coverage.task.covered}/{model.model_readiness.coverage.task.total}
          </p>
        </section>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Link to="/models" className="inline-flex items-center gap-2 text-xs text-text-muted hover:text-text-primary"><ArrowLeft className="h-4 w-4" />返回模型清单</Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs text-accent-primary-light">{model.l3_code}</p>
          <h1 className="mt-1 font-heading text-3xl font-bold">{model.l3_name}</h1>
          <p className="mt-2 text-sm text-text-secondary">{model.l4s.length} 个 L4 交付活动 · {model.value_nodes.length} 个价值节点 · 蓝图 {model.blueprint.version || '未覆盖'}</p>
          {model.value_stream_mappings.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {model.value_stream_mappings.map((vs, index) => (
                <span key={index} className="rounded-full bg-teal-400/10 px-2.5 py-1 text-[11px] font-medium text-teal-700">
                  {String(vs.vs_code)} · {String(vs.vs_name)} · {String(vs.stage_code)} · 第{String(vs.stage_sequence ?? '?')}阶段 {String(vs.stage_name)}
                </span>
              ))}
            </div>
          ) : (
            <p className="mt-2 text-[11px] text-text-muted">当前未定位到客户旅程/价值流阶段（数据库bridge_l3_vs_stage未覆盖该L3）</p>
          )}
          {model.kpi_mappings.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {model.kpi_mappings.map(kpi => (
                kpi.source_type === 'definition' ? (
                  <span key={kpi.kpi_code} className="rounded-full bg-amber-400/10 px-2.5 py-1 text-[11px] font-medium text-amber-800" title={kpi.kpi_formula ?? undefined}>
                    {kpi.kpi_name}{kpi.measurement_cycle ? `·${kpi.measurement_cycle}度` : ''}
                  </span>
                ) : (
                  <span key={kpi.kpi_code} className="rounded-full border border-dashed border-rose-300 bg-rose-50 px-2.5 py-1 text-[11px] font-medium text-rose-700">
                    {kpi.kpi_name}·战略权重{kpi.contribution_weight ?? '?'}·{kpi.weight_confirmed === 'blocked' ? '阻塞' : '待确认'}
                  </span>
                )
              ))}
            </div>
          ) : (
            <p className="mt-2 text-[11px] text-text-muted">当前未关联KPI（数据库dim_kpi/bridge_kpi_l3未覆盖该L3）</p>
          )}
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="flex gap-2">
            {(['M', 'E', 'A'] as const).map(gate => <span key={gate} className={`rounded-lg border px-3 py-2 font-mono text-xs ${gateTone(model.gates[gate].status)}`}>Gate {gate} · {model.gates[gate].status}</span>)}
          </div>
          <button
            onClick={() => downloadMarkdown(model)}
            className="flex items-center gap-1.5 rounded-lg border border-border-default bg-bg-surface px-3 py-2 text-xs text-text-secondary hover:bg-bg-elevated"
          >
            <Download className="h-3.5 w-3.5" /> 导出统一分析报告（.md）
          </button>
        </div>
      </div>

      {model.analysis_freshness === 'INPUT_CHANGED' && (
        <section className="rounded-2xl border border-rose-300 bg-rose-50 p-4">
          <p className="text-sm font-semibold text-rose-800">源头输入已变化 · 旧分析不再是当前结论</p>
          <p className="mt-1 text-xs leading-5 text-rose-700">事实层和面板F已更新；涉及模型推导的内容只作为过期参考，必须基于新快照重跑统一分析后才能恢复为当前草稿。</p>
        </section>
      )}

      <section className="rounded-2xl border border-indigo-200 bg-indigo-50/60 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold text-indigo-700">统一分析标准 · {model.analysis.analysis_standard_id}</p>
            <p className="mt-1 text-xs leading-5 text-text-secondary">
              当前事实包已从同一数据库与知识输入链生成，提取出 {model.analysis.tasks.length} 条可追溯蓝图任务。
              {model.analysis.analysis_status === 'PENDING_MODEL'
                ? '模型分析尚未执行，以下页面只展示事实层，不会自动补造COM式结论。'
                : model.analysis.analysis_status === 'REVIEWED'
                  ? '已形成人工复核基线，页面结论仍保留证据引用和版本边界。'
                  : '模型分析草稿已生成，页面中的推导内容必须保留证据引用。'}
            </p>
          </div>
          <span className={`rounded-full px-3 py-1.5 text-xs font-medium ${model.analysis.analysis_status === 'PENDING_MODEL' ? 'bg-amber-100 text-amber-800' : model.analysis.analysis_status === 'REVIEWED' ? 'bg-emerald-100 text-emerald-800' : 'bg-violet-100 text-violet-800'}`}>
            {model.analysis.analysis_status === 'PENDING_MODEL' ? '待运行统一模型' : model.analysis.analysis_status === 'REVIEWED' ? '人工复核基线' : '模型分析草稿'}
          </span>
        </div>
        {model.analysis.missing_analysis.length > 0 && (
          <p className="mt-2 text-[11px] text-text-muted">尚待生成：{model.analysis.missing_analysis.join('、')}</p>
        )}
      </section>

      <section className="panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-accent-primary-light" /><h2 className="text-sm font-semibold">为什么处于这个 Gate</h2></div>
          <PanelMeta ssot="数据库L3/L4、D1–D6、流程蓝图、SOP与规则覆盖快照。" logic="Gate由确定性程序规则计算，不由大模型自由判断；M控制能否建模，E说明证据充分度，A说明是否可支持行动决策。" />
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {(['M', 'E', 'A'] as const).map(gate => (
            <div key={gate} className="rounded-xl border border-border-default bg-bg-surface p-4">
              <p className="font-mono text-xs font-semibold text-text-primary">Gate {gate} · {GATE_INFO[gate].name}</p>
              <p className="mt-2 text-[11px] leading-5 text-text-muted">{GATE_INFO[gate].description}</p>
              <p className={`mt-3 inline-block rounded-full border px-2 py-1 text-[10px] ${gateTone(model.gates[gate].status)}`}>当前：{model.gates[gate].status}</p>
              <div className="mt-2 space-y-2">
                {model.gates[gate].checks.map(check => (
                  <div key={check.rule_id} className="flex gap-2 text-xs">
                    <span className={check.passed ? 'text-emerald-700' : 'text-amber-700'}>{check.passed ? '✓' : '!'}</span>
                    <span className="text-text-secondary">{check.detail}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-default pb-3">
          <div className="flex items-center gap-2"><GitBranch className="h-4 w-4 text-accent-primary-light" /><h2 className="text-sm font-semibold">面板 A · L3流程叙事（理想态执行路径）</h2></div>
          <PanelMeta ssot={`${model.blueprint.filename || '流程蓝图待补'}；正文解析为${model.blueprint.steps.length}步、${model.blueprint.decisions.length}个判断点。`} logic="仅按蓝图中显式步骤、箭头、判断和返回关系绘制；大模型不得补造流程节点。" />
        </div>
        {model.blueprint.structure_status === 'PARSED' ? (
          <>
            <div className="mt-4 overflow-x-auto pb-3">
              <div className="flex min-w-max items-stretch gap-2">
                {model.blueprint.steps.map((step, index) => {
                const highlighted = step.l4_codes.some(code => mappedL4s.has(code))
                return (
                  <div key={step.step_id} className="flex items-center gap-2">
                    <div className={`w-48 shrink-0 rounded-xl border p-3 ${highlighted ? 'border-violet-300 bg-violet-50' : 'border-slate-200 bg-white'}`}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-[10px] text-accent-primary">{step.l4_codes.join(' / ') || `步骤${step.sequence}`}</span>
                        <span className="text-[9px] text-text-muted">#{step.sequence}</span>
                      </div>
                      <p className="mt-2 text-sm font-semibold leading-5 text-text-primary">{step.step_name}</p>
                      {step.activities[0] && <p className="mt-2 line-clamp-3 text-[11px] leading-4 text-text-secondary">{step.activities[0]}</p>}
                      <p className="mt-2 text-[9px] text-text-muted">蓝图第 {step.source_line} 行</p>
                    </div>
                    {index < model.blueprint.steps.length - 1 && <ArrowRight className="h-5 w-5 shrink-0 text-slate-500" />}
                  </div>
                )
              })}
              </div>
            </div>
            {model.blueprint.decisions.length === 0 ? (
              <div className="mt-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-800">蓝图没有显式判断菱形，因此不增加决策点或回退线；支链和控制点不能擅自改画成主链判断。</div>
            ) : (
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {model.blueprint.decisions.map(decision => (
                  <div key={decision.decision_id} className="rounded-xl border border-amber-300 bg-amber-50 p-4">
                    <p className="text-center text-sm font-semibold text-amber-900">◇ {decision.question}？</p>
                    <div className="mt-3 space-y-2">{decision.branches.map((branch, index) => <p key={index} className={`rounded-lg border bg-white px-3 py-2 text-xs ${branch.is_return ? 'border-rose-200 text-rose-800' : 'border-amber-100 text-text-secondary'}`}><b>{branch.label}</b> → {branch.target_text}</p>)}</div>
                  </div>
                ))}
              </div>
            )}
            {Boolean(model.analysis.control_chain?.some(item => Boolean(item?.l4_code && item?.label))) && (
              <div className="mt-4">
                <div className="flex flex-wrap items-center justify-center gap-2">
                  {model.analysis.control_chain?.filter(item => Boolean(item?.l4_code && item?.label)).map((item, index, controls) => <div key={item.l4_code} className="flex items-center gap-2">
                    <div className={`rounded-xl border px-4 py-3 ${item.tone === 'critical' ? 'border-rose-300 bg-rose-50' : 'border-slate-200 bg-white'}`}>
                      <p className="text-xs font-bold text-text-primary">{item.level || '控制点'} · {String(item.l4_code).replace('L4-', '')}</p>
                      <p className="mt-1 text-xs text-text-secondary">{item.label}</p>
                    </div>
                    {index < controls.length - 1 && <ArrowRight className="h-4 w-4 text-slate-500" />}
                  </div>)}
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="mt-4 rounded-xl border border-amber-400/25 bg-amber-400/5 p-4">
            <p className="text-sm font-medium text-amber-800">当前不生成流程图：{model.blueprint.structure_status}</p>
            <p className="mt-1 text-xs leading-5 text-text-secondary">{model.blueprint.note}</p>
            {Boolean(model.blueprint.diagnostics?.missing_in_blueprint?.length) && (
              <p className="mt-2 text-xs text-text-muted">数据库存在但蓝图未覆盖：{model.blueprint.diagnostics.missing_in_blueprint?.join('、')}</p>
            )}
          </div>
        )}
      </section>

      <section className="panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-2"><Layers3 className="h-4 w-4 text-accent-primary-light" /><h2 className="text-sm font-semibold">面板 E · L4交付物地图</h2></div>
          <PanelMeta ssot="数据库L4、交付物、Tier、L2能力、价值节点映射；OB知识库Skill封装评估。" logic="大模型只在有效证据上分析交付物角色、具体能力、AI重塑方式和质量锚点；数据库Tier与模型建议并列保留。" />
        </div>
        <p className="mt-2 text-xs text-text-muted">围绕 L3 目标查看交付物、数据库 Tier 和人工介入点。当前蓝图为 {model.blueprint.structure_status}，因此不展示未经正文解析的流程箭头。</p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {COLUMNS.map(column => (
            <div key={column.id} className={`rounded-lg border p-3 ${column.color}`}>
              <p className="text-xs font-semibold text-text-primary">{column.label}</p>
              <p className="mt-1 text-[10px] leading-4 text-text-secondary">{column.explanation}</p>
            </div>
          ))}
        </div>
        <div className="mt-3 rounded-lg border border-cyan-200 bg-cyan-50/70 p-3">
          <p className="text-[11px] font-semibold text-cyan-800">人力现状参考 · 当前负责岗位</p>
          {positionCategory ? (
            <p className="mt-1 text-[11px] leading-5 text-text-secondary">
              本L3当前由 <b>{positionCategory.category_name}</b>（{positionCategory.family_name}，{positionCategory.family_code}，{positionCategory.category_type}）负责，下辖全部L4共享同一岗位归属。
            </p>
          ) : (
            <p className="mt-1 text-[11px] text-text-muted">本L3未在68L3岗位族归属设计v6.1中找到岗位归属（可能是外包/新增L3，待归口）。</p>
          )}
          <p className="mt-2 text-[9px] text-text-muted">SSOT：2026-07-20_68L3岗位族归属设计_v6.1_SUBMITTED.md（三/四节各族详细映射）</p>
        </div>
        {businessDataSummary && (
          <Link to={`/business-data?l3=${model.l3_code}`} className="mt-3 flex items-center justify-between gap-2 rounded-lg border border-emerald-200 bg-emerald-50/70 p-3 text-[11px] text-emerald-800 hover:bg-emerald-50">
            <span>业务数据分析：{businessDataSummary.matched}/{businessDataSummary.total} 个L4已定位到业务数据仓库表 · 查看完整分析 →</span>
          </Link>
        )}
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {model.l4s.map(l4 => {
            const analysis = model.analysis.l4_analysis.find(item => String(item.l4_code) === l4.l4_code) as Record<string, unknown> | undefined
            const displayTier = String(analysis?.recommended_tier || l4.tier || '')
            const rawDeliverable = String(l4.deliverable || '')
            const sameValueCount = model.l4s.filter(item => String(item.deliverable || '') === rawDeliverable).length
            const deliverableIssue = deliverableQuality(rawDeliverable, sameValueCount)
            const proposedDeliverable = String(analysis?.proposed_deliverable || '')
            return (
            <div key={l4.l4_code} className={`rounded-xl border p-4 ${roleTone(String(analysis?.deliverable_role || ''))}`}>
              <div className="flex items-center justify-between gap-3"><span className="font-mono text-[11px] text-accent-primary-light">{l4.l4_code}</span><span className={`rounded-md border px-2 py-1 text-[10px] font-semibold ${tierTone(displayTier)}`}>{tierLabel(displayTier)}</span></div>
              <p className="mt-2 text-sm font-bold text-text-primary">{l4.l4_name}</p>
              {l4.skill_feasibility && (
                <div className="mt-3 rounded-lg border border-slate-200 bg-white/80 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded-md border px-2 py-1 text-[10px] font-semibold ${skillTone(l4.skill_feasibility.grade)}`}>{shortSkillGrade(l4.skill_feasibility.grade)}</span>
                    <span className="rounded-md bg-slate-100 px-2 py-1 text-[10px] text-slate-700">{l4.skill_feasibility.action_nature}</span>
                    <span className="rounded-md bg-slate-100 px-2 py-1 text-[10px] text-slate-700">{l4.skill_feasibility.action_singularity}</span>
                    {l4.skill_feasibility.verification_status === 'PROVISIONAL' && <span className="rounded-md border border-violet-200 bg-violet-50 px-2 py-1 text-[10px] text-violet-700">待书面佐证</span>}
                  </div>
                  <p className="mt-2 text-[11px] leading-5 text-text-secondary"><b>封装判断：</b>{l4.skill_feasibility.judgment_basis}</p>
                  <p className="mt-1 text-[11px] font-medium leading-5 text-indigo-700"><b>基于数据库Tier的设计路径：</b>{l4.skill_feasibility.recommended_path}</p>
                  {(l4.skill_feasibility.funds_safety_hard_gate || l4.skill_feasibility.physical_execution) && (
                    <p className="mt-2 text-[10px] font-medium text-rose-700">
                      {l4.skill_feasibility.funds_safety_hard_gate ? '资金安全：必须保留人工确认关卡。' : ''}
                      {l4.skill_feasibility.physical_execution ? ' 物理执行：只优化前后信息流。' : ''}
                    </p>
                  )}
                </div>
              )}
              {deliverableIssue ? (
                <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-[10px] font-semibold text-amber-800">{deliverableIssue.label}</span>
                    <span className="font-mono text-[9px] text-amber-700">{String(l4.evidence_refs.l4_deliverable || '')}</span>
                  </div>
                  <p className="mt-1 text-[10px] leading-4 text-amber-800">{deliverableIssue.reason}</p>
                  {proposedDeliverable && <p className="mt-2 text-xs font-medium text-text-primary"><b>模型拆分草稿：</b>{proposedDeliverable}</p>}
                  {proposedDeliverable && <p className="mt-1 text-[10px] text-amber-800">仅供业务确认，尚未回写数据库。</p>}
                  <details className="mt-2">
                    <summary className="cursor-pointer text-[10px] text-amber-800">展开数据库原文</summary>
                    <p className="mt-2 break-words text-[10px] leading-4 text-text-secondary">{rawDeliverable}</p>
                  </details>
                </div>
              ) : (
                <p className="mt-2 text-xs text-text-secondary"><b>权威交付物：</b>{rawDeliverable || '待补'}</p>
              )}
              {Boolean(analysis?.deliverable_role) && <span className="mt-3 inline-block rounded-full bg-indigo-50 px-2.5 py-1 text-[10px] font-medium text-indigo-700">{String(analysis?.deliverable_role)}</span>}
              {Array.isArray(analysis?.specific_capabilities) && analysis.specific_capabilities.length > 0 && <p className="mt-3 text-xs leading-5 text-text-secondary"><b>具体能力：</b>{analysis.specific_capabilities.join('、')}</p>}
              {Boolean(analysis?.ai_reshape) && <p className="mt-2 text-xs leading-5 text-indigo-700"><b>AI重塑：</b>{String(analysis?.ai_reshape)}</p>}
              {Boolean(analysis?.quality_anchor) && <p className="mt-2 text-xs leading-5 text-emerald-700"><b>质量锚点：</b>{String(analysis?.quality_anchor)}</p>}
              {Boolean(analysis?.database_tier && analysis?.recommended_tier && analysis.database_tier !== analysis.recommended_tier) && <p className="mt-2 text-[10px] text-amber-700">数据库Tier：{String(analysis?.database_tier)} · 正式复核建议：{String(analysis?.recommended_tier)}</p>}
              {!analysis?.ai_reshape && l4.human_touchpoint && <p className="mt-2 text-xs text-text-secondary">人工介入：{l4.human_touchpoint}</p>}
              {l4.position_family ? (
                <p className="mt-3 text-[10px] text-cyan-700">
                  负责岗位：{l4.position_family.category_name}（{l4.position_family.family_name} {l4.position_family.family_code}）
                </p>
              ) : (
                <p className="mt-3 text-[10px] text-text-muted">负责岗位：68L3岗位族归属设计v6.1未覆盖该L3，待归口</p>
              )}
            </div>
          )})}
        </div>
        {model.blueprint.blueprint_value_nodes.length > 0 && (
          <>
            <h3 className="mt-6 text-sm font-semibold text-text-primary">服务的价值节点</h3>
            <p className="mt-1 text-xs text-text-muted">数据库正式映射与蓝图补充关系分层展示；蓝图内容不冒充数据库桥接。</p>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {model.blueprint.blueprint_value_nodes.map(node => (
                <div key={node.vn_id} className="rounded-xl border border-amber-200 bg-amber-50/70 p-4">
                  <div className="flex justify-between gap-3"><span className="font-mono text-xs text-amber-800">{node.vn_id}</span><span className="text-[10px] text-text-muted">蓝图第 {node.source_line} 行</span></div>
                  <p className="mt-2 text-sm font-medium text-text-primary">{node.vn_name}</p>
                  <p className="mt-1 text-xs text-text-secondary">{node.deliverable}</p>
                  <p className="mt-2 text-[11px] text-text-muted">{node.l4_codes.join('、')} · {node.status_text}</p>
                </div>
              ))}
            </div>
          </>
        )}
      </section>

      <section className="panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2"><Bot className="h-4 w-4 text-accent-primary-light" /><h2 className="text-sm font-semibold">面板 C · AI任务卡片工作坊</h2></div>
            <p className="mt-2 text-xs text-text-muted">初始位置来自数据库；拖动后的差异仅是本机工作坊共识，不会写回权威库。</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <PanelMeta ssot="蓝图任务、规则、交付物构成及经校验的任务证据。" logic="统一模型按任务判断Human/Aug/Hybrid/Auto；拖动结果仅保存为浏览器工作坊共识。" />
            <label className="flex items-center gap-2 rounded-lg border border-border-default bg-white px-3 py-2 text-xs text-text-secondary">
              <span>L4筛选</span>
              <select value={taskL4Filter} onChange={event => setTaskL4Filter(event.target.value)} className="bg-transparent font-mono text-[11px] text-text-primary outline-none">
                <option value="ALL">全部任务（{cards.length}）</option>
                {taskL4Options.map(code => {
                  const l4Name = model.l4s.find(item => item.l4_code === code)?.l4_name || '名称待补'
                  return <option key={code} value={code}>{code} · {l4Name}（{cards.filter(card => card.l4_code === code).length}）</option>
                })}
              </select>
            </label>
            <button onClick={reset} className="flex items-center gap-1.5 rounded-lg border border-border-default px-3 py-2 text-xs text-text-muted hover:text-text-primary"><RotateCcw className="h-3.5 w-3.5" />恢复数据库位置</button>
            <button onClick={persist} className="flex items-center gap-1.5 rounded-lg bg-accent-primary px-3 py-2 text-xs text-white"><Save className="h-3.5 w-3.5" />保存到本机</button>
          </div>
        </div>
        {session.baseSnapshotHash && session.baseSnapshotHash !== model.snapshot_hash && (
          <div className="mt-4 rounded-xl border border-rose-400/30 bg-rose-400/5 p-3 text-xs text-rose-800">
            这份本机工作坊草稿基于旧模型快照。系统不会自动合并；请先对照新数据，再保存为当前版本或恢复数据库位置。
          </div>
        )}

        {cards.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-amber-300 bg-amber-50 p-5">
            <p className="text-sm font-medium text-amber-800">逐任务分析缺失</p>
            <p className="mt-1 text-xs leading-5 text-text-secondary">模型没有返回通过证据与结构校验的任务拆分。系统不会用L4活动卡片冒充任务；需重新运行任务模块或补充可拆分的蓝图/规则输入。</p>
          </div>
        ) : (
        <div className="mt-4 grid gap-3 lg:grid-cols-4">
          {COLUMNS.map(column => (
            <div key={column.id} onDragOver={event => event.preventDefault()} onDrop={event => moveCard(event.dataTransfer.getData('text/card'), column.id)} className={`min-h-48 rounded-xl border p-3 ${column.color}`}>
              <div className="mb-3 flex items-center justify-between"><h3 className="text-sm font-semibold">{column.label}</h3><span className="text-xs text-text-muted">{visibleCards.filter(card => card.placement === column.id).length}</span></div>
              <p className="mb-3 text-[10px] leading-4 text-text-secondary">{column.explanation}</p>
              <div className="space-y-2">
                {visibleCards.filter(card => card.placement === column.id).map(card => (
                  <article key={card.card_id} draggable onDragStart={event => event.dataTransfer.setData('text/card', card.card_id)} className="cursor-grab rounded-lg border border-border-default bg-bg-elevated p-3 active:cursor-grabbing">
                    <p className="mb-2 font-mono text-[10px] font-semibold text-indigo-700">TASK：{card.displayTaskCode}</p>
                    <div className="flex gap-2"><GripVertical className="mt-0.5 h-4 w-4 shrink-0 text-text-muted" /><div><p className="text-xs font-medium text-text-primary">{card.deliverable || card.l4_name}</p><p className="mt-1 font-mono text-[10px] text-text-muted">{card.l4_code}</p></div></div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <span className={`rounded px-2 py-1 text-[9px] ${card.sequenceNo === null ? 'bg-amber-50 text-amber-800' : 'bg-indigo-50 text-indigo-700'}`}>
                        {card.sequenceNo === null ? '顺序待确认' : `蓝图阶段 ${String(card.sequenceNo).padStart(2, '0')}`}
                      </span>
                      {card.sourceLine && <span className="rounded bg-slate-100 px-2 py-1 text-[9px] text-slate-600">源文第 {card.sourceLine} 行</span>}
                    </div>
                    <p className="mt-1 text-[10px] text-text-muted">{card.source_type}</p>
                    {model.l4s.find(item => item.l4_code === card.l4_code)?.skill_feasibility?.action_singularity.includes('复合') && (
                      <p className="mt-2 rounded bg-amber-50 px-2 py-1 text-[10px] leading-4 text-amber-800">该L4被复核为复合动作；应以蓝图/规则继续拆成任务后再决定AI分工。</p>
                    )}
                    {card.changed && <p className="mt-2 rounded bg-violet-400/10 px-2 py-1 text-[10px] text-violet-700">工作坊共识假设 · 数据库原位置：{card.tier}</p>}
                    <select aria-label={`调整 ${card.card_id} 的工作坊位置`} value={card.placement} onChange={event => moveCard(card.card_id, event.target.value)} className="mt-2 w-full rounded border border-border-default bg-bg-surface px-2 py-1 text-[10px] text-text-secondary lg:hidden">
                      {COLUMNS.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
                    </select>
                  </article>
                ))}
              </div>
            </div>
          ))}
        </div>
        )}

        <label className="mt-4 block text-xs text-text-secondary">本次讨论结论
          <textarea value={session.note} onChange={event => setSession(current => ({ ...current, note: event.target.value }))} placeholder="只记录负责人确认的结论、待验证事项和责任人；保存后仅留在当前浏览器。" className="mt-2 min-h-24 w-full rounded-xl border border-border-default bg-bg-surface p-3 text-sm text-text-primary placeholder:text-text-muted" />
        </label>
        {session.updatedAt && <p className="mt-2 text-[11px] text-text-muted">本机最后保存：{new Date(session.updatedAt).toLocaleString()}</p>}
      </section>

      <section className="panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-accent-primary-light" /><h2 className="text-sm font-semibold">面板 B · 人机协作与控制地图</h2></div>
          <PanelMeta ssot="L4人工触点、D1–D6、蓝图控制点、SOP与规则证据。" logic="大模型逐L4划分AI责任、人工责任、转人工触发条件和不可绕过控制门；不依据Tier名称直接反推控制规则。" />
        </div>
        <p className="mt-2 text-xs text-text-muted">固定展示AI负责、人负责、转人工条件和不可绕过控制门。模型未完成分析时保留缺失态，不从Tier名称反推业务控制。</p>
        {model.analysis.analysis_status === 'PENDING_MODEL' ? (
          <div className="mt-4 rounded-xl border border-dashed border-amber-300 bg-amber-50 p-5">
            <p className="text-sm font-medium text-amber-800">待运行统一模型</p>
            <p className="mt-1 text-xs leading-5 text-text-secondary">当前只有数据库Tier和人工触点，尚不足以生成逐L4的人机责任、异常升级条件和控制门。</p>
          </div>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-[980px] w-full text-xs">
              <thead><tr className="border-b border-border-default text-left text-text-muted"><th className="py-2">L4</th><th>AI负责</th><th>人负责</th><th>何时转人工</th><th>不可绕过控制门</th></tr></thead>
              <tbody>{model.analysis.l4_analysis.map((item, index) => {
                const row = item as Record<string, unknown>
                return <tr key={String(row.l4_code || index)} className="border-b border-border-default/70 align-top"><td className="py-3 font-mono text-accent-primary">{String(row.l4_code || '')}</td><td>{String(row.ai_responsibility || '待补')}</td><td>{String(row.human_responsibility || '待补')}</td><td>{readableList(row.handoff_triggers)}</td><td>{readableList(row.control_gates)}</td></tr>
              })}</tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2"><Layers3 className="h-4 w-4 text-accent-primary-light" /><h2 className="text-sm font-semibold">面板 D · AI机会优先级工作坊</h2></div>
            <p className="mt-2 text-xs text-text-muted">可将每项 L4 拖入讨论后的象限。初始位置来自分析包；移动结果仅是本机工作坊共识，不会写回权威库。</p>
          </div>
          <div className="flex items-center gap-2">
            <PanelMeta ssot="逐L4四维分析：数据依据、流程背景、风险/限制、当前建议。" logic="大模型提供可追溯的初始建议；无数据支持时保持待归类。负责人拖动后只形成本机工作坊共识。" />
            <button onClick={reset} className="flex items-center gap-1.5 rounded-lg border border-border-default px-3 py-2 text-xs text-text-muted hover:text-text-primary"><RotateCcw className="h-3.5 w-3.5" />恢复初始位置</button>
            <button onClick={persist} className="flex items-center gap-1.5 rounded-lg bg-accent-primary px-3 py-2 text-xs text-white"><Save className="h-3.5 w-3.5" />保存到本机</button>
          </div>
        </div>
        {model.analysis.priority_drafts.length === 0 ? (
          <div className="mt-4 space-y-3">
            <div className="rounded-xl border border-indigo-200 bg-indigo-50/60 p-4">
              <p className="text-sm font-semibold text-indigo-900">Skill封装评估已接入，但不自动编造象限坐标</p>
              <p className="mt-1 text-xs leading-5 text-text-secondary">A/B/C/F回答“适合怎么封装”，Tier回答“需要多少人工判断”。正式象限仍需逐L4四维分析或负责人工作坊确认。</p>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {model.l4s.filter(l4 => l4.skill_feasibility).map(l4 => (
                  <div key={l4.l4_code} className="rounded-lg border border-white bg-white p-3">
                    <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-[10px] text-accent-primary">{l4.l4_code}</span><b className="text-xs">{l4.l4_name}</b><span className={`rounded border px-2 py-0.5 text-[9px] ${skillTone(l4.skill_feasibility?.grade || '')}`}>{shortSkillGrade(l4.skill_feasibility?.grade || '')}</span></div>
                    <p className="mt-2 text-[11px] leading-5 text-text-secondary">{l4.skill_feasibility?.recommended_path}</p>
                  </div>
                ))}
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {PRIORITY_ZONES.map(zone => (
                <div key={zone.id} className={`min-h-28 rounded-xl border p-4 ${zone.tone}`}>
                  <p className="text-sm font-semibold text-text-primary">{zone.label}</p>
                  <p className="mt-2 text-[11px] leading-5 text-text-secondary">{zone.explanation}</p>
                  <p className="mt-2 text-[10px] font-medium text-text-primary">归类指引：{zone.guide}</p>
                  <p className="mt-2 text-[10px] text-text-muted">当前无经过证据校验的逐L4位置，不生成假坐标。</p>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="mt-4 space-y-3">
            <div
              onDragOver={event => event.preventDefault()}
              onDrop={event => movePriority(event.dataTransfer.getData('text/priority'), 'unclassified')}
              className="min-h-24 rounded-xl border border-violet-200 bg-violet-50/70 p-4"
            >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-violet-900">待负责人归类 · 不编造象限位置</p>
                  <span className="rounded-full bg-white px-2 py-1 text-[10px] text-violet-700">{priorityDrafts.filter(item => item.placement === 'unclassified').length} 项 · 可拖入下方象限</span>
                </div>
                <div className="mt-3 grid gap-2 lg:grid-cols-2">
                  {priorityDrafts.filter(item => item.placement === 'unclassified').map((item, index) => (
                    <div key={item.l4Code || index} draggable onDragStart={event => event.dataTransfer.setData('text/priority', item.l4Code)} className="cursor-grab rounded-lg border border-violet-100 bg-white p-3 shadow-sm active:cursor-grabbing">
                      <div className="flex items-center gap-2">
                        <GripVertical className="h-3.5 w-3.5 shrink-0 text-text-muted" />
                        <p className="text-xs text-text-primary"><span className="font-mono text-[10px] text-accent-primary">{item.l4Code}</span><b className="ml-2">{item.l4Name}</b></p>
                      </div>
                      <p className="mt-3 text-[11px] leading-5 text-text-secondary"><b>数据依据：</b>{item.data_basis.join('；') || '待补'}</p>
                      <p className="mt-1 text-[11px] leading-5 text-text-secondary"><b>流程背景：</b>{item.process_context || '待补'}</p>
                      <p className="mt-1 text-[11px] leading-5 text-text-secondary"><b>风险/限制：</b>{item.risks_limits.join('；') || '待补'}</p>
                      <p className="mt-1 text-[11px] font-medium leading-5 text-text-primary"><b>当前建议：</b>{item.current_recommendation || '待补'}</p>
                      <select aria-label={`调整 ${item.l4Code} 的优先级位置`} value={item.placement} onChange={event => movePriority(item.l4Code, event.target.value)} className="mt-2 w-full rounded border border-border-default bg-bg-surface px-2 py-1 text-[10px] text-text-secondary lg:hidden">
                        <option value="unclassified">待负责人归类</option>
                        {PRIORITY_ZONES.map(zone => <option key={zone.id} value={zone.id}>{zone.label}</option>)}
                      </select>
                    </div>
                  ))}
                </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {PRIORITY_ZONES.map(zone => (
                <div
                  key={zone.id}
                  onDragOver={event => event.preventDefault()}
                  onDrop={event => movePriority(event.dataTransfer.getData('text/priority'), zone.id)}
                  className={`min-h-40 rounded-xl border p-4 ${zone.tone}`}
                >
                  <div className="flex items-center justify-between"><p className="text-sm font-semibold text-text-primary">{zone.label}</p><span className="text-xs text-text-muted">{priorityDrafts.filter(item => item.placement === zone.id).length}</span></div>
                  <p className="mt-2 text-[10px] leading-4 text-text-secondary">{zone.explanation}</p>
                  <p className="mt-1 text-[10px] font-medium text-text-primary">归类指引：{zone.guide}</p>
                  <div className="mt-3 space-y-2">
                    {priorityDrafts.filter(item => item.placement === zone.id).map((item, index) => (
                      <div key={item.l4Code || index} draggable onDragStart={event => event.dataTransfer.setData('text/priority', item.l4Code)} className="cursor-grab rounded-lg border border-white/80 bg-white p-3 shadow-sm active:cursor-grabbing">
                        <div className="flex items-center gap-2">
                          <GripVertical className="h-3.5 w-3.5 shrink-0 text-text-muted" />
                          <p className="text-xs text-text-primary"><span className="font-mono text-[10px] text-accent-primary">{item.l4Code}</span><b className="ml-2">{item.l4Name}</b></p>
                        </div>
                        <p className="mt-3 text-[11px] leading-5 text-text-secondary"><b>数据依据：</b>{item.data_basis.join('；') || '待补'}</p>
                        <p className="mt-1 text-[11px] leading-5 text-text-secondary"><b>流程背景：</b>{item.process_context || '待补'}</p>
                        <p className="mt-1 text-[11px] leading-5 text-text-secondary"><b>风险/限制：</b>{item.risks_limits.join('；') || '待补'}</p>
                        <p className="mt-1 text-[11px] font-medium leading-5 text-text-primary"><b>当前建议：</b>{item.current_recommendation || '待补'}</p>
                        {item.changed && <p className="mt-2 rounded bg-violet-50 px-2 py-1 text-[10px] text-violet-700">工作坊共识 · 初始位置：{item.initial === 'unclassified' ? '待负责人归类' : PRIORITY_ZONES.find(value => value.id === item.initial)?.label}</p>}
                        <select aria-label={`调整 ${item.l4Code} 的优先级位置`} value={item.placement} onChange={event => movePriority(item.l4Code, event.target.value)} className="mt-2 w-full rounded border border-border-default bg-bg-surface px-2 py-1 text-[10px] text-text-secondary lg:hidden">
                          <option value="unclassified">待负责人归类</option>
                          {PRIORITY_ZONES.map(option => <option key={option.id} value={option.id}>{option.label}</option>)}
                        </select>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-indigo-200 bg-gradient-to-br from-indigo-50 to-white p-5 shadow-panel">
        <div className="flex items-center gap-2"><Bot className="h-4 w-4 text-accent-primary" /><h2 className="text-sm font-semibold">负责人决策 · 先试哪些AI任务</h2></div>
        <p className="mt-2 text-xs text-text-muted">只输出任务级优先顺序、最小试点、人工边界和需要拍板的事项。</p>
        <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] leading-5 text-amber-800">
          以下是统一模型生成的决策建议草稿，不是数据库结论或已达成的业务共识。试点范围、周期、责任人和验收指标必须由负责人确认后才生效。
        </p>
        {model.analysis.decision_drafts.length === 0 ? (
          <div className="mt-4 rounded-xl border border-dashed border-indigo-200 bg-white/80 p-5 text-sm text-text-secondary">
            当前尚无通过证据校验的负责人决策草稿。完成统一模型分析后再生成，不使用通用建议占位。
          </div>
        ) : (
          <div className="mt-4 space-y-3">{model.analysis.decision_drafts.map((draft, index) => (
            <div key={String(draft.priority || index)} className="grid gap-3 rounded-xl border border-indigo-100 bg-white p-4 md:grid-cols-[90px_1.2fr_1fr_1fr]">
              <div><span className="rounded-full bg-indigo-100 px-2.5 py-1 text-xs font-bold text-indigo-800">{String(draft.priority || '')}</span></div>
              <div>
                <p className="text-sm font-semibold text-text-primary">{String(draft.title || '')}</p>
                <p className="mt-1 font-mono text-[10px] text-text-muted">{Array.isArray(draft.task_ids) ? draft.task_ids.join('、') : ''}</p>
                {Array.isArray(draft.evidence_refs) && draft.evidence_refs.length > 0 && (
                  <p className="mt-1 font-mono text-[9px] leading-4 text-indigo-500">证据：{draft.evidence_refs.join('、')}</p>
                )}
              </div>
              <div><p className="eyebrow">最小试点</p><p className="mt-1 text-xs leading-5 text-text-secondary">{String(draft.pilot_scope || '')}</p></div>
              <div><p className="eyebrow">人工边界</p><p className="mt-1 text-xs leading-5 text-text-secondary">{String(draft.human_boundary || '')}</p></div>
            </div>
          ))}</div>
        )}
      </section>

      <section className="panel p-5">
        <details>
          <summary className="cursor-pointer text-sm font-semibold text-text-primary">面板 F · SSOT与证据</summary>
          <div className="mt-3 flex justify-end">
            <PanelMeta ssot="数据库 process_analytics 与已纳入VNW引用范围的OB知识库文件；每条记录保留来源对象、字段、键和证据ID。" logic="本面板不生成业务判断，只展示证据注册表。模型只能引用ACTIVE且通过准入的证据；CONSENSUS/UNVERIFIED不参与自动分析。" />
          </div>
          <p className="mt-2 text-xs text-text-muted">当前模型共登记 {model.evidence_registry.length} 条字段证据；分析标准为 {model.analysis.analysis_standard_id}。</p>
          <div className="mt-4 rounded-xl border border-violet-200 bg-violet-50/70 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-sm font-semibold text-violet-900">本Demo输入谱系 · 数据、知识与方法</h3>
                <p className="mt-1 text-[11px] text-text-secondary">回答“这份L3模型实际使用了什么来源、具体定位到哪里、带来什么思考、进入哪个面板”；每个L3按实际命中范围独立生成。</p>
              </div>
              <span className="rounded-full bg-white px-2.5 py-1 text-[10px] font-medium text-violet-700">{inputLineage.length} 类事实来源 + 2 项分析方法</span>
            </div>
            {inputLineage.length === 0 ? (
              <p className="mt-3 rounded-lg border border-dashed border-violet-200 bg-white/70 p-3 text-xs text-text-muted">当前 L3 没有登记可追溯事实输入，不生成模型贡献说明。</p>
            ) : (
              <div className="mt-3 space-y-3">
                {inputLineage.map(item => (
                  <div key={`${item.sourceSystem}:${item.sourceObject}`} className="rounded-xl border border-white bg-white p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold text-text-primary">{item.sourceObject}</p>
                        <p className="mt-1 text-[10px] text-text-muted">{item.sourceSystem} · {item.sourceVersion || '版本见源文件'} · 本L3命中 {item.keys.length} 个对象 / {item.evidenceCount} 条字段证据</p>
                        <p className="mt-1 font-mono text-[10px] text-violet-700">{item.location}</p>
                      </div>
                      <span className="rounded-full bg-violet-50 px-2 py-1 text-[9px] text-violet-700">{item.fields.join('、')}</span>
                    </div>
                    <div className="mt-3 grid gap-3 md:grid-cols-2">
                      <div className="rounded-lg bg-slate-50 p-3">
                        <p className="text-[10px] font-semibold text-slate-700">带来的核心思考</p>
                        <p className="mt-1 text-[11px] leading-5 text-text-secondary">{item.thinking}</p>
                      </div>
                      <div className="rounded-lg bg-indigo-50 p-3">
                        <p className="text-[10px] font-semibold text-indigo-700">进入本模型的输入</p>
                        <p className="mt-1 text-[11px] leading-5 text-text-secondary">{item.input}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="mt-4 border-t border-violet-200 pt-4">
              <h4 className="text-xs font-semibold text-violet-900">分析方法与大模型加工</h4>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div className="rounded-xl border border-white bg-white p-4">
                  <p className="text-xs font-semibold text-text-primary">L3流程模型统一模板_v1.0.md</p>
                  <p className="mt-1 text-[10px] text-text-muted">方法论模板 · {model.analysis.analysis_standard_id}</p>
                  <p className="mt-3 text-[11px] leading-5 text-text-secondary"><b>核心思考：</b>用统一的Gate、面板A–F、双轴AI判断和负责人决策结构约束所有L3，避免每份Demo各自发挥。</p>
                  <p className="mt-2 text-[11px] leading-5 text-indigo-700"><b>进入本模型：</b>决定页面结构、必填分析字段、缺失态和可发布门槛。</p>
                </div>
                <div className="rounded-xl border border-white bg-white p-4">
                  <p className="text-xs font-semibold text-text-primary">L3统一分析模型_v1.0.md</p>
                  <p className="mt-1 text-[10px] text-text-muted">{model.analysis.model_run?.model_name || '模型尚未运行'} · Prompt {model.analysis.model_run?.prompt_version || model.analysis.analysis_standard_id}</p>
                  <p className="mt-3 text-[11px] leading-5 text-text-secondary"><b>核心思考：</b>模型只能使用事实包，必须逐项引用证据；Skill封装与AI Tier分轴判断，复合动作拆为任务，具体人名不进入展示。</p>
                  <p className="mt-2 text-[11px] leading-5 text-indigo-700"><b>进入本模型：</b>加工面板B–E和负责人决策；其输出为MODEL_DRAFT，不改变数据库与知识库原文。</p>
                </div>
              </div>
            </div>
          </div>
          <div className="mt-4 max-h-96 overflow-auto rounded-xl border border-border-default">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-bg-surface text-text-muted"><tr><th className="px-3 py-2">证据ID</th><th>证据层</th><th>字段</th><th>状态</th></tr></thead>
              <tbody>{model.evidence_registry.map((item, index) => {
                const row = item as Record<string, unknown>
                return <tr key={String(row.evidence_id || index)} className="border-t border-border-default"><td className="px-3 py-2 font-mono text-[10px] text-accent-primary">{String(row.evidence_id || '')}</td><td>{String(row.evidence_class || '')}</td><td>{String(row.field_name || '')}</td><td>{String(row.status || '')}</td></tr>
              })}</tbody>
            </table>
          </div>
        </details>
      </section>

      <section className="panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-default pb-3">
          <h2 className="text-sm font-semibold">综合判断 · VNW统一分析Spec v1.0</h2>
          <span className={`rounded-full px-3 py-1.5 text-xs font-medium ${model.unified_analysis.status === 'CONFIRMED' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}`}>
            {model.unified_analysis.status === 'CONFIRMED' ? `已确认 · ${model.unified_analysis.confirmed_by ?? ''}` : '草稿 · 尚未人工确认'}
          </span>
        </div>
        {model.unified_analysis.status === 'DRAFT' ? (
          <p className="mt-3 text-xs leading-5 text-amber-700">草稿状态的综合判断不能作为最终结论用于投入决策，需Jasper/L3业务负责人复核后写入决策确认记录（07_接入记忆_Integrate_Memory/analysis_confirmations/{model.l3_code}.json）。</p>
        ) : (
          <p className="mt-3 text-xs leading-5 text-emerald-700">{model.unified_analysis.confirmed_at} 由 {model.unified_analysis.confirmed_by} 确认。{model.unified_analysis.confirmation_notes}</p>
        )}

        <div className="mt-4 grid gap-3 grid-cols-2 lg:grid-cols-5">
          {[
            ['L4总数', model.unified_analysis.coverage.l4_total, 'text-text-primary'],
            ['业务数据覆盖', model.unified_analysis.coverage.business_evidence_covered, 'text-emerald-700'],
            ['岗位归属覆盖', model.unified_analysis.coverage.position_covered, 'text-cyan-700'],
            ['关联KPI', model.unified_analysis.coverage.kpi_count, 'text-amber-700'],
            ['价值流位置', model.unified_analysis.coverage.value_stream_count, 'text-teal-700'],
          ].map(([label, value, tone]) => (
            <div key={String(label)} className="rounded-lg border border-border-default bg-bg-surface p-3 text-center">
              <p className={`font-mono text-xl ${tone}`}>{value}</p>
              <p className="mt-1 text-[10px] text-text-muted">{label}</p>
            </div>
          ))}
        </div>

        {model.unified_analysis.axis_conflicts.length > 0 ? (
          <div className="mt-4 rounded-lg border border-rose-300 bg-rose-50 p-3">
            <p className="text-xs font-semibold text-rose-800">双轴冲突（D1-D6/Tier轴 与 候选Agent封装轴方向相反）</p>
            <p className="mt-1 text-[11px] leading-5 text-rose-700">{model.unified_analysis.axis_conflicts.join('、')} —— 需业务方澄清，不自动选边，不合并成单一自动化分数。</p>
          </div>
        ) : (
          <p className="mt-4 text-[11px] text-text-muted">本L3当前无双轴冲突（D1-D6/Tier轴与候选Agent封装轴方向一致）。</p>
        )}

        <details className="mt-4">
          <summary className="cursor-pointer text-xs font-semibold text-text-primary">Definition of Done · 10项发布前检查</summary>
          <div className="mt-2 space-y-1.5">
            {model.unified_analysis.dod_checklist.map((item, index) => (
              <p key={index} className="flex items-start gap-2 text-[11px] leading-4 text-text-secondary">
                <span className={item.satisfied ? 'text-emerald-600' : 'text-rose-600'}>{item.satisfied ? '✓' : '✗'}</span>
                {item.item}
              </p>
            ))}
          </div>
        </details>

        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-semibold text-text-primary">逐L4根因阶梯（事实 → 机制 → 结构 → 策略）</summary>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {model.l4s.map(l4 => {
              const ladder = model.unified_analysis.root_cause_ladders[l4.l4_code]
              if (!ladder) return null
              return (
                <div key={l4.l4_code} className="rounded-lg border border-border-default bg-bg-surface p-3">
                  <p className="font-mono text-[11px] text-accent-primary-light">{l4.l4_code} · {l4.l4_name}</p>
                  <div className="mt-2 space-y-1">
                    {ladder.map((layer, i) => (
                      <p key={i} className="text-[10px] leading-4 text-text-secondary">
                        <span className="font-semibold">[{layer.layer}·{layer.grade}级]</span> {layer.statement}
                      </p>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        </details>

        <p className="mt-3 text-[9px] text-text-muted">SSOT：03_规划项目结构_Plan_Project_Structure/VNW统一分析Spec_v1.0.md</p>
      </section>

      <div className="flex items-start gap-2 rounded-xl border border-sky-400/20 bg-sky-400/5 p-4 text-xs text-sky-800">
        <Info className="mt-0.5 h-4 w-4 shrink-0" />
        <span>本页业务事实来自 process_analytics 快照，共 {model.evidence_registry.length} 条字段证据。浏览器保存内容属于 CONSENSUS 层，不参与 Gate 自动判断。</span>
      </div>
    </div>
  )
}
