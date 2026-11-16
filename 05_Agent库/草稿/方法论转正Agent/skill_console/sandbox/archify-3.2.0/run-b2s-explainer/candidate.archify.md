# book-to-skill 能把内部手册做成可查的技能吗？ {#b2s-verdict}

**能，但 Word 手册要人工补两步。** 用 EE 方法论手册试点，按章节问答答对，表格内容全部逐字保真。

- 生成 1 份主文件和 10 章，安全扫描和格式校验都通过。[](source:release)
- 测试题「G2 的通过条件」答对，3 处依据与手册原文一致。
- Word 的表格会被挪到文末，中文章标题也识别不出，需要宿主模型对回章节。

@answer scope="book-to-skill v1.4.0 · EE 方法论手册 v1.0 · 沙箱试点 2026-11-12 · 未在实际项目使用"
@meta locale=zh-CN style=editorial
@source release title="book-to-skill v1.4.0 发布页" url=https://github.com/virgiliojr94/book-to-skill/releases/tag/v1.4.0
@source repo title="book-to-skill 仓库" url=https://github.com/virgiliojr94/book-to-skill

## 试点是怎么跑的？ {#pipeline}

@workflow id=b2s-flow title="book-to-skill 试点流程"
| lane prep | 准备 |
| lane build | 生成 |
| lane check | 检查 |
| extract | 抽取正文 | backend | prep |
| split | 按标题切章 | backend | prep |
| write | 生成技能文件 | backend | build |
| scan | 安全扫描 | security | check |
| validate | 格式校验 | security | check |
| ask | 按章问答 | frontend | check |
| extract > split | |
| split > write | |
| write > scan | |
| scan > validate | 通过 |
| validate > ask | 通过 | emphasis |

@steps id=flow-steps
| s1 | 抽取正文 | 运行 extract.py，得到 326 行正文；23 张表全部落在文末。 | b2s-flow | extract |
| s2 | 按标题切章 | 工具识别不出「一 使用范围」这类标题，改由宿主模型按 Word 标题样式切章，并把表格逐张对回。 | b2s-flow | split |
| s3 | 生成技能文件 | 产出主文件、10 章、术语表、方法清单和速查表，共 14 个文件。 | b2s-flow | write |
| s4 | 安全扫描 | 运行 scan_generated_skill，未发现问题。 | b2s-flow | scan |
| s5 | 格式校验 | 运行 validate_skill，0 警告。 | b2s-flow | validate |
| s6 | 按章问答 | 问 G2 通过条件，技能从主题索引找到第 8 章作答。 | b2s-flow | ask |

## 生成的内容可信吗？ {#fidelity}

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| 表格单元格 | 全部逐字匹配 {good:保真} | 从手册表格搬来的内容都能在原文找到 |
| G2 问答依据 | 3 处与原文一致 {good:答对} | 最低证据、允许结论、D 加七时点 |
| 章节示例 | 手册没有，工具补写 {caution:需标注} | 已统一标「示意，非手册原文」 |
| 启动验收项数 | 实为 10 项 {caution:顺带纠错} | 表格 11 行含 1 行表头，速查表曾误写 11 项 |

## 哪些问题要人工处理？ {#defects}

| 问题 | 影响 | 处理办法 |
| --- | --- | --- |
| 表格挪到文末 | 七态、Evidence 分级、Gate 条件都在表里 | 宿主模型逐张对回所属章节 |
| 中文章标题识别不出 | 章节数显示为 0 | 按 Word 标题样式手工切章 |
| 补写示例像原文 | 读者可能当成手册规定 | 每处示例标注「非原文」 |

@callout level=warning title="适用边界"
这三处问题只在 Word 文档上出现；PDF、EPUB 未在本次试点中验证。

## 换一份手册时要检查什么？ {#checklist}

- [ ] 抽取后核对表格数，确认每张表都对回了所属章节。
- [ ] 核对章节数，为 0 时按标题样式手工切章。
- [ ] 每处补写的示例都标注「示意，非手册原文」。
- [ ] 运行 scan_generated_skill 和 validate_skill，两项都通过。
- [ ] 用一道已知答案的问题测试，依据要能在原文逐字找到。
