# -*- coding: utf-8 -*-
"""跨境交通段碳排：里程 × 人均公里因子。

因子与里程来自 macau.sqlite::transport_factors（带 source_ref，可审计）；
本模块只做确定性乘法，不猜线路、不补缺省因子。
"""
from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, Optional, Tuple

MODE_KEYWORDS = (
    ("coach_hk_gz", ("中旅", "跨境大巴", "直通巴", "大巴", "巴士", "客车")),
    ("hsr_hk_gz", ("高铁", "动车", "港铁", "铁路")),
    ("ferry_turbojet", ("喷射飞航", "turbojet", "噴射飛航")),
    ("ferry_cotai", ("金光飞航", "金光", "cotai")),
    ("ferry_turbojet", ("渡轮", "客船", "坐船", "乘船")),
)

DEFAULT_MODE = {
    ("内地", "香港"): "hsr_hk_gz",
    ("香港", "内地"): "hsr_hk_gz",
    ("澳门", "香港"): "ferry_turbojet",
    ("香港", "澳门"): "ferry_turbojet",
}

_CACHE: Dict[str, Tuple[int, Dict[str, Dict[str, Any]]]] = {}


def route_pair(direction: Optional[str]) -> Optional[Tuple[str, str]]:
    if not direction or "入境" not in direction:
        return None
    src, _, dst = direction.partition("入境")
    if src in ("内地", "澳门", "香港") and dst in ("内地", "澳门", "香港"):
        return src, dst
    return None


def detect_mode(text: str) -> Optional[str]:
    low = (text or "").lower()
    for mode, words in MODE_KEYWORDS:
        if any(w.lower() in low for w in words):
            return mode
    return None


def _rows(db_path: str) -> Dict[str, Dict[str, Any]]:
    try:
        mtime = os.path.getmtime(db_path)
    except OSError:
        return {}
    hit = _CACHE.get(db_path)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = {r["mode_key"]: dict(r) for r in conn.execute(
            "SELECT * FROM transport_factors")}
        conn.close()
    except sqlite3.Error:
        return {}
    _CACHE[db_path] = (mtime, rows)
    return rows


def estimate_transport(direction: Optional[str], text: str,
                       db_path: str) -> Optional[Dict[str, Any]]:
    """返回本段交通碳排；非香港路线或查不到因子时返回 None。"""
    pair = route_pair(direction)
    if not pair or "香港" not in pair:
        return None
    mode = detect_mode(text) or DEFAULT_MODE.get(pair)
    row = _rows(db_path).get(mode or "")
    if not row:
        return None
    kg = round(float(row["distance_km"]) * float(row["factor_per_pkm"]), 3)
    return {
        "mode_key": row["mode_key"],
        "label": row["label"],
        "distance_km": float(row["distance_km"]),
        "factor_per_pkm": float(row["factor_per_pkm"]),
        "unit": row["unit"],
        "kg": kg,
        "source_ref": row["source_ref"],
        "data_quality": row["data_quality"],
    }
