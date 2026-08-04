# Phase A 阶段门与评估规范 v0.1

## 1. 评估的四个层面

### 框架完整性

- Theme是否覆盖关键行业问题；
- Source是否有明确权限与证据边界；
- Fact/Claim是否可追溯；
- Spec是否可继承和熔断；
- Run是否记录角色、Gate和返工。

### 工程正确性

- ID唯一、引用有效；
- 状态转换合法；
- 必填字段完整；
- 确定性规则可执行；
- 版本变更有影响分析。

### 分析纪律

- 一个主Theme和主维度；
- 事实、观点和经验分离；
- A/B/C语言匹配；
- B级有替代解释和反证；
- 页面不突破数据颗粒度。

### 人机协作质量

- 人工责任点是否明确；
- Agent是否在不确定时停止；
- 用户纠正是否改变正式对象和规则；
- 失败是否转成预防检查；
- 没有把文件生成误当成工作完成。

## 2. Phase A完成条件

- [x] 总蓝图与缺口矩阵；
- [x] Theme Universe与Theme Registry；
- [x] Source Strategy与Source Registry；
- [x] Fact/Evidence/Claim元模型；
- [x] Spec Registry与Analysis Contract；
- [x] Agent Run Log、角色交接与Incident规范；
- [ ] 为全部机器对象建立正式Schema验证器；
- [ ] 由Jasper审核Theme、Source和Spec边界；
- [ ] 用Phase B垂直切片验证对象是否过多或缺失。

因此Phase A当前状态为：**设计骨架完成，待审阅和工程化验证，不宣称正式转正。**

## 3. Phase B准入条件

进入监管结构化数据切片前，需要：

1. T12 Theme Card被人工确认；
2. `SRC-REG-IA-LTQ`保持Active；
3. T12 Analysis Contract的G1签核；
4. 选定事实登记实现方式：旁路Registry或SQLite扩展表；
5. 定义首批原表locator粒度；
6. 指定Data Steward与Reviewer责任。

## 4. Phase B首个目标

不是重算更多图，而是将现有45期IA数据接入新对象链：

```text
Source Registry
→ 45个Asset Card
→ 关键行Fact ID与原表locator
→ Formula Registry
→ T12 Claim Graph
→ Page-to-Claim映射
→ 完整Run Log
```

完成后再重做Probe-01 v1.0，与早期单页比较过程质量差异。

