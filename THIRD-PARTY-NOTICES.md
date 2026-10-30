# 第三方组件与素材说明

本文件记录本项目（gal_time / GameTime）对第三方代码、素材与外部服务的实际使用情况，
用于确认 MIT 许可（见 `LICENSE`）可以被完整地适用于本仓库。

审计时间：2026-10-30 ｜ 对应提交：`9115b14` 之后

## 一、结论

**本仓库不包含任何第三方的源代码、字体、图标或图片素材。** 主程序是一个零依赖的单文件 HTML，
所有功能均为手写实现；`tools/` 下的 Python 脚本调用 Playwright，但它是运行时通过 pip 安装的
依赖，不属于本仓库的分发内容。

因此本仓库只受自身 MIT 许可约束，没有额外的开源义务（无 NOTICE 传递、无 copyleft 传染）。

## 二、主程序（`GameTime/index.html`）

| 项目 | 实现方式 | 来源 | 许可 |
| --- | --- | --- | --- |
| Markdown 解析器 | 手写，约 200 行，支持标题/列表/引用/代码块/链接等 | 本项目原创 | MIT |
| 评分占比环状图 | 纯 CSS `conic-gradient` + 内联样式 | 本项目原创 | MIT |
| 最近 7 天柱状图 | 纯 CSS 高度百分比 | 本项目原创 | MIT |
| 图标（导航、按钮） | 手写内联 `<svg>` 路径 | 本项目原创 | MIT |
| 网页图标 favicon | 内联 SVG data URI（`<link rel="icon">`） | 本项目原创 | MIT |
| 字体 | 系统字体栈：`Segoe UI`、`Microsoft YaHei`、`system-ui`、`Georgia`、`Times New Roman` | 操作系统自带，不随仓库分发 | 随 OS 授权 |
| 交互逻辑（计时、存储、导入导出） | 手写原生 JavaScript | 本项目原创 | MIT |

审计方式：检查 `index.html` 中是否存在 `<script src>`、`<link href>`（除 data URI）、`@import`、
CDN 域名（`cdn.` / `unpkg` / `jsdelivr` / `googleapis` 等）以及常见库特征串（marked、highlight.js、
Chart.js、KaTeX、Prism、jQuery、Vue、React、Bootstrap、Tailwind、D3 等），结果均为零命中。

## 三、构建/同步脚本（`tools/`）

仅开发期使用，普通用户运行主程序时不会触发。

| 组件 | 版本要求 | 用途 | 许可证 | 是否随仓库分发 |
| --- | --- | --- | --- | --- |
| Python | 3.8+ | 解释器 | PSF License 2.0 | 否（系统安装） |
| `argparse` / `json` / `re` / `sqlite3` / `difflib` / `pathlib` / `unicodedata` 等 | 标准库 | 参数解析、JSON、正则、文本相似度 | PSF License 2.0 | 否 |
| Playwright（`playwright`，Python 版） | 1.x | 驱动系统 Edge 访问 Bangumi，脚本内 `from playwright.sync_api import sync_playwright` | Apache License 2.0 | 否（`pip install playwright` 自行安装，未打包进本仓库） |

Playwright 采用 Apache-2.0，其义务（保留版权与许可声明、附 NOTICE 文件）只在实际分发其代码时触发。
本仓库不包含 Playwright 的任何源码或二进制，仅在脚本中以 `import` 方式调用，因此无需在此附带其许可全文。
如需查看：<https://github.com/microsoft/playwright/blob/main/LICENSE>。

## 四、运行宿主

| 组件 | 说明 | 许可 |
| --- | --- | --- |
| Microsoft Edge | 启动器通过 `msedge.exe --app=file:///.../index.html` 打开独立窗口，浏览器本身由系统提供 | 专有软件（Microsoft 软件许可条款），不随本仓库分发 |
| Chromium 内核 | Edge 内置，本项目未直接链接或修改 | BSD-3-Clause（由 Microsoft 随 Edge 分发） |

## 五、外部数据（Bangumi）

`tools/bgm_crawl.py` / `bgm_login_crawl.py` 会按用户指定的 UID 读取 Bangumi 的公开收藏与条目信息
（名称、发行、剧本、原画、平台、售价、简介、标签等），写入**用户本机的浏览器 localStorage**。

- 这些数据**不进入本仓库**：`.gitignore` 排除了 `GameTime/profile/`（浏览器用户目录），
  同步结果截图目录 `同步截图/` 也已排除。
- 作品资料的权利归 Bangumi 及其贡献者所有，脚本仅用于个人整理自己的收藏，
  不构成对这些内容的再分发。
- 使用时请遵守 Bangumi 的服务条款与抓取频率限制；脚本默认每个条目间隔 0.35 秒。

## 六、仓库内其他文件

| 文件 | 来源 | 许可 |
| --- | --- | --- |
| `GameTime/app.ico` | 本项目自制（与 favicon 同一套图形） | MIT |
| `界面预览*.png` / `同步截图/*.png` | 本项目运行截图 | MIT（`同步截图/` 仅本地保留，未入库） |
| `GameTime/使用说明.txt` / `README.md` / 本文件 | 本项目撰写 | MIT |

## 七、维护建议

如果以后引入第三方库（例如换成现成的 Markdown 渲染器、图表库或图标集），请同步更新本文件，
并在仓库根目录按需新增对方的许可全文（如 `licenses/xxx-LICENSE.txt`）：

1. 记录组件名、版本、许可证、是否随仓库分发；
2. copyleft 类许可（GPL/AGPL/LGPL）需要评估对整体分发方式的影响；
3. MIT/BSD/Apache-2.0 类只需保留版权声明，Apache-2.0 还需保留其 NOTICE。
