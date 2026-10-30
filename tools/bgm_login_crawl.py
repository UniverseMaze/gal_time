#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
带登录态的 Bangumi 抓取。

背景:
    Bangumi 对未登录用户屏蔽了大量 R18 游戏条目（兰斯系列、末世孤雄、BLACKSOULS 等），
    /v0/subjects/{id} 与网页 subject 页都会返回 404。登录后这些条目才可见。

用法:
    python tools/bgm_login_crawl.py --uid 756388 --types 2,3 --out .tmp/bgm_raw_full.json

行为:
    1. 打开一个可见的 Edge 窗口，停在 Bangumi 登录页（独立 profile，不动日常 Edge 配置）；
    2. 每 5 秒轮询 /v0/me，检测到登录成功就自动继续，不需要手动关窗口；
    3. 复用同一会话抓取收藏列表与条目详情，逻辑与 bgm_crawl.py 一致；
    4. 进度写入 .tmp/login_status.txt，方便外部查看。

注意:
    密码只输入在浏览器里，脚本不接触任何凭据。
"""
import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bgm_crawl import fetch_list, fetch_subject, normalize_infobox, COLLECT_TYPES  # noqa: E402

BASE = "https://bgm.tv"
STATUS_FILE = Path(".tmp/login_status.txt")


def write_status(msg):
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(msg + "\n", encoding="utf-8")
    print(f"[status] {msg}", flush=True)


def check_login(page):
    """检测登录态。

    坑一：api.bgm.tv/v0/me 只认 OAuth Token，用网页 Cookie 访问恒为 401，
          不能拿它判断是否登录。
    坑二：靠首页是否包含「退出」这类关键词判断，会随页面改版失效。
    所以这里做**功能性探测**：请求一个 R18 条目（11168 兰斯6）。
    未登录时 Bangumi 会返回「数据库中没有查询您所指定的条目」；
    登录且账号允许 R18 时，页面里才存在 infobox（发行/剧本/原画等字段）。
    返回 {'ok': bool, 'detail': str}
    """
    try:
        r = page.evaluate(
            """async () => {
                try {
                    const res = await fetch('https://bgm.tv/subject/11168',
                                            {credentials: 'include'});
                    const t = await res.text();
                    return {
                        status: res.status,
                        hasInfobox: t.includes('id="infobox"'),
                        blocked: t.includes('数据库中没有') || t.includes('没有查询到'),
                        hasLogout: /href="[^"]*logout/.test(t),
                        len: t.length
                    };
                } catch (e) { return {error: String(e)}; }
            }"""
        )
        if r.get("error"):
            return {"ok": False, "detail": "probe error"}
        ok = bool(r.get("hasInfobox")) or bool(r.get("hasLogout"))
        detail = "infobox=%s blocked=%s logout=%s" % (
            r.get("hasInfobox"), r.get("blocked"), r.get("hasLogout"))
        return {"ok": ok, "detail": detail}
    except Exception:
        return {"ok": False, "detail": "check exception"}


def scrape_subject_html(page, sid):
    """API 拿不到时，直接解析条目网页（登录后才可见被屏蔽的条目）。

    返回 dict（同 API 的字段口径）或 None 表示确实不存在。
    """
    page.goto(f"{BASE}/subject/{sid}", timeout=60000, wait_until="domcontentloaded")
    html = page.content()
    if "数据库中没" in html or "没有查询到" in html:
        return None
    lis = page.locator("#infobox li")
    n = lis.count()
    if not n:
        return None
    infobox = {}
    for i in range(n):
        txt = lis.nth(i).inner_text().replace("\n", " ").strip()
        if not txt:
            continue
        for sep in (":", "："):
            if sep in txt:
                k, v = txt.split(sep, 1)
                infobox[k.strip()] = v.strip()
                break
        else:
            infobox[txt] = ""
    name = ""
    try:
        if page.locator("h1.nameSingle a").count():
            name = page.locator("h1.nameSingle a").first.inner_text().strip()
    except Exception:
        pass
    summary = ""
    try:
        if page.locator("#subject_summary").count():
            summary = page.locator("#subject_summary").first.inner_text().strip()
    except Exception:
        pass
    return {"name_bgm": name, "infobox": infobox, "summary": summary}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uid", required=True)
    ap.add_argument("--types", default="2,3")
    ap.add_argument("--out", default=".tmp/bgm_raw_full.json")
    ap.add_argument("--profile", default=".tmp/bgm_login")
    ap.add_argument("--delay", type=float, default=0.35)
    ap.add_argument("--wait", type=int, default=900, help="等待登录的最长秒数")
    args = ap.parse_args()

    types = [int(t) for t in args.types.split(",") if t.strip()]

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            args.profile, channel="msedge", headless=False,
            args=["--no-first-run", "--no-default-browser-check"],
            viewport={"width": 1100, "height": 820},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(f"{BASE}/login", timeout=60000, wait_until="domcontentloaded")
        write_status("WAITING_LOGIN 窗口已打开，请在浏览器里登录 Bangumi")

        deadline = time.time() + args.wait
        st = {"ok": False, "detail": ""}
        while time.time() < deadline:
            time.sleep(4)
            st = check_login(page)
            if st["ok"]:
                write_status(f"LOGIN_OK 已登录（探测：{st['detail']}）")
                break
            write_status(f"WAITING_LOGIN 尚未登录（{st['detail']}）…")
        else:
            write_status("TIMEOUT 等待登录超时，未执行抓取")
            ctx.close()
            return

        # 登录后回到站点，确保会话上下文就绪
        page.goto(f"{BASE}/user/{args.uid}", timeout=60000, wait_until="domcontentloaded")

        result = {
            "uid": args.uid,
            "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "logged_in": True,
            "types": {str(t): COLLECT_TYPES.get(t, str(t)) for t in types},
            "collections": {},
        }

        all_items = {}
        for t in types:
            res = fetch_list(page, args.uid, 4, t)
            if "error" in res:
                write_status(f"ERROR 类型 {t} 拉取失败: HTTP {res['error']}")
                continue
            write_status(f"LIST {COLLECT_TYPES.get(t, t)}: {res['total']} 条")
            result["collections"][str(t)] = {"label": COLLECT_TYPES.get(t, str(t)), "total": res["total"]}
            for it in res["data"]:
                if it["id"] not in all_items:
                    it["collect_type"] = t
                    all_items[it["id"]] = it

        write_status(f"SUBJECTS 开始抓取 {len(all_items)} 个条目详情 …")
        ok = missing = via_html = 0
        for i, (sid, it) in enumerate(all_items.items(), 1):
            r = fetch_subject(page, sid)
            if r.get("status") == 200:
                body = r["body"]
                it["status"] = "ok"
                it["source"] = "api"
                it["infobox"] = normalize_infobox(body.get("infobox"))
                it["infobox_raw"] = body.get("infobox") or []
                it["summary"] = (body.get("summary") or "").strip()
                it["name_bgm"] = body.get("name")
                it["name_cn_bgm"] = body.get("name_cn") or ""
                it["date_bgm"] = body.get("date") or ""
                it["platform"] = body.get("platform") or ""
                it["rating"] = (body.get("rating") or {}).get("score") or 0
                it["tags_bgm"] = [x.get("name") for x in (body.get("tags") or []) if x.get("name")]
                ok += 1
            else:
                # API 对未登录/被屏蔽条目返回 404，改抓网页
                page_res = scrape_subject_html(page, sid)
                if page_res:
                    it["status"] = "ok"
                    it["source"] = "html"
                    it["infobox"] = page_res["infobox"]
                    it["infobox_raw"] = []
                    it["summary"] = page_res["summary"]
                    it["name_bgm"] = page_res["name_bgm"] or it.get("name") or ""
                    it["name_cn_bgm"] = it.get("name_cn") or ""
                    it["date_bgm"] = page_res["infobox"].get("发售日") or page_res["infobox"].get("发行日期") or it.get("date") or ""
                    it["platform"] = " / ".join(
                        [v for k, v in page_res["infobox"].items() if "平台" in k]
                    )
                    it["rating"] = 0
                    it["tags_bgm"] = []
                    ok += 1
                    via_html += 1
                else:
                    it["status"] = "missing"
                    it["source"] = "none"
                    it["infobox"] = {}
                    it["summary"] = ""
                    missing += 1
            if i % 10 == 0 or i == len(all_items):
                write_status(f"SUBJECTS {i}/{len(all_items)}  成功 {ok}（网页补 {via_html}）· 失效 {missing}")
            time.sleep(args.delay)

        result["items"] = list(all_items.values())
        result["stats"] = {"total": len(all_items), "ok": ok, "missing": missing}

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        write_status(f"DONE 成功 {ok} / 失效 {missing} → {out}")

        ctx.close()


if __name__ == "__main__":
    main()
