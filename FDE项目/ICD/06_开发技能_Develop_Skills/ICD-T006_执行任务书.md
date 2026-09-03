# ICD-T006 · 中国人寿（海外）HTML 分红实现率解析与入库

> 执行方：vscode-deepseek  
> 推动与审计：Codex  
> 状态：DISPATCHED  
> 派发日期：2026-09-03

## 目标

实现注册表中中国人寿（海外）CLO `fulfillment_ratio` HTML 源（当前按注册表顺序为 source_id=9）的完整闭环，使成功标准指定的 AIA、CTF Life、CLO 三家分红实现率全部具备真实官网证据、标准化记录和可重复查询结果。

## 允许范围

- `06_开发技能_Develop_Skills/skills/`新增或扩展 CLO HTML 解析与解析分流
- `05_集成工具_Integrate_Tools/tools/`仅补充必要的通用解析能力
- `04_定义Agent_Define_Agent/agents/agent.py`补充接入（若需要）
- `09_测试与调试_Test_and_Debug/tests/`新增脱敏 fixture 与 T006 测试
- `07_接入记忆_Integrate_Memory/`写受控真实快照及数据库验证产物
- `README.md`、`settings.json`、本任务书和任务日志回执区

禁止修改 `source_registry.json`、数据契约、流程设计、T001-T005 任务书；真实结构若无法由现契约无损表达，停止并提出重大决策 Gate。禁止 ICD 外写入、Git 提交或自行标记 ACCEPTED。

## 功能要求

1. 先通过 T003 抓取 source_id=9，记录 HTTP 状态、最终 URL、哈希、字节数、页面语言、目标表格数量和稳定 DOM 锚点；以当前真实页面为准。
2. 解析必须基于页面段落、产品标题、表头、行列与合并单元格关系；不得用全页百分号匹配冒充业务解析，也不得读取官方 PDF 替代注册表 HTML。
3. 原样保存产品名、指标原文、币种/披露分组、报告年度、观察期原文和数值原文；AD/TD/RB/TB/TCV/OTHER 不得合并。未知指标不得猜测；可无损落 `OTHER + metric_type_raw` 时须有测试，否则升级 Gate。
4. 数字观察年写整数，非数字期间写 NULL 并保留原文；百分比统一为小数比率。不可数值化项保留原文并写 `PARTIAL + VALUE_UNPARSEABLE`。
5. 结构漂移、零产品和零业务记录明确失败；解析不联网；同一 run_id 事务写入、硬失败回滚、重复解析幂等。
6. 页面导航、说明文字、脚注、隐藏模板和非目标表格不得入库；中英文混排、HTML 实体及空白折叠需确定性处理。

## 验收标准

1. 脱敏 fixture 至少覆盖两个产品、两个指标、跨年份、合并单元格、脚注/非数值、结构漂移、零记录、幂等和回滚。
2. 真实验证通过 source_id=9 的 T003 快照完成，记录产品数、记录数、指标/观察年分布、可数值与不可数值计数，并至少逐字核对 3 组官网 HTML→数据库原值。
3. 每条记录均可经 run_id 反查最终 URL、HTTP 状态、时间、哈希和快照；关键维度不得为空，自然业务键不得重复。
4. 全量 T002-T005 测试无回归，测试仅使用临时目录。

## 执行回执

由 vscode-deepseek 追加；必须分开记录 fixture、回归测试和真实网络证据，不得自行标记 ACCEPTED。
