# ICD-T013 · AXA / FWD Next.js 多产品分红扩展

> 执行与自审：Codex  
> 里程碑复核：vscode-deepseek（完成后集中执行）  
> 状态：SUBMITTED（Codex 自审通过；待 DeepSeek 外部传输授权后完成里程碑复核）  
> 日期：2026-09-04

## 目标

从 AXA、FWD 官方索引确定性发现产品子页，抓取并解析 Next.js SSR 披露数据，使分红实现率覆盖达到 8 家建设期里程碑。

## 验收标准

1. 索引→产品页证据链完整，产品链接去重且限定官方域名；FWD 正确处理尾部斜杠与重定向。
2. 不执行浏览器 JavaScript；仅解析首屏 HTML/`__NEXT_DATA__` 中的官方披露。
3. 单产品失败隔离、结构漂移显式失败、原始快照可追溯、重复运行幂等。
4. 两家真实产品/记录/年份/类型统计与抽样原文核对通过；coverage 更新为真实结果。
5. T002-T013 全量回归通过后，生成限定上下文的 DeepSeek 集中独立复核任务。

## Codex 执行与自审回执（2026-09-04）

- 新增 `skills/nextjs_ratio.py`：AXA 50 个、FWD 70 个官方产品页的索引发现、并发采集、gzip+base64 原始 `__NEXT_DATA__` 证据包、离线解析和结构漂移门禁。
- AXA run_id=16，2025 年，50 产品、1155 条，315 条数值、840 条官网占位原文；FWD run_id=17，2025 年，70 产品、2552 条，345 条数值、2207 条官网占位原文。
- 真实库分红履行率累计 8 家、10696 条；`--run-all --no-network` processed=11/succeeded=11/failed=0；SQLite `integrity_check=ok`、`foreign_key_check=[]`。
- 新增 T013 聚焦测试并更新 T009 支持矩阵；T002-T013 共 10 套回归全部通过。
- 自审结论：通过。独立复核尚未执行：DeepSeek 会把限定范围源码/SQLite 统计发送到外部 API，安全门禁要求 Jasper 明确知情授权。
