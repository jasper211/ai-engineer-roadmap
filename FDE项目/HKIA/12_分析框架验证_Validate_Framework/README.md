# Phase B｜分析框架验证

本目录不是报告交付区，而是把 Phase A 的对象规范放进真实运行中验证。

## Slice 01 的双轨目标

1. 监管轨：尝试接入 IA 年度长期业务 Table L5，验证 Source → Asset → Fact → Claim。
2. 经验轨：建立一张待人工填写的 Experience Card，验证 Experience → Research Question / Evidence Link。

## 当前状态

- IA Table L5 已从统计总入口定位至2024年度详情页，并通过页面会话取得官方XLSX。
- 直接请求附件仍返回HTTP 403，但这只说明直链采集方式不适用，不代表页面或数据不可读取。
- 官方XLSX已保存、重复下载校验和一致；非相连3.7%与相连7.0%已按G14/G25转为正式Fact。
- 已发现 IA 季度新闻稿存在 MCV 摘要，故把 T14 从 `missing` 校正为 `weak_partial`；新闻稿与季度 Excel 仍是两条证据链。
- Experience Schema 与空白实例已建立，等待一条真实行业经验，不由 AI 补写。

## Gate 结果

`G2_data_ready = pass`：L5原始XLSX已落库、校验并完成单元格级Fact登记。`G3_evidence`仍等待第一条真实行业经验。
