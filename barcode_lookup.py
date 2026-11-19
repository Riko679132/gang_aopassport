# -*- coding: utf-8 -*-
"""条形码 → 商品信息：Open Food Facts（免费、无 Key）优先，失败回退网络搜索。

返回：
    {"code","name","brand","ingredients","source"}
    或 {"code","name":"","brand":"","ingredients":"","source":"web","clues":[...]}
    查不到返回 None。
"""
from __future__ import annotations

import re
import time
from typing import Dict, Optional

import requests

UA = "MacauGreenPass/1.0 (+https://github.com/Riko679132/macou_march)"
OFF_URL = "https://world.openfoodfacts.org/api/v2/product/%s.json"
OFF_FIELDS = ("product_name,product_name_zh,brands,"
              "ingredients_text,ingredients_text_zh,categories")
_CACHE: Dict[str, tuple] = {}
_TTL = 86400


def _norm(code: str) -> str:
    return re.sub(r"\D", "", code or "")


def lookup_barcode(code: str) -> Optional[dict]:
    code = _norm(code)
    if not (8 <= len(code) <= 14):
        return None
    now = time.time()
    hit = _CACHE.get(code)
    if hit and now - hit[0] < _TTL:
        return hit[1]

    info = None
    try:  # 1) Open Food Facts
        r = requests.get(OFF_URL % code, params={"fields": OFF_FIELDS},
                         headers={"User-Agent": UA, "Accept": "application/json"},
                         timeout=10)
        if r.status_code == 200 and "json" in (r.headers.get("content-type") or ""):
            data = r.json()
            p = data.get("product") if data.get("status") == 1 else None
            if p:
                name = (p.get("product_name_zh") or p.get("product_name") or "").strip()
                ing = (p.get("ingredients_text_zh") or p.get("ingredients_text") or "").strip()
                brand = (p.get("brands") or "").strip()
                if name or ing:
                    info = {"code": code, "name": name, "brand": brand,
                            "ingredients": ing, "source": "Open Food Facts"}
    except Exception:
        pass

    if not info:  # 2) 网络搜索兜底
        try:
            from web_search import search_web
            clues = []
            for r in search_web("%s 条形码 商品" % code, max_results=3)[:2]:
                t = (r.get("title") or "").strip()
                s = (r.get("snippet") or "").strip()
                if t or s:
                    clues.append(("%s %s" % (t, s)).strip()[:160])
            if clues:
                info = {"code": code, "name": "", "brand": "", "ingredients": "",
                        "source": "web", "clues": clues}
        except Exception:
            pass

    _CACHE[code] = (now, info)
    return info
