#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 UniverseMaze
"""
把 bgm_crawl.py 抓到的条目信息，按名称匹配进 GameTime 本地存档。

用法:
    # 1. 只看匹配结果，不写任何文件
    python tools/match_local.py --bgm .tmp/bgm_raw.json --local .tmp/local_db.json --report

    # 2. 生成合并后的存档 JSON（可用程序里的「导入备份」导入）
    python tools/match_local.py --bgm .tmp/bgm_raw.json --local .tmp/local_db.json \
        --out .tmp/gametime_merged.json

匹配策略（从强到弱）:
    1. 归一化后精确命中：本地名 == bgm 原名 / 中文名 / 任一别名
    2. 去括号副标题后命中：如 "9-nine- 新章" vs "9-nine-新章"
    3. 互含关系：一方包含另一方且长度接近
    4. 仍认不出的，列在 unmatched 里，可用 --map 手工指定

字段映射（bgm infobox 的 key → 本地 info 字段）:
    发行→publisher  开发→developer  剧本→scenario  原画→art  背景→background
    平台→platforms  游戏类型→genre  游戏引擎→engine  游玩人数→players
    发行日期→release  售价→price    简介→synopsis   别名→alias
"""
import argparse
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

FIELD_MAP = {
    "发行": "publisher",
    "开发": "developer",
    "剧本": "scenario",
    "原画": "art",
    "背景": "background",
    "平台": "platforms",
    "游戏类型": "genre",
    "游戏引擎": "engine",
    "游玩人数": "players",
    "发行日期": "release",
    "售价": "price",
}

PUNCT = r"[\s\-_~·・:：!！?？,，.。'\"“”‘’()（）\[\]【】/\\|&＆+＋=＝★☆♪～〜—–]"


def norm(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", str(s)).lower()
    return re.sub(PUNCT, "", s)


def strip_brackets(s):
    """去掉括号里的副标题后归一化，用于 '兰斯6 -赛斯崩坏-' 这类"""
    s2 = re.sub(r"[（(\[【].*?[)）\]】]", "", s or "")
    return norm(s2)


def alias_overflow(box):
    """网页解析时，infobox 里「别名」下面若干行的链接会被拆成独立的空值键。

    例如 末世孤雄 Vol 3 的 infobox 里会出现：
        '行尸走肉横行的世界只有我不被袭击 Vol 3': ''
    这些其实都是别名，需要回收，否则会被当成无效字段丢掉。
    """
    known = set(FIELD_MAP) | {"中文名", "链接", "官方网站", "别名"}
    out = []
    for k, v in box.items():
        if k in known:
            continue
        if isinstance(v, str) and not v.strip() and k.strip():
            out.append(k.strip())
    return out


def aliases_of(item):
    """一个 bgm 条目的所有可匹配名称"""
    names = [item.get("name"), item.get("name_cn"), item.get("name_bgm"), item.get("name_cn_bgm")]
    box = item.get("infobox") or {}
    extra = box.get("别名")
    if isinstance(extra, list):
        names.extend(extra)
    elif isinstance(extra, str) and extra:
        names.extend(re.split(r"[/、]", extra))
    names.extend(alias_overflow(box))
    cn = box.get("中文名")
    if isinstance(cn, str) and cn:
        names.append(cn)
    out, seen = [], set()
    for n in names:
        n = (n or "").strip()
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def match_score(local_name, item):
    """返回 (分数, 命中方式)。0 表示不匹配"""
    ln = norm(local_name)
    lb = strip_brackets(local_name)
    best = (0.0, "")
    for al in aliases_of(item):
        an = norm(al)
        ab = strip_brackets(al)
        if not an:
            continue
        if ln == an:
            return (1.0, "精确")
        if lb and lb == ab:
            return (0.96, "去括号命中")
        # 互含：短的是长的子串，且长度差不超过 6 个字
        if lb and ab and (lb in ab or ab in lb) and abs(len(lb) - len(ab)) <= 6:
            score = 0.86 - abs(len(lb) - len(ab)) * 0.01
            if score > best[0]:
                best = (score, "包含")
        ratio = SequenceMatcher(None, lb or ln, ab or an).ratio()
        if ratio > 0.82 and ratio > best[0]:
            best = (ratio * 0.9, "相似")
    return best


def split_lines(v):
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [x.strip() for x in re.split(r"[、,，/]", v) if x.strip()]
    return []


def build_info(item, local_name):
    """把 bgm infobox 转成本地 info 结构（只返回有值的字段）"""
    box = item.get("infobox") or {}
    info = {}
    for bgm_key, local_key in FIELD_MAP.items():
        raw = box.get(bgm_key)
        if raw in (None, "", []):
            continue
        if local_key == "platforms":
            vals = split_lines(raw)
            if vals:
                info["platforms"] = vals
        elif local_key == "price":
            vals = split_lines(raw) if isinstance(raw, list) else [str(raw)]
            vals = [v for v in vals if v]
            if vals:
                info["price"] = "\n".join(vals)
        else:
            val = "、".join(split_lines(raw)) if isinstance(raw, list) else str(raw).strip()
            if val:
                info[local_key] = val

    # 发行日期兜底用 subject.date
    if not info.get("release") and item.get("date"):
        info["release"] = item["date"]

    # 别名：原名 / 中文名 / infobox 别名，去掉和本地名重复的
    cand = aliases_of(item)
    seen_local = norm(local_name)
    alias = []
    for a in cand:
        if norm(a) and norm(a) != seen_local and a not in alias:
            alias.append(a)
    if alias:
        info["alias"] = "\n".join(alias[:4])

    if item.get("summary"):
        info["synopsis"] = item["summary"]
    return info


TAG_DROP = {
    "pc", "windows", "游戏", "日本", "汉化", "中文", "ns", "ps4", "ps5",
    "switch", "android", "ios", "模拟器",
    # bgm 用户标签里的技术性品类：和下面统一的品类标签重复，过滤掉
    "galgame", "gal", "avg", "adv", "视觉小说", "ノベル",
}
MIN_TAG_FREQ = 2      # bgm 用户标签在整个收藏里至少出现这么多次才采用，滤掉一次性梗标签


def canon_genre(genre_text):
    """把各家五花八门的「游戏类型」收敛成统一的品类标签"""
    t = (genre_text or "").lower()
    if not t.strip():
        return ""
    if "rpg" in t or "角色扮演" in genre_text:
        return "RPG"
    if "音乐" in genre_text or "music" in t:
        return "音乐"
    if "动作" in genre_text or "action" in t:
        return "动作"
    if "战略" in genre_text or "模拟" in genre_text or "slg" in t:
        return "策略模拟"
    if ("视觉小说" in genre_text or "novel" in t or "avg" in t
            or "adv" in t or "ノベル" in genre_text or "文字" in genre_text):
        return "视觉小说"
    return genre_text.strip()[:14]


def bad_tag(t, item):
    t = (t or "").strip()
    if not t or len(t) > 14:
        return True
    if re.fullmatch(r"[\d\s\-\.]+", t):          # 2016、Vol.3 这类纯数字
        return True
    if t.lower() in TAG_DROP:
        return True
    # 和作品名 / 别名重复的标签没意义
    keys = {norm(a) for a in aliases_of(item)}
    if norm(t) in keys:
        return True
    return False


def build_tags(item, local_name, freq=None):
    """标签 = 统一品类 + 出现频次较高的 bgm 主题标签（最多 6 个）

    freq 是全局标签频次表：只保留至少出现 MIN_TAG_FREQ 次的标签，
    这样能滤掉「蘑菇使いの坑」这类只出现一次的玩梗标签。
    """
    box = item.get("infobox") or {}
    freq = freq or {}
    out, seen = [], set()

    def add(t, is_genre=False):
        t = (t or "").strip()
        key = norm(t)
        if not key or key in seen:
            return
        # 品类标签只做长度/重复校验，不套用 bgm 标签的黑名单
        if is_genre:
            if len(t) > 14:
                return
        elif bad_tag(t, item):
            return
        seen.add(key)
        out.append(t)

    # 先放品类，保证每款至少有一个可用标签
    genre_raw = "、".join(split_lines(box.get("游戏类型")))
    add(canon_genre(genre_raw), is_genre=True)

    for t in (item.get("tags_bgm") or [])[:12]:
        t = (t or "").strip()
        if freq.get(t, 0) >= MIN_TAG_FREQ:
            add(t)
    return out[:6]


def merge_info(existing, incoming, overwrite=False):
    """空字段才填；overwrite=True 时用新值覆盖非空字段"""
    out = dict(existing or {})
    filled = {}
    for k, v in incoming.items():
        cur = out.get(k)
        empty = (cur is None) or (cur == "") or (cur == [])
        if empty:
            out[k] = v
            filled[k] = v
        elif overwrite:
            out[k] = v
            filled[k] = v
    return out, filled


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bgm", default=".tmp/bgm_raw.json")
    ap.add_argument("--local", default=".tmp/local_db.json")
    ap.add_argument("--out", help="输出合并后的存档 JSON")
    ap.add_argument("--report", action="store_true", help="打印匹配报告")
    ap.add_argument("--overwrite", action="store_true", help="覆盖本地已有的非空字段")
    ap.add_argument("--threshold", type=float, default=0.86, help="认定匹配的最低分")
    ap.add_argument("--map", help='手工映射 JSON: {"本地名":"bgm_id"}')
    ap.add_argument("--no-tags", action="store_true", help="不填充标签（默认会用品类与 bgm 标签生成）")
    args = ap.parse_args()

    bgm = json.loads(Path(args.bgm).read_text(encoding="utf-8"))
    db = json.loads(Path(args.local).read_text(encoding="utf-8"))
    manual = json.loads(Path(args.map).read_text(encoding="utf-8")) if args.map else {}

    items = bgm["items"]
    by_id = {it["id"]: it for it in items}

    # 全局标签频次：用于滤掉一次性玩梗标签
    from collections import Counter
    tag_freq = Counter()
    for it in items:
        for t in (it.get("tags_bgm") or [])[:12]:
            tag_freq[(t or "").strip()] += 1

    matched, ambiguous, unmatched = [], [], []
    used_ids = set()

    for g in db["games"]:
        name = g["name"]
        # 手工映射优先
        if name in manual:
            sid = manual[name]
            it = by_id.get(sid)
            if it:
                matched.append((g, it, 1.0, "手工"))
                used_ids.add(sid)
                continue
        scored = sorted(((match_score(name, it), it) for it in items),
                        key=lambda x: x[0][0], reverse=True)
        if not scored:
            unmatched.append((g, None))
            continue
        (score, how), it = scored[0]
        if score >= args.threshold:
            matched.append((g, it, score, how))
            used_ids.add(it["id"])
        elif score >= 0.6:
            ambiguous.append((g, it, score, how))
        else:
            unmatched.append((g, None))

    if args.report:
        print(f"=== 匹配结果: 强匹配 {len(matched)} / 待确认 {len(ambiguous)} / 未匹配 {len(unmatched)} ===\n")
        print("【已匹配】")
        for g, it, sc, how in matched:
            flag = "" if it["status"] == "ok" else "  (条目已失效，只有名称/日期)"
            print(f"  {g['name']:<28} → {it['id']:>7} {it.get('name_cn') or it.get('name'):<30} {sc:.2f} {how}{flag}")
        if ambiguous:
            print("\n【待确认】分数不够高，默认不动")
            for g, it, sc, how in ambiguous:
                print(f"  {g['name']:<28} ? {it['id']:>7} {it.get('name_cn') or it.get('name'):<30} {sc:.2f} {how}")
        if unmatched:
            print("\n【未匹配】本地有、bgm 列表里找不到")
            for g, _ in unmatched:
                print(f"  {g['name']}")
        not_used = [it for it in items if it["id"] not in used_ids]
        if not_used:
            print(f"\n【bgm 有但本地没对应】{len(not_used)} 条")
            for it in not_used:
                print(f"  {it['id']:>7} {it.get('name_cn') or it.get('name')}")

    if args.out:
        stat = {"info_filled": 0, "fields": 0, "skipped": 0, "tags_filled": 0}
        detail = []
        for g, it, sc, how in matched:
            incoming = build_info(it, g["name"])
            if not incoming:
                stat["skipped"] += 1
                continue
            merged, filled = merge_info(g.get("info"), incoming, args.overwrite)
            if filled:
                g["info"] = merged
                stat["info_filled"] += 1
                stat["fields"] += len(filled)
                detail.append({"game": g["name"], "bgm_id": it["id"], "fields": sorted(filled.keys())})

            # 标签：只在本地还没有标签时生成，不覆盖用户自己打的
            if not args.no_tags and not (g.get("tags") or []):
                tags = build_tags(it, g["name"], tag_freq)
                if tags:
                    g["tags"] = tags
                    stat["tags_filled"] += 1

        Path(args.out).write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n写出 {args.out}: 更新信息 {stat['info_filled']} 款 / {stat['fields']} 个字段"
              f"，填充标签 {stat['tags_filled']} 款，跳过 {stat['skipped']} 款")
        for d in detail[:60]:
            print(f"  {d['game']:<28} ← {d['bgm_id']:>7}  {', '.join(d['fields'])}")


if __name__ == "__main__":
    main()
