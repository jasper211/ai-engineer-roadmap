# PPT生成 · 旧流水线映射与新架构设计 v0.1

> 来源：对 `07_接入记忆_Integrate_Memory/raw_data/业绩报表PPT/` 下11746行旧代码（`update_ppt.py`
> 5320行 + `apply_w14_patches.py`914行 + `final_gap_patch.py`1039行 + 若干辅助模块 + 5个按周硬编码的
> `update_sowhat_*.py`历史补丁 + `build_slide12_13.py`/`build_s9_slides.py`）做的逐文件通读分析，
> 目的是为新的 Agent 化 PPT 生成技能（`06_开发技能_Develop_Skills/skills/`）提供架构依据。
> 分析方法：Agent逐段读完9个主流水线文件，浏览5个历史补丁+2个扩展页面文件，并核对新旧CSV表头。

## 0. 总体结论

旧代码不是可复用的"引擎"，是**同一份PPT被逐周手工打补丁演化出的操作日志**：
- 多处逻辑被实现2-3遍仍在生产路径里跑，只有最后一次生效，前面的是冗余死代码
  （Slide3 TOP10产品表：`update_ppt.py`用错列名`折扣`，静默失效；真正生效的是`final_gap_patch.py`用对了`首年折扣`）
- "So What"规则式文案生成器（`sowhat_generators.py`）6月26日起被团队弃用，改成人工撰写后硬编码进
  `update_sowhat_0626~0717.py`五个补丁——说明纯规则文案在实战中撑不住，**新版应该用LLM生成**
- 全文件依赖EMU绝对坐标+字符串精确匹配，换模板/换周次数据格式大概率整套失效

**可复用的是设计模式和少数工具函数，不是整体代码。**

## 1. 死代码/冗余清单

| 位置 | 状态 |
|---|---|
| `update_ppt.py` 3157-3287行 + 3587-3711行（Q/R/S热力矩阵前两次克隆） | 冗余，被`final_gap_patch.py`第三次整体重画覆盖 |
| `update_ppt.py` 3713-3825行（Slide3 TOP10表，`rec.get("折扣","")`） | 静默失效死代码，列名应为`首年折扣` |
| `update_ppt.py` G牌照表写3次（内存态/坐标态/post-save zip patch） | 前两次基本被第三次覆盖 |
| `apply_w14_patches.py::patch_heat_matrix()`（170行） | 完全不可达，依赖不存在的`热力图.pptx` |
| 5个`update_sowhat_*.py`（约370行） | 纯历史存档，人工手打文案，无复用价值 |
| `build_slide12_13.py`/`build_s9_slides.py`（2137行，经`run_full_deck.py`调用生成第12-14页） | 不在11页模板范围内；完全不读CSV，直接读原始Excel+matplotlib画PNG贴图，与主链路脱节 |

## 2. 逐页映射表（11页模板全覆盖）

| 页 | 标题 | 用到的S板块 | 生效函数 |
|---|---|---|---|
| 1 | 全维度业绩分析仪表盘 | S1-A/B/C/D/E/G | `chart_updates.py`初始化 + `update_ppt.py::_patch_s1_monthly_trend`覆盖 |
| 2 | 月度效能深析(F批核路径) | S1-A/C/D/E/F | `update_ppt.py::_fix_f_chart_may_and_forecast`；**5-12月预测值硬编码常量** |
| 3 | 永明业绩汇报(Sun Life) | S1-A/H，S2-F/G/H-APE，S4-C | `final_gap_patch.py::patch_license_table`/`patch_top10_table`（最终生效） |
| 4 | 业务端视角(缺口分解) | S2-A，S1-B，S2-C/D/E-APE | `update_ppt.py`（气泡图/瀑布图坐标硬编码） |
| 5 | 业务端视角仪表盘 | S2-A | `update_ppt.py::_patch_L_segment_chart` + `chart_updates.py` |
| 6 | 执行管理端 第1部分 | S3-A-APE/件数，S2-I | `update_ppt.py`；**P表TOP10需自己排序+自己算合计（新CSV无此列）** |
| 7 | 执行管理端 第2部分 | S3-B/C/D-APE/件数，S3-G | `final_gap_patch.py::rebuild_heat_matrix_on_slide7`/`update_t_table` |
| 8 | 同行业绩 第1部分 | S2-J/K/L-APE | `update_ppt.py::_build_peer_ka_table_data`（残差补齐算法） |
| 9 | 同行业绩 第2部分 | S3-J/K/L-APE，**S2-L/M/N-APE/件数(新CSV缺失)** | `apply_w14_patches.py::patch_weekly_deck` |
| 10 | BK业务 第1部分 | **S2-P/Q/R-APE(新CSV缺失)**，S2-O，S2-A | `chart_updates.py` |
| 11 | BK业务 第2部分 | S3-M/N/O-APE/件数，S2-S-APE | `update_ppt.py::_update_ac_table` |

完整逐模块表格（含每个KPI卡片/图表/表格的具体计算口径）见对话记录中Agent报告全文，或按需重新生成。

## 3. 关键缺口（阻塞项，实现前必须解决）

1. **S2旧版 L/M/N(同行月度)、P/Q/R(银行月度)在新版CSV完全不存在**（新S2只有A-K/O/S/T共14个文件）。
   驱动第9页"W月度分析表"+第10页"Z银行月度走势图"。
   建议方案：用`apply_w14_patches.py::derive_monthly_buckets`（ISO周→月分桶算法，可直接复用）对新版
   S3的J/K/L_ape.csv（同行周度）、M/N/O_ape.csv（银行周度）做周→月聚合，不必依赖S9。
2. **S2旧版-I(KA TOP20)有"排名"/"合计APE"/"合计件数"列，新版S2/I.csv没有**，新Agent需自己按
   `2026批核APE`降序排序、自己算合计。
3. **业务线顺序清单在旧代码里4处重复定义且互相不一致**：`HEAT_ORDER`(7项，漏了IFA业务)
   vs `T_TABLE_ROW_ORDER`(8项，含IFA)。经核对 `s2_business_view.py::SEGMENT_GROUPS`
   （已被Jasper确认的口径），**标准应为8项（含IFA业务）**，旧热力矩阵漏了IFA业务是活的bug，
   新版必须统一成8项业务线，不能沿用7项版本。
4. **新旧CSV文件组织方式不同**：新版是"一个字母板块一个CSV文件"（部分拆成`_ape`/`_count`两个文件），
   旧版是"一个S表一个CSV、内部用`A. `字母块头分隔多个板块"。新Agent的加载层需要重写，
   不能沿用`data_loader.py`的字母块头解析（那是给旧格式设计的，新格式直接`pd.read_csv`更简单）。

## 4. 硬编码风险清单（新版本必须参数化掉）

- 周次/日期默认回退值（`"W18"`/`"W14"`）、具体周文件名
- 5-12月批核预测目标 `[80.0,88.0,95.0,100.0,100.0,100.0,100.0,96.0]`（无任何来源注释）
- `MIN_LINE=69.5`节奏基准线、年度总目标`1113`(M)直接写成字面量除数
- 几百处EMU绝对坐标（模板稍作排版调整就会静默失效）
- Sun Life牌照表固定6行坐标（历史上曾因漏行导致下方全部错位）

## 5. 新Skill模块划分建议

1. **`s_data_loader.py`** — 按S{n}文件夹读取，兼容两种新CSV命名规则；复用`data_loader.py::num()`
   （数值清洗容错）和`_read_text_any_encoding()`（多编码兜底）。
2. **`ppt_page_builder.py`**（或每页一个小模块）— 每页一个`build_slideN()`函数。
   图表写入复用`chart_xml_patch.py::patch_chart`/`patch_chart_dlbls`（全代码库里最通用、
   不依赖具体模板的部分，直接操作`<c:numCache>`/`<c:strCache>`）。
3. **定位机制**：弃用EMU绝对坐标，改用`apply_w14_patches.py`里`find_slide_with_all`/
   `find_table_by_header`/`iter_charts`这套"结构化发现"范式（按标题关键词/表头文字/图表类别找，
   而不是硬编码坐标）——这是旧代码库里唯一体现参数化思想的部分。
4. **`sowhat_llm.py`** — 抛弃规则拼句，保留`sowhat_generators.py`里"找最大值/算占比/算环比/算缺口"
   的纯计算逻辑，把结构化数字交给LLM生成叙事文案。So What文本框定位建议模板阶段就用固定shape name。
5. **配置层** — `MIN_LINE`/年度目标/预测月度目标/8项业务线顺序清单统一提到YAML/JSON，
   不散落在Python字面量里。

### 可直接复用的函数
`data_loader.py::num()` / `_read_text_any_encoding()`；`chart_xml_patch.py`全文件；
`heatmatrix_cloner.py`（克隆逻辑，但建议改用"整体重画"策略）；
`apply_w14_patches.py::load_rows/_find_section_start/_find_header_row/parse_section_weekly_all/
parse_section_records/derive_monthly_buckets/find_slide_with_all/find_table_by_header/iter_charts`；
`sowhat_generators.py`各`gen_*`函数的取数逻辑（不含拼句部分）。

### 不建议复用的部分
`update_ppt.py`全部EMU坐标+字符串替换模块；`build_slide12_13.py`/`build_s9_slides.py`的
matplotlib+PNG渲染；5个`update_sowhat_*.py`；post-save zip直接改pptx包的应急补丁
（若新模板不保留OLE外部Excel链接，这类补丁不需要存在）。

---
记录时间：2026-09-29，基于对旧流水线代码的完整通读分析
