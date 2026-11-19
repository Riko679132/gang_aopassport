#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""抓取香港海关 / 渔农自然护理署 / 食环署 / 财政部公开法条页，存到 knowledge/raw/hk/。

只做“取回原文并留痕”，不做条款切分：结构化入库仍由人工核对后的
knowledge/customs_rules_hk.jsonl + tools/load_rules_to_db.py 完成。

用法：
    python tools/fetch_hk_rules.py
    python tools/fetch_hk_rules.py --only formula meat
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

import requests
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
OUT_DIR = os.path.join(PROJECT_ROOT, "knowledge", "raw", "hk")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

SOURCES = (
    {
        "id": "formula",
        "name": "香港海关 · 配方粉离境规定",
        "url": "https://www.customs.gov.hk/tc/customs-announcement/press-release/index_id_1346.html",
    },
    {
        "id": "imports",
        "name": "香港海关 · 进口管制（肉类/植物/动物）",
        "url": "https://www.customs.gov.hk/tc/service-enforcement-information/trade-facilitation/prohibited-articles/controlled-imports/index.html",
    },
    {
        "id": "afcd_plants",
        "name": "渔农自然护理署 · 植物进口",
        "url": "https://www.afcd.gov.hk/tc_chi/quarantine/qua_plants/qua_plants_pq/qua_plants_pq_imp/qua_plants_pq_imp.html",
    },
    {
        "id": "duty_free",
        "name": "财政部等 · 2024年第7号（自港澳进境免税额）",
        "url": "https://fgk.chinatax.gov.cn/zcfgk/c102416/c5232646/content.html",
    },
    {
        "id": "hk_duty_free",
        "name": "香港海关 · 旅客免税优惠（烟酒）",
        "url": "https://www.customs.gov.hk/tc/service-enforcement-information/passenger-clearance/duty-free-concessions/index.html",
    },
    {
        "id": "hk_cash",
        "name": "香港海关 · 现金类物品申报",
        "url": "https://www.customs.gov.hk/tc/service-enforcement-information/passenger-clearance/currency-bearer-negotiable-instruments/index.html",
    },
    {
        "id": "hk_vape",
        "name": "卫生署控烟酒办公室 · 另类吸烟产品禁令",
        "url": "https://www.taco.gov.hk/t/tc_chi/legislation/legislation_asp.html",
    },
    {
        "id": "afcd_animals",
        "name": "渔农自然护理署 · 动物进出口常见问题",
        "url": "https://www.afcd.gov.hk/tc_chi/quarantine/qua_ie/f_a_q.html",
    },
)


def _curl_fallback(url: str) -> str:
    """部分 .gov.hk 站点对 Python TLS 指纹直接断连；退回系统 curl（禁用吊销检查）。"""
    exe = shutil.which("curl")
    if not exe:
        raise RuntimeError("requests 失败且系统无 curl 可回退")
    fd, path = tempfile.mkstemp(suffix=".html")
    os.close(fd)
    try:
        subprocess.run([exe, "-sSL", "--ssl-no-revoke", "-m", "40",
                        "-A", UA, url, "-o", path], check=True,
                       capture_output=True)
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def fetch_text(url: str) -> str:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        r.raise_for_status()
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = r.apparent_encoding or "utf-8"
        html = r.text
    except Exception:
        html = _curl_fallback(url)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [re.sub(r"[ \t\u3000]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def main() -> int:
    ap = argparse.ArgumentParser(description="抓取香港法条原文（留痕）")
    ap.add_argument("--only", nargs="*", help="只抓指定 id：formula imports afcd_plants duty_free")
    args = ap.parse_args()
    wanted = set(args.only or [s["id"] for s in SOURCES])
    os.makedirs(OUT_DIR, exist_ok=True)

    ok = 0
    for src in SOURCES:
        if src["id"] not in wanted:
            continue
        dst = os.path.join(OUT_DIR, "%s.txt" % src["id"])
        try:
            body = fetch_text(src["url"])
        except Exception as exc:
            print("[FAIL] %-12s %s: %s" % (src["id"], src["name"], exc))
            continue
        with open(dst, "w", encoding="utf-8") as fh:
            fh.write("# %s\n# %s\n# fetched_at: %s\n\n%s\n"
                     % (src["name"], src["url"],
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), body))
        print("[OK]   %-12s %6d 字 → %s" % (src["id"], len(body), dst))
        ok += 1

    print("\n完成 %d/%d。结构化入库请核对后更新 knowledge/customs_rules_hk.jsonl，"
          "再运行 tools/load_rules_to_db.py --jsonl knowledge/customs_rules_hk.jsonl"
          % (ok, len(wanted)))
    return 0 if ok == len(wanted) else 1


if __name__ == "__main__":
    sys.exit(main())
