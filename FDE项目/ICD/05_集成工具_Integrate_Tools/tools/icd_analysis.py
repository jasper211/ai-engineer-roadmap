"""ICD 只读业务分析：覆盖、披露完整度、分红分布与 RBC 资本缓冲。"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List

from tools import icd_query


def _percentile(values: Iterable[float], p: float) -> float | None:
    xs = sorted(float(x) for x in values)
    if not xs:
        return None
    pos = (len(xs) - 1) * p
    lo, hi = math.floor(pos), math.ceil(pos)
    value = xs[lo] if lo == hi else xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)
    return round(value, 6)


def build(db_path: Path | str) -> Dict[str, Any]:
    """从最新成功版本构建分析；全程 SQLite mode=ro。"""
    with icd_query.ICDClient.open_readonly(db_path) as client:
        conn = client.conn
        latest = """
          f.run_id=(SELECT MAX(f2.run_id) FROM fulfillment_ratio f2
            JOIN fetch_run fr2 ON fr2.run_id=f2.run_id AND fr2.fetch_status='OK'
            WHERE f2.insurer_code=f.insurer_code AND f2.product_name_raw=f.product_name_raw
              AND f2.metric_type=f.metric_type AND f2.scope_currency_raw=f.scope_currency_raw
              AND f2.report_year=f.report_year AND f2.observation_year_raw=f.observation_year_raw)
        """
        rows = conn.execute(f"""
          SELECT f.insurer_code,f.product_name_raw,f.metric_type,f.report_year,
                 f.normalized_value,f.run_id
          FROM fulfillment_ratio f JOIN fetch_run fr ON fr.run_id=f.run_id
          WHERE fr.fetch_status='OK' AND {latest}
        """).fetchall()
        by_insurer: Dict[str, List[Any]] = {}
        for row in rows:
            by_insurer.setdefault(row[0], []).append(row)

        fulfillment = []
        for code in sorted(by_insurer):
            data = by_insurer[code]
            nums = [r[4] for r in data if r[4] is not None]
            metrics: Dict[str, int] = {}
            for r in data:
                metrics[r[2]] = metrics.get(r[2], 0) + 1
            fulfillment.append({
                "insurer_code": code,
                "report_years": sorted({r[3] for r in data}),
                "product_count": len({r[1] for r in data}),
                "observation_count": len(data),
                "numeric_count": len(nums),
                "non_numeric_count": len(data) - len(nums),
                "numeric_rate": round(len(nums) / len(data), 6) if data else None,
                "metric_counts": dict(sorted(metrics.items())),
                "numeric_distribution": {
                    "p25": _percentile(nums, .25), "median": _percentile(nums, .5),
                    "p75": _percentile(nums, .75), "min": min(nums) if nums else None,
                    "max": max(nums) if nums else None,
                },
                "evidence_run_ids": sorted({r[5] for r in data}),
            })

        rbc_rows = client.rbc(limit=1000)["data"]
        rbc = [{k: row[k] for k in (
            "insurer_code", "legal_entity_name_raw", "report_year", "solvency_ratio",
            "solvency_ratio_raw", "capital_base", "capital_base_raw",
            "prescribed_capital_amount", "prescribed_capital_amount_raw", "currency",
            "amount_unit_raw", "run_id", "sha256", "source_url"
        )} for row in sorted(rbc_rows, key=lambda x: (-x["solvency_ratio"], x["insurer_code"]))]
        coverage = client.coverage()["data"]
        as_of = conn.execute("SELECT MAX(fetched_at) FROM fetch_run WHERE fetch_status='OK'").fetchone()[0]

    return {
        "report_type": "ICD_BUSINESS_ANALYSIS",
        "data_as_of": as_of,
        "fulfillment_summary": fulfillment,
        "rbc_summary": rbc,
        "coverage": coverage,
        "interpretation_guardrails": [
            "分红实现率是历史披露，不代表未来回报或保证利益。",
            "不同产品、指标、币种和观察期不可只凭一个中位数直接排名；分布仅用于数据概览。",
            "官网 N/A/未推出等原文计入 non_numeric_count，不当作零。",
            "RBC 按持牌法律主体比较，不代表集团合并口径；高于监管底线不等于没有风险。",
        ],
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = ["# ICD 业务分析快照", "", f"数据截至：`{report['data_as_of']}`", "",
             "## 分红实现率披露概览", "",
             "| 保司 | 报告年 | 产品数 | 观测数 | 数值数 | 原文占位 | 数值率 | 中位数 |", 
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for x in report["fulfillment_summary"]:
        median = x["numeric_distribution"]["median"]
        lines.append(f"| {x['insurer_code']} | {','.join(map(str,x['report_years']))} | {x['product_count']} | {x['observation_count']} | {x['numeric_count']} | {x['non_numeric_count']} | {x['numeric_rate']:.1%} | {median:.1%} |")
    lines += ["", "中位数仅描述已数值化观测的分布，不用于跨产品业绩排名。", "", "## 2024 RBC 概览", "",
              "| 法律主体 | RBC 比率 | 资本基础原文 | 规定资本额原文 | 证据 run_id |", "|---|---:|---:|---:|---:|"]
    for x in report["rbc_summary"]:
        lines.append(f"| {x['legal_entity_name_raw']} | {x['solvency_ratio']:.0%} | {x['capital_base_raw']} | {x['prescribed_capital_amount_raw']} | {x['run_id']} |")
    lines += ["", "## 使用限制", ""] + [f"- {x}" for x in report["interpretation_guardrails"]]
    return "\n".join(lines) + "\n"


def write(report: Dict[str, Any], output_dir: Path | str) -> Dict[str, str]:
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    json_path, md_path = root / "ICD_业务分析_最新.json", root / "ICD_业务分析_最新.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json_path": str(json_path), "markdown_path": str(md_path)}
