# -*- coding: utf-8 -*-
"""端到端冒烟测试：默认离线（不调模型、不联网），--online 走真实 DeepSeek。

用法：
    .venv\\Scripts\\python.exe tools\\smoke_test.py
    .venv\\Scripts\\python.exe tools\\smoke_test.py --online
"""
from __future__ import annotations

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import agent_brain as ab

# (名称, 输入, 方向, 离线期望, 在线期望)；离线为 None 表示该用例只能在线判定
CASES = (
    ("肉松饼干", "我带了2公斤含肉松的饼干", "内地入境澳门", "red", "red"),
    ("曲奇含鸡蛋", "曲奇，配料：小麦粉、白砂糖、植物油、鸡蛋、食盐", "内地入境澳门", "green", "green"),
    ("散装自制糕点", "散装自制糕点", "内地入境澳门", "yellow", "yellow"),
    ("奥利奥", "一袋奥利奥", "内地入境澳门", None, "green"),
    ("苹果入境澳门", "一斤苹果", "内地入境澳门", "green", "green"),
    ("苹果返回内地", "一斤苹果", "澳门入境内地", "red", "red"),
    ("多件奢侈品", "八个 LV 手提包", "澳门入境内地", "red", "red"),
    ("香烟单位不匹配", "1条香烟", "内地入境澳门", "error", "error"),
    ("巴旦木薄脆", "巴旦木薄脆", "内地入境澳门", "green", "green"),
    ("香港奶粉限额", "我要从香港回内地，带了3罐婴儿配方奶粉。", "香港入境内地",
     "yellow", ("yellow", "red")),
    ("香港奶粉超重", "我要从香港回内地，带了3罐婴儿配方奶粉，每罐900克。", "香港入境内地",
     "red", "red"),
    ("中旅大巴月饼", "我坐中旅大巴从香港回广州，买了两盒香港美心月饼。", "香港入境内地",
     "green", "green"),
    ("香港生肉禁令", "我从内地带了两斤新鲜猪肉去香港。", "内地入境香港", "red", "red"),
)


def run_offline(desc: str, direction: str, cfg: dict, kb) -> dict:
    return ab.decide(desc, cfg, kb, offline=True,
                     direction=ab.normalize_direction(direction))


def main() -> int:
    ap = argparse.ArgumentParser(description="澳门绿色通关 · 端到端冒烟测试")
    ap.add_argument("--online", action="store_true",
                    help="真实调用 DeepSeek（会产生 token 费用）")
    args = ap.parse_args()

    cfg = ab.load_config()
    if args.online:
        key, source = ab.resolve_api_key(cfg)
        if not key:
            print("[FAIL] 未配置 DeepSeek Key（%s），无法在线测试" % source)
            return 1
        print("[INFO] 在线模式：model=%s max_tokens=%s"
              % (cfg["deepseek"]["model"], cfg["deepseek"]["max_tokens"]))
    else:
        print("[INFO] 离线模式：只跑本地规则，不调用模型、不联网")

    # 烟测不应污染 search_logs（AGENTS 要求保留真实查询历史）
    ab.write_log = lambda *a, **k: None

    kb = ab.KnowledgeBase(cfg)
    passed = failed = skipped = 0
    for name, desc, direction, want_off, want_on in CASES:
        expected = want_on if args.online else want_off
        if expected is None:
            skipped += 1
            result = (ab.analyze_item(desc, direction) if args.online
                      else run_offline(desc, direction, cfg, kb))
            print("[SKIP] %-16s %s（仅在线判定，实际=%s）"
                  % (name, direction, result.get("status")))
            continue

        t0 = time.time()
        result = (ab.analyze_item(desc, direction) if args.online
                  else run_offline(desc, direction, cfg, kb))
        elapsed = int((time.time() - t0) * 1000)
        status = result.get("status")
        allowed = expected if isinstance(expected, (tuple, set, list)) else (expected,)
        ok = status in allowed and not (args.online and result.get("error"))
        if ok:
            passed += 1
        else:
            failed += 1
        print("[%s] %-16s %-9s 期望=%-11s 实际=%-6s %5dms"
              % ("PASS" if ok else "FAIL", name, direction,
                 "/".join(allowed), status, elapsed))
        if not ok:
            detail = result.get("error") or result.get("reason") or ""
            print("       └─ %s" % str(detail)[:160])

    total = passed + failed
    print("\n结果：%d/%d 通过" % (passed, total)
          + ("，%d 个用例跳过（需 --online）" % skipped if skipped else ""))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
