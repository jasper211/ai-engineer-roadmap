#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ppt_config.py — PPT生成阶段的集中配置。

设计原则（吸取旧版update_ppt.py的教训——业务线顺序清单散落4处、互相矛盾）：
凡是"业务口径"类的常量只在这里定义一次，build_slideN() 里禁止再本地重复定义。
能从数据动态读取的值（年度目标、月度预测路径）不在这里硬编码字面量，
统一从CSV/配置文件读取，找不到就报错，不用旧代码那种"猜一个默认值"的兜底方式。
"""

# 8项业务细分标准顺序，跟 s2_business_view.py::SEGMENT_GROUPS 保持一致
# （Jasper已确认口径，见settings.json migration_note）。
# 旧模板的热力矩阵(HEAT_ORDER)只写了7项、漏了IFA业务，是活的bug——
# 新版本任何用到"业务线顺序"的地方一律用这8项，不再各处各写一份。
SEGMENT_ORDER = [
    "天领业务", "成事家办", "BK业务", "同行经代",
    "永明经代", "合伙转介业务", "ICLUB业务", "IFA业务",
]

SEGMENT_TARGET_CODE = {
    "天领业务": "SLC", "成事家办": "GTD", "BK业务": "BK", "同行经代": "BRK",
    "永明经代": "SLBRK", "合伙转介业务": "REF", "ICLUB业务": "ICLUB", "IFA业务": "IFA",
}

# K节"同行"=segment IN(永明经代,同行经代[含MGA])，跟s2_business_view.py一致
PEER_SEGMENTS = ["永明经代", "同行经代", "MGA业务"]

# 旧模板7业务线配色（来自apply_w14_patches.py::Config.heat_row_colors）
SEGMENT_ROW_COLORS = {
    "天领业务":    (0xB6, 0xCC, 0xDC),
    "成事家办":    (0xE4, 0xE4, 0xE4),
    "BK业务":     (0xA5, 0xAD, 0xC8),
    "同行经代":    (0xF4, 0xC2, 0x9F),
    "永明经代":    (0x9D, 0xC5, 0xB0),
    "合伙转介业务": (0xE8, 0xE8, 0xE8),
    "ICLUB业务":  (0xCF, 0xB8, 0xDE),
    # IFA业务：旧模板没有这行的配色（旧热力矩阵漏了这个业务线），
    # 这里先给一个跟其余低饱和度色系接近的占位值，正式上线前需要Jasper确认视觉规范。
    "IFA业务":    (0xD8, 0xC7, 0xB0),
}

TEMPLATE_FILE = "template.pptx"

# S3新版CSV文件名前缀（不含_ape/_count后缀），驱动同行/银行周度→月度聚合
S3_PEER_WEEKLY_LETTERS = {"预约": "J", "签单": "K", "批核": "L"}
S3_BANK_WEEKLY_LETTERS = {"预约": "M", "签单": "N", "批核": "O"}

# --- 以下值旧版是Python字面量硬编码，本版本刻意不给默认值 ---
# 5-12月批核APE月度预测路径（旧代码硬编码 [80.0,88.0,95.0,...]，无任何来源注释）：
# 这是业务侧的规划输入，不是可以从历史数据反推的量，必须由Jasper提供，
# 否则第2页"批核路径管控"图的预测区间没有依据。取值前先跟Jasper确认。
FORECAST_PATH_SOURCE = "待Jasper提供：5-12月各月批核APE预测目标（原MIN_LINE=69.5同类输入）"
