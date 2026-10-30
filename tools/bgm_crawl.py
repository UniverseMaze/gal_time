#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 UniverseMaze
"""
从 Bangumi 抓取指定用户「玩过」的游戏条目信息，供 GameTime 匹配用。

用法:
    python tools/bgm_crawl.py --uid 756388
    python tools/bgm_crawl.py --uid 756388 --types 2,3 --out .tmp/bgm_raw.json

说明:
- 用 Playwright 驱动本机 Edge（走系统代理），因为直连 api.bgm.tv 会被 DNS 污染。
- 收藏列表走 /v0/users/{uid}/collections，条目详情走 /v0/subjects/{id}。
  部分老条目的 ID 在 API 与网页上都已不存在（被合并或删除），会标记 status=missing，
  这类条目只能保留列表里的基础信息（名称 / 日期 / 封面），没有 infobox。
- 输出为原始 JSON，不做任何本地数据写入。
"""
import argparse
import json
import time
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://bgm.tv"
API = "https://api.bgm.tv"
COLLECT_TYPES = {1: "想玩", 2: "玩过", 3: "在玩", 4: "搁置", 5: "抛弃"}


def fetch_list(page, uid, subject_type, ctype):
    """翻页拉全量收藏列表，返回 [{id,name,name_cn,date,rate,images}]"""
    return page.evaluate(
        """async ({uid, subjectType, ctype}) => {
            let out = [], offset = 0, total = null;
            while (true) {
                const url = `https://api.bgm.tv/v0/users/${uid}/collections`
                    + `?subject_type=${subjectType}&type=${ctype}&limit=50&offset=${offset}`;
                const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
                if (!res.ok) return { error: res.status, data: out };
                const j = await res.json();
                total = j.total;
                const batch = j.data || [];
                out = out.concat(batch);
                if (!batch.length || out.length >= total) break;
                offset += 50;
            }
            return {
                total,
                data: out.map(x => ({
                    id: x.subject.id,
                    name: x.subject.name,
                    name_cn: x.subject.name_cn || '',
                    date: x.subject.date || '',
                    rate: x.rate || 0,
                    images: x.subject.images || null,
                    type: x.subject.type,
                    comment: x.comment || '',
                    tags: x.tags || []
                }))
            };
        }""",
        {"uid": str(uid), "subjectType": subject_type, "ctype": ctype},
    )


def fetch_subject(page, sid):
    """取单个条目详情。返回 (status, payload)"""
    return page.evaluate(
        """async (sid) => {
            const res = await fetch('https://api.bgm.tv/v0/subjects/' + sid,
                                    { headers: { 'Accept': 'application/json' } });
            if (!res.ok) return { status: res.status };
            return { status: 200, body: await res.json() };
        }""",
        sid,
    )


def normalize_infobox(raw):
    """把 infobox 的 key/value 拉平成 {key: 字符串或字符串数组}"""
    out = {}
    for box in raw or []:
        key = (box.get("key") or "").strip()
        if not key:
            continue
        val = box.get("value")
        if isinstance(val, list):
            items = []
            for v in val:
                if isinstance(v, dict):
                    items.append(str(v.get("v", "")).strip())
                else:
                    items.append(str(v).strip())
            items = [x for x in items if x]
            out[key] = items if len(items) > 1 else (items[0] if items else "")
        else:
            out[key] = str(val).strip() if val is not None else ""
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uid", required=True, help="Bangumi 用户 UID")
    ap.add_argument("--types", default="2", help="收藏类型，逗号分隔。2=玩过 3=在玩")
    ap.add_argument("--out", default=".tmp/bgm_raw.json")
    ap.add_argument("--delay", type=float, default=0.3, help="每个条目之间的间隔秒数")
    ap.add_argument("--channel", default="msedge", help="浏览器通道，默认 msedge")
    args = ap.parse_args()

    types = [int(t) for t in args.types.split(",") if t.strip()]
    result = {
        "uid": args.uid,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "types": {str(t): COLLECT_TYPES.get(t, str(t)) for t in types},
        "collections": {},
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(channel=args.channel, headless=True)
        page = browser.new_page()
        # 先在站点内建立会话，后面在页面上下文里 fetch 同源/跨域 API
        page.goto(f"{BASE}/user/{args.uid}", timeout=60000, wait_until="domcontentloaded")
        print(f"[1/3] 已打开用户主页: {page.title()}")

        all_items = {}
        for t in types:
            res = fetch_list(page, args.uid, 4, t)
            if "error" in res:
                print(f"  ! 类型 {t} 拉取失败: HTTP {res['error']}", file=sys.stderr)
                continue
            print(f"[2/3] {COLLECT_TYPES.get(t, t)}: {res['total']} 条")
            result["collections"][str(t)] = {"label": COLLECT_TYPES.get(t, str(t)), "total": res["total"]}
            for it in res["data"]:
                if it["id"] not in all_items:
                    it["collect_type"] = t
                    all_items[it["id"]] = it

        print(f"[3/3] 抓取 {len(all_items)} 个条目详情 ...")
        ok, missing = 0, 0
        for i, (sid, it) in enumerate(all_items.items(), 1):
            r = fetch_subject(page, sid)
            if r.get("status") == 200:
                body = r["body"]
                it["status"] = "ok"
                it["infobox"] = normalize_infobox(body.get("infobox"))
                it["infobox_raw"] = body.get("infobox") or []
                it["summary"] = (body.get("summary") or "").strip()
                it["name_bgm"] = body.get("name")
                it["name_cn_bgm"] = body.get("name_cn") or ""
                it["date_bgm"] = body.get("date") or ""
                it["platform"] = body.get("platform") or ""
                it["rating"] = (body.get("rating") or {}).get("score") or 0
                it["tags_bgm"] = [t.get("name") for t in (body.get("tags") or []) if t.get("name")]
                ok += 1
            else:
                it["status"] = "missing"
                it["infobox"] = {}
                it["summary"] = ""
                missing += 1
            if i % 10 == 0 or i == len(all_items):
                print(f"    {i}/{len(all_items)}  成功 {ok} · 条目失效 {missing}")
            time.sleep(args.delay)

        browser.close()

    result["items"] = list(all_items.values())
    result["stats"] = {"total": len(all_items), "ok": ok, "missing": missing}

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完成: 成功 {ok} / 失效 {missing} → {out}")


if __name__ == "__main__":
    main()
