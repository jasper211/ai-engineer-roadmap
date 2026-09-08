#!/usr/bin/env python3
"""T018 RBC：FWD 比较年度、跨行主体说明与 BOC 官方快照。"""

import hashlib
import sys
from pathlib import Path

ICD = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ICD / "06_开发技能_Develop_Skills"))
from skills import rbc_parser  # noqa: E402


CASES = [
    ("FWD", 18, "05a0ce4c3c9d9a7c2b30d0b25256994a42d2d24e3fb022e136ae05f65362bdb5",
     "FWD Life Insurance Company (Bermuda) Limited", "199%", 1.99,
     "21,295,041", "10,703,322", 21295041000.0, 10703322000.0),
    ("BOC", 19, "e5e7ae4c6efe1dce869d74adce7fe64df0d08d3bfe1f87b9a47c4bd2350f7bf4",
     "BOC Group Life Assurance Company Limited", "204%", 2.04,
     "16,924,044", "8,311,199", 16924044000.0, 8311199000.0),
]


def snapshot(code, source_id, digest):
    return ICD / "07_接入记忆_Integrate_Memory/raw_data" / code / str(source_id) / f"{digest}.pdf"


def main():
    for code, source_id, digest, legal, raw, ratio, cb, pca, cb_abs, pca_abs in CASES:
        body = snapshot(code, source_id, digest).read_bytes()
        assert hashlib.sha256(body).hexdigest() == digest
        row = rbc_parser.parse_rbc(body)["records"][0]
        assert row["report_year"] == 2024
        assert row["legal_entity_name_raw"] == legal
        assert row["solvency_ratio_raw"] == raw and row["solvency_ratio"] == ratio
        assert row["capital_base_raw"] == cb and row["prescribed_capital_amount_raw"] == pca
        assert row["capital_base"] == cb_abs and row["prescribed_capital_amount"] == pca_abs
        assert row["amount_unit_raw"] == "in HKD thousands"

    # 比较年度不得覆盖标题报告时点；标题自身歧义仍必须 fail closed。
    synthetic = [{"text": "Disclosure Statement at 31 December 2024\nCapital adequacy\n"
                           "Authorized insurer's name\nExample Limited\n"
                           "Comparative as at 31 December 2023\n"
                           "Ratio of capital base to prescribed capital amount 200%",
                  "tables": []}]
    assert rbc_parser.extract_rbc(synthetic)["report_year"] == 2024
    synthetic[0]["text"] += "\nDisclosure Statement at 31 December 2023"
    try:
        rbc_parser.extract_rbc(synthetic)
    except rbc_parser.RbcParseError:
        pass
    else:
        raise AssertionError("多个披露标题年度必须安全失败")
    print("T018 focused tests: PASS (FWD/BOC + primary-year fail-closed)")


if __name__ == "__main__":
    main()
