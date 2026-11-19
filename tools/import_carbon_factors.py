#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通用碳排因子导入：读取 JSONL，幂等写入 macau.sqlite::carbon_factors。

每行必填：material / emission_factor / unit / source_ref。
可选：material_en / category / system_boundary / data_quality / valid_year / notes。

用法：
    python tools/import_carbon_factors.py --jsonl knowledge/carbon_factors_extra.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
DB_PATH = os.path.join(PROJECT_ROOT, "data", "macau.sqlite")


def main() -> int:
    ap = argparse.ArgumentParser(description="碳排因子 JSONL 入库")
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--db", default=DB_PATH)
    args = ap.parse_args()
    if os.path.basename(args.db).lower() != "macau.sqlite":
        print("[ABORT] 只允许写 macau.sqlite")
        return 1

    rows = []
    with open(args.jsonl, "r", encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            missing = [k for k in ("material", "emission_factor", "unit", "source_ref")
                       if rec.get(k) in (None, "")]
            if missing:
                print("[ABORT] 第 %d 行缺少 %s" % (n, missing))
                return 1
            rows.append(rec)

    conn = sqlite3.connect(args.db)
    try:
        added = 0
        for r in rows:
            cur = conn.execute(
                "INSERT OR IGNORE INTO carbon_factors (material, material_en, category, "
                "emission_factor, unit, system_boundary, source_ref, data_quality, "
                "valid_year, notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (r["material"], r.get("material_en"), r.get("category", "food"),
                 float(r["emission_factor"]), r["unit"],
                 r.get("system_boundary", "cradle-to-gate"), r["source_ref"],
                 r.get("data_quality", "unknown"), r.get("valid_year"), r.get("notes")))
            added += cur.rowcount
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM carbon_factors").fetchone()[0]
        print("[OK] 新增 %d 条，carbon_factors 共 %d 行" % (added, total))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
