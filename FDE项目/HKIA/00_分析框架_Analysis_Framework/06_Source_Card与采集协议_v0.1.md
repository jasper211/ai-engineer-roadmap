# Source Card 与采集协议 v0.1

## 1. Source Card 模板

```yaml
source_id: SRC-REG-IA-LTQ
name: IA长期业务季度临时统计
publisher: Insurance Authority Hong Kong
source_class: S1_regulatory_structured
channels: [website, excel]
themes: [T00, T01, T02, T10, T11, T12, T13, T20, T21]
acquisition:
  mode: manual_current
  target: automated_future
  update_pattern: quarterly
access_policy:
  public: true
  authentication: none_or_site_challenge
  automation_review_required: true
quality_profile:
  authority: primary_official
  proximity: primary
  method_transparency: high_with_schema_breaks
  reproducibility: high
evidence_permissions: [fact, regulatory_event]
status: active
```

## 2. Asset Card 最低字段

每次下载或读取产生一个 Asset Card：

| 字段 | 含义 |
|---|---|
| asset_id | 唯一ID |
| source_id | 来源登记 |
| canonical_url | 具体发布页/文件URL |
| title | 原始标题 |
| author/publisher | 作者和发布主体 |
| published_at | 发布时间 |
| collected_at | 采集时间 |
| content_type | xls/xlsx/html/pdf/post/video/image等 |
| language | 语言 |
| storage_path | 不可变原始快照位置 |
| checksum | 内容哈希，用于去重与版本判断 |
| parent_asset_id | 转发、引用、修订关系 |
| access_method | manual/browser/API/connector |
| rights_status | allowed/restricted/unknown |
| parse_status | pending/success/partial/failed |
| themes | 初步主题路由 |

## 3. 标准采集流程

```text
发现候选来源
→ 权限与价值评估
→ Source登记与批准
→ 生成采集计划
→ 获取Asset
→ 保存原始快照与哈希
→ 去重/版本关联
→ 解析
→ 主题路由
→ Fact/Opinion/Experience抽取
→ 质量与证据准入
```

采集成功只说明资料已保存，不代表事实已经验证。

## 4. 不同渠道的采集协议

### 官方文件/API

- 优先API/结构化下载；否则浏览器自动化或人工下载。
- 保存发布页与文件两个Asset，建立父子关系。
- 检查期间、版本和格式变更。

### 公众号/行业媒体

- 优先用户授权转存、官方可访问页面、RSS或合法连接器。
- 保存标题、作者、公众号、日期、原文链接和可引用快照。
- 区分原创、转载和二次整理；追踪最早来源。
- 若访问条款不允许自动保存全文，只保存允许的元数据、摘要和用户提供内容。

### LinkedIn/专家动态

- 优先官方API、已安装连接器或用户授权的浏览器会话。
- 保存作者身份、任职时间、发布日期、原帖URL和编辑版本。
- 转发与评论不作为独立原始证据；记录其引用链。
- 观点进入Expert Opinion，不自动进入Fact。

### 公司披露

- 优先投资者关系官网、监管公告和正式PDF。
- 区分经审计数字、管理层目标和营销表述。
- 公司改名、集团与法人实体需绑定Entity Registry。

### 内部/老板知识

- 通过访谈、会议纪要或知识库连接器进入。
- 原文按权限存储；公开报告只引用允许披露的内容。
- 抽取为Experience Card：规则、情境、案例、反例、置信度、维护人。

## 5. 去重与版本协议

去重分四层：

1. **文件重复**：checksum一致。
2. **URL重复**：canonical URL一致但参数不同。
3. **转载重复**：正文高度相似且引用同一原始来源。
4. **事实重复**：多个Asset引用同一个监管数字。

重复资料保留关系，不重复增加“独立证据数量”。修订版Asset通过 `supersedes` 关联旧版，不覆盖旧版。

## 6. 冲突处理

当两个来源冲突：

1. 先检查期间、对象、单位和口径；
2. 检查是否同一原始来源的转述错误；
3. 比较来源接近度与方法透明度；
4. 保留双方，不静默选择；
5. 创建 `evidence_conflict`，记录待解决条件；
6. 在解决前限制相关命题进入确定性标题。

## 7. Source Scout Agent 边界

### 可以自动做

- 按已批准Source检查更新；
- 下载允许获取的Asset；
- 写入元数据、哈希和采集状态；
- 识别明显重复、转载与版本变化；
- 根据Theme Registry做初步路由；
- 提醒访问失败和新来源候选。

### 必须人工确认

- 新来源是否纳入长期监测；
- 权限不清内容是否允许自动获取；
- 作者是否具有相关行业身份；
- 转载关系和原创性存在争议时的裁定；
- 内部资料的披露权限。

## 8. 采集质量指标

| 指标 | 含义 |
|---|---|
| source_coverage | P0 Theme是否有第一来源 |
| collection_success | 计划Asset成功获取比例 |
| freshness_lag | 发布到入库的时间差 |
| provenance_complete | 核心元数据完整率 |
| duplicate_rate | 重复或转载比例 |
| parse_success | 完整/部分/失败比例 |
| evidence_admission | Asset转成有效Fact/Opinion的比例 |
| access_incidents | 权限、登录、条款或抓取失败事件 |

指标用于评估流水线，不用于证明分析结论正确。

