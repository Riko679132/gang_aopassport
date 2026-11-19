#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 knowledge/transport_factors.jsonl 写入 macau.sqlite::transport_factors（幂等）。

用法：
    python tools/import_transport_factors.py
    python tools/import_transport_factors.py --jsonl knowledge/transport_factors.jsonl
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
DEFAULT_JSONL = os.path.join(PROJECT_ROOT, "knowledge", "transport_factors.jsonl")


def main() -> int:
    ap = argparse.ArgumentParser(description="跨境交通碳排因子入库")
    ap.add_argument("--jsonl", default=DEFAULT_JSONL)
    ap.add_argument("--db", default=DB_PATH)
    args = ap.parse_args()
    if os.path.basename(args.db).lower() != "macau.sqlite":
        print("[ABORT] 只允许写 macau.sqlite")
        return 1

    rows = []
    with open(args.jsonl, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    missing = [r.get("mode_key") for r in rows
               if not r.get("source_ref") or not r.get("distance_km")]
    if missing:
        print("[ABORT] 缺少 source_ref/distance_km：%s" % missing)
        return 1

    conn = sqlite3.connect(args.db)
    try:
        for r in rows:
            conn.execute(
                "INSERT INTO transport_factors (mode_key, label, region_from, region_to, "
                "distance_km, factor_per_pkm, unit, source_ref, data_quality, notes) "
                "VALUES (?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(mode_key) DO UPDATE SET label=excluded.label, "
                "region_from=excluded.region_from, region_to=excluded.region_to, "
                "distance_km=excluded.distance_km, factor_per_pkm=excluded.factor_per_pkm, "
                "unit=excluded.unit, source_ref=excluded.source_ref, "
                "data_quality=excluded.data_quality, notes=excluded.notes",
                (r["mode_key"], r["label"], r["region_from"], r["region_to"],
                 r["distance_km"], r["factor_per_pkm"], r.get("unit", "kg CO2e/人·公里"),
                 r["source_ref"], r.get("data_quality", "unknown"), r.get("notes")))
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM transport_factors").fetchone()[0]
        print("[OK] transport_factors 共 %d 行" % n)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
