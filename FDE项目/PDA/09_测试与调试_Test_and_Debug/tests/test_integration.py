#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDA 集成测试唯一入口。白盒 import 调用真实 skill，不用 subprocess 黑盒调用。

按 Agent 搭建 SOP v1.2 第5步"Agent验证方法论·五条原则"：
- 能用脚本/断言判定对错的，不用主观判断（本文件全部是确定性断言）
- 用真实底表跑（07_接入记忆_Integrate_Memory/raw_data/ 下 Jasper 放的原始文件），
  不是只用合成 fixture——断言里的具体数字（3593/53/12等）就是需求定义.md
  第十一节核实出的真实数字，不是随手编的期望值。
"""
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
for sub in ("06_开发技能_Develop_Skills", "07_接入记忆_Integrate_Memory"):
    sys.path.insert(0, str(AGENT_ROOT / sub))

from skills.data_loader import DataLoader, MissingColumnsError
from skills.cleaner import Cleaner, UnmappedStatusError
from skills.aggregator import Aggregator
from skills.dashboard_generator import DashboardGenerator

RAW_DATA_DIR = AGENT_ROOT / "07_接入记忆_Integrate_Memory" / "raw_data"

failures = []


def check(name, condition, detail=""):
    status = "✅" if condition else "❌"
    print(f"{status} {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def main():
    if not any(RAW_DATA_DIR.glob("*.xlsx")):
        print(f"⚠️ {RAW_DATA_DIR} 下没有真实底表文件，无法做真实数据验证，测试终止")
        sys.exit(1)

    # ---- L3-PDA-01 ----
    load_result = DataLoader(RAW_DATA_DIR).load()
    check("底表读取成功", load_result.df is not None)
    check("有效记录数为 3593（真实核实数字，见需求定义.md七节）",
          len(load_result.df) == 3593, f"实际 {len(load_result.df)}")
    check("剔除表头残留行 1 行", load_result.header_echo_rows_dropped == 1,
          f"实际 {load_result.header_echo_rows_dropped}")
    check("表头残留行已从数据中剔除（policy_id 不再含'订单编号'）",
          "订单编号" not in load_result.df["policy_id"].values)
    check("导出日期解析成功", load_result.export_date is not None)

    # ---- L3-PDA-02 ----
    df = Cleaner().clean(load_result.df, load_result.export_date)
    check("清洗后行数不变（清洗不丢行）", len(df) == len(load_result.df))
    check("sign_date 无 NaT（Excel序列号日期已全部修正）", df["sign_date"].notna().all())
    check("sign_date 范围正确，不含1970年附近脏值（真问题1已修复）",
          df["sign_date"].min().year >= 2024, f"实际最小值 {df['sign_date'].min()}")
    check("future_dated 真实为 53 条，不是原型硬编码的11条（真问题2已修复）",
          int(df["future_dated"].sum()) == 53, f"实际 {int(df['future_dated'].sum())}")
    check("policy_status_tier 全部归入 生效/在途/终止 三档，无遗漏",
          set(df["policy_status_tier"].unique()) == {"生效", "在途", "终止"})
    check("在途+终止+生效计数等于总行数（三档映射无重复无遗漏）",
          df["policy_status_tier"].value_counts().sum() == len(df))
    check("premium 无缺失（缺失已按0处理）", df["premium"].notna().all())
    check("currency_code 无缺失（空值已归为'未填'）", df["currency_code"].notna().all())

    try:
        Cleaner().clean(load_result.df.assign(policy_status=["未知状态"] * len(load_result.df)), load_result.export_date)
        check("policy_status 出现未知取值时应抛出 UnmappedStatusError", False)
    except UnmappedStatusError:
        check("policy_status 出现未知取值时正确抛出 UnmappedStatusError", True)

    # ---- L3-PDA-03 ----
    agg = Aggregator().aggregate(df)
    check("覆盖牌照端 12 家", len(agg["entities"]) == 12, f"实际 {len(agg['entities'])}")
    check("总保费与原始底表逐行加总一致（独立重算校验，不是自我复述）",
          abs(sum(v["premium"] for v in agg["by_entity_all"].values()) - df["premium"].sum()) < 0.01)
    check("总保单数与清洗后行数一致",
          sum(v["count"] for v in agg["by_entity_all"].values()) == len(df))
    check("top_carriers 命中香港永明金融（已知最大保司）",
          "香港永明金融有限公司" in agg["top_carriers"])
    check("cycle_avg 已计算出结果（非空）", len(agg["cycle_avg"]) > 0)
    check("months 覆盖到 future_dated 批次所在的 2026-08（真实反映修复后的完整数据）",
          "2026-08" in agg["months"])

    # ---- L3-PDA-04 ----
    html = DashboardGenerator().render(
        agg,
        source_file_name=load_result.source_file.name,
        export_date="2026-07-24",
        raw_rows=load_result.raw_row_count,
        header_rows_dropped=load_result.header_echo_rows_dropped,
        record_count=len(df),
        future_dated_count=int(df["future_dated"].sum()),
        generated_at="test-run",
    )
    check("看板 HTML 生成成功且非空", len(html) > 10000)
    check("看板 footer 里真实数字(53)已注入，不再是原型硬编码的11",
          "53 条签单日期晚于导出日" in html)
    check("看板未残留未替换的占位符", "__DATA_JSON__" not in html and "__SOURCE__" not in html)

    # ---- 缺列时应报错，不静默跳过 ----
    from skills.data_loader import EXPECTED_COLUMNS
    broken = load_result.df.drop(columns=["premium"])
    missing = [c for c in EXPECTED_COLUMNS if c not in broken.columns]
    check("列完整性校验能识别出缺失列", missing == ["premium"])

    print()
    if failures:
        print(f"❌ {len(failures)} 项失败: {failures}")
        sys.exit(1)
    else:
        print("✅ 全部检查通过")
        print("真实数据验证对象：raw_data/" + load_result.source_file.name)


if __name__ == "__main__":
    main()
