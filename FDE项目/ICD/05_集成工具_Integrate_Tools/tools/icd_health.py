"""ICD 生产健康检查：只读审计数据库、快照、时效和覆盖缺口。"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from tools import icd_query


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _snapshot_path(raw_root: Path, stored: str) -> Path:
    rel = Path(stored)
    if rel.parts and rel.parts[0] == "raw_data":
        rel = Path(*rel.parts[1:])
    path = (raw_root / rel).resolve()
    root = raw_root.resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"快照路径越界: {stored}")
    return path


def check(db_path: Path | str, raw_root: Path | str, *, max_age_days: int = 400,
          now: datetime | None = None) -> Dict[str, Any]:
    if not isinstance(max_age_days, int) or isinstance(max_age_days, bool) or max_age_days < 1:
        raise ValueError("max_age_days 必须是正整数")
    now = now or datetime.now(timezone.utc)
    raw_root = Path(raw_root)
    critical, warnings = [], []
    checks: Dict[str, Any] = {}
    with icd_query.ICDClient.open_readonly(db_path) as client:
        conn = client.conn
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        checks["integrity_check"] = integrity
        checks["foreign_key_violations"] = len(fk)
        if integrity != "ok": critical.append(f"SQLite integrity_check={integrity}")
        if fk: critical.append(f"SQLite 外键违例 {len(fk)} 个")

        orphan_ratio = conn.execute("""SELECT COUNT(*) FROM fulfillment_ratio f
          LEFT JOIN fetch_run r ON r.run_id=f.run_id
          WHERE r.run_id IS NULL OR r.fetch_status<>'OK'""").fetchone()[0]
        orphan_rbc = conn.execute("""SELECT COUNT(*) FROM rbc_statement s
          LEFT JOIN fetch_run r ON r.run_id=s.run_id
          WHERE r.run_id IS NULL OR r.fetch_status<>'OK'""").fetchone()[0]
        duplicates = conn.execute("""SELECT COUNT(*) FROM (
          SELECT insurer_code,product_name_raw,metric_type,scope_currency_raw,
                 report_year,observation_year_raw,run_id,COUNT(*) n
          FROM fulfillment_ratio GROUP BY insurer_code,product_name_raw,metric_type,
                 scope_currency_raw,report_year,observation_year_raw,run_id HAVING n>1)""").fetchone()[0]
        checks.update(business_orphan_rows=orphan_ratio + orphan_rbc,
                      fulfillment_duplicate_keys=duplicates)
        if orphan_ratio + orphan_rbc: critical.append(f"业务记录关联非成功抓取 {orphan_ratio + orphan_rbc} 条")
        if duplicates: critical.append(f"分红自然键重复 {duplicates} 组")

        snapshots = conn.execute("""SELECT run_id,content_hash,snapshot_path,fetched_at
          FROM fetch_run WHERE fetch_status='OK' ORDER BY run_id""").fetchall()
        missing = mismatched = 0
        stale = []
        for run_id, expected, stored, fetched_at in snapshots:
            path = _snapshot_path(raw_root, stored)
            if not path.is_file():
                missing += 1
            elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                mismatched += 1
            age = (now - _parse_utc(fetched_at)).days
            if age > max_age_days:
                stale.append({"run_id": run_id, "age_days": age})
        checks.update(successful_snapshots=len(snapshots), snapshot_missing=missing,
                      snapshot_hash_mismatch=mismatched, stale_successful_runs=stale)
        if missing: critical.append(f"成功抓取快照缺失 {missing} 个")
        if mismatched: critical.append(f"成功抓取快照哈希错配 {mismatched} 个")
        if stale: warnings.append(f"超过 {max_age_days} 天的成功抓取 {len(stale)} 个")

        coverage = client.coverage()["data"]
        gaps = [x for x in coverage if x["coverage_status"] != "FULL"]
        checks["coverage_gaps"] = gaps
        if gaps: warnings.append(f"非 FULL 覆盖项 {len(gaps)} 个")

    status = "CRITICAL" if critical else ("DEGRADED" if warnings else "HEALTHY")
    return {"status": status, "checked_at": now.isoformat(), "max_age_days": max_age_days,
            "checks": checks, "critical": critical, "warnings": warnings,
            "exit_code": {"HEALTHY": 0, "DEGRADED": 1, "CRITICAL": 2}[status]}
