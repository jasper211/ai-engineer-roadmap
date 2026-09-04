# ICD-T008 · AIA RBC 官方索引发现、PDF 解析与入库

> 执行方：vscode-deepseek  
> 推动与审计：Codex  
> 状态：DISPATCHED  
> 派发日期：2026-09-03

## 目标

完成需求成功标准中的第二家 RBC：从注册表 source_id=12 的 AIA 官方监管披露索引，确定 2024 英文 Disclosure Statement PDF 的真实 URL 与法律主体，形成索引发现→PDF 抓取→文本解析→标准化→SQLite 入库的可审计闭环。需求材料中的 304% 仅为人工锚点，结果必须由当前真实 PDF 独立提取，不得写死。

## 允许范围

- ICD 内 source registry、数据契约与必要的主体种子修正
- PDF 索引发现、下载解析、RBC 通用解析/写入工具
- agent CLI 接入、fixture、测试、README/settings、证据材料、任务书与任务日志

禁止修改 ICD 外项目；禁止 Git 提交；禁止读取或记录密钥；不得引入浏览器自动化。若出现无法从官方页面确认 PDF、核心口径不可无损表达或必须改变已确认业务边界的情况，停止并提出 Gate。

## 功能要求

1. 先抓取 source_id=12 官方索引页并保留证据，解析链接时必须限定官方域名、2024 报告期、英文 Disclosure Statement 语义，不得凭搜索结果或文件名猜测。
2. 索引页与最终 PDF 是两段证据链：记录索引 final_url/HTTP/哈希/快照，以及 PDF final_url/HTTP/哈希/快照；数据库记录必须可回查最终 PDF。若现有 fetch_run/source 模型不足以表达两段链路，提出最小可审计方案。
3. 读取 PDF 的 `Authorized insurer's name`。当前 AIA 代码代表 AIA International Limited；若 PDF 为 AIA Company Limited 或其他法律主体，按 T007 已确认政策建立独立、语义明确的 insurer_code，修正 source 归属并迁移快照，不得混淆。
4. 泛化现有 Prudential 专用解析器为可复用 RBC Capital Adequacy 解析能力，保留针对不同版式的受限适配；不得复制一套仅改名字的硬编码解析器，不得全文任意百分号命中。
5. 提取 report_year、legal_entity_name_raw、solvency_ratio/raw、currency、capital_base/raw、prescribed_capital_amount/raw、amount_unit_raw/scale，以及可无损表达的风险分解；不能无损映射的分解保留 JSON，不强塞枚举。
6. 结构漂移、PDF 链接歧义、错误年度、法律主体不一致、重复比率、非 PDF、无文字层、零记录均需确定性失败或明确状态测试；事务、幂等、迁移补偿与既有 T002-T007 回归必须通过。

## 验收标准

1. 真实官方索引可重复定位唯一的 2024 英文 PDF；索引和 PDF 的 URL、HTTP 状态、哈希、字节、快照和抓取时间齐备。
2. 真实 PDF 文字层可用，记录页数与字符数；至少逐字核对法律主体、304% 原文/3.04 标准值及一项金额或单位至数据库。
3. 最终记录法律主体编码与 PDF 原文一致，不复用不同持牌实体代码；默认库旧数据安全迁移，integrity/FK/自然键/快照路径均正确。
4. 解析器证明不是写死 304%，fixture 至少覆盖另一合法比率、跨行断词、歧义和结构漂移。
5. 全量 T002-T007 无回归；测试不污染默认数据库；执行回执列明命令、退出码、计数、证据与变更范围。

## 执行回执

由 vscode-deepseek 完成后追加；不得自行标记 ACCEPTED。
