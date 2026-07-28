// Table file mapping
const TABLE_FILES: Record<string, string> = {
  node_index: '/data/node_index.json',
  signals: '/data/signals.json',
  interview_leads: '/data/interview_leads.json',
  actions: '/data/actions.json',
  rules: '/data/rules.json',
  deliverables: '/data/deliverables.json',
  gaps: '/data/gaps.json',
  value_stream: '/data/value_stream.json',
  interview_batches: '/data/interview_batches.json',
  role_mapping: '/data/role_mapping.json',
  gate_ratings: '/data/gate_ratings.json',
  node_review: '/data/node_review.json',
  domain_progress: '/data/domain_progress.json',
  interview_recordings: '/data/interview_recordings.json',
  report_tracking: '/data/report_tracking.json',
  // 2026-07-25新增:数据底座A类新建/重建的表
  fused_tasks: '/data/fused_tasks.json',
  sop_progress: '/data/sop_progress.json',
  l4_tier: '/data/l4_tier.json',
  data_audit: '/data/data_audit.json',
  ait_handoff: '/data/ait_handoff.json',
  deliverable_risk: '/data/deliverable_risk.json',
  fused_status: '/data/fused_status.json',
  candidate_agents: '/data/candidate_agents.json',
  // D类:人工试点,非自动更新,但仍可浏览
  sop_pilot_classification: '/data/sop_pilot_classification.json',
  flow_context: '/data/flow_context.json',
  // 2026-07-26新增:数据仓库(process_analytics schema)权威源新表
  l3_l2_bridge: '/data/l3_l2_bridge.json',
  org_roles: '/data/org_roles.json',
};
const TABLE_NAMES = Object.keys(TABLE_FILES);

type Cache = Record<string, any[]>;
const cache: Cache = {};

export async function loadAllData(): Promise<Cache> {
  const results = await Promise.all(
    TABLE_NAMES.map(async (name) => {
      try {
        const res = await fetch(TABLE_FILES[name]);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const text = await res.text();
        const sanitized = text.replace(/: ?NaN/g, ': null').replace(/: ?-Infinity/g, ': null').replace(/: ?Infinity/g, ': null');
        const data = JSON.parse(sanitized);
        const rows = Array.isArray(data) ? data : (data.data ?? []);
        cache[name] = rows;
        return [name, rows] as [string, any[]];
      } catch (err) {
        console.warn(`Failed to load table ${name}:`, err);
        cache[name] = cache[name] || [];
        return [name, cache[name]] as [string, any[]];
      }
    })
  );
  return Object.fromEntries(results);
}

export function getTableData(tableName: string): any[] {
  return cache[tableName] || [];
}

export function getNodeById(nodeId: string): any | undefined {
  return (cache.node_index || []).find((n: any) => n.node_id === nodeId);
}

export function getNodeValueStream(nodeId: string): any | undefined {
  return (cache.value_stream || []).find((n: any) => n.vn_id === nodeId);
}

export function getRelatedData(nodeId: string): Cache {
  const result: Cache = {};
  for (const [tableName, rows] of Object.entries(cache)) {
    if (tableName === 'node_index' || tableName === 'value_stream') continue;
    result[tableName] = rows.filter((r: any) =>
      r.node_id === nodeId || r.vn_id === nodeId || r.value_node_id === nodeId
    );
  }
  return result;
}

export function useDataCache(): Cache {
  return { ...cache };
}

// Domains
// 2026-07-25更新:域代码改成跟sync_data_foundation.py里DOMAINS常量一致的8个真实域
// (EQ/FA/HR/INS/KA/PARTNER/PAY/TREASURY)。旧版BAM/MGA/AGT三个域代码在当前数据里
// 从未出现过,FA/PARTNER/TREASURY这三个真实域之前反而没有条目,会被getDomainInfo
// 误判成DOMAINS[0](PAY)。
export const DOMAINS = [
  { code: 'PAY', name: 'PAY·佣金与支付域', color: '#F472B6', tw: 'border-pink-500 text-pink-500', bg: 'bg-pink-500' },
  { code: 'EQ', name: 'EQ·权益域', color: '#A78BFA', tw: 'border-violet-500 text-violet-500', bg: 'bg-violet-500' },
  { code: 'HR', name: 'HR·人力资源域', color: '#38BDF8', tw: 'border-sky-500 text-sky-500', bg: 'bg-sky-500' },
  { code: 'INS', name: 'INS·保司合作域', color: '#34D399', tw: 'border-emerald-500 text-emerald-500', bg: 'bg-emerald-500' },
  { code: 'FA', name: 'FA·理财师全生命周期域', color: '#818CF8', tw: 'border-indigo-500 text-indigo-500', bg: 'bg-indigo-500' },
  { code: 'PARTNER', name: 'PARTNER·机构合作域', color: '#FB923C', tw: 'border-orange-500 text-orange-500', bg: 'bg-orange-500' },
  { code: 'TREASURY', name: 'TREASURY·资金管理域', color: '#22D3EE', tw: 'border-cyan-500 text-cyan-500', bg: 'bg-cyan-500' },
  { code: 'KA', name: 'KA·KA域', color: '#A3E635', tw: 'border-lime-500 text-lime-500', bg: 'bg-lime-500' },
];

export function getDomainInfo(nodeId: string) {
  const prefix = nodeId?.split('-')[1];
  return DOMAINS.find(d => d.code === prefix) || DOMAINS[0];
}

// Workflow stages
export const WORKFLOW_STAGES = [
  { id: 1, name: '价值节点识别', short: '节点', desc: '梳理所有价值节点及交付物' },
  { id: 2, name: '规则空白识别', short: '空白', desc: '围绕价值节点识别潜在规则、行动和Gap' },
  { id: 3, name: '调研模板生成', short: '模板', desc: '基于规则空白生成调研模板' },
  { id: 4, name: '执行访谈', short: '访谈', desc: '按调研模板执行访谈，收集规则信号' },
  { id: 5, name: '规则清单确认', short: '清单', desc: '整理访谈结果，形成规则清单和Gap清单' },
  { id: 6, name: '报告生成', short: '报告', desc: '基于规则和Gap清单生成分析报告' },
  { id: 7, name: '梳理SOP', short: 'SOP', desc: '围绕需要梳理的环节产出SOP' },
  { id: 8, name: '数据回填', short: '回填', desc: 'SOP完成后提炼数据回填到数据表' },
  { id: 9, name: '持续迭代', short: '持续', desc: '行动和Gap解决后持续生成报告并回填' },
];

// Table display names
// 2026-07-25:描述文字里不再写死行数(之前"72个节点""209个Gap"这类数字会随数据
// 更新过时,之前就发生过72→78节点、209→211个Gap导致描述文字失真的问题)。
export const TABLE_DISPLAY_NAMES: Record<string, { name: string; desc: string }> = {
  node_index: { name: 'T1·节点索引', desc: '价值节点全景信息' },
  signals: { name: 'T2·信号数据', desc: '规则信号提取记录' },
  interview_leads: { name: 'T3·访谈线索', desc: '访谈线索与问题(人工维护)' },
  actions: { name: 'T4·行动项', desc: '待执行行动项(人工维护)' },
  rules: { name: 'T5·规则清单', desc: '已识别规则,直接同步自04层' },
  deliverables: { name: 'T6·交付物清单', desc: '交付物清单' },
  gaps: { name: 'T7·缺口清单', desc: '规则Gap清单,直接同步自04层' },
  value_stream: { name: 'T9·价值流归属', desc: '节点价值流映射(人工维护)' },
  interview_batches: { name: 'T10·访谈批次', desc: '访谈批次与岗位映射(人工维护)' },
  role_mapping: { name: 'T11·岗位映射', desc: '岗位角色映射' },
  gate_ratings: { name: 'T12·Gate评级', desc: '节点质量门评级,数据仓库权威源(dim_vn)' },
  node_review: { name: 'T13·节点复评', desc: '节点复评追踪(人工维护)' },
  domain_progress: { name: 'T14·域进度', desc: '业务域扩展进度' },
  interview_recordings: { name: 'T16·访谈记录', desc: '访谈录音跟踪(人工维护)' },
  report_tracking: { name: 'T17·报告跟踪', desc: '报告发送跟踪(人工维护)' },
  fused_tasks: { name: 'T18·熔断任务分发', desc: '熔断节点补建任务,按域最新版补建清单生成' },
  sop_progress: { name: 'T19·SOP生产进度', desc: '05_SOP全部文件现状,含VN价值节点/TOI-TOB证据/L3流程三种编码体系' },
  l4_tier: { name: 'T20·L4自动化Tier评估', desc: 'L4级自动化Tier判断,数据仓库权威源(dim_process)' },
  data_audit: { name: 'T21·数据对齐审计', desc: '数据底座自我审计记录,每次同步重新生成' },
  ait_handoff: { name: 'T23·VNW→AIT移交追踪', desc: '节点向AIT移交的状态追踪' },
  deliverable_risk: { name: 'T24·交付物四标签风险分析', desc: 'A类型/B责任/C验证/D授权四标签,目前仅PAY域格式已解析' },
  fused_status: { name: 'T25·熔断状态清单', desc: '节点熔断/非熔断权威判定,数据仓库权威源(dim_vn.is_fused)' },
  candidate_agents: { name: 'T26·Agent规划', desc: '数据仓库dim_agent,1条L4=1个规划中的原子级Agent(跟旧版聚合候选Agent颗粒度不同)' },
  sop_pilot_classification: { name: 'T22·SOP规则人机协同分类', desc: '人工试点分类示例,不自动更新' },
  l3_l2_bridge: { name: 'T29·L3-L2业务能力桥接', desc: '数据仓库bridge_l3_l2,L3流程归属哪个L2业务能力' },
  org_roles: { name: 'T30·岗位组织', desc: '数据仓库dim_org,岗位族/编制目标/汇报关系' },
};
