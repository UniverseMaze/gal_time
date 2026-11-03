#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 UniverseMaze
"""
GameTime 桌面启动器（打包成 GameTime.exe 的源码）。

职责很单一：找到同目录的 index.html，用系统里的 Edge / Chrome 以「应用窗口」方式打开，
并继续使用同目录下的 profile/ 作为用户数据目录 —— 这样打包成 exe 之后，
原有计时记录、封面、评分、评论全部原地可读，不需要迁移。

参数与 启动游戏计时器.vbs 完全一致，两者可以并存，生成的 profile 也是同一个。
"""
import ctypes
import os
import subprocess
import sys

APP_NAME = "GameTime · 游戏计时器"

# 浏览器候选：优先 Edge（Windows 11 自带），其次 Chrome
BROWSERS = [
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
]

# 与 VBS 启动器保持一致：独立窗口、独立 profile、关掉后台联网与更新
BROWSER_FLAGS = [
    "--no-first-run",
    "--no-default-browser-check",
    "--no-service-autorun",
    "--disable-component-update",
    "--disable-background-networking",
    "--disable-sync",
    "--disk-cache-size=52428800",
    "--window-size=1300,900",
]

MB_ICONERROR = 0x10
MB_ICONINFORMATION = 0x40

# 设置环境变量 GAMETIME_LOG=<文件路径> 可输出启动诊断日志（排查「双击没反应」时用）
LOG_PATH = os.environ.get("GAMETIME_LOG", "")


def log(msg):
    if not LOG_PATH:
        return
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def base_dir():
    """打包后取 exe 所在目录，开发时取脚本所在目录"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(os.path.dirname(__file__)))


def alert(text, flags=MB_ICONERROR):
    try:
        ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, flags)
    except Exception:
        pass


def find_browser():
    for pattern in BROWSERS:
        path = os.path.expandvars(pattern)
        if os.path.isfile(path):
            return path
    return None


def locate_app(base):
    """返回 (index.html 绝对路径, profile 目录)"""
    html = os.path.join(base, "index.html")
    if os.path.isfile(html):
        return html, os.path.join(base, "profile")
    # exe 放在仓库根目录时，自动往 GameTime/ 里找一层
    nested = os.path.join(base, "GameTime", "index.html")
    if os.path.isfile(nested):
        return nested, os.path.join(base, "GameTime", "profile")
    return None, None


def main():
    base = base_dir()
    log("[start] exe_dir=%s frozen=%s" % (base, getattr(sys, "frozen", False)))
    html, profile = locate_app(base)

    if not html:
        log("[error] index.html not found under %s" % base)
        alert(
            "找不到程序文件 index.html。\n\n"
            "请把 GameTime.exe 放在 index.html 同一个文件夹里"
            "（也就是 GameTime 目录）再运行。\n\n"
            "当前所在目录：\n" + base
        )
        return 1

    browser = find_browser()
    log("[found] html=%s profile=%s browser=%s" % (html, profile, browser))
    if not browser:
        alert(
            "没有找到 Microsoft Edge 或 Google Chrome。\n\n"
            "本程序需要一个基于 Chromium 的浏览器作为运行环境。\n"
            "Windows 11 自带 Edge，如果你卸载过，请重新安装。\n\n"
            "也可以直接双击 index.html 用默认浏览器打开（但数据目录会不同）。"
        )
        return 1

    os.makedirs(profile, exist_ok=True)
    url = "file:///" + os.path.abspath(html).replace("\\", "/")
    args = [browser, "--app=" + url, "--user-data-dir=" + profile] + BROWSER_FLAGS

    # 脱离父进程：启动器立刻退出，浏览器继续独立运行
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    try:
        p = subprocess.Popen(
            args,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
        log("[spawn] pid=%s" % p.pid)
    except OSError as e:
        log("[error] spawn failed: %s" % e)
        alert("启动浏览器失败：\n%s\n\n浏览器路径：\n%s" % (e, browser))
        return 1
    log("[done]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
