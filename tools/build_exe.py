#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 UniverseMaze
"""
把 tools/launcher.py 打包成 GameTime/GameTime.exe（单文件、无控制台窗口、带程序图标）。

用法:
    python tools/build_exe.py

产物:
    GameTime/GameTime.exe    约 8-12 MB，与 index.html 放同一目录即可独立运行

依赖（仅构建时需要，用户端不需要）:
    pip install pyinstaller
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.path.join(ROOT, "tools", "launcher.py")
ICON = os.path.join(ROOT, "GameTime", "app.ico")
VERSION = os.path.join(ROOT, "tools", "version_info.txt")
DIST = os.path.join(ROOT, "GameTime")
WORK = os.path.join(ROOT, ".tmp", "pyinstaller")


def main():
    for f in (ENTRY, ICON, VERSION):
        if not os.path.isfile(f):
            print("缺少文件:", f, file=sys.stderr)
            return 1

    # 清掉上一次的中间产物，避免缓存了旧脚本
    for d in (WORK, os.path.join(ROOT, "build")):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        # 关键：单文件模式默认把运行时解包到系统临时目录（%TEMP%\\_MEIxxxx），
        # 在部分机器上（临时目录被安全软件/策略限制）会导致
        # 「Could not create temporary directory!」而无法启动。
        # 指定 "." 后改为解包到 exe 所在目录，绕开系统临时目录；
        # 该目录本来就需要可写（profile/ 就写在这里），因此不会引入新的限制。
        "--runtime-tmpdir", ".",
        "--noconsole",
        "--noupx",
        "--clean",
        "--name", "GameTime",
        "--icon", ICON,
        "--version-file", VERSION,
        "--distpath", DIST,
        "--workpath", WORK,
        "--specpath", WORK,
        "--log-level", "WARN",
        ENTRY,
    ]
    print("执行:", " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print("打包失败，退出码", r.returncode, file=sys.stderr)
        return r.returncode

    exe = os.path.join(DIST, "GameTime.exe")
    if not os.path.isfile(exe):
        print("未生成 exe:", exe, file=sys.stderr)
        return 1
    print("\n完成: %s（%.1f MB）" % (exe, os.path.getsize(exe) / 1024 / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
