# HKIA 原始文件存放处

从 IA 官网"長期業務季度發表的臨時統計數字"（`market_7_{year}.html`）人工下载的 13 份 Excel 文件放这里，**保留官网原始文件名**（下载时浏览器默认建议的名字就是下面这些，直接存，不用改名）。

这个目录是 HKIA 的专属工作区（对应 SOP 第7步"接入记忆"的隔离原则），不跟其他 Agent/项目共用。

## 期待的 13 个文件（2023 Q1 ~ 2026 Q1）

| 年份 | Q1 | Q2 | Q3 | Q4 |
|---|---|---|---|---|
| 2023 | `1q23long.xls` | `2q23long.xls` | `3q23long.xls` | `4q23long.xls` |
| 2024 | `1q24long.xls` | `2q24long.xls` | `3q24_long.xlsx`（注意有下划线，且已是新版格式） | `4q24long.xlsx` |
| 2025 | `1q25long.xlsx` | `2q25long.xlsx` | `3q25long.xlsx` | `4q25long.xlsx` |
| 2026 | `1q26_long.xlsx`（注意有下划线） | — | — | — |

共 13 份。**文件名本身不统一是官网真实情况**（2023~2024Q2 是老版 `.xls`，2024Q3 起换成新版 `.xlsx`，个别期数文件名多了下划线）——这不是下载错了，就是官网本来这么乱，保留原名即可，解析脚本会按真实文件名处理，不假设统一模式。

对应的期末日期 / 累计口径标注：

| 期数 | 期末日期 | `period_type` |
|---|---|---|
| Q1 | 3月31日 | `YTD_Q1` |
| Q2 | 6月30日 | `YTD_H1` |
| Q3 | 9月30日 | `YTD_9M` |
| Q4 | 12月31日 | `YTD_FY` |

## 下载入口

<https://www.ia.org.hk/tc/infocenter/statistics/quarterly_release_of_provisional_statistics_for_long_term_business.html> → 点年份 → 点各期的 [EXCEL] 链接。
