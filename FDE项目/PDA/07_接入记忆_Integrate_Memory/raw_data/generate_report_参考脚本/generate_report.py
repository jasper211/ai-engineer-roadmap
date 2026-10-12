#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
业绩分析报表生成脚本 V1.0
对应框架：V4.4  |  支持自动滚动月份/周次/保司/牌照

使用方法：
    python generate_report.py <CSV文件路径>
    python generate_report.py 业绩数据0414.csv
    python generate_report.py 业绩数据0414.csv --weeks W15   # 可选：指定最新周
    python generate_report.py 业绩数据0414.csv --output 报表.xlsx

自动滚动说明：
  每次更新CSV后直接运行脚本，以下内容自动更新：
  - 月度时间列：从2026-01滚动至CSV最新月（新月自动追加列）
  - 周度时间列：从2026W01滚动至最新周（新周自动追加列）  
  - 牌照列表：基础9个 + 数据中出现的新牌照自动追加
  - 保司列表：基础17家全列 + 数据中新保司自动追加末尾
  - 数据截止日：自动取issue_date最大值

依赖安装：
    pip install pandas openpyxl
"""

import sys
import os
import re
import argparse
import datetime
import pandas as pd
import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# ═══════════════════════════════════════════════════════════════════════
# 一、业务常量（修改目标值只需改此处）
# ═══════════════════════════════════════════════════════════════════════

SEGMENTS = ['天领业务','成事家办','BK业务','同行经代','永明经代',
            '合伙转介业务','ICLUB业务','IFA业务']

TARGET_ALL = {
    '天领业务':193_000_000, '成事家办':70_000_000,  'BK业务':200_000_000,
    '同行经代':160_000_000, '永明经代':340_000_000, '合伙转介业务':73_000_000,
    'ICLUB业务':52_000_000, 'IFA业务':25_000_000,
}
TARGET_YM = {
    '天领业务':135_100_000, '成事家办':56_000_000,  'BK业务':200_000_000,
    '同行经代':140_000_000, '永明经代':340_000_000, '合伙转介业务':51_100_000,
    'ICLUB业务':36_400_000, 'IFA业务':17_500_000,
}

YM_CARRIER = '香港永明金融有限公司'

# 固定17家保司（S4-A必须全列，含零业务）
CARRIERS_FULL = [
    '香港永明金融有限公司','中国人寿保险（海外）股份有限公司（香港）','万通保险国际有限公司',
    '香港安盛保险有限公司','中国人寿保险（海外）股份有限公司（澳门）','宏利人寿保险（国际）有限公司',
    '友邦保险（国际）有限公司','立桥人寿保险有限公司','中国太平洋保险（香港）有限公司',
    '周大福人寿保险有限公司','保诚保险有限公司','中银人寿保险有限公司','澳门太平',
    '保柏环球有限公司','富卫人寿保险（百慕大）有限公司','忠意保险有限公司','信诺环球保险公司',
]
CARRIER_SHORT = {
    '香港永明金融有限公司':'永明','中国人寿保险（海外）股份有限公司（香港）':'中国人寿',
    '万通保险国际有限公司':'万通','香港安盛保险有限公司':'安盛',
    '中国人寿保险（海外）股份有限公司（澳门）':'澳门中国人寿','宏利人寿保险（国际）有限公司':'宏利',
    '友邦保险（国际）有限公司':'友邦','立桥人寿保险有限公司':'立桥',
    '中国太平洋保险（香港）有限公司':'太平洋','周大福人寿保险有限公司':'周大福',
    '保诚保险有限公司':'保诚','中银人寿保险有限公司':'中银人寿','澳门太平':'澳门太平',
    '保柏环球有限公司':'保柏','富卫人寿保险（百慕大）有限公司':'富卫',
    '忠意保险有限公司':'忠意','信诺环球保险公司':'信诺',
}

# 固定9个牌照基础列表（简体字，与CSV一致）
LICENSES_BASE = [
    '怡泰财富管理有限公司','九富保险服务有限公司','众和恒富理财集团有限公司',
    '富强天一财富管理有限公司','盈富理财顾问有限公司','置富理财(香港)有限公司',
    '利泰丰财富管理有限公司','泰溢国际有限公司','唯思管理有限公司',
]

# 永明汇报行定义
SUNLIFE_ROWS = [
    ('JF',          lambda d: d['issuing_entity']=='九富保险服务有限公司'),
    ('UNIWIN',      lambda d: d['issuing_entity']=='众和恒富理财集团有限公司'),
    ('DW-Non-Bank', lambda d: (d['issuing_entity']=='怡泰财富管理有限公司')&(d['segment']!='BK业务')),
    ('DW Bank',     lambda d: (d['issuing_entity']=='怡泰财富管理有限公司')&(d['segment']=='BK业务')),
]

# ═══════════════════════════════════════════════════════════════════════
# 二、颜色常量
# ═══════════════════════════════════════════════════════════════════════

DARK_BLUE  = '1F3864'
MID_BLUE   = '2E74B5'
LIGHT_BLUE = 'F0F6FA'
LIGHT_YEL  = 'FFF2CC'
GRAY_TOT   = 'E7E6E6'
WHITE      = 'FFFFFF'
ORANGE_FLD = 'FCE5CD'

# ═══════════════════════════════════════════════════════════════════════
# 三、CSV读取与数据预处理
# ═══════════════════════════════════════════════════════════════════════

def excel_serial_to_date(val):
    """Excel序列号或字符串 → YYYY-MM-DD"""
    if pd.isna(val) or str(val).strip() in ('','nan','NaN'):
        return None
    try:
        n = float(val)
        if n > 1000:
            return (datetime.date(1899,12,30)+datetime.timedelta(days=int(n))).strftime('%Y-%m-%d')
        return None
    except Exception:
        pass
    try:
        return pd.to_datetime(str(val),errors='coerce').strftime('%Y-%m-%d')
    except Exception:
        return None

def get_week_code(date_str):
    """计算 YYYYWnn 周次（锚点=每年1月4日所在周日=W01）"""
    if not date_str or pd.isna(date_str):
        return None
    try:
        d = pd.to_datetime(date_str).date()
        year = d.year
        anchor = datetime.date(year,1,4)
        w01 = anchor - datetime.timedelta(days=(anchor.weekday()+1)%7)
        diff = (d-w01).days
        if diff < 0:
            py=year-1; ap=datetime.date(py,1,4)
            pw=ap-datetime.timedelta(days=(ap.weekday()+1)%7)
            return f"{py}W{(d-pw).days//7+1:02d}"
        return f"{year}W{diff//7+1:02d}"
    except Exception:
        return None

def load_csv(path):
    """读取CSV，自动处理编码/列名空格/日期格式，生成所有派生字段"""
    for enc in ('utf-8','utf-8-sig','gbk','gb18030'):
        try:
            df = pd.read_csv(path, encoding=enc)
            df.columns = [c.strip() for c in df.columns]
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"无法读取 {path}，请检查文件编码")

    if 'policy_status' in df.columns:
        df = df[df['policy_status']!='保单状态'].reset_index(drop=True)

    rename_map = {
        'policy_status':'status','business_category':'biz_type','segment_code':'segment',
        'market_segment':'market_seg','key_account':'ka','company_name':'company',
        'partner_code':'partner','carrier_code':'carrier','product_category':'product_cat',
        'product_id':'product','premium_term':'term','currency_code':'currency',
        'premium_orig':'premium_orig','premium':'premium_hkd','Is_Premium_Financing':'is_pf',
        'customer_type':'cust_type','SQ_rate':'discount_special','referral_code':'referral',
        'tr_register_number':'tr_reg','tr_name':'tr','tr_assistant_name':'tr_asst',
        'business_admin_name':'biz_admin',
    }
    df.rename(columns={k:v for k,v in rename_map.items() if k in df.columns}, inplace=True)

    for col in ('ape','premium_hkd','is_pf','sum_assured','premium_orig'):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col],errors='coerce').fillna(0)
    df['term'] = pd.to_numeric(df.get('term',pd.Series(dtype=float)),errors='coerce')

    for col in ('res_date','sign_date','submit_date','issue_date'):
        if col in df.columns:
            df[col] = df[col].apply(excel_serial_to_date)

    for col,prefix in [('sign_date','sign'),('issue_date','issue'),
                       ('res_date','res'),('submit_date','submit')]:
        if col in df.columns:
            dt = pd.to_datetime(df[col],errors='coerce')
            df[f'{prefix}_year'] = dt.dt.year
            df[f'{prefix}_ym']   = dt.dt.strftime('%Y-%m')
            df[f'{prefix}_yw']   = df[col].apply(get_week_code)

    df['tat'] = (pd.to_datetime(df.get('issue_date'),errors='coerce') -
                 pd.to_datetime(df.get('sign_date'), errors='coerce')).dt.days

    df['phase'] = df['status'].map(
        {'生效':'A','尚欠保费':'B','已签单':'B','pending':'B','待批核':'B','排期':'C'}
    ).fillna('D')

    biz_map={'天领业务':'代理人业务','成事家办':'代理人业务','BK业务':'经代业务',
             '同行经代':'经代业务','永明经代':'经代业务','合伙转介业务':'KA业务',
             'ICLUB业务':'KA业务','IFA业务':'KA业务'}
    df['biz_cat'] = df['segment'].map(biz_map).fillna(df.get('biz_type',''))

    def term_cat(t):
        if pd.isna(t): return None
        if t<=1: return '短期(≤1年)'
        if t<=5: return '中期(2-5年)'
        if t<=20: return '长期(6-20年)'
        return '终身(>20年)'
    df['term_cat'] = df['term'].apply(term_cat)
    df['pf_label'] = df['is_pf'].apply(lambda x:'融资' if x==1 else '常规')

    def prem_tier(p):
        if pd.isna(p): return None
        if p<50000: return '<5万'
        if p<200000: return '5-20万'
        if p<500000: return '20-50万'
        if p<1000000: return '50-100万'
        return '100万+'
    df['prem_tier'] = df['premium_hkd'].apply(prem_tier)

    def ape_tier(a):
        if pd.isna(a): return None
        if a<30000: return '<3万'
        if a<150000: return '3-15万'
        if a<400000: return '15-40万'
        if a<800000: return '40-80万'
        return '80万+'
    df['ape_tier'] = df['ape'].apply(ape_tier)

    print(f"  ✓ 数据加载：{len(df):,}条记录，最新批核：{df['issue_date'].max()}")
    return df

# ═══════════════════════════════════════════════════════════════════════
# 四、时间范围自动检测（自动滚动核心）
# ═══════════════════════════════════════════════════════════════════════

def get_months_2026(df):
    """从2026-01到数据最新月（自动滚动）"""
    all_m = set()
    for col in ('sign_ym','issue_ym','res_ym','submit_ym'):
        if col in df.columns:
            all_m.update(df[col].dropna().unique())
    return sorted([m for m in all_m if str(m)>='2026-01' and str(m)<='2099-12'])

def get_weeks_2026(df, force=None):
    """从2026W01到最新有数据的周，以res_yw（预约时间）最大周为上限，避免签单/批核未来日期产生空白列。"""
    # 以预约时间最大周为上限
    max_res_week = None
    if 'res_yw' in df.columns:
        res_weeks = sorted([w for w in df['res_yw'].dropna().unique() if str(w).startswith('2026W')])
        if res_weeks:
            max_res_week = res_weeks[-1]

    all_w = set()
    for col in ('sign_yw','issue_yw','res_yw','submit_yw'):
        if col in df.columns:
            all_w.update(df[col].dropna().unique())
    weeks = sorted([w for w in all_w if str(w).startswith('2026W')])

    # 截断到 res_yw 最大周
    if max_res_week:
        weeks = [w for w in weeks if w <= max_res_week]

    # --weeks 参数可进一步限制上限
    if force and force in weeks:
        weeks = [w for w in weeks if w <= force]
    elif force and force not in weeks:
        pass
    return weeks

def get_issue_months(df):
    return sorted([m for m in df[df['status']=='生效']['issue_ym'].dropna().unique()
                   if str(m)>='2026-01'])

def get_pending_months(df):
    mask = df['status'].isin(['尚欠保费','已签单','pending','待批核','排期'])
    return sorted([m for m in df[mask]['sign_ym'].dropna().unique() if str(m)>='2025-08'])

def get_licenses(df):
    data = df['issuing_entity'].dropna().unique().tolist() if 'issuing_entity' in df.columns else []
    extra = [l for l in data if l not in LICENSES_BASE]
    return LICENSES_BASE + extra

def safe_div(a, b): return a/b if b and b != 0 else 0
def pct_bar(pct, width=20): 
    filled = int(round(pct * width))
    return '█' * filled + '░' * (width - filled) + f'  {pct*100:.1f}%'

def st_title(c): 
    c.font=Font(bold=True,color=WHITE,size=12); c.fill=PatternFill("solid",fgColor=DARK_BLUE)
    c.alignment=Alignment(wrap_text=True)
def st_sub(c): 
    c.font=Font(bold=True,color=WHITE,size=11); c.fill=PatternFill("solid",fgColor=DARK_BLUE)
def st_hdr(c): 
    c.font=Font(bold=True,color=WHITE,size=9); c.fill=PatternFill("solid",fgColor=MID_BLUE)
    c.alignment=Alignment(horizontal='center',wrap_text=True)
def st_data(c,alt=False): 
    c.font=Font(size=9)
    if alt: c.fill=PatternFill("solid",fgColor=LIGHT_BLUE)
def st_total(c): 
    c.font=Font(bold=True,size=9); c.fill=PatternFill("solid",fgColor=GRAY_TOT)
def st_hl(c): 
    c.font=Font(bold=True,size=9); c.fill=PatternFill("solid",fgColor=LIGHT_YEL)
def st_note(c): 
    c.font=Font(italic=True,size=8,color="666666")

def write_row(ws, row, values, style_fn, fmts=None):
    for i, v in enumerate(values):
        c = ws.cell(row=row, column=i+1)
        c.value = v
        style_fn(c)
        if fmts and i < len(fmts) and fmts[i]:
            c.number_format = fmts[i]

def seg_stats(mask_main, carrier_filter=None):
    """Return dict: seg -> (ape, count, prem)"""
    m = mask_main.copy()
    if carrier_filter:
        m = m & (df['carrier']==carrier_filter)
    result = {}
    for seg in SEGMENTS:
        sub = df[m & (df['segment']==seg)]
        result[seg] = (sub['ape'].sum(), len(sub), sub['premium_hkd'].sum())
    return result

def agg3(mask):
    """Return ape, count, premium"""
    sub = df[mask]
    return sub['ape'].sum(), len(sub), sub['premium_hkd'].sum()

def agg3_seg(mask, seg):
    sub = df[mask & (df['segment']==seg)]
    return sub['ape'].sum(), len(sub), sub['premium_hkd'].sum()

def agg3_carrier(mask, carrier):
    sub = df[mask & (df['carrier']==carrier)]
    return sub['ape'].sum(), len(sub), sub['premium_hkd'].sum()

print("Functions defined. Building workbook...")


def build_all_sheets(df, months_26, weeks_26, issue_months, pending_months, licenses):
    # ── 公共过滤条件 ──────────────────────────────────
    mask_eff2025 = (df['status']=='生效') & (df['issue_year']==2025)
    mask_eff2026 = (df['status']=='生效') & (df['issue_year']==2026)
    mask_pending = df['status'].isin(['尚欠保费','已签单','pending','待批核'])
    mask_waiting = df['status']=='排期'
    mask_lost2026 = df['status'].isin(['失效','退保','取消投保','搁置受保','取消预约']) & (df['sign_year']==2026)
    mask_c = ~df['status'].isin(['失效','退保','取消投保','搁置受保','取消预约'])
    mask_d2 = ~df['status'].isin(['排期','失效','退保','取消投保','搁置受保','取消预约'])
    mask_e2 = df['status']=='生效'

    wb = Workbook()
    wb.remove(wb.active)  # remove default sheet

    # ============================================================
    # SHEET 1: 总览仪表盘
    # ============================================================
    ws = wb.create_sheet("S1_总览仪表盘")
    ws.column_dimensions['A'].width = 28
    ws.column_dimensions['B'].width = 18
    ws.column_dimensions['C'].width = 18
    ws.column_dimensions['D'].width = 14
    ws.column_dimensions['E'].width = 30
    ws.column_dimensions['F'].width = 14

    r = 1
    ws.merge_cells(f'A{r}:F{r}')
    ws[f'A{r}'] = 'Sheet 1  总览仪表盘 | Performance Dashboard'
    st_title(ws[f'A{r}'])
    r+=1
    _latest_date = df['issue_date'].dropna().max()
    _latest_date_str = str(_latest_date)[:10] if _latest_date else (months_26[-1] if months_26 else '')
    ws[f'A{r}'] = f'服务对象：管理层/经营分析 | 集团业绩全貌一页纸  (数据截至 {_latest_date_str})'
    st_note(ws[f'A{r}'])
    r+=2

    # A. 目标达成率
    ws.merge_cells(f'A{r}:F{r}')
    ws[f'A{r}'] = 'A. 目标达成率 | Target Achievement Rate'
    st_sub(ws[f'A{r}'])
    r+=1
    ws[f'A{r}'] = '📌 按目标类型统计2026年批核APE（issue_year=2026），计算达成率'
    st_note(ws[f'A{r}'])
    r+=1
    for col,txt in zip(['A','B','C','D','E'],['指标','目标APE','已达成APE','目标达成率','完成进度']):
        c = ws[f'{col}{r}']; c.value=txt; st_hdr(c)
    r+=1

    ape_all = df[mask_eff2026]['ape'].sum()
    ape_ym = df[mask_eff2026 & (df['carrier']=='香港永明金融有限公司')]['ape'].sum()
    tgt_all = 1113000000; tgt_ym = 976100000
    pct_all = safe_div(ape_all, tgt_all); pct_ym = safe_div(ape_ym, tgt_ym)

    for vals in [('2026全业务目标',tgt_all,ape_all,pct_all,pct_bar(pct_all)),
                 ('2026永明业务目标',tgt_ym,ape_ym,pct_ym,pct_bar(pct_ym))]:
        row_vals = list(vals)
        for i,v in enumerate(row_vals):
            c = ws.cell(row=r, column=i+1); c.value=v; st_hl(c)
            if i==1: c.number_format='#,##0'
            if i==2: c.number_format='#,##0'
            if i==3: c.number_format='0.0%'
        r+=1

    r+=1
    # B. KPI汇总
    ws.merge_cells(f'A{r}:F{r}')
    ws[f'A{r}'] = 'B. 顶部KPI汇总 | Top KPI Summary'
    st_sub(ws[f'A{r}'])
    r+=1
    ws[f'A{r}'] = '📌 批核(2025/2026):status=生效+issue_year；未批核:IN(尚欠/已签/pending/待批核)；待签:排期；流失(2026):流失+sign_year=2026'
    st_note(ws[f'A{r}'])
    r+=1
    for col,txt in zip(['A','B','C','D','E','F'],['指标行','件数','APE','年总保费(HKD)','件均APE','融资占比']):
        c=ws[f'{col}{r}']; c.value=txt; st_hdr(c)
    r+=1

    kpi_rows = [
        ('批核(2025)', mask_eff2025),
        ('批核(2026)', mask_eff2026),
        ('未批核(跨年)', mask_pending),
        ('待签(跨年)', mask_waiting),
        ('流失(2026)', mask_lost2026),
    ]
    for i,(label,mask) in enumerate(kpi_rows):
        sub = df[mask]
        ape_v=sub['ape'].sum(); cnt=len(sub); prem=sub['premium_hkd'].sum()
        je=safe_div(ape_v,cnt); pf=safe_div(sub[sub['is_pf']==1]['ape'].sum(),ape_v) if ape_v>0 else 0
        vals=[label,cnt,ape_v,prem,je,pf]
        for j,v in enumerate(vals):
            c=ws.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [2,3,4]: c.number_format='#,##0'
            if j==5: c.number_format='0.0%'
        r+=1

    r+=1
    # C. 月度业绩走势—预约
    ws.merge_cells(f'A{r}:G{r}')
    ws[f'A{r}'] = 'C. 月度业绩走势—按预约时间 | Monthly by Reservation Date'
    st_sub(ws[f'A{r}'])
    r+=1
    _latest_month_label = months_26[-1] if months_26 else '最新月'
    ws[f'A{r}'] = f'📌 res_ym；排除取消预约，保留所有其他状态；2025-01至{_latest_month_label}'
    st_note(ws[f'A{r}'])
    r+=1
    for col,txt in zip(['A','B','C','D','E','F','G'],['预约年月','件数','APE','年总保费(HKD)','件均APE','环比增长%','同比增长%']):
        c=ws[f'{col}{r}']; c.value=txt; st_hdr(c)
    r+=1

    mask_res = ~df['status'].isin(['取消预约'])
    months_c = sorted(df[mask_res & df['res_ym'].notna()]['res_ym'].unique())
    months_c = [m for m in months_c if str(m)>='2025-01']
    prev_ape={}
    for i,ym in enumerate(months_c):
        sub=df[mask_res & (df['res_ym']==ym)]
        ape_v=sub['ape'].sum(); cnt=len(sub); prem=sub['premium_hkd'].sum()
        je=safe_div(ape_v,cnt)
        mom=safe_div(ape_v-prev_ape.get('last',0),prev_ape.get('last',0)) if prev_ape.get('last') else None
        yoy_key=str(ym).replace('2026','2025')
        yoy=safe_div(ape_v-prev_ape.get(yoy_key,0),prev_ape.get(yoy_key,0)) if prev_ape.get(yoy_key) else None
        prev_ape['last']=ape_v; prev_ape[str(ym)]=ape_v
        vals=[str(ym),cnt,ape_v,prem,je,mom,yoy]
        for j,v in enumerate(vals):
            c=ws.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [2,3,4]: c.number_format='#,##0'
            if j in [5,6] and v is not None: c.number_format='0.0%'
        r+=1

    r+=1
    # D. 月度业绩走势—签单
    ws.merge_cells(f'A{r}:G{r}')
    ws[f'A{r}'] = 'D. 月度业绩走势—按签单时间 | Monthly by Signing Date'
    st_sub(ws[f'A{r}'])
    r+=1
    ws[f'A{r}'] = f'📌 sign_ym；排除排期、取消预约，保留所有其他状态；2025-01至{_latest_month_label}'
    st_note(ws[f'A{r}'])
    r+=1
    for col,txt in zip(['A','B','C','D','E','F','G'],['签单年月','件数','APE','年总保费(HKD)','件均APE','环比增长%','同比增长%']):
        c=ws[f'{col}{r}']; c.value=txt; st_hdr(c)
    r+=1

    mask_d = ~df['status'].isin(['排期','取消预约'])
    months_d = sorted(df[mask_d & df['sign_ym'].notna()]['sign_ym'].unique())
    months_d = [m for m in months_d if str(m)>='2025-01']
    prev_ape={}
    for i,ym in enumerate(months_d):
        sub=df[mask_d & (df['sign_ym']==ym)]
        ape_v=sub['ape'].sum(); cnt=len(sub); prem=sub['premium_hkd'].sum()
        je=safe_div(ape_v,cnt)
        mom=safe_div(ape_v-prev_ape.get('last',0),prev_ape.get('last',0)) if prev_ape.get('last') else None
        yoy_key=str(ym).replace('2026','2025')
        yoy=safe_div(ape_v-prev_ape.get(yoy_key,0),prev_ape.get(yoy_key,0)) if prev_ape.get(yoy_key) else None
        prev_ape['last']=ape_v; prev_ape[str(ym)]=ape_v
        vals=[str(ym),cnt,ape_v,prem,je,mom,yoy]
        for j,v in enumerate(vals):
            c=ws.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [2,3,4]: c.number_format='#,##0'
            if j in [5,6] and v is not None: c.number_format='0.0%'
        r+=1

    r+=1
    # E. 月度批核
    ws.merge_cells(f'A{r}:G{r}')
    ws[f'A{r}'] = 'E. 月度业绩走势—按批核时间 | Monthly by Issue Date'
    st_sub(ws[f'A{r}'])
    r+=1
    ws[f'A{r}'] = f'📌 issue_ym；status=生效；2025-01至{_latest_month_label}'
    st_note(ws[f'A{r}'])
    r+=1
    for col,txt in zip(['A','B','C','D','E','F','G'],['批核年月','件数','APE','年总保费(HKD)','件均APE','环比增长%','同比增长%']):
        c=ws[f'{col}{r}']; c.value=txt; st_hdr(c)
    r+=1

    months_e = sorted(df[(df['status']=='生效') & df['issue_ym'].notna()]['issue_ym'].unique())
    months_e = [m for m in months_e if str(m)>='2025-01']
    prev_ape={}
    for i,ym in enumerate(months_e):
        sub=df[(df['status']=='生效') & (df['issue_ym']==ym)]
        ape_v=sub['ape'].sum(); cnt=len(sub); prem=sub['premium_hkd'].sum()
        je=safe_div(ape_v,cnt)
        mom=safe_div(ape_v-prev_ape.get('last',0),prev_ape.get('last',0)) if prev_ape.get('last') else None
        yoy_key=str(ym).replace('2026','2025')
        yoy=safe_div(ape_v-prev_ape.get(yoy_key,0),prev_ape.get(yoy_key,0)) if prev_ape.get(yoy_key) else None
        prev_ape['last']=ape_v; prev_ape[str(ym)]=ape_v
        vals=[str(ym),cnt,ape_v,prem,je,mom,yoy]
        for j,v in enumerate(vals):
            c=ws.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [2,3,4]: c.number_format='#,##0'
            if j in [5,6] and v is not None: c.number_format='0.0%'
        r+=1

    r+=1
    # F. 保单状态分布
    ws.merge_cells(f'A{r}:H{r}')
    ws[f'A{r}'] = 'F. 保单状态分布-2026 | Policy Status Distribution'
    st_sub(ws[f'A{r}'])
    r+=1
    ws[f'A{r}'] = '📌 10个保单状态；批核(2026)=生效+issue_year=2026；流失按sign_year=2026'
    st_note(ws[f'A{r}'])
    r+=1
    for col,txt in zip('ABCDEFGH',['保单状态','统计说明','件数','APE','年总保费(HKD)','件数占比','APE占比','年总保费占比']):
        c=ws[f'{col}{r}']; c.value=txt; st_hdr(c)
    r+=1
    ws.column_dimensions['B'].width = 22

    f_rows = [
        ('A.批核(2026)','status=生效+issue_year=2026',mask_eff2026),
        ('B.排期','status=排期',mask_waiting),
        ('C.已签单','status=已签单',df['status']=='已签单'),
        ('D.待批核','status=待批核',df['status']=='待批核'),
        ('E.pending','status=pending',df['status']=='pending'),
        ('F.尚欠保费','status=尚欠保费',df['status']=='尚欠保费'),
        ('G.失效','status=失效+sign_year=2026',(df['status']=='失效')&(df['sign_year']==2026)),
        ('H.退保','status=退保+sign_year=2026',(df['status']=='退保')&(df['sign_year']==2026)),
        ('I.取消投保','status=取消投保+sign_year=2026',(df['status']=='取消投保')&(df['sign_year']==2026)),
        ('J.搁置受保','status=搁置受保+sign_year=2026',(df['status']=='搁置受保')&(df['sign_year']==2026)),
    ]
    tot_cnt=sum(df[m].shape[0] for _,_,m in f_rows)
    tot_ape=sum(df[m]['ape'].sum() for _,_,m in f_rows)
    tot_prem=sum(df[m]['premium_hkd'].sum() for _,_,m in f_rows)
    for i,(st,desc,mask) in enumerate(f_rows):
        sub=df[mask]; cnt=len(sub); ape_v=sub['ape'].sum(); prem=sub['premium_hkd'].sum()
        vals=[st,desc,cnt,ape_v,prem,safe_div(cnt,tot_cnt),safe_div(ape_v,tot_ape),safe_div(prem,tot_prem)]
        for j,v in enumerate(vals):
            c=ws.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [3,4]: c.number_format='#,##0'
            if j in [5,6,7]: c.number_format='0.0%'
        r+=1
    # 合计行
    tot_vals=['合计','',tot_cnt,tot_ape,tot_prem,1.0,1.0,1.0]
    for j,v in enumerate(tot_vals):
        c=ws.cell(row=r,column=j+1); c.value=v; st_total(c)
        if j in [3,4]: c.number_format='#,##0'
        if j in [5,6,7]: c.number_format='0.0%'
    r+=1

    r+=1
    # G. 业务类型维度
    ws.merge_cells(f'A{r}:I{r}')
    ws[f'A{r}'] = 'G. 业务类型维度-2026 | Business Type Dimension'
    st_sub(ws[f'A{r}'])
    r+=1
    ws[f'A{r}'] = '📌 business_category；2026批核=生效+issue_year=2026；未批核/待签跨年'
    st_note(ws[f'A{r}'])
    r+=1
    hdrs=['业务类型','2026批核APE','批核件数','未批核APE','未批核件数','待签APE','待签件数','合计APE','合计件数']
    for j,txt in enumerate(hdrs):
        c=ws.cell(row=r,column=j+1); c.value=txt; st_hdr(c)
    r+=1
    # FIX1: use biz_cat (segment-derived) not biz_type (CSV field, may have NaN)
    biz_types=[('代理人业务',df['biz_cat']=='代理人业务'),('经代业务',df['biz_cat']=='经代业务'),('KA业务',df['biz_cat']=='KA业务')]
    row_sums = {'a26':0,'c26':0,'ap':0,'cp':0,'aw':0,'cw':0}
    for i,(bt,bm) in enumerate(biz_types):
        a2026=df[mask_eff2026&bm]['ape'].sum(); c2026=df[mask_eff2026&bm].shape[0]
        apend=df[mask_pending&bm]['ape'].sum(); cpend=df[mask_pending&bm].shape[0]
        awt=df[mask_waiting&bm]['ape'].sum(); cwt=df[mask_waiting&bm].shape[0]
        row_sums['a26']+=a2026; row_sums['c26']+=c2026
        row_sums['ap']+=apend;  row_sums['cp']+=cpend
        row_sums['aw']+=awt;    row_sums['cw']+=cwt
        vals=[bt,a2026,c2026,apend,cpend,awt,cwt,a2026+apend+awt,c2026+cpend+cwt]
        for j,v in enumerate(vals):
            c=ws.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [1,3,5,7]: c.number_format='#,##0'
        r+=1
    # Total row = sum of 3 data rows (not grand total, to match exactly)
    tot_a26=row_sums['a26']; tot_c26=row_sums['c26']
    tot_ap=row_sums['ap'];   tot_cp=row_sums['cp']
    tot_aw=row_sums['aw'];   tot_cw=row_sums['cw']
    tot_vals=['合计',tot_a26,tot_c26,tot_ap,tot_cp,tot_aw,tot_cw,
              tot_a26+tot_ap+tot_aw, tot_c26+tot_cp+tot_cw]
    for j,v in enumerate(tot_vals):
        c=ws.cell(row=r,column=j+1); c.value=v; st_total(c)
        if j in [1,3,5,7]: c.number_format='#,##0'
    r+=2

    # H. 永明业绩汇报
    ws.merge_cells(f'A{r}:H{r}')
    ws[f'A{r}'] = 'H. 永明业绩汇报数据-2026 | Sunlife Performance Report'
    st_sub(ws[f'A{r}'])
    r+=1
    ws[f'A{r}'] = '📌 批核=status=生效+issue_ym；未批核=IN(尚欠/已签/pending/待批核)；本月已递交=submit_ym=当月；carrier=香港永明金融有限公司；EG=key_account=EGA'
    st_note(ws[f'A{r}'])
    r+=1
    issue_months_h = issue_months  # 动态取批核月，与CSV对齐
    h_hdrs = ['牌照'] + issue_months_h + ['未批核','本月已递交']
    for j,txt in enumerate(h_hdrs):
        c=ws.cell(row=r,column=j+1); c.value=txt; st_hdr(c)
    r+=1
    YM_YM = '香港永明金融有限公司'
    # 当月提交月份：取issue_months_h最后一个月
    _latest_submit_ym = issue_months_h[-1] if issue_months_h else None
    # EG口径：key_account='EGA' + carrier=香港永明金融有限公司
    mask_eg = df['ka']=='EGA'
    h_rows = [
        ('JF',          df['issuing_entity']=='九富保险服务有限公司'),
        ('UNIWIN',      df['issuing_entity']=='众和恒富理财集团有限公司'),
        ('DW-Non-Bank', (df['issuing_entity']=='怡泰财富管理有限公司')&(df['segment']!='BK业务')),
        ('EG',          mask_eg),
        ('DW Bank',     (df['issuing_entity']=='怡泰财富管理有限公司')&(df['segment']=='BK业务')),
    ]
    # Sub Total = JF + UNIWIN + DW-Non-Bank + EG
    _sub_total_entities = [
        df['issuing_entity']=='九富保险服务有限公司',
        df['issuing_entity']=='众和恒富理财集团有限公司',
        (df['issuing_entity']=='怡泰财富管理有限公司')&(df['segment']!='BK业务'),
        mask_eg,
    ]
    def _subtotal_mask(base_mask):
        combined = _sub_total_entities[0] | _sub_total_entities[1] | _sub_total_entities[2] | _sub_total_entities[3]
        return base_mask & combined & (df['carrier']==YM_YM)

    for i,(label,lmask) in enumerate(h_rows):
        vals=[label]
        for ym in issue_months_h:
            m=(df['status']=='生效')&(df['issue_ym']==ym)&lmask&(df['carrier']==YM_YM)
            vals.append(df[m]['ape'].sum())
        pend_m=mask_pending&lmask&(df['carrier']==YM_YM)
        vals.append(df[pend_m]['ape'].sum())
        sub_m=(df['submit_ym']==_latest_submit_ym)&lmask&(df['carrier']==YM_YM)
        vals.append(df[sub_m]['ape'].sum())
        for j,v in enumerate(vals):
            c=ws.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j>0: c.number_format='#,##0'
        r+=1
        if label=='EG':
            # Sub Total row: JF + UNIWIN + DW-Non-Bank + EG
            st_vals=['Sub Total']
            for ym in issue_months_h:
                v=df[(df['status']=='生效')&(df['issue_ym']==ym)&_subtotal_mask(pd.Series([True]*len(df), index=df.index))]['ape'].sum()
                # recalculate correctly per ym
                v2 = 0
                for em in _sub_total_entities:
                    v2 += df[(df['status']=='生效')&(df['issue_ym']==ym)&em&(df['carrier']==YM_YM)]['ape'].sum()
                st_vals.append(v2)
            pst = sum(df[mask_pending&em&(df['carrier']==YM_YM)]['ape'].sum() for em in _sub_total_entities)
            st_vals.append(pst)
            sub_m2 = sum(df[(df['submit_ym']==_latest_submit_ym)&em&(df['carrier']==YM_YM)]['ape'].sum() for em in _sub_total_entities)
            st_vals.append(sub_m2)
            for j,v in enumerate(st_vals):
                c=ws.cell(row=r,column=j+1); c.value=v; st_total(c)
                if j>0: c.number_format='#,##0'
            r+=1

    print("Sheet1 done, row:", r)

    # ============================================================
    # SHEET 2: 业务端视角
    # ============================================================
    ws2 = wb.create_sheet("S2_业务端视角")
    ws2.column_dimensions['A'].width = 18
    for col in 'BCDEFGHIJK': ws2.column_dimensions[col].width = 16

    r = 1
    ws2.merge_cells(f'A{r}:K{r}')
    ws2[f'A{r}'] = 'Sheet 2  业务端视角 | Sales & Channel View'
    st_title(ws2[f'A{r}'])
    r+=2

    def write_seg_table(ws, r, title, note, targets, carrier_filter=None):
        ws.merge_cells(f'A{r}:K{r}')
        ws[f'A{r}'] = title; st_sub(ws[f'A{r}'])
        r+=1
        ws[f'A{r}'] = note; st_note(ws[f'A{r}'])
        r+=1
        hdrs=['业务细分','目标APE','达成率','2026批核APE','批核件数','未批核APE','未批核件数','待签APE','待签件数','合计APE','合计件数']
        for j,h in enumerate(hdrs):
            c=ws.cell(row=r,column=j+1); c.value=h; st_hdr(c)
        r+=1
        tot_eff26_ape=0; tot_eff26_cnt=0; tot_pend_ape=0; tot_pend_cnt=0; tot_wait_ape=0; tot_wait_cnt=0
        for i,seg in enumerate(SEGMENTS):
            cm = df['segment']==seg
            if carrier_filter: cm2 = cm & (df['carrier']==carrier_filter)
            else: cm2=cm
            a26=df[mask_eff2026&cm2]['ape'].sum(); c26=df[mask_eff2026&cm2].shape[0]
            ap=df[mask_pending&cm2]['ape'].sum(); cp=df[mask_pending&cm2].shape[0]
            aw=df[mask_waiting&cm2]['ape'].sum(); cw=df[mask_waiting&cm2].shape[0]
            tgt=targets.get(seg,0); ach_r=safe_div(a26,tgt)
            tot_eff26_ape+=a26; tot_eff26_cnt+=c26; tot_pend_ape+=ap; tot_pend_cnt+=cp; tot_wait_ape+=aw; tot_wait_cnt+=cw
            # 与CSV对齐: % 写格式化字符串，APE取整
            vals=[seg, int(tgt), f"{ach_r:.1%}" if tgt>0 else '',
                  int(round(a26)), c26, int(round(ap)), cp, int(round(aw)), cw,
                  int(round(a26+ap+aw)), c26+cp+cw]
            for j,v in enumerate(vals):
                c=ws.cell(row=r,column=j+1); c.value=v
                if i%2==0: st_data(c,True)
                else: st_data(c)
            r+=1
        tot_tgt=sum(targets.values()); tot_ach=safe_div(tot_eff26_ape,tot_tgt)
        tot_vals=['合计', int(tot_tgt), f"{tot_ach:.1%}" if tot_tgt>0 else '',
                  int(round(tot_eff26_ape)), tot_eff26_cnt,
                  int(round(tot_pend_ape)), tot_pend_cnt,
                  int(round(tot_wait_ape)), tot_wait_cnt,
                  int(round(tot_eff26_ape+tot_pend_ape+tot_wait_ape)),
                  tot_eff26_cnt+tot_pend_cnt+tot_wait_cnt]
        for j,v in enumerate(tot_vals):
            c=ws.cell(row=r,column=j+1); c.value=v; st_total(c)
        r+=2
        return r

    r = write_seg_table(ws2, r, 'A. 业务细分年度汇总—全业务', '📌 segment_code(8个); 2026批核=生效+issue_year=2026; 合计行达成率=合计批核APE÷合计目标APE', TARGET_ALL)
    r = write_seg_table(ws2, r, 'B. 业务细分年度汇总—永明', '📌 同A区 + carrier=香港永明金融有限公司', TARGET_YM, carrier_filter='香港永明金融有限公司')

    # Monthly sub-tables for Sheet2: C-H (APE and count separate)
    # months_26 is passed in as parameter — do NOT redefine here

    def write_monthly_seg(ws, r, title, note, time_col, status_mask, carrier_filter=None, months=None):
        if months is None: months = months_26
        ws.merge_cells(f'A{r}:{get_column_letter(1+len(months)+1)}{r}')
        ws[f'A{r}'] = title; st_sub(ws[f'A{r}'])
        r+=1; ws[f'A{r}'] = note; st_note(ws[f'A{r}'])
        r+=1
        hdrs=['业务细分']+[str(m) for m in months]+['合计']
        for j,h in enumerate(hdrs):
            c=ws.cell(row=r,column=j+1); c.value=h; st_hdr(c)
        r+=1
        tot_row=[0]*len(months)
        for i,seg in enumerate(SEGMENTS):
            sm = df['segment']==seg
            if carrier_filter: sm = sm & (df['carrier']==carrier_filter)
            vals=[seg]
            row_tot=0
            for k,ym in enumerate(months):
                m2=status_mask&sm&(df[time_col]==ym)
                v=int(round(df[m2]['ape'].sum()))
                vals.append(v); row_tot+=v; tot_row[k]+=v
            vals.append(row_tot)
            for j,v in enumerate(vals):
                c=ws.cell(row=r,column=j+1); c.value=v
                if i%2==0: st_data(c,True)
                else: st_data(c)
            r+=1
        tot_vals=['合计']+tot_row+[sum(tot_row)]
        for j,v in enumerate(tot_vals):
            c=ws.cell(row=r,column=j+1); c.value=v; st_total(c)
        r+=2
        return r

    def write_monthly_seg_cnt(ws, r, title, note, time_col, status_mask, carrier_filter=None, months=None):
        if months is None: months = months_26
        ws.merge_cells(f'A{r}:{get_column_letter(1+len(months)+1)}{r}')
        ws[f'A{r}'] = title; st_sub(ws[f'A{r}'])
        r+=1; ws[f'A{r}'] = note; st_note(ws[f'A{r}'])
        r+=1
        hdrs=['业务细分']+[str(m) for m in months]+['合计']
        for j,h in enumerate(hdrs):
            c=ws.cell(row=r,column=j+1); c.value=h; st_hdr(c)
        r+=1
        tot_row=[0]*len(months)
        for i,seg in enumerate(SEGMENTS):
            sm = df['segment']==seg
            if carrier_filter: sm = sm & (df['carrier']==carrier_filter)
            vals=[seg]
            row_tot=0
            for k,ym in enumerate(months):
                m2=status_mask&sm&(df[time_col]==ym)
                v=df[m2].shape[0]
                vals.append(v); row_tot+=v; tot_row[k]+=v
            vals.append(row_tot)
            for j,v in enumerate(vals):
                c=ws.cell(row=r,column=j+1); c.value=v
                if i%2==0: st_data(c,True)
                else: st_data(c)
            r+=1
        tot_vals=['合计']+tot_row+[sum(tot_row)]
        for j,v in enumerate(tot_vals):
            c=ws.cell(row=r,column=j+1); c.value=v; st_total(c)
        r+=2
        return r

    mask_c = ~df['status'].isin(['取消预约','失效','退保','取消投保','搁置受保'])
    mask_d2 = ~df['status'].isin(['排期','取消预约','失效','退保','取消投保','搁置受保'])
    mask_e2 = df['status']=='生效'

    r = write_monthly_seg(ws2, r, 'C-APE. 月度预约业绩—全业务 (APE)', '📌 res_ym；排除流失类', 'res_ym', mask_c)
    r = write_monthly_seg_cnt(ws2, r, 'C-件数. 月度预约业绩—全业务 (件数)', '📌 res_ym；排除流失类', 'res_ym', mask_c)
    r = write_monthly_seg(ws2, r, 'D-APE. 月度签单业绩—全业务 (APE)', '📌 sign_ym；排除排期及流失', 'sign_ym', mask_d2)
    r = write_monthly_seg_cnt(ws2, r, 'D-件数. 月度签单业绩—全业务 (件数)', '📌 sign_ym；排除排期及流失', 'sign_ym', mask_d2)
    r = write_monthly_seg(ws2, r, 'E-APE. 月度批核业绩—全业务 (APE)', '📌 issue_ym；仅生效', 'issue_ym', mask_e2)
    r = write_monthly_seg_cnt(ws2, r, 'E-件数. 月度批核业绩—全业务 (件数)', '📌 issue_ym；仅生效', 'issue_ym', mask_e2)
    r = write_monthly_seg(ws2, r, 'F-APE. 月度预约业绩—永明 (APE)', '📌 res_ym；排除流失类 + carrier=香港永明金融有限公司', 'res_ym', mask_c, carrier_filter='香港永明金融有限公司')
    r = write_monthly_seg_cnt(ws2, r, 'F-件数. 月度预约业绩—永明 (件数)', '📌 res_ym；排除流失类 + carrier=香港永明金融有限公司', 'res_ym', mask_c, carrier_filter='香港永明金融有限公司')
    r = write_monthly_seg(ws2, r, 'G-APE. 月度签单业绩—永明 (APE)', '📌 sign_ym；排除排期及流失 + carrier=香港永明金融有限公司', 'sign_ym', mask_d2, carrier_filter='香港永明金融有限公司')
    r = write_monthly_seg_cnt(ws2, r, 'G-件数. 月度签单业绩—永明 (件数)', '📌 sign_ym；排除排期及流失 + carrier=香港永明金融有限公司', 'sign_ym', mask_d2, carrier_filter='香港永明金融有限公司')
    r = write_monthly_seg(ws2, r, 'H-APE. 月度批核业绩—永明 (APE)', '📌 issue_ym；仅生效 + carrier=香港永明金融有限公司', 'issue_ym', mask_e2, carrier_filter='香港永明金融有限公司')
    r = write_monthly_seg_cnt(ws2, r, 'H-件数. 月度批核业绩—永明 (件数)', '📌 issue_ym；仅生效 + carrier=香港永明金融有限公司', 'issue_ym', mask_e2, carrier_filter='香港永明金融有限公司')

    # I. KA TOP20
    ws2.merge_cells(f'A{r}:K{r}')
    ws2[f'A{r}'] = 'I. KEY ACCOUNT 排名 TOP20 | KA Ranking'
    st_sub(ws2[f'A{r}'])
    r+=1; ws2[f'A{r}'] = '📌 2026批核APE降序TOP20；含未批核/待签/合计列；含合计行'; st_note(ws2[f'A{r}'])
    r+=1
    hdrs=['排名','KEY ACCOUNT','业务细分','2026批核APE','批核件数','未批核APE','未批核件数','待签APE','待签件数','合计APE','合计件数']
    for j,h in enumerate(hdrs):
        c=ws2.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    ka_seg_eff = (df[mask_eff2026].groupby(['ka','segment'])['ape'].sum()
                  .reset_index().sort_values('ape',ascending=False).head(20))
    tot_i=[0]*8
    for i,row_ks in enumerate(ka_seg_eff.itertuples()):
        ka=row_ks.ka; seg=row_ks.segment; ape_v=int(round(row_ks.ape))
        km=(df['ka']==ka)&(df['segment']==seg)
        cnt=df[mask_eff2026&km].shape[0]
        ap=int(round(df[mask_pending&km]['ape'].sum())); cp=df[mask_pending&km].shape[0]
        aw=int(round(df[mask_waiting&km]['ape'].sum())); cw=df[mask_waiting&km].shape[0]
        for ii,v in enumerate([ape_v,cnt,ap,cp,aw,cw,ape_v+ap+aw,cnt+cp+cw]): tot_i[ii]+=v
        vals=[i+1,ka,seg,ape_v,cnt,ap,cp,aw,cw,ape_v+ap+aw,cnt+cp+cw]
        for j,v in enumerate(vals):
            c=ws2.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
        r+=1
    # 合计行
    tot_vals=['合计','','',tot_i[0],tot_i[1],tot_i[2],tot_i[3],tot_i[4],tot_i[5],tot_i[6],tot_i[7]]
    for j,v in enumerate(tot_vals):
        c=ws2.cell(row=r,column=j+1); c.value=v; st_total(c)
    r+=2

    # J. 同行推荐人
    ws2.merge_cells(f'A{r}:I{r}')
    ws2[f'A{r}'] = 'J. 同行推荐人分析 | Peer Referral Analysis'
    st_sub(ws2[f'A{r}'])
    r+=1; ws2[f'A{r}'] = '📌 6人：战略合作/Mark/姜通/高瑶/白博文/魏子璐；按2026批核APE降序'; st_note(ws2[f'A{r}'])
    r+=1
    hdrs=['推荐人','2026批核APE','批核件数','未批核APE','未批核件数','待签APE','待签件数','总APE','总件数']
    for j,h in enumerate(hdrs):
        c=ws2.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    referrals=['战略合作','Mark','姜通','高瑶','白博文','魏子璐']
    ref_data=[]
    for ref in referrals:
        rm=df['referral']==ref
        a26=df[mask_eff2026&rm]['ape'].sum(); c26=df[mask_eff2026&rm].shape[0]
        ap=df[mask_pending&rm]['ape'].sum(); cp=df[mask_pending&rm].shape[0]
        aw=df[mask_waiting&rm]['ape'].sum(); cw=df[mask_waiting&rm].shape[0]
        ref_data.append((ref,a26,c26,ap,cp,aw,cw,a26+ap+aw,c26+cp+cw))
    ref_data.sort(key=lambda x: -x[1])
    for i,vals in enumerate(ref_data):
        for j,v in enumerate(vals):
            c=ws2.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [1,3,5,7]: c.number_format='#,##0'
        r+=1
    tot_v=['合计']+[sum(x[k] for x in ref_data) for k in range(1,9)]
    for j,v in enumerate(tot_v):
        c=ws2.cell(row=r,column=j+1); c.value=v; st_total(c)
        if j in [1,3,5,7]: c.number_format='#,##0'
    r+=2

    # ============================================================
    # S2: K. 同行业绩分析 + L/M/N 月度子表
    # ============================================================
    mask_tonghang = df['segment'].isin(['永明经代','同行经代'])

    ws2.merge_cells(f'A{r}:I{r}')
    ws2[f'A{r}'] = 'K. 同行业绩分析 | Peer Channel Analysis'
    st_sub(ws2[f'A{r}'])
    r+=1; ws2[f'A{r}'] = '📌 segment IN(永明经代，同行经代)；按2026批核APE降序'; st_note(ws2[f'A{r}'])
    r+=1
    hdrs=['KEY ACCOUNT','2026批核APE','批核件数','未批核APE','未批核件数','待签APE','待签件数','总APE','总件数']
    for j,h in enumerate(hdrs):
        c=ws2.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    # build sorted by 2026 batch ape
    th_ka_sorted = df[mask_eff2026 & (df['segment'].isin(['永明经代','同行经代']))].groupby('ka')['ape'].sum().sort_values(ascending=False).index.tolist()
    th_ka_extra = [k for k in df[(df['segment'].isin(['永明经代','同行经代'])) & (mask_pending | mask_waiting)]['ka'].unique() if k not in th_ka_sorted]
    th_ka_all = th_ka_sorted + th_ka_extra

    th_tot = [0]*8
    for i,ka in enumerate(th_ka_all):
        km = df['ka']==ka
        a26=int(round(df[mask_eff2026&km]['ape'].sum())); c26=df[mask_eff2026&km].shape[0]
        ap=int(round(df[mask_pending&km]['ape'].sum())); cp=df[mask_pending&km].shape[0]
        aw=int(round(df[mask_waiting&km]['ape'].sum())); cw=df[mask_waiting&km].shape[0]
        vals=[ka,a26,c26,ap,cp,aw,cw,a26+ap+aw,c26+cp+cw]
        for idx in range(8): th_tot[idx] += vals[idx+1]
        for j,v in enumerate(vals):
            c=ws2.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
        r+=1
    th_tot_row=['合计']+th_tot
    for j,v in enumerate(th_tot_row):
        c=ws2.cell(row=r,column=j+1); c.value=v; st_total(c)
    r+=2

    # L/M/N 同行月度业绩子表
    def write_monthly_ka(ws, r, title, note, time_col, status_mask, ka_pool, months=None):
        """Sort by this table's own total APE descending. Returns (new_r, sorted_ka_order)."""
        if months is None: months=months_26
        # Compute each KA's total APE within this table's scope, then sort
        ka_totals = {ka: sum(df[status_mask & (df['ka']==ka) & (df[time_col]==ym)]['ape'].sum() for ym in months)
                     for ka in ka_pool}
        active = sorted([ka for ka,v in ka_totals.items() if v > 0], key=lambda k: -ka_totals[k])
        ws.merge_cells(f'A{r}:{get_column_letter(1+len(months)+1)}{r}')
        ws[f'A{r}'] = title; st_sub(ws[f'A{r}'])
        r+=1; ws[f'A{r}'] = note; st_note(ws[f'A{r}'])
        r+=1
        hdrs=['KEY ACCOUNT']+[str(m) for m in months]+['合计']
        for j,h in enumerate(hdrs):
            c=ws.cell(row=r,column=j+1); c.value=h; st_hdr(c)
        r+=1
        tot_row=[0]*len(months)
        for i,ka in enumerate(active):
            km=df['ka']==ka
            vals=[ka]; row_tot=0
            for k,ym in enumerate(months):
                v=int(round(df[status_mask&km&(df[time_col]==ym)]['ape'].sum()))
                vals.append(v); row_tot+=v; tot_row[k]+=v
            vals.append(row_tot)
            for j,v in enumerate(vals):
                c=ws.cell(row=r,column=j+1); c.value=v
                if i%2==0: st_data(c,True)
                else: st_data(c)
            r+=1
        tot_vals=['合计']+tot_row+[sum(tot_row)]
        for j,v in enumerate(tot_vals):
            c=ws.cell(row=r,column=j+1); c.value=v; st_total(c)
        r+=2
        return r, active

    def write_monthly_ka_cnt(ws, r, title, note, time_col, status_mask, ka_order, months=None):
        """Follow ka_order (from paired APE table)."""
        if months is None: months=months_26
        active = [ka for ka in ka_order if df[status_mask & (df['ka']==ka)].shape[0] > 0]
        ws.merge_cells(f'A{r}:{get_column_letter(1+len(months)+1)}{r}')
        ws[f'A{r}'] = title; st_sub(ws[f'A{r}'])
        r+=1; ws[f'A{r}'] = note; st_note(ws[f'A{r}'])
        r+=1
        hdrs=['KEY ACCOUNT']+[str(m) for m in months]+['合计']
        for j,h in enumerate(hdrs):
            c=ws.cell(row=r,column=j+1); c.value=h; st_hdr(c)
        r+=1
        tot_row=[0]*len(months)
        for i,ka in enumerate(active):
            km=df['ka']==ka
            vals=[ka]; row_tot=0
            for k,ym in enumerate(months):
                v=df[status_mask&km&(df[time_col]==ym)].shape[0]
                vals.append(v); row_tot+=v; tot_row[k]+=v
            vals.append(row_tot)
            for j,v in enumerate(vals):
                c=ws.cell(row=r,column=j+1); c.value=v
                if i%2==0: st_data(c,True)
                else: st_data(c)
            r+=1
        tot_vals=['合计']+tot_row+[sum(tot_row)]
        for j,v in enumerate(tot_vals):
            c=ws.cell(row=r,column=j+1); c.value=v; st_total(c)
        r+=2
        return r

    th_kas_full = df[df['segment'].isin(['永明经代','同行经代'])]['ka'].unique().tolist()

    # Pre-compute sorted order: total APE (批核+未批核+待签) descending
    mask_th_all = (mask_eff2026 | mask_pending | mask_waiting) & df['segment'].isin(['永明经代','同行经代'])
    th_ka_order = df[mask_th_all].groupby('ka')['ape'].sum().sort_values(ascending=False).index.tolist()

    r, th_order_L = write_monthly_ka(ws2, r, 'L-APE. 月度预约业绩—同行 (APE)', '📌 res_ym；排除流失类；⭐ 按该表自身合计APE降序', 'res_ym', mask_c & (df['segment'].isin(['永明经代','同行经代'])), th_ka_order)
    r = write_monthly_ka_cnt(ws2, r, 'L-件数. 月度预约业绩—同行 (件数)', '📌 同L-APE；行顺序跟随APE子表', 'res_ym', mask_c & (df['segment'].isin(['永明经代','同行经代'])), th_order_L)
    r, th_order_M = write_monthly_ka(ws2, r, 'M-APE. 月度签单业绩—同行 (APE)', '📌 sign_ym；排除排期及流失；⭐ 按该表自身合计APE降序', 'sign_ym', mask_d2 & (df['segment'].isin(['永明经代','同行经代'])), th_ka_order)
    r = write_monthly_ka_cnt(ws2, r, 'M-件数. 月度签单业绩—同行 (件数)', '📌 同M-APE；行顺序跟随APE子表', 'sign_ym', mask_d2 & (df['segment'].isin(['永明经代','同行经代'])), th_order_M)
    r, th_order_N = write_monthly_ka(ws2, r, 'N-APE. 月度批核业绩—同行 (APE)', '📌 issue_ym；仅生效；⭐ 按该表自身合计APE降序', 'issue_ym', mask_e2 & (df['segment'].isin(['永明经代','同行经代'])), th_ka_order)
    r = write_monthly_ka_cnt(ws2, r, 'N-件数. 月度批核业绩—同行 (件数)', '📌 同N-APE；行顺序跟随APE子表', 'issue_ym', mask_e2 & (df['segment'].isin(['永明经代','同行经代'])), th_order_N)

    # ============================================================
    # S2: O. 银行业绩分析 + P/Q/R 月度 + S/T 分行
    # ============================================================
    mask_bk = df['segment']=='BK业务'
    bk_kas_full = df[mask_bk]['ka'].unique().tolist()

    ws2.merge_cells(f'A{r}:I{r}')
    ws2[f'A{r}'] = 'O. 银行业绩分析 | Bank Channel Analysis'
    st_sub(ws2[f'A{r}'])
    r+=1; ws2[f'A{r}'] = '📌 segment=BK业务；按2026批核APE降序'; st_note(ws2[f'A{r}'])
    r+=1
    hdrs=['KEY ACCOUNT','2026批核APE','批核件数','未批核APE','未批核件数','待签APE','待签件数','总APE','总件数']
    for j,h in enumerate(hdrs):
        c=ws2.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    bk_ka_sorted = df[mask_eff2026 & mask_bk].groupby('ka')['ape'].sum().sort_values(ascending=False).index.tolist()
    bk_ka_extra = [k for k in df[mask_bk & (mask_pending | mask_waiting)]['ka'].unique() if k not in bk_ka_sorted]
    bk_ka_all = bk_ka_sorted + bk_ka_extra
    bk_tot = [0]*8
    for i,ka in enumerate(bk_ka_all):
        km=df['ka']==ka
        a26=int(round(df[mask_eff2026&km]['ape'].sum())); c26=df[mask_eff2026&km].shape[0]
        ap=int(round(df[mask_pending&km]['ape'].sum())); cp=df[mask_pending&km].shape[0]
        aw=int(round(df[mask_waiting&km]['ape'].sum())); cw=df[mask_waiting&km].shape[0]
        vals=[ka,a26,c26,ap,cp,aw,cw,a26+ap+aw,c26+cp+cw]
        for idx in range(8): bk_tot[idx]+=vals[idx+1]
        for j,v in enumerate(vals):
            c=ws2.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
        r+=1
    bk_tot_row=['合计']+bk_tot
    for j,v in enumerate(bk_tot_row):
        c=ws2.cell(row=r,column=j+1); c.value=v; st_total(c)
    r+=2

    bk_kas_full = df[mask_bk]['ka'].unique().tolist()

    # Pre-compute sorted order: total APE (批核+未批核+待签) descending for BK
    mask_bk_all = (mask_eff2026 | mask_pending | mask_waiting) & mask_bk
    bk_ka_order = df[mask_bk_all].groupby('ka')['ape'].sum().sort_values(ascending=False).index.tolist()
    bk_ka_extra = [k for k in df[mask_bk]['ka'].unique() if k not in bk_ka_order]
    bk_ka_order = bk_ka_order + bk_ka_extra

    r, bk_order_P = write_monthly_ka(ws2, r, 'P-APE. 月度预约业绩—银行 (APE)', '📌 res_ym；排除流失类；⭐ 按该表自身合计APE降序', 'res_ym', mask_c & mask_bk, bk_ka_order)
    r = write_monthly_ka_cnt(ws2, r, 'P-件数. 月度预约业绩—银行 (件数)', '📌 同P-APE；行顺序跟随APE子表', 'res_ym', mask_c & mask_bk, bk_order_P)
    r, bk_order_Q = write_monthly_ka(ws2, r, 'Q-APE. 月度签单业绩—银行 (APE)', '📌 sign_ym；排除排期及流失；⭐ 按该表自身合计APE降序', 'sign_ym', mask_d2 & mask_bk, bk_ka_order)
    r = write_monthly_ka_cnt(ws2, r, 'Q-件数. 月度签单业绩—银行 (件数)', '📌 同Q-APE；行顺序跟随APE子表', 'sign_ym', mask_d2 & mask_bk, bk_order_Q)
    r, bk_order_R = write_monthly_ka(ws2, r, 'R-APE. 月度批核业绩—银行 (APE)', '📌 issue_ym；仅生效；⭐ 按该表自身合计APE降序', 'issue_ym', mask_e2 & mask_bk, bk_ka_order)
    r = write_monthly_ka_cnt(ws2, r, 'R-件数. 月度批核业绩—银行 (件数)', '📌 同R-APE；行顺序跟随APE子表', 'issue_ym', mask_e2 & mask_bk, bk_order_R)

    # S/T 银行各分行批核业绩 - stable sort by APE descending then partner name
    mask_bk_all2 = (mask_eff2026 | mask_pending | mask_waiting) & mask_bk
    bk_partner_ape = df[mask_bk_all2 & df['partner'].notna()].groupby('partner')['ape'].sum()
    bk_partner_order = bk_partner_ape.reset_index().sort_values(['ape','partner'], ascending=[False,True])['partner'].tolist()
    bk_partner_extra = [p for p in df[mask_bk & df['partner'].notna()]['partner'].unique() if p not in bk_partner_order]
    bk_partners_all = bk_partner_order + bk_partner_extra

    for (title, note, vtype) in [
        ('S-APE. 批核业绩—银行各分行 (APE)', '📌 issue_ym；仅生效；行=partner；⭐ 按该表自身合计APE降序', 'ape'),
        ('T-件数. 批核业绩—银行各分行 (件数)', '📌 同S-APE；行顺序跟随S-APE', 'cnt'),
    ]:
        ws2.merge_cells(f'A{r}:{get_column_letter(1+len(months_26)+1)}{r}')
        ws2[f'A{r}'] = title; st_sub(ws2[f'A{r}'])
        r+=1; ws2[f'A{r}'] = note; st_note(ws2[f'A{r}'])
        r+=1
        hdrs=['合作伙伴(分行)']+[str(m) for m in months_26]+['合计']
        for j,h in enumerate(hdrs):
            c=ws2.cell(row=r,column=j+1); c.value=h; st_hdr(c)
        r+=1
        tot_row=[0]*len(months_26)
        for i,pt in enumerate(bk_partners_all):
            pm=df['partner']==pt
            vals=[pt]; row_tot=0
            for k,ym in enumerate(months_26):
                if vtype=='ape':
                    v=int(round(df[mask_e2&mask_bk&pm&(df['issue_ym']==ym)]['ape'].sum()))
                else:
                    v=df[mask_e2&mask_bk&pm&(df['issue_ym']==ym)].shape[0]
                vals.append(v); row_tot+=v; tot_row[k]+=v
            vals.append(row_tot)
            for j,v in enumerate(vals):
                c=ws2.cell(row=r,column=j+1); c.value=v
                if i%2==0: st_data(c,True)
                else: st_data(c)
            r+=1
        tot_vals=['合计']+tot_row+[sum(tot_row)]
        for j,v in enumerate(tot_vals):
            c=ws2.cell(row=r,column=j+1); c.value=v; st_total(c)
        r+=2

    print("Sheet2 done, row:", r)

    # ============================================================
    # SHEET 3: 执行管理端
    # ============================================================
    ws3 = wb.create_sheet("S3_执行管理端")
    ws3.column_dimensions['A'].width = 18
    for i in range(2, 20): ws3.column_dimensions[get_column_letter(i)].width = 14

    r = 1
    ws3.merge_cells(f'A{r}:P{r}')
    ws3[f'A{r}'] = 'Sheet 3  执行管理端 | Execution Management View'
    st_title(ws3[f'A{r}'])
    r+=2

    # weeks_26 is passed as parameter — auto-scrolls to latest week in data
    # A. 阶段周追踪漏斗
    ws3.merge_cells(f'A{r}:{get_column_letter(1+len(weeks_26)+1)}{r}')
    ws3[f'A{r}'] = 'A-APE. 阶段周追踪漏斗 (APE)'; st_sub(ws3[f'A{r}'])
    r+=1; ws3[f'A{r}'] = f'📌 预约=res_yw；签单=sign_yw；递交=submit_yw；批核=issue_yw(仅生效)；2026W01至最新周'; st_note(ws3[f'A{r}'])
    r+=1
    hdrs=['阶段']+weeks_26+['合计']
    for j,h in enumerate(hdrs):
        c=ws3.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1

    # All status except lost for res, sign, submit; only effective for issue
    funnel_masks = [
        ('预约', 'res_yw', mask_c),
        ('签单', 'sign_yw', mask_d2),
        ('递交', 'submit_yw', ~df['status'].isin(['失效','退保','取消投保','搁置受保','取消预约'])),
        ('批核', 'issue_yw', mask_e2),
    ]
    for i,(label,tcol,fmask) in enumerate(funnel_masks):
        vals=[label]
        tot=0
        for wk in weeks_26:
            v=df[fmask & (df[tcol]==wk)]['ape'].sum()
            vals.append(v); tot+=v
        vals.append(tot)
        for j,v in enumerate(vals):
            c=ws3.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j>0: c.number_format='#,##0'
        r+=1
    r+=2

    ws3.merge_cells(f'A{r}:{get_column_letter(1+len(weeks_26)+1)}{r}')
    ws3[f'A{r}'] = 'A-件数. 阶段周追踪漏斗 (件数)'; st_sub(ws3[f'A{r}'])
    r+=1; ws3[f'A{r}'] = '📌 同A-APE；值为件数'; st_note(ws3[f'A{r}'])
    r+=1
    hdrs=['阶段']+weeks_26+['合计']
    for j,h in enumerate(hdrs):
        c=ws3.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    for i,(label,tcol,fmask) in enumerate(funnel_masks):
        vals=[label]
        tot=0
        for wk in weeks_26:
            v=df[fmask & (df[tcol]==wk)].shape[0]
            vals.append(v); tot+=v
        vals.append(tot)
        for j,v in enumerate(vals):
            c=ws3.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
        r+=1
    r+=2

    # B/C/D weekly business tables
    def write_weekly_seg(ws, r, title, note, time_col, status_mask, weeks=None):
        if weeks is None: weeks=weeks_26
        ws.merge_cells(f'A{r}:{get_column_letter(1+len(weeks)+1)}{r}')
        ws[f'A{r}'] = title; st_sub(ws[f'A{r}'])
        r+=1; ws[f'A{r}'] = note; st_note(ws[f'A{r}'])
        r+=1
        hdrs=['业务细分']+weeks+['合计']
        for j,h in enumerate(hdrs):
            c=ws.cell(row=r,column=j+1); c.value=h; st_hdr(c)
        r+=1
        tot_row=[0]*len(weeks)
        for i,seg in enumerate(SEGMENTS):
            sm=df['segment']==seg
            vals=[seg]; row_tot=0
            for k,wk in enumerate(weeks):
                v=int(round(df[status_mask&sm&(df[time_col]==wk)]['ape'].sum()))
                vals.append(v); row_tot+=v; tot_row[k]+=v
            vals.append(row_tot)
            for j,v in enumerate(vals):
                c=ws.cell(row=r,column=j+1); c.value=v
                if i%2==0: st_data(c,True)
                else: st_data(c)
            r+=1
        tot_vals=['合计']+tot_row+[sum(tot_row)]
        for j,v in enumerate(tot_vals):
            c=ws.cell(row=r,column=j+1); c.value=v; st_total(c)
        r+=2
        return r

    def write_weekly_seg_cnt(ws, r, title, note, time_col, status_mask, weeks=None):
        if weeks is None: weeks=weeks_26
        ws.merge_cells(f'A{r}:{get_column_letter(1+len(weeks)+1)}{r}')
        ws[f'A{r}'] = title; st_sub(ws[f'A{r}'])
        r+=1; ws[f'A{r}'] = note; st_note(ws[f'A{r}'])
        r+=1
        hdrs=['业务细分']+weeks+['合计']
        for j,h in enumerate(hdrs):
            c=ws.cell(row=r,column=j+1); c.value=h; st_hdr(c)
        r+=1
        tot_row=[0]*len(weeks)
        for i,seg in enumerate(SEGMENTS):
            sm=df['segment']==seg
            vals=[seg]; row_tot=0
            for k,wk in enumerate(weeks):
                v=df[status_mask&sm&(df[time_col]==wk)].shape[0]
                vals.append(v); row_tot+=v; tot_row[k]+=v
            vals.append(row_tot)
            for j,v in enumerate(vals):
                c=ws.cell(row=r,column=j+1); c.value=v
                if i%2==0: st_data(c,True)
                else: st_data(c)
            r+=1
        tot_vals=['合计']+tot_row+[sum(tot_row)]
        for j,v in enumerate(tot_vals):
            c=ws.cell(row=r,column=j+1); c.value=v; st_total(c)
        r+=2
        return r

    r = write_weekly_seg(ws3, r, 'B-APE. 周度预约业绩 (APE)', '📌 res_yw；status NOT IN(失效/退保/取消投保/搁置受保/取消预约)', 'res_yw', mask_c)
    r = write_weekly_seg_cnt(ws3, r, 'B-件数. 周度预约业绩 (件数)', '📌 res_yw；status NOT IN(失效/退保/取消投保/搁置受保/取消预约)', 'res_yw', mask_c)
    r = write_weekly_seg(ws3, r, 'C-APE. 周度签单业绩 (APE)', '📌 sign_yw；status NOT IN(排期/失效/退保/取消投保/搁置受保/取消预约)', 'sign_yw', mask_d2)
    r = write_weekly_seg_cnt(ws3, r, 'C-件数. 周度签单业绩 (件数)', '📌 sign_yw；status NOT IN(排期/失效/退保/取消投保/搁置受保/取消预约)', 'sign_yw', mask_d2)
    r = write_weekly_seg(ws3, r, 'D-APE. 周度批核业绩 (APE)', '📌 issue_yw；仅status=生效', 'issue_yw', mask_e2)
    r = write_weekly_seg_cnt(ws3, r, 'D-件数. 周度批核业绩 (件数)', '📌 issue_yw；仅status=生效', 'issue_yw', mask_e2)

    # ============================================================
    # S3: E/F 未批核与待签分布（常规 vs 融资）
    # ============================================================
    # Sign months from 2025-08 onwards
    mask_ef_base = df['status'].isin(['尚欠保费','已签单','pending','待批核','排期'])
    sign_months_ef = sorted([m for m in df[mask_ef_base & df['sign_ym'].notna()]['sign_ym'].unique() if str(m) >= '2025-08'])

    for (sec_label, pf_val, pf_name) in [('E', 0, '常规'), ('F', 1, '融资')]:
        mask_pf = mask_ef_base & (df['is_pf']==pf_val)
        # Get all KAs with any data, sorted by total APE descending (stable sort for consistent tie-breaking)
        ka_pool_ef = df[mask_pf & df['ka'].notna()]['ka'].unique().tolist()
        ka_totals_ef = {ka: df[mask_pf & (df['ka']==ka)]['ape'].sum() for ka in ka_pool_ef}
        ka_order_ef = sorted([ka for ka,v in ka_totals_ef.items() if v > 0 or df[mask_pf & (df['ka']==ka)].shape[0] > 0],
                             key=lambda k: (-round(ka_totals_ef.get(k, 0), 0), str(k)))

        # E/F-APE
        n_cols = len(sign_months_ef)
        ws3.merge_cells(f'A{r}:{get_column_letter(n_cols+2)}{r}')
        ws3[f'A{r}'] = f'{sec_label}-APE. 未批核与待签分布—{pf_name} (APE) | Pending & Waiting Distribution'
        st_sub(ws3[f'A{r}'])
        r+=1
        ws3[f'A{r}'] = f'📌 status IN(尚欠/已签/pending/待批核/排期)；is_pf={pf_val}({pf_name})；列=sign_ym(2025-08起)；⭐ 按该表自身合计APE降序'
        st_note(ws3[f'A{r}'])
        r+=1
        hdrs=['KEY ACCOUNT']+[str(m) for m in sign_months_ef]+['合计']
        for j,h in enumerate(hdrs):
            c=ws3.cell(row=r,column=j+1); c.value=h; st_hdr(c)
        r+=1
        tot_row=[0]*n_cols
        for i,ka in enumerate(ka_order_ef):
            km=df['ka']==ka
            vals=[ka]; row_tot=0
            for k,ym in enumerate(sign_months_ef):
                v=df[mask_pf&km&(df['sign_ym']==ym)]['ape'].sum()
                vals.append(v); row_tot+=v; tot_row[k]+=v
            vals.append(row_tot)
            for j,v in enumerate(vals):
                c=ws3.cell(row=r,column=j+1); c.value=v
                if i%2==0: st_data(c,True)
                else: st_data(c)
                if j>0: c.number_format='#,##0'
            r+=1
        tot_vals=['合计']+tot_row+[sum(tot_row)]
        for j,v in enumerate(tot_vals):
            c=ws3.cell(row=r,column=j+1); c.value=v; st_total(c)
            if j>0: c.number_format='#,##0'
        r+=2

        # E/F-件数
        ws3.merge_cells(f'A{r}:{get_column_letter(n_cols+2)}{r}')
        ws3[f'A{r}'] = f'{sec_label}-件数. 未批核与待签分布—{pf_name} (件数)'
        st_sub(ws3[f'A{r}'])
        r+=1
        ws3[f'A{r}'] = f'📌 同{sec_label}-APE；行顺序跟随APE子表'
        st_note(ws3[f'A{r}'])
        r+=1
        hdrs=['KEY ACCOUNT']+[str(m) for m in sign_months_ef]+['合计']
        for j,h in enumerate(hdrs):
            c=ws3.cell(row=r,column=j+1); c.value=h; st_hdr(c)
        r+=1
        tot_row=[0]*n_cols
        for i,ka in enumerate(ka_order_ef):
            km=df['ka']==ka
            vals=[ka]; row_tot=0
            for k,ym in enumerate(sign_months_ef):
                v=df[mask_pf&km&(df['sign_ym']==ym)].shape[0]
                vals.append(v); row_tot+=v; tot_row[k]+=v
            vals.append(row_tot)
            for j,v in enumerate(vals):
                c=ws3.cell(row=r,column=j+1); c.value=v
                if i%2==0: st_data(c,True)
                else: st_data(c)
            r+=1
        tot_vals=['合计']+tot_row+[sum(tot_row)]
        for j,v in enumerate(tot_vals):
            c=ws3.cell(row=r,column=j+1); c.value=v; st_total(c)
        r+=2

    # G. 签批时效分析
    ws3.merge_cells(f'A{r}:H{r}')
    ws3[f'A{r}'] = 'G. 签批时效分析—2026批核 | TAT Analysis'; st_sub(ws3[f'A{r}'])
    r+=1; ws3[f'A{r}'] = '📌 status=生效 AND issue_year=2026；TAT=issue_date-sign_date(天)；SLA达标率=COUNT(tat≤60)/COUNT(*)'; st_note(ws3[f'A{r}'])
    r+=1
    hdrs=['业务细分','件数','件均APE','平均时效(天)','中位时效(天)','P90时效(天)','最大时效(天)','SLA达标率≤60']
    for j,h in enumerate(hdrs):
        c=ws3.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    tat_data = []
    for i,seg in enumerate(SEGMENTS):
        sub=df[mask_eff2026 & (df['segment']==seg) & df['tat'].notna()]
        if len(sub)==0:
            # 无数据行也写入，与CSV对齐（所有段均列出）
            vals=[seg, 0, '', '', '', '', '', '']
        else:
            sla = safe_div((sub['tat']<=60).sum(), len(sub))
            vals=[seg, len(sub), int(round(safe_div(sub['ape'].sum(),len(sub)))),
                  round(sub['tat'].mean(),1), round(sub['tat'].median(),1),
                  round(sub['tat'].quantile(0.9),1), int(sub['tat'].max()),
                  f"{sla:.1%}"]
        tat_data.append(vals)
        for j,v in enumerate(vals):
            c=ws3.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
        r+=1
    all_tat=df[mask_eff2026 & df['tat'].notna()]
    sla_tot = safe_div((all_tat['tat']<=60).sum(), len(all_tat))
    tot_tat=['合计', len(all_tat), int(round(safe_div(all_tat['ape'].sum(),len(all_tat)))),
             round(all_tat['tat'].mean(),1), round(all_tat['tat'].median(),1),
             round(all_tat['tat'].quantile(0.9),1), int(all_tat['tat'].max()),
             f"{sla_tot:.1%}"]
    for j,v in enumerate(tot_tat):
        c=ws3.cell(row=r,column=j+1); c.value=v; st_total(c)
    r+=2

    # H. 时效分档
    ws3.merge_cells(f'A{r}:E{r}')
    ws3[f'A{r}'] = 'H. 签批时效分档—2026批核 | TAT Buckets'; st_sub(ws3[f'A{r}'])
    r+=1; ws3[f'A{r}'] = '📌 分档：≤7天/8-14天/15-30天/31-60天/61-90天/>90天；status=生效 AND issue_year=2026'; st_note(ws3[f'A{r}'])
    r+=1
    for j,h in enumerate(['时效分档','件数','APE','件数占比','APE占比']):
        c=ws3.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    tat_buckets=[('≤7天',0,7),('8-14天',8,14),('15-30天',15,30),('31-60天',31,60),('61-90天',61,90),('>90天',91,9999)]
    all_tat2=df[mask_eff2026 & df['tat'].notna()]
    tot_cnt_h=len(all_tat2); tot_ape_h=int(round(all_tat2['ape'].sum()))
    for i,(label,lo,hi) in enumerate(tat_buckets):
        sub=all_tat2[(all_tat2['tat']>=lo)&(all_tat2['tat']<=hi)]
        vals=[label, len(sub), int(round(sub['ape'].sum())),
              f"{safe_div(len(sub),tot_cnt_h):.1%}", f"{safe_div(sub['ape'].sum(),all_tat2['ape'].sum()):.1%}"]
        for j,v in enumerate(vals):
            c=ws3.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
        r+=1
    for j,v in enumerate(['合计', tot_cnt_h, tot_ape_h, '100.0%', '100.0%']):
        c=ws3.cell(row=r,column=j+1); c.value=v; st_total(c)
    r+=2

    # ============================================================
    # S3: J/K/L 同行周度业绩追踪
    # ============================================================
    def write_weekly_ka(ws, r, title, note, time_col, status_mask, ka_pool, weeks=None):
        """Sort by this table's own total APE descending. Returns (new_r, sorted_ka_order)."""
        if weeks is None: weeks=weeks_26
        ka_totals = {ka: sum(df[status_mask & (df['ka']==ka) & (df[time_col]==wk)]['ape'].sum() for wk in weeks)
                     for ka in ka_pool}
        active = sorted([ka for ka,v in ka_totals.items() if v > 0], key=lambda k: -ka_totals[k])
        ws.merge_cells(f'A{r}:{get_column_letter(1+len(weeks)+1)}{r}')
        ws[f'A{r}'] = title; st_sub(ws[f'A{r}'])
        r+=1; ws[f'A{r}'] = note; st_note(ws[f'A{r}'])
        r+=1
        hdrs=['KEY ACCOUNT']+weeks+['合计']
        for j,h in enumerate(hdrs):
            c=ws.cell(row=r,column=j+1); c.value=h; st_hdr(c)
        r+=1
        tot_row=[0]*len(weeks)
        for i,ka in enumerate(active):
            km=df['ka']==ka
            vals=[ka]; row_tot=0
            for k,wk in enumerate(weeks):
                v=int(round(df[status_mask&km&(df[time_col]==wk)]['ape'].sum()))
                vals.append(v); row_tot+=v; tot_row[k]+=v
            vals.append(row_tot)
            for j,v in enumerate(vals):
                c=ws.cell(row=r,column=j+1); c.value=v
                if i%2==0: st_data(c,True)
                else: st_data(c)
            r+=1
        tot_vals=['合计']+tot_row+[sum(tot_row)]
        for j,v in enumerate(tot_vals):
            c=ws.cell(row=r,column=j+1); c.value=v; st_total(c)
        r+=2
        return r, active

    def write_weekly_ka_cnt(ws, r, title, note, time_col, status_mask, ka_order, weeks=None):
        """Follow ka_order (from paired APE table)."""
        if weeks is None: weeks=weeks_26
        active = [ka for ka in ka_order if df[status_mask & (df['ka']==ka)].shape[0] > 0]
        ws.merge_cells(f'A{r}:{get_column_letter(1+len(weeks)+1)}{r}')
        ws[f'A{r}'] = title; st_sub(ws[f'A{r}'])
        r+=1; ws[f'A{r}'] = note; st_note(ws[f'A{r}'])
        r+=1
        hdrs=['KEY ACCOUNT']+weeks+['合计']
        for j,h in enumerate(hdrs):
            c=ws.cell(row=r,column=j+1); c.value=h; st_hdr(c)
        r+=1
        tot_row=[0]*len(weeks)
        for i,ka in enumerate(active):
            km=df['ka']==ka
            vals=[ka]; row_tot=0
            for k,wk in enumerate(weeks):
                v=df[status_mask&km&(df[time_col]==wk)].shape[0]
                vals.append(v); row_tot+=v; tot_row[k]+=v
            vals.append(row_tot)
            for j,v in enumerate(vals):
                c=ws.cell(row=r,column=j+1); c.value=v
                if i%2==0: st_data(c,True)
                else: st_data(c)
            r+=1
        tot_vals=['合计']+tot_row+[sum(tot_row)]
        for j,v in enumerate(tot_vals):
            c=ws.cell(row=r,column=j+1); c.value=v; st_total(c)
        r+=2
        return r

    th_kas_s3 = df[df['segment'].isin(['永明经代','同行经代'])]['ka'].unique().tolist()
    mask_th = df['segment'].isin(['永明经代','同行经代'])

    # Pre-compute sorted order by total APE for S3 tonghang
    mask_th_all_s3 = (mask_eff2026 | mask_pending | mask_waiting) & mask_th
    th_ka_order_s3 = df[mask_th_all_s3].groupby('ka')['ape'].sum().sort_values(ascending=False).index.tolist()

    r, th_order_J = write_weekly_ka(ws3, r, 'J-APE. 周度预约业绩—同行 (APE)', '📌 res_yw；排除流失类；⭐ 按该表自身合计APE降序', 'res_yw', mask_c & mask_th, th_kas_s3)
    r = write_weekly_ka_cnt(ws3, r, 'J-件数. 周度预约业绩—同行 (件数)', '📌 同J-APE；行顺序跟随APE子表', 'res_yw', mask_c & mask_th, th_order_J)
    r, th_order_K = write_weekly_ka(ws3, r, 'K-APE. 周度签单业绩—同行 (APE)', '📌 sign_yw；排除排期及流失；⭐ 按该表自身合计APE降序', 'sign_yw', mask_d2 & mask_th, th_kas_s3)
    r = write_weekly_ka_cnt(ws3, r, 'K-件数. 周度签单业绩—同行 (件数)', '📌 同K-APE；行顺序跟随APE子表', 'sign_yw', mask_d2 & mask_th, th_order_K)
    r, th_order_L = write_weekly_ka(ws3, r, 'L-APE. 周度批核业绩—同行 (APE)', '📌 issue_yw；仅生效；⭐ 按该表自身合计APE降序', 'issue_yw', mask_e2 & mask_th, th_kas_s3)
    r = write_weekly_ka_cnt(ws3, r, 'L-件数. 周度批核业绩—同行 (件数)', '📌 同L-APE；行顺序跟随APE子表', 'issue_yw', mask_e2 & mask_th, th_order_L)

    # ============================================================
    # S3: M/N/O 银行周度业绩追踪
    # ============================================================
    bk_kas_s3 = df[df['segment']=='BK业务']['ka'].unique().tolist()
    mask_bk3 = df['segment']=='BK业务'

    # Pre-compute sorted order by total APE for S3 BK
    mask_bk_all_s3 = (mask_eff2026 | mask_pending | mask_waiting) & mask_bk3
    bk_ka_order_s3 = df[mask_bk_all_s3].groupby('ka')['ape'].sum().sort_values(ascending=False).index.tolist()
    bk_ka_extra_s3 = [k for k in df[mask_bk3]['ka'].unique() if k not in bk_ka_order_s3]
    bk_ka_order_s3 = bk_ka_order_s3 + bk_ka_extra_s3

    r, bk_order_M = write_weekly_ka(ws3, r, 'M-APE. 周度预约业绩—银行 (APE)', '📌 res_yw；排除流失类；⭐ 按该表自身合计APE降序', 'res_yw', mask_c & mask_bk3, bk_kas_s3)
    r = write_weekly_ka_cnt(ws3, r, 'M-件数. 周度预约业绩—银行 (件数)', '📌 同M-APE；行顺序跟随APE子表', 'res_yw', mask_c & mask_bk3, bk_order_M)
    r, bk_order_N = write_weekly_ka(ws3, r, 'N-APE. 周度签单业绩—银行 (APE)', '📌 sign_yw；排除排期及流失；⭐ 按该表自身合计APE降序', 'sign_yw', mask_d2 & mask_bk3, bk_kas_s3)
    r = write_weekly_ka_cnt(ws3, r, 'N-件数. 周度签单业绩—银行 (件数)', '📌 同N-APE；行顺序跟随APE子表', 'sign_yw', mask_d2 & mask_bk3, bk_order_N)
    r, bk_order_O = write_weekly_ka(ws3, r, 'O-APE. 周度批核业绩—银行 (APE)', '📌 issue_yw；仅生效；⭐ 按该表自身合计APE降序', 'issue_yw', mask_e2 & mask_bk3, bk_kas_s3)
    r = write_weekly_ka_cnt(ws3, r, 'O-件数. 周度批核业绩—银行 (件数)', '📌 同O-APE；行顺序跟随APE子表', 'issue_yw', mask_e2 & mask_bk3, bk_order_O)

    print("Sheet3 done, row:", r)

    # ============================================================
    # SHEET 4: 产品端视角
    # ============================================================
    ws4 = wb.create_sheet("S4_产品端视角")
    ws4.column_dimensions['A'].width = 30
    for col in 'BCDEFGH': ws4.column_dimensions[col].width = 16

    r=1
    ws4.merge_cells(f'A{r}:H{r}')
    ws4[f'A{r}'] = 'Sheet 4  产品端视角 | Product View'; st_title(ws4[f'A{r}'])
    r+=2

    # A. 保险公司维度
    ws4.merge_cells(f'A{r}:H{r}')
    ws4[f'A{r}'] = 'A. 保险公司维度 | Carrier Dimension'; st_sub(ws4[f'A{r}'])
    r+=1; ws4[f'A{r}'] = '📌 sign_year=2026；status IN(生效/尚欠/已签/pending/待批核/排期)；全17家保司列出(零业务保留)；按APE降序'; st_note(ws4[f'A{r}'])
    r+=1
    hdrs=['保险公司','件数','APE','年总保费(HKD)','件数占比','APE件均','年总保费件均','APE占比']
    for j,h in enumerate(hdrs):
        c=ws4.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    mask_s26 = (df['sign_year']==2026) & df['status'].isin(['生效','尚欠保费','已签单','pending','待批核','排期'])
    # 动态追加数据中出现的新保司（与CSV逻辑对齐）
    data_carriers_s4 = df[mask_s26]['carrier'].dropna().unique().tolist()
    carriers_s4_full = CARRIERS_FULL + [c for c in data_carriers_s4 if c not in CARRIERS_FULL]
    carr_data=[]
    for car in carriers_s4_full:
        short=CARRIER_SHORT.get(car,car)
        sub=df[mask_s26 & (df['carrier']==car)]
        carr_data.append((short,len(sub),sub['ape'].sum(),sub['premium_hkd'].sum()))
    carr_data.sort(key=lambda x: -x[2])
    tot_cnt4=sum(x[1] for x in carr_data); tot_ape4=sum(x[2] for x in carr_data); tot_prem4=sum(x[3] for x in carr_data)
    for i,row_d in enumerate(carr_data):
        short,cnt,ape_v,prem=row_d
        vals=[short,cnt,ape_v,prem,safe_div(cnt,tot_cnt4),safe_div(ape_v,cnt),safe_div(prem,cnt),safe_div(ape_v,tot_ape4)]
        for j,v in enumerate(vals):
            c=ws4.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [2,3,5,6]: c.number_format='#,##0'
            if j in [4,7]: c.number_format='0.0%'
        r+=1
    for j,v in enumerate(['合计',tot_cnt4,tot_ape4,tot_prem4,1.0,safe_div(tot_ape4,tot_cnt4),safe_div(tot_prem4,tot_cnt4),1.0]):
        c=ws4.cell(row=r,column=j+1); c.value=v; st_total(c)
        if j in [2,3,5,6]: c.number_format='#,##0'
        if j in [4,7]: c.number_format='0.0%'
    r+=2

    # B. 产品TOP20 年总保费
    ws4.merge_cells(f'A{r}:H{r}')
    ws4[f'A{r}'] = 'B. 产品TOP20—年总保费 | Product TOP20 by Premium'; st_sub(ws4[f'A{r}'])
    r+=1; ws4[f'A{r}'] = '📌 ⭐ 联合主键=产品名称+年期+首年特殊折扣(SQ_rate)；sign_year=2026；status非流失；按年总保费降序'; st_note(ws4[f'A{r}'])
    r+=1
    hdrs=['排名','保司','产品名称','年期','首年折扣','件数','年总保费(HKD)','年总保费件均']
    for j,h in enumerate(hdrs):
        c=ws4.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    mask_prod = (df['sign_year']==2026) & ~df['status'].isin(['失效','退保','取消投保','搁置受保','取消预约'])
    prod_grp = df[mask_prod].groupby(['product','term','discount_special']).agg(
        cnt=('policy_id','count'), prem=('premium_hkd','sum'), ape=('ape','sum'),
        carrier=('carrier', lambda x: x.mode()[0] if len(x)>0 else '')).reset_index()
    prod_grp = prod_grp.sort_values('prem',ascending=False).head(20)
    for i,row_p in enumerate(prod_grp.itertuples()):
        short=CARRIER_SHORT.get(row_p.carrier, str(row_p.carrier)[:4] if row_p.carrier else '')
        disc = row_p.discount_special if pd.notna(row_p.discount_special) and str(row_p.discount_special).strip() not in ['','nan'] else ''
        vals=[i+1,short,row_p.product,row_p.term,disc,row_p.cnt,row_p.prem,safe_div(row_p.prem,row_p.cnt)]
        for j,v in enumerate(vals):
            c=ws4.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [6,7]: c.number_format='#,##0'
        r+=1
    r+=1

    # C. 产品TOP20 APE
    ws4.merge_cells(f'A{r}:H{r}')
    ws4[f'A{r}'] = 'C. 产品TOP20—APE | Product TOP20 by APE'; st_sub(ws4[f'A{r}'])
    r+=1; ws4[f'A{r}'] = '📌 ⭐ 联合主键同B区（产品名称+年期+首年特殊折扣）；按APE降序'; st_note(ws4[f'A{r}'])
    r+=1
    hdrs=['排名','保司','产品名称','年期','首年折扣','件数','APE','APE件均']
    for j,h in enumerate(hdrs):
        c=ws4.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    prod_grp_ape = df[mask_prod].groupby(['product','term','discount_special']).agg(
        cnt=('policy_id','count'), prem=('premium_hkd','sum'), ape=('ape','sum'),
        carrier=('carrier', lambda x: x.mode()[0] if len(x)>0 else '')).reset_index()
    prod_grp_ape = prod_grp_ape.sort_values('ape',ascending=False).head(20)
    for i,row_p in enumerate(prod_grp_ape.itertuples()):
        short=CARRIER_SHORT.get(row_p.carrier, str(row_p.carrier)[:4] if row_p.carrier else '')
        disc = row_p.discount_special if pd.notna(row_p.discount_special) and str(row_p.discount_special).strip() not in ['','nan'] else ''
        vals=[i+1,short,row_p.product,row_p.term,disc,row_p.cnt,row_p.ape,safe_div(row_p.ape,row_p.cnt)]
        for j,v in enumerate(vals):
            c=ws4.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [6,7]: c.number_format='#,##0'
        r+=1
    r+=1

    # D. 年期分布
    ws4.merge_cells(f'A{r}:G{r}')
    ws4[f'A{r}'] = 'D. 年期分布 | Term Distribution'; st_sub(ws4[f'A{r}'])
    r+=1; ws4[f'A{r}'] = '📌 sign_year=2026；status非流失；APO>0；4档：短期(≤1年)/中期(2-5年)/长期(6-20年)/终身(>20年)'; st_note(ws4[f'A{r}'])
    r+=1
    hdrs=['年期分类','件数','APE','年总保费(HKD)','件数占比','APE件均','年总保费件均']
    for j,h in enumerate(hdrs):
        c=ws4.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    term_cats=[('短期(≤1年)','短期(≤1年)'),('中期(2-5年)','中期(2-5年)'),('长期(6-20年)','长期(6-20年)'),('终身(>20年)','终身(>20年)')]
    sub_d = df[mask_prod]
    # FIX5: 只计APE>0的行（排除APE为空/0的排期单等）
    sub_d_valid = sub_d[sub_d['ape']>0]
    tot_tc=len(sub_d_valid); tot_ta=sub_d_valid['ape'].sum(); tot_tp=sub_d_valid['premium_hkd'].sum()
    for i,(lbl,tc) in enumerate(term_cats):
        sub=sub_d_valid[sub_d_valid['term_cat']==tc]
        cnt=len(sub); ape_v=sub['ape'].sum(); prem_v=sub['premium_hkd'].sum()
        vals=[lbl,cnt,ape_v,prem_v,
              safe_div(cnt,tot_tc),safe_div(ape_v,cnt),safe_div(prem_v,cnt)]
        for j,v in enumerate(vals):
            c=ws4.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [2,3,5,6]: c.number_format='#,##0'
            if j==4: c.number_format='0.0%'
        r+=1
    for j,v in enumerate(['合计',tot_tc,tot_ta,tot_tp,1.0,safe_div(tot_ta,tot_tc),safe_div(tot_tp,tot_tc)]):
        c=ws4.cell(row=r,column=j+1); c.value=v; st_total(c)
        if j in [2,3,5,6]: c.number_format='#,##0'
        if j==4: c.number_format='0.0%'
    r+=2

    # E. 供款方式
    ws4.merge_cells(f'A{r}:G{r}')
    ws4[f'A{r}'] = 'E. 供款方式分布 | Payment Mode Distribution'; st_sub(ws4[f'A{r}'])
    r+=1; ws4[f'A{r}'] = '📌 sign_year=2026；status非流失；APO>0；供款方式：预缴/年缴/整付'; st_note(ws4[f'A{r}'])
    r+=1
    hdrs=['供款方式','件数','APE','年总保费(HKD)','件数占比','APE件均','年总保费件均']
    for j,h in enumerate(hdrs):
        c=ws4.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    pay_modes=['预缴','年缴','整付']
    # FIX5: 供款方式同样只计APE>0的行
    tot_tc_e=len(sub_d_valid); tot_ta_e=sub_d_valid['ape'].sum(); tot_tp_e=sub_d_valid['premium_hkd'].sum()
    for i,pm in enumerate(pay_modes):
        sub=sub_d_valid[sub_d_valid['payment_mode']==pm]
        cnt=len(sub); ape_v=sub['ape'].sum(); prem_v=sub['premium_hkd'].sum()
        vals=[pm,cnt,ape_v,prem_v,
              safe_div(cnt,tot_tc_e),safe_div(ape_v,cnt),safe_div(prem_v,cnt)]
        for j,v in enumerate(vals):
            c=ws4.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [2,3,5,6]: c.number_format='#,##0'
            if j==4: c.number_format='0.0%'
        r+=1
    for j,v in enumerate(['合计',tot_tc_e,tot_ta_e,tot_tp_e,1.0,safe_div(tot_ta_e,tot_tc_e),safe_div(tot_tp_e,tot_tc_e)]):
        c=ws4.cell(row=r,column=j+1); c.value=v; st_total(c)
        if j in [2,3,5,6]: c.number_format='#,##0'
        if j==4: c.number_format='0.0%'
    r+=1
    print("Sheet4 done, row:", r)

    # ============================================================
    # SHEET 5: 财务端视角
    # ============================================================
    ws5 = wb.create_sheet("S5_财务端视角")
    ws5.column_dimensions['A'].width = 28
    for col in 'BCDEFGHIJKL': ws5.column_dimensions[col].width = 16

    r=1
    ws5.merge_cells(f'A{r}:L{r}')
    ws5[f'A{r}'] = 'Sheet 5  财务端视角 | Finance View'; st_title(ws5[f'A{r}'])
    r+=2

    # A. 牌照维度
    ws5.merge_cells(f'A{r}:G{r}')
    ws5[f'A{r}'] = 'A. 牌照维度—2026批核 | License Dimension'; st_sub(ws5[f'A{r}'])
    r+=1; ws5[f'A{r}'] = '📌 status=生效 AND issue_year=2026; 按年总保费降序'; st_note(ws5[f'A{r}'])
    r+=1
    hdrs=['牌照(签单供应商)','件数','批核APE','批核年总保费(HKD)','件数占比','APE占比','批核年总保费占比']
    for j,h in enumerate(hdrs):
        c=ws5.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    lic_data=[]
    for lic in licenses:
        sub=df[mask_eff2026 & (df['issuing_entity']==lic)]
        lic_data.append((lic,len(sub),sub['ape'].sum(),sub['premium_hkd'].sum()))
    # Also check actual licenses in data
    actual_lics = df[mask_eff2026]['issuing_entity'].unique()
    for alic in actual_lics:
        if alic not in licenses and pd.notna(alic):
            sub=df[mask_eff2026 & (df['issuing_entity']==alic)]
            lic_data.append((alic,len(sub),sub['ape'].sum(),sub['premium_hkd'].sum()))
    lic_data.sort(key=lambda x: -x[3])
    tot_lc=sum(x[1] for x in lic_data); tot_la=sum(x[2] for x in lic_data); tot_lp=sum(x[3] for x in lic_data)
    for i,row_l in enumerate(lic_data):
        lic,cnt,ape_v,prem=row_l
        vals=[lic,cnt,ape_v,prem,safe_div(cnt,tot_lc),safe_div(ape_v,tot_la),safe_div(prem,tot_lp)]
        for j,v in enumerate(vals):
            c=ws5.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [2,3]: c.number_format='#,##0'
            if j in [4,5,6]: c.number_format='0.0%'
        r+=1
    for j,v in enumerate(['合计',tot_lc,tot_la,tot_lp,1.0,1.0,1.0]):
        c=ws5.cell(row=r,column=j+1); c.value=v; st_total(c)
        if j in [2,3]: c.number_format='#,##0'
        if j in [4,5,6]: c.number_format='0.0%'
    r+=2

    # B/C. 牌照×批核月度趋势
    issue_months_5 = issue_months  # 动态取批核月，与CSV对齐
    for (title,note,val_col,fmt) in [
        ('B-保费. 牌照×批核月度年总保费','📌 status=生效；issue_ym；年总保费(HKD)','premium_hkd','#,##0'),
        ('B-件数. 牌照×批核月度件数','📌 status=生效；issue_ym；件数',None,None),
        ('C-APE. 牌照×批核月度APE','📌 status=生效；issue_ym；APE','ape','#,##0'),
        ('C-件数. 牌照×批核月度件数','📌 status=生效；issue_ym；件数',None,None),
    ]:
        ws5.merge_cells(f'A{r}:{get_column_letter(1+len(issue_months_5)+1)}{r}')
        ws5[f'A{r}'] = title; st_sub(ws5[f'A{r}'])
        r+=1; ws5[f'A{r}'] = note; st_note(ws5[f'A{r}'])
        r+=1
        hdrs=['牌照']+issue_months_5+['合计']
        for j,h in enumerate(hdrs):
            c=ws5.cell(row=r,column=j+1); c.value=h; st_hdr(c)
        r+=1
        tot_row=[0]*len(issue_months_5)
        lic_list = [x[0] for x in sorted(lic_data,key=lambda x: -x[3])]
        for i,lic in enumerate(lic_list):
            lm=df['issuing_entity']==lic
            vals=[lic]; row_tot=0
            for k,ym in enumerate(issue_months_5):
                sub=df[mask_e2 & (df['issue_ym']==ym) & lm]
                v=sub[val_col].sum() if val_col else len(sub)
                vals.append(v); row_tot+=v; tot_row[k]+=v
            vals.append(row_tot)
            for j,v in enumerate(vals):
                c=ws5.cell(row=r,column=j+1); c.value=v
                if i%2==0: st_data(c,True)
                else: st_data(c)
                if j>0 and fmt: c.number_format=fmt
            r+=1
        tot_vals=['合计']+tot_row+[sum(tot_row)]
        for j,v in enumerate(tot_vals):
            c=ws5.cell(row=r,column=j+1); c.value=v; st_total(c)
            if j>0 and fmt: c.number_format=fmt
        r+=2

    # D. 保费规模分布
    ws5.merge_cells(f'A{r}:F{r}')
    ws5[f'A{r}'] = 'D. 保费规模分布—2026批核 | Premium Size Distribution'; st_sub(ws5[f'A{r}'])
    r+=1; ws5[f'A{r}'] = '📌 status=生效 AND issue_year=2026; 按premium(HKD)分档'; st_note(ws5[f'A{r}'])
    r+=1
    hdrs=['保费规模档','件数','年总保费(HKD)','年总保费件均','年总保费占比','融资年总保费占比']
    for j,h in enumerate(hdrs):
        c=ws5.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    prem_tiers=['<5万','5-20万','20-50万','50-100万','100万+']
    sub_d5=df[mask_eff2026]
    tot_p5=sub_d5['premium_hkd'].sum()
    for i,pt in enumerate(prem_tiers):
        sub=sub_d5[sub_d5['prem_tier']==pt]
        pf_sub=sub[sub['is_pf']==1]
        vals=[pt,len(sub),sub['premium_hkd'].sum(),safe_div(sub['premium_hkd'].sum(),len(sub) if len(sub)>0 else 1),
              safe_div(sub['premium_hkd'].sum(),tot_p5),safe_div(pf_sub['premium_hkd'].sum(),sub['premium_hkd'].sum())]
        for j,v in enumerate(vals):
            c=ws5.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [2,3]: c.number_format='#,##0'
            if j in [4,5]: c.number_format='0.0%'
        r+=1
    for j,v in enumerate(['合计',len(sub_d5),tot_p5,safe_div(tot_p5,len(sub_d5)),1.0,safe_div(sub_d5[sub_d5['is_pf']==1]['premium_hkd'].sum(),tot_p5)]):
        c=ws5.cell(row=r,column=j+1); c.value=v; st_total(c)
        if j in [2,3]: c.number_format='#,##0'
        if j in [4,5]: c.number_format='0.0%'
    r+=2

    # E. APE规模分布
    ws5.merge_cells(f'A{r}:F{r}')
    ws5[f'A{r}'] = 'E. APE规模分布—2026批核 | APE Size Distribution'; st_sub(ws5[f'A{r}'])
    r+=1; ws5[f'A{r}'] = '📌 status=生效 AND issue_year=2026; 按ape分档'; st_note(ws5[f'A{r}'])
    r+=1
    hdrs=['APE规模档','件数','APE','APE占比','APE件均','融资APE占比']
    for j,h in enumerate(hdrs):
        c=ws5.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    ape_tiers=['<3万','3-15万','15-40万','40-80万','80万+']
    tot_a5=sub_d5['ape'].sum()
    for i,at in enumerate(ape_tiers):
        sub=sub_d5[sub_d5['ape_tier']==at]
        pf_sub=sub[sub['is_pf']==1]
        vals=[at,len(sub),sub['ape'].sum(),safe_div(sub['ape'].sum(),tot_a5),
              safe_div(sub['ape'].sum(),len(sub) if len(sub)>0 else 1),
              safe_div(pf_sub['ape'].sum(),sub['ape'].sum())]
        for j,v in enumerate(vals):
            c=ws5.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [2,4]: c.number_format='#,##0'
            if j in [3,5]: c.number_format='0.0%'
        r+=1
    for j,v in enumerate(['合计',len(sub_d5),tot_a5,1.0,safe_div(tot_a5,len(sub_d5)),safe_div(sub_d5[sub_d5['is_pf']==1]['ape'].sum(),tot_a5)]):
        c=ws5.cell(row=r,column=j+1); c.value=v; st_total(c)
        if j in [2,4]: c.number_format='#,##0'
        if j in [3,5]: c.number_format='0.0%'
    r+=2

    # F. 常规vs融资
    ws5.merge_cells(f'A{r}:G{r}')
    ws5[f'A{r}'] = 'F. 常规 vs 融资对比—2026批核 | Regular vs PF'; st_sub(ws5[f'A{r}'])
    r+=1; ws5[f'A{r}'] = '📌 status=生效 AND issue_year=2026; Is_PF=0常规, 1融资'; st_note(ws5[f'A{r}'])
    r+=1
    hdrs=['类型','件数','APE','年总保费(HKD)','件数占比','APE占比','年总保费占比']
    for j,h in enumerate(hdrs):
        c=ws5.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    tot_cnt5=len(sub_d5); tot_ape5=sub_d5['ape'].sum(); tot_prem5=sub_d5['premium_hkd'].sum()
    for i,(lbl,pf_val) in enumerate([('常规',0),('融资',1)]):
        sub=sub_d5[sub_d5['is_pf']==pf_val]
        vals=[lbl,len(sub),sub['ape'].sum(),sub['premium_hkd'].sum(),
              safe_div(len(sub),tot_cnt5),safe_div(sub['ape'].sum(),tot_ape5),safe_div(sub['premium_hkd'].sum(),tot_prem5)]
        for j,v in enumerate(vals):
            c=ws5.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [2,3]: c.number_format='#,##0'
            if j in [4,5,6]: c.number_format='0.0%'
        r+=1
    for j,v in enumerate(['合计',tot_cnt5,tot_ape5,tot_prem5,1.0,1.0,1.0]):
        c=ws5.cell(row=r,column=j+1); c.value=v; st_total(c)
        if j in [2,3]: c.number_format='#,##0'
        if j in [4,5,6]: c.number_format='0.0%'
    r+=2

    # G. 大额保单TOP20 保费
    ws5.merge_cells(f'A{r}:L{r}')
    ws5[f'A{r}'] = 'G. 大额保单TOP20—年总保费 | Top20 by Premium'; st_sub(ws5[f'A{r}'])
    r+=1; ws5[f'A{r}'] = '📌 status=生效 AND issue_year=2026; 按premium(HKD)降序TOP20'; st_note(ws5[f'A{r}'])
    r+=1
    hdrs=['排名','保单号','签单日','牌照','KA','保司','产品','年期','APE','年总保费(HKD)','类型','状态']
    for j,h in enumerate(hdrs):
        c=ws5.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    top20p = sub_d5.nlargest(20,'premium_hkd')
    for i,row_p in enumerate(top20p.itertuples()):
        pf_lbl='融资' if row_p.is_pf==1 else '常规'
        short=CARRIER_SHORT.get(row_p.carrier,row_p.carrier)
        lic_short=str(row_p.issuing_entity)[:4] if row_p.issuing_entity else ''
        vals=[i+1,row_p.policy_no,str(row_p.sign_date)[:10],lic_short,row_p.ka,short,row_p.product,
              row_p.term,row_p.ape,row_p.premium_hkd,pf_lbl,row_p.status]
        for j,v in enumerate(vals):
            c=ws5.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [8,9]: c.number_format='#,##0'
        r+=1

    r+=1
    # H. 大额保单TOP20 APE
    ws5.merge_cells(f'A{r}:L{r}')
    ws5[f'A{r}'] = 'H. 大额保单TOP20—APE | Top20 by APE'; st_sub(ws5[f'A{r}'])
    r+=1; ws5[f'A{r}'] = '📌 status=生效 AND issue_year=2026; 按APE降序TOP20'; st_note(ws5[f'A{r}'])
    r+=1
    hdrs=['排名','保单号','签单日','牌照','KA','保司','产品','年期','APE','年总保费(HKD)','类型','状态']
    for j,h in enumerate(hdrs):
        c=ws5.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    top20a = sub_d5.nlargest(20,'ape')
    for i,row_p in enumerate(top20a.itertuples()):
        pf_lbl='融资' if row_p.is_pf==1 else '常规'
        short=CARRIER_SHORT.get(row_p.carrier,row_p.carrier)
        lic_short=str(row_p.issuing_entity)[:4] if row_p.issuing_entity else ''
        vals=[i+1,row_p.policy_no,str(row_p.sign_date)[:10],lic_short,row_p.ka,short,row_p.product,
              row_p.term,row_p.ape,row_p.premium_hkd,pf_lbl,row_p.status]
        for j,v in enumerate(vals):
            c=ws5.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [8,9]: c.number_format='#,##0'
        r+=1

    print("Sheet5 done, row:", r)

    # ============================================================
    # SHEET 6: 市场与交叉视角
    # ============================================================
    ws6 = wb.create_sheet("S6_市场与交叉视角")
    ws6.column_dimensions['A'].width = 22
    for i in range(2, 12): ws6.column_dimensions[get_column_letter(i)].width = 14

    r=1
    ws6.merge_cells(f'A{r}:K{r}')
    ws6[f'A{r}'] = 'Sheet 6  市场与交叉视角 | Market & Cross-Analysis View'; st_title(ws6[f'A{r}'])
    r+=2

    def write_cross_matrix(ws, r, title, note, row_vals, row_label, status_mask, value_type='ape'):
        n_segs = len(SEGMENTS)
        ws.merge_cells(f'A{r}:{get_column_letter(n_segs+2)}{r}')
        ws[f'A{r}'] = title; st_sub(ws[f'A{r}'])
        r+=1; ws[f'A{r}'] = note; st_note(ws[f'A{r}'])
        r+=1
        hdrs=[row_label]+SEGMENTS+['合计']
        for j,h in enumerate(hdrs):
            c=ws.cell(row=r,column=j+1); c.value=h; st_hdr(c)
        r+=1
        tot_cols=[0]*n_segs
        for i,row_val in enumerate(row_vals):
            rm = df[row_label if row_label in df.columns else ('ka' if row_label=='KA' else row_label.lower())] == row_val
            # handle different row dimensions
            vals=[row_val]
            row_tot=0
            for k,seg in enumerate(SEGMENTS):
                sm=df['segment']==seg
                if value_type=='ape':
                    v=df[status_mask&rm&sm]['ape'].sum()
                else:
                    v=df[status_mask&rm&sm].shape[0]
                vals.append(v); row_tot+=v; tot_cols[k]+=v
            vals.append(row_tot)
            for j,v in enumerate(vals):
                c=ws.cell(row=r,column=j+1); c.value=v
                if i%2==0: st_data(c,True)
                else: st_data(c)
                if j>0 and value_type=='ape': c.number_format='#,##0'
            r+=1
        tot_vals=['合计']+tot_cols+[sum(tot_cols)]
        for j,v in enumerate(tot_vals):
            c=ws.cell(row=r,column=j+1); c.value=v; st_total(c)
            if j>0 and value_type=='ape': c.number_format='#,##0'
        r+=2
        return r

    # Get KA list sorted by 2026 batch APE
    ka_list = df[mask_eff2026].groupby('ka')['ape'].sum().sort_values(ascending=False).index.tolist()
    # Get carrier list sorted by 2026 batch APE
    carrier_list = df[mask_eff2026].groupby('carrier')['ape'].sum().sort_values(ascending=False).index.tolist()

    # A. 业务细分×KA 2026批核
    for (title,note,s_mask,vtype) in [
        ('A-APE. 业务细分×KA—2026批核 (APE)','📌 status=生效 AND issue_year=2026',mask_eff2026,'ape'),
        ('A-件数. 业务细分×KA—2026批核 (件数)','📌 status=生效 AND issue_year=2026',mask_eff2026,'cnt'),
        ('B-APE. 业务细分×KA—未批核 (APE)','📌 status IN(尚欠/已签/pending/待批核)',mask_pending,'ape'),
        ('B-件数. 业务细分×KA—未批核 (件数)','📌 status IN(尚欠/已签/pending/待批核)',mask_pending,'cnt'),
        ('C-APE. 业务细分×KA—待签 (APE)','📌 status=排期',mask_waiting,'ape'),
        ('C-件数. 业务细分×KA—待签 (件数)','📌 status=排期',mask_waiting,'cnt'),
    ]:
        n_segs=len(SEGMENTS)
        ws6.merge_cells(f'A{r}:{get_column_letter(n_segs+2)}{r}')
        ws6[f'A{r}'] = title; st_sub(ws6[f'A{r}'])
        r+=1; ws6[f'A{r}'] = note; st_note(ws6[f'A{r}'])
        r+=1
        hdrs=['KA']+SEGMENTS+['合计']
        for j,h in enumerate(hdrs):
            c=ws6.cell(row=r,column=j+1); c.value=h; st_hdr(c)
        r+=1
        tot_cols=[0]*n_segs
        # Only show KAs with any activity under this mask
        active_kas = df[s_mask]['ka'].unique()
        ka_list_active = [k for k in ka_list if k in active_kas]
        if vtype=='ape':
            ka_sorted = df[s_mask].groupby('ka')['ape'].sum().sort_values(ascending=False).index.tolist()
        else:
            ka_sorted = df[s_mask].groupby('ka').size().sort_values(ascending=False).index.tolist()

        for i,ka in enumerate(ka_sorted):
            km=df['ka']==ka
            vals=[ka]
            row_tot=0
            for k,seg in enumerate(SEGMENTS):
                sm=df['segment']==seg
                v=df[s_mask&km&sm]['ape'].sum() if vtype=='ape' else df[s_mask&km&sm].shape[0]
                vals.append(v); row_tot+=v; tot_cols[k]+=v
            vals.append(row_tot)
            for j,v in enumerate(vals):
                c=ws6.cell(row=r,column=j+1); c.value=v
                if i%2==0: st_data(c,True)
                else: st_data(c)
                if j>0 and vtype=='ape': c.number_format='#,##0'
            r+=1
        tot_vals=['合计']+tot_cols+[sum(tot_cols)]
        for j,v in enumerate(tot_vals):
            c=ws6.cell(row=r,column=j+1); c.value=v; st_total(c)
            if j>0 and vtype=='ape': c.number_format='#,##0'
        r+=2

    # D/E/F: carrier x segment
    for (title,note,s_mask,vtype) in [
        ('D-APE. 业务细分×保司—2026批核 (APE)','📌 status=生效 AND issue_year=2026',mask_eff2026,'ape'),
        ('D-件数. 业务细分×保司—2026批核 (件数)','📌 status=生效 AND issue_year=2026',mask_eff2026,'cnt'),
        ('E-APE. 业务细分×保司—未批核 (APE)','📌 status IN(尚欠/已签/pending/待批核)',mask_pending,'ape'),
        ('E-件数. 业务细分×保司—未批核 (件数)','📌 status IN(尚欠/已签/pending/待批核)',mask_pending,'cnt'),
        ('F-APE. 业务细分×保司—待签 (APE)','📌 status=排期',mask_waiting,'ape'),
        ('F-件数. 业务细分×保司—待签 (件数)','📌 status=排期',mask_waiting,'cnt'),
    ]:
        n_segs=len(SEGMENTS)
        ws6.merge_cells(f'A{r}:{get_column_letter(n_segs+2)}{r}')
        ws6[f'A{r}'] = title; st_sub(ws6[f'A{r}'])
        r+=1; ws6[f'A{r}'] = note; st_note(ws6[f'A{r}'])
        r+=1
        hdrs=['保司']+SEGMENTS+['合计']
        for j,h in enumerate(hdrs):
            c=ws6.cell(row=r,column=j+1); c.value=h; st_hdr(c)
        r+=1
        tot_cols=[0]*n_segs
        if vtype=='ape':
            car_sorted=df[s_mask].groupby('carrier')['ape'].sum().sort_values(ascending=False).index.tolist()
        else:
            car_sorted=df[s_mask].groupby('carrier').size().sort_values(ascending=False).index.tolist()
        for i,car in enumerate(car_sorted):
            short=CARRIER_SHORT.get(car,car)
            cm=df['carrier']==car
            vals=[short]
            row_tot=0
            for k,seg in enumerate(SEGMENTS):
                sm=df['segment']==seg
                v=df[s_mask&cm&sm]['ape'].sum() if vtype=='ape' else df[s_mask&cm&sm].shape[0]
                vals.append(v); row_tot+=v; tot_cols[k]+=v
            vals.append(row_tot)
            for j,v in enumerate(vals):
                c=ws6.cell(row=r,column=j+1); c.value=v
                if i%2==0: st_data(c,True)
                else: st_data(c)
                if j>0 and vtype=='ape': c.number_format='#,##0'
            r+=1
        tot_vals=['合计']+tot_cols+[sum(tot_cols)]
        for j,v in enumerate(tot_vals):
            c=ws6.cell(row=r,column=j+1); c.value=v; st_total(c)
            if j>0 and vtype=='ape': c.number_format='#,##0'
        r+=2

    print("Sheet6 done, row:", r)

    # ============================================================
    # SHEET 7: 合规端视角
    # ============================================================
    ws7 = wb.create_sheet("S7_合规端视角")
    ws7.column_dimensions['A'].width = 26
    for i in range(2,15): ws7.column_dimensions[get_column_letter(i)].width = 14

    r=1
    ws7.merge_cells(f'A{r}:N{r}')
    ws7[f'A{r}'] = 'Sheet 7  合规端视角 | Compliance View'; st_title(ws7[f'A{r}'])
    r+=2

    # A. 牌照合规概览
    ws7.merge_cells(f'A{r}:M{r}')
    ws7[f'A{r}'] = 'A. 牌照合规概览 | License Compliance Overview'; st_sub(ws7[f'A{r}'])
    r+=1; ws7[f'A{r}'] = '📌 10个牌照；2026批核/未批核/待签分别统计；按合计APE降序'; st_note(ws7[f'A{r}'])
    r+=1
    hdrs=['签单供应商','2026批核APE','批核件数','未批核APE','未批核件数','待签APE','待签件数','合计APE','合计件数','保险公司数','产品数','KA数','TR数']
    for j,h in enumerate(hdrs):
        c=ws7.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    lic_comp=[]
    all_lics = licenses
    for lic in all_lics:
        lm=df['issuing_entity']==lic
        a26=df[mask_eff2026&lm]['ape'].sum(); c26=df[mask_eff2026&lm].shape[0]
        ap=df[mask_pending&lm]['ape'].sum(); cp=df[mask_pending&lm].shape[0]
        aw=df[mask_waiting&lm]['ape'].sum(); cw=df[mask_waiting&lm].shape[0]
        n_car=df[(mask_eff2026|mask_pending|mask_waiting)&lm]['carrier'].nunique()
        n_prod=df[(mask_eff2026|mask_pending|mask_waiting)&lm]['product'].nunique()
        n_ka=df[(mask_eff2026|mask_pending|mask_waiting)&lm]['ka'].nunique()
        n_tr=df[(mask_eff2026|mask_pending|mask_waiting)&lm]['tr'].nunique()
        tot_a=a26+ap+aw; tot_c=c26+cp+cw
        lic_comp.append((lic,a26,c26,ap,cp,aw,cw,tot_a,tot_c,n_car,n_prod,n_ka,n_tr))
    lic_comp.sort(key=lambda x: -x[7])
    for i,vals in enumerate(lic_comp):
        for j,v in enumerate(vals):
            c=ws7.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [1,3,5,7]: c.number_format='#,##0'
        r+=1
    tot7=['合计']+[sum(x[k] for x in lic_comp) for k in range(1,9)]+['-','-','-','-']
    for j,v in enumerate(tot7):
        c=ws7.cell(row=r,column=j+1); c.value=v; st_total(c)
        if j in [1,3,5,7]: c.number_format='#,##0'
    r+=2

    # B/C/D: 牌照×业务细分矩阵
    for (title,note,s_mask,vtype) in [
        ('B-APE. 牌照×业务细分—2026批核 (APE)','📌 status=生效 AND issue_year=2026',mask_eff2026,'ape'),
        ('B-件数. 牌照×业务细分—2026批核 (件数)','📌 status=生效 AND issue_year=2026',mask_eff2026,'cnt'),
        ('C-APE. 牌照×业务细分—未批核 (APE)','📌 status IN(尚欠/已签/pending/待批核)',mask_pending,'ape'),
        ('C-件数. 牌照×业务细分—未批核 (件数)','📌 status IN(尚欠/已签/pending/待批核)',mask_pending,'cnt'),
        ('D-APE. 牌照×业务细分—待签 (APE)','📌 status=排期',mask_waiting,'ape'),
        ('D-件数. 牌照×业务细分—待签 (件数)','📌 status=排期',mask_waiting,'cnt'),
    ]:
        n_segs=len(SEGMENTS)
        ws7.merge_cells(f'A{r}:{get_column_letter(n_segs+2)}{r}')
        ws7[f'A{r}'] = title; st_sub(ws7[f'A{r}'])
        r+=1; ws7[f'A{r}'] = note; st_note(ws7[f'A{r}'])
        r+=1
        hdrs=['签单供应商']+SEGMENTS+['合计']
        for j,h in enumerate(hdrs):
            c=ws7.cell(row=r,column=j+1); c.value=h; st_hdr(c)
        r+=1
        tot_cols=[0]*n_segs
        lic_list7 = [x[0] for x in sorted(lic_comp,key=lambda x: -x[7])]
        for i,lic in enumerate(lic_list7):
            lm=df['issuing_entity']==lic
            vals=[lic]; row_tot=0
            for k,seg in enumerate(SEGMENTS):
                sm=df['segment']==seg
                v=df[s_mask&lm&sm]['ape'].sum() if vtype=='ape' else df[s_mask&lm&sm].shape[0]
                vals.append(v); row_tot+=v; tot_cols[k]+=v
            vals.append(row_tot)
            for j,v in enumerate(vals):
                c=ws7.cell(row=r,column=j+1); c.value=v
                if i%2==0: st_data(c,True)
                else: st_data(c)
                if j>0 and vtype=='ape': c.number_format='#,##0'
            r+=1
        tot_vals=['合计']+tot_cols+[sum(tot_cols)]
        for j,v in enumerate(tot_vals):
            c=ws7.cell(row=r,column=j+1); c.value=v; st_total(c)
            if j>0 and vtype=='ape': c.number_format='#,##0'
        r+=2

    # E. 签批时效异常预警
    ws7.merge_cells(f'A{r}:K{r}')
    ws7[f'A{r}'] = 'E. 签批时效异常预警 | TAT Warning (>60 Days)'; st_sub(ws7[f'A{r}'])
    r+=1; ws7[f'A{r}'] = '📌 status=生效 AND issue_year=2026 AND TAT>60天; 按时效天数降序'; st_note(ws7[f'A{r}'])
    r+=1
    hdrs=['保单号','签单日','批核日','时效(天)','牌照','KA','保司','产品','年期','APE','状态']
    for j,h in enumerate(hdrs):
        c=ws7.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    warn_df = df[mask_eff2026 & df['tat'].notna() & (df['tat']>60)].sort_values('tat',ascending=False)
    for i,row_w in enumerate(warn_df.itertuples()):
        short=CARRIER_SHORT.get(row_w.carrier,row_w.carrier)
        lic_s=str(row_w.issuing_entity)[:8] if row_w.issuing_entity else ''
        vals=[row_w.policy_no,str(row_w.sign_date)[:10],str(row_w.issue_date)[:10],
              row_w.tat,lic_s,row_w.ka,short,row_w.product,row_w.term,row_w.ape,row_w.status]
        for j,v in enumerate(vals):
            c=ws7.cell(row=r,column=j+1); c.value=v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j==9: c.number_format='#,##0'
        r+=1
    r+=1

    # F. TR人效
    ws7.merge_cells(f'A{r}:G{r}')
    ws7[f'A{r}'] = 'F. TR维度人效—2026签单 | TR Productivity'; st_sub(ws7[f'A{r}'])
    r+=1; ws7[f'A{r}'] = '📌 sign_year=2026; 除排期外所有状态; 按APE降序'; st_note(ws7[f'A{r}'])
    r+=1
    hdrs=['TR','APE','件数','件均APE','服务KA数','业务线数']
    for j,h in enumerate(hdrs):
        c=ws7.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1
    mask_tr = (df['sign_year']==2026) & ~df['status'].isin(['排期'])
    tr_grp = df[mask_tr].groupby('tr').agg(
        ape=('ape','sum'), cnt=('policy_id','count'),
        n_ka=('ka','nunique'), n_seg=('segment','nunique')).reset_index()
    tr_grp['je']=tr_grp['ape']/tr_grp['cnt']
    tr_grp = tr_grp.sort_values('ape',ascending=False)
    for i,row_t in enumerate(tr_grp.itertuples()):
        vals=[row_t.tr,row_t.ape,row_t.cnt,row_t.je,row_t.n_ka,row_t.n_seg]
        for j,v in enumerate(vals):
            c=ws7.cell(row=r,column=j+1); c.value=round(v,0) if isinstance(v,float) else v
            if i%2==0: st_data(c,True)
            else: st_data(c)
            if j in [1,3]: c.number_format='#,##0'
        r+=1
    tot7f=['合计',tr_grp['ape'].sum(),tr_grp['cnt'].sum(),safe_div(tr_grp['ape'].sum(),tr_grp['cnt'].sum()),
           df[mask_tr]['ka'].nunique(),df[mask_tr]['segment'].nunique()]
    for j,v in enumerate(tot7f):
        c=ws7.cell(row=r,column=j+1); c.value=round(v,0) if isinstance(v,float) else v; st_total(c)
        if j in [1,3]: c.number_format='#,##0'
    r+=1
    print("Sheet7 done, row:", r)

    # ============================================================
    # SHEET 8: 明细数据底表
    # ============================================================
    ws8 = wb.create_sheet("S8_明细数据底表")
    ws8.column_dimensions['A'].width = 14
    for i in range(2,45): ws8.column_dimensions[get_column_letter(i)].width = 16

    r=1
    ws8.merge_cells(f'A{r}:AR{r}')
    ws8[f'A{r}'] = f'Sheet 8  明细数据底表 | Raw Data ({len(df):,} Records，0409底数 (2779条))'
    st_title(ws8[f'A{r}'])
    r+=1

    # Header row
    orig_hdrs = ['订单编号','保单号码','保单状态','签单供应商','业务类型','业务细分','市场细分',
        'KEY ACCOUNT','公司名字','合作伙伴','保险公司','产品品类','产品名称','年期','供款方式',
        '币种','保费','保费（港币）','APE','保额','是否融资单','客户分群','首年特殊折扣',
        '预约日期','签单日期','递交日期','批核日（年/月/日）','同行推荐人','注册编号IA','TR',
        '保单阶段','业务大类','年期分类','融资标签','首年折扣(标准化)','保费分档','APE分档',
        '签批时效(天)','签单年','签单年月','批核年','批核年月','预约年月']
    for j,h in enumerate(orig_hdrs):
        c=ws8.cell(row=r,column=j+1); c.value=h; st_hdr(c)
    r+=1

    # Write data rows
    orig_cols = ['policy_id','policy_no','status','issuing_entity','biz_type','segment','market_seg',
        'ka','company','partner','carrier','product_cat','product','term','payment_mode',
        'currency','premium_orig','premium_hkd','ape','sum_assured','is_pf','cust_type',
        'discount_special','res_date','sign_date','submit_date','issue_date','referral',
        'tr_reg','tr','phase','biz_cat','term_cat','pf_label','discount_std','prem_tier',
        'ape_tier','tat','sign_year','sign_ym','issue_year','issue_ym','res_ym']

    available_cols = [c for c in orig_cols if c in df.columns]
    for i,row_d in enumerate(df[available_cols].itertuples(index=False)):
        for j,v in enumerate(row_d):
            c=ws8.cell(row=r,column=j+1)
            c.value = None if pd.isna(v) else v
            c.font = Font(size=8)
            if i%2==0: c.fill = PatternFill("solid",fgColor="F9F9F9")
        r+=1

    print("Sheet8 done, total rows:", r)

    # ============================================================
    # SHEET 9: 代理人与KA业务
    # ============================================================
    ws9 = wb.create_sheet("S9_代理人与KA业务")
    ws9.column_dimensions['A'].width = 22
    for col in 'BCDEFGHIJK': ws9.column_dimensions[col].width = 16

    r = 1
    ws9.merge_cells(f'A{r}:K{r}')
    ws9[f'A{r}'] = 'Sheet 9  代理人与KA业务 | Agent & KA Business View'
    st_title(ws9[f'A{r}'])
    r += 2

    # ── A. 业务细分年度汇总（天领/成事家办/BK，样式同S2-A）───────────
    S9_SEGS = ['天领业务', '成事家办', '合伙转介业务', 'ICLUB业务', 'IFA业务']
    ws9.merge_cells(f'A{r}:K{r}')
    ws9[f'A{r}'] = 'A. 业务细分年度汇总（代理人+KA）'
    st_sub(ws9[f'A{r}'])
    r += 1
    ws9[f'A{r}'] = '📌 天领业务/成事家办/合伙转介业务/ICLUB业务/IFA业务五条业务线；2026批核=生效+issue_year=2026；数据口径与S2-A完全一致'
    st_note(ws9[f'A{r}'])
    r += 1
    hdrs = ['业务细分','目标APE','达成率','2026批核APE','批核件数','未批核APE','未批核件数','待签APE','待签件数','合计APE','合计件数']
    for j, h in enumerate(hdrs):
        c = ws9.cell(row=r, column=j+1); c.value = h; st_hdr(c)
    r += 1
    s9a_ape = 0; s9a_cnt = 0; s9a_tgt = 0; s9a_ap = 0; s9a_cp = 0; s9a_aw = 0; s9a_cw = 0
    for i, seg in enumerate(S9_SEGS):
        cm = df['segment'] == seg
        a26 = df[mask_eff2026 & cm]['ape'].sum(); c26 = df[mask_eff2026 & cm].shape[0]
        ap = df[mask_pending & cm]['ape'].sum(); cp = df[mask_pending & cm].shape[0]
        aw = df[mask_waiting & cm]['ape'].sum(); cw = df[mask_waiting & cm].shape[0]
        tgt = TARGET_ALL.get(seg, 0); ach_r = safe_div(a26, tgt)
        s9a_ape += a26; s9a_cnt += c26; s9a_tgt += tgt
        s9a_ap += ap; s9a_cp += cp; s9a_aw += aw; s9a_cw += cw
        vals = [seg, int(tgt), f"{ach_r:.1%}" if tgt > 0 else '',
                int(round(a26)), c26, int(round(ap)), cp, int(round(aw)), cw,
                int(round(a26+ap+aw)), c26+cp+cw]
        for j, v in enumerate(vals):
            c = ws9.cell(row=r, column=j+1); c.value = v
            if i % 2 == 0: st_data(c, True)
            else: st_data(c)
        r += 1
    tot_ach = safe_div(s9a_ape, s9a_tgt)
    tot_vals = ['合计', int(s9a_tgt), f"{tot_ach:.1%}" if s9a_tgt > 0 else '',
                int(round(s9a_ape)), s9a_cnt,
                int(round(s9a_ap)), s9a_cp,
                int(round(s9a_aw)), s9a_cw,
                int(round(s9a_ape+s9a_ap+s9a_aw)), s9a_cnt+s9a_cp+s9a_cw]
    for j, v in enumerate(tot_vals):
        c = ws9.cell(row=r, column=j+1); c.value = v; st_total(c)
    r += 2

    # ── B/C. KA业绩分析（样式同S2-K）──────────────────────────────
    def write_s9_ka_table(ws, r, title, note, seg_filter):
        ws.merge_cells(f'A{r}:I{r}')
        ws[f'A{r}'] = title; st_sub(ws[f'A{r}'])
        r += 1; ws[f'A{r}'] = note; st_note(ws[f'A{r}'])
        r += 1
        hdrs = ['KEY ACCOUNT','2026批核APE','批核件数','未批核APE','未批核件数','待签APE','待签件数','总APE','总件数']
        for j, h in enumerate(hdrs):
            c = ws.cell(row=r, column=j+1); c.value = h; st_hdr(c)
        r += 1
        seg_mask = df['segment'] == seg_filter
        ka_sorted = (df[mask_eff2026 & seg_mask].groupby('ka')['ape'].sum()
                     .sort_values(ascending=False).index.tolist())
        ka_extra = [k for k in df[seg_mask & (mask_pending | mask_waiting)]['ka'].dropna().unique()
                    if k not in ka_sorted]
        ka_all = ka_sorted + ka_extra
        tot = [0] * 8
        for i, ka in enumerate(ka_all):
            km = df['ka'] == ka
            a26 = int(round(df[mask_eff2026 & km & seg_mask]['ape'].sum()))
            c26 = df[mask_eff2026 & km & seg_mask].shape[0]
            ap = int(round(df[mask_pending & km & seg_mask]['ape'].sum()))
            cp = df[mask_pending & km & seg_mask].shape[0]
            aw = int(round(df[mask_waiting & km & seg_mask]['ape'].sum()))
            cw = df[mask_waiting & km & seg_mask].shape[0]
            vals = [ka, a26, c26, ap, cp, aw, cw, a26+ap+aw, c26+cp+cw]
            for idx in range(8): tot[idx] += vals[idx+1]
            for j, v in enumerate(vals):
                c = ws.cell(row=r, column=j+1); c.value = v
                if i % 2 == 0: st_data(c, True)
                else: st_data(c)
            r += 1
        for j, v in enumerate(['合计'] + tot):
            c = ws.cell(row=r, column=j+1); c.value = v; st_total(c)
        r += 2
        return r

    r = write_s9_ka_table(ws9, r,
        'B. 天领业务—KA业绩分析 | Tian Ling KA Analysis',
        '📌 segment=天领业务；按key_account汇总；排序按2026批核APE降序',
        '天领业务')

    r = write_s9_ka_table(ws9, r,
        'C. 成事家办—KA业绩分析 | Cheng Shi KA Analysis',
        '📌 segment=成事家办；按key_account汇总；排序按2026批核APE降序',
        '成事家办')

    # ── D/E. 月度明细（2026年月度明细，包含流失单）───────────────────
    # 对应S1的C（预约res_ym）、D（签单sign_ym）、E（批核issue_ym）三区域
    # mask_c: 预约，排除取消预约；mask_d2: 签单，排除排期+取消预约；mask_e2: 批核，仅生效
    mask_c_s9  = ~df['status'].isin(['取消预约','失效','退保','取消投保','搁置受保'])
    mask_d2_s9 = ~df['status'].isin(['排期','取消预约','失效','退保','取消投保','搁置受保'])
    mask_e2_s9 = df['status'] == '生效'

    def write_s9_monthly_table(ws, r, title, note, seg_filter):
        seg_m = df['segment'] == seg_filter
        n_cols = len(months_26)
        ws.merge_cells(f'A{r}:{get_column_letter(n_cols+2)}{r}')
        ws[f'A{r}'] = title; st_sub(ws[f'A{r}'])
        r += 1; ws[f'A{r}'] = note; st_note(ws[f'A{r}'])
        r += 1
        # Header row
        hdrs = ['指标'] + [str(m) for m in months_26] + ['合计']
        for j, h in enumerate(hdrs):
            c = ws.cell(row=r, column=j+1); c.value = h; st_hdr(c)
        r += 1

        row_defs = [
            ('预约 APE',   mask_c_s9,  'res_ym',   'ape'),
            ('预约 件数',  mask_c_s9,  'res_ym',   'cnt'),
            ('签单 APE',   mask_d2_s9, 'sign_ym',  'ape'),
            ('签单 件数',  mask_d2_s9, 'sign_ym',  'cnt'),
            ('批核 APE',   mask_e2_s9, 'issue_ym', 'ape'),
            ('批核 件数',  mask_e2_s9, 'issue_ym', 'cnt'),
        ]
        for i, (label, base_mask, time_col, vtype) in enumerate(row_defs):
            sub_m = base_mask & seg_m
            vals = [label]
            row_tot = 0
            for ym in months_26:
                sub = df[sub_m & (df[time_col] == ym)]
                v = int(round(sub['ape'].sum())) if vtype == 'ape' else len(sub)
                vals.append(v); row_tot += v
            vals.append(int(round(row_tot)) if vtype == 'ape' else row_tot)
            for j, v in enumerate(vals):
                c = ws.cell(row=r, column=j+1); c.value = v
                if 'APE' in label: st_hl(c)
                else: st_data(c, i % 4 < 2)
            r += 1
        r += 1
        return r

    r = write_s9_monthly_table(ws9, r,
        'D. 天领业务月度明细（含流失单） | Tian Ling Monthly Detail',
        f'📌 segment=天领业务；预约=res_ym(排除取消预约)；签单=sign_ym(排除排期/取消预约)；批核=issue_ym(仅生效)；2026-01至{months_26[-1] if months_26 else "最新月"}',
        '天领业务')

    r = write_s9_monthly_table(ws9, r,
        'E. 成事家办月度明细（含流失单） | Cheng Shi Monthly Detail',
        f'📌 segment=成事家办；预约=res_ym(排除取消预约)；签单=sign_ym(排除排期/取消预约)；批核=issue_ym(仅生效)；2026-01至{months_26[-1] if months_26 else "最新月"}',
        '成事家办')

    # ── F. KA业务三细分各自KA汇总（ICLUB/合伙转介/IFA）─────────────
    KA_SEGS = ['ICLUB业务', '合伙转介业务', 'IFA业务']

    def write_s9_ka_table_generic(ws, r, title, note, seg_filter):
        """Generic KA table for any segment, style same as S2-K."""
        ws.merge_cells(f'A{r}:I{r}')
        ws[f'A{r}'] = title; st_sub(ws[f'A{r}'])
        r += 1; ws[f'A{r}'] = note; st_note(ws[f'A{r}'])
        r += 1
        hdrs = ['KEY ACCOUNT','2026批核APE','批核件数','未批核APE','未批核件数','待签APE','待签件数','总APE','总件数']
        for j, h in enumerate(hdrs):
            c = ws.cell(row=r, column=j+1); c.value = h; st_hdr(c)
        r += 1
        seg_mask = df['segment'] == seg_filter
        ka_sorted = (df[mask_eff2026 & seg_mask].groupby('ka')['ape'].sum()
                     .sort_values(ascending=False).index.tolist())
        ka_extra = [k for k in df[seg_mask & (mask_pending | mask_waiting)]['ka'].dropna().unique()
                    if k not in ka_sorted]
        ka_all = ka_sorted + ka_extra
        tot = [0] * 8
        for i, ka in enumerate(ka_all):
            km = df['ka'] == ka
            a26 = int(round(df[mask_eff2026 & km & seg_mask]['ape'].sum()))
            c26 = df[mask_eff2026 & km & seg_mask].shape[0]
            ap  = int(round(df[mask_pending & km & seg_mask]['ape'].sum()))
            cp  = df[mask_pending & km & seg_mask].shape[0]
            aw  = int(round(df[mask_waiting & km & seg_mask]['ape'].sum()))
            cw  = df[mask_waiting & km & seg_mask].shape[0]
            vals = [ka, a26, c26, ap, cp, aw, cw, a26+ap+aw, c26+cp+cw]
            for idx in range(8): tot[idx] += vals[idx+1]
            for j, v in enumerate(vals):
                c = ws.cell(row=r, column=j+1); c.value = v
                if i % 2 == 0: st_data(c, True)
                else: st_data(c)
            r += 1
        for j, v in enumerate(['合计'] + tot):
            c = ws.cell(row=r, column=j+1); c.value = v; st_total(c)
        r += 2
        return r

    ws9.merge_cells(f'A{r}:I{r}')
    ws9[f'A{r}'] = 'F. KA业务—各业务细分KA汇总'
    st_sub(ws9[f'A{r}'])
    r += 1
    ws9[f'A{r}'] = '📌 ICLUB业务/合伙转介业务/IFA业务三个业务细分，各自按key_account汇总；2026批核=生效+issue_year=2026'
    st_note(ws9[f'A{r}'])
    r += 2

    for seg in KA_SEGS:
        r = write_s9_ka_table_generic(ws9, r,
            f'F-{seg}. KA汇总 | {seg} KA Analysis',
            f'📌 segment={seg}；按key_account汇总；按2026批核APE降序',
            seg)

    # ── G. KA业务整体月度明细（ICLUB+合伙转介+IFA）─────────────────
    mask_ka3 = df['segment'].isin(KA_SEGS)
    n_cols_g = len(months_26)
    ws9.merge_cells(f'A{r}:{get_column_letter(n_cols_g+2)}{r}')
    ws9[f'A{r}'] = 'G. KA业务整体月度明细（含流失单） | KA Business Monthly Detail'
    st_sub(ws9[f'A{r}'])
    r += 1
    ws9[f'A{r}'] = (f'📌 segment IN(ICLUB业务,合伙转介业务,IFA业务)；'
                    f'预约=res_ym(排除取消预约)；签单=sign_ym(排除排期/取消预约)；批核=issue_ym(仅生效)；'
                    f'2026-01至{months_26[-1] if months_26 else "最新月"}')
    st_note(ws9[f'A{r}'])
    r += 1
    hdrs_g = ['指标'] + [str(m) for m in months_26] + ['合计']
    for j, h in enumerate(hdrs_g):
        c = ws9.cell(row=r, column=j+1); c.value = h; st_hdr(c)
    r += 1
    row_defs_g = [
        ('预约 APE',  mask_c_s9,  'res_ym',   'ape'),
        ('预约 件数', mask_c_s9,  'res_ym',   'cnt'),
        ('签单 APE',  mask_d2_s9, 'sign_ym',  'ape'),
        ('签单 件数', mask_d2_s9, 'sign_ym',  'cnt'),
        ('批核 APE',  mask_e2_s9, 'issue_ym', 'ape'),
        ('批核 件数', mask_e2_s9, 'issue_ym', 'cnt'),
    ]
    for i, (label, base_mask, time_col, vtype) in enumerate(row_defs_g):
        sub_m = base_mask & mask_ka3
        vals = [label]
        row_tot = 0
        for ym in months_26:
            sub = df[sub_m & (df[time_col] == ym)]
            v = int(round(sub['ape'].sum())) if vtype == 'ape' else len(sub)
            vals.append(v); row_tot += v
        vals.append(int(round(row_tot)) if vtype == 'ape' else row_tot)
        for j, v in enumerate(vals):
            c = ws9.cell(row=r, column=j+1); c.value = v
            if 'APE' in label: st_hl(c)
            else: st_data(c, i % 4 < 2)
        r += 1
    r += 2

    # ── H/I/J. 周度明细（参考S3 J/K/L 结构）───────────────────────
    def write_s9_weekly_ka_block(ws, r, section_title, section_note, seg_mask_weekly):
        """Write 6 sub-tables: APE+件数 × 预约/签单/批核, style same as S3 J/K/L."""

        # Pre-compute KA order by total APE desc across all statuses
        mask_all_w = (mask_eff2026 | mask_pending | mask_waiting) & seg_mask_weekly
        ka_order_base = (df[mask_all_w].groupby('ka')['ape'].sum()
                         .sort_values(ascending=False).index.tolist())
        ka_extra_w = [k for k in df[seg_mask_weekly]['ka'].dropna().unique()
                      if k not in ka_order_base]
        ka_pool = ka_order_base + ka_extra_w

        sub_defs = [
            ('预约', 'res_yw',   mask_c_s9,  '排除取消预约及流失类'),
            ('签单', 'sign_yw',  mask_d2_s9, '排除排期/取消预约及流失类'),
            ('批核', 'issue_yw', mask_e2_s9, '仅生效'),
        ]

        # Section header (just a note line, no merge needed — tables follow directly)
        ws.merge_cells(f'A{r}:{get_column_letter(len(weeks_26)+2)}{r}')
        ws[f'A{r}'] = section_title; st_sub(ws[f'A{r}'])
        r += 1
        ws[f'A{r}'] = section_note; st_note(ws[f'A{r}'])
        r += 2

        for cn, tc, sm, sm_note in sub_defs:
            # Compute per-KA totals for this table, sort descending
            ka_totals = {}
            for ka in ka_pool:
                km = df['ka'] == ka
                ka_totals[ka] = sum(
                    df[sm & seg_mask_weekly & km & (df[tc] == wk)]['ape'].sum()
                    for wk in weeks_26
                )
            active = sorted([ka for ka, v in ka_totals.items() if v > 0],
                            key=lambda k: -ka_totals[k])

            for vtype, suffix in [('ape', 'APE'), ('cnt', '件数')]:
                n_w = len(weeks_26)
                ws.merge_cells(f'A{r}:{get_column_letter(n_w+2)}{r}')
                ws[f'A{r}'] = f'{cn}—{suffix} | Weekly {cn} ({suffix})'
                st_sub(ws[f'A{r}'])
                r += 1
                ws[f'A{r}'] = f'📌 {tc}；{sm_note}；⭐ 按该表自身合计APE降序'
                st_note(ws[f'A{r}'])
                r += 1
                hdrs_w = ['KEY ACCOUNT'] + weeks_26 + ['合计']
                for j, h in enumerate(hdrs_w):
                    c = ws.cell(row=r, column=j+1); c.value = h; st_hdr(c)
                r += 1
                tot_row = [0] * n_w
                for i, ka in enumerate(active):
                    km = df['ka'] == ka
                    vals = [ka]; row_tot = 0
                    for k, wk in enumerate(weeks_26):
                        sub = df[sm & seg_mask_weekly & km & (df[tc] == wk)]
                        v = int(round(sub['ape'].sum())) if vtype == 'ape' else len(sub)
                        vals.append(v); row_tot += v; tot_row[k] += v
                    vals.append(int(round(row_tot)) if vtype == 'ape' else row_tot)
                    for j, v in enumerate(vals):
                        c = ws.cell(row=r, column=j+1); c.value = v
                        if i % 2 == 0: st_data(c, True)
                        else: st_data(c)
                    r += 1
                tot_vals = ['合计'] + tot_row + [sum(tot_row)]
                for j, v in enumerate(tot_vals):
                    c = ws.cell(row=r, column=j+1); c.value = v; st_total(c)
                r += 2
        return r

    r = write_s9_weekly_ka_block(ws9, r,
        'H. 天领业务周度明细 | Tian Ling Weekly Detail',
        '📌 segment=天领业务；按key_account拆分；参考S3 J/K/L模块',
        df['segment'] == '天领业务')

    r = write_s9_weekly_ka_block(ws9, r,
        'I. 成事家办周度明细 | Cheng Shi Weekly Detail',
        '📌 segment=成事家办；按key_account拆分；参考S3 J/K/L模块',
        df['segment'] == '成事家办')

    r = write_s9_weekly_ka_block(ws9, r,
        'J. KA业务周度明细（ICLUB+合伙转介+IFA） | KA Business Weekly Detail',
        '📌 segment IN(ICLUB业务,合伙转介业务,IFA业务)；按key_account拆分；参考S3 J/K/L模块',
        df['segment'].isin(KA_SEGS))

    print("Sheet9 done, row:", r)

    # ============================================================
    # SAVE
    # ============================================================
    # output handled by main()
    # wb.save handled by main()
    return wb

# ═══════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════
# CSV导出函数：S1-S4各生成一份CSV，多个表格用空行+标题行分隔
# ═══════════════════════════════════════════════════════════════════════

def write_csv_section(rows, section_title, field_list='', note=''):
    # 计算最大列数（以数据行为准）
    max_cols = max((len(r) for r in rows), default=1)

    result = []

    # 行1: 标题行 — 第1列标题，其余空白，对应Excel合并单元格深蓝标题
    result.append([section_title] + [''] * (max_cols - 1))

    # 行2: 📌口径说明行 — 第1列，其余空白，对应Excel灰色斜体行
    # 注意：口径说明中的英文逗号替换为中文逗号，防止csv模块加引号包裹后data_loader跳过失败
    if note:
        safe_note = note.replace(',', '，')
        result.append(['📌 ' + safe_note] + [''] * (max_cols - 1))

    # 行3+: 表头+数据+合计行，各列已与Excel完全对应
    for row in rows:
        result.append(row)

    # 空行分隔
    result.append([])
    return result

def df_to_rows(df_in):
    """DataFrame转为list of lists（含表头）"""
    rows = [list(df_in.columns)]
    for _, row in df_in.iterrows():
        rows.append([v if v is not None else '' for v in row.tolist()])
    return rows


# ── helper: format number for CSV (integer display, no .0) ──────────────
def _n(v):
    """Format number: round to nearest integer for display (APE/premium are always integers)"""
    if v is None or (isinstance(v, float) and (v != v)):  # NaN
        return ''
    try:
        f = float(v)
        if f == 0: return 0
        # Round to nearest integer for monetary values
        return int(round(f, 0))
    except (TypeError, ValueError):
        return v

def _pct(v):
    """Format as percentage string"""
    try: return f"{float(v):.1%}"
    except: return str(v) if v else ''


def build_csv_s1(df, months_26, issue_months):
    """S1 总览仪表盘 — 格式与Excel完全对齐"""
    all_rows = []
    m26=(df['status']=='生效')&(df['issue_year']==2026)
    m25=(df['status']=='生效')&(df['issue_year']==2025)
    mpd=df['status'].isin(['尚欠保费','已签单','pending','待批核'])
    mwt=df['status']=='排期'
    mlost=df['status'].isin(['失效','退保','取消投保','搁置受保','取消预约'])&(df['sign_year']==2026)

    # ── A. 目标达成率 ────────────────────────────────────────
    ape_all=df[m26]['ape'].sum(); ape_ym=df[m26&(df['carrier']=='香港永明金融有限公司')]['ape'].sum()
    rows=[['指标','目标APE','已达成APE','目标达成率','完成进度'],
          ['2026全业务目标',1_113_000_000,_n(ape_all),_pct(ape_all/1_113_000_000),_pct(ape_all/1_113_000_000)],
          ['2026永明业务目标',976_100_000,_n(ape_ym),_pct(ape_ym/976_100_000),_pct(ape_ym/976_100_000)]]
    all_rows += write_csv_section(rows,'A. 目标达成率 | Target Achievement Rate',
        '指标  /  目标APE  /  已达成APE  /  目标达成率  /  完成进度',
        '按目标类型统计2026年批核APE（issue_year=2026），计算达成率')

    # ── B. 顶部KPI汇总 ────────────────────────────────────────
    rows=[['指标行','件数','APE','年总保费(HKD)','件均APE','融资占比']]
    for lbl,mask in [('批核(2025)',m25),('批核(2026)',m26),('未批核(跨年)',mpd),('待签(跨年)',mwt),('流失(2026)',mlost)]:
        sub=df[mask]; cnt=len(sub); ape_v=sub['ape'].sum(); prem=sub['premium_hkd'].sum()
        pf=safe_div(sub[sub['is_pf']==1]['ape'].sum(),ape_v) if ape_v>0 else 0
        rows.append([lbl,cnt,_n(ape_v),_n(prem),_n(safe_div(ape_v,cnt)),_pct(pf)])
    all_rows += write_csv_section(rows,'B. 顶部KPI汇总 | Top KPI Summary',
        '指标行  /  件数  /  APE  /  年总保费(HKD)  /  件均APE  /  融资占比',
        '批核(2025/2026):status=生效+issue_year；未批核:IN(尚欠/已签/pending/待批核)；待签:排期；流失(2026):流失+sign_year=2026')

    # ── C/D/E 月度走势 ────────────────────────────────────────
    for sec,time_col,status_filter,ym_label,note in [
        ('C. 月度业绩走势—按预约时间 | Monthly by Reservation Date',
         'res_ym',~df['status'].isin(['取消预约']),'预约年月',
         'res_ym；排除取消预约，保留所有其他状态；2025-01至最新月'),
        ('D. 月度业绩走势—按签单时间 | Monthly by Signing Date',
         'sign_ym',~df['status'].isin(['排期','取消预约']),'签单年月',
         'sign_ym；排除排期、取消预约，保留所有其他状态；2025-01至最新月'),
        ('E. 月度业绩走势—按批核时间 | Monthly by Issue Date',
         'issue_ym',df['status']=='生效','批核年月',
         'issue_ym；status=生效；2025-01至最新月'),
    ]:
        sub_t=df[status_filter]
        ym_data=sorted([m for m in sub_t[time_col].dropna().unique() if str(m)>='2025-01'])
        rows=[[ym_label,'件数','APE','年总保费(HKD)','件均APE','环比增长%','同比增长%']]
        prev={}
        for ym in ym_data:
            s2=sub_t[sub_t[time_col]==ym]; ape_v=s2['ape'].sum(); cnt=len(s2); prem=s2['premium_hkd'].sum()
            mom=_pct((ape_v-prev.get('last',0))/prev.get('last',1)) if prev.get('last') else ''
            yoy_k=str(ym).replace('2026','2025')
            yoy=_pct((ape_v-prev.get(yoy_k,0))/prev.get(yoy_k,1)) if prev.get(yoy_k) else ''
            prev['last']=ape_v; prev[str(ym)]=ape_v
            rows.append([str(ym),cnt,_n(ape_v),_n(prem),_n(safe_div(ape_v,cnt)),mom,yoy])
        fld=ym_label+'  /  件数  /  APE  /  年总保费(HKD)  /  件均APE  /  环比增长%  /  同比增长%'
        all_rows += write_csv_section(rows,sec,fld,note)

    # ── F. 保单状态分布 ────────────────────────────────────────
    f_rows=[('A.批核(2026)','status=生效+issue_year=2026',m26),
            ('B.排期','status=排期',mwt),('C.已签单','status=已签单',df['status']=='已签单'),
            ('D.待批核','status=待批核',df['status']=='待批核'),('E.pending','status=pending',df['status']=='pending'),
            ('F.尚欠保费','status=尚欠保费',df['status']=='尚欠保费'),
            ('G.失效','失效+sign_year=2026',(df['status']=='失效')&(df['sign_year']==2026)),
            ('H.退保','退保+sign_year=2026',(df['status']=='退保')&(df['sign_year']==2026)),
            ('I.取消投保','取消投保+sign_year=2026',(df['status']=='取消投保')&(df['sign_year']==2026)),
            ('J.搁置受保','搁置受保+sign_year=2026',(df['status']=='搁置受保')&(df['sign_year']==2026))]
    tot_c=sum(df[m].shape[0] for _,_,m in f_rows)
    tot_a=sum(df[m]['ape'].sum() for _,_,m in f_rows)
    tot_p=sum(df[m]['premium_hkd'].sum() for _,_,m in f_rows)
    rows=[['保单状态','统计说明','件数','APE','年总保费(HKD)','件数占比','APE占比','年总保费占比']]
    for st,desc,mask in f_rows:
        sub=df[mask]; cnt=len(sub); ape_v=sub['ape'].sum(); prem=sub['premium_hkd'].sum()
        rows.append([st,desc,cnt,_n(ape_v),_n(prem),_pct(safe_div(cnt,tot_c)),_pct(safe_div(ape_v,tot_a)),_pct(safe_div(prem,tot_p))])
    rows.append(['合计','',tot_c,_n(tot_a),_n(tot_p),'100.0%','100.0%','100.0%'])
    all_rows += write_csv_section(rows,'F. 保单状态分布-2026 | Policy Status Distribution',
        '保单状态  /  统计说明  /  件数  /  APE  /  年总保费(HKD)  /  件数占比  /  APE占比  /  年总保费占比',
        '10个保单状态；批核(2026)=生效+issue_year=2026；流失按sign_year=2026')

    # ── G. 业务类型维度 ────────────────────────────────────────
    rows=[['业务类型','2026批核APE','批核件数','未批核APE','未批核件数','待签APE','待签件数','合计APE','合计件数']]
    gs={'a26':0,'c26':0,'ap':0,'cp':0,'aw':0,'cw':0}
    for bt in ['代理人业务','经代业务','KA业务']:
        bm=df['biz_cat']==bt
        a26=df[m26&bm]['ape'].sum(); c26=df[m26&bm].shape[0]
        ap=df[mpd&bm]['ape'].sum(); cp=df[mpd&bm].shape[0]
        aw=df[mwt&bm]['ape'].sum(); cw=df[mwt&bm].shape[0]
        for k,v in zip(['a26','c26','ap','cp','aw','cw'],[a26,c26,ap,cp,aw,cw]): gs[k]+=v
        rows.append([bt,_n(a26),c26,_n(ap),cp,_n(aw),cw,_n(a26+ap+aw),c26+cp+cw])
    rows.append(['合计',_n(gs['a26']),gs['c26'],_n(gs['ap']),gs['cp'],_n(gs['aw']),gs['cw'],
        _n(gs['a26']+gs['ap']+gs['aw']),gs['c26']+gs['cp']+gs['cw']])
    all_rows += write_csv_section(rows,'G. 业务类型维度-2026 | Business Type Dimension',
        '业务类型  /  2026批核APE  /  批核件数  /  未批核APE  /  未批核件数  /  待签APE  /  待签件数  /  合计APE  /  合计件数',
        'business_category；2026批核=生效+issue_year=2026；未批核/待签跨年')

    # ── H. 永明汇报 ────────────────────────────────────────────
    YM_CARRIER='香港永明金融有限公司'
    # EG口径：key_account='EGA' + carrier=香港永明金融有限公司
    _eg_mask = lambda d: d['ka']=='EGA'
    SUNLIFE_ROWS=[('JF',lambda d:d['issuing_entity']=='九富保险服务有限公司'),
        ('UNIWIN',lambda d:d['issuing_entity']=='众和恒富理财集团有限公司'),
        ('DW-Non-Bank',lambda d:(d['issuing_entity']=='怡泰财富管理有限公司')&(d['segment']!='BK业务')),
        ('EG', _eg_mask),
        ('DW Bank',lambda d:(d['issuing_entity']=='怡泰财富管理有限公司')&(d['segment']=='BK业务'))]
    # Sub Total entities: JF + UNIWIN + DW-Non-Bank + EG
    _st_masks = [
        lambda d: d['issuing_entity']=='九富保险服务有限公司',
        lambda d: d['issuing_entity']=='众和恒富理财集团有限公司',
        lambda d: (d['issuing_entity']=='怡泰财富管理有限公司')&(d['segment']!='BK业务'),
        _eg_mask,
    ]
    latest_month=issue_months[-1] if issue_months else None
    fld_h='牌照  /  '+'  /  '.join(issue_months)+'  /  未批核  /  本月已递交'
    rows=[['牌照']+issue_months+['未批核','本月已递交']]
    subtotal_vals = None
    for label,mask_fn in SUNLIFE_ROWS:
        lm=mask_fn(df); row=[label]
        for ym in issue_months:
            row.append(_n(df[(df['status']=='生效')&(df['issue_ym']==ym)&lm&(df['carrier']==YM_CARRIER)]['ape'].sum()))
        pend_v=df[mpd&lm&(df['carrier']==YM_CARRIER)]['ape'].sum()
        sub_m=df[(df['submit_ym']==latest_month)&lm&(df['carrier']==YM_CARRIER)]['ape'].sum() if latest_month else 0
        row+=[_n(pend_v),_n(sub_m)]
        rows.append(row)
        if label=='EG':
            # Insert Sub Total after EG: JF+UNIWIN+DW-Non-Bank+EG
            st_row=['Sub Total']
            for ym in issue_months:
                v=sum(df[(df['status']=='生效')&(df['issue_ym']==ym)&stm(df)&(df['carrier']==YM_CARRIER)]['ape'].sum() for stm in _st_masks)
                st_row.append(_n(v))
            pst=sum(df[mpd&stm(df)&(df['carrier']==YM_CARRIER)]['ape'].sum() for stm in _st_masks)
            sub_st=sum(df[(df['submit_ym']==latest_month)&stm(df)&(df['carrier']==YM_CARRIER)]['ape'].sum() for stm in _st_masks) if latest_month else 0
            st_row+=[_n(pst),_n(sub_st)]
            rows.append(st_row)
    all_rows += write_csv_section(rows,'H. 永明业绩汇报数据-2026 | Sunlife Performance Report',
        fld_h,
        '批核=status=生效+issue_ym；未批核=IN(尚欠/已签/pending/待批核)；已递交=submit_ym=当月；carrier=香港永明金融有限公司；EG=key_account=EGA')

    return all_rows


def build_csv_s2(df, months_26):
    """S2 业务端视角 — 用pivot预聚合，完全对齐Excel单元格"""
    all_rows = []
    m26=(df['status']=='生效')&(df['issue_year']==2026)
    mpd=df['status'].isin(['尚欠保费','已签单','pending','待批核'])
    mwt=df['status']=='排期'
    SEGS=['天领业务','成事家办','BK业务','同行经代','永明经代','合伙转介业务','ICLUB业务','IFA业务']
    TALL={'天领业务':193_000_000,'成事家办':70_000_000,'BK业务':200_000_000,'同行经代':160_000_000,
        '永明经代':340_000_000,'合伙转介业务':73_000_000,'ICLUB业务':52_000_000,'IFA业务':25_000_000}
    TYM={'天领业务':135_100_000,'成事家办':56_000_000,'BK业务':200_000_000,'同行经代':140_000_000,
        '永明经代':340_000_000,'合伙转介业务':51_100_000,'ICLUB业务':36_400_000,'IFA业务':17_500_000}
    YM='香港永明金融有限公司'
    mask_c=~df['status'].isin(['失效','退保','取消投保','搁置受保','取消预约'])
    mask_d=~df['status'].isin(['排期','失效','退保','取消投保','搁置受保','取消预约'])
    mask_e=df['status']=='生效'
    FLD_SEG='业务细分  /  目标APE  /  达成率  /  2026批核APE  /  批核件数  /  未批核APE  /  未批核件数  /  待签APE  /  待签件数  /  合计APE  /  合计件数'

    def pivot_seg_ym(mask, time_col, cf=None):
        """预聚合：segment × time_col → ape/cnt pivot"""
        sub = df[mask].copy()
        if cf: sub = sub[sub['carrier']==cf]
        if sub.empty or time_col not in sub.columns:
            return pd.DataFrame(), pd.DataFrame()
        pa = sub.pivot_table(index='segment', columns=time_col, values='ape', aggfunc='sum', fill_value=0)
        pc = sub.pivot_table(index='segment', columns=time_col, values='ape', aggfunc='count', fill_value=0)
        return pa, pc

    def pivot_ka_ym(mask, time_col, seg_filter=None, cf=None):
        """预聚合：ka × time_col → ape/cnt pivot"""
        sub = df[mask].copy()
        if cf: sub = sub[sub['carrier']==cf]
        if seg_filter is not None: sub = sub[seg_filter.loc[sub.index]]
        if sub.empty or time_col not in sub.columns:
            return pd.DataFrame(), pd.DataFrame()
        pa = sub.pivot_table(index='ka', columns=time_col, values='ape', aggfunc='sum', fill_value=0)
        pc = sub.pivot_table(index='ka', columns=time_col, values='ape', aggfunc='count', fill_value=0)
        return pa, pc

    def seg_annual(title, targets, note, cf=None):
        cfm=(df['carrier']==cf) if cf else pd.Series([True]*len(df),index=df.index)
        rows=[['业务细分','目标APE','达成率','2026批核APE','批核件数','未批核APE','未批核件数','待签APE','待签件数','合计APE','合计件数']]
        gs={'a26':0,'c26':0,'tgt':0,'ap':0,'cp':0,'aw':0,'cw':0}
        for seg in SEGS:
            sm=df['segment']==seg
            a26=df[m26&sm&cfm]['ape'].sum(); c26=int(df[m26&sm&cfm].shape[0])
            ap=df[mpd&sm&cfm]['ape'].sum(); cp=int(df[mpd&sm&cfm].shape[0])
            aw=df[mwt&sm&cfm]['ape'].sum(); cw=int(df[mwt&sm&cfm].shape[0])
            tgt=targets.get(seg,0)
            for k,v in zip(['a26','c26','tgt','ap','cp','aw','cw'],[a26,c26,tgt,ap,cp,aw,cw]): gs[k]+=v
            rows.append([seg,tgt,_pct(safe_div(a26,tgt)) if tgt>0 else '',
                _n(a26),c26,_n(ap),cp,_n(aw),cw,_n(a26+ap+aw),c26+cp+cw])
        tot_a26=df[m26&cfm]['ape'].sum()
        rows.append(['合计',gs['tgt'],_pct(safe_div(tot_a26,gs['tgt'])),
            _n(gs['a26']),gs['c26'],_n(gs['ap']),gs['cp'],_n(gs['aw']),gs['cw'],
            _n(gs['a26']+gs['ap']+gs['aw']),gs['c26']+gs['cp']+gs['cw']])
        return write_csv_section(rows,title,FLD_SEG,note)

    all_rows += seg_annual('A. 业务细分年度汇总—全业务',TALL,'segment_code(8个); 2026批核=生效+issue_year=2026; 合计行达成率=合计批核APE÷合计目标APE')
    all_rows += seg_annual('B. 业务细分年度汇总—永明',TYM,'同A区 + carrier=香港永明金融有限公司',cf=YM)

    # C-H 月度子表 — 用pivot预聚合
    fld_m='业务细分  /  '+'  /  '.join(months_26)+'  /  合计'
    for code,ta,tc_l,tc_note,time_col,s_mask,cf in [
        ('C','C-APE. 月度预约业绩—全业务 (APE)','C-件数. 月度预约业绩—全业务 (件数)','res_ym；排除流失类','res_ym',mask_c,None),
        ('D','D-APE. 月度签单业绩—全业务 (APE)','D-件数. 月度签单业绩—全业务 (件数)','sign_ym；排除排期及流失','sign_ym',mask_d,None),
        ('E','E-APE. 月度批核业绩—全业务 (APE)','E-件数. 月度批核业绩—全业务 (件数)','issue_ym；仅生效','issue_ym',mask_e,None),
        ('F','F-APE. 月度预约业绩—永明 (APE)','F-件数. 月度预约业绩—永明 (件数)','res_ym；排除流失类 + carrier=香港永明金融有限公司','res_ym',mask_c,YM),
        ('G','G-APE. 月度签单业绩—永明 (APE)','G-件数. 月度签单业绩—永明 (件数)','sign_ym；排除排期及流失 + carrier=香港永明金融有限公司','sign_ym',mask_d,YM),
        ('H','H-APE. 月度批核业绩—永明 (APE)','H-件数. 月度批核业绩—永明 (件数)','issue_ym；仅生效 + carrier=香港永明金融有限公司','issue_ym',mask_e,YM),
    ]:
        sub = df[s_mask].copy()
        if cf: sub = sub[sub['carrier']==cf]
        # pivot: segment × month
        if not sub.empty and time_col in sub.columns:
            pa = sub.pivot_table(index='segment', columns=time_col, values='ape', aggfunc='sum', fill_value=0)
            pc = sub.pivot_table(index='segment', columns=time_col, values='policy_id', aggfunc='count', fill_value=0)
        else:
            pa = pd.DataFrame(); pc = pd.DataFrame()

        for vtype,title in [('ape',ta),('cnt',tc_l)]:
            rows=[['业务细分']+months_26+['合计']]
            tots=[0]*len(months_26)
            for seg in SEGS:
                row=[seg]
                rtot=0
                for k,ym in enumerate(months_26):
                    pt = pa if vtype=='ape' else pc
                    v = int(pt.loc[seg, ym]) if (not pt.empty and seg in pt.index and ym in pt.columns) else 0
                    row.append(_n(v) if vtype=='ape' else v)
                    rtot+=v; tots[k]+=v
                row.append(_n(rtot) if vtype=='ape' else rtot)
                rows.append(row)
            rows.append(['合计']+[_n(t) if vtype=='ape' else t for t in tots]+[_n(sum(tots)) if vtype=='ape' else sum(tots)])
            all_rows += write_csv_section(rows,title,fld_m,tc_note)

    # I. KA TOP20
    ka_seg_eff=(df[m26].groupby(['ka','segment'])['ape'].sum()
                .reset_index().sort_values('ape',ascending=False).head(20))
    rows=[['排名','KEY ACCOUNT','业务细分','2026批核APE','批核件数','未批核APE','未批核件数','待签APE','待签件数','合计APE','合计件数']]
    tot_i=[0]*8
    for i,row_ks in enumerate(ka_seg_eff.itertuples()):
        ka=row_ks.ka; seg=row_ks.segment; ape_v=row_ks.ape
        km=(df['ka']==ka)&(df['segment']==seg)
        cnt=int(df[m26&km].shape[0]); ap=df[mpd&km]['ape'].sum(); cp=int(df[mpd&km].shape[0])
        aw=df[mwt&km]['ape'].sum(); cw=int(df[mwt&km].shape[0])
        for ii,v in enumerate([ape_v,cnt,ap,cp,aw,cw,ape_v+ap+aw,cnt+cp+cw]): tot_i[ii]+=v
        rows.append([i+1,ka,seg,_n(ape_v),cnt,_n(ap),cp,_n(aw),cw,_n(ape_v+ap+aw),cnt+cp+cw])
    rows.append(['合计','','',_n(tot_i[0]),int(tot_i[1]),_n(tot_i[2]),int(tot_i[3]),_n(tot_i[4]),int(tot_i[5]),_n(tot_i[6]),int(tot_i[7])])
    all_rows += write_csv_section(rows,'I. KEY ACCOUNT 排名 TOP20 | KA Ranking',
        '排名  /  KEY ACCOUNT  /  业务细分  /  2026批核APE  /  批核件数  /  未批核APE  /  未批核件数  /  待签APE  /  待签件数  /  合计APE  /  合计件数',
        '2026批核APE降序TOP20；含未批核/待签/合计列；含合计行')

    # J. 推荐人
    refs=['战略合作','Mark','姜通','高瑶','白博文','魏子璐']
    rows=[['推荐人','2026批核APE','批核件数','未批核APE','未批核件数','待签APE','待签件数','总APE','总件数']]
    ref_data=[]
    for ref in refs:
        rm=df['referral']==ref
        a26=df[m26&rm]['ape'].sum(); c26=int(df[m26&rm].shape[0])
        ap=df[mpd&rm]['ape'].sum(); cp=int(df[mpd&rm].shape[0])
        aw=df[mwt&rm]['ape'].sum(); cw=int(df[mwt&rm].shape[0])
        ref_data.append([ref,_n(a26),c26,_n(ap),cp,_n(aw),cw,_n(a26+ap+aw),c26+cp+cw])
    ref_data.sort(key=lambda x: -x[1] if isinstance(x[1],int) else 0)
    rows += ref_data
    rows.append(['合计']+[sum(x[k] for x in ref_data if isinstance(x[k],(int,float))) for k in range(1,9)])
    all_rows += write_csv_section(rows,'J. 同行推荐人分析 | Peer Referral Analysis',
        '推荐人  /  2026批核APE  /  批核件数  /  未批核APE  /  未批核件数  /  待签APE  /  待签件数  /  总APE  /  总件数',
        '6人：战略合作/Mark/姜通/高瑶/白博文/魏子璐；按2026批核APE降序')

    # K/O KA汇总 + L-N/P-R月度 + S/T分行
    fld_m2='KEY ACCOUNT  /  '+'  /  '.join(months_26)+'  /  合计'
    for grp_name,seg_f,k_title,k_note,codes in [
        ('同行',df['segment'].isin(['永明经代','同行经代']),'K. 同行业绩分析 | Peer Channel Analysis',
         'segment IN(永明经代,同行经代)；按2026批核APE降序',
         [('L','预约','res_ym',mask_c),('M','签单','sign_ym',mask_d),('N','批核','issue_ym',mask_e)]),
        ('银行',df['segment']=='BK业务','O. 银行业绩分析 | Bank Channel Analysis',
         'segment=BK业务；按2026批核APE降序',
         [('P','预约','res_ym',mask_c),('Q','签单','sign_ym',mask_d),('R','批核','issue_ym',mask_e)]),
    ]:
        # KA汇总 — 与xlsx完全对齐：先取有2026批核APE的KA，再追加只有未批核/待签的KA
        ka_ord_base = df[m26&seg_f].groupby('ka')['ape'].sum().sort_values(ascending=False).index.tolist()
        ka_ord_extra = [k for k in df[(mpd|mwt)&seg_f]['ka'].dropna().unique() if k not in ka_ord_base]
        ka_ord = ka_ord_base + ka_ord_extra
        fld_ka='KEY ACCOUNT  /  2026批核APE  /  批核件数  /  未批核APE  /  未批核件数  /  待签APE  /  待签件数  /  总APE  /  总件数'
        rows=[['KEY ACCOUNT','2026批核APE','批核件数','未批核APE','未批核件数','待签APE','待签件数','总APE','总件数']]
        tots=[0]*8
        for ka in ka_ord:
            km=df['ka']==ka
            a26=df[m26&km]['ape'].sum(); c26=int(df[m26&km].shape[0])
            ap=df[mpd&km]['ape'].sum(); cp=int(df[mpd&km].shape[0])
            aw=df[mwt&km]['ape'].sum(); cw=int(df[mwt&km].shape[0])
            for ii,v in enumerate([a26,c26,ap,cp,aw,cw,a26+ap+aw,c26+cp+cw]): tots[ii]+=v
            rows.append([ka,_n(a26),c26,_n(ap),cp,_n(aw),cw,_n(a26+ap+aw),c26+cp+cw])
        rows.append(['合计',_n(tots[0]),int(tots[1]),_n(tots[2]),int(tots[3]),_n(tots[4]),int(tots[5]),_n(tots[6]),int(tots[7])])
        all_rows += write_csv_section(rows,k_title,fld_ka,k_note)

        # 月度子表 — 用pivot预聚合
        for code,cn,tc,sm in codes:
            sub_g = df[sm & seg_f].copy()
            if not sub_g.empty and tc in sub_g.columns:
                pa_g = sub_g.pivot_table(index='ka', columns=tc, values='ape', aggfunc='sum', fill_value=0)
                pc_g = sub_g.pivot_table(index='ka', columns=tc, values='policy_id', aggfunc='count', fill_value=0)
                ka_tot_ape = pa_g[pa_g.columns.intersection(months_26)].sum(axis=1)
                active = ka_tot_ape[ka_tot_ape > 0].sort_values(ascending=False).index.tolist()
            else:
                pa_g = pd.DataFrame(); pc_g = pd.DataFrame(); active = []

            for vtype,title,mn in [
                ('ape',f'{code}-APE. 月度{cn}业绩—{grp_name} (APE)',f'{tc}；{"仅生效" if cn=="批核" else "排除排期及流失" if cn=="签单" else "排除流失类"}；⭐ 按该表自身合计APE降序'),
                ('cnt',f'{code}-件数. 月度{cn}业绩—{grp_name} (件数)',f'同{code}-APE；行顺序跟随APE子表'),
            ]:
                pt = pa_g if vtype=='ape' else pc_g
                rows=[['KEY ACCOUNT']+months_26+['合计']]
                tots=[0]*len(months_26)
                for ka in active:
                    row=[ka]; rtot=0
                    for k,ym in enumerate(months_26):
                        v = int(pt.loc[ka, ym]) if (not pt.empty and ka in pt.index and ym in pt.columns) else 0
                        row.append(_n(v) if vtype=='ape' else v); rtot+=v; tots[k]+=v
                    row.append(_n(rtot) if vtype=='ape' else rtot)
                    rows.append(row)
                rows.append(['合计']+[_n(t) if vtype=='ape' else t for t in tots]+[_n(sum(tots)) if vtype=='ape' else sum(tots)])
                all_rows += write_csv_section(rows,title,fld_m2,mn)

    # S/T 分行 — 与xlsx完全对齐：稳定排序，包含所有BK分行（不限状态）
    bk_seg=df['segment']=='BK业务'
    fld_st='合作伙伴(分行)  /  '+'  /  '.join(months_26)+'  /  合计'
    mask_bk_all_st = (df['status'].isin(['生效','尚欠保费','已签单','pending','待批核','排期','失效','退保','取消投保','搁置受保','取消预约'])) & bk_seg
    sub_st=df[mask_e&bk_seg].copy()
    if not sub_st.empty and 'issue_ym' in sub_st.columns:
        pa_st = sub_st.pivot_table(index='partner', columns='issue_ym', values='ape', aggfunc='sum', fill_value=0)
        pc_st = sub_st.pivot_table(index='partner', columns='issue_ym', values='policy_id', aggfunc='count', fill_value=0)
        # Stable sort: APE降序 then partner name
        pt_tot_s = pa_st[pa_st.columns.intersection(months_26)].sum(axis=1)
        pt_tot_df = pt_tot_s.reset_index()
        pt_tot_df.columns = ['partner', 'ape_tot']
        pt_tot_df = pt_tot_df.sort_values(['ape_tot','partner'], ascending=[False,True])
        partners_with_ape = pt_tot_df['partner'].tolist()
        # 追加所有BK分行（不限状态，与xlsx对齐）
        all_bk_partners = df[bk_seg & df['partner'].notna()]['partner'].unique().tolist()
        partners_extra = [p for p in all_bk_partners if p not in partners_with_ape]
        partners = partners_with_ape + partners_extra
    else:
        pa_st=pd.DataFrame(); pc_st=pd.DataFrame(); partners=[]

    for vtype,title,note in [
        ('ape','S-APE. 批核业绩—银行各分行 (APE)','issue_ym；仅生效；行=partner；⭐ 按该表自身合计APE降序'),
        ('cnt','T-件数. 批核业绩—银行各分行 (件数)','同S-APE；行顺序跟随S-APE'),
    ]:
        pt = pa_st if vtype=='ape' else pc_st
        rows=[['合作伙伴(分行)']+months_26+['合计']]
        tots=[0]*len(months_26)
        for ptn in partners:
            row=[ptn]; rtot=0
            for k,ym in enumerate(months_26):
                v = int(pt.loc[ptn, ym]) if (not pt.empty and ptn in pt.index and ym in pt.columns) else 0
                row.append(_n(v) if vtype=='ape' else v); rtot+=v; tots[k]+=v
            row.append(_n(rtot) if vtype=='ape' else rtot)
            rows.append(row)
        rows.append(['合计']+[_n(t) if vtype=='ape' else t for t in tots]+[_n(sum(tots)) if vtype=='ape' else sum(tots)])
        all_rows += write_csv_section(rows,title,fld_st,note)

    return all_rows


def build_csv_s3(df, weeks_26, pending_months):
    """S3 执行管理端 — 用pivot预聚合，完全对齐Excel单元格"""
    all_rows = []
    m26=(df['status']=='生效')&(df['issue_year']==2026)
    mpd=df['status'].isin(['尚欠保费','已签单','pending','待批核'])
    mwt=df['status']=='排期'
    mask_c=~df['status'].isin(['失效','退保','取消投保','搁置受保','取消预约'])
    mask_d=~df['status'].isin(['排期','失效','退保','取消投保','搁置受保','取消预约'])
    mask_e=df['status']=='生效'
    mask_sub=~df['status'].isin(['失效','退保','取消投保','搁置受保','取消预约'])
    SEGS=['天领业务','成事家办','BK业务','同行经代','永明经代','合伙转介业务','ICLUB业务','IFA业务']

    def pivot_by(mask, group_col, time_col, time_vals):
        sub = df[mask].copy()
        if sub.empty or time_col not in sub.columns or group_col not in sub.columns:
            return pd.DataFrame(), pd.DataFrame()
        pa = sub.pivot_table(index=group_col, columns=time_col, values='ape', aggfunc='sum', fill_value=0)
        pc = sub.pivot_table(index=group_col, columns=time_col, values='policy_id', aggfunc='count', fill_value=0)
        return pa, pc

    def make_rows_from_pivot(pa, pc, rows_idx, time_vals, vtype):
        rows = [[('阶段' if rows_idx == 'stage' else '业务细分' if rows_idx == 'segment' else 'KEY ACCOUNT')] + time_vals + ['合计']]
        tots = [0]*len(time_vals)
        pt = pa if vtype=='ape' else pc
        for idx in rows_idx if isinstance(rows_idx, list) else []:
            row = [idx]; rtot = 0
            for k, tv in enumerate(time_vals):
                v = int(pt.loc[idx, tv]) if (not pt.empty and idx in pt.index and tv in pt.columns) else 0
                row.append(_n(v) if vtype=='ape' else v); rtot+=v; tots[k]+=v
            row.append(_n(rtot) if vtype=='ape' else rtot)
            rows.append(row)
        rows.append(['合计']+[_n(t) if vtype=='ape' else t for t in tots]+[_n(sum(tots)) if vtype=='ape' else sum(tots)])
        return rows

    # A 漏斗 — 预聚合4条阶段线
    fld_a='阶段  /  '+'  /  '.join(weeks_26)+'  /  合计'
    funnel_defs=[('预约','res_yw',mask_c),('签单','sign_yw',mask_d),('递交','submit_yw',mask_sub),('批核','issue_yw',mask_e)]
    # pre-aggregate each funnel line
    funnel_pivots = {}
    for lbl,tc,fm in funnel_defs:
        sub=df[fm].copy()
        if not sub.empty and tc in sub.columns:
            funnel_pivots[lbl] = (
                sub.pivot_table(columns=tc, values='ape', aggfunc='sum', fill_value=0),
                sub.pivot_table(columns=tc, values='policy_id', aggfunc='count', fill_value=0)
            )
        else:
            funnel_pivots[lbl] = (pd.Series(dtype=float), pd.Series(dtype=int))

    for vtype,title,note in [
        ('ape','A-APE. 阶段周追踪漏斗 (APE)','预约=res_yw；签单=sign_yw；递交=submit_yw；批核=issue_yw(仅生效)；2026W01至最新周'),
        ('cnt','A-件数. 阶段周追踪漏斗 (件数)','同A-APE；值为件数'),
    ]:
        rows=[['阶段']+weeks_26+['合计']]
        for lbl,tc,fm in funnel_defs:
            pa_f, pc_f = funnel_pivots[lbl]
            pt = pa_f if vtype=='ape' else pc_f
            row=[lbl]; rtot=0
            for wk in weeks_26:
                # pt is a 1-row DataFrame or empty; use iloc[0] to get scalar
                if not pt.empty and wk in pt.columns:
                    v = int(pt[wk].iloc[0])
                else:
                    v = 0
                row.append(_n(v) if vtype=='ape' else v); rtot+=v
            row.append(_n(rtot) if vtype=='ape' else rtot)
            rows.append(row)
        all_rows += write_csv_section(rows,title,fld_a,note)

    # B/C/D 周度业绩 — 预聚合segment×week
    fld_w='业务细分  /  '+'  /  '.join(weeks_26)+'  /  合计'
    for ta,tc_l,note,tc,sm in [
        ('B-APE. 周度预约业绩 (APE)','B-件数. 周度预约业绩 (件数)','res_yw；status NOT IN(失效/退保/取消投保/搁置受保/取消预约)','res_yw',mask_c),
        ('C-APE. 周度签单业绩 (APE)','C-件数. 周度签单业绩 (件数)','sign_yw；status NOT IN(排期/失效/退保/取消投保/搁置受保/取消预约)','sign_yw',mask_d),
        ('D-APE. 周度批核业绩 (APE)','D-件数. 周度批核业绩 (件数)','issue_yw；仅status=生效','issue_yw',mask_e),
    ]:
        pa_w, pc_w = pivot_by(sm, 'segment', tc, weeks_26)
        for vtype,title in [('ape',ta),('cnt',tc_l)]:
            rows=[['业务细分']+weeks_26+['合计']]
            tots=[0]*len(weeks_26)
            pt = pa_w if vtype=='ape' else pc_w
            for seg in SEGS:
                row=[seg]; rtot=0
                for k,wk in enumerate(weeks_26):
                    v = int(pt.loc[seg, wk]) if (not pt.empty and seg in pt.index and wk in pt.columns) else 0
                    row.append(_n(v) if vtype=='ape' else v); rtot+=v; tots[k]+=v
                row.append(_n(rtot) if vtype=='ape' else rtot)
                rows.append(row)
            rows.append(['合计']+[_n(t) if vtype=='ape' else t for t in tots]+[_n(sum(tots)) if vtype=='ape' else sum(tots)])
            all_rows += write_csv_section(rows,title,fld_w,note)

    # E/F 未批核待签分布 — 预聚合ka×sign_ym
    mask_pend=df['status'].isin(['尚欠保费','已签单','pending','待批核','排期'])
    fld_ef='KEY ACCOUNT  /  '+'  /  '.join(pending_months)+'  /  合计'
    for pf_val,pf_name,sec_code in [(0,'常规','E'),(1,'融资','F')]:
        pf_mask=mask_pend&(df['is_pf']==pf_val)
        sub_pf=df[pf_mask].copy()
        if not sub_pf.empty and 'sign_ym' in sub_pf.columns:
            pa_pf=sub_pf.pivot_table(index='ka',columns='sign_ym',values='ape',aggfunc='sum',fill_value=0)
            pc_pf=sub_pf.pivot_table(index='ka',columns='sign_ym',values='policy_id',aggfunc='count',fill_value=0)
            ka_tot_pf=pa_pf[pa_pf.columns.intersection(pending_months)].sum(axis=1)
            # 稳定排序：APE降序，同值时按KA名称字母序，与xlsx保持一致
            active2=ka_tot_pf[ka_tot_pf>0].reset_index().sort_values(
                [0,'ka'], ascending=[False,True]).set_index('ka').index.tolist()
        else:
            pa_pf=pd.DataFrame(); pc_pf=pd.DataFrame(); active2=[]

        for vtype,title,note in [
            ('ape',f'{sec_code}-APE. 未批核与待签分布—{pf_name} (APE) | Pending & Waiting Distribution',
             f'status IN(尚欠/已签/pending/待批核/排期)；is_pf={pf_val}({pf_name})；列=sign_ym(2025-08起)；⭐ 按该表自身合计APE降序'),
            ('cnt',f'{sec_code}-件数. 未批核与待签分布—{pf_name} (件数)',f'同{sec_code}-APE；行顺序跟随APE子表'),
        ]:
            pt = pa_pf if vtype=='ape' else pc_pf
            rows=[['KEY ACCOUNT']+pending_months+['合计']]
            tots=[0]*len(pending_months)
            for ka in active2:
                row=[ka]; rtot=0
                for k,ym in enumerate(pending_months):
                    v = int(pt.loc[ka, ym]) if (not pt.empty and ka in pt.index and ym in pt.columns) else 0
                    row.append(_n(v) if vtype=='ape' else v); rtot+=v; tots[k]+=v
                row.append(_n(rtot) if vtype=='ape' else rtot)
                rows.append(row)
            rows.append(['合计']+[_n(t) if vtype=='ape' else t for t in tots]+[_n(sum(tots)) if vtype=='ape' else sum(tots)])
            all_rows += write_csv_section(rows,title,fld_ef,note)

    # G 时效分析
    tat_sub=df[m26&df['tat'].notna()]
    rows=[['业务细分','件数','件均APE','平均时效(天)','中位时效(天)','P90时效(天)','最大时效(天)','SLA达标率≤60']]
    for seg in SEGS:
        sub=tat_sub[tat_sub['segment']==seg]
        if len(sub)==0:
            rows.append([seg,0,'','','','','',''])
        else:
            rows.append([seg,len(sub),_n(safe_div(sub['ape'].sum(),len(sub))),
                round(sub['tat'].mean(),1),round(sub['tat'].median(),1),
                round(sub['tat'].quantile(0.9),1),int(sub['tat'].max()),
                _pct(safe_div((sub['tat']<=60).sum(),len(sub)))])
    rows.append(['合计',len(tat_sub),_n(safe_div(tat_sub['ape'].sum(),len(tat_sub))),
        round(tat_sub['tat'].mean(),1),round(tat_sub['tat'].median(),1),
        round(tat_sub['tat'].quantile(0.9),1),int(tat_sub['tat'].max()),
        _pct(safe_div((tat_sub['tat']<=60).sum(),len(tat_sub)))])
    all_rows += write_csv_section(rows,'G. 签批时效分析—2026批核 | TAT Analysis',
        '业务细分  /  件数  /  件均APE  /  平均时效(天)  /  中位时效(天)  /  P90时效(天)  /  最大时效(天)  /  SLA达标率≤60',
        'status=生效 AND issue_year=2026；TAT=issue_date-sign_date(天)；SLA达标率=COUNT(tat≤60)/COUNT(*)')

    # H 时效分档
    rows=[['时效分档','件数','APE','件数占比','APE占比']]
    for lbl,lo,hi in [('≤7天',0,7),('8-14天',8,14),('15-30天',15,30),('31-60天',31,60),('61-90天',61,90),('>90天',91,9999)]:
        sub=tat_sub[(tat_sub['tat']>=lo)&(tat_sub['tat']<=hi)]
        rows.append([lbl,len(sub),_n(sub['ape'].sum()),
            _pct(safe_div(len(sub),len(tat_sub))),_pct(safe_div(sub['ape'].sum(),tat_sub['ape'].sum()))])
    rows.append(['合计',len(tat_sub),_n(tat_sub['ape'].sum()),'100.0%','100.0%'])
    all_rows += write_csv_section(rows,'H. 签批时效分档—2026批核 | TAT Buckets',
        '时效分档  /  件数  /  APE  /  件数占比  /  APE占比',
        '分档：≤7天/8-14天/15-30天/31-60天/61-90天/>90天；status=生效 AND issue_year=2026')

    # J-L 同行周度 / M-O 银行周度 — 预聚合ka×week
    fld_kaw='KEY ACCOUNT  /  '+'  /  '.join(weeks_26)+'  /  合计'
    for grp_name,seg_f,codes2 in [
        ('同行',df['segment'].isin(['永明经代','同行经代']),
         [('J','预约','res_yw',mask_c),('K','签单','sign_yw',mask_d),('L','批核','issue_yw',mask_e)]),
        ('银行',df['segment']=='BK业务',
         [('M','预约','res_yw',mask_c),('N','签单','sign_yw',mask_d),('O','批核','issue_yw',mask_e)]),
    ]:
        for code,cn,tc,sm in codes2:
            sub_g=df[sm&seg_f].copy()
            if not sub_g.empty and tc in sub_g.columns:
                pa_g=sub_g.pivot_table(index='ka',columns=tc,values='ape',aggfunc='sum',fill_value=0)
                pc_g=sub_g.pivot_table(index='ka',columns=tc,values='policy_id',aggfunc='count',fill_value=0)
                ka_tot=pa_g[pa_g.columns.intersection(weeks_26)].sum(axis=1)
                active=ka_tot[ka_tot>0].sort_values(ascending=False).index.tolist()
            else:
                pa_g=pd.DataFrame(); pc_g=pd.DataFrame(); active=[]

            for vtype,title,note in [
                ('ape',f'{code}-APE. 周度{cn}业绩—{grp_name} (APE)',f'{tc}；{"仅生效" if cn=="批核" else "排除排期及流失" if cn=="签单" else "排除流失类"}；⭐ 按该表自身合计APE降序'),
                ('cnt',f'{code}-件数. 周度{cn}业绩—{grp_name} (件数)',f'同{code}-APE；行顺序跟随APE子表'),
            ]:
                pt = pa_g if vtype=='ape' else pc_g
                rows=[['KEY ACCOUNT']+weeks_26+['合计']]
                tots=[0]*len(weeks_26)
                for ka in active:
                    row=[ka]; rtot=0
                    for k,wk in enumerate(weeks_26):
                        v = int(pt.loc[ka, wk]) if (not pt.empty and ka in pt.index and wk in pt.columns) else 0
                        row.append(_n(v) if vtype=='ape' else v); rtot+=v; tots[k]+=v
                    row.append(_n(rtot) if vtype=='ape' else rtot)
                    rows.append(row)
                rows.append(['合计']+[_n(t) if vtype=='ape' else t for t in tots]+[_n(sum(tots)) if vtype=='ape' else sum(tots)])
                all_rows += write_csv_section(rows,title,fld_kaw,note)

    return all_rows



def build_csv_s4(df):
    """S4 产品端视角 — 格式与Excel完全对齐"""
    all_rows = []
    CARRIERS_FULL=['香港永明金融有限公司','中国人寿保险（海外）股份有限公司（香港）','万通保险国际有限公司',
        '香港安盛保险有限公司','中国人寿保险（海外）股份有限公司（澳门）','宏利人寿保险（国际）有限公司',
        '友邦保险（国际）有限公司','立桥人寿保险有限公司','中国太平洋保险（香港）有限公司',
        '周大福人寿保险有限公司','保诚保险有限公司','中银人寿保险有限公司','澳门太平',
        '保柏环球有限公司','富卫人寿保险（百慕大）有限公司','忠意保险有限公司','信诺环球保险公司']
    CARRIER_SHORT={'香港永明金融有限公司':'永明','中国人寿保险（海外）股份有限公司（香港）':'中国人寿',
        '万通保险国际有限公司':'万通','香港安盛保险有限公司':'安盛',
        '中国人寿保险（海外）股份有限公司（澳门）':'澳门中国人寿','宏利人寿保险（国际）有限公司':'宏利',
        '友邦保险（国际）有限公司':'友邦','立桥人寿保险有限公司':'立桥',
        '中国太平洋保险（香港）有限公司':'太平洋','周大福人寿保险有限公司':'周大福',
        '保诚保险有限公司':'保诚','中银人寿保险有限公司':'中银人寿','澳门太平':'澳门太平',
        '保柏环球有限公司':'保柏','富卫人寿保险（百慕大）有限公司':'富卫',
        '忠意保险有限公司':'忠意','信诺环球保险公司':'信诺'}
    mask_26_all=(df['sign_year']==2026)&df['status'].isin(['生效','尚欠保费','已签单','pending','待批核','排期'])
    mask_prod=(df['sign_year']==2026)&~df['status'].isin(['失效','退保','取消投保','搁置受保','取消预约'])

    # A 保险公司（全17家+新增，零业务保留）
    data_carriers=df[mask_26_all]['carrier'].dropna().unique().tolist()
    carriers_list=CARRIERS_FULL+[c for c in data_carriers if c not in CARRIERS_FULL]
    carr_data=[(CARRIER_SHORT.get(c,c),df[mask_26_all&(df['carrier']==c)].shape[0],
        df[mask_26_all&(df['carrier']==c)]['ape'].sum(),
        df[mask_26_all&(df['carrier']==c)]['premium_hkd'].sum()) for c in carriers_list]
    carr_data.sort(key=lambda x:-x[2])
    tot_c=sum(x[1] for x in carr_data); tot_a=sum(x[2] for x in carr_data); tot_p=sum(x[3] for x in carr_data)
    rows=[['保险公司','件数','APE','年总保费(HKD)','件数占比','APE件均','年总保费件均','APE占比']]
    for s,cnt,ape,prem in carr_data:
        rows.append([s,cnt,_n(ape),_n(prem),_pct(safe_div(cnt,tot_c)),_n(safe_div(ape,cnt)),_n(safe_div(prem,cnt)),_pct(safe_div(ape,tot_a))])
    rows.append(['合计',tot_c,_n(tot_a),_n(tot_p),'100.0%',_n(safe_div(tot_a,tot_c)),_n(safe_div(tot_p,tot_c)),'100.0%'])
    all_rows += write_csv_section(rows,'A. 保险公司维度 | Carrier Dimension',
        '保险公司  /  件数  /  APE  /  年总保费(HKD)  /  件数占比  /  APE件均  /  年总保费件均  /  APE占比',
        'sign_year=2026；status IN(生效/尚欠/已签/pending/待批核/排期)；全17家保司列出(零业务保留)；按APE降序')

    # B/C 产品TOP20（联合主键=产品名称+年期+首年折扣）
    for sort_col,title,val_col,val_lbl,note in [
        ('premium_hkd','B. 产品TOP20—年总保费 | Product TOP20 by Premium','prem','年总保费(HKD)',
         '⭐ 联合主键=产品名称+年期+首年特殊折扣(SQ_rate)；sign_year=2026；status非流失；按年总保费降序'),
        ('ape','C. 产品TOP20—APE | Product TOP20 by APE','ape','APE',
         '⭐ 联合主键同B区（产品名称+年期+首年特殊折扣）；按APE降序'),
    ]:
        grp=df[mask_prod].groupby(['product','term','discount_special']).agg(
            cnt=('policy_id','count'),prem=('premium_hkd','sum'),ape=('ape','sum'),
            carrier=('carrier',lambda x:x.mode()[0] if len(x)>0 else '')).reset_index()
        sort_by='prem' if sort_col=='premium_hkd' else 'ape'
        grp=grp.sort_values(sort_by,ascending=False).head(20)
        fld_bc=f'排名  /  保司  /  产品名称  /  年期  /  首年折扣  /  件数  /  {val_lbl}  /  {val_lbl}件均'
        rows=[[  '排名','保司','产品名称','年期','首年折扣','件数',val_lbl,f'{val_lbl}件均']]
        for i,row_p in enumerate(grp.itertuples()):
            short=CARRIER_SHORT.get(row_p.carrier,str(row_p.carrier)[:6])
            disc=row_p.discount_special if pd.notna(row_p.discount_special) and str(row_p.discount_special).strip() not in ('','nan') else ''
            v=_n(row_p.prem) if val_col=='prem' else _n(row_p.ape)
            rows.append([i+1,short,row_p.product,row_p.term,disc,row_p.cnt,v,_n(safe_div(float(v) if isinstance(v,int) else 0,row_p.cnt))])
        all_rows += write_csv_section(rows,title,fld_bc,note)

    # D/E 年期分布 / 供款方式（APE>0）
    sub_d_valid=df[mask_prod][df[mask_prod]['ape']>0]
    tot_tc=len(sub_d_valid); tot_ta=sub_d_valid['ape'].sum(); tot_tp=sub_d_valid['premium_hkd'].sum()
    for sec,col,cats,note in [
        ('D. 年期分布 | Term Distribution','term_cat',['短期(≤1年)','中期(2-5年)','长期(6-20年)','终身(>20年)'],
         'sign_year=2026；status非流失；APE>0；4档：短期(≤1年)/中期(2-5年)/长期(6-20年)/终身(>20年)'),
        ('E. 供款方式分布 | Payment Mode Distribution','payment_mode',['预缴','年缴','整付'],
         'sign_year=2026；status非流失；APE>0；供款方式：预缴/年缴/整付'),
    ]:
        fld_de='年期分类' if col=='term_cat' else '供款方式'
        fld_de+='  /  件数  /  APE  /  年总保费(HKD)  /  件数占比  /  APE件均  /  年总保费件均'
        rows=[['年期分类' if col=='term_cat' else '供款方式','件数','APE','年总保费(HKD)','件数占比','APE件均','年总保费件均']]
        for cat in cats:
            sub=sub_d_valid[sub_d_valid[col]==cat]
            cnt=len(sub); ape_v=sub['ape'].sum(); prem_v=sub['premium_hkd'].sum()
            rows.append([cat,cnt,_n(ape_v),_n(prem_v),_pct(safe_div(cnt,tot_tc)),_n(safe_div(ape_v,cnt)),_n(safe_div(prem_v,cnt))])
        rows.append(['合计',tot_tc,_n(tot_ta),_n(tot_tp),'100.0%',_n(safe_div(tot_ta,tot_tc)),_n(safe_div(tot_tp,tot_tc))])
        all_rows += write_csv_section(rows,sec,fld_de,note)

    return all_rows


def export_csvs(df, months_26, weeks_26, issue_months, pending_months, output_prefix=''):
    """生成四份CSV附表(S1-S4)，供pipeline脚本(data_loader)读取。"""
    import csv as _csv
    prefix = output_prefix if output_prefix else ''
    builders = [
        ('S1-总览仪表盘', build_csv_s1(df, months_26, issue_months)),
        ('S2-业务端视角', build_csv_s2(df, months_26)),
        ('S3-执行管理端', build_csv_s3(df, weeks_26, pending_months)),
        ('S4-产品端视角', build_csv_s4(df)),
    ]
    created = []
    for name, all_rows in builders:
        path = f'{prefix}{name}.csv'
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = _csv.writer(f)
            for row in all_rows:
                writer.writerow(['' if v is None else v for v in row])
        created.append(path)
        print(f"  ✓ {name}.csv  ({len(all_rows)} rows)")
    return created



def main():
    parser = argparse.ArgumentParser(description='业绩分析报表生成脚本 V1.0')
    parser.add_argument('csv_file', help='源数据CSV文件路径，如：业绩数据0414.csv')
    parser.add_argument('--weeks', default=None,
                        help='（可选）强制指定最新周次，如 W15 或 2026W15')
    parser.add_argument('--output', default=None,
                        help='（可选）输出文件名，默认：业绩分析报表_MMDD.xlsx')
    args = parser.parse_args()

    if not os.path.exists(args.csv_file):
        print(f"错误：找不到文件 {args.csv_file}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  业绩分析报表生成脚本 V1.0")
    print(f"  源数据：{args.csv_file}")
    print(f"{'='*60}")

    # ── 加载数据 ────────────────────────────────────────
    global df
    df = load_csv(args.csv_file)

    # ── 自动检测时间范围 ──────────────────────────────
    force_week = None
    if args.weeks:
        force_week = f"2026{args.weeks}" if not args.weeks.startswith('2026') else args.weeks

    months_26      = get_months_2026(df)
    weeks_26       = get_weeks_2026(df, force=force_week)
    issue_months   = get_issue_months(df)
    pending_months = get_pending_months(df)
    licenses       = get_licenses(df)

    print(f"\n时间范围自动检测：")
    print(f"  月度列：{months_26[0] if months_26 else '-'} ~ {months_26[-1] if months_26 else '-'}（共{len(months_26)}个月）")
    print(f"  周度列：{weeks_26[0] if weeks_26 else '-'} ~ {weeks_26[-1] if weeks_26 else '-'}（共{len(weeks_26)}周）")
    print(f"  批核月：{issue_months[0] if issue_months else '-'} ~ {issue_months[-1] if issue_months else '-'}")
    print(f"  牌照数：{len(licenses)}个（基础9个{'+新增' if len(licenses)>9 else ''}）")
    print(f"\n开始生成报表（共8张Sheet）：")

    # ── 构建工作簿 ───────────────────────────────────
    wb = build_all_sheets(df, months_26, weeks_26, issue_months, pending_months, licenses)

    # 输出文件
    if args.output:
        out_path = args.output
    else:
        date_str = datetime.date.today().strftime('%m%d')
        out_path = f"业绩分析报表_{date_str}.xlsx"

    wb.save(out_path)

    # ── 生成四份CSV（S1-S4）──────────────────────────────
    csv_dir = os.path.dirname(os.path.abspath(out_path))
    csv_prefix = os.path.join(csv_dir, '')
    print("\n生成CSV附表（S1-S4）：")
    csv_files = export_csvs(df, months_26, weeks_26, issue_months, pending_months, output_prefix=csv_prefix)

    print(f"\n{'='*60}")
    print(f"  ✅ 报表生成完成！")
    print(f"  Excel文件：{out_path}")
    print(f"  CSV文件：{', '.join(os.path.basename(f) for f in csv_files)}")
    m26=(df['status']=='生效')&(df['issue_year']==2026)
    mpd=df['status'].isin(['尚欠保费','已签单','pending','待批核'])
    mwt=df['status']=='排期'
    print(f"  数据统计：总{len(df):,}条 | 2026生效{m26.sum()}件 | 未批核{mpd.sum()}件 | 待签{mwt.sum()}件")
    ape26=df[m26]['ape'].sum()
    print(f"  全业务达成率：{ape26/1_113_000_000:.1%}（{ape26:,.0f} / 1,113,000,000）")
    ym26=df[m26&(df['carrier']==YM_CARRIER)]['ape'].sum()
    print(f"  永明达成率：{ym26/976_100_000:.1%}（{ym26:,.0f} / 976,100,000）")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
