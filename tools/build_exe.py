#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 UniverseMaze
"""
用 Nuitka 把 tools/launcher.py 编译成 GameTime/GameTime.exe（standalone 目录模式）。

为什么用 Nuitka 而不是 PyInstaller：
    PyInstaller 的单文件 exe 启动时会把运行库解包到临时目录（%TEMP%\\_MEIxxxx），
    这一步会被火绒 HIPS / 企业终端管控等安全软件拦截，导致双击时报
    「Could not create temporary directory!」而无法启动。
    Nuitka 把 Python 代码真正编译成原生机器码，standalone 模式下运行时
    完全不解包、不建临时目录，因此不会被这类安全软件拦截。

用法:
    python tools/build_exe.py

产物:
    GameTime/GameTime.exe（约 5 MB）+ 同目录下若干 *.pyd / *.dll 运行时依赖
    （约 8 MB），必须一起分发。index.html / profile 仍放在同一目录。

构建依赖（仅构建时需要，用户端不需要）:
    1. Python 3.12（Nuitka 的 --mingw64 不支持 Python 3.13+）:
       winget install Python.Python.3.12
    2. Nuitka:
       <python312> -m pip install nuitka
    3. MinGW-w64（WinLibs，Nuitka 会按需自动下载到本机缓存，或手动放置）:
       Nuitka 需要精确版本 winlibs gcc，首次编译会自动下载（需能访问 GitHub）。
       如需手动指定，参照本脚本底部的 CACHE 说明。
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.path.join(ROOT, "tools", "launcher.py")
ICON = os.path.join(ROOT, "GameTime", "app.ico")
DIST = os.path.join(ROOT, "GameTime")
WORK = os.path.join(ROOT, ".tmp", "nuitka")

# Nuitka 用的 Python（3.12，因为 3.13 不能用 --mingw64）
PY312 = r"C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe"

# MinGW 所在目录（加入 PATH 供 Nuitka/Scons 使用；Nuitka 实际会用它自己的缓存 gcc）
MINGW_BIN = r"D:\tools\mingw64\bin"


def main():
    for f in (ENTRY, ICON):
        if not os.path.isfile(f):
            print("缺少文件:", f, file=sys.stderr)
            return 1
    if not os.path.isfile(PY312):
        print("未找到 Python 3.12:", PY312, file=sys.stderr)
        print("请先安装: winget install Python.Python.3.12", file=sys.stderr)
        return 1

    # 清掉上一次的中间产物
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)

    # 让 Nuitka/Scons 能找到 gcc
    env = dict(os.environ)
    env["PATH"] = MINGW_BIN + os.pathsep + env.get("PATH", "")

    cmd = [
        PY312, "-m", "nuitka",
        "--mingw64",
        "--standalone",
        "--assume-yes-for-downloads",
        "--disable-ccache",          # ccache 在 8.3 短路径下会写缓存失败
        "--windows-console-mode=disable",
        "--windows-icon-from-ico=" + ICON,
        "--output-dir=" + WORK,
        "--output-filename=GameTime.exe",
        ENTRY,
    ]
    print("执行:", " ".join(cmd))
    r = subprocess.run(cmd, env=env)
    if r.returncode != 0:
        print("编译失败，退出码", r.returncode, file=sys.stderr)
        return r.returncode

    # 产物在 dist 子目录，复制到 GameTime/（与 index.html、profile 并列）
    src = os.path.join(WORK, "launcher.dist")
    exe = os.path.join(src, "GameTime.exe")
    if not os.path.isfile(exe):
        print("未生成 exe:", exe, file=sys.stderr)
        return 1

    for name in os.listdir(src):
        s = os.path.join(src, name)
        d = os.path.join(DIST, name)
        if os.path.isdir(s):
            if os.path.exists(d):
                shutil.rmtree(d, ignore_errors=True)
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)

    total = sum(os.path.getsize(os.path.join(DIST, f))
                for f in os.listdir(DIST)
                if os.path.isfile(os.path.join(DIST, f))
                and f.endswith((".exe", ".pyd", ".dll")))
    print("\n完成: %s（exe %d KB，连同运行时依赖共 %.1f MB）"
          % (exe, os.path.getsize(exe) // 1024, total / 1024 / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
