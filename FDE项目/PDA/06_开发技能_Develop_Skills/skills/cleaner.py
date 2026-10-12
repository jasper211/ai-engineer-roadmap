#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能：清洗标准化底表 DataFrame。

对应 流程设计.md L3-PDA-02。修复需求定义.md 第十一节核实出的 2 个真实 bug：
- 【真问题1】res_date/sign_date/submit_date/issue_date 混有 Excel 序列号整数，
  朴素 pd.to_datetime 会静默解析成 1970 年附近的错误时间戳。
- 【真问题2】future_dated 用文件名解析出的导出日期动态判断，不再硬编码某个日期。

v0.19.0新增【真问题3】实体别名（简繁体）归一化：issuing_entity 列里同一家公司因为
简繁体写法不同被当成两个不同实体分别统计，导致下游全部 S1-S9 聚合（都是围绕
issuing_entity 分组）把同一家公司的数据拆散成两行、各自都不完整。核实过程：
1. 同事 Mark 的《标准报表》第3页"永明内部牌照明细"原文明确把"九富保险服务有限公司"/
   "九富保險服務有限公司"、"怡泰财富管理有限公司"/"怡泰財富管理有限公司"列成两行分别
   统计，备注"保留源名称"（即 Mark 自己也知道这是同一家公司，但选择不合并、只在"内部
   合计"行手工加总），这是业务方自己承认问题存在的直接证据。
2. 用权威生成脚本 generate_report.py 的 LICENSES_BASE 常量（9个牌照基础名单，Carrie
   本人维护、经 S1-S4 CSV 验证过的权威口径）逐字核对：9个名字全部是简体，其中5个在
   本项目1009底表里确认存在"简体版+繁体版同时出现"的情况（逐字符diff，差异字符均为
   标准简繁字符对：财/財、险/險+务/務、众/眾、强/強，长度和其余字符完全一致，不是
   泛泛的"名字相似"）：
     怡泰财富管理有限公司(748条) / 怡泰財富管理有限公司(335条)
     九富保险服务有限公司(442条) / 九富保險服務有限公司(723条)
     众和恒富理财集团有限公司(631条) / 眾和恒富理财集团有限公司(595条)
     富强天一财富管理有限公司(17条) / 富強天一财富管理有限公司(9条)
     置富理财(香港)有限公司(19条) / 置富理財(香港)有限公司(7条)
   归一化目标统一选 LICENSES_BASE 里的简体全称（官方权威口径），不是"频次更高的那个"
   ——九富的繁体版本实际记录数(723)反而比简体版本(442)多，如果按频次规则会选错方向，
   选官方全称更可靠也更面向未来（generate_report.py 今后只会继续产出简体）。
3. 另发现一组名字结构完全不同（非简繁字符替换、长度都不同）的疑似对子"唯思管理有限
   公司"(3条，恰好是LICENSES_BASE官方名)/"唯思财富顾问有限公司"(4条)——逐字符diff显示
   6个字符全部不同，不是简繁体变体，可能是真实改名或两个不同主体，本版本**不**归一化，
   作为开放项留给Jasper/业务侧确认（见settings.json known_limitations，数据量也小，
   共7条不影响任何大盘数字）。
4. 环境没有可用的 opencc 简繁转换库（pip 安装被系统 Python 的 externally-managed-
   environment 策略拦截，未strong-arm用--break-system-packages绕过），改用逐字符diff
   人工核验替代——每一对都满足"长度相同+仅差已知标准简繁字符对"，核验结果可重现
   （见本文件对应测试 test_integration.py 的归一化断言）。
- 【真问题4】raw底表carrier_code列也存在"中国太平保险（澳门）有限公司"vs"澳门太平"、
  "永明金融有限公司(新加坡)"等看似相似但核实后是不同法律主体的名称（非简繁变体，
  是新加坡永明 vs 香港永明两家不同公司、"澳门太平"和"中国太平保险(澳门)"字面都不同、
  经核对 generate_report.py 的 CARRIERS_FULL 常量未发现"澳门太平"在当前数据里出现，
  判断是两个不同的历史命名，不是本次归一化范围），carrier_code本版本不做归一化，
  只记录核实过程（见settings.json）。key_account 列逐一人工审查未发现任何简繁重复。
"""
import datetime as dt

import pandas as pd

DATE_COLUMNS = ["res_date", "sign_date", "submit_date", "issue_date"]

EXCEL_EPOCH = dt.datetime(1899, 12, 30)

# issuing_entity 简繁体别名归一化表：繁体/变体写法 -> 官方简体全称
# 官方全称口径来自 raw_data/generate_report_参考脚本/generate_report.py::LICENSES_BASE
# （Carrie维护的权威报表生成脚本的9个牌照基础名单，全部是简体）。
# 核实依据见本文件模块docstring第三段——5对均为"长度相同+仅差标准简繁字符对"，
# 其中2对（怡泰/九富）另有同事Mark《标准报表》第3页"保留源名称"备注的独立交叉确认。
ENTITY_ALIAS_MAP = {
    "怡泰財富管理有限公司": "怡泰财富管理有限公司",
    "九富保險服務有限公司": "九富保险服务有限公司",
    "眾和恒富理财集团有限公司": "众和恒富理财集团有限公司",
    "富強天一财富管理有限公司": "富强天一财富管理有限公司",
    "置富理財(香港)有限公司": "置富理财(香港)有限公司",
}

# 沿用阶段一原型 footer 已经写死的三档口径（需求定义.md 七、十一节），不是本次新发明
STATUS_TIER_MAP = {
    "生效": "生效",
    "待批核": "在途",
    "pending": "在途",
    "排期": "在途",
    "已签单": "在途",
    "尚欠保费": "在途",
    "取消投保": "终止",
    "退保": "终止",
    "搁置受保": "终止",
    "拒保": "终止",
}

# 全角/半角空格等"看起来空但不是NaN"的值，清洗时统一转空
BLANK_LIKE = {"　", " ", ""}


class UnmappedStatusError(Exception):
    """出现 STATUS_TIER_MAP 里没有的 policy_status 取值时抛出，不静默归类。"""


def _excel_serial_to_date(x):
    """把单元格值统一转成 Timestamp：int/float 按 Excel 序列号换算，
    datetime/date 直接用，其余（含空）返回 NaT。"""
    if pd.isna(x):
        return pd.NaT
    if isinstance(x, (dt.datetime, dt.date)):
        return pd.Timestamp(x)
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return pd.Timestamp(EXCEL_EPOCH + dt.timedelta(days=float(x)))
    return pd.NaT


class Cleaner:
    """接收 DataLoader 产出的原始 DataFrame，返回清洗后 DataFrame，不读写任何持久化状态。"""

    def clean(self, df: pd.DataFrame, export_date: "pd.Timestamp | None") -> pd.DataFrame:
        df = df.copy()

        for col in DATE_COLUMNS:
            df[col] = df[col].apply(_excel_serial_to_date)

        unknown_status = set(df["policy_status"].unique()) - set(STATUS_TIER_MAP)
        if unknown_status:
            raise UnmappedStatusError(f"policy_status 出现未知取值，需要补充映射规则: {unknown_status}")
        df["policy_status_tier"] = df["policy_status"].map(STATUS_TIER_MAP)

        if export_date is not None:
            df["future_dated"] = df["sign_date"] > export_date
        else:
            df["future_dated"] = False

        df["premium"] = pd.to_numeric(df["premium"], errors="coerce").fillna(0)
        df["ape"] = pd.to_numeric(df["ape"], errors="coerce").fillna(0)

        df["currency_code"] = df["currency_code"].where(df["currency_code"].notna(), "未填")

        df["sum_assured"] = df["sum_assured"].apply(
            lambda x: pd.NA if isinstance(x, str) and x.strip() in BLANK_LIKE else x
        )

        df["Is_Premium_Financing"] = pd.to_numeric(df["Is_Premium_Financing"], errors="coerce").fillna(0).astype(int)

        # 实体别名归一化（真问题3）：简繁体变体统一成官方简体全称，在所有下游
        # S1-S9聚合/aggregator之前完成，保证围绕issuing_entity的分组不再被
        # 简繁体拆散。只替换标签，不增删/不重复任何记录。
        if "issuing_entity" in df.columns:
            df["issuing_entity"] = df["issuing_entity"].replace(ENTITY_ALIAS_MAP)

        return df
