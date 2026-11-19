#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""增量迁移 macau.sqlite → v2：
    1. customs_rules 新增 region（内地/澳门/香港），direction 扩展香港双向枚举；
    2. 新建 transport_factors（跨境交通碳排因子）。

幂等：已迁移则跳过重建，只补建缺失的表。重建前自动备份到 data/backups/。

用法：
    python scripts/migrate_hk_region.py [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
DB_PATH = os.path.join(PROJECT_ROOT, "data", "macau.sqlite")
BACKUP_DIR = os.path.join(PROJECT_ROOT, "data", "backups")

NEW_RULES_DDL = """
CREATE TABLE customs_rules_new (
    rule_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    region          TEXT    NOT NULL DEFAULT '澳门' CHECK (region IN ('内地', '澳门', '香港')),
    direction       TEXT    NOT NULL CHECK (direction IN (
                        'inbound_macau', 'outbound_macau',
                        'inbound_mainland', 'outbound_mainland',
                        'inbound_hongkong', 'outbound_hongkong',
                        'bidirectional'
                    )),
    item_category   TEXT    NOT NULL,
    item_subtype    TEXT,
    rule_type       TEXT    NOT NULL CHECK (
                        rule_type IN ('prohibited', 'restricted', 'declaration', 'duty_free')
                    ),
    limit_value     REAL,
    limit_unit      TEXT,
    limit_evidence  TEXT,
    penalty_clause  TEXT,
    authority       TEXT,
    effective_date  TEXT,
    source_ref      TEXT,
    raw_text        TEXT,
    dedup_hash      TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
)
"""

TRANSPORT_DDL = """
CREATE TABLE IF NOT EXISTS transport_factors (
    mode_key        TEXT    PRIMARY KEY,
    label           TEXT    NOT NULL,
    region_from     TEXT    NOT NULL CHECK (region_from IN ('内地', '澳门', '香港')),
    region_to       TEXT    NOT NULL CHECK (region_to IN ('内地', '澳门', '香港')),
    distance_km     REAL    NOT NULL CHECK (distance_km > 0),
    factor_per_pkm  REAL    NOT NULL CHECK (factor_per_pkm >= 0),
    unit            TEXT    NOT NULL DEFAULT 'kg CO2e/人·公里',
    source_ref      TEXT    NOT NULL,
    data_quality    TEXT    NOT NULL DEFAULT 'unknown' CHECK (
                        data_quality IN ('measured', 'literature', 'database', 'estimate', 'unknown')
                    ),
    notes           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""

REGION_CASE = """
CASE
    WHEN lower(coalesce(source_ref, '')) LIKE '%customs.gov.mo%'
      OR coalesce(authority, '') LIKE '%澳门%'
      OR coalesce(authority, '') LIKE '%市政署%' THEN '澳门'
    ELSE '内地'
END
"""


def guard(path: str) -> None:
    if "ccus" in os.path.basename(path).lower():
        raise SystemExit("[ABORT] 禁止操作父项目 ccus 库：%s" % path)
    if os.path.basename(path).lower() != "macau.sqlite":
        raise SystemExit("[ABORT] 本脚本仅用于 macau.sqlite，收到：%s" % path)


def archive(db_path: str) -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(BACKUP_DIR, "macau_%s.sqlite" % stamp)
    shutil.copy2(db_path, dst)
    return dst


def main() -> int:
    ap = argparse.ArgumentParser(description="macau.sqlite v2 迁移（region / 香港方向 / 交通因子）")
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    guard(args.db)

    conn = sqlite3.connect(args.db)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(customs_rules)")}
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='customs_rules'"
        ).fetchone()
        old_sql = (row[0] or "") if row else ""
        need_rebuild = "region" not in cols or "inbound_hongkong" not in old_sql

        print("[INFO] 当前列：%s" % ", ".join(sorted(cols)))
        print("[INFO] 需要重建 customs_rules：%s" % ("是" if need_rebuild else "否（已迁移）"))
        if args.dry_run:
            print("[DRY-RUN] 未写入任何内容")
            return 0

        if need_rebuild:
            print("[INFO] 备份到 %s" % archive(args.db))
            conn.execute("BEGIN")
            conn.execute("DROP TABLE IF EXISTS customs_rules_new")
            conn.execute(NEW_RULES_DDL)
            conn.execute(
                "INSERT INTO customs_rules_new (rule_id, region, direction, item_category, "
                "item_subtype, rule_type, limit_value, limit_unit, limit_evidence, "
                "penalty_clause, authority, effective_date, source_ref, raw_text, "
                "dedup_hash, is_active, created_at) "
                "SELECT rule_id, %s, direction, item_category, item_subtype, rule_type, "
                "limit_value, limit_unit, limit_evidence, penalty_clause, authority, "
                "effective_date, source_ref, raw_text, dedup_hash, is_active, created_at "
                "FROM customs_rules" % REGION_CASE
            )
            kept = conn.execute("SELECT COUNT(*) FROM customs_rules_new").fetchone()[0]
            conn.execute("DROP TABLE customs_rules")
            conn.execute("ALTER TABLE customs_rules_new RENAME TO customs_rules")
            for ddl in (
                "CREATE INDEX idx_rules_direction ON customs_rules(direction)",
                "CREATE INDEX idx_rules_region ON customs_rules(region)",
                "CREATE INDEX idx_rules_category ON customs_rules(item_category)",
                "CREATE INDEX idx_rules_type ON customs_rules(rule_type)",
                "CREATE UNIQUE INDEX idx_rules_dedup ON customs_rules(dedup_hash)",
            ):
                conn.execute(ddl)
            conn.execute("PRAGMA user_version = 2")
            conn.commit()
            print("[OK] customs_rules 重建完成，保留 %d 行" % kept)

        conn.executescript(TRANSPORT_DDL)
        conn.commit()
        n_tf = conn.execute("SELECT COUNT(*) FROM transport_factors").fetchone()[0]
        n_rules = conn.execute("SELECT COUNT(*) FROM customs_rules").fetchone()[0]
        print("[OK] customs_rules=%d 行；transport_factors=%d 行" % (n_rules, n_tf))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
